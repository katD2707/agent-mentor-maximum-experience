# Deploys the Mentor hub (Cloudflare Worker + KV) to https://hub.mentor-hoc.workers.dev
#   powershell -ExecutionPolicy Bypass -File infra\hub\deploy.ps1 [-ScriptUrl <Apps Script web app URL>]
# Needs CLOUDFLARE_WORKERS_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment (never printed).
# Generates ADMIN_KEY and SCRIPT_SECRET once and keeps them in mentor\.secrets\ (gitignored). Safe to run again.
param([string]$ScriptUrl = "")
$ErrorActionPreference = "Stop"
$Hub = $PSScriptRoot
$Root = Split-Path -Parent (Split-Path -Parent $Hub)
$Secrets = Join-Path $Root ".secrets"
$Api = "https://api.cloudflare.com/client/v4"

if (-not $env:CLOUDFLARE_WORKERS_TOKEN) { throw "Missing CLOUDFLARE_WORKERS_TOKEN in the environment." }
if (-not $env:CLOUDFLARE_ACCOUNT_ID) {  # the token sees one account: use it
    $env:CLOUDFLARE_ACCOUNT_ID = (Invoke-RestMethod -Uri "$Api/accounts" -Headers @{ Authorization = "Bearer $env:CLOUDFLARE_WORKERS_TOKEN" }).result[0].id
}
$env:CLOUDFLARE_API_TOKEN = $env:CLOUDFLARE_WORKERS_TOKEN   # wrangler reads this name
New-Item -ItemType Directory -Force -Path $Secrets | Out-Null

function New-RandomSecret([int]$Bytes) {
    $b = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($b); $rng.Dispose()
    return (($b | ForEach-Object { $_.ToString("x2") }) -join "")
}
function Get-OrCreateSecret([string]$File, [int]$Bytes) {
    if (-not (Test-Path $File)) { [System.IO.File]::WriteAllText($File, (New-RandomSecret $Bytes), (New-Object System.Text.UTF8Encoding($false))) }
}
$AdminFile = Join-Path $Secrets "hub-admin-key.txt"
$ScriptSecretFile = Join-Path $Secrets "hub-script-secret.txt"
Get-OrCreateSecret $AdminFile 24
Get-OrCreateSecret $ScriptSecretFile 24

# 1. KV namespace "mentor-hub": create if missing, write its id into wrangler.toml
$h = @{ Authorization = "Bearer $env:CLOUDFLARE_WORKERS_TOKEN" }
$kvUrl = "$Api/accounts/$($env:CLOUDFLARE_ACCOUNT_ID)/storage/kv/namespaces"
$ns = (Invoke-RestMethod -Uri "$kvUrl`?per_page=100" -Headers $h).result | Where-Object { $_.title -eq "mentor-hub" } | Select-Object -First 1
if (-not $ns) {
    Write-Host "Creating KV namespace mentor-hub..."
    $ns = (Invoke-RestMethod -Method Post -Uri $kvUrl -Headers $h -ContentType "application/json" -Body '{"title":"mentor-hub"}').result
}
$toml = Join-Path $Hub "wrangler.toml"
$text = [System.IO.File]::ReadAllText($toml)
$text = [regex]::Replace($text, '(?m)^id\s*=\s*"[^"]*"', ('id = "' + $ns.id + '"'))
[System.IO.File]::WriteAllText($toml, $text, (New-Object System.Text.UTF8Encoding($false)))

Push-Location $Hub
try {
    # 2. deploy the worker
    npx --yes wrangler@4.20.0 deploy
    if ($LASTEXITCODE -ne 0) { throw "wrangler deploy failed." }
    # the workers.dev route is off for a new script until enabled
    Invoke-RestMethod -Method Post -Uri "$Api/accounts/$($env:CLOUDFLARE_ACCOUNT_ID)/workers/scripts/hub/subdomain" -Headers $h `
        -ContentType "application/json" -Body '{"enabled":true}' | Out-Null

    # 3. secrets, piped from files so they never reach the screen
    function Set-WorkerSecret([string]$Name, [string]$File) {
        Get-Content -Raw $File | npx --yes wrangler@4.20.0 secret put $Name | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "wrangler secret put $Name failed." }
        Write-Host "Secret $Name set."
    }
    Set-WorkerSecret "ADMIN_KEY" $AdminFile
    Set-WorkerSecret "SCRIPT_SECRET" $ScriptSecretFile
    if ($ScriptUrl) {
        $tmp = Join-Path $Secrets "hub-script-url.tmp"
        [System.IO.File]::WriteAllText($tmp, $ScriptUrl.Trim(), (New-Object System.Text.UTF8Encoding($false)))
        try { Set-WorkerSecret "SCRIPT_URL" $tmp } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
    }
} finally { Pop-Location }

# 4. the Apps Script with the secret filled in, for the owner to paste
$gs = [System.IO.File]::ReadAllText((Join-Path $Hub "apps-script.gs"))
$sec = ([System.IO.File]::ReadAllText($ScriptSecretFile)).Trim()
[System.IO.File]::WriteAllText((Join-Path $Secrets "apps-script.gs"), $gs.Replace("__SCRIPT_SECRET__", $sec), (New-Object System.Text.UTF8Encoding($false)))

Write-Host ""
Write-Host "Hub deployed: https://hub.mentor-hoc.workers.dev" -ForegroundColor Green
Write-Host "Admin page:   https://hub.mentor-hoc.workers.dev/quan-tri  (key: $AdminFile)"
if ($ScriptUrl) { Write-Host "SCRIPT_URL set." } else { Write-Host "Apps Script: paste $(Join-Path $Secrets 'apps-script.gs') (infra\hub\README.md), then run again with -ScriptUrl <url>." }
