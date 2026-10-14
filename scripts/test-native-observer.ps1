param(
    [string]$CMakePath,
    [string]$JsonSourceDirectory,
    [string]$ResultSourceDirectory,
    [ValidateRange(1, 16)][int]$Jobs = 4
)

$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$testSource = Join-Path $workspace 'native/tests/windows-observer'

function Find-AxiomDependency([string]$Name, [string]$Provided) {
    if ($Provided) { return [System.IO.Path]::GetFullPath($Provided) }
    $cache = Join-Path $workspace ('.tools/cpm-cache/' + $Name)
    if (-not (Test-Path -LiteralPath $cache -PathType Container)) {
        throw "Existing $Name dependency source is required. Run build-native.ps1 first, or pass its source directory."
    }
    $candidates = @(Get-ChildItem -LiteralPath $cache -Directory | Where-Object {
        Test-Path -LiteralPath (Join-Path $_.FullName 'CMakeLists.txt') -PathType Leaf
    })
    if ($candidates.Count -ne 1) {
        throw "No unique existing $Name source; pass its explicit source directory."
    }
    return $candidates[0].FullName
}

$JsonSourceDirectory = Find-AxiomDependency 'json' $JsonSourceDirectory
$ResultSourceDirectory = Find-AxiomDependency 'result' $ResultSourceDirectory
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
    throw 'Visual Studio x64 C++ tools are required for the software-only observer checks.'
}
$vsInstall = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -format json | ConvertFrom-Json)[0]
if (-not $vsInstall) { throw 'No Visual Studio x64 C++ installation found.' }
$generator = switch (([version]$vsInstall.installationVersion).Major) {
    18 { 'Visual Studio 18 2026' }
    17 { 'Visual Studio 17 2022' }
    default { throw 'Unsupported Visual Studio generation.' }
}
if (-not $CMakePath) {
    $CMakePath = Join-Path $vsInstall.installationPath 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    if (-not (Test-Path -LiteralPath $CMakePath)) { $CMakePath = (Get-Command cmake -ErrorAction Stop).Source }
}

# Always use a fresh ignored directory. The main Geode build, package marker,
# game/runtime/profile files and previous test results are never modified.
$tools = Join-Path $workspace '.tools'
if (Test-Path -LiteralPath $tools) {
    $item = Get-Item -LiteralPath $tools -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Test output .tools must be an ordinary workspace directory.'
    }
} else { New-Item -ItemType Directory -Path $tools | Out-Null }
$output = Join-Path $tools ('windows-observer-tests-' + [guid]::NewGuid().ToString('N'))
if (Test-Path -LiteralPath $output) { throw 'Fresh test output unexpectedly exists.' }
New-Item -ItemType Directory -Path $output | Out-Null
$sourceFiles = @(
    (Join-Path $workspace 'native/src/WindowsInputObserver.cpp'),
    (Join-Path $workspace 'native/src/WindowsInputObserver.hpp'),
    $PSCommandPath
) + @(Get-ChildItem -LiteralPath $testSource -Recurse -File | ForEach-Object FullName)
$dependencyFiles = @(
    (Join-Path $JsonSourceDirectory 'CMakeLists.txt'),
    (Join-Path $ResultSourceDirectory 'CMakeLists.txt')
) + @(Get-ChildItem -LiteralPath (Join-Path $JsonSourceDirectory 'include'),(Join-Path $JsonSourceDirectory 'src'),(Join-Path $ResultSourceDirectory 'include') -Recurse -File | ForEach-Object FullName)
$dependencyBefore = @{}
foreach ($path in $dependencyFiles) { $dependencyBefore[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$before = @{}
foreach ($path in $sourceFiles) { $before[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$utf8 = [System.Text.UTF8Encoding]::new($false)

& $CMakePath -S $testSource -B (Join-Path $output 'build') -G $generator -A x64 "-DAXIOM_JSON_SOURCE_DIR=$JsonSourceDirectory" "-DAXIOM_RESULT_SOURCE_DIR=$ResultSourceDirectory" *> (Join-Path $output 'configure.log')
if ($LASTEXITCODE -ne 0) { throw "Observer test configuration failed; preserved log: $output/configure.log" }
& $CMakePath --build (Join-Path $output 'build') --config Release --parallel $Jobs *> (Join-Path $output 'build.log')
if ($LASTEXITCODE -ne 0) { throw "Observer test build failed; preserved log: $output/build.log" }
$executable = Join-Path $output 'build/Release/axiom_windows_observer_fault_tests.exe'
$lines = @(& $executable 2> (Join-Path $output 'stderr.log'))
$testExit = $LASTEXITCODE
$resultPath = Join-Path $output 'checks.json'
[System.IO.File]::WriteAllText($resultPath, ($lines -join "`n") + "`n", $utf8)
$result = ($lines -join "`n") | ConvertFrom-Json
$after = @{}
foreach ($path in $sourceFiles) { $after[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$unchanged = @($before.Keys | Where-Object { $before[$_] -ne $after[$_] }).Count -eq 0
$dependencyAfter = @{}
foreach ($path in $dependencyFiles) { $dependencyAfter[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
$dependenciesUnchanged = @($dependencyBefore.Keys | Where-Object { $dependencyBefore[$_] -ne $dependencyAfter[$_] }).Count -eq 0
$manifest = [ordered]@{
    schema_version = 1
    kind = 'software_only_windows_observer_fault_test_manifest'
    scope = 'actual_observer_source_with_fake_Win32_and_Geode_window_clock'
    live_windows_qualification = 'not_established'
    gd_launched = $false
    source_sha256_before = $before
    source_sha256_after = $after
    sources_unchanged = $unchanged
    dependency_sources = @{ json = $JsonSourceDirectory; result = $ResultSourceDirectory }
    dependency_source_sha256_before = $dependencyBefore
    dependency_source_sha256_after = $dependencyAfter
    dependency_sources_unchanged = $dependenciesUnchanged
    generator = $generator
    executable_sha256 = (Get-FileHash -LiteralPath $executable -Algorithm SHA256).Hash.ToLowerInvariant()
    check_report_sha256 = (Get-FileHash -LiteralPath $resultPath -Algorithm SHA256).Hash.ToLowerInvariant()
    exit_code = $testExit
    case_count = $result.case_count
    check_count = $result.check_count
    failed_cases = $result.failed_cases
}
[System.IO.File]::WriteAllText((Join-Path $output 'manifest.json'), ($manifest | ConvertTo-Json -Depth 8) + "`n", $utf8)
Write-Output "Software-only observer checks: $($result.case_count) cases, $($result.check_count) checks, $($result.failed_cases) failed cases."
Write-Output "Preserved results: $output"
if (-not $unchanged -or -not $dependenciesUnchanged -or $testExit -ne 0 -or $result.failed_cases -ne 0) {
    throw 'Software-only observer fault checks failed; retained report is not live qualification.'
}
