"""Offline tests for naver_images.py: a fake session stands in for the CDN, Pillow makes the photos.

    .venv/bin/python -m pytest scripts/test_naver_images.py -q
"""
import hashlib
import io
import os
import struct

import pytest
import requests
from PIL import Image

import naver_images as I
from image_prep import ImageSeo
from shop_stores import get_store

STORE = get_store("fairwardgolf")


@pytest.fixture(autouse=True)
def fresh_pacing():
    I._last_request.clear()              # the pacing is per process: each test starts as a new run

OK = "https://shop-phinf.pstatic.net/20250709_275/a.jpg"


def jpeg(width=871, height=870):
    """A minimal JPEG header: SOI, an APP0 segment, SOF0 with the size."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHH", 11, 8, height, width) + b"\x01\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof0 + b"\x00" * 32


def photo(width=871, height=870, fmt="JPEG"):
    """A real, decodable photo."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


def png(width=600, height=600):
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"


class Resp:
    def __init__(self, status=200, body=b"", ctype="image/jpeg", length=None):
        self.status_code, self.body = status, body
        self.headers = {"Content-Type": ctype}
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, size):
        for i in range(0, len(self.body), size):
            yield self.body[i:i + size]


class Session:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def test_saves_only_the_store_webp(tmp_path):
    body = photo()
    s = Session(Resp(body=body))
    out = I.save_image(OK, str(tmp_path), "gallery", STORE, "fairwardgolf-1-001", session=s, sleep=lambda x: None)
    assert out["source_sha256"] == hashlib.sha256(body).hexdigest() and out["source_format"] == "JPEG"
    assert out["file"].endswith(f"fairwardgolf-1-001-{out['sha256'][:16]}.webp") and out["rendition"] == "original"
    assert (out["width"], out["height"], out["source_width"], out["quality"]) == (871, 870, 871, 85)
    assert os.listdir(tmp_path) == [os.path.basename(out["file"])]          # no source file, no .part left
    data = open(out["file"], "rb").read()
    assert data[8:12] == b"WEBP" and hashlib.sha256(data).hexdigest() == out["sha256"] and out["bytes"] == len(data)
    assert b"Fairward Golf" in data
    assert s.calls[0][1]["allow_redirects"] is False and s.calls[0][1]["timeout"] == I.TIMEOUT


def test_formats():
    padded = jpeg()[:20] + b"\xff" + jpeg()[20:]                      # a 0xFF fill byte before SOF0
    assert I.image_info(padded) == ("jpg", 871, 870)
    assert I.image_info(png(600, 400)) == ("png", 600, 400)
    assert I.image_info(b"GIF89a" + struct.pack("<HH", 10, 20)) == ("gif", 10, 20)
    assert I.image_info(b"<html>") is None


@pytest.mark.parametrize("url", ["http://shop-phinf.pstatic.net/a.jpg", "https://example.com/a.jpg", "", None])
def test_only_https_cdn_hosts(url, tmp_path):
    with pytest.raises(I.ImageError):
        I.fetch(url, Session(), sleep=lambda x: None)


def test_rejects_non_images_redirects_and_oversize(tmp_path, monkeypatch):
    for resp in (Resp(body=b"<html>", ctype="text/html"), Resp(status=302), Resp(body=b"not an image")):
        with pytest.raises(I.ImageError):                                    # the original and both fallbacks
            I.fetch(OK, Session(resp, resp, resp), sleep=lambda x: None)
    bad = Resp(body=jpeg(), length="12, 12")
    with pytest.raises(I.ImageError, match="bad Content-Length"):
        I.fetch(OK, Session(bad, bad, bad), sleep=lambda x: None)
    monkeypatch.setattr(I, "MAX_BYTES", 100)
    for resp in (Resp(body=jpeg(), length=10_000), Resp(body=jpeg() + b"\x00" * 200)):   # declared, then streamed
        with pytest.raises(I.ImageError, match="over 100"):
            I.fetch(OK, Session(resp, resp, resp), sleep=lambda x: None)


def test_retries_5xx_and_network_then_gives_up():
    waits = []
    s = Session(Resp(status=503), requests.ConnectionError("reset"), Resp(body=jpeg()))
    assert I.fetch(OK, s, sleep=waits.append)[2] == jpeg()
    assert waits == [pytest.approx(3, abs=0.5), pytest.approx(6, abs=0.5)]
    with pytest.raises(I.ImageError, match="HTTP 500"):
        I.fetch(OK, Session(*[Resp(status=500)] * 9), sleep=lambda x: None)
    s = Session(Resp(status=404), Resp(status=404), Resp(status=404))
    with pytest.raises(I.ImageError, match="original: HTTP 404; m10000_10000_no_rotate: HTTP 404; o1000: HTTP 404"):
        I.fetch(OK, s, sleep=lambda x: None)
    assert len(s.calls) == 3                                                 # a 404 is not retried, only fallen back


def test_falls_back_to_lower_renditions(tmp_path):
    s = Session(Resp(status=404), Resp(body=b"<html>", ctype="text/html"), Resp(body=photo(1000, 1000)))
    out = I.save_image(OK, str(tmp_path), "gallery", STORE, "x", session=s, sleep=lambda x: None)
    assert out["rendition"] == "o1000" and out["source"] == OK + "?type=o1000" and out["url"] == OK
    assert [c[0] for c in s.calls] == [OK, OK + "?type=m10000_10000_no_rotate", OK + "?type=o1000"]
    assert I.renditions("https://phinf.pstatic.net/checkout.phinf/a.jpg") == [
        ("as_given", "https://phinf.pstatic.net/checkout.phinf/a.jpg")]
    assert I.renditions(OK + "?type=w860") == [("as_given", OK + "?type=w860")]   # a link with a query: as given
    s = Session(Resp(status=403))
    with pytest.raises(I.CdnRefused):                                        # 403 / 429: no fallback, stop
        I.fetch(OK, s, sleep=lambda x: None)
    assert len(s.calls) == 1


def test_every_request_paced_fallbacks_and_kinds_too(tmp_path):
    waits = []
    s = Session(Resp(status=404), Resp(body=photo(900, 900)), Resp(body=photo(80, 80)))
    I.save_image(OK, str(tmp_path), "gallery", STORE, "x", session=s, sleep=waits.append)
    I.download_review_media([review("1", [], AVATAR)], str(tmp_path), STORE, s, sleep=waits.append)
    assert len(waits) == 2 and all(0 < w <= I.PACE for w in waits)        # the fallback, then the avatar


def test_a_file_the_preparation_refuses_falls_back(tmp_path):
    broken = jpeg()                                         # a valid header, no picture data
    s = Session(Resp(body=broken), Resp(body=photo(900, 900)))
    out = I.save_image(OK, str(tmp_path), "gallery", STORE, "x", session=s, sleep=lambda x: None)
    assert out["rendition"] == "m10000_10000_no_rotate" and out["width"] == 900


def test_gallery_stops_on_403_and_keeps_order(tmp_path):
    urls = [OK, "https://shop-phinf.pstatic.net/b.png", OK, "https://shop-phinf.pstatic.net/c.jpg",
            "https://shop-phinf.pstatic.net/d.jpg"]
    s = Session(Resp(body=photo()), Resp(body=photo(600, 400, "PNG"), ctype="image/png"), Resp(status=403))
    out = I.download_gallery(urls, str(tmp_path), STORE, "123", session=s, sleep=lambda x: None)
    assert [f["position"] for f in out["files"]] == [0, 1] and out["store"] == "fairwardgolf"
    names = [os.path.basename(f["file"]) for f in out["files"]]
    assert names[0].startswith("fairwardgolf-123-001-") and names[1].startswith("fairwardgolf-123-002-")
    assert out["files"][1]["source_format"] == "PNG" and out["files"][1]["alt"] is None
    assert out["stopped"] == "HTTP 403 on https://shop-phinf.pstatic.net/c.jpg" and not out["is_complete"]
    assert len(s.calls) == 3                                                 # d.jpg never asked for


def test_gallery_position_is_the_index_in_images(tmp_path):
    b = "https://shop-phinf.pstatic.net/b.jpg"
    out = I.download_gallery([OK, OK, "", b], str(tmp_path), STORE, "9", session=Session(Resp(body=photo()),
                             Resp(body=photo(500, 500))), sleep=lambda x: None)
    assert out["total"] == 2 and out["is_complete"] and [f["position"] for f in out["files"]] == [0, 3]
    assert os.path.basename(out["files"][1]["file"]).startswith("fairwardgolf-9-004-")


def test_gallery_with_seo_names_and_alt(tmp_path):
    seo = ImageSeo("callaway-edge-10-club-set", "Callaway Edge 10-Club Set", "Callaway Edge golf set", "Callaway")
    out = I.download_gallery([OK], str(tmp_path), STORE, "123", seo, Session(Resp(body=photo())),
                             sleep=lambda x: None)
    f = out["files"][0]
    assert os.path.basename(f["file"]).startswith("callaway-edge-10-club-set-001-") and f["alt"] == seo.alt
    assert b"Callaway Edge golf set" in open(f["file"], "rb").read()


def test_gallery_dir_exists_when_nothing_saved(tmp_path):
    out_dir = str(tmp_path / "none")
    out = I.download_gallery([OK], out_dir, STORE, session=Session(Resp(status=429)), sleep=lambda x: None)
    assert out["stopped"] and out["files"] == [] and (tmp_path / "none").is_dir()


def test_gallery_complete_and_paced(tmp_path):
    waits = []
    out = I.download_gallery([OK, "https://shop-phinf.pstatic.net/b.png"], str(tmp_path), STORE,
                             session=Session(Resp(body=photo()), Resp(body=photo(fmt="PNG"), ctype="image/png")),
                             sleep=waits.append)
    assert out["is_complete"] and out["failed"] == [] and len(waits) == 1 and 0 < waits[0] <= I.PACE
    assert out["originals"] == 2


PHOTO = "https://phinf.pstatic.net/checkout.phinf/20250101_1/a.jpg"
AVATAR = "https://profile-phinf.pstatic.net/MjAy/b.jpg"


def review(rid, photos=(), avatar=None, video=False):
    attachments = [{"type": "image", "link": p, "width": None, "height": None} for p in photos]
    if video:
        attachments.append({"type": "video", "link": "https://example.com/v.mp4", "width": None, "height": None})
    return {"id": rid, "attachments": attachments, "writer": {"masked_id": "a***", "profile_image": avatar}}


def test_review_media_photos_then_avatar_videos_left_out():
    media = I.review_media([review("1", [PHOTO], AVATAR, video=True), review("2")])
    assert [(r, k.value, u) for r, k, u in media] == [("1", "review-image", PHOTO), ("1", "review-avatar", AVATAR)]


def test_review_media_saved_1024_once_per_url(tmp_path):
    reviews = [review("1", [PHOTO], AVATAR), review("2", [PHOTO])]           # the same photo in two reviews
    s = Session(Resp(body=photo(2000, 1500)), Resp(body=photo(80, 80)))
    out = I.download_review_media(reviews, str(tmp_path), STORE, s, sleep=lambda x: None)
    assert out["is_complete"] and len(s.calls) == 2 and out["store"] == "fairwardgolf"
    image, avatar, again = out["files"]
    assert (image["kind"], image["width"], image["height"]) == ("review-image", 1024, 768)
    assert image["rendition"] == "as_given"
    assert os.path.basename(image["file"]).startswith("fairwardgolf-review-image-")
    assert (avatar["kind"], avatar["width"]) == ("review-avatar", 80)              # never enlarged
    assert os.path.basename(avatar["file"]).startswith("fairwardgolf-review-avatar-")
    assert again["review_id"] == "2" and again["file"] == image["file"]


def test_review_media_skips_a_failed_photo_and_stops_on_403(tmp_path):
    reviews = [review("1", [PHOTO], AVATAR), review("2", [PHOTO, "https://phinf.pstatic.net/checkout.phinf/c.jpg"])]
    s = Session(Resp(status=404), Resp(body=photo(80, 80)), Resp(status=429))
    out = I.download_review_media(reviews, str(tmp_path), STORE, s, sleep=lambda x: None)
    assert [f["kind"] for f in out["files"]] == ["review-avatar"] and not out["is_complete"]
    assert [(f["review_id"], f["error"][:20]) for f in out["failed"]] == [
        ("1", "as_given: HTTP 404"), ("2", "as_given: HTTP 404"), ("2", "HTTP 429 on https://")]
    assert out["stopped"] and len(s.calls) == 3


def test_new_session_keeps_no_cookies():
    policy = I.new_session().cookies._policy          # applies to cookies from answers and on requests
    assert policy.is_not_allowed("shop-phinf.pstatic.net") and policy.is_not_allowed(".naver.com")
