# Native Windows PowerShell 5.1 launcher regression: a bare '-' must reach the script.
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('drlink-stdin-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
$oldModulePath = $env:PSModulePath
try {
    Copy-Item (Join-Path $script:RepoRoot 'windows/tools/drlink.cmd') $root
    @'
param([string]$Command,[string]$SubCommand,[string]$Id,[string]$Property)
Write-Output ('ARGS=' + $Command + '|' + $SubCommand + '|' + $Id + '|' + $Property)
$acl = Get-Acl -LiteralPath $PSScriptRoot -ErrorAction Stop
if (-not $acl) { throw 'Native ACL provider unavailable' }
Write-Output 'ACL_READ=PASS'
if ($Id -eq '-' -or $Property -eq '-') { Write-Output ('INPUT=' + [Console]::In.ReadToEnd().Trim()) }
'@ | Set-Content (Join-Path $root 'FrpClient.ps1') -Encoding UTF8
    $cli = Join-Path $root 'drlink.cmd'
    # Simulate an intermediate process inheriting a non-Windows module path.
    $badModulePath = Join-Path $root 'non-windows-modules'
    $env:PSModulePath = $badModulePath
    foreach ($command in @(@('test','configuration','-'), @('system','diff','configuration','-'), @('system','apply','configuration','-'))) {
        $output = 'fixture' | & $cli @command 2>&1
        Assert-FrpEqual 0 $LASTEXITCODE ('stdin launcher exit: ' + ($command -join ' '))
        Assert-FrpTrue (($output -join "`n") -match 'INPUT=fixture') 'stdin content reaches script'
        Assert-FrpTrue (($output -join "`n") -match 'ACL_READ=PASS') 'native ACL provider can read a directory'
        Assert-FrpEqual $badModulePath $env:PSModulePath 'parent module path unchanged'
        $extra = 'fixture' | & $cli @command unexpected 2>&1
        Assert-FrpEqual 2 $LASTEXITCODE 'extra arguments rejected'
    }
    $normal = & $cli test configuration 'C:\path with spaces\bundle.json' 2>&1
    Assert-FrpEqual 0 $LASTEXITCODE 'ordinary file argument succeeds'
    Assert-FrpTrue (($normal -join "`n").Contains('C:\path with spaces\bundle.json')) 'ordinary quoted arguments preserved'
    Write-FrpTestPass 'cli-stdin-transport'
} finally {
    $env:PSModulePath = $oldModulePath
    Remove-Item $root -Recurse -Force
}
