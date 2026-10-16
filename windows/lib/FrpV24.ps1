# FrpV24.ps1 — canonical v2.4 Windows Agent public surface.
# Windows keeps its native process implementation, while public state and
# management operations follow the shared Remote Service / Bundle contract.
if ((Test-Path variable:script:FrpV24Loaded) -and $script:FrpV24Loaded) { return }
$script:FrpV24Loaded = $true

function Get-FrpV24MgmtBaseUrl {
    if ($env:DRLINK_MGMT_URL) { return ([string]$env:DRLINK_MGMT_URL).TrimEnd('/') }
    if (-not (Test-Path -LiteralPath (Get-FrpStatePath))) { return $null }
    $state = Read-FrpClientState
    foreach ($name in @('mgmt_url','management_url','allocator_url','allocator_public_url')) {
        if (-not (Test-FrpObjectHasProperty -Object $state -Name $name)) { continue }
        $value = ([string]$state.$name).Trim()
        if (-not $value) { continue }
        try {
            $u = [Uri]$value
            return ('{0}://{1}' -f $u.Scheme, $u.Authority)
        } catch {
            return $value.TrimEnd('/')
        }
    }
    return $null
}
function Get-FrpV24MgmtOperation {
    param([string]$Method, [string]$Path)
    $m = ([string]$Method).ToUpperInvariant()
    if ($m -eq 'GET' -and $Path -eq '/v1/catalog') { return 'catalog.read' }
    if ($m -eq 'POST' -and $Path -eq '/v1/remote-services') { return 'remote-service.set' }
    if ($m -eq 'POST' -and $Path -eq '/v1/remote-services-status') { return 'remote-service.status' }
    if ($m -eq 'POST' -and $Path -eq '/v1/agent-lifecycle') { return 'agent.lifecycle' }
    if ($m -eq 'DELETE' -and $Path -match '^/v1/remote-services/[^/]+$') { return 'remote-service.delete' }
    throw 'ERROR: unsupported management operation'
}

function Get-FrpV24FixtureResponse {
    param([string]$Method, [string]$Path, $Body)
    $root = [string]$env:FRP_WINDOWS_V24_FIXTURE_DIR
    if (-not $root) { return $null }
    if ($env:FRP_WINDOWS_V24_FIXTURE_OFFLINE -eq '1') {
        throw 'ERROR: allocator request failed: simulated Server offline'
    }
    if ($Method -eq 'GET' -and $Path -eq '/v1/catalog') {
        $raw = Get-Content -LiteralPath (Join-Path $root 'catalog.json') -Raw
        return ($raw | ConvertFrom-Json)
    }
    if ($Method -eq 'DELETE') {
        return [pscustomobject]@{ status = 'DELETED'; name = [Uri]::UnescapeDataString(($Path -split '/')[-1]) }
    }
    if ($Method -eq 'POST' -and $Path -eq '/v1/remote-services') {
        $port = 6001
        if ($Body.preserve_endpoint_port) { $port = [int]$Body.preserve_endpoint_port }
        return [pscustomobject]@{
            name = [string]$Body.name
            destination = [string]$Body.destination
            destination_client_id = $Body.destination_client_id
            service = [string]$Body.service
            enabled = [bool]$Body.enabled
            status = $(if ([bool]$Body.enabled) { 'DEGRADED' } else { 'DISABLED' })
            endpoint_host = 'fixture.example.test'
            endpoint_port = $port
            pool_class = [string]$Body.pool_class
            pending_allocation = 0
            reason = $(if ([bool]$Body.enabled) { 'Runtime activation pending.' } else { '' })
            runtime_verified = $false
            target_host = [string]$Body.target_host
            target_port = [int]$Body.target_port
            target_mode = [string]$Body.target_mode
        }
    }
    throw 'ERROR: unsupported v2.4 fixture request'
}
function Invoke-FrpV24MgmtRequest {
    param([string]$Method, [string]$Path, $Body = $null)
    $fixture = Get-FrpV24FixtureResponse -Method $Method -Path $Path -Body $Body
    if ($null -ne $fixture) { return $fixture }
    if (-not (Test-FrpIsEnrolled)) { throw 'ERROR: Agent is not enrolled' }
    $base = Get-FrpV24MgmtBaseUrl
    if (-not $base) { throw 'ERROR: Server management URL is not configured' }
    $state = Read-FrpClientState
    $machineId = [string]$state.machine_id
    if (-not $machineId) { throw 'ERROR: management identity is incomplete' }
    $bodyText = ''
    if ($null -ne $Body) { $bodyText = Get-FrpCanonicalJson -Object $Body }
    $ts = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())
    $nonce = New-FrpNonce
    $op = Get-FrpV24MgmtOperation -Method $Method -Path $Path
    $message = Get-FrpSignedMessage -MachineId $machineId -Body $bodyText -Timestamp $ts -Nonce $nonce -Op $op -Method $Method -Path $Path
    $privatePem = Read-FrpIdentityKey
    $signature = Protect-FrpSignMessage -PrivatePem $privatePem -Message $message
    $privatePem = $null
    $headers = @{
        'X-Machine-Id' = $machineId
        'X-Mgmt-Auth' = '1'
        'X-Timestamp' = [string]$ts
        'X-Mgmt-Nonce' = $nonce
        'X-Mgmt-Signature' = $signature
    }
    $url = $base.TrimEnd('/') + $Path
    $wireBody = $bodyText
    if ($Method -eq 'GET') { $wireBody = $null }
    $raw = Invoke-FrpHttpsJson -Method $Method -Url $url -Body $wireBody -Headers $headers
    if (-not $raw) { return [pscustomobject]@{} }
    $data = $raw | ConvertFrom-Json
    if ($data.error) { throw ('ERROR: Server management request failed: {0}' -f [string]$data.error) }
    $props = @($data.PSObject.Properties.Name)
    if ($props -contains 'response_hmac') {
        $received = [string]$data.response_hmac
        $plain = ConvertTo-FrpPlainObject $data
        $plain.Remove('response_hmac')
        $mac = Read-FrpIdentityMac
        $expected = Get-FrpHmacHex -Secret $mac -Message (Get-FrpCanonicalJson -Object $plain)
        if (-not (Test-FrpFixedTimeEquals -Left $received -Right $expected -IgnoreCase)) {
            throw 'ERROR: Server management response failed integrity verification'
        }
        $data.PSObject.Properties.Remove('response_hmac')
    }
    return $data
}

function Get-FrpV24CatalogCachePath {
    return (Join-Path (Get-FrpStateDir) 'v24-catalog.json')
}

function Save-FrpV24CatalogCache {
    param([Parameter(Mandatory=$true)]$Catalog)
    Initialize-FrpDirectories
    $path = Get-FrpV24CatalogCachePath
    $tmp = $path + '.tmp'
    [System.IO.File]::WriteAllText($tmp, ($Catalog | ConvertTo-Json -Depth 12) + [Environment]::NewLine)
    Restrict-FrpFileAcl -Path $tmp
    Move-Item -LiteralPath $tmp -Destination $path -Force
    Restrict-FrpFileAcl -Path $path
}

function Get-FrpV24Catalog {
    try {
        $catalog = Invoke-FrpV24MgmtRequest -Method GET -Path '/v1/catalog'
        Save-FrpV24CatalogCache -Catalog $catalog
        return $catalog
    } catch {
        $path = Get-FrpV24CatalogCachePath
        if (Test-Path -LiteralPath $path) {
            return ((Get-Content -LiteralPath $path -Raw) | ConvertFrom-Json)
        }
        throw
    }
}

function Get-FrpV24ServiceObject {
    param([Parameter(Mandatory=$true)][string]$Name, $Catalog)
    if ($null -eq $Catalog) { $Catalog = Get-FrpV24Catalog }
    foreach ($item in @($Catalog.serviceObjects)) {
        if ([string]$item.name -ieq $Name) {
            $type = ([string]$item.type).ToLowerInvariant()
            if ($type -eq 'udp') { throw 'ERROR: UDP Service Object cannot be used by a Remote Service' }
            if ($type -ne 'tcp' -and $type -ne 'fixed-tcp') {
                throw 'ERROR: unsupported Service Object type for Remote Service'
            }
            return $item
        }
    }
    throw ('ERROR: Service Object not found: {0}' -f $Name)
}
function Resolve-FrpV24LegacyServiceName {
    param([Parameter(Mandatory=$true)]$Item, [Parameter(Mandatory=$true)]$Catalog)
    $preset = ([string]$Item.preset).Trim().ToLowerInvariant()
    $port = 0
    try { $port = [int]$Item.local_port } catch { $port = 0 }

    if ($preset -in @('ssh','http','https','tcp')) {
        foreach ($sobj in @($Catalog.serviceObjects)) {
            if ([string]$sobj.name -ieq $preset -and [string]$sobj.type -in @('tcp','fixed-tcp')) {
                if ($port -le 0 -or [int]$sobj.port -eq $port) { return [string]$sobj.name }
            }
        }
    }

    $matches = @($Catalog.serviceObjects | Where-Object {
        ([string]$_.type -in @('tcp','fixed-tcp')) -and $port -gt 0 -and [int]$_.port -eq $port
    })
    if ($matches.Count -eq 1) { return [string]$matches[0].name }

    $name = [string]$Item.id
    throw (
        "ERROR: legacy service '{0}' cannot be mapped unambiguously to a Server Service Object (local port {1}). " +
        "Create one matching TCP/Fixed TCP Service Object on the Server, then run: system synchronize"
    ) -f $name, $port
}

function ConvertTo-FrpV24RemoteMap {
    $state = Read-FrpClientState
    return (ConvertTo-FrpServiceMap -Services $state.services)
}

function Save-FrpV24ServiceMap {
    param([Parameter(Mandatory=$true)]$Map)
    $state = Read-FrpClientState
    $args = @{
        AllocatorUrl = [string]$state.allocator_url
        FrpServer = [string]$state.frp_server
        FrpServerPort = [int]$state.frp_server_port
        Hostname = [string]$state.hostname
        MachineId = [string]$state.machine_id
        HostId = [string]$state.host_id
        Services = $Map
        Transport = [string]$state.frp_transport
        ProjectVersion = [string]$state.project_version
        FrpVersion = [string]$state.frp_version
        InstallStatus = [string]$state.install_status
    }
    if (Test-FrpObjectHasProperty -Object $state -Name 'public_hostname') {
        $args['PublicHostname'] = [string]$state.public_hostname
    }
    Save-FrpClientState @args | Out-Null
}
function Update-FrpV24Runtime {
    if (-not (Test-Path -LiteralPath (Get-FrpTomlPath))) {
        throw 'ERROR: frpc.toml is missing; cannot activate Remote Service runtime'
    }
    $token = Get-FrpTokenFromToml
    if (-not $token) { throw 'ERROR: cannot regenerate frpc.toml; FRP token is unavailable' }
    $state = Read-FrpClientState
    $map = ConvertTo-FrpServiceMap -Services $state.services
    $runtimeMap = [ordered]@{}
    $desiredEnabledAny = $false
    $runtimeEnabledAny = $false
    foreach ($sid in @($map.Keys)) {
        $item = $map[$sid]
        $enabled = ($item.enabled -ne $false)
        if ($enabled) { $desiredEnabledAny = $true }
        $pending = ($item.v24_remote_service -and ($item.pending_allocation -eq $true -or -not $item.remote_port))
        if ($pending) { continue }
        $runtimeMap[$sid] = $item
        if ($enabled) { $runtimeEnabledAny = $true }
    }
    $tomlArgs = @{
        ServerAddr = [string]$state.frp_server
        ServerPort = [int]$state.frp_server_port
        Token = $token
        HostId = [string]$state.host_id
        Services = $runtimeMap
        Transport = [string]$state.frp_transport
    }
    New-FrpClientToml @tomlArgs | Out-Null

    # Fixture mode validates desired state/config only; it must never start host processes.
    if ($env:FRP_WINDOWS_V24_FIXTURE_DIR) {
        Set-FrpInstallStatus -Status $(if ($desiredEnabledAny) { 'installed' } else { 'management_only' })
        return
    }

    # Lifecycle heartbeat remains present for active, pending, and management-only Agents.
    Install-FrpLifecycleTask | Out-Null
    $running = (Get-FrpClientStatus).Running
    if ($runtimeEnabledAny) {
        Set-FrpInstallStatus -Status 'installed'
        if ($env:FRP_WINDOWS_SKIP_AUTOSTART -ne '1') {
            Install-FrpAutostartTask | Out-Null
        }
        if ($running) { Stop-FrpClient | Out-Null }
        Start-FrpClient -Force:$true | Out-Null
        return
    }

    Set-FrpInstallStatus -Status $(if ($desiredEnabledAny) { 'installed' } else { 'management_only' })
    if ($running) { Stop-FrpClient | Out-Null }
    if ($env:FRP_WINDOWS_SKIP_AUTOSTART -ne '1') {
        Uninstall-FrpAutostartTask | Out-Null
    }
}
function Get-FrpV24RemoteRecord {
    param([Parameter(Mandatory=$true)][string]$Name)
    $map = ConvertTo-FrpV24RemoteMap
    foreach ($key in @($map.Keys)) {
        if ([string]$key -ieq $Name) { return $map[$key] }
    }
    return $null
}

function Format-FrpV24RemoteRecord {
    param($Item)
    if ($null -eq $Item) { return '' }
    $endpoint = '-'
    if ($Item.pending_allocation -eq $true) { $endpoint = 'Pending allocation' }
    elseif ($Item.remote_port) {
        $endpoint = $(if ($Item.endpoint_host) { ('{0}:{1}' -f $Item.endpoint_host, $Item.remote_port) } else { [string]$Item.remote_port })
    }
    $destination = [string]$Item.destination
    if (-not $destination) { $destination = [string]$Item.local_ip }
    $service = [string]$Item.service_object
    if (-not $service) { $service = [string]$Item.preset }
    $status = [string]$Item.status
    if (-not $status) { $status = $(if ($Item.enabled -eq $false) { 'DISABLED' } else { 'DEGRADED' }) }
    return @(
        ('Remote Service: {0}' -f [string]$Item.id)
        ('  Destination : {0}' -f $destination)
        ('  Service     : {0}' -f $service)
        ('  State       : {0}' -f $status)
        ('  Endpoint    : {0}' -f $endpoint)
    ) -join [Environment]::NewLine
}
function Show-FrpV24RemoteServices {
    if (-not (Test-Path -LiteralPath (Get-FrpStatePath))) {
        Write-Host 'No Remote Services configured.'
        return 0
    }
    $map = ConvertTo-FrpV24RemoteMap
    if ($map.Count -eq 0) {
        Write-Host 'No Remote Services configured.'
        return 0
    }
    foreach ($key in @($map.Keys | Sort-Object)) {
        $item = $map[$key]
        Write-Host (Format-FrpV24RemoteRecord -Item $item)
        Write-Host ''
    }
    return 0
}

function Show-FrpV24RemoteService {
    param([Parameter(Mandatory=$true)][string]$Name)
    if (-not (Test-Path -LiteralPath (Get-FrpStatePath))) {
        Write-Host ('ERROR: Remote Service not found: {0}' -f $Name)
        return 1
    }
    $item = Get-FrpV24RemoteRecord -Name $Name
    if ($null -eq $item) {
        Write-Host ('ERROR: Remote Service not found: {0}' -f $Name)
        return 1
    }
    Write-Host (Format-FrpV24RemoteRecord -Item $item)
    return 0
}
function Convert-FrpV24AckToRecord {
    param($Ack)
    $preset = 'custom'
    if ([string]$Ack.service -in @('ssh','http','https')) { $preset = [string]$Ack.service }
    $rec = [ordered]@{
        id = ([string]$Ack.name).ToLowerInvariant()
        name = [string]$Ack.name
        preset = $preset
        protocol = 'tcp'
        local_ip = [string]$Ack.target_host
        local_port = [int]$Ack.target_port
        enabled = [bool]$Ack.enabled
        v24_remote_service = $true
        destination = [string]$Ack.destination
        service_object = [string]$Ack.service
        pool_class = [string]$Ack.pool_class
        status = [string]$Ack.status
        reason = [string]$Ack.reason
        pending_allocation = [bool]$Ack.pending_allocation
    }
    if ($Ack.endpoint_host) { $rec['endpoint_host'] = [string]$Ack.endpoint_host }
    if ($Ack.endpoint_port) { $rec['remote_port'] = [int]$Ack.endpoint_port }
    if ($Ack.destination_client_id) { $rec['destination_client_id'] = [string]$Ack.destination_client_id }
    return $rec
}
function Invoke-FrpV24SetRemoteService {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [string]$Destination,
        [string]$Service,
        $Enabled = $null,
        [switch]$SkipRuntime,
        [switch]$Quiet,
        [switch]$RequireServer
    )
    if (-not (Test-FrpIsEnrolled)) { throw 'ERROR: Agent is not enrolled' }
    $existing = Get-FrpV24RemoteRecord -Name $Name
    if ($null -ne $existing) {
        if (-not $Destination) { $Destination = [string]$existing.destination }
        if (-not $Service) { $Service = [string]$existing.service_object }
        if ($null -eq $Enabled) { $Enabled = [bool]$existing.enabled }
    }
    if (-not $Destination -or -not $Service) {
        throw 'ERROR: new Remote Service requires destination and service'
    }
    if ($null -eq $Enabled) { $Enabled = $true }
    $catalog = Get-FrpV24Catalog
    $sobj = Get-FrpV24ServiceObject -Name $Service -Catalog $catalog
    $target = Resolve-FrpV24DestinationTarget -Destination $Destination -Catalog $catalog
    $pool = $(if ([string]$sobj.type -eq 'fixed-tcp') { 'fixed-tcp' } else { 'normal' })
    $preserve = $null
    if ($null -ne $existing -and $existing.remote_port) { $preserve = [int]$existing.remote_port }
    $body = [ordered]@{
        name = $Name
        destination = $Destination
        service = [string]$sobj.name
        enabled = $Enabled
        pool_class = $pool
        target_host = [string]$target.Host
        target_port = [int]$sobj.port
        target_mode = [string]$target.Mode
        runtime_verified = $false
    }
    if ($target.ClientId) { $body['destination_client_id'] = [string]$target.ClientId }
    if ($null -ne $preserve) { $body['preserve_endpoint_port'] = $preserve }

    try {
        $ack = Invoke-FrpV24MgmtRequest -Method POST -Path '/v1/remote-services' -Body $body
    } catch {
        if ($RequireServer -or -not (Test-FrpV24OfflineEligibleError -Message $_.Exception.Message)) { throw }
        $state = Read-FrpClientState
        $ack = [pscustomobject]@{
            name = $Name
            destination = $Destination
            destination_client_id = $target.ClientId
            service = [string]$sobj.name
            enabled = [bool]$Enabled
            status = $(if ($Enabled) { 'DEGRADED' } else { 'DISABLED' })
            endpoint_host = $(if ($existing.endpoint_host) { [string]$existing.endpoint_host } else { [string]$state.frp_server })
            endpoint_port = $preserve
            pool_class = $pool
            pending_allocation = $(if ($Enabled -and $null -eq $preserve) { 1 } else { 0 })
            reason = $(if ($Enabled -and $null -eq $preserve) { 'Server unavailable; endpoint allocation pending.' } elseif ($Enabled) { 'Server unavailable; existing endpoint reservation preserved.' } else { '' })
            runtime_verified = $false
            target_host = [string]$target.Host
            target_port = [int]$sobj.port
            target_mode = [string]$target.Mode
        }
    }
    $map = ConvertTo-FrpV24RemoteMap
    $key = ([string]$Name).ToLowerInvariant()
    $map[$key] = Convert-FrpV24AckToRecord -Ack $ack
    Save-FrpV24ServiceMap -Map $map
    # Desired state is present again, so any older queued delete for this name
    # is obsolete and must not release the service on the next synchronize.
    Remove-FrpV24PendingDelete -Name $Name
    if (-not $SkipRuntime) { Update-FrpV24Runtime }
    if (-not $Quiet) { Write-Host (Format-FrpV24RemoteRecord -Item $map[$key]) }
    return 0
}

function Confirm-FrpV24Destructive {
    param([string]$Prompt)
    if ($env:FRP_WINDOWS_TEST_CONFIRM -eq 'yes') { return $true }
    if ($env:FRP_WINDOWS_TEST_CONFIRM -eq 'no') { return $false }
    if ([Console]::IsInputRedirected) { return $false }
    $answer = Read-Host ($Prompt + ' [y/N]')
    return ([string]$answer).Trim().ToLowerInvariant() -eq 'y'
}
function Invoke-FrpV24UnsetRemoteService {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [switch]$NoConfirm,
        [switch]$SkipRuntime,
        [switch]$Quiet
    )
    $existing = Get-FrpV24RemoteRecord -Name $Name
    if ($null -eq $existing) { throw ('ERROR: Remote Service not found: {0}' -f $Name) }
    if (-not $NoConfirm) {
        if (-not (Confirm-FrpV24Destructive -Prompt ('Delete Remote Service {0}?' -f $Name))) {
            Write-Host 'Cancelled. No changes were applied.'
            return 0
        }
    }
    $escaped = [Uri]::EscapeDataString($Name)
    $queued = $false
    try {
        Invoke-FrpV24MgmtRequest -Method DELETE -Path ('/v1/remote-services/' + $escaped) | Out-Null
        Remove-FrpV24PendingDelete -Name $Name
    } catch {
        if (-not (Test-FrpV24OfflineEligibleError -Message $_.Exception.Message)) { throw }
        Add-FrpV24PendingDelete -Name $Name
        $queued = $true
    }
    $map = ConvertTo-FrpV24RemoteMap
    $removeKey = $null
    foreach ($key in @($map.Keys)) {
        if ([string]$key -ieq $Name) { $removeKey = $key; break }
    }
    if ($null -ne $removeKey) { $map.Remove($removeKey) }
    Save-FrpV24ServiceMap -Map $map
    if (-not $SkipRuntime) { Update-FrpV24Runtime }
    if (-not $Quiet) {
        if ($queued) {
            Write-Host ('Remote Service deleted locally: {0}' -f $Name)
            Write-Host 'Server release is queued and will be completed by: system synchronize'
        } else {
            Write-Host ('Remote Service deleted: {0}' -f $Name)
        }
    }
    return 0
}
function Invoke-FrpV24Synchronize {
    if (-not (Test-FrpIsEnrolled)) {
        Write-Host 'ERROR: Agent is not enrolled'
        return 1
    }
    try {
        # Synchronize is an explicit reconnect operation: require a live Server.
        $catalog = Invoke-FrpV24MgmtRequest -Method GET -Path '/v1/catalog'
        Save-FrpV24CatalogCache -Catalog $catalog
    } catch {
        Write-Host $_.Exception.Message
        return 1
    }

    $deleted = 0
    foreach ($name in @(Get-FrpV24PendingDeletes)) {
        try {
            $escaped = [Uri]::EscapeDataString([string]$name)
            Invoke-FrpV24MgmtRequest -Method DELETE -Path ('/v1/remote-services/' + $escaped) | Out-Null
            Remove-FrpV24PendingDelete -Name ([string]$name)
            $deleted++
        } catch {
            Write-Host $_.Exception.Message
            return 1
        }
    }

    $map = ConvertTo-FrpV24RemoteMap
    $changed = 0
    $migrated = @{}

    # Upgrade convergence: promote pre-v2.4 Windows service records into the
    # canonical Remote Service model while preserving their existing endpoint.
    foreach ($key in @($map.Keys)) {
        $item = $map[$key]
        if ($item.v24_remote_service) { continue }
        try {
            $service = Resolve-FrpV24LegacyServiceName -Item $item -Catalog $catalog
            $setArgs = @{
                Name = [string]$item.id
                Destination = 'this-host'
                Service = $service
                Enabled = [bool]($item.enabled -ne $false)
                SkipRuntime = $true
                Quiet = $true
                RequireServer = $true
            }
            Invoke-FrpV24SetRemoteService @setArgs | Out-Null
            $migrated[[string]$key] = $true
            $changed++
        } catch {
            Write-Host $_.Exception.Message
            return 1
        }
    }

    $map = ConvertTo-FrpV24RemoteMap
    foreach ($key in @($map.Keys)) {
        if ($migrated.ContainsKey([string]$key)) { continue }
        $item = $map[$key]
        if (-not $item.v24_remote_service) { continue }
        $service = [string]$item.service_object
        if (-not $service) { continue }
        try {
            Get-FrpV24ServiceObject -Name $service -Catalog $catalog | Out-Null
            $setArgs = @{
                Name = [string]$item.id
                Destination = [string]$item.destination
                Service = $service
                Enabled = [bool]$item.enabled
                SkipRuntime = $true
                Quiet = $true
                RequireServer = $true
            }
            Invoke-FrpV24SetRemoteService @setArgs | Out-Null
            $changed++
        } catch {
            Write-Host $_.Exception.Message
            return 1
        }
    }
    try { Update-FrpV24Runtime } catch {
        Write-Host $_.Exception.Message
        return 1
    }
    Write-Host ('Agent Remote Service synchronization complete. Reconciled: {0}; deleted: {1}' -f $changed, $deleted)
    return 0
}
function ConvertFrom-FrpV24YamlScalar {
    param([string]$Text)
    $v = ([string]$Text).Trim()
    if ($v.Length -ge 2 -and $v.StartsWith("'") -and $v.EndsWith("'")) {
        return $v.Substring(1, $v.Length - 2).Replace("''", "'")
    }
    if ($v.Length -ge 2 -and $v.StartsWith('"') -and $v.EndsWith('"')) {
        return $v.Substring(1, $v.Length - 2)
    }
    if ($v -ieq 'true') { return $true }
    if ($v -ieq 'false') { return $false }
    return $v
}

function ConvertTo-FrpV24YamlScalar {
    param([string]$Text)
    $v = [string]$Text
    return "'" + $v.Replace("'", "''") + "'"
}

function Read-FrpV24AgentBundle {
    param([Parameter(Mandatory=$true)][string]$Path)
    if ($Path -eq '-') { $text = [Console]::In.ReadToEnd() }
    else { $text = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop }
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'ERROR: ConfigurationBundle is empty' }
    $trim = $text.TrimStart()
    if ($trim.StartsWith('{')) {
        $doc = $text | ConvertFrom-Json
        $body = $doc.configurationBundle
        if ($null -eq $body) { throw 'ERROR: configurationBundle root is required' }
        if ([string]$body.context -ne 'agent') {
            throw 'ERROR: ConfigurationBundle context must be agent on a Windows Agent Host'
        }
        $items = @($body.remoteServices)
        foreach ($item in $items) {
            if (-not [string]$item.name) { throw 'ERROR: Remote Service name is required' }
            $state = ([string]$item.state).Trim().ToLowerInvariant()
            if ($state -and $state -ne 'absent') { throw 'ERROR: Remote Service state must be absent when supplied' }
            if ($state -ne 'absent') {
                if (-not [string]$item.destination) { throw ('ERROR: Remote Service {0} destination is required' -f $item.name) }
                if (-not [string]$item.service) { throw ('ERROR: Remote Service {0} service is required' -f $item.name) }
                if ($null -eq $item.enabled) { $item | Add-Member -NotePropertyName enabled -NotePropertyValue $true -Force }
            }
        }
        return [pscustomobject]@{ context = 'agent'; remoteServices = $items }
    }
    $context = $null
    $items = New-Object System.Collections.ArrayList
    $current = $null
    $inRemote = $false
    foreach ($rawLine in ($text -split "[$([char]13)$([char]10)]+")) {
        $line = $rawLine
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line.TrimStart().StartsWith('#')) { continue }
        if ($line -match '^[ ]*configurationBundle:[ ]*$') { continue }
        if ($line -match '^[ ]{2}context:[ ]*(.+?)[ ]*$') {
            $context = [string](ConvertFrom-FrpV24YamlScalar -Text $Matches[1])
            continue
        }
        if ($line -match '^[ ]{2}remoteServices:[ ]*\[\][ ]*$') {
            $inRemote = $true
            continue
        }
        if ($line -match '^[ ]{2}remoteServices:[ ]*$') {
            $inRemote = $true
            continue
        }
        if ($inRemote -and $line -match '^[ ]{4}\[\][ ]*$') { continue }
        if ($inRemote -and $line -match '^[ ]{4}-[ ]+name:[ ]*(.+?)[ ]*$') {
            if ($null -ne $current) { [void]$items.Add([pscustomobject]$current) }
            $current = [ordered]@{ name = [string](ConvertFrom-FrpV24YamlScalar -Text $Matches[1]) }
            continue
        }
        if ($inRemote -and $line -match '^[ ]{6}(destination|service|enabled|state):[ ]*(.*?)[ ]*$') {
            if ($null -eq $current) { throw 'ERROR: remoteServices item must start with name' }
            $current[$Matches[1]] = ConvertFrom-FrpV24YamlScalar -Text $Matches[2]
            continue
        }
        throw ('ERROR: unsupported ConfigurationBundle YAML line: {0}' -f $line.Trim())
    }
    if ($null -ne $current) { [void]$items.Add([pscustomobject]$current) }
    if ([string]$context -ne 'agent') { throw 'ERROR: ConfigurationBundle context must be agent on a Windows Agent Host' }
    foreach ($item in @($items)) {
        if (-not [string]$item.name) { throw 'ERROR: Remote Service name is required' }
        $state = ([string]$item.state).Trim().ToLowerInvariant()
        if ($state -and $state -ne 'absent') { throw 'ERROR: Remote Service state must be absent when supplied' }
        if ($state -ne 'absent') {
            if (-not [string]$item.destination) { throw ('ERROR: Remote Service {0} destination is required' -f $item.name) }
            if (-not [string]$item.service) { throw ('ERROR: Remote Service {0} service is required' -f $item.name) }
            if ($null -eq $item.enabled) { $item | Add-Member -NotePropertyName enabled -NotePropertyValue $true -Force }
        }
    }
    return [pscustomobject]@{ context = 'agent'; remoteServices = @($items) }
}
function Export-FrpV24AgentBundleText {
    $lines = New-Object System.Collections.ArrayList
    [void]$lines.Add('configurationBundle:')
    [void]$lines.Add('  context: agent')
    [void]$lines.Add('  remoteServices:')
    $remoteLineIndex = $lines.Count - 1
    $map = ConvertTo-FrpV24RemoteMap
    $legacy = @($map.Keys | Where-Object { -not $map[$_].v24_remote_service })
    if ($legacy.Count -gt 0) {
        throw (
            "ERROR: legacy Windows service state has not been converged to v2.4 Remote Services. " +
            "Run: system synchronize, then export again."
        )
    }
    $count = 0
    foreach ($key in @($map.Keys | Sort-Object)) {
        $item = $map[$key]
        $count++
        [void]$lines.Add(('    - name: {0}' -f (ConvertTo-FrpV24YamlScalar -Text ([string]$item.id))))
        [void]$lines.Add(('      destination: {0}' -f (ConvertTo-FrpV24YamlScalar -Text ([string]$item.destination))))
        [void]$lines.Add(('      service: {0}' -f (ConvertTo-FrpV24YamlScalar -Text ([string]$item.service_object))))
        [void]$lines.Add(('      enabled: {0}' -f $(if ($item.enabled -eq $false) { 'false' } else { 'true' })))
    }
    if ($count -eq 0) { $lines[$remoteLineIndex] = '  remoteServices: []' }
    return (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

function Export-FrpV24AgentBundle {
    param([Parameter(Mandatory=$true)][string]$Path)
    $text = Export-FrpV24AgentBundleText
    [System.IO.File]::WriteAllText($Path, $text, [System.Text.UTF8Encoding]::new($false))
    Write-Host ('Configuration exported (redacted): {0}' -f $Path)
    return 0
}
function Get-FrpV24BundlePlan {
    param($Bundle)
    $catalog = Get-FrpV24Catalog
    $changes = New-Object System.Collections.ArrayList
    foreach ($item in @($Bundle.remoteServices)) {
        $name = [string]$item.name
        $existing = Get-FrpV24RemoteRecord -Name $name
        $state = ([string]$item.state).Trim().ToLowerInvariant()
        if ($state -eq 'absent') {
            $op = $(if ($null -eq $existing) { 'NO_CHANGE' } else { 'DELETE' })
            [void]$changes.Add([pscustomobject]@{ op=$op; name=$name; item=$item; before=$existing })
            continue
        }
        Get-FrpV24ServiceObject -Name ([string]$item.service) -Catalog $catalog | Out-Null
        $op = 'CREATE'
        if ($null -ne $existing) {
            if (-not $existing.v24_remote_service -or -not [string]$existing.service_object) {
                throw ('ERROR: existing legacy service {0} must be converged first. Run: system synchronize' -f $name)
            }
            $same = ([string]$existing.destination -ieq [string]$item.destination) -and
                ([string]$existing.service_object -ieq [string]$item.service) -and
                ([bool]$existing.enabled -eq [bool]$item.enabled)
            $op = $(if ($same) { 'NO_CHANGE' } else { 'UPDATE' })
        }
        [void]$changes.Add([pscustomobject]@{ op=$op; name=$name; item=$item; before=$existing })
    }
    return ,$changes.ToArray()
}
function Write-FrpV24BundlePlan {
    param($Changes)
    $create = @($Changes | Where-Object { $_.op -eq 'CREATE' }).Count
    $update = @($Changes | Where-Object { $_.op -eq 'UPDATE' }).Count
    $delete = @($Changes | Where-Object { $_.op -eq 'DELETE' }).Count
    $same = @($Changes | Where-Object { $_.op -eq 'NO_CHANGE' }).Count
    Write-Host ''
    Write-Host 'Planned changes:'
    Write-Host ('  + {0} CREATE' -f $create)
    Write-Host ('  ~ {0} UPDATE' -f $update)
    Write-Host ('  - {0} DELETE' -f $delete)
    Write-Host ('  = {0} NO CHANGE' -f $same)
    foreach ($c in @($Changes)) {
        Write-Host ('  [{0}] remoteServices/{1}' -f $c.op, $c.name)
    }
}

function Test-FrpV24AgentBundle {
    param([Parameter(Mandatory=$true)][string]$Path, [switch]$Diff)
    try {
        $bundle = Read-FrpV24AgentBundle -Path $Path
        $changes = Get-FrpV24BundlePlan -Bundle $bundle
        Write-Host 'VALID'
        Write-FrpV24BundlePlan -Changes $changes
        Write-Host ''
        Write-Host 'No changes were applied.'
        if ($Diff) {
            $mut = @($changes | Where-Object { $_.op -ne 'NO_CHANGE' }).Count
            Write-Host ('Diff result: {0}' -f $(if ($mut -eq 0) { 'NO CHANGE' } else { 'CHANGES' }))
        }
        return 0
    } catch {
        Write-Host $_.Exception.Message
        Write-Host 'No changes were applied.'
        return 1
    }
}
function Restore-FrpV24BundleChange {
    param($Change)
    $before = $Change.before
    $name = [string]$Change.name
    if ($null -eq $before) {
        $current = Get-FrpV24RemoteRecord -Name $name
        if ($null -ne $current) {
            Invoke-FrpV24UnsetRemoteService -Name $name -NoConfirm -SkipRuntime -Quiet | Out-Null
        }
        return
    }
    $service = [string]$before.service_object
    $destination = [string]$before.destination
    if (-not $service -or -not $destination) {
        throw ('ERROR: cannot compensate legacy Remote Service: {0}' -f $name)
    }
    $args = @{
        Name = [string]$before.id
        Destination = $destination
        Service = $service
        Enabled = [bool]$before.enabled
        SkipRuntime = $true
        Quiet = $true
    }
    Invoke-FrpV24SetRemoteService @args | Out-Null
}

function Invoke-FrpV24AgentBundleApply {
    param([Parameter(Mandatory=$true)][string]$Path)
    try {
        $bundle = Read-FrpV24AgentBundle -Path $Path
        $changes = Get-FrpV24BundlePlan -Bundle $bundle
    } catch {
        Write-Host $_.Exception.Message
        Write-Host 'No changes were applied.'
        return 1
    }
    Write-Host 'VALID'
    Write-FrpV24BundlePlan -Changes $changes
    $mutating = @($changes | Where-Object { $_.op -ne 'NO_CHANGE' })
    if ($mutating.Count -eq 0) {
        Write-Host ''
        Write-Host 'NO CHANGE'
        return 0
    }
    if (-not (Confirm-FrpV24Destructive -Prompt 'Apply this ConfigurationBundle?')) {
        Write-Host 'Cancelled. No changes were applied.'
        return 0
    }
    $applied = New-Object System.Collections.ArrayList
    try {
        foreach ($c in $mutating) {
            if ($c.op -eq 'DELETE') {
                Invoke-FrpV24UnsetRemoteService -Name ([string]$c.name) -NoConfirm -SkipRuntime -Quiet | Out-Null
            } else {
                $args = @{
                    Name = [string]$c.name
                    Destination = [string]$c.item.destination
                    Service = [string]$c.item.service
                    Enabled = [bool]$c.item.enabled
                    SkipRuntime = $true
                    Quiet = $true
                }
                Invoke-FrpV24SetRemoteService @args | Out-Null
            }
            [void]$applied.Add($c)
        }
        Update-FrpV24Runtime
    } catch {
        $original = $_.Exception.Message
        $rollbackOk = $true
        for ($i = $applied.Count - 1; $i -ge 0; $i--) {
            try { Restore-FrpV24BundleChange -Change $applied[$i] }
            catch { $rollbackOk = $false }
        }
        try { Update-FrpV24Runtime } catch { $rollbackOk = $false }
        if ($rollbackOk) {
            Write-Host 'ERROR: ConfigurationBundle apply failed.'
            Write-Host 'Previous configuration was restored.'
            Write-Host $original
        } else {
            Write-Host 'ERROR: ConfigurationBundle apply failed and automatic rollback was incomplete.'
            Write-Host 'RECOVERY_REQUIRED'
            Write-Host $original
        }
        return 1
    }
    Write-Host ''
    Write-Host 'ConfigurationBundle applied.'
    return 0
}
function Show-FrpV24Agent {
    if (-not (Test-FrpIsEnrolled)) {
        Write-Host 'Agent Host'
        Write-Host '  Enrollment : Not enrolled'
        return 0
    }
    $state = Read-FrpClientState
    $status = Get-FrpClientStatus
    Write-Host 'Agent Host'
    Write-Host ('  Machine ID : {0}' -f [string]$state.machine_id)
    Write-Host ('  Hostname   : {0}' -f [string]$state.hostname)
    Write-Host ('  Server     : {0}' -f [string]$state.frp_server)
    Write-Host ('  Runtime    : {0}' -f $(if ($status.Running) { 'active' } else { 'stopped' }))
    Write-Host ('  Autostart  : {0}' -f $(if (Test-FrpAutostartTaskExists) { 'enabled' } else { 'disabled' }))
    return 0
}
function Test-FrpV24OfflineEligibleError {
    param([string]$Message)
    $m = ([string]$Message).ToLowerInvariant()
    return (
        $m -match 'allocator request failed' -or
        $m -match 'server management url is not configured' -or
        $m -match 'timed out' -or
        $m -match 'name or service not known' -or
        $m -match 'no such host' -or
        $m -match 'connection refused'
    )
}

function Resolve-FrpV24DestinationTarget {
    param([Parameter(Mandatory=$true)][string]$Destination, [Parameter(Mandatory=$true)]$Catalog)
    $dest = $Destination.Trim()
    if ($dest -ieq 'this-host' -or $dest -ieq 'self' -or $dest -ieq 'this_host') {
        return [pscustomobject]@{ Host='127.0.0.1'; Mode='local'; ClientId=$null }
    }
    foreach ($obj in @($Catalog.networkObjects)) {
        if ([string]$obj.name -ine $dest) { continue }
        $values = @($obj.values)
        if ($values.Count -gt 0 -and [string]$values[0]) {
            return [pscustomobject]@{ Host=[string]$values[0]; Mode='host'; ClientId=$obj.client_id }
        }
    }
    foreach ($host in @($Catalog.managedHosts)) {
        if ([string]$host.name -ine $dest -and [string]$host.hostname -ine $dest) { continue }
        $addresses = @($host.addresses)
        if ($addresses.Count -gt 0 -and [string]$addresses[0]) {
            return [pscustomobject]@{ Host=[string]$addresses[0]; Mode='host'; ClientId=$host.id }
        }
    }
    throw ('ERROR: Destination Network Object or Managed Host not found in synchronized catalog: {0}' -f $Destination)
}

function Get-FrpV24PendingDeletePath {
    return (Join-Path (Get-FrpStateDir) 'v24-pending-deletes.json')
}

function Get-FrpV24PendingDeletes {
    $path = Get-FrpV24PendingDeletePath
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    try {
        $raw = Get-Content -LiteralPath $path -Raw
        if ([string]::IsNullOrWhiteSpace($raw)) { return @() }
        return @($raw | ConvertFrom-Json)
    } catch {
        throw 'ERROR: pending Remote Service delete queue is unreadable'
    }
}
function Save-FrpV24PendingDeletes {
    param([string[]]$Names)
    Initialize-FrpDirectories
    $path = Get-FrpV24PendingDeletePath
    $unique = @($Names | Where-Object { $_ } | ForEach-Object { ([string]$_).Trim().ToLowerInvariant() } | Sort-Object -Unique)
    if ($unique.Count -eq 0) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        return
    }
    $tmp = $path + '.tmp'
    [System.IO.File]::WriteAllText($tmp, ($unique | ConvertTo-Json) + [Environment]::NewLine)
    Restrict-FrpFileAcl -Path $tmp
    Move-Item -LiteralPath $tmp -Destination $path -Force
    Restrict-FrpFileAcl -Path $path
}

function Add-FrpV24PendingDelete {
    param([Parameter(Mandatory=$true)][string]$Name)
    $all = New-Object System.Collections.ArrayList
    foreach ($item in @(Get-FrpV24PendingDeletes)) { [void]$all.Add([string]$item) }
    [void]$all.Add($Name)
    Save-FrpV24PendingDeletes -Names @($all)
}

function Remove-FrpV24PendingDelete {
    param([Parameter(Mandatory=$true)][string]$Name)
    $left = @((Get-FrpV24PendingDeletes) | Where-Object { [string]$_ -ine $Name })
    Save-FrpV24PendingDeletes -Names $left
}
