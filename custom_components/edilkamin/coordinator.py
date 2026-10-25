import base64
import json
import time
from datetime import timedelta

import async_timeout
import edilkamin

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import LOGGER

# Renew the token when less than this many seconds of validity are left
TOKEN_MIN_VALIDITY = 300


def _token_expiry(token: str | None) -> float:
    """Return the expiry timestamp (exp claim) of a JWT, 0 if unreadable.

    The signature is not checked: the value is only used to decide when to
    sign in again. An unreadable token is treated as expired.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:  # pylint: disable=broad-except
        return 0.0


def _is_auth_error(err: Exception) -> bool:
    """Return True if the error is an HTTP 401/403 from the API."""
    response = getattr(err, "response", None)
    return getattr(response, "status_code", None) in (401, 403)


class EdilkaminCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(
        self,
        hass,
        username: str,
        password: str,
        mac_address: str,
    ) -> None:
        """Initialize my coordinator."""
        super().__init__(
            hass,
            LOGGER,
            # Name of the data. For logging purposes.
            name="Edilkamin updater",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=180),
        )
        self._username = username
        self._password = password
        self._mac_address = mac_address

        self._token = None
        self._device_info = {}

    async def refresh_token(self) -> str:
        """Login to refresh the token."""
        return await self.hass.async_add_executor_job(
            edilkamin.sign_in,
            self._username,
            self._password
        )

    def _token_is_valid(self) -> bool:
        """Return True if the cached token can still be used."""
        return (
            self._token is not None
            and _token_expiry(self._token) - time.time() > TOKEN_MIN_VALIDITY
        )

    async def update(self) -> None:
        """Get the latest data and update the relevant Entity attributes."""
        signed_in = False
        if not self._token_is_valid():
            self._token = await self.refresh_token()
            signed_in = True
        try:
            return await self.hass.async_add_executor_job(
                edilkamin.device_info,
                self._token,
                self._mac_address
            )
        except Exception as err:  # pylint: disable=broad-except
            # The cached token was rejected: sign in again and retry once
            if signed_in or not _is_auth_error(err):
                raise
            LOGGER.debug("Token rejected, signing in again")
            self._token = await self.refresh_token()
            return await self.hass.async_add_executor_job(
                edilkamin.device_info,
                self._token,
                self._mac_address
            )

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        try:
            # Note: asyncio.TimeoutError and aiohttp.ClientError are already
            # handled by the data update coordinator.
            async with async_timeout.timeout(10):
                return await self.update()
        except:
            raise UpdateFailed("Error communicating with API")

    def get_token(self):
        return self._token

    def get_mac(self):
        return self._mac_address
