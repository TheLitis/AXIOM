param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [Parameter(Mandatory = $true)][string]$MatrixPath,
    [Parameter(Mandatory = $true)][string]$MatrixEvidenceDirectory,
    [string[]]$CaseId,
    [ValidateRange(2, 16)][int]$Repetitions = 3,
    [string]$RuntimeDirectory,
    [string]$OutputDirectory
)

# Records the declared synthetic UI callback route against an existing owned
# matrix run. A negative full-stream comparison is an experimental result.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
$utf8 = [Text.UTF8Encoding]::new($false)
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')

function Write-StudyJson([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 60) + "`n", $utf8)
}
function Get-StudyHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-StudyTextHash([string]$Value) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($utf8.GetBytes($Value))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
}
function ConvertTo-StudyCanonicalJson($Value) {
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [Collections.IDictionary]) {
        $parts = @()
        foreach ($key in @($Value.Keys | Sort-Object)) {
            $parts += (ConvertTo-Json -InputObject ([string]$key) -Compress) + ':' + (ConvertTo-StudyCanonicalJson $Value[$key])
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [pscustomobject]) {
        $parts = @()
        foreach ($property in @($Value.PSObject.Properties | Sort-Object Name)) {
            $parts += (ConvertTo-Json -InputObject $property.Name -Compress) + ':' + (ConvertTo-StudyCanonicalJson $property.Value)
        }
        return '{' + ($parts -join ',') + '}'
    }
    if ($Value -is [Collections.IEnumerable] -and $Value -isnot [string]) {
        $parts = @()
        foreach ($entry in $Value) { $parts += ConvertTo-StudyCanonicalJson $entry }
        return '[' + ($parts -join ',') + ']'
    }
    return ConvertTo-Json -InputObject $Value -Compress
}
function Assert-StudyIdentity($Left, $Right, [string]$Name) {
    if ((ConvertTo-StudyCanonicalJson $Left) -cne (ConvertTo-StudyCanonicalJson $Right)) {
        throw "Study identity differs: $Name"
    }
}
function Assert-StudyOrdinaryPath([string]$Path, [bool]$Directory) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if ($item.PSIsContainer -ne $Directory -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Study path has the wrong type or is redirected: $Path"
        }
    }
}
function Get-StudyPackage {
    $root = [IO.Path]::GetFullPath($workspace).TrimEnd([char[]]'\/')
    $marker = Join-Path $root '.tools/native-package-path.txt'
    Assert-StudyOrdinaryPath $marker $false
    if (Test-Path -LiteralPath $marker) {
        if ((Get-Item -LiteralPath $marker).Length -gt 4096) { throw 'Native package marker is oversized.' }
        $relative = [IO.File]::ReadAllText($marker).Trim()
        $parts = @($relative -split '[\\/]')
        if (-not $relative -or [IO.Path]::IsPathRooted($relative) -or @($parts | Where-Object {
            -not $_ -or $_ -eq '.' -or $_ -eq '..' -or $_.EndsWith('.') -or $_.EndsWith(' ') -or
            $_.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0
        }).Count) { throw 'Native package marker must be a contained workspace-relative path.' }
        $package = [IO.Path]::GetFullPath((Join-Path $root $relative))
    } else { $package = Join-Path $root 'native/build/axiom.native-capture.geode' }
    if (-not $package.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Native package escapes the workspace.'
    }
    $ancestor = [IO.Path]::GetDirectoryName($package)
    while ($ancestor -ne $root) {
        Assert-StudyOrdinaryPath $ancestor $true
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    Assert-StudyOrdinaryPath $package $false
    return (Resolve-Path -LiteralPath $package).Path
}
function Get-StudyPackageDllHash([string]$Package) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Package)
    try {
        $entries = @($zip.Entries | Where-Object FullName -ceq 'axiom.native-capture.dll')
        if ($entries.Count -ne 1) { throw 'Package must contain exactly one root adapter DLL.' }
        $stream = $entries[0].Open()
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose(); $hasher.Dispose() }
    } finally { $zip.Dispose() }
}
function Get-StudyNativeTreeHash {
    $nativeRoot = Join-Path $workspace 'native'
    $identity = ''
    $files = @(Get-ChildItem -LiteralPath (Join-Path $nativeRoot 'src') -File -Recurse |
        Where-Object { $_.Extension -in @('.cpp', '.hpp') } | Sort-Object FullName)
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($nativeRoot.Length + 1).Replace('\', '/')
        $identity += $relative + ':' + (Get-StudyHash $file.FullName) + "`n"
    }
    foreach ($relative in @('CMakeLists.txt', 'mod.json')) {
        $identity += $relative + ':' + (Get-StudyHash (Join-Path $nativeRoot $relative)) + "`n"
    }
    return Get-StudyTextHash $identity
}
function Assert-StudyFrozenFiles {
    foreach ($relative in $analysisFiles.Keys) {
        if ((Get-StudyHash (Join-Path $workspace $relative)) -cne $analysisFiles[$relative]) {
            throw "Analysis source changed during study: $relative"
        }
    }
    if ((Get-StudyHash $matrixFile) -cne $manifest.source_specification_sha256 -or
        (Get-StudyHash $matrixResultPath) -cne $manifest.matrix_result_sha256 -or
        (Get-StudyHash $package) -cne $manifest.native_package.sha256 -or
        (Get-StudyNativeTreeHash) -cne $manifest.native_package.current_native_tree_sha256) {
        throw 'Frozen matrix, package or native source bytes changed during study.'
    }
    if ($manifest.native_package.prepared_package_sha256 -and
        (Get-StudyHash (Join-Path $runtime 'geode/mods/axiom.native-capture.geode')) -cne $manifest.native_package.prepared_package_sha256) {
        throw 'Prepared runtime package changed during study.'
    }
}
function Quote-StudyArgument([string]$Value) {
    # No shell is involved; quote each argument for the Windows process parser.
    if ($Value.Contains('"')) { throw 'A study process argument contains an unsupported quote.' }
    return '"' + ($Value -replace '(\\+)$', '$1$1') + '"'
}
function Invoke-StudyAnalysis([string[]]$AnalysisArguments, [string]$Stem) {
    $record = [ordered]@{ arguments = $AnalysisArguments; stdout_path = $Stem + '.stdout.txt';
        stderr_path = $Stem + '.stderr.txt'; exit_code = $null; started_at_utc = [DateTime]::UtcNow.ToString('o') }
    $manifest.analysis_invocations += $record
    $argumentLine = (@($AnalysisArguments | ForEach-Object { Quote-StudyArgument $_ }) -join ' ')
    $process = Start-Process -FilePath $python -WorkingDirectory $workspace -ArgumentList $argumentLine -WindowStyle Hidden -PassThru -RedirectStandardOutput $record.stdout_path -RedirectStandardError $record.stderr_path
    try {
        if (-not $process.WaitForExit(120000)) { throw 'Analysis process timed out; diagnostic output is retained.' }
        $record.exit_code = $process.ExitCode
        if ($process.ExitCode -ne 0) { throw "Analysis failed structurally (exit $($process.ExitCode)); see $($record.stderr_path)" }
    } finally {
        if (-not $process.HasExited) {
            Stop-Process -InputObject $process -Force
            if (-not $process.WaitForExit(5000)) { throw 'Owned analysis process cleanup timed out.' }
        }
        $record.finished_at_utc = [DateTime]::UtcNow.ToString('o')
        $process.Dispose()
    }
}
function Invoke-StudyCapture($Selection, [int]$Index, $Record, [string]$Directory) {
    Assert-StudyFrozenFiles
    if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) {
        throw 'Existing active sandbox process; study does not own it.'
    }
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Name] = $true }
    $arguments = @('--geode:axiom-sandbox', '--geode:axiom.native-capture.replay',
        '--geode:axiom.native-capture.input-driver=scheduled-ui-callback',
        "--geode:axiom.native-capture.clock-policy=$clockPolicy")
    if ($Selection.Case.watch_groups.Count) { $arguments += '--geode:axiom.native-capture.watch-groups=' + ($Selection.Case.watch_groups -join ',') }
    $stem = Join-Path $Directory ("ui-$Index")
    $Record.launch_arguments = $arguments
    $Record.stdout_path = $stem + '.stdout.txt'
    $Record.stderr_path = $stem + '.stderr.txt'
    $Record.started_at_utc = [DateTime]::UtcNow.ToString('o')
    Write-StudyJson ($stem + '.launch.json') $Record
    $process = Start-Process -FilePath $exe -WorkingDirectory $runtime -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput $Record.stdout_path -RedirectStandardError $Record.stderr_path -PassThru
    $Record.process_id = $process.Id
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $captureFailure = $null
    try {
        $capture = $null
        while ($timer.Elapsed.TotalSeconds -lt 45) {
            $new = @(Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | Where-Object { -not $before.ContainsKey($_.Name) } | Sort-Object Name)
            if ($new.Count) {
                foreach ($file in $new) {
                    $destination = if ($file -eq $new[0]) { $stem + '.json' } else { Join-Path $Directory ('unexpected-' + $file.Name) }
                    Copy-Item -LiteralPath $file.FullName -Destination $destination
                    $Record.exported_captures += [ordered]@{ path = $destination; source_path = $file.FullName; sha256 = Get-StudyHash $destination }
                }
                if ($new.Count -ne 1) { throw 'Multiple native exports appeared; all are retained without selecting a successful replacement.' }
                $capture = $stem + '.json'
                $Record.capture_path = $capture
                $Record.capture_sha256 = Get-StudyHash $capture
                break
            }
            if ($process.HasExited) { throw 'Sandbox exited before native export.' }
            Start-Sleep -Milliseconds 200
        }
        if (-not $capture) { throw 'UI delivery run timed out; outputs and launch record are retained.' }
        return $capture
    } catch { $captureFailure = $_; throw }
    finally {
        $cleanupError = $null
        try {
            if (-not $process.HasExited) {
                Stop-Process -InputObject $process -Force
                if (-not $process.WaitForExit(5000)) { throw 'Owned sandbox process did not exit within cleanup timeout.' }
            }
            $Record.owned_process_cleanup = 'exited'
        } catch {
            $cleanupError = $_
            $Record.owned_process_cleanup = 'failed'
            $Record.cleanup_error = $_.Exception.Message
        } finally {
            $Record.finished_at_utc = [DateTime]::UtcNow.ToString('o')
            Write-StudyJson ($stem + '.launch.json') $Record
            $process.Dispose()
        }
        if ($cleanupError) {
            if ($captureFailure) { throw "Capture failed: $($captureFailure.Exception.Message). Cleanup failed: $($cleanupError.Exception.Message)" }
            throw $cleanupError
        }
    }
}

$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else { Join-Path $workspace ('reports/native/delivery-study-' + [guid]::NewGuid().ToString('N')) }
if (Test-Path -LiteralPath $out) { throw 'Evidence output directory already exists; preserved without replacement.' }
New-Item -ItemType Directory -Path $out | Out-Null
$runtime = if ($RuntimeDirectory) { [IO.Path]::GetFullPath($RuntimeDirectory) } else { Join-Path $workspace ('.tools/runtime-delivery-' + [guid]::NewGuid().ToString('N')) }
$profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $profile 'captures'
$exe = Join-Path $runtime 'AXIOMSandbox.exe'
$snapshot = $null
$priorExecutionState = $null
$studyComplete = $false
$errors = [Collections.Generic.List[string]]::new()
$manifest = [ordered]@{ schema_version = 1; kind = 'native_delivery_study_result';
    protocol = 'synthetic-owned-vs-ui-queue-p1-button1-v1'; started_at_utc = [DateTime]::UtcNow.ToString('o');
    status = 'delivery_study_incomplete'; runtime_directory = $runtime; repetitions_per_case = $Repetitions;
    cases = @(); excluded_cases = @(); analysis_invocations = @(); errors = @();
    authentication_status = 'not_authenticated'; ordinary_os_input_equivalence = 'not_established';
    human_authorship = 'not_established'; m1_gate = 'not_established_by_file_inspection';
    limitations = @('This records supplied selected evidence and does not authenticate it.',
        'Scheduled UILayer callbacks bypass Windows, physical devices and the dispatcher.',
        'All actual input receipts and negative comparisons are retained; none are removed as cleanup noise.',
        'Selected dynamics and queue witnesses do not establish complete state or ordinary-input equivalence.',
        'Four-file restoration covers only the declared experiment files, not the complete machine or personal saves.') }
try {
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --extra dev first.' }
    if (@(Get-Process AXIOMSandbox -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }).Count) { throw 'Existing active sandbox process; finish that experiment first.' }
    Assert-AxiomExperimentPaths $workspace $runtime
    if (Test-Path -LiteralPath $runtime) { throw 'Delivery study requires a fresh runtime directory; existing contents are preserved.' }
    $matrixFile = (Resolve-Path -LiteralPath $MatrixPath).Path
    $evidenceRoot = (Resolve-Path -LiteralPath $MatrixEvidenceDirectory).Path
    Assert-StudyOrdinaryPath $matrixFile $false
    Assert-StudyOrdinaryPath $evidenceRoot $true
    $matrixResultPath = Join-Path $evidenceRoot 'matrix-result.json'
    $matrixResult = Get-Content -LiteralPath $matrixResultPath -Raw | ConvertFrom-Json
    if ($matrixResult.kind -ne 'native_fixture_matrix_result' -or $matrixResult.schema_version -ne 3 -or $matrixResult.status -ne 'declared_matrix_recorded_subset_passed') {
        throw 'Study requires a passed schema-3 confirming matrix manifest.'
    }
    $manifest.matrix_evidence_directory = $evidenceRoot
    $manifest.matrix_result_sha256 = Get-StudyHash $matrixResultPath
    $manifest.matrix_analysis_source_commit = $matrixResult.analysis_source_commit
    $manifest.source_specification_sha256 = Get-StudyHash $matrixFile
    if ($manifest.source_specification_sha256 -cne $matrixResult.source_specification_sha256) { throw 'Source matrix SHA differs from the confirming manifest.' }
    $analysisFiles = [ordered]@{}
    foreach ($relative in @('src/axiom/fixtures.py', 'src/axiom/native.py', 'src/axiom/equivalence.py', 'src/axiom/cli.py',
        'scripts/run-native-delivery-study.ps1', 'scripts/native-experiment-state.ps1', 'scripts/prepare-native-sandbox.ps1')) {
        $analysisFiles[$relative] = Get-StudyHash (Join-Path $workspace $relative)
    }
    $manifest.analysis_file_sha256 = $analysisFiles
    $manifest.analysis_source_commit = $null
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $candidate = & git -C $workspace rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0) { $manifest.analysis_source_commit = "$candidate".Trim() }
    }
    $validatedPath = Join-Path $out 'validated-matrix.json'
    Invoke-StudyAnalysis @('-m', 'axiom', 'fixtures', $matrixFile, '--json', $validatedPath) (Join-Path $out 'matrix-validation')
    $matrix = Get-Content -LiteralPath $validatedPath -Raw | ConvertFrom-Json
    $manifest.specification_sha256 = Get-StudyHash $validatedPath
    if ($matrix.schema_version -ne 3 -or $manifest.specification_sha256 -cne $matrixResult.specification_sha256) { throw 'Validated matrix SHA/schema differs from the confirming manifest.' }
    $clockPolicy = $matrixResult.clock_policy
    if ($clockPolicy -notin @('native', 'fixed-base-60', 'fixed-scheduler-240')) { throw 'Unsupported confirming clock policy.' }
    $manifest.clock_policy = $clockPolicy
    $package = Get-StudyPackage
    $manifest.native_package = [ordered]@{ path = $package; sha256 = Get-StudyHash $package;
        adapter_dll_sha256 = Get-StudyPackageDllHash $package; current_native_tree_sha256 = Get-StudyNativeTreeHash }
    if ($CaseId) {
        if (@($CaseId | Select-Object -Unique).Count -ne $CaseId.Count) { throw 'Duplicate requested case ID.' }
        foreach ($requested in $CaseId) {
            if (-not @($matrix.cases | Where-Object id -eq $requested).Count) { throw "Unknown requested case: $requested" }
        }
    }
    $selections = @()
    foreach ($case in @($matrix.cases)) {
        if ($CaseId -and $CaseId -notcontains $case.id) { continue }
        $replays = @($case.runs | Where-Object role -eq 'replay')
        if ($replays.Count -ne 1) { throw "Expected exactly one designated replay run: $($case.id)" }
        $run = $replays[0]
        if (-not $run.inputs.Count -or @($run.inputs | Where-Object { $_.player -ne 1 -or $_.button -ne 1 }).Count) {
            $manifest.excluded_cases += [ordered]@{ case_id = $case.id; reason = 'requires_nonempty_P1_button1_plan' }
            if ($CaseId) { throw "Requested case does not support the scoped UI plan: $($case.id)" }
            continue
        }
        $caseEvidence = @($matrixResult.cases | Where-Object case_id -eq $case.id)
        if ($caseEvidence.Count -ne 1 -or $caseEvidence[0].case_gate -ne 'passed_for_declared_recorded_subset') { throw "Missing confirming case: $($case.id)" }
        $recorded = @($caseEvidence[0].runs | Where-Object { $_.run_id -eq $run.id -and $_.repetition -eq 1 })
        if ($recorded.Count -ne 1 -or -not $recorded[0].checks.complete_plan_executed) { throw "Owned source plan was not confirmed fully executed: $($case.id)" }
        $source = Join-Path (Join-Path $evidenceRoot $case.id) ($run.id + '-1.json')
        if ((Get-StudyHash $source) -cne $recorded[0].capture_sha256) { throw "Owned capture SHA differs from its matrix run record: $($case.id)" }
        $casePath = Join-Path $out $case.id
        New-Item -ItemType Directory -Path $casePath | Out-Null
        $ownedPath = Join-Path $casePath 'owned-reference.json'
        Copy-Item -LiteralPath $source -Destination $ownedPath
        if ((Get-StudyHash $ownedPath) -cne $recorded[0].capture_sha256) { throw 'Copied owned reference differs from its confirming run digest.' }
        $ownedInspectionPath = $ownedPath + '.native-inspection.json'
        Invoke-StudyAnalysis @('-m', 'axiom', 'native', $ownedPath, '--json', $ownedInspectionPath) (Join-Path $casePath 'owned-inspection')
        $owned = Get-Content -LiteralPath $ownedPath -Raw | ConvertFrom-Json
        $ownedInspection = Get-Content -LiteralPath $ownedInspectionPath -Raw | ConvertFrom-Json
        if ($owned.schema_version -ne 4 -or $owned.attempt.start_kind -ne 'level_start' -or $owned.attempt.input_source -ne 'replay' -or
            $owned.attempt.input_delivery.driver -ne 'owned-pre-command' -or $ownedInspection.counts.unexecuted_planned_tail -ne 0) { throw 'Owned reference is outside the declared delivery domain.' }
        Assert-StudyIdentity @($owned.attempt.planned_inputs) @($run.inputs) 'owned planned inputs'
        Assert-StudyIdentity $owned.collector $caseEvidence[0].collector 'confirming collector'
        if ($owned.challenge.level_sha256 -cne $case.level_sha256 -or $owned.environment_sha256 -cne $caseEvidence[0].environment_sha256 -or
            $owned.environment.clocks.clock_policy -cne $clockPolicy -or $owned.environment.adapter_binary_sha256 -cne $manifest.native_package.adapter_dll_sha256 -or
            $owned.collector.source_tree_sha256 -cne $manifest.native_package.current_native_tree_sha256) { throw 'Owned reference differs from frozen challenge, environment or selected native source/package.' }
        if ($owned.attempt.terminal.outcome -cne $recorded[0].outcome -or $owned.attempt.terminal.command_index -ne $recorded[0].terminal_command_index) {
            throw 'Owned terminal differs from the confirming run record.'
        }
        $planSource = Join-Path (Join-Path $evidenceRoot $case.id) ($run.id + '.plan.json')
        $planPath = Join-Path $casePath 'replay.plan.json'
        Copy-Item -LiteralPath $planSource -Destination $planPath
        if ((Get-StudyHash $planPath) -cne $owned.attempt.replay_sha256) { throw 'Retained source plan bytes differ from the owned replay digest.' }
        $plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
        Assert-StudyIdentity @($plan.inputs) @($owned.attempt.planned_inputs) 'retained source plan'
        if ($plan.level_sha256 -cne $case.level_sha256 -or $plan.environment_sha256 -cne $owned.environment_sha256) { throw 'Retained plan challenge/environment differs.' }
        $caseRecord = [ordered]@{ case_id = $case.id; source_run_id = $run.id; level_sha256 = $case.level_sha256;
            environment_sha256 = $owned.environment_sha256; collector = $owned.collector;
            owned_capture_source_path = $source; owned_capture_path = $ownedPath; owned_capture_sha256 = Get-StudyHash $ownedPath;
            owned_inspection_path = $ownedInspectionPath; owned_inspection_sha256 = Get-StudyHash $ownedInspectionPath;
            owned_inspection_status = $ownedInspection.status; plan_path = $planPath; plan_sha256 = Get-StudyHash $planPath;
            planned_inputs = @($run.inputs); runs = @(); same_route_comparison = $null; status = 'incomplete' }
        $manifest.cases += $caseRecord
        $selections += [pscustomobject]@{ Case = $case; Run = $run; Owned = $owned; OwnedPath = $ownedPath;
            Directory = $casePath; PlanPath = $planPath; Record = $caseRecord }
    }
    if (-not $selections.Count) { throw 'No nonempty fully executed P1 button-1 cases were selected.' }
    Assert-StudyFrozenFiles
    # Snapshot these four files before preparation mutates the experiment profile.
    $snapshot = Get-AxiomExperimentSnapshot $workspace $runtime
    if (-not ('AxiomDeliveryPower' -as [type])) {
        Add-Type -Name AxiomDeliveryPower -Namespace '' -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);'
    }
    $priorExecutionState = [AxiomDeliveryPower]::SetThreadExecutionState([uint32]2147483651)
    if (-not $priorExecutionState) { throw 'Unable to request temporary system/display execution state.' }
    $manifest.startup_execution_state = 'system_and_display_required_during_study'
    & (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $GameDirectory -NativePackage $package -RuntimeDirectory $runtime
    $preparedPackage = Join-Path $runtime 'geode/mods/axiom.native-capture.geode'
    if ((Get-StudyHash $preparedPackage) -cne $manifest.native_package.sha256) { throw 'Prepared package differs from selected native package.' }
    $manifest.native_package.prepared_package_sha256 = Get-StudyHash $preparedPackage
    foreach ($selection in $selections) {
        $loader = @($selection.Owned.environment.mods | Where-Object id -eq 'geode.loader')
        if ($loader.Count -ne 1 -or (Get-StudyHash $exe) -cne $selection.Owned.environment.game_executable_sha256 -or
            (Get-StudyHash (Join-Path $runtime 'Geode.dll')) -cne $loader[0].binary_sha256) {
            throw 'Prepared game/loader binary differs from the owned reference environment.'
        }
    }
    $seenAttempts = @{}
    foreach ($selection in $selections) {
        if ($seenAttempts.ContainsKey($selection.Owned.attempt.id)) { throw 'Duplicate owned reference attempt ID.' }
        $seenAttempts[$selection.Owned.attempt.id] = $true
    }
    foreach ($selection in $selections) {
        [IO.File]::WriteAllText((Join-Path $runtime 'fixture-level.txt'), $selection.Case.level_string, $utf8)
        [IO.File]::WriteAllBytes((Join-Path $profile 'replay.json'), [IO.File]::ReadAllBytes($selection.PlanPath))
        $repeatPaths = @()
        for ($index = 1; $index -le $Repetitions; $index++) {
            $record = [ordered]@{ repetition = $index; status = 'incomplete'; exported_captures = @() }
            $selection.Record.runs += $record
            $capturePath = Invoke-StudyCapture $selection $index $record $selection.Directory
            $inspectionPath = $capturePath + '.native-inspection.json'
            Invoke-StudyAnalysis @('-m', 'axiom', 'native', $capturePath, '--json', $inspectionPath) ($capturePath + '.inspection')
            $record.inspection_path = $inspectionPath
            $record.inspection_sha256 = Get-StudyHash $inspectionPath
            $inspection = Get-Content -LiteralPath $inspectionPath -Raw | ConvertFrom-Json
            $record.inspection_status = $inspection.status
            $data = Get-Content -LiteralPath $capturePath -Raw | ConvertFrom-Json
            $record.attempt_id = $data.attempt.id
            if ($seenAttempts.ContainsKey($data.attempt.id)) { throw 'Duplicate attempt ID in the delivery study.' }
            $seenAttempts[$data.attempt.id] = $true
            if ($data.schema_version -ne 4 -or $data.attempt.input_delivery.driver -ne 'scheduled-ui-callback' -or
                $data.attempt.replay_sha256 -cne $selection.Record.plan_sha256 -or $inspection.counts.unexecuted_planned_tail -ne 0) { throw 'UI capture route or full planned execution differs.' }
            foreach ($key in @('challenge', 'environment', 'collector', 'state_fields', 'layer_state_fields')) {
                Assert-StudyIdentity $data.$key $selection.Owned.$key $key
            }
            $record.terminal_outcome = $data.attempt.terminal.outcome
            $record.terminal_command_index = $data.attempt.terminal.command_index
            $record.input_delivery = $data.attempt.input_delivery
            $record.input_record_count = $data.attempt.inputs.Count
            $record.delivery_event_count = $data.attempt.delivery_events.Count
            $record.mechanic_event_count = $data.attempt.mechanic_events.Count
            $comparisonPath = $capturePath + '.delivery-comparison.json'
            Invoke-StudyAnalysis @('-m', 'axiom', 'native-delivery-compare', $selection.OwnedPath, $capturePath, '--json', $comparisonPath) ($capturePath + '.comparison')
            $comparison = Get-Content -LiteralPath $comparisonPath -Raw | ConvertFrom-Json
            $record.comparison_path = $comparisonPath
            $record.comparison_sha256 = Get-StudyHash $comparisonPath
            $record.comparison_status = $comparison.status
            $record.checks = $comparison.checks
            $record.diagnostics = $comparison.diagnostics
            $record.ui_queue_path = $comparison.ui_queue_path
            $record.suppressed_request_diagnostics = $comparison.suppressed_request_diagnostics
            $record.full_actual_input_stream_equal = $comparison.checks.native_input_receipts_equal
            $record.status = 'comparison_recorded'
            $repeatPaths += $capturePath
            Write-StudyJson (Join-Path $out 'delivery-result.json') $manifest
            Write-Host "Delivery $($selection.Case.id)/$index : $($comparison.status), full actual input stream equal=$($record.full_actual_input_stream_equal)"
        }
        $repeatComparisonPath = Join-Path $selection.Directory 'ui-repeat-comparison.json'
        Invoke-StudyAnalysis (@('-m', 'axiom', 'native-compare') + $repeatPaths + @('--json', $repeatComparisonPath)) (Join-Path $selection.Directory 'ui-repeat-comparison')
        $repeatComparison = Get-Content -LiteralPath $repeatComparisonPath -Raw | ConvertFrom-Json
        $selection.Record.same_route_comparison = [ordered]@{ path = $repeatComparisonPath; sha256 = Get-StudyHash $repeatComparisonPath;
            status = $repeatComparison.status; component_consistency = $repeatComparison.component_consistency;
            delivery_context_protocol = $repeatComparison.delivery_context_protocol;
            absolute_timestamp_diagnostics = @($repeatComparison.comparisons | ForEach-Object { $_.delivery_absolute_timestamp_diagnostics }) }
        $selection.Record.status = 'all_declared_comparisons_recorded'
    }
    Assert-StudyFrozenFiles
    $studyComplete = $true
} catch {
    $errors.Add($_.Exception.Message)
} finally {
    try {
        if ($snapshot) {
            try { Restore-AxiomExperimentSnapshot $snapshot }
            catch { $errors.Add('Four-file restoration: ' + $_.Exception.Message) }
            try {
                $preservation = Test-AxiomExperimentSnapshot $snapshot
                Write-StudyJson (Join-Path $out 'state-preservation.json') $preservation
                $manifest.state_preservation = [ordered]@{ path = Join-Path $out 'state-preservation.json';
                    sha256 = Get-StudyHash (Join-Path $out 'state-preservation.json'); all_preserved = $preservation.all_preserved }
                if (-not $preservation.all_preserved) { $errors.Add('Experiment file byte/existence restoration did not match.') }
            } catch { $errors.Add('Four-file verification: ' + $_.Exception.Message) }
        } else { $manifest.state_preservation = [ordered]@{ status = 'not_started_no_preparation' } }
    } finally {
        if ($priorExecutionState) {
            try {
                if (-not [AxiomDeliveryPower]::SetThreadExecutionState($priorExecutionState)) { throw 'Unable to restore previous execution-state request.' }
                $manifest.execution_state_restoration = 'restored'
            } catch { $errors.Add($_.Exception.Message); $manifest.execution_state_restoration = 'failed' }
        } else { $manifest.execution_state_restoration = 'not_requested' }
    }
}
$manifest.errors = @($errors.ToArray())
$manifest.recorded_at_utc = [DateTime]::UtcNow.ToString('o')
$manifest.status = if ($studyComplete -and -not $errors.Count) { 'declared_delivery_study_recorded' } else { 'delivery_study_incomplete' }
$manifest.recording_success_does_not_mean_equivalence_passed = $true
Write-StudyJson (Join-Path $out 'delivery-result.json') $manifest
Write-Output "Delivery study: $($manifest.status)"
Write-Output "Evidence: $out"
if ($errors.Count) { throw ($errors -join ' | ') }
