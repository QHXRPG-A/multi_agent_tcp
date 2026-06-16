@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart-gulicode-bp-plugin.ps1" -SyncFrameworkAssets -SkipWebBuild -NoOpen %*
exit /b %ERRORLEVEL%
