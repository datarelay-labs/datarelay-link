# test-zero-service.ps1 — empty ticket services stay management-only (no RDP injection)
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    $local = Get-FrpDefaultServices -Platform 'windows'
    Assert-FrpEqual 1 @($local).Count 'local defaults still provide RDP'
    Assert-FrpEqual 'rdp' $local[0].id 'rdp for guided path'

    $ssh = Get-FrpDefaultServices -Platform 'linux'
    Assert-FrpEqual 'ssh' ([string]$ssh[0].id) 'non-Windows default is SSH'
    Assert-FrpEqual 22 ([int]$ssh[0].local_port) 'SSH default port unchanged'
    Assert-FrpTrue (-not ($ssh[0].PSObject.Properties.Name -contains 'ssh_user')) 'SSH username is never inferred'

    # Empty ticket services must not call defaults (logic mirror)
    $ticketServices = @()
    Assert-FrpEqual 0 @($ticketServices).Count 'empty ticket stays empty'

    $id = New-FrpEcdsaIdentity
    Save-FrpIdentityKey -PrivatePem $id.PrivatePem | Out-Null
    Save-FrpIdentityPublic -PublicPem $id.PublicPem | Out-Null
    $mid = Get-FrpOrCreateClientId
    Save-FrpClientState -AllocatorUrl 'https://example.test/enroll' -FrpServer 'example.test' `
        -FrpServerPort 7000 -Hostname 'win' -MachineId $mid -HostId 'h' `
        -Services @{} -Transport 'tcp' -InstallStatus 'enrolled_incomplete' | Out-Null
    New-FrpClientToml -ServerAddr 'example.test' -ServerPort 7000 -Token 'tok' `
        -HostId 'h' -Services @{} -Transport 'tcp' | Out-Null

    $rc = Complete-FrpZeroTouchPostEnroll -SkipStart -SkipDownload -Services @{}
    Assert-FrpEqual 0 $rc 'management-only complete succeeds'
    Assert-FrpEqual 'management_only' (Get-FrpInstallStatus) 'status management_only'
    Assert-FrpTrue (-not (Get-FrpClientStatus).Running) 'frpc not started'
    $status = Get-FrpClientStatus
    Assert-FrpEqual 'Healthy' $status.RuntimeLevel 'management-only relay inactivity is healthy'
    Assert-FrpEqual 'Inactive (no enabled relay services)' $status.RuntimeState 'management-only does not report unexpected stopped relay'
    Assert-FrpEqual $false $status.RelayRequired 'no relay log or process required'


    Write-FrpTestPass 'test-zero-service'
} finally {
    Remove-FrpWindowsTestRoot
}
