# Builds the Gunny-style costume sprites of one subject into assets/ga/trang-phuc/ (never touches the live sprites in assets/ga/).
#   powershell -ExecutionPolicy Bypass -File mockups\assets\ga\src\build_costume.ps1 -Subject toan -Anim 3,4
# Output names follow the live ones: <id>-1.png, <id>-2.png, <id>.png (stage 3), <id>-4.png, and -dung / -nhay WebP for the stages in -Anim.
param([string]$Subject = "toan", [string[]]$Stages = @("1", "2", "3", "4"), [string[]]$Anim = @("3", "4"), [switch]$Lineup)
$Stages = ($Stages -join ",") -split ","; $Anim = ($Anim -join ",") -split ","
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot; $dst = Join-Path (Split-Path -Parent $PSScriptRoot) "trang-phuc"; New-Item -ItemType Directory -Force $dst | Out-Null
$bl = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
$tmp = Join-Path $env:TEMP ("mentor-costume-" + $PID); New-Item -ItemType Directory -Force $tmp | Out-Null
$EQ = "eq=saturation=1.2:contrast=1.04"
function Blend($out, [string[]]$rest) {
  $log = & $bl -b -P (Join-Path $src "chicken.py") -- $out @rest 2>&1
  if ($log -match "Traceback|Error:") { $log | Select-String "Traceback|Error" | Select-Object -First 5; throw "render failed: $rest" }
}
foreach ($st in $Stages) {
  $n = if ($st -eq "3") { $Subject } else { "$Subject-$st" }
  $o = Join-Path $tmp $n
  Write-Host "costume $n"
  if ($Anim -contains $st) {
    Blend $o @("anim", $Subject, $st, "costume")
    ffmpeg -v error -y -framerate 12 -start_number 1 -i "$o\f_%04d.png" -frames:v 24 -vf $EQ -c:v libwebp_anim -q:v 82 -loop 0 -pix_fmt yuva420p "$dst\$n-dung.webp"
    ffmpeg -v error -y -framerate 12 -start_number 25 -i "$o\f_%04d.png" -frames:v 24 -vf $EQ -c:v libwebp_anim -q:v 82 -loop 0 -pix_fmt yuva420p "$dst\$n-nhay.webp"
    ffmpeg -v error -y -i "$o\f_0001.png" -vf $EQ "$dst\$n.png"
  } else {
    Blend $o @("still", $Subject, $st, "costume"); ffmpeg -v error -y -i "$o\still.png" -vf $EQ "$dst\$n.png"
  }
  Remove-Item -Recurse -Force $o
}
if ($Lineup) {
  Blend $tmp @("clineup", $Subject, "3", "costume"); ffmpeg -v error -y -i "$tmp\lineup.png" -vf $EQ "$dst\$Subject-giai-doan.png"
}
Remove-Item -Recurse -Force $tmp; Write-Host "done" -ForegroundColor Green
