"""Tektronix SCPI dialect over the shared simulated instrument state."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re

from .simulator_backend import SimulatorBackend, SimulatorBackendError, _parse_scpi_number, _simulated_screenshot_bmp


@dataclass
class TektronixSimulatorBackend(SimulatorBackend):
    backend: str = "Tektronix simulator"
    stop_after: str = "RUNSTOP"
    tek_setups: dict[int, dict[str, object]] = field(default_factory=dict)

    tek_settings: dict[str, str] = field(default_factory=dict)
    tek_measurements: dict[int, dict[str, str]] = field(default_factory=dict)
    hardcopy_port: str = "USB"
    hardcopy_pending: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.physical_model.vendor_id != "tektronix":
            raise SimulatorBackendError("Tektronix simulator requires a Tektronix model")
        if self.acquisition_count not in (self._capabilities.average_counts or ()):
            self.acquisition_count = self._capabilities.average_counts[0]
        self.tek_settings = {
            "CURSOR:FUNCTION": "OFF", "CURSOR:SELECT:SOURCE": "CH1", "SELECT:CONTROL": "CH1",
            "CURSOR:VBARS:UNITS": "SECONDS", "CURSOR:HBARS:UNITS": "BASE" if self._capabilities.series == "TBS2000B" else "VOLTS",
            "CURSOR:VBARS:POSITION1": "0", "CURSOR:VBARS:POSITION2": "0.001",
            "CURSOR:HBARS:POSITION1": "0", "CURSOR:HBARS:POSITION2": "1",
            "SELECT:MATH": "OFF", "MATH:DEFINE": '"CH1+CH2"',
            "DISPLAY:PERSISTENCE": "OFF", "DISPLAY:PERSISTENCE:STATE": "OFF", "DISPLAY:PERSISTENCE:VALUE": "1",
            "SAVE:IMAGE:FILEFORMAT": "PNG", "SAVE:WAVEFORM:FILEFORMAT": "SPREADSheet",
            "HORIZONTAL:DELAY:MODE": "OFF", "HORIZONTAL:DELAY:TIME": "0",
            "TRIGGER:A:PULSE:CLASS": "WIDTH", "TRIGGER:A:RUNT:SOURCE": "CH1",
            "TRIGGER:A:RUNT:POLARITY": "POSITIVE", "TRIGGER:A:RUNT:WHEN": "OCCURS", "TRIGGER:A:RUNT:WIDTH": "1e-6",
            "TRIGGER:MAIN:VIDEO:SOURCE": "CH1", "TRIGGER:MAIN:VIDEO:STANDARD": "NTSC",
            "TRIGGER:MAIN:VIDEO:POLARITY": "NORMAL", "TRIGGER:MAIN:VIDEO:SYNC": "ODD",
            **self.tek_settings,
        }
        slots = 5 if self._capabilities.series == "TDS2000B" else 6
        self.tek_measurements = {i: {"TYPE": "NONE", "SOURCE": "CH1", "SOURCE1": "CH1", "STATE": "OFF"} for i in range(1, slots + 1)}
        if self._capabilities.series != "TBS2000B":
            self.record_length_points = self.acquisition_points = 2500
            self.hardcopy_format = "BMP"
        self.trigger_holdoff = self._capabilities.trigger_holdoff_min_seconds or 0.0
        self.trigger_slope = "FALL" if self.trigger_slope.upper().startswith("NEG") else "RISE"
        if self._capabilities.series == "TBS2000B":
            self.trigger_levels.setdefault(self.trigger_source, self.trigger_level)

    def _record(self, command: str, *, query: bool) -> None:
        self._ensure_open()
        self.history.append(command)
        self._raise_configured_failure(
            self.query_failures if query else self.write_failures, command
        )

    def _channel_number(self, token: str) -> int:
        return self._validate_channel(int(token))

    def _reference_slot(self, token: str) -> int:
        name = token.upper()
        if self._capabilities.series == "TBS2000B":
            slots = {"REF1": 1, "REF2": 2}
        else:
            slots = {"REFA": 1, "REFB": 2}
        if name not in slots:
            raise SimulatorBackendError(f"Unsupported Tek reference: {token}")
        return slots[name]

    def _trigger_path(self, command: str) -> str | None:
        root = "TRIGGER:A:" if self._capabilities.series == "TBS2000B" else "TRIGGER:MAIN:"
        upper = command.upper()
        return upper[len(root):] if upper.startswith(root) else None

    def _write_supported_settings(self, command: str) -> bool:
        header, _, value = command.partition(" ")
        header, token = header.upper(), value.upper()
        b2 = self._capabilities.series == "TBS2000B"
        match = re.fullmatch(r"CH(\d+):YUNIT", header)
        if match:
            channel = self._channel_number(match[1])
            if (not b2 or channel in self._capabilities.channel_units_channels) and token in {"V", "A"}:
                self.channel_units[channel] = "volt" if token == "V" else "amp"
                return True
        if header == "DISPLAY:PERSISTENCE" and not b2:
            if token in {"OFF", "INFINITE"} or value in {"1", "2", "5"}:
                self.tek_settings[header] = value
                return True
        if header == "DISPLAY:PERSISTENCE:VALUE" and b2:
            if token == "INFINITE" or 0.1 <= _parse_scpi_number(value) <= 60:
                self.tek_settings[header] = value
                return True
        if header == "CURSOR:FUNCTION" and token in ({"OFF"} if b2 else {"OFF", "VBARS", "HBARS"}):
            self.tek_settings[header] = value
            return True
        if header == "CURSOR:SELECT:SOURCE" and not b2 and re.fullmatch(r"CH\d+", token):
            self._channel_number(token[2:])
            self.tek_settings[header] = value
            return True
        if re.fullmatch(r"CURSOR:(VBARS|HBARS):POSITION[12]", header) and not b2:
            _parse_scpi_number(value)
            self.tek_settings[header] = value
            return True
        if header == "MATH:DEFINE" and value.strip('"').upper() in self._capabilities.math_expressions:
            self.tek_settings[header] = value
            return True
        choices = {"SELECT:MATH": {"ON", "OFF"}}
        if b2:
            choices.update({
                "DISPLAY:PERSISTENCE:STATE": {"ON", "OFF"}, "SAVE:IMAGE:FILEFORMAT": {"PNG", "BMP"},
                "SAVE:WAVEFORM:FILEFORMAT": {"SPREADSHEET"}, "TRIGGER:A:PULSE:CLASS": {"WIDTH", "RUNT"},
                "TRIGGER:A:RUNT:SOURCE": {"CH1", "CH2"}, "TRIGGER:A:RUNT:POLARITY": {"POSITIVE", "NEGATIVE"},
                "TRIGGER:A:RUNT:WHEN": {"OCCURS", "LESSTHAN", "MORETHAN"},
            })
            if header == "TRIGGER:A:RUNT:WIDTH" or re.fullmatch(r"TRIGGER:A:(LOWERTHRESHOLD|UPPERTHRESHOLD):CH[12]", header):
                _parse_scpi_number(value)
                self.tek_settings[header] = value
                return True
        else:
            choices.update({
                "TRIGGER:MAIN:VIDEO:SOURCE": {f"CH{i}" for i in range(1, self._capabilities.analog_channels + 1)},
                "TRIGGER:MAIN:VIDEO:STANDARD": {"NTSC", "PAL"}, "TRIGGER:MAIN:VIDEO:POLARITY": {"INVERT", "NORMAL"},
                "TRIGGER:MAIN:VIDEO:SYNC": {"ODD", "EVEN", "FIELD", "LINE"},
            })
        if header in choices and token in choices[header]:
            self.tek_settings[header] = value
            return True
        match = re.fullmatch(r"MEASUREMENT:MEAS(\d+):(TYPE|SOURCE1?|STATE)", header)
        if match and int(match[1]) in self.tek_measurements:
            setting = match[2]
            if setting == ("SOURCE1" if b2 else "SOURCE") and re.fullmatch(r"CH\d+", token):
                self._channel_number(token[2:])
            elif setting == "STATE" and b2 and token in {"ON", "OFF"}:
                pass
            elif setting == "TYPE":
                from .tektronix import TektronixOscilloscope
                scope = TektronixOscilloscope(self)
                scope.capabilities = self._capabilities
                types = scope._measurement_types()
                allowed = {types[item].upper() for item in self._capabilities.measurement_install_items}
                if token not in allowed | ({"NONE"} if not b2 else set()):
                    return False
            else:
                return False
            self.tek_measurements[int(match[1])][setting] = value
            return True
        if header == "SAVE:IMAGE" and re.fullmatch(r'"[^"\r\n]+"', value):
            self.tek_settings[header] = value
            return True
        if header == "HARDCOPY:INKSAVER" and not b2 and token in {"ON", "OFF"}:
            self.hardcopy_inksaver = token == "ON"
            return True
        if self._capabilities.screenshot_formats:
            if header == "HARDCOPY:FORMAT" and token in {"BMP", "EPS", "TIFF", "PCX", "RLE"}:
                self.hardcopy_format = value
                return True
            if header == "HARDCOPY:PORT" and token in {"USB", "FILE"}:
                self.hardcopy_port = value
                return True
            if header == "HARDCOPY:LAYOUT" and token in {"PORTRAIT", "LANDSCAPE"}:
                self.hardcopy_layout = value
                return True
            if header == "HARDCOPY" and token == "START" and self.hardcopy_format.upper() == "BMP":
                self.hardcopy_pending = True
                return True
        return False

    def _query_supported_settings(self, command: str) -> str | None:
        header = command.upper().removesuffix("?")
        b2 = self._capabilities.series == "TBS2000B"
        if header == "HORIZONTAL:RECORDLENGTH": return str(self.record_length_points)
        if b2 and header == "HORIZONTAL:SAMPLERATE": return str(self.sample_rate_hz)
        if b2 and header == "ACQUIRE:MAXSAMPLERATE": return str(self.maximum_sample_rate_hz)
        match = re.fullmatch(r"CH(\d+):(YUNIT|POSITION)", header)
        if match:
            channel = self._channel_number(match[1])
            if match[2] == "YUNIT" and (not b2 or channel in self._capabilities.channel_units_channels):
                return "A" if self.channel_units.get(channel) == "amp" else "V"
            if match[2] == "POSITION" and not b2: return "0"
        match = re.fullmatch(r"MEASUREMENT:MEAS(\d+):(TYPE|SOURCE1?|STATE)", header)
        if match and int(match[1]) in self.tek_measurements:
            if match[2] in ({"TYPE", "SOURCE1", "STATE"} if b2 else {"TYPE", "SOURCE"}):
                return self.tek_measurements[int(match[1])][match[2]]
        match = re.fullmatch(r"CURSOR:(VBARS|HBARS):DELTA", header)
        if match:
            root = f"CURSOR:{match[1]}:POSITION"
            return str(float(self.tek_settings[root + "2"]) - float(self.tek_settings[root + "1"]))
        common = {"CURSOR:FUNCTION", "CURSOR:VBARS:UNITS", "CURSOR:HBARS:UNITS",
                  "CURSOR:VBARS:POSITION1", "CURSOR:VBARS:POSITION2", "CURSOR:HBARS:POSITION1", "CURSOR:HBARS:POSITION2",
                  "SELECT:MATH", "MATH:DEFINE"}
        supported = common | ({
            "SELECT:CONTROL", "DISPLAY:PERSISTENCE:STATE", "DISPLAY:PERSISTENCE:VALUE", "SAVE:IMAGE:FILEFORMAT",
            "SAVE:WAVEFORM:FILEFORMAT", "HORIZONTAL:DELAY:MODE", "HORIZONTAL:DELAY:TIME", "TRIGGER:A:PULSE:CLASS",
            "TRIGGER:A:RUNT:SOURCE", "TRIGGER:A:RUNT:POLARITY", "TRIGGER:A:RUNT:WHEN", "TRIGGER:A:RUNT:WIDTH",
        } if b2 else {
            "CURSOR:SELECT:SOURCE", "DISPLAY:PERSISTENCE", "TRIGGER:MAIN:VIDEO:SOURCE",
            "TRIGGER:MAIN:VIDEO:STANDARD", "TRIGGER:MAIN:VIDEO:POLARITY", "TRIGGER:MAIN:VIDEO:SYNC",
        })
        if header in supported: return self.tek_settings[header]
        if b2 and re.fullmatch(r"TRIGGER:A:(LOWERTHRESHOLD|UPPERTHRESHOLD):CH[12]", header):
            return self.tek_settings.get(header, "0")
        if header == "HARDCOPY:INKSAVER" and not b2: return "ON" if self.hardcopy_inksaver else "OFF"
        if self._capabilities.screenshot_formats:
            if header == "HARDCOPY:FORMAT": return self.hardcopy_format
            if header == "HARDCOPY:PORT": return self.hardcopy_port
            if header == "HARDCOPY:LAYOUT": return self.hardcopy_layout
        return None

    def read_raw(self) -> bytes:
        self._ensure_open()
        if not self.hardcopy_pending:
            raise SimulatorBackendError("No supported Tek hardcopy transfer is pending")
        self.hardcopy_pending = False
        self._raise_configured_failure(self.binary_failures, "HARDCopy STARt")
        return bytes(self.binary_overrides.get("HARDCopy STARt", _simulated_screenshot_bmp(False)))

    def query_binary_values(self, command: str, **kwargs: object) -> tuple:
        self._record(command, query=True)
        raise SimulatorBackendError(f"Unsupported Tek binary query: {command}")

    def query_binary_bytes(self, command: str) -> bytes:
        self._record(command, query=True)
        raise SimulatorBackendError(f"Unsupported Tek binary query: {command}")

    def write(self, command: str) -> None:
        upper = command.upper()
        if upper == "*CLS":
            super().write(command)
            return
        self._record(command, query=False)
        if self._write_supported_settings(command):
            return
        match = re.fullmatch(r"ACQUIRE:STOPAFTER (RUNSTOP|SEQUENCE)", upper)
        if match:
            self.stop_after = match.group(1)
            return
        match = re.fullmatch(r"ACQUIRE:STATE (ON|OFF)", upper)
        if match:
            self.run_state = "stopped" if match.group(1) == "OFF" else (
                "single" if self.stop_after == "SEQUENCE" else "running"
            )
            return
        if upper == "TRIGGER FORCE":
            return
        match = re.fullmatch(r"ACQUIRE:MODE (SAMPLE|PEAKDETECT|AVERAGE|HIRES)", upper)
        if match:
            modes = {"SAMPLE": "NORMal", "PEAKDETECT": "PEAK", "AVERAGE": "AVERage", "HIRES": "HRESolution"}
            canonical = {"SAMPLE": "normal", "PEAKDETECT": "peak", "AVERAGE": "average", "HIRES": "high_resolution"}[match.group(1)]
            if canonical not in (self._capabilities.acquisition_modes or ()):
                raise SimulatorBackendError(f"Unsupported Tek acquisition mode: {command}")
            self.acquisition_type = modes[match.group(1)]
            return
        match = re.fullmatch(r"ACQUIRE:NUMAVG (\d+)", upper)
        if match:
            count = int(match.group(1))
            if count not in (self._capabilities.average_counts or ()):
                raise SimulatorBackendError(f"Unsupported Tek average count: {count}")
            self.acquisition_count = count
            return
        if upper == "AUTOSET EXECUTE":
            return
        if upper == "DISPLAY:STYLE VECTORS" and self._capabilities.series != "TBS2000B":
            self.display_vectors = True
            return
        match = re.fullmatch(r"HORIZONTAL:MAIN:(SCALE|POSITION) (.+)", upper)
        if match:
            if match.group(1) == "POSITION" and self._capabilities.series == "TBS2000B":
                raise SimulatorBackendError(f"Unsupported Tek write: {command}")
            setattr(self, "timebase_scale" if match.group(1) == "SCALE" else "timebase_position", _parse_scpi_number(match.group(2)))
            return
        match = re.fullmatch(r"SELECT:CH(\d+) (ON|OFF)", upper)
        if match:
            self.channel_display[self._channel_number(match.group(1))] = match.group(2) == "ON"
            return
        match = re.fullmatch(r"CH(\d+):(SCALE|OFFSET|COUPLING|PROBE(?::GAIN)?|BANDWIDTH|INVERT|LABEL|DESKEW) (.+)", command, re.IGNORECASE)
        if match:
            channel = self._channel_number(match.group(1))
            setting, value = match.group(2).upper(), match.group(3)
            b2 = self._capabilities.series == "TBS2000B"
            if setting in {"OFFSET", "LABEL", "DESKEW"} and not b2:
                raise SimulatorBackendError(f"Unsupported Tek write: {command}")
            if setting == "PROBE:GAIN" and not b2 or setting == "PROBE" and b2:
                raise SimulatorBackendError(f"Unsupported Tek write: {command}")
            if setting == "SCALE": self.channel_scale[channel] = _parse_scpi_number(value)
            elif setting == "OFFSET": self.channel_offset[channel] = _parse_scpi_number(value)
            elif setting == "COUPLING" and value.upper() in {"AC", "DC"}: self.channel_coupling[channel] = value.upper()
            elif setting.startswith("PROBE"):
                number = _parse_scpi_number(value)
                if number <= 0: raise SimulatorBackendError("Tek probe value must be positive")
                self.channel_probe[channel] = 1 / number if b2 else number
            elif setting == "BANDWIDTH" and value.upper() in ({"TWENTY", "FULL"} if b2 else {"ON", "OFF"}):
                self.channel_bandwidth_limit[channel] = value.upper() in {"TWENTY", "ON"}
            elif setting == "INVERT" and value.upper() in {"ON", "OFF"}: self.channel_invert[channel] = value.upper() == "ON"
            elif setting == "LABEL" and re.fullmatch(r'"[^\"]*"', value): self.channel_label[channel] = value[1:-1]
            elif setting == "DESKEW": self.channel_probe_skew[channel] = _parse_scpi_number(value)
            else: raise SimulatorBackendError(f"Unsupported Tek write: {command}")
            return
        match = re.fullmatch(r"SAVE:WAVEFORM CH(\d+),(REF[12]|REF[AB])", upper)
        if match:
            self.reference_saved_source[self._reference_slot(match.group(2))] = self._channel_number(match.group(1))
            return
        match = re.fullmatch(r"SELECT:(REF[12]|REF[AB]) (ON|OFF)", upper)
        if match:
            self.reference_display[self._reference_slot(match.group(1))] = match.group(2) == "ON"
            return
        match = re.fullmatch(r'FILESYSTEM:CWD "([^\"]*)"', command, re.IGNORECASE)
        if match:
            self.save_pwd = match.group(1)
            return
        match = re.fullmatch(r"SAVE:SETUP ([1-9])", upper)
        if match:
            self.tek_setups[int(match.group(1))] = deepcopy({
                "channel_display": self.channel_display, "channel_scale": self.channel_scale,
                "channel_offset": self.channel_offset, "timebase_scale": self.timebase_scale,
                "timebase_position": self.timebase_position, "trigger_source": self.trigger_source,
                "trigger_level": self.trigger_level, "trigger_levels": self.trigger_levels,
            })
            return
        match = re.fullmatch(r"RECALL:SETUP ([1-9])", upper)
        if match:
            saved = self.tek_setups.get(int(match.group(1)))
            if saved is None: raise SimulatorBackendError("Tek setup slot has not been saved")
            for name, value in saved.items(): setattr(self, name, deepcopy(value))
            return
        path = self._trigger_path(command)
        if path is not None:
            header, separator, value = path.partition(" ")
            if separator:
                allowed = {
                    "TYPE": {"EDGE", "PULSE"} | ({"VIDEO"} if self._capabilities.series != "TBS2000B" else set()), "MODE": {"AUTO", "NORMAL"},
                    "EDGE:SLOPE": {"RISE", "FALL"},
                    "EDGE:COUPLING": {"DC", "LFREJ"} | ({"AC"} if self._capabilities.series != "TBS2000B" else set()),
                }
                if header in allowed and value.upper() in allowed[header]:
                    setattr(self, {"TYPE": "trigger_mode", "MODE": "trigger_sweep", "EDGE:SLOPE": "trigger_slope", "EDGE:COUPLING": "trigger_edge_coupling"}[header], value.upper())
                    return
                if header == "EDGE:SOURCE" and value in ({"LINE"} if self._capabilities.series == "TBS2000B" else {"ACLINE", "EXT"}):
                    self.trigger_source = value
                    return
                if header == "EDGE:SOURCE" and re.fullmatch(r"CH\d+", value, re.IGNORECASE):
                    self.trigger_source = self._channel_number(value[2:])
                    return
                if header in {"LEVEL", "HOLDOFF:TIME", "HOLDOFF:VALUE"} or re.fullmatch(r"LEVEL:CH\d+", header):
                    b2 = self._capabilities.series == "TBS2000B"
                    if header == "LEVEL" and b2 or header.startswith("LEVEL:CH") and not b2 or header == "HOLDOFF:TIME" and not b2 or header == "HOLDOFF:VALUE" and b2:
                        raise SimulatorBackendError(f"Unsupported Tek write: {command}")
                    number = _parse_scpi_number(value)
                    if header.startswith("LEVEL"):
                        channel = self._channel_number(header[8:]) if header.startswith("LEVEL:CH") else self.trigger_source
                        self.trigger_levels[channel] = number
                        if channel == self.trigger_source: self.trigger_level = number
                    else: self.trigger_holdoff = number
                    return
        raise SimulatorBackendError(f"Unsupported Tek write: {command}")

    def query(self, command: str) -> str:
        upper = command.upper()
        if upper in {"*IDN?", "*OPC?", "*STB?", "*ESR?"}:
            return super().query(command)
        self._record(command, query=True)
        if command in self.query_overrides: return self.query_overrides[command]
        response = self._query_supported_settings(command)
        if response is not None:
            return response
        if upper == "ACQUIRE:MODE?":
            return {"NORMal": "SAMple", "PEAK": "PEAKdetect", "AVERage": "AVErage", "HRESolution": "HIRes"}[self.acquisition_type]
        if upper == "ACQUIRE:NUMAVG?": return str(self.acquisition_count)
        if upper == "DISPLAY:STYLE?" and self._capabilities.series != "TBS2000B": return "VECtors" if self.display_vectors else "DOTs"
        if upper == "HORIZONTAL:MAIN:SCALE?": return str(self.timebase_scale)
        if upper == "HORIZONTAL:MAIN:POSITION?" and self._capabilities.series != "TBS2000B": return str(self.timebase_position)
        match = re.fullmatch(r"SELECT:CH(\d+)\?", upper)
        if match: return "ON" if self.channel_display.get(self._channel_number(match.group(1)), True) else "OFF"
        match = re.fullmatch(r"CH(\d+):(SCALE|OFFSET|COUPLING|PROBE(?::GAIN)?|BANDWIDTH|INVERT|LABEL|DESKEW)\?", upper)
        if match:
            channel = self._channel_number(match.group(1))
            setting = match.group(2)
            b2 = self._capabilities.series == "TBS2000B"
            if setting in {"OFFSET", "LABEL", "DESKEW"} and not b2 or setting == "PROBE:GAIN" and not b2 or setting == "PROBE" and b2:
                raise SimulatorBackendError(f"Unsupported Tek query: {command}")
            values = {
                "SCALE": str(self.channel_scale.get(channel, 1.0)), "OFFSET": str(self.channel_offset.get(channel, 0.0)),
                "COUPLING": self.channel_coupling.get(channel, "DC"),
                "PROBE": str(self.channel_probe.get(channel, 1.0)),
                "PROBE:GAIN": str(1 / self.channel_probe.get(channel, 1.0)),
                "BANDWIDTH": ("TWEnty" if self.channel_bandwidth_limit.get(channel, False) else "FULl") if b2 else ("ON" if self.channel_bandwidth_limit.get(channel, False) else "OFF"),
                "INVERT": "ON" if self.channel_invert.get(channel, False) else "OFF",
                "LABEL": f'"{self.channel_label.get(channel, "")}"', "DESKEW": str(self.channel_probe_skew.get(channel, 0.0)),
            }
            return values[setting]
        match = re.fullmatch(r"SELECT:(REF[12]|REF[AB])\?", upper)
        if match: return "ON" if self.reference_display[self._reference_slot(match.group(1))] else "OFF"
        if upper == "FILESYSTEM:CWD?": return f'"{self.save_pwd}"'
        path = self._trigger_path(command)
        if path and path.endswith("?"):
            header = path[:-1]
            if header == "TYPE": return self.trigger_mode
            if header == "MODE": return self.trigger_sweep
            if header == "EDGE:SOURCE": return f"CH{self.trigger_source}" if isinstance(self.trigger_source, int) else self.trigger_source
            if header == "EDGE:SLOPE": return self.trigger_slope
            if header == "EDGE:COUPLING": return self.trigger_edge_coupling
            if header == "LEVEL" and self._capabilities.series != "TBS2000B": return str(self.trigger_level)
            match = re.fullmatch(r"LEVEL:CH(\d+)", header)
            if match and self._capabilities.series == "TBS2000B":
                channel = self._channel_number(match.group(1))
                return str(self.trigger_levels.get(channel, 0.0))
            if header == ("HOLDOFF:TIME" if self._capabilities.series == "TBS2000B" else "HOLDOFF:VALUE"):
                return str(self.trigger_holdoff)
        raise SimulatorBackendError(f"Unsupported Tek query: {command}")
