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

## CI Responsibilities

- **Code quality & WebUI** runs Ruff, both text checks, JavaScript syntax
  checks, and every `frontend_node` test under `tests/webui/`. Mark individual
  Node runtime cases, including those in mixed Python/JavaScript files. Node.js
  is required: missing Node must fail these tests rather than skip them.
  This job also runs `tests/webui/desktop-main.test.cjs` with the built-in
  Node test runner.
- **Linux Python 3.13** runs the primary no-hardware Python suite, excluding
  `frontend_node` and `windows_powershell` tests. Python 3.10, 3.11, and 3.12
  run explicit compatibility selections covering identity, capabilities,
  drivers, Core operations, CLI simulation and safety, Sequence, WebUI HTTP,
  all-model adapter admission, legacy rejection, and Worker process contracts.
- **Windows Python 3.10, 3.12, and 3.13** run CLI safety and driver selection,
  output files, Desktop Host and Launcher lifecycle, job shutdown, Worker
  subprocess/HTTP/JSONL contracts, and mocked Windows packaging. These jobs
  exclude Node and PowerShell validation tests.
- Every Linux and Windows Python matrix job retains package build, import,
  and installed CLI help smoke checks. Mock packaging tests do not establish
  that a real PyInstaller bundle builds or runs.
- **Windows packaging smoke** runs after packaging-related changes on Windows x64,
  builds the actual Desktop onedir output, and executes a packaged CLI simulator
  smoke test. Release-layout changes select `build_release.ps1` instead of a
  separate Desktop build, then verify the versioned artifacts, SHA-256 checksums,
  distribution metadata, extracted shared `_internal`, and packaged CLI/Help.
  Each job builds the Electron onedir only once. It does not establish
  real-instrument support or GUI interaction.
- **Windows Python 3.13** also runs focused release-script contracts when their
  inputs change. These use synthetic artifacts and mocked build/install commands;
  they do not execute full release acceptance. The manual
  `scripts/release-acceptance.ps1` gate requires committed, clean HEAD and writes
  its no-hardware reports and final artifacts under `.tmp_tests/`.
- **Build Windows** is a separate, manual-only workflow for Bundle/Desktop ZIP
  artifacts. It runs the same hardware-free packaged CLI smoke before uploading.

The operation matrix validates adapter admission for every registered model.
Dry-run and simulator execution uses one representative per driver/capability
profile, including both legacy Tektronix channel layouts. DSOX4034A shares the
DSOX4024A execution profile and retains its own adapter admission checks.

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
complete PowerShell validation suite on 3.13, including boundary smoke. General
Python jobs exclude these PowerShell tests; the Windows validation jobs own
their execution.

The 3.13 Windows PowerShell validation suite is partitioned into mutually
exclusive shared, Keysight, and Tektronix groups without removing any tests.
Collection automatically assigns exactly one of `validation_shared`,
`validation_keysight`, or `validation_tektronix` to each
`windows_powershell` node. Unknown modules or unclassified cases fail
collection. The Linux quality job verifies a reviewed case inventory without running
the Windows tests, while the Windows groups run in parallel when their own
inputs or common vendor-neutral inputs change. Inventory changes require a
coverage justification, not just a numeric update. The Windows
3.10/3.12 `windows_boundary_smoke` tests remain unchanged. Only hardware-free
validation runs in CI; actual instrument access remains explicit and opt-in.
Representative Tektronix parser and pulse-width readback cases cover distinct
public contracts rather than every equivalent model/trigger combination. The
Tektronix baseline run is reused between contract assertions for the same model,
but fault-injection and cleanup cases each execute independently. Keysight
Autoscale/Trigger cases remain separated by distinct capability profiles.
Large PowerShell Controls/Artifacts harnesses use a shared process launcher,
while each maintains its own independent runtime assertions.
