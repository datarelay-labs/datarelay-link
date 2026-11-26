# Exercise the actual no-argument CLI, menu, error recovery and literal parser.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $script:WindowsLib 'FrpInteractive.ps1')
$entry = Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
$exe = (Get-Process -Id $PID).Path
$root = Join-Path ([IO.Path]::GetTempPath()) ('frp-interactive-' + [guid]::NewGuid().ToString('N'))
$env:FRP_WINDOWS_ROOT = $root
try {
    $words = @(Split-FrpInteractiveLine 'system export configuration "C:\a b\bundle.yaml"')
    Assert-FrpEqual 4 $words.Count 'quoted path token count'
    Assert-FrpEqual 'C:\a b\bundle.yaml' $words[3] 'quoted path is literal'
    $literal = @(Split-FrpInteractiveLine 'show remote-service "$(Get-Date)"')
    Assert-FrpEqual '$(Get-Date)' $literal[2] 'no expression evaluation'
    $bad = $false
    try { $null = @(Split-FrpInteractiveLine 'show "unterminated') } catch { $bad = $true }
    Assert-FrpTrue $bad 'unmatched quote rejected'
    Assert-FrpTrue (@(Get-FrpInteractiveCompletions 'sh') -contains 'show') 'root completion'
    Assert-FrpTrue (@(Get-FrpInteractiveCompletions 'show remote-') -contains 'remote-services') 'resource completion'
    Assert-FrpTrue (@(Get-FrpInteractiveCompletions 'system update ') -contains 'product') 'nested completion'
    Assert-FrpTrue (@(Get-FrpInteractiveCompletions 'system update ') -notcontains 'check-engine') 'server-only command hidden'
    # Test redirected input on actual entrypoint (not native keyboard qualification).
    $lines = @('show remote-services','invalid-command','help','menu','2','0','exit')
    $out = $lines | & $exe -NoProfile -ExecutionPolicy Bypass -File $entry 2>&1 | Out-String
    Assert-FrpEqual 0 $LASTEXITCODE 'exit from interactive shell'
    Assert-FrpTrue ($out -match 'drlink>') 'no-argument launch enters prompt'
    Assert-FrpTrue ($out -match 'No Remote Services configured') 'real show command executed'
    Assert-FrpTrue ($out -match 'Command failed with exit code 2') 'error preserved without ending session'
    Assert-FrpTrue ($out -match 'Data Relay Link - Windows Agent Host Commands') 'ASCII help heading'
    Assert-FrpTrue ($out -match 'Select:') 'guided menu reads selection'
    Assert-FrpTrue ($out -match 'Enrollment : Not enrolled') 'menu invokes real Agent command'
    Assert-FrpTrue ([regex]::Matches($out,'drlink>').Count -ge 5) 'returns to prompt after command and menu'
    $direct = & $exe -NoProfile -ExecutionPolicy Bypass -File $entry help 2>&1 | Out-String
    Assert-FrpEqual 0 $LASTEXITCODE 'one-shot help exit code'
    Assert-FrpTrue ($direct -notmatch 'drlink>') 'explicit help does not open REPL'
    $cancel = @('set remote-service test-redirected','exit') | & $exe -NoProfile -ExecutionPolicy Bypass -File $entry 2>&1 | Out-String
    Assert-FrpTrue ($cancel -match 'guided changes require an interactive terminal') 'redirected wizard fails closed'
    Write-FrpTestPass 'test-interactive-cli'
} finally {
    Remove-FrpWindowsTestRoot
    Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue
}
