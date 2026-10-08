from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest
from tests.tooling._live_script_test_support import REPO_ROOT


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_wgen_applicability_and_runtime_failure(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-wgen-applicability-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @(
    "Add-CaseResult", "Add-NotApplicableCase", "Assert-NearlyEqual",
    "Assert-FiniteNumber", "Assert-ScpiSent", "ConvertTo-InvariantString",
    "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$fixtureFunctionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-FixtureBaseline"
    )
}, $true)
if ($null -eq $fixtureFunctionAst) { throw "Missing Invoke-FixtureBaseline." }
Invoke-Expression $fixtureFunctionAst.Extent.Text

$snapshotAssignment = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('$snapshot = [pscustomobject]@{')
    )
}, $true)
if ($null -eq $snapshotAssignment) { throw "Missing production snapshot construction." }

$systemStatusCommand = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "system-status"') -and
        $node.Extent.Text.Contains('$snapshot.InstalledOptions = @($options.result.options)')
    )
}, $true)
if ($null -eq $systemStatusCommand) { throw "Missing production system-status command." }

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
}

$wgenIf = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('if (-not $script:FunctionalFailed -and $snapshot.WgenApplicable -eq $true)')
    )
}, $true)
if ($null -eq $wgenIf) { throw "Missing wgen-basic applicability gate." }
$wgenCode = $wgenIf.Extent.Text

$demoIf = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_demo)')
    )
}, $true)
if ($null -eq $demoIf) { throw "Missing demo-basic continuation gate." }
$demoCode = $demoIf.Extent.Text

$wgenModelIf = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.TrimStart().StartsWith('if (-not $script:FunctionalFailed -and $snapshot.WgenApplicable -eq $true -and $snapshot.Is4000XSeries -eq $true)')
    )
}, $true)
if ($null -eq $wgenModelIf) { throw "Missing wgen-model-validation applicability gate." }
$wgenModelCode = $wgenModelIf.Extent.Text

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:Scenario = ""
$script:InstalledOptions = @()

function New-QueryPayload {
    param([hashtable] $Values)
    return [pscustomobject]@{
        result = [pscustomobject]$Values
    }
}

function New-ProductionIdentity {
    return [pscustomobject]@{
        capabilities = [pscustomobject]@{
            series = "4000X"
            analog_channels = 4
            default_waveform_points = 1000
            safe_max_waveform_points = 4000000
            supports_word_format = $true
            supports_raw_points_mode = $true
            supports_measurements = $true
            supports_delay_measurement = $true
            supports_measure_results_dump = $true
            supports_demo = $true
            demo_functions = @("sine")
            math_function_count = 4
            supports_math_goft = $true
            math_filter_operations = @()
            math_visualization_operations = @()
            supports_advanced_fft = $true
            supports_screenshot = $true
            supports_screenshot_hardcopy_controls = $true
            supports_segmented_memory = $true
            segmented_max_segments = 1000
            supports_serial_decode = $true
            serial_bus_count = 2
            serial_modes = @("uart", "i2c", "spi", "can")
            reference_waveforms = 4
            supports_channel_label = $true
            channel_label_max_length = 10
            supports_display_label = $true
            supports_annotation = $false
            supports_annotation_position = $false
            annotation_slots = 0
            supports_indexed_annotation = $false
            supports_50_ohm_impedance = $true
            supports_search_basic = $true
            supports_search_event_navigation = $true
            search_modes = @("edge")
        }
    }
}

function Initialize-ProductionSnapshot {
    param([Parameter(Mandatory = $true)] $Identity, [bool] $Is4000X = $false)

    $acquisition = New-QueryPayload @{ type = "normal"; count = 1 }
    $channelDisplay = New-QueryPayload @{ display = $true }
    $channelCoupling = New-QueryPayload @{ coupling = "dc" }
    $channelLabel = New-QueryPayload @{ text = "Original" }
    $channelScale = New-QueryPayload @{ volts_per_division = 1.0 }
    $channelOffset = New-QueryPayload @{ volts = 0.0 }
    $channelProbe = New-QueryPayload @{ probe_ratio = 10.0 }
    $channelBandwidth = New-QueryPayload @{ bandwidth_limit = $false }
    $channelImpedance = New-QueryPayload @{ impedance = "one_meg" }
    $channelInvert = New-QueryPayload @{ invert = $false }
    $channelRange = New-QueryPayload @{ range_volts = 8.0 }
    $channelUnits = New-QueryPayload @{ units = "volt" }
    $channelVernier = New-QueryPayload @{ vernier = $false }
    $channelProbeSkew = New-QueryPayload @{ probe_skew_seconds = 0.0 }
    $displayLabels = New-QueryPayload @{ display_label = $true }
    $displayPersistence = New-QueryPayload @{ mode = "minimum"; seconds = $null }
    $displayIntensity = New-QueryPayload @{ value = 50 }
    $displayVectors = New-QueryPayload @{ value = $true }
    $annotationState = $null
    $annotationRestorable = $false
    $timebaseScale = New-QueryPayload @{ seconds_per_division = 0.001 }
    $timebasePosition = New-QueryPayload @{ position_seconds = 0.0 }
    $timebaseReference = New-QueryPayload @{ reference = "center" }
    $triggerSource = New-QueryPayload @{ source = "analog-channel"; source_channel = 1 }
    $triggerSlope = New-QueryPayload @{ slope = "negative" }
    $triggerLevel = New-QueryPayload @{ level_volts = 0.0 }
    $triggerHoldoff = New-QueryPayload @{ seconds = 0.000001 }
    $is2000XSeries = $false
    $is3000XSeries = $false
    $is4000XSeries = $Is4000X
    $triggerEdgeCoupling = $null
    $triggerEdgeReject = $null
    $triggerSweep = $null
    $triggerNoiseReject = $null
    $triggerHfReject = $null
    $externalTrigger = $null
    $externalTriggerLevel = $null
    $searchSupported = $true
    $identity = $Identity
    $savePwd = New-QueryPayload @{ path = "\\usb" }
    $saveFilename = New-QueryPayload @{ name = "scope" }
    $saveImageFormat = New-QueryPayload @{ format = "none" }
    $saveImagePalette = New-QueryPayload @{ palette = "color" }
    $saveImageInkSaver = New-QueryPayload @{ enabled = $true }
    $saveImageFactors = New-QueryPayload @{ enabled = $false }
    $saveWaveformFormat = New-QueryPayload @{ format = "csv" }
    $saveWaveformLength = New-QueryPayload @{ points = 1000 }
    $saveWaveformLengthMax = New-QueryPayload @{ enabled = $false }
    $snapshot = $null
    Invoke-Expression $snapshotAssignment.Extent.Text | Out-Null
    return $snapshot
}

function Invoke-ProductionSystemStatus {
    $is2000XSeries = $false
    $is3000XSeries = $false
    $is4000XSeries = $false
    Invoke-Expression $systemStatusCommand.Extent.Text | Out-Null
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($script:Scenario -eq "runtime-failure" -and $Command -eq "wgen-function") {
        throw "-241,Hardware missing"
    }
    switch ($Command) {
        "channel-display" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:DISPlay ON") }
                result = [pscustomobject]@{ command = ":CHANnel1:DISPlay ON" }
            }
        }
        "channel-scale" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe 2") }
                result = [pscustomobject]@{ command = ":CHANnel1:SCALe 2" }
            }
        }
        "acquisition" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":ACQuire:TYPE NORMal") }
                result = [pscustomobject]@{ command = ":ACQuire:TYPE NORMal" }
            }
        }
        "trigger-edge" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    ":TRIGger:MODE EDGE",
                    ":TRIGger:EDGE:SOURce CHANnel1",
                    ":TRIGger:EDGE:SLOPe POSitive"
                ) }
                result = [pscustomobject]@{ command = ":TRIGger:EDGE:SLOPe POSitive" }
            }
        }
        "system-opc" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*OPC?") }
                result = [pscustomobject]@{ complete = $true; raw = "1" }
            }
        }
        "system-status-byte" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*STB?") }
                result = [pscustomobject]@{ value = 0; set_bits = @() }
            }
        }
        "system-operation-status" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":OPERegister:CONDition?") }
                result = [pscustomobject]@{ value = 0; set_bits = @() }
            }
        }
        "system-standard-event" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*ESR?") }
                result = [pscustomobject]@{ value = 0; set_bits = @() }
            }
        }
        "system-options" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*OPT?") }
                result = [pscustomobject]@{
                    raw = ($script:InstalledOptions -join ",")
                    options = @($script:InstalledOptions)
                }
            }
        }
        "wgen-function" {
            $script:FakeWgen.function = [string]$Arguments[1]
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
        "wgen-frequency" {
            $script:FakeWgen.frequency_hz = [double]$Arguments[1]
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
        "wgen-voltage" {
            $script:FakeWgen.amplitude_volts = [double]$Arguments[1]
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
        "wgen-offset" {
            $script:FakeWgen.offset_volts = [double]$Arguments[1]
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
        "wgen-load" {
            $newLoad = [string]$Arguments[1]
            if ([string]$script:FakeWgen.load -ne $newLoad) {
                if ($newLoad -eq "fifty") {
                    $script:FakeWgen.amplitude_volts = [double]$script:FakeWgen.amplitude_volts / 2.0
                    $script:FakeWgen.offset_volts = [double]$script:FakeWgen.offset_volts / 2.0
                } elseif ($newLoad -eq "one-meg") {
                    $script:FakeWgen.amplitude_volts = [double]$script:FakeWgen.amplitude_volts * 2.0
                    $script:FakeWgen.offset_volts = [double]$script:FakeWgen.offset_volts * 2.0
                }
            }
            $script:FakeWgen.load = $newLoad
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
        "wgen-output" {
            if ($Arguments -contains "--query") {
                $sent = @(":WGEN1:OUTPut?")
            } elseif ($Arguments -contains "true") {
                $script:FakeWgen.enabled = $true
                $sent = @(":WGEN1:OUTPut ON")
            } elseif ($Arguments -contains "false") {
                $script:FakeWgen.enabled = $false
                $sent = @(":WGEN1:OUTPut OFF")
            } else {
                throw "Unexpected fake wgen-output arguments."
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $sent }
                result = [pscustomobject]@{
                    enabled = [bool]$script:FakeWgen.enabled
                }
            }
        }
        "wgen-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                enabled = [bool]$script:FakeWgen.enabled
                function = [string]$script:FakeWgen.function
                load = [string]$script:FakeWgen.load
                frequency_hz = [double]$script:FakeWgen.frequency_hz
                amplitude_volts = [double]$script:FakeWgen.amplitude_volts
                offset_volts = [double]$script:FakeWgen.offset_volts
            } }
        }
        "demo-function" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":DEMO:FUNCtion SIN") }
                result = [pscustomobject]@{}
            }
        }
        "demo-output" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(
                    if ($Arguments -contains "true") { ":DEMO:OUTPut ON" } else { ":DEMO:OUTPut OFF" }
                ) }
                result = [pscustomobject]@{}
            }
        }
        "demo-query" {
            return [pscustomobject]@{ result = [pscustomobject]@{
                enabled = $true
                function = "sine"
            } }
        }
        default {
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
    }
}

function Invoke-Scenario {
    param(
        [ValidateSet("installed", "installed-4000x", "absent", "runtime-failure")]
        [string] $Name
    )
    $script:Scenario = $Name
    $script:Invocations.Clear()
    $script:CaseResults = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:FakeWgen = [pscustomobject]@{
        enabled = $true
        function = "sine"
        load = "one-meg"
        frequency_hz = 1000
        amplitude_volts = 0.5
        offset_volts = 0.0
    }
    $identity = New-ProductionIdentity
    $script:InstalledOptions = if ($Name -eq "installed" -or $Name -eq "installed-4000x" -or $Name -eq "runtime-failure") {
        @("WAVEGEN")
    } else {
        @("BASIC")
    }
    $snapshot = Initialize-ProductionSnapshot -Identity $identity -Is4000X ($Name -eq "installed-4000x")
    $initialInstalledOptions = @($snapshot.InstalledOptions)
    $unknownBeforeSystemStatus = $null -eq $snapshot.WgenApplicable
    Invoke-ProductionSystemStatus
    $applicability = [pscustomobject]@{
        Applicable = $snapshot.WgenApplicable
        Detail = $snapshot.WgenApplicabilityDetail
    }
    Invoke-Expression $wgenCode
    $wgenCommands = @($script:Invocations |
        Where-Object { $_.command -like "wgen-*" } |
        ForEach-Object { $_.command })
        Invoke-Expression $wgenModelCode
        $modelInvocations = @($script:Invocations |
            Where-Object { $_.stage -like "wgen-model-*" })
        $rampFunctionInvocations = @($modelInvocations | Where-Object {
            $_.stage -eq "wgen-model-function-ramp"
        })
        $outputOffQueryInvocations = @($modelInvocations | Where-Object {
            $_.stage -eq "wgen-model-output-off-query"
        })
        if ($Name -eq "installed-4000x") {
            if ($rampFunctionInvocations.Count -ne 1) {
                throw "Expected exactly one WGEN model ramp function invocation."
            }
            if ($outputOffQueryInvocations.Count -ne 1) {
                throw "Expected exactly one WGEN model output-off query invocation."
            }
        }
    if ($Name -eq "absent") {
        Invoke-Expression $demoCode
    }
    return [pscustomobject]@{
        applicability = $applicability
        initial_installed_options = $initialInstalledOptions
        installed_options = @($snapshot.InstalledOptions)
        wgen_applicable = $snapshot.WgenApplicable
        unknown_before_system_status = $unknownBeforeSystemStatus
        supports_wgen_absent = $null -eq $identity.capabilities.PSObject.Properties["supports_wgen"]
        system_status = [string]$script:CaseResults["system-status"].Status
        system_options_queries = @($script:Invocations |
            Where-Object { $_.command -eq "system-options" }).Count
        wgen_status = [string]$script:CaseResults["wgen-basic"].Status
        wgen_commands = $wgenCommands
        model_status = if ($script:CaseResults.Contains("wgen-model-validation")) {
            [string]$script:CaseResults["wgen-model-validation"].Status
        } else { "" }
        model_commands = @($modelInvocations | ForEach-Object { $_.command })
        model_stages = @($modelInvocations | ForEach-Object { $_.stage })
        model_output_on = @($modelInvocations | Where-Object {
            $_.command -eq "wgen-output" -and $_.arguments -contains "true"
        }).Count
            model_restore_amplitude = @($modelInvocations | Where-Object {
                $_.stage -eq "wgen-model-restore-amplitude"
            } | ForEach-Object { @($_.arguments) })
            model_ramp_function = if ($rampFunctionInvocations.Count -eq 1) {
                ,@($rampFunctionInvocations[0].arguments)
            } else {
                @()
            }
            model_output_off_query = if ($outputOffQueryInvocations.Count -eq 1) {
                ,@($outputOffQueryInvocations[0].arguments)
            } else {
                @()
            }
        demo_status = if ($script:CaseResults.Contains("demo-basic")) {
            [string]$script:CaseResults["demo-basic"].Status
        } else { "" }
        functional_failed = [bool]$script:FunctionalFailed
    }
}

[ordered]@{
    installed = Invoke-Scenario -Name "installed"
    installed_4000x = Invoke-Scenario -Name "installed-4000x"
    absent = Invoke-Scenario -Name "absent"
    runtime_failure = Invoke-Scenario -Name "runtime-failure"
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    installed = result["installed"]
    assert installed["applicability"]["Applicable"] is True
    assert installed["initial_installed_options"] == []
    assert installed["unknown_before_system_status"] is True
    assert installed["supports_wgen_absent"] is True
    assert installed["system_status"] == "PASS"
    assert installed["system_options_queries"] == 1
    assert installed["installed_options"] == ["WAVEGEN"]
    assert installed["wgen_applicable"] is True
    assert installed["wgen_status"] == "PASS"
    assert installed["wgen_commands"] == [
        "wgen-function",
        "wgen-frequency",
        "wgen-voltage",
        "wgen-offset",
        "wgen-load",
        "wgen-output",
        "wgen-query",
        "wgen-output",
    ]
    assert installed["functional_failed"] is False
    assert installed["model_status"] == "N/A"
    assert installed["model_commands"] == []
    assert installed["model_output_on"] == 0

    model4000x = result["installed_4000x"]
    assert model4000x["system_status"] == "PASS"
    assert model4000x["wgen_status"] == "PASS"
    assert model4000x["model_status"] == "PASS"
    assert model4000x["functional_failed"] is False
    assert model4000x["model_output_on"] == 0
    for stage in (
        "wgen-model-snapshot",
        "wgen-model-output-off",
        "wgen-model-output-off-query",
        "wgen-model-function-ramp",
        "wgen-model-frequency-200khz",
        "wgen-model-amplitude-15mv",
        "wgen-model-transition-before-query",
        "wgen-model-load-fifty-e",
        "wgen-model-transition-halved-query",
        "wgen-model-load-highz-restore-e",
        "wgen-model-transition-restored-query",
        "wgen-model-interaction-query",
        "wgen-model-restore-amplitude",
        "wgen-model-restore-off-query",
    ):
        assert stage in model4000x["model_stages"]
    assert model4000x["model_ramp_function"] == ["--function", "ramp"]
    assert model4000x["model_output_off_query"] == ["--query"]
    assert model4000x["model_restore_amplitude"] == ["--amplitude", "0.5"]
    stages = model4000x["model_stages"]
    assert stages.index("wgen-model-transition-before-query") < stages.index(
        "wgen-model-load-fifty-e"
    ) < stages.index("wgen-model-transition-halved-query") < stages.index(
        "wgen-model-load-highz-restore-e"
    ) < stages.index("wgen-model-transition-restored-query")

    absent = result["absent"]
    assert absent["applicability"]["Applicable"] is False
    assert "option is not installed" in absent["applicability"]["Detail"]
    assert absent["initial_installed_options"] == []
    assert absent["unknown_before_system_status"] is True
    assert absent["supports_wgen_absent"] is True
    assert absent["system_status"] == "PASS"
    assert absent["system_options_queries"] == 1
    assert absent["installed_options"] == ["BASIC"]
    assert absent["wgen_applicable"] is False
    assert absent["wgen_status"] == "N/A"
    assert absent["wgen_commands"] == []
    assert absent["demo_status"] == "PASS"
    assert absent["functional_failed"] is False
    assert absent["model_status"] == "N/A"
    assert absent["model_commands"] == []
    assert absent["model_output_on"] == 0

    runtime_failure = result["runtime_failure"]
    assert runtime_failure["applicability"]["Applicable"] is True
    assert runtime_failure["supports_wgen_absent"] is True
    assert runtime_failure["system_status"] == "PASS"
    assert runtime_failure["system_options_queries"] == 1
    assert runtime_failure["installed_options"] == ["WAVEGEN"]
    assert runtime_failure["wgen_applicable"] is True
    assert runtime_failure["wgen_status"] == "FAIL"
    assert runtime_failure["functional_failed"] is True
    assert runtime_failure["model_status"] == ""
    assert runtime_failure["model_commands"] == []


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_workflow_acquisition_run_precondition(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-workflow-check.ps1"
    harness_path = tmp_path / "workflow-acquisition-precondition-harness.ps1"
    harness_path.write_text(
        """\
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse workflow live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @("Get-RequiredResultValue", "Ensure-WorkflowAcquisitionRunning")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$script:OperationConditionRunMask = 8
$script:Invocations = New-Object System.Collections.Generic.List[object]

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,
        [Parameter(Mandatory = $true)]
        [string] $Command,
        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    if ($Command -eq "run") {
        return [pscustomobject]@{ ok = $true }
    }
    if ($Command -eq "system-operation-status") {
        return [pscustomobject]@{
            result = [pscustomobject]@{ value = 8 }
        }
    }
    throw "Unexpected live command: ${Command}"
}

# Case 1 - originally running: helper should return without invoking CLI
$script:Invocations.Clear()
$runningError = ""
try {
    Ensure-WorkflowAcquisitionRunning -WasRunning $true
} catch {
    $runningError = $_.Exception.Message
}
$runningCalls = @($script:Invocations | ForEach-Object {
    [ordered]@{ command = $_.command; arguments = @($_.arguments) }
})

# Case 2 - originally stopped: helper should issue run + status query
$script:Invocations.Clear()
$stoppedError = ""
try {
    Ensure-WorkflowAcquisitionRunning -WasRunning $false
} catch {
    $stoppedError = $_.Exception.Message
}
$stoppedCalls = @($script:Invocations | ForEach-Object {
    [ordered]@{ command = $_.command; arguments = @($_.arguments) }
})

[ordered]@{
    running_error = $runningError
    running_calls = @($runningCalls)
    running_count = $runningCalls.Count
    stopped_error = $stoppedError
    stopped_calls = @($stoppedCalls)
    stopped_count = $stoppedCalls.Count
} | ConvertTo-Json -Depth 8 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    # Case 1 - originally running: no CLI invocation
    assert result["running_error"] == ""
    assert result["running_count"] == 0
    assert result["running_calls"] == []

    # Case 2 - originally stopped: exactly run + status query
    assert result["stopped_error"] == ""
    assert result["stopped_count"] == 2
    assert result["stopped_calls"][0]["command"] == "run"
    assert result["stopped_calls"][0]["arguments"] == []
    assert result["stopped_calls"][1]["command"] == "system-operation-status"
    assert result["stopped_calls"][1]["arguments"] == ["--query"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_timebase_reference_restore_preserves_primary_failure(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "timebase-reference-restore-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Assert-NearlyEqual", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"timebase`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one timebase case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:Drains.Add($Stage)
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Stages.Add($Stage)
    $result = [ordered]@{}
    switch ($Stage) {
        "timebase-scale-query" { $result.seconds_per_division = 0.001 }
        "timebase-position-query" { $result.position_seconds = 0.0 }
        "timebase-reference-set" {
            if ($script:Scenario -eq "set-failure") {
                throw "reference set failure"
            }
        }
        "timebase-reference-query" {
            $result.reference = if ($script:Scenario -eq "primary-and-restore-failure") {
                "right"
            } else {
                "left"
            }
        }
        "timebase-reference-restore" {
            if ($script:Scenario -eq "primary-and-restore-failure") {
                throw "reference restore failure"
            }
        }
        "timebase-reference-restore-query" { $result.reference = "center" }
    }
    return [pscustomobject]@{ result = [pscustomobject]$result }
}

function Invoke-Scenario {
    param(
        [ValidateSet("success", "set-failure", "primary-and-restore-failure")]
        [string] $Name
    )
    $script:Scenario = $Name
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:Stages = New-Object System.Collections.Generic.List[string]
    $script:Drains = New-Object System.Collections.Generic.List[string]
    $snapshot = [pscustomobject]@{ TimebaseReference = "center" }
    Invoke-Expression $caseBlock
    $diagnostics = @(
        if ($script:Diagnostics.Contains("timebase")) {
            $script:Diagnostics["timebase"] | ForEach-Object { $_ }
        }
    )
    return [pscustomobject]@{
        passed = $script:CaseResults["timebase"].Passed
        detail = $script:CaseResults["timebase"].Detail
        stages = @($script:Stages | ForEach-Object { $_ })
        drains = @($script:Drains | ForEach-Object { $_ })
        diagnostics = $diagnostics
    }
}

[ordered]@{
    success = Invoke-Scenario -Name "success"
    set_failure = Invoke-Scenario -Name "set-failure"
    primary_and_restore_failure = Invoke-Scenario -Name "primary-and-restore-failure"
} | ConvertTo-Json -Depth 8 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    success = result["success"]
    assert success["passed"] is True, success["detail"]
    assert success["stages"][-2:] == [
        "timebase-reference-restore",
        "timebase-reference-restore-query",
    ]
    assert success["drains"] == []
    assert success["diagnostics"] == []

    set_failure = result["set_failure"]
    assert set_failure["passed"] is False
    assert "reference set failure" in set_failure["detail"]
    assert "timebase-reference-restore" not in set_failure["stages"]
    assert set_failure["drains"] == ["timebase-error-drain"]

    combined_failure = result["primary_and_restore_failure"]
    assert combined_failure["passed"] is False
    assert "Timebase reference readback does not match left" in combined_failure["detail"]
    assert "reference restore failure" not in combined_failure["detail"]
    assert combined_failure["stages"][-1] == "timebase-reference-restore"
    assert "timebase-reference-restore-query" not in combined_failure["stages"]
    assert combined_failure["drains"] == [
        "timebase-reference-restore-error-drain",
        "timebase-error-drain",
    ]
    assert combined_failure["diagnostics"] == [
        "timebase reference restore failed: reference restore failure"
    ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_cursor_lifecycle_preserves_primary_failure_during_cleanup(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "cursor-lifecycle-cleanup-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

$functionAst = $ast.Find({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq "Invoke-BaselineCase"
    )
}, $true)
if ($null -eq $functionAst) { throw "Missing Invoke-BaselineCase." }
Invoke-Expression $functionAst.Extent.Text

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"cursor-lifecycle`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one cursor-lifecycle case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Add-Diagnostic {
    param([string] $Name, [string] $Message)
    if (-not $script:Diagnostics.Contains($Name)) {
        $script:Diagnostics[$Name] = New-Object System.Collections.Generic.List[string]
    }
    $script:Diagnostics[$Name].Add($Message)
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:Events.Add("drain:${Stage}")
}

function Assert-ScpiSent {
    param([object] $Payload, [string[]] $ExpectedCommands, [string] $Label)
    if ($script:Scenario -eq "configure-assert-and-cleanup-fail" -and
        $Label -eq "Cursor baseline configure") {
        throw "cursor configure assertion failure"
    }
}

function Assert-NearlyEqual {
    param([double] $Actual, [double] $Expected, [string] $Label)
    $tolerance = [Math]::Max(1e-12, [Math]::Abs($Expected) * 1e-3)
    if ([Math]::Abs($Actual - $Expected) -gt $tolerance) {
        throw "${Label} readback ${Actual} does not match ${Expected}."
    }
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Events.Add($Stage)
    if ($script:Scenario -eq "configure-fail" -and $Stage -eq "cursor-set-baseline") {
        throw "cursor configure primary failure"
    }
    if ($script:Scenario -eq "query-and-cleanup-fail" -and
        $Stage -eq "cursor-query-baseline") {
        throw "cursor query primary failure"
    }
    if ($script:Scenario -in @(
            "query-and-cleanup-fail",
            "cleanup-only-fail",
            "configure-assert-and-cleanup-fail"
        ) -and
        $Stage -eq "cursor-off") {
        throw "cursor cleanup failure"
    }
    $mode = if ($Stage -eq "cursor-off-query") { "off" } else { "manual" }
    $y2 = if ($Stage -in @("cursor-set-y2-partial", "cursor-query-y2-partial")) { 0.25 } else { 0.5 }
    return [pscustomobject]@{
        result = [pscustomobject]@{
            mode = $mode
            x1_seconds = 0.0005
            x2_seconds = 0.001
            y1_volts = 0
            y2_volts = $y2
        }
        scpi = [pscustomobject]@{ sent = @() }
    }
}

function Invoke-Scenario {
    param([string] $Name)
    $script:Scenario = $Name
    $script:CaseResults = [ordered]@{}
    $script:Diagnostics = [ordered]@{}
    $script:FunctionalFailed = $false
    $script:Events = New-Object System.Collections.Generic.List[string]
    Invoke-Expression $caseBlock
    return [pscustomobject]@{
        passed = $script:CaseResults["cursor-lifecycle"].Passed
        detail = $script:CaseResults["cursor-lifecycle"].Detail
        diagnostics = @(
            if ($script:Diagnostics.Contains("cursor-lifecycle")) {
                $script:Diagnostics["cursor-lifecycle"] | ForEach-Object { [string]$_ }
            }
        )
        events = @($script:Events | ForEach-Object { $_ })
    }
}

[ordered]@{
    query_and_cleanup_fail = Invoke-Scenario -Name "query-and-cleanup-fail"
    cleanup_only_fail = Invoke-Scenario -Name "cleanup-only-fail"
    configure_fail = Invoke-Scenario -Name "configure-fail"
    configure_assert_and_cleanup_fail = Invoke-Scenario `
        -Name "configure-assert-and-cleanup-fail"
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    combined = result["query_and_cleanup_fail"]
    assert combined["passed"] is False
    assert "cursor query primary failure" in combined["detail"]
    assert "cursor cleanup failure" not in combined["detail"]
    assert any("cursor cleanup failure" in item for item in combined["diagnostics"])
    assert combined["events"] == [
        "cursor-set-baseline",
        "cursor-query-baseline",
        "drain:cursor-primary-error-drain",
        "cursor-off",
        "cursor-off-query",
        "drain:cursor-lifecycle-error-drain",
    ]

    cleanup_only = result["cleanup_only_fail"]
    assert cleanup_only["passed"] is False
    assert "cursor cleanup failure" in cleanup_only["detail"]
    assert cleanup_only["events"] == [
        "cursor-set-baseline",
        "cursor-query-baseline",
        "cursor-set-x1-partial",
        "cursor-query-x1-partial",
        "cursor-set-y2-partial",
        "cursor-query-y2-partial",
        "cursor-off",
        "cursor-off-query",
        "drain:cursor-lifecycle-error-drain",
    ]

    configure = result["configure_fail"]
    assert configure["passed"] is False
    assert "cursor configure primary failure" in configure["detail"]
    assert configure["events"] == [
        "cursor-set-baseline",
        "drain:cursor-lifecycle-error-drain",
    ]

    configure_assert = result["configure_assert_and_cleanup_fail"]
    assert configure_assert["passed"] is False
    assert "cursor configure assertion failure" in configure_assert["detail"]
    assert "cursor cleanup failure" not in configure_assert["detail"]
    assert any(
        "cursor cleanup failure" in item
        for item in configure_assert["diagnostics"]
    )
    assert configure_assert["events"] == [
        "cursor-set-baseline",
        "drain:cursor-primary-error-drain",
        "cursor-off",
        "cursor-off-query",
        "drain:cursor-lifecycle-error-drain",
    ]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_fft_accepts_documented_hann_readback_and_rejects_other_window(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-fft-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-CaseResult", "Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"fft`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) { throw "Expected one fft case." }
$caseBlock = $matchingCommands[0].Extent.Text

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{ Passed = $Passed; Detail = $Detail }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    if ($Stage -eq "fft-set") {
        return [pscustomobject]@{
            scpi = [pscustomobject]@{ sent = @(
                ":FUNCtion1:OPERation FFT",
                ":FUNCtion1:SOURce1 CHANnel1",
                ":FUNCtion1:FFT:WINDow HANNing"
            ) }
            result = [pscustomobject]@{}
        }
    }
    if ($Stage -eq "fft-query") {
        return [pscustomobject]@{
            scpi = [pscustomobject]@{ sent = @(
                ":FUNCtion1:OPERation?",
                ":FUNCtion1:SOURce1?",
                ":FUNCtion1:FFT:WINDow?"
            ) }
            result = [pscustomobject]@{
                fft_operation_canonical = "fft"
                source_channel = 1
                window = $script:FftWindow
            }
        }
    }
    if ($Stage -eq "fft-display-off") {
        $script:FftCleanupCalls += 1
        return [pscustomobject]@{
            scpi = [pscustomobject]@{ sent = @(":FUNCtion1:DISPlay OFF") }
            result = [pscustomobject]@{}
        }
    }
    throw "Unexpected stage: ${Stage}"
}

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:FftCleanupCalls = 0
$script:FftWindow = "HANN"
$identity = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        math_function_count = 4
    }
}
Invoke-Expression $caseBlock
$pass = $script:CaseResults["fft"].Passed
$passFailed = $script:FunctionalFailed
$pass_cleanup_calls = $script:FftCleanupCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:FftCleanupCalls = 0
$script:FftWindow = "FLAT"
Invoke-Expression $caseBlock

[ordered]@{
    pass = $pass
    pass_failed = $passFailed
    pass_cleanup_calls = $pass_cleanup_calls
    failure_passed = $script:CaseResults["fft"].Passed
    failure_detail = $script:CaseResults["fft"].Detail
    failure_functional_failed = $script:FunctionalFailed
    failure_drain_calls = $script:DrainCalls
} | ConvertTo-Json -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass"] is True
    assert result["pass_failed"] is False
    assert result["pass_cleanup_calls"] == 1
    assert result["failure_passed"] is False
    assert "FFT readback is invalid" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_live_validator_holdoff_series_gating(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "holdoff-series-gating-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "ConvertTo-InvariantString",
    "Assert-ScpiSent",
    "Assert-NearlyEqual",
    "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"trigger-holdoff`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one trigger-holdoff case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$snapshot = [pscustomobject]@{ TriggerHoldoffSeconds = 0.000002 }
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:ConfigureScpi = @(
    ":TRIGger:HOLDoff:RANDom OFF",
    ":TRIGger:HOLDoff 1e-6"
)
$is4000XSeries = $true

function Add-CaseResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [bool] $Passed,

        [string] $Detail = ""
    )

    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )

    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    switch ($Stage) {
        "trigger-holdoff-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $script:ConfigureScpi }
            }
        }
        "trigger-holdoff-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":TRIGger:HOLDoff?") }
                result = [pscustomobject]@{ seconds = 0.000001 }
            }
        }
        "trigger-holdoff-restore" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":TRIGger:HOLDoff 2e-6") }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
}

Invoke-Expression $caseBlock
$series4000XResult = $script:CaseResults["trigger-holdoff"].Passed
$series4000XFunctionalFailed = $script:FunctionalFailed
$series4000XDrainCalls = $script:DrainCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:ConfigureScpi = @(":TRIGger:HOLDoff 1e-6")
$is4000XSeries = $false
Invoke-Expression $caseBlock

[ordered]@{
    series_4000x_result = $series4000XResult
    series_4000x_functional_failed = $series4000XFunctionalFailed
    series_4000x_drain_calls = $series4000XDrainCalls
    non_4000x_result = $script:CaseResults["trigger-holdoff"].Passed
    non_4000x_functional_failed = $script:FunctionalFailed
    non_4000x_drain_calls = $script:DrainCalls
} | ConvertTo-Json -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["series_4000x_result"] is True
    assert result["series_4000x_functional_failed"] is False
    assert result["series_4000x_drain_calls"] == 0
    assert result["non_4000x_result"] is True
    assert result["non_4000x_functional_failed"] is False
    assert result["non_4000x_drain_calls"] == 0


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_channel_vertical_rejects_payload_self_oracle(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-channel-vertical-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @(
    "ConvertTo-InvariantString",
    "Assert-ScpiSent",
    "Assert-NearlyEqual",
    "Invoke-BaselineCase"
)) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"channel-vertical`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one channel-vertical case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$script:snapshot = [pscustomobject]@{
    ChannelLabel = "Input a"
    ChannelScale = 0.5
    ChannelRange = 4.0
    ChannelOffset = 0.0
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:WrongScalePath = $false

function Add-CaseResult {
    param([string] $Name, [bool] $Passed, [string] $Detail = "")
    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch ($Stage) {
        "channel-label-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(':CHANnel1:LABel "Input a"') }
                result = [pscustomobject]@{ command = ':CHANnel1:LABel "Input a"' }
            }
        }
        "channel-label-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:LABel?") }
                result = [pscustomobject]@{ text = "Input a" }
            }
        }
        "channel-vertical-scale-set" {
            $commandText = if ($script:WrongScalePath) {
                ":CHANnel1:OFFSet 2"
            } else {
                ":CHANnel1:SCALe 2"
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @($commandText) }
                result = [pscustomobject]@{ command = $commandText }
            }
        }
        "channel-vertical-scale-query" {
            $scale = if ($script:WrongScalePath) { 0.5 } else { 2.0 }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:SCALe?") }
                result = [pscustomobject]@{ volts_per_division = $scale }
            }
        }
        "channel-range-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:RANGe 4") }
                result = [pscustomobject]@{ command = ":CHANnel1:RANGe 4" }
            }
        }
        "channel-range-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:RANGe?") }
                result = [pscustomobject]@{ range_volts = 4.0 }
            }
        }
        "channel-vertical-offset-set" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:OFFSet 0") }
                result = [pscustomobject]@{ command = ":CHANnel1:OFFSet 0" }
            }
        }
        "channel-vertical-offset-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":CHANnel1:OFFSet?") }
                result = [pscustomobject]@{ volts = 0.0 }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
}

Invoke-Expression $caseBlock
$passResult = $script:CaseResults["channel-vertical"].Passed
$passFunctionalFailed = $script:FunctionalFailed
$passDrainCalls = $script:DrainCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations.Clear()
$script:WrongScalePath = $true
Invoke-Expression $caseBlock

[ordered]@{
    pass_result = $passResult
    pass_functional_failed = $passFunctionalFailed
    pass_drain_calls = $passDrainCalls
    failure_passed = $script:CaseResults["channel-vertical"].Passed
    failure_detail = $script:CaseResults["channel-vertical"].Detail
    failure_functional_failed = $script:FunctionalFailed
    failure_drain_calls = $script:DrainCalls
    failure_stages = @($script:Invocations | ForEach-Object { $_.stage })
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_result"] is True
    assert result["pass_functional_failed"] is False
    assert result["pass_drain_calls"] == 0
    assert result["failure_passed"] is False
    assert "CH1 scale SCPI path" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1
    assert "channel-vertical-scale-query" in result["failure_stages"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_acquisition_queries_validate_payloads_and_scpi_history(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-acquisition-harness.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath,
    [ref] $tokens,
    [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) {
    throw "Failed to parse live script: $($parseErrors[0].Message)"
}

foreach ($functionName in @("Assert-FiniteNumber", "Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) {
        throw "${functionName} was not found in ${ScriptPath}."
    }
    Invoke-Expression $functionAst.Extent.Text
}

$matchingCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains("-Name `"acquisition-queries`"")
    )
}, $true))
if ($matchingCommands.Count -ne 1) {
    throw "Expected one acquisition-queries case in ${ScriptPath}."
}
$caseBlock = $matchingCommands[0].Extent.Text

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:EmptySampleRateHistory = $false
$is4000XSeries = $true

function Add-CaseResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [bool] $Passed,

        [string] $Detail = ""
    )

    $script:CaseResults[$Name] = [pscustomobject]@{
        Passed = $Passed
        Detail = $Detail
    }
}

function Drain-AfterFailure {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $CaseName
    )

    $script:DrainCalls += 1
}

function Invoke-LiveCli {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage,

        [Parameter(Mandatory = $true)]
        [string] $Command,

        [string[]] $Arguments = @()
    )

    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })

    switch ($Stage) {
        "sample-rate-query" {
            if ($script:EmptySampleRateHistory) {
                return [pscustomobject]@{
                    scpi = [pscustomobject]@{ sent = @() }
                    result = [pscustomobject]@{ sample_rate_hz = 5000000000.0 }
                }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*IDN?", ":ACQuire:SRATe?") }
                result = [pscustomobject]@{ sample_rate_hz = 5000000000.0 }
            }
        }
        "acquisition-points-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*IDN?", ":ACQuire:POINts?") }
                result = [pscustomobject]@{ acquisition_points = 1000000 }
            }
        }
        "record-length-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @("*IDN?", ":ACQuire:RLENgth?") }
                result = [pscustomobject]@{ record_length_points = 65536 }
            }
        }
        default {
            throw "Unexpected stage: ${Stage}"
        }
    }
}

Invoke-Expression $caseBlock
$passResult = $script:CaseResults["acquisition-queries"].Passed
$passInvocations = @($script:Invocations | ForEach-Object { $_ })
$passFunctionalFailed = $script:FunctionalFailed

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:EmptySampleRateHistory = $true
$is4000XSeries = $true
Invoke-Expression $caseBlock
$failurePassed = $script:CaseResults["acquisition-queries"].Passed
$failureDetail = $script:CaseResults["acquisition-queries"].Detail
$failureFunctionalFailed = $script:FunctionalFailed
$failureDrainCalls = $script:DrainCalls

$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:DrainCalls = 0
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:EmptySampleRateHistory = $false
$is4000XSeries = $false
Invoke-Expression $caseBlock

[ordered]@{
    pass_result = $passResult
    pass_functional_failed = $passFunctionalFailed
    pass_invocations = $passInvocations
    failure_passed = $failurePassed
    failure_detail = $failureDetail
    failure_functional_failed = $failureFunctionalFailed
    failure_drain_calls = $failureDrainCalls
    non_4000x_result = $script:CaseResults["acquisition-queries"].Passed
    non_4000x_functional_failed = $script:FunctionalFailed
    non_4000x_invocations = @($script:Invocations | ForEach-Object { $_ })
} | ConvertTo-Json -Depth 12 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["pass_result"] is True
    assert result["pass_functional_failed"] is False
    invocations = result["pass_invocations"]
    assert [entry["command"] for entry in invocations] == [
        "sample-rate",
        "acquisition-points",
        "record-length",
    ]
    assert all(entry["arguments"] == ["--query"] for entry in invocations)
    assert result["failure_passed"] is False
    assert "empty SCPI history" in result["failure_detail"]
    assert result["failure_functional_failed"] is True
    assert result["failure_drain_calls"] == 1
    assert result["non_4000x_result"] is True
    assert result["non_4000x_functional_failed"] is False
    non_4000x_invocations = result["non_4000x_invocations"]
    assert [entry["command"] for entry in non_4000x_invocations] == [
        "sample-rate",
        "acquisition-points",
    ]
    assert all(
        entry["arguments"] == ["--query"] for entry in non_4000x_invocations
    )
    assert "record-length" not in {
        entry["command"] for entry in non_4000x_invocations
    }


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_diagnostic_drain_ignores_empty_error_collection(
    tmp_path: Path,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-empty-diagnostic-drain-harness.ps1"
    harness_path.write_text(
        r'''
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-Diagnostic", "Drain-AfterFailure")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$script:Diagnostics = [ordered]@{}

function Get-ErrorDrain {
    param([string] $Stage)
    return [pscustomobject]@{
        Errors = @()
        Terminated = $true
    }
}

function Write-DrainErrors {
    throw "Write-DrainErrors must not be called for an empty error collection."
}

Drain-AfterFailure -Stage "empty-error-drain" -CaseName "cleanup"

[ordered]@{
    diagnostic_count = $script:Diagnostics.Count
    diagnostics = @(
        $script:Diagnostics.Values |
            ForEach-Object { $_ } |
            ForEach-Object { [string]$_ }
    )
} | ConvertTo-Json -Depth 6 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["diagnostic_count"] == 0
    assert result["diagnostics"] == []


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_search_basic_and_event_execution(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-search-harness.ps1"
    harness_path.write_text(
        r"""
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-CaseResult", "Assert-ScpiSent", "Invoke-BaselineCase")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$searchBasicCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "search-basic"')
    )
}, $true))
if ($searchBasicCommands.Count -ne 1) {
    throw "Expected one search-basic case in ${ScriptPath}."
}
$searchBasicCode = $searchBasicCommands[0].Extent.Text

$searchEventCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "search-event"')
    )
}, $true))
if ($searchEventCommands.Count -ne 1) {
    throw "Expected one search-event case in ${ScriptPath}."
}
$searchEventCode = $searchEventCommands[0].Extent.Text

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0
$script:SearchCount = 3
$script:SimulateFailure = $false

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch -Regex ($Stage) {
        "^search-state-enable$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 1") }
                result = [pscustomobject]@{ enabled = $true }
            }
        }
        "^search-state-query$" {
            if ($script:SimulateFailure) {
                return [pscustomobject]@{
                    scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                    result = [pscustomobject]@{ enabled = $false }
                }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                result = [pscustomobject]@{ enabled = $true }
            }
        }
        "^search-mode-(.*)-set$" {
            $mode = $Matches[1]
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 1", ":SEARch:MODE $($mode.ToUpperInvariant())") }
                result = [pscustomobject]@{ mode = $mode; enabled = $true }
            }
        }
        "^search-mode-(.*)-query$" {
            $mode = $Matches[1]
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:MODE?") }
                result = [pscustomobject]@{ mode = $mode; enabled = $true }
            }
        }
        "^search-count-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:COUNt?") }
                result = [pscustomobject]@{ count = [int64]$script:SearchCount }
            }
        }
        "^search-state-disable$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 0") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        "^search-state-disable-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        "^search-event-enable$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 1") }
                result = [pscustomobject]@{ enabled = $true }
            }
        }
        "^search-event-mode-edge$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:MODE EDGE") }
                result = [pscustomobject]@{ mode = "edge"; enabled = $true }
            }
        }
        "^search-event-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:EVENt?") }
                result = [pscustomobject]@{ event = [int64]1 }
            }
        }
        "^search-event-count-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:COUNt?") }
                result = [pscustomobject]@{ count = [int64]$script:SearchCount }
            }
        }
        "^search-event-set$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:EVENt 1") }
                result = [pscustomobject]@{ event = [int64]1 }
            }
        }
        "^search-event-readback$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:EVENt?") }
                result = [pscustomobject]@{ event = [int64]1 }
            }
        }
        "^search-event-cleanup$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe 0") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        "^search-event-cleanup-query$" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":SEARch:STATe?") }
                result = [pscustomobject]@{ enabled = $false }
            }
        }
        default {
            throw "Unexpected stage in test harness: $Stage"
        }
    }
}

function Run-SearchSection {
    param($Identity)
    $supportsEdgeSearch = "edge" -in @($Identity.capabilities.search_modes)
    if (-not $script:FunctionalFailed -and [bool]$Identity.capabilities.supports_search_basic -and $supportsEdgeSearch) {
        Invoke-Expression $searchBasicCode
    }
    if (-not $script:FunctionalFailed -and [bool]$Identity.capabilities.supports_search_event_navigation) {
        Invoke-Expression $searchEventCode
    }
}

# Run 1: 4000X capabilities, count > 0 (normal pass)
$identity4000x = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        supports_search_basic = $true
        supports_search_event_navigation = $true
        search_modes = @("edge", "glitch", "runt", "transition", "serial1", "serial2", "peak")
    }
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SearchCount = 3
Run-SearchSection -Identity $identity4000x
$pass4000xResults = [ordered]@{}
foreach ($k in $script:CaseResults.Keys) {
    $pass4000xResults[$k] = $script:CaseResults[$k].Passed
}
$pass4000xInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 2: 4000X capabilities, count == 0 (query only, skips event-set)
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SearchCount = 0
Run-SearchSection -Identity $identity4000x
$zeroHit4000xResults = [ordered]@{}
foreach ($k in $script:CaseResults.Keys) {
    $zeroHit4000xResults[$k] = $script:CaseResults[$k].Passed
}
$zeroHit4000xInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 3: 2000X capabilities (search_modes only serial1, no edge)
$identity2000x = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        supports_search_basic = $true
        supports_search_event_navigation = $false
        search_modes = @("serial1")
    }
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
Run-SearchSection -Identity $identity2000x
$pass2000xResults = [ordered]@{}
foreach ($k in $script:CaseResults.Keys) {
    $pass2000xResults[$k] = $script:CaseResults[$k].Passed
}
$pass2000xInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 4: Failure path
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SimulateFailure = $true
Run-SearchSection -Identity $identity4000x

[ordered]@{
    pass4000x_results = $pass4000xResults
    pass4000x_invocations = $pass4000xInvocations
    zero_hit_results = $zeroHit4000xResults
    zero_hit_invocations = $zeroHit4000xInvocations
    pass2000x_results = $pass2000xResults
    pass2000x_invocations = $pass2000xInvocations
    fail_passed = $script:CaseResults["search-basic"].Passed
    fail_functional_failed = $script:FunctionalFailed
} | ConvertTo-Json -Depth 10 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout.strip().splitlines()[-1])

    # 4000X normal pass
    assert data["pass4000x_results"]["search-basic"] is True
    assert data["pass4000x_results"]["search-event"] is True
    stages_4000x = [entry["stage"] for entry in data["pass4000x_invocations"]]
    assert "search-state-enable" in stages_4000x
    assert "search-mode-edge-set" in stages_4000x
    assert "search-mode-glitch-set" in stages_4000x
    assert "search-mode-runt-set" in stages_4000x
    assert "search-mode-transition-set" in stages_4000x
    assert "search-mode-peak-set" in stages_4000x
    assert "search-count-query" in stages_4000x
    assert "search-state-disable" in stages_4000x
    assert "search-event-set" in stages_4000x
    assert "search-event-cleanup" in stages_4000x
    assert "search-event-cleanup-query" in stages_4000x

    # 4000X count == 0 skips search-event-set
    assert data["zero_hit_results"]["search-basic"] is True
    assert data["zero_hit_results"]["search-event"] is True
    stages_zero = [entry["stage"] for entry in data["zero_hit_invocations"]]
    assert "search-event-query" in stages_zero
    assert "search-event-count-query" in stages_zero
    assert "search-event-set" not in stages_zero
    assert "search-event-cleanup" in stages_zero
    assert "search-event-cleanup-query" in stages_zero

    # 2000X N/A: neither case runs
    assert "search-basic" not in data["pass2000x_results"]
    assert "search-event" not in data["pass2000x_results"]
    assert len(data["pass2000x_invocations"]) == 0

    # Failure simulation
    assert data["fail_passed"] is False
    assert data["fail_functional_failed"] is True


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
def test_baseline_annotation_execution_and_cleanup(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / "baseline-annotation-harness.ps1"
    harness_path.write_text(
        r"""
param([Parameter(Mandatory = $true)][string] $ScriptPath)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($functionName in @("Add-CaseResult", "Assert-ScpiSent", "Invoke-BaselineCase", "Restore-InstrumentState", "ConvertTo-InvariantString", "Assert-NearlyEqual")) {
    $functionAst = $ast.Find({
        param($node)
        return (
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq $functionName
        )
    }, $true)
    if ($null -eq $functionAst) { throw "Missing ${functionName}." }
    Invoke-Expression $functionAst.Extent.Text
}

$annotationCommands = @($ast.FindAll({
    param($node)
    return (
        $node -is [System.Management.Automation.Language.CommandAst] -and
        $node.GetCommandName() -eq "Invoke-BaselineCase" -and
        $node.Extent.Text.Contains('-Name "display-annotation"')
    )
}, $true))
if ($annotationCommands.Count -ne 1) {
    throw "Expected one display-annotation case in ${ScriptPath}."
}
$annotationCode = $annotationCommands[0].Extent.Text

function Drain-AfterFailure {
    param([string] $Stage, [string] $CaseName)
    $script:DrainCalls += 1
}

$script:SaveFixtureEstablished = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:DrainCalls = 0
$script:SimulateFailure = $false

function Invoke-LiveCli {
    param([string] $Stage, [string] $Command, [string[]] $Arguments = @())
    $script:Invocations.Add([pscustomobject]@{
        stage = $Stage
        command = $Command
        arguments = @($Arguments)
    })
    switch -Regex ($Stage) {
        "^annotation-set$" {
            $cmds = @(':DISPlay:ANNotation1:TEXT "Live note"', ":DISPlay:ANNotation1 ON")
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $cmds }
                result = [pscustomobject]@{ commands = $cmds }
            }
        }
        "^annotation-query$" {
            $cmds = @(
                ":DISPlay:ANNotation1?",
                ":DISPlay:ANNotation1:TEXT?",
                ":DISPlay:ANNotation1:COLor?",
                ":DISPlay:ANNotation1:BACKground?",
                ":DISPlay:ANNotation1:X1Position?",
                ":DISPlay:ANNotation1:Y1Position?"
            )
            if ($script:SimulateFailure) {
                return [pscustomobject]@{
                    scpi = [pscustomobject]@{ sent = $cmds }
                    result = [pscustomobject]@{ commands = $cmds; enabled = $false; text = "wrong"; slot = 1; color = "WHITE"; background = "OPAQ"; x = 20; y = 30 }
                }
            }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = $cmds }
                result = [pscustomobject]@{ commands = $cmds; enabled = $true; text = "Live note"; slot = 1; color = "WHITE"; background = "OPAQ"; x = 20; y = 30 }
            }
        }
        "^restore-channel-summary-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ channels = @(
                [pscustomobject]@{
                    label = "Original"
                    scale = 1.0
                    range = 8.0
                    offset = 0.0
                    bandwidth_limit = $false
                    impedance = "one_meg"
                    invert = $false
                    units = "volt"
                    vernier = $false
                    probe_ratio = 10.0
                    probe_skew = 0.0
                }
            ) } }
        }
        "^restore-display-label-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ display_label = $true } }
        }
        "^restore-display-persistence-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ mode = "minimum"; seconds = $null } }
        }
        "^restore-display-intensity-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ value = 50 } }
        }
        "^restore-display-vectors-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ value = $true } }
        }
        "^restore-timebase-reference-query$" {
            return [pscustomobject]@{ result = [pscustomobject]@{ reference = "center" } }
        }
        "^restore-annotation-query$" {
            return [pscustomobject]@{
                result = [pscustomobject]@{ enabled = $false; text = ""; color = "WHITE"; background = "OPAQ"; x = 20; y = 30 }
            }
        }
        default {
            return [pscustomobject]@{ result = [pscustomobject]@{} }
        }
    }
}

# Run 1: Annotation supported, executes display-annotation
$identity = [pscustomobject]@{
    capabilities = [pscustomobject]@{
        supports_annotation = $true
    }
}
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()

if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_annotation) {
    Invoke-Expression $annotationCode
}
$passResult = $script:CaseResults["display-annotation"].Passed
$passInvocations = @($script:Invocations | ForEach-Object { $_ })

# Run 2: Annotation failure
$script:CaseResults = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations.Clear()
$script:SimulateFailure = $true
if (-not $script:FunctionalFailed -and [bool]$identity.capabilities.supports_annotation) {
    Invoke-Expression $annotationCode
}
$failResult = $script:CaseResults["display-annotation"].Passed
$failFunctionalFailed = $script:FunctionalFailed

# Run 3: Restore when not restorable but supported (safe baseline --slot 1 --off --clear)
$script:Invocations.Clear()
$nonRestorableSnapshot = [pscustomobject]@{
    ChannelProbeSkew = 0.0
    ChannelVernier = $false
    ChannelUnits = "volt"
    ChannelInvert = $false
    ChannelImpedance = "one_meg"
    ChannelBandwidthLimit = $false
    ChannelProbeRatio = 10.0
    ChannelRange = 8.0
    ChannelScale = 1.0
    ChannelOffset = 0.0
    ChannelLabel = "Original"
    DisplayIntensity = 50
    DisplayPersistenceSeconds = $null
    DisplayPersistenceMode = "minimum"
    DisplayLabels = $true
    TriggerLevel = 0.0
    TriggerSlope = "negative"
    TriggerSource = "analog-channel"
    TriggerSourceChannel = 2
    TimebasePosition = 0.0
    TimebaseScale = 0.001
    TimebaseReference = "center"
    ChannelCoupling = "dc"
    ChannelDisplay = $true
    AcquisitionType = "normal"
    AcquisitionCount = 1
    DisplayVectors = $true
    AnnotationRestorable = $false
    AnnotationSupported = $true
}
Restore-InstrumentState -Snapshot $nonRestorableSnapshot
$nonRestorableRestoreInvocations = @($script:Invocations | ForEach-Object { $_ })

[ordered]@{
    pass_result = $passResult
    pass_invocations = $passInvocations
    fail_result = $failResult
    fail_functional_failed = $failFunctionalFailed
    non_restorable_restore_invocations = $nonRestorableRestoreInvocations
} | ConvertTo-Json -Depth 10 -Compress
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    data = json.loads(completed.stdout.strip().splitlines()[-1])
    assert data["pass_result"] is True
    stages = [entry["stage"] for entry in data["pass_invocations"]]
    assert "annotation-set" in stages
    assert "annotation-query" in stages

    assert data["fail_result"] is False
    assert data["fail_functional_failed"] is True

    restore_commands = [entry for entry in data["non_restorable_restore_invocations"] if entry["command"] == "annotation"]
    assert len(restore_commands) >= 1
    assert restore_commands[0]["arguments"] == ["--slot", "1", "--off", "--clear"]


@pytest.mark.skipif(os.name != "nt", reason="requires Windows PowerShell")
@pytest.mark.parametrize(
    ("series", "installed_options", "expected_transform_status", "expected_transform_operation", "expected_filter_status", "expected_visualization_status"),
    [
        (
            "2000X",
            "BW20",
            "N/A",
            "",
            "N/A",
            "N/A",
        ),
        (
            "3000X",
            "BW20",
            "PASS",
            "differentiate",
            "N/A",
            "N/A",
        ),
    ],
    ids=["2000X_no_plus", "3000X_no_advmath"],
)
def test_live_cli_math_option_applicability_runtime(
    tmp_path: Path,
    series: str,
    installed_options: str,
    expected_transform_status: str,
    expected_transform_operation: str,
    expected_filter_status: str,
    expected_visualization_status: str,
) -> None:
    script_path = REPO_ROOT / "scripts" / "live-cli-check.ps1"
    harness_path = tmp_path / f"math-option-{series}.ps1"
    harness_path.write_text(
        r'''
param(
    [Parameter(Mandatory = $true)]
    [string] $ScriptPath,
    [Parameter(Mandatory = $true)]
    [string] $Series,
    [Parameter(Mandatory = $true)]
    [string] $InstalledOptionsCsv
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $ScriptPath, [ref] $tokens, [ref] $parseErrors
)
if ($parseErrors.Count -ne 0) { throw $parseErrors[0].Message }

foreach ($fn in @("Add-CaseResult", "Add-NotApplicableCase", "Add-Diagnostic", "Assert-ScpiSent", "Assert-ScpiSentPrefix", "Invoke-BaselineCase", "Assert-FiniteNumber", "ConvertTo-InvariantString", "Assert-NearlyEqual")) {
    $fa = $ast.Find({
        param($node)
        return ($node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $fn)
    }, $true)
    if ($null -ne $fa) { Invoke-Expression $fa.Extent.Text }
}

# Provide lightweight stubs where production helpers are not needed to load.
if (-not (Get-Command Assert-ScpiSent -ErrorAction SilentlyContinue)) {
    function Assert-ScpiSent { param($Payload,$Label,$ExpectedCommands) }
}
if (-not (Get-Command Assert-ScpiSentPrefix -ErrorAction SilentlyContinue)) {
    function Assert-ScpiSentPrefix { param($Payload,$Label,$ExpectedPrefix) }
}
if (-not (Get-Command Assert-FiniteNumber -ErrorAction SilentlyContinue)) {
    function Assert-FiniteNumber { param($Value,$Label) return [double]$Value }
}
if (-not (Get-Command Add-Diagnostic -ErrorAction SilentlyContinue)) {
    function Add-Diagnostic { param($Name,$Message) }
}
if (-not (Get-Command ConvertTo-InvariantString -ErrorAction SilentlyContinue)) {
    function ConvertTo-InvariantString { param([double]$Value) return $Value.ToString("R", [System.Globalization.CultureInfo]::InvariantCulture) }
}
if (-not (Get-Command Assert-NearlyEqual -ErrorAction SilentlyContinue)) {
    function Assert-NearlyEqual { param([double]$Actual,[double]$Expected,[string]$Label) }
}
function Drain-AfterFailure { param($Stage,$CaseName) }

$script:CaseResults = [ordered]@{}
$script:Diagnostics = [ordered]@{}
$script:FunctionalFailed = $false
$script:Invocations = New-Object System.Collections.Generic.List[object]
$script:LastTransformOperation = $null
$script:LastFilterOperation = $null
$script:LastVisualizationOperation = $null
$script:LastVerticalScale = $null
$script:LastVerticalOffset = $null
$script:BaselineVerticalScale = 250000
$script:BaselineVerticalOffset = 0

$installedOptions = @()
if (-not [string]::IsNullOrWhiteSpace($InstalledOptionsCsv)) {
    $installedOptions = @($InstalledOptionsCsv -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" })
}

$identity = [pscustomobject]@{
    idn = [pscustomobject]@{ series = $Series }
    capabilities = [pscustomobject]@{
        series = $Series
        math_function_count = 1
        math_filter_operations = @("low-pass", "high-pass")
        math_visualization_operations = @("magnify", "trend")
        supports_math_goft = $true
        supports_measurements = $true
        supports_demo = $false
    }
}
$is2000XSeries = [string]$identity.idn.series -eq "2000X"
$is3000XSeries = [string]$identity.idn.series -eq "3000X"
$is4000XSeries = [string]$identity.idn.series -eq "4000X"
$snapshot = [pscustomobject]@{
    Is4000XSeries = $is4000XSeries
    MathEnhancementsInstalled = $false
    AdvancedMathInstalled = $false
    InstalledOptions = @($installedOptions)
    WgenApplicable = $null
    WgenApplicabilityDetail = ""
    MathFunctionCount = 1
}
# Use production option applicability assignments instead of duplicating logic
$plusAssignmentNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if ($is2000XSeries)') -and $txt.Contains('$snapshot.MathEnhancementsInstalled = "PLUS"')
}, $true))
$advmAssignmentNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if ($is3000XSeries)') -and $txt.Contains('$snapshot.AdvancedMathInstalled = "ADVMATH"')
}, $true))
if ($plusAssignmentNodes.Count -ne 1) { throw "Expected 1 PLUS assignment, found $($plusAssignmentNodes.Count)" }
if ($advmAssignmentNodes.Count -ne 1) { throw "Expected 1 ADVMATH assignment, found $($advmAssignmentNodes.Count)" }
Invoke-Expression $plusAssignmentNodes[0].Extent.Text
Invoke-Expression $advmAssignmentNodes[0].Extent.Text

# Override baseline helpers to capture runtime behavior without real hardware.
function Add-CaseResult {
    param([string]$Name,[bool]$Passed,[string]$Detail="")
    $s = if ($Passed) { "PASS" } else { "FAIL" }
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = $s; Detail = $Detail; Passed = $Passed }
}
function Add-NotApplicableCase {
    param([string]$Name,[string]$Detail)
    $script:CaseResults[$Name] = [pscustomobject]@{ Status = "N/A"; Detail = $Detail; Passed = $false }
    $script:Invocations.Add([pscustomobject]@{ stage = "N/A"; command = "Add-NotApplicableCase"; arguments = @($Name, $Detail) })
}
function Invoke-BaselineCase {
    param([string]$Name,[scriptblock]$Action)
    try {
        & $Action
        if (-not $script:CaseResults.Contains($Name)) {
            $script:CaseResults[$Name] = [pscustomobject]@{ Status = "PASS"; Detail = ""; Passed = $true }
        }
    } catch {
        $script:CaseResults[$Name] = [pscustomobject]@{ Status = "FAIL"; Detail = $_.Exception.Message; Passed = $false }
        $script:FunctionalFailed = $true
    }
}
function Invoke-LiveCli {
    param([string]$Stage,[string]$Command,[string[]]$Arguments=@())
    $script:Invocations.Add([pscustomobject]@{ stage = $Stage; command = $Command; arguments = @($Arguments) })
    switch -Wildcard ($Stage) {
        "math-transform-set" {
            $idx = [array]::IndexOf($Arguments, "--operation")
            if ($idx -ge 0) { $script:LastTransformOperation = $Arguments[$idx+1] }
            $tok = if ($script:LastTransformOperation -eq "differentiate") { "DIFF" } else { "ABSolute" }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:OPERation $tok", ":FUNCtion:SOURce1 CHANnel1") }
                result = [pscustomobject]@{}
            }
        }
        "math-transform-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @() }
                result = [pscustomobject]@{ math_operation = $script:LastTransformOperation; source = "channel1" }
            }
        }
        "math-filter-set" {
            $idx = [array]::IndexOf($Arguments, "--operation")
            if ($idx -ge 0) { $script:LastFilterOperation = $Arguments[$idx+1] }
            return [pscustomobject]@{ scpi = [pscustomobject]@{ sent = @() }; result = [pscustomobject]@{} }
        }
        "math-filter-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @() }
                result = [pscustomobject]@{ math_operation = $script:LastFilterOperation; source = "channel1" }
            }
        }
        "math-visualization-set" {
            $idx = [array]::IndexOf($Arguments, "--operation")
            if ($idx -ge 0) { $script:LastVisualizationOperation = $Arguments[$idx+1] }
            return [pscustomobject]@{ scpi = [pscustomobject]@{ sent = @() }; result = [pscustomobject]@{} }
        }
        "math-visualization-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @() }
                result = [pscustomobject]@{ math_operation = $script:LastVisualizationOperation }
            }
        }
        "math-vertical-baseline-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:SCALe?", ":FUNCtion:RANGe?", ":FUNCtion:OFFSet?") }
                result = [pscustomobject]@{ scale = $script:BaselineVerticalScale; range = 2000000; offset = $script:BaselineVerticalOffset }
            }
        }
        "math-vertical-set" {
            $idxScale = [array]::IndexOf($Arguments, "--scale")
            $idxOffset = [array]::IndexOf($Arguments, "--offset")
            if ($idxScale -ge 0) { $script:LastVerticalScale = $Arguments[$idxScale+1] }
            if ($idxOffset -ge 0) { $script:LastVerticalOffset = $Arguments[$idxOffset+1] }
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:SCALe $($Arguments[$idxScale+1])", ":FUNCtion:OFFSet $($Arguments[$idxOffset+1])") }
                result = [pscustomobject]@{}
            }
        }
        "math-vertical-query" {
            return [pscustomobject]@{
                scpi = [pscustomobject]@{ sent = @(":FUNCtion:SCALe?", ":FUNCtion:RANGe?", ":FUNCtion:OFFSet?") }
                result = [pscustomobject]@{ scale = [double]$script:LastVerticalScale; range = 2000000; offset = [double]$script:LastVerticalOffset }
            }
        }
        default {
            return [pscustomobject]@{ scpi = [pscustomobject]@{ sent = @() }; result = [pscustomobject]@{} }
        }
    }
}

# Locate the three production Math blocks that now contain option gating.
# Use TrimStart prefix to avoid matching ancestor `if ($snapshotComplete)` blocks.
$transformNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if ($is2000XSeries -and -not $snapshot.MathEnhancementsInstalled') -and $txt.Contains('Add-NotApplicableCase -Name "math-transform"')
}, $true))
$filterNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if (-not $script:FunctionalFailed -and @($identity.capabilities.math_filter_operations).Count -gt 0)') -and $txt.Contains('Add-NotApplicableCase -Name "math-filter"')
}, $true))
$visualNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if (-not $script:FunctionalFailed -and @($identity.capabilities.math_visualization_operations).Count -gt 0)') -and $txt.Contains('Add-NotApplicableCase -Name "math-visualization"')
}, $true))

if ($transformNodes.Count -ne 1) { throw "Expected 1 math-transform conditional, found $($transformNodes.Count)" }
if ($filterNodes.Count -ne 1) { throw "Expected 1 math-filter conditional, found $($filterNodes.Count)" }
if ($visualNodes.Count -ne 1) { throw "Expected 1 math-visualization conditional, found $($visualNodes.Count)" }

# Execute the production conditionals exactly as they appear in the script.
Invoke-Expression $transformNodes[0].Extent.Text
Invoke-Expression $filterNodes[0].Extent.Text
Invoke-Expression $visualNodes[0].Extent.Text

# Also execute math-vertical to verify dynamic fixture (must run after transform which sets DIFF)
$verticalNodes = @($ast.FindAll({
    param($node)
    if ($node -isnot [System.Management.Automation.Language.IfStatementAst]) { return $false }
    $txt = $node.Extent.Text.TrimStart()
    return $txt.StartsWith('if (-not $script:FunctionalFailed -and [int]$identity.capabilities.math_function_count -gt 0)') -and $txt.Contains('Invoke-BaselineCase -Name "math-vertical"')
}, $true))
if ($verticalNodes.Count -ne 1) { throw "Expected 1 math-vertical conditional, found $($verticalNodes.Count)" }
Invoke-Expression $verticalNodes[0].Extent.Text
$verticalResult = if ($script:CaseResults.Contains("math-vertical")) { $script:CaseResults["math-vertical"] } else { $null }

$transformResult = if ($script:CaseResults.Contains("math-transform")) { $script:CaseResults["math-transform"] } else { $null }
$filterResult = if ($script:CaseResults.Contains("math-filter")) { $script:CaseResults["math-filter"] } else { $null }
$visualResult = if ($script:CaseResults.Contains("math-visualization")) { $script:CaseResults["math-visualization"] } else { $null }

# Collect invoked SCPI-like operation names for negative checks.
$allArgs = @($script:Invocations | ForEach-Object { ($_.arguments -join " ") })
$joinedArgs = $allArgs -join " | "

[ordered]@{
    series = $Series
    installed = @($installedOptions)
    math_enhancements = [bool]$snapshot.MathEnhancementsInstalled
    advanced_math = [bool]$snapshot.AdvancedMathInstalled
    transform_status = if ($null -ne $transformResult) { [string]$transformResult.Status } else { "" }
    transform_detail = if ($null -ne $transformResult) { [string]$transformResult.Detail } else { "" }
    transform_operation = [string]$script:LastTransformOperation
    filter_status = if ($null -ne $filterResult) { [string]$filterResult.Status } else { "" }
    filter_detail = if ($null -ne $filterResult) { [string]$filterResult.Detail } else { "" }
    visualization_status = if ($null -ne $visualResult) { [string]$visualResult.Status } else { "" }
    visualization_detail = if ($null -ne $visualResult) { [string]$visualResult.Detail } else { "" }
    vertical_status = if ($null -ne $verticalResult) { [string]$verticalResult.Status } else { "" }
    vertical_detail = if ($null -ne $verticalResult) { [string]$verticalResult.Detail } else { "" }
    vertical_scale = [string]$script:LastVerticalScale
    vertical_offset = [string]$script:LastVerticalOffset
    joined_args = $joinedArgs
    invocations = @($script:Invocations | ForEach-Object { [ordered]@{ stage = $_.stage; command = $_.command; arguments = @($_.arguments) } })
} | ConvertTo-Json -Depth 10 -Compress
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness_path),
            "-ScriptPath",
            str(script_path),
            "-Series",
            series,
            "-InstalledOptionsCsv",
            installed_options,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])

    assert result["series"] == series
    if series == "2000X":
        assert result["math_enhancements"] is False
        assert result["transform_status"] == expected_transform_status
        assert result["filter_status"] == expected_filter_status
        assert result["visualization_status"] == expected_visualization_status
        assert result["transform_operation"] == ""
        assert "PLUS" in result["transform_detail"]
        assert "PLUS" in result["filter_detail"]
        assert "PLUS" in result["visualization_detail"]
        # Must not have executed any PLUS-only SCPI.
        assert "absolute" not in result["joined_args"].lower()
        assert "low-pass" not in result["joined_args"].lower()
        assert "magnify" not in result["joined_args"].lower()
        assert "ABSolute" not in result["joined_args"]
        assert "LOWPass" not in result["joined_args"]
        assert "MAGNify" not in result["joined_args"]
        # Verify math-vertical also uses dynamic baseline (same as 3000X)
        assert result["vertical_status"] == "PASS"
        vertical_invocations = [inv for inv in result["invocations"] if inv["stage"] == "math-vertical-set"]
        assert len(vertical_invocations) == 1
        v_args = vertical_invocations[0]["arguments"]
        assert v_args[v_args.index("--scale") + 1] == "250000"
        assert v_args[v_args.index("--offset") + 1] == "0"
    else:
        assert result["advanced_math"] is False
        assert result["transform_status"] == expected_transform_status
        assert result["transform_operation"] == expected_transform_operation
        assert result["filter_status"] == expected_filter_status
        assert result["visualization_status"] == expected_visualization_status
        assert "ADVMATH" in result["filter_detail"]
        assert "ADVMATH" in result["visualization_detail"]
        # 3000X without ADVMATH must use DIFF, not ABSolute/LOWPass/MAGNify.
        assert result["transform_operation"] == "differentiate"
        assert "differentiate" in result["joined_args"]
        assert "absolute" not in result["joined_args"].lower()
        assert "low-pass" not in result["joined_args"].lower()
        assert "magnify" not in result["joined_args"].lower()
        assert "ABSolute" not in result["joined_args"]
        assert "LOWPass" not in result["joined_args"]
        assert "MAGNify" not in result["joined_args"]
        # Verify math-vertical dynamic fixture: baseline query used and set uses baseline values, not hardcoded 1
        assert result["vertical_status"] == "PASS"
        vertical_invocations = [inv for inv in result["invocations"] if inv["stage"] == "math-vertical-set"]
        assert len(vertical_invocations) == 1
        v_args = vertical_invocations[0]["arguments"]
        scale_idx = v_args.index("--scale") if "--scale" in v_args else -1
        offset_idx = v_args.index("--offset") if "--offset" in v_args else -1
        assert scale_idx != -1 and offset_idx != -1
        assert v_args[scale_idx + 1] == "250000"
        assert v_args[offset_idx + 1] == "0"
        # Ensure baseline query was executed
        baseline_stages = [inv["stage"] for inv in result["invocations"]]
        assert "math-vertical-baseline-query" in baseline_stages
        assert "math-vertical-query" in baseline_stages
