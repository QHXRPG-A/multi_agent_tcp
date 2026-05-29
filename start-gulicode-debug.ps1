param(
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $Root "GuLiCode\packages\app"
$DesktopLauncher = Join-Path $Root "start-gulicode-desktop.cmd"
$SeedConfig = Join-Path $Root "examples\collaboration_server_debug_seed.json"

$env:NO_PROXY = "127.0.0.1,localhost,::1"
$env:no_proxy = $env:NO_PROXY

function Test-ListeningPort {
    param([int]$Port)
    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    return $null -ne $connection
}

function Test-MonitorRoute {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:8787/api/admin/monitor/users" -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            return $status -eq 401 -or $status -eq 403
        }
        return $false
    }
}

function Stop-StaleCollaborationServer {
    $connections = Get-NetTCPConnection -State Listen -LocalPort 8787 -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $ownerPid = [int]$connection.OwningProcess
        if ($ownerPid -le 0) {
            continue
        }
        $process = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ownerPid) -ErrorAction SilentlyContinue
        if ($null -eq $process -or $process.CommandLine -notlike "*multi_agent_tcp*collaboration-server*") {
            continue
        }
        Write-Host ("[start-gulicode-debug] stopping stale collaboration server pid={0}" -f $ownerPid)
        Stop-Process -Id $ownerPid -Force
    }
    Start-Sleep -Seconds 1
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ProcessId) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return ""
    }
    return [string]$process.CommandLine
}

function Get-GuLiCodeElectronMainProcess {
    $rootNeedle = (Join-Path $Root "GuLiCode").ToLowerInvariant()
    return Get-Process -Name electron -ErrorAction SilentlyContinue |
        Where-Object {
            $path = [string]$_.Path
            $title = [string]$_.MainWindowTitle
            $path.ToLowerInvariant().Contains($rootNeedle) -and $title -like "GuLiCode*"
        } |
        Select-Object -First 1
}

function Test-GuLiCodeDesktopBridge {
    $main = Get-GuLiCodeElectronMainProcess
    if ($null -eq $main) {
        return $false
    }
    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object {
            $_.OwningProcess -eq $main.Id -and
            ($_.LocalAddress -eq "127.0.0.1" -or $_.LocalAddress -eq "::1")
        }
    # Current desktop dev exposes both the sidecar and desktop-control bridge from the main process.
    return (($listeners | Measure-Object).Count -ge 2)
}

function Stop-StaleGuLiCodeDesktop {
    $rootNeedle = (Join-Path $Root "GuLiCode").ToLowerInvariant()
    $targets = New-Object System.Collections.Generic.HashSet[int]

    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $name = ([string]$_.Name).ToLowerInvariant()
            $exe = ([string]$_.ExecutablePath).ToLowerInvariant()
            $cmd = ([string]$_.CommandLine).ToLowerInvariant()
            (
                $name -like "electron*" -and $exe.Contains($rootNeedle)
            ) -or (
                ($name -eq "bun.exe" -or $name -eq "bun") -and
                ($cmd.Contains("packages\desktop-electron") -or $cmd.Contains("packages/desktop-electron") -or $cmd.Contains("scripts/dev-desktop.ts"))
            ) -or (
                $name -eq "cmd.exe" -and $cmd.Contains("start-gulicode-desktop.cmd")
            )
        } |
        ForEach-Object { [void]$targets.Add([int]$_.ProcessId) }

    foreach ($connection in (Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue)) {
        $ownerPid = [int]$connection.OwningProcess
        if ($ownerPid -le 0) {
            continue
        }
        $cmd = (Get-ProcessCommandLine $ownerPid).ToLowerInvariant()
        if ($cmd.Contains("packages\desktop-electron") -or $cmd.Contains("packages/desktop-electron") -or $cmd.Contains("electron-vite")) {
            [void]$targets.Add($ownerPid)
        }
    }

    foreach ($targetPid in $targets) {
        if ($targetPid -le 0) {
            continue
        }
        Write-Host ("[start-gulicode-debug] stopping stale GuLiCode desktop pid={0}" -f $targetPid)
        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
    }
    if ($targets.Count -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Start-BackgroundProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
    Write-Host ("[start-gulicode-debug] started {0} pid={1}" -f $Name, $process.Id)
}

function Wait-Http {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Write-Host ("[start-gulicode-debug] root = {0}" -f $Root)

if ((Test-ListeningPort 8787) -and (Test-MonitorRoute)) {
    Write-Host "[start-gulicode-debug] collaboration server already listening on 8787"
} else {
    if (Test-ListeningPort 8787) {
        Write-Host "[start-gulicode-debug] collaboration server is stale or missing /api/admin/monitor/users"
        Stop-StaleCollaborationServer
    }
    if (Test-ListeningPort 8787) {
        throw "Port 8787 is still occupied by a non-debug process."
    }
    $args = @(
        "-m",
        "multi_agent_tcp",
        "collaboration-server",
        "--host",
        "127.0.0.1",
        "--port",
        "8787",
        "--db",
        "logs/collaboration_server.sqlite3",
        "--seed-config",
        $SeedConfig,
        "--log-dir",
        "logs",
        "--log-level",
        "INFO"
    )
    Start-BackgroundProcess -Name "collaboration server" -FilePath "python" -ArgumentList $args -WorkingDirectory $Root
}

if (Test-ListeningPort 3040) {
    Write-Host "[start-gulicode-debug] app dev server already listening on 3040"
} else {
    Start-BackgroundProcess -Name "app dev server" -FilePath "bun" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1") -WorkingDirectory $AppDir
}

$desktopRendererReady = Test-ListeningPort 5173
$desktopBridgeReady = Test-GuLiCodeDesktopBridge
if ($desktopRendererReady -and $desktopBridgeReady) {
    Write-Host "[start-gulicode-debug] GuLiCode desktop already listening on 5173 with desktop bridge"
} else {
    if ($desktopRendererReady) {
        Write-Host "[start-gulicode-debug] desktop renderer is stale or missing desktop bridge"
        Stop-StaleGuLiCodeDesktop
    }
    Start-BackgroundProcess -Name "GuLiCode desktop" -FilePath $DesktopLauncher -ArgumentList @("--no-clean") -WorkingDirectory $Root
}

$healthOk = Wait-Http "http://127.0.0.1:8787/api/health" 30
$mobileOk = Wait-Http "http://127.0.0.1:3040/mobile" 45
$consoleOk = Wait-Http "http://127.0.0.1:3040/console" 45
$rendererOk = Wait-Http "http://localhost:5173/" 60

Write-Host ("[start-gulicode-debug] health  = {0}" -f $healthOk)
Write-Host ("[start-gulicode-debug] mobile  = {0} http://127.0.0.1:3040/mobile" -f $mobileOk)
Write-Host ("[start-gulicode-debug] console = {0} http://127.0.0.1:3040/console" -f $consoleOk)
Write-Host ("[start-gulicode-debug] desktop = {0} http://localhost:5173/" -f $rendererOk)

if (-not $NoOpen) {
    Start-Process "http://127.0.0.1:3040/mobile"
    Start-Process "http://127.0.0.1:3040/console"
}
