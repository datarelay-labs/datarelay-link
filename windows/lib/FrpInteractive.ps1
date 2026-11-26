# Native Agent interactive shell. No Invoke-Expression, shell evaluation or
# independent mutation path: every action invokes the canonical CLI entry.
function Get-FrpInteractivePaths {
    @(
        'show status', 'show agent', 'show remote-services', 'show remote-service <NAME>',
        'set remote-service <NAME> destination <DEST> service <SERVICE> enabled',
        'set remote-service <NAME> destination <DEST> service <SERVICE> disabled',
        'set remote-service <NAME> service <SERVICE>',
        'set remote-service <NAME> destination <DEST>',
        'set remote-service <NAME> enabled', 'set remote-service <NAME> disabled',
        'unset remote-service <NAME>', 'test configuration <FILE>',
        'system info', 'system version', 'system pause', 'system resume', 'system restart',
        'system synchronize', 'system autostart', 'system autostart enable', 'system autostart disable',
        'system update product', 'system update engine', 'system diagnostics', 'system support-bundle',
        'system export configuration <FILE>', 'system diff configuration <FILE>',
        'system apply configuration <FILE>', 'system uninstall',
        'help', 'help commands', 'help workflows', 'help system', 'help remote-service',
        'menu', 'exit', '?'
    )
}

function Split-FrpInteractiveLine {
    param([string]$Line)
    # Quoted text is literal; no expansion, substitutions or shell execution.
    $matches = [regex]::Matches($Line, '\s+|"(?:[^"]*)"|''(?:[^'']*)''|[^\s"'']+')
    $end = 0
    foreach ($m in $matches) {
        if ($m.Index -ne $end) { throw 'ERROR: unmatched quotation mark.' }
        $end = $m.Index + $m.Length
        if ($m.Value -match '^\s+$') { continue }
        $value = $m.Value
        if ($value.StartsWith('"') -or $value.StartsWith("'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        # Do not silently split adjacent quoted/unquoted fragments.
        if ($end -lt $Line.Length -and -not [char]::IsWhiteSpace($Line[$end])) {
            throw 'ERROR: separate arguments with spaces.'
        }
        $value
    }
    if ($end -ne $Line.Length) { throw 'ERROR: unmatched quotation mark.' }
}

function Get-FrpInteractiveCompletions {
    param([string]$Line)
    try { $words = @(Split-FrpInteractiveLine $Line) } catch { return }
    $prefix = ''
    $index = $words.Count
    if ($words.Count -and $Line -notmatch '\s$') {
        $index--
        $prefix = [string]$words[$index]
    }
    $results = @()
    foreach ($path in Get-FrpInteractivePaths) {
        $parts = $path.Split(' ')
        if ($index -ge $parts.Count) { continue }
        $valid = $true
        for ($i=0; $i -lt $index; $i++) {
            if ($parts[$i] -notmatch '^<.*>$' -and $parts[$i] -ine $words[$i]) { $valid = $false; break }
        }
        if (-not $valid) { continue }
        $next = $parts[$index]
        if ($next -eq '<NAME>') {
            try { $results += @((ConvertTo-FrpV24RemoteMap).Keys) } catch { }
        } elseif ($next -eq '<DEST>') {
            $results += 'this-host'
        } elseif ($next -eq '<SERVICE>') {
            # Completion is read-only and never makes a network request.
            try {
                $cache = Get-FrpV24CatalogCachePath
                if (Test-Path -LiteralPath $cache) {
                    $results += @((Get-Content -LiteralPath $cache -Raw | ConvertFrom-Json).serviceObjects | ForEach-Object { $_.name })
                }
            } catch { }
        } elseif ($next -notmatch '^<.*>$') {
            $results += $next
        }
    }
    $results | Where-Object { $_ -and ([string]$_).StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) } | Sort-Object -Unique
}

function Read-FrpInteractiveLine {
    param([string]$Prompt = 'drlink> ', [switch]$NoCompletion)
    # Redirected streams are supported for non-mutating CLI tests and EOF.
    # Mutating commands retain the existing dispatcher confirmation checks.
    if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) {
        [Console]::Write($Prompt)
        return [Console]::In.ReadLine()
    }
    $line = ''
    [Console]::Write($Prompt)
    $oldCtrlC = [Console]::TreatControlCAsInput
    try {
        [Console]::TreatControlCAsInput = $true
        while ($true) {
            $key = [Console]::ReadKey($true)
            if ($key.Key -eq [ConsoleKey]::Enter) { [Console]::WriteLine(); return $line }
            if (($key.Modifiers -band [ConsoleModifiers]::Control) -and $key.Key -eq [ConsoleKey]::C) {
                [Console]::WriteLine('^C'); if ($NoCompletion) { return $null }; return ''
            }
            if (($key.Modifiers -band [ConsoleModifiers]::Control) -and $key.Key -in @([ConsoleKey]::D,[ConsoleKey]::Z) -and -not $line) {
                [Console]::WriteLine(); return $null
            }
            if ($key.Key -eq [ConsoleKey]::Backspace -and $line.Length) {
                $line = $line.Substring(0,$line.Length-1)
                [Console]::Write("`b `b")
                continue
            }
            if ($key.Key -eq [ConsoleKey]::Tab -and -not $NoCompletion) {
                $candidates = @(Get-FrpInteractiveCompletions $line)
                if ($candidates.Count -eq 1) {
                    $word = [string]$candidates[0]
                    $fragment = [regex]::Match($line,'[^\s]*$').Value
                    if ($fragment -and -not $word.StartsWith($fragment,[StringComparison]::OrdinalIgnoreCase)) { continue }
                    $suffix = $word.Substring($fragment.Length) + ' '
                    $line += $suffix
                    [Console]::Write($suffix)
                } elseif ($candidates.Count -gt 1) {
                    [Console]::WriteLine()
                    [Console]::WriteLine(($candidates -join '  '))
                    [Console]::Write($Prompt + $line)
                }
                continue
            }
            if (-not [char]::IsControl($key.KeyChar)) {
                $line += $key.KeyChar
                [Console]::Write($key.KeyChar)
            }
        }
    } finally { [Console]::TreatControlCAsInput = $oldCtrlC }
}

function Invoke-FrpInteractiveCommand {
    param([string]$Entry, [string[]]$Tokens)
    if (-not $Tokens.Count) { return }
    # Named positional binding preserves literal paths containing spaces and
    # prevents PowerShell parameter syntax from becoming an execution channel.
    $names = @('Command','SubCommand','Id','Property','Value','Extra1','Extra2','Extra3','Extra4')
    if ($Tokens.Count -gt $names.Count) { Write-Host 'ERROR: unexpected extra arguments.'; return }
    $bound = @{}
    for ($i=0; $i -lt $Tokens.Count; $i++) { $bound[$names[$i]] = $Tokens[$i] }
    try {
        & $Entry @bound
        if ($LASTEXITCODE -ne 0) { Write-Host ("Command failed with exit code {0}." -f $LASTEXITCODE) }
    } catch {
        Write-Host ("ERROR: {0}" -f $_.Exception.Message)
    }
}

function Invoke-FrpInteractiveRemoteWizard {
    param([string]$Entry,[string]$Name)
    if ([Console]::IsInputRedirected) { Write-Host 'ERROR: guided changes require an interactive terminal.'; return }
    if (-not $Name) { $Name = Read-FrpInteractiveLine -Prompt 'Remote Service name (empty cancels): ' -NoCompletion }
    if (-not $Name) { return }
    $existing = $null
    try { $existing = Get-FrpV24RemoteRecord -Name $Name } catch { }
    $destDefault = 'this-host'
    if ($existing -and $existing.destination) { $destDefault = [string]$existing.destination }
    $dest = Read-FrpInteractiveLine -Prompt "Destination [$destDefault]: " -NoCompletion
    if ($null -eq $dest) { return }
    if (-not $dest) { $dest = $destDefault }
    $serviceDefault = ''
    if ($existing) { $serviceDefault = [string]$existing.service_object }
    $service = Read-FrpInteractiveLine -Prompt "Service Object [$serviceDefault]: " -NoCompletion
    if ($null -eq $service) { return }
    if (-not $service) { $service = $serviceDefault }
    if (-not $service) { Write-Host 'ERROR: Service Object is required. No changes were applied.'; return }
    $enabledDefault = 'enabled'
    if ($existing -and -not $existing.enabled) { $enabledDefault = 'disabled' }
    $enabled = Read-FrpInteractiveLine -Prompt "State (enabled/disabled) [$enabledDefault]: " -NoCompletion
    if ($null -eq $enabled) { return }
    if (-not $enabled) { $enabled = $enabledDefault }
    if ($enabled -notin @('enabled','disabled')) { Write-Host 'ERROR: invalid state. No changes were applied.'; return }
    Write-Host ("Remote Service: {0}; Destination: {1}; Service Object: {2}; State: {3}" -f $Name,$dest,$service,$enabled)
    $answer = Read-FrpInteractiveLine -Prompt 'Apply changes? [y/N]: ' -NoCompletion
    if ($answer -ine 'y' -and $answer -ine 'yes') { Write-Host 'No changes were applied.'; return }
    Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @('set','remote-service',$Name,'destination',$dest,'service',$service,$enabled)
}

function Invoke-FrpInteractiveMenu {
    param([string]$Entry)
    while ($true) {
        Write-Host ''
        Write-Host 'Data Relay Link - Agent Host'
        Write-Host '  1. Remote Services'
        Write-Host '  2. Agent'
        Write-Host '  3. Configuration'
        Write-Host '  4. System'
        Write-Host '  5. Help'
        Write-Host '  0. Back / Exit'
        $choice = Read-FrpInteractiveLine -Prompt 'Select: ' -NoCompletion
        if ($null -eq $choice -or $choice -eq '0' -or $choice -ieq 'exit') { return }
        switch ($choice) {
            '1' {
                Write-Host '  1. List Remote Services'
                Write-Host '  2. Create / edit Remote Service'
                Write-Host '  3. Show Remote Service'
                Write-Host '  4. Remove Remote Service'
                Write-Host '  0. Back'
                $action = Read-FrpInteractiveLine -Prompt 'Select: ' -NoCompletion
                if ($null -eq $action) { return }
                switch ($action) {
                    '1' { Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @('show','remote-services') }
                    '2' { Invoke-FrpInteractiveRemoteWizard -Entry $Entry }
                    { $_ -in @('3','4') } {
                        $name = Read-FrpInteractiveLine -Prompt 'Remote Service name: ' -NoCompletion
                        if ($name) {
                            $verb = if ($action -eq '3') {'show'} else {'unset'}
                            Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @($verb,'remote-service',$name)
                        }
                    }
                }
            }
            '2' { Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @('show','agent') }
            '3' {
                Write-Host '  1. Test configuration'
                Write-Host '  2. Export configuration'
                Write-Host '  3. Diff configuration'
                Write-Host '  4. Apply configuration'
                Write-Host '  0. Back'
                $action = Read-FrpInteractiveLine -Prompt 'Select: ' -NoCompletion
                if ($null -eq $action) { return }
                if ($action -in @('1','2','3','4')) {
                    $file = Read-FrpInteractiveLine -Prompt 'Configuration file: ' -NoCompletion
                    if ($file) {
                        if ($action -eq '1') { Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @('test','configuration',$file) }
                        else {
                            $op = @{'2'='export';'3'='diff';'4'='apply'}[$action]
                            Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @('system',$op,'configuration',$file)
                        }
                    }
                }
            }
            '4' {
                $ops = @('info','version','diagnostics','synchronize','pause','resume','restart','autostart','autostart enable','autostart disable','update product','update engine','support-bundle','uninstall')
                for ($i=0; $i -lt $ops.Count; $i++) { Write-Host ("  {0}. {1}" -f ($i+1),$ops[$i]) }
                Write-Host '  0. Back'
                $action = Read-FrpInteractiveLine -Prompt 'Select: ' -NoCompletion
                if ($null -eq $action) { return }
                $number = 0
                if ([int]::TryParse($action,[ref]$number) -and $number -gt 0 -and $number -le $ops.Count) {
                    Invoke-FrpInteractiveCommand -Entry $Entry -Tokens (@('system') + $ops[$number-1].Split(' '))
                }
            }
            '5' { Invoke-FrpInteractiveCommand -Entry $Entry -Tokens @('help') }
            default { Write-Host 'Invalid selection.' }
        }
    }
}

function Invoke-FrpInteractive {
    param([string]$Entry)
    Write-Host ("Data Relay Link: {0}" -f (Get-FrpProjectVersion))
    Write-Host 'Role: DRLink Agent Host'
    Write-Host ''
    Write-Host "Type '?' for commands, 'menu' for guided menu, or 'exit' to leave."
    Write-Host 'Press Tab to complete commands and Remote Service names.'
    while ($true) {
        $line = Read-FrpInteractiveLine
        if ($null -eq $line) { return }
        if (-not $line.Trim()) { continue }
        try { $tokens = @(Split-FrpInteractiveLine $line) } catch { Write-Host $_.Exception.Message; continue }
        if ($tokens.Count -eq 1 -and $tokens[0] -ieq 'exit') { return }
        if ($tokens.Count -eq 1 -and $tokens[0] -ieq 'menu') { Invoke-FrpInteractiveMenu -Entry $Entry; continue }
        if ($tokens.Count -in @(2,3) -and $tokens[0] -ieq 'set' -and $tokens[1] -ieq 'remote-service' -and ($tokens.Count -eq 2 -or $tokens[2] -ne '?')) {
            $name = if ($tokens.Count -eq 3) {$tokens[2]} else {''}
            Invoke-FrpInteractiveRemoteWizard -Entry $Entry -Name $name
            continue
        }
        Invoke-FrpInteractiveCommand -Entry $Entry -Tokens $tokens
    }
}
