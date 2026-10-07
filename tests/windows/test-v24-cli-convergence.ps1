# test-v24-cli-convergence.ps1 — canonical Windows Agent surface.
. (Join-Path $PSScriptRoot 'common.ps1')
$client = Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
$hostExe = 'pwsh'
try { $hostExe = (Get-Process -Id $PID).Path } catch { }
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ('drlink-win-v24-' + [guid]::NewGuid().ToString('N'))
$fixture = Join-Path $tmp 'fixture'
$env:FRP_WINDOWS_ROOT = $tmp
$env:FRP_WINDOWS_V24_FIXTURE_DIR = $fixture
$env:FRP_WINDOWS_TEST_CONFIRM = 'yes'
New-Item -ItemType Directory -Path (Join-Path $tmp 'state'), (Join-Path $tmp 'config'), $fixture -Force | Out-Null
Set-Content -LiteralPath (Join-Path $tmp 'state/client-identity.pub') -Value 'fixture-public'
Set-Content -LiteralPath (Join-Path $tmp 'state/client-identity.key') -Value 'fixture-private'
Set-Content -LiteralPath (Join-Path $tmp 'config/frpc.toml') -Value 'auth.token = "fixture-token"'
$state = [ordered]@{
    schema_version=1; allocator_url='https://example.test/enroll'; frp_server='example.test'
    frp_server_port=7000; frp_transport='tcp'; hostname='win-agent'
    machine_id='00112233445566778899aabbccddeeff'; host_id='win-agent-00112233'
    services=@{}; management_only=$true; project_version='2.4.0'; frp_version='0.71.0'
    platform='windows'; install_status='management_only'
}
$state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $tmp 'state/client-state.json')
$catalog = [ordered]@{
    serviceObjects=@(
        @{name='ssh';type='tcp';port=22},
        @{name='license';type='fixed-tcp';port=27000},
        @{name='dns';type='udp';port=53}
    )
    networkObjects=@(); managedHosts=@()
}
$catalog | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $fixture 'catalog.json')

function Run-Cli {
    param([string[]]$CliArgs)
    $lines = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $client @CliArgs 2>&1
    $rc = $LASTEXITCODE
    $out = $lines | Out-String
    return @{ Rc=$rc; Out=$out }
}
try {
    $help = Run-Cli @('help')
    Assert-FrpEqual 0 $help.Rc 'help exit'
    Assert-FrpTrue ($help.Out -match 'show remote-services') 'canonical remote-services advertised'
    Assert-FrpTrue ($help.Out -match 'test configuration') 'ConfigurationBundle advertised'
    Assert-FrpTrue ($help.Out -notmatch 'show services') 'noncanonical show services hidden'

    foreach ($legacy in @(@('status'), @('doctor'), @('service','list'), @('client','info'))) {
        $r = Run-Cli $legacy
        Assert-FrpTrue ($r.Rc -ne 0) ('legacy path rejected: ' + ($legacy -join ' '))
    }
    $empty = Run-Cli @('show','remote-services')
    Assert-FrpEqual 0 $empty.Rc 'empty remote-services exit'
    Assert-FrpTrue ($empty.Out -match 'No Remote Services configured') 'empty state explicit'

    $set = Run-Cli @('set','remote-service','ssh-access','destination','this-host','service','ssh','enabled')
    if ($set.Rc -ne 0) { Write-Host $set.Out }
    Assert-FrpEqual 0 $set.Rc 'set remote-service exit'
    Assert-FrpTrue ($set.Out -match 'Remote Service: ssh-access') 'set output canonical'

    $show = Run-Cli @('show','remote-service','ssh-access')
    Assert-FrpEqual 0 $show.Rc 'show remote-service exit'
    Assert-FrpTrue ($show.Out -match 'Service\s+: ssh') 'show service object'
    Assert-FrpTrue ($show.Out -match 'Endpoint\s+: fixture\.example\.test:6001') 'show allocated endpoint'

    $disable = Run-Cli @('set','remote-service','ssh-access','disabled')
    if ($disable.Rc -ne 0) { Write-Host $disable.Out }
    Assert-FrpEqual 0 $disable.Rc 'partial edit preserves existing fields'
    Assert-FrpTrue ($disable.Out -match 'DISABLED') 'disable state'

    $udp = Run-Cli @('set','remote-service','bad-dns','destination','this-host','service','dns','enabled')
    Assert-FrpTrue ($udp.Rc -ne 0) 'UDP Remote Service rejected'
    Assert-FrpTrue ($udp.Out -match 'UDP Service Object') 'UDP guidance'

    # Upgrade convergence: pre-v2.4 enrolled service becomes canonical Remote
    # Service on explicit synchronize without changing its public endpoint.
    $statePath = Join-Path $tmp 'state/client-state.json'
    $legacyState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $legacyServices = [ordered]@{}
    foreach ($prop in $legacyState.services.PSObject.Properties) { $legacyServices[$prop.Name] = $prop.Value }
    $legacyServices['legacy-ssh'] = [ordered]@{
        id='legacy-ssh'; name='Legacy SSH'; preset='ssh'; protocol='tcp'
        local_ip='127.0.0.1'; local_port=22; remote_port=6022; enabled=$true
    }
    $legacyState.services = [pscustomobject]$legacyServices
    $legacyState | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $statePath
    $migrate = Run-Cli @('system','synchronize')
    Assert-FrpEqual 0 $migrate.Rc 'legacy service synchronize exits 0'
    $migrated = Run-Cli @('show','remote-service','legacy-ssh')
    Assert-FrpEqual 0 $migrated.Rc 'migrated Remote Service visible'
    Assert-FrpTrue ($migrated.Out -match 'Service\s+: ssh') 'legacy preset mapped to Service Object'
    Assert-FrpTrue ($migrated.Out -match 'Endpoint\s+: fixture\.example\.test:6022') 'legacy endpoint preserved'

    $export = Join-Path $tmp 'agent.yaml'
    $er = Run-Cli @('system','export','configuration',$export)
    Assert-FrpEqual 0 $er.Rc 'bundle export exit'
    Assert-FrpTrue (Test-Path -LiteralPath $export) 'bundle export exists'

    $test = Run-Cli @('test','configuration',$export)
    Assert-FrpEqual 0 $test.Rc 'bundle test exit'
    Assert-FrpTrue ($test.Out -match 'VALID') 'bundle test valid'

    $wrongContext = Join-Path $tmp 'wrong-context.json'
    '{"configurationBundle":{"context":"server","remoteServices":[]}}' |
        Set-Content -LiteralPath $wrongContext
    $wrong = Run-Cli @('test','configuration',$wrongContext)
    Assert-FrpTrue ($wrong.Rc -ne 0) 'server-context Bundle rejected on Agent'
    Assert-FrpTrue ($wrong.Out -match 'context must be agent') 'context mismatch guidance'

    $diff = Run-Cli @('system','diff','configuration',$export)
    Assert-FrpEqual 0 $diff.Rc 'bundle diff exit'
    Assert-FrpTrue ($diff.Out -match 'NO CHANGE') 'bundle diff no change'

    $bundle = Join-Path $tmp 'apply.yaml'
    @'
configurationBundle:
  context: agent
  remoteServices:
    - name: fixed-license
      destination: this-host
      service: license
      enabled: true
'@ | Set-Content -LiteralPath $bundle
    $apply = Run-Cli @('system','apply','configuration',$bundle)
    Assert-FrpEqual 0 $apply.Rc 'bundle apply exit'
    Assert-FrpTrue ($apply.Out -match 'ConfigurationBundle applied') 'bundle apply message'

    $fixed = Run-Cli @('show','remote-service','fixed-license')
    Assert-FrpEqual 0 $fixed.Rc 'fixed remote-service show'
    Assert-FrpTrue ($fixed.Out -match 'Service\s+: license') 'fixed service object retained'

    # Server-unreachable semantics: cached catalog allows desired-state work,
    # while endpoint allocation/deletion stays explicitly pending until sync.
    $env:FRP_WINDOWS_V24_FIXTURE_OFFLINE = '1'
    $offlineSet = Run-Cli @('set','remote-service','offline-web','destination','this-host','service','ssh','enabled')
    Assert-FrpEqual 0 $offlineSet.Rc 'offline Remote Service desired state saved'
    Assert-FrpTrue ($offlineSet.Out -match 'DEGRADED') 'offline create is degraded'
    Assert-FrpTrue ($offlineSet.Out -match 'Pending allocation') 'offline create reports pending allocation'

    $offlineDelete = Run-Cli @('unset','remote-service','fixed-license')
    Assert-FrpEqual 0 $offlineDelete.Rc 'offline delete saved locally'
    Assert-FrpTrue ($offlineDelete.Out -match 'queued') 'offline delete queues Server release'
    $pendingDeletePath = Join-Path $tmp 'state/v24-pending-deletes.json'
    Assert-FrpTrue (Test-Path -LiteralPath $pendingDeletePath) 'pending delete queue exists'

    $recreate = Run-Cli @('set','remote-service','fixed-license','destination','this-host','service','license','enabled')
    Assert-FrpEqual 0 $recreate.Rc 'offline recreate succeeds from cached catalog'
    Assert-FrpTrue (-not (Test-Path -LiteralPath $pendingDeletePath)) 'recreate cancels queued delete'
    $redelete = Run-Cli @('unset','remote-service','fixed-license')
    Assert-FrpEqual 0 $redelete.Rc 'offline delete can be queued again'
    Assert-FrpTrue (Test-Path -LiteralPath $pendingDeletePath) 'queued delete restored for reconnect test'

    $offlineSync = Run-Cli @('system','synchronize')
    Assert-FrpTrue ($offlineSync.Rc -ne 0) 'explicit synchronize requires live Server'

    Remove-Item Env:FRP_WINDOWS_V24_FIXTURE_OFFLINE -ErrorAction SilentlyContinue
    $reconnect = Run-Cli @('system','synchronize')
    Assert-FrpEqual 0 $reconnect.Rc 'reconnect synchronize exits 0'
    Assert-FrpTrue ($reconnect.Out -match 'deleted: 1') 'reconnect flushes queued delete'
    Assert-FrpTrue (-not (Test-Path -LiteralPath $pendingDeletePath)) 'pending delete queue cleared'
    $online = Run-Cli @('show','remote-service','offline-web')
    Assert-FrpEqual 0 $online.Rc 'reconnected Remote Service exists'
    Assert-FrpTrue ($online.Out -match 'Endpoint\s+: fixture\.example\.test:6001') 'reconnect allocates endpoint'

    $unset = Run-Cli @('unset','remote-service','ssh-access')
    Assert-FrpEqual 0 $unset.Rc 'unset remote-service exit'
    Assert-FrpTrue ($unset.Out -match 'Remote Service deleted') 'delete message'

    Write-FrpTestPass 'test-v24-cli-convergence'
} finally {
    Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_WINDOWS_V24_FIXTURE_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_WINDOWS_V24_FIXTURE_OFFLINE -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_WINDOWS_TEST_CONFIRM -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
