import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .coordinator import OmniRouteDataCoordinator

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
    
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
