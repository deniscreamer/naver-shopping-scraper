"""Offline tests for reprice.py: a tiny shop folder, the fake Shopify clients of test_publish.py. No network.

    .venv/bin/python -m pytest scripts/test_reprice.py -q
"""
import json

import pytest

import publish as PB
import reprice as RP
from test_publish import KEY, FakeFiles, FakeProducts, _product

PREFIX = "fairwardgolf:naver:100:"
HELD, PLAIN, NEW = PREFIX + "557", PREFIX + "556", PREFIX + "558"        # KEY is ...:555
NEW_PRICES = [819, 829]                     # _product(): 5 560 / 6 560 KRW, the default box at level 1 (x2.50)


def _rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _shop(tmp_path):
    """Four ready products, in this order: HELD (a variant without a box), KEY (its ledger row has the prices the
    rule gives now), PLAIN (a ledger row from before prices_usd), NEW (ready, never published)."""
    d = tmp_path / "fairwardgolf"
    files = {"prepared/products.jsonl": [], "translation/translated.jsonl": [], "placement/placements.jsonl": []}
    for key in (HELD, KEY, PLAIN, NEW):
        prepared, translated, placement = _product()
        prepared["key"], translated["key"], placement["key"] = key, key, key
        prepared["source"]["product_id"] = key.rsplit(":", 1)[1]
        if key == HELD:
            del prepared["product"]["variants"][1]["package"]["package_width_mm"]
        for rel, row in zip(files, (prepared, translated, placement)):
            files[rel].append(row)
    for rel, rows in files.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    for f in ("a.webp", "b.webp", "av.webp", "p1.webp"):
        p = d / "collected/r/images/555" / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f.encode())
    ledger = []
    for n, (key, prices) in enumerate(((HELD, [6, 7]), (KEY, NEW_PRICES), (PLAIN, None)), 11):
        row = {"format": "published/1", "key": key, "status": "published", "at": "2026-11-10T00:00:00Z",
               "digest": "before-the-rule", "product_id": f"gid://shopify/Product/{n}", "handle": f"set-{n}",
               "created": True, "photos": [], "photos_failed": [], "reviews": 1, "feed_url": None}
        if prices:
            row["prices_usd"] = prices
        ledger.append(row)
    (d / "publish").mkdir()
    (d / "publish/published.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ledger))
    return PB.Shop("fairwardgolf", str(tmp_path))


def _no_shopify(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a dry run reached Shopify")
    monkeypatch.setattr(PB, "clients", refuse)
    monkeypatch.setattr(PB, "publish_one", refuse)


def test_dry_run_prints_and_writes_the_table_and_sends_nothing(tmp_path, monkeypatch, capsys):
    shop = _shop(tmp_path)
    _no_shopify(monkeypatch)
    ledger = open(shop.ledger_path, encoding="utf-8").read()
    assert RP.main(["fairwardgolf", "--shops-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"{HELD}  set-11  held: no package box to price the delivery  (stays at 6-7)" in out
    assert f"{KEY}  set-12  level 1 x2.50  819-829 -> 819-829  +0" in out
    assert f"{PLAIN}  set-13  level 1 x2.50  6-7 (plain rule) -> 819-829  +813/+822" in out
    assert NEW not in out                                                   # ready, never published
    assert "3 products: 1 changed, 1 same price, 1 held; lowest prices of the 2 priced: 825 USD -> 1638 USD (+813); " \
        "--apply sends 2 (inputs changed since publication)" \
        in out and "dry run: nothing sent" in out
    tsv = [p for p in (tmp_path / "fairwardgolf/publish").iterdir() if p.name.startswith("reprice-")]
    assert len(tsv) == 1 and f"table: {tsv[0]}" in out
    lines = [line.split("\t") for line in tsv[0].read_text().splitlines()]
    assert lines[0] == list(RP.COLUMNS) and [c[0] for c in lines[1:]] == [HELD, KEY, PLAIN]
    assert lines[3] == [PLAIN, "set-13", "changed", "1", "2.50", "6", "7", "plain rule", "819", "829", "+813/+822",
                        ""]
    assert lines[1][2] == "held" and lines[1][8:11] == ["", "", ""] and lines[1][-1].startswith("no package box")
    assert open(shop.ledger_path, encoding="utf-8").read() == ledger      # nothing written to the ledger


def test_old_prices_from_the_ledger_else_the_plain_rule():
    prepared, _, _ = _product()
    row = RP.reprice("fairwardgolf", KEY, prepared, {"handle": "h", "prices_usd": [100, 120]})
    assert (row["old"], row["old_from"], row["new"], row["status"]) == ([100, 120], "ledger", NEW_PRICES, "changed")
    assert (row["levels"], row["coefficients"]) == ([1], ["2.50"])
    row = RP.reprice("fairwardgolf", KEY, prepared, {"handle": "h"})
    assert (row["old"], row["old_from"]) == ([6, 7], "plain rule")                 # 5 560 / 6 560 KRW at 1000
    assert RP.reprice("another", KEY, prepared, {"handle": "h"})["status"] == "same price"  # a shop without the rule


def test_a_product_without_a_box_is_held_and_the_run_goes_on(tmp_path):
    rows = RP.table(_shop(tmp_path))
    assert [(r["key"], r["status"]) for r in rows] == [(HELD, "held"), (KEY, "same price"), (PLAIN, "changed")]
    assert [r["sends"] for r in rows] == [False, True, True]          # a same price is sent too: its digest moved
    assert rows[0]["new"] is None and "no package box" in rows[0]["reason"]


def test_apply_sends_the_products_not_held_and_the_ledger_gets_the_prices(tmp_path, monkeypatch, capsys):
    shop = _shop(tmp_path)
    prepared_all, translated_all, placed_all = shop.inputs()
    lines = _rows(shop.ledger_path)                     # KEY's inputs unchanged since it was published: skipped
    lines[1]["digest"] = PB.inputs_digest(prepared_all[KEY], translated_all[KEY], placed_all[KEY], "fairwardgolf",
                                          PB.gallery(shop, prepared_all[KEY]), "")
    shop_dir = tmp_path / "fairwardgolf"
    (shop_dir / "publish/published.jsonl").write_text("".join(json.dumps(r) + "\n" for r in lines))
    products, files, calls = FakeProducts(), FakeFiles(), []

    def clients(name):
        calls.append(name)
        return products, files, {"publications": ["gid://shopify/Publication/9"], "location": "gid://shopify/Location/1"}
    monkeypatch.setattr(PB, "clients", clients)
    assert RP.main(["fairwardgolf", "--shops-root", str(tmp_path), "--apply"]) == 0
    out = capsys.readouterr().out
    assert calls == ["fairwardgolf"]                                            # once
    assert [pid for _, pid in products.sent] == ["gid://shopify/Product/13"]    # PLAIN only: HELD held, KEY skipped
    assert f"{KEY}: skipped set-12" in out and f"{PLAIN}: published " in out
    assert "3 products: {'held': 1, 'skipped': 1, 'published': 1}" in out
    last = shop.ledger()
    assert last[PLAIN]["prices_usd"] == NEW_PRICES and last[PLAIN]["pricing"] == "landed/2"
    assert last[HELD]["digest"] == "before-the-rule" and last[HELD]["prices_usd"] == [6, 7]   # untouched


def test_apply_counts_a_refusal_and_goes_on(tmp_path, monkeypatch, capsys):
    from shopify_catalog import CatalogError
    shop = _shop(tmp_path)
    sent = []

    def publish_one(shop_, key, products, files, ids):
        sent.append(key)
        if key == KEY:
            raise CatalogError("userErrors: price")
        return {"key": key, "status": "published", "handle": "h"}
    monkeypatch.setattr(PB, "clients", lambda name: (None, None, {}))
    monkeypatch.setattr(PB, "publish_one", publish_one)
    assert RP.apply(shop, RP.table(shop)) == {"held": 1, "failed": 1, "published": 1}
    assert sent == [KEY, PLAIN] and f"{KEY}: failed userErrors: price" in capsys.readouterr().out


def test_only_limits_the_products(tmp_path, monkeypatch, capsys):
    _shop(tmp_path)
    _no_shopify(monkeypatch)
    RP.main(["fairwardgolf", "--shops-root", str(tmp_path), "--only", PLAIN, "--only", NEW])
    captured = capsys.readouterr()
    assert PLAIN in captured.out and KEY + " " not in captured.out and HELD not in captured.out
    assert f"{NEW}: not published or not ready" in captured.err
    tsv = next(p for p in (tmp_path / "fairwardgolf/publish").iterdir() if p.name.startswith("reprice-"))
    assert [line.split("\t")[0] for line in tsv.read_text().splitlines()[1:]] == [PLAIN]


def test_change_and_range_text():
    assert RP._range([789, 789]) == "789" and RP._range([789, 1299]) == "789-1299" and RP._range(None) == "-"
    assert RP._change([6, 7], [789, 799]) == "+783/+792" and RP._change([800, 800], [789, 789]) == "-11"


@pytest.mark.parametrize("apply_flag", [False, True])
def test_a_shop_with_nothing_published_reads_no_credentials(tmp_path, monkeypatch, capsys, apply_flag):
    (tmp_path / "fairwardgolf").mkdir()
    _no_shopify(monkeypatch)
    RP.main(["fairwardgolf", "--shops-root", str(tmp_path)] + (["--apply"] if apply_flag else []))
    assert "0 products: 0 changed, 0 same price, 0 held" in capsys.readouterr().out


def test_a_published_product_no_longer_ready_is_named_and_left_out(tmp_path, monkeypatch, capsys):
    shop = _shop(tmp_path)
    gone = "fairwardgolf:naver:1:gone"
    with open(shop.ledger_path, "a") as f:
        f.write(json.dumps({"format": "published/1", "key": gone, "status": "published", "handle": "gone"}) + "\n")
    _no_shopify(monkeypatch)
    rows = RP.table(shop)
    assert gone not in [r["key"] for r in rows]
    assert f"{gone}: published but not ready" in capsys.readouterr().err


def test_a_variant_that_breaks_the_rule_otherwise_is_held_too(tmp_path):
    shop = _shop(tmp_path)
    prepared = shop.inputs()[0][KEY]
    prepared["product"]["variants"][0]["price_krw"] = "not a number"
    row = RP.reprice("fairwardgolf", KEY, prepared, shop.ledger()[KEY])
    assert row["status"] == "held" and row["reason"].startswith("ValueError")


def test_an_unknown_shop_writes_nothing(tmp_path, capsys):
    assert RP.main(["nosuchshop", "--shops-root", str(tmp_path)]) == 1
    assert "no shop folder" in capsys.readouterr().err and not (tmp_path / "nosuchshop").exists()
