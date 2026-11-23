<#
.SYNOPSIS
  Builds the self-contained Mentor package for F-Eco: dist/mentor-<version>-windows-x64.zip

.DESCRIPTION
  1. freezes the gateway with PyInstaller (one-folder) from a throw-away venv built from uv.lock,
  2. builds the Tauri app (standalone flavour: no updater, starts the bundled gateway),
  3. lays out Mentor.exe + gateway\ and zips it (entries at the zip root, no ../ paths).
  Needs: uv, pnpm, Rust (cargo), Windows PowerShell 5.1+. Nothing is installed globally. Everything is written under
  dist\ (gitignored). Run from anywhere:   powershell -ExecutionPolicy Bypass -File integrations\feco\build.ps1
  -Clean       removes dist\standalone (venv, PyInstaller work files) afterwards.
  -SkipGateway reuses an earlier dist\standalone\out\mentor-gateway.
  -SkipApp     reuses the Mentor.exe of the last tauri build (repack only).
  -PackStage   zips dist\standalone\windows-x64 exactly as it is (use after signing the files there), no re-staging.

  The exe is NOT code-signed. F-Eco requires an Authenticode signature: sign Mentor.exe and gateway\mentor-gateway.exe
  before `f-dev publish` (see README.md).
#>
param([switch]$Clean, [switch]$SkipGateway, [switch]$SkipApp, [switch]$PackStage)
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$app = Join-Path $root 'apps\app'
$tauriConf = Join-Path $app 'src-tauri\tauri.conf.json'
$work = Join-Path $root 'dist\standalone'
$out = Join-Path $root 'dist'

function Invoke-Checked([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

$version = (Get-Content $tauriConf -Raw | ConvertFrom-Json).version
Write-Host "Mentor $version"

# the manifest carries the same version as the app
$manifestPath = Join-Path $PSScriptRoot 'f-app.toml'
$manifest = Get-Content $manifestPath -Raw -Encoding UTF8
$manifest = [regex]::Replace($manifest, '(?m)^version = ".*"\r?$', "version = `"$version`"")
[System.IO.File]::WriteAllText($manifestPath, $manifest, (New-Object System.Text.UTF8Encoding($false)))

# 1. the gateway sidecar
$gatewayOut = Join-Path $work 'out\mentor-gateway'
if (-not $SkipGateway) {
    New-Item -ItemType Directory -Force $work | Out-Null
    $sample = Join-Path $work 'sample-content'
    $venv = Join-Path $work 'venv'
    $py = Join-Path $venv 'Scripts\python.exe'
    $req = Join-Path $work 'req.txt'
    Push-Location $root
    try {
        if (-not (Test-Path $py)) { Invoke-Checked 'uv venv' { uv venv $venv --python 3.12 } }
        Invoke-Checked 'uv export' { uv export --frozen --package mentor-gateway --no-dev --no-emit-workspace --no-hashes -o $req }
        Invoke-Checked 'pip install (locked)' { uv pip install --python $py -r $req pyinstaller }
        Invoke-Checked 'pip install (workspace)' { uv pip install --python $py --no-deps --reinstall ./packages/mentor-schemas ./sandbox-image/scripts ./services/gateway }
        Invoke-Checked 'sample content' { & $py services\gateway\standalone\build_sample.py mentor-content $sample }
        Invoke-Checked 'pyinstaller' {
            & (Join-Path $venv 'Scripts\pyinstaller.exe') --noconfirm --clean --onedir --name mentor-gateway --noconsole `
                --distpath (Join-Path $work 'out') --workpath (Join-Path $work 'work') --specpath $work `
                --collect-submodules uvicorn --collect-submodules mentor_gateway --collect-data tzdata --collect-data mentor_gateway `
                --exclude-module tkinter --exclude-module torch --add-data "$sample;sample-content" `
                services\gateway\standalone\entry.py
        }
    } finally { Pop-Location }
}
if (-not (Test-Path (Join-Path $gatewayOut 'mentor-gateway.exe'))) { throw "no frozen gateway at $gatewayOut" }

# the sample courses are refreshed on every run (also with -SkipGateway): a few MB of copying, no re-freezing
$sampleSrc = Join-Path $work 'sample-content'
Invoke-Checked 'sample content' { uv run --no-project python (Join-Path $root 'services\gateway\standalone\build_sample.py') (Join-Path $root 'mentor-content') $sampleSrc }
$sampleDst = Join-Path $gatewayOut '_internal\sample-content'
if (Test-Path $sampleDst) { Remove-Item $sampleDst -Recurse -Force }
Copy-Item $sampleSrc $sampleDst -Recurse

# 2. the app (the web build runs as Tauri's beforeBuildCommand)
if (-not $SkipApp) {
Push-Location $app
try {
    Invoke-Checked 'pnpm install' { pnpm install --frozen-lockfile }
    Invoke-Checked 'tauri build' { pnpm tauri build --no-bundle --config src-tauri/tauri.standalone.conf.json }
} finally { Pop-Location }
}
$exe = Join-Path $app 'src-tauri\target\release\mentor-app.exe'
if (-not (Test-Path $exe)) { throw "tauri did not produce $exe" }

# 3. the package folder and the zip
$stage = Join-Path $work 'windows-x64'
if (-not $PackStage) {
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory -Force $stage | Out-Null
    Copy-Item $exe (Join-Path $stage 'Mentor.exe')
    Copy-Item $gatewayOut (Join-Path $stage 'gateway') -Recurse
    Copy-Item (Join-Path $root 'THIRD_PARTY_NOTICES.md') $stage
}
if (-not (Test-Path (Join-Path $stage 'Mentor.exe'))) { throw "nothing staged in $stage" }
$zip = Join-Path $out "mentor-$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
# written entry by entry: Windows PowerShell 5.1's CreateFromDirectory stores backslash names, a zip must use "/"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open($zip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    $prefix = $stage.TrimEnd('\') + '\'
    foreach ($f in Get-ChildItem $stage -Recurse -File) {
        $name = $f.FullName.Substring($prefix.Length).Replace('\', '/')
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $f.FullName, $name, [System.IO.Compression.CompressionLevel]::Optimal)
    }
} finally { $archive.Dispose() }

$mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Package: $zip ($mb MB). Unsigned: sign Mentor.exe and gateway\mentor-gateway.exe before publishing."
if ($Clean) { Remove-Item $work -Recurse -Force }
