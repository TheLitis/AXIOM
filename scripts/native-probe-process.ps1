# Shared, bounded process and byte-preservation primitives for probe workers.
# Dot-sourcing this file never starts a process or touches the sandbox profile.
. (Join-Path $PSScriptRoot 'native-experiment-state.ps1')

function Get-AxiomProbeAbsolutePath([string]$Path) {
    if (-not $Path -or $Path -cne $Path.Trim() -or $Path.Length -gt 32700 -or
        $Path -notmatch '^[A-Za-z]:[\\/]' -or $Path.Substring(2).Contains(':') -or
        $Path.IndexOf([char]0) -ge 0) {
        throw 'Probe paths must be absolute local drive paths without alternate streams.'
    }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd([char[]]'\/')
    if ($full.Length -eq 2) { $full += [IO.Path]::DirectorySeparatorChar }
    if (-not [String]::Equals($Path.TrimEnd([char[]]'\/').Replace('/', '\'),
            $full.TrimEnd([char[]]'\/'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Probe paths must not contain traversal or relative components.'
    }
    foreach ($part in @($full.Substring(3) -split '[\\/]' | Where-Object { $_ })) {
        if ($part.EndsWith('.') -or $part.EndsWith(' ') -or
            $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
            $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)') {
            throw 'Probe paths contain an unsupported Windows filename component.'
        }
    }
    return $full
}

function Assert-AxiomProbeOrdinaryPath(
    [string]$Path,
    [ValidateSet('file', 'directory', 'any')][string]$Kind = 'any',
    [switch]$MissingAllowed
) {
    $full = Get-AxiomProbeAbsolutePath $Path
    $ancestors = @()
    $current = $full
    while ($current) {
        $ancestors += $current
        $current = [IO.Path]::GetDirectoryName($current)
    }
    [Array]::Reverse($ancestors)
    foreach ($current in $ancestors) {
        $item = $null
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch [Management.Automation.ItemNotFoundException] {
            if (-not $MissingAllowed) { throw "Missing probe path: $current" }
        }
        if ($item) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Redirected probe path is not allowed: $current"
            }
            if ($current -cne $full -and -not $item.PSIsContainer) {
                throw "Probe ancestor must be an ordinary directory: $current"
            }
            if ($current -ceq $full -and (($Kind -eq 'file' -and $item.PSIsContainer) -or
                    ($Kind -eq 'directory' -and -not $item.PSIsContainer))) {
                throw "Probe path has the wrong type: $current"
            }
        }
    }
}

function Assert-AxiomProbeBelow([string]$Path, [string]$Root) {
    $full = Get-AxiomProbeAbsolutePath $Path
    $rootFull = (Get-AxiomProbeAbsolutePath $Root).TrimEnd([char[]]'\/')
    if (-not $full.StartsWith($rootFull + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Probe path must remain below its intended root: $rootFull"
    }
}

function Get-AxiomProbeHash([string]$Path) {
    Assert-AxiomProbeOrdinaryPath $Path 'file'
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose(); $stream.Dispose() }
}

function Copy-AxiomProbeExactBytes(
    [string]$Source,
    [string]$Destination,
    [string]$ExpectedSha256,
    [long]$MaximumBytes = 16777216,
    [switch]$AllowExistingDestination
) {
    Assert-AxiomProbeOrdinaryPath $Source 'file'
    Assert-AxiomProbeOrdinaryPath $Destination 'file' -MissingAllowed
    Assert-AxiomProbeOrdinaryPath ([IO.Path]::GetDirectoryName($Destination)) 'directory'
    if ((Test-Path -LiteralPath $Destination) -and -not $AllowExistingDestination) {
        throw "Previous probe bytes are preserved; destination exists: $Destination"
    }
    if ([String]::Equals((Get-AxiomProbeAbsolutePath $Source), (Get-AxiomProbeAbsolutePath $Destination),
            [StringComparison]::OrdinalIgnoreCase)) { throw 'Probe byte copy source and destination must differ.' }
    if ($ExpectedSha256 -and $ExpectedSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Invalid expected byte hash.' }
    $sourceStream = [IO.File]::Open($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $targetStream = $null
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        if ($sourceStream.Length -le 0 -or $sourceStream.Length -gt $MaximumBytes) {
            throw 'Probe input/capture bytes are empty or exceed the declared bound.'
        }
        $sourceHash = [BitConverter]::ToString($hasher.ComputeHash($sourceStream)).Replace('-', '').ToLowerInvariant()
        if ($ExpectedSha256 -and $sourceHash -cne $ExpectedSha256) { throw 'Probe source byte hash differs from the frozen request.' }
        $sourceStream.Position = 0
        Assert-AxiomProbeOrdinaryPath $Destination 'file' -MissingAllowed
        $mode = if ($AllowExistingDestination) { [IO.FileMode]::Create } else { [IO.FileMode]::CreateNew }
        $targetStream = [IO.File]::Open($Destination, $mode, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $sourceStream.CopyTo($targetStream)
        $targetStream.Flush()
        $targetStream.Dispose(); $targetStream = $null
        if ((Get-AxiomProbeHash $Destination) -cne $sourceHash) { throw 'Retained probe bytes do not match their source.' }
        return $sourceHash
    } finally {
        if ($targetStream) { $targetStream.Dispose() }
        $hasher.Dispose(); $sourceStream.Dispose()
    }
}

function Write-AxiomProbeFreshJson([string]$Path, $Value) {
    Assert-AxiomProbeOrdinaryPath $Path 'file' -MissingAllowed
    Assert-AxiomProbeOrdinaryPath ([IO.Path]::GetDirectoryName($Path)) 'directory'
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes(($Value | ConvertTo-Json -Depth 30) + [Environment]::NewLine)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Assert-AxiomProbeNotCancelled([string]$EvidenceDirectory) {
    $marker = Join-Path $EvidenceDirectory 'cancel.request.json'
    Assert-AxiomProbeOrdinaryPath $marker 'file' -MissingAllowed
    if (Test-Path -LiteralPath $marker) {
        throw 'Native probe cancellation requested; owned cleanup and restoration will run.'
    }
}

function Get-AxiomProbeExceptionCleanupErrors([Exception]$Exception) {
    $errors = @()
    for ($current = $Exception; $null -ne $current; $current = $current.InnerException) {
        if ($current.Data.Contains('AxiomProbeCleanupErrors')) { $errors += @($current.Data['AxiomProbeCleanupErrors']) }
    }
    return @($errors | Select-Object -Unique)
}

function Restore-AxiomProbeExperimentSnapshot($Snapshot) {
    # Validate and restore each independent file. A redirected fixture/runtime
    # must not block restoration of the three separate profile files.
    $result = [ordered]@{ all_preserved=$false; files=@(); cleanup_errors=@() }
    $profile = Join-Path $env:LOCALAPPDATA 'AXIOMSandbox/geode/mods'
    $expected = @((Join-Path $Snapshot.RuntimeDirectory 'fixture-level.txt'),
        (Join-Path $profile 'axiom.native-capture/replay.json'),
        (Join-Path $profile 'axiom.native-capture/settings.json'),
        (Join-Path $profile 'geode.loader/settings.json'))
    if ($Snapshot.Files.Count -ne 4) { throw 'Probe restoration requires the original four-file snapshot.' }
    for ($index = 0; $index -lt 4; $index++) {
        $file = $Snapshot.Files[$index]
        $identityValid = $false
        $beforeHash = $null
        if ($file.Existed) {
            $hasher = [Security.Cryptography.SHA256]::Create()
            try { $beforeHash = [BitConverter]::ToString($hasher.ComputeHash([byte[]]$file.Bytes)).Replace('-', '').ToLowerInvariant() }
            finally { $hasher.Dispose() }
        }
        try {
            $actual = Get-AxiomProbeAbsolutePath $file.Path
            if (-not [String]::Equals($actual, (Get-AxiomProbeAbsolutePath $expected[$index]),
                    [StringComparison]::OrdinalIgnoreCase)) { throw 'Experiment snapshot path identity changed.' }
            $identityValid = $true
            Assert-AxiomProbeOrdinaryPath $file.Path 'file' -MissingAllowed
            if ($file.Existed) {
                Assert-AxiomProbeOrdinaryPath ([IO.Path]::GetDirectoryName($file.Path)) 'directory'
                [IO.File]::WriteAllBytes($file.Path, [byte[]]$file.Bytes)
            } elseif (Test-Path -LiteralPath $file.Path) { Remove-Item -LiteralPath $file.Path }
        } catch { $result.cleanup_errors += "Unable to restore experiment file ${index}: $($_.Exception.Message)" }
        $exists = $null
        $afterHash = $null
        $preserved = $false
        try {
            if (-not $identityValid) { throw 'Unsafe snapshot identity cannot be inspected.' }
            Assert-AxiomProbeOrdinaryPath $file.Path 'file' -MissingAllowed
            $exists = Test-Path -LiteralPath $file.Path
            if ($exists) { $afterHash = Get-AxiomProbeHash $file.Path }
            $preserved = $file.Existed -eq $exists -and $beforeHash -ceq $afterHash
        } catch { $result.cleanup_errors += "Unable to verify experiment file ${index}: $($_.Exception.Message)" }
        $result.files += [ordered]@{path=$expected[$index]; existed_before=[bool]$file.Existed; exists_after=$exists;
            sha256_before=$beforeHash; sha256_after=$afterHash; preserved=[bool]$preserved}
    }
    $result.all_preserved = -not $result.cleanup_errors.Count -and
        @($result.files | Where-Object { -not $_.preserved }).Count -eq 0
    return $result
}

function Enter-AxiomProbeLease([string]$ProfileDirectory) {
    $identity = (Get-AxiomProbeAbsolutePath $ProfileDirectory).ToLowerInvariant()
    Assert-AxiomProbeOrdinaryPath $ProfileDirectory 'directory' -MissingAllowed
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $suffix = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity))).Replace('-', '') }
    finally { $hasher.Dispose() }
    # Global makes the same user's profile exclusive across Windows sessions.
    $mutex = [Threading.Mutex]::new($false, ('Global\AXIOMNativeProbe-' + $suffix))
    $acquired = $false
    try {
        try { $acquired = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] {
            $mutex.ReleaseMutex()
            throw 'A preceding worker abandoned the profile lease; preservation is not established.'
        }
        if (-not $acquired) { throw 'Another native probe worker owns the sandbox profile lease.' }
        return [pscustomobject]@{ Mutex=$mutex; Acquired=$true }
    } catch { $mutex.Dispose(); throw }
}

function Exit-AxiomProbeLease($Lease) {
    if ($Lease) {
        try { if ($Lease.Acquired) { $Lease.Mutex.ReleaseMutex(); $Lease.Acquired = $false } }
        finally { $Lease.Mutex.Dispose() }
    }
}

function ConvertTo-AxiomProbeArgumentLine([string[]]$Arguments) {
    # Win32 CRT quoting; embedded quotes and trailing backslashes survive exactly.
    $quoted = foreach ($argument in $Arguments) {
        if ($null -eq $argument -or $argument.IndexOf([char]0) -ge 0) { throw 'Invalid process argument.' }
        $builder = [Text.StringBuilder]::new()
        [void]$builder.Append('"')
        $slashes = 0
        foreach ($character in $argument.ToCharArray()) {
            if ($character -eq '\') { $slashes++; continue }
            if ($character -eq '"') {
                [void]$builder.Append(('\' * (2 * $slashes + 1)))
                [void]$builder.Append('"')
            } else {
                [void]$builder.Append(('\' * $slashes))
                [void]$builder.Append($character)
            }
            $slashes = 0
        }
        [void]$builder.Append(('\' * (2 * $slashes)))
        [void]$builder.Append('"')
        $builder.ToString()
    }
    return ($quoted -join ' ')
}

function Initialize-AxiomProbeOwnedJobType {
    if ('AxiomProbeOwnedJob' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using Microsoft.Win32.SafeHandles;

public sealed class AxiomProbeOwnedJob : SafeHandleZeroOrMinusOneIsInvalid {
    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimits {
        public long ProcessUserTime, JobUserTime;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSet, MaximumWorkingSet;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters {
        public ulong ReadOperations, WriteOperations, OtherOperations;
        public ulong ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimits {
        public BasicLimits Basic;
        public IoCounters Io;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct SecurityAttributes {
        public int Length;
        public IntPtr SecurityDescriptor;
        [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct StartupInfo {
        public uint Size;
        public IntPtr Reserved, Desktop, Title;
        public uint X, Y, XSize, YSize, XCountChars, YCountChars, FillAttribute, Flags;
        public ushort ShowWindow, ReservedSize;
        public IntPtr ReservedBytes, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct StartupInfoEx {
        public StartupInfo Startup;
        public IntPtr Attributes;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInformation {
        public IntPtr Process, Thread;
        public uint ProcessId, ThreadId;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct BasicAccounting {
        public long TotalUserTime, TotalKernelTime, PeriodUserTime, PeriodKernelTime;
        public uint PageFaults, TotalProcesses, ActiveProcesses, TerminatedProcesses;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern IntPtr CreateJobObjectW(IntPtr security, string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool SetInformationJobObject(IntPtr job, int kind, ref ExtendedLimits value, uint size);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool CloseHandle(IntPtr value);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern SafeFileHandle CreateFileW(string path, uint access, uint share,
        ref SecurityAttributes security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool GetFileSizeEx(SafeFileHandle file, out long size);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, int flags, ref IntPtr size);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr kind,
        IntPtr value, IntPtr size, IntPtr previous, IntPtr returnedSize);
    [DllImport("kernel32.dll")]
    private static extern void DeleteProcThreadAttributeList(IntPtr list);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    private static extern bool CreateProcessW(string application, StringBuilder command,
        IntPtr processSecurity, IntPtr threadSecurity, bool inheritHandles, uint flags,
        IntPtr environment, string directory, ref StartupInfoEx startup, out ProcessInformation process);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool TerminateProcess(IntPtr process, uint code);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern uint WaitForSingleObject(IntPtr value, uint milliseconds);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool GetExitCodeProcess(IntPtr process, out uint code);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool belongs);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool TerminateJobObject(IntPtr job, uint code);
    [DllImport("kernel32.dll", SetLastError=true)]
    private static extern bool QueryInformationJobObject(IntPtr job, int kind,
        out BasicAccounting accounting, uint size, IntPtr returnedSize);
    private AxiomProbeOwnedJob() : base(true) {}
    public static AxiomProbeOwnedJob Create() {
        var job = new AxiomProbeOwnedJob();
        job.SetHandle(CreateJobObjectW(IntPtr.Zero, null));
        if (job.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
        var limits = new ExtendedLimits();
        limits.Basic.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (!SetInformationJobObject(job.handle, 9, ref limits, (uint)Marshal.SizeOf(typeof(ExtendedLimits)))) {
            int error = Marshal.GetLastWin32Error(); job.Dispose(); throw new Win32Exception(error);
        }
        return job;
    }
    private static SafeFileHandle OpenInheritedFile(string path, uint access, bool output) {
        var security = new SecurityAttributes();
        security.Length = Marshal.SizeOf(typeof(SecurityAttributes)); security.InheritHandle = true;
        var file = CreateFileW(path, access, 1, ref security, 3, 0x80, IntPtr.Zero); // OPEN_EXISTING
        if (file.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
        if (output) {
            long length;
            if (!GetFileSizeEx(file, out length)) {
                int error = Marshal.GetLastWin32Error(); file.Dispose(); throw new Win32Exception(error);
            }
            if (length != 0) { file.Dispose(); throw new InvalidOperationException("Reserved console output is no longer empty."); }
        }
        return file;
    }
    public Process StartSuspended(string executable, string command, string directory,
        string stdout, string stderr, bool hidden) {
        if (IsClosed || IsInvalid) throw new InvalidOperationException("Owned job is already closed.");
        SafeFileHandle input = null, output = null, errorOutput = null;
        IntPtr attributes = IntPtr.Zero, inherited = IntPtr.Zero;
        bool attributesInitialized = false, created = false;
        var information = new ProcessInformation();
        Process owned = null;
        try {
            input = OpenInheritedFile("NUL", 0x80000000, false);
            output = OpenInheritedFile(stdout, 0x40000000, true);
            errorOutput = OpenInheritedFile(stderr, 0x40000000, true);
            IntPtr size = IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref size);
            if (size == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            attributes = Marshal.AllocHGlobal(size);
            if (!InitializeProcThreadAttributeList(attributes, 1, 0, ref size)) throw new Win32Exception(Marshal.GetLastWin32Error());
            attributesInitialized = true;
            inherited = Marshal.AllocHGlobal(IntPtr.Size * 3);
            Marshal.WriteIntPtr(inherited, 0, input.DangerousGetHandle());
            Marshal.WriteIntPtr(inherited, IntPtr.Size, output.DangerousGetHandle());
            Marshal.WriteIntPtr(inherited, IntPtr.Size * 2, errorOutput.DangerousGetHandle());
            if (!UpdateProcThreadAttribute(attributes, 0, new IntPtr(0x20002), inherited,
                    new IntPtr(IntPtr.Size * 3), IntPtr.Zero, IntPtr.Zero)) throw new Win32Exception(Marshal.GetLastWin32Error());
            var startup = new StartupInfoEx();
            startup.Startup.Size = (uint)Marshal.SizeOf(typeof(StartupInfoEx));
            startup.Startup.Flags = 0x101; // STARTF_USESHOWWINDOW | STARTF_USESTDHANDLES
            startup.Startup.ShowWindow = hidden ? (ushort)0 : (ushort)1;
            startup.Startup.Input = input.DangerousGetHandle();
            startup.Startup.Output = output.DangerousGetHandle();
            startup.Startup.Error = errorOutput.DangerousGetHandle();
            startup.Attributes = attributes;
            uint flags = 0x4 | 0x80000 | 0x400; // SUSPENDED | EXTENDED_STARTUPINFO | UNICODE_ENVIRONMENT
            if (hidden) flags |= 0x8000000; // CREATE_NO_WINDOW for headless console checks
            if (!CreateProcessW(executable, new StringBuilder(command), IntPtr.Zero, IntPtr.Zero, true,
                    flags, IntPtr.Zero, directory, ref startup, out information)) throw new Win32Exception(Marshal.GetLastWin32Error());
            created = true;
            // No application instruction or descendant creation can precede
            // job assignment: the primary thread is still suspended here.
            if (!AssignProcessToJobObject(handle, information.Process)) throw new Win32Exception(Marshal.GetLastWin32Error());
            // The retained creation handle prevents PID reuse while the managed
            // Process wrapper obtains its own handle. Cleanup keeps this object.
            owned = Process.GetProcessById((int)information.ProcessId);
            IntPtr retainedProcessHandle = owned.Handle;
            if (ResumeThread(information.Thread) != 1) throw new Win32Exception(Marshal.GetLastWin32Error());
            return owned;
        } catch (Exception primary) {
            string cleanup = "";
            if (created) {
                uint exitCode;
                if ((!GetExitCodeProcess(information.Process, out exitCode) || exitCode == 259) &&
                        !TerminateProcess(information.Process, 2)) cleanup += " Owned-process termination failed: " + Marshal.GetLastWin32Error();
                if (WaitForSingleObject(information.Process, 30000) != 0) cleanup += " Owned-process termination wait failed.";
            }
            if (owned != null) owned.Dispose();
            var failure = new InvalidOperationException("Suspended owned-process launch failed: " + primary.Message, primary);
            if (cleanup.Length != 0) failure.Data["AxiomProbeCleanupErrors"] = new string[] { cleanup.Trim() };
            throw failure;
        } finally {
            if (information.Thread != IntPtr.Zero) CloseHandle(information.Thread);
            if (information.Process != IntPtr.Zero) CloseHandle(information.Process);
            if (attributesInitialized) DeleteProcThreadAttributeList(attributes);
            if (attributes != IntPtr.Zero) Marshal.FreeHGlobal(attributes);
            if (inherited != IntPtr.Zero) Marshal.FreeHGlobal(inherited);
            if (errorOutput != null) errorOutput.Dispose();
            if (output != null) output.Dispose();
            if (input != null) input.Dispose();
        }
    }
    public bool Contains(Process process) {
        bool belongs;
        if (!IsProcessInJob(process.Handle, handle, out belongs)) throw new Win32Exception(Marshal.GetLastWin32Error());
        return belongs;
    }
    public void TerminateAndDrain(int timeoutMilliseconds) {
        if (IsClosed) return;
        if (!TerminateJobObject(handle, 2)) throw new Win32Exception(Marshal.GetLastWin32Error());
        var timer = Stopwatch.StartNew();
        while (true) {
            BasicAccounting accounting;
            if (!QueryInformationJobObject(handle, 1, out accounting,
                    (uint)Marshal.SizeOf(typeof(BasicAccounting)), IntPtr.Zero)) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (accounting.ActiveProcesses == 0) return;
            if (timer.ElapsedMilliseconds >= timeoutMilliseconds) throw new TimeoutException("Owned job did not drain before its cleanup deadline.");
            Thread.Sleep(20);
        }
    }
    protected override bool ReleaseHandle() { return CloseHandle(handle); }
}
'@
}

function Start-AxiomProbeOwnedProcess(
    [string]$Workspace,
    [string]$EvidenceDirectory,
    [string]$Executable,
    [string]$WorkingDirectory,
    [string[]]$Arguments,
    [ValidatePattern('^[a-z][a-z0-9-]*$')][string]$LogName,
    [ValidateSet('Hidden', 'Normal')][string]$WindowStyle = 'Hidden'
) {
    Assert-AxiomProbeOrdinaryPath $Workspace 'directory'
    Assert-AxiomProbeBelow $EvidenceDirectory $Workspace
    Assert-AxiomProbeOrdinaryPath $EvidenceDirectory 'directory'
    Assert-AxiomProbeOrdinaryPath $Executable 'file'
    Assert-AxiomProbeOrdinaryPath $WorkingDirectory 'directory'
    $stdout = Join-Path $EvidenceDirectory ($LogName + '.stdout.txt')
    $stderr = Join-Path $EvidenceDirectory ($LogName + '.stderr.txt')
    foreach ($path in @($stdout, $stderr)) {
        Assert-AxiomProbeOrdinaryPath $path 'file' -MissingAllowed
        if (Test-Path -LiteralPath $path) { throw 'Previous probe console evidence is preserved; choose new log paths.' }
    }
    $argumentLine = ConvertTo-AxiomProbeArgumentLine (@($Executable) + $Arguments)
    Initialize-AxiomProbeOwnedJobType
    $job = [AxiomProbeOwnedJob]::Create()
    $owned = $null
    try {
        # CreateNew reserves both names without replacing any prior evidence.
        foreach ($path in @($stdout, $stderr)) {
            $reservation = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $reservation.Dispose()
        }
        Assert-AxiomProbeOrdinaryPath $EvidenceDirectory 'directory'
        $owned = $job.StartSuspended($Executable, $argumentLine, $WorkingDirectory, $stdout, $stderr, ($WindowStyle -eq 'Hidden'))
        return [pscustomobject]@{ Process=$owned; Job=$job; stdout_path=$stdout; stderr_path=$stderr }
    } catch {
        $primary = $_.Exception
        $failures = @(Get-AxiomProbeExceptionCleanupErrors $primary)
        try { if ($owned) { Stop-AxiomOwnedProcess $owned } }
        catch { $failures += $_.Exception.Message }
        try { $job.TerminateAndDrain(30000) }
        catch { $failures += $_.Exception.Message }
        finally {
            try { $job.Dispose() }
            catch { $failures += $_.Exception.Message }
        }
        if ($failures.Count) { $primary.Data['AxiomProbeCleanupErrors'] = [string[]]$failures }
        throw $primary
    }
}

function Complete-AxiomProbeOwnedProcess($Owned) {
    $record = [ordered]@{ process_cleanup=$null; cleanup_errors=@() }
    if (-not $Owned) { return $record }
    try {
        $exited = $Owned.Process.HasExited
        $record.process_cleanup = [ordered]@{
            exit_observed_before_cleanup=[bool]$exited
            termination_requested=(-not $exited)
            natural_exit_code=$(if ($exited) { $Owned.Process.ExitCode } else { $null })
        }
    } catch { $record.cleanup_errors += $_.Exception.Message }
    try { Stop-AxiomOwnedProcess $Owned.Process }
    catch { $record.cleanup_errors += $_.Exception.Message }
    finally {
        try { $Owned.Job.TerminateAndDrain(30000) }
        catch { $record.cleanup_errors += $_.Exception.Message }
        try { $Owned.Job.Dispose() }
        catch { $record.cleanup_errors += $_.Exception.Message }
    }
    return $record
}

function Invoke-AxiomProbeConsoleProcess(
    [string]$Workspace,
    [string]$EvidenceDirectory,
    [string]$Executable,
    [string]$WorkingDirectory,
    [string[]]$Arguments,
    [ValidatePattern('^[a-z][a-z0-9-]*$')][string]$LogName,
    [ValidateRange(1, 600)][int]$TimeoutSeconds = 30,
    [string]$CancellationDirectory
) {
    $owned = $null
    $result = [ordered]@{kind='headless_probe_console_process'; status='runner_error'; exit_code=$null;
        timeout_reached=$false; error=$null; stdout_path=$null; stderr_path=$null;
        process_cleanup=$null; cleanup_errors=@()}
    try {
        if ($CancellationDirectory) {
            Assert-AxiomProbeBelow $CancellationDirectory $Workspace
            Assert-AxiomProbeOrdinaryPath $CancellationDirectory 'directory'
            Assert-AxiomProbeNotCancelled $CancellationDirectory
        }
        $owned = Start-AxiomProbeOwnedProcess $Workspace $EvidenceDirectory $Executable $WorkingDirectory $Arguments $LogName 'Hidden'
        $result.stdout_path = $owned.stdout_path; $result.stderr_path = $owned.stderr_path
        $timer = [Diagnostics.Stopwatch]::StartNew()
        $exited = $false
        while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
            if ($CancellationDirectory) { Assert-AxiomProbeNotCancelled $CancellationDirectory }
            if ($owned.Process.WaitForExit(250)) { $exited = $true; break }
        }
        if (-not $exited) {
            $result.timeout_reached = $true
            throw "Owned probe console reached the $TimeoutSeconds-second deadline."
        }
        if ($CancellationDirectory) { Assert-AxiomProbeNotCancelled $CancellationDirectory }
        $result.exit_code = $owned.Process.ExitCode
        if ($null -eq $result.exit_code -or $result.exit_code -ne 0) {
            throw "Owned probe console exited with code $($result.exit_code)."
        }
        $result.status = 'completed'
    } catch {
        $result.error = $_.Exception.Message
        $result.cleanup_errors += @(Get-AxiomProbeExceptionCleanupErrors $_.Exception)
    }
    finally {
        $cleanup = Complete-AxiomProbeOwnedProcess $owned
        $result.process_cleanup = $cleanup.process_cleanup
        $result.cleanup_errors += @($cleanup.cleanup_errors)
        if ($result.cleanup_errors.Count) {
            $result.status = 'runner_error'
            if (-not $result.error) { $result.error = $result.cleanup_errors[0] }
        }
    }
    return $result
}
