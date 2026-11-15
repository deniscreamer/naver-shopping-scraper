"""Duplicates: one product sold by several stores, kept once in the shop, at the best seller (the owner approved
the rule 2026-11-15; research/dedupe/final.md). Pure functions over the collected records, an in-memory index
for a job (job.py --dedupe), and two read-only commands for the owner:

    .venv/bin/python scripts/dedupe.py --report fairwardgolf [--category 50002787]   # duplicate groups in the store
    .venv/bin/python scripts/dedupe.py --pairs fairwardgolf --job <job id> [--out DIR] # a job's pairs, side by side

The rule:
  1. title key: the category + the set of the name's tokens (NFKC, lower case, [0-9a-z가-힣]+, what is in brackets
     kept, order ignored). A possible duplicate has the same title key, another store (channel_no) and a price
     within PRICE_RATIO (x2) of it. Products are matched by name only here: the screen (listing_filter) and the
     shop check (shopify_catalog) still match by the source key.
  2. confirmed by the collected records: the first photo is the same file (source_sha256), or >= PHOTOS_SHARED of
     the smaller gallery are the same files, or the variants' values agree >= VARIANTS_JACCARD (Jaccard over each
     variant's options, case and spaces ignored; no variants on either side: no signal). Not confirmed: an ordinary
     product (a renamed copy is not caught: a copy, as before).
  3. who is better (better(a, b), strict): the store's grade (GRADES), then the product's review count. Price never
     decides (only the x2 guard).

Index: built at a job's start from the publication ledger (published products, and withdrawn ones except those
withdrawn as replaced_by:<key>: their replacement is the live copy) plus the job's own collected products, each with
its latest collected record; add() takes in a product the job collected, so a later seller of it in the same job is
compared with it. decide() gives the decision for a candidate:
  duplicate_of_withdrawn  a confirmed match was withdrawn by the owner: never taken
  duplicate_of            the candidate is not strictly better than the best confirmed match: not taken
  duplicate_better        it is strictly better: taken, and the match is withdrawn once the candidate is published
                          (job.py: still published, and the new product has no fewer variants)
  None                    no confirmed match (`matches` still lists the title matches and their signals)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata
from typing import Any, Iterable

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
JOBS_ROOT = os.path.join(SCRIPTS, "output", "jobs")
GRADES = ("SEED", "SPROUT", "POWER", "BIG_POWER", "PREMIUM", "PLATINUM")   # Naver's store grades, lowest first
PRICE_RATIO = 2.0
PHOTOS_SHARED = 0.5
VARIANTS_JACCARD = 0.8
REPLACED = "replaced_by:"                       # the withdraw reason job.py writes for a replaced product
TOKEN = re.compile(r"[0-9a-z가-힣]+")


# ---- pure functions ------------------------------------------------------------------------------------------

def title_key(name: str | None, category: str | None) -> str | None:
    """'<category>|<sorted tokens>' (None without a name or a token)."""
    tokens = sorted(set(TOKEN.findall(unicodedata.normalize("NFKC", name or "").lower())))
    return f"{category or ''}|{' '.join(tokens)}" if tokens else None


def grade_rank(grade: str | None) -> int:
    """PLATINUM 5 ... SEED 0; no grade or an unknown one -1."""
    return GRADES.index(grade) if grade in GRADES else -1


def _norm(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", str(value)).lower().split())


def entry(line: dict[str, Any], status: str = "job") -> dict[str, Any]:
    """What the rule needs of a collected record (job.py's kept line): key, store, category, title key, price, grade,
    review count, photos' source hashes (the first one apart), variant values, variant count."""
    listing = line.get("listing") or {}
    details = line.get("details") or {}
    key = line.get("key") or listing.get("key") or ""
    parts = key.split(":")
    category = str(listing.get("category_id") or ((line.get("specs") or {}).get("category") or {}).get("id") or "")
    pricing = listing.get("pricing") or details.get("pricing") or {}
    files = sorted((f for f in (line.get("photos") or {}).get("files") or [] if f.get("source_sha256")),
                   key=lambda f: f.get("position", 0))
    variants = (line.get("variants") or {}).get("variants") or []
    name = listing.get("name") or details.get("name")
    return {"key": key, "channel": parts[2] if len(parts) > 3 else str((listing.get("store") or {}).get("channel_no")),
            "category": category, "name": name, "tkey": title_key(name, category),
            "price": pricing.get("discounted_price") or pricing.get("sale_price"),
            "grade": (listing.get("store") or {}).get("grade"), "reviews": (listing.get("reviews") or {}).get("count") or 0,
            "first": files[0]["source_sha256"] if files else None, "shas": {f["source_sha256"] for f in files},
            "values": {"/".join(_norm(o) for o in v.get("options") or [v.get("name") or ""]) for v in variants},
            "variants": len(variants), "status": status}


def better(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """a strictly better than b: a higher grade, or the same grade and more reviews."""
    return (grade_rank(a.get("grade")), a.get("reviews") or 0) > (grade_rank(b.get("grade")), b.get("reviews") or 0)


def price_ok(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """The prices within PRICE_RATIO of each other (a missing price: no guard)."""
    pa, pb = a.get("price"), b.get("price")
    if not pa or not pb:
        return True
    return max(pa, pb) / min(pa, pb) <= PRICE_RATIO


def signals(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """The confirmation signals of a pair and whether they confirm it."""
    first = bool(a["first"]) and a["first"] == b["first"]
    small = min(len(a["shas"]), len(b["shas"]))
    photos = round(len(a["shas"] & b["shas"]) / small, 2) if small else 0.0
    union = a["values"] | b["values"]
    variants = round(len(a["values"] & b["values"]) / len(union), 2) if a["values"] and b["values"] else 0.0
    return {"first_photo": first, "photos": photos, "variants": variants,
            "confirmed": first or photos >= PHOTOS_SHARED or variants >= VARIANTS_JACCARD}


def confirm(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    return signals(candidate, existing)["confirmed"]


def possible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Step 1: the same title key, another store, the price guard."""
    return bool(a["tkey"]) and a["tkey"] == b["tkey"] and a["channel"] != b["channel"] and a["key"] != b["key"] \
        and price_ok(a, b)


def _brief(e: dict[str, Any]) -> dict[str, Any]:
    return {"key": e["key"], "status": e["status"], "grade": e["grade"], "reviews": e["reviews"], "price": e["price"],
            "variants": e["variants"]}


class Index:
    """The products a candidate is compared with, by title key."""

    def __init__(self, entries: Iterable[dict[str, Any]] = ()):
        self.by_key: dict[str, dict[str, Any]] = {}
        for e in entries:
            self.add(e)

    def add(self, e: dict[str, Any]) -> None:
        if e.get("key") and e.get("tkey"):
            self.by_key[e["key"]] = e

    def drop(self, key: str) -> None:
        self.by_key.pop(key, None)

    def matches(self, c: dict[str, Any]) -> list[dict[str, Any]]:
        return [e for e in self.by_key.values() if possible(c, e)]

    def decide(self, c: dict[str, Any]) -> dict[str, Any]:
        """{decision, of, matches: [{key, status, grade, reviews, price, variants, first_photo, photos, variants_j,
        confirmed}]} (decision None: no confirmed match)."""
        found = [(e, signals(c, e)) for e in self.matches(c)]
        rows = [{**_brief(e), **{("variants_j" if k == "variants" else k): v for k, v in s.items()}}
                for e, s in found]
        confirmed = [e for e, s in found if s["confirmed"]]
        out: dict[str, Any] = {"decision": None, "of": None, "matches": rows}
        withdrawn = [e for e in confirmed if e["status"] == "withdrawn"]
        if withdrawn:
            return {**out, "decision": "duplicate_of_withdrawn", "of": withdrawn[0]["key"]}
        if not confirmed:
            return out
        best = max(confirmed, key=lambda e: (grade_rank(e["grade"]), e["reviews"] or 0))
        return {**out, "decision": "duplicate_better" if better(c, best) else "duplicate_of", "of": best["key"]}


# ---- reading the shop ----------------------------------------------------------------------------------------

def _jsonl(path: str) -> list[dict[str, Any]]:
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass                                    # a torn last line
    return out


def ledger(shop: str, shops_root: str = SHOPS_ROOT) -> dict[str, dict[str, Any]]:
    """key -> the publication ledger's last line."""
    last: dict[str, dict[str, Any]] = {}
    for row in _jsonl(os.path.join(shops_root, shop, "publish", "published.jsonl")):
        last[row.get("key")] = row
    return last


def ledger_status(row: dict[str, Any]) -> str | None:
    """published, withdrawn (by the owner), or None (not in the store, or withdrawn as replaced: not compared)."""
    if row.get("status") == "published":
        return "published"
    if row.get("status") == "withdrawn" and not str(row.get("reason") or "").startswith(REPLACED):
        return "withdrawn"
    return None


def collected(shop: str, shops_root: str = SHOPS_ROOT) -> dict[str, dict[str, Any]]:
    """key -> the latest collected record (run_transform.latest_lines)."""
    if not os.path.isdir(os.path.join(shops_root, shop, "collected")):
        return {}
    from run_transform import latest_lines
    return {k: v[2] for k, v in latest_lines(shop, None, shops_root).items()}


def load(shop: str, shops_root: str = SHOPS_ROOT, job_keys: Iterable[str] = (), withdrawn: bool = True,
         records: dict[str, dict[str, Any]] | None = None) -> Index:
    """The index of a shop: its published (and, with `withdrawn`, owner-withdrawn) products, plus `job_keys` (a job's
    own collected products), each from its latest collected record; a key without one is left out."""
    records = collected(shop, shops_root) if records is None else records
    index = Index()
    for key in job_keys:
        if key in records:
            index.add(entry(records[key], "job"))
    for key, row in ledger(shop, shops_root).items():
        status = ledger_status(row)
        if status and key in records and (withdrawn or status == "published"):
            index.add(entry(records[key], status))
    return index


def variant_count(shop: str, key: str, shops_root: str = SHOPS_ROOT) -> int | None:
    """The prepared product's variant count (what the store shows); None when it is not prepared."""
    prepared = {p.get("key"): p for p in _jsonl(os.path.join(shops_root, shop, "prepared", "products.jsonl"))}
    if key not in prepared:
        return None
    return len((prepared[key].get("product") or {}).get("variants") or [])


# ---- --report ------------------------------------------------------------------------------------------------

def groups(entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Duplicate groups among products already in the store: the same title key, joined by confirmed pairs of
    different stores within the price guard; each group best first."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e["tkey"]:
            buckets.setdefault(e["tkey"], []).append(e)
    out = []
    for bucket in buckets.values():
        parent = list(range(len(bucket)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                if possible(bucket[i], bucket[j]) and confirm(bucket[i], bucket[j]):
                    parent[root(i)] = root(j)
        joined: dict[int, list[dict[str, Any]]] = {}
        for i, e in enumerate(bucket):
            joined.setdefault(root(i), []).append(e)
        for g in joined.values():
            if len(g) > 1:
                out.append(sorted(g, key=lambda e: (-grade_rank(e["grade"]), -(e["reviews"] or 0), e["key"])))
    return sorted(out, key=lambda g: (g[0]["category"], g[0]["tkey"]))


def report(shop: str, shops_root: str = SHOPS_ROOT, category: str | None = None) -> dict[str, Any]:
    index = load(shop, shops_root, withdrawn=False)
    entries = [e for e in index.by_key.values() if category is None or e["category"] == category]
    found = groups(entries)
    by_cat: dict[str, dict[str, int]] = {}
    for g in found:
        c = by_cat.setdefault(g[0]["category"], {"groups": 0, "products": 0})
        c["groups"] += 1
        c["products"] += len(g)
    stores: dict[str, set[str]] = {}
    for e in entries:
        stores.setdefault(e["tkey"], set()).add(e["channel"])
    same_title = sum(1 for s in stores.values() if len(s) > 1)
    return {"published": len(entries), "groups": len(found), "products": sum(len(g) for g in found),
            "extra_copies": sum(len(g) - 1 for g in found), "same_title_groups": same_title,
            "by_category": by_cat, "list": found}


# ---- --pairs -------------------------------------------------------------------------------------------------

PAIR_EVENTS = ("duplicate_seen", "duplicate_better", "not_taken")


def pairs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every (candidate, match) a job looked at: n, decision, candidate, match and its signals."""
    out = []
    for e in events:
        if e.get("event") not in PAIR_EVENTS or not e.get("matches"):
            continue
        decision = e.get("decision") or (e.get("reason") if e["event"] == "not_taken" else
                                         f"duplicate_better:{e.get('replaces')}")
        for m in e["matches"]:
            out.append({"n": len(out) + 1, "event": e["event"], "decision": decision, "candidate": e["key"], **m})
    return out


def _photo(shop_dir: str, key: str) -> str | None:
    pid = key.split(":")[3]
    found = sorted(glob.glob(os.path.join(shop_dir, "collected", "*", "images", pid, "*-001-*")))
    return found[-1] if found else None


def draw_pairs(rows: list[dict[str, Any]], shop_dir: str, out: str, per_sheet: int = 30, thumb: int = 150,
               names: dict[str, str] | None = None) -> list[str]:
    """Sheets of numbered pairs (candidate | match, 5 pairs a line) and index.tsv into `out`."""
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(out, exist_ok=True)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    except OSError:
        font = ImageFont.load_default()
    columns, cell = 5, 2 * thumb + 12
    sheets = []
    for start in range(0, len(rows), per_sheet):
        chunk = rows[start:start + per_sheet]
        lines = (len(chunk) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * cell, lines * (thumb + 16)), "white")
        pen = ImageDraw.Draw(sheet)
        for i, row in enumerate(chunk):
            x, y = (i % columns) * cell, (i // columns) * (thumb + 16)
            for side, key in enumerate((row["candidate"], row["key"])):
                path, px = _photo(shop_dir, key), x + side * thumb
                try:
                    if not path:
                        raise OSError
                    with Image.open(path) as im:
                        im = im.convert("RGB")
                        im.thumbnail((thumb - 4, thumb - 4))
                        sheet.paste(im, (px + 2, y + 2))
                except OSError:
                    pen.text((px + 4, y + 4), "no photo", fill="gray", font=font)
            mark = "dup" if row.get("confirmed") else "-"
            pen.text((x + 3, y + thumb), f"{row['n']} {mark}", fill="red", font=font)
        path = os.path.join(out, f"pairs{start // per_sheet + 1}.jpg")
        sheet.save(path, quality=70)
        sheets.append(path)
    names = names or {}
    with open(os.path.join(out, "index.tsv"), "w", encoding="utf-8") as f:
        f.write("n\tdecision\tconfirmed\tfirst_photo\tphotos\tvariants\tcandidate\tmatch\tmatch_status\t"
                "candidate_title\tmatch_title\n")
        for r in rows:
            f.write(f"{r['n']}\t{r['decision']}\t{r.get('confirmed')}\t{r.get('first_photo')}\t{r.get('photos')}\t"
                    f"{r.get('variants_j')}\t{r['candidate']}\t{r['key']}\t{r.get('status')}\t"
                    f"{names.get(r['candidate'], '')}\t{names.get(r['key'], '')}\n")
    return sheets


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Duplicates: groups in the store (--report), a job's pairs (--pairs).")
    p.add_argument("--report", metavar="SHOP")
    p.add_argument("--pairs", metavar="SHOP")
    p.add_argument("--category")
    p.add_argument("--job")
    p.add_argument("--out")
    p.add_argument("--list", action="store_true", help="--report: every group, best first")
    p.add_argument("--shops-root", default=SHOPS_ROOT)
    p.add_argument("--jobs-root", default=JOBS_ROOT)
    a = p.parse_args(argv)
    if a.report:
        r = report(a.report, a.shops_root, a.category)
        print(f"{a.report}: {r['published']} published; {r['groups']} duplicate groups, {r['products']} products "
              f"({r['extra_copies']} extra copies); same title in several stores: {r['same_title_groups']} titles")
        for cat, c in sorted(r["by_category"].items()):
            print(f"  {cat}: {c['groups']} groups, {c['products']} products")
        if a.list:
            for g in r["list"]:
                print(f"{g[0]['category']}\t{g[0]['name']}")
                for i, e in enumerate(g):
                    print(f"  {'best' if i == 0 else '    '} {e['key']}\t{e['grade']}\t{e['reviews']} reviews\t"
                          f"{e['price']} KRW\t{e['variants']} variants")
        return 0
    if a.pairs:
        if not a.job:
            print("stop: --pairs needs --job")
            return 2
        events = _jsonl(os.path.join(a.jobs_root, a.job, "events.jsonl"))
        rows = pairs(events)
        shop_dir = os.path.join(a.shops_root, a.pairs)
        records = collected(a.pairs, a.shops_root)
        names = {k: entry(v)["name"] or "" for k, v in records.items()
                 if k in {r["candidate"] for r in rows} | {r["key"] for r in rows}}
        out = a.out or os.path.join(a.jobs_root, a.job, "pairs")
        sheets = draw_pairs(rows, shop_dir, out, names=names)
        print(f"{len(rows)} pairs ({sum(1 for r in rows if r.get('confirmed'))} confirmed); {len(sheets)} sheet(s) "
              f"and index.tsv in {out}")
        return 0
    p.error("--report SHOP or --pairs SHOP --job ID")
    return 2


if __name__ == "__main__":
    sys.exit(main())
