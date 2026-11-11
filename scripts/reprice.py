"""Reprice: the products a shop already has in its store, priced by the shop's rule now (the owner, 2026-11-11).

The owner, 2026-11-11: the price with delivery, duty and margin (shop_pricing.py) is made for future products in
the full flow (job.py -> publish.py); the products published before it get their prices back through a separate
flow, this one. Per product published and still ready it shows the prices the store has (the ledger's
`prices_usd`; a row written before the ledger kept them: what the plain rule gave, 1 000 KRW = 1 USD up to a
whole dollar) next to what the shop's rule gives now, with the confidence level(s) and coefficient(s) of the boxes.
`--apply` sends them again through publish.publish_one: the rule is in the publication's digest, so a product it
changes is sent and one whose digest did not change is skipped.

    .venv/bin/python scripts/reprice.py fairwardgolf                     # the table only: nothing sent (dry run)
    .venv/bin/python scripts/reprice.py fairwardgolf --only <key> [--only <key>]
    .venv/bin/python scripts/reprice.py fairwardgolf --apply             # then send them (Shopify)
    .venv/bin/python scripts/reprice.py fairwardgolf --shops-root scripts/output/trial-20261108/shops

The table is also written as tab-separated text to shops/<shop>/publish/reprice-<UTC time>.tsv. A product whose
price cannot be made (a variant without a box, a box over the tariff: shop_pricing.PriceError) is held with the
reason, stays as it is in the store and the run goes on. Without --apply no credentials are read.
"""
import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

import publish as PB
import shopify_payload as sp
from shop_pricing import Policy, PriceError, policy
from shopify_catalog import CatalogError

COLUMNS = ("key", "handle", "status", "levels", "coefficients", "old_min", "old_max", "old_from", "new_min",
           "new_max", "change", "reason")


def _span(prices: list[int]) -> list[int]:
    return [min(prices), max(prices)]


def _range(span: list[int] | None) -> str:
    if not span:
        return "-"
    return str(span[0]) if span[0] == span[1] else f"{span[0]}-{span[1]}"


def _change(old: list[int], new: list[int]) -> str:
    """The difference of the lowest prices, and of the highest when they differ from it: "+640", "+640/+702"."""
    low, high = new[0] - old[0], new[1] - old[1]
    return f"{low:+d}" if low == high else f"{low:+d}/{high:+d}"


def reprice(shop: str, key: str, prepared: dict[str, Any], published: dict[str, Any]) -> dict[str, Any]:
    """One product's row: the old and the new [lowest, highest] variant price in whole dollars, its status
    (changed / same price / held) and, in a shop with the rule, the levels and coefficients of its boxes."""
    product, rule = prepared["product"], policy(shop)
    variants = product.get("variants") or []
    old, old_from = published.get("prices_usd"), "ledger"
    if not old and variants:
        plain = Policy(krw_per_usd=rule.krw_per_usd)
        old, old_from = _span([plain.quote(v, product).price for v in variants]), "plain rule"
    row: dict[str, Any] = {"key": key, "handle": published.get("handle") or "", "old": old, "old_from": old_from,
                           "new": None, "levels": [], "coefficients": [], "reason": ""}
    try:
        if not variants:
            raise PriceError("no variant")
        quotes = [rule.quote(v, product) for v in variants]
    except (PriceError, KeyError, TypeError, ValueError) as e:     # one product never stops the table
        return {**row, "status": "held", "reason": str(e) if isinstance(e, PriceError) else f"{type(e).__name__}: {e}"}
    breakdowns = [q.breakdown for q in quotes if q.breakdown]
    new = _span([q.price for q in quotes])
    return {**row, "new": new, "status": "changed" if new != old else "same price",
            "levels": sorted({b["level"] for b in breakdowns}),
            "coefficients": sorted({b["coefficient"] for b in breakdowns}, key=float)}


def table(shop: PB.Shop, only: list[str] | None = None) -> list[dict[str, Any]]:
    """The rows of the shop's products that are published and ready (in the prepared file's order); `only`: these
    keys (one not published or not ready is reported on stderr)."""
    published, prepared = shop.ledger(), shop.inputs()[0]
    ready = set(shop.ready())
    keys = [k for k in shop.ready() if k in published]
    for k in sorted(set(published) - ready):
        if not only or k in only:
            print(f"{k}: published but not ready (prepared, translated or placed is missing): not repriced",
                  file=sys.stderr)
    for k in (only or []):
        if k not in keys:
            print(f"{k}: not published or not ready (needs prepared ready, translated, placed)", file=sys.stderr)
    if only:
        keys = [k for k in keys if k in only]
    rows = [reprice(shop.shop, k, prepared[k], published[k]) for k in keys]
    for r in rows:                              # what --apply really sends: the inputs changed since publication
        r["sends"] = r["status"] != "held" and sends(shop, r["key"], published[r["key"]])
    return rows


def sends(shop: PB.Shop, key: str, published: dict[str, Any]) -> bool:
    """Whether publish_one would send the product: its digest now differs from the ledger's (a new rule changes the
    cost per item and the breakdown too, so a product whose price stays the same is still sent)."""
    import describe
    prepared, translated, placed = (part[key] for part in shop.inputs())
    description = (describe.load_store(shop.dir).get(key) or {}).get("html") or ""
    return PB.inputs_digest(prepared, translated, placed, shop.shop, PB.gallery(shop, prepared),
                            description) != published.get("digest")


def line(row: dict[str, Any]) -> str:
    head = f"{row['key']}  {row['handle'] or '-'}"
    old = f"{_range(row['old'])}{' (plain rule)' if row['old_from'] != 'ledger' else ''}"
    if row["status"] == "held":
        return f"{head}  held: {row['reason']}  (stays at {old})"
    levels = ",".join(str(n) for n in row["levels"]) or "-"
    coefficients = ",".join(row["coefficients"]) or "-"
    return (f"{head}  level {levels} x{coefficients}  {old} -> {_range(row['new'])}  "
            f"{_change(row['old'], row['new']) if row['old'] else ''}".rstrip())


def write_tsv(shop: PB.Shop, rows: list[dict[str, Any]], at: datetime | None = None) -> str:
    stamp = (at or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    path = shop.path(os.path.join("publish", f"reprice-{stamp}.tsv"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for r in rows:
            old, new = r["old"] or [None, None], r["new"] or [None, None]
            cells = [r["key"], r["handle"], r["status"], ",".join(str(n) for n in r["levels"]),
                     ",".join(r["coefficients"]), old[0], old[1], r["old_from"], new[0], new[1],
                     _change(r["old"], r["new"]) if r["old"] and r["new"] else "", r["reason"]]
            f.write("\t".join("" if c is None else str(c).replace("\t", " ").replace("\n", " ")
                              for c in cells) + "\n")
    return path


def summary(rows: list[dict[str, Any]]) -> str:
    """Counts, and the sum of the lowest prices of the products priced now (old -> new), whole dollars."""
    count = {s: sum(1 for r in rows if r["status"] == s) for s in ("changed", "same price", "held")}
    priced = [r for r in rows if r["new"] and r["old"]]
    old, new = sum(r["old"][0] for r in priced), sum(r["new"][0] for r in priced)
    return (f"{len(rows)} products: {count['changed']} changed, {count['same price']} same price, {count['held']} held; "
            f"lowest prices of the {len(priced)} priced: {old} USD -> {new} USD ({new - old:+d}); "
            f"--apply sends {sum(1 for r in rows if r.get('sends'))} (inputs changed since publication)")


def apply(shop: PB.Shop, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Send every row not held through publish.publish_one (Shopify); the statuses counted as publish.main counts."""
    counts: dict[str, int] = {}
    send = [r for r in rows if r["status"] != "held"]
    for r in rows:
        if r["status"] == "held":
            counts["held"] = counts.get("held", 0) + 1
    if not send:
        return counts
    products, files, ids = PB.clients(shop.shop)
    for r in send:
        key = r["key"]
        try:
            out = PB.publish_one(shop, key, products, files, ids)
        except (sp.Untranslated, sp.PayloadError) as e:
            out = {"key": key, "status": "held", "reason": f"{type(e).__name__}: {e}"}
        except CatalogError as e:                       # Shopify refused: go on with the next product
            out = {"key": key, "status": "failed", "reason": str(e)[:500]}
        counts[out["status"]] = counts.get(out["status"], 0) + 1
        print(f"{key}: " + " ".join(str(out[k]) for k in ("status", "handle", "admin_url", "reason") if out.get(k)))
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shop")
    ap.add_argument("--only", action="append", default=[], help="a product key (repeat for several)")
    ap.add_argument("--apply", action="store_true", help="send the products to the store (default: the table only)")
    ap.add_argument("--shops-root", default=PB.SHOPS_ROOT, help="the folder holding <shop>/")
    args = ap.parse_args(argv)
    shop = PB.Shop(args.shop, args.shops_root)
    if not os.path.isdir(shop.dir):
        print(f"no shop folder {shop.dir}", file=sys.stderr)
        return 1
    rows = table(shop, args.only)
    for r in rows:
        print(line(r))
    print(f"reprice {args.shop} ({policy(args.shop).describe()['version']}): {summary(rows)}")
    print(f"table: {write_tsv(shop, rows)}")
    if args.apply:
        print(f"reprice {args.shop} --apply: {len(rows)} products: {apply(shop, rows)}")
    else:
        print("dry run: nothing sent (--apply sends them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
