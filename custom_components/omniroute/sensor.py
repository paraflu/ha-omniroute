from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityPlatform
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: EntityPlatform.AddEntities):
    """Set up sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    # Health sensor
    entities.append(OmniRouteHealthSensor(coordinator))
    
    # Dynamic quota sensors based on coordinator data
    quotas = coordinator.data.get("quotas", {})
    for provider_name in quotas:
        entities.append(OmniRouteQuotaSensor(coordinator, provider_name))
        
    async_add_entities(entities)

class OmniRouteHealthSensor(SensorEntity):
    """Sensor for OmniRoute health status."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        super().__init__()

    @property
    def name(self):
        return "OmniRoute Health"

    @property
    def state(self):
        return self.coordinator.data.get("health", "unknown")

    @property
    def unique_id(self):
        return f"{DOMAIN}_health"

class OmniRouteQuotaSensor(SensorEntity):
    """Sensor for OmniRoute provider quotas."""

    def __init__(self, coordinator, provider_name):
        self.coordinator = coordinator
        self.provider_name = provider_name
        super().__init__()

    @property
    def name(self):
        return f"OmniRoute Quota {self.provider_name.capitalize()}"

    @property
    def state(self):
        quotas = self.coordinator.data.get("quotas", {})
        return quotas.get(self.provider_name, "unknown")

    @property
    def unique_id(self):
        return f"{DOMAIN}_quota_{self.provider_name}"
