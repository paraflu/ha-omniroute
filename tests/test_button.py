from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.exceptions import HomeAssistantError
from custom_components.omniroute.button import OmniRouteRefreshButton

@pytest.mark.asyncio
async def test_refresh_and_cooldown():
    coordinator=SimpleNamespace(host='https://example.org',api_key='test',config_entry=SimpleNamespace(entry_id='a'),async_request_refresh=AsyncMock())
    button=OmniRouteRefreshButton(coordinator)
    response=AsyncMock(); response.status=200; response.json.return_value={'succeeded':2,'failed':0}; response.__aenter__.return_value=response
    with patch('aiohttp.ClientSession.post',return_value=response) as post:
        await button.async_press()
        coordinator.async_request_refresh.assert_awaited_once()
        assert post.call_args.args[0].endswith('/api/usage/provider-limits')
        with pytest.raises(HomeAssistantError,match='60 seconds'):
            await button.async_press()
        assert post.call_count==1
