# Saves a Cloudflare API token that can run Workers AI (free daily allowance) into .env.dev.local as
# CLOUDFLARE_AI_TOKEN. Used to repaint mockup art (mockups/assets/ga/src/paint.py). The token is never printed.
#
# What only a person can do: on the page this opens, make sure the permission is "Account · Workers AI · Read"
# (add it if the list is empty), click "Continue to summary", "Create Token", then paste the token here.
#   powershell -ExecutionPolicy Bypass -File infra\share\cf-ai-token.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnvFile = Join-Path $Root ".env.dev.local"

$perms = '[{"key":"workers_ai","type":"read"}]'
$url = "https://dash.cloudflare.com/profile/api-tokens?permissionGroupKeys=" + [uri]::EscapeDataString($perms) +
       "&name=mentor-ai&accountId=*&zoneId=all"
Write-Host ""
Write-Host "1. Trang tao token Cloudflare dang mo (dang nhap neu can)."
Write-Host "2. Quyen phai la: Account - Workers AI - Read (neu trong thi bam 'Add more' va chon)."
Write-Host "3. Bam 'Continue to summary', roi 'Create Token'."
Write-Host "4. Bam 'Copy', quay lai day dan vao (khong hien tren man hinh) roi Enter."
Start-Process $url
$sec = Read-Host "Token" -AsSecureString
$token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
if (-not $token) { Write-Host "Chua dan token." -ForegroundColor Red; exit 1 }

$r = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/user/tokens/verify" -Headers @{ Authorization = "Bearer $token" }
if (-not $r.success) { Write-Host "Token khong hop le." -ForegroundColor Red; exit 1 }

$lines = @()
if (Test-Path $EnvFile) { $lines = @(Get-Content $EnvFile -Encoding UTF8 | Where-Object { $_ -notmatch "^\s*CLOUDFLARE_AI_TOKEN\s*=" }) }
$lines += "CLOUDFLARE_AI_TOKEN=$token"
Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
Write-Host "Da luu token. Quay lai Claude va bao 'xong'." -ForegroundColor Green
