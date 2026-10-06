"""Configurable polling: UI validation, shared scheduling, transport isolation."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol

KEY = "codex_reset_poll_minutes"
BASE = {"url": "https://gateway.example", "api_key": "test", "codex_reset_monitor": True}


@pytest.mark.parametrize("value", [True, False, 1.0, 5.5, 0, -1, 61, "5", None])
def test_poll_schema_rejects_non_integer_or_out_of_range(value):
    from custom_components.omniroute.config_flow import STEP_USER_DATA_SCHEMA
    with pytest.raises(vol.Invalid) as error:
        STEP_USER_DATA_SCHEMA({**BASE, KEY: value})
    assert error.value.path == [KEY]


@pytest.mark.parametrize("value", [1, 5, 60])
def test_poll_schema_accepts_bounds(value):
    from custom_components.omniroute.config_flow import STEP_USER_DATA_SCHEMA
    assert STEP_USER_DATA_SCHEMA({**BASE, KEY: value})[KEY] == value


def test_poll_schema_serializes_for_ha_ui():
    import voluptuous_serialize
    from custom_components.omniroute.config_flow import STEP_USER_DATA_SCHEMA
    fields = voluptuous_serialize.convert(STEP_USER_DATA_SCHEMA)
    field = next(item for item in fields if item["name"] == KEY)
    assert field["type"] == "integer"
    assert field["valueMin"] == 1 and field["valueMax"] == 60
    assert field["default"] == 5


def test_poll_schema_legacy_default():
    from custom_components.omniroute.config_flow import STEP_USER_DATA_SCHEMA
    assert STEP_USER_DATA_SCHEMA(BASE)[KEY] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["user", "init"])
@pytest.mark.parametrize("value", [True, 3.5, 0, 61])
async def test_flow_poll_error_targets_poll_field(step, value):
    from custom_components.omniroute.config_flow import OmniRouteConfigFlow
    entry = SimpleNamespace(entry_id="one", data=BASE, options={})
    flow = OmniRouteConfigFlow() if step == "user" else OmniRouteConfigFlow.async_get_options_flow(entry)
    with patch.object(flow, "async_show_form") as show:
        await getattr(flow, "async_step_"+step)({**BASE, KEY: value})
        assert show.call_args.kwargs["errors"] == {KEY: "invalid_poll_minutes"}


@pytest.mark.asyncio
async def test_setup_and_options_poll_roundtrip():
    from custom_components.omniroute.config_flow import OmniRouteConfigFlow
    flow = OmniRouteConfigFlow()
    with patch.object(flow, "async_set_unique_id", new_callable=AsyncMock), \
         patch.object(flow, "_abort_if_unique_id_configured"), \
         patch.object(flow, "async_create_entry") as create:
        await flow.async_step_user({**BASE, KEY: 12})
        data = create.call_args.kwargs["data"]
        assert data[KEY] == 12
    entry = SimpleNamespace(entry_id="one", data=data, options={KEY: 2})
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_get_known_entry.return_value = entry
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_reload = AsyncMock()
    flow = OmniRouteConfigFlow.async_get_options_flow(entry)
    flow.hass = hass
    flow.handler = "one"
    with patch.object(flow, "async_show_form") as show:
        await flow.async_step_init()
        schema = show.call_args.kwargs["data_schema"]
        assert schema({"api_key": "test"})[KEY] == 2
    with patch.object(flow, "async_create_entry") as create:
        await flow.async_step_init({**BASE, KEY: 60})
        assert hass.config_entries.async_update_entry.call_args.kwargs["options"][KEY] == 60
        assert create.call_args.kwargs["data"][KEY] == 60
        hass.config_entries.async_reload.assert_awaited_once_with("one")


@pytest.mark.asyncio
async def test_options_schedule_only_change_does_not_reload_or_fetch():
    from custom_components.omniroute.config_flow import OmniRouteConfigFlow
    from custom_components.omniroute.codex_reset import MONITOR_KEY
    entry = SimpleNamespace(entry_id="one", data=BASE, options={KEY: 5})
    hass = MagicMock()
    monitor = MagicMock()
    monitor.async_add_entry = AsyncMock()
    hass.data = {"omniroute": {MONITOR_KEY: monitor}}
    hass.config_entries.async_get_known_entry.return_value = entry
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_reload = AsyncMock()
    flow = OmniRouteConfigFlow.async_get_options_flow(entry)
    flow.hass = hass
    flow.handler = "one"
    with patch.object(flow, "async_create_entry"):
        await flow.async_step_init({**BASE, KEY: 2})
    hass.config_entries.async_reload.assert_not_awaited()
    monitor.async_add_entry.assert_awaited_once_with("one", True, 2)


@pytest.mark.asyncio
async def test_legacy_options_poll_default():
    from custom_components.omniroute.config_flow import OmniRouteConfigFlow
    entry = SimpleNamespace(entry_id="one", data=BASE, options={})
    flow = OmniRouteConfigFlow.async_get_options_flow(entry)
    flow.hass = MagicMock()
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    flow.handler = "one"
    with patch.object(flow, "async_show_form") as show:
        await flow.async_step_init()
        assert show.call_args.kwargs["data_schema"]({"api_key": "test"})[KEY] == 5


@pytest.mark.asyncio
async def test_shortest_poll_reschedules_without_immediate_fetch():
    from custom_components.omniroute import codex_reset as module
    hass = MagicMock()
    with patch.object(module, "Store"), patch.object(module, "async_track_time_interval") as track:
        cancels = [MagicMock() for _ in range(5)]
        track.side_effect = cancels
        monitor = module.ResetMonitor(hass)
        monitor.async_poll = AsyncMock()
        await monitor.async_add_entry("one", False, 12)
        assert track.call_args.args[2] == timedelta(minutes=12)
        monitor.async_poll.assert_awaited_once()
        await monitor.async_add_entry("two", True, 2)
        cancels[0].assert_called_once()
        assert track.call_args.args[2] == timedelta(minutes=2)
        await monitor.async_add_entry("three", False, 60)
        assert track.call_count == 2
        await monitor.async_add_entry("two", False, 3)
        assert track.call_args.args[2] == timedelta(minutes=3)
        await monitor.async_remove_entry("two")
        assert track.call_args.args[2] == timedelta(minutes=12)
        await monitor.async_remove_entry("one")
        assert track.call_args.args[2] == timedelta(minutes=60)
        await monitor.async_remove_entry("missing")
        assert track.call_count == 5
        monitor.async_poll.assert_awaited_once()
        await monitor.async_remove_entry("three")
        for cancel in cancels:
            cancel.assert_called_once()
        track.side_effect = None
        await monitor.async_add_entry("legacy", True)
        assert track.call_args.args[2] == timedelta(minutes=5)
        assert monitor.async_poll.await_count == 2


@pytest.mark.asyncio
async def test_integration_passes_poll_option_and_legacy_default():
    from custom_components import omniroute
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    with patch.object(omniroute, "OmniRouteDataCoordinator") as coordinator, \
         patch.object(omniroute, "ResetMonitor") as factory:
        coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
        factory.return_value.async_add_entry = AsyncMock()
        for name, data, options, expected in [
            ("legacy", BASE, {}, 5),
            ("configured", {**BASE, KEY: 12}, {}, 12),
            ("override", {**BASE, KEY: 12}, {KEY: 1}, 1),
        ]:
            await omniroute.async_setup_entry(hass, SimpleNamespace(entry_id=name, data=data, options=options))
            factory.return_value.async_add_entry.assert_awaited_with(name, True, expected)


@pytest.mark.asyncio
@pytest.mark.enable_socket
@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_real_http_request_has_no_auth_cookies_or_account_data():
    import pytest_socket
    pytest_socket.enable_socket()
    from aiohttp import ClientSession, web
    from custom_components.omniroute import codex_reset as module
    received = []

    async def timeline(request):
        received.append((dict(request.headers), dict(request.query)))
        return web.json_response({"events": []})

    app = web.Application()
    app.router.add_get("/api/timeline", timeline)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    sessions = []

    def create_session(hass, **kwargs):
        kwargs.pop("auto_cleanup")
        session = ClientSession(**kwargs)
        sessions.append(session)
        return session

    try:
        hass = MagicMock()
        # Gateway data exists but must never enter tracker request arguments.
        hass.data = {"omniroute": {"api_key": "fake-private-gateway-key"}}
        with patch.object(module, "TIMELINE_URL", f"http://127.0.0.1:{port}/api/timeline"), \
             patch.object(module, "async_create_clientsession", side_effect=create_session), \
             patch.object(module, "Store"):
            assert await module.ResetMonitor(hass).async_fetch() == {"events": []}
        headers, query = received[0]
        assert "Authorization" not in headers
        assert "Cookie" not in headers
        assert query == {}
        assert "fake-private-gateway-key" not in str(received)
        assert sessions[0].closed
    finally:
        await runner.cleanup()
        pytest_socket.disable_socket(allow_unix_socket=True)


def test_poll_translations():
    import json
    from pathlib import Path
    directory = Path(__file__).parents[1]/"custom_components/omniroute"
    strings = json.loads((directory/"strings.json").read_text())
    assert strings == json.loads((directory/"translations/en.json").read_text())
    for group, step in [("config", "user"), ("options", "init")]:
        assert KEY in strings[group]["step"][step]["data"]
        assert "invalid_poll_minutes" in strings[group]["error"]
