<#
.SYNOPSIS
  Builds the Mentor desktop installer (NSIS, per-user, no admin) with the web origin baked in.

.DESCRIPTION
  1. Checks the origin: https, or plain http only for localhost (test builds).
  2. Sets the version in tauri.conf.json, Cargo.toml and package.json (only writes files that change).
  3. Makes sure the bundle icons exist (regenerates them from icon.svg when missing or older), and
     copies the mascot element (packages\mentor-mascot\mascot.js -> src\mascot.js, see
     scripts\sync-mascot.mjs; `tauri build` runs the same script as its beforeBuildCommand).
  4. pnpm install, then `pnpm tauri build` with WEB_ORIGIN set, into a separate cargo target dir
     (default apps\desktop\target-release) so it never fights a running `pnpm tauri dev` over
     src-tauri\target\debug\mentor-desktop.exe.
  5. Copies the installer to <repo>\dist\Mentor-Setup-<version>.exe and prints its size and SHA-256
     (also written to <installer>.sha256).

  End users never set an environment variable: release builds use the baked origin and ignore
  WEB_ORIGIN at run time (see web_origin() in src-tauri\src\main.rs).

  Windows PowerShell 5.1 or later. Needs Rust (MSVC), the VS C++ build tools, Node 20+ and pnpm.
  The first build downloads NSIS into %LOCALAPPDATA%\tauri if it is not there yet.

.PARAMETER WebOrigin
  Where the panel loads the web app from, e.g. https://mentor.example.vn (path is dropped).

.PARAMETER Version
  x.y.z. Default: the version already in tauri.conf.json.

.PARAMETER SignCommand
  Optional code-signing command, run by Tauri on the app exe, the uninstaller and the installer.
  `%1` is replaced by the file path, e.g.
  'signtool sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a %1'
  Without it the installer is unsigned and Windows SmartScreen shows "Windows protected your PC"
  (users click "More info" -> "Run anyway"; see docs\huong-dan-su-dung.md).

.PARAMETER TargetDir
  Cargo target dir for this build. Default: apps\desktop\target-release.

.PARAMETER RegenerateIcons
  Regenerate src-tauri\icons from icon.svg even if they look up to date.

.PARAMETER SkipInstall
  Skip `pnpm install`.

.EXAMPLE
  .\build-release.ps1 -WebOrigin https://mentor.example.vn -Version 0.1.0

.EXAMPLE
  .\build-release.ps1 -WebOrigin http://localhost:3000     # test build against the dev web app
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$WebOrigin,
    [string]$Version,
    [string]$SignCommand,
    [string]$TargetDir,
    [switch]$RegenerateIcons,
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$DesktopDir = $PSScriptRoot
$TauriDir = Join-Path $DesktopDir 'src-tauri'
$RepoRoot = (Resolve-Path (Join-Path $DesktopDir '..\..')).Path
$DistDir = Join-Path $RepoRoot 'dist'
if (-not $TargetDir) { $TargetDir = Join-Path $DesktopDir 'target-release' }
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Fail([string]$msg) { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# Runs a native command; fails the script on a non-zero exit code. Stderr (cargo progress) is not
# turned into PowerShell errors.
function Invoke-Native([string]$what, [scriptblock]$cmd) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $cmd } finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { Fail "$what failed (exit code $LASTEXITCODE)" }
}

# ------------------------------------------------------------------ 1. origin
$uri = $null
if (-not [Uri]::TryCreate($WebOrigin.Trim(), [UriKind]::Absolute, [ref]$uri) -or
    ($uri.Scheme -ne 'https' -and $uri.Scheme -ne 'http') -or -not $uri.Host) {
    Fail "-WebOrigin '$WebOrigin' is not an http(s) URL, e.g. https://mentor.example.vn"
}
$isLocal = @('localhost', '127.0.0.1', '[::1]', '::1') -contains $uri.Host.ToLowerInvariant()
if ($uri.Scheme -eq 'http' -and -not $isLocal) {
    Fail "-WebOrigin must use https (plain http is only allowed for localhost test builds)"
}
$Origin = $uri.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
$TestBuild = $uri.Scheme -ne 'https'

# ------------------------------------------------------------------ 2. version
$confPath = Join-Path $TauriDir 'tauri.conf.json'
$cargoPath = Join-Path $TauriDir 'Cargo.toml'
$pkgPath = Join-Path $DesktopDir 'package.json'
$conf = [IO.File]::ReadAllText($confPath)
if (-not $Version) { $Version = (ConvertFrom-Json $conf).version }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "-Version '$Version' must look like 0.1.0" }

function Set-FileVersion([string]$path, [string]$pattern, [string]$replacement) {
    $text = [IO.File]::ReadAllText($path)
    $re = New-Object System.Text.RegularExpressions.Regex($pattern, 'Multiline')
    if (-not $re.IsMatch($text)) { Fail "no version field found in $path" }
    $new = $re.Replace($text, $replacement, 1)
    if ($new -ne $text) {
        # Only write when it changes: a running `pnpm tauri dev` rebuilds on any src-tauri change.
        [IO.File]::WriteAllText($path, $new, $Utf8NoBom)
        Write-Host "    set version $Version in $path"
    }
}
Step "Version $Version"
Set-FileVersion $confPath '^(\s*"version"\s*:\s*")[^"]*(")' "`${1}$Version`${2}"
Set-FileVersion $cargoPath '^(version\s*=\s*")[^"]*(")' "`${1}$Version`${2}"
Set-FileVersion $pkgPath '^(\s*"version"\s*:\s*")[^"]*(")' "`${1}$Version`${2}"

# Release builds must not ship devtools: the tauri `devtools` cargo feature must stay off.
if ((Get-Content $cargoPath -Raw) -match 'devtools') { Fail "Cargo.toml enables 'devtools'; remove it for release builds" }

# ------------------------------------------------------------------ 3. tools
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    $cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
    if (Test-Path (Join-Path $cargoBin 'cargo.exe')) {
        $env:PATH = "$cargoBin;$env:PATH"
    } else {
        Fail "cargo not found (install Rust from https://rustup.rs, MSVC toolchain)"
    }
}
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) { Fail "pnpm not found (npm install -g pnpm)" }

Push-Location $DesktopDir
$savedEnv = @{ WEB_ORIGIN = $env:WEB_ORIGIN; CARGO_TARGET_DIR = $env:CARGO_TARGET_DIR }
try {
    if (-not $SkipInstall) {
        Step "pnpm install"
        Invoke-Native 'pnpm install' { pnpm install --frozen-lockfile }
    }

    # -------------------------------------------------------------- 4. icons
    $iconsDir = Join-Path $TauriDir 'icons'
    $svg = Join-Path $DesktopDir 'icon.svg'
    $needed = @('32x32.png', '128x128.png', '128x128@2x.png', 'icon.icns', 'icon.ico', 'icon.png')
    $missing = @($needed | Where-Object { -not (Test-Path (Join-Path $iconsDir $_)) })
    $ico = Join-Path $iconsDir 'icon.ico'
    $stale = (Test-Path $ico) -and (Test-Path $svg) -and ((Get-Item $svg).LastWriteTime -gt (Get-Item $ico).LastWriteTime)
    if ($RegenerateIcons -or $missing.Count -gt 0 -or $stale) {
        Step "Generating icons from icon.svg"
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        pnpm tauri icon $svg
        $ok = $LASTEXITCODE -eq 0
        $ErrorActionPreference = $prev
        if (-not $ok) {
            # Older CLIs cannot read SVG: fall back to a PNG source (1024x1024 preferred).
            $png = @((Join-Path $DesktopDir 'icon.png'), (Join-Path $iconsDir 'icon.png')) |
                Where-Object { Test-Path $_ } | Select-Object -First 1
            if (-not $png) { Fail "tauri icon could not read icon.svg; export it as apps\desktop\icon.png (1024x1024) and rerun" }
            $tmpPng = Join-Path $env:TEMP 'mentor-icon-source.png'
            Copy-Item $png $tmpPng -Force   # the source may be overwritten by the generator itself
            Write-Host "    icon.svg failed; using $png"
            Invoke-Native 'tauri icon' { pnpm tauri icon $tmpPng }
        }
    } else {
        Write-Host "    icons up to date"
    }

    # The bubble's mascot is a plain file next to bubble.html (frontendDist is ..\src).
    Step "Syncing the mascot element"
    Invoke-Native 'sync-mascot' { node (Join-Path $DesktopDir 'scripts\sync-mascot.mjs') }
    if (-not (Test-Path (Join-Path $DesktopDir 'src\mascot.js'))) {
        Write-Host "    src\mascot.js missing: the bubble will show the plain 'M' tile" -ForegroundColor Yellow
    }

    # -------------------------------------------------------------- 5. build
    $env:WEB_ORIGIN = $Origin
    $env:CARGO_TARGET_DIR = $TargetDir
    New-Item -ItemType Directory -Force $TargetDir | Out-Null
    $buildArgs = @('tauri', 'build', '--bundles', 'nsis')
    if ($SignCommand) {
        # Passed as a config file: PowerShell 5.1 mangles quotes in JSON given on the command line.
        $override = Join-Path $TargetDir 'sign-override.json'
        $json = @{ bundle = @{ windows = @{ signCommand = $SignCommand } } } | ConvertTo-Json -Depth 5
        [IO.File]::WriteAllText($override, $json, $Utf8NoBom)
        $buildArgs += @('--config', $override)
    }
    Step "Building Mentor $Version for $Origin (target dir $TargetDir)"
    if ($TestBuild) { Write-Host "    TEST BUILD (plain http): not for end users" -ForegroundColor Yellow }
    Invoke-Native 'pnpm tauri build' { pnpm @buildArgs }

    # -------------------------------------------------------------- 6. collect
    $exe = Join-Path $TargetDir 'release\mentor-desktop.exe'
    $bytes = [IO.File]::ReadAllBytes($exe)
    if ([Text.Encoding]::ASCII.GetString($bytes).IndexOf($Origin, [StringComparison]::Ordinal) -lt 0) {
        Fail "$Origin is not baked into $exe (stale build? delete $TargetDir and rerun)"
    }
    $bundleDir = Join-Path $TargetDir 'release\bundle\nsis'
    $setup = Get-ChildItem $bundleDir -Filter "*_${Version}_*-setup.exe" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $setup) { Fail "no NSIS installer for $Version in $bundleDir" }

    New-Item -ItemType Directory -Force $DistDir | Out-Null
    $suffix = ''
    if ($TestBuild) { $suffix = '-' + ($uri.Host -replace '[^A-Za-z0-9.-]', '') }
    $outName = "Mentor-Setup-$Version$suffix.exe"
    $out = Join-Path $DistDir $outName
    Copy-Item $setup.FullName $out -Force
    $hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText("$out.sha256", "$hash  $outName`n", $Utf8NoBom)
    $sizeMb = [Math]::Round((Get-Item $out).Length / 1MB, 2)

    $sig = (Get-AuthenticodeSignature $out).Status
    Write-Host ""
    Write-Host "Installer : $out" -ForegroundColor Green
    Write-Host "Size      : $sizeMb MB"
    Write-Host "SHA-256   : $hash"
    Write-Host "Origin    : $Origin"
    Write-Host "Signature : $sig"
    if ($sig -ne 'Valid') {
        Write-Host "            unsigned: users will see SmartScreen ('More info' -> 'Run anyway')." -ForegroundColor Yellow
    }
} finally {
    foreach ($k in $savedEnv.Keys) {
        if ($null -eq $savedEnv[$k]) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue }
        else { Set-Item "Env:$k" $savedEnv[$k] }
    }
    Pop-Location
}
