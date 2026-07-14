Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$contract = '^[a-z0-9-]{1,32}$'
$cases = @(
    @{ Name = "one-character"; Value = "a"; Expected = $true },
    @{ Name = "over-twelve-characters"; Value = "ps-zero-audit"; Expected = $true },
    @{ Name = "exactly-thirty-two-characters"; Value = ("a" * 32); Expected = $true },
    @{ Name = "thirty-three-characters"; Value = ("a" * 33); Expected = $false },
    @{ Name = "uppercase"; Value = "Demo"; Expected = $false },
    @{ Name = "underscore"; Value = "demo_instance"; Expected = $false },
    @{ Name = "empty"; Value = ""; Expected = $false }
)

foreach ($case in $cases) {
    $actual = [regex]::IsMatch([string] $case.Value, $contract)
    if ($actual -ne $case.Expected) { throw "Instance-name case failed: $($case.Name)." }
    Write-Host "PASS instance-name-$($case.Name) accepted=$actual"
}

$expectedContract = "^[a-z0-9-]{1,32}$"
$expectedMessage = "LECTURELENS_DEMO_INSTANCE must match [a-z0-9-]{1,32}."
foreach ($name in @("start-infrastructure.ps1", "stop-infrastructure.ps1")) {
    $content = Get-Content -LiteralPath (Join-Path $PSScriptRoot $name) -Raw -Encoding UTF8
    if (-not $content.Contains($expectedContract) -or -not $content.Contains($expectedMessage)) {
        throw "PowerShell Demo script does not enforce the instance-name contract: $name"
    }
    Write-Host "PASS instance-name-contract script=$name"
}
