@echo off
setlocal
REM A PS7 -> cmd.exe -> Windows PowerShell chain inherits PS7 module paths.
REM Rebuild defaults in the child engine; do not change the caller environment.
set "PSModulePath="
REM drlink.cmd — canonical Data Relay Link Windows CLI identity.
REM DRLINK-PRODUCT-SHIM — ownership marker: uninstall removes only launchers carrying it.
REM PowerShell 5.1 -File rejects a standalone dash before invoking the script.
REM Transport only the three canonical stdin forms as named literal values.
if /I "%~1"=="test" if /I "%~2"=="configuration" if "%~3"=="-" goto stdin_test
if /I "%~1"=="system" if /I "%~2"=="diff" if /I "%~3"=="configuration" if "%~4"=="-" goto stdin_diff
if /I "%~1"=="system" if /I "%~2"=="apply" if /I "%~3"=="configuration" if "%~4"=="-" goto stdin_apply
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0FrpClient.ps1" %*
exit /b %errorlevel%
:stdin_test
if not "%4"=="" goto extra_arguments
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0FrpClient.ps1" test configuration -Id:-
exit /b %errorlevel%
:stdin_diff
if not "%5"=="" goto extra_arguments
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0FrpClient.ps1" system diff configuration -Property:-
exit /b %errorlevel%
:stdin_apply
if not "%5"=="" goto extra_arguments
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0FrpClient.ps1" system apply configuration -Property:-
exit /b %errorlevel%
:extra_arguments
echo ERROR: unexpected extra arguments.
exit /b 2
