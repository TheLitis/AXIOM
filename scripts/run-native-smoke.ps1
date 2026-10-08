param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [ValidateRange(2, 16)][int]$Repetitions = 3
)

# Explicit engine experiment on a generated fixture, not human performance data.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --extra dev first.' }
if (Get-Process AXIOMSandbox -ErrorAction SilentlyContinue) {
    throw 'An AXIOMSandbox process is already running; finish that experiment first.'
}
& (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $GameDirectory
$runtime = Join-Path $workspace '.tools/runtime'
$executable = Join-Path $runtime 'AXIOMSandbox.exe'
$saveDir = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $saveDir 'captures'
$out = Join-Path $workspace ("reports/native/smoke-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force $out, $saveDir | Out-Null
$replayPath = Join-Path $saveDir 'replay.json'
$hadReplay = Test-Path -LiteralPath $replayPath
[byte[]]$oldReplay = @()
if ($hadReplay) { $oldReplay = [System.IO.File]::ReadAllBytes($replayPath) }

function Invoke-Fixture([bool]$Replay, [string]$Destination) {
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Name] = $true }
    $launchArgs = @('--geode:axiom-sandbox')
    if ($Replay) { $launchArgs += '--geode:axiom.native-capture.replay' }
    $process = Start-Process -FilePath $executable -WorkingDirectory $runtime -ArgumentList $launchArgs -WindowStyle Hidden -PassThru
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $captureFile = $null
        while ($timer.Elapsed.TotalSeconds -lt 45) {
            $captureFile = Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue |
                Where-Object { -not $before.ContainsKey($_.Name) } | Sort-Object Name | Select-Object -First 1
            if ($captureFile) { break }
            if ($process.HasExited) { throw "Sandbox exited before export (exit $($process.ExitCode))." }
            Start-Sleep -Milliseconds 200
        }
        if (-not $captureFile) { throw 'No native export within 45 seconds; inspect the sandbox Geode logs.' }
        Copy-Item -LiteralPath $captureFile.FullName -Destination $Destination
        $data = Get-Content -LiteralPath $Destination -Raw | ConvertFrom-Json
        if ($data.attempt.terminal.outcome -ne 'completed' -or $data.attempt.start_kind -ne 'level_start') {
            throw "Fixture did not complete from level_start; exported evidence preserved at $Destination"
        }
        $expectedSource = if ($Replay) { 'replay' } else { 'unknown' }
        if ($data.attempt.input_source -ne $expectedSource) {
            throw "Fixture effective input mode differs from requested mode: $Destination"
        }
        & $python -m axiom native $Destination --json ($Destination + '.inspection.json')
        if ($LASTEXITCODE -ne 0) { throw "Native capture validation failed: $Destination" }
        if ($Replay) {
            $inspection = Get-Content -LiteralPath ($Destination + '.inspection.json') -Raw | ConvertFrom-Json
            if ($inspection.counts.unexecuted_planned_tail -ne 0 -or $inspection.counts.planned_inputs -ne 2) {
                throw "Smoke fixture did not execute its complete two-event plan: $Destination"
            }
            $push = @($data.attempt.inputs | Where-Object { $_.phase -eq 'push' -and $_.pressed })
            $release = @($data.attempt.inputs | Where-Object { $_.phase -eq 'release' -and -not $_.pressed })
            if (-not $push.Count -or -not $release.Count) {
                throw "Native player push/release callbacks are missing: $Destination"
            }
        }
        Write-Host "Native fixture exported and validated: $Destination"
        return $data
    } finally {
        if (-not $process.HasExited -and $process.Path -eq $executable) {
            Stop-Process -Id $process.Id
            $process.WaitForExit(3000) | Out-Null
        }
    }
}

try {
    $baseline = Invoke-Fixture $false (Join-Path $out 'baseline.json')
    $plan = [ordered]@{
        schema_version = 1
        kind = 'native_replay'
        clock = 'processCommands_call_index'
        level_sha256 = $baseline.challenge.level_sha256
        environment_sha256 = $baseline.environment_sha256
        inputs = @(
            [ordered]@{ command_index = 60; player = 1; button = 1; pressed = $true },
            [ordered]@{ command_index = 90; player = 1; button = 1; pressed = $false }
        )
    }
    $planText = ($plan | ConvertTo-Json -Depth 10) + "`n"
    [System.IO.File]::WriteAllText($replayPath, $planText, [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText((Join-Path $out 'replay.json'), $planText, [System.Text.UTF8Encoding]::new($false))
    $repeatPaths = @()
    for ($index = 1; $index -le $Repetitions; $index++) {
        $destination = Join-Path $out "replay-$index.json"
        $null = Invoke-Fixture $true $destination
        $repeatPaths += $destination
    }
    & $python -m axiom native-compare @repeatPaths --json (Join-Path $out 'comparison.json')
    if ($LASTEXITCODE -ne 0) { throw 'Native repetition identities are incompatible; evidence preserved.' }
    $comparison = Get-Content -LiteralPath (Join-Path $out 'comparison.json') -Raw | ConvertFrom-Json
    Write-Output "Recorded subset comparison: $($comparison.status)"
    Write-Output "Evidence directory: $out"
    Write-Output 'This smoke test does not certify complete engine state, environment coverage, timing windows or AR.'
    if ($comparison.status -ne 'recorded_subset_consistent') {
        throw 'Recorded subset repeat agreement failed; comparison and captures are preserved.'
    }
} finally {
    if ($hadReplay) { [System.IO.File]::WriteAllBytes($replayPath, $oldReplay) }
    elseif (Test-Path -LiteralPath $replayPath) { Remove-Item -LiteralPath $replayPath }
}
