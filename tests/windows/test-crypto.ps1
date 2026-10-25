# test-crypto.ps1 — roundtrip + basic vectors
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    $id = New-FrpEcdsaIdentity
    Assert-FrpTrue ($id.PublicPem -match 'BEGIN PUBLIC KEY') 'public pem'
    Assert-FrpTrue ($id.PrivatePem -like '*-*PRIVATE KEY*-*') 'private pem'

    $msg = Get-FrpSignedMessage -MachineId 'machine-deadbeef' -Body '{}' -Timestamp 1700000000 -Nonce ('ab' * 32)
    $sig = Protect-FrpSignMessage -PrivatePem $id.PrivatePem -Message $msg
    Assert-FrpTrue (Test-FrpSignature -PublicPem $id.PublicPem -Message $msg -SignatureBase64 $sig) 'sign/verify'

    $ct = Protect-FrpTokenPbkdf2 -Token 'tok-deadbeef' -Secret 'secret-deadbeef0123456789'
    $pt = Unprotect-FrpTokenPbkdf2 -Ciphertext $ct -Secret 'secret-deadbeef0123456789'
    Assert-FrpEqual 'tok-deadbeef' $pt 'token roundtrip'

    $mac = Get-FrpDerivedMacKey -Secret 'enroll-secret-deadbeef' -MachineId 'machine-deadbeef'
    Assert-FrpEqual 64 $mac.Length 'mac hex length'

    $cj = Get-FrpCanonicalJson -Object (@{ b = 1; a = 2 })
    Assert-FrpEqual '{"a":2,"b":1}' $cj 'canonical sort'

    # A signed Server response contains ISO timestamps. ConvertFrom-Json can
    # convert these strings into local DateTime values before HMAC validation.
    $wire = '{"empty":{},"items":["2026-10-25T03:04:05.123456Z"],"syncedAt":"2026-10-25T03:04:05+00:00"}'
    $parsed = ConvertFrom-FrpJson -Json $wire
    Assert-FrpEqual $wire (Get-FrpCanonicalJson $parsed) 'signed JSON preserves timestamp strings, arrays and empty objects'
    # Vector produced by Python's hmac/json implementation, not by the parser
    # under test. Exercise the actual management-response verification path.
    $vectorMac = 'c9b16acbd215a58719c17b6fa1a8b8b6c26c36534563e5c2abd240d71130c184'
    Assert-FrpEqual $vectorMac (Get-FrpHmacHex -Secret ('aa' * 32) -Message (Get-FrpCanonicalJson $parsed)) 'Python response MAC interoperability'
    Save-FrpIdentityKey -PrivatePem $id.PrivatePem | Out-Null
    Save-FrpIdentityPublic -PublicPem $id.PublicPem | Out-Null
    Save-FrpIdentityMac -MacKeyHex ('aa' * 32) | Out-Null
    Set-Content -LiteralPath (Get-FrpStatePath) -Value '{"machine_id":"fixture-agent","allocator_url":"https://example.test/enroll"}'
    Set-Content -LiteralPath (Get-FrpTomlPath) -Value '# isolated test fixture'
    $script:WireResponse = $wire.Substring(0, $wire.Length - 1) + ',"response_hmac":"' + $vectorMac + '"}'
    function Invoke-FrpHttpsJson { return $script:WireResponse }
    $verified = Invoke-FrpV24MgmtRequest -Method GET -Path '/v1/catalog'
    Assert-FrpEqual '2026-10-25T03:04:05+00:00' $verified.syncedAt 'signed Server timestamp accepted without conversion'
    $script:WireResponse = $script:WireResponse.Replace('03:04:05+00:00', '03:04:06+00:00')
    $rejected = $false
    try { Invoke-FrpV24MgmtRequest -Method GET -Path '/v1/catalog' | Out-Null }
    catch { $rejected = $_.Exception.Message -match 'integrity verification' }
    Assert-FrpTrue $rejected 'tampered Server response still rejected'

    $script:WireResponse = $wire.Substring(0, $wire.Length - 1) + ',"response_hmac":"' + $vectorMac + '"}'
    $lifecycle = Invoke-FrpAgentLifecycle -State connected
    Assert-FrpEqual '2026-10-25T03:04:05+00:00' $lifecycle.syncedAt 'lifecycle signed timestamps stay strings'
    $script:WireResponse = $script:WireResponse.Replace('03:04:05+00:00', '03:04:06+00:00')
    $rejected = $false
    try { Invoke-FrpAgentLifecycle -State connected | Out-Null }
    catch { $rejected = $_.Exception.Message -match 'HMAC verification' }
    Assert-FrpTrue $rejected 'tampered lifecycle response rejected'

    Write-FrpTestPass 'test-crypto'
} finally {
    Remove-FrpWindowsTestRoot
}
