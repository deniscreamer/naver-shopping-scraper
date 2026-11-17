"""Visual lenses: contact sheets of a shop's products drawn for one question each, for an AI agent (or the owner) to
look at by eye, then check by number. Read only, offline: local files in, JPGs and an index out; nothing is sent to
Naver, Shopify or any model, nothing in the pipeline's files changes. What to do with a finding (withdraw, fix a
rule, republish) stays the owner's word. When to use which lens: scripts/LENSES.md.

    .venv/bin/python scripts/lens.py <lens> <shop> [scope] [--out DIR]

    section   one photo per product of a section (--leaf), a category (--category) or a job (--job): is every one of
              them the section's product?
    price     a category's products cheapest first, outliers flagged: an accessory, a single club, a used set, a
              wrong price among the sets
    brand     products by brand and where the brand came from (--source none,title_word,...): is the vendor right?
    dupes     the store's duplicate groups (dedupe.py --report), kept copy first, members joined by title words only
              flagged: one product, or versions (colour edition, with or without its bag)?
    held      a job's held and not-taken products by reason, a duplicate beside its match: was the hold right?
    products  given products side by side, all their photos (keys, product ids, handles or links: shop_view.resolve;
              a ref of several products is left out with their keys listed): an ad hoc look

Every lens writes <out>/sheet1.jpg ... (numbered cards: red = flagged by the lens's rule, blue = look at it,
green = the kept copy), <out>/index.tsv and <out>/summary.json (the same cards as text: key, titles, price, brand,
section, options, links, the lens's own fields). Default out:
scripts/output/shops/<shop>/lens/<lens>[-<scope>][-<store>][-src-<sources>]/ (old sheets there are replaced).
The one file a lens writes besides its output: lens/reviewed.jsonl, by `dupes --versions` on the owner's word.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

import sheet as S
from shop_files import append_line
from shop_view import JOBS_ROOT, SHOPS_ROOT, Product, RefError, ShopView, job_events, job_keys, resolve

WEAK_BRAND = ("none", "title_word", "title_stem", "description_row", "origin", "images_text", "images_text_latin",
              "release_row")
LOW_Z, HIGH_Z = 2.0, 3.0              # robust z of log price (median, MAD) beyond which a card is red: cheap sooner
MAD_FLOOR = 0.05                      # log units: most prices equal (MAD 0) must not make a 1% step an outlier
FAR_LOW, FAR_HIGH = 0.1, 25.0         # red under x0.1 or beyond x25 of the median whatever the z (a two-humped category:
                                      # junior PING Prodi G sets are x16 of the junior median, a ₩5M placeholder x41)
CHEAPEST, DEAREST = 0.05, 0.02        # shares marked blue at the foot and the top even within the z: a wide category
                                      # (junior sets ₩10k-₩5M) has no outlier by z, yet singles, toys, placeholders
                                      # sit at its ends
REVIEWED = "reviewed.jsonl"           # lens/<file>: duplicate groups the owner judged versions (dupes --versions)
_SINGLE_TITLE = re.compile(r"(?i)또는\s*개별|및\s*개별|or\s+singles?\b|\bsingle\s+wedge\b|단품")


@dataclass
class Plan:
    """What a lens draws: its cards, the layout (grid or rows), the extra index columns, the summary meta."""
    lens: str
    cards: list[S.Card]
    layout: str = "grid"
    columns: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    photos: int = 4                   # rows layout: photos a line


BASE_COLUMNS = ["product_id", "category", "store", "price_krw", "variants", "brand", "brand_source", "leaves",
                "options", "title_en", "title_ko", "handle", "admin", "link"]


def _won(v: int | None) -> str:
    return f"₩{v:,}" if v else "₩?"


def _card(n: int, p: Product, lines: list[str], mark: str | None = None, group: str | None = None,
          photos: list[str | None] | None = None, **extra: Any) -> S.Card:
    return S.Card(n=n, key=p.key, photos=list(p.photos if photos is None else photos), lines=lines, mark=mark,
                  group=group, data={**p.row(), **extra})


def _title(p: Product) -> str:
    return p.title_en or p.title_ko


def single_looking(p: Product) -> bool:
    """The product may sell one club: its title says "or single" (또는 개별, 단품), or every variant's own words do
    (transform.single_club: one loft, 1pc, 단품, no set word)."""
    if _SINGLE_TITLE.search(f"{p.title_ko} {p.title_en}"):
        return True
    if not p.variant_values:
        return False
    from transform import single_club
    return all(single_club(v) for v in p.variant_values)


# ---- the lenses ----------------------------------------------------------------------------------------------

def section(view: ShopView, category: str | None = None, leaf: str | None = None, job: str | None = None,
            store: str = "published", jobs_root: str = JOBS_ROOT) -> Plan:
    """Red: no photo on disk; blue: the product may sell one club (single_looking)."""
    keys = job_keys(job, jobs_root, "published") if job else None
    products = view.select(category, leaf, store, keys)
    cards = []
    for n, p in enumerate(products, 1):
        single = single_looking(p)
        cards.append(_card(n, p, [f"{_won(p.price_krw)} v{p.variants}" + (" single?" if single else ""), _title(p)],
                           "flag" if not p.photos else ("info" if single else None), single_looking=single))
    return Plan("section", cards, columns=["single_looking"],
                meta={"category": category, "leaf": leaf, "job": job, "store": store,
                      "no_photo": sum(1 for p in products if not p.photos)})


def outliers(prices: list[int]) -> tuple[float | None, Callable[[int], float]]:
    """The median price and a robust z (log price against the median, scaled by the MAD, at least MAD_FLOOR) for a
    price; no median under 5 prices."""
    logs = [math.log(v) for v in prices if v and v > 0]
    if len(logs) < 5:
        return None, lambda v: 0.0
    mid = statistics.median(logs)
    mad = max(statistics.median(abs(x - mid) for x in logs) * 1.4826, MAD_FLOOR)
    return math.exp(mid), lambda v: (math.log(v) - mid) / mad if v and v > 0 else 0.0


def price(view: ShopView, category: str | None = None, leaf: str | None = None, store: str = "published",
          low: float = LOW_Z, high: float = HIGH_Z, cheapest: float = CHEAPEST, dearest: float = DEAREST) -> Plan:
    """Cheapest first, by the Naver price (KRW, the lowest variant: the source, not the store's USD price). Red: z
    below -low or above high, under x0.1 or beyond x25 of the median, or no price; blue: the cheapest and the dearest
    shares not already red. Under 5 prices there is no median: nothing is marked, read the ladder by eye."""
    products = sorted(view.select(category, leaf, store), key=lambda p: (p.price_krw or 0, p.key))
    median, score = outliers([p.price_krw for p in products if p.price_krw])
    foot = math.ceil(len(products) * cheapest) if median else 0
    top = len(products) - math.ceil(len(products) * dearest) if median else len(products)
    cards = []
    for n, p in enumerate(products, 1):
        s = score(p.price_krw) if p.price_krw else 0.0
        r = p.price_krw / median if median and p.price_krw else None
        far = r is not None and (r >= FAR_HIGH or r <= FAR_LOW)
        red = not p.price_krw or s < -low or s > high or far
        mark = "flag" if red else ("info" if n <= foot or n > top else None)
        ratio = f"x{r:.2f}" if r is not None else "x?"
        cards.append(_card(n, p, [f"{_won(p.price_krw)} {ratio}", _title(p)], mark, z=round(s, 2), of_median=ratio))
    return Plan("price", cards, columns=["z", "of_median"],
                meta={"category": category, "leaf": leaf, "store": store, "median_krw": round(median) if median else None,
                      "low_z": low, "high_z": high, "far": [FAR_LOW, FAR_HIGH], "cheapest_marked": foot,
                      "dearest_marked": len(products) - top,
                      "note": None if median else "fewer than 5 prices: no median, nothing marked"})


def brand_norm(text: str | None) -> str:
    """One spelling of a brand: casefold, no spaces or signs, no "golf" ("Yamato Golf", "yamato" -> "yamato")."""
    t = re.sub(r"[^0-9a-z가-힣]", "", (text or "").casefold())
    return re.sub(r"golf|골프", "", t) or t


def brand(view: ShopView, category: str | None = None, leaf: str | None = None, store: str = "published",
          sources: list[str] | None = None) -> Plan:
    """Weak sources first (red), then by brand. Blue: a brand written several ways among the products shown
    (yamato / yamato golf / 야마토 -> Yamato): one vendor in the store under several names."""
    products = [p for p in view.select(category, leaf, store)
                if not sources or (p.brand_source or "none").split(":")[0] in sources]
    vendor = {p.key: p.brand_en or p.brand or "" for p in products}
    spellings: dict[str, set[str]] = {}
    for p in products:
        for name in {p.brand_en, p.brand} - {None, ""}:
            spellings.setdefault(brand_norm(p.brand_en or p.brand), set()).add(vendor[p.key])
    split = {k: sorted(v) for k, v in spellings.items() if len(v) > 1}
    order = {s: i for i, s in enumerate(WEAK_BRAND)}
    products.sort(key=lambda p: (order.get((p.brand_source or "none").split(":")[0], len(order)),
                                 brand_norm(p.brand_en or p.brand), p.key))
    cards = []
    for n, p in enumerate(products, 1):
        src = (p.brand_source or "none").split(":")[0]
        norm = brand_norm(p.brand_en or p.brand)
        mark = "flag" if src in WEAK_BRAND else ("info" if norm in split else None)
        cards.append(_card(n, p, [f"{p.brand_en or p.brand or '—'} [{src}]", _title(p)], mark,
                           brand_spellings=split.get(norm)))
    return Plan("brand", cards, columns=["brand_spellings"],
                meta={"category": category, "leaf": leaf, "store": store, "sources": sources,
                      "weak_sources": list(WEAK_BRAND), "spellings": split})


def reviewed(view: ShopView) -> list[dict[str, Any]]:
    from shop_view import jsonl
    return jsonl(os.path.join(view.dir, "lens", REVIEWED))


def mark_versions(view: ShopView, keys: list[str], note: str, by: str = "owner") -> dict[str, Any]:
    """Record that these products are versions, not copies (the owner's word): the dupes lens shows their group grey
    and says so. -> the row written to lens/reviewed.jsonl (the lens's own file, no pipeline file)."""
    import datetime
    row = {"keys": sorted(set(keys)), "verdict": "versions", "note": note, "by": by,
           "at": datetime.date.today().isoformat()}
    path = os.path.join(view.dir, "lens", REVIEWED)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    append_line(path, json.dumps(row, ensure_ascii=False))
    return row


def dupes(view: ShopView, category: str | None = None, shops_root: str | None = None) -> Plan:
    """The store's duplicate groups, kept copy first. Green: the kept copy; red: joined by title words only (red wins
    over green: such a kept copy is red too, its line says keep); grey with "reviewed": a group the owner judged
    versions (lens/reviewed.jsonl)."""
    import dedupe
    rep = dedupe.report(view.shop, shops_root or view.shops_root, category)   # the view's shop, not the default
    judged = [set(r.get("keys") or []) for r in reviewed(view) if r.get("verdict") == "versions"]
    cards, n, seen = [], 0, []
    for g, group in enumerate(rep["list"], 1):
        weak = set(dedupe.title_only(group))
        keys = {e["key"] for e in group}
        done = any(keys <= j for j in judged)
        if done:
            seen.append(g)
        for i, e in enumerate(group):
            n += 1
            p = view.get(e["key"])
            role = "keep" if i == 0 else "copy"
            mark = None if done else ("flag" if e["key"] in weak else ("ok" if i == 0 else None))
            how = "reviewed: versions" if done else ("title words only" if e["key"] in weak else "photo/variants")
            cards.append(_card(n, p, [f"{role} {e['grade'] or '?'} r{e['reviews']}",
                                      f"{_won(e['price'])} v{e['variants']}", how, *p.options[:2], _title(p)],
                               mark, group=f"group {g}{' (reviewed: versions)' if done else ''}: {group[0]['name']}",
                               dup_group=g, role=role, title_only=e["key"] in weak, reviewed=done,
                               grade=e["grade"], reviews=e["reviews"]))
    return Plan("dupes", cards, layout="rows",
                columns=["dup_group", "role", "title_only", "reviewed", "grade", "reviews"],
                meta={"category": category, "published": rep["published"], "groups": rep["groups"],
                      "extra_copies": rep["extra_copies"], "title_only": rep["title_only"],
                      "same_title_groups": rep["same_title_groups"], "reviewed_groups": seen})


def held(view: ShopView, job: str, jobs_root: str = JOBS_ROOT) -> Plan:
    """A job's products that did not reach the store, by cause: the last word on each key that is a not_taken,
    failed or deferred event, or a held prepared / translated one (a product the job published is left out). A
    duplicate shows its match's photos on the right, both sides' options and the pair's signals; red when the match
    is no longer in the store (the live copy named when the withdrawal says it)."""
    last: dict[str, tuple[str, str]] = {}              # key -> (reason, event)
    for e in job_events(job, jobs_root):
        key, ev = e.get("key"), e.get("event")
        if not key:
            continue
        if ev == "published":
            last.pop(key, None)
        elif ev == "not_taken":
            last[key] = (str(e.get("reason") or "?"), ev)
        elif ev == "failed":
            last[key] = (f"failed {e.get('stage') or '?'}: {e.get('reason') or '?'}", ev)
        elif ev == "deferred":
            last[key] = (f"deferred: {e.get('reason') or '?'}", ev)
        elif ev in ("prepared", "translated") and e.get("status") == "held":
            last[key] = ("held: " + ", ".join(e.get("held") or []), ev) if e.get("held") else last.get(key, ("held", ev))
    published = set(job_keys(job, jobs_root, "published"))
    items = sorted(((r, ev, k) for k, (r, ev) in last.items() if k not in published),
                   key=lambda x: (_reason_group(x[0]), x[2]))
    cards = []
    for n, (reason, ev, key) in enumerate(items, 1):
        p = view.get(key)
        match = _match_key(reason)
        photos: list[str | None] = list(p.photos[:2]) or [None]
        lines = [p.title_ko or p.title_en or p.pid, f"{_won(p.price_krw)} v{p.variants}",
                 f"{ev}: {_short(reason)}", *p.options[:1]]
        extra: dict[str, Any] = {"reason": reason, "event": ev, "match": match}
        mark = None
        if match:
            m = view.get(match)
            photos = [*photos[:2], *[None] * (2 - len(photos[:2])), *m.photos[:2]]
            live = m.store == "published"
            lines.append(f"right: {m.pid} {m.store or 'not in store'}")
            found, path = (match, [match]) if live else live_copy(view, match)
            if not live:
                pids = [k.split(":")[-1] for k in path]
                lines.append(f"-> live: {pids[-1]}" + (f" via {','.join(pids[1:-1])}" if len(pids) > 2 else "")
                             if found else "-> no live copy" + (f" (ends at {pids[-1]})" if len(pids) > 1 else ""))
            lines.extend(f"right {o}" for o in m.options[:1])
            mark = "info" if live else "flag"
            extra.update(match_store=m.store, match_live=found, match_path=path, match_options=m.options,
                         signals=_signals(view, key, match))
        cards.append(_card(n, p, lines, mark, group=_reason_group(reason), photos=photos, **extra))
    return Plan("held", cards, layout="rows", columns=["event", "reason", "match", "match_store", "match_live", "signals"],
                meta={"job": job, "held": len(cards)})


_POINTS_AT = re.compile(r"^(?:replaced_by:|hold: copy of live )([a-z0-9_]+:naver:\d+:\d+)")


def live_copy(view: ShopView, key: str, limit: int = 20) -> tuple[str | None, list[str]]:
    """The live product a withdrawn one points at, and the path walked (the key first): its withdrawal reason
    "replaced_by:<key>" (dedupe) or "hold: copy of live <key>, ..." (a copy held as a draft, OWNER_RULES rule 2)
    names the next key, followed until a published one. 2026-11-16, the wedge-set review: 4 held cards named
    13379851400 as live, itself replaced_by 12918511112; 4 more said "no live copy" for the holds 12557420063 and
    13512885159 ("hold: copy of live ..."). (None, path) when the chain ends at a key not in the store, a reason
    that names no key, or a loop."""
    path = [key]
    while len(path) <= limit:
        p = view.get(path[-1])
        if p.store == "published" and len(path) > 1:     # the first key is the withdrawn match itself
            return path[-1], path
        m = _POINTS_AT.match(str(p.reason or "")) if p.store == "withdrawn" else None
        if not m or m.group(1) in path:
            return None, path
        path.append(m.group(1))
    return None, path


def _short(text: str) -> str:
    """A reason with its keys cut to product ids ("duplicate_of:fairwardgolf:naver:1100142898:136..." -> "...:136...")."""
    return re.sub(r"[a-z0-9_]+:naver:\d+:(\d+)", r"\1", str(text))


def _signals(view: ShopView, a: str, b: str) -> dict[str, Any] | None:
    """dedupe's signals of a pair from their collected lines (first photo, photo share, variants alike), or None."""
    la, lb = view.collected_line(a), view.collected_line(b)
    if not la or not lb:
        return None
    import dedupe
    s = dedupe.signals(dedupe.entry(la), dedupe.entry(lb))
    return {k: s[k] for k in ("first_photo", "photos", "variants")}


def _reason_group(reason: str) -> str:
    """The banner a reason goes under, by cause: the duplicate kind; a hold by its code whether the transform held it
    or the placement did ("placement held: single_only" and "held: single_only" -> "held: single_only"); the inside
    of "not ready to publish (...)"; "failed <stage>"; "deferred: <why>"; a screen code with its rule
    ("title:not_golf (a cable grip)" -> "title: not_golf")."""
    reason = " ".join(str(reason or "").split())
    for marker in ("duplicate_of_withdrawn", "duplicate_of"):
        if reason.startswith(marker) or f" {marker}" in reason:
            return marker
    inner = re.fullmatch(r"not ready to publish \((.+)\)", reason)
    if inner:
        reason = inner.group(1)
        return reason[len("placement "):] if reason.startswith("placement held") else reason
    if reason.startswith(("held", "deferred")):
        return reason
    if reason.startswith("failed"):
        return reason.split(":")[0]
    head = reason.split("(")[0].strip()
    code, _, rule = head.partition(":")
    return f"{code}: {rule.strip()}" if rule.strip() else (code or "?")


def _match_key(reason: str) -> str | None:
    for marker in ("duplicate_of_withdrawn:", "duplicate_of:"):
        if marker in reason:
            return reason.split(marker, 1)[1].split()[0].strip(")")
    return None


def products(view: ShopView, refs: list[str]) -> Plan:
    cards: list[S.Card] = []
    known = set(view.keys())
    for ref in refs:
        try:                                     # a key, product id, handle or link; several: none shown, the keys
            key = resolve(view, ref)             # listed to choose from (2026-11-16: no longer "the first")
        except RefError as e:
            print(f"   {e}; left out")
            continue
        if key not in known:
            print(f"   {ref}: not in the shop's files, left out")
            continue
        p = view.get(key)
        lines = [p.title_en, p.title_ko, f"{_won(p.price_krw)} v{p.variants} {p.store or 'not sent'}",
                 f"{p.brand_en or p.brand or '—'} [{p.brand_source or 'none'}]", ", ".join(p.leaves), *p.options[:3]]
        cards.append(_card(len(cards) + 1, p, [x for x in lines if x]))
    return Plan("products", cards, layout="rows", photos=6, meta={"refs": refs})


# ---- drawing and the command line ----------------------------------------------------------------------------

def render(plan: Plan, out: str) -> dict[str, Any]:
    """Draw the plan into `out` (old sheets there removed). -> {sheets, index, summary, cards, flagged, marked}."""
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "sheet*.jpg")):
        os.remove(old)
    if plan.layout == "rows":
        sheets = S.rows(plan.cards, out, photos=plan.photos)
    else:
        sheets = S.grid(plan.cards, out, label_lines=3)
    meta = {"lens": plan.lens, **plan.meta, "cards": len(plan.cards),
            "flagged": [c.n for c in plan.cards if c.mark == "flag"],
            "marked": [c.n for c in plan.cards if c.mark == "info"]}
    index, summary = S.write_index(plan.cards, out, [*plan.columns, *BASE_COLUMNS], meta)
    return {"sheets": sheets, "index": index, "summary": summary, "cards": len(plan.cards),
            "flagged": meta["flagged"], "marked": meta["marked"], "meta": meta}


def out_dir(shops_root: str, shop: str, lens: str, scope: str, store: str = "published",
            source: str | None = None) -> str:
    """lens/<lens>[-<scope>][-<store>][-src-<sources>]/: two looks at one scope never overwrite each other."""
    parts = [lens, scope, "" if store == "published" else store, f"src-{source.replace(',', '+')}" if source else ""]
    return os.path.join(shops_root, shop, "lens", "-".join(x for x in parts if x))


def _numbers(xs: list[int]) -> str:
    return f": {xs[:30]}{' ...' if len(xs) > 30 else ''}" if xs else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Visual lenses: contact sheets of a shop's products for a look by eye "
                                             "(scripts/LENSES.md).")
    ap.add_argument("lens", choices=["section", "price", "brand", "dupes", "held", "products"])
    ap.add_argument("shop")
    ap.add_argument("refs", nargs="*", help="products: keys, product ids, handles or links")
    ap.add_argument("--category")
    ap.add_argument("--leaf", help="a section leaf (placement), e.g. wedge-sets")
    ap.add_argument("--job")
    ap.add_argument("--store", default="published", choices=["published", "withdrawn", "any"])
    ap.add_argument("--source", help="brand: only these brand sources, comma-separated (none, title_word, ...)")
    ap.add_argument("--low", type=float, default=LOW_Z, help="price: flag a robust z below -LOW")
    ap.add_argument("--high", type=float, default=HIGH_Z, help="price: flag a robust z above HIGH")
    ap.add_argument("--versions", help="dupes: record these keys (comma-separated) as versions, not copies "
                                      "(the owner's word), with --note")
    ap.add_argument("--note", default="")
    ap.add_argument("--out")
    ap.add_argument("--shops-root", default=SHOPS_ROOT)
    ap.add_argument("--jobs-root", default=JOBS_ROOT)
    a = ap.parse_args(argv)
    view = ShopView(a.shop, a.shops_root)
    if a.lens == "section":
        if not (a.category or a.leaf or a.job):
            ap.error("section: --category, --leaf or --job")
        plan = section(view, a.category, a.leaf, a.job, a.store, a.jobs_root)
    elif a.lens == "price":
        if not (a.category or a.leaf):
            ap.error("price: --category or --leaf (one kind of product to compare)")
        plan = price(view, a.category, a.leaf, a.store, a.low, a.high)
    elif a.lens == "brand":
        plan = brand(view, a.category, a.leaf, a.store, a.source.split(",") if a.source else None)
    elif a.lens == "dupes":
        if a.versions:
            keys = [k.strip() for k in a.versions.split(",") if k.strip()]
            if len(keys) < 2 or not a.note:
                ap.error("dupes --versions: two or more keys and --note (whose word, why)")
            print(f"   recorded as versions: {mark_versions(view, keys, a.note)}")
        plan = dupes(view, a.category, a.shops_root)
    elif a.lens == "held":
        if not a.job:
            ap.error("held: --job")
        plan = held(view, a.job, a.jobs_root)
    else:
        if not a.refs:
            ap.error("products: one or more keys or product ids")
        plan = products(view, a.refs)
    scope = a.leaf or a.category or a.job or ("-".join(a.refs[:3]) if a.refs else "")
    out = a.out or out_dir(a.shops_root, a.shop, a.lens, scope, a.store, a.source if a.lens == "brand" else None)
    done = render(plan, out)
    print(f"{a.lens}: {done['cards']} cards, {len(done['flagged'])} flagged (red){_numbers(done['flagged'])}; "
          f"{len(done['marked'])} marked to look at (blue){_numbers(done['marked'])}")
    for k in ("note", "published", "same_title_groups", "reviewed_groups", "spellings"):
        if done["meta"].get(k):
            print(f"   {k}: {done['meta'][k]}")
    for path in done["sheets"]:
        print(f"   {path}")
    print(f"   {done['index']}\n   {done['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
