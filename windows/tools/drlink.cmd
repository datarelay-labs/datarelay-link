@echo off
REM drlink.cmd — canonical Data Relay Link Windows CLI identity.
REM DRLINK-PRODUCT-SHIM — ownership marker: uninstall removes only launchers carrying it.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0FrpClient.ps1" %*
