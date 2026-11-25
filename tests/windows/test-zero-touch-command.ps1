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
Assert-FrpTrue ($text -match 'BootstrapLocator') 'BootstrapLocator param'
Assert-FrpTrue ($text -match 'FRP_ZERO_TOUCH') 'honors FRP_ZERO_TOUCH env from generated one-liners'
Assert-FrpTrue ($text -notmatch '(?i)Invoke-RestMethod\s*\|\s*Invoke-Expression') 'no irm|iex invocation'
Assert-FrpTrue ($text -match 'initial entry HTTPS does not authenticate' -and $text -match 'iex\(curl\.exe -kfsS https://[^/]+/[A-Za-z0-9_-]{8}\|Out-String\)') 'documents fixed entry and initial TLS risk'

$boot = Get-Content -LiteralPath (Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path 'windows\lib\FrpBootstrap.ps1') -Raw
Assert-FrpTrue ($boot -match 'already enrolled') 'enroll once messaging'
Assert-FrpTrue ($boot -match 'Clear-FrpSecretEnv') 'secret env cleanup'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$create = Get-Content -LiteralPath (Join-Path $repo 'tools\frp-create-client') -Raw
Assert-FrpTrue ($create -match 'render_entry_command' -and $create -notmatch 'windows_strict_launcher') 'Windows issuer uses the fixed entry renderer'
Assert-FrpTrue ($create -notmatch '--long-bootstrap|pinned_ca_windows_command|legacy_env') 'retired Windows long-form command must not return'
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
