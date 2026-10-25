"""Binary sensor platform for Edilkamin."""
from __future__ import annotations

from .const import DOMAIN

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)

from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


# Extra read-only flags, from the status of the stove
FLAG_SENSORS = [
    {
        "flag": "is_cleaning_in_progress",
        "label": "Cleaning in Progress",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "icon": "mdi:broom",
    },
    {
        "flag": "is_backup_battery_level_low",
        "label": "Backup Battery Low",
        "device_class": BinarySensorDeviceClass.BATTERY,
        "category": EntityCategory.DIAGNOSTIC,
    },
    {
        "flag": "is_cat_service_required",
        "label": "Service Required",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "category": EntityCategory.DIAGNOSTIC,
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the stove with config flow."""
    name = entry.data[CONF_NAME]
    coordinator = hass.data[DOMAIN]["coordinator"]

    async_add_entities(
        [
            PelletReserve(coordinator, name)
        ],
        update_before_add=False,
    )

    # Extra flags, only created if the stove reports them
    flags = (coordinator.data or {}).get("status", {}).get("flags", {})
    async_add_entities(
        [
            FlagBinarySensor(coordinator, name, **description)
            for description in FLAG_SENSORS
            if description["flag"] in flags
        ],
        update_before_add=False,
    )


class PelletReserve(CoordinatorEntity, BinarySensorEntity):
    """Pellet in Reserve Binary sensor entity"""

    def __init__(
        self,
        coordinator,
        name: str,
    ) -> None:
        """Create the Edilkamin Pellet in Reserve binary sensor entity."""
        super().__init__(coordinator)

        self._mac_address = coordinator.get_mac()

        self._attr_name = f"{name} Pellet in Reserve"
        self._attr_unique_id = f"{self._mac_address}_pelletinreserve"
        self._attr_icon = "mdi:storage-tank"

        # Initial value
        self._attr_is_on = (
            self.coordinator.data["status"]["flags"]["is_pellet_in_reserve"]
        )

        self._attr_device_info = {
            "identifiers": {("edilkamin", self._mac_address)}
        }

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = (
            self.coordinator.data["status"]["flags"]["is_pellet_in_reserve"]
        )
        self.async_write_ha_state()


class FlagBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Read-only binary sensor reading a flag of the stove status."""

    def __init__(
        self,
        coordinator,
        name: str,
        flag: str,
        label: str,
        device_class=None,
        icon=None,
        category=None,
    ) -> None:
        """Create the binary sensor."""
        super().__init__(coordinator)

        self._mac_address = coordinator.get_mac()
        self._flag = flag

        self._attr_name = f"{name} {label}"
        self._attr_unique_id = f"{self._mac_address}_{flag}"
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_entity_category = category

        self._attr_device_info = {
            "identifiers": {("edilkamin", self._mac_address)}
        }

    @property
    def is_on(self) -> bool | None:
        """Return the value of the flag, None if the stove does not report it."""
        flags = (self.coordinator.data or {}).get("status", {}).get("flags", {})
        value = flags.get(self._flag)
        return None if value is None else bool(value)
