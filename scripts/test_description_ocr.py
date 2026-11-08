"""Offline tests for description_ocr.py: text normalisation, the slicer, snap tile stitching, rows. No OCR engine
(a fake one where needed): the RapidOCR models are not needed for these tests.

    .venv/bin/python -m pytest scripts/test_description_ocr.py -q
"""
import io

from PIL import Image, ImageDraw

import description_ocr as O

SNAP = "https://shop-phinf.pstatic.net/20260101_1/p-123-s-4-A-{}.jpg"


def png(w, h, bars=()):
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for y0, y1 in bars:
        d.rectangle((20, y0, w - 20, y1), fill="black")
        for x in range(30, w - 30, 40):                     # edges inside the bar, like text
            d.line((x, y0, x, y1), fill="white")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_norm():
    assert O.norm("91cm×31cm×40cm") == "91cm x 31cm x 40cm"
    assert O.norm("약 4.1 k g") == "약 4.1 kg"
    assert O.norm("2Okg / 1O.5kg") == "20kg / 10.5kg"
    assert O.norm("45.5″ ㎏") == '45.5" kg'


def test_short_image_is_one_slice():
    [s] = list(O.slices_of([("https://shop-phinf.pstatic.net/a.jpg", png(860, 900))]))
    assert (s["y0"], s["y1"]) == (0, 900)


def test_wide_image_scaled_down():
    [s] = list(O.slices_of([("https://shop-phinf.pstatic.net/a.jpg", png(2560, 1000))]))
    assert s["image"].width == O.MAX_W and s["y1"] == 500


def test_tall_image_cut_in_blank_bands_not_through_text():
    bars = [(y, y + 30) for y in range(50, 6000, 60)]           # text lines every 60 px, 30 px blank between
    slices = list(O.slices_of([("https://shop-phinf.pstatic.net/a.jpg", png(860, 6000, bars))]))
    assert len(slices) >= 3 and slices[0]["y0"] == 0 and slices[-1]["y1"] == 6000
    for a, b in zip(slices, slices[1:]):
        assert a["y1"] == b["y0"]                                # band cuts: no overlap, no gap
        assert not any(y0 < a["y1"] < y1 for y0, y1 in bars)     # never inside a text line


def test_no_blank_band_hard_cut_with_overlap():
    bars = [(0, 5000)]
    slices = list(O.slices_of([("https://shop-phinf.pstatic.net/a.jpg", png(860, 5000, bars))]))
    assert slices[0]["y1"] - slices[1]["y0"] == O.OVERLAP


def test_snap_tiles_are_one_strip():
    tiles = [(SNAP.format(i), png(945, 1134, [(500, 530)])) for i in range(6)]
    slices = list(O.slices_of(tiles))
    assert {s["link"] for s in slices} == {SNAP.format(0)}
    assert slices[0]["y0"] == 0 and slices[-1]["y1"] == 6 * 1134
    for a, b in zip(slices, slices[1:]):
        assert b["y0"] <= a["y1"]


def test_snap_strip_ends_before_a_plain_image():
    tiles = [(SNAP.format(i), png(945, 1134)) for i in range(2)] + [("https://shop-phinf.pstatic.net/b.jpg",
                                                                     png(860, 700))]
    slices = list(O.slices_of(tiles))
    assert [s["link"] for s in slices][-1].endswith("b.jpg") and slices[-1]["y1"] == 700


def test_rows_join_boxes_on_one_line():
    boxes = [("총중량(g)", 0.99, 10, 100, 80, 20), ("296g", 0.97, 200, 102, 40, 18), ("헤드체적", 0.9, 10, 160, 80, 20)]
    assert O.rows(boxes) == [{"text": "총중량(g) / 296g", "conf": 0.97, "y": 100}, {"text": "헤드체적", "conf": 0.9, "y": 160}]


def test_read_slices_with_a_fake_engine():
    slices = list(O.slices_of([("https://shop-phinf.pstatic.net/a.jpg", png(860, 900))]))
    out = O.read_slices(lambda im: [("무게 / 3.5kg", 0.98, 0, 0, 100, 20)], slices)
    assert out == [{"link": "https://shop-phinf.pstatic.net/a.jpg", "y0": 0, "y1": 900,
                    "rows": [{"text": "무게 / 3.5kg", "conf": 0.98, "y": 0}]}]


def test_engine_info_names_the_params():
    info = O.engine_info()
    assert info["params"]["Global.max_side_len"] == 10000 and "korean" in info["name"]


def test_alpha_and_16_bit_images():
    """Review 2026-11-07: a wide RGBA PNG was not scaled down; a 16-bit grey PNG came out all white."""
    buf = io.BytesIO()
    Image.new("RGBA", (2560, 400), (0, 0, 0, 255)).save(buf, "PNG")
    assert O.open_rgb(buf.getvalue()).size == (O.MAX_W, 200)
    buf = io.BytesIO()
    Image.new("I;16", (50, 50), 8000).save(buf, "PNG")
    assert O.open_rgb(buf.getvalue()).getpixel((0, 0))[0] < 64


def test_norm_keeps_a_table_pipe():
    assert O.norm("300|310") == "300|310" and O.norm("1l0") == "110"
