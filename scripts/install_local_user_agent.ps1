$ErrorActionPreference = 'Stop'

$ServerHost = '192.168.50.120'
$TaskName = 'SmartCenterAgentUser'
$AgentDir = Join-Path $env:LOCALAPPDATA 'SmartCenterAgent'
$WorkerPath = Join-Path $AgentDir 'agent_worker.ps1'
$LauncherPath = Join-Path $AgentDir 'agent_launcher.ps1'
$ConfigPath = Join-Path $AgentDir 'agent_config.json'
$InstallLog = Join-Path $AgentDir 'install.log'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-InstallLog([string]$msg) {
    New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
    [System.IO.File]::AppendAllText(
        $InstallLog,
        ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg + [Environment]::NewLine),
        $Utf8NoBom
    )
}

function Write-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::WriteAllText($path, [string]$content, $Utf8NoBom)
}

function Build-WorkerScript([string]$serverHost) {
    $payload = @'
$ErrorActionPreference = 'Continue'
$AgentVersion = '2026.04.03.4-user'
$AgentDir = Join-Path $env:LOCALAPPDATA 'SmartCenterAgent'
$ConfigPath = Join-Path $AgentDir 'agent_config.json'
$LogPath = Join-Path $AgentDir 'agent.log'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Append-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::AppendAllText($path, ([string]$content + [Environment]::NewLine), $Utf8NoBom)
}

function Write-AgentLog([string]$msg) {
    Append-TextFile $LogPath ("[" + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + "] " + $msg)
}

function Get-CommandOrNull([string]$name) {
    try {
        return Get-Command $name -ErrorAction Stop
    } catch {
        return $null
    }
}

function Get-AgentInstances([string]$className, [string]$filter = '') {
    $items = $null
    $cim = Get-CommandOrNull 'Get-CimInstance'
    if ($cim) {
        try {
            if ($filter) {
                $items = Get-CimInstance -ClassName $className -Filter $filter -ErrorAction Stop
            } else {
                $items = Get-CimInstance -ClassName $className -ErrorAction Stop
            }
        } catch {}
        if ($items) {
            return $items
        }
    }
    $wmi = Get-CommandOrNull 'Get-WmiObject'
    if ($wmi) {
        try {
            if ($filter) {
                $items = Get-WmiObject -Class $className -Filter $filter -ErrorAction Stop
            } else {
                $items = Get-WmiObject -Class $className -ErrorAction Stop
            }
        } catch {}
    }
    return $items
}

function Convert-ToHashtable([object]$obj) {
    if ($null -eq $obj) { return $null }
    if ($obj -is [string] -or $obj -is [char]) { return [string]$obj }
    if ($obj -is [System.ValueType]) { return $obj }
    if ($obj -is [System.Collections.IDictionary]) {
        $hash = @{}
        foreach ($key in $obj.Keys) {
            $hash[$key] = Convert-ToHashtable $obj[$key]
        }
        return $hash
    }
    if (($obj -is [System.Collections.IEnumerable]) -and -not ($obj -is [string])) {
        $items = @()
        foreach ($item in $obj) {
            $items += ,(Convert-ToHashtable $item)
        }
        return $items
    }
    if ($obj.PSObject -and $obj.PSObject.Properties.Count -gt 0) {
        $hash = @{}
        foreach ($prop in $obj.PSObject.Properties) {
            $hash[$prop.Name] = Convert-ToHashtable $prop.Value
        }
        return $hash
    }
    return $obj
}

function Write-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    [System.IO.File]::WriteAllText($path, [string]$content, $Utf8NoBom)
}

function Load-Config() {
    $defaults = @{
        current_server_url = '__SERVER_URL__'
        report_path = '/report'
    }
    if (Test-Path $ConfigPath) {
        try {
            $json = (Get-Content $ConfigPath -Raw -Encoding UTF8) | ConvertFrom-Json
            return @{
                current_server_url = if ($null -ne $json.current_server_url -and [string]$json.current_server_url) {
                    [string]$json.current_server_url
                } else {
                    $defaults.current_server_url
                }
                report_path = if ($null -ne $json.report_path -and [string]$json.report_path) {
                    [string]$json.report_path
                } else {
                    $defaults.report_path
                }
            }
        } catch {
            Write-AgentLog ('config load failed: ' + $_.Exception.Message)
        }
    }
    return $defaults
}

function Save-Config([hashtable]$cfg) {
    Write-TextFile $ConfigPath ($cfg | ConvertTo-Json -Depth 6)
}

function Get-PrimaryIPv4() {
    try {
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {
            $_.IPEnabled -eq $true -and $_.IPAddress
        }
        foreach ($adapter in $adapters) {
            $ipv4 = $adapter.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
            if ($ipv4 -and $ipv4 -like '192.168.30.*') { return $ipv4 }
        }
        foreach ($adapter in $adapters) {
            $ipv4 = $adapter.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
            if ($ipv4) { return $ipv4 }
        }
    } catch {}
    return ''
}

function Get-MacAddress() {
    try {
        $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {
            $_.IPEnabled -eq $true -and $_.MACAddress
        }
        foreach ($adapter in $adapters) {
            $ipv4 = $adapter.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
            if ($ipv4 -and $ipv4 -like '192.168.30.*') {
                return ($adapter.MACAddress -replace ':','-').ToUpper()
            }
        }
        $adapter = $adapters | Select-Object -First 1
        if ($adapter) {
            return ($adapter.MACAddress -replace ':','-').ToUpper()
        }
    } catch {}
    return 'TEMP-' + [guid]::NewGuid().ToString().Substring(0, 12).ToUpper()
}

function Get-BoardText([object]$board) {
    $parts = @()
    foreach ($value in @($board.Manufacturer, $board.Product)) {
        $text = [string]$value
        if (
            $text -and
            $text.Trim() -and
            $text.Trim() -notin @('Default string', 'System manufacturer', 'System Product Name', 'To be filled by O.E.M.')
        ) {
            $parts += $text.Trim()
        }
    }
    if ($parts.Count -gt 0) { return ($parts -join ' ') }
    if ($board.SerialNumber -and ([string]$board.SerialNumber).Trim()) {
        return ([string]$board.SerialNumber).Trim()
    }
    return 'unknown'
}

function Get-GpuInfo() {
    $gpuList = @()
    $seen = @{}
    $ignorePatterns = @(
        'virtual',
        'idd',
        'remote display',
        'indirect display',
        'mirror driver',
        'basic render',
        'parsec',
        'gameviewer',
        'oray'
    )
    function Test-GpuNameAllowed([string]$name) {
        if (-not $name) { return $false }
        $text = $name.Trim()
        if (-not $text) { return $false }
        $lower = $text.ToLowerInvariant()
        foreach ($pattern in $ignorePatterns) {
            if ($lower.Contains($pattern)) {
                return $false
            }
        }
        return $true
    }
    try {
        $gpus = @(Get-AgentInstances 'Win32_VideoController')
        $index = 0
        foreach ($gpu in $gpus) {
            $name = [string]$gpu.Name
            if (Test-GpuNameAllowed $name -and -not $seen.ContainsKey($name.Trim())) {
                $seen[$name.Trim()] = $true
                $gpuList += @{
                    index = $index
                    name = $name.Trim()
                    util_percent = 0
                    temp = 0
                }
                $index += 1
            }
        }
    } catch {}
    if ($gpuList.Count -eq 0) {
        try {
            $pnpDevices = Get-PnpDevice -Class Display -ErrorAction Stop | Where-Object {
                $_.FriendlyName -and $_.Status -eq 'OK'
            }
            $index = 0
            foreach ($gpu in $pnpDevices) {
                $name = [string]$gpu.FriendlyName
                if (Test-GpuNameAllowed $name -and -not $seen.ContainsKey($name.Trim())) {
                    $seen[$name.Trim()] = $true
                    $gpuList += @{
                        index = $index
                        name = $name.Trim()
                        util_percent = 0
                        temp = 0
                    }
                    $index += 1
                }
            }
        } catch {}
    }
    return @($gpuList)
}

function Get-MemorySpeed() {
    try {
        $modules = @(Get-AgentInstances 'Win32_PhysicalMemory') | Where-Object { $_.Speed -gt 0 }
        if ($modules) {
            return [int](($modules | Measure-Object -Property Speed -Maximum).Maximum)
        }
    } catch {}
    try {
        $modules = @(Get-AgentInstances 'Win32_PhysicalMemory') | Where-Object { $_.ConfiguredClockSpeed -gt 0 }
        if ($modules) {
            return [int](($modules | Measure-Object -Property ConfiguredClockSpeed -Maximum).Maximum)
        }
    } catch {}
    return 0
}

function Get-Payload([hashtable]$cfg) {
    $cpu = $null
    $board = $null
    $os = $null
    $disk = $null
    try { $cpu = @(Get-AgentInstances 'Win32_Processor') | Select-Object -First 1 } catch {}
    try { $board = @(Get-AgentInstances 'Win32_BaseBoard') | Select-Object -First 1 } catch {}
    try { $os = Get-AgentInstances 'Win32_OperatingSystem' } catch {}
    try { $disk = Get-AgentInstances 'Win32_LogicalDisk' "DeviceID='C:'" } catch {}
    $gpuList = @(Get-GpuInfo)
    $memUsed = 0
    $memTotal = 0
    $memPercent = 0
    if ($os) {
        try {
            $memUsed = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 2)
            $memTotal = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
            $memPercent = if ($memTotal -gt 0) { [math]::Round(($memUsed / $memTotal) * 100, 1) } else { 0 }
        } catch {}
    }
    $diskPercent = 0
    if ($disk -and $disk.Size -gt 0) {
        try {
            $diskPercent = [math]::Round((($disk.Size - $disk.FreeSpace) / $disk.Size) * 100, 1)
        } catch {}
    }
    $cpuPercent = 0
    try {
        $cpuPercent = [math]::Round((Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples[0].CookedValue, 1)
    } catch {}
    return @{
        mac = Get-MacAddress
        hostname = $env:COMPUTERNAME
        ip = Get-PrimaryIPv4
        timestamp = (Get-Date).ToString('o')
        status = @{
            cpu_name = if ($cpu -and $cpu.Name) { $cpu.Name } else { 'Unknown CPU' }
            motherboard = if ($board) { Get-BoardText $board } else { 'Unknown motherboard' }
            mem_speed = Get-MemorySpeed
            cpu_percent = $cpuPercent
            mem_used = $memUsed
            mem_total = $memTotal
            mem_percent = $memPercent
            disk_percent = $diskPercent
            net_sent_kb_s = 0
            net_recv_kb_s = 0
            gpu_list = $gpuList
            hardware_refreshed_at = (Get-Date).ToString('o')
            agent = @{
                version = $AgentVersion
                current_server_url = $cfg['current_server_url']
                report_interval_sec = 60
                task_name = 'SmartCenterAgentUser'
                task_exists = $true
                task_state = 'running'
                task_user = $env:USERNAME
            }
        }
    }
}

try {
    New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
    $cfg = Load-Config
    if (-not $cfg['current_server_url']) {
        $cfg['current_server_url'] = '__SERVER_URL__'
    }
    Save-Config $cfg
    $payload = Get-Payload $cfg | ConvertTo-Json -Depth 8
    $reportUrl = $cfg['current_server_url'].TrimEnd('/') + $cfg['report_path']
    Invoke-RestMethod -Uri $reportUrl -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 8 -ErrorAction Stop | Out-Null
    Write-AgentLog ('report ok -> ' + $reportUrl)
    exit 0
} catch {
    Write-AgentLog ('report failed: ' + $_.Exception.Message)
    exit 1
}
'@
    return $payload.Replace('__SERVER_URL__', 'http://' + $serverHost + ':6899')
}

function Build-LauncherScript() {
    return @'
$ErrorActionPreference = 'Continue'
$AgentDir = Join-Path $env:LOCALAPPDATA 'SmartCenterAgent'
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
'@
}

New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
Write-InstallLog 'install started'
$worker = Build-WorkerScript $ServerHost
$launcher = Build-LauncherScript
Write-TextFile $WorkerPath $worker
Write-TextFile $LauncherPath $launcher
Write-TextFile $ConfigPath ('{"current_server_url":"http://' + $ServerHost + ':6899","report_path":"/report"}')
Write-InstallLog 'files written'

try {
    schtasks /Delete /TN $TaskName /F *> $null
} catch {}

$startTime = (Get-Date).AddMinutes(1).ToString('HH:mm')
$taskCommand = 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $LauncherPath + '"'
schtasks /Create /SC MINUTE /MO 1 /TN $TaskName /TR $taskCommand /ST $startTime /F | Out-Null
Write-InstallLog 'scheduled task created'
schtasks /Run /TN $TaskName | Out-Null
Write-InstallLog 'scheduled task started'

Write-Host 'Local user agent installed'
