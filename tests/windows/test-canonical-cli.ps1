# test-canonical-cli.ps1 — Windows resource-first drlink grammar + update modes.
. (Join-Path $PSScriptRoot 'common.ps1')

$clientPath = Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
$hostExe = 'pwsh'
if ($PSVersionTable.PSEdition -eq 'Desktop') { $hostExe = 'powershell.exe' }
try {
    $hp = (Get-Process -Id $PID).Path
    if ($hp) { $hostExe = $hp }
} catch { }

$tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('frp-win-canon-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
$env:FRP_WINDOWS_ROOT = $tmpRoot
try {
    . (Join-Path $script:WindowsLib 'FrpPaths.ps1')
    . (Join-Path $script:WindowsLib 'FrpCrypto.ps1')
    . (Join-Path $script:WindowsLib 'FrpState.ps1')
    Initialize-FrpDirectories
    $mid = Get-FrpOrCreateClientId
    Save-FrpClientState -AllocatorUrl 'https://example.test/enroll' -FrpServer 'example.test' `
        -FrpServerPort 7000 -Hostname 'win-cli' -MachineId $mid -HostId 'cliabcd' `
        -Services @{ rdp = @{ id = 'rdp'; name = 'RDP'; preset = 'rdp'; local_ip = '127.0.0.1'; local_port = 3389; remote_port = 60040; enabled = $true } } `
        -Transport 'tcp' -InstallStatus 'installed' | Out-Null

    $help = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath help 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'help exits 0'
    Assert-FrpTrue ($help -match 'show status') 'help advertises show status'
    Assert-FrpTrue ($help -match 'show remote-services') 'help advertises show remote-services'
    Assert-FrpTrue ($help -match 'test configuration') 'help advertises Agent ConfigurationBundle'
    Assert-FrpTrue ($help -match 'system info') 'help advertises system info'
    Assert-FrpTrue ($help -match 'system pause') 'help advertises system pause'
    Assert-FrpTrue ($help -match 'system resume') 'help advertises system resume'
    Assert-FrpTrue ($help -match 'system restart') 'help advertises system restart'
    Assert-FrpTrue ($help -match 'system autostart') 'help advertises system autostart'
    Assert-FrpTrue ($help -match 'system update product') 'help advertises system update product'
    Assert-FrpTrue ($help -match 'system update engine') 'help advertises system update engine'
    Assert-FrpTrue ($help -match 'system support-bundle') 'help advertises system support-bundle'
    Assert-FrpTrue ($help -match 'system uninstall') 'help advertises system uninstall'
    Assert-FrpTrue ($help -notmatch '(?m)^  status\s') 'help hides legacy root status'
    Assert-FrpTrue ($help -notmatch 'add-service') 'help hides legacy add-service'
    Assert-FrpTrue ($help -notmatch '(?m)^  start\s') 'help hides legacy root start'
    Assert-FrpTrue ($help -notmatch '(?m)^  stop\s') 'help hides legacy root stop'

    $list = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath show remote-services 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'show remote-services exits 0'
    Assert-FrpTrue ($list -match 'rdp') 'show remote-services shows rdp'

    $info = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system info 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'system info exits 0'

    # Unreleased v2.4 has no public compatibility grammar.
    $legacyList = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath service list 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -ne 0) 'legacy service list is rejected'
    Assert-FrpTrue ($legacyList -match 'obsolete Windows CLI path') 'legacy service list gives canonical guidance'

    # Resource-first support bundle vocabulary (legacy support-bundle still works).
    $bundleOut = Join-Path $tmpRoot 'bundle-test.zip'
    $bundle = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system support-bundle $bundleOut 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'system support-bundle exits 0'
    Assert-FrpTrue (Test-Path -LiteralPath $bundleOut) 'support bundle wrote archive'
    $extractDir = Join-Path $tmpRoot 'bundle-extract'
    New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
    Expand-Archive -LiteralPath $bundleOut -DestinationPath $extractDir -Force
    $doctorTxt = Get-ChildItem -Path $extractDir -Recurse -Filter 'doctor.txt' | Select-Object -First 1
    Assert-FrpTrue ($null -ne $doctorTxt) 'support bundle contains doctor.txt'
    $doctorBody = Get-Content -LiteralPath $doctorTxt.FullName -Raw
    Assert-FrpTrue ($doctorBody -match 'Data Relay Link Agent Host diagnostics') 'doctor.txt has diagnostics header'
    Assert-FrpTrue ($doctorBody -match 'MISS|Enrolled|Doctor|diagnostics') 'doctor.txt has diagnostic content'
    Assert-FrpTrue ($doctorBody -notmatch '^\s*[01]\s*$') 'doctor.txt is not bare exit code'

    $legacyAdd = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath service add 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -ne 0) 'legacy service add is rejected'

    $legacyUpdate = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath update -Check 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -ne 0) 'legacy update root is rejected'
    Assert-FrpTrue ($legacyUpdate -match 'system update product') 'legacy update gives canonical guidance'

    # WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS — project -Check is project-only (not engine apply dry-run)
    $projCheck = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system update product -Check 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS exit 0'
    Assert-FrpTrue ($projCheck -match 'Data Relay Link project') 'WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS shows project'
    Assert-FrpTrue ($projCheck -match 'verified immutable repository package') 'WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS source path'
    Assert-FrpTrue ($projCheck -notmatch 'Would download:') 'WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS omits engine download'
    Assert-FrpTrue ($projCheck -notmatch 'FRP engine') 'WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS omits engine section'

    # WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS — engine -Check is engine-only
    $engCheck = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system update engine -Check 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS exit 0'
    Assert-FrpTrue ($engCheck -match 'Would download:') 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS Would download'
    Assert-FrpTrue ($engCheck -match 'Expected SHA256:') 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS sha256'
    Assert-FrpTrue ($engCheck -match 'FRP engine') 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS engine header'
    Assert-FrpTrue ($engCheck -notmatch 'Data Relay Link project') 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS omits project section'
    Assert-FrpTrue ($engCheck -notmatch 're-run the Windows client installer') 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS omits installer path'

    # Installed-client project apply is honest: without a distinct source tree, guide to installer.
    $prevSrc = $env:FRP_WINDOWS_PROJECT_SRC
    Remove-Item Env:FRP_WINDOWS_PROJECT_SRC -ErrorAction SilentlyContinue
    try {
        # Point "installed" product root at the temp root so repo windows/ is not used as source.
        # FrpClient still runs from the repo path; Resolve refuses when candidate == product root only.
        # Simulate missing/explicit-denied source by setting FRP_WINDOWS_PROJECT_SRC to the product root.
        $env:FRP_WINDOWS_PROJECT_SRC = $tmpRoot
        $projApply = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system update product 2>&1 | Out-String
        Assert-FrpTrue ($LASTEXITCODE -ne 0) 'update project without source fails'
        Assert-FrpTrue ($projApply -match 'PROJECT_UPDATE_USE_INSTALLER') 'update project FAILURE_CLASS=PROJECT_UPDATE_USE_INSTALLER'
        Assert-FrpTrue ($projApply -match 'FRP_WINDOWS_PROJECT_SRC' -and $projApply -match 'docs/UPGRADE.md') 'update project guides to reviewed source'
    } finally {
        if ($null -ne $prevSrc -and $prevSrc -ne '') {
            $env:FRP_WINDOWS_PROJECT_SRC = $prevSrc
        } else {
            Remove-Item Env:FRP_WINDOWS_PROJECT_SRC -ErrorAction SilentlyContinue
        }
    }

    # Positive project update must persist the standalone lifecycle worker used
    # by the canonical Agent heartbeat/synchronization Scheduled Task.
    $prevSrc = $env:FRP_WINDOWS_PROJECT_SRC
    try {
        $env:FRP_WINDOWS_PROJECT_SRC = Join-Path $script:RepoRoot 'windows'
        $projApplyOk = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system update product 2>&1 | Out-String
        Assert-FrpTrue ($LASTEXITCODE -eq 0) ("project update from reviewed source succeeds; out=$projApplyOk")
        Assert-FrpTrue (Test-Path -LiteralPath (Join-Path $tmpRoot 'tools/FrpLifecycleWorker.ps1')) 'project update persists lifecycle worker'
    } finally {
        if ($null -ne $prevSrc -and $prevSrc -ne '') {
            $env:FRP_WINDOWS_PROJECT_SRC = $prevSrc
        } else {
            Remove-Item Env:FRP_WINDOWS_PROJECT_SRC -ErrorAction SilentlyContinue
        }
    }

    $bad = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath client nope 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -ne 0) 'bad client subcommand fails'

    $pause = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath system pause 2>&1 | Out-String
    Assert-FrpTrue ($LASTEXITCODE -eq 0) 'system pause exits 0'
    Assert-FrpTrue ($pause -match 'paused|already paused') 'system pause messaging'

    Write-FrpTestPass 'test-canonical-cli'
    Write-FrpTestPass 'WINDOWS_UPDATE_PROJECT_CHECK_SEMANTICS'
    Write-FrpTestPass 'WINDOWS_UPDATE_ENGINE_CHECK_SEMANTICS'
} finally {
    Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
}
