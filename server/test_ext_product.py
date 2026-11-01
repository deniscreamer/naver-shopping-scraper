"""Offline tests for /products/specs (ext_product.py): a fake page read and a
fake details record stand in for Chrome and the box; the shared adapter lock
(listing_jobs.with_adapter) is checked against a running listing job.

    python -m pytest server/test_ext_product.py -q
"""
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
    status, again = call("GET", "/naver-shopping/products/specs", product=LINK)
    assert status == 200 and len(specs) == 1                                  # cached
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
