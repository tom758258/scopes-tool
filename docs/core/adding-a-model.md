# Adding an oscilloscope model

Model differences belong in Core. CLI, Worker and WebUI consume the registered
identity, capabilities, driver plans and results; they must not add their own
SCPI or model-name branches.

1. Register the physical identity in `identity.py`, including accepted vendor
   and model names, the capability profile ID and the driver ID. Live identity
   comes from `*IDN?`. A planning identity must never override live detection.
2. Define the profile in `capabilities.py`. List supported operations and their
   actual channel, measurement, acquisition, waveform, screenshot and sequence
   subsets. For screenshots, specify `screenshot_formats` explicitly (empty for
   no capture). This tuple is the sole format capability source;
   `supports_any_screenshot` and `supports_png_screenshot` are derived
   predicates. Preserve the existing
   command's default format and the sequence action subset. A shared series
   does not imply identical model capabilities. An
   operation may use multiple native commands to satisfy the existing public
   semantic; a different command spelling is not a reason to disable it.
3. Implement only the necessary driver differences. Reuse existing strategies
   when the manual establishes the same behavior. Branches for a finite set of
   series must reject all other series explicitly. Preserve actual raw
   responses, completion, temporary-state restoration and artifact encodings.
4. Pass the registered physical model ID through planning and simulation. Do
   not select a representative model from a series name. The planning backend
   must reject an identity/profile mismatch. Capture and measurement plans use
   `plan_capture_scpi` and `plan_measure_scpi` on the registered driver. Simulate
   the same native command
   vocabulary, state changes, error/status behavior and model restrictions.
5. Compose workflows from the driver boundary: `preflight_status`,
   `workflow_status`, `wait_for_current_trigger_completion`, and driver-owned
   `plan_workflow_step`. Waiting for the current acquisition never arms it.
   Keep native status distinct from a normalized error queue. Derive optional
   cleanup steps and sequence actions from capabilities.
6. Project the Core profile into adapter metadata. Measurement choices,
   channels, capture formats/points and sequence actions must agree in WebUI,
   CLI validation, Worker validation and runtime, including bypassed UI inputs.
   Set `horizontal_display_divisions` and `timebase_reference_mode` in Core;
   the position editor consumes their projection without testing series names.
   Set `vertical_display_divisions` for cursor bounds and
   `cursor_source_selection` for independent versus selected-waveform source
   behavior. The latter requires a driver adapter and a projected UI notice of
   source/display/acquisition effects. Semantic metadata is fail-closed:
   display-division counts are positive integers,
   `timebase_reference_mode` is `configurable` or `fixed-center`, and
   `cursor_source_selection` is `independent` or `selected-waveform`.
   Declare `fixed_acquisition_memory_mode` only when the model's acquisition
   architecture establishes a fixed `realtime`, `segmented`, or
   `equivalent_time` mode; absence of segmented support is insufficient.
   Acquisition processing type remains a separate driver query.

Verify identity rejection, profile/driver consistency, dry-run plans, simulator
execution, adapter payloads and unsupported-option rejection before writes.
`tests/test_supported_operation_surface_consistency.py` checks every explicitly
listed operation against an acceptance case and its applicable adapter routes.
The cases execute Core through CLI and WebUI simulation, check dry-run planning
where available, and validate Worker requests where that command is exposed.
Legacy profiles run shared cases exposed by WebUI; domain tests cover their
remaining CLI-only commands and additional options. Adapter-only commands and aliases are recorded explicitly,
so capability support does not imply adding a new public adapter surface.

Exercise meaningful error paths: malformed/incomplete status, temporary-state
restoration, timeout, force, cancellation and a sequence containing a later
unsupported step. Reuse the acceptance matrix across registered models rather
than taking the intersection of their capabilities. Live acceptance tooling
must consume Core capability metadata rather than maintain a second support
matrix: if a runner labels an operation unsupported while Core admits it, the
runner must fail as stale instead of reporting N/A.

Follow [Testing Guidelines](../testing-guidelines.md). Hardware-free results do
not establish live behavior. Live validation is explicit, bounded and uses only
a user-supplied resource; its private evidence stays outside tracked public
documentation. Maintain all durable model behavior and option limits in
[supported models](supported-models.md).
