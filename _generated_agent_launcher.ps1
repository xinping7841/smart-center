$ErrorActionPreference = 'Continue'
$AgentDir = Join-Path $env:ProgramData 'SmartCenterAgent'
$WorkerPath = Join-Path $AgentDir 'agent_worker.ps1'
$RunnerLogPath = Join-Path $AgentDir 'agent_runner.log'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Append-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::AppendAllText($path, ([string]$content + [Environment]::NewLine), $Utf8NoBom)
}

function Write-RunnerLog([string]$msg) {
    Append-TextFile $RunnerLogPath ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg)
}

Write-RunnerLog 'launcher started'
try {
    if (-not (Test-Path $WorkerPath)) {
        throw ('missing worker script: ' + $WorkerPath)
    }
    & powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $WorkerPath *>> $RunnerLogPath
    $workerExitCode = $LASTEXITCODE
    if ($workerExitCode -ne 0) {
        Write-RunnerLog ('worker exited with code ' + $workerExitCode)
        exit $workerExitCode
    }
    Write-RunnerLog 'worker exited successfully'
} catch {
    Write-RunnerLog ('launcher failed: ' + $_.Exception.Message)
    throw
}
