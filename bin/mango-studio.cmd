@echo off
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
call "%ROOT%\apps\roblox-studio\MangoStudio.cmd" %*
exit /b %ERRORLEVEL%
