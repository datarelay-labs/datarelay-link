# test-canonical-sign.ps1
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    $body = '{"machine_id":"machine-id-deadbeef01","hostname":"win-test","services":[]}'
    $ts = 1700000000L
    $nonce = 'ab' * 32
    $msg = Get-FrpSignedMessage -MachineId 'machine-id-deadbeef01' -Body $body -Timestamp $ts -Nonce $nonce
    Assert-FrpTrue ($msg -match '"schema":1') 'schema 1'
    Assert-FrpTrue ($msg -match '"alg":"ecdsa-p256-sha256"') 'alg'
    Assert-FrpTrue ($msg -match '"op":"enroll"') 'op'
    # sort_keys order: alg, body_sha256, machine_id, nonce, op, schema, ts
    Assert-FrpTrue ($msg.StartsWith('{"alg":')) 'sorted keys start with alg'

    $lifecycleMsg = Get-FrpSignedMessage -MachineId 'machine-id-deadbeef01' -Body '{"state":"connected"}' `
        -Timestamp $ts -Nonce $nonce -Op 'agent.lifecycle' -Method 'POST' -Path '/v1/agent-lifecycle'
    Assert-FrpTrue ($lifecycleMsg -match '"method":"POST"') 'method bound into lifecycle signature'
    Assert-FrpTrue ($lifecycleMsg -match '"path":"/v1/agent-lifecycle"') 'path bound into lifecycle signature'
    Assert-FrpTrue ($lifecycleMsg -match '"op":"agent.lifecycle"') 'lifecycle op bound into signature'

    $id = New-FrpEcdsaIdentity
    $sig = Protect-FrpSignMessage -PrivatePem $id.PrivatePem -Message $msg
    Assert-FrpTrue (Test-FrpSignature -PublicPem $id.PublicPem -Message $msg -SignatureBase64 $sig) 'verify'

    Write-FrpTestPass 'test-canonical-sign'
} finally {
    Remove-FrpWindowsTestRoot
}
