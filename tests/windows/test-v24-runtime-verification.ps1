# Verify native runtime evidence and signed acknowledgement before HEALTHY.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    Set-Content -LiteralPath (Get-FrpTomlPath) -Value '# runtime fixture'
    $script:ProcessTicks = 123456
    function Get-FrpRuntimeProcessIdentity { return $script:ProcessTicks }
    function Get-FrpClientStatus { return [pscustomobject]@{Running=$true;Pid=42} }
    $map = [ordered]@{ ssh = [ordered]@{id='ssh';enabled=$true;remote_port=6002;v24_remote_service=$true;status='DEGRADED';pending_allocation=$false} }
    $log = Get-FrpLogPath
    Set-Content -LiteralPath $log -Value '[old] login to server success [old]'
    Add-Content -LiteralPath $log -Value '[old] [agent-ssh] start proxy success'
    Save-FrpV24RuntimeBoundary -ProcessId 42
    Assert-FrpTrue (-not (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent')) 'old log success cannot verify fresh process'
    Add-Content -LiteralPath $log -Value '[current] login to server success, get run id [new]'
    Add-Content -LiteralPath $log -Value '[current] [agent-ssh] start proxy success'
    Assert-FrpTrue (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent') 'owned current process and current connection proxy success verify'
    $script:ProcessTicks++
    Assert-FrpTrue (-not (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent')) 'PID reuse fails closed'
    $script:ProcessTicks--
    Add-Content -LiteralPath $log -Value 'control worker is closed'
    Assert-FrpTrue (-not (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent')) 'closed connection invalidates success'
    Add-Content -LiteralPath $log -Value 'login to server success, get run id [next]'
    Assert-FrpTrue (-not (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent')) 'new connection needs new proxy success'
    Add-Content -LiteralPath $log -Value '[agent-ssh] start proxy success'
    Add-Content -LiteralPath $log -Value '[agent-ssh] start proxy error: denied'
    Assert-FrpTrue (-not (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent')) 'last proxy event failure invalidates success'
    Add-Content -LiteralPath $log -Value '[agent-ssh] start proxy success'
    Add-Content -LiteralPath (Get-FrpTomlPath) -Value '# changed config'
    Assert-FrpTrue (-not (Test-FrpV24RuntimeService -Item $map.ssh -HostId 'agent')) 'changed config invalidates generation'
    Save-FrpV24RuntimeBoundary -ProcessId 42
    Add-Content -LiteralPath $log -Value 'login to server success, get run id [final]'
    Add-Content -LiteralPath $log -Value '[agent-ssh] start proxy success'
    function Read-FrpClientState { return [pscustomobject]@{host_id='agent'} }
    function ConvertTo-FrpV24RemoteMap { return $map }
    function Save-FrpV24ServiceMap { param($Map) $script:Saved = $Map }
    function Invoke-FrpV24MgmtRequest {
        param($Method,$Path,$Body)
        Assert-FrpEqual '/v1/remote-services-status' $Path 'signed status report path'
        Assert-FrpTrue $Body.services[0].runtime_verified 'claim requires native runtime verification'
        return [pscustomobject]@{services=@([pscustomobject]@{name='ssh';status='HEALTHY';runtime_verified=$true;endpoint_port=6002;pending_allocation=0;reason=''})}
    }
    Assert-FrpTrue (Update-FrpV24RuntimeStatus) 'validated matching Server ACK accepted'
    Assert-FrpEqual 'HEALTHY' $script:Saved.ssh.status 'local state follows acknowledged health'
    $script:ProcessTicks++
    Assert-FrpTrue ((Format-FrpV24RemoteRecord -Item $script:Saved.ssh) -match 'State\s+: DEGRADED') 'read view never trusts stale persisted HEALTHY'
    $script:ProcessTicks--
    function Invoke-FrpV24Synchronize { throw 'stable heartbeat must not restart runtime' }
    Assert-FrpEqual 0 (Invoke-FrpV24LifecycleSync) 'stable heartbeat avoids synchronize/restart'
    function Invoke-FrpV24MgmtRequest { return [pscustomobject]@{services=@([pscustomobject]@{name='ssh';status='HEALTHY';runtime_verified=$true;endpoint_port=6099})} }
    Assert-FrpTrue (-not (Update-FrpV24RuntimeStatus)) 'different endpoint ACK rejected'
    Assert-FrpEqual 'DEGRADED' $script:Saved.ssh.status 'endpoint mismatch never leaves stale healthy'
    function Invoke-FrpV24MgmtRequest { throw 'tampered signed response' }
    $rejected = $false
    try { Update-FrpV24RuntimeStatus | Out-Null } catch { $rejected = $_.Exception.Message -eq 'tampered signed response' }
    Assert-FrpTrue $rejected 'integrity failure propagates'
    Assert-FrpEqual 'DEGRADED' $script:Saved.ssh.status 'failed integrity never leaves stale healthy'
    Write-FrpTestPass 'test-v24-runtime-verification'
} finally { Remove-FrpWindowsTestRoot }
