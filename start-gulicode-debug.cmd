@echo off
setlocal

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%start-gulicode-debug.ps1"

if not exist "%SCRIPT%" (
    echo [start-gulicode-debug] Missing script: %SCRIPT%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
