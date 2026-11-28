# Regression for existing ProgramData installs inheriting Users write access.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    if (-not (Test-FrpIsWindowsHost)) {
        Write-Host 'NATIVE_ACL_TEST=NOT_RUN (requires Windows)'
        return
    }
    # Reproduce the actual default ProgramData parent, not a user-owned temp
    # ancestor. Never touch the installed product or register a task.
    Remove-FrpWindowsTestRoot
    $env:FRP_WINDOWS_ROOT=Join-Path $env:ProgramData ('drlink-acl-fixture-' + [guid]::NewGuid().ToString('N'))
    Initialize-FrpDirectories
    $root=Get-FrpWindowsRoot
    $dirs=@($root,(Get-FrpToolsDir),(Get-FrpLibDir),(Get-FrpBinDir))
    $fixture=Join-Path (Get-FrpToolsDir) 'acl-fixture.ps1'
    Set-Content -LiteralPath $fixture -Value '# test only'
    $state=Join-Path (Get-FrpStateDir) 'acl-canary.txt'
    Set-Content -LiteralPath $state -Value 'preserve'
    Restrict-FrpFileAcl -Path $state
    $admin=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
    $profilePath=Get-FrpAiExecutorProfilePath
    $profile=@{enabled=$true;account_sid='S-1-5-18';allowed_roots=@((ConvertTo-FrpAiWindowsPath (Get-FrpStateDir)));allow_command_exec=$false}
    $profile | ConvertTo-Json | Set-Content -LiteralPath $profilePath
    Restrict-FrpFileAcl -Path $profilePath
    foreach ($path in @((Get-FrpStateDir),$profilePath)) {
        $acl=Get-Acl -LiteralPath $path
        $acl.SetOwner($admin)
        Set-Acl -LiteralPath $path -AclObject $acl
    }
    $profileBefore=(Get-FileHash -LiteralPath $profilePath).Hash
    $before=(Get-Acl -LiteralPath $state).Sddl
    $stateHash=(Get-FileHash -LiteralPath $state).Hash
    $parentAcl=(Get-Acl -LiteralPath (Split-Path -Parent $root)).Sddl
    $users=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-545')
    foreach ($path in @($dirs)+@($fixture)) {
        $acl=Get-Acl -LiteralPath $path
        $rule=[Security.AccessControl.FileSystemAccessRule]::new($users,[Security.AccessControl.FileSystemRights]::Write,[Security.AccessControl.AccessControlType]::Allow)
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $path -AclObject $acl
    }
    Assert-FrpTrue (-not (Test-FrpExecutionTreeAcl)) 'writable installation must fail security check'
    Assert-FrpTrue (-not (Get-FrpAiExecutorProfile -ForStatus)) 'unsafe installation cannot opt in'
    Protect-FrpExecutionTree
    Assert-FrpTrue (Test-FrpExecutionTreeAcl) 'installation code is protected'
    Assert-FrpTrue ([bool](Get-FrpAiExecutorProfile -ForStatus)) 'protected profile accepted with normal ProgramData ancestors'
    Assert-FrpEqual $profileBefore (Get-FileHash -LiteralPath $profilePath).Hash 'profile bytes unchanged'
    foreach ($path in @($dirs)+@($fixture)) {
        $acl=Get-Acl -LiteralPath $path
        Assert-FrpTrue $acl.AreAccessRulesProtected 'execution path does not inherit unsafe ACL'
        $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | Where-Object { $_.IdentityReference.Value -eq $users.Value -and $_.AccessControlType -eq 'Allow' })
        Assert-FrpTrue ($rules.Count -gt 0) 'standard user read/execute retained'
        foreach ($rule in $rules) {
            Assert-FrpTrue (-not ($rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Write)) 'standard user cannot write code'
        }
    }
    Assert-FrpEqual $parentAcl (Get-Acl -LiteralPath (Split-Path -Parent $root)).Sddl 'parent ACL unchanged'
    Assert-FrpEqual $before (Get-Acl -LiteralPath $state).Sddl 'protected state ACL unchanged'
    Assert-FrpEqual $stateHash (Get-FileHash -LiteralPath $state).Hash 'state bytes unchanged'
    $outside=Join-Path $root 'outside-canary.txt'
    Set-Content -LiteralPath $outside -Value 'outside'
    $outsideAcl=(Get-Acl -LiteralPath $outside).Sddl
    $link=Join-Path (Get-FrpToolsDir) 'hardlink.ps1'
    New-Item -ItemType HardLink -Path $link -Target $outside -ErrorAction Stop | Out-Null
    $rejected=$false
    try { Protect-FrpExecutionTree } catch { $rejected=$true }
    Assert-FrpTrue $rejected 'hardlink path rejected'
    Assert-FrpEqual $outsideAcl (Get-Acl -LiteralPath $outside).Sddl 'hardlink target ACL unchanged'
    Write-FrpTestPass 'test-install-code-acl'
} finally { Remove-FrpWindowsTestRoot }
