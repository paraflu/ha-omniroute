"""Opt-in third-party reset announcements; never account-level verification."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
import logging
import re

from aiohttp import ClientError, ClientTimeout, DummyCookieJar
from homeassistant.components import persistent_notification
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util.dt import utcnow

from .const import DOMAIN

CONF_RESET_MONITOR = "codex_reset_monitor"
CONF_RESET_NOTIFICATIONS = "codex_reset_notifications"
CONF_RESET_POLL_MINUTES = "codex_reset_poll_minutes"
DEFAULT_RESET_POLL_MINUTES = 5
MONITOR_KEY = "codex_reset_monitor_instance"
EVENT_RESET = "omniroute_codex_reset"
TIMELINE_URL = "https://codex-reset.com/api/timeline"
MAX_AGE = timedelta(hours=1)
MAX_SEEN = 512
MAX_BYTES = 1_048_576
_LOGGER = logging.getLogger(__name__)

# Intentionally narrow: unknown language is skipped rather than guessed.
_DENIAL = re.compile(r"\b(?:not|no|never|can't|cannot|won't|maybe|might|either|if|cancelled|canceled)\b")
_COMPLETED = re.compile(r"\bresets? (?:all |fully )?propagated\b|\ball reset for everyone\b")
_ANNOUNCED = re.compile(r"\b(?:global |full )?reset landing\b|\b(?:we'll|we will) reset usage limits\b")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Missing ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires timezone")
    return parsed


def parse_timeline(payload: object, now: datetime) -> list[dict]:
    """Validate feed freshness, then classify only well-supported reset phases."""
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("Invalid timeline schema")
    updated = _timestamp(payload.get("updated_at"))
    if not -timedelta(minutes=5) <= now - updated <= MAX_AGE:
        raise ValueError("Stale or future timeline")
    if len(payload["events"]) > 2000:
        raise ValueError("Too many timeline events")
    results = {}
    for item in payload["events"]:
        if not isinstance(item, dict) or item.get("type") != "reset":
            continue
        event_id = item.get("id")
        if not isinstance(event_id, str) or not re.fullmatch(r"[0-9]{15,22}", event_id):
            continue
        source_url = item.get("url")
        if source_url not in {
            f"https://x.com/thsottiaux/status/{event_id}",
            f"https://twitter.com/thsottiaux/status/{event_id}",
        }:
            continue
        try:
            announced = _timestamp(item.get("announced_at"))
        except (ValueError, TypeError):
            continue
        if announced > now + timedelta(minutes=5) or announced > updated + timedelta(minutes=5):
            continue
        message = item.get("summary")
        if not isinstance(message, str) or not message or len(message) > 4000:
            continue
        text = message.lower().replace("’", "'")
        if _DENIAL.search(text):
            continue
        source = item.get("source")
        if (source == "archive" and item.get("confidence") == "high"
                and item.get("reset_kind") == "hard" and item.get("preview") is not True):
            phase = "tracker_verified"
        elif source == "live" and _COMPLETED.search(text):
            phase = "declared_completed"
        elif source == "live" and _ANNOUNCED.search(text):
            phase = "announced"
        else:
            continue
        results[(event_id, phase)] = {
            "phase": phase, "event_id": event_id, "source_url": source_url,
            "message": message, "announced_at": item["announced_at"],
        }
    return sorted(results.values(), key=lambda event: (_timestamp(event["announced_at"]), event["event_id"]))


class ResetMonitor:
    """One independent poller per HA instance, reference-counted by opted-in entries."""

    def __init__(self, hass):
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}.codex_reset")
        self.entries: dict[str, bool] = {}
        self._poll_minutes: dict[str, int] = {}
        self._interval = None
        self._cancel = None
        self._lock = asyncio.Lock()
        self._loaded = False
        self._state = {"baseline_at": None, "seen": []}

    def _reschedule(self) -> None:
        """Keep one timer at the shortest opted-in interval; never fetch here."""
        interval = timedelta(minutes=min(self._poll_minutes.values())) if self.entries else None
        if interval == self._interval:
            return
        if self._cancel is not None:
            self._cancel()
            self._cancel = None
        self._interval = interval
        if interval is not None:
            self._cancel = async_track_time_interval(self.hass, self.async_poll, interval)

    async def async_add_entry(
        self, entry_id: str, notifications: bool,
        poll_minutes: int = DEFAULT_RESET_POLL_MINUTES,
    ) -> None:
        async with self._lock:
            first_entry = not self.entries
            self.entries[entry_id] = notifications
            self._poll_minutes[entry_id] = poll_minutes
            self._reschedule()
        if first_entry:
            await self.async_poll()

    async def async_remove_entry(self, entry_id: str) -> None:
        async with self._lock:
            self.entries.pop(entry_id, None)
            self._poll_minutes.pop(entry_id, None)
            self._reschedule()

    async def async_fetch(self) -> dict:
        """Public HTTPS only: no gateway token, redirects, cookies, or unbounded body."""
        # A dedicated, cookie-less session cannot inherit gateway headers/auth or
        # the shared HA session's cookies. Disable netrc/proxy credentials too.
        async with async_create_clientsession(
            self.hass, auto_cleanup=False, cookie_jar=DummyCookieJar(), trust_env=False,
        ) as session:
            async with session.get(TIMELINE_URL, timeout=ClientTimeout(total=15),
                                   allow_redirects=False) as response:
                response.raise_for_status()
                if response.status != 200:
                    raise ValueError("Unexpected tracker HTTP status")
                raw = bytearray()
                while chunk := await response.content.read(65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_BYTES:
                        raise ValueError("Timeline exceeds size limit")
                return json.loads(raw)

    async def async_poll(self, _now=None) -> None:
        """Persist before publishing (at-most-once); failures never establish a baseline."""
        async with self._lock:
            if not self.entries:
                return
            try:
                if not self._loaded:
                    saved = await self.store.async_load()
                    if saved is not None:
                        if (not isinstance(saved, dict) or not isinstance(saved.get("seen"), list)
                                or len(saved["seen"]) > MAX_SEEN
                                or not all(isinstance(key, str) for key in saved["seen"])):
                            raise ValueError("Invalid reset monitor storage")
                        _timestamp(saved.get("baseline_at"))
                        self._state = saved
                    self._loaded = True
                now = utcnow()
                data = await self.async_fetch()
                events = parse_timeline(data, now)
                baseline = self._state["baseline_at"]
                seen = list(self._state["seen"])
                known_ids = {key.split(":", 1)[0] for key in seen}
                pending = []
                for event in events:
                    key = f"{event['event_id']}:{event['phase']}"
                    if key in seen:
                        continue
                    if baseline is not None and (
                        _timestamp(event["announced_at"]) > _timestamp(baseline)
                        or event["event_id"] in known_ids
                    ):
                        pending.append(event)
                    seen.append(key)
                # Advance the timestamp watermark so evicted IDs cannot replay.
                # Known IDs may still progress to a new phase with their original timestamp.
                watermark = max([_timestamp(baseline or data["updated_at"])] +
                                [_timestamp(event["announced_at"]) for event in events])
                state = {"baseline_at": watermark.isoformat(), "seen": seen[-MAX_SEEN:]}
                if state != self._state:
                    await self.store.async_save(state)
                    self._state = state
                # One global event, not one event per gateway entry.
                entry_id = sorted(self.entries)[0]
                for event in pending:
                    self.hass.bus.async_fire(EVENT_RESET, {**event, "entry_id": entry_id})
                    if any(self.entries.values()) and event["phase"] in {"announced", "declared_completed"}:
                        label = "Reset announced" if event["phase"] == "announced" else "Reset declared completed (not account-verified)"
                        persistent_notification.async_create(
                            self.hass, f"{label}\n\n{event['message']}\n\nSource: {event['source_url']}",
                            title=f"Codex: {label}",
                            notification_id=f"omniroute_reset_{event['event_id']}_{event['phase']}",
                        )
            except (ClientError, TimeoutError, ValueError, OSError, TypeError) as err:
                _LOGGER.warning("Codex reset tracker unavailable; no reset alerts: %s", type(err).__name__)
