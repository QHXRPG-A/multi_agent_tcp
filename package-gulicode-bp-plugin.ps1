param(
    [string]$ReleaseDir = "",
    [switch]$SkipWebBuild,
    [switch]$NoSmoke,
    [switch]$SmokeInstalledPlugin,
    [int]$SmokeTimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginRoot = Join-Path $Root "plugins\gulicode-bp"
$PluginManifest = Join-Path $PluginRoot ".codex-plugin\plugin.json"
$PluginInstaller = Join-Path $PluginRoot "scripts\install_personal_plugin.py"
$StandaloneSmoke = Join-Path $PluginRoot "scripts\smoke_standalone_plugin.py"
$LogDir = Join-Path $Root "logs"
$SummaryFile = Join-Path $LogDir "gulicode-bp-package-ready.json"

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

function Assert-ReleasePackage {
    param([string]$Path)

    $requiredFiles = @(
        ".codex-plugin\plugin.json",
        ".mcp.json",
        "mcp\gulicode_bp_mcp.py",
        "scripts\bootstrap_mcp.py",
        "scripts\bootstrap_runtime.py",
        "skills\blueprint\SKILL.md",
        "web\dist\index.html"
    )
    foreach ($relative in $requiredFiles) {
        $target = Join-Path $Path $relative
        if (-not (Test-Path -LiteralPath $target -PathType Leaf)) {
            throw ("Release package is missing required file: {0}" -f $target)
        }
    }

    $wheelDir = Join-Path $Path "runtime\wheels"
    $wheel = Get-ChildItem -LiteralPath $wheelDir -Filter "multi_agent_tcp-*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $wheel) {
        throw ("Release package is missing runtime wheel under {0}" -f $wheelDir)
    }

    $runtimeDir = Join-Path $Path ".runtime"
    if (Test-Path -LiteralPath $runtimeDir) {
        throw ("Release package must not contain runtime state: {0}" -f $runtimeDir)
    }

    $mcp = Get-Content -Raw -LiteralPath (Join-Path $Path ".mcp.json") | ConvertFrom-Json
    $server = $mcp.mcpServers.'gulicode-bp'
    if ($server.command -ne "python") {
        throw ("Release MCP command must be python, got: {0}" -f $server.command)
    }
    if (($server.args -join " ") -ne "scripts/bootstrap_mcp.py") {
        throw ("Release MCP args must be scripts/bootstrap_mcp.py, got: {0}" -f ($server.args -join " "))
    }
    if ($server.cwd -ne ".") {
        throw ("Release MCP cwd must be ., got: {0}" -f $server.cwd)
    }
    if ($server.env.PYTHONPATH -or $server.env.GULICODE_BP_REPO_ROOT) {
        throw "Release MCP env must not include PYTHONPATH or GULICODE_BP_REPO_ROOT"
    }
}

if (-not (Test-Path -LiteralPath $PluginManifest -PathType Leaf)) {
    throw ("Missing plugin manifest: {0}" -f $PluginManifest)
}
if (-not (Test-Path -LiteralPath $PluginInstaller -PathType Leaf)) {
    throw ("Missing plugin installer: {0}" -f $PluginInstaller)
}
if (-not (Test-Path -LiteralPath $StandaloneSmoke -PathType Leaf)) {
    throw ("Missing standalone smoke: {0}" -f $StandaloneSmoke)
}

$manifest = Get-Content -Raw -LiteralPath $PluginManifest | ConvertFrom-Json
$version = [string]$manifest.version
if ([string]::IsNullOrWhiteSpace($version)) {
    throw "Plugin manifest is missing version"
}

if ([string]::IsNullOrWhiteSpace($ReleaseDir)) {
    $ReleaseDir = Join-Path $Root ("dist\gulicode-bp-{0}" -f $version)
}
$ReleaseDir = [System.IO.Path]::GetFullPath($ReleaseDir)

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host ("[package-gulicode-bp-plugin] root = {0}" -f $Root)
Write-Host ("[package-gulicode-bp-plugin] release = {0}" -f $ReleaseDir)

$installArgs = @(
    $PluginInstaller,
    "--force",
    "--release-dir",
    $ReleaseDir
)
if ($SkipWebBuild) {
    $installArgs += "--skip-web-build"
}

Invoke-Checked -FilePath "python" -ArgumentList $installArgs -WorkingDirectory $Root
Assert-ReleasePackage -Path $ReleaseDir

if (-not $NoSmoke) {
    Invoke-Checked -FilePath "python" -ArgumentList @(
        $StandaloneSmoke,
        "--plugin-root",
        $ReleaseDir,
        "--timeout",
        ([string]$SmokeTimeoutSeconds)
    ) -WorkingDirectory $Root
    $ReleaseRuntime = Join-Path $ReleaseDir ".runtime"
    if (Test-Path -LiteralPath $ReleaseRuntime) {
        Remove-Item -LiteralPath $ReleaseRuntime -Recurse -Force
    }
    Assert-ReleasePackage -Path $ReleaseDir

    if ($SmokeInstalledPlugin) {
        $InstalledPlugin = Join-Path $HOME "plugins\gulicode-bp"
        if (-not (Test-Path -LiteralPath $InstalledPlugin -PathType Container)) {
            throw ("Installed plugin was not found: {0}" -f $InstalledPlugin)
        }
        Invoke-Checked -FilePath "python" -ArgumentList @(
            $StandaloneSmoke,
            "--plugin-root",
            $InstalledPlugin,
            "--timeout",
            ([string]$SmokeTimeoutSeconds)
        ) -WorkingDirectory $Root
    }
}

$summary = [ordered]@{
    ok = $true
    version = $version
    releaseDir = $ReleaseDir
    installedPlugin = (Join-Path $HOME "plugins\gulicode-bp")
    smoke = (-not $NoSmoke)
    installedSmoke = ($SmokeInstalledPlugin -and (-not $NoSmoke))
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SummaryFile -Encoding UTF8
Write-Host ("[package-gulicode-bp-plugin] summary = {0}" -f $SummaryFile)
Write-Host "[package-gulicode-bp-plugin] done"
