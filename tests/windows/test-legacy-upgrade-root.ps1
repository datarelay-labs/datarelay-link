. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $script:WindowsLib 'FrpPaths.ps1')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('drlink-legacy-root-' + [guid]::NewGuid().ToString('N'))
$oldProgramData = $env:ProgramData
$oldRoot = $env:FRP_WINDOWS_ROOT
function Test-FrpIsWindowsHost { return $true }
function Seed-EnrolledRoot([string]$Root, [string]$KeyName = 'client-identity.key.dpapi') {
    foreach ($rel in @('state/client-state.json','config/frpc.toml','state/client-identity.pub',('state/' + $KeyName))) {
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
    Seed-EnrolledRoot $canonical 'client-identity.key'
    $failed = $false
    try { Get-FrpWindowsRoot | Out-Null } catch { $failed = $_.Exception.Message -match 'multiple enrolled' }
    Assert-FrpTrue $failed 'ambiguous two enrolled roots fail closed'
    Remove-Item -LiteralPath $canonical -Recurse -Force
    $script:RootProbeFailures = 1
    $script:RootProbeAlwaysDenied = $false
    function Test-Path {
        [CmdletBinding()]
        param([string]$LiteralPath, [string]$Path, [string]$PathType)
        $probe = if ($LiteralPath) { $LiteralPath } else { $Path }
        if ($probe -eq (Join-Path $legacy 'state/client-state.json') -and
            ($script:RootProbeAlwaysDenied -or $script:RootProbeFailures -gt 0)) {
            $script:RootProbeFailures--
            throw [System.UnauthorizedAccessException]::new('concurrent state replacement fixture')
        }
        $parameters = @{}
        if ($LiteralPath) { $parameters.LiteralPath = $LiteralPath }
        else { $parameters.Path = $Path }
        if ($PathType) { $parameters.PathType = $PathType }
        return (Microsoft.PowerShell.Management\Test-Path @parameters)
    }
    try {
        Assert-FrpEqual $legacy (Get-FrpWindowsRoot) 'transient metadata denial retries without replacing enrolled identity'
        $script:RootProbeFailures = 2
        Assert-FrpEqual $legacy (Get-FrpWindowsRoot) 'last bounded attempt can still recover the same legacy root'
        $script:RootProbeAlwaysDenied = $true
        $failed = $false
        try { Get-FrpWindowsRoot | Out-Null }
        catch { $failed = $_.Exception.Message -match 'cannot inspect.*Retry.*Refusing' }
        Assert-FrpTrue $failed 'persistent access denial fails closed with actionable recovery, never canonical fallback'
        Seed-EnrolledRoot $canonical 'client-identity.key'
        $failed = $false
        try { Get-FrpWindowsRoot | Out-Null }
        catch { $failed = $_.Exception.Message -match 'cannot inspect.*Retry.*Refusing' }
        Assert-FrpTrue $failed 'a complete canonical root cannot hide a second unreadable legacy identity'
    } finally {
        Remove-Item Function:Test-Path
    }
    Write-FrpTestPass 'test-legacy-upgrade-root'
} finally {
    $env:ProgramData = $oldProgramData
    if ($null -eq $oldRoot) { Remove-Item Env:FRP_WINDOWS_ROOT -ErrorAction SilentlyContinue }
    else { $env:FRP_WINDOWS_ROOT = $oldRoot }
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
