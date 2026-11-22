# Rebuilds every character sprite used by the Làng gà mockups (assets/ga/): chickens (idle + jump WebP, still, happy /
# sad / surprised), the boy and girl (idle + wave), the growth-stage and mood line-ups, and the app icon art.
# A light saturation/contrast pass is applied to every frame so the 3D renders sit on the painted village.
#   powershell -ExecutionPolicy Bypass -File mockups\assets\ga\src\build_sprites.ps1
# The other subjects' chickens get an idle + jump WebP and a still (no mood stills) at three growth stages:
# <id>-1 gà con, <id>-2 gà choai, <id> trưởng thành.
#   -Only li,hoa   rebuilds just those chickens (ids of either list), nothing else
#   -Stages 1,2    only those stages of the other subjects' chickens
# Needs Blender 4.5 (winget BlenderFoundation.Blender.LTS.4.5) and ffmpeg. Takes about two hours for everything.
param([string[]]$Only, [string[]]$Stages = @("1", "2", "3"))
if ($Only) { $Only = ($Only -join ",") -split "," }  # -File passes "a,b" as one string
$Stages = ($Stages -join ",") -split ","
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot; $dst = Split-Path -Parent $PSScriptRoot
$bl = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
$tmp = Join-Path $env:TEMP ("mentor-sprites-" + $PID); New-Item -ItemType Directory -Force $tmp | Out-Null
$EQ = "eq=saturation=1.2:contrast=1.04"
function Blend($script, $out, [string[]]$rest) {
  $log = & $bl -b -P (Join-Path $src $script) -- $out @rest 2>&1
  if ($log -match "Traceback|Error:") { $log | Select-String "Traceback|Error" | Select-Object -First 5; throw "render failed: $script $rest" }
}
function Anim($frames, $start, $outFile) {
  ffmpeg -v error -y -framerate 12 -start_number $start -i $frames -frames:v 24 -vf $EQ -c:v libwebp_anim -q:v 82 -loop 0 -pix_fmt yuva420p $outFile
  if ($LASTEXITCODE) { throw "ffmpeg failed: $outFile" }
}
function Still($inFile, $outFile) { ffmpeg -v error -y -i $inFile -vf $EQ $outFile; if ($LASTEXITCODE) { throw "ffmpeg failed: $outFile" } }

$MAIN = @(@("toan", 3), @("van", 2), @("anh", 2))
$OTHERS = "li", "hoa", "sinh", "su", "dia", "tin", "cn", "cd", "khoahoc", "nghethuat", "kynang", "khmt", "ktmt", "httt", "khdl", "vatli", "hoahoc", "kinhte", "ketoan", "daicuong"
foreach ($job in $MAIN) {
  $sj = $job[0]; if ($Only -and $Only -notcontains $sj) { continue }; $st = [string]$job[1]; $o = Join-Path $tmp $sj
  Write-Host "chicken $sj (stage $st)"
  Blend "chicken.py" $o @("anim", $sj, $st)
  Anim "$o\f_%04d.png" 1 "$dst\$sj-dung.webp"; Anim "$o\f_%04d.png" 25 "$dst\$sj-nhay.webp"; Still "$o\f_0001.png" "$dst\$sj.png"
  foreach ($m in @(@("happy", "vui"), @("sad", "buon"), @("surprised", "ngac"))) {
    Blend "chicken.py" $o @($m[0], $sj, $st); Still "$o\$sj-$($m[1]).png" "$dst\$sj-$($m[1]).png"
  }
}
foreach ($sj in $OTHERS) {
  if ($Only -and $Only -notcontains $sj) { continue }
  foreach ($st in $Stages) {
    # the adult (stage 3) keeps the plain name; gà con / gà choai get -1 / -2
    $n = if ($st -eq "3") { $sj } else { "$sj-$st" }
    Write-Host "chicken $n"; $o = Join-Path $tmp $n
    Blend "chicken.py" $o @("anim", $sj, $st)
    Anim "$o\f_%04d.png" 1 "$dst\$n-dung.webp"; Anim "$o\f_%04d.png" 25 "$dst\$n-nhay.webp"; Still "$o\f_0001.png" "$dst\$n.png"
    Remove-Item -Recurse -Force $o
  }
}
if ($Only) { Remove-Item -Recurse -Force $tmp; Write-Host "done" -ForegroundColor Green; exit }
foreach ($k in "nam", "nu") {
  Write-Host "student $k"; $o = Join-Path $tmp "kid-$k"
  Blend "kid.py" $o @($k)
  Anim "$o\k_%04d.png" 1 "$dst\hs-$k.webp"; Anim "$o\k_%04d.png" 25 "$dst\hs-$k-vay.webp"; Still "$o\k_0001.png" "$dst\hs-$k.png"
}
Write-Host "line-ups and icon"
Blend "chicken.py" $tmp @("lineup"); Still "$tmp\lineup.png" "$dst\toan-giai-doan.png"
Blend "chicken.py" $tmp @("faces"); Still "$tmp\faces.png" "$dst\toan-net-mat.png"
Blend "chicken.py" $tmp @("icon", "toan", "3"); Still "$tmp\icon-toan.png" "$dst\icon-ga.png"
Remove-Item -Recurse -Force $tmp
Write-Host "done" -ForegroundColor Green
