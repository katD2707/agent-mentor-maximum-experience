# Shares the Mentor server running on this PC with everyone who installed the app, at a fixed address:
#   https://app.mentor-hoc.workers.dev/api   (the address compiled into the GitHub Release installers)
# Starts the router + gateway (infra\dev-up.ps1 -ServerOnly, skipped when already running), opens a Cloudflare quick
# tunnel to the gateway, and points the worker at the tunnel's new address. Restarts the tunnel if it drops and keeps
# the PC from sleeping while this window is open. Close the window to stop sharing (the gateway keeps running).
#
#   powershell -ExecutionPolicy Bypass -File infra\share\share-up.ps1
#
# Needs: cloudflared (winget install Cloudflare.cloudflared) and CLOUDFLARE_WORKERS_TOKEN in .env.dev.local
# (infra\share\cf-token.ps1). README.md has the details.
param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnvFile = Join-Path $Root ".env.dev.local"
$Api = "https://api.cloudflare.com/client/v4"
$Public = "https://app.mentor-hoc.workers.dev"

$token = ""
foreach ($l in Get-Content $EnvFile -Encoding UTF8) { if ($l -match '^\s*CLOUDFLARE_WORKERS_TOKEN\s*=\s*(.+)$') { $token = $Matches[1].Trim() } }
if (-not $token) { throw "Missing CLOUDFLARE_WORKERS_TOKEN in .env.dev.local: run infra\share\cf-token.ps1 first." }
$h = @{ Authorization = "Bearer $token" }
$acc = (Invoke-RestMethod -Uri "$Api/accounts" -Headers $h).result[0].id
$ns = ((Invoke-RestMethod -Uri "$Api/accounts/$acc/storage/kv/namespaces" -Headers $h).result | Where-Object title -eq "mentor-share").id
if (-not $ns) { throw "KV namespace 'mentor-share' not found (README.md: first-time setup)." }

$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf) { $cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe" }
if (-not (Test-Path $cf)) { throw "cloudflared is not installed: winget install Cloudflare.cloudflared" }

# keep the PC awake (not the screen) while sharing
Add-Type -Namespace Mentor -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);'
[void][Mentor.Power]::SetThreadExecutionState([uint32]"0x80000001")  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
    Write-Host "Starting the router and the gateway..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "infra\dev-up.ps1") -ServerOnly
    foreach ($i in 1..60) { if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { break }; Start-Sleep 2 }
}

while ($true) {
    Write-Host "Opening the tunnel..."
    $log = Join-Path $env:TEMP "mentor-tunnel.log"
    Remove-Item $log -ErrorAction SilentlyContinue
    $p = Start-Process $cf -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port" `
        -RedirectStandardError $log -NoNewWindow -PassThru
    $url = $null
    foreach ($i in 1..60) {
        Start-Sleep 1
        if (Test-Path $log) {
            $m = Select-String -Path $log -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($m) { $url = $m.Matches[0].Value; break }
        }
        if ($p.HasExited) { break }
    }
    if ($url) {
        Invoke-RestMethod -Method Put -Uri "$Api/accounts/$acc/storage/kv/namespaces/$ns/values/target" -Headers $h `
            -ContentType "text/plain" -Body $url | Out-Null
        Write-Host ""
        Write-Host "Mentor is shared at $Public (tunnel $url)." -ForegroundColor Green
        Write-Host "Keep this window open. Close it to stop sharing."
        $p.WaitForExit()
        Write-Host "The tunnel stopped; reopening in 5 s..." -ForegroundColor Yellow
    } else {
        if (-not $p.HasExited) { $p.Kill() }
        Write-Host "No tunnel address yet (network?); retrying in 15 s..." -ForegroundColor Yellow
        Start-Sleep 10
    }
    Start-Sleep 5
}
