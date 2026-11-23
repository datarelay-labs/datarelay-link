$ErrorActionPreference = 'Stop'
# Real E2E pre-enrollment probe for a Windows client.
# - Canonical root (ProgramData\drlink): created by earlier runs of this harness,
#   so it is uninstalled through the product's own tool.
# - Legacy root (ProgramData\frp-auto-deploy): an enrolled v2.3.x Agent that this
#   harness did not create.  Never touch it; fail closed so the owner decides.
$programData = $env:ProgramData
$canonical = Join-Path $programData 'drlink'
$legacy = Join-Path $programData 'frp-auto-deploy'

$legacyEnrolled = $true
foreach ($rel in @('state/client-state.json', 'config/frpc.toml', 'state/client-identity.pub')) {
    if (-not (Test-Path -LiteralPath (Join-Path $legacy $rel) -PathType Leaf)) { $legacyEnrolled = $false; break }
}
if ($legacyEnrolled) {
    Write-Output "LEGACY_INSTALL_PRESENT $legacy"
    exit 1
}

$tool = Join-Path $canonical 'tools/frp-client.cmd'
if (Test-Path -LiteralPath $tool) {
    & $tool uninstall
    if (Test-Path -LiteralPath $canonical) { exit 1 }
    Write-Output 'UNINSTALL_OK'
} else {
    Write-Output 'NO_INSTALL'
}
