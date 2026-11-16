"""Offline tests for shopify_catalog.py's CLI and ShopCatalog.paged: real answers of fairwardgolf's store replayed
through the fake Shopify of test_shopify_catalog.py, our files from the shared real-data fixture (shop_fixture).

fixtures/shopify/answers.json: the GraphQL `data` of each call, captured once on 2026-11-16 through ShopCatalog itself
(WRITES = False, check_shop first) by running this CLI against the store: show of an ACTIVE product (13016112970,
7 variants, every metafield, media), a DRAFT one (12557420063, withdrawn), one with 6 variants and one namespace's
metafields (13830324906), dump --limit 20 (one page), counts, a collection and two handle lookups. No token, header
or secret: only the answers' data.

    .venv/bin/python -m pytest scripts/test_shopify_catalog_cli.py -q
"""
import copy
import json
import os

import pytest

import shopify_catalog as SC
from shop_files import read_jsonl
from shopify_catalog import CatalogError, main
from test_shopify_catalog import PROBE, SHOP_ONLY, START, VERIFIED, Answer, catalog, creds, token  # noqa: F401

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "shopify", "answers.json"),
          encoding="utf-8") as _f:
    REAL = json.load(_f)["cases"]


def data(case, n=0):
    """One captured answer as the fake session returns it ({"data": ...}), a fresh copy."""
    return {"data": copy.deepcopy(REAL[case]["answers"][n])}


def node_of(case):
    return REAL[case]["answers"][0]["node"]


def nodes():
    return copy.deepcopy(REAL["dump_page"]["answers"][0]["products"]["nodes"])


def page(items, cursor=None, path=("products",)):
    body = {"nodes": items, "pageInfo": {"hasNextPage": bool(cursor), "endCursor": cursor}}
    for name in reversed(path):
        body = {name: body}
    return {"data": body}


def run(creds, sf, argv, answers, capsys):
    """main() on a fake store: START (mint, verify, probe, check_shop) then `answers`."""
    c, shopify = catalog(creds, START + answers)
    code = main(["fairwardgolf", "--shops-root", sf.shops, *argv], catalog=c)
    out, err = capsys.readouterr()
    return code, out, err, shopify.calls[4:]                   # the calls after check_shop


def ledger_gid(sf, pid):
    path = os.path.join(sf.shops, sf.shop, "publish", "published.jsonl")
    rows = read_jsonl(path, tail_ok=True)
    return [r["product_id"] for r in rows if r["key"] == sf.key(pid) and r.get("product_id")][-1]


# ---- show --------------------------------------------------------------------------------------------------------

def test_show_active_by_naver_id_reads_the_ledgers_product(creds, shop_fixture, capsys):
    code, out, _, calls = run(creds, shop_fixture, ["show", "13016112970", "--variants", "--metafields", "--media"],
                              [data("show_active")], capsys)
    assert code == 0 and len(calls) == 1
    assert calls[0]["variables"] == {"id": ledger_gid(shop_fixture, "13016112970")}
    q = calls[0]["query"]
    assert "variants(first: 100)" in q and "metafields(first: 100)" in q and "media(first: 100)" in q
    lines = out.splitlines()
    assert "status\tACTIVE" in lines and "key\tfairwardgolf:naver:102329146:13016112970" in lines
    assert "variant_count\t7" in lines and "collections\tfairwardgolf-clubs,fairwardgolf-wedge-sets" in lines
    variants = [x for x in lines if x.startswith("variant\t")]
    assert len(variants) == 7 and variants[0].split("\t")[2] == "609.00"
    assert "Size=1 Rainbow 52 56 60 Degree; Style Name=" in variants[0]
    assert len([x for x in lines if x.startswith("media\t")]) == 3
    assert all(len(x.split("\t")) == 4 for x in lines if x.startswith("metafield\t"))     # json values: one cell


def test_show_draft_by_a_handle_of_the_ledger(creds, shop_fixture, capsys):
    handle = node_of("show_draft")["handle"]
    answer = data("show_draft")                                  # as the store answers without the flags
    for extra in ("variants", "metafields", "media"):
        answer["data"]["node"].pop(extra)
    code, out, _, calls = run(creds, shop_fixture, ["show", handle], [answer], capsys)
    assert code == 0 and len(calls) == 1 and "productByIdentifier" not in calls[0]["query"]
    assert "status\tDRAFT" in out.splitlines() and "published\t" in out.splitlines()
    assert "variants(first" not in calls[0]["query"] and "media(first" not in calls[0]["query"]
    assert not [x for x in out.splitlines() if x.split("\t")[0] in ("variant", "metafield", "media")]


@pytest.mark.parametrize("ref", ["gid://shopify/Product/15495241564227",
                                 "https://admin.shopify.com/store/93r1y5-tt/products/15495241564227",
                                 "15495241564227",                                         # the Shopify number
                                 "fairwardgolf:naver:1100167681:13830324906",
                                 "https://smartstore.naver.com/gwglb025/products/13830324906",
                                 "https://fairwardgolf.com/products/"
                                 "mile-high-life-wedge-set-unisex-beginner-right-handed-3-piece-52-56-60"])
def test_show_takes_every_kind_of_ref(creds, shop_fixture, capsys, ref):
    code, out, _, calls = run(creds, shop_fixture, ["show", ref, "--variants", "--metafields", "fairwardgolf"],
                              [data("show_variants")], capsys)
    assert code == 0 and calls[0]["variables"] == {"id": "gid://shopify/Product/15495241564227"}
    meta = [x.split("\t")[1] for x in out.splitlines() if x.startswith("metafield\t")]
    assert meta and all(m.startswith("fairwardgolf.") for m in meta)                       # global.title_tag left out
    assert len([x for x in out.splitlines() if x.startswith("variant\t")]) == 6


def test_show_every_old_handle_of_a_rehandled_product(creds, shop_fixture, capsys):
    path = os.path.join(shop_fixture.shops, shop_fixture.shop, "publish", "published.jsonl")
    key = shop_fixture.key("13830324906")
    handles = {json.loads(x).get("handle") for x in open(path, encoding="utf-8") if key in x} - {None}
    assert len(handles) == 3                                     # the fixture's case: rehandled twice
    for h in handles:
        code, _, _, calls = run(creds, shop_fixture, ["show", h], [data("show_variants")], capsys)
        assert code == 0 and calls[0]["variables"]["id"] == "gid://shopify/Product/15495241564227"


def test_show_one_metafield_and_json(creds, shop_fixture, capsys):
    code, out, _, _ = run(creds, shop_fixture, ["show", "13016112970", "--metafields", "fairwardgolf.source_offer_id",
                                                "--json"], [data("show_active")], capsys)
    node = json.loads(out)
    assert code == 0 and node["metafields"]["nodes"] == [
        {"namespace": "fairwardgolf", "key": "source_offer_id", "type": "single_line_text_field",
         "value": "fairwardgolf:naver:102329146:13016112970"}]
    assert node["id"] == node_of("show_active")["id"]


def test_a_handle_our_files_never_had_is_asked_of_the_store(creds, shop_fixture, capsys, tmp_path):
    empty = tmp_path / "no-shops"                                # an empty shop: no files at all
    empty.mkdir()
    c, shopify = catalog(creds, START + [data("by_handle"), data("show_draft")])
    code = main(["fairwardgolf", "--shops-root", str(empty), "show", REAL["by_handle"]["handle"]], catalog=c)
    assert code == 0 and "productByIdentifier" in shopify.calls[4]["query"]
    assert shopify.calls[4]["variables"] == {"handle": REAL["by_handle"]["handle"]}
    assert shopify.calls[5]["variables"] == {"id": node_of("show_draft")["id"]}
    assert "status\tDRAFT" in capsys.readouterr().out


def test_a_handle_nobody_has(creds, shop_fixture, capsys):
    code, out, err, calls = run(creds, shop_fixture, ["show", "no-such-handle-xyz"], [data("by_handle_missing")],
                                capsys)
    assert code == 1 and out == "" and "neither our files nor the store have it" in err and len(calls) == 1


def test_several_of_our_products_match_names_them_and_asks_nothing(creds, shop_fixture, capsys):
    twin = "fairwardgolf:naver:999:13016112970"                   # the same Naver id under another channel
    path = os.path.join(shop_fixture.shops, shop_fixture.shop, "prepared", "products.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": twin, "status": "ready"}) + "\n")
    code, out, err, calls = run(creds, shop_fixture, ["show", "13016112970"], [], capsys)
    assert code == 1 and out == "" and calls == []
    assert "2 products match" in err and twin in err and shop_fixture.key("13016112970") in err


@pytest.mark.parametrize("ref, message", [
    ("fairwardgolf:naver:101365130:11097352600", "was never sent to the store"),     # held, never published
    ("13532274688", "was never sent to the store"),                                  # placement unresolved
    ("https://fairwardgolf.com/collections/all", "a link without /products/"),
    ("  ", "an empty ref"),
])
def test_refs_that_name_no_product_in_the_store(creds, shop_fixture, capsys, ref, message):
    code, out, err, calls = run(creds, shop_fixture, ["show", ref], [], capsys)
    assert (code, out, calls) == (1, "", []) and message in err


def test_a_product_the_store_no_longer_has(creds, shop_fixture, capsys):
    code, _, err, _ = run(creds, shop_fixture, ["show", "13016112970"], [{"data": {"node": None}}], capsys)
    assert code == 1 and "is not in the store" in err


def test_a_torn_last_ledger_line_is_ignored_like_everywhere(creds, shop_fixture, capsys):
    path = os.path.join(shop_fixture.shops, shop_fixture.shop, "publish", "published.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"key": "fairwardgolf:naver:102329146:13016112970", "product_id": "gid://sho')
    code, _, err, calls = run(creds, shop_fixture, ["show", "13016112970"], [data("show_active")], capsys)
    assert code == 0 and calls[0]["variables"] == {"id": ledger_gid(shop_fixture, "13016112970")}


def test_a_broken_middle_line_stops_with_exit_1(creds, shop_fixture, capsys):
    path = os.path.join(shop_fixture.shops, shop_fixture.shop, "prepared", "products.jsonl")
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    lines.insert(1, "{not json\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    code, _, err, calls = run(creds, shop_fixture, ["show", "13016112970"], [], capsys)
    assert code == 1 and "not a JSON line" in err and calls == []


# ---- dump --------------------------------------------------------------------------------------------------------

def test_dump_one_real_page(creds, shop_fixture, capsys, tmp_path):
    out = tmp_path / "dump.jsonl"
    argv = ["dump", "--limit", "20", "--fields", "id,handle,status,vendor,title,key,variants,price_min,price_max",
            "--out", str(out)]
    code, stdout, err, calls = run(creds, shop_fixture, argv, [data("dump_page")], capsys)
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert code == 0 and stdout == "" and "20 products" in err
    assert len(calls) == 1 and "products(first: 20" in calls[0]["query"]                # --limit: one page, no more
    assert len(rows) == 20 and list(rows[0]) == ["id", "handle", "status", "vendor", "title", "key", "variants",
                                                 "price_min", "price_max"]
    assert all(r["key"].startswith("fairwardgolf:naver:") for r in rows if r["key"])
    assert rows[2]["variants"] == 18 and rows[0]["price_min"] == "1399.0"
    assert not [p for p in os.listdir(tmp_path) if p.endswith(".part")]


def test_dump_defaults_query_and_every_page(creds, shop_fixture, capsys, tmp_path):
    out = tmp_path / "d.jsonl"
    items = nodes()
    code, _, _, calls = run(creds, shop_fixture, ["dump", "--query", "status:active", "--out", str(out)],
                            [page(items[:12], "c1"), page(items[12:])], capsys)
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert code == 0 and len(rows) == 20 and list(rows[0]) == list(SC.DUMP_DEFAULT)
    assert calls[0]["variables"] == {"query": "status:active", "cursor": None}
    assert calls[1]["variables"] == {"query": "status:active", "cursor": "c1"}
    assert "$query: String" in calls[0]["query"] and f"products(first: {SC.PAGE}" in calls[0]["query"]


def test_dump_a_big_catalog(creds, shop_fixture, capsys, tmp_path):
    out, base = tmp_path / "big.jsonl", nodes()[0]
    pages = [page([{**base, "id": f"gid://shopify/Product/{p * 100 + i}"} for i in range(100)],
                  f"c{p}" if p < 29 else None) for p in range(30)]
    code, _, err, calls = run(creds, shop_fixture, ["dump", "--out", str(out)], pages, capsys)
    assert code == 0 and len(calls) == 30 and "3000 products" in err
    assert len(out.read_text(encoding="utf-8").splitlines()) == 3000


def test_a_failed_dump_keeps_the_old_file(creds, shop_fixture, capsys, tmp_path):
    out = tmp_path / "d.jsonl"
    out.write_text("old\n")
    code, _, err, _ = run(creds, shop_fixture, ["dump", "--out", str(out)],
                          [page(nodes()[:5], "c1"), Answer({}, 403)], capsys)
    assert code == 4 and "token is refused" in err
    assert out.read_text() == "old\n" and not [p for p in os.listdir(tmp_path) if ".part" in p]


def test_dump_with_collections_asks_smaller_pages(creds, shop_fixture, capsys, tmp_path):
    items = [{**n, "collections": {"nodes": [{"handle": "fairwardgolf-clubs"}]}} for n in nodes()[:3]]
    code, _, _, calls = run(creds, shop_fixture, ["dump", "--fields", "handle", "collections", "--out",
                                                  str(tmp_path / "c.jsonl")], [page(items)], capsys)
    assert code == 0 and "products(first: 50" in calls[0]["query"]
    assert json.loads((tmp_path / "c.jsonl").read_text().splitlines()[0])["collections"] == ["fairwardgolf-clubs"]


@pytest.mark.parametrize("argv", [["dump", "--fields", "nope", "--out", "x"], ["dump", "--limit", "0", "--out", "x"],
                                  ["dump"], ["collection", "h", "--count-by", "price"], ["bogus"]])
def test_usage_errors_ask_nothing(creds, shop_fixture, capsys, argv):
    c, shopify = catalog(creds, [])
    with pytest.raises(SystemExit) as e:
        main(["fairwardgolf", *argv], catalog=c)
    assert e.value.code == 2 and shopify.calls == []


def test_an_unknown_shop_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as e:
        main(["nosuchshop", "counts"])
    assert e.value.code == 2 and "unknown store" in capsys.readouterr().err


def test_a_store_without_shopify_values_exits_3(capsys):
    assert main(["skinsli", "counts"]) == 3
    assert "no Shopify values yet" in capsys.readouterr().err


# ---- counts, vendors, collection ---------------------------------------------------------------------------------

def test_counts(creds, shop_fixture, capsys):
    code, out, _, calls = run(creds, shop_fixture, ["counts"], [data("counts")], capsys)
    real = REAL["counts"]["answers"][0]
    assert code == 0 and out.splitlines() == [f"{s}\t{real[s]['count']}" for s in ("active", "draft", "archived",
                                                                                     "all")]
    assert 'query: "status:draft"' in calls[0]["query"] and "limit: null" in calls[0]["query"]
    answer = data("counts")
    answer["data"]["all"]["precision"] = "AT_LEAST"
    code, out, _, _ = run(creds, shop_fixture, ["counts", "--json"], [answer], capsys)
    assert json.loads(out)["active"] == real["active"]["count"]
    _, out, _, _ = run(creds, shop_fixture, ["counts"], [answer], capsys)
    assert out.splitlines()[-1] == f"all\t{real['all']['count']}+"


def test_vendors_over_pages(creds, shop_fixture, capsys):
    items = nodes()
    code, out, _, calls = run(creds, shop_fixture, ["vendors"], [page(items[:7], "c"), page(items[7:])], capsys)
    counts = {}
    for n in items:
        counts[n["vendor"]] = counts.get(n["vendor"], 0) + 1
    rows = [x.split("\t") for x in out.splitlines()]
    assert code == 0 and {v: int(c) for v, c in rows} == counts
    assert [int(c) for _, c in rows] == sorted(counts.values(), reverse=True)
    assert f"products(first: {SC.LIGHT_PAGE}" in calls[0]["query"]


def test_collection_products_and_counts(creds, shop_fixture, capsys):
    items, path = nodes(), ("collection", "products")
    col = REAL["collection_lookup"]["answers"][0]["collectionByIdentifier"]
    code, out, err, calls = run(creds, shop_fixture, ["collection", col["handle"]],
                                [data("collection_lookup"), page(items[:10], "c", path), page(items[10:], None, path)],
                                capsys)
    assert code == 0 and len(out.splitlines()) == 20 and f"{col['productsCount']['count']} products" in err
    assert calls[1]["variables"] == {"id": col["id"], "cursor": None} and "collection(id: $id)" in calls[1]["query"]
    assert out.splitlines()[0].split("\t")[:2] == [items[0]["handle"], items[0]["status"]]
    code, out, _, _ = run(creds, shop_fixture, ["collection", col["handle"], "--count-by", "vendor,status", "--json"],
                          [data("collection_lookup"), page(items, None, path)], capsys)
    rows = json.loads(out)
    assert code == 0 and sum(r["count"] for r in rows) == 20 and set(rows[0]) == {"vendor", "status", "count"}


def test_a_collection_the_store_does_not_have(creds, shop_fixture, capsys):
    code, _, err, calls = run(creds, shop_fixture, ["collection", "nope"],
                              [{"data": {"collectionByIdentifier": None}}], capsys)
    assert code == 1 and "no collection" in err and len(calls) == 1


def test_another_shop_answering_stops_before_any_read(creds, shop_fixture, capsys):
    other = {"data": {"shop": {"id": "gid://shopify/Shop/1", "myshopifyDomain": "other.myshopify.com"}}}
    c, shopify = catalog(creds, [token(), VERIFIED, PROBE, other])
    assert main(["fairwardgolf", "counts"], catalog=c) == 4
    assert "not 93r1y5" in capsys.readouterr().err and len(shopify.calls) == 4


# ---- ShopCatalog.paged -------------------------------------------------------------------------------------------

def test_paged_stops_reading_when_the_caller_stops(creds):
    c, shopify = catalog(creds, [token(), VERIFIED, PROBE, page(nodes()[:2], "c1"), page(nodes()[2:4])])
    it = c.paged("query P($cursor: String) { products(first: 2, after: $cursor) { nodes { id } } }", "products")
    assert next(it)["id"] == nodes()[0]["id"]
    it.close()
    assert len(shopify.calls) == 4                                # mint, verify, probe, one page


@pytest.mark.parametrize("answer, message", [
    ({"data": {"products": None}}, "has no products"),
    (page(nodes()[:1], None, ("other",)), "has no products"),
    ({"data": {"products": {"nodes": [], "pageInfo": {"hasNextPage": True}}}}, "a next page without a cursor"),
])
def test_paged_refuses_an_odd_answer(creds, answer, message):
    c, _ = catalog(creds, [token(), VERIFIED, PROBE, answer])
    with pytest.raises(CatalogError, match=message):
        list(c.paged("query P($cursor: String) { products(first: 1, after: $cursor) { nodes { id } } }", "products"))


def test_paged_refuses_a_mutation_and_the_class_still_reads_only(creds):
    c, shopify = catalog(creds, [])
    with pytest.raises(CatalogError, match="reads only"):
        list(c.paged("mutation { productDelete(input: {id: 1}) { deletedProductId } }", "products"))
    assert shopify.calls == [] and SC.ShopCatalog.WRITES is False


def test_the_fixture_holds_no_secret():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "shopify", "answers.json"),
              encoding="utf-8") as f:
        text = f.read()
    for word in ("shpat_", "shpca_", "access_token", "X-Shopify-Access-Token", "client_secret", "PRODUCTS_API_"):
        assert word not in text
    assert {"show_active", "show_draft", "show_variants", "dump_page", "counts"} <= set(REAL)
    assert node_of("show_active")["status"] == "ACTIVE" and node_of("show_draft")["status"] == "DRAFT"
