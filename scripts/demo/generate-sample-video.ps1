Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$outputDir = Join-Path $repoRoot ".demo"
$outputFile = Join-Path $outputDir "lecturelens-sample.mp4"

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "FFmpeg is required. Install FFmpeg and make the ffmpeg command available in PATH."
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
& ffmpeg -hide_banner -loglevel error -y `
    -f lavfi -i "color=c=0xf2f4f1:size=640x360:rate=24,drawbox=x=64:y=48:w=512:h=264:color=0xffffff:t=fill,drawbox=x=96:y=84:w=184:h=14:color=0x2f7d65:t=fill,drawbox=x=96:y=122:w=352:h=12:color=0x202a26:t=fill,drawbox=x=96:y=150:w=412:h=8:color=0xa8b0ac:t=fill,drawbox=x=96:y=176:w=372:h=8:color=0xc5cbc8:t=fill,drawbox=x=96:y=220:w=248:h=52:color=0xdceae4:t=fill,drawbox=x=116:y=240:w=136:h=12:color=0x2f7d65:t=fill" `
    -f lavfi -i "sine=frequency=660:sample_rate=48000" `
    -t 2 -c:v libx264 -preset veryfast -crf 32 -pix_fmt yuv420p `
    -c:a aac -b:a 64k -shortest -movflags +faststart $outputFile

if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputFile)) {
    throw "Sample video generation failed."
}

Write-Host "PASS sample-video $outputFile"
