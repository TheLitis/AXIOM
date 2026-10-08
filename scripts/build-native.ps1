param(
    [string]$CMakePath,
    [ValidateRange(1, 16)][int]$Jobs = 4
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $workspace '.tools'
$sdkDir = Join-Path $toolsDir 'geode-sdk'
$bindingsDir = Join-Path $toolsDir 'bindings'
$cliDir = Join-Path $toolsDir 'geode-cli'
$sdkCommit = '2a5fd87433da47d6bf07221774f0cbb25535ae08'
$bindingsCommit = '2a8b5c489ce8b49e7061b0543aa2bc5b22570063'

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}

function Ensure-Checkout([string]$Destination, [string]$Repository, [string]$Commit) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Invoke-Checked 'git' @('clone', '--filter=blob:none', '--no-checkout', $Repository, $Destination)
        Invoke-Checked 'git' @('-C', $Destination, 'checkout', '--detach', $Commit)
    }
    $actual = (& git -C $Destination rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $Commit) {
        throw "Expected pinned commit $Commit at $Destination; existing checkout was preserved."
    }
    if (& git -C $Destination status --porcelain --untracked-files=no) {
        throw "Tracked changes in dependency checkout $Destination; preserved without reset."
    }
}

function Ensure-Archive([string]$Url, [string]$Destination, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Invoke-WebRequest -Uri $Url -OutFile $Destination
    }
    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $ExpectedHash) { throw "SHA-256 mismatch for $Destination" }
}

New-Item -ItemType Directory -Force $toolsDir, $cliDir | Out-Null
Ensure-Checkout $sdkDir 'https://github.com/geode-sdk/geode.git' $sdkCommit
Ensure-Checkout $bindingsDir 'https://github.com/geode-sdk/bindings.git' $bindingsCommit

$cliArchive = Join-Path $cliDir 'geode-cli-v3.9.0-win.zip'
Ensure-Archive 'https://github.com/geode-sdk/cli/releases/download/v3.9.0/geode-cli-v3.9.0-win.zip' $cliArchive 'ce7eaaa6766ae350a33d6cc1371c20644dfc489cd32a6cd33b4d15c673e1c858'
Expand-Archive -LiteralPath $cliArchive -DestinationPath $cliDir -Force
$loaderArchive = Join-Path $toolsDir 'geode-v5.8.2-win.zip'
Ensure-Archive 'https://github.com/geode-sdk/geode/releases/download/v5.8.2/geode-v5.8.2-win.zip' $loaderArchive '95b9470032f71560205e51c776081be24dd8572f3094acf2d4d13f1abd5aa16c'
$loaderDir = Join-Path $toolsDir 'loader-5.8.2'
Expand-Archive -LiteralPath $loaderArchive -DestinationPath $loaderDir -Force
$importDir = Join-Path $sdkDir 'bin/5.8.2'
New-Item -ItemType Directory -Force $importDir | Out-Null
Copy-Item -LiteralPath (Join-Path $loaderDir 'Geode.lib') -Destination $importDir -Force

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio with x64 C++ build tools is required.' }
$vsInstall = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json)[0]
if (-not $vsInstall) { throw 'No installed Visual Studio x64 C++ build tools found.' }
$vsMajor = ([version]$vsInstall.installationVersion).Major
$generator = switch ($vsMajor) {
    18 { 'Visual Studio 18 2026' }
    17 { 'Visual Studio 17 2022' }
    default { throw "Unsupported Visual Studio generation $vsMajor" }
}
if (-not $CMakePath) {
    $bundled = Join-Path $vsInstall.installationPath 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    if (Test-Path -LiteralPath $bundled) { $CMakePath = $bundled }
    else { $CMakePath = (Get-Command cmake -ErrorAction Stop).Source }
}
$buildDir = Join-Path $workspace 'native/build'
Invoke-Checked $CMakePath @(
    '-S', (Join-Path $workspace 'native'), '-B', $buildDir,
    '-G', $generator, '-A', 'x64',
    "-DGEODE_SDK=$sdkDir", "-DGEODE_BINDINGS_REPO_PATH=$bindingsDir",
    "-DGEODE_CLI=$(Join-Path $cliDir 'geode.exe')",
    '-DGEODE_DONT_UPDATE_INDEX=OFF', '-DGEODE_DONT_INSTALL_MODS=ON', '-DSKIP_BUILDING_CODEGEN=OFF',
    "-DAXIOM_SDK_COMMIT=$sdkCommit", "-DAXIOM_BINDINGS_COMMIT=$bindingsCommit",
    "-DCPM_SOURCE_CACHE=$(Join-Path $toolsDir 'cpm-cache')"
)
Invoke-Checked $CMakePath @('--build', $buildDir, '--config', 'Release', '--parallel', "$Jobs")
Write-Output "Native package built in $buildDir. Installation and game launch are separate operations."
