import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_API_KEY

CONF_user = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_API_KEY): str,
})

class OmniRouteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle OmniRoute config flow."""

    async def async_step_user(self, user_input=None):
        """Handle the first step of the config flow."""
        errors = {}
        if user_input is not None:
            try:
                CONF_user(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_data"
                return self.async_show_form(
                    step_id="user",
                    data=user_input,
                    errors=errors,
                )

            return self.async_create_entry(
                title=user_input[CONF_HOST],
                data=user_input
            )

        return self.async_show_form(
            step_id="user",
            data={},
            errors=errors,
        )
