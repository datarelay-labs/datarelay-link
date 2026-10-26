# Schema and existing-resource patch semantics must agree for JSON and YAML.
. (Join-Path $PSScriptRoot '_import.ps1')
function Get-FrpV24Catalog { return [pscustomobject]@{ serviceObjects=@([pscustomobject]@{name='ssh';type='tcp';port=22}); managedHosts=@();networkObjects=@() } }
function Read-FrpClientState { return [pscustomobject]@{machine_id='aabbcc';hostname='test-agent'} }
function Get-FrpV24RemoteRecord {
    param([string]$Name)
    if ($Name -eq 'keep') { return [pscustomobject]@{destination='this-host';service_object='ssh';enabled=$false;v24_remote_service=$true} }
    return $null
}
function ConvertTo-FrpV24RemoteMap { return @{keep=(Get-FrpV24RemoteRecord 'keep')} }
$failures = New-Object System.Collections.Generic.List[string]
try {
    $cases = @(
        @{name='absent-plus-fields';valid=$false;item=@{name='keep';state='absent';enabled=$false}},
        @{name='invalid-enabled';valid=$false;item=@{name='keep';destination='this-host';service='ssh';enabled='sometimes'}},
        @{name='unknown-item-field';valid=$false;item=@{name='keep';destination='this-host';service='ssh';typo='x'}},
        @{name='existing-omitted-fields';valid=$true;item=@{name='keep'}},
        @{name='existing-enabled-patch';valid=$true;item=@{name='keep';enabled=$true}},
        @{name='new-missing-fields';valid=$false;item=@{name='new'}}
    )
    foreach ($format in @('json','yaml')) {
        foreach ($case in $cases) {
            $body = @{context='agent';remoteServices=@($case.item)}
            if ($format -eq 'json') { $text = @{configurationBundle=$body} | ConvertTo-Json -Depth 8 }
            else {
                $lines = @('configurationBundle:','  context: agent','  remoteServices:',('    - name: ' + $case.item.name))
                foreach ($key in @($case.item.Keys | Where-Object { $_ -ne 'name' })) {
                    $value = $case.item[$key]
                    if ($value -is [bool]) { $value = $value.ToString().ToLowerInvariant() }
                    $lines += ('      ' + $key + ': ' + $value)
                }
                $text = $lines -join "`n"
            }
            $file = Join-Path $env:FRP_WINDOWS_ROOT ('schema.' + $format)
            Set-Content -LiteralPath $file -Value $text
            $valid = $true; $detail = ''
            try {
                $bundle = Read-FrpV24AgentBundle -Path $file
                $plan = Get-FrpV24BundlePlan -Bundle $bundle
                if ($case.name -eq 'existing-omitted-fields') {
                    if ($plan.Count -ne 1 -or $plan[0].op -ne 'NO_CHANGE' -or $plan[0].item.enabled -ne $false) { throw 'omitted fields must preserve existing disabled state' }
                }
            } catch { $valid = $false; $detail = $_.Exception.Message }
            if ($valid -ne $case.valid) { $failures.Add(($format + '/' + $case.name + ': ' + $detail)) }
        }
    }
    foreach ($body in @(@{context='agent'}, @{context='agent';networkObjects=@()})) {
        $file = Join-Path $env:FRP_WINDOWS_ROOT 'section.json'
        @{configurationBundle=$body} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $file
        $valid = $true
        try { Get-FrpV24BundlePlan -Bundle (Read-FrpV24AgentBundle -Path $file) | Out-Null } catch { $valid = $false }
        if ($valid -ne (-not $body.ContainsKey('networkObjects'))) { $failures.Add('section validation: ' + ($body.Keys -join ',')) }
    }
    if ($failures.Count) { throw ($failures -join "`n") }
    Write-FrpTestPass 'v24-bundle-schema-parity'
} finally { Remove-FrpWindowsTestRoot }
