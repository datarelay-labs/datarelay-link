# Exercise public installer/CLI guidance and the existing source-update path.
# Temporary fixtures test PowerShell behavior; this is not Windows OS qualification.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
$installedRoot = Get-FrpWindowsRoot
$env:FRP_AUTOSTART_TASK_NAME = 'DRLinkGuidanceAutostart-' + [guid]::NewGuid().ToString('N')
$env:FRP_LIFECYCLE_TASK_NAME = 'DRLinkGuidanceLifecycle-' + [guid]::NewGuid().ToString('N')
$env:FRP_WINDOWS_FAKE_MACHINE_PATH = Join-Path $installedRoot 'machine-path-fixture.txt'
Set-Content -LiteralPath $env:FRP_WINDOWS_FAKE_MACHINE_PATH -Value ''
$sourcePackage = Join-Path ([IO.Path]::GetTempPath()) ('drlink-reviewed-source-' + [guid]::NewGuid().ToString('N'))
$hostExe = (Get-Process -Id $PID).Path
$installer = Join-Path $script:RepoRoot 'windows/install-client.ps1'
$client = Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
$failures = New-Object System.Collections.Generic.List[string]
function Check-Guidance {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { [void]$failures.Add($Message); Write-Host "FAIL $Message" }
}
function Run-PublicCli {
    param([string[]]$CliArgs)
    $lines = & $hostExe -NoProfile -File $client @CliArgs 2>&1
    return @{Rc=$LASTEXITCODE; Text=($lines | Out-String)}
}
try {
    foreach ($legacy in @(
        @{Path='update'; Args=@('update'); Commands=@('drlink system update product', 'drlink system update engine')},
        @{Path='service'; Args=@('service'); Commands=@('drlink show remote-services', 'drlink set remote-service <NAME>', 'drlink unset remote-service <NAME>')},
        @{Path='client'; Args=@('client'); Commands=@('drlink show agent', 'drlink system info')},
        @{Path='show invalid resource'; Args=@('show','not-a-resource'); Commands=@('drlink show status','drlink show agent','drlink show remote-services','drlink show remote-service <NAME>')}
    )) {
        $rejected = Run-PublicCli -CliArgs $legacy.Args
        Check-Guidance ($rejected.Rc -eq 2) ('obsolete ' + $legacy.Path + ' fails closed')
        foreach ($command in $legacy.Commands) {
            Check-Guidance ($rejected.Text -match ('(?m)^Use: ' + [regex]::Escape($command) + '\s*$')) ('complete recovery command: ' + $command)
        }
        Check-Guidance ($rejected.Text -notmatch 'show/set/unset|remote-service\(s\)|(?m)^Use:.*\|') ('obsolete ' + $legacy.Path + ' omits pseudo commands/pipelines')
    }
    $help = & $hostExe -NoProfile -File $installer -Help 2>&1 | Out-String
    Check-Guidance ($LASTEXITCODE -eq 0) 'public installer help succeeds'
    Check-Guidance ($help -match 'Windows Agent Host installer') 'installer uses current public role'
    Check-Guidance ($help -notmatch '(?i)Windows client installer') 'installer omits retired role title'
    $missingMode = & $hostExe -NoProfile -File $installer 2>&1 | Out-String
    Check-Guidance ($LASTEXITCODE -ne 0) 'missing enrollment mode fails closed'
    Check-Guidance ($missingMode -match 'tools\\drlink.cmd') 'installer directs lifecycle users to public launcher'
    Check-Guidance ($missingMode -notmatch 'use tools\\FrpClient.ps1') 'installer does not recommend backend lifecycle entry'

    # Preserve raw fixture bytes, including private material, without printing them.
    $state = @{schema_version=1;allocator_url='https://example.test/enroll';frp_server='example.test';
        frp_server_port=443;frp_transport='wss';hostname='guidance-agent';
        machine_id=('1' * 32);host_id='guidance-agent';services=@{};install_status='management_only'}
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Get-FrpStatePath)
    Set-Content -LiteralPath (Get-FrpTomlPath) -Value 'fixture-runtime-configuration'
    Set-Content -LiteralPath (Get-FrpIdentityPubPath) -Value 'fixture-public-identity'
    Set-Content -LiteralPath (Get-FrpIdentityKeyPath) -Value 'fixture-private-identity'
    Set-Content -LiteralPath (Get-FrpAllocatorCaPath) -Value 'fixture-enrollment-ca'
    $preservedPaths = @((Get-FrpStatePath), (Get-FrpTomlPath), (Get-FrpIdentityPubPath),
        (Get-FrpIdentityKeyPath), (Get-FrpAllocatorCaPath))
    $before = @{}
    foreach ($path in $preservedPaths) { $before[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }

    $doctor = Run-PublicCli @('system','diagnostics')
    Check-Guidance ($doctor.Text -match 'Data Relay Link Agent Host diagnostics') 'doctor uses current public role'
    Check-Guidance ($doctor.Text -notmatch 'Data Relay Link client diagnostics') 'doctor omits retired role title'
    $version = Run-PublicCli @('system','version')
    Check-Guidance ($version.Rc -eq 0 -and $version.Text -match 'Windows Agent Host') 'version fallback names current role'

    $paused = Run-PublicCli @('system','pause')
    Check-Guidance ($paused.Rc -eq 0 -and $paused.Text -match 'Agent Host is already paused') 'idle lifecycle message names current role'

    $env:FRP_WINDOWS_PROJECT_SRC = $installedRoot
    $failedUpdate = Run-PublicCli @('system','update','product')
    Check-Guidance ($failedUpdate.Rc -ne 0) 'installed product tree is rejected as update source'
    Check-Guidance ($failedUpdate.Text -match 'FRP_WINDOWS_PROJECT_SRC' -and $failedUpdate.Text -match 'system update product') 'failure gives existing source-update recovery'
    Check-Guidance ($failedUpdate.Text -match 'immutable' -and $failedUpdate.Text -match 'docs/UPGRADE.md') 'failure explains reviewed source prerequisite and guide'
    Check-Guidance ($failedUpdate.Text -notmatch 're-run the canonical Windows client installer|re-run.*installer.*identity and ports') 'failure does not promise preservation through rejected reenrollment'

    # A complete external repository package supplies metadata and windows/tools+lib.
    New-Item -ItemType Directory -Path $sourcePackage -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $script:RepoRoot 'windows') -Destination $sourcePackage -Recurse
    foreach ($file in @('VERSION','release-manifest.json')) {
        Copy-Item -LiteralPath (Join-Path $script:RepoRoot $file) -Destination $sourcePackage
    }
    $env:FRP_WINDOWS_PROJECT_SRC = Join-Path $sourcePackage 'windows'
    $success = Run-PublicCli @('system','update','product')
    Check-Guidance ($success.Rc -eq 0) ('existing source-update succeeds: ' + $success.Text)
    foreach ($path in $preservedPaths) {
        Check-Guidance ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -eq $before[$path]) ('update preserves fixture bytes: ' + [IO.Path]::GetFileName($path))
    }
    Check-Guidance (Test-Path -LiteralPath (Join-Path $installedRoot 'tools/FrpLifecycleWorker.ps1')) 'update persists management worker'
    $installedClient = Join-Path $installedRoot 'tools/FrpClient.ps1'
    $installedHelp = & $hostExe -NoProfile -File $installedClient help 2>&1 | Out-String
    Check-Guidance ($LASTEXITCODE -eq 0 -and $installedHelp -match 'Agent Host') 'updated installed CLI remains discoverable'
    if ($failures.Count -gt 0) { throw ($failures -join '; ') }
    Write-FrpTestPass 'test-public-operator-guidance'
} finally {
    Uninstall-FrpLifecycleTask | Out-Null
    Uninstall-FrpAutostartTask | Out-Null
    Remove-Item Env:FRP_AUTOSTART_TASK_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_LIFECYCLE_TASK_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_WINDOWS_FAKE_MACHINE_PATH -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_WINDOWS_PROJECT_SRC -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $sourcePackage -Recurse -Force -ErrorAction SilentlyContinue
    Remove-FrpWindowsTestRoot
}
