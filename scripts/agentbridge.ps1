param(
  [Parameter(Position = 0)]
  [ValidateSet("status", "login", "init", "dev", "claude", "codex", "kill")]
  [string]$Command = "status",

  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BridgeRoot = "E:\agent-bridge"
$BridgeCli = Join-Path $BridgeRoot "src\cli.ts"

function New-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Set-AgentBridgeEnv {
  $base = Join-Path $env:USERPROFILE ".codex\memories\codex-home"
  $runtime = Join-Path $env:USERPROFILE ".codex\memories\agentbridge-runtime"

  @(
    $base,
    (Join-Path $base ".codex"),
    (Join-Path $base "AppData\Roaming"),
    (Join-Path $base "AppData\Local"),
    (Join-Path $base ".config"),
    (Join-Path $base ".local\state"),
    (Join-Path $base ".local\share"),
    $runtime
  ) | ForEach-Object { New-Dir $_ }

  $env:HOME = $base
  $env:USERPROFILE = $base
  $env:APPDATA = Join-Path $base "AppData\Roaming"
  $env:LOCALAPPDATA = Join-Path $base "AppData\Local"
  $env:XDG_CONFIG_HOME = Join-Path $base ".config"
  $env:XDG_STATE_HOME = Join-Path $base ".local\state"
  $env:XDG_DATA_HOME = Join-Path $base ".local\share"
  $env:CODEX_HOME = Join-Path $base ".codex"
  $env:AGENTBRIDGE_STATE_DIR = $runtime

  return @{
    Base = $base
    Runtime = $runtime
  }
}

function Invoke-BridgeCli([string]$Subcommand, [string[]]$ForwardArgs) {
  if (-not (Test-Path -LiteralPath $BridgeCli)) {
    throw "Bridge CLI not found: $BridgeCli"
  }

  & bun --cwd $ProjectRoot $BridgeCli $Subcommand @ForwardArgs
  exit $LASTEXITCODE
}

function Show-Status {
  $envInfo = Set-AgentBridgeEnv

  Write-Host "ProjectRoot : $ProjectRoot"
  Write-Host "BridgeRoot  : $BridgeRoot"
  Write-Host "CODEX_HOME  : $($env:CODEX_HOME)"
  Write-Host "RuntimeDir  : $($envInfo.Runtime)"
  Write-Host ""

  Write-Host "[versions]"
  try { & bun --version } catch { Write-Host "bun: missing" }
  try { & claude --version } catch { Write-Host "claude: missing" }
  try { & codex --version } catch { Write-Host "codex: missing" }
  Write-Host ""

  Write-Host "[codex login]"
  try {
    & codex login status
  } catch {
    Write-Host $_.Exception.Message
  }
  Write-Host ""

  $configPath = Join-Path $ProjectRoot ".agentbridge\config.json"
  if (Test-Path -LiteralPath $configPath) {
    Write-Host "[project config]"
    Get-Content -LiteralPath $configPath
  } else {
    Write-Host "[project config]"
    Write-Host "Missing: $configPath"
  }
}

switch ($Command) {
  "status" {
    Show-Status
  }
  "login" {
    Set-AgentBridgeEnv | Out-Null
    & codex login @Args
    exit $LASTEXITCODE
  }
  default {
    Set-AgentBridgeEnv | Out-Null
    Invoke-BridgeCli -Subcommand $Command -ForwardArgs $Args
  }
}
