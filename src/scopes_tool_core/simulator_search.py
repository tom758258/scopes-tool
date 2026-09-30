"""Simulated waveform Search SCPI write and query handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .simulator_support import SimulatorBackendError, _parse_scpi_bool_write

if TYPE_CHECKING:
    from .simulator_backend import SimulatorBackend


def apply_search_write(backend: SimulatorBackend, command: str) -> bool:
    """Apply one simulated Search write, reporting whether it was recognized."""

    upper = command.upper()
    if upper.startswith(":SEARCH:STATE "):
        backend.search_enabled = _parse_scpi_bool_write(command)
    elif upper.startswith(":SEARCH:MODE "):
        value = command.rsplit(" ", 1)[1].upper()
        canonical_by_scpi = {
            "SER1": "serial1",
            "SERIAL1": "serial1",
            "SER2": "serial2",
            "SERIAL2": "serial2",
            "EDGE": "edge",
            "GLIT": "glitch",
            "GLITCH": "glitch",
            "RUNT": "runt",
            "TRAN": "transition",
            "TRANSITION": "transition",
            "PEAK": "peak",
        }
        scpi_by_canonical = {
            "serial1": "SERial1",
            "serial2": "SERial2",
            "edge": "EDGE",
            "glitch": "GLITch",
            "runt": "RUNT",
            "transition": "TRANsition",
            "peak": "PEAK",
        }
        canonical = canonical_by_scpi.get(value)
        if canonical is None or canonical not in backend._capabilities.search_modes:
            raise SimulatorBackendError(
                f"Search mode {value!r} is not supported by simulator model {backend.model}."
            )
        backend.search_mode = scpi_by_canonical[canonical]
    elif upper.startswith(":SEARCH:SERIAL:UART:MODE "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_uart_mode[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:UART:DATA "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_uart_data[bus] = int(command.split(" ", 1)[1].strip())
    elif upper.startswith(":SEARCH:SERIAL:UART:QUALIFIER "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_uart_qualifier[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:IIC:MODE "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_i2c_mode[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:IIC:PATTERN:ADDRESS "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_i2c_address[bus] = int(command.split(" ", 1)[1].strip())
    elif upper.startswith(":SEARCH:SERIAL:IIC:PATTERN:DATA2 "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_i2c_data2[bus] = int(command.split(" ", 1)[1].strip())
    elif upper.startswith(":SEARCH:SERIAL:IIC:PATTERN:DATA "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_i2c_data[bus] = int(command.split(" ", 1)[1].strip())
    elif upper.startswith(":SEARCH:SERIAL:IIC:QUALIFIER "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_i2c_qualifier[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:SPI:MODE "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_spi_mode[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:SPI:PATTERN:DATA "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        raw_pattern = command.split(" ", 1)[1].strip().strip('"')
        backend.search_spi_data[bus] = raw_pattern.upper() if raw_pattern.lower().startswith("0x") else raw_pattern
    elif upper.startswith(":SEARCH:SERIAL:SPI:PATTERN:WIDTH "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_spi_width[bus] = int(command.split(" ", 1)[1].strip())
    elif upper.startswith(":SEARCH:SERIAL:CAN:MODE "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_can_mode[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:CAN:PATTERN:DATA:LENGTH "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_can_data_length[bus] = int(command.split(" ", 1)[1].strip())
    elif upper.startswith(":SEARCH:SERIAL:CAN:PATTERN:DATA "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        raw_pattern = command.split(" ", 1)[1].strip().strip('"')
        backend.search_can_data[bus] = raw_pattern.upper() if raw_pattern.lower().startswith("0x") else raw_pattern
    elif upper.startswith(":SEARCH:SERIAL:CAN:PATTERN:ID:MODE "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        backend.search_can_id_mode[bus] = command.split(" ", 1)[1].strip()
    elif upper.startswith(":SEARCH:SERIAL:CAN:PATTERN:ID "):
        bus = 2 if backend.search_mode == "SERial2" else 1
        raw_pattern = command.split(" ", 1)[1].strip().strip('"')
        backend.search_can_id[bus] = raw_pattern.upper() if raw_pattern.lower().startswith("0x") else raw_pattern
    elif upper.startswith(":SEARCH:EVENT "):
        if not backend._capabilities.supports_search_event_navigation:
            raise SimulatorBackendError(
                f"Search event navigation is not supported by simulator model {backend.model}."
            )
        value_str = command.rsplit(" ", 1)[1].strip()
        try:
            val = int(value_str)
        except ValueError as exc:
            raise SimulatorBackendError(
                f"Invalid search event for simulator: {command}"
            ) from exc
        if val <= 0:
            raise SimulatorBackendError(
                f"Invalid search event for simulator: {command}"
            )
        backend.search_event = val
    else:
        return False
    return True


def query_search(backend: SimulatorBackend, command: str) -> str | None:
    """Return the simulated Search response, or None for other commands."""

    upper = command.upper()
    if upper == ":SEARCH:STATE?":
        return "1" if backend.search_enabled else "0"
    if upper == ":SEARCH:MODE?":
        return backend.search_mode if backend.search_enabled else "OFF"
    if upper == ":SEARCH:COUNT?":
        return str(backend.search_count)
    if upper == ":SEARCH:SERIAL:UART:MODE?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_uart_mode[bus]
    if upper == ":SEARCH:SERIAL:UART:DATA?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return str(backend.search_uart_data[bus])
    if upper == ":SEARCH:SERIAL:UART:QUALIFIER?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_uart_qualifier[bus]
    if upper == ":SEARCH:SERIAL:IIC:MODE?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_i2c_mode[bus]
    if upper == ":SEARCH:SERIAL:IIC:PATTERN:ADDRESS?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return str(backend.search_i2c_address[bus])
    if upper == ":SEARCH:SERIAL:IIC:PATTERN:DATA?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return str(backend.search_i2c_data[bus])
    if upper == ":SEARCH:SERIAL:IIC:PATTERN:DATA2?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return str(backend.search_i2c_data2[bus])
    if upper == ":SEARCH:SERIAL:IIC:QUALIFIER?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_i2c_qualifier[bus]
    if upper == ":SEARCH:SERIAL:SPI:MODE?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_spi_mode[bus]
    if upper == ":SEARCH:SERIAL:SPI:PATTERN:DATA?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        val = backend.search_spi_data[bus]
        return f'"{val}"' if not (val.startswith('"') and val.endswith('"')) else val
    if upper == ":SEARCH:SERIAL:SPI:PATTERN:WIDTH?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return str(backend.search_spi_width[bus])
    if upper == ":SEARCH:SERIAL:CAN:MODE?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_can_mode[bus]
    if upper == ":SEARCH:SERIAL:CAN:PATTERN:DATA?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        val = backend.search_can_data[bus]
        return f'"{val}"' if not (val.startswith('"') and val.endswith('"')) else val
    if upper == ":SEARCH:SERIAL:CAN:PATTERN:DATA:LENGTH?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return str(backend.search_can_data_length[bus])
    if upper == ":SEARCH:SERIAL:CAN:PATTERN:ID?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        val = backend.search_can_id[bus]
        return f'"{val}"' if not (val.startswith('"') and val.endswith('"')) else val
    if upper == ":SEARCH:SERIAL:CAN:PATTERN:ID:MODE?":
        bus = 2 if backend.search_mode == "SERial2" else 1
        return backend.search_can_id_mode[bus]
    if upper == ":SEARCH:EVENT?":
        if not backend._capabilities.supports_search_event_navigation:
            raise SimulatorBackendError(
                f"Search event navigation is not supported by simulator model {backend.model}."
            )
        return str(backend.search_event)
    return None
