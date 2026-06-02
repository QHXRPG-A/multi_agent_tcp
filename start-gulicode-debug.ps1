param(
    [switch]$NoOpen,
    [string]$BlueprintId = "default",
    [switch]$SkipPluginInstall,
    [switch]$SkipWebBuild
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $Root "GuLiCode\packages\app"
$PluginRoot = Join-Path $Root "plugins\gulicode-bp"
$PersonalPluginRoot = Join-Path $HOME "plugins\gulicode-bp"
$PluginInstaller = Join-Path $PluginRoot "scripts\install_personal_plugin.py"
$WorkbenchScript = Join-Path $PluginRoot "scripts\start_workbench.py"
$PersonalWorkbenchScript = Join-Path $PersonalPluginRoot "scripts\start_workbench.py"
$SeedConfig = Join-Path $Root "examples\collaboration_server_debug_seed.json"
$LogDir = Join-Path $Root "logs"
$ReadyFile = Join-Path $LogDir "gulicode-bp-workbench-ready.json"
$WorkbenchOut = Join-Path $LogDir "gulicode-bp-workbench.out.log"
$WorkbenchErr = Join-Path $LogDir "gulicode-bp-workbench.err.log"

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

function Start-WorkbenchProcess {
    param(
        [string[]]$ArgumentList
    )
    foreach ($path in @($WorkbenchOut, $WorkbenchErr)) {
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    $process = Start-Process `
        -FilePath "python" `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $WorkbenchOut `
        -RedirectStandardError $WorkbenchErr `
        -PassThru
    Write-Host ("[start-gulicode-debug] started blueprint workbench pid={0}" -f $process.Id)
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

function Wait-WorkbenchReady {
    param(
        [string]$Path,
        [int]$TimeoutSeconds = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $Path) {
            try {
                $raw = Get-Content -Raw -LiteralPath $Path
                if ($raw.Trim().Length -gt 0) {
                    $payload = $raw | ConvertFrom-Json
                    if ($payload.ok -eq $false) {
                        throw ("blueprint workbench failed: {0}" -f $payload.error)
                    }
                    return $payload
                }
            } catch {
                if ((Get-Date) -ge $deadline) {
                    throw
                }
            }
        }
        Start-Sleep -Milliseconds 500
    }
    throw ("Timed out waiting for blueprint workbench. See {0} and {1}" -f $WorkbenchOut, $WorkbenchErr)
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory
    )
    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw ("Command failed with exit code {0}: {1}" -f $LASTEXITCODE, $FilePath)
    }
}

Write-Host ("[start-gulicode-debug] root = {0}" -f $Root)
Write-Host "[start-gulicode-debug] mode = plugin workbench + mobile + console; Electron desktop is not started"

if (-not (Test-Path $PluginInstaller)) {
    throw ("Missing plugin installer: {0}" -f $PluginInstaller)
}
if (-not (Test-Path $WorkbenchScript)) {
    throw ("Missing workbench launcher: {0}" -f $WorkbenchScript)
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (Test-Path $ReadyFile) {
    Remove-Item -LiteralPath $ReadyFile -Force
}

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
    Write-Host "[start-gulicode-debug] singleton plugin service will start the collaboration server on demand"
}

if (-not $SkipPluginInstall) {
    $installArgs = @($PluginInstaller, "--force")
    if ($SkipWebBuild) {
        $installArgs += "--skip-web-build"
    }
    Write-Host "[start-gulicode-debug] refreshing gulicode-bp personal plugin"
    Invoke-Checked -FilePath "python" -ArgumentList $installArgs -WorkingDirectory $Root
} else {
    Write-Host "[start-gulicode-debug] skipping personal plugin refresh"
}

if (Test-Path $PersonalWorkbenchScript) {
    $WorkbenchScript = $PersonalWorkbenchScript
    Write-Host ("[start-gulicode-debug] using personal plugin workbench wrapper = {0}" -f $WorkbenchScript)
}

if (Test-ListeningPort 3040) {
    Write-Host "[start-gulicode-debug] app dev server already listening on 3040"
} else {
    Start-BackgroundProcess -Name "app dev server" -FilePath "bun" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1") -WorkingDirectory $AppDir
}

$workbenchArgs = @(
    "-u",
    $WorkbenchScript,
    "--project-dir",
    $Root,
    "--blueprint-id",
    $BlueprintId,
    "--ready-file",
    $ReadyFile
)
Start-WorkbenchProcess -ArgumentList $workbenchArgs

$workbench = Wait-WorkbenchReady -Path $ReadyFile -TimeoutSeconds 45

$healthOk = Wait-Http "http://127.0.0.1:8787/api/health" 30
$mobileOk = Wait-Http "http://127.0.0.1:3040/mobile" 45
$consoleOk = Wait-Http "http://127.0.0.1:3040/console" 45
$workbenchOk = Wait-Http $workbench.url 45

Write-Host ("[start-gulicode-debug] health    = {0}" -f $healthOk)
Write-Host ("[start-gulicode-debug] workbench = {0} {1}" -f $workbenchOk, $workbench.url)
Write-Host ("[start-gulicode-debug] mobile    = {0} http://127.0.0.1:3040/mobile" -f $mobileOk)
Write-Host ("[start-gulicode-debug] console   = {0} http://127.0.0.1:3040/console" -f $consoleOk)
Write-Host "[start-gulicode-debug] desktop   = skipped"

if (-not $NoOpen) {
    Start-Process $workbench.url
    Start-Process "http://127.0.0.1:3040/mobile"
    Start-Process "http://127.0.0.1:3040/console"
}
