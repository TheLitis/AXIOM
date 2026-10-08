param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [ValidateRange(2, 16)][int]$Repetitions = 3
)

# Cross two generated fixtures with three explicitly identified clock policies.
# Raw captures/logs stay local. A failed native clock arm is a measured result.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$gameDir = (Resolve-Path -LiteralPath $GameDirectory).Path
$shellPath = (Get-Process -Id $PID).Path
$smokePath = Join-Path $PSScriptRoot 'run-native-smoke.ps1'
$out = Join-Path $workspace ('reports/native/clock-study-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $out | Out-Null
if (Get-Process AXIOMSandbox -ErrorAction SilentlyContinue) { throw 'Existing sandbox process; finish that experiment first.' }
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')
$snapshot = Get-AxiomExperimentSnapshot $workspace
$results = @()
try {
foreach ($fixture in @('flat', 'spike')) {
    foreach ($policy in @('native', 'fixed-base-60', 'fixed-scheduler-240')) {
        $caseName = "$fixture-$policy"
        $casePath = Join-Path $out $caseName
        $stdout = Join-Path $out ($caseName + '.stdout.log')
        $stderr = Join-Path $out ($caseName + '.stderr.log')
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $smokePath + '"'),
            '-GameDirectory', ('"' + $gameDir + '"'), '-ClockPolicy', $policy,
            '-Fixture', $fixture, '-Repetitions', $Repetitions,
            '-OutputDirectory', ('"' + $casePath + '"'))
        Write-Host "Native clock experiment: $caseName ($Repetitions replays)"
        $process = Start-Process -FilePath $shellPath -WorkingDirectory $workspace -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $timer = [System.Diagnostics.Stopwatch]::StartNew()
        while (-not $process.WaitForExit(1000)) {
            if ($timer.Elapsed.TotalSeconds -gt (($Repetitions + 1) * 45 + 120)) {
                # Restrict cleanup to the sandbox directly owned by this child.
                $sandboxExe = Join-Path $workspace '.tools/runtime/AXIOMSandbox.exe'
                Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)" | Where-Object Name -eq 'AXIOMSandbox.exe' | ForEach-Object {
                    $child = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
                    if ($child -and $child.Path -eq $sandboxExe) {
                        Stop-Process -Id $child.Id
                        $child.WaitForExit(5000) | Out-Null
                    }
                }
                if (-not $process.HasExited -and $process.Path -eq $shellPath) { Stop-Process -Id $process.Id; $process.WaitForExit(5000) | Out-Null }
                throw "Clock study timed out; preserve evidence at $out"
            }
        }
        $comparisonPath = Join-Path $casePath 'comparison.json'
        if (-not (Test-Path -LiteralPath $comparisonPath)) {
            throw "Clock arm failed before comparison; inspect $stderr and $stdout"
        }
        $comparison = Get-Content -LiteralPath $comparisonPath -Raw | ConvertFrom-Json
        $expectedExit = if ($comparison.status -eq 'recorded_subset_consistent') { 0 } elseif ($comparison.status -eq 'recorded_subset_inconsistent') { 1 } else { -1 }
        if ($process.ExitCode -ne $expectedExit) {
            throw "Unexpected clock-arm exit $($process.ExitCode); preserve evidence at $out"
        }
        $results += [ordered]@{
            fixture = $fixture; clock_policy = $policy; exit_code = $process.ExitCode
            comparison_status = $comparison.status; attempt_count = $comparison.attempt_count
            comparison_sha256 = (Get-FileHash -LiteralPath $comparisonPath -Algorithm SHA256).Hash.ToLowerInvariant()
            component_consistency = $comparison.component_consistency
        }
        Write-Host "Clock arm result: $caseName = $($comparison.status)"
    }
}
$fixedCases = @($results | Where-Object { $_.clock_policy -eq 'fixed-scheduler-240' })
$fixedPassed = $fixedCases.Count -eq 2 -and @($fixedCases | Where-Object { $_.comparison_status -ne 'recorded_subset_consistent' }).Count -eq 0
$manifest = [ordered]@{
    schema_version = 1; kind = 'native_clock_study'; recorded_at_utc = [DateTime]::UtcNow.ToString('o')
    fixed_scheduler_gate = if ($fixedPassed) { 'passed_for_recorded_subset_and_generated_fixtures' } else { 'failed' }
    cases = $results
    limitations = @('Clock intervention changes the declared test environment.',
        'No position corrections, checkpoint restores or relaxed comparison are used.',
        'This study does not establish complete-state determinism, ordinary-input equivalence or AR.')
}
[System.IO.File]::WriteAllText((Join-Path $out 'study.json'), ($manifest | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
Write-Output "Clock study evidence: $out"
if (-not $fixedPassed) { throw 'Fixed scheduler recorded-subset agreement failed; study evidence preserved.' }

} finally {
    Restore-AxiomExperimentSnapshot $snapshot
}
