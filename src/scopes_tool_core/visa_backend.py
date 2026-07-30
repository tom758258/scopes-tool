"""Low-level PyVISA backend helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .errors import VisaBackendError
from .log import get_logger


ASRL_VERIFY_TIMEOUT_MS = 1000
_SERIAL_TERMINATION_VALUES = {
    "CRLF": "\r\n",
    "LF": "\n",
    "CR": "\r",
    "NONE": None,
}


@dataclass(frozen=True)
class VisaResourceListing:
    """Visible VISA resources and selected backend description."""

    resources: tuple[str, ...]
    backend: str


@dataclass(frozen=True)
class VisaLiveVerification:
    """Best-effort live verification result for one VISA resource."""

    resource: str
    live: bool
    raw_idn: str | None
    detail: str | None


def list_visa_resources(visa_library: str | None = None) -> VisaResourceListing:
    """List VISA resources using PyVISA's selected backend."""

    resource_manager = _create_resource_manager(visa_library)
    try:
        resources = tuple(str(resource) for resource in resource_manager.list_resources())
        backend = _describe_backend(resource_manager)
        return VisaResourceListing(resources=resources, backend=backend)
    except Exception as exc:  # pragma: no cover - depends on installed VISA stack
        raise VisaBackendError(f"Failed to list VISA resources: {exc}") from exc
    finally:
        _close_quietly(resource_manager)


def is_asrl_resource(resource: str) -> bool:
    """Return whether a VISA resource string names an ASRL transport."""

    return resource.strip().upper().startswith("ASRL")


def normalize_serial_termination(value: str) -> str | None:
    """Map CLI serial termination tokens to PyVISA attribute values."""

    try:
        return _SERIAL_TERMINATION_VALUES[value.upper()]
    except KeyError as exc:
        raise ValueError(f"unsupported serial termination: {value}") from exc


def verify_asrl_resource_live(
    resource: str,
    *,
    visa_library: str | None = None,
    serial_read_termination: str | None = None,
    serial_write_termination: str | None = None,
) -> VisaLiveVerification:
    """Bounded best-effort ASRL `*IDN?` verification for discovery only."""

    resource_manager = None
    session = None
    try:
        resource_manager = _create_resource_manager(visa_library)
        session = resource_manager.open_resource(
            resource,
            open_timeout=ASRL_VERIFY_TIMEOUT_MS,
        )
        session.timeout = ASRL_VERIFY_TIMEOUT_MS
        if serial_read_termination is not None:
            session.read_termination = normalize_serial_termination(
                serial_read_termination
            )
        if serial_write_termination is not None:
            session.write_termination = normalize_serial_termination(
                serial_write_termination
            )
        logger = get_logger("scpi")
        logger.debug("SCPI >> %s", "*IDN?")
        raw_idn = str(session.query("*IDN?")).strip()
        logger.debug("SCPI << %s", raw_idn)
        return VisaLiveVerification(
            resource=resource,
            live=True,
            raw_idn=raw_idn,
            detail=None,
        )
    except Exception as exc:  # pragma: no cover - exact VISA failures are backend-specific
        return VisaLiveVerification(
            resource=resource,
            live=False,
            raw_idn=None,
            detail=f"ASRL verification failed: {exc}",
        )
    finally:
        if session is not None:
            _close_quietly(session)
        if resource_manager is not None:
            _close_quietly(resource_manager)


class VisaBackend:
    """Low-level PyVISA session wrapper."""

    def __init__(self, resource_name: str, visa_library: str | None = None) -> None:
        self.resource_name = resource_name
        self._resource_manager = _create_resource_manager(visa_library)
        self.backend = _describe_backend(self._resource_manager)
        self.history: list[str] = []
        self._closed = False
        try:
            self._resource = self._resource_manager.open_resource(resource_name)
        except Exception as exc:  # pragma: no cover - depends on installed VISA stack
            _close_quietly(self._resource_manager)
            raise VisaBackendError(f"Failed to open VISA resource {resource_name}: {exc}") from exc

    @property
    def timeout(self) -> int | None:
        """Return the backend timeout in milliseconds without changing it."""

        return getattr(self._resource, "timeout", None)

    def set_timeout(self, timeout_ms: int | None) -> None:
        """Set the backend timeout in milliseconds."""

        self._ensure_open()
        try:
            self._resource.timeout = timeout_ms
        except Exception as exc:  # pragma: no cover - depends on installed VISA stack
            raise VisaBackendError(f"Failed to set VISA timeout to {timeout_ms}: {exc}") from exc

    def write(self, command: str) -> None:
        """Write one raw command to the VISA resource."""

        self._ensure_open()
        self.history.append(command)
        try:
            self._resource.write(command)
        except Exception as exc:  # pragma: no cover - depends on installed VISA stack
            raise VisaBackendError(f"VISA write failed for {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        """Write one raw query and return its response."""

        self._ensure_open()
        self.history.append(command)
        try:
            return str(self._resource.query(command))
        except Exception as exc:  # pragma: no cover - depends on installed VISA stack
            raise VisaBackendError(f"VISA query failed for {command!r}: {exc}") from exc

    def read_raw(self) -> bytes:
        """Read raw bytes from the VISA resource."""

        self._ensure_open()
        try:
            return bytes(self._resource.read_raw())
        except Exception as exc:  # pragma: no cover - depends on installed VISA stack
            raise VisaBackendError(f"VISA raw read failed: {exc}") from exc

    def query_binary_values(self, command: str, **kwargs: Any) -> Sequence[Any]:
        """Query binary values through PyVISA."""

        self._ensure_open()
        self.history.append(command)
        try:
            return self._resource.query_binary_values(command, **kwargs)
        except Exception as exc:  # pragma: no cover - depends on installed VISA stack
            raise VisaBackendError(f"VISA binary query failed for {command!r}: {exc}") from exc

    def close(self) -> None:
        """Close the VISA session and resource manager."""

        if self._closed:
            return
        _close_quietly(self._resource)
        _close_quietly(self._resource_manager)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise VisaBackendError("VISA backend is closed.")


def _load_pyvisa() -> Any:
    try:
        import pyvisa
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise VisaBackendError(
            "PyVISA is not installed. Install the project with "
            '`uv pip install -e ".[all,dev]"`.'
        ) from exc
    return pyvisa


def _create_resource_manager(visa_library: str | None = None) -> Any:
    pyvisa = _load_pyvisa()
    try:
        if visa_library is None:
            return pyvisa.ResourceManager()
        return pyvisa.ResourceManager(visa_library)
    except Exception as exc:  # pragma: no cover - depends on installed VISA stack
        raise VisaBackendError(f"Failed to create PyVISA ResourceManager: {exc}") from exc


def _describe_backend(resource_manager: Any) -> str:
    return str(getattr(resource_manager, "visalib", "unknown"))


def _close_quietly(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        pass
