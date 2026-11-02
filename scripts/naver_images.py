"""Download the photos the API linked and save them as a store's WebP files.

One tool for every photo we keep: the product gallery (/products/details
`images`) and review photos + avatars (/products/reviews, /products/reviews/
selected). Each file is fetched with a plain HTTP GET from Naver's image CDN
(*.pstatic.net: no browser, no adapter, no cookies), held in memory, prepared
by image_prep (WebP, size, metadata: the same algorithm for every store) and
only the WebP is written; the source file is not kept. The store
(shop_stores) decides the publisher in the file and the file name prefix.

Which file is the original (measured 2026-11-01 on 25 gallery photos of 6
products, smartstore and brand store):

  rendition                    resolution                         bytes
  (no type, the API's link)    the file's own, always the largest the seller's file
  ?type=m10000_10000_no_rotate the same                           a re-encode (other sha)
  ?type=o1000                  always 1000 px: 17 of 25 upscaled  -
                               (600 -> 1000), 2000x1501 downscaled
  ?type=w860                   at most 860 px                     -

The API's gallery links have no `type` and equal the product page's gallery
(4 smartstore pages); review photo links are originals too. So a link is
downloaded as given. Only for a gallery link that fails (404, a broken or
non-image answer, a file image_prep refuses, 5xx after retries) is the same
photo tried as FALLBACKS in order; each file records its `rendition`.

Fetch rules (adapted from a catalog project's image downloader):
  * HTTPS and IMAGE_HOSTS only; no redirects (a redirect fails the file);
  * TIMEOUT per request, MAX_BYTES per file, also with no Content-Length;
  * image/* content type and a known file signature (JPEG, PNG, GIF, WebP);
  * 403 / 429 stop the whole download (CdnRefused): no other rendition, no
    thumbnail instead; network errors and 5xx retry up to RETRIES times after
    RETRY_WAITS seconds; any other answer fails that file only;
  * one request at a time, at least PACE seconds after the previous one
    (fallback renditions, retries, gallery and review photos alike).

    from naver_images import download_gallery, download_review_media
    from shop_stores import get_store
    store = get_store()
    gallery = download_gallery(product["images"], "scripts/output/images-123", store, product["id"])
    media = download_review_media(picked["results"], "scripts/output/images-123", store)
"""
import hashlib
import http.cookiejar
import os
import struct
import time
from urllib.parse import urlsplit

import requests

from image_prep import ImageKind, PrepError, prepare

IMAGE_HOSTS = ("shop-phinf.pstatic.net", "shopping-phinf.pstatic.net", "phinf.pstatic.net",
               "profile-phinf.pstatic.net")      # the last two: review photos (checkout.phinf) and avatars
RENDITION_HOSTS = ("shop-phinf.pstatic.net", "shopping-phinf.pstatic.net")   # where ?type= selects a rendition
FALLBACKS = ("m10000_10000_no_rotate", "o1000")     # after the original, best first (see the docstring)
TIMEOUT = 30                    # seconds, connect and each read
MAX_BYTES = 20 * 1024 * 1024
RETRIES = 3                     # attempts in all
RETRY_WAITS = (3, 6)            # seconds before the 2nd and 3rd attempt
PACE = 2.0                      # seconds between downloads, at least
CHUNK = 64 * 1024


class CdnRefused(Exception):
    """The CDN answered 403 / 429: stop downloading, do not try other renditions."""


class ImageError(Exception):
    """This file could not be downloaded or is not an image (`retry`: a 5xx or a network error)."""

    def __init__(self, message, retry=False):
        super().__init__(message)
        self.retry = retry


def new_session():
    """A requests session that never stores or sends a cookie."""
    session = requests.Session()
    session.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
    return session


def allowed(url):
    parts = urlsplit(url or "")
    return parts.scheme == "https" and parts.hostname in IMAGE_HOSTS


def image_info(data):
    """-> (extension, width, height) from the file header, or None for an unknown format."""
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker == 0xFF:                       # fill bytes before a marker are allowed
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", width, height
            i += 2 + length
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return "gif", width, height
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 ":
            width, height = struct.unpack("<HH", data[26:30])
            return "webp", width & 0x3FFF, height & 0x3FFF
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return "webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            return "webp", int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    return None


def _get(session, url):
    """One attempt -> (bytes, content type). CdnRefused on 403/429; ImageError(retry=True) on 5xx / network."""
    try:
        with session.get(url, timeout=TIMEOUT, stream=True, allow_redirects=False) as resp:
            if resp.status_code in (403, 429):
                raise CdnRefused(f"HTTP {resp.status_code} on {url}")
            if resp.status_code >= 500:
                raise ImageError(f"HTTP {resp.status_code}", True)
            if resp.status_code != 200:
                raise ImageError(f"HTTP {resp.status_code}")       # a redirect lands here too
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                raise ImageError(f"not an image: {ctype or 'no content type'}")
            declared = resp.headers.get("Content-Length") or "0"
            if not declared.strip().isdigit():
                raise ImageError(f"bad Content-Length {declared[:20]!r}")
            if int(declared) > MAX_BYTES:
                raise ImageError(f"over {MAX_BYTES} bytes")
            data = bytearray()
            for chunk in resp.iter_content(CHUNK):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ImageError(f"over {MAX_BYTES} bytes")
            return bytes(data), ctype
    except requests.RequestException as e:
        raise ImageError(f"{type(e).__name__}: {e}", True)


def renditions(url):
    """[(rendition, url)] to try for one photo: the link itself, then FALLBACKS for a
    rendition host link without a query (another link is only tried as given)."""
    parts = urlsplit(url or "")
    if parts.hostname not in RENDITION_HOSTS or parts.query:
        return [("as_given", url)]
    return [("original", url)] + [(t, f"{url}?type={t}") for t in FALLBACKS]


_last_request: list[float] = []           # monotonic time of the last CDN request, in this process


def _pace(sleep, gap=PACE):
    """At least `gap` seconds since the previous CDN request: every rendition, retry and kind of photo."""
    if _last_request:
        sleep(max(0.0, gap - (time.monotonic() - _last_request[0])))
    _last_request[:] = [time.monotonic()]


def _fetch(session, url, sleep):
    """One URL with retries on 5xx / network -> (bytes, content type, (ext, width, height))."""
    for attempt in range(RETRIES):
        try:
            _pace(sleep, PACE if attempt == 0 else RETRY_WAITS[min(attempt - 1, len(RETRY_WAITS) - 1)])
            data, ctype = _get(session, url)
            break
        except ImageError as e:
            if not e.retry or attempt == RETRIES - 1:
                raise ImageError(str(e))
    info = image_info(data)
    if info is None:
        raise ImageError(f"unknown image format ({ctype})")
    return data, ctype, info


def fetch(url, session=None, sleep=time.sleep, prepare_with=None):
    """The photo at `url`, or its best FALLBACKS rendition when that fails -> (rendition, source url,
    bytes, prepare_with(bytes) or None). A rendition whose bytes `prepare_with` refuses (PrepError) counts
    as failed too. Raises CdnRefused / ImageError."""
    if not allowed(url):
        raise ImageError(f"not an allowed image URL: {url}")
    session = session or new_session()
    errors = []
    for rendition, source in renditions(url):
        try:
            data, _, _ = _fetch(session, source, sleep)
            return rendition, source, data, (prepare_with(data) if prepare_with else None)
        except (ImageError, PrepError) as e:
            errors.append(f"{rendition}: {e}")
    raise ImageError("; ".join(errors))


def save_image(url, out_dir, kind, store, stem, seo=None, session=None, sleep=time.sleep):
    """Download `url`, prepare it as `kind` for `store` (image_prep), write <stem>-<sha16>.webp.
    The source bytes stay in memory only. -> {url, rendition, source, source_sha256, source_bytes,
    source_format, source_width, source_height, first_frame_of, file, sha256, bytes, width, height,
    quality}. Raises CdnRefused / ImageError."""
    rendition, source, data, out = fetch(url, session, sleep, lambda b: prepare(b, kind, store, seo))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{stem}-{out.sha256[:16]}.webp")
    if not os.path.exists(path):
        with open(path + ".part", "wb") as f:
            f.write(out.data)
        os.replace(path + ".part", path)
    return {"url": url, "rendition": rendition, "source": source,
            "source_sha256": hashlib.sha256(data).hexdigest(), "source_bytes": len(data),
            "source_format": out.source_format, "source_width": out.source_width,
            "source_height": out.source_height, "first_frame_of": out.first_frame_of,
            "file": path, "sha256": out.sha256, "bytes": len(out.data), "width": out.width,
            "height": out.height, "quality": out.quality}


def download_gallery(urls, out_dir, store, product_id=None, seo=None, session=None, sleep=time.sleep):
    """A product's gallery in order, PACE apart, as the store's WebP files <stem>-<NNN>-<sha16>.webp;
    stem = seo.slug, else <store>-<product id>; NNN = position + 1. -> {store, total, files, failed,
    stopped, is_complete, originals}: position is the index in `urls` (a repeated or empty link is
    skipped, so `total` counts the distinct links); files [{position, alt, ...save_image}], failed
    [{position, url, error}], stopped: the 403/429 message or None. is_complete when every distinct
    photo was saved (in any rendition); originals counts those taken from the original file."""
    session = session or new_session()
    os.makedirs(out_dir, exist_ok=True)                  # the caller's manifest goes here even if nothing saves
    stem = seo.slug if seo else f"{store.file_prefix}-{product_id or 'product'}"
    files, failed, stopped = [], [], None
    unique = {}
    for position, url in enumerate(urls):
        if url and url not in unique:
            unique[url] = position
    for url, position in unique.items():
        try:
            saved = save_image(url, out_dir, ImageKind.GALLERY, store, f"{stem}-{position + 1:03}", seo,
                               session, sleep)
            files.append({"position": position, "alt": seo.alt if seo else None, **saved})
        except CdnRefused as e:
            stopped = str(e)
            failed.append({"position": position, "url": url, "error": stopped})
            break
        except ImageError as e:
            failed.append({"position": position, "url": url, "error": str(e)})
    return {"store": store.id.value, "total": len(unique), "files": files, "failed": failed, "stopped": stopped,
            "is_complete": len(files) == len(unique),
            "originals": sum(1 for f in files if f["rendition"] in ("original", "as_given"))}


def review_media(reviews):
    """[(review id, kind, url)] of selected / listed reviews: photos in order, then the avatar.
    Videos are left out; a null avatar is Naver's placeholder (the server drops it)."""
    out = []
    for review in reviews:
        for a in review.get("attachments") or []:
            if a.get("type") == "image" and a.get("link"):
                out.append((review.get("id"), ImageKind.REVIEW_IMAGE, a["link"]))
        avatar = (review.get("writer") or {}).get("profile_image")
        if avatar:
            out.append((review.get("id"), ImageKind.REVIEW_AVATAR, avatar))
    return out


def download_review_media(reviews, out_dir, store, session=None, sleep=time.sleep):
    """Review photos and avatars as the store's WebP files (1024 px, publisher only, no SEO):
    <store>-review-image-<sha16>.webp, <store>-review-avatar-<sha16>.webp. A URL shared by several
    reviews is fetched once. A failed one is skipped (the review stays); 403/429 stops the rest.
    -> {store, files [{review_id, kind, ...save_image}], failed [{review_id, kind, url, error}],
    stopped, is_complete}."""
    session = session or new_session()
    os.makedirs(out_dir, exist_ok=True)
    files, failed, stopped = [], [], None
    done: dict[str, dict | str] = {}                     # url -> its record, or its error
    for review_id, kind, url in review_media(reviews):
        if url in done:                                  # the same file: its result again
            prior = done[url]
            if isinstance(prior, dict):
                files.append({**prior, "review_id": review_id, "kind": kind.value})
            else:
                failed.append({"review_id": review_id, "kind": kind.value, "url": url, "error": prior})
            continue
        try:
            saved = save_image(url, out_dir, kind, store, f"{store.file_prefix}-{kind.value}", None, session, sleep)
            done[url] = saved
            files.append({"review_id": review_id, "kind": kind.value, **saved})
        except CdnRefused as e:
            stopped = str(e)
            failed.append({"review_id": review_id, "kind": kind.value, "url": url, "error": stopped})
            break
        except ImageError as e:
            done[url] = str(e)
            failed.append({"review_id": review_id, "kind": kind.value, "url": url, "error": str(e)})
    return {"store": store.id.value, "files": files, "failed": failed, "stopped": stopped,
            "is_complete": not failed}
