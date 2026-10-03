import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed
from custom_components.omniroute import async_setup_entry, async_unload_entry
from custom_components.omniroute.config_flow import OmniRouteConfigFlow
from custom_components.omniroute.coordinator import OmniRouteDataCoordinator


def test_sensor_import_and_coordinator_subscription():
    sensor = importlib.import_module('custom_components.omniroute.sensor')
    assert issubclass(sensor.OmniRouteHealthSensor, CoordinatorEntity)
    assert issubclass(sensor.OmniRouteQuotaSensor, CoordinatorEntity)


def test_options_constructs_without_readonly_assignment():
    assert OmniRouteConfigFlow.async_get_options_flow(MagicMock()) is not None


@pytest.mark.asyncio
async def test_unload_cleans_data():
    hass = MagicMock()
    hass.data = {'omniroute': {'entry1': object()}}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await async_unload_entry(hass, SimpleNamespace(entry_id='entry1'))
    assert 'entry1' not in hass.data['omniroute']


@pytest.mark.asyncio
async def test_setup_passes_url_and_entry():
    hass = MagicMock(); hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    entry = SimpleNamespace(entry_id='entry1', data={'url':'https://example.org','api_key':'test'})
    with patch('custom_components.omniroute.OmniRouteDataCoordinator') as cls:
        cls.return_value.async_config_entry_first_refresh = AsyncMock()
        assert await async_setup_entry(hass, entry)
        assert cls.call_args.args[1] == 'https://example.org'
        assert cls.call_args.kwargs['config_entry'] is entry
    entry.async_on_unload = MagicMock()


@pytest.mark.asyncio
async def test_real_quota_list_keeps_accounts_and_attributes():
    hass = MagicMock()
    health = AsyncMock(); health.status=200; health.__aenter__.return_value=health
    quota = AsyncMock(); quota.status=200; quota.__aenter__.return_value=quota
    quota.json.return_value={'providers':[{'connectionId':'a','provider':'codex','name':'one','percentRemaining':37,'quotaTotal':None,'tokenStatus':'valid'}, {'connectionId':'b','provider':'codex','name':'two','percentRemaining':62}]}
    with patch('aiohttp.ClientSession.get', side_effect=[health,quota,health,health]):
        c=OmniRouteDataCoordinator(hass,'https://example.org','test')
        data=await c._async_update_data()
    assert data['quotas']=={'a':37,'b':62}
    assert data['accounts']['a']['tokenStatus']=='valid'


@pytest.mark.asyncio
async def test_http_failure_is_update_failed():
    health=AsyncMock(); health.status=200; health.__aenter__.return_value=health
    quota=AsyncMock(); quota.status=503; quota.__aenter__.return_value=quota
    with patch('aiohttp.ClientSession.get', side_effect=[health,quota,health,health]):
        c=OmniRouteDataCoordinator(MagicMock(),'https://example.org','test')
        with pytest.raises(UpdateFailed): await c._async_update_data()


def test_metadata_uses_actual_repository():
    root=Path(__file__).parents[1]
    manifest=json.loads((root/'custom_components/omniroute/manifest.json').read_text())
    assert manifest['documentation']=='https://github.com/paraflu/ha-omniroute'
    assert manifest['codeowners']==['@paraflu']


@pytest.mark.asyncio
async def test_sensor_discovery_updates_and_instance_ids():
    from custom_components.omniroute.sensor import async_setup_entry as setup_sensors, OmniRouteQuotaSensor
    c = MagicMock()
    c.config_entry = SimpleNamespace(entry_id='first')
    c.data = {'health':'healthy', 'quotas':{'a':37}, 'accounts':{'a':{'provider':'codex'}}}
    c.last_update_success = True
    c.async_add_listener = MagicMock(return_value=lambda: None)
    entry = MagicMock(); entry.entry_id='first'
    hass = MagicMock(); hass.data={'omniroute':{'first':c}}
    add = MagicMock()
    await setup_sensors(hass, entry, add)
    entity = add.call_args.args[0][0]
    assert entity.native_value == 37
    c.data['quotas']['a']=62
    assert entity.native_value == 62
    c.data['quotas']['b']=20
    c.async_add_listener.call_args.args[0]()
    assert add.call_args.args[0][0].provider_name=='b'
    c.config_entry=SimpleNamespace(entry_id='second')
    assert OmniRouteQuotaSensor(c,'a').unique_id != entity.unique_id


@pytest.mark.asyncio
async def test_options_updates_identity_and_reloads():
    entry=SimpleNamespace(entry_id='first',data={'url':'https://old.example'})
    hass=MagicMock()
    hass.config_entries.async_get_known_entry.return_value=entry
    hass.config_entries.async_entries.return_value=[entry]
    hass.config_entries.async_reload=AsyncMock(return_value=True)
    flow=OmniRouteConfigFlow.async_get_options_flow(entry)
    flow.hass=hass; flow.handler='first'
    with patch.object(flow,'async_create_entry',return_value={'type':'create_entry'}):
        await flow.async_step_init({'url':'https://new.example/','api_key':'new-test'})
    assert hass.config_entries.async_update_entry.call_args.kwargs['unique_id']=='https://new.example'
    hass.config_entries.async_reload.assert_awaited_once_with('first')
