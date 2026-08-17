"""Standalone local WebUI server entry point."""

from __future__ import annotations

import argparse

from . import __version__


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8025


def parse_port(value: str) -> int:
    try:
        port = int(value.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be a number.") from exc
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535.")
    return port


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scopes Tool WebUI server")
    parser.add_argument(
        "--version",
        action="version",
        version=f"scopes-tool-webui {__version__}",
    )
    parser.add_argument(
        "--port",
        type=parse_port,
        default=DEFAULT_PORT,
        help=f"Port to bind on {DEFAULT_HOST} (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args(argv)

    try:
        import uvicorn
        from .app import app
    except ModuleNotFoundError as exc:
        missing = exc.name or "WebUI runtime dependency"
        parser.error(
            f"Missing optional WebUI dependency {missing!r}; "
            "install the 'webui' extra."
        )

    uvicorn.run(app, host=DEFAULT_HOST, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
