param([Parameter(Mandatory = $true)][string]$RequestPath)

# One full-start replay attempt. This is an engine worker, not device input.
# The parent validates native capture/terminal identity after this worker exits.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native-probe-process.ps1')

function Read-AxiomProbeRequest([string]$Path) {
    Assert-AxiomProbeOrdinaryPath $Path 'file'
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        if ($stream.Length -le 0 -or $stream.Length -gt 65536) { throw 'Probe request is empty or exceeds 64 KiB.' }
        $bytes = [byte[]]::new([int]$stream.Length)
        $position = 0
        while ($position -lt $bytes.Length) {
            $read = $stream.Read($bytes, $position, $bytes.Length - $position)
            if (-not $read) { throw 'Probe request byte read was incomplete.' }
            $position += $read
        }
        $request = [Text.UTF8Encoding]::new($false, $true).GetString($bytes) | ConvertFrom-Json
    } finally { $stream.Dispose() }
    $fields = @('schema_version', 'kind', 'trial_id', 'workspace', 'attempt_directory', 'runtime_directory',
        'game_directory', 'native_package', 'native_package_sha256', 'level_path', 'replay_path', 'level_sha256',
        'replay_file_sha256', 'environment_sha256', 'game_executable_sha256', 'adapter_binary_sha256', 'timeout_seconds')
    if ($null -eq $request -or $request -is [array] -or
        @($request.PSObject.Properties).Count -ne $fields.Count -or
        @(Compare-Object @($request.PSObject.Properties.Name) $fields -CaseSensitive).Count) {
        throw 'Probe request must contain exactly the supported schema-1 fields.'
    }
    if (($request.schema_version -isnot [int] -and $request.schema_version -isnot [long]) -or
        $request.schema_version -ne 1 -or $request.kind -isnot [string] -or $request.kind -cne 'native_probe_attempt_request' -or
        $request.trial_id -isnot [string] -or $request.trial_id -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$' -or
        ($request.timeout_seconds -isnot [int] -and $request.timeout_seconds -isnot [long]) -or
        $request.timeout_seconds -lt 30 -or $request.timeout_seconds -gt 600) {
        throw 'Invalid native probe request schema, trial id or timeout.'
    }
    foreach ($field in @('level_sha256', 'replay_file_sha256', 'environment_sha256',
            'game_executable_sha256', 'adapter_binary_sha256', 'native_package_sha256')) {
        if ($request.$field -isnot [string] -or $request.$field -cnotmatch '^[0-9a-f]{64}$') {
            throw "Invalid probe request hash: $field"
        }
    }
    foreach ($field in @('workspace', 'attempt_directory', 'runtime_directory', 'game_directory',
            'native_package', 'level_path', 'replay_path')) {
        if ($request.$field -isnot [string]) { throw "Probe request path is not a string: $field" }
        [void](Get-AxiomProbeAbsolutePath $request.$field)
    }
    $workspace = Get-AxiomProbeAbsolutePath (Split-Path -Parent $PSScriptRoot)
    if (-not [String]::Equals($workspace, $request.workspace.TrimEnd([char[]]'\/'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Probe request workspace must be the worker checkout.'
    }
    Assert-AxiomProbeOrdinaryPath $request.workspace 'directory'
    Assert-AxiomProbeBelow $request.attempt_directory $request.workspace
    Assert-AxiomProbeOrdinaryPath $request.attempt_directory 'directory'
    if (-not [String]::Equals((Get-AxiomProbeAbsolutePath $Path),
            (Join-Path $request.attempt_directory 'request.json'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Probe request must be request.json in its declared attempt directory.'
    }
    $allowed = @('request.json', 'worker.stdout.txt', 'worker.stderr.txt', 'cancel.request.json')
    foreach ($entry in @(Get-ChildItem -LiteralPath $request.attempt_directory -Force)) {
        if ($entry.PSIsContainer -or $entry.Name -cnotin $allowed) {
            throw 'Probe attempt directory is not fresh; prior evidence is preserved.'
        }
        Assert-AxiomProbeOrdinaryPath $entry.FullName 'file'
    }
    return $request
}

function Get-AxiomProbePackageDllHash([string]$Path) {
    Assert-AxiomProbeOrdinaryPath $Path 'file'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entries = @($archive.Entries | Where-Object { $_.FullName -ieq 'axiom.native-capture.dll' })
        if ($entries.Count -ne 1 -or $entries[0].FullName -cne 'axiom.native-capture.dll' -or
            $entries[0].Length -le 0 -or $entries[0].Length -gt 67108864) {
            throw 'Native package requires exactly one bounded root adapter DLL.'
        }
        $stream = $entries[0].Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
    } finally { $archive.Dispose() }
}

function Assert-AxiomProbeFrozenInputs($Request, [string]$RequestSha256, [switch]$Prepared) {
    if ((Get-AxiomProbeHash $RequestPath) -cne $RequestSha256) { throw 'Probe request bytes changed during execution.' }
    foreach ($pair in @(@($Request.level_path, $Request.level_sha256),
            @($Request.replay_path, $Request.replay_file_sha256),
            @($Request.native_package, $Request.native_package_sha256),
            @((Join-Path $Request.game_directory 'GeometryDash.exe'), $Request.game_executable_sha256))) {
        if ((Get-AxiomProbeHash $pair[0]) -cne $pair[1]) { throw 'A frozen native probe input changed.' }
    }
    if ((Get-AxiomProbePackageDllHash $Request.native_package) -cne $Request.adapter_binary_sha256) {
        throw 'Packaged adapter DLL differs from the frozen probe request.'
    }
    if ($Prepared) {
        foreach ($pair in @(@((Join-Path $Request.runtime_directory 'fixture-level.txt'), $Request.level_sha256),
                @((Join-Path $profile 'replay.json'), $Request.replay_file_sha256),
                @((Join-Path $Request.runtime_directory 'AXIOMSandbox.exe'), $Request.game_executable_sha256),
                @((Join-Path $Request.runtime_directory 'geode/mods/axiom.native-capture.geode'), $Request.native_package_sha256))) {
            if ((Get-AxiomProbeHash $pair[0]) -cne $pair[1]) { throw 'Prepared sandbox bytes differ from the frozen probe request.' }
        }
    }
}

function Get-AxiomProbeCaptureInventory([string]$Directory) {
    Assert-AxiomProbeOrdinaryPath $Directory 'directory' -MissingAllowed
    $inventory = @{}
    if (Test-Path -LiteralPath $Directory) {
        foreach ($file in @(Get-ChildItem -LiteralPath $Directory -Filter '*.json' -Force)) {
            Assert-AxiomProbeOrdinaryPath $file.FullName 'file'
            $inventory[$file.Name] = Get-AxiomProbeHash $file.FullName
        }
    }
    return $inventory
}

function Get-AxiomProbeNewCaptures([string]$Directory, $Before) {
    Assert-AxiomProbeOrdinaryPath $Directory 'directory' -MissingAllowed
    $new = @()
    if (Test-Path -LiteralPath $Directory) {
        foreach ($file in @(Get-ChildItem -LiteralPath $Directory -Filter '*.json' -Force)) {
            Assert-AxiomProbeOrdinaryPath $file.FullName 'file'
            if (-not $Before.ContainsKey($file.Name)) { $new += $file }
        }
    }
    return ,$new
}

function Assert-AxiomProbeExistingCapturesPreserved([string]$Directory, $Before) {
    foreach ($name in $Before.Keys) {
        $path = Join-Path $Directory $name
        if (-not (Test-Path -LiteralPath $path) -or (Get-AxiomProbeHash $path) -cne $Before[$name]) {
            throw 'An existing capture changed or disappeared during the probe attempt.'
        }
    }
}

# A malformed request cannot establish a trusted output path and fails without
# writing into an arbitrary supplied directory. The parent records that failure.
$request = Read-AxiomProbeRequest $RequestPath
$out = $request.attempt_directory
$requestHash = Get-AxiomProbeHash $RequestPath
$profileRoot = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox'
$profile = Join-Path $profileRoot 'geode/mods/axiom.native-capture'
$captures = Join-Path $profile 'captures'
$owned = $null
$lease = $null
$snapshot = $null
$beforeCaptures = $null
$prepared = $false
$retainedSourceName = $null
$manifest = [ordered]@{
    schema_version=1; kind='native_probe_attempt'; trial_id=$request.trial_id; status='runner_error'
    capture=$null; error=$null; timeout_reached=$false; process_cleanup=$null
    preservation=@(); cleanup_errors=@(); request_sha256=$requestHash
}

try {
    Assert-AxiomProbeNotCancelled $out
    Assert-AxiomProbeBelow $request.runtime_directory (Join-Path $request.workspace '.tools')
    Assert-AxiomProbeOrdinaryPath $request.runtime_directory 'directory' -MissingAllowed
    if (Test-Path -LiteralPath $request.runtime_directory) { throw 'Probe runtime must be new; previous runtime is preserved.' }
    Assert-AxiomProbeOrdinaryPath $request.game_directory 'directory'
    foreach ($path in @($request.native_package, $request.level_path, $request.replay_path,
            (Join-Path $request.game_directory 'GeometryDash.exe'), (Join-Path $request.game_directory 'Geode.dll'),
            (Join-Path $request.game_directory 'steam_appid.txt'))) {
        Assert-AxiomProbeOrdinaryPath $path 'file'
    }
    foreach ($sourceDll in @(Get-ChildItem -LiteralPath $request.game_directory -File -Filter '*.dll')) {
        Assert-AxiomProbeOrdinaryPath $sourceDll.FullName 'file'
    }
    Assert-AxiomProbeOrdinaryPath (Join-Path $request.game_directory 'Resources') 'directory'
    $loaderResources = Join-Path $request.game_directory 'geode/resources/geode.loader'
    if (Test-Path -LiteralPath $loaderResources) {
        Assert-AxiomProbeOrdinaryPath $loaderResources 'directory'
        foreach ($item in @(Get-ChildItem -LiteralPath $loaderResources -Recurse -Force)) {
            Assert-AxiomProbeOrdinaryPath $item.FullName $(if ($item.PSIsContainer) { 'directory' } else { 'file' })
        }
    }
    Assert-AxiomProbeOrdinaryPath $profileRoot 'directory' -MissingAllowed
    Assert-AxiomProbeOrdinaryPath $profile 'directory' -MissingAllowed
    Assert-AxiomProbeOrdinaryPath $captures 'directory' -MissingAllowed
    Assert-AxiomProbeFrozenInputs $request $requestHash
    $lease = Enter-AxiomProbeLease $profileRoot
    if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
        throw 'An active AXIOMSandbox process exists; this worker does not own it.'
    }
    Assert-AxiomProbeNotCancelled $out
    # Snapshot precedes preparation because even failed preparation can update
    # loader settings. Keep the lease through restoration and its byte checks.
    $snapshot = Get-AxiomExperimentSnapshot $request.workspace $request.runtime_directory
    $beforeCaptures = Get-AxiomProbeCaptureInventory $captures
    & (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $request.game_directory `
        -NativePackage $request.native_package -RuntimeDirectory $request.runtime_directory | Out-Null
    Assert-AxiomProbeNotCancelled $out
    Assert-AxiomProbeOrdinaryPath $profile 'directory' -MissingAllowed
    [void][IO.Directory]::CreateDirectory($profile)
    [void](Copy-AxiomProbeExactBytes $request.level_path (Join-Path $request.runtime_directory 'fixture-level.txt') `
        $request.level_sha256 1048576 -AllowExistingDestination)
    [void](Copy-AxiomProbeExactBytes $request.replay_path (Join-Path $profile 'replay.json') `
        $request.replay_file_sha256 16777216 -AllowExistingDestination)
    $prepared = $true
    Assert-AxiomProbeFrozenInputs $request $requestHash -Prepared
    Assert-AxiomProbeNotCancelled $out
    if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
        throw 'An AXIOMSandbox process appeared before launch; preserved without interference.'
    }
    $arguments = @('--geode:axiom-sandbox', '--geode:axiom.native-capture.capture',
        '--geode:axiom.native-capture.clock-policy=fixed-scheduler-240',
        '--geode:axiom.native-capture.input-driver=owned-pre-command', '--geode:axiom.native-capture.replay')
    $owned = Start-AxiomProbeOwnedProcess $request.workspace $out (Join-Path $request.runtime_directory 'AXIOMSandbox.exe') `
        $request.runtime_directory $arguments 'game' 'Normal'
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $candidateName = $null
    $candidateHash = $null
    $captureCopyError = $null
    while ($timer.Elapsed.TotalSeconds -lt $request.timeout_seconds) {
        Assert-AxiomProbeNotCancelled $out
        $new = Get-AxiomProbeNewCaptures $captures $beforeCaptures
        if ($new.Count -gt 1) { throw 'Multiple new captures were exported; no single attempt can be accepted.' }
        if ($new.Count -eq 1) {
            try {
                $observedHash = Get-AxiomProbeHash $new[0].FullName
                if ($new[0].Name -ceq $candidateName -and $observedHash -ceq $candidateHash) {
                    $digest = Copy-AxiomProbeExactBytes $new[0].FullName (Join-Path $out 'capture.json') $observedHash 16777216
                    $manifest.capture = [ordered]@{path='capture.json'; sha256=$digest}
                    $retainedSourceName = $new[0].Name
                    break
                }
                $candidateName = $new[0].Name; $candidateHash = $observedHash
            } catch [IO.IOException] {
                # A writer may still own the source. Poll again without creating
                # a replacement capture or extending the attempt deadline.
                if (Test-Path -LiteralPath (Join-Path $out 'capture.json')) { throw }
                $captureCopyError = $_.Exception.Message
                $candidateName = $null; $candidateHash = $null
            }
        } elseif ($owned.Process.HasExited) {
            throw "Owned sandbox exited before export (exit code $($owned.Process.ExitCode))."
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $manifest.capture) {
        $manifest.timeout_reached = $true
        $details = if ($captureCopyError) { " Last capture-read error: $captureCopyError" } else { '' }
        throw "Owned sandbox reached the $($request.timeout_seconds)-second deadline without a stable single export.$details"
    }
    Assert-AxiomProbeFrozenInputs $request $requestHash -Prepared
    Assert-AxiomProbeNotCancelled $out
    $manifest.status = 'capture_retained'
} catch {
    $manifest.error = $_.Exception.Message
    $manifest.cleanup_errors += @(Get-AxiomProbeExceptionCleanupErrors $_.Exception)
}
finally {
    $cleanup = Complete-AxiomProbeOwnedProcess $owned
    $manifest.process_cleanup = $cleanup.process_cleanup
    $manifest.cleanup_errors += @($cleanup.cleanup_errors)
    # Process termination closes the export interval. A second export appearing
    # during shutdown must invalidate an otherwise retained first capture.
    if ($null -ne $beforeCaptures) {
        try {
            $finalCaptures = Get-AxiomProbeNewCaptures $captures $beforeCaptures
            if ($manifest.capture -and ($finalCaptures.Count -ne 1 -or
                    $finalCaptures[0].Name -cne $retainedSourceName -or
                    (Get-AxiomProbeHash $finalCaptures[0].FullName) -cne $manifest.capture.sha256)) {
                throw 'Final exported capture set differs from the retained single source.'
            }
            Assert-AxiomProbeExistingCapturesPreserved $captures $beforeCaptures
            if ($prepared) { Assert-AxiomProbeFrozenInputs $request $requestHash -Prepared }
        } catch { $manifest.cleanup_errors += $_.Exception.Message }
    }
    if ($snapshot) {
        try {
            $preserved = Restore-AxiomProbeExperimentSnapshot $snapshot
            $manifest.preservation = @($preserved.files)
            $manifest.cleanup_errors += @($preserved.cleanup_errors)
            if (-not $preserved.all_preserved) { throw 'Four experiment files were not restored exactly.' }
        } catch { $manifest.cleanup_errors += $_.Exception.Message }
    }
    try { Exit-AxiomProbeLease $lease }
    catch { $manifest.cleanup_errors += $_.Exception.Message }
    try { Assert-AxiomProbeNotCancelled $out }
    catch { if (-not $manifest.error) { $manifest.error = $_.Exception.Message } }
    if ($manifest.cleanup_errors.Count -or $manifest.error -or -not $manifest.capture) {
        $manifest.status = 'runner_error'
        if (-not $manifest.error) {
            $manifest.error = if ($manifest.cleanup_errors.Count) { $manifest.cleanup_errors[0] } else { 'No native capture was retained.' }
        }
    }
    if ($manifest.error -and $manifest.error.Length -gt 1024) { $manifest.error = $manifest.error.Substring(0, 1024) }
    $manifest.cleanup_errors = @($manifest.cleanup_errors | ForEach-Object {
        if ($_.Length -gt 1024) { $_.Substring(0, 1024) } else { $_ }
    })
    Write-AxiomProbeFreshJson (Join-Path $out 'attempt.json') $manifest
}

if ($manifest.status -cne 'capture_retained') {
    Write-Error $manifest.error -ErrorAction Continue
    exit 2
}
Write-Output 'Native capture retained; the parent must validate its full-start terminal and frozen identities.'
exit 0
