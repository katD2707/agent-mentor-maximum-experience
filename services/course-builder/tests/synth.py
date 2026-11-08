"""Synthetic page images for tests (no network, no fixtures on disk)."""

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LINE = "The quick brown fox jumps over the lazy dog. Pythagoras: a^2 + b^2 = c^2, 0123456789."


def clean_page(w: int = 1240, h: int = 1754, size: int = 30) -> Image.Image:
    img = Image.new("RGB", (w, h), (250, 249, 245))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=size)
    y = 90
    while y < h - 90:
        d.text((90, y), LINE, fill=(20, 20, 20), font=font)
        y += int(size * 1.9)
    return img


def blurred(img: Image.Image, radius: float = 4.0) -> Image.Image:
    return img.filter(ImageFilter.GaussianBlur(radius))


def darkened(img: Image.Image, factor: float = 0.25) -> Image.Image:
    return img.point(lambda v: int(v * factor))


def half_black(img: Image.Image) -> Image.Image:
    out = img.copy()
    ImageDraw.Draw(out).rectangle([0, img.height // 2, img.width, img.height], fill=(0, 0, 0))
    return out


def rotated(img: Image.Image, deg: float) -> Image.Image:
    return img.rotate(deg, expand=True, fillcolor=(250, 249, 245), resample=Image.BICUBIC)
