# Native AI job policy helpers. No profile is created during install/upgrade.
# The current enrolled management identity and existing protected local state
# are the only transport/opt-in authority.
if ((Test-Path variable:script:FrpAiExecutorLoaded) -and $script:FrpAiExecutorLoaded) { return }
$script:FrpAiExecutorLoaded = $true

function ConvertTo-FrpAiWindowsPath {
    param([string]$Path)
    $raw = $Path.Replace([char]92,[char]47)
    if ($raw -cnotmatch '^[A-Za-z]:/.*$' -or $raw.Length -gt 240) { return $null }
    $suffix = $raw.Substring(3)
    if (-not $suffix) { return ($raw.Substring(0,1).ToUpperInvariant() + ':/') }
    foreach ($part in $suffix.Split('/')) {
        if (-not $part -or $part -ceq '.' -or $part -ceq '..' -or
            $part -match '[. ]$' -or $part -match '[\x00-\x1f<>:"|?*%~]' -or
            $part.Split('.')[0].TrimEnd(' ') -match '^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[0-9\u00b9\u00b2\u00b3]|LPT[0-9\u00b9\u00b2\u00b3])$') { return $null }
    }
    return ($raw.Substring(0,1).ToUpperInvariant() + ':/' + $suffix)
}

function Test-FrpAiWindowsPathScope {
    param([string]$Path, $Patterns)
    $canonical = ConvertTo-FrpAiWindowsPath $Path
    if (-not $canonical) { return $false }
    foreach ($raw in @($Patterns)) {
        if ($raw -ceq '/**') { return $true }
        $pattern = ([string]$raw).Replace([char]92,[char]47)
        $tree = $pattern.EndsWith('/**',[StringComparison]::Ordinal)
        if ($tree) { $pattern = $pattern.Substring(0,$pattern.Length-3) }
        if ($pattern -cmatch '^[A-Za-z]:$') { $pattern += '/' }
        $base = ConvertTo-FrpAiWindowsPath $pattern
        if ($base -and ($canonical -ceq $base -or ($tree -and $canonical.StartsWith($base.TrimEnd('/')+'/',[StringComparison]::Ordinal)))) { return $true }
    }
    return $false
}

function Get-FrpAiExecutorProfilePath { Join-Path (Get-FrpStateDir) 'ai-executor.json' }

function Test-FrpAiProfileAcl {
    param([string]$Path)
    if (-not (Test-FrpIsWindowsHost) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $trusted = @('S-1-5-18','S-1-5-32-544','S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
        $writeMask = [Security.AccessControl.FileSystemRights]::Write -bor [Security.AccessControl.FileSystemRights]::Delete -bor [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership
        $protectedPaths = @((Get-FrpWindowsRoot),(Get-FrpToolsDir),(Get-FrpLibDir),(Get-FrpStateDir),$Path)
        $protectedPaths += @(Get-ChildItem -LiteralPath (Get-FrpToolsDir),(Get-FrpLibDir) -Filter '*.ps1' -File -ErrorAction Stop | ForEach-Object FullName)
        foreach ($name in $protectedPaths) {
            $item = Get-Item -LiteralPath $name -Force -ErrorAction Stop
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
            $acl = Get-Acl -LiteralPath $name -ErrorAction Stop
            if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { return $false }
            $sensitive = $name -in @((Get-FrpStateDir),$Path)
            if ($sensitive -and -not $acl.AreAccessRulesProtected) { return $false }
            foreach ($entry in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
                if ($entry.AccessControlType -eq 'Allow' -and -not ($entry.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and $entry.IdentityReference.Value -notin $trusted) {
                    if ($sensitive -or ($entry.FileSystemRights -band $writeMask)) { return $false }
                }
            }
        }
        # Never opt in through a reparse ancestor or a directory that an
        # untrusted local principal can delete/replace from its parent.
        $parent = (Get-Item -LiteralPath (Get-FrpWindowsRoot)).Parent
        while ($parent) {
            if ($parent.Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
            $acl = Get-Acl -LiteralPath $parent.FullName -ErrorAction Stop
            if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $trusted) { return $false }
            foreach ($entry in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
                if ($entry.AccessControlType -eq 'Allow' -and -not ($entry.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -and $entry.IdentityReference.Value -notin $trusted -and
                    ($entry.FileSystemRights -band ([Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor [Security.AccessControl.FileSystemRights]::ChangePermissions -bor [Security.AccessControl.FileSystemRights]::TakeOwnership))) { return $false }
            }
            $parent = $parent.Parent
        }
        return $true
    } catch { return $false }
}

function Get-FrpAiExecutorProfile {
    param([switch]$ForStatus)
    $path = Get-FrpAiExecutorProfilePath
    if (-not (Test-FrpAiProfileAcl $path)) { return $null }
    try {
        if ((Get-Item -LiteralPath $path).Length -gt 16384) { return $null }
        $profile = Get-Content -LiteralPath $path -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($profile.enabled -isnot [bool] -or -not $profile.enabled -or
            [string]$profile.account_sid -notmatch '^S-1-[0-9-]+$' -or
            $profile.allow_command_exec -isnot [bool]) { return $null }
        if (-not $ForStatus -and [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne $profile.account_sid) { return $null }
        $roots = @()
        foreach ($raw in @($profile.allowed_roots)) {
            $root = ConvertTo-FrpAiWindowsPath ([string]$raw)
            if (-not $root) { return $null }
            $roots += ($root.TrimEnd('/')+'/**')
        }
        return [pscustomobject]@{ AccountSid=[string]$profile.account_sid; Patterns=$roots; AllowCommandExec=[bool]$profile.allow_command_exec }
    } catch { return $null }
}

function Get-FrpAiExecutorStatusText {
    if (Get-FrpAiExecutorProfile -ForStatus) { return 'Locally opted in; verify live readiness on Server' }
    return 'Disabled (explicit protected local opt-in required)'
}


function Initialize-FrpNativeAiFiles {
    if (-not (Test-FrpIsWindowsHost)) { throw 'Native Windows filesystem required' }
    if ('Drlink.NativeAiFiles' -as [type]) { return }
    # Hold every parent without write/delete sharing; open the leaf itself,
    # never follow a reparse point. Mutations use a verified native handle.
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Generic;
using System.Text;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Drlink {
    public static class NativeAiFiles {
        const uint Attr = 0x80, Read = 0x80000000, Write = 0x40000000, Delete = 0x10000;
        const uint Reparse = 0x400, Directory = 0x10;
        const uint OpenExisting = 3, CreateNew = 1;
        const uint OpenReparse = 0x00200000, BackupSemantics = 0x02000000;
        const int MaxBytes = 1024 * 1024;
        [StructLayout(LayoutKind.Sequential)]
        struct Info {
            public uint Attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME Creation, Access, Modified;
            public uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
        }
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
        struct RenameHeader {
            public uint Replace;
            public IntPtr Root;
            public uint NameLength;
            public char First;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
        static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool SetFileInformationByHandle(SafeFileHandle handle, int kind, IntPtr value, uint length);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, ExactSpelling=true, SetLastError=true)]
        static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle,StringBuilder buffer,uint size,uint flags);
        static IOException Failure() { return new IOException("Native file operation denied or unavailable"); }
        static void VerifyName(SafeFileHandle handle,string path) {
            var buffer=new StringBuilder(1024);
            uint size=GetFinalPathNameByHandleW(handle,buffer,(uint)buffer.Capacity,0);
            if(size==0 || size>=buffer.Capacity ||
                !String.Equals(buffer.ToString(),@"\\?\"+path,StringComparison.OrdinalIgnoreCase)) throw Failure();
        }
        static SafeFileHandle Open(string path, uint access, uint share, uint how, bool directory) {
            var h=CreateFileW(path, access, share, IntPtr.Zero, how, OpenReparse | (directory ? BackupSemantics : Attr), IntPtr.Zero);
            if (h.IsInvalid) { h.Dispose(); throw Failure(); }
            try {
                Info i;
                if (!GetFileInformationByHandle(h,out i) || (i.Attributes & Reparse)!=0 ||
                    ((i.Attributes & Directory)!=0)!=directory || (!directory && i.Links!=1)) throw Failure();
                VerifyName(h,path);
                return h;
            } catch { h.Dispose(); throw; }
        }
        static List<SafeFileHandle> Parents(string path) {
            var handles=new List<SafeFileHandle>();
            try {
                string root=Path.GetPathRoot(path);
                if (String.IsNullOrEmpty(root) || root.Length!=3 || new DriveInfo(root).DriveType!=DriveType.Fixed ||
                    !String.Equals(path,Path.GetFullPath(path),StringComparison.Ordinal)) throw Failure();
                string parent=Path.GetDirectoryName(path);
                if (String.IsNullOrEmpty(parent)) throw Failure();
                string current=root;
                handles.Add(Open(current,Attr,1,OpenExisting,true));
                string tail=parent.Substring(root.Length < parent.Length ? root.Length : parent.Length);
                if (tail.Length>0) foreach (var segment in tail.Split(Path.DirectorySeparatorChar)) {
                    current=Path.Combine(current,segment);
                    handles.Add(Open(current,Attr,1,OpenExisting,true));
                }
                return handles;
            } catch { Close(handles); throw; }
        }
        static void Close(List<SafeFileHandle> handles) {
            for (int i=handles.Count-1;i>=0;i--) handles[i].Dispose();
        }
        static void MarkDelete(SafeFileHandle handle) {
            IntPtr buf=Marshal.AllocHGlobal(1);
            try {
                Marshal.WriteByte(buf,1);
                if (!SetFileInformationByHandle(handle,4,buf,1)) throw Failure();
            } finally { Marshal.FreeHGlobal(buf); }
        }
        static void Rename(SafeFileHandle handle,string destination) {
            byte[] name=System.Text.Encoding.Unicode.GetBytes(destination);
            int off=(int)Marshal.OffsetOf(typeof(RenameHeader),"First");
            int bytes=off+name.Length+2;
            IntPtr buf=Marshal.AllocHGlobal(bytes);
            try {
                for (int i=0;i<bytes;i++) Marshal.WriteByte(buf,i,0);
                Marshal.WriteInt32(buf,0,0);
                Marshal.WriteInt32(buf,(int)Marshal.OffsetOf(typeof(RenameHeader),"NameLength"),name.Length);
                Marshal.Copy(name,0,IntPtr.Add(buf,off),name.Length);
                if (!SetFileInformationByHandle(handle,3,buf,(uint)bytes)) throw Failure();
            } finally { Marshal.FreeHGlobal(buf); }
        }
        public static byte[] ReadAll(string path) {
            var parents=Parents(path);
            try {
                using(var h=Open(path,Read|Attr,1,OpenExisting,false))
                using(var stream=new FileStream(h,FileAccess.Read)) {
                    if (stream.Length>MaxBytes) throw Failure();
                    using(var result=new MemoryStream()) {
                        byte[] b=new byte[8192]; int n;
                        while((n=stream.Read(b,0,b.Length))>0) {
                            if (result.Length+n>MaxBytes) throw Failure();
                            result.Write(b,0,n);
                        }
                        return result.ToArray();
                    }
                }
            } finally { Close(parents); }
        }
        public static void WriteAll(string path,byte[] data) {
            if (data==null || data.Length>MaxBytes) throw Failure();
            var parents=Parents(path);
            try {
                // Inspect a present destination without following it. Missing
                // leaf is accepted; any other error fails closed.
                var check=CreateFileW(path,Attr,1,IntPtr.Zero,OpenExisting,OpenReparse,IntPtr.Zero);
                int err=Marshal.GetLastWin32Error();
                bool exists=!check.IsInvalid;
                using(check) {
                    if (exists) {
                        Info i;
                        if(!GetFileInformationByHandle(check,out i) || (i.Attributes&(Reparse|Directory))!=0 || i.Links!=1) throw Failure();
                        VerifyName(check,path);
                    } else if (err!=2) throw Failure();
                }
                if (exists) {
                    // Preserve the existing file owner and ACL. An exclusive
                    // verified handle prevents leaf/link substitution during
                    // write. Restore bounded old bytes on an ordinary error.
                    using(var h=Open(path,Read|Write|Attr,0,OpenExisting,false))
                    using(var stream=new FileStream(h,FileAccess.ReadWrite)) {
                        if(stream.Length>MaxBytes) throw Failure();
                        byte[] old=new byte[(int)stream.Length]; int offset=0;
                        while(offset<old.Length) {
                            int n=stream.Read(old,offset,old.Length-offset);
                            if(n<=0) throw Failure();
                            offset+=n;
                        }
                        try {
                            stream.Position=0; stream.Write(data,0,data.Length); stream.SetLength(data.Length); stream.Flush(true);
                        } catch {
                            try { stream.Position=0; stream.Write(old,0,old.Length); stream.SetLength(old.Length); stream.Flush(true); } catch {}
                            throw;
                        }
                    }
                    return;
                }
                string temp=Path.Combine(Path.GetDirectoryName(path),".drlink-ai-"+Guid.NewGuid().ToString("N")+".tmp");
                using(var h=Open(temp,Write|Delete|Attr,0,CreateNew,false))
                using(var stream=new FileStream(h,FileAccess.Write)) {
                    try {
                        stream.Write(data,0,data.Length);
                        stream.Flush(true);
                        // Rename by the open source handle, not a mutable temp
                        // pathname. The locked parent fixes the namespace.
                        Rename(h,path);
                    } catch {
                        try { MarkDelete(h); } catch {}
                        throw;
                    }
                }
            } finally { Close(parents); }
        }
        public static void Remove(string path) {
            var parents=Parents(path);
            try { using(var h=Open(path,Delete|Attr,0,OpenExisting,false)) MarkDelete(h); }
            finally { Close(parents); }
        }
    }
}
'@ -ErrorAction Stop
}

function Invoke-FrpNativeAiFile {
    param([string]$Capability, $Arguments, $Patterns, $Profile)
    $path = ConvertTo-FrpAiWindowsPath ([string]$Arguments.path)
    if (-not $path -or $path.EndsWith('/') -or
        -not (Test-FrpAiWindowsPathScope $path $Patterns) -or
        -not (Test-FrpAiWindowsPathScope $path $Profile.Patterns)) { throw 'Path is outside allowed scope' }
    Initialize-FrpNativeAiFiles
    $native = $path.Replace([char]47,[char]92)
    switch ($Capability) {
        {$_ -in @('read_file','download_file')} {
            $bytes = [Drlink.NativeAiFiles]::ReadAll($native)
            return @{path=$path;bytes=$bytes.Length;truncated=$false;content_b64=[Convert]::ToBase64String($bytes)}
        }
        {$_ -in @('write_file','upload_file')} {
            $text = [string]$Arguments.content
            if ($text.Length -gt 1400000) { throw 'Payload too large' }
            $bytes = if ($Arguments.encoding -ceq 'base64') { [Convert]::FromBase64String($text) } else { [Text.Encoding]::UTF8.GetBytes($text) }
            if ($null -eq $bytes) { $bytes = [byte[]]@() }
            if ($bytes.Length -gt 1048576) { throw 'Payload too large' }
            [Drlink.NativeAiFiles]::WriteAll($native,[byte[]]$bytes)
            return @{path=$path;bytes=$bytes.Length}
        }
        'delete_file' {
            [Drlink.NativeAiFiles]::Remove($native)
            return @{path=$path;deleted=$true}
        }
        default { throw 'Unsupported file capability' }
    }
}


function Initialize-FrpNativeAiCommand {
    if (-not (Test-FrpIsWindowsHost)) { throw 'Native Windows execution required' }
    if ('Drlink.NativeAiCommand' -as [type]) { return }
    # A fixed child waits for stdin. Assign it to a kill-on-close Job Object
    # before delivering any operator-authorized command. No breakaway.
    Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Diagnostics;
using System.Threading.Tasks;
using System.Runtime.InteropServices;

namespace Drlink {
    public static class NativeAiCommand {
        [StructLayout(LayoutKind.Sequential)]
        struct Basic {
            public long UserTime, JobTime;
            public uint Flags;
            public UIntPtr MinWorkingSet, MaxWorkingSet;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct Counters {
            public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
        }
        [StructLayout(LayoutKind.Sequential)]
        struct Extended {
            public Basic Limits;
            public Counters Io;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        static extern IntPtr CreateJobObject(IntPtr attributes,string name);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool SetInformationJobObject(IntPtr job,int kind,IntPtr info,uint length);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool TerminateJobObject(IntPtr job,uint exitCode);
        [DllImport("kernel32.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool CloseHandle(IntPtr handle);
        public class Capture {
            public byte[] Bytes;
            public bool Truncated;
        }
        public class Outcome {
            public bool TimedOut;
            public int ExitStatus;
            public long DurationMs;
            public Capture Output, Error;
        }
        static Capture Drain(Stream stream,int limit) {
            using(var memory=new MemoryStream()) {
                var b=new byte[8192]; int n; bool truncated=false;
                while((n=stream.Read(b,0,b.Length))>0) {
                    int take=Math.Min(n,limit-(int)memory.Length);
                    if(take>0) memory.Write(b,0,take);
                    if(take<n) truncated=true;
                }
                return new Capture { Bytes=memory.ToArray(),Truncated=truncated };
            }
        }
        public static Outcome Run(string executable,string fixedArguments,string payload,int timeoutMs) {
            if (String.IsNullOrEmpty(payload) || payload.Length>32768 || timeoutMs<1 || timeoutMs>30000)
                throw new InvalidOperationException("Invalid bounded command");
            IntPtr job=CreateJobObject(IntPtr.Zero,null);
            if(job==IntPtr.Zero) throw new InvalidOperationException("Job containment unavailable");
            var limits=new Extended(); limits.Limits.Flags=0x2000; // KILL_ON_JOB_CLOSE
            IntPtr buf=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(Extended)));
            Process process=null;
            bool assigned=false;
            var timer=Stopwatch.StartNew();
            try {
                Marshal.StructureToPtr(limits,buf,false);
                if(!SetInformationJobObject(job,9,buf,(uint)Marshal.SizeOf(typeof(Extended))))
                    throw new InvalidOperationException("Job containment unavailable");
                var start=new ProcessStartInfo(executable,fixedArguments);
                start.UseShellExecute=false; start.CreateNoWindow=true;
                start.RedirectStandardInput=true; start.RedirectStandardOutput=true; start.RedirectStandardError=true;
                process=Process.Start(start);
                if(process==null || !AssignProcessToJobObject(job,process.Handle))
                    throw new InvalidOperationException("Job containment unavailable");
                assigned=true;
                var stdout=Task.Factory.StartNew(()=>Drain(process.StandardOutput.BaseStream,65536));
                var stderr=Task.Factory.StartNew(()=>Drain(process.StandardError.BaseStream,16384));
                int remaining=Math.Max(0,timeoutMs-(int)timer.ElapsedMilliseconds);
                bool delivered=false;
                if(remaining>0) {
                    var send=Task.Factory.StartNew(()=>{process.StandardInput.WriteLine(payload);process.StandardInput.Close();});
                    delivered=send.Wait(remaining);
                }
                remaining=Math.Max(0,timeoutMs-(int)timer.ElapsedMilliseconds);
                bool done=delivered && process.WaitForExit(remaining);
                int code=done ? process.ExitCode : -9;
                // Also terminate any descendants after a normal shell exit.
                if(!TerminateJobObject(job,1)) throw new InvalidOperationException("Job cleanup failed");
                if(!process.WaitForExit(5000) || !Task.WaitAll(new Task[]{stdout,stderr},5000))
                    throw new InvalidOperationException("Job cleanup incomplete");
                return new Outcome {TimedOut=!done,ExitStatus=code,DurationMs=timer.ElapsedMilliseconds,
                    Output=stdout.Result,Error=stderr.Result};
            } finally {
                if(process!=null) {
                    if(!assigned) { try { if(!process.HasExited) process.Kill(); } catch {} }
                    process.Dispose();
                }
                CloseHandle(job);
                Marshal.FreeHGlobal(buf);
            }
        }
    }
}
'@ -ErrorAction Stop
}

function Invoke-FrpNativeAiCommand {
    param([string]$Command,[int]$TimeoutMs,$Profile)
    if (-not $Profile.AllowCommandExec) { throw 'Local command execution is not opted in' }
    if (-not $Command -or [Text.Encoding]::UTF8.GetByteCount($Command) -gt 16384) { throw 'Invalid command size' }
    Initialize-FrpNativeAiCommand
    $exe = Join-Path ([Environment]::GetFolderPath('System')) 'WindowsPowerShell/v1.0/powershell.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Windows shell unavailable' }
    # Only the fixed waiting wrapper is in argv; the command arrives on stdin
    # after successful native containment. Inherit the selected OS account.
    $wrapper = @'
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.Encoding]::UTF8
try {
    $line=[Console]::ReadLine()
    if (-not $line) { exit 2 }
    $command=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($line))
    & ([scriptblock]::Create($command))
    if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }
    exit 0
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
'@
    $fixed = '-NoProfile -NonInteractive -EncodedCommand ' + [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($wrapper))
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($Command))
    $result = [Drlink.NativeAiCommand]::Run($exe,$fixed,$payload,$TimeoutMs)
    return @{result=$(if ($result.TimedOut) {'TIMEOUT'} else {'ALLOW'});exit_status=$result.ExitStatus;
        duration_ms=$result.DurationMs;stdout=[Text.Encoding]::UTF8.GetString($result.Output.Bytes);
        stderr=[Text.Encoding]::UTF8.GetString($result.Error.Bytes);stdout_truncated=$result.Output.Truncated;stderr_truncated=$result.Error.Truncated}
}

function Invoke-FrpNativeAiJob {
    param($Job,$Profile)
    try {
        $deadline = [DateTimeOffset]::Parse([string]$Job.deadline_at,[Globalization.CultureInfo]::InvariantCulture)
        $remaining = [Math]::Floor(($deadline-[DateTimeOffset]::UtcNow).TotalMilliseconds)
        if ($remaining -le 0) { throw 'Job deadline expired' }
        if (-not $Profile) { throw 'Local executor is not opted in' }
        $cap = [string]$Job.capability
        switch -CaseSensitive ($cap) {
            'get_system_info' {
                return @{sysname='Windows';nodename=[Environment]::MachineName;release=[Environment]::OSVersion.Version.ToString();machine=$(if ([Environment]::Is64BitOperatingSystem) {'amd64'} else {'x86'})}
            }
            'list_processes' {
                $lines=@('PID NAME')
                foreach ($process in @(Get-Process -ErrorAction Stop | Sort-Object Id | Select-Object -First 199)) {
                    $lines += ('{0} {1}' -f $process.Id,$process.ProcessName)
                }
                return @{lines=$lines;count=$lines.Count}
            }
            {$_ -cin @('read_file','download_file','write_file','upload_file','delete_file')} {
                return (Invoke-FrpNativeAiFile -Capability $cap -Arguments $Job.arguments -Patterns $Job.patterns -Profile $Profile)
            }
            'exec' {
                $timeout = [Math]::Min(30,[Math]::Max(1,[int]$Job.timeout))*1000
                return (Invoke-FrpNativeAiCommand -Command ([string]$Job.arguments.command) -TimeoutMs ([int][Math]::Min($timeout,$remaining)) -Profile $Profile)
            }
            default { throw 'Unsupported native AI capability' }
        }
    } catch {
        # Do not return local exception paths, command bodies, or credentials.
        return @{result='DENY';error='Native Agent operation rejected or unavailable'}
    }
}

function Invoke-FrpNativeAiWorkerStep {
    $profile = Get-FrpAiExecutorProfile
    if (-not $profile -or -not (Test-FrpIsEnrolled)) { return $false }
    # Existing signed management request verifies the response HMAC before use.
    $reply = Invoke-FrpV24MgmtRequest -Method POST -Path '/v1/ai-jobs/claim' -Body @{platform='windows';limit=1;wait_ms=5000} -TimeoutSec 15
    foreach ($job in @($reply.jobs)) {
        if ($null -eq $job) { continue }
        if ([string]$job.id -notmatch '^job_[0-9a-f]+$' -or
            [string]$job.claim_token -notmatch '^atk_[A-Za-z0-9_-]+$' -or
            [string]$job.attempt_id -notmatch '^att_[0-9a-f]+$') { throw 'Malformed signed AI job' }
        $current = Get-FrpAiExecutorProfile
        $result = Invoke-FrpNativeAiJob -Job $job -Profile $current
        # Never run the job again on completion failure. The Server owns its
        # attempt/claim token and terminal recovery state.
        $ack = Invoke-FrpV24MgmtRequest -Method POST -Path '/v1/ai-jobs/complete' -Body @{id=[string]$job.id;claim_token=[string]$job.claim_token;attempt_id=[string]$job.attempt_id;result=$result} -TimeoutSec 15
        if ($ack.ok -isnot [bool] -or -not $ack.ok) { throw 'AI completion not acknowledged' }
    }
    return $true
}
