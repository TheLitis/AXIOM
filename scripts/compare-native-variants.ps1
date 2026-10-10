param(
    [Parameter(Mandatory = $true)][string]$MatrixPath,
    [Parameter(Mandatory = $true)][string]$StudyPath,
    [Parameter(Mandatory = $true)][string]$MatrixEvidenceDirectory,
    [string]$OutputDirectory
)

# Offline file comparison: never launches the game or authenticates records.
$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$python = Join-Path $workspace '.venv/Scripts/python.exe'
$matrixFile = (Resolve-Path -LiteralPath $MatrixPath).Path
$studyFile = (Resolve-Path -LiteralPath $StudyPath).Path
$evidence = (Resolve-Path -LiteralPath $MatrixEvidenceDirectory).Path
$out = if ($OutputDirectory) { [IO.Path]::GetFullPath($OutputDirectory) } else {
    Join-Path $workspace ('reports/native/variants-' + [guid]::NewGuid().ToString('N'))
}
if (Test-Path -LiteralPath $out) { throw 'Evidence output already exists; preserved without replacement.' }
$matrixResultPath = Join-Path $evidence 'matrix-result.json'
$matrixResult = Get-Content -LiteralPath $matrixResultPath -Raw | ConvertFrom-Json
if ($matrixResult.schema_version -ne 3 -or $matrixResult.kind -ne 'native_fixture_matrix_result' -or $matrixResult.status -ne 'declared_matrix_recorded_subset_passed') {
    throw 'Require a passed schema-3 confirming matrix manifest.'
}
$matrixHash = (Get-FileHash -LiteralPath $matrixFile -Algorithm SHA256).Hash.ToLowerInvariant()
if ($matrixHash -cne $matrixResult.source_specification_sha256) { throw 'Source matrix SHA differs from confirming result.' }
$studyHash = (Get-FileHash -LiteralPath $studyFile -Algorithm SHA256).Hash.ToLowerInvariant()
# Validate the complete bounded protocol before resolving case paths below.
& $python -c 'import sys; from axiom.interactions import load_variant_study; load_variant_study(sys.argv[1],sys.argv[2])' $studyFile $matrixFile
if ($LASTEXITCODE -ne 0) { throw 'Variant study validation failed.' }
$study = Get-Content -LiteralPath $studyFile -Raw | ConvertFrom-Json
$analysisFiles = [ordered]@{}
foreach ($relative in @('src/axiom/interactions.py', 'src/axiom/fixtures.py', 'src/axiom/native.py', 'src/axiom/cli.py', 'scripts/compare-native-variants.ps1')) {
    $analysisFiles[$relative] = (Get-FileHash -LiteralPath (Join-Path $workspace $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
}
New-Item -ItemType Directory -Path $out | Out-Null
$manifest = [ordered]@{
    kind='native_fixture_variant_study_result'; schema_version=1; status='variant_study_incomplete'
    analysis_source_commit=(& git -C $workspace rev-parse HEAD).Trim(); analysis_file_sha256=$analysisFiles
    matrix_result_sha256=(Get-FileHash -LiteralPath $matrixResultPath -Algorithm SHA256).Hash.ToLowerInvariant()
    fixture_matrix_sha256=$matrixHash; study_sha256=$studyHash; cases=@()
    authentication='not_authenticated'; ordinary_input_equivalence='not_established'; m1_gate='not_established_by_file_inspection'
}
try {
    foreach ($case in $study.cases) {
        $paths = @()
        foreach ($role in @('positive', 'control')) {
            $reference = $case.$role
            $recordedCase = @($matrixResult.cases | Where-Object case_id -ceq $reference.case_id)
            if ($recordedCase.Count -ne 1 -or $recordedCase[0].case_gate -ne 'passed_for_declared_recorded_subset') { throw 'Missing passed source case.' }
            $run = @($recordedCase[0].runs | Where-Object { $_.run_id -ceq $reference.run_id -and $_.repetition -eq 1 })
            if ($run.Count -ne 1) { throw 'Missing first source replay record.' }
            $capture = Join-Path (Join-Path $evidence $reference.case_id) ($reference.run_id + '-1.json')
            if ((Get-FileHash -LiteralPath $capture -Algorithm SHA256).Hash.ToLowerInvariant() -cne $run[0].capture_sha256) { throw 'Source capture SHA differs from manifest.' }
            $paths += $capture
        }
        $destination = Join-Path $out ($case.id + '.json')
        & $python -m axiom fixture-variants $studyFile $matrixFile $paths[0] $paths[1] --case $case.id --json $destination
        if ($LASTEXITCODE -ne 0) { throw 'Variant comparison failed structurally.' }
        $result = Get-Content -LiteralPath $destination -Raw | ConvertFrom-Json
        $manifest.cases += [ordered]@{case_id=$case.id; status=$result.status; checks=$result.checks
            result_sha256=(Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant(); capture_sha256=$result.capture_sha256}
        Write-Host "Variant $($case.id): $($result.status)"
    }
    foreach ($relative in $analysisFiles.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $workspace $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $analysisFiles[$relative]) { throw 'Analysis source changed during comparison.' }
    }
    if ((Get-FileHash -LiteralPath $studyFile -Algorithm SHA256).Hash.ToLowerInvariant() -cne $studyHash -or (Get-FileHash -LiteralPath $matrixFile -Algorithm SHA256).Hash.ToLowerInvariant() -cne $matrixHash) { throw 'Specification changed during comparison.' }
    $manifest.status = if (@($manifest.cases | Where-Object status -ne 'declared_variant_effect_observed').Count) { 'declared_variant_study_not_established' } else { 'declared_variant_study_recorded_subset_passed' }
} finally {
    $manifest.recorded_at_utc=[DateTime]::UtcNow.ToString('o')
    [IO.File]::WriteAllText((Join-Path $out 'variant-result.json'), ($manifest | ConvertTo-Json -Depth 30), [Text.UTF8Encoding]::new($false))
}
Write-Output "Variant evidence: $out"
if ($manifest.status -ne 'declared_variant_study_recorded_subset_passed') { throw 'Variant gate remains open; negative comparisons retained.' }
