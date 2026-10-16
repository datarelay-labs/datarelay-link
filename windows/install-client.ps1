#Requires -Version 5.1
<#
.SYNOPSIS
  Windows FRP client installer (zero-touch and manual helpers).

.DESCRIPTION
  Works with Windows PowerShell 5.1 and PowerShell 7.
  Reuses the existing allocator bootstrap/enroll protocol (no forked enrollment).

.EXAMPLE
  .\install-client.ps1 -ZeroTouch -AllocatorUrl https://frp.example/enroll `
    -CaSha256 <sha256> -BootstrapTicket 'bt1.xxx.yyy'
#>
[CmdletBinding()]
param(
    [string]$AllocatorUrl = $env:FRP_ALLOCATOR_URL,
    [string]$CaSha256 = $env:FRP_ALLOCATOR_CA_SHA256,
    [string]$BootstrapTicket = $env:FRP_BOOTSTRAP_TICKET,
    [switch]$ZeroTouch,
    [string]$Platform = 'windows',
    [string]$ServicesJson = $env:FRP_SERVICES_JSON,
    [string]$SshUser = $env:FRP_SSH_USER,
    [string]$Hostname = $env:FRP_HOSTNAME,
    [switch]$SkipStart,
    [switch]$SkipDownload,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

function Show-FrpInstallHelp {
    @'
Data Relay Link Windows Agent Host installer

Zero-touch:
  .\install-client.ps1 -ZeroTouch -AllocatorUrl https://HOST/enroll `
      -CaSha256 <DER-SHA256> -BootstrapTicket 'bt1.<id>.<secret>'

Environment equivalents:
  FRP_ALLOCATOR_URL, FRP_ALLOCATOR_CA_SHA256, FRP_BOOTSTRAP_TICKET

After enrollment:
  tools\drlink.cmd show status
  tools\drlink.cmd show remote-services
  tools\drlink.cmd system info
  tools\drlink.cmd system pause
  tools\drlink.cmd system resume
  tools\drlink.cmd system restart
  tools\drlink.cmd system autostart
  tools\drlink.cmd system synchronize
  tools\drlink.cmd test configuration <FILE|->
  tools\drlink.cmd system export configuration <FILE>
  tools\drlink.cmd system diff configuration <FILE|->
  tools\drlink.cmd system apply configuration <FILE|->
  tools\drlink.cmd system diagnostics
  tools\drlink.cmd system update product
  tools\drlink.cmd system update engine
  tools\drlink.cmd system uninstall

Notes:
  - ENROLL ONCE: if already enrolled, refuse ticket re-use; use drlink system resume
  - No irm|iex. Download this script, verify SHA256, then execute with -File
  - Does not modify Windows Firewall
'@ | Write-Host
}

if ($Help) { Show-FrpInstallHelp; exit 0 }

$libDir = Join-Path $PSScriptRoot 'lib'
foreach ($mod in @(
        'FrpPaths.ps1', 'FrpLock.ps1', 'FrpCrypto.ps1', 'FrpTls.ps1', 'FrpState.ps1', 'FrpDraft.ps1',
        'FrpConfig.ps1', 'FrpProcess.ps1', 'FrpShim.ps1', 'FrpAutostart.ps1', 'FrpBootstrap.ps1', 'FrpV24.ps1'
    )) {
    $path = Join-Path $libDir $mod
    if (-not (Test-Path -LiteralPath $path)) {
        Write-Error "ERROR: missing module $path"
        exit 1
    }
    . $path
}

# Load DPAPI assembly when present (Windows).
try { Add-Type -AssemblyName System.Security -ErrorAction SilentlyContinue | Out-Null } catch { }

# Generated one-liners and Short URL bootstraps set FRP_ZERO_TOUCH=1 and
# invoke this script with -File (never irm|iex). Honor that env so enrollment
# does not require a redundant -ZeroTouch switch.
if (-not $ZeroTouch) {
    $ztEnv = ([string]$env:FRP_ZERO_TOUCH).Trim().ToLowerInvariant()
    if ($ztEnv -eq '1' -or $ztEnv -eq 'true' -or $ztEnv -eq 'yes') {
        $ZeroTouch = $true
    }
}

if (-not $ZeroTouch) {
    Show-FrpInstallHelp
    Write-Host ''
    Write-Host 'ERROR: specify -ZeroTouch for enrollment, or use tools\drlink.cmd for lifecycle commands.'
    exit 1
}

# The installer's pre-flight already reads and can write identity state (it
# materializes the immutable client id), so it runs inside the same client
# lifecycle lock that Invoke-FrpZeroTouch holds. The lock is re-entrant per
# process; a second concurrent installer is refused here rather than racing
# the first one into a split identity.
if (-not (Enter-FrpClientLock)) {
    Write-Host 'ERROR: another Data Relay Link Agent Host lifecycle operation is already running on this host.'
    Write-Host 'FAILURE_CLASS=CLIENT_LOCK_BUSY'
    Write-Host 'Wait for it to finish, then check status with: drlink show status'
    exit 1
}
try {
    # Finding A: Zero-Touch lost-response recovery. If a prior enrollment
    # attempt on this host redeemed a ticket and/or enrolled but crashed (or the
    # HTTP response was lost) before local state was committed, a matching
    # crash-safe pending-enrollment transaction lets Invoke-FrpZeroTouch resume
    # without a Bootstrap Ticket or CA hash. Do not require them up front in
    # that case (the ticket is single-use and must not be re-supplied/re-used).
    Initialize-FrpDirectories
    $__frpResumeMachineId = Get-FrpOrCreateClientId
    $__frpResumePending = (-not (Test-FrpIsEnrolled)) -and (Test-FrpPendingEnrollMatches -MachineId $__frpResumeMachineId)
    if ($__frpResumePending -and -not $AllocatorUrl) {
        $__frpPendingPeek = Get-FrpPendingEnrollRaw
        if ($__frpPendingPeek -and $__frpPendingPeek.allocator_url) {
            $AllocatorUrl = [string]$__frpPendingPeek.allocator_url
        }
    }

    if (-not $AllocatorUrl) {
        Write-Host 'ERROR: -AllocatorUrl / FRP_ALLOCATOR_URL is required'
        exit 1
    }
    if (-not $__frpResumePending) {
        if (-not $CaSha256) {
            Write-Host 'ERROR: -CaSha256 / FRP_ALLOCATOR_CA_SHA256 is required'
            exit 1
        }
        if (-not $BootstrapTicket) {
            Write-Host 'ERROR: -BootstrapTicket / FRP_BOOTSTRAP_TICKET is required'
            exit 1
        }
    }

    $rc = Invoke-FrpZeroTouch -AllocatorUrl $AllocatorUrl -CaSha256 $CaSha256 `
        -BootstrapTicket $BootstrapTicket -Platform $Platform -ServicesJson $ServicesJson `
        -SshUser $SshUser -Hostname $Hostname -SkipStart:$SkipStart -SkipDownload:$SkipDownload
    exit [int]$rc
} finally {
    Exit-FrpClientLock
}
