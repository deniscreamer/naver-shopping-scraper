"""Description images -> OCR rows: cut tall images into slices, stitch Naver's snap tiles, read each slice with
RapidOCR (PP-OCRv5 Korean, ONNX, CPU), and join the boxes into rows. Used by description_images.py.

Measured on the 50 fixture products (OCR study, 2026-11-07): RapidOCR read Korean with a line error
rate of 5.1 % and 95.2 % of the numbers, 0.40 s a slice on an M4 (Apple Vision: 77.6 % of the numbers, a quarter of
the short table cells dropped). Its default `Global.max_side_len` 2000 shrinks 14 % of the slices: raised to 10000.
Not used (the owner, 2026-11-07: RapidOCR only, local, any OS): Apple Vision (reads tables column by column on 14 %
of the slices against 0.6 %, macOS only), Live Text (writes Chinese characters on stylized Hangul), the Vision +
RapidOCR hybrid that read best (prose spaces kept: 0.1 % of lines run together against 11.8 %; one engine more),
unions and 2- / 3-engine votes (within noise: the boxes only Vision finds are logo and photo text), a 2x upscale
(1.55x the time for +0.3 points, more short cells lost), VLMs such as Qwen3-VL (rewrite the text, tens of seconds a
slice), cloud OCR (~$24 per 1000 products). MAX_W 1280: spec-table text is ~15-17 px tall at 860 px wide, the low
end for Hangul; a 2560 px master scaled to 1280 keeps it >= 23 px, the page's w848 rendition shrinks it 1.3-3x.

  slices      a description image is 860-1280 px wide and up to ~30 000 px tall. It is cut near TARGET px in the
              widest blank band within +-SEARCH px (no text line is cut); with no band, a hard cut with OVERLAP px
              read twice; a tail under MIN_LAST px joins the slice above. Wider than MAX_W: scaled down first.
  snap tiles  Naver cuts an editor-less body into 945 x 1134 tiles (/p-<n>-s-<n>-<X>-<n> in the link). They are
              one picture: stitched in a rolling buffer (only the uncut part + one tile in memory), then cut.
  rows        boxes whose vertical centres lie within half the smaller box height are one row; cells left to
              right joined with " / ". Each row keeps the lowest confidence of its cells; the text as read.
  norm        (applied when the rows are read, description_images.image_rows) NFKC (㎏ ㎝, full width), inch marks to ", a multiplication sign between numbers to " x ",
              spaced or misread units (k g, kq), O / l inside a digit run.

    from description_ocr import Engine, slices_of, read_slices
    engine = Engine()                                  # loads the ONNX models once (first run downloads them)
    rows = read_slices(engine, slices_of([image_bytes]))
"""
import io
import re
import unicodedata
from collections.abc import Iterable, Iterator
from typing import Any

from PIL import Image, ImageFilter, ImageOps

Image.MAX_IMAGE_PIXELS = 400_000_000         # a 1280 x 60 000 body is legitimate; MAX_BYTES caps the download

MAX_W = 1280
TARGET = 1800
SEARCH = 400
MIN_BAND = 6
OVERLAP = 160
MIN_LAST = 300
EDGE_PX = 40            # an edge pixel: FIND_EDGES above this (JPEG noise stays under ~25)
EDGE_T = 2.0            # a row with fewer edge pixels than this is blank
ENGINE_PARAMS = {"Global.use_cls": False, "Global.log_level": "warning", "Global.max_side_len": 10000}
ENGINE_NAME = "rapidocr PP-OCRv5 korean mobile"
SNAP_RE = re.compile(r"/p-\d+-s-\d+-[A-Z]-\d+")

_QUOTES = str.maketrans({"”": '"', "“": '"', "″": '"', "＂": '"', "〃": '"', "˝": '"'})
_TIMES = r"[xX×✕✖╳*ㅅ]"


# RapidOCR misreads on spec tables not repaired here (seen 2026-11-07, 50 golf sets): a thin ″ or ° read as "*" (the
# _TIMES rule then writes " x " between two numbers: a false size triple is possible), 3° as 30, 43g as 439, D1 as 01
# at a 0.99 score, a Latin L as ㄴ, a thin I dropped ("DRVER"); sellers' decimal commas (58,5) come out as periods.
# Only the degree-as-0 in angle rows is fixed (description_image_text); description_measures.NUMBER_CONF limits trust.
def norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", (text or "").translate(_QUOTES)).replace("′′", '"').replace("''", '"')
    t = re.sub(rf"(?<=\d)(\s*(?:cm|mm|m|inch|\")?)\s*{_TIMES}\s*(?=\d)", r"\1 x ", t, flags=re.I)
    for bad, good in ((r"k\s+g", "kg"), (r"c\s+m", "cm"), (r"m\s+m", "mm"), (r"kq", "kg"), (r"K\s*G", "kg")):
        t = re.sub(rf"(?<=\d)(\s?){bad}(?![a-z])", rf"\1{good}", t)
    t = re.sub(r"(?<=\d)[Oo](?=\d|[.,]\d|\s?(?:kg|g|cm|mm)\b)", "0", t)
    t = re.sub(r"(?<=\d[.,])[Oo]", "0", t)
    t = re.sub(r"(?<=\d)[lI](?=\d)", "1", t)            # not "|": a table separator ("300|310")
    return t.strip()


def open_rgb(data: bytes) -> Image.Image:
    im: Image.Image = Image.open(io.BytesIO(data))
    if getattr(im, "n_frames", 1) > 1:
        im.seek(0)
    if im.mode in ("RGBA", "LA", "P", "PA"):
        rgba = im.convert("RGBA")
        im = Image.new("RGB", rgba.size, "white")
        im.paste(rgba, mask=rgba.split()[-1])
    elif im.mode.startswith("I"):                      # 16-bit grey: RGB would clip it to white
        im = im.convert("I").point(lambda v: v / 256).convert("L").convert("RGB")
    else:
        im = im.convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.Resampling.LANCZOS)
    return im


def row_energy(im: Image.Image) -> list[float]:
    """About the number of edge pixels in every row."""
    g = ImageOps.grayscale(im).filter(ImageFilter.FIND_EDGES)
    g = g.crop((3, 0, max(4, g.width - 3), g.height))       # FIND_EDGES marks the left / right border
    g = g.point(lambda v: 255 if v > EDGE_PX else 0)
    col = g.resize((1, g.height), Image.Resampling.BOX)
    return [v * g.width / 255 for v in col.tobytes()]


def cut_points(energy: list[float], target: int = TARGET, final: bool = True) -> tuple[list[tuple[int, int]], int]:
    """-> ([(y0, y1)] of the slices, the first row of the part not cut). final=False (a stitched buffer that goes
    on): the last open part is left uncut."""
    h, cuts, y = len(energy), [], 0
    while h - y > target + MIN_LAST:
        lo, hi = y + target - SEARCH, min(h - MIN_LAST, y + target + SEARCH)
        best, start, best_len = None, None, 0
        for r in range(lo, hi):
            if energy[r] < EDGE_T:
                start = r if start is None else start
                if r - start + 1 > best_len:
                    best_len, best = r - start + 1, (start, r)
            else:
                start = None
        if best and best_len >= MIN_BAND:
            c = (best[0] + best[1]) // 2
            cuts.append((y, c))
            y = c
        else:
            c = y + target
            cuts.append((y, c + OVERLAP // 2))
            y = c - OVERLAP // 2
    if final:
        cuts.append((y, h))
        y = h
    return cuts, y


def _cut(im: Image.Image, final: bool = True) -> tuple[list[tuple[int, int, Image.Image]], int]:
    """-> ([(y0, y1, slice)], the first row not cut yet)."""
    cuts, end = cut_points(row_energy(im), final=final)
    return [(a, b, im.crop((0, a, im.width, b))) for a, b in cuts], end


def slices_of(images: Iterable[tuple[str, bytes]]) -> Iterator[dict[str, Any]]:
    """(link, bytes) in description order -> {link, y0, y1, image} slices. Consecutive snap tiles are one picture
    (y0 / y1 are rows of the stitched strip, link = its first tile)."""
    buffer: Image.Image | None = None
    first, offset = "", 0

    def flush(final: bool) -> Iterator[dict[str, Any]]:
        nonlocal buffer, offset
        assert buffer is not None
        cut, end = _cut(buffer, final)
        for a, b, im in cut:
            yield {"link": first, "y0": offset + a, "y1": offset + b, "image": im}
        if final:
            buffer = None
        else:
            rest = buffer.crop((0, end, buffer.width, buffer.height))
            offset, buffer = offset + end, rest

    for link, data in images:
        im = open_rgb(data)
        if SNAP_RE.search(link):
            if buffer is None:
                buffer, first, offset = im, link, 0
            else:
                grown = Image.new("RGB", (max(buffer.width, im.width), buffer.height + im.height), "white")
                grown.paste(buffer, (0, 0))
                grown.paste(im, ((grown.width - im.width) // 2, buffer.height))
                buffer = grown
            if buffer.height >= TARGET + SEARCH + MIN_LAST + TARGET:
                yield from flush(False)
            continue
        if buffer is not None:
            yield from flush(True)
        for a, b, piece in _cut(im)[0]:
            yield {"link": link, "y0": a, "y1": b, "image": piece}
    if buffer is not None:
        yield from flush(True)


def rows(boxes: list[tuple[str, float, float, float, float, float]]) -> list[dict[str, Any]]:
    """OCR boxes (text, conf, x, y, w, h) of one slice -> [{text, conf, y}] rows top to bottom. The text is the
    engine's as read (norm() is applied by the reader, so a better norm needs no new OCR)."""
    out: list[dict[str, Any]] = []
    for text, conf, x, y, w, h in sorted(boxes, key=lambda b: b[3] + b[5] / 2):
        cy = y + h / 2
        for r in out[-3:]:
            if abs(cy - r["cy"]) <= 0.5 * min(h, r["h"]):
                r["cells"].append((x, text, conf))
                break
        else:
            out.append({"cy": cy, "h": h, "y": y, "cells": [(x, text, conf)]})
    return [{"text": " / ".join(c[1] for c in sorted(r["cells"])), "conf": round(min(c[2] for c in r["cells"]), 3),
             "y": round(r["y"])} for r in out]


class Engine:
    """RapidOCR with the Korean PP-OCRv5 models, loaded once. Call with a PIL image -> boxes."""

    def __init__(self) -> None:
        from rapidocr import EngineType, LangDet, ModelType, OCRVersion, RapidOCR   # optional dependency
        self._ocr = RapidOCR(params={
            **ENGINE_PARAMS,
            "Det.engine_type": EngineType.ONNXRUNTIME, "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.MOBILE, "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.engine_type": EngineType.ONNXRUNTIME, "Rec.lang_type": "korean",
            "Rec.model_type": ModelType.MOBILE, "Rec.ocr_version": OCRVersion.PPOCRV5})

    def info(self) -> dict[str, Any]:
        return engine_info()

    def __call__(self, image: Image.Image) -> list[tuple[str, float, float, float, float, float]]:
        import numpy as np
        r: Any = self._ocr(np.asarray(image)[:, :, ::-1])    # RapidOCR takes BGR like OpenCV
        if r.txts is None:
            return []
        out = []
        for box, txt, score in zip(r.boxes, r.txts, r.scores):
            xs, ys = [float(p[0]) for p in box], [float(p[1]) for p in box]
            out.append((txt, float(score), min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
        return out


def engine_info() -> dict[str, Any]:
    """What a sidecar records of the engine: rapidocr (it ships its models) and onnxruntime versions, the params;
    a change makes every sidecar stale (read again)."""
    return {"name": ENGINE_NAME, "version": _version("rapidocr"), "onnxruntime": _version("onnxruntime"),
            "params": ENGINE_PARAMS}


def _version(name: str) -> str:
    import importlib.metadata
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def dhash(image: Image.Image) -> int:
    """A 64-bit difference hash: the same picture (a banner repeated inside one body's tiles) gives the same."""
    g = ImageOps.grayscale(image).resize((9, 8), Image.Resampling.BILINEAR).tobytes()
    return sum(1 << i for i in range(64) if g[(i // 8) * 9 + i % 8] > g[(i // 8) * 9 + i % 8 + 1])


def read_slices(engine: Any, slices: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """-> [{link, y0, y1, rows}] (the slice images are dropped once read). A slice equal to one already read in
    this product (same size and dHash: a banner repeated in the tiles, research: 218 pairs, 0 false) takes its
    rows, not a second OCR."""
    out, seen = [], {}
    for s in slices:
        im = s["image"]
        mark = (im.width, im.height, dhash(im))
        if mark not in seen:
            seen[mark] = rows(engine(im))
        out.append({"link": s["link"], "y0": s["y0"], "y1": s["y1"], "rows": seen[mark]})
    return out
