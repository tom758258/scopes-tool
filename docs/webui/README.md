# Scopes Tool WebUI

The Scopes Tool WebUI is a small local browser shell served by the single
`scopes-tool` distribution. The WebUI is a parallel adapter over Core and does
not import or own the CLI adapter.

Import package: `scopes_tool_webui`

## Installation

Install the optional WebUI dependencies from a source checkout:

```powershell
uv pip install -e ".[webui]"
```

## Start the server

The server entry point serves the browser shell on `127.0.0.1:8025` by
default:

```powershell
scopes-tool-webui
scopes-tool-webui --port 8030
```

The standalone server uses the selected port directly and fails if that port
is unavailable. It binds only to loopback; remote binding is not supported.

## Start the Launcher

The English-only Tk Launcher starts the local server, waits for
`GET /api/health` to report the `scopes-tool-webui` service identity, and then
opens the browser:

```powershell
scopes-tool-webui-launcher
scopes-tool-webui-launcher --port 8030
```

Without an explicit port, the Launcher tries up to 100 ports beginning at
8025. Automatic fallback is used only for port-in-use conflicts. An explicit
`--port` is fixed unless `--auto-port` is supplied. If all automatic
candidates are unavailable, the Launcher presents a manual-port fallback.

## Current WebUI

The current WebUI provides the browser shell, static assets, and the health
endpoint:

- `GET /` serves the shell.
- `GET /api/health` returns the service status, package identity, and version.
- `/static/` serves the shell assets.

Instrument Commands, Basic Controls, dynamic forms, localization, and hardware
execution are not part of this runtime.
