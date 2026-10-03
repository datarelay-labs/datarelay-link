# test-autostart.ps1 — product autostart task lifecycle (non-Windows marker
# backend) + zero-touch wiring + uninstall cleanup + FrpClient.ps1 CLI.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    # Isolate from any leftover product/E2E scheduled task on Windows CI hosts.
    # Keep the unique suffix digits-only so the fixture itself can never
    # accidentally match the reverse-SSH/E2E exclusion regex below.
    $testSuffix = "$PID-$([DateTime]::UtcNow.Ticks)"
    $env:FRP_AUTOSTART_TASK_NAME = 'DataRelayLinkClient-Test-' + $testSuffix
    $env:FRP_LIFECYCLE_TASK_NAME = 'DataRelayLinkLifecycle-Test-' + $testSuffix
    $taskName = Get-FrpAutostartTaskName
    $lifecycleTaskName = Get-FrpLifecycleTaskName
    Assert-FrpEqual $env:FRP_AUTOSTART_TASK_NAME $taskName 'product-owned task name'
    # Canonical default branding (when env override unset).
    $prevOverride = $env:FRP_AUTOSTART_TASK_NAME
    Remove-Item Env:FRP_AUTOSTART_TASK_NAME -ErrorAction SilentlyContinue
    Assert-FrpEqual 'DataRelayLinkClient' (Get-FrpAutostartTaskName) 'canonical Scheduled Task name'
    Assert-FrpEqual 'FRPAutoDeployClient' (Get-FrpAutostartLegacyTaskName) 'legacy Scheduled Task name'
    $env:FRP_AUTOSTART_TASK_NAME = $prevOverride
    # Never collides with the E2E reverse-SSH scheduled task.
    Assert-FrpTrue ($taskName -notmatch '(?i)reverse|ssh|e2e') 'task name does not look like the E2E reverse-SSH task'
    try { Uninstall-FrpAutostartTask -TaskName $taskName | Out-Null } catch { }

    # --- Low-level register/query/remove (marker backend on non-Windows) -----
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists -TaskName $taskName)) 'not registered initially'
    Install-FrpAutostartTask | Out-Null
    Assert-FrpTrue (Test-FrpAutostartTaskExists) 'registered after install'
    Assert-FrpTrue (Test-FrpAutostartHealthy) 'healthy SYSTEM boot task after install'
    $runCmd = Get-FrpAutostartRunCommand
    $runArgs = Get-FrpAutostartRunArguments
    Assert-FrpTrue ($runCmd -match 'frp-autostart\.cmd$') 'run command targets frp-autostart.cmd'
    Assert-FrpEqual '' $runArgs 'run arguments empty (wrapper owns start)'
    Assert-FrpTrue ($runCmd -match [regex]::Escape((Get-FrpToolsDir))) 'run command uses the persisted tools dir, not the temp bootstrap tree'
    $xml = New-FrpAutostartTaskXml -Command $runCmd -Arguments $runArgs
    Assert-FrpTrue ($xml -match 'DisallowStartIfOnBatteries>false') 'battery disallow disabled'
    Assert-FrpTrue ($xml -match 'S-1-5-18') 'runs as SYSTEM'
    Assert-FrpTrue ($xml -match 'BootTrigger') 'boot trigger present'

    Install-FrpLifecycleTask | Out-Null
    Assert-FrpTrue (Test-FrpLifecycleTaskHealthy) 'lifecycle SYSTEM boot worker after install'
    $lifeXml = New-FrpAutostartTaskXml -Command (Get-FrpLifecycleRunCommand) `
        -Arguments (Get-FrpLifecycleRunArguments) -DelaySeconds 5 -ExecutionTimeLimit 'PT0'
    Assert-FrpTrue ($lifeXml -match 'lifecycle-worker') 'lifecycle task targets lifecycle worker'
    Assert-FrpTrue ($lifeXml -match '<ExecutionTimeLimit>PT0</ExecutionTimeLimit>') 'lifecycle task has no execution time limit'
    Uninstall-FrpLifecycleTask | Out-Null
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists -TaskName $lifecycleTaskName)) 'lifecycle task removed'

    # Idempotent: re-install (overwrite) does not throw.
    Install-FrpAutostartTask | Out-Null
    Assert-FrpTrue (Test-FrpAutostartTaskExists) 'still registered after re-install'

    Uninstall-FrpAutostartTask | Out-Null
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists)) 'removed after uninstall'
    # Idempotent: uninstalling an already-absent task is success, not an error.
    Uninstall-FrpAutostartTask | Out-Null

    # Independent Agent lifecycle worker: SYSTEM boot task, long-running, and
    # separate from frpc autostart so management-only Agents still heartbeat.
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists -TaskName $lifecycleTaskName)) 'lifecycle task absent initially'
    Install-FrpLifecycleTask | Out-Null
    Assert-FrpTrue (Test-FrpLifecycleTaskHealthy) 'lifecycle SYSTEM boot task healthy'
    $lifecycleXml = New-FrpAutostartTaskXml -Command (Get-FrpLifecycleRunCommand) `
        -Arguments (Get-FrpLifecycleRunArguments) -ExecutionTimeLimit 'PT0S'
    Assert-FrpTrue ($lifecycleXml -match 'lifecycle-worker') 'lifecycle task invokes worker'
    Assert-FrpTrue ($lifecycleXml -match '<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>') 'lifecycle worker has no task time limit'
    Uninstall-FrpLifecycleTask | Out-Null
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists -TaskName $lifecycleTaskName)) 'lifecycle task removed'

    # Legacy branding migration: product-owned FRPAutoDeployClient is removed
    # when installing the canonical DataRelayLinkClient (or test override) task.
    $legacyName = Get-FrpAutostartLegacyTaskName
    Initialize-FrpDirectories
    $runCmdLegacy = Get-FrpAutostartRunCommand
    if (-not (Test-Path -LiteralPath $runCmdLegacy)) {
        # Ownership validation requires the product wrapper path to exist.
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $runCmdLegacy) | Out-Null
        Set-Content -LiteralPath $runCmdLegacy -Value "@echo off`r`nrem Data Relay Link autostart wrapper`r`n"
    }
    $prevOverride = $env:FRP_AUTOSTART_TASK_NAME
    try {
        # Install under the legacy name so Windows schtasks (and marker backends)
        # both create a product-owned task that migration can detect.
        $env:FRP_AUTOSTART_TASK_NAME = $legacyName
        try { Uninstall-FrpAutostartTask -TaskName $legacyName | Out-Null } catch { }
        Install-FrpAutostartTask | Out-Null
        Assert-FrpTrue (Test-FrpAutostartHealthy -TaskName $legacyName) 'legacy task is product-owned'
    } finally {
        $env:FRP_AUTOSTART_TASK_NAME = $prevOverride
    }
    Install-FrpAutostartTask | Out-Null
    Assert-FrpTrue (Test-FrpAutostartTaskExists) 'canonical task registered after migrate'
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists -TaskName $legacyName)) 'legacy product task migrated away'
    Uninstall-FrpAutostartTask | Out-Null
    try { Uninstall-FrpAutostartTask -TaskName $legacyName | Out-Null } catch { }

    # Simulated failure hook (mirrors FRP_WINDOWS_FAIL_ACL pattern).
    $env:FRP_WINDOWS_FAIL_AUTOSTART = '1'
    $threw = $false
    try { Install-FrpAutostartTask | Out-Null } catch { $threw = $true }
    Assert-FrpTrue $threw 'install honors FRP_WINDOWS_FAIL_AUTOSTART'
    $threw = $false
    try { Uninstall-FrpAutostartTask | Out-Null } catch { $threw = $true }
    Assert-FrpTrue $threw 'uninstall honors FRP_WINDOWS_FAIL_AUTOSTART'
    Remove-Item Env:FRP_WINDOWS_FAIL_AUTOSTART -ErrorAction SilentlyContinue
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists)) 'still not registered after failed install attempt'

    Write-FrpTestPass 'test-autostart (register/query/remove)'

    # --- Zero-touch wiring: registers only when frpc actually needs to run ---
    $id = New-FrpEcdsaIdentity
    Save-FrpIdentityKey -PrivatePem $id.PrivatePem | Out-Null
    Save-FrpIdentityPublic -PublicPem $id.PublicPem | Out-Null
    $mid = Get-FrpOrCreateClientId
    $services = @{
        rdp = @{ id = 'rdp'; name = 'RDP'; preset = 'rdp'; local_ip = '127.0.0.1'; local_port = 3389; remote_port = 60050; enabled = $true }
    }
    Save-FrpClientState -AllocatorUrl 'https://example.test/enroll' -FrpServer 'example.test' `
        -FrpServerPort 7000 -Hostname 'win' -MachineId $mid -HostId 'abcd' `
        -Services $services -Transport 'tcp' -InstallStatus 'enrolled_incomplete' | Out-Null
    New-FrpClientToml -ServerAddr 'example.test' -ServerPort 7000 -Token 'tok' `
        -HostId 'abcd' -Services $services -Transport 'tcp' | Out-Null

    Complete-FrpZeroTouchPostEnroll -SkipDownload -SkipStart -Services $services | Out-Null
    Assert-FrpTrue (Test-FrpAutostartTaskExists) 'autostart registered for a client with enabled services'
    Assert-FrpTrue (Test-FrpLifecycleTaskHealthy) 'lifecycle worker registered for enabled-services client'
    Uninstall-FrpAutostartTask | Out-Null
    Uninstall-FrpLifecycleTask | Out-Null

    Write-FrpTestPass 'test-autostart (zero-touch registers for services)'

    # Management-only: no frpc to run, autostart must not be registered.
    Remove-FrpDraftState | Out-Null
    $mid2 = 'deadbeefcafedeadbeefcafedeadbef'
    Save-FrpClientState -AllocatorUrl 'https://example.test/enroll' -FrpServer 'example.test' `
        -FrpServerPort 7000 -Hostname 'win2' -MachineId $mid2 -HostId 'wxyz' `
        -Services @{} -Transport 'tcp' -InstallStatus 'enrolled_incomplete' | Out-Null
    New-FrpClientToml -ServerAddr 'example.test' -ServerPort 7000 -Token 'tok' `
        -HostId 'wxyz' -Services @{} -Transport 'tcp' | Out-Null
    Complete-FrpZeroTouchPostEnroll -SkipDownload -SkipStart -Services @{} | Out-Null
    Assert-FrpTrue (-not (Test-FrpAutostartTaskExists)) 'management-only client does not register frpc autostart'
    Assert-FrpTrue (Test-FrpLifecycleTaskHealthy) 'management-only client keeps lifecycle heartbeat task'
    Uninstall-FrpLifecycleTask | Out-Null

    Write-FrpTestPass 'test-autostart (management-only skips frpc registration)'

    # Registration failure with enabled public services must FAIL CLOSED.
    Save-FrpClientState -AllocatorUrl 'https://example.test/enroll' -FrpServer 'example.test' `
        -FrpServerPort 7000 -Hostname 'win' -MachineId $mid -HostId 'abcd' `
        -Services $services -Transport 'tcp' -InstallStatus 'enrolled_incomplete' | Out-Null
    New-FrpClientToml -ServerAddr 'example.test' -ServerPort 7000 -Token 'tok' `
        -HostId 'abcd' -Services $services -Transport 'tcp' | Out-Null
    $env:FRP_WINDOWS_FAIL_AUTOSTART = '1'
    $rc = Complete-FrpZeroTouchPostEnroll -SkipDownload -SkipStart -Services $services
    Remove-Item Env:FRP_WINDOWS_FAIL_AUTOSTART -ErrorAction SilentlyContinue
    Assert-FrpEqual 1 $rc 'enrollment fails closed when autostart registration fails'
    Assert-FrpTrue ((Get-FrpInstallStatus) -ne 'installed') 'must not report fully installed without autostart'

    Write-FrpTestPass 'test-autostart (registration failure is fail-closed)'
} finally {
    Remove-Item Env:FRP_WINDOWS_FAIL_AUTOSTART -ErrorAction SilentlyContinue
    try { Uninstall-FrpAutostartTask | Out-Null } catch { }
    try { Uninstall-FrpLifecycleTask | Out-Null } catch { }
    Remove-Item Env:FRP_AUTOSTART_TASK_NAME -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_LIFECYCLE_TASK_NAME -ErrorAction SilentlyContinue
    Remove-FrpWindowsTestRoot
}
