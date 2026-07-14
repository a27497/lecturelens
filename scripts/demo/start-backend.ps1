param([string] $EnvFile = ".env.demo.local")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$envPath = if ([IO.Path]::IsPathRooted($EnvFile)) { $EnvFile } else { Join-Path $repoRoot $EnvFile }
if (-not (Test-Path -LiteralPath $envPath)) { throw "Copy .env.demo.example to .env.demo.local first." }

foreach ($line in [IO.File]::ReadLines($envPath)) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $separator = $trimmed.IndexOf("=")
    if ($separator -le 0) { throw "Invalid Demo environment entry." }
    $name = $trimmed.Substring(0, $separator).Trim()
    $value = $trimmed.Substring($separator + 1).Trim()
    if ($name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { throw "Invalid Demo environment variable name." }
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

$listeners = @(Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) { throw "Port 8080 is already in use. This script will not stop an unknown process." }

Push-Location (Join-Path $repoRoot "backend")
try { & .\mvnw.cmd spring-boot:run; exit $LASTEXITCODE } finally { Pop-Location }
