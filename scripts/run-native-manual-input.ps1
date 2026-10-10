param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [string]$RuntimeDirectory,
    [string]$OutputDirectory,
    [ValidateRange(30, 600)][int]$TimeoutSeconds = 180
)

# User-operated observation only: no replay, clock intervention or OS injection.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --extra dev first.' }
if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
    throw 'Existing active sandbox process; finish that experiment first.'
}
$runtime = if ($RuntimeDirectory) { [IO.Path]::GetFullPath($RuntimeDirectory) } else {
    Join-Path $workspace ('.tools/runtime-manual-' + [guid]::NewGuid().ToString('N'))
}
$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else {
    Join-Path $workspace ('reports/native/manual-input-' + [guid]::NewGuid().ToString('N'))
}
if (Test-Path -LiteralPath $out) { throw 'Evidence directory already exists; preserved without replacement.' }
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')
$snapshot = Get-AxiomExperimentSnapshot $workspace $runtime
New-Item -ItemType Directory -Path $out | Out-Null
$profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $profile 'captures'
$process = $null
$priorExecutionState = $null
try {
    if (-not ('AxiomManualPower' -as [type])) {
        Add-Type -Name AxiomManualPower -Namespace '' -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
    }
    $priorExecutionState = [AxiomManualPower]::SetThreadExecutionState([uint32]2147483651)
    if (-not $priorExecutionState) { throw 'Unable to request temporary system/display execution state.' }
    & (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $GameDirectory -RuntimeDirectory $runtime
    $level = 'kA13,0,kA15,0,kA16,0,kA14,0;1,1,2,1800,3,-15;'
    [IO.File]::WriteAllText((Join-Path $runtime 'fixture-level.txt'), $level, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $out 'fixture-level.txt'), $level, [Text.UTF8Encoding]::new($false))
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Name] = $true }
    $arguments = @('--geode:axiom-sandbox', '--geode:axiom-sandbox-manual', '--geode:axiom.native-capture.clock-policy=native')
    # A visible window is required for the human's explicitly requested test.
    $process = Start-Process -FilePath (Join-Path $runtime 'AXIOMSandbox.exe') -WorkingDirectory $runtime -ArgumentList $arguments -WindowStyle Normal -RedirectStandardOutput (Join-Path $out 'stdout.txt') -RedirectStandardError (Join-Path $out 'stderr.txt') -PassThru
    $sourceCommit = (& git -C $workspace rev-parse HEAD).Trim()
    $analysisFiles = [ordered]@{}
    foreach ($relative in @('src/axiom/native.py', 'scripts/run-native-manual-input.ps1', 'scripts/native-experiment-state.ps1', 'scripts/prepare-native-sandbox.ps1')) {
        $analysisFiles[$relative] = (Get-FileHash -LiteralPath (Join-Path $workspace $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    [IO.File]::WriteAllText((Join-Path $out 'launch.json'), ([ordered]@{
        pid=$process.Id; started_at_utc=$process.StartTime.ToUniversalTime().ToString('o'); arguments=$arguments
        analysis_source_commit=$sourceCommit; analysis_file_sha256=$analysisFiles
        package_sha256=(Get-FileHash -LiteralPath (Join-Path $runtime 'geode/mods/axiom.native-capture.geode') -Algorithm SHA256).Hash.ToLowerInvariant()
        input_provenance='unknown'; human_authorship='requires_separate_user_statement'
    } | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    Write-Host "Manual observation window launched; click Start AXIOM Test, then press/release Space. Evidence: $out"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $capture = $null
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $capture = Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | Where-Object { -not $before.ContainsKey($_.Name) } | Sort-Object Name | Select-Object -First 1
        if ($capture) { break }
        if ($process.HasExited) { throw 'Owned sandbox exited before export.' }
        Start-Sleep -Milliseconds 200
    }
    if (-not $capture) { throw 'Manual test timed out; launch and logs retained.' }
    $destination = Join-Path $out 'capture.json'
    Copy-Item -LiteralPath $capture.FullName -Destination $destination
    & $python -m axiom native $destination --json (Join-Path $out 'inspection.json')
    if ($LASTEXITCODE -ne 0) { throw 'Manual capture failed structure/integrity validation; evidence retained.' }
    $data = Get-Content -LiteralPath $destination -Raw | ConvertFrom-Json
    if ($data.schema_version -ne 4 -or $data.environment.clocks.clock_policy -ne 'native' -or $data.attempt.input_delivery.driver -ne 'none' -or $data.attempt.input_source -ne 'unknown') {
        throw 'Manual observation domain differs from requested no-replay native-clock conditions.'
    }
    $levelHasher = [Security.Cryptography.SHA256]::Create()
    try { $levelHash = [BitConverter]::ToString($levelHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($level))).Replace('-', '').ToLowerInvariant() }
    finally { $levelHasher.Dispose() }
    if ($data.challenge.level_sha256 -ne $levelHash) { throw 'Captured manual challenge differs.' }
    $result = [ordered]@{
        kind='native_manual_input_observation'; recorded_at_utc=[DateTime]::UtcNow.ToString('o')
        capture_sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
        collector=$data.collector; outcome=$data.attempt.terminal.outcome; terminal_command_index=$data.attempt.terminal.command_index
        native_input_receipt_count=$data.attempt.inputs.Count; delivery_event_count=$data.attempt.delivery_events.Count
        input_provenance='unknown'; human_authorship='requires_separate_user_statement'
        ordinary_input_equivalence='not_established'; m1_gate='not_established'
    }
    [IO.File]::WriteAllText((Join-Path $out 'manual-result.json'), ($result | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
    Write-Host "Manual observation recorded: $($result.outcome); input authorship remains unknown in the capture."
} finally {
    try {
        if ($process) { Stop-AxiomOwnedProcess $process }
    } finally {
        try {
            Restore-AxiomExperimentSnapshot $snapshot
            $preserved = Test-AxiomExperimentSnapshot $snapshot
            [IO.File]::WriteAllText((Join-Path $out 'state-preservation.json'), ($preserved | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
            if (-not $preserved.all_preserved) { throw 'Four experiment files were not restored exactly.' }
        } finally {
            if ($priorExecutionState -and -not [AxiomManualPower]::SetThreadExecutionState($priorExecutionState)) {
                throw 'Unable to restore prior execution-state request.'
            }
        }
    }
}
