"""Config flow for OmniRoute."""

from __future__ import annotations

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import callback

from .const import DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
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
            except (vol.Invalid, KeyError):
                errors["base"] = "invalid_url"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=url,
                    data={CONF_URL: url, CONF_API_KEY: validated[CONF_API_KEY].strip()},
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
        return OmniRouteOptionsFlow(config_entry)


class OmniRouteOptionsFlow(config_entries.OptionsFlow):
    """Allow updating the URL and API key without removing the entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        """Update connection settings."""
        if user_input is not None:
            try:
                url = _valid_base_url(user_input[CONF_URL])
            except (vol.Invalid, KeyError):
                return self.async_show_form(
                    step_id="init",
                    data_schema=STEP_USER_DATA_SCHEMA,
                    errors={"base": "invalid_url"},
                )
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_URL: url, CONF_API_KEY: user_input[CONF_API_KEY].strip()},
                title=url,
            )
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=STEP_USER_DATA_SCHEMA,
        )
