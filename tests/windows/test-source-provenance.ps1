# Native Windows install provenance: qualified outer bytes, persistent CLI,
# engine-only preservation, and fail-closed mismatch before enrollment.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
$bundle = Join-Path ([IO.Path]::GetTempPath()) ('frp-provenance-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path (Join-Path $bundle 'windows') -Force | Out-Null
    $script:FrpWindowsSrcRoot = Join-Path $bundle 'windows'
    $content = 'a' * 40
    $candidate = 'b' * 40
    @{ project_version='2.4.0'; channel='development'; git_ref=$content } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $bundle 'release-manifest.json')
    $env:FRP_WINDOWS_BOOTSTRAP_PATH = Join-Path $bundle 'bootstrap-client.ps1'
    Set-Content -LiteralPath $env:FRP_WINDOWS_BOOTSTRAP_PATH -Value 'qualified installer bytes'
    $digest = Get-FrpSha256HexOfFile -Path $env:FRP_WINDOWS_BOOTSTRAP_PATH
    $script:QualifiedManifest = @{
        source_head=$candidate; project_version='2.4.0'; channel='development'; qualification_status='PASS'
        artifacts=@(@{ artifact_type='agent-installer'; platform='windows'; architecture='amd64'
            filename='bootstrap-client.ps1'; source_head=$candidate; sha256=$digest })
    }
    $script:Requests = 0
    function Invoke-FrpHttpsJson {
        param($Method, $Url)
        Assert-FrpEqual 'GET' $Method 'provenance is read only'
        Assert-FrpEqual 'https://qualified.example/artifacts/manifest.json' $Url 'same allocator HTTPS origin'
        $script:Requests++
        return ($script:QualifiedManifest | ConvertTo-Json -Depth 10)
    }
    Initialize-FrpDirectories
    Confirm-FrpWindowsSourceProvenance -AllocatorUrl 'https://qualified.example/enroll'
    Write-FrpInstalledVersion
    $text = Get-Content -LiteralPath (Get-FrpVersionPath) -Raw
    Assert-FrpTrue ($text.Contains("SOURCE_HEAD=$candidate")) 'exact qualified candidate stored'
    Assert-FrpTrue ($text.Contains("CONTENT_SOURCE_HEAD=$content")) 'embedded source separately stored'
    Assert-FrpTrue ($text.Contains('ROLE=AgentHost') -and $text.Contains('RELEASE_CHANNEL=development')) 'role/channel stored'

    # Simulate permanent installation, remove the entire unpacked bundle,
    # and run the real installed public command in a new PowerShell process.
    Copy-Item -LiteralPath (Join-Path $bundle 'release-manifest.json') -Destination (Get-FrpWindowsRoot)
    Copy-Item -Path (Join-Path $script:RepoRoot 'windows/lib/*.ps1') -Destination (Get-FrpLibDir) -Force
    Copy-Item -LiteralPath (Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1') -Destination (Get-FrpToolsDir) -Force
    Remove-Item -LiteralPath $bundle -Recurse -Force
    Remove-Item Env:FRP_WINDOWS_BOOTSTRAP_PATH
    $script:FrpWindowsSrcRoot = Get-FrpWindowsRoot
    Write-FrpInstalledVersion  # Binary-only maintenance retains identity.
    $exe = (Get-Process -Id $PID).Path
    $output = & $exe -NoProfile -File (Join-Path (Get-FrpToolsDir) 'FrpClient.ps1') system version 2>&1 | Out-String
    Assert-FrpEqual 0 $LASTEXITCODE 'installed version exit'
    Assert-FrpTrue ($output.Contains("Source HEAD: $candidate")) 'public exact source survives temporary payload removal'
    Assert-FrpTrue (-not $output.Contains('Source provenance is not verified')) 'verified Source HEAD does not recommend unnecessary reinstall'

    # Different local source content must never inherit old exact-candidate identity.
    $m = @{project_version='2.4.0';channel='development';git_ref=('c' * 40)}
    $m | ConvertTo-Json | Set-Content -LiteralPath (Join-Path (Get-FrpWindowsRoot) 'release-manifest.json')
    Write-FrpInstalledVersion
    Assert-FrpTrue ((Get-Content -LiteralPath (Get-FrpVersionPath) -Raw).Contains('SOURCE_HEAD=UNKNOWN')) 'changed unverified source fails closed'
    $unverifiedOutput = & $exe -NoProfile -File (Join-Path (Get-FrpToolsDir) 'FrpClient.ps1') system version 2>&1 | Out-String
    Assert-FrpEqual 0 $LASTEXITCODE 'unverified installed version command returns an operator result'
    Assert-FrpTrue ($unverifiedOutput.Contains('Source HEAD: UNKNOWN') -and $unverifiedOutput.Contains('Next action:')) 'unknown Source HEAD explains how to recover qualified provenance'

    # An altered outer payload cannot acquire the Server's qualified source.
    $env:FRP_WINDOWS_BOOTSTRAP_PATH = Join-Path (Get-FrpWindowsRoot) 'altered-bootstrap.ps1'
    Set-Content -LiteralPath $env:FRP_WINDOWS_BOOTSTRAP_PATH -Value 'altered bytes'
    $before = Get-Content -LiteralPath (Join-Path (Get-FrpWindowsRoot) 'source-provenance.json') -Raw
    $rejected = $false
    try { Confirm-FrpWindowsSourceProvenance -AllocatorUrl 'https://qualified.example/enroll' }
    catch { $rejected = $_.Exception.Message -match 'source provenance does not match' }
    Assert-FrpTrue $rejected 'outer payload mismatch rejected'
    Assert-FrpEqual $before (Get-Content -LiteralPath (Join-Path (Get-FrpWindowsRoot) 'source-provenance.json') -Raw) 'failed qualification preserves previous receipt'
    $script:FrpVerifiedBootstrapDigest = $null
    $script:QualifiedManifest.artifacts[0].sha256 = Get-FrpSha256HexOfFile -Path $env:FRP_WINDOWS_BOOTSTRAP_PATH
    $script:QualifiedManifest.channel = 'stable'
    $rejected = $false
    try { Confirm-FrpWindowsSourceProvenance -AllocatorUrl 'https://qualified.example/enroll' }
    catch { $rejected = $_.Exception.Message -match 'source provenance does not match' }
    Assert-FrpTrue $rejected 'qualified manifest cannot silently change embedded release channel'
    Write-FrpTestPass 'test-source-provenance'
} finally {
    Remove-Item Env:FRP_WINDOWS_BOOTSTRAP_PATH -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $bundle -Recurse -Force -ErrorAction SilentlyContinue
    Remove-FrpWindowsTestRoot
}
