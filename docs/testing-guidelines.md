# Testing Guidelines

Tests in Scopes Tool should protect behavior and public contracts without
making routine documentation and implementation improvements unnecessarily
difficult.

## What To Test

- Public Python APIs, console entry points, command options, and exit behavior.
- JSON and JSONL schemas, including durable field names and correlation rules.
- Safety boundaries for dry-run, simulation, live resources, SCPI access,
  stopping, and cleanup.
- Package ownership boundaries and the documented locations of public files.
- Runtime behavior at the narrowest useful layer, with integration tests for
  workflows that cross package or process boundaries.
- Durable documentation structure when users and integrations rely on it, such
  as contract links and major contract headings.

## What Not To Freeze

- Natural-language wording, paragraph order, or formatting that does not define
  a public contract.
- Example variable names, helper names, or one particular example
  implementation.
- Internal module layout and private implementation details.
- References to frameworks or tools unless the choice itself is a supported
  public contract.
- Byte-for-byte copies of files owned by another repository. Common contracts
  under `docs/contracts/` are owned by this repository and should be reviewed as
  contracts here.

## Documentation Tests

Documentation tests should verify ownership, discoverability, public entry
points, durable headings, known contract links, and schema field names. Prefer
checking a small set of stable tokens over complete sentences.

Do not use documentation tests as substitutes for runtime tests. Worker
correlation, stopping, cleanup, safety, and artifact behavior belong in worker
and CLI tests even when examples also describe them.

## Frontend Static Tests

When a user-facing WebUI is implemented, static tests should protect public
routes, asset ownership, accessibility landmarks, stable test selectors, and
security-relevant configuration. Test user-visible workflows in a browser when
behavior depends on rendering or interaction.

Do not freeze framework names, generated markup, CSS class names, snapshots of
large pages, or exact prose unless they are intentionally public contracts.

## Review Standard

Review tests by asking what regression each assertion detects and whether a
less brittle assertion detects the same regression. Strict assertions are
appropriate for public contracts and safety behavior. Assertions about prose,
examples, and internal structure require a clear maintenance benefit.

## Windows Live Validation Tests

Core and CLI tests own model capabilities, command validation, SCPI generation,
and JSON schemas. PowerShell tests own identity and confirmation gates, CLI
process boundaries, snapshot and restoration, failure propagation, native
versus normalized errors, and report privacy. Use representative runtime cases
instead of checking source text or repeating equivalent model and transport
combinations. Live trigger tests verify setter execution, main readbacks, and
restoration with fake instruments; they do not establish hardware support.

Mark PowerShell tests with `windows_powershell`. The smaller
`windows_boundary_smoke` subset starts the selected Python CLI and checks
arguments, JSON parsing, and nonzero exits. CI runs ordinary Windows Python
tests on Python 3.10, 3.12, and 3.13, boundary smoke on 3.10 and 3.12, and the
complete PowerShell validation suite on 3.13, including boundary smoke. The
Linux Python matrix remains independent of these Windows tests.
