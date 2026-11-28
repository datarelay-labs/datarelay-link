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


# Independent retry clocks: a failed Remote Service reconciliation must not
# starve authenticated claims, and an AI failure must not starve lifecycle.
$idle = 30
$retry = 5
$lifecycleBackoff = $retry
$aiBackoff = $retry
$nextLifecycle = [DateTimeOffset]::MinValue
$nextAi = [DateTimeOffset]::MinValue
$nextReceipt = [DateTimeOffset]::MinValue
$lastLifecycle = 'NOT_TESTED'
$lastAi = 'NOT_TESTED'
while ($true) {
    $now = [DateTimeOffset]::UtcNow
    $lifecycleDue = $now -ge $nextLifecycle
    $aiDue = $now -ge $nextAi
    if (-not $lifecycleDue -and -not $aiDue) {
        Start-Sleep -Milliseconds 250
        continue
    }
    $cycle = Invoke-FrpLifecycleWorkerCycle -LifecycleDue:$lifecycleDue -AiDue:$aiDue
    $now = [DateTimeOffset]::UtcNow
    $changed = $false
    if ($lifecycleDue) {
        $changed = $changed -or ($lastLifecycle -ne $cycle.Lifecycle)
        $lastLifecycle = $cycle.Lifecycle
        if ($lastLifecycle -eq 'SYNC_OK') {
            $lifecycleBackoff = $retry
            $nextLifecycle = $now.AddSeconds($idle)
        } else {
            $nextLifecycle = $now.AddSeconds($lifecycleBackoff)
            $lifecycleBackoff = [Math]::Min(60, $lifecycleBackoff * 2)
        }
    }
    if ($aiDue) {
        $changed = $changed -or ($lastAi -ne $cycle.Ai)
        $lastAi = $cycle.Ai
        if ($lastAi -eq 'CLAIM_OK') {
            $aiBackoff = $retry
            $nextAi = $now.AddMilliseconds(250)
        } elseif ($lastAi -in @('LOCAL_PROFILE_UNAVAILABLE','NOT_ENROLLED')) {
            $aiBackoff = $retry
            $nextAi = $now.AddSeconds($idle)
        } else {
            $nextAi = $now.AddSeconds($aiBackoff)
            $aiBackoff = [Math]::Min(60, $aiBackoff * 2)
        }
    }
    if ($changed -or $now -ge $nextReceipt) {
        Write-FrpWorkerStatus -Lifecycle $lastLifecycle -Ai $lastAi
        $nextReceipt = $now.AddSeconds($idle)
    }
}
