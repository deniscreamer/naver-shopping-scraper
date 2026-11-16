"""Offline tests for the visual lenses: sheet.py (drawing, index, summary), shop_view.py (the joined view of a shop's
files) and lens.py (each lens's choice, order and marks, the command line).

    .venv/bin/python -m pytest scripts/test_lens.py -q
"""
import json
import os

import pytest
from PIL import Image

import lens as L
import sheet as S
from shop_view import ShopView, job_keys

SHOP = "fairwardgolf"


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def photo(path, colour="blue"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (60, 40), colour).save(path)
    return path


def prepared(pid, price, brand="야마토", source="specs:브랜드", category="50002783", status="ready", held=(),
             photos=1, channel=100):
    key = f"{SHOP}:naver:{channel}:{pid}"
    return {"key": key, "status": status, "held": list(held),
            "source": {"category_id": category, "link": f"https://smartstore.naver.com/x/products/{pid}"},
            "texts": [{"id": f"title:{pid}", "kind": "title", "ko": f"웨지 세트 {pid}"}],
            "product": {"brand_ko": brand, "brand_source": source,
                        "variants": [{"price_krw": price}, {"price_krw": price + 1000}],
                        "options": [{"name_ko": "로프트", "values_ko": ["52", "56"]}],
                        "images": [{"position": i, "file": f"collected/run/images/{pid}/{SHOP}-{pid}-{i + 1:03d}-x.webp"}
                                   for i in range(photos)]}}


@pytest.fixture
def shop(tmp_path):
    """Six wedge sets (one at ₩20,000 among ~₩300,000), one withdrawn, one never prepared, a job with holds."""
    root = tmp_path / "shops"
    d = root / SHOP
    rows = [prepared(1, 300000), prepared(2, 310000), prepared(3, 290000, brand="노브랜드", source="none"),
            prepared(4, 305000), prepared(5, 20000, source="title_word"), prepared(6, 295000),
            prepared(7, 280000, status="held", held=["single_only"])]
    write_jsonl(str(d / "prepared" / "products.jsonl"), rows)
    for r in rows:
        pid = r["key"].split(":")[3]
        photo(str(d / "collected" / "run" / "images" / pid / f"{SHOP}-{pid}-001-x.webp"))
    photo(str(d / "collected" / "run" / "images" / "8" / f"{SHOP}-8-001-y.webp"), "red")   # collected only
    write_jsonl(str(d / "translation" / "translated.jsonl"),
                [{"key": r["key"], "en": {f"title:{r['key'].split(':')[3]}": f"Wedge Set {r['key'].split(':')[3]}",
                                          "brand:x": "Yamato"}} for r in rows])
    write_jsonl(str(d / "placement" / "placements.jsonl"),
                [{"key": r["key"], "status": "placed", "leaves": [{"leaf": "wedge-sets"}]} for r in rows[:6]])
    ledger = [{"key": r["key"], "status": "published", "handle": f"h{i}", "admin_url": f"a{i}"}
              for i, r in enumerate(rows[:6], 1)]
    ledger.append({"key": rows[3]["key"], "status": "withdrawn", "reason": "owner: not a set"})
    write_jsonl(str(d / "publish" / "published.jsonl"), ledger)
    jobs = tmp_path / "jobs"
    k = [r["key"] for r in rows]
    write_jsonl(str(jobs / "j1" / "events.jsonl"), [
        {"key": k[0], "event": "published"},
        {"key": k[6], "event": "prepared", "status": "held", "held": ["single_only"]},
        {"key": f"{SHOP}:naver:200:8", "event": "not_taken", "reason": f"duplicate_of:{k[1]}"},
        {"key": k[5], "event": "not_taken", "reason": "not ready to publish (placement held: single_only)"},
        {"key": k[5], "event": "published"},                       # published later: not held
    ])
    return str(root), str(jobs), k


# ---- sheet.py ------------------------------------------------------------------------------------------------

def test_grid_and_rows_number_every_card_and_draw_a_missing_photo(tmp_path):
    p = photo(str(tmp_path / "a.jpg"))
    cards = [S.Card(n=i, key=f"k{i}", photos=[p] if i % 2 else [None], lines=["₩1,000", "웨지 세트 제목"],
                    mark="flag" if i == 3 else None, group="g1" if i < 4 else "g2") for i in range(1, 6)]
    grids = S.grid(cards, str(tmp_path / "g"), per_sheet=2, columns=2, thumb=60)
    assert [os.path.basename(x) for x in grids] == ["sheet1.jpg", "sheet2.jpg", "sheet3.jpg"]
    lines = S.rows(cards, str(tmp_path / "r"), per_sheet=3, photos=2, thumb=50)
    assert len(lines) == 2                                       # group g1 (3) fills sheet 1, g2 goes on sheet 2
    tsv, js = S.write_index(cards, str(tmp_path / "r"), ["price"], {"lens": "t"})
    head, first = open(tsv, encoding="utf-8").read().splitlines()[:2]
    assert head == "n\tkey\tgroup\tmark\tprice" and first.startswith("1\tk1\tg1\t")
    data = json.load(open(js, encoding="utf-8"))
    assert data["meta"] == {"lens": "t"} and [c["n"] for c in data["cards"]] == [1, 2, 3, 4, 5]


def test_an_empty_plan_draws_no_sheet(tmp_path):
    assert S.grid([], str(tmp_path)) == [] and S.rows([], str(tmp_path)) == []


# ---- shop_view.py --------------------------------------------------------------------------------------------

def test_the_view_joins_prepared_translated_placement_and_the_ledger(shop):
    root, _, k = shop
    v = ShopView(SHOP, root)
    p = v.get(k[0])
    assert (p.title_en, p.brand_en, p.price_krw, p.variants, p.leaves) == ("Wedge Set 1", "Yamato", 300000, 2, ["wedge-sets"])
    assert p.store == "published" and p.handle == "h1" and p.photos[0].endswith("-1-001-x.webp")
    w = v.get(k[3])
    assert w.store == "withdrawn" and w.reason == "owner: not a set" and w.handle == "h4"   # handle from before
    only = v.get(f"{SHOP}:naver:200:8")
    assert only.prepared is None and only.photos[0].endswith("-8-001-y.webp")              # collected photos
    assert [x.pid for x in v.select("50002783")] == ["1", "2", "3", "5", "6"]
    assert [x.pid for x in v.select(store="withdrawn")] == ["4"]


# ---- the lenses ----------------------------------------------------------------------------------------------

def test_price_puts_the_cheapest_first_and_flags_the_one_far_below(shop):
    root, _, k = shop
    plan = L.price(ShopView(SHOP, root), "50002783")
    assert [c.key for c in plan.cards][0] == k[4]
    assert [c.n for c in plan.cards if c.mark == "flag"] == [1] and plan.cards[0].data["z"] < -2


def test_brand_shows_the_weak_sources_first_and_flags_them(shop):
    root, _, k = shop
    plan = L.brand(ShopView(SHOP, root), "50002783")
    assert [c.key for c in plan.cards][:2] == [k[2], k[4]] and [c.mark for c in plan.cards][:3] == ["flag", "flag", None]
    only = L.brand(ShopView(SHOP, root), "50002783", sources=["title_word"])
    assert [c.key for c in only.cards] == [k[4]]


def test_section_by_leaf_and_by_job(shop):
    root, jobs, k = shop
    v = ShopView(SHOP, root)
    assert len(L.section(v, leaf="wedge-sets").cards) == 5
    assert [c.key for c in L.section(v, job="j1", jobs_root=jobs).cards] == [k[0], k[5]]


def test_held_groups_by_reason_and_puts_a_duplicate_beside_its_match(shop):
    root, jobs, k = shop
    plan = L.held(ShopView(SHOP, root), "j1", jobs)
    by = {c.key: c for c in plan.cards}
    assert set(by) == {k[6], f"{SHOP}:naver:200:8"}                          # k[5] published later
    dup = by[f"{SHOP}:naver:200:8"]
    assert dup.group == "duplicate_of" and dup.data["match"] == k[1] and dup.mark == "info"
    assert dup.photos[0].endswith("-8-001-y.webp") and dup.photos[2].endswith("-2-001-x.webp")
    assert by[k[6]].group == "held: single_only" and by[k[6]].data["reason"] == "held: single_only"
    assert by[k[6]].data["event"] == "prepared"
    assert job_keys("j1", jobs, "published") == [k[0], k[5]]


def test_reason_groups():
    assert L._reason_group("not ready to publish (placement held: single_only)") == "held: single_only"
    assert L._reason_group("not ready to publish (placement unresolved: gender unknown)") == \
        "placement unresolved: gender unknown"
    assert L._reason_group("duplicate_of_withdrawn:fairwardgolf:naver:1:2") == "duplicate_of_withdrawn"
    assert L._match_key("duplicate_of_withdrawn:fairwardgolf:naver:1:2") == "fairwardgolf:naver:1:2"


def test_products_by_id_or_key_and_the_command_line_writes_sheets(shop, tmp_path, capsys):
    root, jobs, k = shop
    plan = L.products(ShopView(SHOP, root), ["2", k[0], "999"])
    assert [c.key for c in plan.cards] == [k[1], k[0]] and plan.layout == "rows"
    out = tmp_path / "out"
    assert L.main(["price", SHOP, "--category", "50002783", "--shops-root", root, "--out", str(out)]) == 0
    assert (out / "sheet1.jpg").exists() and (out / "index.tsv").exists()
    summary = json.load(open(out / "summary.json", encoding="utf-8"))
    assert summary["meta"]["lens"] == "price" and summary["meta"]["flagged"] == [1]
    assert "1 flagged" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        L.main(["held", SHOP, "--shops-root", root])                         # held needs --job


def test_dupes_draws_the_reports_groups(shop, monkeypatch):
    root, _, k = shop
    import dedupe
    e = lambda key, grade: {"key": key, "grade": grade, "reviews": 0, "price": 300000, "variants": 2,  # noqa: E731
                            "name": "웨지 세트", "category": "50002783", "tkey": "t", "channel": key.split(":")[2],
                            "agency": True, "first": None, "shas": set(), "values": set(), "words": set(), "numbers": ""}
    group = [e(k[0], "POWER"), e(k[1], "SEED")]
    monkeypatch.setattr(dedupe, "report", lambda *a, **kw: {"list": [group], "groups": 1, "extra_copies": 1,
                                                             "title_only": 1, "published": 2, "same_title_groups": 1})
    monkeypatch.setattr(dedupe, "title_only", lambda g: [k[1]])
    plan = L.dupes(ShopView(SHOP, root))
    assert [(c.data["role"], c.mark) for c in plan.cards] == [("keep", "ok"), ("copy", "flag")]
    assert plan.cards[0].group.startswith("group 1")
