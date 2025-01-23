"""Config flow for edilkamin integration."""
from __future__ import annotations

from typing import Any

import edilkamin
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_MAC,
    CONF_NAME
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components import dhcp
from homeassistant.helpers import device_registry as dr

import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, LOGGER
from .utils import is_valid_mac_address

STEP_CRED_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Optional(CONF_NAME, default="Pellet Stove"): cv.string,
    }
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MAC): cv.string,
    }
)


class EdilkaminHub:
    """EdilkaminHub used for testing the authentication."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Create the Edilkamin hub using the HomeAssistant instance."""
        self.hass = hass

    async def authenticate(self, username: str, password: str) -> bool:
        """Authenticate with the host and return the token or
        raise an exception."""
        try:
            token = await self.hass.async_add_executor_job(
                edilkamin.sign_in, username, password
            )
        except Exception as exception:
            # we can't easily catch for the NotAuthorizedException directly
            # since it was created dynamically with a factory
            if exception.__class__.__name__ == "NotAuthorizedException":
                raise InvalidAuth(exception) from exception
            raise CannotConnect(exception) from exception
        return token


async def validate_input(
    hass: HomeAssistant,
    data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA
    with values provided by the user.
    """
    hub = EdilkaminHub(hass)
    username = data[CONF_USERNAME]
    password = data[CONF_PASSWORD]
    if CONF_NAME not in data:
        data[CONF_NAME] = "Pellet Stove"
    token = await hub.authenticate(username, password)
    if not token:
        raise InvalidAuth
    return {}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for edilkamin."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._discovered_mac = None

        self.data = {}

    async def async_step_dhcp(
        self,
        discovery_info: dhcp.DhcpServiceInfo
    ) -> FlowResult:
        """Handle discovery via dhcp."""
        self._discovered_mac = discovery_info.macaddress
        LOGGER.debug(
            "Edilkamin stove discovered from dhcp : MAC is %s",
            self._discovered_mac
        )
        return await self._async_handle_discovery()

    async def _async_handle_discovery(self) -> FlowResult:
        """Handle any discovery."""
        mac = dr.format_mac(self._discovered_mac)
        self.data[CONF_MAC] = mac

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        return await self.async_step_cred()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user.
        First step : enter mac address"""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA
            )

        # Mac address validation
        valid_mac = is_valid_mac_address(user_input[CONF_MAC])
        if not valid_mac:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "invalid_mac"}
            )

        mac = dr.format_mac(user_input[CONF_MAC])
        self.data[CONF_MAC] = mac

        return await self.async_step_cred()

    async def async_step_cred(
        self,
        user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Second step of the config flow"""

        if user_input is None:
            return self.async_show_form(
                step_id="cred",
                data_schema=STEP_CRED_DATA_SCHEMA
            )
        errors = {}
        try:
            await validate_input(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.data = self.data | user_input
            return self.async_create_entry(
                # title=user_input[CONF_USERNAME],
                title=self.data[CONF_MAC],
                data=self.data
            )

        return self.async_show_form(
            step_id="cred", data_schema=STEP_CRED_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
