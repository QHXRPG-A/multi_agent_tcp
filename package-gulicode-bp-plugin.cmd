@echo off
setlocal

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%package-gulicode-bp-plugin.ps1"

if not exist "%SCRIPT%" (
    echo [package-gulicode-bp-plugin] Missing script: %SCRIPT%
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
