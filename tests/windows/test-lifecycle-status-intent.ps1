. (Join-Path $PSScriptRoot '_import.ps1')
# Isolate process/task observations; persist actual intent in the test root.
function Test-FrpIsEnrolled { return $true }
function Test-FrpAutostartTaskExists { param([string]$TaskName) return $script:TasksEnabled }
$script:TasksEnabled = $false
try {
    $status = Get-FrpClientStatus
    Assert-FrpEqual 'unknown' $status.RuntimeIntent 'legacy absence does not invent pause intent'
    Assert-FrpEqual 'Stopped (intent unknown)' $status.RuntimeState 'legacy stopped state is explicit'
    Set-FrpClientRuntimeIntent -Intent paused
    $status = Get-FrpClientStatus
    Assert-FrpEqual 'Paused (intentional)' $status.RuntimeState 'deliberate pause differs from crash'
    Assert-FrpEqual $false $status.AutostartEnabled 'disabled autostart visible'
    $script:TasksEnabled = $true
    Set-FrpClientRuntimeIntent -Intent active
    $status = Get-FrpClientStatus
    Assert-FrpEqual 'Stopped (unexpected)' $status.RuntimeState 'active intent with missing process is unexpected'
    Assert-FrpEqual $true $status.AutostartEnabled 'enabled autostart visible'
    Set-Content -LiteralPath (Join-Path (Get-FrpStateDir) 'runtime-intent.json') -Value 'invalid-json'
    Assert-FrpEqual 'unknown' (Get-FrpClientStatus).RuntimeIntent 'corrupt marker never invents intent'
    Write-FrpTestPass 'lifecycle-status-intent'
} finally { Remove-FrpWindowsTestRoot }
