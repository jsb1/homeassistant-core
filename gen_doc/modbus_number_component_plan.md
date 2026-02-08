# Modbus Number Component Implementation Plan

## Overview
Add a number component to the Home Assistant Modbus integration, similar to the existing sensor.py implementation. The component supports both read and write operations for Modbus registers.

## Architecture

### File Structure
```
homeassistant/components/modbus/
├── number.py          # New file - Modbus number entity implementation
├── const.py           # Update - Add CONF_NUMBERS and PLATFORMS
├── __init__.py        # Update - Register number platform
└── entity.py          # Existing - Base classes (no changes needed)
```

## Implementation Details

### 1. `modbus/number.py`

#### Class: `ModbusRegisterNumber`
- **Inherits from**: `ModbusStructEntity`, `RestoreNumber`, `NumberEntity`
- **Purpose**: Main number entity for single Modbus register
- **Key attributes**:
  - `native_unit_of_measurement`: Unit of measurement (e.g., "°C", "W")
  - `device_class`: Number device class (e.g., `NumberDeviceClass.TEMPERATURE`)
  - `mode`: Number mode ("auto", "box", "slider")
  - `native_min_value`: Minimum value in native units
  - `native_max_value`: Maximum value in native units
  - `native_step`: Step size for increments/decrements
  - `precision`: Number of decimal places for display (from config)
  - `suggested_display_precision`: Precision for UI display (for floats)
- **DataUpdateCoordinator**: Used for multi-slave setups to coordinate data updates
- **Methods**:
  - `async_setup_platform()`: Entry point for platform setup
  - `async_setup_slaves()`: Handle multiple slave devices
  - `async_added_to_hass()`: Restore previous state
  - `_async_update()`: Read from Modbus
  - `async_set_native_value()`: Write value to Modbus register

#### Class: `SlaveNumber`
- **Inherits from**: `CoordinatorEntity`, `RestoreNumber`, `NumberEntity`
- **Purpose**: Number entity for slave devices in multi-slave setups
- **Key attributes**:
  - `name`: Formatted as "{base_name} {idx}"
  - `unique_id`: Formatted as "{base_unique_id}_{idx}"
- **DataUpdateCoordinator**: Receives data from parent coordinator
- **Methods**:
  - `_handle_coordinator_update()`: Handle coordinator data updates
  - `async_set_native_value()`: Write value to Modbus register

### 2. `modbus/const.py` Updates

#### Add Configuration Constants
```python
CONF_NUMBERS = "numbers"
```

#### Update PLATFORMS Tuple
```python
PLATFORMS = (
    (Platform.BINARY_SENSOR, CONF_BINARY_SENSORS),
    (Platform.CLIMATE, CONF_CLIMATES),
    (Platform.COVER, CONF_COVERS),
    (Platform.LIGHT, CONF_LIGHTS),
    (Platform.FAN, CONF_FANS),
    (Platform.NUMBER, CONF_NUMBERS),  # Add this line
    (Platform.SENSOR, CONF_SENSORS),
    (Platform.SWITCH, CONF_SWITCHES),
)
```

### 3. `modbus/__init__.py` Updates

#### Import Number Platform
```python
from . import number
```

#### Register Platform
```python
PLATFORMS = [
    (Platform.BINARY_SENSOR, CONF_BINARY_SENSORS),
    (Platform.CLIMATE, CONF_CLIMATES),
    (Platform.COVER, CONF_COVERS),
    (Platform.LIGHT, CONF_LIGHTS),
    (Platform.FAN, CONF_FANS),
    (Platform.NUMBER, CONF_NUMBERS),
    (Platform.SENSOR, CONF_SENSORS),
    (Platform.SWITCH, CONF_SWITCHES),
]
```

### 4. `modbus/__init__.py` Schema Updates

#### Add NUMBER_SCHEMA
```python
NUMBER_SCHEMA = vol.All(
    BASE_STRUCT_SCHEMA.extend(
        {
            vol.Optional(CONF_DEVICE_CLASS): DEVICE_CLASSES_SCHEMA,
            vol.Optional(CONF_MODE, default="auto"): vol.In(["auto", "box", "slider"]),
            vol.Optional(CONF_MIN_VALUE): vol.Coerce(float),
            vol.Optional(CONF_MAX_VALUE): vol.Coerce(float),
            vol.Optional(CONF_STEP): vol.Coerce(float),
            vol.Optional(CONF_PRECISION): cv.positive_int,
        }
    ),
)
```

#### Add to MODBUS_SCHEMA
```python
MODBUS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_HUB): cv.string,
        vol.Optional(CONF_TIMEOUT, default=3): cv.socket_timeout,
        vol.Optional(CONF_DELAY, default=0): cv.positive_int,
        vol.Optional(CONF_MSG_WAIT): cv.positive_int,
        vol.Optional(CONF_BINARY_SENSORS): vol.All(
            cv.ensure_list, [BINARY_SENSOR_SCHEMA]
        ),
        vol.Optional(CONF_CLIMATES): vol.All(
            cv.ensure_list, [vol.All(CLIMATE_SCHEMA, struct_validator)]
        ),
        vol.Optional(CONF_COVERS): vol.All(cv.ensure_list, [COVERS_SCHEMA]),
        vol.Optional(CONF_LIGHTS): vol.All(cv.ensure_list, [LIGHT_SCHEMA]),
        vol.Optional(CONF_NUMBERS): vol.All(
            cv.ensure_list, [vol.All(NUMBER_SCHEMA, struct_validator)]
        ),
        vol.Optional(CONF_SENSORS): vol.All(
            cv.ensure_list, [vol.All(SENSOR_SCHEMA, struct_validator)]
        ),
        vol.Optional(CONF_SWITCHES): vol.All(cv.ensure_list, [SWITCH_SCHEMA]),
        vol.Optional(CONF_FANS): vol.All(cv.ensure_list, [FAN_SCHEMA]),
    },
    extra=vol.ALLOW_EXTRA,
)
```

## Configuration Schema

### Number Configuration Example
```yaml
modbus:
  - name: my_modbus_hub
    type: tcp
    host: 192.168.1.100
    port: 502
    sensors:
      - name: Temperature
        address: 0
        input_type: holding
        data_type: float32
        scale: 0.1
        unit_of_measurement: "°C"
        device_class: temperature
        min_value: -50
        max_value: 150
        step: 0.5
    numbers:
      - name: Target Temperature
        address: 10
        input_type: holding
        data_type: float32
        scale: 0.1
        unit_of_measurement: "°C"
        device_class: temperature
        min_value: 16
        max_value: 30
        step: 0.5
        mode: slider
        precision: 1  # Display with 1 decimal place
```

### Precision Handling

The `precision` configuration parameter controls the number of decimal places displayed in the UI:

| Data Type | Default Precision | Behavior |
|-----------|-------------------|----------|
| `float16`, `float32`, `float64` | 2 | Display with specified decimal places |
| `int16`, `int32`, `int64`, `uint16`, `uint32`, `uint64` | 0 | Display as integer |
| `string`, `custom` | N/A | Not applicable |

**Example configurations:**
```yaml
# Display temperature with 1 decimal place
numbers:
  - name: Temperature
    precision: 1

# Display power with 2 decimal places
numbers:
  - name: Power
    precision: 2

# Integer values (no decimal places)
numbers:
  - name: Counter
    data_type: uint16
    precision: 0
```

**Note**: Precision affects display only. The native value stored and used internally maintains full precision from the Modbus register.

### Schema Constants

| Constant | Type | Description |
|----------|------|-------------|
| `BASE_COMPONENT_SCHEMA` | vol.Schema | Base schema with name, address, slave, scan_interval, unique_id |
| `BASE_STRUCT_SCHEMA` | vol.Schema | Base schema with input_type, count, data_type, structure, scale, offset, precision, swap |
| `NUMBER_SCHEMA` | vol.All | Number-specific schema extending BASE_STRUCT_SCHEMA |
| `MODBUS_SCHEMA` | vol.Schema | Main schema including all platform schemas |
| `CONF_NUMBERS` | str | Configuration key for numbers list |
| `CONF_MODE` | str | Number mode: "auto", "box", or "slider" |
| `CONF_STEP` | float | Step size for increments/decrements |
| `CONF_MIN_VALUE` | float | Minimum value |
| `CONF_MAX_VALUE` | float | Maximum value |
| `CONF_PRECISION` | int | Number of decimal places for display |

## Key Differences from Sensor Component

| Aspect | Sensor | Number |
|--------|--------|--------|
| Base Class | `SensorEntity` | `NumberEntity` |
| Restore Mixin | `RestoreSensor` | `RestoreNumber` |
| State Property | `native_value` | `native_value` |
| Set Method | N/A | `async_set_native_value()` |
| Config Key | `CONF_SENSORS` | `CONF_NUMBERS` |
| Platform | `Platform.SENSOR` | `Platform.NUMBER` |

## DataUpdateCoordinator Pattern

### Purpose
The DataUpdateCoordinator is used to coordinate data updates across multiple slave devices in a single Modbus read operation. This is essential for efficiency when reading multiple registers from different slave addresses.

### How It Works

1. **Main Entity (`ModbusRegisterNumber`)**:
   - Creates a `DataUpdateCoordinator` instance when `slave_count > 0`
   - Performs a single Modbus read for all slave devices
   - Processes the raw result and splits it into individual values
   - Sets the coordinator data with an array of values: `[value_1, value_2, ..., value_n]`
   - Each slave entity reads its specific value from the coordinator data

2. **Slave Entities (`SlaveNumber`)**:
   - Receive data from the coordinator via `_handle_coordinator_update()`
   - Index into the coordinator data array using `self._idx`
   - Update their `native_value` based on the coordinator data

### Coordinator Data Structure
```python
# Coordinator data is a list of float | None values
# Example with 3 slaves:
# coordinator.data = [23.5, None, 18.2]
# Slave 1 (idx=0) reads: 23.5
# Slave 2 (idx=1) reads: None
# Slave 3 (idx=2) reads: 18.2
```

### Benefits
- **Efficiency**: Single Modbus read for multiple slave devices
- **Consistency**: All slaves get data from the same read operation
- **Scalability**: Easy to add more slave devices without changing the read pattern
- **Error Handling**: Coordinator handles data availability and None values

## Write Support Implementation

### Main Entity (`ModbusRegisterNumber`)
The main entity supports writing to Modbus registers via `async_set_native_value()`:

```python
async def async_set_native_value(self, value: float) -> None:
    """Set new value (write to Modbus)."""
    # Convert value to register format based on data_type
    # Apply scale and offset if configured
    # Write to Modbus using the appropriate write type
    # Update local state
```

### Slave Entity (`SlaveNumber`)
Slave entities also support writing to their respective Modbus registers:

```python
async def async_set_native_value(self, value: float) -> None:
    """Set new value (write to Modbus)."""
    # Convert value to register format
    # Write to Modbus using the appropriate write type
    # Update local state
```

### Write Type Configuration
The write type is determined by the `input_type` configuration:
- `holding` → `CALL_TYPE_WRITE_REGISTER` (write to holding register)
- `input` → Not writable (read-only)
- `coil` → `CALL_TYPE_WRITE_COIL` (write to coil)
- `discrete_input` → Not writable (read-only)

### Write Flow
1. User sets value via UI or service call
2. `async_set_native_value()` is called
3. Value is converted to native format (apply scale/offset if needed)
4. Value is written to Modbus register
5. Local state is updated
6. Coordinator data is refreshed (for slave entities)

### Error Handling
- Invalid value range (below min_value or above max_value) → ServiceValidationError
- Modbus write failure → Log error, set unavailable
- Connection issues → Log error, set unavailable

## Implementation Notes

1. **Write Support**: Both main and slave entities support writing to Modbus registers
2. **Value Conversion**: Values are converted using scale and offset from config
3. **State Restoration**: Uses `NumberExtraStoredData` for restoring previous values
4. **Coordinator Pattern**: Supports multi-slave setups with coordinator pattern
5. **Precision Handling**: `precision` config controls decimal places for display (affects `suggested_display_precision`)

## Testing Considerations

1. **Unit Tests**: Test entity creation, state updates, and restoration
2. **Integration Tests**: Test with mock Modbus devices
3. **Config Validation**: Ensure proper schema validation
4. **Slave Device Tests**: Verify multi-slave number entities work correctly

## Dependencies

- `homeassistant.components.number` - NumberEntity, RestoreNumber, NumberEntityDescription
- `homeassistant.helpers.update_coordinator` - CoordinatorEntity, DataUpdateCoordinator
- Existing modbus dependencies (ModbusHub, ModbusStructEntity, etc.)

## Implementation Order

1. Create `modbus/number.py` with both entity classes
2. Add `CONF_NUMBERS` constant to `modbus/const.py`
3. Add `Platform.NUMBER` to `PLATFORMS` tuple in `modbus/const.py`
4. Update `modbus/__init__.py` to import and register the number platform
5. Write tests for the new component
