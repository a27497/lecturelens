Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envFile = Join-Path $repoRoot ".env.demo.local"
if (-not (Test-Path -LiteralPath $envFile)) { throw "Copy .env.demo.example to .env.demo.local first." }
$instance = if ($env:LECTURELENS_DEMO_INSTANCE) { $env:LECTURELENS_DEMO_INSTANCE } else { "default" }
if ($instance -notmatch '^[a-z0-9-]{1,32}$') { throw "LECTURELENS_DEMO_INSTANCE must match [a-z0-9-]{1,32}." }

Push-Location $repoRoot
try {
    & docker compose --project-name "lecturelens-demo-$instance" --env-file .env.demo.local down
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose shutdown failed for Demo instance $instance." }
    Write-Host "PASS infrastructure-stopped instance=$instance volumes-preserved=true"
} finally { Pop-Location }
