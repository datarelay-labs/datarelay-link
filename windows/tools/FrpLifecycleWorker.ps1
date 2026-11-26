#Requires -Version 5.1
# Internal Agent lifecycle heartbeat/synchronization worker.
$ErrorActionPreference = 'Stop'
$toolDir = $PSScriptRoot
$libDir = Join-Path (Split-Path -Parent $toolDir) 'lib'
foreach ($mod in @(
    'FrpPaths.ps1', 'FrpLock.ps1', 'FrpCrypto.ps1', 'FrpTls.ps1',
    'FrpState.ps1', 'FrpDraft.ps1', 'FrpConfig.ps1', 'FrpProcess.ps1',
    'FrpShim.ps1', 'FrpAutostart.ps1', 'FrpBootstrap.ps1', 'FrpV24.ps1', 'FrpAiExecutor.ps1'
)) {
    $path = Join-Path $libDir $mod
    if (-not (Test-Path -LiteralPath $path)) { throw "ERROR: missing module $path" }
    . $path
}

$idle = 30
$retry = 5
$backoff = $retry
$nextLifecycle = [DateTimeOffset]::MinValue
while ($true) {
    $rc = 1
    try {
        if (Test-FrpIsEnrolled) {
            $rc = 0
            if ([DateTimeOffset]::UtcNow -ge $nextLifecycle) {
                $null = Invoke-FrpAgentLifecycle -State 'connected'
                $rc = Invoke-FrpWithClientLock {
                    # A signed status-only heartbeat preserves live connections.
                    return (Invoke-FrpV24LifecycleSync)
                }
                if ($rc -eq 0) { $nextLifecycle=[DateTimeOffset]::UtcNow.AddSeconds($idle) }
            }
            # No profile is installed or enabled by upgrade. Existing local
            # lifecycle authority alone must never enable AI execution.
            if ($rc -eq 0 -and (Get-FrpAiExecutorProfile)) {
                if (Invoke-FrpNativeAiWorkerStep) {
                    $backoff=$retry
                    Start-Sleep -Milliseconds 250
                    continue
                }
            }
        }
    } catch {
        $rc = 1
    }
    if ($rc -eq 0) {
        $backoff = $retry
        Start-Sleep -Seconds $idle
    } else {
        Start-Sleep -Seconds $backoff
        $backoff = [Math]::Min(60, [Math]::Max($retry, $backoff * 2))
    }
}
