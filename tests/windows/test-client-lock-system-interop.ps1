. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
if (-not (Test-FrpIsWindowsHost)) {
    Write-Host 'SKIP client lock SYSTEM interop: native Windows required'
    Remove-FrpWindowsTestRoot
    exit 0
}

$task = 'DrlinkLockInterop-' + [guid]::NewGuid().ToString('N')
$script:systemProbeTasks = @()
$resultPath = Join-Path $env:FRP_WINDOWS_ROOT 'system-probe.json'
$releasePath = Join-Path $env:FRP_WINDOWS_ROOT 'release-system-probe'
$xmlPath = Join-Path $env:FRP_WINDOWS_ROOT 'system-probe.xml'
$mutexName = Get-FrpClientLockMutexName
function Start-SystemProbe([bool]$Hold) {
    Remove-Item -LiteralPath $resultPath,$releasePath -Force -ErrorAction SilentlyContinue
    $source = @'
$ErrorActionPreference = 'Stop'
$m = $null; $owns = $false
try {
    $m = [Threading.Mutex]::new($false, '__MUTEX__')
    try { $owns = $m.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owns = $true }
    [IO.File]::WriteAllText('__RESULT__.tmp', ('{"acquired":' + $owns.ToString().ToLowerInvariant() + '}'))
    [IO.File]::Move('__RESULT__.tmp', '__RESULT__')
    $deadline = [datetime]::UtcNow.AddSeconds(20)
    while (__HOLD__ -and $owns -and -not [IO.File]::Exists('__RELEASE__') -and [datetime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 100
    }
} catch {
    if (-not [IO.File]::Exists('__RESULT__')) {
        [IO.File]::WriteAllText('__RESULT__.tmp', ('{"error":"' + $_.Exception.GetType().FullName + '"}'))
        [IO.File]::Move('__RESULT__.tmp', '__RESULT__')
    }
} finally {
    if ($null -ne $m) { if ($owns) { $m.ReleaseMutex() }; $m.Dispose() }
}
'@
    $source = $source.Replace('__MUTEX__',$mutexName).Replace('__RESULT__',$resultPath).Replace('__RELEASE__',$releasePath).Replace('__HOLD__',('$' + $Hold.ToString().ToLowerInvariant()))
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($source))
    $xml = New-FrpAutostartTaskXml -Command (Join-Path $PSHOME 'powershell.exe') -Arguments ('-NoProfile -EncodedCommand ' + $encoded) -DelaySeconds 0 -ExecutionTimeLimit 'PT1M'
    # Native PS7 uses pwsh; the service probe deliberately uses stock WinPS5.1.
    $xml = $xml.Replace((Join-Path $PSHOME 'powershell.exe'), (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'))
    Set-Content -LiteralPath $xmlPath -Value $xml -Encoding Unicode
    $probeTask = $task + '-' + [guid]::NewGuid().ToString('N')
    $script:systemProbeTasks += $probeTask
    $created = Invoke-FrpSchtasks -ArgString ('/Create /F /TN "{0}" /XML "{1}"' -f $probeTask,$xmlPath)
    Assert-FrpEqual 0 $created.ExitCode 'create owned SYSTEM probe'
    $ran = Invoke-FrpSchtasks -ArgString ('/Run /TN "{0}"' -f $probeTask)
    Assert-FrpEqual 0 $ran.ExitCode 'run owned SYSTEM probe'
    $deadline = [datetime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $resultPath) -and [datetime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    Assert-FrpTrue (Test-Path -LiteralPath $resultPath) 'SYSTEM probe publishes a result'
    return (Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json)
}
try {
    Assert-FrpTrue (Enter-FrpClientLock) 'operator owns lock'
    $probe = Start-SystemProbe $false
    Assert-FrpTrue (-not $probe.error -and $probe.acquired -eq $false) 'SYSTEM sees operator ownership without ACL changes'
    Exit-FrpClientLock
    $probe = Start-SystemProbe $true
    Assert-FrpTrue (-not $probe.error -and $probe.acquired -eq $true) 'SYSTEM can own the same per-root mutex'
    # Observe with synchronization rights, not the constructor's FullControl.
    $observer = [Threading.Mutex]::OpenExisting($mutexName, [Security.AccessControl.MutexRights]::Synchronize)
    try { Assert-FrpTrue (-not $observer.WaitOne(0)) 'operator opens SYSTEM mutex and observes ownership' }
    finally { $observer.Dispose() }
    Assert-FrpTrue (-not (Enter-FrpClientLock)) 'operator cannot mutate while SYSTEM owns lock'
    Set-Content -LiteralPath $releasePath -Value 'release'
    $deadline = [datetime]::UtcNow.AddSeconds(30)
    $reacquired = $false
    do {
        Start-Sleep -Milliseconds 100
        $reacquired = Enter-FrpClientLock
    } while (-not $reacquired -and [datetime]::UtcNow -lt $deadline)
    Assert-FrpTrue $reacquired 'operator reacquires after SYSTEM releases without permission changes'
    Exit-FrpClientLock
    Write-FrpTestPass 'client-lock-system-interop'
} finally {
    Set-Content -LiteralPath $releasePath -Value 'release' -ErrorAction SilentlyContinue
    Exit-FrpClientLock
    foreach ($probeTask in $script:systemProbeTasks) {
        try { $null = Invoke-FrpSchtasks -ArgString ('/End /TN "{0}"' -f $probeTask) } catch { }
        try { $null = Invoke-FrpSchtasks -ArgString ('/Delete /F /TN "{0}"' -f $probeTask) } catch { }
    }
    Remove-FrpWindowsTestRoot
}
