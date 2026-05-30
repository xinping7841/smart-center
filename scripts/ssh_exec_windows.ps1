Param(
  [Parameter(Mandatory = $true)]
  [string]$HostName,

  [Parameter(Mandatory = $true)]
  [string]$ScriptPath,

  [string]$RemoteWorkDir = "",

  [string]$RemoteTempRoot = "C:\Users\Public\Temp"
)

$ErrorActionPreference = "Stop"

function Quote-CmdSingle {
  Param([string]$Value)
  if ($null -eq $Value) {
    return "''"
  }
  return "'" + $Value.Replace("'", "''") + "'"
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
$remoteTmp = Join-Path $RemoteTempRoot ("codex_exec_" + [System.Guid]::NewGuid().ToString("N"))
$remoteScript = Join-Path $remoteTmp "payload.ps1"
$remoteWrapper = Join-Path $remoteTmp "run.ps1"
$localWrapper = Join-Path ([System.IO.Path]::GetTempPath()) ("codex_ssh_windows_wrapper_" + [System.Guid]::NewGuid().ToString("N") + ".ps1")

Write-Host "[ssh_exec_windows] create temp: ${HostName}:$remoteTmp"
Run-Native ssh $HostName "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path $(Quote-CmdSingle $remoteTmp) | Out-Null`""

try {
  Write-Host "[ssh_exec_windows] upload: $absScript -> ${HostName}:$remoteScript"
  Run-Native scp "-q" $absScript "${HostName}:$remoteScript"

  $wrapperLines = @(
    '$ErrorActionPreference = "Stop"',
    '$RemoteScript = ' + (Quote-CmdSingle $remoteScript),
    '$RemoteWorkDir = ' + (Quote-CmdSingle $RemoteWorkDir),
    '',
    'if ($RemoteWorkDir -ne "") {',
    '  Set-Location -LiteralPath $RemoteWorkDir',
    '}',
    '',
    '& powershell -NoProfile -ExecutionPolicy Bypass -File $RemoteScript',
    'exit $LASTEXITCODE'
  )
  $wrapperLines | Set-Content -LiteralPath $localWrapper -Encoding ascii

  Write-Host "[ssh_exec_windows] upload wrapper -> ${HostName}:$remoteWrapper"
  Run-Native scp "-q" $localWrapper "${HostName}:$remoteWrapper"

  # The user script body is never embedded in ssh quotes, so PowerShell
  # metacharacters stay intact. Keep the remote command tiny on purpose.
  Write-Host "[ssh_exec_windows] run on $HostName"
  & ssh $HostName "powershell -NoProfile -ExecutionPolicy Bypass -File $remoteWrapper"
  $runExit = $LASTEXITCODE
  if ($runExit -ne 0) {
    exit $runExit
  }
}
finally {
  Write-Host "[ssh_exec_windows] cleanup: ${HostName}:$remoteTmp"
  Remove-Item -LiteralPath $localWrapper -Force -ErrorAction SilentlyContinue
  & ssh $HostName "powershell -NoProfile -Command `"Remove-Item -LiteralPath $(Quote-CmdSingle $remoteTmp) -Recurse -Force -ErrorAction SilentlyContinue`"" | Out-Null
}
