"""Offline tests for /products/specs (ext_product.py): a fake page read and a
fake details record stand in for Chrome and the box; the shared adapter lock
(listing_jobs.with_adapter) is checked against a running listing job.

    python -m pytest server/test_ext_product.py -q
"""
import json
import os

import pytest

import cache
import ext_product
import listing_jobs
from naver_shopping import api, parsers
from test_listing_jobs import FakeBridge, call, jobs, wait_status  # noqa: F401  (fixture + helpers)

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "naver_shopping", "fixtures")
LINK = "https://smartstore.naver.com/thegolf/products/5543663553"


def details(product):
    return {"id": "5543663553", "name": "신품 혼마 D1 남성용 골프채 풀세트", "link": LINK,
            "category": {"id": "50002788", "name": "풀세트", "path": ["스포츠/레저", "골프", "골프클럽", "풀세트"],
                         "path_ids": ["50000007", "50000029", "50001102", "50002788"]},
            "brand": None, "manufacturer": None, "model_name": None, "notice": None}


@pytest.fixture
def specs(jobs, monkeypatch):          # noqa: F811  (the listing-jobs fixture: fake bridge, temp dirs)
    reads = []

    def fake_read(bridge, product_id, query, out_dir):
        reads.append((product_id, query))
        with open(os.path.join(FX, "pdp_specs_honma.html"), encoding="utf-8") as f:
            return {"url": LINK, "title": "t", "html": f.read(), "search_url": "s"}

    monkeypatch.setattr(api, "product_details", details)
    monkeypatch.setattr(ext_product, "read_page", fake_read)
    monkeypatch.setattr(cache, "_store", {})
    return reads


def test_specs_answer(specs):
    status, body = call("GET", "/products/specs", product=LINK)
    assert status == 200, body
    assert specs == [("5543663553", "신품 혼마 D1 남성용 골프채 풀세트")]        # default query: the name
    assert [r["label"] for r in body["specs"]] == ["상품번호", "제조사", "원산지"] and body["is_complete"]
    assert body["facts"]["brand"] == {"value": "혼마", "source": "specs:제조사"}
    assert body["category"]["id"] == "50002788" and body["read_at"].endswith("Z")
    assert body["options"] is None                                            # the page gave no product answer
    assert body["measures"] == {"is_set": True, "weights": [], "dimensions": [], "references": [], "review": []}
    status, again = call("GET", "/naver-shopping/products/specs", product=LINK)
    assert status == 200 and len(specs) == 2                                  # options unknown: read again
    status, _ = call("GET", "/products/specs", product=LINK, query="남성 골프채 풀세트")
    assert status == 200 and specs[-1][1] == "남성 골프채 풀세트"


def test_folded_answer_is_not_cached(specs, monkeypatch):
    def folded(bridge, product_id, query, out_dir):
        specs.append((product_id, query))
        with open(os.path.join(FX, "pdp_specs_ping_folded.html"), encoding="utf-8") as f:
            return {"url": LINK, "title": "t", "html": f.read(), "search_url": "s"}
    monkeypatch.setattr(ext_product, "read_page", folded)
    for _ in range(2):
        status, body = call("GET", "/products/specs", product=LINK)
        assert status == 200 and not body["is_complete"] and len(body["specs"]) == 9
    assert len(specs) == 2                                                   # read again, not cached


def test_specs_busy_while_a_listing_runs(specs, jobs):  # noqa: F811
    _, job = call("POST", "/listings", query="q", max_batches=1)
    status, body = call("GET", "/products/specs", product=LINK)
    assert status == 409 and "busy" in body["error"] and not specs
    jobs.set()
    wait_status(job["id"], "done")
    assert call("GET", "/products/specs", product=LINK)[0] == 200


def test_listing_busy_while_a_read_runs(specs):
    assert listing_jobs._adapter.acquire(blocking=False)
    try:
        status, body = call("POST", "/listings", query="q")
        assert status == 409 and body["job_id"] is None and "product page" in body["error"]
    finally:
        listing_jobs._adapter.release()


def test_specs_errors(specs, monkeypatch):
    monkeypatch.setattr(listing_jobs, "_bridge", FakeBridge(connected=False))
    status, body = call("GET", "/products/specs", product=LINK)
    assert status == 503 and "extension" in body["error"]
    monkeypatch.setattr(listing_jobs, "_bridge", FakeBridge())

    def not_listed(bridge, product_id, query, out_dir):
        raise ext_product.NotListed("not on the page")
    monkeypatch.setattr(ext_product, "read_page", not_listed)
    assert call("GET", "/products/specs", product=LINK, query="zz")[0] == 404

    def walled(bridge, product_id, query, out_dir):
        raise ext_product.PageBlocked("ban page")
    monkeypatch.setattr(ext_product, "read_page", walled)
    assert call("GET", "/products/specs", product=LINK, query="yy")[0] == 503
    assert call("GET", "/products/specs")[0] == 400
    assert parsers.product_facts(details(LINK))["brand"] is None


def test_specs_options_from_the_page_answer(specs, monkeypatch):
    def with_answer(bridge, product_id, query, out_dir):
        specs.append((product_id, query))
        with open(os.path.join(FX, "pdp_specs_honma.html"), encoding="utf-8") as f:
            html = f.read()
        with open(os.path.join(FX, "page_product_idmakers.json"), encoding="utf-8") as f:
            return {"url": LINK, "title": "t", "html": html, "search_url": "s", "product": json.load(f)}
    monkeypatch.setattr(ext_product, "read_page", with_answer)
    status, body = call("GET", "/products/specs", product=LINK)
    assert status == 200 and len(body["options"]["variants"]) == 5
    text = body["options"]["text_options"][0]
    assert text["id"] == "11800253335" and text["required"] is None   # the HTML has no text field: page keys null
    status, _ = call("GET", "/products/specs", product=LINK)
    assert status == 200 and len(specs) == 1                                  # options read: cached


class Answers:
    """A bridge whose `captures` hands out the page's answers in arrival order."""
    def __init__(self, answers):
        self.answers, self.patterns = list(answers), []

    def call(self, op, **args):
        assert op == "captures"
        self.patterns.append(args["pattern"])
        hit, self.answers = self.answers, []
        return hit


def test_product_answer_picks_the_product(monkeypatch):
    monkeypatch.setattr(ext_product.time, "sleep", lambda s: None)
    base = "https://smartstore.naver.com/i/v2/channels/u1/products/42"
    bridge = Answers([
        {"url": base, "status": 419, "body": '{"code":"SDW-E90419"}'},             # before the page's reload
        {"url": base + "/category-navigations?x=1", "status": 200, "body": '{"a": 1}'},
        {"url": base, "status": 200, "body": '{"id": 42, "optionUsable": true}'},
        {"url": base + "/verticals", "status": 200, "body": "[]"},
    ])
    assert ext_product._product_answer(bridge, 7, "42") == {"id": 42, "optionUsable": True}
    assert bridge.patterns == ["/products/42"]
    brand = Answers([{"url": "https://brand.naver.com/n/v2/channels/u/products/42?withWindow=false",
                      "status": 200, "body": '{"id": 42}'}])
    assert ext_product._product_answer(brand, 7, "42") == {"id": 42}
    none = Answers([])
    assert ext_product._product_answer(none, 7, "42") is None and len(none.patterns) == ext_product.ANSWER_TRIES
