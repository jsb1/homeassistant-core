"""Support for Modbus Register numbers."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import (
    CONF_MODE,
    CONF_STEP,
    NumberEntity,
    RestoreNumber,
)
from homeassistant.const import (
    CONF_DEVICE_CLASS,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_NAME,
    CONF_OFFSET,
    CONF_SENSORS,
    CONF_UNIQUE_ID,
    CONF_UNIT_OF_MEASUREMENT,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import get_hub
from .const import (
    _LOGGER,
    CALL_TYPE_COIL,
    CALL_TYPE_DISCRETE,
    CALL_TYPE_REGISTER_HOLDING,
    CALL_TYPE_REGISTER_INPUT,
    CALL_TYPE_WRITE_COIL,
    CALL_TYPE_WRITE_COILS,
    CALL_TYPE_WRITE_REGISTER,
    CALL_TYPE_WRITE_REGISTERS,
    CALL_TYPE_X_COILS,
    CALL_TYPE_X_REGISTER_HOLDINGS,
    CONF_SCALE,
    CONF_SLAVE_COUNT,
    CONF_VIRTUAL_COUNT,
    DEFAULT_OFFSET,
    DEFAULT_SCALE,
)
from .entity import ModbusStructEntity
from .modbus import ModbusHub

PARALLEL_UPDATES = 1

WRITE_TYPE_MAP = {
    CALL_TYPE_REGISTER_INPUT: None,  # Read-only
    CALL_TYPE_DISCRETE: None,  # Read-only
    CALL_TYPE_COIL: CALL_TYPE_WRITE_COIL,
    CALL_TYPE_X_COILS: CALL_TYPE_WRITE_COILS,
    CALL_TYPE_REGISTER_HOLDING: CALL_TYPE_WRITE_REGISTER,
    CALL_TYPE_X_REGISTER_HOLDINGS: CALL_TYPE_WRITE_REGISTERS,
}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Modbus numbers."""

    if discovery_info is None:
        return

    numbers: list[ModbusRegisterNumber | SlaveNumber] = []
    hub = get_hub(hass, discovery_info[CONF_NAME])
    for entry in discovery_info[CONF_SENSORS]:
        slave_count = entry.get(CONF_SLAVE_COUNT, None) or entry.get(
            CONF_VIRTUAL_COUNT, 0
        )
        number = ModbusRegisterNumber(hass, hub, entry, slave_count)
        if slave_count > 0:
            numbers.extend(await number.async_setup_slaves(hass, slave_count, entry))
        numbers.append(number)
    async_add_entities(numbers)


class ModbusRegisterNumber(ModbusStructEntity, RestoreNumber, NumberEntity):
    """Modbus register number."""

    def __init__(
        self,
        hass: HomeAssistant,
        hub: ModbusHub,
        entry: dict[str, Any],
        slave_count: int,
    ) -> None:
        """Initialize the modbus register number."""
        super().__init__(hass, hub, entry)
        if slave_count:
            self._count = self._count * (slave_count + 1)
        self._coordinator: DataUpdateCoordinator[list[float | None] | None] | None = (
            None
        )
        self._scale = entry.get(CONF_SCALE, DEFAULT_SCALE)
        self._offset = entry.get(CONF_OFFSET, DEFAULT_OFFSET)
        self._attr_native_unit_of_measurement = entry.get(CONF_UNIT_OF_MEASUREMENT)
        self._attr_device_class = entry.get(CONF_DEVICE_CLASS)
        self._attr_mode = entry.get(CONF_MODE, "auto")
        self._attr_native_min_value = entry.get(CONF_MIN_VALUE)
        self._attr_native_max_value = entry.get(CONF_MAX_VALUE)
        self._attr_native_step = entry.get(CONF_STEP)
        if self._precision > 0 or self._scale != int(self._scale):
            self._value_is_int = False
        if self._precision > 0 and self._data_type not in ["string", "custom"]:
            self._attr_suggested_display_precision = self._precision

    async def async_setup_slaves(
        self, hass: HomeAssistant, slave_count: int, entry: dict[str, Any]
    ) -> list[SlaveNumber]:
        """Add slaves as needed (1 read for multiple numbers)."""

        name = self._attr_name or "modbus_number"
        self._coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            config_entry=None,
            name=name,
        )

        return [
            SlaveNumber(self._coordinator, idx, entry) for idx in range(slave_count)
        ]

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await self.async_base_added_to_hass()
        state = await self.async_get_last_number_data()
        if state:
            self._attr_native_value = state.native_value

    async def _async_update(self) -> None:
        """Update the state of the number."""
        raw_result = await self._hub.async_pb_call(
            self._device_address, self._address, self._count, self._input_type
        )
        if raw_result is None:
            self._attr_available = False
            self._attr_native_value = None
            if self._coordinator:
                self._coordinator.async_set_updated_data(None)
            self.async_write_ha_state()
            return

        self._attr_available = True
        result = self.unpack_structure_result(
            raw_result.registers, self._scale, self._offset
        )

        if self._coordinator:
            result_array = self._parse_result_array(result)
            self._attr_native_value = result_array[0] if result_array else None
            self._coordinator.async_set_updated_data(result_array)
        else:
            self._attr_native_value = result
        self.async_write_ha_state()

    def _parse_result_array(self, result: str | None) -> list[float | None]:
        """Parse comma-separated result string into array of values.

        Args:
            result: Comma-separated string of values or None.

        Returns:
            List of float or int values, or None if result is None.
        """
        if not result:
            return (self._slave_count + 1) * [None]

        result_array: list[float | None] = []
        for item in result.split(","):
            if item == "None":
                result_array.append(None)
                continue

            try:
                value = float(item) if not self._value_is_int else int(item)
                result_array.append(value)
            except (ValueError, TypeError) as err:
                _LOGGER.debug(
                    "Failed to parse value '%s' as %s: %s",
                    item,
                    "integer" if self._value_is_int else "float",
                    err,
                )
                result_array.append(None)

        return result_array

    async def async_set_native_value(self, value: float) -> None:
        """Set new value (write to Modbus)."""
        if self._min_value is not None and value < self._min_value:
            raise ValueError(
                f"Value {value} is below minimum {self._min_value}"
            )
        if self._max_value is not None and value > self._max_value:
            raise ValueError(
                f"Value {value} is above maximum {self._max_value}"
            )

        write_type = WRITE_TYPE_MAP.get(self._input_type)
        if write_type is None:
            return

        result = await self._hub.async_pb_call(
            self._device_address, self._address, value, write_type
        )
        if result is None:
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True
        self._attr_native_value = value
        self.async_write_ha_state()


class SlaveNumber(
    CoordinatorEntity[DataUpdateCoordinator[list[float | None] | None]],
    RestoreNumber,
    NumberEntity,
):
    """Modbus slave register number."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._attr_available

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[list[float | None] | None],
        idx: int,
        entry: dict[str, Any],
    ) -> None:
        """Initialize the Modbus register number."""
        idx += 1
        self._idx = idx
        self._attr_name = f"{entry[CONF_NAME]} {idx}"
        self._attr_unique_id = entry.get(CONF_UNIQUE_ID)
        if self._attr_unique_id:
            self._attr_unique_id = f"{self._attr_unique_id}_{idx}"
        self._attr_native_unit_of_measurement = entry.get(CONF_UNIT_OF_MEASUREMENT)
        self._attr_device_class = entry.get(CONF_DEVICE_CLASS)
        self._attr_mode = entry.get(CONF_MODE, "auto")
        self._attr_native_min_value = entry.get(CONF_MIN_VALUE)
        self._attr_native_max_value = entry.get(CONF_MAX_VALUE)
        self._attr_native_step = entry.get(CONF_STEP)
        self._attr_available = False
        super().__init__(coordinator)

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        if state := await self.async_get_last_state():
            self._attr_native_value = state.native_value
        await super().async_added_to_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        result = self.coordinator.data
        if not result or self._idx >= len(result):
            self._attr_native_value = None
            self._attr_available = False
        else:
            self._attr_native_value = result[self._idx]
            self._attr_available = True
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set new value (write to Modbus)."""
        if self._min_value is not None and value < self._min_value:
            raise ValueError(
                f"Value {value} is below minimum {self._min_value}"
            )
        if self._max_value is not None and value > self._max_value:
            raise ValueError(
                f"Value {value} is above maximum {self._max_value}"
            )

        write_type = WRITE_TYPE_MAP.get(self._input_type)
        if write_type is None:
            return

        result = await self._hub.async_pb_call(
            self._device_address, self._address, value, write_type
        )
        if result is None:
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True
        self._attr_native_value = value
        self.async_write_ha_state()
