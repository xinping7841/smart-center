$ErrorActionPreference = 'Continue'
$AgentVersion = '2026.04.03.1'
$TaskName = 'SmartCenterAgent'
$AgentDir = Join-Path $env:ProgramData 'SmartCenterAgent'
$ConfigPath = Join-Path $AgentDir 'agent_config.json'
$LogPath = Join-Path $AgentDir 'agent.log'
$WorkerPath = if ($PSCommandPath) { $PSCommandPath } else { Join-Path $AgentDir 'agent_worker.ps1' }
$lastNetBytesSent = $null
$lastNetBytesRecv = $null
$lastNetSampleTime = $null
$script:HardwareCache = $null
$script:LastTaskInfoAt = $null
$script:TaskInfoCache = $null
$script:ConsecutiveFailures = 0
$script:LastSuccessfulReportAt = $null
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-TextFile([string]$path, [string]$content) {
    $parent = [System.IO.Path]::GetDirectoryName($path)
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    if (Test-Path $path -PathType Container) {
        Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
    }
    $lastError = $null
    for ($attempt = 1; $attempt -le 8; $attempt++) {
        try {
            [System.IO.File]::WriteAllText($path, [string]$content, $Utf8NoBom)
            return
        } catch {
            $lastError = $_
            Start-Sleep -Milliseconds (150 * $attempt)
        }
    }
    if ($lastError) {
        throw $lastError
    }
}

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

function Convert-ToHashtable([object]$obj) {
    if ($null -eq $obj) { return $null }
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

function Add-UniqueValue([System.Collections.ArrayList]$list, [hashtable]$seen, [object]$value) {
    if ($null -eq $value) { return }
    if (($value -is [System.Collections.IEnumerable]) -and -not ($value -is [string])) {
        foreach ($item in $value) {
            Add-UniqueValue $list $seen $item
        }
        return
    }
    $text = [string]$value
    if (-not $text) { return }
    $text = $text.Trim()
    if (-not $text) { return }
    if (-not $seen.ContainsKey($text)) {
        $seen[$text] = $true
        [void]$list.Add($text)
    }
}

function Merge-UniqueList([object]$values) {
    $list = New-Object System.Collections.ArrayList
    $seen = @{}
    Add-UniqueValue $list $seen $values
    return @($list)
}

function Get-InitialAgentConfig() {
    $json = @"
{
  "service": "smart_center_agent",
  "version": "2026.04.03.1",
  "server_host": "192.168.50.120",
  "server_port": 6899,
  "report_path": "/report",
  "config_path": "/agent/config",
  "report_interval_sec": 60,
  "sync_interval_sec": 60,
  "discovery_retry_sec": 120,
  "candidate_hosts": [
    "192.168.50.120",
    "192.168.30.12",
    "12700K"
  ],
  "scan_networks": [
    "192.168.30.0/24"
  ],
  "updated_at": "2026-04-03T13:59:06.241467"
}
"@
    return (Convert-ToHashtable ($json | ConvertFrom-Json))
}

function New-AgentConfigObject([hashtable]$raw) {
    $cfg = @{}
    if ($raw) {
        foreach ($key in $raw.Keys) {
            $cfg[$key] = $raw[$key]
        }
    }
    if (-not $cfg.ContainsKey('service') -or -not $cfg['service']) { $cfg['service'] = 'smart_center_agent' }
    if (-not $cfg.ContainsKey('version') -or -not $cfg['version']) { $cfg['version'] = $AgentVersion }
    if (-not $cfg.ContainsKey('server_port') -or -not $cfg['server_port']) { $cfg['server_port'] = 6899 }
    if (-not $cfg.ContainsKey('report_path') -or -not $cfg['report_path']) { $cfg['report_path'] = '/report' }
    if (-not $cfg.ContainsKey('config_path') -or -not $cfg['config_path']) { $cfg['config_path'] = '/agent/config' }
    if (-not $cfg.ContainsKey('report_interval_sec') -or -not $cfg['report_interval_sec']) { $cfg['report_interval_sec'] = 60 }
    if (-not $cfg.ContainsKey('sync_interval_sec') -or -not $cfg['sync_interval_sec']) { $cfg['sync_interval_sec'] = 60 }
    if (-not $cfg.ContainsKey('discovery_retry_sec') -or -not $cfg['discovery_retry_sec']) { $cfg['discovery_retry_sec'] = 120 }
    $cfg['candidate_hosts'] = @(Merge-UniqueList @($cfg['server_host'], $cfg['candidate_hosts']))
    $cfg['scan_networks'] = @(Merge-UniqueList @($cfg['scan_networks']))
    if ((-not $cfg.ContainsKey('server_host') -or -not $cfg['server_host']) -and $cfg['candidate_hosts'].Count -gt 0) {
        $cfg['server_host'] = $cfg['candidate_hosts'][0]
    }
    if (-not $cfg.ContainsKey('current_server_url') -or -not $cfg['current_server_url']) {
        if ($cfg['server_host']) {
            $cfg['current_server_url'] = 'http://' + $cfg['server_host'] + ':' + $cfg['server_port']
        } else {
            $cfg['current_server_url'] = ''
        }
    }
    return $cfg
}

function Save-AgentConfig([hashtable]$cfg) {
    Write-TextFile $ConfigPath ($cfg | ConvertTo-Json -Depth 8)
}

function Load-AgentConfig() {
    $initial = New-AgentConfigObject (Get-InitialAgentConfig)
    if (Test-Path $ConfigPath) {
        try {
            $stored = Convert-ToHashtable ((Get-Content $ConfigPath -Raw -Encoding UTF8) | ConvertFrom-Json)
            return New-AgentConfigObject $stored
        } catch {
            Write-AgentLog ('load local config failed, fallback to defaults: ' + $_.Exception.Message)
        }
    }
    Save-AgentConfig $initial
    return $initial
}

function Merge-AgentConfig([hashtable]$cfg, [hashtable]$incoming) {
    if (-not $incoming) { return $cfg }
    foreach ($key in @('service','version','server_host','server_port','report_path','config_path','report_interval_sec','sync_interval_sec','discovery_retry_sec')) {
        if ($incoming.ContainsKey($key) -and $null -ne $incoming[$key] -and [string]$incoming[$key] -ne '') {
            $cfg[$key] = $incoming[$key]
        }
    }
    if ($incoming.ContainsKey('candidate_hosts')) {
        $cfg['candidate_hosts'] = @(Merge-UniqueList @($incoming['candidate_hosts'], $cfg['candidate_hosts'], $incoming['server_host'], $cfg['server_host']))
    } else {
        $cfg['candidate_hosts'] = @(Merge-UniqueList @($cfg['candidate_hosts'], $cfg['server_host']))
    }
    if ($incoming.ContainsKey('scan_networks')) {
        $cfg['scan_networks'] = @(Merge-UniqueList @($incoming['scan_networks'], $cfg['scan_networks']))
    } else {
        $cfg['scan_networks'] = @(Merge-UniqueList @($cfg['scan_networks']))
    }
    if ((-not $cfg['server_host']) -and $cfg['candidate_hosts'].Count -gt 0) {
        $cfg['server_host'] = $cfg['candidate_hosts'][0]
    }
    if ($cfg['server_host']) {
        $cfg['current_server_url'] = 'http://' + $cfg['server_host'] + ':' + $cfg['server_port']
    }
    $cfg['config_updated_at'] = (Get-Date).ToString('o')
    return $cfg
}

function Convert-IPv4ToUInt([string]$ip) {
    $bytes = [System.Net.IPAddress]::Parse($ip).GetAddressBytes()
    [array]::Reverse($bytes)
    return [BitConverter]::ToUInt32($bytes, 0)
}

function Convert-UIntToIPv4([uint32]$value) {
    $bytes = [BitConverter]::GetBytes([uint32]$value)
    [array]::Reverse($bytes)
    return ([System.Net.IPAddress]::new($bytes)).ToString()
}

function Get-LocalDiscoveryNetworks() {
    $networks = @()
    try {
        $ipv4 = Get-PrimaryIPv4
        if ($ipv4) {
            $parts = $ipv4.Split('.')
            if ($parts.Count -eq 4) {
                $networks += ($parts[0] + '.' + $parts[1] + '.' + $parts[2] + '.0/24')
            }
        }
    } catch {}
    return @(Merge-UniqueList $networks)
}

function Get-NetworkHosts([string]$networkText) {
    $networkText = [string]$networkText
    if (-not $networkText) { return @() }
    $parts = $networkText.Split('/')
    if ($parts.Count -ne 2) { return @() }
    try {
        $prefix = [int]$parts[1]
        if ($prefix -lt 16 -or $prefix -gt 30) { return @() }
        $base = Convert-IPv4ToUInt $parts[0]
        $hostBits = 32 - $prefix
        $mask = [uint32]0xFFFFFFFF
        if ($hostBits -gt 0) {
            $mask = [uint32]($mask -shl $hostBits)
        }
        $networkBase = [uint32]($base -band $mask)
        $maxHosts = [Math]::Min([Math]::Pow(2, $hostBits) - 2, 254)
        $hosts = @()
        for ($i = 1; $i -le $maxHosts; $i++) {
            $hosts += (Convert-UIntToIPv4 ([uint32]($networkBase + $i)))
        }
        return $hosts
    } catch {
        return @()
    }
}

function Get-AgentTaskInfo() {
    if ($script:TaskInfoCache -and $script:LastTaskInfoAt -and ((Get-Date) - $script:LastTaskInfoAt).TotalSeconds -lt 30) {
        return $script:TaskInfoCache
    }
    $info = @{
        exists = $false
        state = 'unknown'
        user = ''
        last_run_time = ''
        next_run_time = ''
    }
    try {
        $schedule = New-Object -ComObject 'Schedule.Service'
        $schedule.Connect()
        $rootFolder = $schedule.GetFolder('\')
        $task = $null
        try {
            $task = $rootFolder.GetTask('\' + $TaskName)
        } catch {
            try {
                $task = $rootFolder.GetTask($TaskName)
            } catch {}
        }
        if ($task) {
            $stateMap = @{
                0 = 'unknown'
                1 = 'disabled'
                2 = 'queued'
                3 = 'ready'
                4 = 'running'
            }
            $stateValue = 0
            try {
                $stateValue = [int]$task.State
            } catch {}
            $info.exists = $true
            $info.state = if ($stateMap.ContainsKey($stateValue)) { $stateMap[$stateValue] } else { [string]$task.State }
            try {
                if ($task.Definition -and $task.Definition.Principal) {
                    $info.user = [string]$task.Definition.Principal.UserId
                }
            } catch {}
            try {
                $lastRun = [datetime]$task.LastRunTime
                if ($lastRun.Year -ge 2000) {
                    $info.last_run_time = $lastRun.ToString('o')
                }
            } catch {}
            try {
                $nextRun = [datetime]$task.NextRunTime
                if ($nextRun.Year -ge 2000) {
                    $info.next_run_time = $nextRun.ToString('o')
                }
            } catch {}
        }
        if (-not $info.exists) {
            $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if ($task) {
                $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
                $info.exists = $true
                $info.state = [string]$task.State
                $info.user = if ($task.Principal) { [string]$task.Principal.UserId } else { '' }
                $info.last_run_time = if ($taskInfo -and $taskInfo.LastRunTime) { $taskInfo.LastRunTime.ToString('o') } else { '' }
                $info.next_run_time = if ($taskInfo -and $taskInfo.NextRunTime) { $taskInfo.NextRunTime.ToString('o') } else { '' }
            }
        }
    } catch {}
    $script:LastTaskInfoAt = Get-Date
    $script:TaskInfoCache = $info
    return $info
}

function Invoke-AgentConfigProbe([string]$serverUrl, [hashtable]$cfg) {
    if (-not $serverUrl) { return $null }
    try {
        $uri = $serverUrl.TrimEnd('/') + $cfg['config_path'] + '?probe=1'
        $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 2
        $incoming = $null
        if ($response -and $response.agent_config) {
            $incoming = Convert-ToHashtable $response.agent_config
        } elseif ($response -and $response.service -eq 'smart_center_agent') {
            $incoming = Convert-ToHashtable $response
        }
        if ($incoming) {
            if (-not $incoming.ContainsKey('server_host') -or -not $incoming['server_host']) {
                try {
                    $incoming['server_host'] = ([uri]$serverUrl).Host
                } catch {}
            }
            return $incoming
        }
    } catch {}
    return $null
}

function Find-AvailableServer([hashtable]$cfg, [switch]$ForceDiscovery) {
    $urls = @()
    if ($cfg['current_server_url']) {
        $urls += $cfg['current_server_url']
    }
    foreach ($host in @($cfg['candidate_hosts'])) {
        if ($host) {
            $urls += ('http://' + $host + ':' + $cfg['server_port'])
        }
    }
    $urls = @(Merge-UniqueList $urls)
    foreach ($url in $urls) {
        $incoming = Invoke-AgentConfigProbe $url $cfg
        if ($incoming) {
            Merge-AgentConfig $cfg $incoming | Out-Null
            $cfg['last_config_sync_at'] = (Get-Date).ToString('o')
            Save-AgentConfig $cfg
            return $cfg
        }
    }

    $shouldDiscover = $ForceDiscovery
    if (-not $shouldDiscover) {
        if (-not $cfg['last_discovery_at']) {
            $shouldDiscover = $true
        } else {
            try {
                $shouldDiscover = ((Get-Date) - [datetime]::Parse($cfg['last_discovery_at'])).TotalSeconds -ge [int]$cfg['discovery_retry_sec']
            } catch {
                $shouldDiscover = $true
            }
        }
    }
    if (-not $shouldDiscover) {
        return $cfg
    }

    $cfg['last_discovery_at'] = (Get-Date).ToString('o')
    $networks = @(Merge-UniqueList @($cfg['scan_networks'], (Get-LocalDiscoveryNetworks)))
    foreach ($network in $networks) {
        foreach ($host in Get-NetworkHosts $network) {
            if ($host -eq (Get-PrimaryIPv4)) { continue }
            $url = 'http://' + $host + ':' + $cfg['server_port']
            $incoming = Invoke-AgentConfigProbe $url $cfg
            if ($incoming) {
                Merge-AgentConfig $cfg $incoming | Out-Null
                $cfg['last_config_sync_at'] = (Get-Date).ToString('o')
                Save-AgentConfig $cfg
                Write-AgentLog ('discovered control server: ' + $cfg['current_server_url'])
                return $cfg
            }
        }
    }
    Save-AgentConfig $cfg
    return $cfg
}

function Get-MacAddress {
    $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {
        $_.IPEnabled -eq $true -and $_.MACAddress
    }
    $adapter = $adapters | Select-Object -First 1
    if ($adapter) { return ($adapter.MACAddress -replace ':','-').ToUpper() }
    return 'TEMP-' + [guid]::NewGuid().ToString().Substring(0, 12).ToUpper()
}

function Get-PrimaryIPv4 {
    $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration | Where-Object {
        $_.IPEnabled -eq $true -and $_.IPAddress
    }
    foreach ($adapter in $adapters) {
        $ipv4 = $adapter.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1
        if ($ipv4) { return $ipv4 }
    }
    return ''
}

function Get-NetSpeed {
    $counters = Get-CimInstance Win32_PerfRawData_Tcpip_NetworkInterface
    $totalSent = 0
    $totalRecv = 0
    foreach ($counter in $counters) {
        $totalSent += [double]$counter.BytesSentPersec
        $totalRecv += [double]$counter.BytesReceivedPersec
    }
    $now = Get-Date
    $sendKb = 0
    $recvKb = 0
    if ($lastNetSampleTime) {
        $seconds = ($now - $lastNetSampleTime).TotalSeconds
        if ($seconds -gt 0) {
            $sendKb = [math]::Round((($totalSent - $lastNetBytesSent) / $seconds) / 1KB, 1)
            $recvKb = [math]::Round((($totalRecv - $lastNetBytesRecv) / $seconds) / 1KB, 1)
        }
    }
    $script:lastNetBytesSent = $totalSent
    $script:lastNetBytesRecv = $totalRecv
    $script:lastNetSampleTime = $now
    return @($sendKb, $recvKb)
}

function Get-GpuInfo {
    $gpuList = @()
    try {
        $gpus = Get-CimInstance Win32_VideoController
        $index = 0
        foreach ($gpu in $gpus) {
            if ($gpu.Name) {
                $gpuList += @{
                    index = $index
                    name = $gpu.Name
                    util_percent = 0
                    temp = 0
                }
                $index += 1
            }
        }
    } catch {}
    return $gpuList
}

function Get-MemorySpeed {
    try {
        $modules = Get-CimInstance Win32_PhysicalMemory | Where-Object { $_.Speed -gt 0 }
        if ($modules) {
            return [int](($modules | Measure-Object -Property Speed -Maximum).Maximum)
        }
    } catch {}
    return 0
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
    if ($parts.Count -gt 0) {
        return ($parts -join ' ')
    }
    if ($board.SerialNumber -and ([string]$board.SerialNumber).Trim()) {
        return ([string]$board.SerialNumber).Trim()
    }
    return 'unknown'
}

function Get-HardwareSnapshot {
    if (-not $script:HardwareCache) {
        $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
        $board = Get-CimInstance Win32_BaseBoard | Select-Object -First 1
        $script:HardwareCache = @{
            cpu_name = if ($cpu -and $cpu.Name) { $cpu.Name } else { 'Unknown CPU' }
            motherboard = if ($board) { Get-BoardText $board } else { 'Unknown motherboard' }
            mem_speed = Get-MemorySpeed
            hardware_refreshed_at = (Get-Date).ToString('o')
        }
    }
    return $script:HardwareCache
}

function Get-StatusPayload([hashtable]$cfg) {
    $hardware = $null
    try {
        $hardware = Get-HardwareSnapshot
    } catch {
        $hardware = @{
            cpu_name = 'Unknown CPU'
            motherboard = 'Unknown motherboard'
            mem_speed = 0
            hardware_refreshed_at = ''
        }
    }
    $os = $null
    try {
        $os = Get-CimInstance Win32_OperatingSystem
    } catch {}
    $logicalDisk = $null
    try {
        $logicalDisk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    } catch {}
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
    if ($logicalDisk -and $logicalDisk.Size -gt 0) {
        try {
            $diskPercent = [math]::Round((($logicalDisk.Size - $logicalDisk.FreeSpace) / $logicalDisk.Size) * 100, 1)
        } catch {}
    }
    $cpuPercent = 0
    try {
        $cpuPercent = [math]::Round((Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples[0].CookedValue, 1)
    } catch {}
    $netSpeed = @(0, 0)
    try {
        $netSpeed = Get-NetSpeed
    } catch {}
    $taskInfo = Get-AgentTaskInfo

    return @{
        mac = Get-MacAddress
        hostname = $env:COMPUTERNAME
        ip = Get-PrimaryIPv4
        timestamp = (Get-Date).ToString('o')
        status = @{
            cpu_name = $hardware.cpu_name
            motherboard = $hardware.motherboard
            mem_speed = $hardware.mem_speed
            cpu_percent = $cpuPercent
            mem_used = $memUsed
            mem_total = $memTotal
            mem_percent = $memPercent
            disk_percent = $diskPercent
            net_sent_kb_s = $netSpeed[0]
            net_recv_kb_s = $netSpeed[1]
            gpu_list = @(Get-GpuInfo)
            os_caption = if ($os) { $os.Caption } else { '' }
            os_version = if ($os) { $os.Version } else { '' }
            hardware_refreshed_at = $hardware.hardware_refreshed_at
            agent = @{
                version = $AgentVersion
                current_server_url = $cfg['current_server_url']
                candidate_hosts = @($cfg['candidate_hosts'])
                report_interval_sec = [int]$cfg['report_interval_sec']
                config_updated_at = $cfg['config_updated_at']
                last_config_sync_at = $cfg['last_config_sync_at']
                last_discovery_at = $cfg['last_discovery_at']
                task_name = $TaskName
                task_exists = $taskInfo.exists
                task_state = $taskInfo.state
                task_user = $taskInfo.user
                task_last_run_time = $taskInfo.last_run_time
                task_next_run_time = $taskInfo.next_run_time
                worker_path = $WorkerPath
            }
        }
    }
}

try {
    New-Item -ItemType Directory -Force -Path $AgentDir | Out-Null
    Write-AgentLog ('worker run starting version=' + $AgentVersion)
    $config = Load-AgentConfig
    Write-AgentLog ('config loaded current=' + [string]$config['current_server_url'])
    $config = Find-AvailableServer $config
    Write-AgentLog ('active server=' + [string]$config['current_server_url'])
} catch {
    try {
        Write-AgentLog ('worker startup failed: ' + $_.Exception.Message)
    } catch {}
    exit 1
}

try {
    if ($config['last_config_sync_at']) {
        try {
            $secondsSinceSync = ((Get-Date) - [datetime]::Parse($config['last_config_sync_at'])).TotalSeconds
        } catch {
            $secondsSinceSync = [int]$config['sync_interval_sec']
        }
    } else {
        $secondsSinceSync = [int]$config['sync_interval_sec']
    }
    if ($secondsSinceSync -ge [int]$config['sync_interval_sec']) {
        $config = Find-AvailableServer $config
    }

    $payload = Get-StatusPayload $config | ConvertTo-Json -Depth 8
    $reportUrl = $config['current_server_url'].TrimEnd('/') + $config['report_path']
    $response = Invoke-RestMethod -Uri $reportUrl -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 8 -ErrorAction Stop
    Write-AgentLog ('report ok -> ' + $reportUrl)
    if ($response -and $response.agent_config) {
        Merge-AgentConfig $config (Convert-ToHashtable $response.agent_config) | Out-Null
        $config['last_config_sync_at'] = (Get-Date).ToString('o')
        Save-AgentConfig $config
    }
    if ($response.command -eq 'refresh') {
        $script:HardwareCache = $null
        Write-AgentLog 'refresh command received'
    } elseif ($response.command -eq 'shutdown') {
        Write-AgentLog 'shutdown command received'
        Stop-Computer -Force
    } elseif ($response.command -eq 'restart') {
        Write-AgentLog 'restart command received'
        Restart-Computer -Force
    }
} catch {
    Write-AgentLog ('worker run failed: ' + $_.Exception.Message)
    exit 1
}
exit 0
