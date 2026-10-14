# Headless console integration checks. No game, UI window or device input.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'native-startup.ps1')
$out = Join-Path $workspace ('reports/startup-console-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $out | Out-Null
$runtime = Join-Path $out 'runtime'
New-Item -ItemType Directory -Path $runtime | Out-Null
$inventory = Join-Path $out 'inventory.json'
$checks = @()
$success = Invoke-AxiomStartupTool $workspace $out @('native-startup-baseline', $runtime, '--output', $inventory) 'startup-baseline'
if ($success.exit_code -ne 0 -or -not (Test-Path -LiteralPath $inventory -PathType Leaf)) {
    throw 'Fast successful console exit did not preserve its inventory.'
}
$checks += 'fast_console_exit_zero_and_inventory'
$beforeHash = (Get-FileHash -LiteralPath $success.stdout_path -Algorithm SHA256).Hash
$expectedFailure = $false
try {
    Invoke-AxiomStartupTool $workspace $out @('native-startup', (Join-Path $out 'missing-bundle.json')) 'startup-missing' | Out-Null
} catch {
    if ($_.Exception.Message -notmatch 'code 2;') { throw }
    $expectedFailure = $true
}
if (-not $expectedFailure -or -not (Get-Item -LiteralPath (Join-Path $out 'startup-missing.stderr.txt')).Length) {
    throw 'Fast nonzero console exit did not retain its error and exit code.'
}
$checks += 'fast_console_exit_two_and_retained_stderr'
$expectedFailure = $false
try {
    Invoke-AxiomStartupTool $workspace $out @('native-startup-baseline', $runtime, '--output', $inventory) 'startup-baseline' | Out-Null
} catch {
    if ($_.Exception.Message -notmatch 'Previous startup console evidence') { throw }
    $expectedFailure = $true
}
if (-not $expectedFailure -or (Get-FileHash -LiteralPath $success.stdout_path -Algorithm SHA256).Hash -ne $beforeHash) {
    throw 'Existing diagnostic console evidence was not preserved.'
}
$checks += 'existing_console_logs_rejected_unchanged'
$expectedFailure = $false
try {
    Invoke-AxiomStartupTool $workspace ([IO.Path]::GetTempPath()) @('native-startup', 'unused') 'startup-outside' | Out-Null
} catch {
    if ($_.Exception.Message -notmatch 'within this workspace') { throw }
    $expectedFailure = $true
}
if (-not $expectedFailure) { throw 'Outside-workspace diagnostic console path was accepted.' }
$checks += 'outside_workspace_rejected_before_process'
$result = [ordered]@{
    kind='headless_startup_console_integration'; status='passed'; checks=$checks
    evidence_directory=$out; game_launched=$false; os_input_injected=$false
}
[IO.File]::WriteAllText((Join-Path $out 'result.json'), ($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Output ($result | ConvertTo-Json -Depth 8)
