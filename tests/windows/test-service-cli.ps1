# test-service-cli.ps1 — retired Windows service grammar must fail closed.
. (Join-Path $PSScriptRoot 'common.ps1')
$clientPath = Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
$hostExe = 'pwsh'
try { $hostExe = (Get-Process -Id $PID).Path } catch { }
$tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('drlink-win-legacy-cli-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $tmpRoot 'state') -Force | Out-Null
$env:FRP_WINDOWS_ROOT = $tmpRoot

function Run-Legacy {
    param([string[]]$CliArgs)
    $lines = & $hostExe -NoProfile -ExecutionPolicy Bypass -File $clientPath @CliArgs 2>&1
    $rc = $LASTEXITCODE
    return @{ Rc=$rc; Out=($lines | Out-String) }
}
try {
    $state = [ordered]@{
        schema_version=1; allocator_url='https://example.test/enroll'; frp_server='example.test'
        frp_server_port=7000; frp_transport='tcp'; hostname='win-cli'; machine_id='00112233445566778899aabbccddeeff'
        host_id='cliabcd'; services=@{}; management_only=$true; project_version='2.4.0'; frp_version='0.71.0'
        platform='windows'; install_status='management_only'
    }
    $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $tmpRoot 'state/client-state.json')

    $legacyCases = @(
        @('list'),
        @('add-service'),
        @('set-service','x','target-port','22'),
        @('enable-service','x'),
        @('disable-service','x'),
        @('discard'),
        @('service','list'),
        @('service','add'),
        @('show','services'),
        @('set','service','x','target-port','22'),
        @('unset','service','x')
    )
    foreach ($case in $legacyCases) {
        $r = Run-Legacy $case
        Assert-FrpTrue ($r.Rc -ne 0) ('legacy grammar rejected: ' + ($case -join ' '))
    }

    $canonical = Run-Legacy @('show','remote-services')
    Assert-FrpEqual 0 $canonical.Rc 'canonical show remote-services remains available'
    Assert-FrpTrue ($canonical.Out -match 'No Remote Services configured') 'canonical empty state'

    Write-FrpTestPass 'test-service-cli'
} finally {
    Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
}
