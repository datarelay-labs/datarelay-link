# FrpLock.ps1 — local exclusive lock for client state/draft/runtime mutation.
# Same role as Unix frp_acquire_client_lock: serialize add/set/enable/disable,
# apply, discard, sync, update, and uninstall on one host. Read-only commands
# (status/info/list/doctor) must not take this lock.
#
# A per-root OS mutex serializes metadata publication and stale-owner reclaim.
# The directory/PID remains readable and compatible with older clients.
# Re-entrant for the same process so apply can enter internal helpers.

if ((Test-Path variable:script:FrpLockLoaded) -and $script:FrpLockLoaded) { return }
$script:FrpLockLoaded = $true
$script:FrpClientLockDepth = 0
$script:FrpClientLockOwner = $null
$script:FrpClientLockPath = $null
$script:FrpClientLockMutex = $null

function Get-FrpClientLockPath {
    Join-Path (Get-FrpStateDir) 'client-manage.lock'
}

function Get-FrpClientLockMutexName {
    $root = [IO.Path]::GetFullPath((Get-FrpWindowsRoot)).TrimEnd([char[]]@('\', '/'))
    if (Test-FrpIsWindowsHost) { $root = $root.ToUpperInvariant() }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root)) }
    finally { $sha.Dispose() }
    # SYSTEM boot workers and interactive/SSH operators use different sessions.
    return ('Global\DataRelayLinkClient-' + [BitConverter]::ToString($digest).Replace('-', ''))
}

function Test-FrpLockPidAlive {
    param([string]$ProcessId, [string]$PidPath)
    if (-not $ProcessId -or $ProcessId -notmatch '^[0-9]+$') { return $false }
    try {
        $holder = Get-Process -Id ([int]$ProcessId) -ErrorAction Stop
        # Every client management lock is written with the PowerShell $PID.
        # Windows may reuse that numeric PID for unrelated processes after an
        # interrupted command. Never let svchost.exe or another non-PowerShell
        # process indefinitely block updates, enrollment, or local recovery.
        if ($holder.ProcessName -notin @('powershell', 'pwsh')) { return $false }
        if ($PidPath -and (Test-Path -LiteralPath $PidPath)) {
            try {
                $pidWrittenAt = (Get-Item -LiteralPath $PidPath -ErrorAction Stop).LastWriteTimeUtc
                $processStartedAt = $holder.StartTime.ToUniversalTime()
                # A new PowerShell process started after this pid file was
                # written is also PID reuse, not the original lock owner.
                if ($processStartedAt -gt $pidWrittenAt) { return $false }
            } catch {
                # Unknown process timestamps are NOT proof of a stale lock.
                return $true
            }
        }
        return $true
    } catch {
        return $false
    }
}

function Enter-FrpClientLock {
    if ($script:FrpClientLockDepth -gt 0 -and [string]$script:FrpClientLockOwner -eq [string]$PID) {
        $script:FrpClientLockDepth++
        return $true
    }
    $mutex = $null
    $ownsMutex = $false
    $entered = $false
    try {
        $mutex = [Threading.Mutex]::new($false, (Get-FrpClientLockMutexName))
        try { $ownsMutex = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
        if (-not $ownsMutex) {
            Write-Host 'ERROR: another Data Relay Link Agent management operation is already running.'
            return $false
        }
        Initialize-FrpDirectories
        $lock = Get-FrpClientLockPath
        if (Test-Path -LiteralPath $lock) {
            $pidPath = Join-Path $lock 'pid'
            $old = ''
            if (Test-Path -LiteralPath $pidPath) {
                try { $old = ([string](Get-Content -LiteralPath $pidPath -ErrorAction Stop | Select-Object -First 1)).Trim() }
                catch {
                    # An unreadable ownership publication is not a dead owner.
                    Write-Host 'ERROR: another Data Relay Link Agent management operation is already running.'
                    return $false
                }
            }
            if (Test-FrpLockPidAlive -ProcessId $old -PidPath $pidPath) {
                Write-Host 'ERROR: another Data Relay Link Agent management operation is already running.'
                return $false
            }
            if ($old -notmatch '^[0-9]+$') {
                $age = ([datetime]::UtcNow - (Get-Item -LiteralPath $lock -ErrorAction Stop).LastWriteTimeUtc).TotalSeconds
                if ($age -lt 30) {
                    Write-Host 'ERROR: another Data Relay Link Agent management operation is already running.'
                    return $false
                }
            }
            Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction Stop
        }
        try {
            New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
            # Unlike the provider's mkdir check, CreateNew cannot let two
            # concurrent publishers both overwrite an ownership record.
            $pidPath = Join-Path $lock 'pid'
            $stream = [IO.File]::Open($pidPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
            try {
                $bytes = [Text.Encoding]::UTF8.GetBytes(([string]$PID + [Environment]::NewLine))
                $stream.Write($bytes, 0, $bytes.Length)
                $stream.Flush()
            } finally { $stream.Dispose() }
        } catch [IO.IOException] {
            Write-Host 'ERROR: another Data Relay Link Agent management operation is already running.'
            return $false
        }
        $script:FrpClientLockDepth = 1
        $script:FrpClientLockOwner = $PID
        $script:FrpClientLockPath = $lock
        $script:FrpClientLockMutex = $mutex
        $entered = $true
        return $true
    } catch {
        Write-Host ('ERROR: cannot acquire the Agent management lock. Retry after the current operation finishes; check local state access if the error persists. {0}' -f $_.Exception.Message)
        return $false
    } finally {
        if (-not $entered -and $null -ne $mutex) {
            if ($ownsMutex) { $mutex.ReleaseMutex() }
            $mutex.Dispose()
        }
    }
}

function Exit-FrpClientLock {
    if ($script:FrpClientLockDepth -le 0 -or [string]$script:FrpClientLockOwner -ne [string]$PID) { return }
    if ($script:FrpClientLockDepth -gt 1 -and [string]$script:FrpClientLockOwner -eq [string]$PID) {
        $script:FrpClientLockDepth--
        return
    }
    try {
        $lock = $script:FrpClientLockPath
        if ($lock -and (Test-Path -LiteralPath $lock)) {
            Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction SilentlyContinue
        }
    } finally {
        if ($null -ne $script:FrpClientLockMutex) {
            try { $script:FrpClientLockMutex.ReleaseMutex() }
            finally { $script:FrpClientLockMutex.Dispose() }
        }
        $script:FrpClientLockMutex = $null
        $script:FrpClientLockDepth = 0
        $script:FrpClientLockOwner = $null
        $script:FrpClientLockPath = $null
    }
}

function Invoke-FrpWithClientLock {
    param([Parameter(Mandatory = $true)][scriptblock]$Action)
    if (-not (Enter-FrpClientLock)) { return 1 }
    try {
        return (& $Action)
    } finally {
        Exit-FrpClientLock
    }
}
