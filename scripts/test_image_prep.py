"""Offline tests for image_prep.py: Pillow makes every photo.

    .venv/bin/python -m pytest scripts/test_image_prep.py -q
"""
import io
import os

import pytest
from PIL import Image, ImageCms

import image_prep as P
from shop_stores import get_store

STORE = get_store("fairwardgolf")


def encode(im, fmt="JPEG", **kw):
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def back(out):
    im = Image.open(io.BytesIO(out.data))
    im.load()
    return im


# ---- the WebP ------------------------------------------------------------------------------

def test_gallery_jpeg_to_webp_with_store_xmp_only():
    exif = Image.Exif()
    exif[0x010F] = "Camera maker"
    exif[0x8825] = {1: "N", 2: (37.0, 30.0, 0.0)}                              # GPS
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = encode(Image.new("RGB", (1200, 900), (10, 120, 200)), exif=exif.tobytes(), icc_profile=icc)
    out = P.prepare(src, P.ImageKind.GALLERY, STORE)
    im = back(out)
    assert im.format == "WEBP" and im.size == (1200, 900) == (out.width, out.height) and out.quality == 85
    assert out.source_format == "JPEG" and (out.source_width, out.source_height) == (1200, 900)
    assert "exif" not in im.info and "icc_profile" not in im.info and out.first_frame_of is None
    meta = im.info["xmp"].decode()
    assert "<rdf:li>Fairward Golf</rdf:li>" in meta and "<dc:source>https://fairwardgolf.com</dc:source>" in meta
    assert "dc:title" not in meta and "Camera" not in meta
    assert len(out.data) <= P.MAX_OUTPUT_BYTES


def test_other_store_is_the_publisher():
    out = P.prepare(encode(Image.new("RGB", (50, 50))), "review-image", get_store("banafish"))
    assert b"BanaFish" in out.data and b"https://banafish.store" in out.data and b"Fairward" not in out.data


def size(data, kind="gallery"):
    out = P.prepare(data, kind, STORE)
    return out.width, out.height


def test_gallery_short_side_down_to_1500_never_enlarged():
    white = (255, 255, 255)
    assert size(encode(Image.new("RGB", (3000, 4000), white))) == (1500, 2000)          # both sides stay >= 1500
    assert size(encode(Image.new("RGB", (4000, 2000), white))) == (3000, 1500)
    assert size(encode(Image.new("RGB", (2000, 2000), white))) == (1500, 1500)
    assert size(encode(Image.new("RGB", (4000, 1000), white))) == (4000, 1000)          # short side under 1500: kept
    assert size(encode(Image.new("RGB", (900, 600), white))) == (900, 600)
    assert size(encode(Image.new("RGB", (12000, 1600), white), "PNG")) == (5000, 667)   # Shopify's long side cap


def test_reviews_long_side_1024_never_enlarged():
    big = encode(Image.new("RGB", (4000, 1000), (255, 255, 255)))
    assert size(big, "review-image") == (1024, 256) and size(big, "review-avatar") == (1024, 256)
    assert size(encode(Image.new("RGB", (300, 200))), "review-avatar") == (300, 200)


def test_size_ladder_until_it_fits(monkeypatch):
    monkeypatch.setattr(P, "MAX_OUTPUT_BYTES", 40_000)
    noise = Image.frombytes("RGB", (900, 600), os.urandom(900 * 600 * 3))
    out = P.prepare(encode(noise, "PNG"), "gallery", STORE)
    assert len(out.data) <= 40_000 and out.width < 900 and out.quality in P.QUALITIES
    assert out.width / out.height == pytest.approx(1.5, abs=0.02)
    monkeypatch.setattr(P, "MAX_OUTPUT_BYTES", 10)
    with pytest.raises(P.PrepError, match="no size"):
        P.prepare(encode(noise, "PNG"), "gallery", STORE)


def test_exif_orientation_applied():
    exif = Image.Exif()
    exif[0x0112] = 6                                                           # rotate 90 on display
    out = P.prepare(encode(Image.new("RGB", (400, 100)), exif=exif.tobytes()), "gallery", STORE)
    assert (out.width, out.height) == (100, 400)


def test_alpha_kept_cmyk_to_rgb():
    out = P.prepare(encode(Image.new("RGBA", (64, 64), (255, 0, 0, 100)), "PNG"), "gallery", STORE)
    assert back(out).mode == "RGBA" and back(out).getpixel((5, 5))[3] == pytest.approx(100, abs=2)
    out = P.prepare(encode(Image.new("CMYK", (64, 64), (0, 255, 255, 0))), "gallery", STORE)
    assert back(out).mode == "RGB"


def test_animation_becomes_first_frame_broken_one_refused():
    frames = [Image.new("RGB", (50, 40), (i * 50, 0, 0)) for i in range(5)]
    gif = encode(frames[0], "GIF", save_all=True, append_images=frames[1:])
    out = P.prepare(gif, "review-avatar", STORE)
    assert out.first_frame_of == 5 and back(out).getpixel((1, 1)) == (0, 0, 0)
    assert b"ANIM" not in out.data and b"ANMF" not in out.data
    with pytest.raises(P.PrepError, match="decode failed"):
        P.prepare(gif[:-30], "review-avatar", STORE)


def test_refuses_what_is_not_a_photo():
    with pytest.raises(P.PrepError, match="not a readable image"):
        P.prepare(b"<html></html>", "gallery", STORE)
    with pytest.raises(P.PrepError, match="unsupported format"):
        P.prepare(encode(Image.new("RGB", (10, 10)), "BMP"), "gallery", STORE)
    with pytest.raises(P.PrepError, match="aspect ratio"):
        P.prepare(encode(Image.new("RGB", (2020, 20)), "PNG"), "gallery", STORE)


def test_seo_text_in_xmp_for_the_gallery_only():
    seo = P.ImageSeo("pga-tour-gloves-5-pack", "PGA TOUR Gloves <5-Pack>", "PGA TOUR gloves & more", "PGA TOUR")
    out = P.prepare(encode(Image.new("RGB", (50, 50))), "gallery", STORE, seo)
    meta = back(out).info["xmp"].decode()
    assert "PGA TOUR Gloves &lt;5-Pack&gt;" in meta and "PGA TOUR gloves &amp; more" in meta
    assert "<dc:subject><rdf:Bag><rdf:li>PGA TOUR</rdf:li><rdf:li>PGA TOUR Gloves &lt;5-Pack&gt;</rdf:li>" in meta
    with pytest.raises(ValueError, match="gallery photos only"):
        P.prepare(encode(Image.new("RGB", (50, 50))), "review-image", STORE, seo)


@pytest.mark.parametrize("slug", ["Callaway", "골프-세트", "a--b", "-a", "a" * 201, ""])
def test_seo_slug_and_alt_rules(slug):
    with pytest.raises(ValueError):
        P.ImageSeo(slug)
    with pytest.raises(ValueError, match="at most 125"):
        P.ImageSeo("ok-slug", alt="x" * 126)


def test_verify_refuses_foreign_metadata():
    out = P.prepare(encode(Image.new("RGB", (50, 50))), "gallery", STORE)
    with pytest.raises(P.PrepError, match="not ours"):
        P.verify(out.data, 50, 50, P.xmp(get_store("skinsli")))
    with pytest.raises(P.PrepError, match="size|read back"):
        P.verify(out.data, 60, 50, P.xmp(STORE))
    with_exif = encode(Image.new("RGB", (50, 50)), "WEBP", exif=b"Exif\x00\x00MM", xmp=P.xmp(STORE))
    with pytest.raises(P.PrepError, match="chunks"):
        P.verify(with_exif, 50, 50, P.xmp(STORE))


def test_sixteen_bit_grey_scaled_not_clipped():
    out = P.prepare(encode(Image.new("I;16", (40, 40), 30000), "PNG"), "gallery", STORE)
    assert back(out).getpixel((5, 5)) == pytest.approx((116, 116, 116), abs=3)


@pytest.mark.parametrize("mode, colour, key", [("L", 7, 7), ("RGB", (1, 2, 3), (1, 2, 3))])
def test_trns_transparency_kept(mode, colour, key):
    out = P.prepare(encode(Image.new(mode, (40, 40), colour), "PNG", transparency=key), "gallery", STORE)
    assert back(out).mode == "RGBA" and back(out).getpixel((5, 5))[3] == 0


P3 = "/System/Library/ColorSync/Profiles/Display P3.icc"              # macOS, the supported platform


@pytest.mark.skipif(not os.path.exists(P3), reason="no Display P3 profile on this machine")
@pytest.mark.parametrize("mode", ["RGB", "P"])
def test_icc_profile_converted_to_srgb(mode):
    icc = open(P3, "rb").read()
    im = Image.new("RGB", (40, 40), (200, 60, 40))
    im = im.convert("P", palette=Image.Palette.ADAPTIVE) if mode == "P" else im
    out = P.prepare(encode(im, "PNG", icc_profile=icc), "gallery", STORE)
    r, g, b = back(out).getpixel((5, 5))[:3]
    assert r > 210 and g < 50 and b < 30                      # P3 red is beyond sRGB: more saturated, not 200/60/40


def test_mpo_later_picture_size_checked(monkeypatch):
    small, large = Image.new("RGB", (64, 48)), Image.new("RGB", (640, 480))
    mpo = encode(small, "MPO", save_all=True, append_images=[large])
    assert P.prepare(mpo, "gallery", STORE).first_frame_of is None              # a phone's photo, not an animation
    monkeypatch.setattr(P, "MAX_PIXELS", 10_000)
    with pytest.raises(P.PrepError, match="frame 2 size 640x480"):
        P.prepare(mpo, "gallery", STORE)
