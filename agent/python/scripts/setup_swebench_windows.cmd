@echo off
REM Bypasses PowerShell execution policy. Run as Administrator.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_swebench_windows.ps1"
exit /b %ERRORLEVEL%
