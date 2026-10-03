import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from homeassistant.core import HomeAssistant
from custom_components.omniroute.config_flow import OmniRouteConfigFlow
from custom_components.omniroute.coordinator import OmniRouteDataCoordinator
from homeassistant.exceptions import ConfigEntryAuthFailed
import aiohttp

@pytest.fixture
def hass():
    hass = MagicMock(spec=HomeAssistant)
    return hass

@pytest.mark.asyncio
async def test_config_flow_success(hass):
    flow = OmniRouteConfigFlow()
    user_input = {"host": "http://localhost:20128", "api_key": "test-key"}
    result = await flow.async_step_user(user_input)
    assert result["type"] == "create_entry"
    assert result["title"] == "http://localhost:20128"
    assert result["data"] == user_input

@pytest.mark.asyncio
async def test_config_flow_invalid_data(hass):
    # Mock async_show_form because it's a method of ConfigFlow
    with patch("homeassistant.config_entries.ConfigFlow.async_show_form") as mock_show:
        mock_show.return_value = {"type": "form", "errors": {"base": "invalid_data"}}
        flow = OmniRouteConfigFlow()
        # Missing api_key
        user_input = {"host": "http://localhost:20128"}
        result = await flow.async_step_user(user_input)
        assert result["type"] == "form"
        assert result["errors"] == {"base": "invalid_data"}
        mock_show.assert_called_once()

@pytest.mark.asyncio
async def test_coordinator_health_success(hass):
    with patch("homeassistant.helpers.frame.report_usage"),          patch("aiohttp.ClientSession.get") as mock_get:
        
        coordinator = OmniRouteDataCoordinator(hass, "http://localhost:20128", "test-key")
        
        mock_resp_health = AsyncMock()
        mock_resp_health.status = 200
        
        mock_resp_quota = AsyncMock()
        mock_resp_quota.status = 200
        mock_resp_quota.json = AsyncMock(return_value={"providers": {"openai": {"quota": 100}}})
        
        mock_get.side_effect = [
            AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_health)),
            AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_quota))
        ]
        
        data = await coordinator._async_update_data()
        assert data["health"] == "healthy"
        assert data["quotas"]["openai"] == 100

@pytest.mark.asyncio
async def test_coordinator_auth_failure(hass):
    with patch("homeassistant.helpers.frame.report_usage"),          patch("aiohttp.ClientSession.get") as mock_get:
        
        coordinator = OmniRouteDataCoordinator(hass, "http://localhost:20128", "bad-key")
        
        mock_resp_health = AsyncMock()
        mock_resp_health.status = 200
        
        mock_resp_quota = AsyncMock()
        mock_resp_quota.status = 403
        
        mock_get.side_effect = [
            AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_health)),
            AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_quota))
        ]
        
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

@pytest.mark.asyncio
async def test_coordinator_defensive_parsing(hass):
    with patch("homeassistant.helpers.frame.report_usage"),          patch("aiohttp.ClientSession.get") as mock_get:
        
        coordinator = OmniRouteDataCoordinator(hass, "http://localhost:20128", "test-key")
        
        mock_resp_health = AsyncMock()
        mock_resp_health.status = 200
        
        mock_resp_quota = AsyncMock()
        mock_resp_quota.status = 200
        mock_resp_quota.json = AsyncMock(return_value={"providers": "not-a-dict"})
        
        mock_get.side_effect = [
            AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_health)),
            AsyncMock(__aenter__=AsyncMock(return_value=mock_resp_quota))
        ]
        
        data = await coordinator._async_update_data()
        assert data["health"] == "healthy"
        assert data["quotas"] == {}
