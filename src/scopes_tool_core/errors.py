"""Project exception types."""


class OscilloscopeError(Exception):
    """Base exception for package-specific errors."""


class VisaBackendError(OscilloscopeError):
    """Raised when VISA setup or I/O fails."""


class BackendClosedError(OscilloscopeError):
    """Raised when a backend is used after it has been closed."""


class IDNParseError(OscilloscopeError, ValueError):
    """Raised when an `*IDN?` response cannot be parsed."""


class UnsupportedModelError(OscilloscopeError, ValueError):
    """Raised when a model cannot be mapped to a capability profile."""


class SystemErrorParseError(OscilloscopeError, ValueError):
    """Raised when `:SYSTem:ERRor?` cannot be parsed."""


class StatusResponseError(OscilloscopeError, ValueError):
    """Raised when a system or status query response cannot be parsed."""


class ParameterValidationError(OscilloscopeError, ValueError):
    """Raised when a setting would be invalid for the selected instrument."""


class ChannelResponseError(OscilloscopeError, ValueError):
    """Raised when a channel query response cannot be parsed."""


class TimebaseResponseError(OscilloscopeError, ValueError):
    """Raised when a timebase query response cannot be parsed."""


class TriggerResponseError(OscilloscopeError, ValueError):
    """Raised when a trigger query response cannot be parsed."""


class MeasurementResponseError(OscilloscopeError, ValueError):
    """Raised when a measurement query response cannot be parsed."""


class DvmResponseError(OscilloscopeError, ValueError):
    """Raised when a DVM query response cannot be parsed."""


class DemoResponseError(OscilloscopeError, ValueError):
    """Raised when a DEMO query response cannot be parsed."""


class WgenResponseError(OscilloscopeError, ValueError):
    """Raised when a WGEN query response cannot be parsed."""


class SearchResponseError(OscilloscopeError, ValueError):
    """Raised when a waveform search query response cannot be parsed."""


class SerialResponseError(OscilloscopeError, ValueError):
    """Raised when a serial decode bus query response cannot be parsed."""


class SaveExportResponseError(OscilloscopeError, ValueError):
    """Raised when an instrument-side SAVE query response cannot be parsed."""


class WaveformResponseError(OscilloscopeError, ValueError):
    """Raised when waveform data or metadata cannot be parsed."""


class ScreenshotResponseError(OscilloscopeError, ValueError):
    """Raised when screenshot image data cannot be parsed."""


class AcquisitionResponseError(OscilloscopeError, ValueError):
    """Raised when an acquisition query response cannot be parsed."""
