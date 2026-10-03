import logging
import aiohttp
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.exceptions import ConfigEntryAuthFailed
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class OmniRouteDataCoordinator(DataUpdateCoordinator):
    """Coordinator for OmniRoute API data."""

    def __init__(self, hass, host, api_key, config_entry=None):
        self.host = host.rstrip("/")
        self.api_key = api_key
        super().__init__(
            hass,
            _LOGGER.name,
            name="OmniRoute",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
            config_entry=config_entry,
        )

    async def _async_update_data(self):
        """Fetch data from API."""
        data = {"health": "unknown", "quotas": {}}
        
        async with aiohttp.ClientSession() as session:
            # 1. Health check (Public)
            try:
                async with session.get(f"{self.host}/api/health", timeout=10) as resp:
                    if resp.status == 200:
                        data["health"] = "healthy"
                    else:
                        data["health"] = f"unhealthy ({resp.status})"
            except Exception as e:
                _LOGGER.error("OmniRoute health check failed: %s", e)
                data["health"] = "unavailable"

            # 2. Quota (Authenticated)
            headers = {"Authorization": f"Bearer {self.api_key}"}
            try:
                async with session.get(f"{self.host}/api/usage/quota", headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        payload = await resp.json()
                        providers = payload.get("providers")
                        if isinstance(providers, dict):
                            for p_name, p_data in providers.items():
                                val = p_data.get("quota", "unknown")
                                data["quotas"][p_name] = val
                        else:
                            _LOGGER.warning("OmniRoute quota payload has unexpected format: %s", payload)
                    elif resp.status == 403:
                        raise ConfigEntryAuthFailed("Invalid API Key or insufficient permissions for usage endpoints")
                    elif resp.status == 401:
                        raise ConfigEntryAuthFailed("Authentication failed: Unauthorized")
                    else:
                        _LOGGER.error("OmniRoute quota API returned error %s", resp.status)
            except aiohttp.ClientError as e:
                _LOGGER.error("OmniRoute quota request failed: %s", e)
            except ConfigEntryAuthFailed:
                raise
            except Exception as e:
                _LOGGER.error("Unexpected error fetching OmniRoute quota: %s", e)

        return data
