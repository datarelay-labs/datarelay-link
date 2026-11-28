# Qualified product update: isolated transport and child installer fixture.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    $script:head = 'b' * 40
    $script:payload = 'verified bootstrap fixture'
    $script:digest = ([BitConverter]::ToString(([Security.Cryptography.SHA256]::Create()).ComputeHash([Text.Encoding]::UTF8.GetBytes($script:payload)))).Replace("-", "").ToLowerInvariant()
    $script:manifest = @{ qualification_status='PASS'; source_head=$script:head; project_version='2.4.0'; channel='development'; artifacts=@(@{artifact_type='agent-installer';platform='windows';architecture='amd64';filename='bootstrap-client.ps1';relative_path='agent/bootstrap-client.ps1';source_head=$script:head;sha256=$script:digest}) }
    $script:sums = "$($script:digest)  agent/bootstrap-client.ps1`n"
    $script:applied = 0
    $script:downloads = 0
    function Test-FrpIsEnrolled { return $true }
    function Read-FrpClientState { return @{allocator_url='https://qualified.example/enroll'} }
    function Invoke-FrpHttpsDownload {
        param($Url,$DestinationPath)
        Assert-FrpTrue ($Url.StartsWith('https://qualified.example/artifacts/')) 'enrolled origin only'
        $script:downloads++
        $body = if ($Url.EndsWith('/manifest.json')) { $script:manifest | ConvertTo-Json -Depth 8 } elseif ($Url.EndsWith('/SHA256SUMS')) { $script:sums } else { $script:payload }
        [IO.File]::WriteAllText($DestinationPath,$body,[Text.UTF8Encoding]::new($false))
    }
    function Invoke-FrpVerifiedWindowsBootstrapUpgrade {
        param($Path)
        Assert-FrpEqual $script:digest (Get-FrpSha256HexOfFile -Path $Path) 'verified before invocation'
        $script:applied++
        [IO.File]::WriteAllText((Get-FrpVersionPath),"PROJECT_VERSION=2.4.0`nRELEASE_CHANNEL=development`nSOURCE_HEAD=$script:head`n")
    }
    [IO.File]::WriteAllText((Get-FrpVersionPath),"PROJECT_VERSION=2.4.0`nRELEASE_CHANNEL=development`nSOURCE_HEAD=$('a'*40)`n")
    $before = Get-Content -LiteralPath (Get-FrpVersionPath) -Raw
    Invoke-FrpQualifiedWindowsProductUpdate -CheckOnly
    Assert-FrpEqual 2 $script:downloads 'check metadata only'
    Assert-FrpEqual 0 $script:applied 'check never applies'
    Assert-FrpEqual $before (Get-Content -LiteralPath (Get-FrpVersionPath) -Raw) 'check preserves installed metadata'
    foreach ($case in @('channel','duplicate','digest','unqualified')) {
        $script:manifest.channel='development'; $script:manifest.qualification_status='PASS'; $script:sums="$($script:digest)  agent/bootstrap-client.ps1`n"; $script:payload='verified bootstrap fixture'
        switch ($case) { 'channel' {$script:manifest.channel='stable'} 'duplicate' {$script:sums += $script:sums} 'digest' {$script:payload='tampered'} 'unqualified' {$script:manifest.qualification_status='FAIL'} }
        $rejected=$false
        try { Invoke-FrpQualifiedWindowsProductUpdate } catch { $rejected=$true }
        Assert-FrpTrue $rejected "$case rejected"
        Assert-FrpEqual 0 $script:applied "$case never executes"
        Assert-FrpEqual $before (Get-Content -LiteralPath (Get-FrpVersionPath) -Raw) "$case preserves metadata"
    }
    $script:manifest.qualification_status='PASS'; $script:manifest.channel='development'; $script:payload='verified bootstrap fixture'; $script:sums="$($script:digest)  agent/bootstrap-client.ps1`n"
    Invoke-FrpQualifiedWindowsProductUpdate
    Assert-FrpEqual 1 $script:applied 'verified artifact applied once'
    Write-FrpTestPass 'test-qualified-product-update'
} finally { Remove-FrpWindowsTestRoot }
