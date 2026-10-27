# F022: standalone Windows support archives carry public installed provenance.
. (Join-Path $PSScriptRoot 'common.ps1')
$testRoot=Join-Path ([IO.Path]::GetTempPath()) ('drlink-support-provenance-'+[guid]::NewGuid().ToString('N'))
$env:FRP_WINDOWS_ROOT=$testRoot
$exe=(Get-Process -Id $PID).Path
$client=Join-Path $script:RepoRoot 'windows/tools/FrpClient.ps1'
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$source='a'*40; $content='b'*40; $engine='c'*64; $canary='F022_private_canary_not_for_support'
@("PROJECT_VERSION=2.4.0",'FRP_VERSION=0.71.0','ROLE=AgentHost','RELEASE_CHANNEL=development',"SOURCE_HEAD=$source","CONTENT_SOURCE_HEAD=$content","FRP_SHA256_WINDOWS_AMD64=$engine","SENSITIVE_TOKEN=$canary") | Set-Content -LiteralPath (Join-Path $testRoot 'version')
$before=(Get-FileHash -Algorithm SHA256 (Join-Path $testRoot 'version')).Hash
try {
    $out=& $exe -NoProfile -File $client system support-bundle 2>&1 | Out-String
    Assert-FrpEqual 0 $LASTEXITCODE 'public support archive exit'
    $zip=Get-ChildItem -LiteralPath (Join-Path $testRoot 'support-bundles') -Filter '*.zip' | Select-Object -First 1
    Assert-FrpTrue ($null -ne $zip) 'archive exists'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive=[IO.Compression.ZipFile]::OpenRead($zip.FullName)
    try {
        $text=@{}
        foreach($entry in $archive.Entries) {
            $rd=New-Object IO.StreamReader($entry.Open())
            try {$text[$entry.FullName]=$rd.ReadToEnd()} finally {$rd.Dispose()}
        }
        $meta=$text['meta.json'] | ConvertFrom-Json
        Assert-FrpEqual $source $meta.provenance.source_head 'standalone archive exact source'
        Assert-FrpEqual $content $meta.provenance.content_source_head 'content source remains distinct'
        Assert-FrpEqual '2.4.0' $meta.provenance.project_version 'installed product version'
        Assert-FrpEqual '0.71.0' $meta.provenance.relay_engine_version 'distinct engine version'
        Assert-FrpEqual $engine $meta.provenance.relay_engine_sha256 'public engine digest'
        Assert-FrpEqual 'development' $meta.provenance.release_channel 'installed channel'
        Assert-FrpEqual 'AgentHost' $meta.role 'current Agent Host role'
        Assert-FrpTrue (-not (($text.Values -join "`n").Contains($canary))) 'unrelated version-file secrets omitted'
    } finally {$archive.Dispose()}
    Assert-FrpEqual $before (Get-FileHash -Algorithm SHA256 (Join-Path $testRoot 'version')).Hash 'support does not rewrite install provenance'
    Write-FrpTestPass 'test-support-source-provenance'
} finally {Remove-Item -LiteralPath $testRoot -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue}
