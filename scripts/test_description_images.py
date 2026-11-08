"""Offline tests for the description images stage (description_images.py): which links are read, the sidecar, the
resumable run, the stop on a CDN refusal. A fake fetcher and a fake engine: no network, no OCR models.

    .venv/bin/python -m pytest scripts/test_description_images.py -q
"""
import io
import json
import os

import pytest
from PIL import Image

import description_images as DI
import description_ocr as O
import keep_run
from naver_images import CdnRefused, ImageError

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "collected")
SE = "https://shop-phinf.pstatic.net/20260101_1/111_JPEG/body.jpg"


class FakeEngine:
    def __init__(self):
        self.calls = 0

    def info(self):
        return O.engine_info()

    def __call__(self, image):
        self.calls += 1
        return [("캐디백 무게 / 3.5kg", 0.98, 0, 0, 100, 20)]


def jpeg(h=800):
    buf = io.BytesIO()
    Image.new("RGB", (860, h), "white").save(buf, "JPEG")
    return buf.getvalue()


def line(images, pid="123", category="50002788"):
    return {"key": f"fairwardgolf:naver:1:{pid}", "details": {"description": {"images": images, "html": ""}},
            "specs": {"category": {"id": category}}}


def test_pick_links():
    links, skipped = DI.pick_links({"images": [
        SE + "?type=w848", "https://shop-phinf.pstatic.net/a/anim.gif?type=w848",
        "https://cafe24.example.com/x.jpg", "https://shop-phinf.pstatic.net/20260101_1/notice_banner.jpg",
        "http://cafe24.example.com/y.jpg", "https://10.0.0.1/z.jpg", "https://localhost/z.jpg"]})
    assert links == [SE, "https://cafe24.example.com/x.jpg"]   # the original: no ?type; a seller's own host too
    assert [s["rule"] for s in skipped] == ["boilerplate_name", "gif"] + ["not_https_public"] * 3


def test_read_product_writes_rows_and_failures():
    def fetcher(link, cache, session, sleep):
        if "bad" in link:
            raise ImageError("HTTP 404")
        return jpeg()
    sc = DI.read_product(line([SE, "https://shop-phinf.pstatic.net/bad.jpg"]), FakeEngine(), None, fetcher=fetcher)
    assert sc["format"] == DI.FORMAT and sc["product_id"] == "123"
    assert [i["status"] for i in sc["images"]] == ["read", "gone"]          # a 404 is for good
    assert sc["images"][0]["slices"][0]["rows"][0]["text"] == "캐디백 무게 / 3.5kg"
    assert DI.image_rows(sc) == [["캐디백 무게 / 3.5kg"]]


def test_cached_fetch_reads_the_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(DI, "fetch", lambda link, session, sleep, any_host: (calls.append(link) or
                                                                            ("original", link, b"x", None)))
    assert DI._cached_fetch(SE, str(tmp_path), None, None) == b"x"
    assert DI._cached_fetch(SE, str(tmp_path), None, None) == b"x" and calls == [SE]


def kept(tmp_path, lines):
    src = tmp_path / "full-50002788"
    src.mkdir()
    (src / "products.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    keep_run.keep(str(src), str(tmp_path / "shops"))
    return str(tmp_path / "shops")


def test_run_is_resumable_and_force_reads_again(tmp_path):
    shops = kept(tmp_path, [line([SE])])
    engine = FakeEngine()
    fetch = lambda link, cache, session, sleep: jpeg()          # noqa: E731
    r = DI.run("fairwardgolf", shops_root=shops, engine=engine, fetcher=fetch, log=lambda m: None)
    assert r["counts"]["read"] == 1 and DI.load_sidecar("fairwardgolf", "123", shops)["images"]
    r = DI.run("fairwardgolf", shops_root=shops, engine=engine, fetcher=fetch, log=lambda m: None)
    assert r["counts"] == {"read": 0, "kept": 1, "off": 0, "no_rules": 0, "errors": 0} and engine.calls == 1
    DI.run("fairwardgolf", shops_root=shops, engine=engine, fetcher=fetch, force=True, log=lambda m: None)
    assert engine.calls == 2


def test_run_skips_categories_without_the_switch(tmp_path):
    shops = kept(tmp_path, [line([SE], category="99999999")])
    r = DI.run("fairwardgolf", shops_root=shops, engine=FakeEngine(), fetcher=lambda *a: jpeg(), log=lambda m: None)
    assert r["counts"]["no_rules"] == 1 and not DI.load_sidecar("fairwardgolf", "123", shops)


def test_cdn_refusal_stops_the_stage(tmp_path):
    shops = kept(tmp_path, [line([SE])])

    def refused(*a):
        raise CdnRefused("HTTP 429")
    with pytest.raises(CdnRefused):
        DI.run("fairwardgolf", shops_root=shops, engine=FakeEngine(), fetcher=refused, log=lambda m: None)
    assert DI.load_sidecar("fairwardgolf", "123", shops) is None


def test_fixture_sidecars_match_their_products():
    """Every sidecar fixture belongs to a collected fixture and was read with today's engine settings."""
    folder = os.path.join(os.path.dirname(FX), "description_images")
    names = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    for name in names:
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            sc = json.load(f)
        with open(os.path.join(FX, name), encoding="utf-8") as f:
            collected = json.load(f)
        links, _ = DI.pick_links(collected["details"]["description"])
        assert sc["links_sha256"] == DI.links_sha(links) and sc["engine"]["params"] == O.ENGINE_PARAMS


def test_repeated_links_read_once_and_failed_images_retried(tmp_path):
    assert DI.pick_links({"images": [SE, SE + "?type=w848"]})[0] == [SE]
    shops = kept(tmp_path, [line([SE])])
    engine, calls = FakeEngine(), []

    def flaky(link, cache, session, sleep):
        calls.append(link)
        if len(calls) == 1:
            raise ImageError("HTTP 503")
        return jpeg()
    DI.run("fairwardgolf", shops_root=shops, engine=engine, fetcher=flaky, log=lambda m: None)
    r = DI.run("fairwardgolf", shops_root=shops, engine=engine, fetcher=flaky, log=lambda m: None)
    assert r["counts"]["read"] == 1 and DI.load_sidecar("fairwardgolf", "123", shops)["images"][0]["status"] == "read"


def test_tiny_images_are_skipped(tmp_path):
    """A seller's host may serve a counter pixel or an icon among the body's images: never read."""
    def fetcher(link, cache, session, sleep):
        return jpeg(30) if "pixel" in link else jpeg()
    sc = DI.read_product(line([SE, "https://seller.example.com/pixel.jpg"]), FakeEngine(), None, fetcher=fetcher)
    assert [i["link"] for i in sc["images"]] == [SE] and sc["skipped"][-1]["rule"] == "tiny"
    assert sc["images"][0]["host"] == "naver"


def test_cache_is_one_folder_per_product(tmp_path):
    shops = kept(tmp_path, [line([SE])])
    seen = []
    DI.run("fairwardgolf", shops_root=shops, engine=FakeEngine(),
           fetcher=lambda link, cache, session, sleep: seen.append(cache) or jpeg(), log=lambda m: None)
    assert seen == [os.path.join(DI.sidecar_dir("fairwardgolf", shops), "cache", "123")]


def test_a_seller_host_refusing_is_that_image_only():
    """Live 2026-11-07: shopping.c.yimg.jp answered 403 to a description image and stopped the whole stage."""
    def fetcher(link, cache, session, sleep):
        if "yimg" in link:
            raise CdnRefused("HTTP 403")
        return jpeg()
    sc = DI.read_product(line([SE, "https://shopping.c.yimg.jp/lib/x.jpg"]), FakeEngine(), None, fetcher=fetcher)
    assert [i["status"] for i in sc["images"]] == ["read", "refused"]



# ---- the production path: a worker process per product (spawned; readers are module-level to be importable) ----

def reader_ok(line, cache):
    return {"format": DI.FORMAT, "product_id": "123", "key": line["key"], "links_sha256": "x",
            "engine": O.engine_info(), "images": [], "skipped": [], "seconds": 0}


def reader_raises(line, cache):
    raise ValueError("an odd image")


def reader_dies(line, cache):
    os._exit(9)                                   # like a worker killed for memory


def reader_hangs(line, cache):
    import time
    time.sleep(60)


def reader_refused(line, cache):
    raise CdnRefused("HTTP 429")


def test_read_isolated_never_hangs_and_reports():
    """Review 2026-11-07: Pool.apply hung forever on a killed worker, one exception stopped the stage."""
    line_ = line([SE])
    assert DI.read_isolated(reader_ok, line_, "c")[0] == "ok"
    assert DI.read_isolated(reader_raises, line_, "c") == ("error", "ValueError: an odd image")
    kind, msg = DI.read_isolated(reader_dies, line_, "c")
    assert kind == "error" and msg.startswith("worker died")
    assert DI.read_isolated(reader_hangs, line_, "c", timeout=3) == ("error", "timeout after 3 s")
    assert DI.read_isolated(reader_refused, line_, "c") == ("refused", "HTTP 429")


def test_run_records_an_error_after_one_retry_and_goes_on(tmp_path):
    shops = kept(tmp_path, [line([SE]), line([SE], pid="456")])
    logs = []
    r = DI.run("fairwardgolf", shops_root=shops, reader=reader_raises, log=logs.append)
    assert r["counts"]["errors"] == 2 and r["counts"]["read"] == 2
    assert sum("attempt" in m for m in logs) == 4
    assert DI.load_sidecar("fairwardgolf", "123", shops)["error"] == "ValueError: an odd image"
    r = DI.run("fairwardgolf", shops_root=shops, reader=reader_ok, log=logs.append)
    assert r["counts"]["kept"] == 2                          # recorded: not read again until --force
    with pytest.raises(CdnRefused):
        DI.run("fairwardgolf", shops_root=shops, reader=reader_refused, force=True, log=logs.append)


def test_two_runs_of_one_shop_are_refused(tmp_path):
    shops = kept(tmp_path, [line([SE])])
    os.makedirs(DI.sidecar_dir("fairwardgolf", shops))
    held = DI._lock(DI.sidecar_dir("fairwardgolf", shops))
    try:
        with pytest.raises(DI.StageBusy):
            DI.run("fairwardgolf", shops_root=shops, engine=FakeEngine(), fetcher=lambda *a: jpeg(), log=print)
    finally:
        held.close()



def test_prune_cache_per_product(tmp_path):
    shops = str(tmp_path / "shops")
    cache = os.path.join(DI.sidecar_dir("fairwardgolf", shops), "cache")
    for pid in ("1", "2"):
        os.makedirs(os.path.join(cache, pid))
        open(os.path.join(cache, pid, "a.bin"), "wb").write(b"x" * 10)
    assert DI.prune_cache("fairwardgolf", ["1"], shops) == (1, 10) and os.listdir(cache) == ["2"]
    assert DI.prune_cache("fairwardgolf", None, shops) == (1, 10) and os.listdir(cache) == []


# ---- fetching less: the research selection rule steps 3-6 ------------------------------------------------------

TILE = "https://shop-phinf.pstatic.net/20260101_1/p-123-s-4-A-{}.jpg"


def tiled_line(sources):
    html = "".join(f'<img src="{u}">' for u in sources)
    return {"key": "fairwardgolf:naver:1:123", "specs": {"category": {"id": "50002788"}},
            "details": {"description": {"images": [TILE.format(i) for i in range(6)], "html": html}}}


def test_tiled_body_read_from_naver_first():
    """The owner, 2026-11-07: Naver first; the seller's sources are not fetched while the tiles read."""
    src = ["https://seller.example.com/a.jpg", "https://seller.example.com/b.jpg"]
    seen = []
    sc = DI.read_product(tiled_line(src), FakeEngine(), None, fetcher=lambda link, *a: seen.append(link) or jpeg())
    assert seen == [TILE.format(i) for i in range(6)] and not any("seller" in i["link"] for i in sc["images"])


def test_a_tile_naver_did_not_serve_falls_back_to_the_sources():
    src = ["https://seller.example.com/a.jpg", "https://seller.example.com/b.jpg"]

    def fetcher(link, *a):
        if link == TILE.format(3):
            raise ImageError("HTTP 404")
        return jpeg()
    sc = DI.read_product(tiled_line(src), FakeEngine(), None, fetcher=fetcher)
    assert [i["link"] for i in sc["images"]] == src
    assert sc["skipped"][-1] == {"link": "6 snap tiles", "rule": "tiles_replaced_by_sources"}


def test_sources_used_only_when_they_all_read():
    def fetcher(link, *a):
        if link == TILE.format(3) or "b.jpg" in link:
            raise ImageError("HTTP 404")
        return jpeg()
    sc = DI.read_product(tiled_line(["https://seller.example.com/a.jpg", "https://seller.example.com/b.jpg"]),
                         FakeEngine(), None, fetcher=fetcher)
    assert all(DI.ocr.SNAP_RE.search(i["link"]) for i in sc["images"])     # the tiles, one of them gone


def test_an_image_the_store_already_read_is_reused(tmp_path):
    shops = kept(tmp_path, [line([SE], pid="111"), line([SE], pid="222")])
    engine, fetched = FakeEngine(), []
    DI.run("fairwardgolf", shops_root=shops, engine=engine, fetcher=lambda link, *a: fetched.append(link) or jpeg(),
           log=lambda m: None)
    assert fetched == [SE] and engine.calls == 1                    # the second product reused it
    assert DI.load_sidecar("fairwardgolf", "222", shops)["images"][0]["reused"] is True


def test_first_small_smart_editor_image_is_the_header():
    html = '<div data-linkdata=\'{"src": "%s?type=w848", "originalWidth": "860", "originalHeight": "120"}\'></div>' % SE
    links, skipped = DI.pick_links({"images": [SE + "?type=w848", "https://shop-phinf.pstatic.net/x/body2.jpg"],
                                    "html": html})
    assert links == ["https://shop-phinf.pstatic.net/x/body2.jpg"] and skipped[0]["rule"] == "first_header"


def test_equal_slices_are_read_once():
    engine = FakeEngine()
    pic = jpeg(900)
    out = DI.ocr.read_slices(engine, DI.ocr.slices_of([("https://a/1.jpg", pic), ("https://a/2.jpg", pic)]))
    assert engine.calls == 1 and out[0]["rows"] == out[1]["rows"]
