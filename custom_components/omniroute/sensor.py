"""Coordinator-backed OmniRoute sensors."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    async_add_entities([OmniRouteHealthSensor(coordinator)])

    def discover():
        new = set(coordinator.data.get("quotas", {})) - known
        known.update(new)
        if new:
            async_add_entities([OmniRouteQuotaSensor(coordinator, key) for key in sorted(new)])

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))

class OmniRouteHealthSensor(CoordinatorEntity, SensorEntity):
    _attr_name = "OmniRoute Health"
    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.config_entry.entry_id}_health"
    @property
    def native_value(self):
        return self.coordinator.data.get("health")

class OmniRouteQuotaSensor(CoordinatorEntity, SensorEntity):
    _attr_native_unit_of_measurement = "%"
    def __init__(self, coordinator, provider_name):
        super().__init__(coordinator)
        self.provider_name = provider_name
        account = coordinator.data.get("accounts", {}).get(provider_name, {})
        self._attr_name = f"OmniRoute Remaining {account.get('provider', provider_name)} {account.get('name', '')}".strip()
        self._attr_unique_id = f"{DOMAIN}_{coordinator.config_entry.entry_id}_quota_{provider_name}"
    @property
    def native_value(self):
        return self.coordinator.data.get("quotas", {}).get(self.provider_name)
    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get("accounts", {}).get(self.provider_name, {})
    @property
    def available(self):
        return super().available and self.provider_name in self.coordinator.data.get("quotas", {})
