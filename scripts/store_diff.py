"""What a publication would change in the store, field by field, read only (the owner, 2026-11-11, after the first
new category: a change for one category touched products of another three times, and none of it stopped a run).

    .venv/bin/python scripts/store_diff.py fairwardgolf                       # every published product
    .venv/bin/python scripts/store_diff.py fairwardgolf --category 50002788   # one Naver category
    .venv/bin/python scripts/store_diff.py fairwardgolf --only <key> [--only <key>]
    .venv/bin/python scripts/store_diff.py fairwardgolf --adopt               # record `output` where nothing differs

For each product in the ledger (publish/published.jsonl) it builds what publish.py would send (publish_one in dry
run: no upload, no write) and reads the product from the store (Admin API, the catalog app's read access), then
compares what Shopify keeps: title, vendor, type, tags, status, body, SEO title, options, each variant (by SKU:
price, option values, its metafields), the product's metafields (the reviews' feed by its content hash), the
photos (the store's media by the hash in their file names, in order). Out: one line per product that would
change, with the fields, and shops/<shop>/publish/store_diff.json. A published product that cannot be built now (no longer ready, translated
or placed: an untranslated paid variant, a placement lost) is listed apart: publish.py would leave it as it is.

--adopt: a product whose store data equals what would be sent gets a ledger row with today's `output` (the hash of
what productSet sends, publish.output_digest), copied from its last row otherwise, so publish.py skips it although
its inputs moved. It writes only the local ledger, never the store.
"""
import argparse
import json
import os
import re
import sys
from typing import Any

import publish as P
from shop_stores import get_store

QUERY = """query($ids: [ID!]!) { nodes(ids: $ids) { ... on Product {
  id title vendor productType status tags descriptionHtml seo { title }
  options { name values }
  media(first: 60) { nodes { ... on MediaImage { image { url } } } }
  metafields(first: 60) { nodes { namespace key value } }
  variants(first: 100) { nodes { sku price selectedOptions { name value } metafields(first: 10) {
    nodes { namespace key value } } } }
} } }"""
BATCH = 20
OURS = ("custom", "fairwardgolf")


def _value(v: str | None) -> Any:
    try:
        return json.loads(v) if v is not None else None
    except ValueError:
        return v


def _feed(url: str | None) -> str | None:
    found = re.search(r"-reviews-\d+-([0-9a-f]{24})\.json", url or "")
    return found.group(1) if found else url


def compare(payload: dict[str, Any], live: dict[str, Any], feed_sha: str | None, images: list[str],
            photos: list[str]) -> list[str]:
    """The fields of `live` that `payload` would change (empty: the store has what would be sent)."""
    out: list[str] = []
    for f in ("title", "vendor", "productType", "status"):
        if (live.get(f) or "") != (payload.get(f) or ""):
            out.append(f"{f}: {live.get(f)!r} -> {payload.get(f)!r}")
    if (live.get("descriptionHtml") or "") != (payload.get("descriptionHtml") or ""):
        out.append("descriptionHtml")
    if sorted(live.get("tags") or []) != sorted(payload.get("tags") or []):
        out.append(f"tags: {sorted(set(live['tags']) ^ set(payload['tags']))}")
    if ((live.get("seo") or {}).get("title") or "") != ((payload.get("seo") or {}).get("title") or ""):
        out.append("seo.title")
    # an option's values in any order: Shopify lists them in the order their variants were made (13068838282)
    want_options = [(o["name"], sorted(v["name"] for v in o["values"])) for o in payload.get("productOptions") or []]
    have_options = [(o["name"], sorted(o["values"])) for o in live.get("options") or []]
    if want_options != have_options and not (want_options == [] and have_options == [("Title", ["Default Title"])]):
        out.append("options")
    have = {v["sku"]: v for v in live["variants"]["nodes"]}
    if set(have) != {v["sku"] for v in payload["variants"]}:
        out.append(f"variants: {len(have)} -> {len(payload['variants'])} (SKUs differ)")
    for v in payload["variants"]:
        h = have.get(v["sku"])
        if not h:
            continue
        if f"{float(h['price']):.2f}" != f"{float(v['price']):.2f}":
            out.append(f"price {v['sku']}: {h['price']} -> {v['price']}")
        if [o["value"] for o in h["selectedOptions"]] != [o["name"] for o in v["optionValues"]] and v["optionValues"]:
            out.append(f"option values {v['sku']}")
        hm = {(m["namespace"], m["key"]): _value(m["value"]) for m in h["metafields"]["nodes"]}
        for m in v.get("metafields") or []:
            if hm.get((m["namespace"], m["key"])) != _value(m["value"]):
                out.append(f"variant {m['namespace']}.{m['key']}")
    lm = {(m["namespace"], m["key"]): m["value"] for m in live["metafields"]["nodes"] if m["namespace"] in OURS}
    sent = set()
    for m in payload.get("metafields") or []:
        k = (m["namespace"], m["key"])
        sent.add(k)
        if k == ("custom", "reviews_feed_url"):
            if _feed(lm.get(k)) != feed_sha:
                out.append("reviews feed")
        elif _value(lm.get(k)) != _value(m["value"]):
            out.append(f"{k[0]}.{k[1]}")
    out += [f"{k[0]}.{k[1]} (deleted)" for k in P.sp.MANAGED if k in lm and k not in sent]
    if photos != images:
        out.append(f"photos: {len(photos)} -> {len(images)}" + ("" if len(photos) != len(images) else " (order or content)"))
    return list(dict.fromkeys(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shop")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--category", help="a Naver leaf category id")
    ap.add_argument("--adopt", action="store_true", help="record today's output for products the store already has")
    ap.add_argument("--shops-root", default=P.SHOPS_ROOT)
    args = ap.parse_args(argv)
    from shopify_admin import ProductsAdmin
    from shopify_catalog import ShopCatalog
    store = get_store(args.shop)
    shop = P.Shop(args.shop, args.shops_root)
    prepared, _, _ = shop.inputs()
    ledger, ready = shop.ledger(), set(shop.ready())
    keys = [k for k in (args.only or sorted(ledger)) if k in ledger and (not args.category or str(
        ((prepared.get(k) or {}).get("source") or {}).get("category_id")) == args.category)]
    catalog = ShopCatalog(store)
    catalog.check_shop()
    admin = ProductsAdmin(store)                         # read only here: the store's vendor spellings
    admin.check_shop()
    ids = {"vendors": P.vendor_spellings(admin.vendor_spellings()), "tenant": store.publisher}
    report: dict[str, Any] = {"shop": args.shop, "changes": {}, "same": [], "not_buildable": {}, "adopted": []}
    built: dict[str, dict[str, Any]] = {}
    for key in keys:
        if key not in ready:
            p = prepared.get(key) or {}
            report["not_buildable"][key] = "not ready / translated / placed" if p.get("status") == "ready" \
                else f"prepared {p.get('status')}"
            continue
        try:
            built[key] = P.publish_one(shop, key, None, None, dict(ids), dry_run=True)
        except Exception as e:                              # Untranslated, PayloadError: it would not be sent
            report["not_buildable"][key] = f"{type(e).__name__}: {e}"
    for i in range(0, len(built), BATCH):
        part = list(built)[i:i + BATCH]
        answer = catalog._post(QUERY, {"ids": [ledger[k]["product_id"] for k in part]})
        nodes = (answer.get("data") or answer)["nodes"]
        for key, live in zip(part, nodes):
            row = built[key]
            if live is None:
                report["changes"][key] = ["not in the store"]
                continue
            with open(row["payload"], encoding="utf-8") as f:
                payload = json.load(f)
            # the store's own photos, by the hash in their file names (2026-11-12: the ledger said 12211893510 had
            # 6 of its 7 photos; the store had lost the first and showed the putter twice)
            photos = [P._sha16(m) or "?" for m in (live.get("media") or {}).get("nodes") or []]
            diff = compare(payload, live, row["feed_sha"], [s[:16] for s in row["images"]], photos)
            if diff:
                report["changes"][key] = diff
                continue
            report["same"].append(key)
            if args.adopt and ledger[key].get("output") != row["output"]:
                P._append(shop.ledger_path, {**ledger[key], "output": row["output"], "adopted": P._now()})
                report["adopted"].append(key)
    out = os.path.join(shop.dir, "publish", "store_diff.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    for key, diff in report["changes"].items():
        print(f"{key}: would change: {'; '.join(diff)}")
    for key, why in report["not_buildable"].items():
        print(f"{key}: would not be sent: {why}")
    print(f"store_diff {args.shop}: {len(keys)} published; {len(report['changes'])} would change, "
          f"{len(report['same'])} as in the store, {len(report['not_buildable'])} not buildable"
          + (f"; output recorded for {len(report['adopted'])}" if args.adopt else "") + f" -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
