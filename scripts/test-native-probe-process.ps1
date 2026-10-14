# Real headless process integration checks. No game or device-input injection.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'native-probe-process.ps1')
$python = Join-Path $workspace '.venv/Scripts/python.exe'
Assert-AxiomProbeOrdinaryPath $python 'file'
$out = Join-Path $workspace ('reports/probe-process-test-' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($out)
$checks = @()
$utf8 = [Text.UTF8Encoding]::new($false)

function Assert-ProbeCheck([bool]$Condition, [string]$Name) {
    if (-not $Condition) { throw "Headless native probe check failed: $Name" }
    $script:checks += $Name
}

$success = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
    @('-I', '-c', 'print("fast successful exit", flush=True)') 'success' 10
Assert-ProbeCheck ($success.status -ceq 'completed' -and $success.exit_code -eq 0 -and
    $success.process_cleanup.exit_observed_before_cleanup -and
    -not $success.process_cleanup.termination_requested -and
    $success.process_cleanup.natural_exit_code -eq 0 -and -not $success.cleanup_errors.Count -and
    [IO.File]::ReadAllText($success.stdout_path).Contains('fast successful exit')) 'fast_exit_zero_retains_stdout_and_natural_exit'

$failure = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
    @('-I', '-c', 'import sys; sys.stderr.write("intentional failure\n"); sys.exit(2)') 'failure' 10
Assert-ProbeCheck ($failure.status -ceq 'runner_error' -and $failure.exit_code -eq 2 -and
    $failure.process_cleanup.exit_observed_before_cleanup -and
    -not $failure.process_cleanup.termination_requested -and
    $failure.process_cleanup.natural_exit_code -eq 2 -and
    [IO.File]::ReadAllText($failure.stderr_path).Contains('intentional failure')) 'fast_exit_two_retains_stderr_without_cleanup_relabeling'

$sentinel = $null
try {
    $sentinel = Start-AxiomProbeOwnedProcess $workspace $out $python $workspace `
        @('-I', '-c', 'import time; print("sentinel alive", flush=True); time.sleep(30)') 'sentinel' 'Hidden'
    $timeout = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
        @('-I', '-c', 'import time; print("timeout alive", flush=True); time.sleep(30)') 'timeout' 1
    Assert-ProbeCheck ($timeout.status -ceq 'runner_error' -and $timeout.timeout_reached -and
        $null -eq $timeout.exit_code -and $timeout.process_cleanup.termination_requested -and
        -not $timeout.process_cleanup.exit_observed_before_cleanup -and
        $null -eq $timeout.process_cleanup.natural_exit_code -and -not $timeout.cleanup_errors.Count -and
        -not $sentinel.Process.HasExited) 'deadline_stops_only_owned_process_and_preserves_primary_timeout'
} finally {
    $sentinelCleanup = Complete-AxiomProbeOwnedProcess $sentinel
    if ($sentinelCleanup.cleanup_errors.Count) { throw ($sentinelCleanup.cleanup_errors -join '; ') }
}

$stdoutBefore = Get-AxiomProbeHash $success.stdout_path
$stderrBefore = Get-AxiomProbeHash $success.stderr_path
$collision = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
    @('-I', '-c', 'raise RuntimeError("must never start")') 'success' 10
Assert-ProbeCheck ($collision.status -ceq 'runner_error' -and $null -eq $collision.process_cleanup -and
    $collision.error.Contains('Previous probe console evidence') -and
    (Get-AxiomProbeHash $success.stdout_path) -ceq $stdoutBefore -and
    (Get-AxiomProbeHash $success.stderr_path) -ceq $stderrBefore) 'existing_console_outputs_rejected_unchanged'

$outside = Invoke-AxiomProbeConsoleProcess $workspace ([IO.Path]::GetTempPath()) $python $workspace `
    @('-I', '-c', 'raise RuntimeError("must never start")') 'outside' 10
Assert-ProbeCheck ($outside.status -ceq 'runner_error' -and $null -eq $outside.process_cleanup -and
    $outside.error.Contains('intended root')) 'outside_workspace_refused_before_process_creation'

$unicodeArgument = -join [char[]]@(0x043A, 0x0438, 0x0440, 0x0438, 0x043B, 0x043B, 0x0438, 0x0446, 0x0430)
$argumentValues = @('space value', 'embedded "quote" value', 'terminal\', '', $unicodeArgument)
$quoting = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
    (@('-I', '-c', 'import json, sys; print(json.dumps(sys.argv[1:], ensure_ascii=True))') + $argumentValues) 'arguments' 10
$observedArguments = [IO.File]::ReadAllText($quoting.stdout_path) | ConvertFrom-Json
Assert-ProbeCheck ($quoting.status -ceq 'completed' -and
    -not @(Compare-Object $argumentValues @($observedArguments) -CaseSensitive).Count -and
    $observedArguments.Count -eq $argumentValues.Count) 'win32_arguments_preserve_spaces_quotes_slashes_empty_and_unicode'

$jobChild = $null
try {
    $jobChild = Start-AxiomProbeOwnedProcess $workspace $out $python $workspace `
        @('-I', '-c', 'import time; print("job child alive", flush=True); time.sleep(30)') 'job-close' 'Hidden'
    Start-Sleep -Milliseconds 150
    $jobChild.Job.Dispose()
    Assert-ProbeCheck ($jobChild.Process.WaitForExit(5000)) 'closing_owned_job_terminates_its_child'
} finally {
    $jobCleanup = Complete-AxiomProbeOwnedProcess $jobChild
    if ($jobCleanup.cleanup_errors.Count) { throw ($jobCleanup.cleanup_errors -join '; ') }
}

$immediateDescendant = $null
$descendant = $null
$unrelated = $null
try {
    $unrelated = Start-AxiomProbeOwnedProcess $workspace $out $python $workspace `
        @('-I', '-c', 'import time; time.sleep(30)') 'unrelated-tree' 'Hidden'
    $descendantPidPath = Join-Path $out 'immediate-descendant.pid'
    $spawnCode = 'import pathlib, subprocess, sys, time; child = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(30)"]); pathlib.Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(30)'
    $immediateDescendant = Start-AxiomProbeOwnedProcess $workspace $out $python $workspace `
        @('-I', '-c', $spawnCode, $descendantPidPath) 'immediate-tree' 'Hidden'
    $wait = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-Path -LiteralPath $descendantPidPath) -and $wait.Elapsed.TotalSeconds -lt 5) { Start-Sleep -Milliseconds 25 }
    if (-not (Test-Path -LiteralPath $descendantPidPath)) { throw 'Owned console did not report its immediate descendant.' }
    # This object is for membership/exit inspection only. Job ownership handles
    # termination; the test never resolves a PID to stop an unrelated process.
    $descendant = [Diagnostics.Process]::GetProcessById([int][IO.File]::ReadAllText($descendantPidPath))
    $descendantHandle = $descendant.Handle
    Assert-ProbeCheck ($immediateDescendant.Job.Contains($descendant) -and
        -not $immediateDescendant.Job.Contains($unrelated.Process)) 'immediate_descendant_is_in_owned_job_before_any_application_spawn'
    $treeCleanup = Complete-AxiomProbeOwnedProcess $immediateDescendant
    $immediateDescendant = $null
    Assert-ProbeCheck (-not $treeCleanup.cleanup_errors.Count -and $descendant.HasExited -and
        -not $unrelated.Process.HasExited) 'job_cleanup_drains_descendants_and_preserves_unrelated_process'
} finally {
    foreach ($ownedTree in @($immediateDescendant, $unrelated)) {
        $treeCleanup = Complete-AxiomProbeOwnedProcess $ownedTree
        if ($treeCleanup.cleanup_errors.Count) { throw ($treeCleanup.cleanup_errors -join '; ') }
    }
    if ($descendant) { $descendant.Dispose() }
}

$invalidExecutable = Join-Path $out 'invalid.exe'
[IO.File]::WriteAllBytes($invalidExecutable, [byte[]]@(0, 1, 2, 3))
$failedCreation = Invoke-AxiomProbeConsoleProcess $workspace $out $invalidExecutable $workspace @() 'failed-create' 1
$handlesReleased = $true
foreach ($path in @((Join-Path $out 'failed-create.stdout.txt'), (Join-Path $out 'failed-create.stderr.txt'))) {
    try {
        $probeStream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        $probeStream.Dispose()
    } catch { $handlesReleased = $false }
}
Assert-ProbeCheck ($failedCreation.status -ceq 'runner_error' -and $null -eq $failedCreation.process_cleanup -and
    $handlesReleased) 'failed_suspended_creation_releases_redirected_handles'

$leaseProfile = Join-Path $out 'lease-profile'
$leaseChildScript = Join-Path $out 'lease-child.ps1'
$helperPath = (Join-Path $PSScriptRoot 'native-probe-process.ps1').Replace("'", "''")
$leasePath = $leaseProfile.Replace("'", "''")
$childBody = '$ErrorActionPreference = ''Stop'';' + [Environment]::NewLine +
    ". '$helperPath'" + [Environment]::NewLine +
    "`$lease = Enter-AxiomProbeLease '$leasePath'" + [Environment]::NewLine +
    'Exit-AxiomProbeLease $lease' + [Environment]::NewLine
[IO.File]::WriteAllText($leaseChildScript, $childBody, $utf8)
$powershell = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$lease = Enter-AxiomProbeLease $leaseProfile
try {
    $contender = Invoke-AxiomProbeConsoleProcess $workspace $out $powershell $workspace `
        @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $leaseChildScript) 'lease-contender' 10
    Assert-ProbeCheck ($contender.status -ceq 'runner_error' -and
        [IO.File]::ReadAllText($contender.stderr_path).Contains('owns the sandbox profile lease')) 'profile_lease_refuses_another_process'
} finally { Exit-AxiomProbeLease $lease }
$secondLease = Enter-AxiomProbeLease $leaseProfile
Exit-AxiomProbeLease $secondLease
Assert-ProbeCheck $true 'profile_lease_is_available_after_owned_release'

$binarySource = Join-Path $out 'raw-source.bin'
$binaryTarget = Join-Path $out 'raw-retained.bin'
[IO.File]::WriteAllBytes($binarySource, [byte[]]@(239, 187, 191, 123, 13, 10, 32, 255, 0, 125))
$binaryHash = Get-AxiomProbeHash $binarySource
$copiedHash = Copy-AxiomProbeExactBytes $binarySource $binaryTarget $binaryHash
Assert-ProbeCheck ($copiedHash -ceq $binaryHash -and (Get-AxiomProbeHash $binaryTarget) -ceq $binaryHash) 'raw_byte_copy_preserves_bom_crlf_non_utf8_and_nul'
$copyCollision = $false
try { [void](Copy-AxiomProbeExactBytes $binarySource $binaryTarget $binaryHash) }
catch { $copyCollision = $_.Exception.Message.Contains('Previous probe bytes') }
Assert-ProbeCheck ($copyCollision -and (Get-AxiomProbeHash $binaryTarget) -ceq $binaryHash) 'raw_byte_copy_rejects_destination_collision'
$wrongHashTarget = Join-Path $out 'wrong-hash.bin'
$wrongHash = $false
try { [void](Copy-AxiomProbeExactBytes $binarySource $wrongHashTarget ('0' * 64)) }
catch { $wrongHash = $_.Exception.Message.Contains('frozen request') }
Assert-ProbeCheck ($wrongHash -and -not (Test-Path -LiteralPath $wrongHashTarget)) 'wrong_source_hash_refused_before_destination_write'

$cancelDirectory = Join-Path $out 'cancel-check'
[void][IO.Directory]::CreateDirectory($cancelDirectory)
Assert-AxiomProbeNotCancelled $cancelDirectory
Write-AxiomProbeFreshJson (Join-Path $cancelDirectory 'cancel.request.json') @{reason='headless integration'}
$cancelled = $false
try { Assert-AxiomProbeNotCancelled $cancelDirectory }
catch { $cancelled = $_.Exception.Message.Contains('cancellation requested') }
Assert-ProbeCheck $cancelled 'ordinary_cancellation_marker_is_detected'

$liveCancellation = Join-Path $out 'live-cancel'
[void][IO.Directory]::CreateDirectory($liveCancellation)
$cancelRun = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
    @('-I', '-c', 'import pathlib, sys, time; time.sleep(0.1); pathlib.Path(sys.argv[1]).write_text("{}"); time.sleep(30)',
        (Join-Path $liveCancellation 'cancel.request.json')) 'cancellation' 10 -CancellationDirectory $liveCancellation
Assert-ProbeCheck ($cancelRun.status -ceq 'runner_error' -and -not $cancelRun.timeout_reached -and
    $cancelRun.error.Contains('cancellation requested') -and $cancelRun.process_cleanup.termination_requested -and
    -not $cancelRun.process_cleanup.exit_observed_before_cleanup -and
    $null -eq $cancelRun.process_cleanup.natural_exit_code -and -not $cancelRun.cleanup_errors.Count) 'live_cancellation_stops_owned_console_without_claiming_timeout'

$alreadyCancelled = Invoke-AxiomProbeConsoleProcess $workspace $out $python $workspace `
    @('-I', '-c', 'raise RuntimeError("must never start")') 'pre-cancellation' 10 -CancellationDirectory $liveCancellation
Assert-ProbeCheck ($alreadyCancelled.status -ceq 'runner_error' -and $null -eq $alreadyCancelled.process_cleanup -and
    -not (Test-Path -LiteralPath (Join-Path $out 'pre-cancellation.stdout.txt'))) 'prelaunch_cancellation_refuses_process_creation'

# Four-file recovery runs against a fresh test profile; the user's real profile
# is never touched. This also exercises restoration after a preparation error.
$localAppDataBefore = $env:LOCALAPPDATA
$testRuntime = Join-Path $workspace ('.tools/probe-preservation-test-' + [guid]::NewGuid().ToString('N'))
$testProfile = Join-Path $out 'fake-local-appdata'
$testSnapshot = $null
try {
    $env:LOCALAPPDATA = $testProfile
    $adapterProfile = Join-Path $testProfile 'AXIOMSandbox/geode/mods/axiom.native-capture'
    $loaderProfile = Join-Path $testProfile 'AXIOMSandbox/geode/mods/geode.loader'
    [void][IO.Directory]::CreateDirectory($testRuntime)
    [void][IO.Directory]::CreateDirectory($adapterProfile)
    [void][IO.Directory]::CreateDirectory($loaderProfile)
    [IO.File]::WriteAllBytes((Join-Path $adapterProfile 'replay.json'), [byte[]]@(123, 13, 10, 125))
    [IO.File]::WriteAllBytes((Join-Path $loaderProfile 'settings.json'), [byte[]]@(239, 187, 191, 123, 125))
    $testSnapshot = Get-AxiomExperimentSnapshot $workspace $testRuntime
    $simulatedPreparationFailure = $null
    try {
        foreach ($file in $testSnapshot.Files) { [IO.File]::WriteAllText($file.Path, 'mutated by test preparation', $utf8) }
        throw 'intentional preparation failure'
    } catch { $simulatedPreparationFailure = $_.Exception.Message }
    finally { $preserved = Restore-AxiomProbeExperimentSnapshot $testSnapshot }
    Assert-ProbeCheck ($preserved.all_preserved -and $preserved.files.Count -eq 4 -and
        $simulatedPreparationFailure -ceq 'intentional preparation failure' -and
        @($preserved.files | Where-Object existed_before).Count -eq 2 -and
        @($preserved.files | Where-Object { -not $_.existed_before -and -not $_.exists_after }).Count -eq 2) 'preparation_failure_restores_four_file_bytes_and_absence'

    $fixturePath = Join-Path $testRuntime 'fixture-level.txt'
    [IO.File]::WriteAllBytes($fixturePath, [byte[]]@(108, 101, 118, 101, 108))
    [IO.File]::WriteAllBytes((Join-Path $adapterProfile 'settings.json'), [byte[]]@(123, 125))
    $allExistingSnapshot = Get-AxiomExperimentSnapshot $workspace $testRuntime
    foreach ($file in $allExistingSnapshot.Files) { [IO.File]::WriteAllText($file.Path, 'mutated before fixture failure', $utf8) }
    Remove-Item -LiteralPath $fixturePath
    [void][IO.Directory]::CreateDirectory($fixturePath)
    $partialRestore = Restore-AxiomProbeExperimentSnapshot $allExistingSnapshot
    Assert-ProbeCheck (-not $partialRestore.all_preserved -and $partialRestore.files.Count -eq 4 -and
        -not $partialRestore.files[0].preserved -and $partialRestore.cleanup_errors.Count -ge 1 -and
        @($partialRestore.files[1..3] | Where-Object preserved).Count -eq 3) 'fixture_restore_failure_still_restores_three_profile_files'
    # Remove only the empty directory created immediately above, then restore
    # the owned test fixture before exercising an ancestor redirection failure.
    [IO.Directory]::Delete($fixturePath, $false)
    $restoredAfterTest = Restore-AxiomProbeExperimentSnapshot $allExistingSnapshot
    if (-not $restoredAfterTest.all_preserved) { throw 'Owned fixture test reset failed.' }
    $outsideFixtureDirectory = Join-Path $out 'outside-fixture-target'
    [void][IO.Directory]::CreateDirectory($outsideFixtureDirectory)
    $outsideFixture = Join-Path $outsideFixtureDirectory 'fixture-level.txt'
    [IO.File]::WriteAllText($outsideFixture, 'outside fixture must remain unchanged', $utf8)
    $outsideFixtureHash = Get-AxiomProbeHash $outsideFixture
    foreach ($file in $allExistingSnapshot.Files[1..3]) { [IO.File]::WriteAllText($file.Path, 'mutated before redirected runtime', $utf8) }
    Remove-Item -LiteralPath $fixturePath
    [IO.Directory]::Delete($testRuntime, $false)
    [void](New-Item -ItemType Junction -Path $testRuntime -Target $outsideFixtureDirectory)
    try {
        $redirectedRestore = Restore-AxiomProbeExperimentSnapshot $allExistingSnapshot
        Assert-ProbeCheck (-not $redirectedRestore.all_preserved -and -not $redirectedRestore.files[0].preserved -and
            @($redirectedRestore.files[1..3] | Where-Object preserved).Count -eq 3 -and
            (Get-AxiomProbeHash $outsideFixture) -ceq $outsideFixtureHash) 'redirected_runtime_is_not_followed_and_other_files_still_restore'
    } finally {
        # Nonrecursive deletion unlinks this owned junction, not its target.
        [IO.Directory]::Delete($testRuntime, $false)
        [void][IO.Directory]::CreateDirectory($testRuntime)
        $restoredAfterTest = Restore-AxiomProbeExperimentSnapshot $allExistingSnapshot
        if (-not $restoredAfterTest.all_preserved) { throw 'Owned redirected-runtime test reset failed.' }
    }
} finally {
    try {
        if ($testSnapshot) {
            $finalTestRestore = Restore-AxiomProbeExperimentSnapshot $testSnapshot
            if (-not $finalTestRestore.all_preserved) { throw 'Owned test profile did not restore exactly.' }
        }
    }
    finally { $env:LOCALAPPDATA = $localAppDataBefore }
}

$redirectedDirectory = Join-Path $out 'junction'
[void](New-Item -ItemType Junction -Path $redirectedDirectory -Target $cancelDirectory)
$junctionRejected = $false
try { Assert-AxiomProbeOrdinaryPath (Join-Path $redirectedDirectory 'cancel.request.json') 'file' }
catch { $junctionRejected = $_.Exception.Message.Contains('Redirected probe path') }
Assert-ProbeCheck $junctionRejected 'real_windows_junction_is_rejected'

$result = [ordered]@{
    kind='headless_native_probe_process_integration'; schema_version=1; status='passed'; checks=$checks
    evidence_directory=$out; game_launched=$false; os_input_injected=$false
    scientific_native_qualification='not_established'
}
Write-AxiomProbeFreshJson (Join-Path $out 'result.json') $result
Write-Output ($result | ConvertTo-Json -Depth 8)
