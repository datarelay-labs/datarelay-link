# Valid YAML indentless sequences preserve the same Agent Bundle document.
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    $canonical = @'
configurationBundle:
  context: agent
  remoteServices:
    - name: first
      destination: this-host
      service: ssh
      enabled: false
    - name: obsolete
      state: absent
'@
    $path = Join-Path $env:FRP_WINDOWS_ROOT 'canonical.yaml'
    Set-Content -LiteralPath $path -Value $canonical
    $a = Read-FrpV24AgentBundle -Path $path
    $indentless = $canonical.Replace('    - name:', '  - name:').Replace('      destination:', '    destination:').Replace('      service:', '    service:').Replace('      enabled:', '    enabled:').Replace('      state:', '    state:')
    $path2 = Join-Path $env:FRP_WINDOWS_ROOT 'indentless.yaml'
    Set-Content -LiteralPath $path2 -Value $indentless
    $b = Read-FrpV24AgentBundle -Path $path2
    Assert-FrpEqual ($a | ConvertTo-Json -Depth 10 -Compress) ($b | ConvertTo-Json -Depth 10 -Compress) 'equivalent YAML sequence indentation'
    Assert-FrpEqual 2 @($b.remoteServices).Count 'both entries retained'
    Assert-FrpEqual $false $b.remoteServices[0].enabled 'boolean retained'
    $mixed = $indentless.Replace('  - name: obsolete', '    - name: obsolete')
    Set-Content -LiteralPath $path2 -Value $mixed
    $rejected = $false
    try { Read-FrpV24AgentBundle -Path $path2 | Out-Null } catch { $rejected = $true }
    Assert-FrpTrue $rejected 'mixed sequence levels reject before apply'
    Write-FrpTestPass 'v24-bundle-yaml-indentation'
} finally { Remove-FrpWindowsTestRoot }
