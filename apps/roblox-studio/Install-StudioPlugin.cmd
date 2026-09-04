@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-StudioPlugin.ps1"
exit /b %ERRORLEVEL%
