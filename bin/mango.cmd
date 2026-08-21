@echo off
setlocal
set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PY=%ROOT%\agent\python\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo mango: not installed. Run:
  echo   %ROOT%\install.cmd
  exit /b 1
)
"%PY%" -m mango_cli %*
