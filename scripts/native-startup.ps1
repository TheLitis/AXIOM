# Bounded console-only startup diagnostics. Never launches the game or sends input.
function Invoke-AxiomStartupTool(
    [string]$Workspace,
    [string]$EvidenceDirectory,
    [string[]]$Arguments,
    [ValidatePattern('^startup-[a-z-]+$')][string]$LogName
) {
    $root = [IO.Path]::GetFullPath($Workspace).TrimEnd([char[]]'\/')
    $out = [IO.Path]::GetFullPath($EvidenceDirectory)
    if (-not $out.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Startup console diagnostics must remain within this workspace.'
    }
    $ancestor = $out
    while ($ancestor -ne $root) {
        $item = Get-Item -LiteralPath $ancestor -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Startup diagnostic directory must be ordinary.'
        }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
    $python = Join-Path $root '.venv/Scripts/python.exe'
    $stdout = Join-Path $out ($LogName + '.stdout.txt')
    $stderr = Join-Path $out ($LogName + '.stderr.txt')
    if ((Test-Path -LiteralPath $stdout) -or (Test-Path -LiteralPath $stderr)) {
        throw 'Previous startup console evidence is preserved; choose new log paths.'
    }
    $argumentLine = (@(@('-m', 'axiom') + $Arguments | ForEach-Object {
        if ($_.Contains('"')) { throw 'Unsupported quote in startup console argument.' }
        '"' + ($_ -replace '(\\+)$', '$1$1') + '"'
    }) -join ' ')
    $owned = $null
    try {
        $owned = Start-Process -FilePath $python -WorkingDirectory $root -ArgumentList $argumentLine -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        $ownedHandle = $owned.Handle
        if (-not $owned.WaitForExit(30000)) { throw 'Startup console diagnostics exceeded 30 seconds; output retained.' }
        $exitCode = $owned.ExitCode
        if ($null -eq $exitCode -or $exitCode -ne 0) {
            throw "Startup console diagnostics exited with code $exitCode; output retained at $stderr"
        }
        return [ordered]@{exit_code=$exitCode; stdout_path=$stdout; stderr_path=$stderr}
    } finally {
        if ($owned) {
            try {
                if (-not $owned.HasExited) {
                    Stop-Process -InputObject $owned -Force
                    if (-not $owned.WaitForExit(30000)) { throw 'Owned diagnostic console did not stop.' }
                }
            } finally { $owned.Dispose() }
        }
    }
}
