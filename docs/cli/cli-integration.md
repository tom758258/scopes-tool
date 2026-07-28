# CLI Integration

The CLI package adapts `argparse.Namespace` inputs into Core run-mode,
planning, and operation calls. Keep parser-only naming and compatibility fields
in this package.

CLI-only fields include:

- `measurement_cli_name`
- command names such as `measure-log`, `capture-batch`, and `hardware-report`
- process return-code behavior
- stderr SCPI diagnostic handling
- parser validation messages

DVM Common Pack v1 adapter commands are `dvm-enable`, `dvm-source`,
`dvm-mode`, `dvm-auto-range`, `dvm-current`, and `dvm-query`. Boolean
configuration uses canonical `--enabled true|false`; `dvm-current` and
`dvm-query` require `--query`. The adapter does not expose DVM frequency,
independent Counter, or `:MEASure:COUNter` commands.

WGEN Basic P1 adapter commands are `wgen-query`, `wgen-output`,
`wgen-function`, `wgen-frequency`, `wgen-voltage`, `wgen-offset`, and
`wgen-load`. The selected model profile determines the concrete `:WGEN` or
`:WGEN1` SCPI root. The adapter exposes no generator selector in P1.

Search Basic Pack v1 adapter commands are `search-state`, `search-mode`, and
query-only `search-count`. Boolean configuration uses canonical
`--enabled true|false`; search modes use lowercase canonical values and are
validated against the selected model capability profile before search SCPI.
Mode configuration enables search before selecting the mode.

These fields are adapter behavior, not Core schema. Core receives normalized
requests and returns runtime data; the CLI decides how to render human text,
JSON stdout, stderr logs, and exit codes.

For one-shot commands, an explicit `--resource` or
`SCOPES_TOOL_RESOURCE` selects one live instrument. The optional `--live`
flag is retained for compatibility and conflicts with `--simulate` and
`--dry-run`. Worker startup remains a separate lifecycle path that requires
`--live --resource`; `list-resources --live-only` remains the only discovery
path that opens each enumerated resource.

The installed console script remains:

```text
scopes-tool = scopes_tool_cli.cli:main
```

The module form remains:

```powershell
python -m scopes_tool_cli.cli
```

CLI JSON behavior is documented by the root Scopes contract:
`docs/contracts/scopes-cli-jsonl-contract.md`. One-shot and lifecycle JSON
payloads include `schema_version: 1` and `timestamp_utc`.
