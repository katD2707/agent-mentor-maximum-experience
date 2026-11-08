# Starts the dev stack with real models, each service in its own PowerShell window:
#   model router (LiteLLM, :4000) + gateway (:8000) + app (apps/app, Vite, :5173) [+ Tauri shell with -Desktop]
# The router and the gateway read secrets from .env.dev.local at the repo root (gitignored).
# Dev accounts (MENTOR_ENV=dev): hocsinh / 123456 (student), giaovien / 123456 (teacher).
# Usage, from the repo root:
#   powershell -ExecutionPolicy Bypass -File infra\dev-up.ps1 [-Desktop] [-DataDir var-dev]
# After the data model changed, wipe the dev DB:  Remove-Item -Recurse -Force var-dev  (an old ops.db is also
# recreated automatically on start-up when it has the pre-redesign schema).
# A service whose port is already taken is skipped, never killed.
param(
    [ValidateSet("all", "router", "gateway", "app", "desktop")] [string]$Service = "all",
    [string]$DataDir = "var-dev",
    [switch]$Desktop
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.dev.local"

function Import-DevEnv {
    if (-not (Test-Path $EnvFile)) { throw "Missing $EnvFile (needs FPT_API_BASE, FPT_API_KEY, MODEL_ROUTER_MASTER_KEY)." }
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$' -and $Matches[2].Trim() -ne "") {
            Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim()
        }
    }
    if (-not $env:FPT_API_KEY) { throw "FPT_API_KEY is empty in $EnvFile." }
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
}

function Test-Port([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Url([string]$Url, [int]$Seconds) {
    for ($i = 0; $i -lt $Seconds; $i += 2) {
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $Url | Out-Null; return $true } catch { Start-Sleep 2 }
    }
    return $false
}

switch ($Service) {
    "router" {
        $Host.UI.RawUI.WindowTitle = "mentor: model router :4000"
        Import-DevEnv
        Set-Location $Root
        uv tool run --from "litellm[proxy]" litellm --config services/model-router/config.yaml --port 4000
    }
    "gateway" {
        $Host.UI.RawUI.WindowTitle = "mentor: gateway :8000"
        Set-Location $Root
        $env:PYTHONUTF8 = "1"
        $env:MENTOR_ENV = "dev"
        $env:MENTOR_DATA_DIR = $DataDir
        $env:WEB_ORIGIN = "http://localhost:5173"
        # Ask, the planner, semantic course search and the course builder call models through the router
        Import-DevEnv
        # 127.0.0.1, not localhost: on Windows each new localhost connection costs 2-3 s
        if (-not $env:MODEL_ROUTER_URL) { $env:MODEL_ROUTER_URL = "http://127.0.0.1:4000" }
        # builder subprocesses read MODEL_ROUTER_KEY; the gateway itself also accepts the master key
        if (-not $env:MODEL_ROUTER_KEY) { $env:MODEL_ROUTER_KEY = $env:MODEL_ROUTER_MASTER_KEY }
        $env:BUILDER_DEEPTUTOR = "1"
        uv run uvicorn mentor_gateway.app:app --port 8000
    }
    "app" {
        $Host.UI.RawUI.WindowTitle = "mentor: app :5173"
        Set-Location (Join-Path $Root "apps\app")
        pnpm dev
    }
    "desktop" {
        $Host.UI.RawUI.WindowTitle = "mentor: desktop"
        Set-Location (Join-Path $Root "apps\app")
        $cargo = Join-Path $env:USERPROFILE ".cargo\bin"
        if ($env:PATH -notlike "*$cargo*") { $env:PATH += ";$cargo" }
        $env:VITE_API_BASE = "http://localhost:8000/api"
        pnpm tauri dev
    }
    "all" {
        Import-DevEnv  # fail fast on a missing router key before opening windows
        $plan = @(@{ Name = "router"; Port = 4000 }, @{ Name = "gateway"; Port = 8000 }, @{ Name = "app"; Port = 5173 })
        if ($Desktop) { $plan += @{ Name = "desktop"; Port = 0 } }
        foreach ($s in $plan) {
            if ($s.Port -and (Test-Port $s.Port)) { Write-Host "skip $($s.Name): port $($s.Port) already in use"; continue }
            # PowerShell 5.1 joins -ArgumentList without quoting, and the repo path has spaces.
            Start-Process powershell -ArgumentList ("-NoExit -ExecutionPolicy Bypass -File `"$PSCommandPath`" " +
                "-Service $($s.Name) -DataDir `"$DataDir`"") -WorkingDirectory $Root
            Write-Host "started $($s.Name)"
        }
        Write-Host "Open http://localhost:5173 once the gateway window shows 'Uvicorn running'. Data dir: $DataDir"
    }
}
