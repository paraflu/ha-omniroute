import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .coordinator import OmniRouteDataCoordinator
from .codex_reset import (
    CONF_RESET_MONITOR, CONF_RESET_NOTIFICATIONS, CONF_RESET_POLL_MINUTES,
    DEFAULT_RESET_POLL_MINUTES, MONITOR_KEY, ResetMonitor,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OmniRoute from a config entry."""
    coordinator = OmniRouteDataCoordinator(
        hass,
        entry.data.get("url", entry.data.get("host")),
        entry.data.get("api_key"),
        config_entry=entry,
    )
    
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.error("Failed to set up OmniRoute: %s", e)
        # Let HA handle ConfigEntryAuthFailed via the coordinator's raise
        raise e
    
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    settings = {**entry.data, **getattr(entry, "options", {})}
    if settings.get(CONF_RESET_MONITOR, False):
        if MONITOR_KEY not in hass.data[DOMAIN]:
            hass.data[DOMAIN][MONITOR_KEY] = ResetMonitor(hass)
        monitor = hass.data[DOMAIN][MONITOR_KEY]
        await monitor.async_add_entry(
            entry.entry_id, settings.get(CONF_RESET_NOTIFICATIONS, True),
            settings.get(CONF_RESET_POLL_MINUTES, DEFAULT_RESET_POLL_MINUTES),
        )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
    if unloaded:
        monitor = hass.data[DOMAIN].get(MONITOR_KEY)
        if monitor is not None:
            await monitor.async_remove_entry(entry.entry_id)
            if not monitor.entries:
                hass.data[DOMAIN].pop(MONITOR_KEY, None)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
