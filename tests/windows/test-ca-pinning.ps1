# test-ca-pinning.ps1 — unit-level helpers
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    $norm = Normalize-FrpCaSha256 -Value 'SHA256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef'
    Assert-FrpEqual 64 $norm.Length 'normalized length'
    Assert-FrpEqual '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' $norm 'normalized value'

    $origin = Get-FrpAllocatorOrigin -AllocatorUrl 'https://frp.example.test:9443/enroll'
    Assert-FrpTrue ($origin -match '^https://frp\.example\.test:9443') 'origin host'

    try {
        Get-FrpAllocatorOrigin -AllocatorUrl 'http://frp.example.test/enroll' | Out-Null
        throw 'expected http reject'
    } catch {
        Assert-FrpTrue ($_.Exception.Message -match 'https') 'http rejected'
    }

    try {
        Normalize-FrpCaSha256 -Value 'deadbeef' | Out-Null
        throw 'expected short fingerprint reject'
    } catch {
        Assert-FrpTrue ($_.Exception.Message -match 'fingerprint') 'short fp rejected'
    }

    # Genuine X.509 pin + atomic replacement under the lifecycle lock.
    # The separate source-provenance test covers the real qualification
    # manifest logic; this fixture checks that verification precedes mutation.
    $ecdsa = [System.Security.Cryptography.ECDsa]::Create([System.Security.Cryptography.ECCurve]::CreateFromFriendlyName('nistP256'))
    $req = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
        'CN=orphan-ca-test', $ecdsa, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
    $cert = $req.CreateSelfSigned([DateTimeOffset]::UtcNow.AddDays(-1), [DateTimeOffset]::UtcNow.AddDays(2))
    $incoming = [IO.Path]::GetTempFileName()
    [IO.File]::WriteAllBytes($incoming, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
    $pin = Get-FrpCertificateDerSha256 -Certificate $cert
    $env:FRP_ALLOCATOR_CA_FILE = $incoming
    $env:FRP_WINDOWS_BOOTSTRAP_PATH = $incoming
    $script:RejectQualification = $false
    $script:QualificationCalls = 0
    function Confirm-FrpWindowsSourceProvenance {
        param($AllocatorUrl, $CaPath, [switch]$VerifyOnly)
        Assert-FrpTrue ($VerifyOnly -and (Test-Path -LiteralPath $CaPath)) 'qualification uses staged CA before mutation'
        $script:QualificationCalls++
        if ($script:RejectQualification) { throw 'fixture provenance rejected' }
    }
    Assert-FrpTrue (Enter-FrpClientLock) 'lifecycle lock held'
    try {
        $ca = Get-FrpAllocatorCaPath
        $scratch = Join-Path (Get-FrpCertsDir) ('allocator-ca.crt.' + ('a' * 32) + '.tmp')
        foreach ($case in @('corrupt-orphan','scratch-only','protected-state','protected-identity','protected-unknown','invalid-pin','invalid-provenance')) {
            if (Test-Path -LiteralPath $ca) { Remove-Item -LiteralPath $ca -Force }
            if (Test-Path -LiteralPath $scratch) { Remove-Item -LiteralPath $scratch -Force }
            $marker = $null
            $script:RejectQualification = ($case -eq 'invalid-provenance')
            $beforeCalls = $script:QualificationCalls
            $casePin = if ($case -eq 'invalid-pin') { 'a' * 64 } else { $pin }
            if ($case -ne 'scratch-only') { [IO.File]::WriteAllText($ca,'old corrupt CA') }
            [IO.File]::WriteAllText($scratch,'old scratch')
            switch ($case) {
                'protected-state' { $marker = Get-FrpStatePath }
                'protected-identity' { $marker = Get-FrpIdentityKeyPath }
                'protected-unknown' { $marker = Join-Path (Get-FrpCertsDir) 'manual-backup.crt' }
            }
            if ($marker) { [IO.File]::WriteAllText($marker,'preserve') }
            if ($case -in @('corrupt-orphan','scratch-only')) {
                # Observe the native classifier itself before asking for repair;
                # the verbose refusal reason is retained if a Windows runner differs.
                $classified = @(Get-FrpUnclaimedWindowsCaResidue -Verbose)
                Assert-FrpEqual $(if ($case -eq 'scratch-only') {1} else {2}) $classified.Count "$case unclaimed classification"
                Assert-FrpTrue ((Split-Path -Leaf $scratch) -in $classified) "$case relative scratch name"
                Assert-FrpTrue (@($classified | Where-Object { $_ -ne (Split-Path -Leaf $_) }).Count -eq 0) "$case no absolute path comparison"
            }
            $failed = $false
            try { Repair-FrpUnclaimedWindowsCaResidue -AllocatorUrl 'https://example.test/enroll' -CaSha256 $casePin -BootstrapLocator 'fixture' }
            catch {
                if ($case -notin @('invalid-pin','invalid-provenance')) { throw }
                $failed = $true
            }
            if ($case -in @('corrupt-orphan','scratch-only')) {
                Assert-FrpTrue (-not $failed -and (Test-Path -LiteralPath $ca)) "$case replaced"
                Assert-FrpTrue (-not (Test-Path -LiteralPath $scratch)) "$case scratch removed"
                $observed = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ca)
                try { Assert-FrpEqual $pin (Get-FrpCertificateDerSha256 -Certificate $observed) "$case CA pin" }
                finally { $observed.Dispose() }
                Assert-FrpEqual ($beforeCalls+1) $script:QualificationCalls "$case qualified once"
            } else {
                Assert-FrpEqual 'old corrupt CA' ([IO.File]::ReadAllText($ca)) "$case CA unchanged"
                Assert-FrpEqual 'old scratch' ([IO.File]::ReadAllText($scratch)) "$case scratch unchanged"
                if ($marker) {
                    Assert-FrpEqual 'preserve' ([IO.File]::ReadAllText($marker)) "$case protected"
                    Remove-Item -LiteralPath $marker -Force
                    Assert-FrpEqual $beforeCalls $script:QualificationCalls "$case no qualification"
                } else {
                    Assert-FrpTrue $failed "$case rejected"
                }
            }
        }
        Write-FrpTestPass 'windows-orphan-ca-residue (7 cases)'
    } finally {
        Exit-FrpClientLock
        Remove-Item -LiteralPath $incoming -Force
        Remove-Item Env:FRP_ALLOCATOR_CA_FILE,Env:FRP_WINDOWS_BOOTSTRAP_PATH -ErrorAction SilentlyContinue
        $cert.Dispose()
        $ecdsa.Dispose()
    }

    Write-FrpTestPass 'test-ca-pinning'
} finally {
    Remove-FrpWindowsTestRoot
}
