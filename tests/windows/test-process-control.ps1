# test-process-control.ps1 — may skip if no frpc
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot '_import.ps1')
try {
    Clear-FrpStalePid
    $st = Get-FrpClientStatus
    Assert-FrpTrue (-not $st.Running) 'not running'

    if (-not (Test-FrpIsWindowsHost)) {
        $env:FRP_WINDOWS_ALLOW_FAKE_PROCESS = '1'
        # Minimal toml so Start-FrpClient proceeds past config check
        New-Item -ItemType Directory -Path (Get-FrpConfigDir) -Force | Out-Null
        Set-Content -LiteralPath (Get-FrpTomlPath) -Value "serverAddr = `"127.0.0.1`"`n"
        New-Item -ItemType Directory -Path (Get-FrpBinDir) -Force | Out-Null
        Set-Content -LiteralPath (Get-FrpFrpcPath) -Value 'dummy'
        $pid1 = Start-FrpClient
        $st2 = Get-FrpClientStatus
        Assert-FrpTrue $st2.Running 'fake running'
        # Idempotent start
        $pid2 = Start-FrpClient
        Assert-FrpEqual $pid1 $pid2 'idempotent start'
        Stop-FrpClient | Out-Null
        Assert-FrpTrue (-not (Get-FrpClientStatus).Running) 'stopped'
        # Idempotent stop
        Stop-FrpClient | Out-Null
        Write-FrpTestPass 'test-process-control (fake)'
    } else {
        $probe = Join-Path $env:FRP_WINDOWS_ROOT 'console-probe.ps1'
        $result = Join-Path $env:FRP_WINDOWS_ROOT 'console-probe.txt'
        @'
param([string]$Result)
Add-Type -Name ConsoleProbe -Namespace DRLinkTest -MemberDefinition '[System.Runtime.InteropServices.DllImport("kernel32.dll")] public static extern System.IntPtr GetConsoleWindow();'
[IO.File]::WriteAllText($Result, [string]([DRLinkTest.ConsoleProbe]::GetConsoleWindow() -eq [IntPtr]::Zero))
'@ | Set-Content -LiteralPath $probe -Encoding ASCII
        $exe = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $command = '"{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}" -Result "{2}"' -f $exe, $probe, $result
        $created = Start-FrpDetachedProcess -CommandLine $command -WorkingDirectory $env:FRP_WINDOWS_ROOT
        Assert-FrpEqual 0 ([int]$created.ReturnValue) 'native detached process created'
        $deadline = [DateTime]::UtcNow.AddSeconds(30)
        while (-not (Test-Path -LiteralPath $result) -and [DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 200
        }
        Assert-FrpTrue (Test-Path -LiteralPath $result) 'native console probe ran'
        Assert-FrpEqual 'True' ([IO.File]::ReadAllText($result)) 'no console allocated'
        Write-FrpTestPass 'test-process-control (native no console)'
    }

    $procSrc = Get-Content -LiteralPath (Join-Path $script:WindowsLib 'FrpProcess.ps1') -Raw
    Assert-FrpTrue ($procSrc -match 'ProcessStartupInformation' -and $procSrc -match 'CreateFlags\s*=\s*\[uint32\]8') 'CIM startup prevents console creation'
    Assert-FrpTrue ($procSrc -match 'Win32_Process') 'starts frpc via Win32_Process.Create so SSH sessions do not reap it'
    Assert-FrpTrue ($procSrc -notmatch 'RedirectStandardOutput') 'does not redirect frpc stdio through Start-Process'
} finally {
    Remove-Item Env:FRP_WINDOWS_ALLOW_FAKE_PROCESS -ErrorAction SilentlyContinue
    Remove-FrpWindowsTestRoot
}
