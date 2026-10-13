param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [string]$NativePackage,
    [string]$RuntimeDirectory,
    [string]$OutputDirectory,
    [ValidateRange(60, 900)][int]$TimeoutSeconds = 600,
    [switch]$AutomaticStart
)

# Game-scoped user-operated Raw Input observation. No OS input is synthesized.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
$utf8 = [Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')
function Get-WindowsObservationHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Write-WindowsObservationJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 80) + [Environment]::NewLine, $utf8)
}
function Get-WindowsObservationTree {
    $root = Join-Path $workspace 'native'
    [string[]]$sources = @(Get-ChildItem -LiteralPath (Join-Path $root 'src') -Recurse -File |
        Where-Object { $_.Extension -in @('.cpp', '.hpp') } |
        ForEach-Object { $_.FullName.Substring($root.Length + 1).Replace('\', '/') })
    [Array]::Sort($sources, [StringComparer]::Ordinal)
    $identity = ''
    foreach ($relative in @($sources) + @('CMakeLists.txt', 'mod.json')) {
        $identity += $relative + ':' + (Get-WindowsObservationHash (Join-Path $root $relative)) + [char]10
    }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($utf8.GetBytes($identity))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}
function Get-WindowsObservationDllHash([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entries = @($archive.Entries | Where-Object FullName -ceq 'axiom.native-capture.dll')
        if ($entries.Count -ne 1) { throw 'Native package requires exactly one root adapter DLL.' }
        $stream = $entries[0].Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
    } finally { $archive.Dispose() }
}
function Assert-WindowsObservationDirectory([string]$Path) {
    $root = [IO.Path]::GetFullPath($workspace).TrimEnd([char[]]'\/')
    $current = [IO.Path]::GetFullPath($Path)
    if (-not $current.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Observation evidence must remain within this workspace.'
    }
    while ($current -ne $root) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Observation directory is redirected or is a file: $current"
            }
        }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}
function Assert-WindowsObservationFrozen {
    foreach ($relative in $manifest.source_file_sha256.Keys) {
        if ((Get-WindowsObservationHash (Join-Path $workspace $relative)) -cne $manifest.source_file_sha256[$relative]) {
            throw "Source changed during observation: $relative"
        }
    }
    if ((Get-WindowsObservationHash $manifest.native_package.path) -cne $manifest.native_package.sha256 -or
        (Get-WindowsObservationTree) -cne $manifest.native_package.native_tree_sha256) {
        throw 'Native package or source tree changed during observation.'
    }
    foreach ($path in @((Join-Path $out 'fixture-level.txt'), (Join-Path $runtime 'fixture-level.txt'))) {
        if ((Get-WindowsObservationHash $path) -cne $manifest.level_sha256) { throw 'Fixture bytes changed during observation.' }
    }
    foreach ($record in $manifest.exported_captures) {
        if ((Get-WindowsObservationHash $record.path) -cne $record.sha256) { throw 'Retained capture bytes changed.' }
    }
}
function Assert-WindowsObservationCapturePath([string]$Path, [bool]$Directory) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if ($item.PSIsContainer -ne $Directory -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Capture path has an unexpected type or is redirected: $Path"
        }
    }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run uv sync --locked --extra dev first.' }
if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
    throw 'An active sandbox exists; this observation does not own it.'
}
$runtime = if ($RuntimeDirectory) { [IO.Path]::GetFullPath($RuntimeDirectory) } else {
    Join-Path $workspace ('.tools/runtime-windows-input-' + [guid]::NewGuid().ToString('N'))
}
$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else {
    Join-Path $workspace ('reports/native/windows-input-' + [guid]::NewGuid().ToString('N'))
}
Assert-AxiomExperimentPaths $workspace $runtime
Assert-WindowsObservationDirectory $out
if ((Test-Path -LiteralPath $runtime) -or (Test-Path -LiteralPath $out)) {
    throw 'Observation runtime and evidence directories must be new; previous evidence is preserved.'
}
$snapshot = Get-AxiomExperimentSnapshot $workspace $runtime
New-Item -ItemType Directory -Path $out | Out-Null
$profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $profile 'captures'
Assert-WindowsObservationCapturePath $captures $true
$process = $null
$analysisProcess = $null
$captureStreams = @()
$priorExecutionState = $null
$manifest = [ordered]@{
    kind='native_windows_input_observation'; status='observation_not_established'
    started_at_utc=[DateTime]::UtcNow.ToString('o'); finished_at_utc=$null; error=$null
    runtime_directory=$runtime; automatic_start=[bool]$AutomaticStart
    analysis_source_commit=(& git -C $workspace rev-parse HEAD).Trim()
    source_file_sha256=[ordered]@{}; native_package=$null; level_sha256=$null
    process_id=$null; process_started_at_utc=$null; arguments=@()
    exported_captures=@(); inspection=$null; analysis=$null; preservation=$null
    input_provenance='unknown'; human_authorship='requires_separate_user_statement'
    hardware_authentication='not_established'; ordinary_input_equivalence='not_established'; m1_gate='not_established'
}
try {
    if (-not ('AxiomWindowsObservationPower' -as [type])) {
        Add-Type -Name AxiomWindowsObservationPower -Namespace '' -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
    }
    $priorExecutionState = [AxiomWindowsObservationPower]::SetThreadExecutionState([uint32]2147483651)
    if (-not $priorExecutionState) { throw 'Unable to request temporary system/display execution state.' }
    $prepare = @{GameDirectory=$GameDirectory; RuntimeDirectory=$runtime}
    if ($NativePackage) { $prepare.NativePackage=$NativePackage }
    & (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') @prepare
    $package = Join-Path $runtime 'geode/mods/axiom.native-capture.geode'
    $manifest.native_package = [ordered]@{
        path=$package; sha256=(Get-WindowsObservationHash $package)
        dll_sha256=(Get-WindowsObservationDllHash $package); native_tree_sha256=(Get-WindowsObservationTree)
    }
    $sources = @('scripts/run-native-windows-input.ps1', 'scripts/native-experiment-state.ps1',
        'scripts/prepare-native-sandbox.ps1', 'native/CMakeLists.txt', 'native/mod.json')
    $sources += @(Get-ChildItem -LiteralPath (Join-Path $workspace 'native/src') -Recurse -File |
        Where-Object { $_.Extension -in @('.cpp', '.hpp') } |
        ForEach-Object { $_.FullName.Substring($workspace.Length + 1).Replace('\', '/') })
    $sources += @(Get-ChildItem -LiteralPath (Join-Path $workspace 'src/axiom') -File -Filter '*.py' |
        ForEach-Object { $_.FullName.Substring($workspace.Length + 1).Replace('\', '/') })
    foreach ($relative in $sources) { $manifest.source_file_sha256[$relative] = Get-WindowsObservationHash (Join-Path $workspace $relative) }
    $level = 'kA13,0,kA15,0,kA16,0,kA14,0;1,1,2,6000,3,-15;'
    foreach ($path in @((Join-Path $out 'fixture-level.txt'), (Join-Path $runtime 'fixture-level.txt'))) {
        [IO.File]::WriteAllText($path, $level, $utf8)
    }
    $manifest.level_sha256 = Get-WindowsObservationHash (Join-Path $out 'fixture-level.txt')
    Assert-WindowsObservationCapturePath $captures $true
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue |
        ForEach-Object {
            Assert-WindowsObservationCapturePath $_.FullName $false
            $before[$_.Name] = Get-WindowsObservationHash $_.FullName
        }
    $arguments = @('--geode:axiom-sandbox', '--geode:axiom.native-capture.clock-policy=native',
        '--geode:axiom.native-capture.windows-input=raw-dispatch-v1')
    if (-not $AutomaticStart) { $arguments += '--geode:axiom-sandbox-manual' }
    $manifest.arguments = $arguments
    Assert-WindowsObservationFrozen
    Write-WindowsObservationJson (Join-Path $out 'manifest.json') $manifest
    $windowStyle = if ($AutomaticStart) { 'Hidden' } else { 'Normal' }
    $process = Start-Process -FilePath (Join-Path $runtime 'AXIOMSandbox.exe') -WorkingDirectory $runtime -ArgumentList $arguments -WindowStyle $windowStyle -PassThru -RedirectStandardOutput (Join-Path $out 'stdout.txt') -RedirectStandardError (Join-Path $out 'stderr.txt')
    $manifest.process_id = $process.Id
    $manifest.process_started_at_utc = $process.StartTime.ToUniversalTime().ToString('o')
    Write-WindowsObservationJson (Join-Path $out 'manifest.json') $manifest
    Write-Host "AXIOM Windows input observer launched. Click Start AXIOM Test, then use the agreed manual sequence. Evidence: $out"
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $newCaptures = @()
    while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        Assert-WindowsObservationCapturePath $captures $true
        $newCaptures = @(Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue |
            Where-Object { -not $before.ContainsKey($_.Name) })
        if ($newCaptures.Count) {
            try {
                foreach ($candidate in $newCaptures) {
                    Assert-WindowsObservationCapturePath $candidate.FullName $false
                    $captureStreams += [IO.File]::Open($candidate.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
                }
                break
            } catch [IO.IOException] {
                foreach ($stream in $captureStreams) { $stream.Dispose() }
                $captureStreams = @()
                $newCaptures = @()
            }
        }
        if ($process.HasExited) { throw 'Owned sandbox exited before any export.' }
        Start-Sleep -Milliseconds 200
    }
    # Do not silently exclude changed files merely because their names predate
    # this process. Retain a separate copy before rejecting this experiment.
    foreach ($capture in @(Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue)) {
        Assert-WindowsObservationCapturePath $capture.FullName $false
        if ($before.ContainsKey($capture.Name) -and (Get-WindowsObservationHash $capture.FullName) -cne $before[$capture.Name]) {
            $changedPath = Join-Path $out ('changed-existing-' + $capture.Name)
            Copy-Item -LiteralPath $capture.FullName -Destination $changedPath
            $manifest.exported_captures += [ordered]@{
                path=$changedPath; sha256=(Get-WindowsObservationHash $changedPath); role='changed-existing'
                original_path=$capture.FullName; original_sha256=$before[$capture.Name]
            }
        }
    }
    for ($index = 0; $index -lt $newCaptures.Count; $index++) {
        $destination = Join-Path $out $newCaptures[$index].Name
        $targetStream = [IO.File]::Open($destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $captureStreams[$index].CopyTo($targetStream) }
        finally { $targetStream.Dispose(); $captureStreams[$index].Dispose() }
        $manifest.exported_captures += [ordered]@{path=$destination; sha256=(Get-WindowsObservationHash $destination); role='new'}
    }
    if ($newCaptures.Count -ne 1) { throw 'Expected one capture from this attempt; all discovered exports were retained.' }
    if (@($manifest.exported_captures | Where-Object { $_.role -eq 'changed-existing' }).Count) {
        throw 'Existing capture bytes changed during observation; changed evidence was retained separately.'
    }
    $destination = $manifest.exported_captures[0].path
    $data = Get-Content -LiteralPath $destination -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($data.schema_version -ne 7 -or $data.environment.windows_input_observer -cne 'raw-dispatch-v1' -or
        $data.environment.clocks.clock_policy -cne 'native' -or
        $data.attempt.input_delivery.driver -cne 'none' -or $data.attempt.input_source -cne 'unknown' -or
        $data.attempt.planned_inputs.Count -ne 0 -or $data.attempt.replay_sha256 -or
        $data.challenge.level_sha256 -cne $manifest.level_sha256 -or
        $data.environment.adapter_binary_sha256 -cne $manifest.native_package.dll_sha256 -or
        $data.collector.source_tree_sha256 -cne $manifest.native_package.native_tree_sha256 -or
        -not $data.attempt.windows_input.enabled -or
        @($data.attempt.windows_input.windows | Where-Object { $_.process_id -ne $manifest.process_id -or -not $_.installed }).Count) {
        throw 'Captured observation differs from the frozen Windows/native-clock/no-replay domain.'
    }
    $analysis = [ordered]@{
        started_at_utc=[DateTime]::UtcNow.ToString('o'); finished_at_utc=$null; exit_code=$null
        stdout_path=(Join-Path $out 'analysis.stdout.txt'); stderr_path=(Join-Path $out 'analysis.stderr.txt')
    }
    $manifest.analysis = $analysis
    $inspectionPath = Join-Path $out 'inspection.json'
    $analysisArguments = @('-m', 'axiom', 'native', $destination, '--json', $inspectionPath)
    $argumentLine = (@($analysisArguments | ForEach-Object {
        if ($_.Contains('"')) { throw 'Unsupported quote in analysis process argument.' }
        '"' + ($_ -replace '(\\+)$', '$1$1') + '"'
    }) -join ' ')
    $analysisProcess = Start-Process -FilePath $python -WorkingDirectory $workspace -ArgumentList $argumentLine -WindowStyle Hidden -PassThru -RedirectStandardOutput $analysis.stdout_path -RedirectStandardError $analysis.stderr_path
    $analysisHandle = $analysisProcess.Handle
    if (-not $analysisProcess.WaitForExit(60000)) { throw 'Capture analysis timed out; diagnostics retained.' }
    $analysis.exit_code = $analysisProcess.ExitCode
    $analysis.finished_at_utc = [DateTime]::UtcNow.ToString('o')
    if ($null -eq $analysis.exit_code -or $analysis.exit_code -ne 0) { throw 'Capture failed structural/integrity inspection.' }
    $manifest.inspection = [ordered]@{path=$inspectionPath; sha256=(Get-WindowsObservationHash $inspectionPath)}
    Assert-WindowsObservationFrozen
    $manifest.status = 'windows_input_observation_recorded'
    $manifest.outcome = $data.attempt.terminal.outcome
    $manifest.terminal_command_index = $data.attempt.terminal.command_index
    Write-Host 'Window/dispatch observation recorded; origin and full input equivalence remain unestablished.'
} catch {
    $manifest.error = $_.Exception.Message
    throw
} finally {
    try {
        foreach ($stream in $captureStreams) { $stream.Dispose() }
        try { if ($analysisProcess) { Stop-AxiomOwnedProcess $analysisProcess } }
        finally { if ($process) { Stop-AxiomOwnedProcess $process } }
    } catch { $manifest.status='observation_not_established'; $manifest.error=$_.Exception.Message; throw }
    finally {
        try {
            Restore-AxiomExperimentSnapshot $snapshot
            $preserved = Test-AxiomExperimentSnapshot $snapshot
            $preservationPath = Join-Path $out 'state-preservation.json'
            Write-WindowsObservationJson $preservationPath $preserved
            $manifest.preservation = [ordered]@{path=$preservationPath; sha256=(Get-WindowsObservationHash $preservationPath)}
            if (-not $preserved.all_preserved) { throw 'Four experiment files were not restored exactly.' }
        } catch { $manifest.status='observation_not_established'; $manifest.error=$_.Exception.Message; throw }
        finally {
            try {
                if ($priorExecutionState -and -not [AxiomWindowsObservationPower]::SetThreadExecutionState($priorExecutionState)) {
                    throw 'Unable to restore prior execution-state request.'
                }
            } catch { $manifest.status='observation_not_established'; $manifest.error=$_.Exception.Message; throw }
            finally {
                $manifest.finished_at_utc=[DateTime]::UtcNow.ToString('o')
                Write-WindowsObservationJson (Join-Path $out 'manifest.json') $manifest
            }
        }
    }
}
