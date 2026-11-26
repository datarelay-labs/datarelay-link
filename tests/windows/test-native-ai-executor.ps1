# Native Win32 paths/handles, signed worker dispatch, and bounded commands.
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    Assert-FrpTrue (-not (Get-FrpAiExecutorProfile)) 'fresh install does not opt in'
    Assert-FrpEqual 'C:/Data/report.txt' (ConvertTo-FrpAiWindowsPath 'c:\Data\report.txt') 'native path canonical form'
    foreach ($bad in @('C:relative','\\server\share\file','\\?\C:\Data\file','C:/Data/../file','C:/Data/file:stream','C:/Data/NUL.txt','C:/Data/COM1.log','C:/Data/CONIN$','C:/Data/report.','C:/Data/report ','C:/Data/%2e%2e/file','C:/Data/SHORT~1','C:/Data//file','C:/Data/*.txt')) {
        Assert-FrpTrue (-not (Test-FrpAiWindowsPathScope $bad @('/**'))) ('reject unsafe path '+$bad)
    }
    Assert-FrpTrue (Test-FrpAiWindowsPathScope 'C:/Data/a.txt' @('C:/Data/**')) 'in scope'
    Assert-FrpTrue (-not (Test-FrpAiWindowsPathScope 'C:/Data-other/a.txt' @('C:/Data/**'))) 'component boundary'
    Assert-FrpTrue (-not (Test-FrpAiWindowsPathScope 'C:/data/a.txt' @('C:/Data/**'))) 'case-sensitive scope'
    Assert-FrpTrue (-not (Test-FrpAiWindowsPathScope 'C:/Data/a.txt' @('/Data/**'))) 'no POSIX scope reinterpretation'
    # Compile Win32 helper declarations on every PS engine; only execute on Windows.
    $source=Get-Content -LiteralPath (Join-Path $script:WindowsLib 'FrpAiExecutor.ps1') -Raw
    foreach($match in [regex]::Matches($source,"(?s)Add-Type -TypeDefinition @'\r?\n(.*?)\r?\n'@ -ErrorAction Stop")) {
        Add-Type -TypeDefinition $match.Groups[1].Value -ErrorAction Stop
    }
    Assert-FrpTrue ([bool]('Drlink.NativeAiFiles' -as [type])) 'file helper compiled'
    Assert-FrpTrue ([bool]('Drlink.NativeAiCommand' -as [type])) 'command helper compiled'
    if (Test-FrpIsWindowsHost) {
        $root = ConvertTo-FrpAiWindowsPath (Get-FrpWindowsRoot)
        $dir = Join-Path (Get-FrpWindowsRoot) 'ai-fixture'
        New-Item -ItemType Directory -Path $dir | Out-Null
        $local = ConvertTo-FrpAiWindowsPath $dir
        $profile=[pscustomobject]@{Patterns=@($local+'/**');AllowCommandExec=$false}
        $path=$local+'/sample.txt'
        function Job($cap,$jobArgs,$patterns=@('/**')) {
            return @{capability=$cap;arguments=$jobArgs;patterns=$patterns;timeout=10;deadline_at=[DateTimeOffset]::UtcNow.AddSeconds(30).ToString('o')}
        }
        $result=Invoke-FrpNativeAiJob (Job 'write_file' @{path=$path;content='first'}) $profile
        Assert-FrpEqual 5 $result.bytes 'native file creation'
        $read=Invoke-FrpNativeAiJob (Job 'read_file' @{path=$path}) $profile
        Assert-FrpEqual 'first' ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($read.content_b64))) 'native read'
        $aclBefore=(Get-Acl -LiteralPath (Join-Path $dir 'sample.txt')).Sddl
        $result=Invoke-FrpNativeAiJob (Job 'write_file' @{path=$path;content='second'}) $profile
        Assert-FrpEqual 6 $result.bytes 'native overwrite'
        Assert-FrpEqual $aclBefore (Get-Acl -LiteralPath (Join-Path $dir 'sample.txt')).Sddl 'overwrite preserves ACL'
        Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob (Job 'read_file' @{path=$path} @('C:/NoSuchScope/**')) $profile).result 'server scope denied'
        Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob (Job 'write_file' @{path=($root+'/outside.txt');content='no'}) $profile).result 'local scope denied'
        Assert-FrpTrue (-not (Test-Path -LiteralPath (Join-Path (Get-FrpWindowsRoot) 'outside.txt'))) 'denied write has no effect'
        # A native hard link and directory junction must not escape the policy.
        $outside=Join-Path (Get-FrpWindowsRoot) 'outside-real.txt'
        Set-Content -LiteralPath $outside -Value 'outside'
        $hard=Join-Path $dir 'hardlink.txt'
        New-Item -ItemType HardLink -Path $hard -Target $outside -ErrorAction Stop | Out-Null
        Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob (Job 'read_file' @{path=($local+'/hardlink.txt')}) $profile).result 'hardlink read denied'
        Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob (Job 'write_file' @{path=($local+'/hardlink.txt');content='no'}) $profile).result 'hardlink write denied'
        $junction=Join-Path $dir 'junction'
        New-Item -ItemType Junction -Path $junction -Target (Get-FrpWindowsRoot) -ErrorAction Stop | Out-Null
        try {
            Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob (Job 'read_file' @{path=($local+'/junction/outside-real.txt')}) $profile).result 'junction traversal denied'
        } finally {
            # Remove only the fixture link, not its target.
            [IO.Directory]::Delete($junction)
        }
        Assert-FrpTrue ((Invoke-FrpNativeAiJob (Job 'delete_file' @{path=$path}) $profile).deleted) 'native delete'
        Assert-FrpTrue (-not (Test-Path -LiteralPath (Join-Path $dir 'sample.txt'))) 'delete effect'
        Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob (Job 'exec' @{command="Write-Output 'fixture'"}) $profile).result 'local command opt-in required'
        $profile.AllowCommandExec=$true
        $savedEncoding=[Console]::InputEncoding
        try {
            foreach ($encoding in @($savedEncoding,[Text.UTF8Encoding]::new($true),[Text.Encoding]::Unicode)) {
                [Console]::InputEncoding=$encoding
                $result=Invoke-FrpNativeAiJob (Job 'exec' @{command="Write-Output 'fixture'"}) $profile
                Assert-FrpEqual 0 $result.exit_status ("native bounded shell exit ("+$encoding.WebName+"): "+$result.stderr)
                Assert-FrpTrue ($result.stdout -match 'fixture') 'native shell output'
            }
        } finally { [Console]::InputEncoding=$savedEncoding }
        $expired=Job 'write_file' @{path=$path;content='late'}
        $expired.deadline_at=[DateTimeOffset]::UtcNow.AddSeconds(-1).ToString('o')
        Assert-FrpEqual 'DENY' (Invoke-FrpNativeAiJob $expired $profile).result 'expired job rejected'
        Assert-FrpTrue (-not (Test-Path -LiteralPath (Join-Path $dir 'sample.txt'))) 'expired job has no effect'
        Write-FrpTestPass 'native AI Windows filesystem and execution'
    } else { Write-Host 'NATIVE_OS_TESTS=NOT_RUN (non-Windows compile/path checks only)' }
    # The worker never claims without opt-in. Once a signed job is claimed,
    # revoke local authority before execution and acknowledge the DENY once.
    $script:profileCalls=0; $script:claims=0; $script:completions=0
    function Get-FrpAiExecutorProfile { $script:profileCalls++; if ($script:profileCalls -eq 2) { return [pscustomobject]@{Patterns=@();AllowCommandExec=$false} }; return $null }
    function Test-FrpIsEnrolled { return $true }
    function Invoke-FrpV24MgmtRequest {
        param($Method,$Path,$Body,$TimeoutSec)
        if ($Path -eq '/v1/ai-jobs/claim') {
            $script:claims++
            Assert-FrpEqual 'windows' $Body.platform 'signed native dialect claim'
            Assert-FrpEqual 1 $Body.limit 'bounded claim'
            return @{jobs=@(@{id='job_0123456789abcdef';claim_token='atk_fixture';attempt_id='att_0123456789abcdef';capability='get_system_info';deadline_at=[DateTimeOffset]::UtcNow.AddSeconds(30).ToString('o')})}
        }
        if ($Path -eq '/v1/ai-jobs/complete') {
            $script:completions++
            Assert-FrpEqual 'atk_fixture' $Body.claim_token 'claim token preserved'
            Assert-FrpEqual 'att_0123456789abcdef' $Body.attempt_id 'attempt preserved'
            Assert-FrpEqual 'DENY' $Body.result.result 'revoked local opt-in denies claimed work'
            return @{ok=$true}
        }
        throw 'Unexpected fixture request'
    }
    Assert-FrpTrue (-not (Invoke-FrpNativeAiWorkerStep)) 'disabled worker does not claim'
    Assert-FrpEqual 0 $script:claims 'no disabled transport claim'
    Assert-FrpTrue (Invoke-FrpNativeAiWorkerStep) 'signed job completion path'
    Assert-FrpEqual 1 $script:claims 'one claim'
    Assert-FrpEqual 1 $script:completions 'one completion without re-execution'
    Write-FrpTestPass 'test-native-ai-executor'
} finally { Remove-FrpWindowsTestRoot }
