param([Parameter(Mandatory = $true)][string]$GameDirectory)

# Generated-fixture oracle controls; no human telemetry or AR.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --extra dev first.' }
if (Get-Process AXIOMSandbox -ErrorAction SilentlyContinue) { throw 'Existing sandbox process; finish that experiment first.' }
& (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $GameDirectory
$runtime = Join-Path $workspace '.tools/runtime'
$exe = Join-Path $runtime 'AXIOMSandbox.exe'
$save = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $save 'captures'
$out = Join-Path $workspace ('reports/native/controls-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $out | Out-Null
$fixturePath = Join-Path $runtime 'fixture-level.txt'
[byte[]]$oldFixture = [IO.File]::ReadAllBytes($fixturePath)
$replayPath = Join-Path $save 'replay.json'
$hadReplay = Test-Path -LiteralPath $replayPath
[byte[]]$oldReplay = @()
if ($hadReplay) { $oldReplay = [IO.File]::ReadAllBytes($replayPath) }
function Run-Control([string]$Name, [bool]$Replay) {
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' | ForEach-Object { $before[$_.Name] = $true }
    $arguments = @('--geode:axiom-sandbox')
    if ($Replay) { $arguments += '--geode:axiom.native-capture.replay' }
    $process = Start-Process -FilePath $exe -WorkingDirectory $runtime -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $capture = $null
        while ($timer.Elapsed.TotalSeconds -lt 45) {
            $capture = Get-ChildItem -LiteralPath $captures -File -Filter '*.json' | Where-Object { -not $before.ContainsKey($_.Name) } | Sort-Object Name | Select-Object -First 1
            if ($capture) { break }
            if ($process.HasExited) { throw 'Sandbox exited before export.' }
            Start-Sleep -Milliseconds 200
        }
        if (-not $capture) { throw 'Native control timed out.' }
        $destination = Join-Path $out ($Name + '.json')
        Copy-Item -LiteralPath $capture.FullName -Destination $destination
        return (Get-Content -LiteralPath $destination -Raw | ConvertFrom-Json)
    } finally {
        if (-not $process.HasExited -and $process.Path -eq $exe) {
            Stop-Process -Id $process.Id
            $process.WaitForExit(3000) | Out-Null
        }
    }
}
try {
    $hazard = 'kA13,0,kA15,0,kA16,0,kA14,0;1,8,2,300,3,15;1,1,2,600,3,-15;'
    [IO.File]::WriteAllText($fixturePath, $hazard, [Text.UTF8Encoding]::new($false))
    $death = Run-Control 'death' $false
    Write-Output ('Death control outcome: ' + $death.attempt.terminal.outcome)
    if ($death.attempt.terminal.outcome -ne 'died' -or -not $death.attempt.terminal.state.player1.is_dead) { throw 'Hazard control did not produce native death.' }
    & $python -m axiom native (Join-Path $out 'death.json') --json (Join-Path $out 'death.inspection.json')
    if ($LASTEXITCODE -ne 0) { throw 'Native death control failed structural validation.' }
    [IO.File]::WriteAllBytes($fixturePath, $oldFixture)
    $plan = [ordered]@{ schema_version=1; kind='native_replay'; clock='processCommands_call_index'; level_sha256=('0' * 64); environment_sha256=$death.environment_sha256; inputs=@() }
    [IO.File]::WriteAllText($replayPath, ($plan | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    $invalid = Run-Control 'wrong-level' $true
    if ($invalid.attempt.terminal.outcome -ne 'error' -or $invalid.integrity.recording_complete -or -not ($invalid.integrity.errors -contains 'Replay level hash mismatch')) { throw 'Wrong-level control did not fail for the required target mismatch.' }
    # Windows PowerShell 5 represents native stderr as error records. This
    # rejection is expected: retain its output and inspect its exit explicitly.
    $savedErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $messages = & $python -m axiom native (Join-Path $out 'wrong-level.json') --json (Join-Path $out 'wrong-level.inspection.json') 2>&1
        $validationExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedErrorAction }
    $messages | ForEach-Object { Write-Output $_.ToString() }
    if ($validationExit -ne 2) { throw 'Incomplete/error control was not rejected by the inspector.' }
    Write-Output 'Wrong-level control: native mismatch error and inspector rejection confirmed.'
    Write-Output "Control evidence directory: $out"
} finally {
    [IO.File]::WriteAllBytes($fixturePath, $oldFixture)
    if ($hadReplay) { [IO.File]::WriteAllBytes($replayPath, $oldReplay) }
    elseif (Test-Path -LiteralPath $replayPath) { Remove-Item -LiteralPath $replayPath }
}
