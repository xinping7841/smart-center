Param(
  [Parameter(Mandatory = $true)]
  [string]$HostName,

  [Parameter(Mandatory = $true)]
  [string]$ScriptPath,

  [string]$RemoteWorkDir = ""
)

$ErrorActionPreference = "Stop"

function Quote-Bash {
  Param([string]$Value)
  if ($null -eq $Value) {
    return "''"
  }
  $escaped = $Value.Replace("'", "'\''")
  return "'" + $escaped + "'"
}

function Run-Native {
  Param(
    [Parameter(Mandatory = $true)]
    [string]$Exe,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
  )
  & $Exe @Args
  if ($LASTEXITCODE -ne 0) {
    throw "$Exe failed with exit code $LASTEXITCODE"
  }
}

if (-not (Test-Path -LiteralPath $ScriptPath)) {
  throw "Script not found: $ScriptPath"
}

$absScript = (Resolve-Path -LiteralPath $ScriptPath).Path
$scriptName = [System.IO.Path]::GetFileName($absScript)
$remoteTmp = "/tmp/codex_exec_$([System.Guid]::NewGuid().ToString('N'))"
$remoteRunner = "bash"
if ($scriptName.ToLowerInvariant().EndsWith(".py")) {
  $remoteScript = "$remoteTmp/payload.py"
  $remoteRunner = "python3"
} else {
  $remoteScript = "$remoteTmp/payload.sh"
}
$remoteWrapper = "$remoteTmp/run.sh"
$localWrapper = Join-Path ([System.IO.Path]::GetTempPath()) ("codex_ssh_wrapper_" + [System.Guid]::NewGuid().ToString("N") + ".sh")

Write-Host "[ssh_exec] upload: $absScript -> ${HostName}:$remoteScript"

Run-Native ssh $HostName "mkdir -p $(Quote-Bash $remoteTmp)"

$wrapperLines = @(
  "#!/usr/bin/env bash",
  "set -euo pipefail",
  "REMOTE_SCRIPT=$(Quote-Bash $remoteScript)",
  "REMOTE_WORKDIR=$(Quote-Bash $RemoteWorkDir)",
  "REMOTE_RUNNER=$(Quote-Bash $remoteRunner)",
  "",
  'chmod +x "$REMOTE_SCRIPT"',
  'if [[ -n "$REMOTE_WORKDIR" ]]; then',
  '  cd "$REMOTE_WORKDIR"',
  'fi',
  "",
  'case "$REMOTE_RUNNER" in',
  '  python3)',
  '    exec python3 "$REMOTE_SCRIPT"',
  '    ;;',
  '  bash)',
  '    exec bash "$REMOTE_SCRIPT"',
  '    ;;',
  '  *)',
  '    echo "unsupported remote runner: $REMOTE_RUNNER" >&2',
  '    exit 2',
  '    ;;',
  'esac'
)

$wrapperLines | Set-Content -LiteralPath $localWrapper -Encoding ascii

Run-Native scp "-q" $absScript "${HostName}:$remoteScript"
Write-Host "[ssh_exec] upload wrapper -> ${HostName}:$remoteWrapper"
Run-Native scp "-q" $localWrapper "${HostName}:$remoteWrapper"

Write-Host "[ssh_exec] run on $HostName"
$runExit = 0
try {
  & ssh $HostName bash $remoteWrapper
  $runExit = $LASTEXITCODE
}
finally {
  Remove-Item -LiteralPath $localWrapper -Force -ErrorAction SilentlyContinue
  & ssh $HostName rm -rf $remoteTmp | Out-Null
}

if ($runExit -ne 0) {
  exit $runExit
}
