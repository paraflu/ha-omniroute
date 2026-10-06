"""Config flow for OmniRoute."""

from __future__ import annotations

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback

from .const import DOMAIN
from .codex_reset import (
    CONF_RESET_MONITOR, CONF_RESET_NOTIFICATIONS, CONF_RESET_POLL_MINUTES,
    DEFAULT_RESET_POLL_MINUTES, MONITOR_KEY,
)


class _PollMinutesRange(vol.Range):
    """Serializable numeric range that also rejects bool and float inputs."""

    def __call__(self, value: object) -> int:
        if type(value) is not int:
            raise vol.Invalid("Enter a whole number of minutes between 1 and 60")
        return super().__call__(value)


POLL_MINUTES_SCHEMA = vol.All(int, _PollMinutesRange(min=1, max=60))


def _validation_errors(error: Exception) -> dict[str, str]:
    """Point polling failures at their field, not the gateway URL."""
    if isinstance(error, vol.Invalid) and error.path == [CONF_RESET_POLL_MINUTES]:
        return {CONF_RESET_POLL_MINUTES: "invalid_poll_minutes"}
    return {"base": "invalid_url"}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_RESET_MONITOR, default=False): bool,
        vol.Optional(CONF_RESET_NOTIFICATIONS, default=True): bool,
        vol.Optional(CONF_RESET_POLL_MINUTES, default=DEFAULT_RESET_POLL_MINUTES): POLL_MINUTES_SCHEMA,
    }
)


def _valid_base_url(value: str) -> str:
    """Validate and normalize the OmniRoute base URL."""
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise vol.Invalid("Enter an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise vol.Invalid("URL must not contain credentials, query, or fragment")
    return normalized


class OmniRouteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle OmniRoute config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                validated = STEP_USER_DATA_SCHEMA(user_input)
                url = _valid_base_url(validated[CONF_URL])
            except (vol.Invalid, KeyError) as error:
                errors = _validation_errors(error)
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=url,
                    data={CONF_URL: url, CONF_API_KEY: validated[CONF_API_KEY].strip(),
                          **({CONF_RESET_MONITOR: True, CONF_RESET_NOTIFICATIONS: validated[CONF_RESET_NOTIFICATIONS],
                              CONF_RESET_POLL_MINUTES: validated[CONF_RESET_POLL_MINUTES]}
                             if validated[CONF_RESET_MONITOR] else {})},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Provide reconfiguration for an existing entry."""
        return OmniRouteOptionsFlow()


class OmniRouteOptionsFlow(config_entries.OptionsFlow):
    """Allow updating the URL and API key without removing the entry."""

    async def async_step_init(self, user_input: dict | None = None):
        """Update connection settings."""
        if user_input is not None:
            try:
                validated = STEP_USER_DATA_SCHEMA(user_input)
                url = _valid_base_url(validated[CONF_URL])
            except (vol.Invalid, KeyError) as error:
                return self.async_show_form(
                    step_id="init",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors=_validation_errors(error),
                )
            if any(e.entry_id != self.config_entry.entry_id and e.data.get(CONF_URL, e.data.get("host")) == url
                   for e in self.hass.config_entries.async_entries(DOMAIN)):
                return self.async_show_form(step_id="init", data_schema=STEP_USER_DATA_SCHEMA,
                                            errors={"base": "already_configured"})
            previous = {**self.config_entry.data, **getattr(self.config_entry, "options", {})}
            monitor = self.hass.data.get(DOMAIN, {}).get(MONITOR_KEY)
            update_monitor_only = (
                monitor is not None
                and previous.get(CONF_RESET_MONITOR, False)
                and validated[CONF_RESET_MONITOR]
                and self.config_entry.data.get(CONF_URL, self.config_entry.data.get("host")) == url
                and self.config_entry.data.get(CONF_API_KEY) == validated[CONF_API_KEY].strip()
            )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_URL: url, CONF_API_KEY: validated[CONF_API_KEY].strip()},
                title=url,
                unique_id=url,
                options={CONF_RESET_MONITOR: validated[CONF_RESET_MONITOR],
                         CONF_RESET_NOTIFICATIONS: validated[CONF_RESET_NOTIFICATIONS],
                         CONF_RESET_POLL_MINUTES: validated[CONF_RESET_POLL_MINUTES]},
            )
            options = {CONF_RESET_MONITOR: validated[CONF_RESET_MONITOR],
                       CONF_RESET_NOTIFICATIONS: validated[CONF_RESET_NOTIFICATIONS],
                       CONF_RESET_POLL_MINUTES: validated[CONF_RESET_POLL_MINUTES]}
            if update_monitor_only:
                await monitor.async_add_entry(
                    self.config_entry.entry_id, validated[CONF_RESET_NOTIFICATIONS],
                    validated[CONF_RESET_POLL_MINUTES],
                )
            else:
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data=options)

        settings = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema({
            vol.Required(CONF_URL, default=settings.get(CONF_URL, settings.get("host", ""))): str,
            vol.Required(CONF_API_KEY): str,
            vol.Optional(CONF_RESET_MONITOR, default=settings.get(CONF_RESET_MONITOR, False)): bool,
            vol.Optional(CONF_RESET_NOTIFICATIONS, default=settings.get(CONF_RESET_NOTIFICATIONS, True)): bool,
            vol.Optional(CONF_RESET_POLL_MINUTES, default=settings.get(
                CONF_RESET_POLL_MINUTES, DEFAULT_RESET_POLL_MINUTES)): POLL_MINUTES_SCHEMA,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
