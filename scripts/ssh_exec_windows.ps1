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
$remoteScript = Join-Path $remoteTmp $scriptName

Write-Host "[ssh_exec_windows] create temp: ${HostName}:$remoteTmp"
Run-Native ssh $HostName "powershell -NoProfile -Command `"New-Item -ItemType Directory -Force -Path $(Quote-CmdSingle $remoteTmp) | Out-Null`""

try {
  Write-Host "[ssh_exec_windows] upload: $absScript -> ${HostName}:$remoteScript"
  Run-Native scp "-q" $absScript "${HostName}:$remoteScript"

  # The user script body is never embedded in ssh quotes, so PowerShell
  # metacharacters stay intact. Keep the wrapper tiny on purpose.
  Write-Host "[ssh_exec_windows] run on $HostName"
  if ($RemoteWorkDir -ne "") {
    $remoteCommand = "Set-Location -Path $(Quote-CmdSingle $RemoteWorkDir); & $(Quote-CmdSingle $remoteScript)"
    & ssh $HostName "powershell -NoProfile -ExecutionPolicy Bypass -Command `"$remoteCommand`""
  } else {
    & ssh $HostName "powershell -NoProfile -ExecutionPolicy Bypass -File $remoteScript"
  }
  $runExit = $LASTEXITCODE
  if ($runExit -ne 0) {
    exit $runExit
  }
}
finally {
  Write-Host "[ssh_exec_windows] cleanup: ${HostName}:$remoteTmp"
  & ssh $HostName "powershell -NoProfile -Command `"Remove-Item -LiteralPath $(Quote-CmdSingle $remoteTmp) -Recurse -Force -ErrorAction SilentlyContinue`"" | Out-Null
}
