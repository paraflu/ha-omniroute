"""Coordinator-backed OmniRoute sensors."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    known_codex = set()
    async_add_entities([OmniRouteHealthSensor(coordinator), OmniRouteVersionSensor(coordinator, 'version'),
                        OmniRouteVersionSensor(coordinator, 'latest_version'), OmniRouteVersionSensor(coordinator, 'update_available')])

    def discover():
        new = set(coordinator.data.get("quotas", {})) - known
        known.update(new)
        if new:
            async_add_entities([OmniRouteQuotaSensor(coordinator, key) for key in sorted(new)])
        new_codex = set(coordinator.data.get('codex_5h', {})) - known_codex
        known_codex.update(new_codex)
        if new_codex:
            async_add_entities([OmniRouteCodexUsageSensor(coordinator, key) for key in sorted(new_codex)])

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
        account = self.coordinator.data.get('accounts', {}).get(self.provider_name, {})
        if account.get('provider') == 'codex':
            return self.coordinator.data.get('codex_weekly', {}).get(self.provider_name, {}).get('remaining_percent')
        return self.coordinator.data.get("quotas", {}).get(self.provider_name)
    @property
    def extra_state_attributes(self):
        account = dict(self.coordinator.data.get("accounts", {}).get(self.provider_name, {}))
        if account.get('provider') == 'codex':
            # Generic endpoint fields are fallback values, not upstream quota.
            for key in ('quotaUsed', 'quotaTotal', 'resetAt'):
                account.pop(key, None)
            account.update(self.coordinator.data.get('codex_weekly', {}).get(self.provider_name, {}))
            account['quota_window'] = 'weekly'
        return account
    @property
    def available(self):
        return super().available and self.provider_name in self.coordinator.data.get("quotas", {})

class OmniRouteVersionSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key=key
        self._attr_name={'version':'OmniRoute Version','latest_version':'OmniRoute Latest Version',
                         'update_available':'OmniRoute Update Available'}[key]
        self._attr_unique_id=f'{DOMAIN}_{coordinator.config_entry.entry_id}_{key}'
    @property
    def native_value(self):
        value=self.coordinator.data.get(self.key)
        if self.key=='update_available' and value is not None:
            return 'yes' if value else 'no'
        return value

class OmniRouteCodexUsageSensor(CoordinatorEntity, SensorEntity):
    _attr_native_unit_of_measurement='%'
    def __init__(self, coordinator, account_id):
        super().__init__(coordinator)
        self.account_id=account_id
        account=coordinator.data.get('accounts',{}).get(account_id,{})
        self._attr_name=f"OmniRoute Codex Usage 5h {account.get('name',account_id)}"
        self._attr_unique_id=f'{DOMAIN}_{coordinator.config_entry.entry_id}_codex_5h_{account_id}'
    @property
    def native_value(self):
        return self.coordinator.data.get('codex_5h',{}).get(self.account_id,{}).get('used_percent')
    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get('codex_5h',{}).get(self.account_id,{})
