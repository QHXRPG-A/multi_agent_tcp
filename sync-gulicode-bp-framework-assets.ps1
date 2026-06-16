param(
    [string]$PluginRoot = "",
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($PluginRoot)) {
    $PluginRoot = Join-Path $HOME "plugins\gulicode-bp"
}

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

$SourceAssets = Join-Path $Root "framework_assets"
$RuntimePython = Join-Path $PluginRoot ".runtime\venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $SourceAssets -PathType Container)) {
    throw ("Missing source framework_assets: {0}" -f $SourceAssets)
}
if (-not (Test-Path -LiteralPath $RuntimePython -PathType Leaf)) {
    throw ("Missing installed plugin runtime Python: {0}" -f $RuntimePython)
}

$lookupCode = @'
from pathlib import Path
import multi_agent_tcp

print(str(Path(multi_agent_tcp.__file__).resolve().parent))
'@

$lookupRaw = & $RuntimePython -c $lookupCode
if ($LASTEXITCODE -ne 0) {
    throw ("Failed to locate installed multi_agent_tcp package with {0}" -f $RuntimePython)
}

$packageRoot = [string]$lookupRaw
if ([string]::IsNullOrWhiteSpace($packageRoot)) {
    throw "Installed multi_agent_tcp package root lookup returned empty output"
}

$TargetAssets = Join-Path $packageRoot "framework_assets"
if (Test-Path -LiteralPath $TargetAssets) {
    Remove-Item -LiteralPath $TargetAssets -Recurse -Force
}
Copy-Item -LiteralPath $SourceAssets -Destination $TargetAssets -Recurse -Force

$validatedPath = Join-Path $TargetAssets "skills\framework-agent-runtime\trunk_release_table_sync.md"
if (-not (Test-Path -LiteralPath $validatedPath -PathType Leaf)) {
    throw ("Missing trunk_release_table_sync.md after sync: {0}" -f $validatedPath)
}
$validatedText = Get-Content -Raw -LiteralPath $validatedPath
if (-not (Test-ContainsText $validatedText "Release/re table commits must be performed by the user")) {
    throw "Synced trunk_release_table_sync.md is missing no-commit rule"
}

$workerSkillPath = Join-Path $TargetAssets "skills\framework-worker-runtime\SKILL.md"
if (-not (Test-Path -LiteralPath $workerSkillPath -PathType Leaf)) {
    throw ("Missing framework-worker-runtime skill after sync: {0}" -f $workerSkillPath)
}
$workerSkillText = Get-Content -Raw -LiteralPath $workerSkillPath
if (-not (Test-ContainsText $workerSkillText "private checkout")) {
    throw "Synced framework-worker-runtime skill is missing private checkout guidance"
}

$fullRulePath = Join-Path $TargetAssets "rules\framework-agent-runtime.md"
if (-not (Test-Path -LiteralPath $fullRulePath -PathType Leaf)) {
    throw ("Missing framework-agent-runtime rule after sync: {0}" -f $fullRulePath)
}
$workerRulePath = Join-Path $TargetAssets "rules\framework-worker-runtime.md"
if (-not (Test-Path -LiteralPath $workerRulePath -PathType Leaf)) {
    throw ("Missing framework-worker-runtime rule after sync: {0}" -f $workerRulePath)
}

if (-not $Quiet) {
    Write-Host ("[sync-gulicode-bp-framework-assets] source = {0}" -f $SourceAssets)
    Write-Host ("[sync-gulicode-bp-framework-assets] target = {0}" -f $TargetAssets)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $validatedPath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $workerSkillPath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $workerRulePath)
}
