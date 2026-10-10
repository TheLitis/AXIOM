# Local state preservation for the explicitly isolated experiment profile.
function Assert-AxiomExperimentPaths([string]$Workspace, [string]$RuntimeDirectory) {
    if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $Workspace '.tools/runtime' }
    $toolsRoot = [IO.Path]::GetFullPath((Join-Path $Workspace '.tools')).TrimEnd([char[]]'\/')
    $RuntimeDirectory = [IO.Path]::GetFullPath($RuntimeDirectory)
    if (-not $RuntimeDirectory.StartsWith($toolsRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Experiment runtime must remain below workspace .tools.'
    }
    $ancestor = $RuntimeDirectory
    while ($ancestor -ne $toolsRoot) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Experiment runtime ancestor is redirected or is a file: $ancestor"
            }
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    $profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox'
    $directories = @((Join-Path $Workspace '.tools'), $RuntimeDirectory,
        $profile, (Join-Path $profile 'geode'), (Join-Path $profile 'geode/mods'),
        (Join-Path $profile 'geode/mods/axiom.native-capture'),
        (Join-Path $profile 'geode/mods/geode.loader'))
    foreach ($path in $directories) {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path -Force
            if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Experiment directory is redirected or is a file: $path"
            }
        }
    }
}

function Get-AxiomExperimentSnapshot([string]$Workspace, [string]$RuntimeDirectory) {
    if (-not $RuntimeDirectory) { $RuntimeDirectory = Join-Path $Workspace '.tools/runtime' }
    $RuntimeDirectory = [IO.Path]::GetFullPath($RuntimeDirectory)
    Assert-AxiomExperimentPaths $Workspace $RuntimeDirectory
    $profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods'
    $paths = @((Join-Path $RuntimeDirectory 'fixture-level.txt'),
        (Join-Path $profile 'axiom.native-capture/replay.json'),
        (Join-Path $profile 'axiom.native-capture/settings.json'),
        (Join-Path $profile 'geode.loader/settings.json'))
    $files = @()
    foreach ($path in $paths) {
        $exists = Test-Path -LiteralPath $path
        [byte[]]$bytes = @()
        if ($exists) {
            $item = Get-Item -LiteralPath $path -Force
            if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Experiment file is redirected or is a directory: $path"
            }
            $bytes = [IO.File]::ReadAllBytes($path)
        }
        $files += [pscustomobject]@{ Path = $path; Existed = $exists; Bytes = $bytes }
    }
    return [pscustomobject]@{ Workspace = $Workspace; RuntimeDirectory = $RuntimeDirectory; Files = $files }
}

function Restore-AxiomExperimentSnapshot($Snapshot) {
    Assert-AxiomExperimentPaths $Snapshot.Workspace $Snapshot.RuntimeDirectory
    foreach ($file in $Snapshot.Files) {
        if (Test-Path -LiteralPath $file.Path) {
            $item = Get-Item -LiteralPath $file.Path -Force
            if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw "Refusing to restore a redirected experiment file: $($file.Path)"
            }
        }
        if ($file.Existed) { [IO.File]::WriteAllBytes($file.Path, [byte[]]$file.Bytes) }
        elseif (Test-Path -LiteralPath $file.Path) { Remove-Item -LiteralPath $file.Path }
    }
}

function Test-AxiomExperimentSnapshot($Snapshot) {
    # Report byte/existence equality for these four files only. This is not a
    # complete personal-save or machine-state preservation claim.
    Assert-AxiomExperimentPaths $Snapshot.Workspace $Snapshot.RuntimeDirectory
    $files = @()
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        foreach ($file in $Snapshot.Files) {
            $exists = Test-Path -LiteralPath $file.Path
            $beforeHash = if ($file.Existed) { [BitConverter]::ToString($hasher.ComputeHash([byte[]]$file.Bytes)).Replace('-', '').ToLowerInvariant() } else { $null }
            $afterHash = if ($exists) { (Get-FileHash -LiteralPath $file.Path -Algorithm SHA256).Hash.ToLowerInvariant() } else { $null }
            $files += [ordered]@{path=$file.Path; existed_before=$file.Existed; exists_after=$exists;
                sha256_before=$beforeHash; sha256_after=$afterHash; preserved=($file.Existed -eq $exists -and $beforeHash -eq $afterHash)}
        }
    } finally { $hasher.Dispose() }
    return [ordered]@{scope='four_experiment_files_only'; all_preserved=(@($files | Where-Object { -not $_.preserved }).Count -eq 0); files=$files}
}
