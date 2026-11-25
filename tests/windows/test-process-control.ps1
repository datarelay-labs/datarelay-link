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
        # Exercise a genuine console-subsystem executable, just like frpc.
        # A detached PowerShell host can exit before executing a script when
        # it has no usable console. Do not use that as the process oracle.
        $src = Join-Path $env:FRP_WINDOWS_ROOT 'console-probe.cs'
        $exe = Join-Path $env:FRP_WINDOWS_ROOT 'console-probe.exe'
        $result = Join-Path $env:FRP_WINDOWS_ROOT 'console-probe.txt'
        @'
using System;
using System.IO;
using System.Runtime.InteropServices;
public static class ConsoleProbe {
    [DllImport("kernel32.dll")]
    private static extern IntPtr GetConsoleWindow();
    public static int Main(string[] args) {
        File.WriteAllText(args[0], (GetConsoleWindow() == IntPtr.Zero).ToString());
        return 0;
    }
}
'@ | Set-Content -LiteralPath $src -Encoding ASCII
        $csc = @(
            (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
            (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
        ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        Assert-FrpTrue ([bool]$csc) 'Windows console fixture compiler available'
        & $csc /nologo /target:exe "/out:$exe" $src
        Assert-FrpEqual 0 $LASTEXITCODE 'console fixture compiled'
        $baseline = Join-Path $env:FRP_WINDOWS_ROOT 'console-probe-baseline.txt'
        & $exe $baseline
        Assert-FrpEqual 0 $LASTEXITCODE 'console fixture can execute'
        Assert-FrpTrue (Test-Path -LiteralPath $baseline) 'console fixture writes result'
        $command = '"{0}" "{1}"' -f $exe, $result
        $created = Start-FrpDetachedProcess -CommandLine $command -WorkingDirectory $env:FRP_WINDOWS_ROOT
        Assert-FrpEqual 0 ([int]$created.ReturnValue) 'native detached process created'
        Assert-FrpTrue ([int]$created.ProcessId -gt 0) 'native process id returned'
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
