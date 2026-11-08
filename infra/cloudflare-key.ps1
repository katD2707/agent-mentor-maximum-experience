# Gets a Cloudflare Workers AI key for course illustrations (FLUX.1 schnell, free 10,000 neurons/day, no card)
# and saves CLOUDFLARE_ACCOUNT_ID + CLOUDFLARE_API_TOKEN into .env.dev.local. The token is never printed.
#
# What only a person can do (Cloudflare needs a captcha and email confirmation): create the account once and
# click "Create" on the token page. Everything else is done here: open the right pages, read the pasted token
# without echoing it, find the account id, test one image, write the env file.
#
# Usage, from the repo root:
#   powershell -ExecutionPolicy Bypass -File infra\cloudflare-key.ps1          # first time
#   powershell -ExecutionPolicy Bypass -File infra\cloudflare-key.ps1 -Check   # only test the saved key
param([switch]$Check, [switch]$NoBrowser)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.dev.local"
$Api = "https://api.cloudflare.com/client/v4"
$Model = "@cf/black-forest-labs/flux-1-schnell"

function Read-EnvValue([string]$Name) {
    if (-not (Test-Path $EnvFile)) { return "" }
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        if ($line -match "^\s*$Name\s*=\s*(.*)$") { return $Matches[1].Trim() }
    }
    return ""
}

function Set-EnvValues([hashtable]$Values) {
    $lines = @()
    if (Test-Path $EnvFile) { $lines = @(Get-Content $EnvFile -Encoding UTF8) }
    foreach ($name in $Values.Keys) {
        $found = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^\s*$name\s*=") { $lines[$i] = "$name=$($Values[$name])"; $found = $true }
        }
        if (-not $found) { $lines += "$name=$($Values[$name])" }
    }
    Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
}

function Invoke-Cf([string]$Method, [string]$Path, [string]$Token, $Body = $null) {
    $req = @{ Method = $Method; Uri = "$Api$Path"; Headers = @{ Authorization = "Bearer $Token" }; TimeoutSec = 60 }
    if ($null -ne $Body) { $req.Body = ($Body | ConvertTo-Json -Compress); $req.ContentType = "application/json" }
    try { return Invoke-RestMethod @req }
    catch {
        $msg = $_.Exception.Message
        try { $msg = (($_.ErrorDetails.Message | ConvertFrom-Json).errors | ForEach-Object { $_.message }) -join "; " } catch {}
        throw "Cloudflare $Method $Path failed: $msg"
    }
}

function Test-Image([string]$AccountId, [string]$Token) {
    Write-Host "Thử sinh 1 ảnh nhỏ bằng $Model ..."
    $t0 = Get-Date
    $r = Invoke-Cf "POST" "/accounts/$AccountId/ai/run/$Model" $Token @{ prompt = "a red apple on a white table, simple flat illustration"; steps = 4 }
    $b64 = $r.result.image
    if (-not $b64) { throw "Cloudflare trả về nhưng không có ảnh." }
    $kb = [math]::Round(($b64.Length * 3 / 4) / 1024)
    Write-Host ("OK: ảnh {0} KB trong {1:n1} s." -f $kb, ((Get-Date) - $t0).TotalSeconds) -ForegroundColor Green
}

if ($Check) {
    $acc = Read-EnvValue "CLOUDFLARE_ACCOUNT_ID"; $tok = Read-EnvValue "CLOUDFLARE_API_TOKEN"
    if (-not $acc -or -not $tok) { throw "Chưa có CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN trong .env.dev.local." }
    Test-Image $acc $tok
    exit 0
}

Write-Host ""
Write-Host "Lấy key Cloudflare Workers AI (miễn phí, không cần thẻ)" -ForegroundColor Cyan
Write-Host "  1. Chưa có tài khoản: đăng ký ở trang vừa mở, xác nhận email."
Write-Host "  2. Thanh bên trái: AI > Workers AI > nút 'REST API' (hoặc 'Use REST API') > 'Create a Workers AI API Token'."
Write-Host "     Không thấy nút đó: biểu tượng người góc phải trên > Profile > API Tokens > Create Token >"
Write-Host "     mẫu 'Workers AI' > Use template > Continue to summary > Create Token."
Write-Host "  3. Bấm nút copy token, quay lại đây và dán (không hiện ra màn hình)."
Write-Host ""
if (-not $NoBrowser) {
    $has = Read-Host "Đã có tài khoản Cloudflare chưa? (c/k)"
    if ($has -match '^[kKnN]') { Start-Process "https://dash.cloudflare.com/sign-up" ; Read-Host "Đăng ký xong thì nhấn Enter" | Out-Null }
    Start-Process "https://dash.cloudflare.com/?to=/:account/ai/workers-ai"
}

$secure = Read-Host "Dán token" -AsSecureString
$token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)).Trim()
if ($token.Length -lt 20) { throw "Token quá ngắn, hãy copy lại." }

# Account id: the token usually can list its own account; otherwise ask (it is shown on the same Workers AI page).
$accountId = ""
try {
    $accs = @((Invoke-Cf "GET" "/accounts?per_page=50" $token).result)
    if ($accs.Count -eq 1) { $accountId = $accs[0].id; Write-Host "Tài khoản: $($accs[0].name)" }
    elseif ($accs.Count -gt 1) {
        for ($i = 0; $i -lt $accs.Count; $i++) { Write-Host "  [$($i + 1)] $($accs[$i].name)" }
        $pick = [int](Read-Host "Chọn tài khoản (số)")
        $accountId = $accs[$pick - 1].id
    }
} catch { Write-Host "Token không liệt kê được tài khoản, sẽ hỏi Account ID." }
if (-not $accountId) { $accountId = (Read-Host "Dán Account ID (ở trang Workers AI, mục 'Account ID')").Trim() }
if ($accountId -notmatch '^[0-9a-f]{32}$') { throw "Account ID không đúng dạng (32 ký tự hex)." }

Test-Image $accountId $token
Set-EnvValues @{ CLOUDFLARE_ACCOUNT_ID = $accountId; CLOUDFLARE_API_TOKEN = $token }
Write-Host "Đã lưu vào .env.dev.local. Bộ soạn khóa sẽ dùng Cloudflare trước các nguồn ảnh khác (IMAGE_SOURCES=auto)." -ForegroundColor Green
