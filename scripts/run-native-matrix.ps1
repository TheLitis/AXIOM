param(
    [Parameter(Mandatory = $true)][string]$GameDirectory,
    [string]$MatrixPath,
    [string[]]$CaseId,
    [ValidateRange(2, 16)][int]$Repetitions = 3,
    [ValidateSet('native', 'fixed-base-60', 'fixed-scheduler-240')][string]$ClockPolicy = 'fixed-scheduler-240',
    [string]$OutputDirectory
)

# Generated fixtures are specifications, not authenticated measurements or AR.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --extra dev first.' }
if (Get-Process AXIOMSandbox -ErrorAction SilentlyContinue) { throw 'Existing sandbox process; finish that experiment first.' }
if (-not $MatrixPath) { $MatrixPath = Join-Path $workspace 'examples/native/fixture-matrix.json' }
$matrixFile = (Resolve-Path -LiteralPath $MatrixPath).Path
if ($OutputDirectory) {
    $out = [IO.Path]::GetFullPath($OutputDirectory)
    if (Test-Path -LiteralPath $out) { throw 'Evidence output directory already exists; preserved without replacement.' }
} else { $out = Join-Path $workspace ('reports/native/matrix-' + [guid]::NewGuid().ToString('N')) }
New-Item -ItemType Directory -Path $out | Out-Null
$validatedPath = Join-Path $out 'validated-matrix.json'
& $python -m axiom fixtures $matrixFile --json $validatedPath
if ($LASTEXITCODE -ne 0) { throw 'Invalid fixture specification; game was not prepared or launched.' }
$matrix = Get-Content -LiteralPath $validatedPath -Raw | ConvertFrom-Json
$sourceCommit = $null
if (Get-Command git -ErrorAction SilentlyContinue) {
    try {
        $candidate = & git -C $workspace rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0) { $sourceCommit = "$candidate".Trim() }
    } catch { $sourceCommit = $null }
}
$analysisFiles = [ordered]@{}
foreach ($relative in @('src/axiom/fixtures.py', 'src/axiom/native.py', 'src/axiom/cli.py', 'scripts/run-native-matrix.ps1')) {
    $analysisFiles[$relative] = (Get-FileHash -LiteralPath (Join-Path $workspace $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$sourceSpecificationHash = (Get-FileHash -LiteralPath $matrixFile -Algorithm SHA256).Hash.ToLowerInvariant()
$cases = @($matrix.cases)
if ($CaseId) {
    if (@($CaseId | Select-Object -Unique).Count -ne $CaseId.Count) { throw 'Duplicate requested case id.' }
    foreach ($requested in $CaseId) {
        if (-not @($cases | Where-Object id -eq $requested).Count) { throw "Unknown requested case: $requested" }
    }
    $cases = @($cases | Where-Object { $CaseId -contains $_.id })
}
$runtime = Join-Path $workspace '.tools/runtime'
$exe = Join-Path $runtime 'AXIOMSandbox.exe'
$profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods/axiom.native-capture'
$captures = Join-Path $profile 'captures'
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')
$snapshot = Get-AxiomExperimentSnapshot $workspace
$results = @()

function Invoke-MatrixCapture($Case, $Run, [int]$Index, [string]$Directory) {
    $before = @{}
    Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | ForEach-Object { $before[$_.Name] = $true }
    $arguments = @('--geode:axiom-sandbox', "--geode:axiom.native-capture.clock-policy=$ClockPolicy")
    if ($Run.input_mode -eq 'replay') { $arguments += '--geode:axiom.native-capture.replay' }
    $process = Start-Process -FilePath $exe -WorkingDirectory $runtime -ArgumentList $arguments -WindowStyle Hidden -PassThru
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $capture = $null
        while ($timer.Elapsed.TotalSeconds -lt 45) {
            $capture = Get-ChildItem -LiteralPath $captures -File -Filter '*.json' -ErrorAction SilentlyContinue | Where-Object { -not $before.ContainsKey($_.Name) } | Sort-Object Name | Select-Object -First 1
            if ($capture) { break }
            if ($process.HasExited) { throw 'Sandbox exited before export.' }
            Start-Sleep -Milliseconds 200
        }
        if (-not $capture) { throw 'Native matrix run timed out; preserve local evidence and logs.' }
        $destination = Join-Path $Directory ("$($Run.id)-$Index.json")
        Copy-Item -LiteralPath $capture.FullName -Destination $destination
        & $python -m axiom native $destination --json ($destination + '.native-inspection.json')
        if ($LASTEXITCODE -ne 0) { throw 'Native matrix capture failed integrity/structure validation.' }
        $data = Get-Content -LiteralPath $destination -Raw | ConvertFrom-Json
        if ($data.environment.clocks.clock_policy -ne $ClockPolicy) { throw 'Requested and effective clock policies differ.' }
        $inspectionPath = $destination + '.fixture-inspection.json'
        & $python -m axiom fixture-check $validatedPath $destination --case $Case.id --run $Run.id --json $inspectionPath
        if ($LASTEXITCODE -ne 0) { throw 'Fixture inspection failed structurally.' }
        $inspection = Get-Content -LiteralPath $inspectionPath -Raw | ConvertFrom-Json
        Write-Host "Fixture $($Case.id)/$($Run.id)/$Index : $($inspection.status) ($($data.attempt.terminal.outcome))"
        return [pscustomobject]@{
            Path = $destination; Data = $data; Inspection = $inspection
            Record = [ordered]@{
                run_id = $Run.id; repetition = $Index; outcome = $data.attempt.terminal.outcome
                terminal_command_index = $data.attempt.terminal.command_index
                observation_status = $inspection.status; checks = $inspection.checks
                observed_mode_sequences = $inspection.observed_mode_sequences
                capture_sha256 = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        }
    } finally {
        if (-not $process.HasExited -and $process.Path -eq $exe) {
            Stop-Process -Id $process.Id
            if (-not $process.WaitForExit(5000)) { throw 'Owned sandbox process did not exit.' }
        }
    }
}

try {
    & (Join-Path $PSScriptRoot 'prepare-native-sandbox.ps1') -GameDirectory $GameDirectory
    foreach ($case in $cases) {
        $casePath = Join-Path $out $case.id
        New-Item -ItemType Directory -Path $casePath | Out-Null
        [IO.File]::WriteAllText((Join-Path $runtime 'fixture-level.txt'), $case.level_string, [Text.UTF8Encoding]::new($false))
        $baselineRun = @($case.runs | Where-Object role -eq 'baseline')[0]
        $baseline = Invoke-MatrixCapture $case $baselineRun 1 $casePath
        $records = @($baseline.Record)
        $firstRuns = @{}; $firstRuns[$baselineRun.id] = $baseline.Path
        $repeatPaths = @()
        foreach ($run in @($case.runs | Where-Object role -ne 'baseline')) {
            $plan = [ordered]@{
                schema_version = 1; kind = 'native_replay'; clock = 'processCommands_call_index'
                level_sha256 = $case.level_sha256; environment_sha256 = $baseline.Data.environment_sha256
                inputs = @($run.inputs)
            }
            $planText = ($plan | ConvertTo-Json -Depth 10) + "`n"
            [IO.File]::WriteAllText((Join-Path $profile 'replay.json'), $planText, [Text.UTF8Encoding]::new($false))
            [IO.File]::WriteAllText((Join-Path $casePath ($run.id + '.plan.json')), $planText, [Text.UTF8Encoding]::new($false))
            $count = if ($run.role -eq 'replay') { $Repetitions } else { 1 }
            for ($index = 1; $index -le $count; $index++) {
                $captured = Invoke-MatrixCapture $case $run $index $casePath
                $records += $captured.Record
                if ($index -eq 1) { $firstRuns[$run.id] = $captured.Path }
                if ($run.role -eq 'replay') { $repeatPaths += $captured.Path }
            }
        }
        $comparisonPath = Join-Path $casePath 'comparison.json'
        & $python -m axiom native-compare @repeatPaths --json $comparisonPath
        if ($LASTEXITCODE -ne 0) { throw 'Native matrix repetition identities are incompatible.' }
        $comparison = Get-Content -LiteralPath $comparisonPath -Raw | ConvertFrom-Json
        $responses = @()
        foreach ($check in @($case.response_checks)) {
            $responsePath = Join-Path $casePath ($check.id + '.response.json')
            & $python -m axiom fixture-response $validatedPath $firstRuns[$check.reference_run] $firstRuns[$check.changed_run] --case $case.id --check $check.id --json $responsePath
            if ($LASTEXITCODE -ne 0) { throw 'Matrix response contrast failed structurally.' }
            $response = Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
            $responses += [ordered]@{ check_id = $check.id; status = $response.status; checks = $response.checks; first_difference = $response.first_difference }
        }
        $allMatched = @($records | Where-Object { $_.observation_status -ne 'fixture_observations_match' }).Count -eq 0
        $responsesMatched = @($responses | Where-Object { $_.status -ne 'selected_response_observed' }).Count -eq 0
        $exactOutcomes = @($case.runs | Where-Object expected_outcome -eq 'any_terminal').Count -eq 0
        $passed = $allMatched -and $responsesMatched -and $exactOutcomes -and $comparison.status -eq 'recorded_subset_consistent'
        $results += [ordered]@{
            case_id = $case.id; case_gate = if ($passed) { 'passed_for_declared_recorded_subset' } else { 'not_established' }
            level_sha256 = $case.level_sha256; environment_sha256 = $baseline.Data.environment_sha256
            collector = $baseline.Data.collector; runs = $records; responses = $responses
            comparison_status = $comparison.status; comparison_components = $comparison.component_consistency
            comparison_sha256 = (Get-FileHash -LiteralPath $comparisonPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $passedAll = @($results | Where-Object { $_.case_gate -ne 'passed_for_declared_recorded_subset' }).Count -eq 0
    $manifest = [ordered]@{
        schema_version = 1; kind = 'native_fixture_matrix_result'; recorded_at_utc = [DateTime]::UtcNow.ToString('o')
        analysis_source_commit = $sourceCommit; analysis_file_sha256 = $analysisFiles
        source_specification_sha256 = $sourceSpecificationHash
        specification_sha256 = (Get-FileHash -LiteralPath $validatedPath -Algorithm SHA256).Hash.ToLowerInvariant()
        clock_policy = $ClockPolicy; repetitions_per_replay = $Repetitions
        status = if ($passedAll) { 'declared_matrix_recorded_subset_passed' } else { 'declared_matrix_not_established' }
        cases = $results
        limitations = @('Selected mode/state observations are not a complete physics or environment model.',
            'Constructed fixtures and owned input plans do not establish ordinary-input equivalence or human AR.',
            'Exploratory outcomes, failed expectations and missing response effects cannot close a case gate.')
    }
    [IO.File]::WriteAllText((Join-Path $out 'matrix-result.json'), ($manifest | ConvertTo-Json -Depth 30), [Text.UTF8Encoding]::new($false))
    Write-Output "Native fixture matrix: $($manifest.status)"
    Write-Output "Matrix evidence: $out"
    if (-not $passedAll) { throw 'Matrix gate remains open; all comparison and observation failures retained.' }
} finally { Restore-AxiomExperimentSnapshot $snapshot }
