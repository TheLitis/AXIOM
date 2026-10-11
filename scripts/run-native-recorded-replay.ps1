param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [Parameter(Mandatory = $true)][string]$SourceCapturePath,
    [Parameter(Mandatory = $true)][string]$LevelPath,
    [string]$RuntimeDirectory,
    [string]$OutputDirectory,
    [ValidateRange(30, 600)][int]$AttemptTimeoutSeconds = 90
)

# An explicit source-cadence intervention and processing-entry request replay.
# Every repetition uses a fresh owned process. Raw unsuccessful attempts remain.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
$utf8 = [Text.UTF8Encoding]::new($false)
$analysisRecords = @()
$analysisSequence = 0
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')

function Get-RecordedHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-RecordedPackageDllHash([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entries = @($archive.Entries | Where-Object FullName -ceq 'axiom.native-capture.dll')
        if ($entries.Count -ne 1) { throw 'Package must contain exactly one root adapter DLL.' }
        $stream = $entries[0].Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
    } finally { $archive.Dispose() }
}
function Get-RecordedNativeTreeHash {
    $nativeRoot = Join-Path $workspace 'native'
    [string[]]$paths = @(Get-ChildItem -LiteralPath (Join-Path $nativeRoot 'src') -File -Recurse |
        Where-Object { $_.Extension -in @('.cpp', '.hpp') } |
        ForEach-Object { $_.FullName.Substring($nativeRoot.Length + 1).Replace('\', '/') })
    [Array]::Sort($paths, [StringComparer]::Ordinal)
    $identity = ''
    foreach ($relative in @($paths) + @('CMakeLists.txt', 'mod.json')) {
        $identity += $relative + ':' + (Get-RecordedHash (Join-Path $nativeRoot $relative)) + "`n"
    }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($utf8.GetBytes($identity))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}
function Assert-RecordedCaptureBuild([string]$Path) {
    $capture = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($capture.environment.adapter_binary_sha256 -cne $manifest.native_package.dll_sha256 -or
        $capture.collector.source_tree_sha256 -cne $manifest.native_package.current_native_tree_sha256) {
        throw 'Captured adapter DLL or compiled native tree differs from the frozen package and source.'
    }
}
function Write-RecordedJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 80) + "`n", $utf8)
}
function Assert-RecordedDirectory([string]$Path) {
    $root = [IO.Path]::GetFullPath($workspace).TrimEnd([char[]]'\/')
    $current = [IO.Path]::GetFullPath($Path)
    if (-not $current.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Experiment runtime and evidence directories must remain inside the workspace.'
    }
    while ($current -ne $root) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Experiment directory is a file or redirected: $current"
            }
        }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}
function Assert-RecordedFrozenFiles {
    foreach ($relative in $manifest.analysis_file_sha256.Keys) {
        if ((Get-RecordedHash (Join-Path $workspace $relative)) -cne $manifest.analysis_file_sha256[$relative]) {
            throw "Analysis source changed during the experiment: $relative"
        }
    }
    foreach ($entry in @($manifest.source_capture, $manifest.level, $manifest.native_package)) {
        if ((Get-RecordedHash $entry.path) -cne $entry.sha256) { throw "Frozen bytes changed: $($entry.path)" }
    }
    if ((Get-RecordedHash (Join-Path $out 'source-capture.json')) -cne $manifest.source_capture.sha256 -or
        (Get-RecordedHash (Join-Path $out 'fixture-level.txt')) -cne $manifest.level.sha256) {
        throw 'Retained source or fixture evidence differs from its original frozen bytes.'
    }
    foreach ($entry in @($manifest.source_inspection, $manifest.comparison)) {
        if ($entry -and (Get-RecordedHash $entry.path) -cne $entry.sha256) { throw 'Retained analysis evidence changed.' }
    }
    foreach ($attempt in $manifest.attempts) {
        foreach ($entry in $attempt.exported_captures) {
            if ((Get-RecordedHash $entry.path) -cne $entry.sha256) { throw 'Retained native capture changed.' }
        }
        if ($attempt.inspection_path -and (Get-RecordedHash $attempt.inspection_path) -cne $attempt.inspection_sha256) {
            throw 'Retained native inspection changed.'
        }
    }
    if ((Get-RecordedNativeTreeHash) -cne $manifest.native_package.current_native_tree_sha256) {
        throw 'Native source tree changed during the experiment.'
    }
    if ((Get-RecordedHash (Join-Path $runtime 'fixture-level.txt')) -cne $manifest.level.sha256) {
        throw 'Prepared fixture bytes changed.'
    }
    if ($manifest.plan -and (Get-RecordedHash $manifest.plan.path) -cne $manifest.plan.sha256) {
        throw 'Frozen replay plan changed.'
    }
    if ($manifest.plan -and (Get-RecordedHash (Join-Path $profile 'replay.json')) -cne $manifest.plan.sha256) {
        throw 'Installed replay plan differs from the frozen plan.'
    }
}
function Invoke-RecordedAnalysis([string[]]$Arguments) {
    $stem = Join-Path $out ('analysis-' + $script:analysisSequence)
    $script:analysisSequence++
    $record = [ordered]@{
        arguments = $Arguments; stdout_path = $stem + '.stdout.txt'; stderr_path = $stem + '.stderr.txt'
        started_at_utc = [DateTime]::UtcNow.ToString('o'); finished_at_utc = $null; exit_code = $null
    }
    $script:analysisRecords += $record
    if ($script:manifest) { $manifest.analysis_invocations = $script:analysisRecords }
    $argumentLine = (@(@('-m', 'axiom') + $Arguments | ForEach-Object {
        if ($_.Contains('"')) { throw 'Unsupported quote in analysis process argument.' }
        '"' + ($_ -replace '(\\+)$', '$1$1') + '"'
    }) -join ' ')
    $process = $null
    try {
        Write-RecordedJson ($stem + '.json') $record
        $process = Start-Process -FilePath $python -WorkingDirectory $workspace -ArgumentList $argumentLine -WindowStyle Hidden -PassThru -RedirectStandardOutput $record.stdout_path -RedirectStandardError $record.stderr_path
        $analysisHandle = $process.Handle
        if (-not $process.WaitForExit(60000)) { throw 'Analysis timed out; diagnostic logs retained.' }
        $record.exit_code = $process.ExitCode
        if ($null -eq $record.exit_code -or $record.exit_code -ne 0) {
            throw "Analysis failed structurally: $($Arguments[0]); see $($record.stderr_path)"
        }
    } finally {
        try { if ($process) { Stop-AxiomOwnedProcess $process } }
        finally {
            $record.finished_at_utc = [DateTime]::UtcNow.ToString('o')
            Write-RecordedJson ($stem + '.json') $record
        }
    }
}
function Invoke-RecordedCapture([string]$Stem, [bool]$Replay) {
    Assert-RecordedFrozenFiles
    if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
        throw 'Existing active sandbox; this experiment does not own it.'
    }
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue |
        ForEach-Object { $before[$_.Name] = $true }
    $arguments = @('--geode:axiom-sandbox', '--geode:axiom.native-capture.clock-policy=native')
    if ($Replay) {
        $arguments = @('--geode:axiom-sandbox', '--geode:axiom.native-capture.replay',
            '--geode:axiom.native-capture.clock-policy=recorded-scheduler-stream',
            '--geode:axiom.native-capture.input-driver=owned-processing-entry')
    }
    $record = [ordered]@{
        role = $(if ($Replay) { 'recorded-replay' } else { 'target-identity-baseline' })
        arguments = $arguments; started_at_utc = [DateTime]::UtcNow.ToString('o')
        process_id = $null; process_started_at_utc = $null
        stdout_path = Join-Path $out ($Stem + '.stdout.txt'); stderr_path = Join-Path $out ($Stem + '.stderr.txt')
        exported_captures = @(); error = $null; inspection_error = $null
        capture_path = $null; capture_sha256 = $null; inspection_path = $null
        inspection_sha256 = $null; finished_at_utc = $null
    }
    $manifest.attempts += $record
    $process = $null
    try {
        $process = Start-Process -FilePath (Join-Path $runtime 'AXIOMSandbox.exe') -WorkingDirectory $runtime -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput $record.stdout_path -RedirectStandardError $record.stderr_path -PassThru
        $record.process_id = $process.Id
        $record.process_started_at_utc = $process.StartTime.ToUniversalTime().ToString('o')
        Write-RecordedJson (Join-Path $out ($Stem + '.launch.json')) $record
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while ($timer.Elapsed.TotalSeconds -lt $AttemptTimeoutSeconds) {
            $new = @(Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue |
                Where-Object { -not $before.ContainsKey($_.Name) } | Sort-Object Name)
            if ($new.Count) {
                for ($index = 0; $index -lt $new.Count; $index++) {
                    $destination = Join-Path $out $(if ($index -eq 0) { $Stem + '.json' } else { $Stem + '-unexpected-' + $new[$index].Name })
                    Copy-Item -LiteralPath $new[$index].FullName -Destination $destination
                    $record.exported_captures += [ordered]@{ path = $destination; source_path = $new[$index].FullName; sha256 = Get-RecordedHash $destination }
                }
                if ($new.Count -ne 1) { throw 'Multiple native exports appeared; all retained without selecting a replacement.' }
                $record.capture_path = $record.exported_captures[0].path
                $record.capture_sha256 = $record.exported_captures[0].sha256
                break
            }
            if ($process.HasExited) { throw 'Owned sandbox exited before export.' }
            Start-Sleep -Milliseconds 200
        }
        if (-not $record.capture_path) { throw 'Attempt timed out; launch and outputs retained.' }
    } catch { $record.error = $_.Exception.Message }
    finally {
        try { if ($process) { Stop-AxiomOwnedProcess $process } }
        catch { $record.error = 'Owned-process cleanup failed: ' + $_.Exception.Message; throw }
        finally {
            $record.finished_at_utc = [DateTime]::UtcNow.ToString('o')
            Write-RecordedJson (Join-Path $out ($Stem + '.launch.json')) $record
        }
    }
    if ($record.capture_path) {
        try {
            Assert-RecordedCaptureBuild $record.capture_path
            $inspectionPath = Join-Path $out ($Stem + '.inspection.json')
            Invoke-RecordedAnalysis @('native', $record.capture_path, '--json', $inspectionPath)
            $record.inspection_path = $inspectionPath
            $record.inspection_sha256 = Get-RecordedHash $inspectionPath
        }
        catch { $record.inspection_error = $_.Exception.Message }
    }
    Write-RecordedJson (Join-Path $out ($Stem + '.launch.json')) $record
    Write-RecordedJson (Join-Path $out 'manifest.json') $manifest
    return $record
}

if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --extra dev first.' }
$source = (Resolve-Path -LiteralPath $SourceCapturePath).Path
$level = (Resolve-Path -LiteralPath $LevelPath).Path
$runtime = if ($RuntimeDirectory) { [IO.Path]::GetFullPath($RuntimeDirectory) } else {
    Join-Path $workspace ('.tools/runtime-recorded-replay-' + [guid]::NewGuid().ToString('N'))
}
$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else {
    Join-Path $workspace ('reports/native/recorded-replay-' + [guid]::NewGuid().ToString('N'))
}
Assert-RecordedDirectory $runtime
Assert-RecordedDirectory $out
if (Test-Path -LiteralPath $runtime) { throw 'Runtime already exists; use a fresh directory.' }
if (Test-Path -LiteralPath $out) { throw 'Evidence directory already exists; preserved without replacement.' }
if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
    throw 'Existing active sandbox; finish its experiment first.'
}
New-Item -ItemType Directory -Path $out | Out-Null
Copy-Item -LiteralPath $source -Destination (Join-Path $out 'source-capture.json')
Copy-Item -LiteralPath $level -Destination (Join-Path $out 'fixture-level.txt')
Invoke-RecordedAnalysis @('native', $source, '--json', (Join-Path $out 'source.inspection.json'))
$sourceData = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json
if ($sourceData.challenge.level_sha256 -cne (Get-RecordedHash $level)) { throw 'Fixture bytes differ from the recorded source challenge.' }
$manifest = [ordered]@{
    schema_version = 1; kind = 'native_recorded_replay_experiment'
    started_at_utc = [DateTime]::UtcNow.ToString('o'); finished_at_utc = $null
    analysis_source_commit = (& git -C $workspace rev-parse HEAD).Trim(); analysis_file_sha256 = [ordered]@{}
    source_capture = [ordered]@{ path = $source; sha256 = Get-RecordedHash $source }
    level = [ordered]@{ path = $level; sha256 = Get-RecordedHash $level }
    native_package = $null; plan = $null; attempts = @(); requested_repetitions = 3
    source_inspection = [ordered]@{ path = Join-Path $out 'source.inspection.json'; sha256 = Get-RecordedHash (Join-Path $out 'source.inspection.json') }
    analysis_invocations = $analysisRecords
    comparison = $null; status = 'running'; error = $null; state_preservation = $null
    input_provenance = 'source_unknown_replay_synthetic'; ordinary_input_equivalence = 'not_established'
    m1_gate = 'not_established'
}
foreach ($relative in @('src/axiom/native.py', 'src/axiom/replaybridge.py', 'src/axiom/cli.py',
    'src/axiom/validation.py', 'src/axiom/__main__.py', 'src/axiom/__init__.py',
    'scripts/run-native-recorded-replay.ps1', 'scripts/native-experiment-state.ps1', 'scripts/prepare-native-sandbox.ps1',
    'native/src/main.cpp', 'native/src/SandboxFixture.cpp', 'native/CMakeLists.txt', 'native/mod.json')) {
    $manifest.analysis_file_sha256[$relative] = Get-RecordedHash (Join-Path $workspace $relative)
}
$snapshot = Get-AxiomExperimentSnapshot $workspace $runtime
$profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $profile 'captures'
$priorExecutionState = $null
try {
    if (-not ('AxiomRecordedPower' -as [type])) {
        Add-Type -Name AxiomRecordedPower -Namespace '' -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
    }
    $priorExecutionState = [AxiomRecordedPower]::SetThreadExecutionState([uint32]2147483651)
    if (-not $priorExecutionState) { throw 'Unable to request temporary system/display execution state.' }
    & (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $GameDirectory -RuntimeDirectory $runtime
    Copy-Item -LiteralPath $level -Destination (Join-Path $runtime 'fixture-level.txt')
    $package = Join-Path $runtime 'geode/mods/axiom.native-capture.geode'
    $manifest.native_package = [ordered]@{
        path = $package; sha256 = Get-RecordedHash $package
        dll_sha256 = Get-RecordedPackageDllHash $package
        current_native_tree_sha256 = Get-RecordedNativeTreeHash
    }
    Write-RecordedJson (Join-Path $out 'manifest.json') $manifest
    $baseline = Invoke-RecordedCapture 'baseline' $false
    if ($baseline.error -or $baseline.inspection_error) { throw 'Target-identity baseline failed; raw evidence retained.' }
    $planPath = Join-Path $out 'replay-plan.json'
    Invoke-RecordedAnalysis @('native-replay-plan', $source, $baseline.capture_path, '--json', $planPath)
    $manifest.plan = [ordered]@{ path = $planPath; sha256 = Get-RecordedHash $planPath }
    Copy-Item -LiteralPath $planPath -Destination (Join-Path $profile 'replay.json')
    $replayRecords = @()
    for ($index = 1; $index -le 3; $index++) {
        $record = Invoke-RecordedCapture ("replay-$index") $true
        $replayRecords += $record
        Write-Host "Recorded replay $index/3 collected; capture=$($record.capture_sha256), error=$($record.error), inspection=$($record.inspection_error)"
    }
    if (@($replayRecords | Where-Object { $_.error -or $_.inspection_error }).Count) {
        throw 'At least one of the three repetitions failed; every attempt is retained.'
    }
    $comparisonPath = Join-Path $out 'comparison.json'
    Invoke-RecordedAnalysis @('native-recorded-compare', $source, $planPath,
        $replayRecords[0].capture_path, $replayRecords[1].capture_path, $replayRecords[2].capture_path,
        '--json', $comparisonPath)
    $comparison = Get-Content -LiteralPath $comparisonPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifest.comparison = [ordered]@{ path = $comparisonPath; sha256 = Get-RecordedHash $comparisonPath; status = $comparison.status }
    $manifest.status = $comparison.status
    Assert-RecordedFrozenFiles
} catch {
    $manifest.status = 'recorded_replay_not_established'
    $manifest.error = $_.Exception.Message
    throw
} finally {
    try {
        Restore-AxiomExperimentSnapshot $snapshot
        $preserved = Test-AxiomExperimentSnapshot $snapshot
        $manifest.state_preservation = $preserved
        Write-RecordedJson (Join-Path $out 'state-preservation.json') $preserved
        if (-not $preserved.all_preserved) { throw 'Four experiment files were not restored exactly.' }
    } catch {
        $manifest.status = 'recorded_replay_not_established'
        $manifest.error = 'State restoration failed: ' + $_.Exception.Message
        throw
    } finally {
        try {
            if ($priorExecutionState -and -not [AxiomRecordedPower]::SetThreadExecutionState($priorExecutionState)) {
                throw 'Unable to restore prior execution-state request.'
            }
        } catch {
            $manifest.status = 'recorded_replay_not_established'
            $manifest.error = 'Execution-state restoration failed: ' + $_.Exception.Message
            throw
        } finally {
            $manifest.finished_at_utc = [DateTime]::UtcNow.ToString('o')
            Write-RecordedJson (Join-Path $out 'manifest.json') $manifest
        }
    }
}
