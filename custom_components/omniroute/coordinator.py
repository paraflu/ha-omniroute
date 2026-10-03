"""Poll OmniRoute health and account quotas."""
import asyncio
import logging
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed
from .const import UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class OmniRouteDataCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host, api_key, config_entry=None):
        self.host = host.rstrip("/")
        self.api_key = api_key
        super().__init__(hass, _LOGGER, name="OmniRoute", config_entry=config_entry,
                         update_interval=timedelta(seconds=UPDATE_INTERVAL))

    async def _async_update_data(self):
        data = {"health": "unknown", "quotas": {}, "accounts": {}}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.host}/api/health", timeout=10) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(f"Health endpoint HTTP {resp.status}")
                    data["health"] = "healthy"
                async with session.get(f"{self.host}/api/usage/quota", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=10) as resp:
                    if resp.status in (401, 403):
                        raise ConfigEntryAuthFailed("API key rejected or missing usage permissions")
                    if resp.status != 200:
                        raise UpdateFailed(f"Quota endpoint HTTP {resp.status}")
                    payload = await resp.json()
                providers = payload.get("providers") if isinstance(payload, dict) else None
                if isinstance(providers, list):
                    for account in providers:
                        if not isinstance(account, dict) or not account.get("connectionId"):
                            raise UpdateFailed("Invalid quota account schema")
                        key = account["connectionId"]
                        remaining = account.get("percentRemaining")
                        if remaining is not None and (isinstance(remaining, bool) or not isinstance(remaining, (int, float))):
                            raise UpdateFailed("Invalid remaining percentage")
                        data["quotas"][key] = remaining
                        data["accounts"][key] = {k: account.get(k) for k in ("provider", "name", "quotaUsed", "quotaTotal", "resetAt", "tokenStatus")}
                elif isinstance(providers, dict):
                    for key, account in providers.items():
                        if not isinstance(account, dict):
                            raise UpdateFailed("Invalid legacy quota schema")
                        data["quotas"][key] = account.get("quota")
                else:
                    raise UpdateFailed("Unexpected quota schema (providers must be list or object)")
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise UpdateFailed("OmniRoute request or JSON decoding failed") from err
        return data
