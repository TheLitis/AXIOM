# Local state preservation for the explicitly isolated experiment profile.
function Assert-AxiomExperimentPaths([string]$Workspace) {
    $profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox'
    $directories = @((Join-Path $Workspace '.tools'), (Join-Path $Workspace '.tools/runtime'),
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

function Get-AxiomExperimentSnapshot([string]$Workspace) {
    Assert-AxiomExperimentPaths $Workspace
    $profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods'
    $paths = @((Join-Path $Workspace '.tools/runtime/fixture-level.txt'),
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
    return [pscustomobject]@{ Workspace = $Workspace; Files = $files }
}

function Restore-AxiomExperimentSnapshot($Snapshot) {
    Assert-AxiomExperimentPaths $Snapshot.Workspace
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
