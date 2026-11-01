"""Offline tests for harvest_listing: price slicing past the 96-card
ceiling and the whole-page rule, the Naver-store-only filter, saturation and resume. A fake API
stands in for the server, so nothing goes to the network.

    .venv/bin/python -m pytest scripts/test_harvest_listing.py -q
"""
import json
import os

import harvest_listing as L


def store_card(i, price):
    return {"type": "product", "id": f"p{i}", "product_id": str(1000000 + i), "name": f"set {i}",
            "link": f"https://smartstore.naver.com/main/products/{1000000 + i}",
            "store": {"name": "golf", "id": "golfshop", "link": "https://smartstore.naver.com/golfshop"},
            "pricing": {"discounted_price": price}, "category": {"id": "50002788"}, "images": ["img"]}


def catalog_card(i, price):
    return {"type": "catalog", "id": f"c{i}", "catalog_id": str(5000000 + i),
            "link": f"https://search.shopping.naver.com/catalog/{5000000 + i}", "pricing": {"discounted_price": price}}


def external_card(i, price):
    return {"type": "product", "id": f"e{i}", "product_id": str(9000000 + i),
            "link": "https://link.coupang.com/re/X", "store": {"link": "https://link.coupang.com/re/LOGO"},
            "pricing": {"discounted_price": price}}


class FakeApi:
    """search over a fixed card list, filtered by inclusive price, answering
    like the ns-portal widget: whole pages of 24 only (all of them under 24),
    at most 96."""

    def __init__(self, cards):
        self.cards = cards
        self.calls = []

    def _in(self, lo, hi):
        return [c for c in self.cards if lo <= c["pricing"]["discounted_price"] <= hi]

    def get(self, path, query=None, category=None, min_price=None, max_price=None):
        self.calls.append(path)
        hits = self._in(min_price, max_price)
        if path == "/products/count":
            return {"total_count": len(hits)}
        shown = len(hits) if len(hits) < 24 else min(len(hits) // 24 * 24, L.SEARCH_MAX_CARDS)
        return {"total_count": len(hits), "results": hits[:shown]}


def read_listing(out):
    with open(os.path.join(out, "listing.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def mixed_cards():
    cards = [store_card(i, 100_000 + i * 997) for i in range(400)]
    cards += [catalog_card(i, 200_000 + i * 1_013) for i in range(30)]
    cards += [external_card(i, 300_000 + i * 1_009) for i in range(20)]
    return cards


def run(api, out, **kw):
    return L.harvest_listing(api, "남성 골프채 풀세트", str(out), category="50002788", delay=0, **kw)


def test_collects_every_store_product_past_96(tmp_path):
    api = FakeApi(mixed_cards())
    state = run(api, tmp_path)
    rows = read_listing(tmp_path)
    assert len(rows) == 400 == state["kept"] and not state["pending"]
    assert len({r["product_id"] for r in rows}) == 400
    assert all(s["cards"] >= s["count"] for s in state["slices"] if not s["split"])
    assert state["skipped"] == {"catalog": 30, "external": 20, "other": 0}


def test_rows_use_canonical_store_link(tmp_path):
    run(FakeApi([store_card(1, 150_000)]), tmp_path)
    row = read_listing(tmp_path)[0]
    assert row["link"] == "https://smartstore.naver.com/golfshop/products/1000001"
    assert row["slice"] == [0, L.MAX_PRICE] and row["category_id"] == "50002788" and row["card"]["id"] == "p1"


def test_partial_page_is_split_until_complete(tmp_path):
    cards = [store_card(i, 10_000 + i * 400) for i in range(45)]          # 45 -> the widget shows 24
    state = run(FakeApi(cards), tmp_path)
    assert state["kept"] == 45 and state["slices"][0]["cards"] == 24 and state["slices"][0]["split"]


def test_one_price_with_a_partial_page_is_saturated(tmp_path):
    cards = [store_card(i, 500_000) for i in range(30)] + [store_card(1000 + i, 700_000) for i in range(5)]
    state = run(FakeApi(cards), tmp_path)
    assert state["saturated"] == [{"price": 500_000, "count": 30, "cards": 24}]
    assert state["kept"] == 24 + 5


def test_split_range_is_disjoint_and_covering():
    for a, b, total in [(0, 9_999_999_999, 28936), (0, 19073, 45), (5, 6, 500), (100, 100, 30)]:
        parts = L.split_range(a, b, total) if a < b else []
        if a == b:
            continue
        assert parts[0][0] == a and parts[-1][1] == b and 2 <= len(parts) <= L.SPLIT_WAYS
        assert all(p[0] <= p[1] for p in parts) and all(x[1] + 1 == y[0] for x, y in zip(parts, parts[1:]))


def test_budget_pauses_and_resume_finishes_without_duplicates(tmp_path):
    cards = mixed_cards()
    paused = run(FakeApi(cards), tmp_path, max_requests=15)
    assert paused["pending"] and paused["kept"] < 400
    done = run(FakeApi(cards), tmp_path)
    rows = read_listing(tmp_path)
    assert not done["pending"] and len(rows) == 400 == len({r["product_id"] for r in rows})


def test_other_query_in_same_run_dir_is_refused(tmp_path):
    run(FakeApi([store_card(1, 1)]), tmp_path)
    try:
        L.harvest_listing(FakeApi([]), "여성 골프채 풀세트", str(tmp_path), category="50002788", delay=0)
    except SystemExit as e:
        assert "use another --out" in str(e)
    else:
        raise AssertionError("expected SystemExit")


def test_empty_result_makes_one_call(tmp_path):
    api = FakeApi([])
    state = run(api, tmp_path)
    assert api.calls == ["/products/search"] and state["kept"] == 0 and not state["pending"]
