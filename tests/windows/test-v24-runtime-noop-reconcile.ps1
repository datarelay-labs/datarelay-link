# Reconciliation after a transient Server outage must preserve recovered sessions.
# Only byte-identical configuration AND current native process/proxy evidence
# allow reuse. Signed status acknowledgement remains a separate health gate.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    Remove-Item Env:FRP_WINDOWS_V24_FIXTURE_DIR -ErrorAction SilentlyContinue
    $script:Config = 'same configuration'
    Set-Content -LiteralPath (Get-FrpTomlPath) -Value $script:Config
    $script:Running = $true
    $script:Verified = $true
    $script:VerifiedIds = @()
    $script:Starts = 0; $script:Stops = 0; $script:Reports = 0; $script:TaskWrites = 0
    function Get-FrpTokenFromToml { return 'fixture-token' }
    function Read-FrpClientState {
        return [pscustomobject]@{frp_server='server';frp_server_port=7000;host_id='host';frp_transport='tcp';services=@{
            ssh=@{id='ssh';enabled=$true;remote_port=6002;v24_remote_service=$true}
            legacy=@{id='legacy';enabled=$true;remote_port=6205}
        }}
    }
    function New-FrpClientToml { Set-Content -LiteralPath (Get-FrpTomlPath) -Value $script:Config }
    function Test-FrpLifecycleTaskHealthy { return $true }
    function Test-FrpAutostartHealthy { return $true }
    function Install-FrpAutostartTask { $script:TaskWrites++ }
    function Set-FrpInstallStatus { param($Status) }
    function Get-FrpClientStatus { return [pscustomobject]@{Running=$script:Running;Pid=42} }
    function Test-FrpV24RuntimeService { param($Item,$HostId) $script:VerifiedIds += $Item.id; return $script:Verified }
    function Stop-FrpClient { $script:Stops++; $script:Running=$false }
    function Start-FrpClient { param([switch]$Force) $script:Starts++; $script:Running=$true }
    function Update-FrpV24RuntimeStatus { $script:Reports++; return $true }

    Update-FrpV24Runtime
    Assert-FrpEqual 0 $script:Stops 'unchanged recovered runtime must retain active connections'
    Assert-FrpEqual 0 $script:Starts 'unchanged recovered runtime must retain process identity'
    Assert-FrpEqual 0 $script:TaskWrites 'healthy boot task must not be ended/recreated'
    Assert-FrpEqual 1 $script:Reports 'reuse still requires signed status acknowledgement'
    Assert-FrpTrue ($script:VerifiedIds -contains 'ssh' -and $script:VerifiedIds -contains 'legacy') 'reuse verifies both canonical and legacy enabled proxies'

    $script:Config = 'changed configuration'
    Update-FrpV24Runtime
    Assert-FrpEqual 1 $script:Stops 'changed config restarts runtime'
    Assert-FrpEqual 1 $script:Starts 'changed config starts new generation'
    $script:Verified=$false
    Update-FrpV24Runtime
    Assert-FrpEqual 2 $script:Stops 'unverified runtime is repaired despite identical bytes'
    Assert-FrpEqual 2 $script:Starts 'unverified runtime starts new generation'
    $script:Running=$false
    Update-FrpV24Runtime
    Assert-FrpEqual 2 $script:Stops 'absent process is not stopped'
    Assert-FrpEqual 3 $script:Starts 'absent process is started'
    $script:Verified=$true
    function Start-Sleep { param($Milliseconds) }
    function Update-FrpV24RuntimeStatus { $script:Reports++; return $false }
    $beforeReports=$script:Reports
    Update-FrpV24Runtime
    Assert-FrpEqual 3 $script:Starts 'missing ACK must not restart independently verified unchanged runtime'
    Assert-FrpEqual 10 ($script:Reports-$beforeReports) 'missing ACK retains bounded status retries'
    function Update-FrpV24RuntimeStatus { throw 'tampered signed response' }
    $rejected=$false
    try { Update-FrpV24Runtime } catch { $rejected=$_.Exception.Message -eq 'tampered signed response' }
    Assert-FrpTrue $rejected 'reuse must propagate signed response integrity failures'
    Write-FrpTestPass 'test-v24-runtime-noop-reconcile'
} finally { Remove-FrpWindowsTestRoot }
