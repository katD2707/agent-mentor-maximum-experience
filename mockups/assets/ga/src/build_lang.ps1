# Builds the Làng gà village for lg-01 (assets/ga/lang/): renders lang.py (background + occluder cut-outs + layout),
# converts the pictures to WebP and the data to scripts the page can load from file:// (layout.js, actors.js).
#   powershell -ExecutionPolicy Bypass -File mockups\assets\ga\src\build_lang.ps1            render + pack
#   powershell -ExecutionPolicy Bypass -File mockups\assets\ga\src\build_lang.ps1 -PackOnly  pack an earlier render (-From <dir>)
# The characters' sprite sheets come from actors.py (assets/ga/lang/actors/); this only wraps actors.json into actors.js.
# Needs Blender 4.5 and ffmpeg. The full render takes 10-20 minutes.
param([switch]$PackOnly, [string]$From)
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot; $dst = Join-Path (Split-Path -Parent $PSScriptRoot) "lang"
$bl = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
$tmp = if ($From) { $From } else { Join-Path $env:TEMP ("mentor-lang-" + $PID) }
New-Item -ItemType Directory -Force $dst, (Join-Path $dst "occ") | Out-Null
if (-not $PackOnly) {
  New-Item -ItemType Directory -Force $tmp | Out-Null
  $log = & $bl -b -P (Join-Path $src "lang.py") -- $tmp all 2>&1
  if ($log -match "Traceback|Error:") { $log | Select-String "Traceback|Error" | Select-Object -First 8; throw "render failed" }
}
function WebP($in, $out, $q) {
  ffmpeg -v error -y -i $in -c:v libwebp -lossless 0 -q:v $q -pix_fmt yuva420p $out
  if ($LASTEXITCODE) { throw "ffmpeg failed: $out" }
}
WebP (Join-Path $tmp "bg.png") (Join-Path $dst "bg.webp") 90
Get-ChildItem (Join-Path $dst "occ") -Filter *.webp | Remove-Item
Get-ChildItem (Join-Path $tmp "occ") -Filter *.png | ForEach-Object { WebP $_.FullName (Join-Path $dst ("occ\" + $_.BaseName + ".webp")) 90 }
$json = [IO.File]::ReadAllText((Join-Path $tmp "layout.json"))
[IO.File]::WriteAllText((Join-Path $dst "layout.js"), "window.LANG_LAYOUT = $json;`n", (New-Object Text.UTF8Encoding($false)))
$aj = Join-Path $dst "actors\actors.json"
if (Test-Path $aj) {
  $a = [IO.File]::ReadAllText($aj)
  [IO.File]::WriteAllText((Join-Path $dst "actors.js"), "window.LANG_ACTORS = $a;`n", (New-Object Text.UTF8Encoding($false)))
}
if (-not $PackOnly -and -not $From) { Remove-Item -Recurse -Force $tmp }
$kb = [math]::Round(((Get-ChildItem $dst -Recurse -File | Where-Object { $_.FullName -notmatch "\\actors\\" } | Measure-Object Length -Sum).Sum) / 1KB)
Write-Host "done: $dst ($kb KB without actors)" -ForegroundColor Green
