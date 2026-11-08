from mentor_course_builder.models import Page
from mentor_course_builder.quality import build_messages, check_page, deterministic_check
from PIL import Image, ImageDraw
from synth import blurred, clean_page, darkened, half_black, rotated


def reasons(img):
    return deterministic_check(img).reasons


def test_clean_page_passes():
    assert reasons(clean_page()) == []
    assert reasons(clean_page(size=22)) == []


def test_blur_flagged_mild_not():
    base = clean_page()
    assert "blurry" in reasons(blurred(base, 3))
    assert "blurry" in reasons(blurred(base, 5))
    assert "blurry" not in reasons(blurred(base, 1))


def test_dark_flagged():
    assert "too_dark" in reasons(darkened(clean_page(), 0.25))
    assert "too_dark" not in reasons(darkened(clean_page(), 0.8))


def test_half_black_is_missing_area_not_dark():
    r = reasons(half_black(clean_page()))
    assert "missing_area" in r and "too_dark" not in r


def test_quarter_black_flagged_small_black_box_not():
    img = clean_page()
    ImageDraw.Draw(img).rectangle([0, 0, img.width, img.height // 4], fill=(0, 0, 0))
    assert "missing_area" in reasons(img)
    img = clean_page()
    ImageDraw.Draw(img).rectangle([100, 100, 300, 260], fill=(0, 0, 0))  # a black figure, not a cut-off page
    assert "missing_area" not in reasons(img)


def test_dark_theme_slide_is_not_cut_off():
    slide = Image.new("RGB", (1280, 720), (10, 10, 10))
    ImageDraw.Draw(slide).rectangle([100, 100, 400, 140], fill=(240, 240, 240))
    assert "missing_area" not in reasons(slide)


def test_skew():
    assert "skewed" in reasons(rotated(clean_page(), 25))
    assert "skewed" in reasons(rotated(clean_page(), -30))
    assert "skewed" not in reasons(rotated(clean_page(), 8))


def test_low_resolution():
    assert "low_resolution" in reasons(clean_page(480, 640, 12))


def test_blank_page_is_not_blurry():
    assert reasons(Image.new("RGB", (1240, 1754), (250, 250, 250))) == ["blank_page"]


def test_check_page_combines_and_messages(tmp_path):
    p = tmp_path / "a.jpg"
    blurred(clean_page(), 4).save(p)
    page = Page(source_file="a.jpg", index=3, kind="image", image_path=str(p))
    c = check_page(page, client=None)
    assert not c.ok and "blurry" in c.reasons
    assert c.message_vi.startswith("Ảnh 3 (a.jpg): ảnh bị mờ")
    assert c.message_en.startswith("Image 3 (a.jpg): the image is blurry")


def test_unreadable_file(tmp_path):
    p = tmp_path / "bad.jpg"
    p.write_bytes(b"not an image")
    c = check_page(Page("bad.jpg", 1, "image", image_path=str(p)), None)
    assert c.reasons == ["unreadable_file"] and not c.ok


def test_build_messages_pdf_page_label():
    vi, _ = build_messages(Page("b.pdf", 3, "scanned_pdf"), ["blurry"])
    assert vi == "Trang 3: ảnh bị mờ, không đọc được chữ"
