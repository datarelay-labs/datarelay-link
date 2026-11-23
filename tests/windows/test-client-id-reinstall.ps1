# BUG-07: uninstall removes enrollment secrets, not the machine binding needed
# to recover the Server-managed identity and reserved Remote Service ports.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')

try {
    $original = Get-FrpOrCreateClientId
    Assert-FrpTrue (Test-FrpClientIdWellFormed -Value $original) 'first install identity valid'
    $root = Get-FrpWindowsRoot
    # Reproduce uninstall deleting the entire product tree (no live services).
    Remove-Item -LiteralPath $root -Recurse -Force
    Assert-FrpTrue (-not (Test-Path -LiteralPath $root)) 'Agent root removed'
    $after = Get-FrpOrCreateClientId
    Assert-FrpEqual $original $after 'reinstall on same machine reuses machine ID'
    Assert-FrpEqual $original (([IO.File]::ReadAllText((Get-FrpClientIdPath))).Trim()) 'fresh Agent state recovers identity'
    Assert-FrpEqual ('win-' + $original.Substring(0,8)) ('win-' + $after.Substring(0,8)) 'expected host ID stable'
    Write-FrpTestPass 'test-client-id-reinstall (same machine)'
    # If an attacker or a copied Agent state disagrees with the durable machine
    # binding, fail closed before overwriting either source of identity.
    [IO.File]::WriteAllText((Get-FrpClientIdPath), ('abcdefabcdefabcdefabcdefabcdefab' + "`n"))
    $threw = $false
    try { Get-FrpOrCreateClientId | Out-Null } catch { $threw = $true }
    Assert-FrpTrue $threw 'copied Agent state cannot replace persistent binding'
    Assert-FrpEqual $original (([IO.File]::ReadAllText((Get-FrpDurableClientIdPath))).Trim()) 'binding unchanged on conflict'
} finally {
    Remove-FrpWindowsTestRoot
}
