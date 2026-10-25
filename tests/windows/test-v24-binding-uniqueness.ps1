. (Join-Path $PSScriptRoot '_import.ps1')
try {
    function Test-FrpIsEnrolled { return $true }
    function Read-FrpClientState { return [pscustomobject]@{machine_id='agent-id'} }
    $script:catalog = [pscustomobject]@{serviceObjects=@([pscustomobject]@{name='ssh';type='tcp';port=22});networkObjects=@();managedHosts=@([pscustomobject]@{id='agent-id';name='agent-name';hostname='agent-host';addresses=@('127.0.0.1')})}
    function Get-FrpV24Catalog { return $script:catalog }
    $script:map = @{original=[pscustomobject]@{name='original';destination='this-host';service_object='ssh';v24_remote_service=$true;enabled=$false;remote_port=6000}}
    function ConvertTo-FrpV24RemoteMap { return $script:map }
    function Get-FrpV24RemoteRecord { param($Name) return $script:map[$Name] }
    $script:requests = 0
    function Invoke-FrpV24MgmtRequest { $script:requests++; throw 'Unexpected network request' }
    foreach ($dest in @('this-host','SELF','agent-name','agent-host')) {
        $rejected = $false
        try { Invoke-FrpV24SetRemoteService -Name 'duplicate' -Destination $dest -Service 'ssh' -SkipRuntime -Quiet }
        catch { $rejected = $_.Exception.Message -match 'already uses.*original' }
        Assert-FrpTrue $rejected ('duplicate rejected before network: '+$dest)
    }
    Assert-FrpEqual 0 $script:requests 'no request or port allocated'
    $bundle = [pscustomobject]@{remoteServices=@([pscustomobject]@{name='duplicate';destination='self';service='ssh';enabled=$true})}
    $rejected=$false
    try { Get-FrpV24BundlePlan $bundle | Out-Null } catch { $rejected=$_.Exception.Message -match 'already uses' }
    Assert-FrpTrue $rejected 'read-only plan rejects duplicate'
    Assert-FrpEqual 1 $script:map.Count 'rejected preview does not mutate desired state'
    $replacement = [pscustomobject]@{remoteServices=@(
        [pscustomobject]@{name='replacement';destination='self';service='ssh';enabled=$true},
        [pscustomobject]@{name='original';state='absent'})}
    $plan = Get-FrpV24BundlePlan $replacement
    Assert-FrpEqual 2 $plan.Count 'delete and replacement plan accepts either document order'
    Assert-FrpEqual 1 $script:map.Count 'successful preview does not mutate desired state'
    Assert-FrpTrue $script:map.ContainsKey('original') 'original remains before apply'

    $script:map=@{}
    $bundle.remoteServices=@([pscustomobject]@{name='a';destination='self';service='ssh';enabled=$true},[pscustomobject]@{name='b';destination='agent-name';service='ssh';enabled=$true})
    $rejected=$false
    try { Get-FrpV24BundlePlan $bundle | Out-Null } catch { $rejected=$_.Exception.Message -match 'already uses' }
    Assert-FrpTrue $rejected 'bundle cannot introduce two aliases of one binding'
    Write-FrpTestPass 'v24-binding-uniqueness'
} finally { Remove-FrpWindowsTestRoot }
