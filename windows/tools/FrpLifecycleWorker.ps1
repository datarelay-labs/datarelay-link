#Requires -Version 5.1
# Internal Agent lifecycle heartbeat/synchronization worker.
$ErrorActionPreference = 'Stop'
$toolDir = $PSScriptRoot
$libDir = Join-Path (Split-Path -Parent $toolDir) 'lib'
foreach ($mod in @(
    'FrpPaths.ps1', 'FrpLock.ps1', 'FrpCrypto.ps1', 'FrpTls.ps1',
    'FrpState.ps1', 'FrpDraft.ps1', 'FrpConfig.ps1', 'FrpProcess.ps1',
    'FrpShim.ps1', 'FrpAutostart.ps1', 'FrpBootstrap.ps1', 'FrpV24.ps1'
)) {
    $path = Join-Path $libDir $mod
    if (-not (Test-Path -LiteralPath $path)) { throw "ERROR: missing module $path" }
    . $path
}

$idle = 30
$retry = 5
$backoff = $retry
while ($true) {
    $rc = 1
    try {
        if (Test-FrpIsEnrolled) {
            $null = Invoke-FrpAgentLifecycle -State 'connected'
            $rc = Invoke-FrpWithClientLock { return (Invoke-FrpV24Synchronize) }
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
