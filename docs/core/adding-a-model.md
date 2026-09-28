# Adding an oscilloscope model

Model differences belong in Core. CLI, Worker and WebUI consume the registered
identity, capabilities, driver plans and results; they must not add their own
SCPI or model-name branches.

1. Register the physical identity in `identity.py`, including accepted vendor
   and model names, the capability profile ID and the driver ID. Live identity
   comes from `*IDN?`. A planning identity must never override live detection.
2. Define the profile in `capabilities.py`. List supported operations and their
   actual channel, measurement, acquisition, waveform, screenshot and sequence
   subsets. A shared series does not imply identical model capabilities. An
   operation may use multiple native commands to satisfy the existing public
   semantic; a different command spelling is not a reason to disable it.
3. Implement only the necessary driver differences. Reuse existing strategies
   when the manual establishes the same behavior. Branches for a finite set of
   series must reject all other series explicitly. Preserve actual raw
   responses, completion, temporary-state restoration and artifact encodings.
4. Pass the registered physical model ID through planning and simulation. Do
   not select a representative model from a series name. The planning backend
   must reject an identity/profile mismatch. Simulate the same native command
   vocabulary, state changes, error/status behavior and model restrictions.
5. Compose workflows from the driver boundary: `preflight_status`,
   `workflow_status`, `wait_for_current_trigger_completion`, and driver-owned
   `plan_workflow_step`. Waiting for the current acquisition never arms it.
   Keep native status distinct from a normalized error queue. Derive optional
   cleanup steps and sequence actions from capabilities.
6. Project the Core profile into adapter metadata. Measurement choices,
   channels, capture formats/points and sequence actions must agree in WebUI,
   CLI validation, Worker validation and runtime, including bypassed UI inputs.

Verify identity rejection, profile/driver consistency, dry-run plans, simulator
execution, adapter payloads and unsupported-option rejection before writes.
Exercise meaningful error paths: malformed/incomplete status, temporary-state
restoration, timeout, force, cancellation and a sequence containing a later
unsupported step. Reuse the acceptance matrix across registered models rather
than taking the intersection of their capabilities.

Follow [Testing Guidelines](../testing-guidelines.md). Hardware-free results do
not establish live behavior. Live validation is explicit, bounded and uses only
a user-supplied resource; its private evidence stays outside tracked public
documentation. Maintain durable behavior and option limits in
[supported models](supported-models.md) and the relevant support matrix.
