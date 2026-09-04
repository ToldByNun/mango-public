@echo off
setlocal EnableExtensions
title Mango Studio Host
cd /d "%~dp0"

echo.
echo  === Mango for Roblox Studio ===
echo.

echo [1/2] Installing local Studio plugin...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-StudioPlugin.ps1"
if errorlevel 1 (
  echo Plugin install failed.
  pause
  exit /b 1
)

echo.
echo [2/2] Starting mango-studio-host on http://127.0.0.1:17880
echo       Keep this window open while using the Mango panel in Studio.
echo       Close the window to stop the host.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-StudioHost.ps1" %*
set "EC=%ERRORLEVEL%"
echo.
echo Host exited with code %EC%.
pause
exit /b %EC%
