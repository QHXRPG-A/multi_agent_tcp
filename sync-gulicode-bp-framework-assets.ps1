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
$SourceResidentServices = Join-Path $SourceAssets "resident_services"
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

$TargetResidentServices = Join-Path $PluginRoot ".runtime\state\resident_services"
if (Test-Path -LiteralPath $SourceResidentServices -PathType Container) {
    if (-not (Test-Path -LiteralPath $TargetResidentServices -PathType Container)) {
        New-Item -ItemType Directory -Path $TargetResidentServices | Out-Null
    }
    Get-ChildItem -LiteralPath $SourceResidentServices -Filter "*.py" -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetResidentServices $_.Name) -Force
    }
}

$validatedPath = Join-Path $TargetAssets "skills\framework-agent-runtime\trunk_release_table_sync.md"
if (-not (Test-Path -LiteralPath $validatedPath -PathType Leaf)) {
    throw ("Missing trunk_release_table_sync.md after sync: {0}" -f $validatedPath)
}
$validatedText = Get-Content -Raw -LiteralPath $validatedPath
if (-not (Test-ContainsText $validatedText "Release/re table commits must be performed by the user")) {
    throw "Synced trunk_release_table_sync.md is missing no-commit rule"
}

$fullSkillPath = Join-Path $TargetAssets "skills\framework-agent-runtime\SKILL.md"
if (-not (Test-Path -LiteralPath $fullSkillPath -PathType Leaf)) {
    throw ("Missing framework-agent-runtime skill after sync: {0}" -f $fullSkillPath)
}
$fullSkillText = Get-Content -Raw -LiteralPath $fullSkillPath
if (-not (Test-ContainsText $fullSkillText "py -3.13")) {
    throw "Synced framework-agent-runtime skill is missing Python 3.13 command guidance"
}
if (-not (Test-ContainsText $fullSkillText "Python313\python.exe")) {
    throw "Synced framework-agent-runtime skill is missing concrete Python interpreter path"
}

$remoteDebugPath = Join-Path $TargetAssets "skills\framework-agent-runtime\remote_client_debugging.md"
if (-not (Test-Path -LiteralPath $remoteDebugPath -PathType Leaf)) {
    throw ("Missing remote_client_debugging.md after sync: {0}" -f $remoteDebugPath)
}
$remoteDebugText = Get-Content -Raw -LiteralPath $remoteDebugPath
if (-not (Test-ContainsText $remoteDebugText "hunter-cli-debug")) {
    throw "Synced remote_client_debugging.md is missing hunter-cli-debug reference"
}
if (-not (Test-ContainsText $remoteDebugText "py -3.13")) {
    throw "Synced remote_client_debugging.md is missing Python 3.13 command guidance"
}
if (
    -not (Test-ContainsText $remoteDebugText "本地") -or
    -not (Test-ContainsText $remoteDebugText "alone is not enough")
) {
    throw "Synced remote_client_debugging.md is missing no-implicit-local rule"
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

$fileSenderServicePath = Join-Path $TargetResidentServices "file_sender_service.py"
if (-not (Test-Path -LiteralPath $fileSenderServicePath -PathType Leaf)) {
    throw ("Missing file_sender_service.py after resident service sync: {0}" -f $fileSenderServicePath)
}

if (-not $Quiet) {
    Write-Host ("[sync-gulicode-bp-framework-assets] source = {0}" -f $SourceAssets)
    Write-Host ("[sync-gulicode-bp-framework-assets] target = {0}" -f $TargetAssets)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $validatedPath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $fullSkillPath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $remoteDebugPath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $workerSkillPath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $workerRulePath)
    Write-Host ("[sync-gulicode-bp-framework-assets] validated = {0}" -f $fileSenderServicePath)
}
