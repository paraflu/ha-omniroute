"""Manually refresh upstream limits."""
import asyncio
from time import monotonic

import aiohttp
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OmniRouteRefreshButton(hass.data[DOMAIN][entry.entry_id])])


class OmniRouteRefreshButton(ButtonEntity):
    _attr_name = 'OmniRoute Refresh Quotas'
    _attr_icon = 'mdi:refresh'

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f'{DOMAIN}_{coordinator.config_entry.entry_id}_refresh_quotas'
        self._lock = asyncio.Lock()
        self._last_refresh = None

    async def async_press(self):
        if self._lock.locked():
            raise HomeAssistantError('Quota refresh already running')
        async with self._lock:
            if self._last_refresh is not None and monotonic() - self._last_refresh < 60:
                raise HomeAssistantError('Wait 60 seconds between upstream refreshes')
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        f'{self.coordinator.host}/api/usage/provider-limits',
                        headers={'Authorization': f'Bearer {self.coordinator.api_key}'},
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as response:
                        if response.status != 200:
                            raise HomeAssistantError(f'Quota refresh HTTP {response.status}')
                        result = await response.json()
                        if not isinstance(result, dict) or result.get('failed', 0):
                            raise HomeAssistantError('Upstream quota refresh incomplete')
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                    raise HomeAssistantError('Upstream quota refresh request failed') from err
            self._last_refresh = monotonic()
            await self.coordinator.async_request_refresh()
