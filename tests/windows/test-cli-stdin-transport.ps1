# Native Windows PowerShell 5.1 launcher regression: a bare '-' must reach the script.
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Join-Path ([IO.Path]::GetTempPath()) ('drlink-stdin-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $root | Out-Null
try {
    Copy-Item (Join-Path $script:RepoRoot 'windows/tools/drlink.cmd') $root
    @'
param([string]$Command,[string]$SubCommand,[string]$Id,[string]$Property)
Write-Output ('ARGS=' + $Command + '|' + $SubCommand + '|' + $Id + '|' + $Property)
if ($Id -eq '-' -or $Property -eq '-') { Write-Output ('INPUT=' + [Console]::In.ReadToEnd().Trim()) }
'@ | Set-Content (Join-Path $root 'FrpClient.ps1') -Encoding UTF8
    $cli = Join-Path $root 'drlink.cmd'
    foreach ($command in @(@('test','configuration','-'), @('system','diff','configuration','-'), @('system','apply','configuration','-'))) {
        $output = 'fixture' | & $cli @command 2>&1
        Assert-FrpEqual 0 $LASTEXITCODE ('stdin launcher exit: ' + ($command -join ' '))
        Assert-FrpTrue (($output -join "`n") -match 'INPUT=fixture') 'stdin content reaches script'
        $extra = 'fixture' | & $cli @command unexpected 2>&1
        Assert-FrpEqual 2 $LASTEXITCODE 'extra arguments rejected'
    }
    $normal = & $cli test configuration 'C:\path with spaces\bundle.json' 2>&1
    Assert-FrpEqual 0 $LASTEXITCODE 'ordinary file argument succeeds'
    Assert-FrpTrue (($normal -join "`n").Contains('C:\path with spaces\bundle.json')) 'ordinary quoted arguments preserved'
    Write-FrpTestPass 'cli-stdin-transport'
} finally { Remove-Item $root -Recurse -Force }
