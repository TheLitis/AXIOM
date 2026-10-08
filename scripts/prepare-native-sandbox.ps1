param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [string]$NativePackage
)

# Copies local, legally installed binaries into an ignored test directory.
# Does not launch, modify the original installation, or copy personal saves.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $workspace '.tools/runtime'
function Assert-OrdinaryDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Sandbox directory must not be a file or reparse point: $Path"
        }
    }
}
function Assert-OrdinaryFile([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if ($item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "Sandbox file must not be a directory or reparse point: $Path"
        }
    }
}
Assert-OrdinaryDirectory (Join-Path $workspace '.tools')
Assert-OrdinaryDirectory $runtimeDir
Assert-OrdinaryDirectory (Join-Path $runtimeDir 'sandbox-saves')
Assert-OrdinaryDirectory (Join-Path $runtimeDir 'geode')
Assert-OrdinaryDirectory (Join-Path $runtimeDir 'geode/mods')
$geodeSaveRoot = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox'
Assert-OrdinaryDirectory $geodeSaveRoot
Assert-OrdinaryDirectory (Join-Path $geodeSaveRoot 'geode')
Assert-OrdinaryDirectory (Join-Path $geodeSaveRoot 'geode/mods')
Assert-OrdinaryDirectory (Join-Path $geodeSaveRoot 'geode/mods/axiom.native-capture')
Assert-OrdinaryDirectory (Join-Path $geodeSaveRoot 'geode/mods/axiom.native-capture/captures')
Assert-OrdinaryDirectory (Join-Path $geodeSaveRoot 'geode/mods/geode.loader')
Assert-OrdinaryFile (Join-Path $geodeSaveRoot 'geode/mods/axiom.native-capture/replay.json')
Assert-OrdinaryFile (Join-Path $runtimeDir 'fixture-level.txt')
if (Test-Path -LiteralPath (Join-Path $runtimeDir 'geode/update')) {
    throw 'Pending sandbox loader update would change the pinned runtime; preserve it separately before testing.'
}
$loaderProfile = Join-Path $geodeSaveRoot 'geode/mods/geode.loader'
New-Item -ItemType Directory -Force $loaderProfile | Out-Null
$loaderSettingsPath = Join-Path $loaderProfile 'settings.json'
Assert-OrdinaryFile $loaderSettingsPath
$loaderSettings = @{}
if (Test-Path -LiteralPath $loaderSettingsPath) {
    $existingSettings = Get-Content -LiteralPath $loaderSettingsPath -Raw | ConvertFrom-Json
    foreach ($property in $existingSettings.PSObject.Properties) {
        $loaderSettings[$property.Name] = $property.Value
    }
}
$loaderSettings['auto-check-updates'] = $false
[System.IO.File]::WriteAllText($loaderSettingsPath, ($loaderSettings | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
$gameDir = (Resolve-Path -LiteralPath $GameDirectory).Path
$gameExe = Join-Path $gameDir 'GeometryDash.exe'
$expectedGameHash = 'fc5a16c292278bc2e8e078fb1d5023c2bd658322dd72712767ea70c2dd9ec6d0'
if ((Get-FileHash -LiteralPath $gameExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedGameHash) {
    throw 'This sandbox fixture has only been scoped to the pinned GD 2.2081 game binary.'
}
$expectedLoaderHash = '61847e05d4aa416bfd4d1f4e026b5b0e66848756473b285add6233a5cc9356d2'
if ((Get-FileHash -LiteralPath (Join-Path $gameDir 'Geode.dll') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedLoaderHash) {
    throw 'This sandbox fixture requires the pinned Geode 5.8.2 loader binary.'
}
if (-not $NativePackage) { $NativePackage = Join-Path $workspace 'native/build/axiom.native-capture.geode' }
$packagePath = (Resolve-Path -LiteralPath $NativePackage).Path
New-Item -ItemType Directory -Force $runtimeDir | Out-Null
Copy-Item -LiteralPath $gameExe -Destination (Join-Path $runtimeDir 'AXIOMSandbox.exe') -Force
Get-ChildItem -LiteralPath $gameDir -File -Filter '*.dll' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $runtimeDir -Force
}
Copy-Item -LiteralPath (Join-Path $gameDir 'steam_appid.txt') -Destination $runtimeDir -Force
$resources = Join-Path $runtimeDir 'Resources'
$sourceResources = Join-Path $gameDir 'Resources'
if (Test-Path -LiteralPath $resources) {
    $existing = Get-Item -LiteralPath $resources
    if ($existing.LinkType -ne 'Junction' -or $existing.Target -ne $sourceResources) {
        throw 'Existing sandbox Resources is not the expected junction; preserved without replacement.'
    }
} else {
    New-Item -ItemType Junction -Path $resources -Target $sourceResources | Out-Null
}
$mods = Join-Path $runtimeDir 'geode/mods'
New-Item -ItemType Directory -Force $mods | Out-Null
if (Get-ChildItem -LiteralPath $mods -File | Where-Object Name -ne 'axiom.native-capture.geode') {
    throw 'Unexpected mod in sandbox; preserve it and use a clean test directory.'
}
Copy-Item -LiteralPath $packagePath -Destination (Join-Path $mods 'axiom.native-capture.geode') -Force
$loaderResources = Join-Path $gameDir 'geode/resources/geode.loader'
if (Test-Path -LiteralPath $loaderResources) {
    $resourceDest = Join-Path $runtimeDir 'geode/resources'
    New-Item -ItemType Directory -Force $resourceDest | Out-Null
    Copy-Item -LiteralPath $loaderResources -Destination $resourceDest -Recurse -Force
}
$fixture = 'kA13,0,kA15,0,kA16,0,kA14,0;1,1,2,600,3,-15;'
[System.IO.File]::WriteAllText((Join-Path $runtimeDir 'fixture-level.txt'), $fixture, [System.Text.UTF8Encoding]::new($false))
Write-Output "Sandbox prepared at $runtimeDir"
Write-Output 'Explicit test launch: AXIOMSandbox.exe --geode:axiom-sandbox'
Write-Output 'The sandbox-only save redirection must pass its runtime check before the fixture starts.'
