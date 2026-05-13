@echo off
REM GuLiCode desktop one-click launcher (Windows)
REM 双击或在 cmd 中执行此文件即可启动 GuLiCode 桌面端 dev 模式。

setlocal

set "ROOT=%~dp0"
set "GULICODE_DIR=%ROOT%GuLiCode"

if not exist "%GULICODE_DIR%\package.json" (
    echo [start-gulicode-desktop] 找不到 GuLiCode 目录: %GULICODE_DIR%
    exit /b 1
)

REM 1. 在 PATH 中找 bun
set "BUN="
for %%I in (bun.exe) do (
    if exist "%%~$PATH:I" set "BUN=%%~$PATH:I"
)

REM 2. 常见安装位置
if "%BUN%"=="" if exist "%USERPROFILE%\.bun\bin\bun.exe" set "BUN=%USERPROFILE%\.bun\bin\bun.exe"
if "%BUN%"=="" if exist "%LOCALAPPDATA%\Programs\bun\bun.exe" set "BUN=%LOCALAPPDATA%\Programs\bun\bun.exe"

if "%BUN%"=="" (
    echo [start-gulicode-desktop] 未找到 bun，请先安装 Bun:
    echo     powershell -c "irm bun.com/install.ps1 ^| iex"
    exit /b 1
)

cd /d "%GULICODE_DIR%" || exit /b 1
"%BUN%" run desktop %*
exit /b %ERRORLEVEL%
