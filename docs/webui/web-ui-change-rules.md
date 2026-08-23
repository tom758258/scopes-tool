# WebUI Change Rules

This document is the maintainer and agent-facing contract for Scopes Tool
WebUI changes. It complements `AGENTS.md` and the [WebUI README](README.md);
it is not an operator guide.

## Authority Boundaries

- Core owns instrument identity, capabilities, validation, drivers, SCPI,
  simulator behavior, and hardware semantics.
- WebUI owns presentation, interaction, browser state, and result display. It
  remains a parallel adapter to the CLI and must not import the CLI.
- Do not create a second SCPI or capability policy in the browser or WebUI
  backend. Presentation limits must be projected from Core-owned metadata.
- Live execution trusts the identity detected through `*IDN?`. A browser or
  planning model must never override a detected Live device. Simulate and
  Dry-run may use an explicitly selected registered planning model.

## Command Exposure

- A public Core operation is not automatically a WebUI command. Expose it only
  when the browser has a clear, safe interaction and result presentation.
- Internal helpers may remain callable by WebUI workflows while hidden from
  the Command workbench. `list-resources` is the discovery example.
- User-facing information and diagnostic commands may remain explicit Read or
  Run actions and should present normalized structured results.
- Do not automatically run consuming or destructive diagnostics such as an
  error-queue read.

## State And Readback

- Operator command and resource-management surfaces share foreground execution
  admission; do not start a second foreground job while one is active.
- Command selection and presentation-only navigation must not perform
  instrument I/O. Reads require an explicit user action or execution
  verification.
- Stateful settings use read current state, edit, Apply, and verification
  readback. Keep the existing Core query/set contract behind that interaction.
- Unapplied dirty input must not be overwritten by automatic readback. Keep
  workspace state and results scoped to command, execution mode, resource,
  detected Live model, and planning model as applicable.
- Readback results may update an editor only while the originating presentation
  context is still current.
- Prefer existing aggregate Core queries. Do not create one hardware job per
  field when Core already returns a coherent state object.

## Capability Presentation

- The frontend consumes the capability projection returned with command
  metadata. Live uses detected capabilities; Simulate and Dry-run use planning
  capabilities.
- UI constraints improve admission and clarity, but Core and backend
  validation remain authoritative.
- Unsupported commands or controls should be disabled with a short reason
  where practical. Do not maintain a frontend model database.

## Results

- Workspace Result presents the latest successful result for the current
  command and execution context. A later failure does not erase that result.
- Prefer dedicated or generic structured presentation for normalized public
  fields. Keep raw diagnostic fields in Raw Result Detail.
- Job lifecycle and bounded Result History remain independent of whether a
  command has a visible workbench entry.

## Localization

- Add English and Traditional Chinese text for user-facing labels, help,
  support reasons, actions, and structured result field names.
- Do not translate command IDs, model IDs, VISA resources, SCPI, protocol
  tokens, artifact filenames, or raw instrument values.

## Testing

- Test WebUI-only changes with no-hardware API, simulator, and frontend
  contract tests. Do not require a real instrument for presentation work.
- Instrument semantics and SCPI changes belong in Core and require Core-owned
  tests and explicit approval under `AGENTS.md`.
- Run focused WebUI tests first, then the complete no-hardware WebUI suite.
  Check modified JavaScript with `node --check`, compile modified Python, and
  run `git diff --check`.
- WebUI index and static assets deliberately prevent stale browser caching:
  entry CSS/JS URLs are versioned with the file mtime and all static responses
  use `Cache-Control: no-store`. Keep this policy when adding or serving
  assets.
- Tests should protect durable ownership and behavior, not incidental prose,
  private helper names, or visual pixel details.
