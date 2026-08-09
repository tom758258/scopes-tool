# Scopes Tool

Scopes Tool is vendor-neutral oscilloscope tooling whose current hardware
support targets Keysight InfiniiVision oscilloscopes. The repository is
published as one Python distribution while keeping separate Core, CLI, and
WebUI import packages. Root documentation keeps project-level orientation,
package behavior, and shared machine contracts.

## Distribution

| Area | Distribution | Import / entry point | Public docs |
| --- | --- | --- | --- |
| Core | `scopes-tool` | `scopes_tool_core` | `docs/core/README.md`, `docs/core/integration.md`, `docs/core/periodic-capture.md`, `docs/core/periodic-capture.zh-TW.md`, `docs/core/triggered-measure-loop.md`, `docs/core/triggered-measure-loop.zh-TW.md`, `docs/core/triggered-capture-series.md`, `docs/core/triggered-capture-series.zh-TW.md`, `docs/core/sequence.md`, `docs/core/sequence.zh-TW.md`, `docs/core/supported-models.md` |
| CLI | `scopes-tool` | `scopes-tool`, `python -m scopes_tool_cli.cli` | `docs/cli/README.md`, `docs/cli/cli-integration.md` |
| WebUI | `scopes-tool` | `scopes_tool_webui` skeleton | `docs/webui/README.md` |

Runtime APIs, console scripts, package metadata, SCPI behavior, and JSON
contracts are owned by the root package metadata, area docs, and root contracts.

## Development

From PowerShell:

```powershell
uv venv .venv
uv pip install -e ".[all,dev]"
.\scripts\run-tests.ps1
```

The repository uses one editable package install for local development. It is not
configured as a committed `uv` workspace.

After the editable install, the Windows virtual environment provides the
`.\.venv\Scripts\scopes-tool.exe` console wrapper. Prefer this wrapper for
normal CLI operations:

```powershell
.\.venv\Scripts\scopes-tool.exe identify --simulate --json
```

The wrapper is part of the virtual environment and is not a portable standalone
executable. The module form remains supported as a development or fallback
entry point:

```powershell
.\.venv\Scripts\python.exe -m scopes_tool_cli.cli ...
```

The PowerShell test script gives each pytest run an isolated temporary
directory. This avoids Windows permission conflicts when tests are run by both
the local user and a sandboxed tool. It removes the directory after a successful
run and preserves it after a failure for inspection. Additional pytest
arguments are forwarded:

```powershell
.\scripts\run-tests.ps1 tests/cli/test_worker_cli.py -vv
```

Running pytest directly may fail with `PermissionError: [WinError 5]` if
`$env:TEMP\pytest-of-$env:USERNAME` was created by another Windows identity.
The test script bypasses that shared directory. To restore direct pytest usage,
remove the conflicting directory from an administrator PowerShell:

```powershell
Remove-Item -LiteralPath "$env:TEMP\pytest-of-$env:USERNAME" -Recurse -Force
```

## Documentation Index

Project-level docs:

- `AGENTS.md`
- `docs/architecture/monorepo-layout.md`
- `docs/contracts/`
- `docs/testing-guidelines.md`

Area docs:

- Core runtime, public import API, VISA/SCPI safety, and capability profiles:
  `docs/core/README.md`, `docs/core/supported-models.md`
- Periodic Capture v1 behavior in English and Traditional Chinese:
  `docs/core/periodic-capture.md`, `docs/core/periodic-capture.zh-TW.md`
- Generic Sequence v1 behavior in English and Traditional Chinese:
  `docs/core/sequence.md`, `docs/core/sequence.zh-TW.md`
- Triggered Measurement Loop v1 behavior in English and Traditional Chinese:
  `docs/core/triggered-measure-loop.md`,
  `docs/core/triggered-measure-loop.zh-TW.md`
- Triggered Capture Series v1 behavior in English and Traditional Chinese:
  `docs/core/triggered-capture-series.md`,
  `docs/core/triggered-capture-series.zh-TW.md`
- CLI command usage, JSON mode, and automation safety:
  `docs/cli/README.md`
- WebUI package skeleton and future ownership notes:
  `docs/webui/README.md`

Shared contracts under `docs/contracts/` remain the source of truth for
cross-package machine behavior. Package docs link to those contracts instead of
duplicating them.

## License and Disclaimer

This project is licensed under the MIT License. See [LICENSE](LICENSE).

This project is an independent, unofficial project and is not affiliated with,
endorsed by, or sponsored by Keysight Technologies.

Users are responsible for complying with all applicable Keysight software,
driver, instrument, and documentation license terms.
