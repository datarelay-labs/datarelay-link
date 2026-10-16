# test-zero-touch-command.ps1 — validate installer parameter patterns
$ErrorActionPreference = 'Stop'

function Assert-FrpTrue {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERT: $Message" }
}
function Write-FrpTestPass { param([string]$Name) Write-Host "PASS $Name" }

$install = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path 'windows\install-client.ps1'
Assert-FrpTrue (Test-Path -LiteralPath $install) 'install-client.ps1 exists'
$text = Get-Content -LiteralPath $install -Raw
Assert-FrpTrue ($text -match 'ZeroTouch') 'ZeroTouch param'
Assert-FrpTrue ($text -match 'AllocatorUrl') 'AllocatorUrl param'
Assert-FrpTrue ($text -match 'CaSha256') 'CaSha256 param'
Assert-FrpTrue ($text -match 'BootstrapTicket') 'BootstrapTicket param'
Assert-FrpTrue ($text -match 'FRP_ZERO_TOUCH') 'honors FRP_ZERO_TOUCH env from generated one-liners'
Assert-FrpTrue ($text -notmatch '(?i)Invoke-RestMethod\s*\|\s*Invoke-Expression') 'no irm|iex invocation'
Assert-FrpTrue ($text -match 'No irm\|iex' -or $text -match 'never.*irm') 'documents no irm|iex'

$boot = Get-Content -LiteralPath (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path 'windows\lib\FrpBootstrap.ps1') -Raw
Assert-FrpTrue ($boot -match 'already enrolled') 'enroll once messaging'
Assert-FrpTrue ($boot -match 'Clear-FrpSecretEnv') 'secret env cleanup'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$create = Get-Content -LiteralPath (Join-Path $repo 'tools\frp-create-client') -Raw
Assert-FrpTrue ($create -match '-File \$p -ZeroTouch') 'fallback Windows one-liner passes -ZeroTouch to -File'
$zt = Get-Content -LiteralPath (Join-Path $repo 'lib\frp_zero_touch.py') -Raw
Assert-FrpTrue ($zt -match '-File \$installer -ZeroTouch') 'Short URL Windows bootstrap passes -ZeroTouch to -File'
Assert-FrpTrue ($zt -match '\[System\.Security\.Cryptography\.X509Certificates\.X509VerificationFlags\]') 'generated pin uses WinPS-compatible X509VerificationFlags type'
Assert-FrpTrue ($zt -match '\[System\.Security\.Cryptography\.X509Certificates\.X509RevocationMode\]') 'generated pin uses WinPS-compatible X509RevocationMode type'
Assert-FrpTrue ($zt -notmatch '\[Net\.Security\.X509Certificates\.') 'generated pin does not use invalid short X509 namespace'

# Execute the exact enum type resolution under Windows PowerShell. This catches
# namespace regressions that source-only string checks cannot detect.
$vf = [System.Security.Cryptography.X509Certificates.X509VerificationFlags]::AllowUnknownCertificateAuthority
$rm = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
Assert-FrpTrue ($null -ne $vf) 'X509VerificationFlags enum resolves at runtime'
Assert-FrpTrue ($null -ne $rm) 'X509RevocationMode enum resolves at runtime'

Write-FrpTestPass 'test-zero-touch-command'
