"""The held lens names the live copy of a withdrawn match (2026-11-16, the owner's wedge-set review): it follows
replaced_by through a chain (13619939279 -> 13379851400 -> 12918511112: 4 cards named the withdrawn 13379851400 as
live) and reads a hold's "hold: copy of live <key>" as the live copy (4 cards said "no live copy" for the holds
12557420063 and 13512885159). Real ledger rows and job events: fixtures/lens/live_copy.json. Offline, display only.

    .venv/bin/python -m pytest scripts/test_lens_live_copy.py -q
"""
import json
import os

import pytest

import lens as L
from shop_view import ShopView

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = json.load(open(os.path.join(HERE, "fixtures", "lens", "live_copy.json"), encoding="utf-8"))
SHOP = "fairwardgolf"
JOB_A, JOB_B = "fairwardgolf-50002783-20261115T150124Z", "fairwardgolf-50002783-20261116T083154Z"


def key(pid):
    keys = {r["key"] for r in FIX["ledger"]} | {e["key"] for j in FIX["jobs"].values() for e in j}
    return next(k for k in keys if k.endswith(":" + pid))


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


@pytest.fixture
def shop(tmp_path):
    root, jobs = tmp_path / "shops", tmp_path / "jobs"
    write_jsonl(str(root / SHOP / "publish" / "published.jsonl"), FIX["ledger"])
    for job, events in FIX["jobs"].items():
        write_jsonl(str(jobs / job / "events.jsonl"), events)
    return ShopView(SHOP, str(root)), str(jobs)


def cards(view, jobs, job):
    return {c.key: c for c in L.held(view, job, jobs).cards}


def arrow(card):
    return next(line for line in card.lines if line.startswith("->"))


def test_a_replaced_by_chain_is_followed_to_the_live_product(shop):
    view, jobs = shop
    assert L.live_copy(view, key("13619939279")) == (key("12918511112"),
                                                     [key("13619939279"), key("13379851400"), key("12918511112")])
    by = cards(view, jobs, JOB_A)
    for pid in ("13261457036", "13405937552", "12951835156", "12557420063"):
        c = by[key(pid)]
        assert c.mark == "flag" and c.data["match_store"] == "withdrawn"           # the match itself is gone
        assert c.data["match_live"] == key("12918511112")
        assert arrow(c) == "-> live: 12918511112 via 13379851400"                 # not the withdrawn 13379851400


def test_a_hold_points_at_its_live_copy(shop):
    view, jobs = shop
    assert L.live_copy(view, key("12557420063")) == (key("12918511112"), [key("12557420063"), key("12918511112")])
    by = cards(view, jobs, JOB_B)
    for pid in ("13261457036", "13405937552", "12951835156"):
        assert by[key(pid)].data["match_live"] == key("12918511112")
        assert arrow(by[key(pid)]) == "-> live: 12918511112"
    a11n = by[key("13310170394")]
    assert a11n.data["match_live"] == key("13552318731") and arrow(a11n) == "-> live: 13552318731"


def test_a_one_hop_replaced_by_stays_as_it_was(shop):
    view, _ = shop
    assert L.live_copy(view, key("13405976594")) == (key("13552318731"), [key("13405976594"), key("13552318731")])


# ---- must NOT name a live copy -----------------------------------------------------------------------------------

def test_a_withdrawal_that_names_no_key_has_no_live_copy(shop):
    view, jobs = shop
    assert L.live_copy(view, key("13363811363")) == (None, [key("13363811363")])       # single_only: no successor
    c = cards(view, jobs, JOB_B)[key("13492293951")]
    assert c.mark == "flag" and c.data["match_live"] is None and arrow(c) == "-> no live copy"


def test_a_chain_ending_off_the_store_or_in_a_loop_has_no_live_copy(tmp_path):
    p = f"{SHOP}:naver:1:"
    rows = [{"key": p + "1", "status": "withdrawn", "reason": f"replaced_by:{p}2"},
            {"key": p + "2", "status": "withdrawn", "reason": f"hold: copy of live {p}3, kept as a draft"},
            {"key": p + "4", "status": "withdrawn", "reason": f"replaced_by:{p}5"},
            {"key": p + "5", "status": "withdrawn", "reason": f"replaced_by:{p}4"},
            {"key": p + "6", "status": "withdrawn", "reason": f"owner: not a set, see replaced_by:{p}7"},
            {"key": p + "7", "status": "published"}]
    write_jsonl(str(tmp_path / SHOP / "publish" / "published.jsonl"), rows)
    view = ShopView(SHOP, str(tmp_path))
    assert L.live_copy(view, p + "1") == (None, [p + "1", p + "2", p + "3"])        # 3: never sent
    assert L.live_copy(view, p + "4") == (None, [p + "4", p + "5"])                 # a loop stops
    assert L.live_copy(view, p + "6") == (None, [p + "6"])                          # a key mid-text is no pointer
