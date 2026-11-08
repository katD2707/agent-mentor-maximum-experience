"""Cover art for placeholder courses: one small scene per subject motif, varied by a seed.

Same visual language as the real covers: cream background, purple outlines, coral/yellow/mint accents, one motif.
A scene is a list of shapes in a 1600x1000 space; it renders to SVG text and to a PIL image (no SVG rasteriser needed).
"""

from __future__ import annotations

import math
import random
from io import BytesIO

from PIL import Image, ImageDraw

W, H = 1600, 1000
CREAM = (242, 237, 224)
GRID = (233, 227, 211)
PURPLE = (91, 75, 196)
INK = (58, 47, 122)
CORAL = (232, 128, 106)
YELLOW = (237, 213, 119)
MINT = (165, 217, 192)
LAV = (230, 225, 243)
PAPER = (255, 251, 242)
ACCENTS = [CORAL, YELLOW, MINT]

Pt = tuple[float, float]


def hexc(c) -> str:
    return "#%02x%02x%02x" % c


def rot(pts: list[Pt], deg: float, c: Pt = (800, 500)) -> list[Pt]:
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(c[0] + (x - c[0]) * ca - (y - c[1]) * sa, c[1] + (x - c[0]) * sa + (y - c[1]) * ca) for x, y in pts]


def curve(f, a: float, b: float, n: int = 60) -> list[Pt]:
    return [f(a + (b - a) * i / n) for i in range(n + 1)]


def ell_pts(cx: float, cy: float, rx: float, ry: float, n: int = 72) -> list[Pt]:
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rr_pts(x: float, y: float, w: float, h: float, r: float, n: int = 8) -> list[Pt]:
    out: list[Pt] = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


def _pts(pts) -> str:
    return " ".join(f"{x:.0f},{y:.0f}" for x, y in pts)


def _paint(fill, st, sw) -> str:
    s = f'fill="{hexc(fill)}"' if fill else 'fill="none"'
    if st:
        s += f' stroke="{hexc(st)}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"'
    return s


class Scene:
    def __init__(self) -> None:
        self.items: list[tuple] = []

    # fill / stroke are RGB tuples or None
    def rect(self, x, y, w, h, r=0, fill=None, stroke=None, sw=10):
        self.items.append(("rect", x, y, w, h, r, fill, stroke, sw))

    def ellipse(self, cx, cy, rx, ry=None, fill=None, stroke=None, sw=10):
        self.items.append(("ell", cx, cy, rx, rx if ry is None else ry, fill, stroke, sw))

    def poly(self, pts, fill=None, stroke=None, sw=10):
        self.items.append(("poly", list(pts), fill, stroke, sw))

    def path(self, pts, stroke=PURPLE, sw=10, dash=False):
        self.items.append(("path", list(pts), stroke, sw, dash))

    def dot(self, x, y, r, fill):
        self.ellipse(x, y, r, fill=fill)

    # ------------------------------------------------------------ svg
    def svg(self) -> str:
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="{hexc(CREAM)}"/>']
        for it in self.items:
            k = it[0]
            if k == "rect":
                _, x, y, w, h, r, fill, st, sw = it
                o.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="{r}" {_paint(fill, st, sw)}/>')
            elif k == "ell":
                _, cx, cy, rx, ry, fill, st, sw = it
                o.append(f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{rx:.0f}" ry="{ry:.0f}" {_paint(fill, st, sw)}/>')
            elif k == "poly":
                _, pts, fill, st, sw = it
                o.append(f'<polygon points="{_pts(pts)}" {_paint(fill, st, sw)}/>')
            else:
                _, pts, st, sw, dash = it
                d = ' stroke-dasharray="1 26"' if dash else ""
                o.append(f'<polyline points="{_pts(pts)}" fill="none" stroke="{hexc(st)}" stroke-width="{sw}" '
                         f'stroke-linecap="round" stroke-linejoin="round"{d}/>')
        o.append("</svg>")
        return "".join(o)

    # ------------------------------------------------------------ raster
    def image(self, size=(960, 600), ss=2) -> Image.Image:
        k = size[0] * ss / W
        im = Image.new("RGB", (size[0] * ss, size[1] * ss), CREAM)
        d = ImageDraw.Draw(im)

        def sc(pts):
            return [(x * k, y * k) for x, y in pts]

        def stroke_line(pts, col, sw, close=False, dash=False):
            pts = sc(list(pts) + ([pts[0]] if close else []))
            w = max(1, round(sw * k))
            if dash:  # dotted: a round dot every ~26 units
                pitch, acc = 26 * k, 0.0
                for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
                    seg = math.hypot(x1 - x0, y1 - y0)
                    t = acc
                    while t <= seg:
                        px, py = x0 + (x1 - x0) * t / (seg or 1), y0 + (y1 - y0) * t / (seg or 1)
                        d.ellipse((px - w / 2, py - w / 2, px + w / 2, py + w / 2), fill=col)
                        t += pitch
                    acc = t - seg
                return
            d.line(pts, fill=col, width=w, joint="curve")
            r = w / 2
            for x, y in pts:
                d.ellipse((x - r, y - r, x + r, y + r), fill=col)

        for it in self.items:
            kd = it[0]
            if kd == "rect":
                _, x, y, w, h, r, fill, st, sw = it
                pts = rr_pts(x, y, w, h, r) if r else [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                if fill:
                    d.polygon(sc(pts), fill=fill)
                if st:
                    stroke_line(pts, st, sw, close=True)
            elif kd == "ell":
                _, cx, cy, rx, ry, fill, st, sw = it
                if fill:
                    d.ellipse(((cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k), fill=fill)
                if st:
                    stroke_line(ell_pts(cx, cy, rx, ry, 96), st, sw, close=True)
            elif kd == "poly":
                _, pts, fill, st, sw = it
                if fill:
                    d.polygon(sc(pts), fill=fill)
                if st:
                    stroke_line(pts, st, sw, close=True)
            else:
                _, pts, st, sw, dash = it
                stroke_line(pts, st, sw, dash=dash)
        return im.resize(size, Image.LANCZOS)


# ---------------------------------------------------------------- motifs
# Each takes (s: Scene, r: Random, a, b, c) with a/b/c the accent colours in this cover's order; draws around (800, 500).

def sparkle(s, x, y, r, col):
    s.poly([(x, y - r), (x + r * .28, y - r * .28), (x + r, y), (x + r * .28, y + r * .28), (x, y + r), (x - r * .28, y + r * .28),
            (x - r, y), (x - r * .28, y - r * .28)], fill=col)


def arrow(s, p0, p1, col=PURPLE, sw=12, head=34):
    s.path([p0, p1], col, sw)
    a = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    s.poly([p1, (p1[0] - head * math.cos(a - .45), p1[1] - head * math.sin(a - .45)),
            (p1[0] - head * math.cos(a + .45), p1[1] - head * math.sin(a + .45))], fill=col, stroke=col, sw=4)


def m_counting(s, r, a, b, c):  # abacus
    s.rect(430, 280, 740, 440, 40, fill=PAPER, stroke=PURPLE, sw=14)
    for i in range(4):
        y = 360 + i * 95
        s.path([(470, y), (1130, y)], PURPLE, 10)
        for j in range(r.randint(2, 8)):
            s.ellipse(520 + j * 62, y, 29, 38, fill=(a, b, c, a)[i], stroke=PURPLE, sw=8)
        for j in range(r.randint(1, 3)):
            s.ellipse(1085 - j * 62, y, 29, 38, fill=(b, c, a, b)[i], stroke=PURPLE, sw=8)


def m_shapes(s, r, a, b, c):
    s.rect(470, 470, 270, 270, 24, fill=a, stroke=PURPLE, sw=14)
    s.ellipse(940, 600, 150, fill=b, stroke=PURPLE, sw=14)
    s.poly([(700, 470), (860, 200), (1020, 470)], fill=c, stroke=PURPLE, sw=14)
    s.path([(420, 770), (1180, 770)], PURPLE, 14)
    for x in range(460, 1160, 70):
        s.path([(x, 770), (x, 790 if (x // 70) % 2 else 810)], PURPLE, 8)


def m_graph(s, r, a, b, c):
    s.path([(420, 220), (420, 760), (1180, 760)], PURPLE, 14)
    k = r.choice([0, 1, 2])
    f = [lambda t: (420 + 760 * t, 740 - 520 * (1 - (2 * t - 1) ** 2) - 20),
         lambda t: (420 + 760 * t, 490 - 230 * math.sin(2 * math.pi * t)),
         lambda t: (420 + 760 * t, 740 - 500 * t ** 2.2)][k]
    pts = curve(f, 0.02, 0.98, 70)
    s.poly(pts + [(pts[-1][0], 760), (pts[0][0], 760)], fill=a)
    s.path(pts, PURPLE, 14)
    px, py = pts[int(len(pts) * r.uniform(.35, .65))]
    s.path([(px, py), (px, 760)], PURPLE, 8, dash=True)
    s.ellipse(px, py, 22, fill=PAPER, stroke=PURPLE, sw=10)
    arrow(s, (px + 40, py - 70), (px + 190, py - 120), b, 14)


def m_matrix(s, r, a, b, c):
    s.path([(500, 280), (450, 280), (450, 720), (500, 720)], PURPLE, 14)
    s.path([(900, 280), (950, 280), (950, 720), (900, 720)], PURPLE, 14)
    for i in range(3):
        for j in range(3):
            s.rect(520 + j * 125, 300 + i * 140, 105, 120, 18, fill=r.choice([a, b, c, PAPER, PAPER]), stroke=PURPLE, sw=8)
    s.path([(1030, 700), (1030, 300)], PURPLE, 10)
    s.path([(1030, 700), (1190, 700)], PURPLE, 10)
    arrow(s, (1030, 700), (1160, 400), a, 14)
    arrow(s, (1030, 700), (1130, 620), b, 14)


def m_prob(s, r, a, b, c):
    pts = curve(lambda t: (420 + 760 * t, 740 - 460 * math.exp(-((t - .5) / .17) ** 2 / 2)), 0, 1, 80)
    s.poly(pts + [(1180, 740), (420, 740)], fill=b)
    s.path(pts, PURPLE, 14)
    s.path([(400, 740), (1200, 740)], PURPLE, 14)
    for x, y, an, n in ((560, 380, -12, r.randint(1, 6)), (700, 250, 14, r.randint(1, 6))):
        s.poly(rot(rr_pts(x, y, 130, 130, 26), an, (x + 65, y + 65)), fill=PAPER, stroke=PURPLE, sw=10)
        for dx, dy in [(.28, .28), (.72, .72), (.28, .72), (.72, .28), (.5, .5), (.28, .5)][:n]:
            q = rot([(x + 130 * dx, y + 130 * dy)], an, (x + 65, y + 65))[0]
            s.dot(q[0], q[1], 11, INK)


def m_book(s, r, a, b, c):
    s.poly([(800, 330), (470, 290), (470, 700), (800, 740)], fill=PAPER, stroke=PURPLE, sw=14)
    s.poly([(800, 330), (1130, 290), (1130, 700), (800, 740)], fill=PAPER, stroke=PURPLE, sw=14)
    for i in range(5):
        y = 380 + i * 55
        s.path([(520, y - 6), (750, y + 8)], PURPLE if i else a, 9)
        s.path([(850, y + 8), (1080, y - 6)], PURPLE, 9)
    s.poly([(960, 290), (1030, 297), (1030, 430), (995, 405), (960, 430)], fill=a, stroke=PURPLE, sw=8)
    s.poly(rot([(1000, 760), (1190, 760), (1230, 790), (1190, 820), (1000, 820)], -18, (1100, 790)), fill=b, stroke=PURPLE, sw=10)
    s.ellipse(560, 230, 40, fill=c, stroke=PURPLE, sw=8)


def m_speech(s, r, a, b, c):
    s.poly(rr_pts(430, 280, 540, 270, 70), fill=a, stroke=PURPLE, sw=14)
    s.poly([(560, 540), (520, 680), (680, 545)], fill=a, stroke=PURPLE, sw=14)
    s.poly(rr_pts(700, 480, 480, 240, 70), fill=b, stroke=PURPLE, sw=14)
    s.poly([(1050, 710), (1110, 820), (1150, 705)], fill=b, stroke=PURPLE, sw=14)
    for i in range(3):
        s.dot(620 + i * 90, 415, 22, PAPER)
    s.path([(780, 600), (1100, 600)], PAPER, 16)
    s.path([(780, 650), (980, 650)], PAPER, 16)
    sparkle(s, 1180, 280, 46, c)


def m_plant(s, r, a, b, c):
    s.ellipse(800, 800, 300, 36, fill=c)
    s.poly([(650, 640), (950, 640), (900, 800), (700, 800)], fill=a, stroke=PURPLE, sw=14)
    s.path(curve(lambda t: (800 + 30 * math.sin(t * 5), 640 - 330 * t), 0, 1, 30), PURPLE, 14)
    for sgn, y in ((-1, 540), (1, 470), (-1, 400)):
        s.poly(rot(ell_pts(800 + sgn * 90, y - 20, 95, 42), sgn * -25, (800 + sgn * 90, y - 20)), fill=c, stroke=PURPLE, sw=10)
    s.ellipse(1080, 280, 70, fill=b, stroke=PURPLE, sw=10)
    for i in range(8):
        an = i * math.pi / 4
        s.path([(1080 + 95 * math.cos(an), 280 + 95 * math.sin(an)), (1080 + 130 * math.cos(an), 280 + 130 * math.sin(an))], b, 12)


def m_home(s, r, a, b, c):
    s.ellipse(800, 790, 520, 40, fill=c)
    s.rect(520, 450, 400, 320, 10, fill=PAPER, stroke=PURPLE, sw=14)
    s.poly([(490, 460), (720, 260), (950, 460)], fill=a, stroke=PURPLE, sw=14)
    s.rect(680, 590, 90, 180, 8, fill=b, stroke=PURPLE, sw=10)
    s.rect(560, 500, 90, 80, 8, fill=b, stroke=PURPLE, sw=10)
    s.rect(800, 500, 90, 80, 8, fill=b, stroke=PURPLE, sw=10)
    s.rect(1075, 590, 34, 180, 6, fill=PURPLE)
    s.ellipse(1092, 520, 100, 110, fill=c, stroke=PURPLE, sw=12)
    s.ellipse(1190, 240, 60, fill=b, stroke=PURPLE, sw=10)


def m_globe(s, r, a, b, c):
    s.ellipse(800, 480, 270, fill=LAV, stroke=PURPLE, sw=14)
    for rx in (90, 190):
        s.ellipse(800, 480, rx, 270, stroke=PURPLE, sw=8)
    for y in (330, 480, 630):
        half = math.sqrt(max(270 ** 2 - (y - 480) ** 2, 0))
        s.path([(800 - half, y), (800 + half, y)], PURPLE, 8)
    s.poly(ell_pts(720, 400, 70, 45), fill=c, stroke=PURPLE, sw=8)
    s.poly(ell_pts(890, 560, 80, 50), fill=b, stroke=PURPLE, sw=8)
    s.path([(560, 790), (800, 760), (1040, 790)], PURPLE, 14)
    s.poly([(1030, 420), (990, 340), (1070, 340)], fill=a, stroke=PURPLE, sw=8)
    s.ellipse(1030, 320, 52, fill=a, stroke=PURPLE, sw=10)
    s.dot(1030, 320, 18, PAPER)


def m_map(s, r, a, b, c):
    s.poly([(450, 300), (700, 260), (900, 320), (1150, 270), (1150, 720), (900, 770), (700, 710), (450, 760)], fill=PAPER, stroke=PURPLE, sw=14)
    s.poly([(450, 300), (700, 260), (700, 710), (450, 760)], fill=c)
    s.poly([(900, 320), (1150, 270), (1150, 720), (900, 770)], fill=b)
    s.path([(700, 260), (700, 710)], PURPLE, 8)
    s.path([(900, 320), (900, 770)], PURPLE, 8)
    s.path([(520, 640), (640, 520), (780, 580), (860, 440), (1000, 470)], a if a != YELLOW else INK, 12, dash=True)
    s.poly([(1040, 420), (1000, 340), (1080, 340)], fill=a, stroke=PURPLE, sw=8)
    s.ellipse(1040, 320, 48, fill=a, stroke=PURPLE, sw=10)
    s.dot(1040, 320, 16, PAPER)


def m_temple(s, r, a, b, c):
    s.ellipse(800, 430, 300, fill=b)
    s.poly([(470, 360), (800, 190), (1130, 360)], fill=a, stroke=PURPLE, sw=14)
    s.rect(500, 370, 600, 50, 6, fill=PAPER, stroke=PURPLE, sw=12)
    for i in range(4):
        s.rect(540 + i * 150, 430, 76, 250, 14, fill=PAPER, stroke=PURPLE, sw=12)
    s.rect(470, 690, 660, 50, 6, fill=PAPER, stroke=PURPLE, sw=12)
    s.rect(430, 750, 740, 50, 6, fill=c, stroke=PURPLE, sw=12)


def m_atom(s, r, a, b, c):
    base = ell_pts(800, 500, 330, 120)
    for ang, col in ((0, a), (60, b), (120, c)):
        s.poly(rot(base, ang), stroke=PURPLE, sw=10)
        t = r.uniform(0, 6.28)
        px, py = rot([(800 + 330 * math.cos(t), 500 + 120 * math.sin(t))], ang)[0]
        s.ellipse(px, py, 26, fill=col, stroke=PURPLE, sw=8)
    s.ellipse(800, 500, 70, fill=a, stroke=PURPLE, sw=12)
    s.dot(780, 480, 14, PAPER)


def m_flask(s, r, a, b, c):
    s.poly([(630, 560), (970, 560), (1075, 740), (525, 740)], fill=a)
    s.poly([(700, 220), (900, 220), (900, 400), (1080, 740), (520, 740), (700, 400)], stroke=PURPLE, sw=14)
    s.path([(630, 560), (970, 560)], PURPLE, 8)
    s.rect(680, 190, 240, 50, 20, fill=b, stroke=PURPLE, sw=12)
    for x, y, rr_ in ((760, 480, 20), (830, 420, 28), (800, 640, 24), (700, 650, 18)):
        s.ellipse(x, y, rr_, fill=PAPER if y > 560 else c, stroke=PURPLE, sw=8)
    s.rect(1140, 380, 90, 360, 40, fill=PAPER, stroke=PURPLE, sw=12)
    s.rect(1148, 560, 74, 172, 34, fill=c)


def m_dna(s, r, a, b, c):
    def f1(t):
        return (420 + 760 * t, 500 + 190 * math.sin(t * 4 * math.pi))

    def f2(t):
        return (420 + 760 * t, 500 - 190 * math.sin(t * 4 * math.pi))

    for i in range(21):
        x, y1 = f1(i / 20)
        s.path([(x, y1), (x, f2(i / 20)[1])], (a, b, c)[i % 3], 12)
    s.path(curve(f1, 0, 1, 90), PURPLE, 16)
    s.path(curve(f2, 0, 1, 90), PURPLE, 16)


def m_cell(s, r, a, b, c):
    s.poly(rot(ell_pts(800, 500, 370, 290), r.randint(-15, 15)), fill=LAV, stroke=PURPLE, sw=14)
    s.ellipse(760, 480, 120, 110, fill=a, stroke=PURPLE, sw=12)
    s.ellipse(740, 460, 38, fill=PAPER, stroke=PURPLE, sw=8)
    for x, y, an, col in ((1000, 400, 20, b), (950, 640, -30, c), (560, 650, 40, b), (580, 350, -25, c)):
        s.poly(rot(ell_pts(x, y, 62, 32), an, (x, y)), fill=col, stroke=PURPLE, sw=8)
    for x, y in ((1040, 540), (880, 340), (640, 560), (900, 600)):
        s.dot(x, y, 12, PURPLE)


def m_code(s, r, a, b, c):
    s.rect(480, 250, 640, 400, 36, fill=INK, stroke=PURPLE, sw=14)
    for i, (w, col) in enumerate(((200, a), (320, b), (260, c), (150, a), (240, b))):
        x0 = 540 + (60 if i in (1, 2) else 0)
        s.path([(x0, 330 + i * 58), (x0 + w, 330 + i * 58)], col, 18)
    s.poly([(400, 650), (1200, 650), (1250, 730), (350, 730)], fill=PAPER, stroke=PURPLE, sw=14)
    s.path([(700, 690), (900, 690)], PURPLE, 10)


def m_terminal(s, r, a, b, c):
    s.rect(450, 250, 700, 500, 36, fill=PAPER, stroke=PURPLE, sw=14)
    s.poly(rr_pts(450, 250, 700, 90, 36)[:18] + [(1150, 340), (450, 340)], fill=PURPLE, stroke=PURPLE, sw=14)
    for i, col in enumerate((a, b, c)):
        s.dot(510 + i * 55, 295, 15, col)
    s.path([(520, 420), (590, 470), (520, 520)], a if a != YELLOW else CORAL, 16)
    s.path([(630, 520), (780, 520)], PURPLE, 16)
    s.path([(520, 610), (900, 610)], PURPLE, 12)
    s.path([(520, 670), (730, 670)], b, 12)


def m_gear(s, r, a, b, c):
    def gear(cx, cy, ro, n, col, ang=0):
        pts = []
        for i in range(n * 2):
            rr_ = ro if i % 2 == 0 else ro * .78
            for d in (-.14, .14):
                an = (i + .5 + d) * math.pi / n + math.radians(ang)
                pts.append((cx + rr_ * math.cos(an), cy + rr_ * math.sin(an)))
        s.poly(pts, fill=col, stroke=PURPLE, sw=12)
        s.ellipse(cx, cy, ro * .35, fill=PAPER, stroke=PURPLE, sw=12)

    gear(700, 520, 250, 10, a)
    gear(1040, 360, 150, 8, b, 12)
    gear(1000, 690, 110, 7, c, 5)


def m_scales(s, r, a, b, c):
    s.rect(775, 260, 50, 480, 12, fill=PAPER, stroke=PURPLE, sw=12)
    s.rect(620, 740, 360, 50, 14, fill=a, stroke=PURPLE, sw=12)
    p0, p1 = rot([(480, 290), (1120, 290)], r.randint(-14, 14), (800, 290))
    s.path([p0, p1], PURPLE, 18)
    for (x, y), col in ((p0, b), (p1, c)):
        s.path([(x, y), (x - 110, y + 210)], PURPLE, 8)
        s.path([(x, y), (x + 110, y + 210)], PURPLE, 8)
        s.poly([(x - 150, y + 210), (x + 150, y + 210), (x + 110, y + 270), (x - 110, y + 270)], fill=col, stroke=PURPLE, sw=12)
    s.ellipse(800, 270, 40, fill=PAPER, stroke=PURPLE, sw=12)


def m_tree(s, r, a, b, c):
    pos = {0: (800, 280), 1: (580, 480), 2: (1020, 480), 3: (470, 690), 4: (690, 690), 5: (910, 690), 6: (1130, 690)}
    for p, ch in ((0, 1), (0, 2), (1, 3), (1, 4), (2, 5), (2, 6)):
        s.path([pos[p], pos[ch]], PURPLE, 12)
    for i, (x, y) in pos.items():
        s.ellipse(x, y, 62, fill=(a, b, c, PAPER)[(i + r.randint(0, 3)) % 4], stroke=PURPLE, sw=12)


def m_market(s, r, a, b, c):
    s.path([(430, 220), (430, 760), (1170, 760)], PURPLE, 14)
    s.path([(500, 290), (1080, 680)], a, 18)
    s.path([(500, 690), (1080, 300)], b if b != a else c, 18)
    s.path([(790, 490), (790, 760)], PURPLE, 8, dash=True)
    s.path([(430, 490), (790, 490)], PURPLE, 8, dash=True)
    s.ellipse(790, 490, 34, fill=PAPER, stroke=PURPLE, sw=12)


def m_neural(s, r, a, b, c):
    layers = [3, 4, 4, 2]
    xs = [470, 670, 930, 1130]
    nodes = [[(x, 500 + (j - (n - 1) / 2) * 140) for j in range(n)] for x, n in zip(xs, layers, strict=True)]
    for l1, l2 in zip(nodes, nodes[1:], strict=False):
        for p in l1:
            for q in l2:
                s.path([p, q], PURPLE, 4)
    for li, layer in enumerate(nodes):
        for p in layer:
            s.ellipse(p[0], p[1], 40, fill=(a, c, PAPER, b)[li], stroke=PURPLE, sw=10)


def m_net(s, r, a, b, c):
    cx, cy = 800, 500
    n = r.randint(5, 7)
    pts = [(cx + 340 * math.cos(2 * math.pi * i / n - 1), cy + 230 * math.sin(2 * math.pi * i / n - 1)) for i in range(n)]
    for p in pts:
        s.path([(cx, cy), p], PURPLE, 10)
    for i, p in enumerate(pts):
        s.rect(p[0] - 62, p[1] - 44, 124, 88, 18, fill=(b, c, PAPER)[i % 3], stroke=PURPLE, sw=10)
        s.path([(p[0] - 30, p[1]), (p[0] + 30, p[1])], PURPLE, 8)
    s.ellipse(cx, cy, 78, fill=a, stroke=PURPLE, sw=12)
    s.ellipse(cx, cy, 30, fill=PAPER, stroke=PURPLE, sw=8)


def m_db(s, r, a, b, c):
    for i, col in enumerate((a, b, c)):
        y = 330 + i * 150
        s.rect(450, y, 420, 130, 0, fill=col)
        s.ellipse(660, y + 130, 210, 44, fill=col, stroke=PURPLE, sw=12)
        s.path([(450, y), (450, y + 130)], PURPLE, 12)
        s.path([(870, y), (870, y + 130)], PURPLE, 12)
        s.ellipse(660, y, 210, 44, fill=col, stroke=PURPLE, sw=12)
        s.dot(530, y + 90, 12, PAPER)
    s.rect(960, 330, 240, 380, 20, fill=PAPER, stroke=PURPLE, sw=12)
    s.rect(960, 330, 240, 76, 20, fill=a, stroke=PURPLE, sw=12)
    for i in range(2, 5):
        s.path([(960, 330 + i * 76), (1200, 330 + i * 76)], PURPLE, 8)
    s.path([(1080, 330), (1080, 710)], PURPLE, 8)


def m_exam(s, r, a, b, c):
    s.poly(rot(rr_pts(500, 220, 540, 600, 40), -4, (770, 520)), fill=PAPER, stroke=PURPLE, sw=14)
    for i in range(4):
        y = 340 + i * 120
        q = rot([(570, y), (700, y), (940, y)], -4, (770, 520))
        s.rect(q[0][0], q[0][1] - 26, 52, 52, 10, fill=(a, b, c, PAPER)[i], stroke=PURPLE, sw=8)
        s.path([q[1], q[2]], PURPLE, 10)
    s.path([(980, 520), (1060, 610), (1210, 380)], a, 34)


def m_circuit(s, r, a, b, c):
    s.path([(480, 330), (1120, 330), (1120, 700), (480, 700), (480, 330)], PURPLE, 14)
    s.rect(420, 440, 120, 150, 14, fill=a, stroke=PURPLE, sw=12)
    s.rect(460, 410, 40, 34, 4, fill=PURPLE)
    s.ellipse(800, 330, 105, fill=b, stroke=PURPLE, sw=12)
    s.path([(760, 340), (790, 300), (810, 340), (840, 300)], PURPLE, 10)
    s.rect(1050, 470, 140, 90, 12, fill=CREAM)
    s.path([(1050, 515), (1090, 485), (1120, 545), (1150, 485), (1190, 515)], PURPLE, 14)
    s.rect(710, 670, 180, 60, 12, fill=c, stroke=PURPLE, sw=10)


def m_bulb(s, r, a, b, c):
    s.ellipse(800, 420, 200, fill=b, stroke=PURPLE, sw=14)
    s.poly([(710, 570), (890, 570), (860, 660), (740, 660)], fill=PAPER, stroke=PURPLE, sw=14)
    s.rect(730, 660, 140, 40, 14, fill=a, stroke=PURPLE, sw=12)
    s.rect(750, 700, 100, 40, 14, fill=c, stroke=PURPLE, sw=12)
    s.path([(740, 360), (780, 430), (800, 380), (820, 430), (860, 360)], PURPLE, 10)
    for i in range(7):
        an = math.radians(-160 + i * 23)
        s.path([(800 + 250 * math.cos(an), 420 + 250 * math.sin(an)), (800 + 320 * math.cos(an), 420 + 320 * math.sin(an))], PURPLE, 10)


def m_calc(s, r, a, b, c):
    s.poly(rot(rr_pts(590, 220, 420, 580, 50), r.randint(-8, 8), (800, 510)), fill=PAPER, stroke=PURPLE, sw=14)
    s.rect(640, 270, 320, 120, 20, fill=c, stroke=PURPLE, sw=10)
    for i in range(3):
        for j in range(4):
            s.rect(645 + i * 108, 430 + j * 88, 92, 70, 16, fill=a if (i == 2 and j == 3) else LAV, stroke=PURPLE, sw=8)


def m_heart(s, r, a, b, c):
    pts = [(800 + 16 * 14 * math.sin(x) ** 3,
            400 - 14 * (13 * math.cos(x) - 5 * math.cos(2 * x) - 2 * math.cos(3 * x) - math.cos(4 * x)))
           for x in (i * 2 * math.pi / 80 for i in range(80))]
    s.poly(pts, fill=a, stroke=PURPLE, sw=14)
    for x, col in ((520, b), (1080, c)):
        s.ellipse(x, 600, 55, fill=PAPER, stroke=PURPLE, sw=12)
        s.poly([(x - 85, 790), (x - 70, 670), (x + 70, 670), (x + 85, 790)], fill=col, stroke=PURPLE, sw=12)
    s.path([(590, 700), (700, 640)], PURPLE, 12)
    s.path([(1010, 700), (900, 640)], PURPLE, 12)


def m_rocket(s, r, a, b, c):
    cen = (800, 500)
    s.poly(rot([(800, 200), (900, 330), (900, 640), (700, 640), (700, 330)], 30, cen), fill=PAPER, stroke=PURPLE, sw=14)
    s.ellipse(*rot([(800, 400)], 30, cen)[0], 52, fill=b, stroke=PURPLE, sw=12)
    s.poly(rot([(700, 560), (620, 700), (700, 640)], 30, cen), fill=a, stroke=PURPLE, sw=12)
    s.poly(rot([(900, 560), (980, 700), (900, 640)], 30, cen), fill=a, stroke=PURPLE, sw=12)
    s.poly(rot([(740, 660), (860, 660), (800, 780)], 30, cen), fill=c, stroke=PURPLE, sw=10)


MOTIFS = {k[2:]: v for k, v in list(globals().items()) if k.startswith("m_")}


# ---------------------------------------------------------------- background and composition
def panel(s, r, style):
    if style == 1:
        for x in range(0, W, 80):
            s.path([(x, 0), (x, H)], GRID, 3)
        for y in range(0, H, 80):
            s.path([(0, y), (W, y)], GRID, 3)
    elif style == 2:
        s.ellipse(800 + r.randint(-60, 60), 500, 440, 420, fill=LAV)
    elif style == 3:
        s.poly(rot(rr_pts(240, 150, 1120, 700, 70), r.uniform(-4, 4)), fill=LAV)


def cover_scene(motif: str, seed: int) -> Scene:
    r = random.Random(seed)
    accents = ACCENTS[:]
    r.shuffle(accents)
    a, b, c = accents
    s = Scene()
    panel(s, r, seed % 4)
    for _ in range(r.randint(6, 9)):
        for _try in range(20):
            x, y = r.randint(60, W - 60), r.randint(60, H - 60)
            if not (330 < x < 1270 and 170 < y < 850):
                break
        s.dot(x, y, r.randint(14, 30), r.choice(accents))
    for _ in range(2):
        sparkle(s, r.randint(120, 1480), r.choice([r.randint(60, 150), r.randint(850, 930)]), r.randint(18, 30), YELLOW)
    MOTIFS[motif](s, r, a, b, c)
    return s


def cover_webp(motif: str, seed: int, size=(960, 600), quality=80) -> bytes:
    buf = BytesIO()
    cover_scene(motif, seed).image(size).save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()
