# test-frpclient-entrypoint.ps1 — powershell -File FrpClient.ps1 must expose lib functions
. (Join-Path $PSScriptRoot 'common.ps1')

$clientPath = Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
$drlinkCmd = Join-Path $script:RepoRoot 'windows/tools/drlink.cmd'
$legacyCmd = Join-Path $script:RepoRoot 'windows/tools/frp-client.cmd'
Assert-FrpTrue (Test-Path -LiteralPath $drlinkCmd) 'canonical drlink.cmd wrapper exists'
Assert-FrpTrue (Test-Path -LiteralPath $legacyCmd) 'retired frp-client.cmd rejection shim exists'
$drlinkSrc = Get-Content -LiteralPath $drlinkCmd -Raw
$legacySrc = Get-Content -LiteralPath $legacyCmd -Raw
Assert-FrpTrue ($drlinkSrc -match 'FrpClient\.ps1') 'drlink.cmd invokes canonical PowerShell CLI directly'
Assert-FrpTrue ($drlinkSrc -notmatch 'frp-client\.cmd') 'drlink.cmd does not traverse the retired launcher'
Assert-FrpTrue ($legacySrc -match 'not a current Data Relay Link command') 'retired launcher fails closed'
$src = Get-Content -LiteralPath $clientPath -Raw
Assert-FrpTrue ($src -match '(?m)^\s*\. Import-FrpWindowsModules\s*$') 'dot-sources Import-FrpWindowsModules into script scope'

$hosts = New-Object System.Collections.ArrayList
[void]$hosts.Add((Get-Process -Id $PID).Path)
if ($env:SystemRoot) {
    $winPs = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (Test-Path -LiteralPath $winPs) {
        [void]$hosts.Add($winPs)
    }
}

$tmpRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('frp-win-entry-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpRoot -Force | Out-Null
$env:FRP_WINDOWS_ROOT = $tmpRoot
# Unenrolled entrypoint root has no client-state allocator_url; provide an
# origin so update -Check can resolve the qualified windows/amd64 artifact URL.
$env:FRP_ALLOCATOR_URL = 'https://example.test/enroll'
try {
    foreach ($exe in @($hosts | Select-Object -Unique)) {
        $label = Split-Path -Leaf $exe
        $doctorOut = & $exe -NoProfile -ExecutionPolicy Bypass -File $clientPath system diagnostics 2>&1 | Out-String
        Assert-FrpTrue ($doctorOut -match 'Data Relay Link Agent Host diagnostics') "$label diagnostics entrypoint ran"
        Assert-FrpTrue ($doctorOut -match 'Root:') "$label diagnostics called Get-FrpWindowsRoot"
        Assert-FrpTrue ($doctorOut -notmatch 'is not recognized') "$label diagnostics has module functions"

        $statusOut = & $exe -NoProfile -ExecutionPolicy Bypass -File $clientPath show status 2>&1 | Out-String
        Assert-FrpTrue ($statusOut -match 'enrolled=') "$label show status entrypoint ran"
        Assert-FrpTrue ($statusOut -notmatch 'is not recognized') "$label show status has module functions"

        $checkOut = & $exe -NoProfile -ExecutionPolicy Bypass -File $clientPath system update engine -Check 2>&1 | Out-String
        Assert-FrpTrue ($checkOut -match 'FRP engine') "$label system update engine -Check shows engine section"
        Assert-FrpTrue ($checkOut -match 'Would download:') "$label system update engine -Check binds to script switch"
        Assert-FrpTrue ($checkOut -match 'preserved') "$label system update engine -Check is dry-run"
        Assert-FrpTrue ($checkOut -notmatch 'is not recognized') "$label update check has Get-FrpWindowsAmd64Url"
    }
    Write-FrpTestPass 'test-frpclient-entrypoint'
} finally {
    Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:FRP_ALLOCATOR_URL -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $tmpRoot -Recurse -Force -ErrorAction SilentlyContinue
}
