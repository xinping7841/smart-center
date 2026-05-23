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

if (-not (Test-Path -LiteralPath $ScriptPath)) {
  throw "Script not found: $ScriptPath"
}

$absScript = (Resolve-Path -LiteralPath $ScriptPath).Path
$scriptName = [System.IO.Path]::GetFileName($absScript)
$remoteTmp = "/tmp/codex_exec_$([System.Guid]::NewGuid().ToString('N'))"
$remoteScript = "$remoteTmp/$scriptName"

Write-Host "[ssh_exec] upload: $absScript -> ${HostName}:$remoteScript"

& ssh $HostName "mkdir -p $(Quote-Bash $remoteTmp)" | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw "Failed to create remote temp dir: $remoteTmp"
}

& scp -q $absScript "${HostName}:$remoteScript"
if ($LASTEXITCODE -ne 0) {
  throw "Failed to upload script: $absScript"
}

$remoteParts = @(
  "set -euo pipefail",
  "chmod +x $(Quote-Bash $remoteScript)"
)

if ($RemoteWorkDir -ne "") {
  $remoteParts += "cd $(Quote-Bash $RemoteWorkDir)"
}

$remoteParts += "bash $(Quote-Bash $remoteScript)"
$remoteCmd = ($remoteParts -join "; ")

Write-Host "[ssh_exec] run on $HostName"
$runExit = 0
try {
  & ssh $HostName "bash -lc $(Quote-Bash $remoteCmd)"
  $runExit = $LASTEXITCODE
}
finally {
  & ssh $HostName "rm -rf $(Quote-Bash $remoteTmp)" | Out-Null
}

if ($runExit -ne 0) {
  exit $runExit
}
