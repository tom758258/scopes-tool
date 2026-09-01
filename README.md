# Scopes Tool

Scopes Tool is vendor-neutral oscilloscope tooling with current hardware
support for the registered Keysight InfiniiVision models documented in
[Supported Models](docs/core/supported-models.md). It provides one installable
Python distribution, `scopes-tool`, while preserving three independent import
packages: `scopes_tool_core`, `scopes_tool_cli`, and `scopes_tool_webui`.

Live hardware identity comes from the instrument's actual `*IDN?` response.
Unknown, unregistered, or mismatched live vendors, models, profiles, or drivers
fail closed; selecting a planning model does not override the detected identity.

**Live hardware prerequisite:** Live operation requires a separately installed
VISA implementation or runtime that PyVISA can load. Scopes Tool installs
PyVISA as its Python API layer, but does not bundle Keysight IO Libraries,
NI-VISA, or another system or vendor VISA runtime. Simulation and
Core-planned dry-run operations do not require a physical instrument or
instrument session. VISA resource discovery still requires a usable PyVISA
backend.

## Features

- Control supported Keysight InfiniiVision oscilloscopes over VISA
- Use Live, Simulate, or Dry-run execution as supported by each command
- Operate through the CLI or localhost-only browser WebUI
- Use the browser WebUI in English or Traditional Chinese
- Configure acquisition, analog channels, timebase, and display behavior
- Capture waveform data and screenshots as host-side artifacts
- Query measurements and statistics, and manage reference waveforms
- Use supported DVM, Math, FFT, and WGEN paths
- Configure supported trigger, Search, and Serial workflows
- Query and configure segmented memory and run finite segmented captures
- Run finite measurement, logging, batch capture, and triggered-capture
  workflows
- Compose supported Core operations with Generic Sequence v1 from the CLI or
  WebUI
- Produce JSON, JSONL, CSV, screenshot, and related artifacts for automation

Feature availability remains model- and capability-dependent. See
[Supported Models](docs/core/supported-models.md) for the exact support scope
and the [CLI README](docs/cli/README.md) for command details.

## Generic Sequence v1

The CLI and WebUI are adapters over the same Core Generic Sequence validation,
planning, execution, progress, and cancellation path. Sequence v1 supports the
seven actions `wait`, `single`, `wait-trigger`, `measure`, `capture`,
`screenshot`, and `cleanup`.

Each document must contain `1..255` steps and use a `loop_count` of `1..255`,
with at most 65,025 total step executions. A document may contain at most 10
combined `capture` and `screenshot` steps per loop. At the maximum loop count,
those limits naturally allow at most 2,550 capture/screenshot executions.
These are Scopes Tool product limits, not oscilloscope hardware limits.

Generic Sequence composes supported Core operations. It is not an arbitrary
SCPI macro facility; instrument settings remain available through their
existing command surfaces.

## Project Structure

The repository has one distribution and one version number. In examples,
`<version>` means `[project].version` from the root `pyproject.toml`:

- Distribution: `scopes-tool` `<version>`
- Core import: `scopes_tool_core`
- CLI import: `scopes_tool_cli`
- WebUI import: `scopes_tool_webui`

```text
src/
  scopes_tool_core/
  scopes_tool_cli/
  scopes_tool_webui/
tests/
  core/
  cli/
  webui/
  tooling/
docs/
  core/
  cli/
  webui/
  contracts/
  architecture/
scripts/
```

## Install

Open PowerShell and enter the project root:

```powershell
cd path\to\scopes-tool
```

Install uv if it is not already available:

```powershell
py -m pip install --user uv
```

Verify uv:

```powershell
uv --version
```

Create the project virtual environment:

```powershell
uv venv .venv
```

Sync the standard development environment from the committed `uv.lock`:

```powershell
uv sync --all-extras --link-mode=copy
```

For CI or strict local checks, require the committed lock file to stay
unchanged:

```powershell
uv sync --all-extras --locked --link-mode=copy
```

Scopes Tool supports Python `>=3.10`. To request a specific compatible Python
version when creating the environment:

```powershell
uv venv .venv --python 3.12
```

On Windows, the project install creates these virtualenv console wrappers:

```text
.\.venv\Scripts\scopes-tool.exe
.\.venv\Scripts\scopes-tool-webui.exe
.\.venv\Scripts\scopes-tool-webui-launcher.exe
```

A new environment normally needs only the standard `uv sync` command. If an
existing `.venv` has synchronized successfully but a project console wrapper
is missing, outdated, or needs to be recreated, ask uv to reinstall only the
`scopes-tool` distribution:

```powershell
uv sync --all-extras --link-mode=copy --reinstall-package scopes-tool
```

This repair does not require a pip reinstall and is not a normal per-install
step.

If only the local browser WebUI dependencies are needed, use the smaller
`webui` extra instead:

```powershell
uv sync --extra webui --link-mode=copy
```

The standard development workflow remains `uv sync --all-extras
--link-mode=copy`; the two sync commands are alternatives, not consecutive
steps.

## Quick Start

Run a safe simulator CLI smoke without hardware:

```powershell
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
```

Start the recommended local WebUI Launcher:

```powershell
.\.venv\Scripts\scopes-tool-webui-launcher.exe
```

The WebUI is localhost-only. The direct server defaults to `127.0.0.1:8025`.
Without an explicit port, the Launcher starts at port 8025 and automatically
tries up to 100 ports for port-in-use conflicts before offering a manual-port
fallback. The direct server can also be started with:

```powershell
.\.venv\Scripts\scopes-tool-webui.exe
```

See the [CLI README](docs/cli/README.md) for detailed CLI behavior and the
[WebUI README](docs/webui/README.md) for Device / Resource, port, command,
language, job, and artifact behavior.

## Build

Build the wheel and source distribution with the `build` package included in
the `dev` extra:

```powershell
.\.venv\Scripts\python.exe -m build
```

This produces one Python distribution:

```text
dist\
  scopes_tool-<version>-py3-none-any.whl
  scopes_tool-<version>.tar.gz
```

## Test

Run the hardware-free test suite with a repository-local pytest temporary
directory to avoid Windows shared-temp permission conflicts. On a fresh
checkout, create the `.tmp_tests` parent first:

```powershell
New-Item -ItemType Directory -Force .tmp_tests | Out-Null
.\.venv\Scripts\python.exe -m pytest -q --basetemp .tmp_tests\full
```

Focused runs target one area:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core -q --basetemp .tmp_tests\core
.\.venv\Scripts\python.exe -m pytest tests\cli -q --basetemp .tmp_tests\cli
.\.venv\Scripts\python.exe -m pytest tests\webui -q --basetemp .tmp_tests\webui
.\.venv\Scripts\python.exe -m pytest tests\tooling -q --basetemp .tmp_tests\tooling
```

See [Testing Guidelines](docs/testing-guidelines.md) for repository testing
expectations. Real-instrument validation is explicit, opt-in, and requires a
user-supplied VISA resource.

## Documentation

- [Core README](docs/core/README.md)
- [Core Integration](docs/core/integration.md)
- [Supported Models](docs/core/supported-models.md)
- [CLI README](docs/cli/README.md)
- [CLI Integration](docs/cli/cli-integration.md)
- [WebUI README](docs/webui/README.md)
- [WebUI Change Rules](docs/webui/web-ui-change-rules.md)
- [Repository / Monorepo Layout](docs/architecture/monorepo-layout.md)
- [Agent Instructions](AGENTS.md)
- [Testing Guidelines](docs/testing-guidelines.md)
- [Public Contracts](docs/contracts/)
- [Scopes CLI JSONL Contract](docs/contracts/scopes-cli-jsonl-contract.md)
- [Scopes Worker Contract](docs/contracts/scopes-worker-contract.md)

## License and Disclaimer

This project is licensed under the MIT License. See [LICENSE](LICENSE).

This project is an independent, unofficial project and is not affiliated with,
endorsed by, or sponsored by Keysight Technologies.

Users are responsible for complying with all applicable Keysight software,
driver, instrument, and documentation license terms.
