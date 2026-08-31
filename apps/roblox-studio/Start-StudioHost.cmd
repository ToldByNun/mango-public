@echo off
REM Silent-ish launcher for mango-studio-host (keeps a console for logs).
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-StudioHost.ps1" %*
