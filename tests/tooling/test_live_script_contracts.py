from __future__ import annotations

from tests.tooling._live_script_test_support import REPO_ROOT


LIVE_SCRIPTS = (
    REPO_ROOT / "scripts" / "live-cli-check.ps1",
    REPO_ROOT / "scripts" / "live-dvm-check.ps1",
    REPO_ROOT / "scripts" / "live-segmented-check.ps1",
    REPO_ROOT / "scripts" / "live-serial-check.ps1",
    REPO_ROOT / "scripts" / "live-workflow-check.ps1",
)


def test_live_scripts_use_shared_backend_arguments_for_live_invocations() -> None:
    for script_path in LIVE_SCRIPTS:
        script = script_path.read_text(encoding="utf-8")
        assert '[Alias("VisaLibrary")]' in script
        assert script.count("Get-LiveConnectionArguments -Resource $Resource") == 1
        assert '"--live"' not in script


def test_baseline_live_script_contains_acquisition_measurement_and_status_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "run",
        "stop-acquisition",
        "single",
        "force-trigger",
        "capture-wait-trigger",
        "trigger-holdoff",
        "acquisition-average",
        "acquisition-high-resolution",
        "acquisition-peak",
        "acquisition-queries",
        "system-status",
        "measurements",
        "measure-phase",
        "measure-delay",
        "measure-stats",
        "measure-controls",
        "cursor-lifecycle",
        "measure-results",
        "channel-summary",
    ):
        assert f'Invoke-BaselineCase -Name "{case_name}"' in script

    for command in (
        'Command "sample-rate"',
        'Command "acquisition-points"',
        'Command "record-length"',
        'Command "system-opc"',
        'Command "system-status-byte"',
        'Command "system-operation-status"',
        'Command "system-standard-event"',
        'Command "system-options"',
        'Command "run"',
        'Command "stop-acquisition"',
        'Command "single"',
        'Command "force-trigger"',
        'Command "capture"',
        'Command "trigger-holdoff"',
        'Command "measure"',
        'Command "measure-stats"',
        'Command "measure-clear"',
        'Command "measure-show"',
        'Command "measure-source"',
        'Command "measure-window"',
        'Command "cursor"',
        'Command "measure-results"',
        'Command "channel-summary"',
    ):
        assert command in script

    assert "$identity.capabilities.supports_measure_results_dump" in script
    assert '@("--type", "average", "--count", "16")' in script
    assert '@("--type", "high_resolution")' in script
    assert '@("--type", "peak")' in script
    assert '@("--type", "normal")' in script

    system_status_start = script.index(
        'Invoke-BaselineCase -Name "system-status"'
    )
    system_status_end = script.index(
        "\n    if (-not $script:FunctionalFailed -and", system_status_start
    )
    system_status_case = script[system_status_start:system_status_end]
    assert '"system-standard-event"' in system_status_case
    assert "*ESR?" in system_status_case

    screenshot_start = script.index('Invoke-BaselineCase -Name "screenshot-bmp"')
    screenshot_end = script.index(
        "\n    if (-not $script:FunctionalFailed", screenshot_start + 1
    )
    screenshot_case = script[screenshot_start:screenshot_end]
    assert 'Add-NotApplicableCase -Name "screenshot-bmp"' in screenshot_case

    for case_name in (
        "run",
        "single",
        "force-trigger",
        "capture-wait-trigger",
    ):
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[case_start:case_end]
        assert 'Command "stop-acquisition"' in case_block

    force_start = script.index('Invoke-BaselineCase -Name "force-trigger"')
    force_end = script.index(
        "\n    if (-not $script:FunctionalFailed", force_start + 1
    )
    force_case = script[force_start:force_end]
    assert force_case.index('Stage "force-trigger-run"') < force_case.index(
        'Stage "force-trigger"'
    )
    assert force_case.index('Command "run"') < force_case.index(
        'Command "force-trigger"'
    )
    assert force_case.index('Command "force-trigger"') < force_case.index(
        'Command "stop-acquisition"'
    )
    assert 'Command "single"' not in force_case

    cursor_start = script.index('Invoke-BaselineCase -Name "cursor-lifecycle"')
    cursor_end = script.index(
        "\n    if (-not $script:FunctionalFailed", cursor_start + 1
    )
    cursor_case = script[cursor_start:cursor_end]
    assert cursor_case.index('Stage "cursor-off"') < cursor_case.index(
        'Stage "cursor-off-query"'
    )
    assert 'Arguments @("--off")' in cursor_case
    assert ':MARKer:MODE MANual' in cursor_case
    assert ':MARKer:MODE TIME' not in cursor_case
    for stage in (
        'Stage "cursor-set-baseline"',
        'Stage "cursor-query-baseline"',
        'Stage "cursor-set-x1-partial"',
        'Stage "cursor-query-x1-partial"',
        'Stage "cursor-set-y2-partial"',
        'Stage "cursor-query-y2-partial"',
    ):
        assert stage in cursor_case
    assert '"--x1", "0.0005"' in cursor_case
    assert '"--y2", "0.25"' in cursor_case
    assert "Assert-NearlyEqual" in cursor_case

    lifecycle_markers = [
        script.index('Invoke-BaselineCase -Name "fixture-baseline"'),
        script.index('Invoke-BaselineCase -Name "save-pwd-fixture"'),
        script.index('Invoke-BaselineCase -Name "save-pwd"'),
        script.index('Invoke-BaselineCase -Name "save-settings"'),
        script.index('Invoke-BaselineCase -Name "save-export"'),
        script.index('Invoke-BaselineCase -Name "acquisition"'),
        script.index('Invoke-BaselineCase -Name "single"'),
        script.index('Invoke-BaselineCase -Name "capture-wait-trigger"'),
    ]
    assert lifecycle_markers == sorted(lifecycle_markers)
    for case_name in (
        "save-pwd-fixture",
        "save-pwd",
        "save-settings",
        "save-export",
    ):
        assert (
            script.count(f'Invoke-BaselineCase -Name "{case_name}"') == 1
        )
    assert script.index("Invoke-FixtureBaseline") < lifecycle_markers[0]

    pair_start = script.index("$pairMeasurementSnapshot = $null")
    pair_end = script.index(
        'Invoke-BaselineCase -Name "measure-stats"', pair_start
    )
    pair_lifecycle = script[pair_start:pair_end]
    for stage in (
        'Stage "pair-ch2-snapshot-display"',
        'Stage "pair-ch2-snapshot-coupling"',
        'Stage "pair-ch2-snapshot-scale"',
        'Stage "pair-ch2-snapshot-offset"',
        'Stage "pair-ch2-snapshot-probe"',
        'Stage "pair-ch2-prepare-display"',
        'Stage "pair-ch2-prepare-coupling"',
        'Stage "pair-ch2-prepare-scale"',
        'Stage "pair-ch2-prepare-offset"',
        'Stage "measure-ch2-readiness"',
    ):
        assert stage in script
    assert "Prepare-PairMeasurementChannel" in pair_lifecycle
    assert "Invoke-StrictPairMeasurement" in pair_lifecycle
    assert "Invoke-PairMeasurementReadiness" in pair_lifecycle
    assert "Restore-PairMeasurementChannel" in pair_lifecycle
    assert pair_lifecycle.index("Prepare-PairMeasurementChannel") < pair_lifecycle.index(
        'Stage "pair-measurement-run"'
    )
    assert pair_lifecycle.index('Stage "pair-measurement-run"') < pair_lifecycle.index(
        "Invoke-PairMeasurementReadiness"
    )
    assert pair_lifecycle.index("Invoke-PairMeasurementReadiness") < pair_lifecycle.index(
        'Invoke-BaselineCase -Name "measure-phase"'
    )
    assert pair_lifecycle.index('Invoke-BaselineCase -Name "measure-phase"') < pair_lifecycle.index(
        'Invoke-BaselineCase -Name "measure-delay"'
    )
    assert pair_lifecycle.index('Invoke-BaselineCase -Name "measure-delay"') < pair_lifecycle.index(
        'Stage "pair-measurement-stop"'
    )
    assert pair_lifecycle.index('Stage "pair-measurement-stop"') < pair_lifecycle.index(
        "Restore-PairMeasurementChannel"
    )
    assert 'Command "run"' in pair_lifecycle
    assert 'ExpectedCommands @(":RUN")' in pair_lifecycle
    assert 'Command "stop-acquisition"' in pair_lifecycle
    assert 'ExpectedCommands @(":STOP")' in pair_lifecycle
    assert "pair-ch2-restore-$($step.Kind)-query" in script
    assert "invalid measurement sentinels are not accepted" in script
    prompt_start = script.index('Write-Host "PHYSICAL SETUP  operator must prepare"')
    prompt_fixture_start = script.index('Write-Host "FIXTURE POLICY"', prompt_start)
    prompt_cleanup_start = script.index(
        'Write-Host "Press Enter only after the PHYSICAL SETUP above is ready."',
        prompt_fixture_start,
    )
    prompt = script[prompt_start : prompt_cleanup_start + 1000]
    assert prompt.index("PHYSICAL SETUP") < prompt.index("THE VALIDATOR WILL CONFIGURE")
    assert prompt.index("THE VALIDATOR WILL CONFIGURE") < prompt.index("FIXTURE POLICY")
    for required_prompt_text in (
        "CH1 probe -> Probe Demo / Probe Comp",
        "CH2 probe -> same Probe Demo / Probe Comp",
        "stable Probe Comp waveforms are visible",
        "physical attenuation must match",
        "Insert writable USB storage",
        "CH1 vertical scale = 2 V/div",
        "trigger = Edge / CH1 / Positive / 1 V",
        "fixed laboratory validation fixture",
        "does not adapt an incorrect physical fixture",
        "Timebase mode = MAIN / normal horizontal timebase",
        "Press Enter only after the PHYSICAL SETUP above is ready",
    ):
        assert required_prompt_text in prompt
    assert "measure minimum" not in script
    assert "measure maximum" not in script
    assert "midpoint" not in script.lower()
    assert "autoscale fallback" not in script.lower()
    assert "--force-trigger-on-timeout" not in script[
        script.index('Invoke-BaselineCase -Name "capture-wait-trigger"'):
        script.index('Invoke-BaselineCase -Name "trigger-holdoff"')
    ]
    readiness_start = script.index("function Invoke-PairMeasurementReadiness")
    readiness_end = script.index("function Get-PairMeasurementChannelSnapshot", readiness_start)
    readiness = script[readiness_start:readiness_end]
    assert "while ($elapsedMilliseconds -le $TimeoutMilliseconds)" in readiness
    assert "Start-Sleep -Milliseconds $sleepMilliseconds" in readiness
    assert "CH2 pair-measurement precondition did not become measurement-ready" in readiness
    assert "if ($systemErrorCode -ne 0)" in readiness
    assert "Invoke-StrictPairMeasurement" not in readiness

    for case_name, expected_query in (
        ("measure-phase", ":MEASure:PHASe? CHANnel1,CHANnel2"),
        ("measure-delay", ":MEASure:DELay? AUTO,CHANnel1,CHANnel2"),
    ):
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[case_start:case_end]
        assert expected_query in case_block
        assert ".result.valid" in case_block
        assert "Assert-FiniteNumber" in case_block
        assert "Invoke-StrictPairMeasurement" in case_block
        assert 'Command "channel-display"' not in case_block

    invoke_live_cli_start = script.index("function Invoke-LiveCli {")
    invoke_live_cli_end = script.index(
        "\nfunction Get-ErrorDrain {", invoke_live_cli_start
    )
    invoke_live_cli = script[invoke_live_cli_start:invoke_live_cli_end]
    assert '"--log-scpi"' not in invoke_live_cli


def test_baseline_live_script_contains_channel_display_search_and_restore_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "channel-vertical",
        "channel-probe",
        "channel-advanced",
        "display-settings",
        "display-annotation",
        "search-basic",
        "search-event",
        "screenshot-bmp",
        "waveform-amp",
    ):
        assert f'Invoke-BaselineCase -Name "{case_name}"' in script

    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "annotation",
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
    ):
        assert f'Command = "{command}"' in script or f'Command "{command}"' in script

    preflight_start = script.index("function Invoke-HardwareFreePreflight {")
    preflight_end = script.index("\nfunction Restore-InstrumentState {", preflight_start)
    preflight = script[preflight_start:preflight_end]
    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "display-vectors",
        "annotation",
        "search-state",
        "search-mode",
        "search-count",
        "search-event",
    ):
        assert f'Command = "{command}"' in preflight
    assert '"--format", "bmp"' in preflight

    channel_vertical_start = script.index(
        'Invoke-BaselineCase -Name "channel-vertical"'
    )
    channel_vertical_end = script.index(
        '\n    if (-not $script:FunctionalFailed)', channel_vertical_start + 1
    )
    channel_vertical = script[channel_vertical_start:channel_vertical_end]
    assert channel_vertical.index('Stage "channel-vertical-scale-set"') < (
        channel_vertical.index('Stage "channel-vertical-scale-query"')
    )
    assert channel_vertical.index('Stage "channel-vertical-scale-query"') < (
        channel_vertical.index('Stage "channel-range-set"')
    )
    assert channel_vertical.index('Stage "channel-range-set"') < (
        channel_vertical.index('Stage "channel-range-query"')
    )
    assert '"--volts-per-division", "2"' in channel_vertical
    assert "-Expected 2.0" in channel_vertical
    assert "$snapshot.ChannelScale" not in channel_vertical

    assert '$identity.capabilities.supports_screenshot_hardcopy_controls' in script
    assert '$identity.capabilities.supports_search_event_navigation' in script
    assert '"edge" -in @($identity.capabilities.search_modes)' in script
    assert 'Stage "waveform-amp-unit-restore"' in script
    assert 'Stage "waveform-amp-unit-restore-query"' in script

    for case_name in (
        "channel-vertical",
        "channel-probe",
        "channel-advanced",
        "display-settings",
        "search-basic",
    ):
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[case_start:case_end]
        assert ".result.command" not in case_block
        assert ".result.commands" not in case_block

    restore_start = script.index("function Restore-InstrumentState {")
    restore_end = script.index("\nif ([string]::IsNullOrWhiteSpace", restore_start)
    restore = script[restore_start:restore_end]
    for command in (
        "channel-label",
        "channel-scale",
        "channel-offset",
        "channel-probe",
        "channel-bandwidth-limit",
        "channel-impedance",
        "channel-invert",
        "channel-range",
        "channel-units",
        "channel-vernier",
        "channel-probe-skew",
        "display-label",
        "display-persistence",
        "display-intensity",
        "annotation",
        "search-state",
    ):
        assert f'Command = "{command}"' in restore


def test_baseline_live_script_contains_trigger_math_generator_save_and_safety_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for case_name in (
        "trigger-edge-settings",
        "trigger-common",
        "trigger-external",
        "trigger-pulse-width",
        "trigger-runt",
        "trigger-transition",
        "trigger-delay",
        "trigger-setup-hold",
        "trigger-edge-burst",
        "trigger-tv",
        "trigger-pattern",
        "trigger-or",
        "math-operator",
        "math-transform",
        "math-display",
        "math-vertical",
        "math-composite-source",
        "math-filter",
        "math-visualization",
        "math-clear",
        "fft",
        "fft-advanced",
        "wgen-basic",
        "wgen-model-validation",
        "demo-basic",
        "demo-phase",
        "autoscale",
        "setup-lifecycle",
        "setup-slot-lifecycle",
        "reference-lifecycle",
        "save-settings",
        "save-export",
        "safe-cleanup",
    ):
        assert f'Invoke-BaselineCase -Name "{case_name}"' in script

    preflight_start = script.index("function Invoke-HardwareFreePreflight {")
    preflight_end = script.index("\nfunction Restore-InstrumentState {", preflight_start)
    preflight = script[preflight_start:preflight_end]
    for command in (
        "trigger-pulse-width",
        "trigger-runt",
        "trigger-transition",
        "trigger-delay",
        "trigger-setup-hold",
        "trigger-edge-burst",
        "trigger-tv",
        "trigger-pattern",
        "trigger-or",
        "trigger-edge-external-level",
        "math-operator",
        "math-transform",
        "fft",
        "wgen-output",
        "demo-output",
        "autoscale",
        "setup-save",
        "setup-recall",
        "save-image",
        "save-waveform",
        "cleanup",
    ):
        assert f'Command = "{command}"' in preflight

    assert '$snapshot.Is4000XSeries' in script
    assert '$snapshot.InstalledOptions = @($options.result.options)' in script
    assert '$snapshot.WgenApplicable = "WAVEGEN" -in @($snapshot.InstalledOptions)' in script
    assert '$snapshot.WgenApplicable' in script
    assert 'Waveform Generator option is not installed' in script
    system_status_start = script.index('Invoke-BaselineCase -Name "system-status"')
    system_status_end = script.index(
        '\n    if (-not $script:FunctionalFailed', system_status_start
    )
    system_status = script[system_status_start:system_status_end]
    assert system_status.count('-Command "system-options"') == 1
    assert 'ExpectedCommands @("*OPT?")' in system_status
    assert script.count('-Command "system-options"') == 1
    assert 'Stage "wgen-output-off"' in script
    assert 'Stage "demo-output-off"' in script
    assert 'Command = "wgen-output"' in script
    assert 'Command = "demo-output"' in script
    assert 'Command = "math-display"' in script
    assert '"--pattern", "XXX1"' in script
    assert '"--pattern", "XXXR"' in script
    assert '"disable_dvm"' in script
    assert '"disable_demo_output"' in script
    assert '":DVM:ENABle 0"' in script
    assert '":DEMO:OUTPut OFF"' in script
    assert '"disable_wgen"' in script
    assert '"wgen_not_implemented"' in script
    assert "Original save format context is not restorable." not in script
    assert "SaveFixtureEstablished" in script
    assert 'Stage "preflight-cli-save-waveform-length-max-query"' in preflight
    assert '-Command "save-waveform-length-max"' in preflight
    assert '-Arguments @("--query")' in preflight
    assert '-Stage "snapshot-save-waveform-length-max"' in script
    assert '-Command "save-waveform-length-max" -Arguments @("--query")' in script
    assert "SaveWaveformLengthMax = [bool]$saveWaveformLengthMax.result.enabled" in script
    assert '@("--format", "none")' not in script
    assert '"\\usb\\scopes-tool-live-${timestamp}.scp"' in script
    setup_slot_start = script.index('Invoke-BaselineCase -Name "setup-slot-lifecycle"')
    setup_slot_end = script.index(
        'Invoke-BaselineCase -Name "safe-cleanup"', setup_slot_start
    )
    setup_slot_case = script[setup_slot_start:setup_slot_end]
    assert 'Command "setup-save"' in setup_slot_case
    assert 'Command "setup-recall"' in setup_slot_case
    assert '"--slot", "1"' in setup_slot_case
    reference_start = script.index('Invoke-BaselineCase -Name "reference-lifecycle"')
    reference_end = script.index(
        'Invoke-BaselineCase -Name "setup-slot-lifecycle"', reference_start
    )
    reference_case = script[reference_start:reference_end]
    for stage in (
        'Stage "reference-run"',
        'Stage "reference-save"',
        'Stage "reference-display-query"',
        'Stage "reference-label-query"',
        'Stage "reference-clear"',
        'Stage "reference-stop"',
    ):
        assert stage in reference_case
    for command in (
        "run",
        "reference-save",
        "reference-query",
        "reference-display",
        "reference-label",
        "reference-clear",
        "stop-acquisition",
    ):
        assert f'Command "{command}"' in reference_case
    assert 'ExpectedCommands @(\":RUN\")' in reference_case
    assert 'ExpectedCommands @(\":STOP\")' in reference_case
    assert ':WMEMory1:SAVE CHANnel1' in reference_case
    assert '"*OPC?"' in reference_case
    assert 'Start-Sleep' not in reference_case
    assert '$referenceFailure = $null' in reference_case
    assert 'Add-Diagnostic -Name "reference-lifecycle" -Message $stopMessage' in reference_case
    assert 'if ($null -eq $referenceFailure)' in reference_case
    assert 'Command "autoscale"' not in reference_case
    assert 'Command "channel-scale"' not in reference_case
    assert reference_case.index('Stage "reference-run"') < reference_case.index(
        "Invoke-ReferenceWaveformReadiness"
    )
    assert reference_case.index("Invoke-ReferenceWaveformReadiness") < reference_case.index(
        'Stage "reference-save"'
    )
    assert reference_case.index('Stage "reference-save"') < reference_case.index(
        'Stage "reference-display-on"'
    )
    assert reference_case.index('Stage "reference-display-query"') < reference_case.index(
        'Stage "reference-label-set"'
    )
    assert reference_case.index('Stage "reference-label-query"') < reference_case.index(
        'Stage "reference-clear"'
    )
    assert reference_case.index('Stage "reference-clear"') < reference_case.index(
        'Stage "reference-stop"'
    )

    reference_readiness_start = script.index("function Invoke-ReferenceWaveformReadiness")
    reference_readiness_end = script.index(
        "function Invoke-PairMeasurementReadiness", reference_readiness_start
    )
    reference_readiness = script[reference_readiness_start:reference_readiness_end]
    assert 'Stage "reference-ch1-readiness"' in reference_readiness
    assert '"--source-channel", "1"' in reference_readiness
    assert '"--item", "vpp"' in reference_readiness
    assert ':MEASure:VPP? CHANnel1' in reference_readiness
    assert "while ($elapsedMilliseconds -le $TimeoutMilliseconds)" in reference_readiness
    assert "Start-Sleep -Milliseconds $sleepMilliseconds" in reference_readiness
    assert "CH1 reference-waveform precondition did not become measurement-ready" in reference_readiness
    assert "if ($systemErrorCode -ne 0)" in reference_readiness
    save_pwd_start = script.index('Invoke-BaselineCase -Name "save-pwd"')
    save_settings_start = script.index('Invoke-BaselineCase -Name "save-settings"')
    save_settings_end = script.index(
        'Invoke-BaselineCase -Name "save-export"', save_settings_start
    )
    save_pwd_case = script[save_pwd_start:save_settings_start]
    save_settings_case = script[save_settings_start:save_settings_end]
    fixture_case_start = script.index('Invoke-BaselineCase -Name "save-pwd-fixture"')
    assert fixture_case_start < save_pwd_start
    assert 'Stage "save-pwd-fixture-query"' in script[fixture_case_start:save_pwd_start]
    assert 'Test-SavePathEquivalent' in script[fixture_case_start:save_pwd_start]
    assert '"\\usb"' in script[fixture_case_start:save_pwd_start]
    assert 'Stage "save-pwd-set"' in save_pwd_case
    assert 'Stage "save-pwd-query"' in save_pwd_case
    assert "save-pwd-restore" not in save_pwd_case
    for command in (
        "save-image-format",
        "save-filename",
        "save-image-palette",
        "save-image-ink-saver",
        "save-image-factors",
    ):
        assert f'Command "{command}"' in save_settings_case
    assert "finally" in save_settings_case
    configure_order = [
        save_settings_case.index('Stage "save-image-format-png"'),
        save_settings_case.index('Stage "save-filename-set"'),
        save_settings_case.index('Stage "save-image-palette-set"'),
        save_settings_case.index('Stage "save-image-ink-saver-set"'),
        save_settings_case.index('Stage "save-image-factors-set"'),
    ]
    assert configure_order == sorted(configure_order)
    restore_order = [
        save_settings_case.index('Stage = "save-image-factors-restore"'),
        save_settings_case.index('Stage = "save-image-ink-saver-restore"'),
        save_settings_case.index('Stage = "save-image-palette-restore"'),
        save_settings_case.index('Stage = "save-filename-restore"'),
    ]
    assert restore_order == sorted(restore_order)
    for stage in (
        "save-filename-restore-query",
        "save-image-palette-restore-query",
        "save-image-ink-saver-restore-query",
        "save-image-factors-restore-query",
    ):
        assert f'Stage "{stage}"' in save_settings_case
    assert "$identity.capabilities.supports_advanced_fft" in script
    assert "$identity.capabilities.supports_math_goft" in script
    assert "$identity.capabilities.demo_functions" in script
    assert "WGEN output OFF and disconnected from unknown DUT" in script
    assert "DEMO output OFF" in script
    assert "External trigger input" in script
    assert "Math Function 1 is disposable" in script

    save_export_start = script.index('Invoke-BaselineCase -Name "save-export"')
    save_export_end = script.index(
        'Invoke-BaselineCase -Name "acquisition"', save_export_start
    )
    save_export = script[save_export_start:save_export_end]
    image_format_set = save_export.index('Stage "save-image-format-png"')
    image_save = save_export.index('$image = Invoke-LiveCli -Stage "save-image"')
    waveform_format_set = save_export.index('Stage "save-waveform-format-csv"')
    waveform_length_set = save_export.index('Stage "save-waveform-length-1000"')
    waveform_stage = save_export.index('$waveform = Invoke-LiveCli -Stage "save-waveform"')
    waveform_validation = save_export.index(
        "if (-not [bool]$waveform.result.instrument_side", waveform_stage
    )
    handoff_sleep = save_export.index("Start-Sleep -Seconds 3", waveform_validation)
    length_restore = save_export.index(
        'Invoke-LiveCli -Stage "save-waveform-length-restore"'
    )
    assert "Start-Sleep -Milliseconds 500" not in save_export
    assert (
        image_format_set
        < image_save
        < waveform_format_set
        < waveform_length_set
        < waveform_stage
        < waveform_validation
        < handoff_sleep
        < length_restore
    )
    assert 'Stage "save-image-format-restore"' not in save_export
    assert 'Stage "save-waveform-format-restore"' not in save_export

    restore_start = script.index("function Restore-InstrumentState {")
    restore_end = script.index(
        "\nif ([string]::IsNullOrWhiteSpace($Resource))", restore_start
    )
    restore = script[restore_start:restore_end]
    assert 'Name = "save directory fixture"' in restore
    assert 'Name = "waveform save format fixture"' in restore
    assert "SaveFixtureEstablished" in restore
    assert 'Command = "save-image-format"' in restore
    assert 'Command = "save-waveform-format"' in restore
    assert 'Name = "waveform save length"' in restore
    assert 'Command = "save-waveform-length"' in restore


def test_save_pwd_validation_uses_fixed_usb_fixture_without_obsolete_logic() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    for obsolete in (
        "Get-SavePathSetterArgument",
        "save-pwd-prerequisite-set",
        "save-pwd-prerequisite-query",
        "save-pwd-restore",
        "queryable but not setter-restorable",
    ):
        assert obsolete not in script
    assert '"--path", [string]$snapshot.SavePwd' not in script
    assert '"--path", $savePwdSetterPath' not in script

    fixture_start = script.index('Invoke-BaselineCase -Name "save-pwd-fixture"')
    assert fixture_start < script.index('Invoke-BaselineCase -Name "save-pwd"')
    fixture_case = script[
        fixture_start:script.index(
            'Invoke-BaselineCase -Name "save-pwd"', fixture_start
        )
    ]
    assert 'Command "save-pwd"' in fixture_case
    assert 'Arguments @("--query")' in fixture_case
    assert "Test-SavePathEquivalent" in fixture_case
    assert '"\\usb"' in fixture_case

    save_pwd_start = script.index('Invoke-BaselineCase -Name "save-pwd"')
    save_pwd_end = script.index('Invoke-BaselineCase -Name "save-settings"')
    save_pwd_case = script[save_pwd_start:save_pwd_end]
    setter_index = save_pwd_case.index('Stage "save-pwd-set"')
    query_index = save_pwd_case.index('Stage "save-pwd-query"')
    assert setter_index < query_index
    assert save_pwd_case.index("-Arguments @(\"--path\", \"\\usb\")") < query_index
    assert save_pwd_case.count('Command "save-pwd"') == 2
    assert ':SAVE:PWD "\\usb"' in save_pwd_case
    assert "Test-SavePathEquivalent" in save_pwd_case

    assert "[10] Set the instrument Save directory" not in script
    assert "Save PWD and active Save image/waveform format context are validator-owned" in script
    assert "Cleanup leaves Save PWD at \\usb and waveform save format CSV after the" in script


def test_baseline_part1_capability_gates_and_cleanup_wiring() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    gated_cases = {
        "measure-delay": "$identity.capabilities.supports_delay_measurement",
        "math-composite-source": "$identity.capabilities.supports_math_goft",
        "fft-advanced": "$identity.capabilities.supports_advanced_fft",
        "demo-phase": "$identity.capabilities.demo_functions",
        "reference-lifecycle": "reference_waveforms",
        "math-filter": "math_filter_operations",
        "math-visualization": "math_visualization_operations",
        "math-clear": "mathClearSupported",
    }
    for case_name, capability in gated_cases.items():
        case_start = script.index(f'Invoke-BaselineCase -Name "{case_name}"')
        gate_start = script.rfind("\n    if (-not $script:FunctionalFailed", 0, case_start)
        assert gate_start >= 0
        case_end = script.index(
            "\n    if (-not $script:FunctionalFailed", case_start + 1
        )
        case_block = script[gate_start:case_end]
        assert capability in case_block
        assert f'Add-NotApplicableCase -Name "{case_name}"' in case_block

    fft_advanced_start = script.index('Invoke-BaselineCase -Name "fft-advanced"')
    fft_advanced_end = script.index(
        'Invoke-BaselineCase -Name "wgen-basic"', fft_advanced_start
    )
    fft_advanced_case = script[fft_advanced_start:fft_advanced_end]
    assert "$identity.capabilities.math_function_count" in script[
        script.rfind("\n    if (-not $script:FunctionalFailed", 0, fft_advanced_start):
    ]
    assert '"--function", "4"' in fft_advanced_case
    assert '"--start-hz", "0"' in fft_advanced_case
    assert '"--gate", "none"' in fft_advanced_case
    assert '"--phase-reference", "trigger"' in fft_advanced_case
    assert '"--detection-type", "sample"' in fft_advanced_case
    assert '"--detection-points", "640"' in fft_advanced_case
    assert '"--gate", "zoom"' not in fft_advanced_case
    for command in (
        ":FUNCtion4:OPERation FFTPhase",
        ":FUNCtion4:FREQuency:STARt 0",
        ":FUNCtion4:FREQuency:STOP 1000000",
        ":FUNCtion4:GATE NONE",
        ":FUNCtion4:PHASe:REFerence TRIGger",
        ":FUNCtion4:DETection:TYPE SAMPle",
        ":FUNCtion4:DETection:POINts 640",
    ):
        assert command in fft_advanced_case
    assert 'Stage "fft-advanced-query"' in fft_advanced_case
    assert '"--function", "4", "--query"' in fft_advanced_case
    assert 'Stage "fft-advanced-display-off"' in fft_advanced_case
    assert '"--function", "4", "--off"' in fft_advanced_case

    demo_phase_start = script.index('Invoke-BaselineCase -Name "demo-phase"')
    demo_phase_end = script.index(
        'Invoke-BaselineCase -Name "autoscale"', demo_phase_start
    )
    demo_phase_case = script[demo_phase_start:demo_phase_end]
    assert 'Command "demo-phase"' in demo_phase_case
    assert 'Arguments @("--degrees", "90")' in demo_phase_case
    assert ':DEMO:FUNCtion:PHASe:PHASe 90' in demo_phase_case
    assert 'Stage "demo-phase-query"' in demo_phase_case
    assert 'Arguments @("--query")' in demo_phase_case
    assert ':DEMO:FUNCtion:PHASe:PHASe?' in demo_phase_case
    assert '$query.result.phase_degrees' in demo_phase_case
    assert '$query.result.degrees' not in demo_phase_case
    assert 'Properties["phase_raw"]' in demo_phase_case
    assert '-Expected 90' in demo_phase_case

    composite_start = script.index(
        'Invoke-BaselineCase -Name "math-composite-source"'
    )
    composite_end = script.index(
        'Invoke-BaselineCase -Name "math-filter"', composite_start
    )
    composite_gate_start = script.rfind(
        "\n    if (-not $script:FunctionalFailed", 0, composite_start
    )
    composite_case = script[composite_gate_start:composite_end]
    assert "$identity.capabilities.supports_math_goft" in composite_case
    assert 'Add-NotApplicableCase -Name "math-composite-source"' in composite_case

    natural_start = script.index('Invoke-BaselineCase -Name "capture-wait-trigger"')
    natural_end = script.index(
        'Invoke-BaselineCase -Name "trigger-holdoff"', natural_start
    )
    natural_case = script[natural_start:natural_end]
    assert '"--wait-trigger", "--trigger-timeout-ms", "5000"' in natural_case
    assert '"--trigger-poll-interval-ms", "100"' in natural_case
    assert "trigger-edge" not in natural_case
    assert '"--item", "minimum"' not in natural_case
    assert '"--item", "maximum"' not in natural_case
    assert "--force-trigger-on-timeout" not in natural_case
    assert 'Invoke-BaselineCase -Name "capture-wait-trigger-fallback"' not in script
    assert "--force-trigger-on-timeout" not in script

    assert 'Command "measure-sweep"' not in script
    assert 'Command "reference-clear"' in script
    assert 'Command "setup-save"' in script
    assert 'Command "setup-recall"' in script
    assert 'Command "math-visualization"' in script
    assert 'Stage "fft-display-off"' in script
    assert 'Stage "fft-advanced-display-off"' in script
    measure_start = script.index('Invoke-BaselineCase -Name "measure-controls"')
    measure_end = script.index(
        'Invoke-BaselineCase -Name "cursor-lifecycle"', measure_start
    )
    measure_case = script[measure_start:measure_end]
    for stage in (
        'Stage "measure-show-before"',
        'Stage "measure-source-before"',
        'Stage "measure-window-before"',
        'Stage "measure-source-restore"',
        'Stage "measure-source-restore-query"',
        'Stage "measure-window-restore"',
        'Stage "measure-window-restore-query"',
    ):
        assert stage in measure_case
    assert "finally" in measure_case
    assert 'throw "Measurement control restoration failed:' in measure_case
    assert "Measure Show may remain ON because the current public CLI exposes" in script
    assert 'Get-ErrorDrain -Stage "final-error-queue"' in script
    assert 'Command "cleanup"' in script


def test_live_cli_check_recommends_restart_before_validation() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    recommended_start = script.index('Write-Host "RECOMMENDED BEFORE VALIDATION"')
    physical_setup = script.index(
        'Write-Host "PHYSICAL SETUP  operator must prepare"'
    )
    prompt = script.index(
        'Write-Host "Press Enter only after the PHYSICAL SETUP above is ready."'
    )

    assert recommended_start < physical_setup < prompt

    block = script[recommended_start:physical_setup].lower()
    assert "restart" in block
    assert "recommended" in block
    assert "not required" in block
    assert "transient instrument-side state" in block

    checklist = script[physical_setup:prompt]
    assert "restart" not in checklist.lower()
    assert 'Write-Host "  [11]' not in script


def _extract_brace_block(script: str, start: int) -> str:
    depth = 0
    for index in range(start, len(script)):
        if script[index] == "{":
            depth += 1
        elif script[index] == "}":
            depth -= 1
            if depth == 0:
                return script[start : index + 1]
    raise AssertionError("unbalanced braces starting at offset %d" % start)


def test_live_cli_check_warns_4034a_about_autoscale_save_destination() -> None:
    script = (REPO_ROOT / "scripts" / "live-cli-check.ps1").read_text(
        encoding="utf-8"
    )

    gate = 'if ([string]$script:Target -eq "keysight-dsox4034a") {'
    gate_positions = []
    search_from = 0
    while True:
        position = script.find(gate, search_from)
        if position < 0:
            break
        gate_positions.append(position)
        search_from = position + 1
    assert len(gate_positions) == 2, (
        "expected exactly two 4034A gates, found %d" % len(gate_positions)
    )

    recommended_start = script.index(
        'Write-Host "RECOMMENDED BEFORE VALIDATION"'
    )
    physical_setup = script.index(
        'Write-Host "PHYSICAL SETUP  operator must prepare"'
    )
    pass_line = script.index('Write-Host "PASS  baseline live validation"')
    exit_zero = script.index("exit 0", pass_line)

    first_gate, second_gate = gate_positions
    pre_block = _extract_brace_block(script, first_gate)
    post_block = _extract_brace_block(script, second_gate)

    assert recommended_start < first_gate < physical_setup
    assert "KNOWN DSO-X 4034A FRONT-PANEL BEHAVIOR" in pre_block
    assert '`"Please Select`"' in pre_block
    assert "not a Scopes Tool SAVE" in pre_block
    assert "reselect the USB destination under Save To" in pre_block

    assert pass_line < second_gate < exit_zero
    assert "NOTE  DSO-X 4034A Autoscale" in post_block
    assert '`"Please Select`"' in post_block
    assert "Reselect the USB destination" in post_block
