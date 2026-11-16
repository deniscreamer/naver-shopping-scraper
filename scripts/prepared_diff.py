"""What changed between two versions of a shop's prepared/products.jsonl, product by product (2026-11-16, the owner's
five tools). Local files only, nothing is sent anywhere; it writes nothing but --keys-out.

    .venv/bin/python scripts/prepared_diff.py old.jsonl new.jsonl                  # every product
    .venv/bin/python scripts/prepared_diff.py old.jsonl new.jsonl --fields status,brand --published-only
    .venv/bin/python scripts/prepared_diff.py old.jsonl new.jsonl --keys-out changed.txt   # -> --keys-file F
    .venv/bin/python scripts/run_transform.py fairwardgolf --diff                  # a snapshot before, this after

A product is compared by a few summary fields (FIELDS), each a short text:

    status    ready | held
    held      the hold codes with their detail ("code: detail")
    notes     the notes ("code: detail")
    brand     brand_ko (brand_source)
    title     title_ko
    price     the variants' price_krw, min-max (pricing.base_krw with no variant)
    variants  each variant's options ("a / b", "[sold out]" when not available)
    package   per package field (package.package_weight_g ...): the variants' values, "min-max (source cN)"
    images    the count and a digest of the photos' sha256 in order
    other     every other part of the record (source, texts, product.reviews, ...): the names of those that differ,
              once, in the new column (old "-"; a part on one side only: "(old only)" / "(new only)")

Output: a TSV on stdout, `key<TAB>change<TAB>field<TAB>old<TAB>new` a line, sorted by key then field. change is
added (field status, new = its status), removed (old = its status) or changed (one line a field that differs; for a
list field old / new hold only the items the other side lacks, joined by " | ", the first 10 then "(+N more)";
other: see above). Tabs and line ends in a value become spaces. One summary line on stderr. --json prints {"old",
"new", "counts", "products": [{"key", "change", "fields": {field: {"old", "new"}}}]} instead. --keys-out F writes
the keys of every listed product, one a line (shop_view's --keys-file reads it). --published-only keeps the products
whose last ledger row (<shops-root>/<shop>/publish/published.jsonl) is "published"; the shop is --shop, else the
new file's first record's; the summary line then says "(published only)". The ledger is the real shop's unless
--shops-root names the clone the two files come from. The keys file starts with a `# prepared_diff.py: N products`
comment line (`wc -l` counts it).

Both files are read with shop_files.read_jsonl, strict (prepared is written whole: a broken line is an error); a key
twice in a file: the last line counts. The ledger is read tail_ok, as the other readers do.

Exit codes: 0 no difference, 1 differences listed, 2 a file is missing or broken, or a bad flag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Iterable

from shop_files import LedgerError, read_jsonl
from shop_view import SHOPS_ROOT, cell as _clean, write_keys as _write_keys      # one TSV cell, one keys file

FIELDS = ("status", "held", "notes", "brand", "title", "price", "variants", "package", "images", "other")
LIST_FIELDS = {"held", "notes", "variants", "other"}
_SUMMARISED = {"status", "held", "notes", "product"}                       # top-level keys a field covers
_PRODUCT_SUMMARISED = {"brand_ko", "brand_source", "title_ko", "variants", "images"}
_VARIANT_SUMMARISED = {"options_ko", "available", "price_krw", "package"}
SHOWN = 10                                   # list items shown a side, then "(+N more)"

Summary = dict[str, Any]                     # field -> str (scalar fields), list[str] (list fields), dict (package)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def _items(rows: Any) -> list[str]:
    return [_clean(f"{r.get('code')}: {r.get('detail')}" if r.get("detail") else r.get("code"))
            for r in rows or [] if isinstance(r, dict)]


def _span(values: Iterable[Any]) -> str:
    got = [v for v in values if isinstance(v, (int, float))]
    if not got:
        return ""
    return f"{min(got)}" if min(got) == max(got) else f"{min(got)}-{max(got)}"


def _package_value(field: Any) -> str:
    if not isinstance(field, dict):
        return _clean(field)
    v = field.get("value")
    value = _span([v.get("min"), v.get("max")]) if isinstance(v, dict) else _clean(v)
    how = " ".join(x for x in (_clean(field.get("source")),
                              f"c{field['confidence']}" if field.get("confidence") is not None else "") if x)
    return f"{value or '-'} ({how})" if how else value or "-"


def summary(record: dict[str, Any]) -> Summary:
    """The record's FIELDS, each a short comparable text (a list for LIST_FIELDS, field -> text for package)."""
    product = record.get("product") or {}
    variants = [v for v in product.get("variants") or [] if isinstance(v, dict)]
    package: dict[str, list[str]] = {}
    for v in variants:
        for name, value in sorted((v.get("package") or {}).items()):
            text = _package_value(value)
            if text not in package.setdefault(name, []):
                package[name].append(text)
    other = {f"{k}": _digest(v) for k, v in record.items() if k not in _SUMMARISED}
    other.update({f"product.{k}": _digest(v) for k, v in product.items() if k not in _PRODUCT_SUMMARISED})
    rest = [{k: x for k, x in v.items() if k not in _VARIANT_SUMMARISED} for v in variants]
    if any(rest):
        other["product.variants (sku, ids, ...)"] = _digest(rest)
    images = [i.get("sha256") if isinstance(i, dict) else i for i in product.get("images") or []]
    brand = _clean(product.get("brand_ko")) or "-"
    return {
        "status": _clean(record.get("status")),
        "held": _items(record.get("held")),
        "notes": _items(record.get("notes")),
        "brand": f"{brand} ({product['brand_source']})" if product.get("brand_source") else brand,
        "title": _clean(product.get("title_ko")),
        "price": _span(v.get("price_krw") for v in variants) if variants
        else _clean((product.get("pricing") or {}).get("base_krw")),
        "variants": [(" / ".join(_clean(o) for o in v.get("options_ko") or []) or "(no option)")
                     + ("" if v.get("available", True) else " [sold out]") for v in variants],
        "package": {k: ", ".join(v) for k, v in package.items()},
        "images": f"{len(images)} ({_digest(images)})" if images else "0",
        "other": [f"{k}={v}" for k, v in sorted(other.items())],
    }


def _only(a: list[str], b: list[str]) -> list[str]:
    """Items of a not in b, a repeated item counted (two equal notes and one left: one listed)."""
    left = list(b)
    out = []
    for x in a:
        if x in left:
            left.remove(x)
        else:
            out.append(x)
    return out


def _joined(items: list[str]) -> str:
    shown = items[:SHOWN]
    return " | ".join(shown + ([f"(+{len(items) - SHOWN} more)"] if len(items) > SHOWN else []))


def compare(old: Summary, new: Summary, fields: Iterable[str] = FIELDS) -> dict[str, dict[str, str]]:
    """field -> {"old", "new"} for each field that differs (package: one entry a package field, package.<name>)."""
    out: dict[str, dict[str, str]] = {}
    for f in fields:
        a, b = old.get(f), new.get(f)
        if f == "package":
            pa, pb = a or {}, b or {}
            for name in sorted(set(pa) | set(pb)):
                if pa.get(name) != pb.get(name):
                    out[f"package.{name}"] = {"old": pa.get(name, "-"), "new": pb.get(name, "-")}
        elif f == "other":
            if a != b:
                da, db = dict(x.split("=", 1) for x in a or []), dict(x.split("=", 1) for x in b or [])
                names = sorted(k for k in set(da) | set(db) if da.get(k) != db.get(k))
                out[f] = {"old": "", "new": " | ".join(k + ("" if k in da and k in db else
                                                             " (old only)" if k in da else " (new only)")
                                                         for k in names)}
        elif f in LIST_FIELDS:
            if a != b:
                gone, came = _only(a or [], b or []), _only(b or [], a or [])
                if not gone and not came:                         # the same items, another order
                    gone, came = ["(order)"], ["(order)"]
                out[f] = {"old": _joined(gone), "new": _joined(came)}
        elif a != b:
            out[f] = {"old": a or "-", "new": b or "-"}
    return out


def summaries(path: str) -> dict[str, Summary]:
    """key -> summary() of a prepared file (shop_files.read_jsonl, strict; the last line of a key counts).
    FileNotFoundError when the file is not there (read_jsonl would say [] and every product would look added)."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return summaries_of(read_jsonl(path))


def summaries_of(records: Iterable[Any]) -> dict[str, Summary]:
    out: dict[str, Summary] = {}
    for r in records:
        if isinstance(r, dict) and r.get("key"):
            out[r["key"]] = summary(r)
    return out


def published_keys(shop: str, shops_root: str = SHOPS_ROOT) -> set[str]:
    """The keys whose last ledger row is "published" (live or a draft in the store, not withdrawn)."""
    last: dict[str, str] = {}
    for row in read_jsonl(os.path.join(shops_root, shop, "publish", "published.jsonl"), tail_ok=True):
        if isinstance(row, dict) and row.get("key"):
            last[row["key"]] = row.get("status") or ""
    return {k for k, s in last.items() if s == "published"}


def diff(old: dict[str, Summary], new: dict[str, Summary], fields: Iterable[str] = FIELDS,
         only: set[str] | None = None) -> list[dict[str, Any]]:
    """[{"key", "change": added|removed|changed, "fields": {field: {"old", "new"}}}] sorted by key; `only`: these
    keys alone (--published-only)."""
    fields = list(fields)
    out: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        if only is not None and key not in only:
            continue
        if key not in old:
            out.append({"key": key, "change": "added", "fields": {"status": {"old": "-", "new": new[key]["status"]}}})
        elif key not in new:
            out.append({"key": key, "change": "removed",
                        "fields": {"status": {"old": old[key]["status"], "new": "-"}}})
        else:
            got = compare(old[key], new[key], fields)
            if got:
                out.append({"key": key, "change": "changed", "fields": got})
    return out


def tsv_lines(products: list[dict[str, Any]]) -> list[str]:
    return ["\t".join([p["key"], p["change"], f, _clean(v["old"]) or "-", _clean(v["new"]) or "-"])
            for p in products for f, v in sorted(p["fields"].items())]


def counts(old: dict[str, Summary], new: dict[str, Summary], products: list[dict[str, Any]],
           only: set[str] | None = None) -> dict[str, Any]:
    by_field: dict[str, int] = {}
    for p in products:
        if p["change"] == "changed":
            for f in p["fields"]:
                name = f.split(".")[0]
                by_field[name] = by_field.get(name, 0) + 1
    seen = [k for k in set(old) | set(new) if only is None or k in only]
    changes = [p["change"] for p in products]
    return {"old": len(old), "new": len(new), "compared": len(seen), "published_only": only is not None,
            "added": changes.count("added"),
            "removed": changes.count("removed"), "changed": changes.count("changed"),
            "same": len(seen) - len(products), "by_field": dict(sorted(by_field.items()))}


def summary_line(c: dict[str, Any]) -> str:
    fields = ", ".join(f"{k} {v}" for k, v in c["by_field"].items())
    return (f"{c['old']} old, {c['new']} new, {c['compared']} compared"
            + (" (published only)" if c.get("published_only") else "")
            + f": {c['added']} added, {c['removed']} removed, "
            f"{c['changed']} changed" + (f" ({fields})" if fields else "") + f", {c['same']} the same")


def write_keys(path: str, products: list[dict[str, Any]]) -> None:
    _write_keys(path, [p["key"] for p in products], "prepared_diff.py")



def _fields(text: str | None) -> list[str]:
    if not text:
        return list(FIELDS)
    got = [x.strip() for x in text.split(",") if x.strip()]
    bad = [x for x in got if x not in FIELDS]
    if bad or not got:
        raise ValueError(f"--fields: unknown {', '.join(bad) or '(empty)'}; known: {', '.join(FIELDS)}")
    return got


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="What changed between two prepared/products.jsonl files, read only.")
    ap.add_argument("old", help="the earlier prepared/products.jsonl (a copy)")
    ap.add_argument("new", help="the later one")
    ap.add_argument("--fields", help=f"compare these alone, comma separated ({','.join(FIELDS)})")
    ap.add_argument("--shop", help="the shop for --published-only (default: the new file's first record's)")
    ap.add_argument("--shops-root", default=SHOPS_ROOT, help="the folder holding the shops (default "
                    "scripts/output/shops)")
    ap.add_argument("--published-only", action="store_true", help="only products whose last ledger row is "
                    "published")
    ap.add_argument("--keys-out", metavar="F", help="write the listed products' keys, one a line")
    ap.add_argument("--json", action="store_true", help="one JSON object instead of the TSV")
    args = ap.parse_args(argv)
    try:
        fields = _fields(args.fields)
    except ValueError as e:
        print(f"prepared_diff: {e}", file=sys.stderr)
        return 2
    try:
        old = summaries(args.old)
        new_rows = read_jsonl(args.new) if os.path.exists(args.new) else None
        if new_rows is None:
            raise FileNotFoundError(args.new)
        new = summaries_of(new_rows)
        shop = args.shop or next((r.get("shop") for r in new_rows if isinstance(r, dict) and r.get("shop")), None)
        del new_rows
        only = None
        if args.published_only:
            if not shop:
                print("prepared_diff: --published-only needs --shop (the new file names none)", file=sys.stderr)
                return 2
            only = published_keys(shop, args.shops_root)
    except FileNotFoundError as e:
        print(f"prepared_diff: no file {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    except LedgerError as e:
        print(f"prepared_diff: {e}", file=sys.stderr)
        return 2
    products = diff(old, new, fields, only)
    c = counts(old, new, products, only)
    if args.keys_out:
        write_keys(args.keys_out, products)
    if args.json:
        print(json.dumps({"old": args.old, "new": args.new, "counts": c, "products": products}, ensure_ascii=False,
                         indent=1))
    else:
        for line in tsv_lines(products):
            print(line)
    print(f"prepared_diff: {summary_line(c)}", file=sys.stderr)
    return 1 if products else 0


if __name__ == "__main__":
    sys.exit(main())
