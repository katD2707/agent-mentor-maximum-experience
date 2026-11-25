# The Mentor app icon: the stage-1 "daicuong" chick (graduation cap) on a sky and grass rounded square.
#   blender -b -P chicken.py -- <dir> appicon daicuong 1 costume   (writes <dir>/appicon-daicuong.png)
#   python app_icon.py <dir>/appicon-daicuong.png icon-1024.png
#   pnpm -C apps/app tauri icon icon-1024.png -o <tmp>, then copy 32x32/128x128/128x128@2x/icon.png/.ico/.icns into src-tauri/icons
#   and resize for apps/app/public (favicon.png 64, icons/icon-192, icon-512, apple-touch-icon 180).
import sys
from PIL import Image, ImageDraw, ImageFilter
S = 2048
chick = Image.open(sys.argv[1]).convert("RGBA"); chick = chick.crop(chick.split()[3].getbbox())
# sky: vertical gradient
bg = Image.new("RGBA", (S, S))
top, bot = (146, 211, 250), (214, 240, 255)
px = bg.load()
for y in range(S):
    t = y / (S - 1); c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,)
    for x in range(S): px[x, y] = c
d = ImageDraw.Draw(bg)
# soft sun glow behind the chick

# grass hill
d.ellipse((-S*0.35, S*0.74, S*1.35, S*1.74), fill=(132, 200, 96, 255))
d.ellipse((-S*0.30, S*0.77, S*1.30, S*1.74), fill=(159, 214, 122, 255))
# chick
w = int(S * 0.86); h = int(chick.height * w / chick.width); chick = chick.resize((w, h), Image.LANCZOS)
cx, base = S // 2, int(S * 0.90)
sh = Image.new("RGBA", (S, S), (0, 0, 0, 0)); ImageDraw.Draw(sh).ellipse((cx - w*0.28, base - S*0.035, cx + w*0.28, base + S*0.03), fill=(70, 130, 50, 140))
bg.alpha_composite(sh.filter(ImageFilter.GaussianBlur(S * 0.012)))
bg.alpha_composite(chick, (cx - w // 2, base - h + int(S * 0.01)))
# rounded square mask
m = Image.new("L", (S, S), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=255)
out = Image.new("RGBA", (S, S), (0, 0, 0, 0)); out.paste(bg, (0, 0), m)
out.resize((1024, 1024), Image.LANCZOS).save(sys.argv[2])
