"""Conservative parsing and durable, shared reset monitor regression tests."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

NOW = datetime(2026, 10, 6, 19, tzinfo=timezone.utc)


def event(**changes):
    value = dict(id="2105843926221660585", type="reset", source="live",
                 summary="Global reset landing tomorrow 10am PST for all paid ChatGPT accounts",
                 url="https://x.com/thsottiaux/status/2105843926221660585",
                 announced_at=NOW.isoformat(), reset_verification_status="pending")
    value.update(changes)
    return value


def payload(*events, updated_at=None):
    return dict(updated_at=updated_at or NOW.isoformat(), events=list(events))


def test_parser_missing_feature():
    from custom_components.omniroute import codex_reset
    assert codex_reset.parse_timeline(payload(event()), NOW)[0]["phase"] == "announced"


@pytest.mark.parametrize("summary", [
    "I can’t really give a reset", "Maybe a reset tomorrow", "More resets coming next week",
    "We'll either ship an improvement or ship a full reset", "I challenge you to do the same",
    "Reset not all propagated", "Global reset landing tomorrow but cancelled",
])
def test_rejects_false_positives(summary):
    from custom_components.omniroute.codex_reset import parse_timeline
    assert parse_timeline(payload(event(summary=summary)), NOW) == []


def test_phases_and_no_inferred_pst_timestamp():
    from custom_components.omniroute.codex_reset import parse_timeline
    announced = parse_timeline(payload(event()), NOW)[0]
    assert announced["phase"] == "announced"
    assert "effective_at" not in announced
    completed = parse_timeline(payload(event(summary="Reset all propagated. Enjoy.")), NOW)[0]
    assert completed["phase"] == "declared_completed"
    archive = event(source="archive", confidence="high", reset_kind="hard")
    assert parse_timeline(payload(archive), NOW)[0]["phase"] == "tracker_verified"
    assert parse_timeline(payload(event(source="archive", confidence="low")), NOW) == []


@pytest.mark.parametrize("change", [dict(id="../bad"), dict(id=123), dict(announced_at="bad"),
    dict(announced_at="2026-10-06T19:00:00"), dict(url="http://x.com/thsottiaux/status/2105843926221660585"),
    dict(url="https://evil.example/status/2105843926221660585"), dict(type="credits"),
    dict(announced_at=(NOW+timedelta(days=1)).isoformat())])
def test_rejects_invalid_event(change):
    from custom_components.omniroute.codex_reset import parse_timeline
    assert parse_timeline(payload(event(**change)), NOW) == []


@pytest.mark.parametrize("data", [None, {}, {"events":{}}, payload(updated_at="bad"),
    payload(updated_at=(NOW-timedelta(hours=2)).isoformat()),
    payload(updated_at=(NOW+timedelta(hours=2)).isoformat())])
def test_invalid_or_stale_feed_does_not_baseline(data):
    from custom_components.omniroute.codex_reset import parse_timeline
    with pytest.raises(ValueError):
        parse_timeline(data, NOW)


def test_real_snapshot():
    from custom_components.omniroute.codex_reset import parse_timeline
    data = json.loads((Path(__file__).parent / "fixtures/reset-timeline.json").read_text())
    results = {e["event_id"]: e for e in parse_timeline(data, datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")))}
    assert results["2105843926221660585"]["phase"] == "announced"
    assert results["2106131810921136451"]["phase"] == "declared_completed"
    assert results["2103911959544610829"]["phase"] == "tracker_verified"
    assert "2105672058269212820" not in results
    assert "2106845241357824205" not in results


@pytest.fixture
def monitor_env():
    from custom_components.omniroute import codex_reset
    hass = MagicMock(); hass.data = {}
    state = {}
    store = MagicMock()
    store.async_load = AsyncMock(side_effect=lambda: deepcopy(state.get("value")))
    async def save(value):
        state["value"] = deepcopy(value)
    store.async_save = AsyncMock(side_effect=save)
    with patch.object(codex_reset, "Store", return_value=store), \
         patch.object(codex_reset, "async_track_time_interval") as interval, \
         patch.object(codex_reset, "utcnow", return_value=NOW), \
         patch.object(codex_reset.persistent_notification, "async_create") as notify:
        yield codex_reset, hass, store, interval, notify


@pytest.mark.asyncio
async def test_baseline_transition_restart_failure_and_notifications(monitor_env):
    module, hass, store, interval, notify = monitor_env
    m = module.ResetMonitor(hass)
    m.async_fetch = AsyncMock(side_effect=[ValueError("offline"), payload(event()),
        payload(event(summary="Reset all propagated. Enjoy.")), payload(event(summary="Reset all propagated. Enjoy."))])
    await m.async_add_entry("entry1", True)
    assert store.async_save.await_count == 0
    await m.async_poll()
    hass.bus.async_fire.assert_not_called()
    await m.async_poll()
    args = hass.bus.async_fire.call_args.args
    assert args[0] == "omniroute_codex_reset"
    assert args[1]["phase"] == "declared_completed"
    assert args[1]["entry_id"] == "entry1"
    notify.assert_called_once()
    await m.async_poll()
    assert hass.bus.async_fire.call_count == 1
    await m.async_remove_entry("entry1")
    interval.return_value.assert_called_once()
    restarted = module.ResetMonitor(hass)
    restarted.async_fetch = AsyncMock(return_value=payload(event(summary="Reset all propagated. Enjoy.")))
    await restarted.async_add_entry("entry1", True)
    assert hass.bus.async_fire.call_count == 1
    await restarted.async_remove_entry("entry1")


@pytest.mark.asyncio
async def test_shared_monitor_new_events_and_unload(monitor_env):
    module, hass, store, interval, notify = monitor_env
    m = module.ResetMonitor(hass)
    m.async_fetch = AsyncMock(return_value=payload())
    await m.async_add_entry("entry1", False)
    await m.async_add_entry("entry2", False)
    assert m.async_fetch.await_count == 1
    interval.assert_called_once()
    m.async_fetch.return_value = payload(event(announced_at=(NOW+timedelta(seconds=1)).isoformat()),
                                          updated_at=(NOW+timedelta(seconds=1)).isoformat())
    await m.async_poll()
    hass.bus.async_fire.assert_called_once()
    notify.assert_not_called()
    await m.async_remove_entry("entry1")
    interval.return_value.assert_not_called()
    await m.async_remove_entry("entry2")
    interval.return_value.assert_called_once()
    calls = m.async_fetch.await_count
    await m.async_poll()
    assert m.async_fetch.await_count == calls


@pytest.mark.asyncio
async def test_store_failure_does_not_emit_or_advance(monitor_env):
    module, hass, store, _, _ = monitor_env
    m = module.ResetMonitor(hass)
    m.async_fetch = AsyncMock(return_value=payload())
    await m.async_add_entry("entry1", False)
    m.async_fetch.return_value = payload(event(announced_at=(NOW+timedelta(seconds=1)).isoformat()),
                                          updated_at=(NOW+timedelta(seconds=1)).isoformat())
    store.async_save.side_effect = OSError("disk full")
    await m.async_poll()
    hass.bus.async_fire.assert_not_called()
    store.async_save.side_effect = None
    await m.async_poll()
    hass.bus.async_fire.assert_called_once()
    await m.async_remove_entry("entry1")


@pytest.mark.asyncio
async def test_fetch_no_credentials_bounded_timeout(monitor_env):
    module, hass, _, _, _ = monitor_env
    response = AsyncMock()
    response.__aenter__.return_value = response
    response.raise_for_status = MagicMock()
    response.status = 200
    response.content.read.side_effect = [json.dumps(payload()).encode(), b""]
    session = MagicMock(); session.get.return_value = response
    with patch.object(module, "async_create_clientsession", return_value=session) as create_session:
        session.__aenter__.return_value = session
        assert await module.ResetMonitor(hass).async_fetch() == payload()
    kwargs = session.get.call_args.kwargs
    assert "Authorization" not in kwargs.get("headers", {})
    assert kwargs["timeout"].total <= 20
    assert kwargs["allow_redirects"] is False
    assert create_session.call_args.kwargs["auto_cleanup"] is False
    assert create_session.call_args.kwargs["trust_env"] is False
    from aiohttp import DummyCookieJar
    assert isinstance(create_session.call_args.kwargs["cookie_jar"], DummyCookieJar)
    assert "auth" not in kwargs and "params" not in kwargs

@pytest.mark.asyncio
async def test_config_optin_and_options_defaults():
    from custom_components.omniroute.config_flow import OmniRouteConfigFlow
    with patch("homeassistant.config_entries.ConfigFlow.async_show_form") as show:
        flow = OmniRouteConfigFlow()
        await flow.async_step_user()
        schema = show.call_args.kwargs["data_schema"]
        values = schema({"url":"https://gateway.example", "api_key":"test"})
        assert values["codex_reset_monitor"] is False
        assert values["codex_reset_notifications"] is True
    with patch.object(flow, "async_set_unique_id", new_callable=AsyncMock), \
         patch.object(flow, "_abort_if_unique_id_configured"), \
         patch.object(flow, "async_create_entry") as create:
        await flow.async_step_user({"url":"https://gateway.example", "api_key":"test", "codex_reset_monitor":True})
        assert create.call_args.kwargs["data"]["codex_reset_monitor"] is True
    entry = SimpleNamespace(entry_id="first", data={"url":"https://gateway.example", "api_key":"test"},
                            options={"codex_reset_monitor":True, "codex_reset_notifications":False})
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_get_known_entry.return_value = entry
    hass.config_entries.async_entries.return_value = [entry]
    hass.config_entries.async_reload = AsyncMock()
    flow = OmniRouteConfigFlow.async_get_options_flow(entry)
    flow.hass = hass; flow.handler = "first"
    with patch.object(flow, "async_show_form") as show:
        await flow.async_step_init()
        defaults = show.call_args.kwargs["data_schema"]({"url":"https://gateway.example", "api_key":"test"})
        assert defaults["codex_reset_monitor"] is True
        assert defaults["codex_reset_notifications"] is False
    with patch.object(flow, "async_create_entry") as create:
        await flow.async_step_init({"url":"https://gateway.example", "api_key":"test",
                                  "codex_reset_monitor":True, "codex_reset_notifications":False})
        assert hass.config_entries.async_update_entry.call_args.kwargs["options"]["codex_reset_monitor"] is True
        assert create.call_args.kwargs["data"]["codex_reset_notifications"] is False


@pytest.mark.asyncio
async def test_integration_shared_setup_unload_and_optout(monitor_env):
    from custom_components.omniroute import async_setup_entry, async_unload_entry
    module, hass, _, interval, _ = monitor_env
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    def entry(name, enabled):
        return SimpleNamespace(entry_id=name, data={"url":"https://gateway.example", "api_key":"test"},
                               options={"codex_reset_monitor":enabled})
    with patch("custom_components.omniroute.OmniRouteDataCoordinator") as coordinator, \
         patch.object(module.ResetMonitor, "async_fetch", new_callable=AsyncMock, return_value=payload()) as fetch:
        coordinator.return_value.async_config_entry_first_refresh = AsyncMock()
        await async_setup_entry(hass, entry("off", False))
        fetch.assert_not_awaited()
        await async_setup_entry(hass, entry("one", True))
        await async_setup_entry(hass, entry("two", True))
        fetch.assert_awaited_once()
        hass.config_entries.async_unload_platforms.return_value = False
        assert not await async_unload_entry(hass, entry("one", True))
        assert len(hass.data["omniroute"][module.MONITOR_KEY].entries) == 2
        hass.config_entries.async_unload_platforms.return_value = True
        await async_unload_entry(hass, entry("one", True))
        interval.return_value.assert_not_called()
        await async_unload_entry(hass, entry("two", True))
        interval.return_value.assert_called_once()
        assert module.MONITOR_KEY not in hass.data["omniroute"]

@pytest.mark.asyncio
async def test_bounded_store_no_replay_and_old_backfill(monitor_env):
    module, hass, store, _, _ = monitor_env
    m = module.ResetMonitor(hass)
    m.async_fetch = AsyncMock(return_value=payload())
    await m.async_add_entry("entry1", False)
    future = (NOW+timedelta(seconds=1)).isoformat()
    items = [event(id=str(2105843926221660585+i),
                   url=f"https://x.com/thsottiaux/status/{2105843926221660585+i}",
                   announced_at=future) for i in range(600)]
    m.async_fetch.return_value = payload(*items, updated_at=future)
    await m.async_poll()
    assert hass.bus.async_fire.call_count == 600
    assert len(store.async_save.call_args.args[0]["seen"]) <= module.MAX_SEEN
    await m.async_poll()
    assert hass.bus.async_fire.call_count == 600
    m.async_fetch.return_value = payload(event(id="2100000000000000001",
        url="https://x.com/thsottiaux/status/2100000000000000001",
        announced_at=(NOW-timedelta(days=30)).isoformat()), updated_at=future)
    await m.async_poll()
    assert hass.bus.async_fire.call_count == 600
    await m.async_remove_entry("entry1")


@pytest.mark.asyncio
async def test_announced_and_verified_notification_meanings(monitor_env):
    module, hass, _, _, notify = monitor_env
    m = module.ResetMonitor(hass)
    m.async_fetch = AsyncMock(return_value=payload())
    await m.async_add_entry("entry1", True)
    future=(NOW+timedelta(seconds=1)).isoformat()
    m.async_fetch.return_value=payload(event(announced_at=future), updated_at=future)
    await m.async_poll()
    assert hass.bus.async_fire.call_args.args[1]["phase"] == "announced"
    notify.assert_called_once()
    m.async_fetch.return_value=payload(event(announced_at=future, source="archive", confidence="high", reset_kind="hard"), updated_at=future)
    await m.async_poll()
    assert hass.bus.async_fire.call_args.args[1]["phase"] == "tracker_verified"
    notify.assert_called_once()
    await m.async_remove_entry("entry1")

def test_ui_translations_manifest_and_automation():
    import yaml
    root = Path(__file__).parents[1]
    strings=json.loads((root/"custom_components/omniroute/strings.json").read_text())
    translations=json.loads((root/"custom_components/omniroute/translations/en.json").read_text())
    assert strings == translations
    for group,step in [("config","user"),("options","init")]:
        assert "codex_reset_monitor" in strings[group]["step"][step]["data"]
    manifest=json.loads((root/"custom_components/omniroute/manifest.json").read_text())
    assert "persistent_notification" in manifest["dependencies"]
    automation=yaml.safe_load((root/"examples/codex-reset-alerts.yaml").read_text())[0]
    assert automation["triggers"][0]["event_type"] == "omniroute_codex_reset"
    assert automation["actions"][0]["action"] == "notify.mobile_app_your_phone"
