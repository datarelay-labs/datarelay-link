. (Join-Path $PSScriptRoot '_import.ps1')
$original = [Console]::In
try {
    $json = '{"configurationBundle":{"context":"agent","remoteServices":[]}}'
    foreach ($inputText in @($json, ($json + "`n:end`nignored input after sentinel"))) {
        [Console]::SetIn((New-Object IO.StringReader($inputText)))
        $bundle = Read-FrpV24AgentBundle -Path '-'
        Assert-FrpEqual 'agent' $bundle.context 'stdin JSON context'
        Assert-FrpEqual 0 @($bundle.remoteServices).Count 'stdin empty service list'
    }
    Write-FrpTestPass 'bundle-stdin-reader'
} finally { [Console]::SetIn($original); Remove-FrpWindowsTestRoot }
