param(
    [Nullable[int]] $TestNodeMajor
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:failures = 0
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Pass([string] $Name, [string] $Version) { Write-Host "PASS $Name $Version" }
function Fail([string] $Name, [string] $Direction) {
    $script:failures++
    Write-Host "FAIL $Name $Direction"
}

function Test-SupportedNodeMajor([int] $Major) {
    return $Major -eq 24
}

if ($null -ne $TestNodeMajor) {
    if (Test-SupportedNodeMajor $TestNodeMajor) {
        Pass "Node-Major-Gate" "Node.js $TestNodeMajor accepted"
        exit 0
    }
    Fail "Node-Major-Gate" "Node.js $TestNodeMajor rejected; Node.js 24 LTS is required."
    exit 1
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) { Pass "Docker" ((& docker --version 2>$null) -join " ") } else { Fail "Docker" "Install Docker Desktop: https://docs.docker.com/desktop/" }
if ($docker -and ((& docker compose version 2>$null) -join " ")) { Pass "Docker-Compose" ((& docker compose version 2>$null) -join " ") } else { Fail "Docker-Compose" "Install the Docker Compose plugin with Docker Desktop." }

$java = Get-Command java -ErrorAction SilentlyContinue
if ($java) {
    $javaVersion = ((& cmd.exe /d /c "java -version 2>&1" | Select-Object -First 1) -join " ")
    if ($javaVersion -match 'version "21(?:\.|\")') { Pass "Java" $javaVersion } else { Fail "Java" "Java 21 required; install a JDK 21 distribution." }
} else { Fail "Java" "Install JDK 21 and add java to PATH." }

if (Test-Path -LiteralPath (Join-Path $repoRoot "backend\mvnw.cmd")) { Pass "Maven-Wrapper" "backend/mvnw.cmd" } else { Fail "Maven-Wrapper" "Restore the tracked backend Maven Wrapper." }

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $nodeVersion = (& node --version).Trim()
    $major = [int](($nodeVersion -replace '^v', '').Split('.')[0])
    if (Test-SupportedNodeMajor $major) { Pass "Node" $nodeVersion } else { Fail "Node" "Node.js 24 LTS required." }
} else { Fail "Node" "Install Node.js 24 LTS." }

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) { Pass "npm" ((& npm --version).Trim()) } else { Fail "npm" "Install npm with Node.js." }

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) { Pass "FFmpeg" ((& ffmpeg -version 2>$null | Select-Object -First 1) -join " ") } else { Fail "FFmpeg" "Install FFmpeg and add ffmpeg to PATH." }

$demoEnv = Join-Path $repoRoot ".env.demo.local"
if (-not (Test-Path -LiteralPath $demoEnv)) { $demoEnv = Join-Path $repoRoot ".env.demo.example" }
$values = @{}
foreach ($line in [IO.File]::ReadLines($demoEnv)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#") -or $trimmed.IndexOf("=") -le 0) { continue }
    $values[$trimmed.Substring(0, $trimmed.IndexOf("=")).Trim()] = $trimmed.Substring($trimmed.IndexOf("=") + 1).Trim()
}
$ports = @(
    @{ Name = "MySQL"; Value = $values["MYSQL_HOST_PORT"] }, @{ Name = "Redis"; Value = $values["REDIS_HOST_PORT"] },
    @{ Name = "MinIO-API"; Value = $values["MINIO_API_HOST_PORT"] }, @{ Name = "MinIO-Console"; Value = $values["MINIO_CONSOLE_HOST_PORT"] },
    @{ Name = "RocketMQ-NameServer"; Value = $values["ROCKETMQ_NAMESRV_HOST_PORT"] }, @{ Name = "RocketMQ-Proxy"; Value = $values["ROCKETMQ_PROXY_HOST_PORT"] },
    @{ Name = "RocketMQ-Broker-Fast"; Value = $values["ROCKETMQ_BROKER_FAST_HOST_PORT"] }, @{ Name = "RocketMQ-Broker-Main"; Value = $values["ROCKETMQ_BROKER_MAIN_HOST_PORT"] },
    @{ Name = "RocketMQ-Broker-HA"; Value = $values["ROCKETMQ_BROKER_HA_HOST_PORT"] }, @{ Name = "Backend"; Value = $values["APP_PORT"] },
    @{ Name = "Frontend"; Value = "5173" }
)
$excluded = @()
if ($env:OS -eq "Windows_NT") {
    $excluded = @(& netsh interface ipv4 show excludedportrange protocol=tcp 2>$null | ForEach-Object {
        if ($_ -match '^\s*(\d+)\s+(\d+)') { [PSCustomObject]@{ Start = [int]$Matches[1]; End = [int]$Matches[2] } }
    })
}
foreach ($port in $ports) {
    $number = 0
    if (-not [int]::TryParse([string]$port.Value, [ref]$number) -or $number -lt 1 -or $number -gt 65535) { Fail $port.Name "Set a valid host port in .env.demo.local."; continue }
    $reserved = @($excluded | Where-Object { $number -ge $_.Start -and $number -le $_.End }).Count -gt 0
    $listening = @(Get-NetTCPConnection -State Listen -LocalPort $number -ErrorAction SilentlyContinue).Count -gt 0
    if ($reserved) { Fail "$($port.Name) port $number" "Windows reserves it; change the corresponding value in .env.demo.local." }
    elseif ($listening) { Fail "$($port.Name) port $number" "It is already listening; change the corresponding value in .env.demo.local." }
    else { Pass "$($port.Name)-Port" $number }
}

if ($script:failures -gt 0) { exit 1 }
