param([string] $ScriptPath, [string] $FixturePath, [string] $PythonPath, [string] $OutputRoot,
    [switch] $RealPreflight, [switch] $RealSettings, [switch] $RealAuto)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$fixture = Get-Content -LiteralPath $FixturePath -Raw | ConvertFrom-Json
$script:ValidatorRoot = Split-Path -Parent $ScriptPath
$script:FakeState = @{}
foreach ($property in $fixture.state.PSObject.Properties) { $script:FakeState[$property.Name] = $property.Value }

function Read-Host {
    switch ($fixture.confirmation) {
        "enter" { return "" }
        "decline" { return "N" }
        "whitespace" { return " " }
        "null" { return $null }
        "unavailable" { throw "No interactive console is attached." }
    }
}

function Invoke-FakeCapturedCommand {
    param([string] $Name, [string] $FilePath, [string[]] $Arguments,
        [string] $StdOutPath, [string] $StdErrPath, [string] $JsonPath = "",
        [string] $WorkingDirectory, [switch] $CaptureInMemory)
    if ($Name -eq "resource-parse" -or
        ($RealPreflight -and $Arguments -notcontains "--resource")) {
        return Invoke-CapturedCommand @PSBoundParameters
    }
    $command = $Arguments[2]
    $live = $Arguments -contains "--resource"
    if ($live -and (($RealSettings -and $command -notin @("identify", "autoscale")) -or
                   ($RealAuto -and $command -eq "autoscale"))) {
        # Run the actual public CLI in simulation to validate snapshot fields,
        # setters, readbacks, and error queries. Never forward a live resource.
        $resourceIndex = [Array]::IndexOf($Arguments, "--resource")
        $simulatedArguments = @($Arguments[0..($resourceIndex - 1)]) +
            @("--simulate", "--model", $fixture.target) + @($Arguments[($resourceIndex + 2)..($Arguments.Count - 1)])
        if ($simulatedArguments -contains "--resource") { throw "Simulation bridge must never forward a resource." }
        return Invoke-CapturedCommand -Name $Name -FilePath $FilePath -Arguments $simulatedArguments `
            -StdOutPath $StdOutPath -StdErrPath $StdErrPath -JsonPath $JsonPath `
            -WorkingDirectory $WorkingDirectory -CaptureInMemory:$CaptureInMemory
    }
    $idn = if ($live) { $fixture.live_idn } else { $fixture.idn }
    $capabilities = $fixture.capabilities
    $payload = [pscustomobject]@{
        ok = $true; error = $null; idn = $idn; capabilities = $capabilities
        system_error = if ($fixture.tektronix) { $null } else { [pscustomobject]@{ code = 0; is_error = $false; raw = '0,"No error"' } }
        scpi = [pscustomobject]@{ sent = @(); planned = @() }
        result = [pscustomobject]@{}
    }
    $exitCode = 0
    $stderr = ""
    if ($command -eq "autoscale") {
        $expected = if ($fixture.tektronix) { "AUTOSet EXECute" } else { ":AUToscale CHANnel1" }
        $commands = @($expected)
        if ($live) {
            # Auto changes every saved value, including hidden CH2/CH4 display.
            foreach ($key in @($script:FakeState.Keys)) {
                $value = $script:FakeState[$key]
                switch ($key.Split(':')[0]) {
                    "channel-display" { $value.display = -not $value.display }
                    "channel-scale" { $value.volts_per_division = 5.0 }
                    "channel-offset" { $value.volts = 0.5 }
                    "channel-probe" { $value.probe_ratio = 1.0 }
                    "channel-coupling" { $value.coupling = "ac" }
                    "timebase-scale" { $value.seconds_per_division = 0.01 }
                    "timebase-reference" { $value.reference = "left" }
                    "timebase-position" { $value.position_seconds = 0.1 }
                    "trigger-mode" { $value.mode = "edge" }
                    "trigger-holdoff" { $value.seconds = 0.01 }
                    "trigger-edge-source" { $value.source = "analog-channel"; $value.source_channel = 1 }
                    "trigger-edge-slope" { $value.slope = "positive" }
                    "trigger-edge-level" { $value.level_volts = 0.25 }
                    "acquisition" { $value.type = "normal"; $value.count = 4 }
                }
            }
            if ($fixture.scenario -in @("fallback", "fallback-failure", "unmarked-fallback")) {
                $commands += ":AUToscale"
                if ($fixture.scenario -ne "unmarked-fallback") {
                    $payload.result | Add-Member -NotePropertyName fallback -NotePropertyValue "bare_autoscale_after_source_undefined_header"
                }
            }
            if ($fixture.scenario -in @("auto-failure", "fallback-failure", "auto-and-restore-failure")) {
                $payload.ok = $false; $exitCode = 1
                $payload.error = [pscustomobject]@{ type = "OscilloscopeError"; message = "Auto command rejected" }
                if (-not $fixture.tektronix) { $payload.system_error.code = -113; $payload.system_error.is_error = $true }
            }
            if ($fixture.scenario -eq "missing-scpi") { $payload.scpi.sent = @("*IDN?") }
            else { $payload.scpi.sent = @("*IDN?") + $commands }
            if ($fixture.scenario -eq "invalid-json") { $payload = $null }
        } elseif ($Arguments -contains "--dry-run") { $payload.scpi.planned = $commands }
        else { $payload.scpi.sent = $commands }
        if ($null -ne $payload) {
            $payload.result | Add-Member -NotePropertyName commands -NotePropertyValue $commands
            $payload.result | Add-Member -NotePropertyName source_channels -NotePropertyValue $(if ($fixture.tektronix) { $null } else { @(1) })
            if ($fixture.tektronix) {
                $bits = if ($live -and $fixture.scenario -eq "dirty-status") { 4 } else { 0 }
                $payload.result | Add-Member -NotePropertyName post_command_status -NotePropertyValue ([pscustomobject]@{ value = $bits; raw = [string]$bits })
            }
        }
    } elseif ($command -eq "check-error") {
        $entries = @([pscustomobject]@{ code = 0; message = "No error" })
        if ($Name -eq "post-auto-status" -and $fixture.scenario -eq "dirty-status") {
            $entries = @([pscustomobject]@{ code = -222; message = "Data out of range" }) + $entries
        }
        if ($Name -eq "post-restore-status" -and $fixture.scenario -eq "restore-status-failure") {
            $entries = @([pscustomobject]@{ code = -222; message = "Restore error" }) + $entries
        }
        if ($Name -eq "post-auto-status" -and $fixture.scenario -eq "unterminated-queue") {
            $entries = @([pscustomobject]@{ code = -222; message = "No terminator" })
        }
        $payload.result = [pscustomobject]@{ entries = $entries }
    } elseif ($command -eq "system-standard-event") {
        $payload.result = [pscustomobject]@{ value = 0; raw = "0" }
    } elseif ($command -notin @("identify", "system-clear-status")) {
        $channel = ""
        foreach ($option in @("--channel", "--source-channel")) {
            if ($Arguments -contains $option) { $channel = $Arguments[[Array]::IndexOf($Arguments, $option) + 1] }
        }
        $key = "${command}:$(if ($command -eq 'trigger-edge-source') { '' } else { $channel })"
        $value = $script:FakeState[$key]
        if ($null -eq $value) { throw "Unknown fake query/set: $Name / $key" }
        if ($Arguments -notcontains "--query") {
            switch ($command) {
                "channel-display" { $value.display = $Arguments -contains "--on" }
                "acquisition" {
                    $value.type = $Arguments[[Array]::IndexOf($Arguments, "--type") + 1]
                    if ($Arguments -contains "--count") { $value.count = [int]$Arguments[[Array]::IndexOf($Arguments, "--count") + 1] }
                }
                "trigger-edge-source" {
                    if ($Arguments -contains "--source-channel") { $value.source = "analog-channel"; $value.source_channel = [int]$channel }
                    else { $value.source = $Arguments[[Array]::IndexOf($Arguments, "--source") + 1]; $value.source_channel = $null }
                }
                default {
                    $setOption = @($Arguments | Where-Object { $_ -match '^--[^=]+=' })[0]
                    $text = $setOption.Split('=', 2)[1]
                    $field = @($value.PSObject.Properties)[0].Name
                    $value.$field = if ($value.$field -is [double]) { [double]::Parse($text, [Globalization.CultureInfo]::InvariantCulture) } else { $text }
                }
            }
        }
        $payload.result = $value.PSObject.Copy()
        if (($fixture.scenario -in @("restore-failure", "auto-and-restore-failure") -and $Name -eq "restore-ch2-channel-scale") -or
            ($fixture.scenario -eq "snapshot-failure" -and $Name -eq "snapshot-ch2-channel-scale")) {
            $payload.ok = $false; $exitCode = 1
            $payload.error = [pscustomobject]@{ type = "OscilloscopeError"; message = "Fixture setting failed" }
        }
        if ($fixture.scenario -eq "readback-failure" -and $Name -eq "readback-ch3-channel-offset") { $payload.result.volts = 99.0 }
    }
    $record = [ordered]@{
        name = $Name; exit_code = $exitCode; success = ($exitCode -eq 0); duration_ms = 1
        payload = $payload; stderr_text = $stderr; stdout_text = ""
        stdout = ""; stderr = ""; json = ""
    }
    if (-not $CaptureInMemory) {
        $json = $payload | ConvertTo-Json -Depth 20
        Write-Utf8NoBomText -LiteralPath $StdOutPath -Text $json
        Write-Utf8NoBomText -LiteralPath $JsonPath -Text $json
        $record.stdout = $StdOutPath; $record.json = $JsonPath
    }
    return $record
}

# Replace only the process boundary, as in the existing Tektronix harness.
# Run the complete script, including its real gates, reports, summary, and exits.
$source = [IO.File]::ReadAllText($ScriptPath).Replace('$PSScriptRoot', '$script:ValidatorRoot')
$source = $source.Replace('Invoke-CapturedCommand', 'Invoke-FakeCapturedCommand')
$arguments = @{
    Target = $fixture.target; Connection = $fixture.connection; Resource = $fixture.resource
    Python = $PythonPath; OutputRoot = $OutputRoot; DebugArtifacts = [bool]$fixture.debug
}
if ($fixture.backend) { $arguments.Backend = $fixture.backend }
& ([scriptblock]::Create($source)) @arguments
