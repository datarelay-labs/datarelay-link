# FrpBootstrap.ps1 — zero-touch redeem → enroll → decrypt → config → download → start.

if ((Test-Path variable:script:FrpBootstrapLoaded) -and $script:FrpBootstrapLoaded) { return }
$script:FrpBootstrapLoaded = $true

# When this file lives in windows/lib, package root is windows/
if (-not $script:FrpWindowsSrcRoot) {
    if ($PSScriptRoot) {
        $script:FrpWindowsSrcRoot = Split-Path -Parent $PSScriptRoot
    }
}

function Clear-FrpSecretEnv {
    foreach ($name in @(
            'FRP_BOOTSTRAP_TICKET', 'FRP_ENROLL_SECRET', 'FRP_ENROLLMENT_SECRET',
            'FRP_TOKEN', 'FRP_SERVER_TOKEN', 'MGMT_ENROLL_SECRET'
        )) {
        if (Test-Path "Env:$name") {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
    }
}

function Get-FrpPackagedManifest {
    param([string]$SourceRoot = $script:FrpWindowsSrcRoot)
    if (-not $SourceRoot) { return $null }
    $path = Join-Path (Split-Path -Parent $SourceRoot) 'release-manifest.json'
    if (-not (Test-Path -LiteralPath $path)) {
        $path = Join-Path $SourceRoot 'release-manifest.json'
    }
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    return (Get-Content -LiteralPath $path -Raw | ConvertFrom-Json)
}

function Get-FrpQualifiedWindowsUpdateMetadata {
    param($Manifest, [string]$Checksums, [string]$InstalledChannel)
    $entry = @($Manifest.artifacts | Where-Object {
        $_.artifact_type -ceq 'agent-installer' -and $_.platform -ceq 'windows' -and
        $_.architecture -ceq 'amd64' -and $_.filename -ceq 'bootstrap-client.ps1' -and
        $_.relative_path -ceq 'agent/bootstrap-client.ps1'
    })
    if ($Manifest.qualification_status -cne 'PASS' -or $entry.Count -ne 1 -or
        [string]$Manifest.source_head -cnotmatch '^[0-9a-f]{40}$' -or
        $entry[0].source_head -cne $Manifest.source_head -or
        [string]$entry[0].sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $Manifest.channel -cnotin @('development','preview','stable') -or
        $InstalledChannel -cnotin @('development','preview','stable') -or
        $Manifest.channel -cne $InstalledChannel -or
        [string]$Manifest.project_version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.+-]+)?$') {
        throw 'ERROR: Server-qualified Windows product manifest, release channel or immutable source is invalid.'
    }
    $digests = @()
    foreach ($line in ($Checksums -split '\r?\n')) {
        if ($line -cmatch '^([0-9a-f]{64}) [ *]agent/bootstrap-client\.ps1$') { $digests += $Matches[1] }
    }
    if ($digests.Count -ne 1 -or $digests[0] -cne $entry[0].sha256) {
        throw 'ERROR: Server-qualified Windows product manifest and SHA256SUMS disagree.'
    }
    return [pscustomobject]@{
        SourceHead = [string]$Manifest.source_head
        Channel = [string]$Manifest.channel
        ProjectVersion = [string]$Manifest.project_version
        Sha256 = [string]$entry[0].sha256
    }
}

function Invoke-FrpVerifiedWindowsBootstrapUpgrade {
    param([Parameter(Mandatory=$true)][string]$Path)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Path -Upgrade
    if ($LASTEXITCODE -ne 0) { throw "ERROR: qualified Windows product upgrade failed (exit $LASTEXITCODE)." }
}

function Invoke-FrpQualifiedWindowsProductUpdate {
    param([switch]$CheckOnly)
    if (-not (Test-FrpIsEnrolled)) { throw 'ERROR: automatic product update requires an enrolled Agent.' }
    $state = Read-FrpClientState
    $origin = Get-FrpAllocatorOrigin -AllocatorUrl ([string]$state.allocator_url)
    $installedManifest = Join-Path (Get-FrpWindowsRoot) 'release-manifest.json'
    $installed = if (Test-Path -LiteralPath $installedManifest) {
        Get-Content -LiteralPath $installedManifest -Raw | ConvertFrom-Json
    } else { $null }
    $channel = [string]$installed.channel
    $installedVersion = @{}
    if (Test-Path -LiteralPath (Get-FrpVersionPath)) {
        foreach ($line in Get-Content -LiteralPath (Get-FrpVersionPath)) {
            if ($line -match '^([^=]+)=(.*)$') { $installedVersion[$Matches[1]] = $Matches[2] }
        }
    }
    if ($installedVersion['RELEASE_CHANNEL'] -in @('development','preview','stable')) {
        if ($channel -and $channel -cne $installedVersion['RELEASE_CHANNEL']) {
            throw 'ERROR: installed Windows product release channel metadata disagrees.'
        }
        $channel = [string]$installedVersion['RELEASE_CHANNEL']
    }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('drlink-update-' + [guid]::NewGuid().ToString('N'))
    try {
        New-FrpProtectedDirectory -Path $work | Out-Null
        $manifestFile = Join-Path $work 'manifest.json'
        $sumsFile = Join-Path $work 'SHA256SUMS'
        $bootstrap = Join-Path $work 'bootstrap-client.ps1'
        Write-Host 'Downloading qualified update metadata from DRLink Server...'
        Invoke-FrpHttpsDownload -Url "$origin/artifacts/manifest.json" -DestinationPath $manifestFile
        Invoke-FrpHttpsDownload -Url "$origin/artifacts/SHA256SUMS" -DestinationPath $sumsFile
        $manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
        $target = Get-FrpQualifiedWindowsUpdateMetadata -Manifest $manifest -Checksums (Get-Content -LiteralPath $sumsFile -Raw) -InstalledChannel $channel
        Write-Host ("Data Relay Link: {0} -> {1}" -f (Get-FrpProjectVersion), $target.ProjectVersion)
        Write-Host ("Channel: {0}" -f $target.Channel)
        Write-Host ("Source HEAD: {0}" -f $target.SourceHead)
        Write-Host ("Expected SHA256: {0}" -f $target.Sha256)
        if ($CheckOnly) {
            Write-Host 'Check only. No update changes were applied.'
            return
        }
        Invoke-FrpHttpsDownload -Url "$origin/artifacts/agent/bootstrap-client.ps1" -DestinationPath $bootstrap
        if ((Get-FrpSha256HexOfFile -Path $bootstrap) -cne $target.Sha256) {
            throw 'ERROR: downloaded Windows product artifact SHA256 mismatch. No update changes were applied.'
        }
        Write-Host 'Qualified Windows product artifact verified.'
        # The existing -Upgrade installer re-verifies the outer bytes with
        # the enrolled Server, then refreshes software without enrollment.
        Invoke-FrpVerifiedWindowsBootstrapUpgrade -Path $bootstrap
        $result = Get-Content -LiteralPath (Get-FrpVersionPath) -Raw
        if ($result -notmatch ('(?m)^PROJECT_VERSION=' + [regex]::Escape($target.ProjectVersion) + '\r?$') -or
            $result -notmatch ('(?m)^SOURCE_HEAD=' + [regex]::Escape($target.SourceHead) + '\r?$') -or
            $result -notmatch ('(?m)^RELEASE_CHANNEL=' + [regex]::Escape($target.Channel) + '\r?$')) {
            throw 'ERROR: installed Windows product provenance does not match the verified target.'
        }
        Write-Host 'Product update complete. Identity, ports, services and CA trust preserved.'
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-FrpPackagedSourceHead {
    param($Manifest)
    foreach ($value in @([string]$Manifest.source_head, [string]$Manifest.git_ref)) {
        if ($value -match '^[0-9a-f]{40}$') { return $value }
    }
    return 'UNKNOWN'
}

function Confirm-FrpWindowsSourceProvenance {
    param([Parameter(Mandatory = $true)][string]$AllocatorUrl, [string]$CaPath, [switch]$VerifyOnly)
    # The generated outer bootstrap remains on disk while its child installer
    # executes. Bind its actual bytes to the Server's CA-verified manifest.
    if (-not $env:FRP_WINDOWS_BOOTSTRAP_PATH) { return }
    $digest = Get-FrpSha256HexOfFile -Path $env:FRP_WINDOWS_BOOTSTRAP_PATH
    if (-not $VerifyOnly -and $script:FrpVerifiedBootstrapDigest -ceq $digest) { return }
    $origin = Get-FrpAllocatorOrigin -AllocatorUrl $AllocatorUrl
    $manifest = if ($CaPath) {
        (Invoke-FrpHttpsJson -Method GET -Url "$origin/artifacts/manifest.json" -CaPath $CaPath) | ConvertFrom-Json
    } else {
        (Invoke-FrpHttpsJson -Method GET -Url "$origin/artifacts/manifest.json") | ConvertFrom-Json
    }
    $packaged = Get-FrpPackagedManifest
    $installerEntries = @($manifest.artifacts | Where-Object {
        $_.artifact_type -eq 'agent-installer' -and $_.platform -eq 'windows' -and
        $_.architecture -eq 'amd64' -and $_.filename -eq 'bootstrap-client.ps1'
    })
    if ($installerEntries.Count -ne 1 -or $installerEntries[0].sha256 -cne $digest -or
        $manifest.source_head -notmatch '^[0-9a-f]{40}$' -or
        $installerEntries[0].source_head -cne $manifest.source_head -or
        $manifest.channel -notin @('development','preview','stable') -or
        $manifest.qualification_status -ne 'PASS' -or -not $packaged -or
        $manifest.channel -cne $packaged.channel -or
        $manifest.project_version -cne $packaged.project_version) {
        throw 'ERROR: Windows installer source provenance does not match the qualified Server artifact. No enrollment was attempted.'
    }
    if ($VerifyOnly) { return }
    $provenance = [ordered]@{
        source_head = [string]$manifest.source_head
        content_source_head = Get-FrpPackagedSourceHead -Manifest $packaged
        channel = [string]$manifest.channel
        bootstrap_sha256 = $digest
    }
    $path = Join-Path (Get-FrpWindowsRoot) 'source-provenance.json'
    [IO.File]::WriteAllText("$path.tmp", ($provenance | ConvertTo-Json))
    Move-Item -LiteralPath "$path.tmp" -Destination $path -Force
    $script:FrpVerifiedBootstrapDigest = $digest
}

# Only a CA and its exact atomic staging names, with no enrolled/pending
# state, runtime, tasks or unknown files, are classified as an unclaimed
# Windows trust residue. This runs under the existing lifecycle lock.
function Get-FrpUnclaimedWindowsCaResidue {
    [CmdletBinding()]
    param()
    if ($script:FrpClientLockDepth -lt 1 -or [string]$script:FrpClientLockOwner -ne [string]$PID) { Write-Verbose "Residue protected: lifecycle lock not owned"; return }
    $root = Get-FrpWindowsRoot
    $dirs = @('bin','config','state','certs','logs','tools','lib','backups')
    $residue = @()
    try {
        $rootItem = Get-Item -LiteralPath $root -Force -ErrorAction Stop
        if (-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { Write-Verbose "Residue protected: unsafe product root"; return }
        foreach ($dir in (Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)) {
            if (-not $dir.PSIsContainer -or $dir.Name -notin $dirs -or ($dir.Attributes -band [IO.FileAttributes]::ReparsePoint)) { Write-Verbose "Residue protected: unexpected product-root entry $($dir.Name)"; return }
            foreach ($entry in (Get-ChildItem -LiteralPath $dir.FullName -Force -ErrorAction Stop)) {
                if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { Write-Verbose "Residue protected: reparse point $($entry.Name)"; return }
                if ($dir.Name -eq 'state') {
                    if ($entry.Name -eq 'client-id' -and -not $entry.PSIsContainer) { continue }
                    if ($entry.Name -eq 'client-manage.lock' -and $entry.PSIsContainer) {
                        $children = @(Get-ChildItem -LiteralPath $entry.FullName -Force -ErrorAction Stop)
                        if ($children.Count -eq 1 -and $children[0].Name -eq 'pid' -and
                            -not $children[0].PSIsContainer -and
                            -not ($children[0].Attributes -band [IO.FileAttributes]::ReparsePoint) -and
                            ([string](Get-Content -LiteralPath $children[0].FullName -Raw -ErrorAction Stop)).Trim() -eq [string]$PID) { continue }
                    }
                    Write-Verbose "Residue protected: unexpected state entry $($entry.Name)"
                    return
                }
                if ($dir.Name -eq 'certs' -and -not $entry.PSIsContainer -and
                    ($entry.Name -eq 'allocator-ca.crt' -or $entry.Name -cmatch '^allocator-ca\.crt\.[0-9a-f]{32}\.tmp$')) {
                    # Compare validated names inside the same certs directory, not
                    # FullName strings: native Windows can expand 8.3 path aliases.
                    $residue += $entry.Name
                    continue
                }
                Write-Verbose "Residue protected: unexpected entry in $($dir.Name): $($entry.Name)"
                return
            }
        }
        foreach ($task in @((Get-FrpAutostartTaskName), (Get-FrpLifecycleTaskName)) + @(Get-FrpAutostartLegacyTaskNames)) {
            if (Test-FrpAutostartTaskExists -TaskName $task) { Write-Verbose "Residue protected: existing product task $task"; return }
        }
        return $residue
    } catch {
        Write-Verbose ("Residue protected: classification failed: " + $_.Exception.Message)
        return
    }
}

function Repair-FrpUnclaimedWindowsCaResidue {
    param([string]$AllocatorUrl, [string]$CaSha256, [string]$BootstrapLocator)
    # Only the qualified Zero-Touch outer bundle and its pre-provisioned
    # CA authorize recovery. The ordinary pin check still rejects other
    # mismatches, including manual installations and pending transactions.
    if (-not $BootstrapLocator -or -not $CaSha256 -or
        -not $env:FRP_ALLOCATOR_CA_FILE -or -not $env:FRP_WINDOWS_BOOTSTRAP_PATH) { return }
    $before = @(Get-FrpUnclaimedWindowsCaResidue)
    if ($before.Count -eq 0) { return }
    $caName = "allocator-ca.crt"
    $certs = Get-FrpCertsDir
    $ca = Join-Path $certs $caName
    $expected = Normalize-FrpCaSha256 -Value $CaSha256
    $same = $false
    if (Test-Path -LiteralPath $ca) {
        try {
            $old = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ca)
            try { $same = (Get-FrpCertificateDerSha256 -Certificate $old) -eq $expected }
            finally { $old.Dispose() }
        } catch { }
    }
    if ($same -and $before.Count -eq 1) { return }
    $stagedName = "allocator-ca.crt." + [guid]::NewGuid().ToString('N') + '.tmp'
    $backupName = "allocator-ca.crt." + [guid]::NewGuid().ToString('N') + '.tmp'
    $staged = Join-Path $certs $stagedName
    $backup = Join-Path $certs $backupName
    try {
        Get-FrpCaCertificate -AllocatorUrl $AllocatorUrl -ExpectedSha256 $expected -DestinationPath $staged | Out-Null
        Confirm-FrpWindowsSourceProvenance -AllocatorUrl $AllocatorUrl -CaPath $staged -VerifyOnly
        $after = @(Get-FrpUnclaimedWindowsCaResidue)
        if ($after.Count -ne ($before.Count + 1) -or $stagedName -notin $after -or
            @(Compare-Object -ReferenceObject @($before | Sort-Object) -DifferenceObject @($after | Where-Object { $_ -ne $stagedName } | Sort-Object)).Count -ne 0) {
            throw 'ERROR: Windows Agent residue changed during verification'
        }
        if (Test-Path -LiteralPath $ca) {
            [IO.File]::Replace($staged, $ca, $backup)
        } else {
            [IO.File]::Move($staged, $ca)
        }
        foreach ($scratchName in @($before | Where-Object { $_ -ne $caName }) + @($backupName)) {
            # Every name originates from the classified directory or a
            # generated GUID, never from a caller or an absolute path.
            $scratch = Join-Path $certs $scratchName
            if (Test-Path -LiteralPath $scratch) {
                $item = Get-Item -LiteralPath $scratch -Force -ErrorAction Stop
                if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    throw 'ERROR: unsafe Windows Agent CA scratch path'
                }
                Remove-Item -LiteralPath $scratch -Force -ErrorAction Stop
            }
        }
        Write-Host 'Removed unclaimed Agent CA residue; continuing fresh enrollment.'
    } finally {
        if (Test-Path -LiteralPath $staged) {
            Remove-Item -LiteralPath $staged -Force -ErrorAction Stop
        }
    }
}

function Write-FrpInstalledVersion {
    param([string]$SourceRoot = $script:FrpWindowsSrcRoot, [string]$EngineSha256 = (Get-FrpWindowsAmd64Sha256))
    $packaged = Get-FrpPackagedManifest -SourceRoot $SourceRoot
    $source = 'UNKNOWN'
    $content = 'UNKNOWN'
    $channel = 'UNKNOWN'
    $project = Get-FrpProjectVersion
    if ($packaged) {
        $project = [string]$packaged.project_version
        $content = Get-FrpPackagedSourceHead -Manifest $packaged
        $channel = [string]$packaged.channel
    }
    $path = Join-Path (Get-FrpWindowsRoot) 'source-provenance.json'
    if (Test-Path -LiteralPath $path) {
        $p = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
        if ($p.content_source_head -ceq $content -and $p.channel -ceq $channel -and
            $p.source_head -match '^[0-9a-f]{40}$') { $source = [string]$p.source_head }
    }
    $text = @("PROJECT_VERSION=$project", "FRP_VERSION=$(Get-FrpUpstreamVersion)",
        "FRP_SHA256_WINDOWS_AMD64=$EngineSha256", 'ROLE=AgentHost',
        "RELEASE_CHANNEL=$channel", "SOURCE_HEAD=$source", "CONTENT_SOURCE_HEAD=$content") -join "`n"
    [IO.File]::WriteAllText((Get-FrpVersionPath) + '.tmp', $text + "`n")
    Move-Item -LiteralPath ((Get-FrpVersionPath) + '.tmp') -Destination (Get-FrpVersionPath) -Force
}

function Expand-FrpZipSafe {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$DestinationDir,
        [Parameter(Mandatory = $true)][string]$EntryName
    )
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue | Out-Null
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $target = $null
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName -replace '\\', '/'
            if ($name.EndsWith('/')) { continue }
            $leaf = Split-Path -Leaf $name
            if ($leaf -ieq $EntryName) {
                # Zip-slip: reject absolute / parent traversal
                if ($name.Contains('..') -or $name.StartsWith('/') -or $name -match '^[A-Za-z]:') {
                    throw 'ERROR: unsafe zip entry rejected'
                }
                $target = $entry
                break
            }
        }
        if (-not $target) {
            throw ("ERROR: {0} not found in FRP archive" -f $EntryName)
        }
        if (-not (Test-Path -LiteralPath $DestinationDir)) {
            New-Item -ItemType Directory -Path $DestinationDir -Force | Out-Null
        }
        $outPath = Join-Path $DestinationDir $EntryName
        $tmp = "$outPath.tmp"
        $fs = [System.IO.File]::Create($tmp)
        try {
            $es = $target.Open()
            try { $es.CopyTo($fs) } finally { $es.Dispose() }
        } finally { $fs.Dispose() }
        Move-Item -LiteralPath $tmp -Destination $outPath -Force
        return $outPath
    } finally {
        $zip.Dispose()
    }
}

function Install-FrpWindowsBinary {
    param(
        [string]$DownloadUrl,
        [string]$ExpectedSha256
    )
    Initialize-FrpDirectories
    if (-not $DownloadUrl) { $DownloadUrl = Get-FrpWindowsAmd64Url }
    if (-not $ExpectedSha256) { $ExpectedSha256 = Get-FrpWindowsAmd64Sha256 }
    $expected = $ExpectedSha256.Trim().ToLowerInvariant()
    if ($DownloadUrl -notmatch '^https://') {
        throw 'ERROR: FRP download URL must be https://'
    }
    if ($DownloadUrl -match 'github\.com/fatedier' -or $DownloadUrl -match '/frp/releases/download/') {
        $ver = Get-FrpUpstreamVersion
        throw @"
ERROR:
Required qualified artifact is not available on this DRLink Server.

Required:
  Data Relay Link Agent 2.4.0
  FRP $ver
  windows/amd64

Reinstall or update the DRLink Server package containing
the required qualified artifacts.

No changes were applied.
"@
    }

    $binDir = Get-FrpBinDir
    $dest = Get-FrpFrpcPath
    if ((Test-Path -LiteralPath $dest) -and $env:FRP_WINDOWS_SKIP_DOWNLOAD -eq '1') {
        return $dest
    }

    $tmpZip = Join-Path ([System.IO.Path]::GetTempPath()) ("frp-win-" + [guid]::NewGuid().ToString('N') + '.zip')
    try {
        Write-Host 'Downloading FRP Windows amd64 package...'
        Invoke-FrpHttpsDownload -Url $DownloadUrl -DestinationPath $tmpZip -TimeoutSec 180
        $actual = Get-FrpSha256HexOfFile -Path $tmpZip
        if ($actual -ne $expected) {
            throw 'ERROR: FRP package SHA256 mismatch'
        }
        Expand-FrpZipSafe -ZipPath $tmpZip -DestinationDir $binDir -EntryName 'frpc.exe' | Out-Null
        if (-not (Test-Path -LiteralPath $dest)) {
            throw 'ERROR: frpc.exe extract failed'
        }
        Write-FrpInstalledVersion -EngineSha256 $expected
        return $dest
    } finally {
        Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
    }
}

function New-FrpEntryClaim {
    param([string]$Action,[string]$Locator,[string]$MachineId,[string]$Hostname,
          [string]$PrivatePem,[string]$PublicPem,[string]$Nonce)
    if (-not $Nonce) { $Nonce = New-FrpNonce }
    $payload = @{
        locator = $Locator; machine_id = $MachineId; hostname = $Hostname
        public_key = $PublicPem; nonce = $Nonce
        timestamp = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    }
    $message = @{} + $payload
    $message['domain'] = 'drlink-entry-v1'
    $message['action'] = $Action
    $payload['signature'] = Protect-FrpSignMessage -PrivatePem $PrivatePem -Message (Get-FrpCanonicalJson -Object $message)
    return (Get-FrpCanonicalJson -Object $payload)
}

function Invoke-FrpEntryRegistration {
    param([string]$AllocatorUrl,[string]$Locator,[string]$MachineId,
      [string]$Hostname,[string]$PrivatePem,[string]$PublicPem)
    if ($Locator -cnotmatch '^[A-Za-z0-9_-]{8}$') { throw 'ERROR: invalid Bootstrap locator' }
    $der = [Convert]::FromBase64String(($PublicPem -replace '-----[^-]+-----','' -replace '\s',''))
    $fingerprint = Get-FrpSha256Hex -Bytes $der
    Write-Host 'Registering Agent identity ...'
    $origin = Get-FrpAllocatorOrigin -AllocatorUrl $AllocatorUrl
    $body = New-FrpEntryClaim -Action request -Locator $Locator -MachineId $MachineId -Hostname $Hostname -PrivatePem $PrivatePem -PublicPem $PublicPem
    $data = ConvertFrom-FrpJson -Json (Invoke-FrpHttpsJson -Method POST -Url "$origin/bootstrap/entry/request" -Body $body)
    if ($data.error -or $data.fingerprint -cne $fingerprint -or
        $data.status -cne 'approved' -or $data.challenge -cnotmatch '^[0-9a-f]{64}$') {
        throw 'ERROR: invalid registration response'
    }
    $body = New-FrpEntryClaim -Action redeem -Locator $Locator -MachineId $MachineId -Hostname $Hostname -PrivatePem $PrivatePem -PublicPem $PublicPem -Nonce $data.challenge
    $result = ConvertFrom-FrpJson -Json (Invoke-FrpHttpsJson -Method POST -Url "$origin/bootstrap/entry/redeem" -Body $body)
    $code = [string]$result.enrollment_code
    if ($result.error -or $code -cnotmatch '^[0-9a-f]{16}\.[0-9a-f]{64}$' -or
        -not (Test-FrpObjectHasProperty -Object $result -Name 'services') -or $null -eq $result.services) {
        throw 'ERROR: invalid enrollment response'
    }
    $parts = $code.Split('.', 2)
    return @{EnrollmentId=$parts[0]; EnrollmentSecret=$parts[1]; Services=@($result.services)}
}

function Invoke-FrpBootstrapRedeem {
    param(
        [Parameter(Mandatory = $true)][string]$AllocatorUrl,
        [Parameter(Mandatory = $true)][string]$Ticket,
        [Parameter(Mandatory = $true)][string]$MachineId,
        [Parameter(Mandatory = $true)][string]$Hostname
    )
    $origin = Get-FrpAllocatorOrigin -AllocatorUrl $AllocatorUrl
    $url = "$origin/bootstrap/redeem"
    $payload = [ordered]@{
        ticket     = $Ticket
        machine_id = $MachineId
        hostname   = $Hostname
    }
    # Compact JSON (no spaces) matching Linux client
    $body = Get-FrpCanonicalJson -Object $payload
    $respText = Invoke-FrpHttpsJson -Method POST -Url $url -Body $body
    $data = ConvertFrom-FrpJson -Json $respText
    if ($data.error) {
        $cls = [string]$data.error_class
        if (-not $cls) { $cls = 'BOOTSTRAP_REDEEM_FAILED' }
        throw ("ERROR: {0} [{1}]" -f [string]$data.error, $cls)
    }
    $code = [string]$data.enrollment_code
    if (-not $code -or -not $code.Contains('.')) {
        throw 'ERROR: bootstrap response is missing enrollment data'
    }
    $parts = $code.Split('.', 2)
    if (-not (Test-FrpObjectHasProperty -Object $data -Name 'services') -or $null -eq $data.services) {
        throw 'ERROR: bootstrap response is missing services'
    }
    # An empty list is valid: it is a management-only ticket.
    $services = @($data.services)
    return @{
        EnrollmentId     = $parts[0]
        EnrollmentSecret = $parts[1]
        Services         = $services
    }
}

function Invoke-FrpEnroll {
    param(
        [Parameter(Mandatory = $true)][string]$AllocatorUrl,
        [Parameter(Mandatory = $true)][string]$EnrollmentId,
        [Parameter(Mandatory = $true)][string]$EnrollmentSecret,
        [Parameter(Mandatory = $true)][string]$MachineId,
        [Parameter(Mandatory = $true)][string]$Hostname,
        [Parameter(Mandatory = $true)]$Services,
        [string]$PublicPem,
        [string]$OperationId
    )
    $enrollServices = Get-FrpEnrollServiceList -Services $Services
    $payload = [ordered]@{
        machine_id = $MachineId
        hostname   = $Hostname
        services   = @($enrollServices)
    }
    if ($PublicPem) {
        $payload['mgmt_pubkey'] = $PublicPem
        $payload['mgmt_alg'] = 'ecdsa-p256-sha256'
    }
    if (-not [string]::IsNullOrWhiteSpace($OperationId)) {
        $payload['operation_id'] = ([string]$OperationId).Trim().ToLowerInvariant()
    }
    $body = Get-FrpCanonicalJson -Object $payload
    $ts = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    $sig = Get-FrpEnrollmentSignature -Secret $EnrollmentSecret -Timestamp ([string]$ts) -Body $body
    $headers = @{
        'X-Enrollment-ID' = $EnrollmentId
        'X-Timestamp'     = [string]$ts
        'X-Signature'     = $sig
    }
    if ($PublicPem -and (Test-Path -LiteralPath (Get-FrpIdentityKeyPath))) {
        $privatePem = Read-FrpIdentityKey
        $digest = Get-FrpSha256Hex -Bytes ([Text.Encoding]::UTF8.GetBytes($body))
        $message = "drlink-entry-enroll-v1`n$EnrollmentId`n$ts`n$digest"
        $headers['X-Entry-Key-Proof'] = Protect-FrpSignMessage -PrivatePem $privatePem -Message $message
    }
    $respText = Invoke-FrpHttpsJson -Method POST -Url $AllocatorUrl -Body $body -Headers $headers
    $data = ConvertFrom-FrpJson -Json $respText
    if ($data.error) {
        throw ("ERROR: allocator rejected enrollment: {0}" -f [string]$data.error)
    }
    # Verify response HMAC over payload without response_hmac field
    $received = [string]$data.response_hmac
    $copy = ConvertTo-FrpPlainObject $data
    if ($copy.ContainsKey('response_hmac')) { $copy.Remove('response_hmac') }
    $canonical = Get-FrpCanonicalJson -Object $copy
    $expected = Get-FrpHmacHex -Secret $EnrollmentSecret -Message $canonical
    if (-not $received -or -not (Test-FrpFixedTimeEquals -Left $received -Right $expected -IgnoreCase)) {
        throw 'ERROR: allocator response HMAC verification failed'
    }
    if (-not $data.token_ciphertext) {
        throw 'ERROR: allocator response is missing token_ciphertext'
    }
    $transport = [string]$data.frp_transport
    if (-not $transport) { $transport = 'tcp' }
    $transport = $transport.Trim().ToLowerInvariant()
    if ($transport -ne 'tcp' -and $transport -ne 'wss') {
        throw 'ERROR: allocator returned an unsupported FRP transport'
    }
    $propNames = @($data.PSObject.Properties.Name)
    return @{
        FrpServer       = [string]$data.frp_server
        FrpServerPort   = [int]$data.frp_server_port
        FrpTransport    = $transport
        TokenCiphertext = [string]$data.token_ciphertext
        Services        = @($data.services)
        MgmtStatus      = [string]$data.mgmt_status
        PublicHostname  = [string]$data.public_hostname
        PublicHostnamePresent = ($propNames -contains 'public_hostname')
    }
}

function Get-FrpDefaultServices {
    param(
        [string]$Platform = 'windows',
        [string]$ServicesJson
    )
    if ($ServicesJson) {
        $parsed = $ServicesJson | ConvertFrom-Json
        return @($parsed)
    }
    if ($Platform -eq 'windows') {
        return @(
            [pscustomobject]@{
                id         = 'rdp'
                name       = 'RDP'
                preset     = 'rdp'
                protocol   = 'tcp'
                local_ip   = '127.0.0.1'
                local_port = 3389
                enabled    = $true
            }
        )
    }
    $ssh = [pscustomobject]@{
        id         = 'ssh'
        name       = 'SSH'
        preset     = 'ssh'
        protocol   = 'tcp'
        local_ip   = '127.0.0.1'
        local_port = 22
        enabled    = $true
    }
    return @($ssh)
}

function Complete-FrpZeroTouchPostEnroll {
    param(
        [switch]$SkipStart,
        [switch]$SkipDownload,
        [object]$Services
    )
    if ($env:FRP_WINDOWS_BOOTSTRAP_PATH) {
        $client = Read-FrpClientState
        Confirm-FrpWindowsSourceProvenance -AllocatorUrl ([string]$client.allocator_url)
    }
    $enabledCount = Get-FrpEnabledServiceCount -Services $Services
    if (-not $Services) {
        try {
            $st = Read-FrpClientState
            $Services = $st.services
            $enabledCount = Get-FrpEnabledServiceCount -Services $Services
            if ($st.management_only -eq $true) { $enabledCount = 0 }
        } catch { }
    }

    Set-FrpInstallStatus -Status 'enrolled_incomplete'

    if ($env:FRP_WINDOWS_FAIL_AFTER_ENROLL -eq '1') {
        throw 'ERROR: simulated failure after enroll (FRP_WINDOWS_FAIL_AFTER_ENROLL=1)'
    }

    if (-not $SkipDownload) {
        if ($env:FRP_WINDOWS_SKIP_DOWNLOAD -eq '1') {
            Write-Host 'Skipping FRP download (FRP_WINDOWS_SKIP_DOWNLOAD=1)'
        } else {
            Install-FrpWindowsBinary | Out-Null
        }
    }

    # Persist product CLI + lib modules into ProgramData so a new PowerShell
    # process can run after the bootstrap temp tree is removed.
    if ($script:FrpWindowsSrcRoot) {
        Initialize-FrpDirectories
        $srcClient = Join-Path $script:FrpWindowsSrcRoot 'tools/FrpClient.ps1'
        $srcCmd = Join-Path $script:FrpWindowsSrcRoot 'tools/frp-client.cmd'
        $srcDrlink = Join-Path $script:FrpWindowsSrcRoot 'tools/drlink.cmd'
        $srcAuto = Join-Path $script:FrpWindowsSrcRoot 'tools/frp-autostart.cmd'
        $srcLifecycleWorker = Join-Path $script:FrpWindowsSrcRoot 'tools/FrpLifecycleWorker.ps1'
        if (Test-Path -LiteralPath $srcClient) {
            Copy-Item -LiteralPath $srcClient -Destination (Join-Path (Get-FrpToolsDir) 'FrpClient.ps1') -Force
        }
        if (Test-Path -LiteralPath $srcCmd) {
            Copy-Item -LiteralPath $srcCmd -Destination (Join-Path (Get-FrpToolsDir) 'frp-client.cmd') -Force
        }
        if (Test-Path -LiteralPath $srcDrlink) {
            Copy-Item -LiteralPath $srcDrlink -Destination (Join-Path (Get-FrpToolsDir) 'drlink.cmd') -Force
        }
        if (Test-Path -LiteralPath $srcAuto) {
            Copy-Item -LiteralPath $srcAuto -Destination (Join-Path (Get-FrpToolsDir) 'frp-autostart.cmd') -Force
        }
        if (Test-Path -LiteralPath $srcLifecycleWorker) {
            Copy-Item -LiteralPath $srcLifecycleWorker -Destination (Join-Path (Get-FrpToolsDir) 'FrpLifecycleWorker.ps1') -Force
        }
        $srcLib = Join-Path $script:FrpWindowsSrcRoot 'lib'
        if (Test-Path -LiteralPath $srcLib) {
            $destLib = Get-FrpLibDir
            Get-ChildItem -LiteralPath $srcLib -Filter '*.ps1' -File -ErrorAction SilentlyContinue | ForEach-Object {
                Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destLib $_.Name) -Force
            }
        }
    }

    $manifestSource = Join-Path (Split-Path -Parent $script:FrpWindowsSrcRoot) 'release-manifest.json'
    if (Test-Path -LiteralPath $manifestSource) {
        Copy-Item -LiteralPath $manifestSource -Destination (Join-Path (Get-FrpWindowsRoot) 'release-manifest.json') -Force
    }
    Write-FrpInstalledVersion

    # Documented UX is a bare `drlink ...` from any shell, so the installed
    # tools directory goes on the system PATH. Never fatal: the client is
    # still fully usable through the explicit launcher path.
    if ($env:FRP_WINDOWS_SKIP_PATH_SHIM -eq '1') {
        Write-Host 'Skipping PATH registration (FRP_WINDOWS_SKIP_PATH_SHIM=1)'
    } else {
        try {
            Install-FrpCommandShim | Out-Null
        } catch {
            Write-Host ("WARNING: could not put the product CLI on the system PATH: {0}" -f $_.Exception.Message)
            Write-Host ("Run the product CLI explicitly as: {0}" -f (Get-FrpShimPath))
        }
    }

    if ($enabledCount -le 0) {
        try {
            Install-FrpLifecycleTask | Out-Null
            if (-not (Test-FrpLifecycleTaskHealthy)) {
                throw 'ERROR: lifecycle task was not registered as a SYSTEM boot worker'
            }
        } catch {
            Write-Host ("ERROR: failed to register Agent lifecycle worker: {0}" -f $_.Exception.Message)
            return 1
        }
        Write-Host 'Management-only enrollment: no public services; skipping frpc start.'
        Set-FrpInstallStatus -Status 'management_only'
        Write-Host ''
        Write-Host 'Enrollment complete (management-only). Use drlink system info for details.'
        Write-Host 'ENROLL ONCE / RUN MANY TIMES: later starts use existing identity and ports.'
        return 0
    }

    if ($env:FRP_WINDOWS_FAIL_BEFORE_START -eq '1') {
        throw 'ERROR: simulated failure before start (FRP_WINDOWS_FAIL_BEFORE_START=1)'
    }

    try {
        Install-FrpLifecycleTask | Out-Null
        if (-not (Test-FrpLifecycleTaskHealthy)) {
            throw 'ERROR: lifecycle task was not registered as a SYSTEM boot worker'
        }
    } catch {
        Write-Host ("ERROR: failed to register Agent lifecycle worker: {0}" -f $_.Exception.Message)
        return 1
    }

    # Register product autostart so frpc survives reboot without an
    # interactive login. Required whenever this client has enabled public
    # services. Management-only installs return above and never reach here.
    if ($env:FRP_WINDOWS_SKIP_AUTOSTART -eq '1') {
        Write-Host 'Skipping autostart registration (FRP_WINDOWS_SKIP_AUTOSTART=1)'
    } else {
        try {
            Install-FrpAutostartTask | Out-Null
            if (-not (Test-FrpAutostartHealthy)) {
                throw 'ERROR: autostart task was not registered as a SYSTEM boot task'
            }
            Write-Host ("Registered autostart ({0}): frpc starts at system boot (SYSTEM, no login required)." -f (Get-FrpAutostartTaskName))
        } catch {
            try { Uninstall-FrpLifecycleTask | Out-Null } catch { }
            Write-Host ("ERROR: failed to register autostart: {0}" -f $_.Exception.Message)
            Write-Host 'ERROR: enabled public services require reboot persistence without login. This Agent Host is not fully installed.'
            return 1
        }
    }

    if (-not $SkipStart) {
        Start-FrpClient | Out-Null
    }

    Set-FrpInstallStatus -Status 'installed'
    Write-Host ''
    Write-Host 'Enrollment complete. Use drlink system info for connection details.'
    Write-Host 'ENROLL ONCE / RUN MANY TIMES: later starts use existing identity and ports.'
    return 0
}

function Invoke-FrpEnrollServices {
    <#
    .SYNOPSIS
      Identity-authenticated apply request (P2.3 management identity, not an
      Enrollment Code). Mirrors the Unix identity-auth branch of
      frp_enroll_services: ECDSA-P256-signed canonical request with
      X-Mgmt-Auth / X-Mgmt-Nonce / X-Mgmt-Signature, response verified with
      the client's stored MAC key. The FRP auth token is never rotated here;
      identity-auth responses must not contain secret material.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$AllocatorUrl,
        [Parameter(Mandatory = $true)][string]$MachineId,
        [Parameter(Mandatory = $true)][string]$Hostname,
        [Parameter(Mandatory = $true)]$Services
    )
    if ($AllocatorUrl -notmatch '^https://') {
        throw 'ERROR: allocator URL must be https://'
    }
    if (-not (Test-FrpIsEnrolled)) {
        throw "ERROR: this client does not have a usable management identity."
    }

    $payload = [ordered]@{
        machine_id = $MachineId
        hostname   = $Hostname
        services   = @($Services)
    }
    $body = Get-FrpCanonicalJson -Object $payload
    $ts = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    $nonce = New-FrpNonce
    $message = Get-FrpSignedMessage -MachineId $MachineId -Body $body -Timestamp $ts -Nonce $nonce -Op 'enroll'
    $privatePem = Read-FrpIdentityKey
    $signature = Protect-FrpSignMessage -PrivatePem $privatePem -Message $message
    $privatePem = $null

    $headers = @{
        'X-Mgmt-Auth'      = '1'
        'X-Timestamp'      = [string]$ts
        'X-Mgmt-Nonce'     = $nonce
        'X-Mgmt-Signature' = $signature
    }
    $respText = Invoke-FrpHttpsJson -Method POST -Url $AllocatorUrl -Body $body -Headers $headers
    $data = ConvertFrom-FrpJson -Json $respText

    if ($data.error) {
        $err = [string]$data.error
        $lowered = $err.ToLowerInvariant()
        if ($lowered -match 'revoked' -or $lowered -match 'does not have a management identity' -or $lowered -match 'unknown client identity') {
            throw ("ERROR: this client's management identity has been revoked. Create a new Enrollment Code on the server, then re-enroll this client. [{0}]" -f $err)
        }
        throw ("ERROR: allocator rejected the change: {0}" -f $err)
    }

    $received = [string]$data.response_hmac
    $copy = ConvertTo-FrpPlainObject $data
    if ($copy.ContainsKey('response_hmac')) { $copy.Remove('response_hmac') }
    $canonical = Get-FrpCanonicalJson -Object $copy
    $mac = Read-FrpIdentityMac
    $expected = Get-FrpHmacHex -Secret $mac -Message $canonical
    if (-not $received -or -not (Test-FrpFixedTimeEquals -Left $received -Right $expected -IgnoreCase)) {
        throw 'ERROR: allocator response HMAC verification failed'
    }
    $propNames = @($data.PSObject.Properties.Name)
    if ($propNames -contains 'ssh_port' -or $propNames -contains 'https_port') {
        throw 'ERROR: allocator returned a legacy SSH/HTTPS response'
    }
    if ($propNames -contains 'token_ciphertext' -or $propNames -contains 'mgmt_mac_key' -or $data.token) {
        throw 'ERROR: allocator returned unexpected secret material'
    }
    if ($propNames -notcontains 'services') {
        throw 'ERROR: allocator response is missing services'
    }
    $transport = [string]$data.frp_transport
    if (-not $transport) { $transport = 'tcp' }
    $transport = $transport.Trim().ToLowerInvariant()
    if ($transport -ne 'tcp' -and $transport -ne 'wss') {
        throw 'ERROR: allocator returned an unsupported FRP transport'
    }
    return @{
        FrpServer      = [string]$data.frp_server
        FrpServerPort  = [int]$data.frp_server_port
        FrpTransport   = $transport
        Services       = @($data.services)
        PublicHostname = [string]$data.public_hostname
        PublicHostnamePresent = ($propNames -contains 'public_hostname')
    }
}

function Invoke-FrpCompensatePreviousServices {
    <#
    .SYNOPSIS
      Re-apply the pre-mutation service set to the allocator after local
      activation failed. Mirrors Unix frp_compensate_previous.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$AllocatorUrl,
        [Parameter(Mandatory = $true)][string]$MachineId,
        [Parameter(Mandatory = $true)][string]$Hostname,
        $Services
    )
    if ($env:FRP_WINDOWS_FAIL_SERVER_COMPENSATE -eq '1') {
        throw 'ERROR: simulated server compensation failure (FRP_WINDOWS_FAIL_SERVER_COMPENSATE=1)'
    }
    Write-Host 'Attempting server registry compensation with the previous service set ...'
    $null = Invoke-FrpEnrollServices -AllocatorUrl $AllocatorUrl -MachineId $MachineId `
        -Hostname $Hostname -Services $Services
}

function Invoke-FrpApplyLocalMetadata {
    <#
    .SYNOPSIS
      Apply display-name-only draft changes without contacting the allocator.
    #>
    param($Current, $DraftMap)
    $curMap = ConvertTo-FrpServiceMap -Services $Current.services
    foreach ($sid in @($DraftMap.Keys)) {
        $item = $DraftMap[$sid]
        if ($curMap.Contains($sid) -and $null -ne $curMap[$sid].remote_port -and [string]$curMap[$sid].remote_port -ne '') {
            if ($null -eq $item['remote_port'] -or [string]$item['remote_port'] -eq '') {
                $item['remote_port'] = [int]$curMap[$sid].remote_port
                $DraftMap[$sid] = $item
            }
        }
    }
    $saveArgs = @{
        AllocatorUrl  = [string]$Current.allocator_url
        FrpServer     = [string]$Current.frp_server
        FrpServerPort = [int]$Current.frp_server_port
        Hostname      = [string]$Current.hostname
        MachineId     = [string]$Current.machine_id
        HostId        = [string]$Current.host_id
        Services      = $DraftMap
        Transport     = $(if ($Current.frp_transport) { [string]$Current.frp_transport } else { 'tcp' })
        InstallStatus = $(if ($Current.install_status) { [string]$Current.install_status } else { 'installed' })
    }
    if (Test-FrpObjectHasProperty -Object $Current -Name 'public_hostname') {
        $saveArgs['PublicHostname'] = [string]$Current.public_hostname
    }
    Save-FrpClientState @saveArgs | Out-Null
    Remove-Item -LiteralPath (Get-FrpDraftPath) -Force -ErrorAction SilentlyContinue
    Write-Host 'Applied local changes.'
    Write-Host 'Allocator contacted : NO'
    Write-Host 'frpc restarted      : NO'
    return 0
}

function Invoke-FrpClientApplyDraft {
    <#
    .SYNOPSIS
      Apply pending draft service changes: identity-auth request to the
      allocator, merge allocated ports, regenerate frpc.toml + client-state.json,
      restart drlink-client if it was running. Existing FRP token is reused (identity
      auth never rotates it). On local activation failure: restore local files
      and compensate the server reservation (Unix-equivalent transaction).
    #>
    if (-not (Enter-FrpClientLock)) { return 1 }
    try {
        return (Invoke-FrpClientApplyDraftLocked)
    } finally {
        Exit-FrpClientLock
    }
}

function Invoke-FrpClientApplyDraftLocked {
    if (-not (Test-FrpIsEnrolled)) {
        Write-Host 'ERROR: not enrolled; run install-client.ps1 -ZeroTouch first'
        return 1
    }

    $draftPath = Get-FrpDraftPath
    if (-not (Test-Path -LiteralPath $draftPath)) {
        Write-Host 'No pending changes.'
        return 0
    }

    $current = Read-FrpClientState
    $draftState = Read-FrpDraftState
    $changeClass = Get-FrpStateChangeClass -Current $current -Draft $draftState
    if ($changeClass -eq 'none') {
        Remove-Item -LiteralPath $draftPath -Force -ErrorAction SilentlyContinue
        Write-Host 'No pending changes.'
        return 0
    }

    $draftMap = ConvertTo-FrpServiceMap -Services $draftState.services

    if ($changeClass -eq 'local') {
        return (Invoke-FrpApplyLocalMetadata -Current $current -DraftMap $draftMap)
    }

    try {
        $null = Invoke-FrpReconcileReleasedServices
    } catch {
        Write-Host 'ERROR: cannot apply because client synchronization failed.'
        $msg = [string]$_.Exception.Message
        if ($msg) { Write-Host $msg }
        return 1
    }

    if (-not (Test-Path -LiteralPath $draftPath)) {
        Write-Host 'No pending changes.'
        return 0
    }
    $current = Read-FrpClientState
    $draftState = Read-FrpDraftState
    $changeClass = Get-FrpStateChangeClass -Current $current -Draft $draftState
    if ($changeClass -eq 'none') {
        Remove-Item -LiteralPath $draftPath -Force -ErrorAction SilentlyContinue
        Write-Host 'No pending changes.'
        return 0
    }
    if ($changeClass -eq 'local') {
        $draftMap = ConvertTo-FrpServiceMap -Services $draftState.services
        return (Invoke-FrpApplyLocalMetadata -Current $current -DraftMap $draftMap)
    }
    $draftMap = ConvertTo-FrpServiceMap -Services $draftState.services

    $machineId = [string]$current.machine_id
    $hostnameValue = [string]$current.hostname
    $allocatorUrl = [string]$current.allocator_url
    $hostId = Get-FrpExpectedHostId -Hostname $hostnameValue -MachineId $machineId
    $priorEnrollList = @(Get-FrpEnrollServiceList -Services $current.services)

    $enrollList = Get-FrpEnrollServiceList -Services $draftMap

    Write-Host ''
    Write-Host 'Authenticating client...'
    Write-Host 'Applying configuration...'

    $serverMutated = $false
    try {
        $result = Invoke-FrpEnrollServices -AllocatorUrl $allocatorUrl -MachineId $machineId `
            -Hostname $hostnameValue -Services $enrollList
        $serverMutated = $true
    } catch {
        Write-Host ("ERROR: apply failed: {0}" -f $_.Exception.Message)
        Write-Host 'The server was not changed; local configuration was not changed.'
        Write-Host 'LOCAL_ROLLBACK=N/A'
        Write-Host 'SERVER_ROLLBACK=N/A'
        return 1
    }

    $emitApplyRollback = {
        param([string]$LocalRollback, [string]$ServerRollback)
        Write-Host ("LOCAL_ROLLBACK={0}" -f $LocalRollback)
        Write-Host ("SERVER_ROLLBACK={0}" -f $ServerRollback)
        if ($ServerRollback -eq 'FAIL') {
            Write-Host 'RECOVERY_REQUIRED=YES'
            Write-Host 'WARNING: server registry may not match local configuration. Reconcile by editing and applying again.'
        }
    }

    foreach ($sid in @($draftMap.Keys)) {
        $item = $draftMap[$sid]
        if ($item['enabled'] -eq $false) { continue }
        $alloc = @($result.Services) | Where-Object { [string]$_.id -eq $sid } | Select-Object -First 1
        if ($null -eq $alloc) {
            Write-Host ("ERROR: allocator response is missing service {0}" -f $sid)
            $localRollback = 'N/A'
            $serverRollback = 'FAIL'
            try {
                Invoke-FrpCompensatePreviousServices -AllocatorUrl $allocatorUrl -MachineId $machineId `
                    -Hostname $hostnameValue -Services $priorEnrollList
                $serverRollback = 'PASS'
            } catch {
                $serverRollback = 'FAIL'
            }
            & $emitApplyRollback $localRollback $serverRollback
            return 1
        }
        $item['remote_port'] = [int]$alloc.remote_port
        $draftMap[$sid] = $item
    }

    $existingToken = Get-FrpTokenFromToml
    if (-not $existingToken) {
        Write-Host 'ERROR: existing FRP client configuration is missing the FRP token; re-enroll this client.'
        $serverRollback = 'FAIL'
        try {
            Invoke-FrpCompensatePreviousServices -AllocatorUrl $allocatorUrl -MachineId $machineId `
                -Hostname $hostnameValue -Services $priorEnrollList
            $serverRollback = 'PASS'
        } catch {
            $serverRollback = 'FAIL'
        }
        & $emitApplyRollback 'N/A' $serverRollback
        return 1
    }

    $transport = [string]$result.FrpTransport
    if (-not $transport) { $transport = [string]$current.frp_transport }
    if (-not $transport) { $transport = 'tcp' }

    Initialize-FrpDirectories
    # The snapshot includes frpc.toml, which carries the plaintext FRP token,
    # so the backup directory and every copy get the product-enforced ACL.
    $backupRoot = New-FrpBackupRoot -Prefix 'apply'
    $snapshotMap = [ordered]@{
        'frpc.toml'         = (Get-FrpTomlPath)
        'client-state.json' = (Get-FrpStatePath)
    }
    foreach ($name in @($snapshotMap.Keys)) {
        $src = $snapshotMap[$name]
        if (Test-Path -LiteralPath $src) {
            Copy-FrpProtectedFile -Source $src -Destination (Join-Path $backupRoot $name) | Out-Null
        }
    }

    $wasRunning = (Get-FrpClientStatus).Running
    $enabledAny = $false
    foreach ($sid in $draftMap.Keys) {
        if ($draftMap[$sid]['enabled'] -ne $false) { $enabledAny = $true; break }
    }
    $saveHostname = @{}
    if ($result.ContainsKey('PublicHostnamePresent') -and $result.PublicHostnamePresent) {
        $saveHostname['PublicHostname'] = [string]$result.PublicHostname
    } elseif (Test-FrpObjectHasProperty -Object $current -Name 'public_hostname') {
        $saveHostname['PublicHostname'] = [string]$current.public_hostname
    }

    try {
        if ($env:FRP_WINDOWS_FAIL_APPLY_ACTIVATE -eq '1') {
            throw 'ERROR: simulated local activation failure (FRP_WINDOWS_FAIL_APPLY_ACTIVATE=1)'
        }
        New-FrpClientToml -ServerAddr $result.FrpServer -ServerPort $result.FrpServerPort -Token $existingToken `
            -HostId $hostId -Services $draftMap -Transport $transport | Out-Null

        Save-FrpClientState -AllocatorUrl $allocatorUrl -FrpServer $result.FrpServer -FrpServerPort $result.FrpServerPort `
            -Hostname $hostnameValue -MachineId $machineId -HostId $hostId -Services $draftMap -Transport $transport `
            -InstallStatus $(if ($enabledAny) { 'installed' } else { 'management_only' }) @saveHostname | Out-Null

        if ($enabledAny) {
            if ($wasRunning) { Stop-FrpClient | Out-Null }
            # Start when leaving zero-service/management-only, but only if the
            # binary is present (unit tests apply without downloading frpc.exe).
            if (Test-Path -LiteralPath (Get-FrpFrpcPath)) {
                Start-FrpClient | Out-Null
            }
            Install-FrpAutostartTask | Out-Null
            if (-not (Test-FrpAutostartHealthy)) {
                throw 'ERROR: autostart task was not registered as a SYSTEM boot task'
            }
        } else {
            if ($wasRunning) { Stop-FrpClient | Out-Null }
            # Zero enabled services: management-only — no reboot autostart.
            Uninstall-FrpAutostartTask | Out-Null
        }
    } catch {
        Write-Host ("ERROR: failed to activate new configuration: {0}" -f $_.Exception.Message)
        Write-Host 'Restoring previous local configuration...'
        $localRollback = 'FAIL'
        try {
            foreach ($name in @($snapshotMap.Keys)) {
                $bak = Join-Path $backupRoot $name
                $dest = $snapshotMap[$name]
                if (Test-Path -LiteralPath $bak) { Copy-Item -LiteralPath $bak -Destination $dest -Force }
            }
            if ($wasRunning) { Start-FrpClient | Out-Null }
            $localRollback = 'PASS'
        } catch {
            $localRollback = 'FAIL'
        }
        $serverRollback = 'FAIL'
        if ($serverMutated) {
            try {
                Invoke-FrpCompensatePreviousServices -AllocatorUrl $allocatorUrl -MachineId $machineId `
                    -Hostname $hostnameValue -Services $priorEnrollList
                $serverRollback = 'PASS'
            } catch {
                $serverRollback = 'FAIL'
            }
        } else {
            $serverRollback = 'N/A'
        }
        & $emitApplyRollback $localRollback $serverRollback
        return 1
    }

    Remove-Item -LiteralPath $draftPath -Force -ErrorAction SilentlyContinue
    Write-Host 'Applied pending changes.'
    Write-Host 'LOCAL_ROLLBACK=N/A'
    Write-Host 'SERVER_ROLLBACK=N/A'
    return 0
}

function Invoke-FrpApplyReconcileRuntime {
    <#
    .SYNOPSIS
      After accepted server reconciliation, converge frpc.toml and runtime.
      Server release is not undone on local runtime failure.
    #>
    param(
        [bool]$DroppedEnabled,
        [bool]$DroppedAny = $false,
        [bool]$HostnameChanged = $false
    )
    if (-not $DroppedEnabled -and -not $DroppedAny -and -not $HostnameChanged) { return }
    if ($DroppedAny -or $DroppedEnabled) {
        if ($env:FRP_CLIENT_HOOK_TOML_REGEN -eq '1') {
            Write-Host 'ERROR: simulated TOML regeneration failure'
            Write-Host 'FAILURE_CLASS=CONFIG_GENERATION_FAILED'
            Write-Host 'RECOVERY_REQUIRED=YES'
            throw 'ERROR: failed to regenerate frpc.toml after server reconciliation.'
        }
        $toml = Get-FrpTomlPath
        if (Test-Path -LiteralPath $toml) {
            $token = Get-FrpTokenFromToml
            if (-not $token) {
                Write-Host 'ERROR: cannot regenerate frpc.toml; FRP token is unavailable.'
                Write-Host 'FAILURE_CLASS=CONFIG_GENERATION_FAILED'
                Write-Host 'RECOVERY_REQUIRED=YES'
                throw 'ERROR: cannot regenerate frpc.toml; FRP token is unavailable.'
            }
            $state = Read-FrpClientState
            $map = ConvertTo-FrpServiceMap -Services $state.services
            $transport = [string]$state.frp_transport
            if (-not $transport) { $transport = 'tcp' }
            New-FrpClientToml -ServerAddr ([string]$state.frp_server) -ServerPort ([int]$state.frp_server_port) `
                -Token $token -HostId ([string]$state.host_id) -Services $map -Transport $transport | Out-Null
        }
    }
    if ($env:FRP_CLIENT_HOOK_ACCESS_REGEN -eq '1') {
        Write-Host 'ERROR: simulated access-info regeneration failure'
        Write-Host 'FAILURE_CLASS=CONFIG_GENERATION_FAILED'
        Write-Host 'RECOVERY_REQUIRED=YES'
        throw 'ERROR: failed to regenerate access-info.txt after server reconciliation.'
    }
    if (-not $DroppedEnabled) { return }
    if ($env:FRP_CLIENT_HOOK_RESTART_FAIL -eq '1') {
        Write-Host 'ERROR: simulated service restart failure'
        Write-Host 'FAILURE_CLASS=FRPC_RESTART_FAILED'
        Write-Host 'RECOVERY_REQUIRED=YES'
        throw 'ERROR: failed to restart drlink-client after server reconciliation.'
    }
    $state = Read-FrpClientState
    $map = ConvertTo-FrpServiceMap -Services $state.services
    $enabledAny = $false
    foreach ($sid in $map.Keys) {
        if ($map[$sid].enabled -ne $false) { $enabledAny = $true; break }
    }
    if (-not $enabledAny) {
        Set-FrpInstallStatus -Status 'management_only'
        Stop-FrpClient | Out-Null
        Uninstall-FrpAutostartTask | Out-Null
        return
    }
    $wasRunning = (Get-FrpClientStatus).Running
    if ($wasRunning) {
        Stop-FrpClient | Out-Null
        Start-FrpClient | Out-Null
    }
}

function Invoke-FrpReconcileReleasedServices {
    <#
    .SYNOPSIS
      Reconcile local services and public_hostname against the server registry.
      Returns $true on SUCCESS (change applied), $false on NO_CHANGE.
      Throws on FAILURE. Strict (explicit sync) treats missing identity as failure.
    #>
    param([switch]$Strict)
    if (-not (Test-Path -LiteralPath (Get-FrpStatePath))) { return $false }

    if ($env:FRP_CLIENT_HOOK_RECONCILE_UNREACHABLE -eq '1') {
        Write-Host 'ERROR: allocator unreachable'
        Write-Host 'FAILURE_CLASS=ALLOCATOR_UNREACHABLE'
        throw 'ERROR: allocator unreachable'
    }
    if ($env:FRP_CLIENT_HOOK_RECONCILE_HMAC -eq '1') {
        Write-Host 'ERROR: allocator response HMAC verification failed'
        Write-Host 'FAILURE_CLASS=HMAC_VERIFICATION_FAILED'
        throw 'ERROR: allocator response HMAC verification failed'
    }
    if ($env:FRP_CLIENT_HOOK_RECONCILE_MALFORMED -eq '1') {
        Write-Host 'ERROR: allocator returned a malformed reconcile response'
        Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
        throw 'ERROR: allocator returned a malformed reconcile response'
    }
    if ($env:FRP_CLIENT_HOOK_RECONCILE_STATE -eq '1') {
        Write-Host 'ERROR: failed to update local client state'
        Write-Host 'FAILURE_CLASS=STATE_WRITE_FAILED'
        throw 'ERROR: failed to update local client state'
    }

    if ($env:FRP_SKIP_CONNECTIVITY_CHECK -eq '1' -and -not $env:FRP_CLIENT_RECONCILE_REGISTRY_IDS -and -not $env:FRP_CLIENT_RECONCILE_RESPONSE) {
        return $false
    }

    $state = Read-FrpClientState
    $map = ConvertTo-FrpServiceMap -Services $state.services
    $registryIds = $null
    $hostnamePresent = $false
    $hostnameValue = ''

    if ($env:FRP_CLIENT_RECONCILE_RESPONSE) {
        try {
            $data = ConvertFrom-FrpJson -Json $env:FRP_CLIENT_RECONCILE_RESPONSE
        } catch {
            Write-Host 'ERROR: allocator returned a malformed reconcile response'
            Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
            throw 'ERROR: allocator returned a malformed reconcile response'
        }
        if ($data.error) {
            Write-Host ("ERROR: allocator rejected the reconcile request: {0}" -f [string]$data.error)
            Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
            throw ("ERROR: allocator rejected the reconcile request: {0}" -f [string]$data.error)
        }
        $mac = $null
        try { $mac = Read-FrpIdentityMac } catch { $mac = $null }
        if (-not $mac) {
            Write-Host 'ERROR: management response key is missing'
            Write-Host 'FAILURE_CLASS=MANAGEMENT_IDENTITY'
            throw 'ERROR: management response key is missing'
        }
        $received = [string]$data.response_hmac
        $copy = ConvertTo-FrpPlainObject $data
        if ($copy.ContainsKey('response_hmac')) { $copy.Remove('response_hmac') }
        $canonical = Get-FrpCanonicalJson -Object $copy
        $expected = Get-FrpHmacHex -Secret $mac -Message $canonical
        if (-not $received -or -not (Test-FrpFixedTimeEquals -Left $received -Right $expected -IgnoreCase)) {
            Write-Host 'ERROR: allocator response HMAC verification failed'
            Write-Host 'FAILURE_CLASS=HMAC_VERIFICATION_FAILED'
            throw 'ERROR: allocator response HMAC verification failed'
        }
        if (-not (Test-FrpObjectHasProperty -Object $data -Name 'registry_service_ids')) {
            Write-Host 'ERROR: allocator returned a malformed reconcile response'
            Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
            throw 'ERROR: allocator returned a malformed reconcile response'
        }
        $registryIds = @()
        if ($null -ne $data.registry_service_ids) {
            $registryIds = @($data.registry_service_ids | ForEach-Object { [string]$_ })
        }
        if (Test-FrpObjectHasProperty -Object $data -Name 'public_hostname') {
            $hostnamePresent = $true
            $hostnameValue = [string]$data.public_hostname
        }
    } elseif ($env:FRP_CLIENT_RECONCILE_REGISTRY_IDS) {
        $parsedIds = $env:FRP_CLIENT_RECONCILE_REGISTRY_IDS | ConvertFrom-Json
        if ($null -eq $parsedIds) {
            $registryIds = @()
        } elseif ($parsedIds -is [string]) {
            $registryIds = @([string]$parsedIds)
        } else {
            $registryIds = @($parsedIds | ForEach-Object { [string]$_ })
        }
        if ($env:FRP_CLIENT_RECONCILE_PUBLIC_HOSTNAME_PRESENT -eq '1') {
            $hostnamePresent = $true
            $hostnameValue = [string]$env:FRP_CLIENT_RECONCILE_PUBLIC_HOSTNAME
        }
    } else {
        if (-not (Test-FrpIsEnrolled)) {
            if ($Strict) {
                Write-Host 'ERROR: this client does not have a usable management identity'
                Write-Host 'FAILURE_CLASS=MANAGEMENT_IDENTITY'
                throw 'ERROR: this client does not have a usable management identity'
            }
            return $false
        }
        $allocatorUrl = [string]$state.allocator_url
        $machineId = [string]$state.machine_id
        $hostnameLocal = [string]$state.hostname
        if (-not $allocatorUrl -or -not $machineId) {
            Write-Host 'ERROR: client state is missing allocator URL or machine ID'
            Write-Host 'FAILURE_CLASS=MANAGEMENT_IDENTITY'
            throw 'ERROR: client state is missing allocator URL or machine ID'
        }
        if ($allocatorUrl -notmatch '^https://') {
            Write-Host 'ERROR: allocator URL must be https://'
            Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
            throw 'ERROR: allocator URL must be https://'
        }

        $payload = [ordered]@{
            machine_id = $machineId
            hostname   = $hostnameLocal
        }
        $body = Get-FrpCanonicalJson -Object $payload
        $ts = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
        $nonce = New-FrpNonce
        $message = Get-FrpSignedMessage -MachineId $machineId -Body $body -Timestamp $ts -Nonce $nonce -Op 'enroll'
        $privatePem = Read-FrpIdentityKey
        $signature = Protect-FrpSignMessage -PrivatePem $privatePem -Message $message
        $privatePem = $null
        $headers = @{
            'X-Mgmt-Auth'      = '1'
            'X-Mgmt-Reconcile' = '1'
            'X-Timestamp'      = [string]$ts
            'X-Mgmt-Nonce'     = $nonce
            'X-Mgmt-Signature' = $signature
        }
        try {
            $respText = Invoke-FrpHttpsJson -Method POST -Url $allocatorUrl -Body $body -Headers $headers
            $data = ConvertFrom-FrpJson -Json $respText
        } catch {
            Write-Host 'ERROR: allocator unreachable'
            Write-Host 'FAILURE_CLASS=ALLOCATOR_UNREACHABLE'
            throw 'ERROR: allocator unreachable'
        }
        if ($data.error) {
            Write-Host ("ERROR: allocator rejected the reconcile request: {0}" -f [string]$data.error)
            Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
            throw ("ERROR: allocator rejected the reconcile request: {0}" -f [string]$data.error)
        }
        $received = [string]$data.response_hmac
        $copy = ConvertTo-FrpPlainObject $data
        if ($copy.ContainsKey('response_hmac')) { $copy.Remove('response_hmac') }
        $canonical = Get-FrpCanonicalJson -Object $copy
        $mac = Read-FrpIdentityMac
        $expected = Get-FrpHmacHex -Secret $mac -Message $canonical
        if (-not $received -or -not (Test-FrpFixedTimeEquals -Left $received -Right $expected -IgnoreCase)) {
            Write-Host 'ERROR: allocator response HMAC verification failed'
            Write-Host 'FAILURE_CLASS=HMAC_VERIFICATION_FAILED'
            throw 'ERROR: allocator response HMAC verification failed'
        }
        if (-not (Test-FrpObjectHasProperty -Object $data -Name 'registry_service_ids')) {
            Write-Host 'ERROR: allocator returned a malformed reconcile response'
            Write-Host 'FAILURE_CLASS=INVALID_RESPONSE'
            throw 'ERROR: allocator returned a malformed reconcile response'
        }
        $registryIds = @()
        if ($null -ne $data.registry_service_ids) {
            $registryIds = @($data.registry_service_ids | ForEach-Object { [string]$_ })
        }
        if (Test-FrpObjectHasProperty -Object $data -Name 'public_hostname') {
            $hostnamePresent = $true
            $hostnameValue = [string]$data.public_hostname
        }
    }

    $idSet = @{}
    foreach ($rid in $registryIds) {
        if ($null -ne $rid -and [string]$rid -ne '') { $idSet[[string]$rid] = $true }
    }

    $droppedEnabled = $false
    $droppedAny = $false
    $committedIds = @{}
    foreach ($sid in @($map.Keys)) { $committedIds[[string]$sid] = $true }
    $newMap = [ordered]@{}
    foreach ($sid in @($map.Keys)) {
        if ($idSet.ContainsKey([string]$sid)) {
            $newMap[$sid] = $map[$sid]
            continue
        }
        $droppedAny = $true
        if ($map[$sid].enabled -ne $false) { $droppedEnabled = $true }
    }

    $oldAlias = ''
    if (Test-FrpObjectHasProperty -Object $state -Name 'public_hostname') {
        $oldAlias = ([string]$state.public_hostname).Trim()
    }
    $hostnameChanged = $false
    $saveHostname = @{}
    if ($hostnamePresent) {
        $alias = ([string]$hostnameValue).Trim()
        $saveHostname['PublicHostname'] = $alias
        if ($alias -ne $oldAlias) { $hostnameChanged = $true }
    }

    if (-not $droppedAny -and -not $hostnameChanged) { return $false }

    $enabledLeft = 0
    foreach ($sid in $newMap.Keys) {
        if ($newMap[$sid].enabled -ne $false) { $enabledLeft++ }
    }
    $installStatus = [string]$state.install_status
    if (-not $installStatus) { $installStatus = 'installed' }
    if ($enabledLeft -eq 0) { $installStatus = 'management_only' }

    Save-FrpClientState -AllocatorUrl ([string]$state.allocator_url) -FrpServer ([string]$state.frp_server) `
        -FrpServerPort ([int]$state.frp_server_port) -Hostname ([string]$state.hostname) `
        -MachineId ([string]$state.machine_id) -HostId ([string]$state.host_id) `
        -Services $newMap -Transport ([string]$state.frp_transport) `
        -InstallStatus $installStatus @saveHostname | Out-Null

    $draftPath = Get-FrpDraftPath
    if (Test-Path -LiteralPath $draftPath) {
        try {
            $draft = Read-FrpDraftState
            $draftMap = ConvertTo-FrpServiceMap -Services $draft.services
            $draftNew = [ordered]@{}
            foreach ($sid in @($draftMap.Keys)) {
                $sidS = [string]$sid
                if ($idSet.ContainsKey($sidS) -or -not $committedIds.ContainsKey($sidS)) {
                    $draftNew[$sid] = $draftMap[$sid]
                }
            }
            if ($draftNew.Count -eq 0) {
                Remove-Item -LiteralPath $draftPath -Force -ErrorAction SilentlyContinue
            } else {
                Save-FrpDraftServiceMap -ServiceMap $draftNew | Out-Null
            }
        } catch { }
    }

    Invoke-FrpApplyReconcileRuntime -DroppedEnabled $droppedEnabled -DroppedAny $droppedAny -HostnameChanged $hostnameChanged
    return $true
}

function Invoke-FrpAgentLifecycle {
    <#
    .SYNOPSIS
      Report signed Agent lifecycle presence to the v2.4 management API.
    #>
    param([ValidateSet('connected','disconnected')][string]$State = 'connected')
    if (-not (Test-FrpIsEnrolled)) { throw 'ERROR: Agent Host is not enrolled' }
    $client = Read-FrpClientState
    $machineId = [string]$client.machine_id
    $allocatorUrl = [string]$client.allocator_url
    if (-not $machineId -or -not $allocatorUrl) { throw 'ERROR: Agent Host lifecycle state is incomplete' }
    $uri = [Uri]$allocatorUrl
    $path = '/v1/agent-lifecycle'
    $url = ('{0}://{1}{2}' -f $uri.Scheme, $uri.Authority, $path)
    $body = Get-FrpCanonicalJson -Object ([ordered]@{ state = $State })
    $ts = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    $nonce = New-FrpNonce
    $message = Get-FrpSignedMessage -MachineId $machineId -Body $body -Timestamp $ts -Nonce $nonce `
        -Op 'agent.lifecycle' -Method 'POST' -Path $path
    $privatePem = Read-FrpIdentityKey
    $signature = Protect-FrpSignMessage -PrivatePem $privatePem -Message $message
    $privatePem = $null
    $headers = @{
        'X-Machine-Id'      = $machineId
        'X-Mgmt-Auth'       = '1'
        'X-Timestamp'       = [string]$ts
        'X-Mgmt-Nonce'      = $nonce
        'X-Mgmt-Signature'  = $signature
    }
    $respText = Invoke-FrpHttpsJson -Method POST -Url $url -Body $body -Headers $headers
    $data = ConvertFrom-FrpJson -Json $respText
    if ($data.error) { throw ("ERROR: lifecycle report rejected: {0}" -f [string]$data.error) }
    $received = [string]$data.response_hmac
    $copy = ConvertTo-FrpPlainObject $data
    if ($copy.ContainsKey('response_hmac')) { $copy.Remove('response_hmac') }
    $expected = Get-FrpHmacHex -Secret (Read-FrpIdentityMac) -Message (Get-FrpCanonicalJson -Object $copy)
    if (-not $received -or -not (Test-FrpFixedTimeEquals -Left $received -Right $expected -IgnoreCase)) {
        throw 'ERROR: lifecycle response HMAC verification failed'
    }
    return $copy
}

function Invoke-FrpClientSync {
    <#
    .SYNOPSIS
      Explicit mutation: reconcile local services against server releases.
    #>
    if (-not (Enter-FrpClientLock)) { return 1 }
    try {
        if (-not (Test-FrpIsEnrolled)) {
            Write-Host 'ERROR: not enrolled; run install-client.ps1 -ZeroTouch first'
            Write-Host 'FAILURE_CLASS=MANAGEMENT_IDENTITY'
            return 1
        }
        try {
            $null = Invoke-FrpReconcileReleasedServices -Strict
        } catch {
            Write-Host ("ERROR: sync failed: {0}" -f $_.Exception.Message)
            return 1
        }
        Write-Host 'Client sync complete.'
        return 0
    } finally {
        Exit-FrpClientLock
    }
}

function Invoke-FrpZeroTouch {
    <#
    .NOTES
      AllocatorUrl / CaSha256 / BootstrapTicket are intentionally NOT
      [Parameter(Mandatory)]: PowerShell's mandatory-parameter binder rejects
      an explicit empty string, but a Finding A crash-safe resume (see
      Test-FrpPendingEnrollMatches below) legitimately needs to call this
      with CaSha256/BootstrapTicket omitted or blank (the CA is already
      pinned to disk and the Bootstrap Ticket must not be re-supplied /
      re-used). Presence is validated explicitly in the body instead, with a
      resume-aware exception for CaSha256/BootstrapTicket.

      Platform / ServicesJson are accepted for installer CLI
      compatibility but do not select services: the Bootstrap Ticket defines
      the authorized service scope and the allocator enforces it at /enroll.

      The entire mutable transaction runs under the client lifecycle lock,
      taken before the first identity/state write (the client id) and held
      through completion, so two concurrent installers cannot interleave and
      produce a split identity. The lock is re-entrant per process, so the
      installer may take it first for its own pre-flight.
    #>
    param(
        [string]$AllocatorUrl,
        [string]$CaSha256,
        [string]$BootstrapTicket,
        [string]$BootstrapLocator = $env:FRP_BOOTSTRAP_LOCATOR,
        [string]$Platform = 'windows',
        [string]$ServicesJson,
        [string]$Hostname,
        [switch]$SkipStart,
        [switch]$SkipDownload
    )

    if (-not (Enter-FrpClientLock)) {
        Write-Host 'ERROR: another Data Relay Link Agent Host lifecycle operation is already running on this host.'
        Write-Host 'FAILURE_CLASS=CLIENT_LOCK_BUSY'
        Write-Host 'Wait for it to finish, then check status with: drlink show status'
        return 1
    }
    try {
        if (Test-FrpIsEnrolled) {
            if (Test-FrpCanResumeInstall) {
                Write-Host 'Resuming incomplete install (same identity and ports; ticket not re-redeemed)...'
                return (Complete-FrpZeroTouchPostEnroll -SkipStart:$SkipStart -SkipDownload:$SkipDownload)
            }
            if (Test-FrpIsInstallComplete) {
                Write-Host 'ERROR: this machine is already enrolled.'
                Write-Host 'ENROLL ONCE: refuse re-ticket path. Use: drlink system resume'
                Write-Host 'To replace this install, uninstall locally first (server reservations are preserved).'
                return 2
            }
            # Legacy enrolled installs without install_status: treat as complete / refuse re-ticket
            Write-Host 'ERROR: this machine is already enrolled.'
            Write-Host 'ENROLL ONCE: refuse re-ticket path. Use: drlink system resume'
            Write-Host 'To replace this install, uninstall locally first (server reservations are preserved).'
            return 2
        }

        # Finding A: Zero-Touch lost-response recovery. Compute the machine
        # id before requiring CA/ticket args (it is deterministic and
        # independent of them) so a lost /bootstrap/redeem or /enroll
        # response can be recovered by resuming from a local crash-safe
        # pending-enrollment transaction instead of re-redeeming a
        # single-use Bootstrap Ticket.
        Initialize-FrpDirectories
        $machineId = Get-FrpOrCreateClientId
        if (-not $Hostname) {
            $Hostname = $env:COMPUTERNAME
            if (-not $Hostname) { $Hostname = [System.Net.Dns]::GetHostName() }
        }
        $Hostname = ([string]$Hostname).Trim()

        $resumePending = $false
        $pending = $null
        if (Test-FrpPendingEnrollMatches -MachineId $machineId) {
            $resumePending = $true
            $pending = Read-FrpPendingEnroll
            if (-not $AllocatorUrl) { $AllocatorUrl = $pending.AllocatorUrl }
        }

        if ($AllocatorUrl -notmatch '^https://') {
            throw 'ERROR: plain HTTP allocator URL is not supported; HTTPS is required'
        }
        if (-not $resumePending) {
            if ([string]::IsNullOrWhiteSpace($CaSha256)) {
                throw 'ERROR: zero-touch setup requires FRP_ALLOCATOR_CA_SHA256 / -CaSha256'
            }
            if ([string]::IsNullOrWhiteSpace($BootstrapTicket) -and [string]::IsNullOrWhiteSpace($BootstrapLocator)) {
                throw 'ERROR: Bootstrap locator is missing'
            }
        }

        $caPath = Get-FrpAllocatorCaPath
        if ($resumePending -and (Test-Path -LiteralPath $caPath)) {
            # Already pinned by the earlier (crashed) attempt; no CA hash is
            # required to resume.
        } else {
            if (-not $resumePending) {
                Repair-FrpUnclaimedWindowsCaResidue -AllocatorUrl $AllocatorUrl -CaSha256 $CaSha256 -BootstrapLocator $BootstrapLocator
            }
            Write-Host 'Bootstrapping allocator CA (pin verify)...'
            Get-FrpCaCertificate -AllocatorUrl $AllocatorUrl -ExpectedSha256 $CaSha256 | Out-Null
        }

        Confirm-FrpWindowsSourceProvenance -AllocatorUrl $AllocatorUrl

        $enrollmentId = $null
        $enrollmentSecret = $null
        $services = $null
        $publicPem = $null
        $operationId = $null

        if ($resumePending) {
            Write-Host 'A previous enrollment did not finish (response lost or interrupted).'
            Write-Host 'Resuming from local crash-safe recovery state; the Bootstrap Ticket is not reused.'
            $enrollmentId = $pending.EnrollmentId
            $enrollmentSecret = $pending.EnrollmentSecret
            $operationId = [string]$pending.OperationId
            if ([string]::IsNullOrWhiteSpace($enrollmentSecret)) {
                throw 'ERROR: local recovery state is present but unusable. Create a new Enrollment Code and re-enroll this Agent Host.'
            }
            $services = @($pending.Services)
            # Identity was generated and saved to disk before the pending
            # record moved to phase=redeemed; reuse it (a fresh keypair would
            # not match what the allocator may have already bound on an
            # "enrolled" exact replay).
            if (-not (Test-Path -LiteralPath (Get-FrpIdentityPubPath))) {
                throw 'ERROR: local recovery state is present but the management identity is missing. Create a new Enrollment Code and re-enroll this Agent Host.'
            }
            $publicPem = [System.IO.File]::ReadAllText((Get-FrpIdentityPubPath))
        } else {
            if ($BootstrapLocator) {
                if (Test-Path -LiteralPath (Get-FrpIdentityKeyPath)) {
                    $privatePem = Read-FrpIdentityKey
                    $publicPem = Get-FrpPublicKeyPem -PrivatePem $privatePem
                } else {
                    $id = New-FrpEcdsaIdentity
                    $privatePem = $id.PrivatePem
                    $publicPem = $id.PublicPem
                    Save-FrpIdentityKey -PrivatePem $privatePem | Out-Null
                }
                Save-FrpIdentityPublic -PublicPem $publicPem | Out-Null
                $redeem = Invoke-FrpEntryRegistration -AllocatorUrl $AllocatorUrl -Locator $BootstrapLocator -MachineId $machineId -Hostname $Hostname -PrivatePem $privatePem -PublicPem $publicPem
            } else {
                Write-Host 'Redeeming bootstrap ticket...'
                $redeem = Invoke-FrpBootstrapRedeem -AllocatorUrl $AllocatorUrl -Ticket $BootstrapTicket `
                    -MachineId $machineId -Hostname $Hostname
            }

            # Ticket redeem is authoritative and the allocator enforces that
            # scope at /enroll. Local input (-ServicesJson / FRP_SERVICES_JSON)
            # must never widen it, including for a management-only (empty)
            # ticket. Get-FrpDefaultServices stays for the explicit local
            # guided UX only.
            $services = @($redeem.Services)
            if (-not [string]::IsNullOrWhiteSpace($ServicesJson)) {
                Write-Host 'NOTE: local service input is ignored; the setup command defines the authorized services.'
            }

            if (-not $BootstrapLocator) {
                Write-Host 'Generating management identity...'
                $id = New-FrpEcdsaIdentity
                Save-FrpIdentityKey -PrivatePem $id.PrivatePem | Out-Null
                Save-FrpIdentityPublic -PublicPem $id.PublicPem | Out-Null
                $publicPem = $id.PublicPem
            }

            $enrollmentId = $redeem.EnrollmentId
            $enrollmentSecret = $redeem.EnrollmentSecret
            $operationId = [guid]::NewGuid().ToString('N').ToLowerInvariant()
        }

        $enrollResult = $null
        if ($resumePending -and [string]$pending.Phase -eq 'enrolled' -and $pending.EnrollMeta -and @($pending.AllocatedServices).Count -gt 0) {
            # The server-committed /enroll response was cached locally before
            # the prior crash; finish the local commit without another
            # network round trip or ticket/enrollment-code reuse.
            Write-Host 'Reusing the previously completed enrollment response...'
            $meta = $pending.EnrollMeta
            $transport = [string]$meta.frp_transport
            if (-not $transport) { $transport = 'tcp' }
            $enrollResult = @{
                FrpServer       = [string]$meta.frp_server
                FrpServerPort   = [int]$meta.frp_server_port
                FrpTransport    = $transport
                TokenCiphertext = [string]$meta.token_ciphertext
                Services        = @($pending.AllocatedServices)
                PublicHostname  = [string]$meta.public_hostname
                PublicHostnamePresent = (Test-FrpObjectHasProperty -Object $meta -Name 'public_hostname')
            }
        } else {
            # Persist the enrollment secret and exact request now, before
            # calling /enroll, so a crash after the server commits (but
            # before the response is received or written) can be recovered
            # by an exact replay instead of requiring a new Enrollment Code.
            Save-FrpPendingEnroll -Phase 'redeemed' -MachineId $machineId -Hostname $Hostname `
                -AllocatorUrl $AllocatorUrl -EnrollmentId $enrollmentId -EnrollmentSecret $enrollmentSecret `
                -Services $services -OperationId $operationId | Out-Null

            Write-Host 'Enrolling with allocator...'
            $enrollResult = Invoke-FrpEnroll -AllocatorUrl $AllocatorUrl `
                -EnrollmentId $enrollmentId -EnrollmentSecret $enrollmentSecret `
                -MachineId $machineId -Hostname $Hostname -Services $services -PublicPem $publicPem `
                -OperationId $operationId

            $enrollMeta = @{
                frp_server       = $enrollResult.FrpServer
                frp_server_port  = $enrollResult.FrpServerPort
                frp_transport    = $enrollResult.FrpTransport
                token_ciphertext = $enrollResult.TokenCiphertext
            }
            if ($enrollResult.ContainsKey('PublicHostnamePresent') -and $enrollResult.PublicHostnamePresent) {
                $enrollMeta['public_hostname'] = [string]$enrollResult.PublicHostname
            }
            Save-FrpPendingEnroll -Phase 'enrolled' -MachineId $machineId -Hostname $Hostname `
                -AllocatorUrl $AllocatorUrl -EnrollmentId $enrollmentId -EnrollmentSecret $enrollmentSecret `
                -Services $services -OperationId $operationId -EnrollMeta $enrollMeta -AllocatedServices $enrollResult.Services | Out-Null

            if ($env:FRP_WINDOWS_HOOK_CRASH_AFTER_ENROLL -eq '1') {
                # Test-only: simulate a crash/lost response after the
                # allocator has committed the enrollment and the response
                # was cached locally, but before any further local commit
                # step runs.
                throw 'ERROR: simulated crash after enrollment commit (FRP_WINDOWS_HOOK_CRASH_AFTER_ENROLL=1)'
            }
        }

        $token = Unprotect-FrpTokenPbkdf2 -Ciphertext $enrollResult.TokenCiphertext -Secret $enrollmentSecret
        $mac = Get-FrpDerivedMacKey -Secret $enrollmentSecret -MachineId $machineId
        Save-FrpIdentityMac -MacKeyHex $mac | Out-Null

        $merged = Merge-FrpAllocatedPorts -LocalServices $services -AllocatedList $enrollResult.Services
        # Must match Linux HOST_ID / Access Control expected_host_id so proxies map.
        $hostId = Get-FrpExpectedHostId -Hostname $Hostname -MachineId $machineId

        $saveHostname = @{}
        if ($enrollResult.ContainsKey('PublicHostnamePresent') -and $enrollResult.PublicHostnamePresent) {
            $saveHostname['PublicHostname'] = [string]$enrollResult.PublicHostname
        }
        Save-FrpClientState -AllocatorUrl $AllocatorUrl -FrpServer $enrollResult.FrpServer `
            -FrpServerPort $enrollResult.FrpServerPort -Hostname $Hostname -MachineId $machineId `
            -HostId $hostId -Services $merged -Transport $enrollResult.FrpTransport `
            -InstallStatus 'enrolled_incomplete' @saveHostname | Out-Null

        New-FrpClientToml -ServerAddr $enrollResult.FrpServer -ServerPort $enrollResult.FrpServerPort `
            -Token $token -HostId $hostId -Services $merged -Transport $enrollResult.FrpTransport | Out-Null

        # Wipe plaintext token from local variable ASAP
        $token = $null

        # Local state (client-state.json + frpc.toml + management identity,
        # all written above) is now committed. The crash-safe recovery
        # transaction is no longer needed; clear it so it is never replayed
        # against a future, unrelated Enrollment Code.
        Clear-FrpPendingEnroll

        return (Complete-FrpZeroTouchPostEnroll -SkipStart:$SkipStart -SkipDownload:$SkipDownload -Services $merged)
    } finally {
        Clear-FrpSecretEnv
        Exit-FrpClientLock
    }
}
