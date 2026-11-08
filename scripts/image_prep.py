"""Turn a downloaded photo into the WebP a store publishes. No network, no files.

One algorithm for every store and every kind of photo (adapted from the
catalog project's product-image-webp/v2 profile); the store (shop_stores)
only supplies the publisher written into the file.

  * any input (JPEG, PNG, GIF, WebP, also a phone's multi-picture JPEG) is
    decoded in full and re-encoded as one static WebP;
  * EXIF orientation applied, colour converted to sRGB by its ICC profile,
    transparency kept;
  * size by FIT[kind], proportions kept, never enlarged, never cropped:
    gallery: the short side down to 1500 (Google Merchant Center recommends
    1500x1500 or more, checked 2026-11-01), so a larger photo keeps both sides
    >= 1500 (3000x4000 -> 1500x2000) and a smaller one stays as it is; the long
    side at most MAX_LONG_SIDE (Shopify's 5000). Review photos and avatars: the
    long side at most 1024;
  * at most MAX_OUTPUT_BYTES: quality 85, 80, 75 at that size, then the same at
    each smaller long side in SIZES; the first that fits wins;
  * an animation (GIF, WebP) becomes its first frame, after its last frame
    decoded (a broken animation is refused, not cut); a phone's MPO becomes its
    first picture (the later ones, depth or HDR gain maps, are not decoded);
  * every old EXIF / GPS / IPTC / ICC / XMP block is dropped; the only metadata
    is a new XMP: dc:publisher + dc:source (the store) and, for a gallery photo
    with English SEO text, dc:title, dc:description (the alt) and dc:subject;
  * the result is read back: RIFF chunks VP8X / VP8 / VP8L / ALPH / XMP only,
    one frame, the expected size and exactly our XMP.

Not done (on purpose, MVP): receipts, policy hashes, encoder pinning, APNG
frames (Pillow reads an APNG's default image as a PNG).

    from image_prep import ImageKind, prepare
    out = prepare(data, ImageKind.GALLERY, store)        # -> Prepared
"""
import hashlib
import io
import re
import struct
from dataclasses import dataclass
from enum import StrEnum
from xml.sax.saxutils import escape

from PIL import Image, ImageCms, ImageOps

from shop_stores import Store


class ImageKind(StrEnum):
    GALLERY = "gallery"
    REVIEW_IMAGE = "review-image"
    REVIEW_AVATAR = "review-avatar"


FIT = {ImageKind.GALLERY: ("short", 1500),           # (which side, its largest size)
       ImageKind.REVIEW_IMAGE: ("long", 1024), ImageKind.REVIEW_AVATAR: ("long", 1024)}
MAX_LONG_SIDE = 5000                     # Shopify's product image limit, any kind
SIZES = (4096, 3584, 3072, 2560, 2048, 1792, 1536, 1280, 1024, 768, 512, 384, 256, 128, 64)  # long sides when
                                                                                       # the bytes do not fit
QUALITIES = (85, 80, 75)
MAX_OUTPUT_BYTES = 1_000_000
MAX_PIXELS = 100_000_000                 # of the source, before decoding
MAX_ASPECT = 100                         # 1:100 .. 100:1
FORMATS = {"JPEG", "MPO", "PNG", "GIF", "WEBP"}
WEBP_CHUNKS = {b"VP8X", b"VP8 ", b"VP8L", b"ALPH", b"XMP "}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG = 200
MAX_ALT = 125
_SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


class PrepError(Exception):
    """The photo cannot be prepared (not decodable, refused, or no size fits)."""


@dataclass(frozen=True)
class ImageSeo:
    """Reviewed English text for a gallery photo (the catalog project refuses Hangul here).
    slug: the file name stem; alt: the HTML alt and dc:description; title: dc:title."""
    slug: str
    title: str | None = None
    alt: str | None = None
    brand: str | None = None             # the product's brand (dc:subject), not the store

    def __post_init__(self):
        if not SLUG_RE.match(self.slug or "") or len(self.slug) > MAX_SLUG:
            raise ValueError(f"slug must be lowercase latin-digit words joined by '-', at most {MAX_SLUG}: "
                             f"{self.slug!r}")
        if self.alt is not None and len(self.alt) > MAX_ALT:
            raise ValueError(f"alt is {len(self.alt)} characters, at most {MAX_ALT}")


@dataclass(frozen=True)
class Prepared:
    data: bytes
    sha256: str
    width: int
    height: int
    quality: int
    source_format: str                   # JPEG / PNG / GIF / WEBP / MPO
    source_width: int
    source_height: int
    first_frame_of: int | None           # frames in the source when it was an animation


def xmp(store: Store, seo: ImageSeo | None = None) -> bytes:
    """The one metadata block a prepared photo carries."""
    def alt(value):
        return f'<rdf:Alt><rdf:li xml:lang="x-default">{escape(value)}</rdf:li></rdf:Alt>'

    fields = [f"<dc:publisher><rdf:Bag><rdf:li>{escape(store.publisher)}</rdf:li></rdf:Bag></dc:publisher>",
              f"<dc:source>{escape(store.site)}</dc:source>"]
    if seo and seo.title:
        fields.append(f"<dc:title>{alt(seo.title)}</dc:title>")
    if seo and seo.alt:
        fields.append(f"<dc:description>{alt(seo.alt)}</dc:description>")
    subjects = [s for s in dict.fromkeys(((seo.brand if seo else None), (seo.title if seo else None))) if s]
    if subjects:
        items = "".join(f"<rdf:li>{escape(s)}</rdf:li>" for s in subjects)
        fields.append(f"<dc:subject><rdf:Bag>{items}</rdf:Bag></dc:subject>")
    return ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            + "".join(fields) + "</rdf:Description></rdf:RDF></x:xmpmeta>").encode()


def _open(data):
    try:
        im = Image.open(io.BytesIO(data))
    except Exception as e:
        raise PrepError(f"not a readable image: {type(e).__name__}") from None
    if im.format not in FORMATS:
        raise PrepError(f"unsupported format {im.format}")
    w, h = im.size
    if w < 1 or h < 1 or w * h > MAX_PIXELS:
        raise PrepError(f"source size {w}x{h} out of range")
    if max(w, h) / min(w, h) > MAX_ASPECT:
        raise PrepError(f"aspect ratio {w}x{h} beyond 1:{MAX_ASPECT}")
    return im


def _first_frame(im):
    """-> (decoded first frame, frame count or None). An animation's last frame must decode too (a broken one is
    refused, not cut). An MPO's later pictures are only size-checked, never decoded: an iPhone HDR photo carries a
    gain map there that Pillow cannot read ("not a JPEG file", seen 2026-11-08 on 4 review photos of the 100-run,
    8822855547, 10050313095, 7674969995), while its first picture, the photo itself, decodes."""
    try:
        frames = getattr(im, "n_frames", 1)              # counting may read the whole file
        if frames > 1:
            try:
                im.seek(frames - 1)
            except Exception:
                if im.format != "MPO":
                    raise
            else:
                w, h = im.size                           # an MPO's later picture can be larger than its first
                if w * h > MAX_PIXELS:
                    raise PrepError(f"frame {frames} size {w}x{h} out of range")
                if im.format != "MPO":
                    im.load()
            im.seek(0)
        im.load()
    except PrepError:
        raise
    except Exception as e:
        raise PrepError(f"decode failed: {type(e).__name__}: {e}") from None
    return im, (frames if frames > 1 and im.format != "MPO" else None)


def _srgb(im):
    """Orientation applied, sRGB, RGB or RGBA, no info carried over."""
    icc = im.info.get("icc_profile")
    alpha = im.mode in ("RGBA", "LA", "PA", "RGBa", "La") or "transparency" in im.info     # also a tRNS colour
    mode = "RGBA" if alpha else "RGB"
    im = ImageOps.exif_transpose(im)
    if im.mode.startswith("I;16") or im.mode == "I":                # 16-bit grey: scaled to 8 bits, not clipped
        im = im.convert("I").point(lambda v: v / 257).convert("L")
    if alpha or im.mode not in ("RGB", "CMYK", "L"):                 # palette, tRNS, LA, 1-bit: RGB(A) first
        im = im.convert(mode)
    if icc:
        try:
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), _SRGB, outputMode=mode)
        except (ImageCms.PyCMSError, OSError):
            pass                         # an unreadable profile, or one that does not fit the pixels: taken as sRGB
    im = im.convert(mode)
    im.info = {}
    return im


def _chunks(data):
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise PrepError("encoder did not write a WebP")
    out, p = [], 12
    while p + 8 <= len(data):
        size = struct.unpack("<I", data[p + 4:p + 8])[0]
        out.append(data[p:p + 4])
        p += 8 + size + (size & 1)
    return out


def verify(data: bytes, width: int, height: int, expected_xmp: bytes) -> None:
    """Raise PrepError unless `data` is a static WebP of that size carrying only `expected_xmp`."""
    chunks = _chunks(data)
    if not set(chunks) <= WEBP_CHUNKS or chunks.count(b"XMP ") != 1:
        raise PrepError(f"unexpected WebP chunks {[c.decode('latin-1') for c in chunks]}")
    if len(data) > MAX_OUTPUT_BYTES:
        raise PrepError(f"output {len(data)} bytes over {MAX_OUTPUT_BYTES}")
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.format != "WEBP" or im.size != (width, height) or getattr(im, "n_frames", 1) != 1:
        raise PrepError(f"output read back as {im.format} {im.size}")
    if im.info.get("exif") or im.info.get("icc_profile") or im.info.get("xmp") != expected_xmp:
        raise PrepError("output metadata is not ours alone")


def _long_sides(w, h, kind):
    """Long sides to try, largest first: the FIT size, then each smaller one in SIZES."""
    side, limit = FIT[kind]
    first = round(max(w, h) * min(1.0, limit / (min(w, h) if side == "short" else max(w, h)),
                                   MAX_LONG_SIDE / max(w, h)))
    return [first] + [s for s in SIZES if s < first]


def prepare(data: bytes, kind: ImageKind, store: Store, seo: ImageSeo | None = None) -> Prepared:
    """Source bytes -> the store's WebP (see the module docstring). Raises PrepError."""
    kind = ImageKind(kind)
    if seo is not None and kind is not ImageKind.GALLERY:
        raise ValueError("SEO text is for gallery photos only")
    src = _open(data)
    fmt, (sw, sh) = src.format, src.size
    frame, frames = _first_frame(src)
    im = _srgb(frame)
    meta = xmp(store, seo)
    w, h = im.size
    for side in _long_sides(w, h, kind):
        scale = side / max(w, h)
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        sized = im if size == im.size else im.resize(size, Image.Resampling.LANCZOS)
        for quality in QUALITIES:
            buf = io.BytesIO()
            sized.save(buf, "WEBP", quality=quality, method=6, alpha_quality=100, exif=b"", icc_profile=b"",
                       xmp=meta)
            out = buf.getvalue()
            if len(out) <= MAX_OUTPUT_BYTES:
                verify(out, size[0], size[1], meta)
                return Prepared(out, hashlib.sha256(out).hexdigest(), size[0], size[1], quality, fmt, sw, sh, frames)
    raise PrepError(f"no size down to {SIZES[-1]} px fits {MAX_OUTPUT_BYTES} bytes")
