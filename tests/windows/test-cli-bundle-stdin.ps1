# Exercise the actual public cmd launcher and actual CLI against an isolated Agent fixture.
. (Join-Path $PSScriptRoot 'common.ps1')
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('drlink-cli-bundle-stdin-' + [guid]::NewGuid().ToString('N'))
$env:FRP_WINDOWS_ROOT = $tmp
$env:FRP_WINDOWS_V24_FIXTURE_DIR = Join-Path $tmp 'fixture'
New-Item -ItemType Directory -Force (Join-Path $tmp 'state'),$env:FRP_WINDOWS_V24_FIXTURE_DIR | Out-Null
@{schema_version=1;machine_id='00112233445566778899aabbccddeeff';host_id='fixture';services=@{};management_only=$true} | ConvertTo-Json | Set-Content (Join-Path $tmp 'state/client-state.json')
'{"serviceObjects":[],"networkObjects":[],"managedHosts":[]}' | Set-Content (Join-Path $env:FRP_WINDOWS_V24_FIXTURE_DIR 'catalog.json')
$cli = Join-Path $script:RepoRoot 'windows/tools/drlink.cmd'
$json = '{"configurationBundle":{"context":"agent","remoteServices":[]}}'
try {
    foreach ($command in @(@('test','configuration','-'),@('system','diff','configuration','-'),@('system','apply','configuration','-'))) {
        foreach ($text in @($json,($json+"`n:end`nignored"))) {
            $out = $text | & $cli @command 2>&1 | Out-String
            Assert-FrpEqual 0 $LASTEXITCODE ('actual CLI stdin: '+($command -join ' ')+' output='+$out)
            Assert-FrpTrue ($out -match 'VALID') 'actual CLI validates stdin'
        }
        $out = 'invalid bundle' | & $cli @command 2>&1 | Out-String
        Assert-FrpTrue ($LASTEXITCODE -ne 0) 'invalid stdin rejected'
    }
    Write-FrpTestPass 'cli-bundle-stdin'
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_WINDOWS_ROOT,Env:FRP_WINDOWS_V24_FIXTURE_DIR -ErrorAction SilentlyContinue
}
