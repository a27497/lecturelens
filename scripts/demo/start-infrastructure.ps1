Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envFile = Join-Path $repoRoot ".env.demo.local"
if (-not (Test-Path -LiteralPath $envFile)) { throw "Copy .env.demo.example to .env.demo.local first." }

$instance = if ($env:LECTURELENS_DEMO_INSTANCE) { $env:LECTURELENS_DEMO_INSTANCE } else { "default" }
if ($instance -notmatch '^[a-z0-9-]{1,32}$') { throw "LECTURELENS_DEMO_INSTANCE must match [a-z0-9-]{1,32}." }
$projectName = "lecturelens-demo-$instance"

function Compose([string[]] $Arguments) {
    & docker compose --project-name $projectName --env-file .env.demo.local @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose command failed for Demo instance $instance." }
}

function Wait-Healthy([string] $Service) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $id = ((& docker compose --project-name $projectName --env-file .env.demo.local ps -q $Service) -join "").Trim()
        if ($id) {
            $health = (& docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $id).Trim()
            if ($health -eq "healthy") { return }
        }
        Start-Sleep -Seconds 2
    }
    throw "$Service did not become healthy for Demo instance $instance."
}

function Wait-Completed([string] $Service) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $id = ((& docker compose --project-name $projectName --env-file .env.demo.local ps -aq $Service) -join "").Trim()
        if ($id) {
            $state = (& docker inspect -f '{{.State.Status}}:{{.State.ExitCode}}' $id).Trim()
            if ($state -eq "exited:0") { return }
        }
        Start-Sleep -Seconds 2
    }
    throw "$Service did not complete successfully for Demo instance $instance."
}

function Wait-Running([string] $Service) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        $id = ((& docker compose --project-name $projectName --env-file .env.demo.local ps -q $Service) -join "").Trim()
        if ($id -and ((& docker inspect -f '{{.State.Status}}' $id).Trim() -eq "running")) { return }
        Start-Sleep -Seconds 2
    }
    throw "$Service did not become running for Demo instance $instance."
}

Push-Location $repoRoot
try {
    Compose @("up", "-d", "mysql", "redis", "minio", "minio-init", "rocketmq-store-init", "rocketmq-namesrv", "rocketmq-broker")
    Wait-Healthy "mysql"
    Wait-Healthy "redis"
    Wait-Healthy "minio"
    Wait-Completed "minio-init"
    Wait-Completed "rocketmq-store-init"
    Wait-Running "rocketmq-namesrv"
    Wait-Running "rocketmq-broker"

    $mqReady = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        & docker compose --project-name $projectName --env-file .env.demo.local exec -T rocketmq-broker sh -lc "/home/rocketmq/rocketmq-5.3.4/bin/mqadmin clusterList -n rocketmq-namesrv:9876 >/dev/null 2>&1"
        if ($LASTEXITCODE -eq 0) { $mqReady = $true; break }
        Start-Sleep -Seconds 3
    }
    if (-not $mqReady) { throw "RocketMQ broker did not become ready." }
    & docker compose --project-name $projectName --env-file .env.demo.local exec -T rocketmq-broker sh -lc "/home/rocketmq/rocketmq-5.3.4/bin/mqadmin updateTopic -n rocketmq-namesrv:9876 -c DefaultCluster -t courselingo-analysis-task >/dev/null"
    if ($LASTEXITCODE -ne 0) { throw "RocketMQ Demo topic initialization failed." }
    Write-Host "PASS infrastructure-ready instance=$instance project=$projectName"
} finally { Pop-Location }
