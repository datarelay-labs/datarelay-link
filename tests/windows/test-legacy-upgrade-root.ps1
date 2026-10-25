. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $script:WindowsLib 'FrpPaths.ps1')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('drlink-legacy-root-' + [guid]::NewGuid().ToString('N'))
$oldProgramData = $env:ProgramData
$oldRoot = $env:FRP_WINDOWS_ROOT
function Test-FrpIsWindowsHost { return $true }
function Seed-EnrolledRoot([string]$Root) {
    foreach ($rel in @('state/client-state.json','config/frpc.toml','state/client-identity.pub','state/client-identity.key')) {
        $path = Join-Path $Root $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
        Set-Content -LiteralPath $path -Value 'fixture'
    }
}
try {
    $env:ProgramData = $temp
    Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue
    $canonical = Join-Path $temp 'drlink'
    $legacy = Join-Path $temp 'frp-auto-deploy'
    Assert-FrpEqual $canonical (Get-FrpWindowsRoot) 'fresh install uses canonical root'
    Seed-EnrolledRoot $legacy
    Assert-FrpEqual $legacy (Get-FrpWindowsRoot) 'verified candidate finds prior enrolled product without root override'
    New-Item -ItemType Directory -Force -Path $canonical | Out-Null
    Assert-FrpEqual $legacy (Get-FrpWindowsRoot) 'empty canonical directory does not hide enrolled legacy identity'
    Seed-EnrolledRoot $canonical
    $failed = $false
    try { Get-FrpWindowsRoot | Out-Null } catch { $failed = $_.Exception.Message -match 'multiple enrolled' }
    Assert-FrpTrue $failed 'ambiguous two enrolled roots fail closed'
    Write-FrpTestPass 'test-legacy-upgrade-root'
} finally {
    $env:ProgramData = $oldProgramData
    if ($null -eq $oldRoot) { Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue }
    else { $env:FRP_WINDOWS_ROOT = $oldRoot }
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
