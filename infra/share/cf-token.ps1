# Saves a Cloudflare API token that can deploy the share worker (infra/share/README.md) into .env.dev.local as
# CLOUDFLARE_WORKERS_TOKEN. The token is never printed.
#
# What only a person can do: click "Continue to summary" and "Create Token" on the page this opens, then paste the token.
#   powershell -ExecutionPolicy Bypass -File infra\share\cf-token.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnvFile = Join-Path $Root ".env.dev.local"

$perms = '[{"key":"workers_scripts","type":"edit"},{"key":"workers_kv_storage","type":"edit"},{"key":"account_settings","type":"read"}]'
$url = "https://dash.cloudflare.com/profile/api-tokens?permissionGroupKeys=" + [uri]::EscapeDataString($perms) +
       "&name=mentor-share&accountId=*&zoneId=all"
Write-Host ""
Write-Host "1. Trang tao token Cloudflare dang mo (dang nhap neu can)."
Write-Host "2. Bam 'Continue to summary', roi 'Create Token'."
Write-Host "3. Bam 'Copy' de chep token, quay lai day dan vao (khong hien tren man hinh) roi Enter."
Start-Process $url
$sec = Read-Host "Token" -AsSecureString
$token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
if (-not $token) { Write-Host "Chua dan token." -ForegroundColor Red; exit 1 }

$r = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/user/tokens/verify" -Headers @{ Authorization = "Bearer $token" }
if (-not $r.success) { Write-Host "Token khong hop le." -ForegroundColor Red; exit 1 }

$lines = @()
if (Test-Path $EnvFile) { $lines = @(Get-Content $EnvFile -Encoding UTF8 | Where-Object { $_ -notmatch "^\s*CLOUDFLARE_WORKERS_TOKEN\s*=" }) }
$lines += "CLOUDFLARE_WORKERS_TOKEN=$token"
Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
Write-Host "Da luu token. Quay lai Claude va bao 'xong'." -ForegroundColor Green
