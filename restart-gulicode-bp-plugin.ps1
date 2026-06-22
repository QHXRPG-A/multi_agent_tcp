param(
    [string]$BlueprintId = "default",
    [string]$ProjectDir = "",
    [switch]$NoOpen,
    [switch]$Install,
    [switch]$SkipWebBuild,
    [switch]$SyncFrameworkAssets,
    [int]$HealthTimeoutSeconds = 45,
    [string]$LogFile = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectDir)) {
    $ProjectRoot = $Root
} else {
    $rawProjectDir = $ProjectDir
    if (-not [System.IO.Path]::IsPathRooted($rawProjectDir)) {
        $rawProjectDir = Join-Path $Root $rawProjectDir
    }
    if (-not (Test-Path -LiteralPath $rawProjectDir -PathType Container)) {
        throw ("ProjectDir does not exist: {0}" -f $ProjectDir)
    }
    $ProjectRoot = (Resolve-Path -LiteralPath $rawProjectDir).Path
}
$PersonalPluginRoot = Join-Path $HOME "plugins\gulicode-bp"
$StateDir = Join-Path $PersonalPluginRoot ".runtime\state"
$StartScript = Join-Path $Root "start-gulicode-debug.ps1"
$SyncFrameworkAssetsScript = Join-Path $Root "sync-gulicode-bp-framework-assets.ps1"
$RepoReadyFile = Join-Path $ProjectRoot "logs\gulicode-bp-workbench-ready.json"
$LogDir = Join-Path $Root "logs"

if ($HealthTimeoutSeconds -lt 1) {
    throw "HealthTimeoutSeconds must be at least 1."
}

if ([string]::IsNullOrWhiteSpace($LogFile)) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogFile = Join-Path $LogDir ("restart-gulicode-bp-plugin-{0}.log" -f $timestamp)
} elseif (-not [System.IO.Path]::IsPathRooted($LogFile)) {
    $LogFile = Join-Path $Root $LogFile
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogFile) | Out-Null
$script:RestartLogFile = [System.IO.Path]::GetFullPath($LogFile)
$script:TranscriptStarted = $false
try {
    Start-Transcript -Path $script:RestartLogFile -Force | Out-Null
    $script:TranscriptStarted = $true
} catch {
    Write-Host ("[restart-gulicode-bp-plugin] failed to start transcript: {0}" -f $_.Exception.Message)
}

trap {
    Write-Host ("[restart-gulicode-bp-plugin] failed: {0}" -f $_.Exception.Message)
    Write-Host ("[restart-gulicode-bp-plugin] log = {0}" -f $script:RestartLogFile)
    if ($script:TranscriptStarted) {
        try {
            Stop-Transcript | Out-Null
        } catch {
        }
        $script:TranscriptStarted = $false
    }
    exit 1
}

$env:NO_PROXY = "127.0.0.1,localhost,::1"
$env:no_proxy = $env:NO_PROXY

function Test-ContainsText {
    param(
        [string]$Text,
        [string]$Needle
    )
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $false
    }
    return $Text.IndexOf($Needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
}

function Test-PluginProcess {
    param([object]$ProcessInfo)

    $commandLine = [string]$ProcessInfo.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    if ((Test-ContainsText $commandLine $PersonalPluginRoot) -and (
        (Test-ContainsText $commandLine "\mcp\gulicode_bp_mcp.py") -or
        (Test-ContainsText $commandLine "\scripts\bootstrap_mcp.py") -or
        (Test-ContainsText $commandLine "\scripts\start_workbench.py") -or
        (Test-ContainsText $commandLine "-m multi_agent_tcp.popo_agent_bot_run")
    )) {
        return $true
    }

    return (
        (Test-ContainsText $commandLine "-m multi_agent_tcp collaboration-server") -and
        (Test-ContainsText $commandLine $StateDir)
    )
}

function Test-RepoLocalStaleServiceProcess {
    param([object]$ProcessInfo)

    $commandLine = [string]$ProcessInfo.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    $repoService = Join-Path $Root "plugins\gulicode-bp\mcp\gulicode_bp_mcp.py"
    return (
        (Test-ContainsText $commandLine $repoService) -and
        (Test-ContainsText $commandLine "--service")
    )
}

function Test-PluginClusterProcess {
    param([object]$ProcessInfo)

    $commandLine = [string]$ProcessInfo.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    if (-not (Test-ContainsText $commandLine $PersonalPluginRoot)) {
        return $false
    }
    if (-not (Test-ContainsText $commandLine "multi_agent_tcp_cluster")) {
        return $false
    }

    return (
        (Test-ContainsText $commandLine "-m multi_agent_tcp broker") -or
        (Test-ContainsText $commandLine "-m multi_agent_tcp agent")
    )
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    if ($ProcessId -le 0 -or $ProcessId -eq $PID) {
        return
    }

    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        & $env:ComSpec /d /c "taskkill.exe /PID $ProcessId /T /F >NUL 2>NUL"
        if ($LASTEXITCODE -eq 0) {
            return
        }
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-PluginProcesses {
    $targets = @()
    foreach ($process in Get-CimInstance Win32_Process) {
        if ($process.Name -like "python*.exe" -and (
            (Test-PluginProcess $process) -or
            (Test-RepoLocalStaleServiceProcess $process) -or
            (Test-PluginClusterProcess $process)
        )) {
            $targets += $process
        }
    }

    $targets = $targets | Sort-Object ProcessId -Unique
    if (-not $targets) {
        Write-Host "[restart-gulicode-bp-plugin] no plugin-owned Python processes found"
        return
    }

    $targetByPid = @{}
    foreach ($target in $targets) {
        $targetByPid[[int]$target.ProcessId] = $true
    }
    $rootTargets = @()
    foreach ($target in $targets) {
        $parentPid = [int]($target.ParentProcessId -as [int])
        if (-not $targetByPid.ContainsKey($parentPid)) {
            $rootTargets += $target
        }
    }
    $rootTargets = $rootTargets | Sort-Object ProcessId -Unique

    Write-Host ("[restart-gulicode-bp-plugin] stopping {0} plugin-owned Python process(es), {1} root tree(s)" -f $targets.Count, $rootTargets.Count)
    foreach ($target in ($rootTargets | Sort-Object ProcessId -Descending)) {
        Write-Host ("[restart-gulicode-bp-plugin] stop tree pid={0} {1}" -f $target.ProcessId, $target.Name)
        Stop-ProcessTree -ProcessId ([int]$target.ProcessId)
    }
}

function Remove-RuntimeMetadata {
    $files = @(
        (Join-Path $StateDir "service.lock"),
        (Join-Path $StateDir "service.json"),
        (Join-Path $StateDir "workbench_ready.json"),
        (Join-Path $StateDir "mcp_status.json"),
        (Join-Path $StateDir "popo_service.json"),
        $RepoReadyFile
    )

    foreach ($file in $files) {
        if (Test-Path -LiteralPath $file) {
            Remove-Item -LiteralPath $file -Force
            Write-Host ("[restart-gulicode-bp-plugin] removed {0}" -f $file)
        }
    }
}

function Wait-ListeningPortFree {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $listener) {
            return $true
        }
        Start-Sleep -Milliseconds 300
    }
    return $false
}

function Invoke-HttpCheck {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )

    $attempts = 0
    $lastDetail = "no response"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $attempts += 1
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host ("[restart-gulicode-bp-plugin] {0} = {1} {2} attempts={3}" -f $Name, $response.StatusCode, $Url, $attempts)
                return [pscustomobject]@{
                    Name = $Name
                    Url = $Url
                    Ok = $true
                    StatusCode = [int]$response.StatusCode
                    Attempts = $attempts
                    LastDetail = ("HTTP {0}" -f $response.StatusCode)
                }
            }
            $lastDetail = ("HTTP {0}" -f $response.StatusCode)
        } catch {
            if ($_.Exception.Response) {
                $status = [int]$_.Exception.Response.StatusCode
                $lastDetail = ("HTTP {0}" -f $status)
                if ($status -ge 200 -and $status -lt 500) {
                    Write-Host ("[restart-gulicode-bp-plugin] {0} = {1} {2} attempts={3}" -f $Name, $status, $Url, $attempts)
                    return [pscustomobject]@{
                        Name = $Name
                        Url = $Url
                        Ok = $true
                        StatusCode = $status
                        Attempts = $attempts
                        LastDetail = $lastDetail
                    }
                }
            } else {
                $lastDetail = $_.Exception.Message
            }
        }
        Start-Sleep -Milliseconds 500
    }

    Write-Host ("[restart-gulicode-bp-plugin] {0} = failed {1} timeout={2}s attempts={3} last={4}" -f $Name, $Url, $TimeoutSeconds, $attempts, $lastDetail)
    return [pscustomobject]@{
        Name = $Name
        Url = $Url
        Ok = $false
        StatusCode = $null
        Attempts = $attempts
        LastDetail = $lastDetail
    }
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

if (-not (Test-Path -LiteralPath $StartScript -PathType Leaf)) {
    throw ("Missing start script: {0}" -f $StartScript)
}
if ($SyncFrameworkAssets -and -not (Test-Path -LiteralPath $SyncFrameworkAssetsScript -PathType Leaf)) {
    throw ("Missing framework assets sync script: {0}" -f $SyncFrameworkAssetsScript)
}
if (-not (Test-Path -LiteralPath $PersonalPluginRoot -PathType Container)) {
    throw ("Installed personal plugin was not found: {0}" -f $PersonalPluginRoot)
}

Write-Host ("[restart-gulicode-bp-plugin] root = {0}" -f $Root)
Write-Host ("[restart-gulicode-bp-plugin] project = {0}" -f $ProjectRoot)
Write-Host ("[restart-gulicode-bp-plugin] personal plugin = {0}" -f $PersonalPluginRoot)
Write-Host ("[restart-gulicode-bp-plugin] log = {0}" -f $script:RestartLogFile)
Write-Host ("[restart-gulicode-bp-plugin] health timeout = {0}s" -f $HealthTimeoutSeconds)

Stop-PluginProcesses
Start-Sleep -Seconds 2
Remove-RuntimeMetadata

foreach ($port in @(3100, 8787)) {
    if (-not (Wait-ListeningPortFree -Port $port -TimeoutSeconds 10)) {
        $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        $owners = ($listeners | ForEach-Object { [string]$_.OwningProcess }) -join ", "
        throw ("Port {0} is still occupied by pid(s): {1}" -f $port, $owners)
    }
}

if ($SyncFrameworkAssets) {
    Write-Host "[restart-gulicode-bp-plugin] syncing framework assets into installed runtime"
    Invoke-Checked -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $SyncFrameworkAssetsScript,
        "-PluginRoot",
        $PersonalPluginRoot
    ) -WorkingDirectory $Root
}

$startArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $StartScript,
    "-BlueprintId",
    $BlueprintId,
    "-ProjectDir",
    $ProjectRoot
)

if ($NoOpen) {
    $startArgs += "-NoOpen"
}
if (-not $Install) {
    $startArgs += "-SkipPluginInstall"
} elseif ($SkipWebBuild) {
    $startArgs += "-SkipWebBuild"
}

Write-Host "[restart-gulicode-bp-plugin] starting plugin stack"
Invoke-Checked -FilePath "powershell.exe" -ArgumentList $startArgs -WorkingDirectory $Root

$serviceJsonPath = Join-Path $StateDir "service.json"
$readyPayload = $null
$servicePayload = $null
if (Test-Path -LiteralPath $RepoReadyFile) {
    $readyPayload = Get-Content -Raw -LiteralPath $RepoReadyFile | ConvertFrom-Json
}
if (Test-Path -LiteralPath $serviceJsonPath) {
    $servicePayload = Get-Content -Raw -LiteralPath $serviceJsonPath | ConvertFrom-Json
}

$collaborationHealth = Invoke-HttpCheck "collaboration" "http://127.0.0.1:8787/api/health" $HealthTimeoutSeconds
$popoHealth = Invoke-HttpCheck "popo" "http://127.0.0.1:3100/health" $HealthTimeoutSeconds
$healthOk = [bool]$collaborationHealth.Ok -and [bool]$popoHealth.Ok

$servicePid = if ($servicePayload) { $servicePayload.pid } else { "" }
$workbenchUrl = if ($readyPayload) { $readyPayload.url } else { "" }

Write-Host ("[restart-gulicode-bp-plugin] service pid = {0}" -f $servicePid)
Write-Host ("[restart-gulicode-bp-plugin] workbench = {0}" -f $workbenchUrl)
Write-Host ("[restart-gulicode-bp-plugin] health ok = {0}" -f $healthOk)

if (-not $healthOk) {
    $failed = @($collaborationHealth, $popoHealth) |
        Where-Object { -not $_.Ok } |
        ForEach-Object { "{0} {1} last={2} attempts={3}" -f $_.Name, $_.Url, $_.LastDetail, $_.Attempts }
    throw ("Post-restart health check failed: {0}" -f ($failed -join "; "))
}

if ($script:TranscriptStarted) {
    try {
        Stop-Transcript | Out-Null
    } catch {
        Write-Host ("[restart-gulicode-bp-plugin] failed to stop transcript: {0}" -f $_.Exception.Message)
    }
    $script:TranscriptStarted = $false
}
