import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_API_KEY, CONF_URL
from custom_components.omniroute.config_flow import OmniRouteConfigFlow
from custom_components.omniroute.coordinator import OmniRouteDataCoordinator
from homeassistant.exceptions import ConfigEntryAuthFailed

@pytest.fixture
def hass():
    return MagicMock(spec=HomeAssistant)

@pytest.mark.asyncio
async def test_config_flow_shows_url_and_key_form():
    with patch("homeassistant.config_entries.ConfigFlow.async_show_form", return_value={"type": "form"}) as show:
        flow = OmniRouteConfigFlow()
        await flow.async_step_user()
        schema = show.call_args.kwargs["data_schema"]
        assert schema is not None
        assert CONF_URL in str(schema)
        assert CONF_API_KEY in str(schema)

@pytest.mark.asyncio
async def test_config_flow_success(hass):
    with patch("homeassistant.config_entries.ConfigFlow.async_set_unique_id", new_callable=AsyncMock), \
         patch("homeassistant.config_entries.ConfigFlow._abort_if_unique_id_configured"), \
         patch("homeassistant.config_entries.ConfigFlow.async_create_entry", return_value={"type": "create_entry"}) as create:
        flow = OmniRouteConfigFlow()
        user_input = {CONF_URL: "http://localhost:20128/", CONF_API_KEY: "test-key"}
        result = await flow.async_step_user(user_input)
        assert result["type"] == "create_entry"
        assert create.call_args.kwargs["title"] == "http://localhost:20128"
        assert create.call_args.kwargs["data"] == {CONF_URL: "http://localhost:20128", CONF_API_KEY: "test-key"}

@pytest.mark.asyncio
async def test_config_flow_rejects_invalid_url():
    with patch("homeassistant.config_entries.ConfigFlow.async_show_form", return_value={"type": "form"}) as show:
        flow = OmniRouteConfigFlow()
        await flow.async_step_user({CONF_URL: "file:///etc/passwd", CONF_API_KEY: "secret"})
        assert show.call_args.kwargs["errors"] == {"base": "invalid_url"}

@pytest.mark.asyncio
async def test_config_flow_invalid_data(hass):
    with patch("homeassistant.config_entries.ConfigFlow.async_show_form", return_value={"type": "form"}) as show, \
         patch("homeassistant.config_entries.ConfigFlow.async_set_unique_id", new_callable=AsyncMock), \
         patch("homeassistant.config_entries.ConfigFlow._abort_if_unique_id_configured"):
        flow = OmniRouteConfigFlow()
        flow.hass = hass
        result = await flow.async_step_user({CONF_URL: "http://localhost:20128"})
        assert result["type"] == "form"
        show.assert_called_once()

@pytest.mark.asyncio
async def test_coordinator_health_success(hass):
    with patch("homeassistant.helpers.frame.report_usage"), patch("aiohttp.ClientSession.get") as mock_get:
        coordinator = OmniRouteDataCoordinator(hass, "http://localhost:20128", "test-key")
        health = AsyncMock(); health.status = 200; health.__aenter__.return_value = health
        quota = AsyncMock(); quota.status = 200; quota.json.return_value = {"providers": {"openai": {"quota": 100}}}; quota.__aenter__.return_value = quota
        mock_get.side_effect = [health, quota]
        data = await coordinator._async_update_data()
        assert data["health"] == "healthy"
        assert data["quotas"]["openai"] == 100

@pytest.mark.asyncio
async def test_coordinator_auth_failure(hass):
    with patch("homeassistant.helpers.frame.report_usage"), patch("aiohttp.ClientSession.get") as mock_get:
        coordinator = OmniRouteDataCoordinator(hass, "http://localhost:20128", "test-key")
        health = AsyncMock(); health.status = 200; health.__aenter__.return_value = health
        quota = AsyncMock(); quota.status = 403; quota.__aenter__.return_value = quota
        mock_get.side_effect = [health, quota]
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_coordinator_defensive_parsing(hass):
    with patch("homeassistant.helpers.frame.report_usage"), patch("aiohttp.ClientSession.get") as mock_get:
        coordinator = OmniRouteDataCoordinator(hass, "http://localhost:20128", "test-key")
        health = AsyncMock(); health.status = 200; health.__aenter__.return_value = health
        quota = AsyncMock(); quota.status = 200; quota.json.return_value = {"invalid": "format"}; quota.__aenter__.return_value = quota
        mock_get.side_effect = [health, quota]
        from homeassistant.helpers.update_coordinator import UpdateFailed
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
