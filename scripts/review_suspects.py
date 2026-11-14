"""The published products of a category that look doubtful, for the owner's review after a lenient run (the owner,
2026-11-14: the screen leaves out only what is certainly not a set; everything doubtful is published and reviewed
afterwards). Read only and offline: the shop's prepared/products.jsonl and publish/published.jsonl (a key's last line;
only `published` ones); the price is today's rule's (shop_pricing, what publish.py sends; a product repriced by hand
may differ in the store). It changes nothing in the store.

    .venv/bin/python scripts/review_suspects.py fairwardgolf [--category 50002788] [--job ID] [--out FILE.csv]

A product is listed with every reason that fits (none: not listed):

  single_club   the transform's own single-club test (package_measures.default_kind with the 50002787 row's
                `single_club` kind, on the title and each variant's words), or the spec rows 아이언개수 단품 /
                총클럽개수 1개, or a word of the category's `folding` title rule (a folding club is one club)
  few_clubs     2-3 clubs: 2종 / 3종 / 2pcs / 3pcs (not 12종, 13pcs) in the title, the `two_clubs` kind, or
                총클럽개수 2개 / 3개
  used          중고 in the title (not 중고급, 초중고, 중고생)
  junior        a junior word (JUNIOR: 주니어, 쥬니어, 어린이, ...; not 주니어용가능 / 겸용 / 및): no title rule leaves
                a junior set out (no other job collects it), so a junior set published as an adult one is found here
  accessory     a word of the category's `accessory` title rules (listing_title_rules.json), their `unless` not
                applied, and 골프공 / 골프볼 (not in the rule: a set given with balls may name no set word)

It prints a table (reason counts first) and writes a CSV (key, product id, handle, admin url, price, reasons,
title): next to the job with --job (<job folder>/suspects.csv, only that job's keys), else in the shop folder
(review_suspects-<category>.csv).
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from typing import Any, Iterable

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
JOBS_ROOT = os.path.join(SCRIPTS, "output", "jobs")
REASONS = ("single_club", "few_clubs", "used", "junior", "accessory")
_FEW = re.compile(r"(?<![0-9])[23]\s*(?:종(?!류)|pcs|pc(?![a-z])|피스)", re.I)
_USED = re.compile(r"(?<!초)중고(?!급|생|등|수)")
_NOT_AFTER = ["용가능", "겸용", "및"]
# The owner, 2026-11-14: never lose a real product, so no title rule leaves a junior set out; the review lists them.
JUNIOR = [{"text": t, "notFollowedBy": _NOT_AFTER, "notPrecededBy": []}
          for t in ("주니어", "쥬니어", "어린이", "아동", "유아", "키즈", "초등", "유치원", "청소년", "kids", "junior")]
BALLS = [{"text": t, "notFollowedBy": [], "notPrecededBy": []} for t in ("골프공", "골프볼")]


def _lines(path: str) -> Iterable[dict[str, Any]]:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for x in f:
            if x.strip():
                try:
                    yield json.loads(x)
                except ValueError:
                    pass                                  # a torn last line


def published(shop_dir: str) -> dict[str, dict[str, Any]]:
    """key -> its last published.jsonl line, for the keys whose last line is `published`."""
    last: dict[str, dict[str, Any]] = {}
    for r in _lines(os.path.join(shop_dir, "publish", "published.jsonl")):
        last[r["key"]] = r
    return {k: r for k, r in last.items() if r.get("status") == "published"}


def _kinds() -> dict[str, dict[str, Any]]:
    """The transform's club-count kinds (category_measures.json, the 50002787 row: single_club, two_clubs)."""
    from package_measures import load_table
    row = next((r for r in load_table()["rows"] if str(r["category_id"]) == "50002787"), {})
    return {"kinds": [k for k in row.get("kinds") or [] if k["kind"] in ("single_club", "two_clubs")]}


def _words(category: str, codes: tuple[str, ...]) -> list[dict[str, Any]]:
    from listing_filter import title_rules
    return [t for rule in title_rules(category) if rule["code"] in codes for t in rule["tokens"]]


def _spec(product: dict[str, Any], label: str) -> str:
    return next((s.get("value_ko") or "" for s in product.get("specs") or [] if s.get("label_ko") == label), "")


def reasons(product: dict[str, Any], kinds: dict[str, Any], junior: list[dict], accessory: list[dict],
            folding: list[dict] = ()) -> list[str]:
    """The review reasons of one prepared product (REASONS order)."""
    from listing_filter import normalize, term_matches
    from package_measures import default_kind
    title = product.get("title_ko") or ""
    flat = re.sub(r"\s+", "", normalize(title))
    variants = [" ".join(v.get("options_ko") or []) for v in product.get("variants") or []] or [None]
    found = {(default_kind(kinds, title, v) or {}).get("kind") for v in variants}
    count = re.match(r"\s*(\d+)\s*개", _spec(product, "총클럽개수"))
    out = []

    def said(words: Iterable[dict]) -> bool:
        return any(term_matches(flat, {**t, "text": re.sub(r"\s+", "", t["text"])}) for t in words)
    if "single_club" in found or _spec(product, "아이언개수") == "단품" or count and count.group(1) == "1" \
            or said(folding):
        out.append("single_club")
    if "two_clubs" in found or _FEW.search(normalize(title)) or count and count.group(1) in ("2", "3"):
        out.append("few_clubs")
    if _USED.search(flat):
        out.append("used")
    if said(junior):
        out.append("junior")
    if said(accessory):
        out.append("accessory")
    return out


def price(shop: str, product: dict[str, Any]) -> str:
    """The variants' prices by today's price rule (shop_pricing, offline: what publish.py sends), USD; a product
    the rule cannot price: its Naver price in KRW."""
    from shop_pricing import policy
    rule = policy(shop)
    try:
        values = sorted({float(rule.quote(v, product).price) for v in product.get("variants") or []})
    except Exception:                                     # PriceError, a variant without a price: shown in KRW
        values = []
    if values:
        lo, hi = values[0], values[-1]
        return f"${lo:.2f}" if lo == hi else f"${lo:.2f}-{hi:.2f}"
    krw = (product.get("pricing") or {}).get("base_krw")
    return f"{krw} KRW" if krw else ""


def suspects(shop_dir: str, category: str, keys: set[str] | None = None) -> list[dict[str, Any]]:
    live = published(shop_dir)
    kinds = _kinds()
    junior, accessory, folding = JUNIOR, _words(category, ("accessory",)) + BALLS, _words(category, ("folding",))
    out = []
    for r in _lines(os.path.join(shop_dir, "prepared", "products.jsonl")):
        key = r.get("key")
        if str((r.get("source") or {}).get("category_id")) != category or key not in live:
            continue
        if keys is not None and key not in keys:
            continue
        why = reasons(r["product"], kinds, junior, accessory, folding)
        if not why:
            continue
        pub = live[key]
        out.append({"key": key, "product_id": str(pub.get("product_id") or "").rsplit("/", 1)[-1],
                    "handle": pub.get("handle") or "", "admin_url": pub.get("admin_url") or "",
                    "price": price(os.path.basename(shop_dir), r["product"]),
                    "reasons": ";".join(why), "title": r["product"].get("title_ko") or ""})
    return out


def job_keys(job_id: str, root: str = JOBS_ROOT) -> tuple[set[str], str]:
    folder = os.path.join(root, job_id)
    keys = {r["key"] for r in _lines(os.path.join(folder, "listing.jsonl")) if r.get("key")}
    return keys, folder


def write_csv(rows: list[dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:      # utf-8-sig: Excel reads the Korean
        w = csv.DictWriter(f, fieldnames=["key", "product_id", "handle", "admin_url", "price", "reasons", "title"])
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("shop")
    ap.add_argument("--category", default="50002788")
    ap.add_argument("--job", help="only this job's keys (its listing.jsonl); the CSV goes next to the job")
    ap.add_argument("--shops-root", default=SHOPS_ROOT)
    ap.add_argument("--jobs-root", default=JOBS_ROOT)
    ap.add_argument("--out", help="the CSV's path (default: next to the job, or in the shop folder)")
    args = ap.parse_args(argv)
    shop_dir = os.path.join(args.shops_root, args.shop)
    if not os.path.isdir(shop_dir):
        print(f"stop: no shop folder {shop_dir}")
        return 2
    keys, out = None, os.path.join(shop_dir, f"review_suspects-{args.category}.csv")
    if args.job:
        keys, folder = job_keys(args.job, args.jobs_root)
        if not os.path.isdir(folder):
            print(f"stop: no job folder {folder}")
            return 2
        out = os.path.join(folder, "suspects.csv")
    rows = suspects(shop_dir, args.category, keys)
    counts = Counter(x for r in rows for x in r["reasons"].split(";"))
    print(f"{len(rows)} doubtful published products of {args.category}"
          + (f" in job {args.job}" if args.job else "") + ": "
          + ", ".join(f"{r} {counts[r]}" for r in REASONS if counts[r]))
    for r in sorted(rows, key=lambda r: (r["reasons"], r["key"])):
        print(f"{r['reasons']:<24} {r['key']:<48} {r['product_id']:<16} {r['price']:<16} {r['title'][:70]}")
    write_csv(rows, args.out or out)
    print(f"csv: {args.out or out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
