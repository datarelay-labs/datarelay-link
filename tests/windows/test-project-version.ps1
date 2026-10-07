# test-project-version.ps1 — Windows fallback matches canonical VERSION
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
$original = @{
    PROJECT_VERSION = $env:PROJECT_VERSION
    FRP_ALLOCATOR_URL = $env:FRP_ALLOCATOR_URL
    FRP_WINDOWS_DOWNLOAD_URL = $env:FRP_WINDOWS_DOWNLOAD_URL
}
try {
    $expected = $null
    foreach ($line in Get-Content -LiteralPath (Join-Path $script:RepoRoot 'VERSION')) {
        if ($line -match '^\s*PROJECT_VERSION\s*=\s*(.+)\s*$') {
            $expected = $Matches[1].Trim()
            break
        }
    }
    Assert-FrpTrue (-not [string]::IsNullOrWhiteSpace($expected)) 'VERSION PROJECT_VERSION present'

    Remove-Item Env:PROJECT_VERSION -ErrorAction SilentlyContinue
    $got = Get-FrpProjectVersion
    Assert-FrpEqual $expected $got 'Get-FrpProjectVersion matches VERSION'
    Assert-FrpTrue ($got -ne '2.1.1') 'stale 2.1.1 fallback removed'

    # Current package defaults must not overwrite an observed installed identity.
    Set-Content -LiteralPath (Get-FrpVersionPath) -Value 'PROJECT_VERSION=2.4.0' -Encoding UTF8
    Assert-FrpEqual '2.4.0' (Get-FrpProjectVersion) 'installed version precedes packaged fallback'
    $env:PROJECT_VERSION = ' 9.8.7 '
    Assert-FrpEqual '9.8.7' (Get-FrpProjectVersion) 'explicit version override has precedence'
    Remove-Item Env:PROJECT_VERSION -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Get-FrpVersionPath) -Force
    Assert-FrpEqual $expected (Get-FrpProjectVersion) 'missing installed version restores packaged identity'

    # Resolve an error only; never download anything or contact a network endpoint.
    Remove-Item Env:FRP_ALLOCATOR_URL -ErrorAction SilentlyContinue
    foreach ($override in @('', 'https://github.com/fatedier/frp/releases/download/unused.zip')) {
        if ($override) { $env:FRP_WINDOWS_DOWNLOAD_URL = $override }
        else { Remove-Item Env:FRP_WINDOWS_DOWNLOAD_URL -ErrorAction SilentlyContinue }
        $errorText = ''
        try { $null = Get-FrpWindowsAmd64Url }
        catch { $errorText = $_.Exception.Message }
        Assert-FrpTrue ($errorText.Contains('Required qualified artifact is not available')) 'missing/unsupported origin fails closed'
        Assert-FrpTrue ($errorText.Contains("Data Relay Link Agent $expected")) 'artifact guidance uses resolved product version'
    }

    Write-FrpTestPass 'test-project-version'
} finally {
    foreach ($name in $original.Keys) {
        if ($null -eq $original[$name]) { Remove-Item ("Env:" + $name) -ErrorAction SilentlyContinue }
        else { Set-Item ("Env:" + $name) -Value $original[$name] }
    }
    Remove-FrpWindowsTestRoot
}
