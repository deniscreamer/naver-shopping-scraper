"""A contact sheet of published products for a quick look by eye (the owner, 2026-11-15): each product's first photo,
numbered, in sheets of 60 (10 x 6), plus index.tsv (number, key, product id, Korean title, handle, Shopify admin link).
Read only: local files, nothing is sent anywhere. Run by hand after a job, then name the numbers to withdraw
(`publish.py <shop> --withdraw <key> --reason ...`, the owner's call):

    .venv/bin/python scripts/review_grid.py fairwardgolf --job <job id>        # the job's published products
    .venv/bin/python scripts/review_grid.py fairwardgolf --category 50002787   # every published product of a category
        [--out DIR] [--per-sheet 60] [--thumb 150]

Writes <out>/sheet1.jpg ... and <out>/index.tsv (default out: the job folder's grid/, or the shop's grid-<category>/).
The drawing is sheet.py's; `lens.py section` is the general form (a section leaf, prices and titles on the cards,
summary.json): scripts/LENSES.md.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Any

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
JOBS_ROOT = os.path.join(SCRIPTS, "output", "jobs")
COLUMNS = 10


def _jsonl(path: str) -> list[dict[str, Any]]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass                                        # a torn last line
    return out


def published(shop_dir: str) -> dict[str, dict[str, Any]]:
    """key -> the ledger's last line, for keys whose last line is `published`."""
    last: dict[str, dict[str, Any]] = {}
    for row in _jsonl(os.path.join(shop_dir, "publish", "published.jsonl")):
        last[row.get("key")] = row
    return {k: r for k, r in last.items() if r.get("status") == "published"}


def items(shop: str, shops_root: str, keys: list[str] | None, category: str | None) -> list[dict[str, Any]]:
    """The products to show, in the order given (a job's) or the prepared file's: key, id, title, handle, admin,
    photo (the first collected photo, None when none is on disk)."""
    shop_dir = os.path.join(shops_root, shop)
    pub = published(shop_dir)
    prepared = {p["key"]: p for p in _jsonl(os.path.join(shop_dir, "prepared", "products.jsonl"))}
    order = keys if keys is not None else [k for k, p in prepared.items()
                                            if category is None or (p.get("source") or {}).get("category_id") == category]
    out = []
    for key in order:
        if key not in pub:
            continue
        pid = key.split(":")[3]
        p = prepared.get(key) or {}
        title = next((t.get("ko") for t in p.get("texts") or [] if t.get("kind") == "title"), "") or ""
        photos = sorted(glob.glob(os.path.join(shop_dir, "collected", "*", "images", pid, "*-001-*")))
        out.append({"key": key, "id": pid, "title": " ".join(title.split()), "handle": pub[key].get("handle") or "",
                    "admin": pub[key].get("admin_url") or "", "photo": photos[-1] if photos else None})
    return out


def draw(rows: list[dict[str, Any]], out: str, per_sheet: int = 60, thumb: int = 150) -> list[str]:
    """Sheets of numbered thumbnails (sheet.grid) and index.tsv into `out`. -> the sheet paths."""
    import sheet as S
    cards = [S.Card(n=n, key=row["key"], photos=[row["photo"]], mark=None if row["photo"] else "flag")
             for n, row in enumerate(rows, 1)]
    sheets = S.grid(cards, out, per_sheet=per_sheet, columns=COLUMNS, thumb=thumb, label_lines=0)
    with open(os.path.join(out, "index.tsv"), "w", encoding="utf-8") as f:
        f.write("n\tkey\tproduct_id\ttitle\thandle\tadmin\n")
        for n, row in enumerate(rows, 1):
            f.write(f"{n}\t{row['key']}\t{row['id']}\t{row['title']}\t{row['handle']}\t{row['admin']}\n")
    return sheets


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="A contact sheet of published products, numbered, for a look by eye.")
    p.add_argument("shop")
    p.add_argument("--job", help="only this job's published products, in its order")
    p.add_argument("--category", help="every published product of this Naver category")
    p.add_argument("--out")
    p.add_argument("--per-sheet", type=int, default=60)
    p.add_argument("--thumb", type=int, default=150)
    p.add_argument("--shops-root", default=SHOPS_ROOT)
    p.add_argument("--jobs-root", default=JOBS_ROOT)
    a = p.parse_args(argv)
    if not a.job and not a.category:
        print("stop: --job or --category")
        return 2
    keys = None
    if a.job:
        folder = os.path.join(a.jobs_root, a.job)
        keys = [e["key"] for e in _jsonl(os.path.join(folder, "events.jsonl")) if e.get("event") == "published"]
        keys = list(dict.fromkeys(keys))
    rows = items(a.shop, a.shops_root, keys, a.category)
    out = a.out or (os.path.join(a.jobs_root, a.job, "grid") if a.job
                    else os.path.join(a.shops_root, a.shop, f"grid-{a.category}"))
    sheets = draw(rows, out, a.per_sheet, a.thumb)
    print(f"{len(rows)} products, {sum(1 for r in rows if not r['photo'])} without a photo on disk; "
          f"{len(sheets)} sheet(s) and index.tsv in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
