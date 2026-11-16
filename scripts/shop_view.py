"""One read-only view of a shop's products for the visual lenses (lens.py): what the pipeline's files say about each
product, joined by key. Local files only, nothing is sent anywhere, nothing is written.

Sources (all under scripts/output/shops/<shop>/): prepared/products.jsonl (titles, brand, variants, prices, photos),
translation/translated.jsonl (English title), placement/placements.jsonl (section), publish/published.jsonl (the
store: published / withdrawn, handle, admin link), collected/<run>/images/<id>/ (photos of a product never prepared).
A job's events (scripts/output/jobs/<job>/events.jsonl) give its order and its held / not taken products.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Any

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
JOBS_ROOT = os.path.join(SCRIPTS, "output", "jobs")


@dataclass
class Product:
    key: str
    pid: str
    channel: str
    category: str | None = None
    store: str | None = None                  # published, withdrawn, or None (never sent)
    reason: str | None = None                 # the withdrawal reason
    prepared: str | None = None               # ready, held, or None (not prepared)
    held: list[str] = field(default_factory=list)
    title_ko: str = ""
    title_en: str = ""
    brand: str | None = None                  # brand_ko
    brand_source: str | None = None
    brand_en: str | None = None
    price_krw: int | None = None              # the lowest variant price (Naver, KRW)
    variants: int = 0
    options: list[str] = field(default_factory=list)   # "name: v1 / v2 / ..." per option
    variant_values: list[list[str]] = field(default_factory=list)   # each variant's option values
    leaves: list[str] = field(default_factory=list)
    placement: str | None = None              # placed, held, unresolved ...
    handle: str = ""
    admin: str = ""
    link: str = ""
    photos: list[str] = field(default_factory=list)    # local paths, gallery order

    def row(self) -> dict[str, Any]:
        """The fields every lens writes to index.tsv / summary.json."""
        return {"product_id": self.pid, "category": self.category, "store": self.store, "price_krw": self.price_krw,
                "variants": self.variants, "brand": self.brand, "brand_source": self.brand_source,
                "leaves": self.leaves, "options": self.options, "title_ko": self.title_ko, "title_en": self.title_en,
                "handle": self.handle, "admin": self.admin, "link": self.link}


def jsonl(path: str) -> list[dict[str, Any]]:
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


def _last(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("key"):
            out[r["key"]] = r
    return out


def collected_photos(shop_dir: str, pid: str) -> list[str]:
    """A product's photos on disk from its newest collect run (by the run's timestamp), gallery order, one image
    shown once (the file name ends in its hash: <shop>-<id>-<position>-<hash>.<ext>)."""
    found = glob.glob(os.path.join(shop_dir, "collected", "*", "images", pid, "*-[0-9][0-9][0-9]-*"))
    if not found:
        return []
    run_of = lambda f: os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(f))))  # noqa: E731
    newest = max((run_of(f) for f in found), key=lambda r: (r.split("-")[-1], r))
    out, seen = [], set()
    for f in sorted(f for f in found if run_of(f) == newest):
        digest = os.path.splitext(os.path.basename(f))[0].rsplit("-", 1)[-1]
        if digest not in seen:
            seen.add(digest)
            out.append(f)
    return out


class ShopView:
    """key -> Product for every product the shop's files know (prepared, published or only collected)."""

    def __init__(self, shop: str, shops_root: str = SHOPS_ROOT):
        self.shop, self.dir = shop, os.path.join(shops_root, shop)
        self.prepared = _last(jsonl(os.path.join(self.dir, "prepared", "products.jsonl")))
        self.translated = _last(jsonl(os.path.join(self.dir, "translation", "translated.jsonl")))
        self.placed = _last(jsonl(os.path.join(self.dir, "placement", "placements.jsonl")))
        ledger = jsonl(os.path.join(self.dir, "publish", "published.jsonl"))
        self.ledger = _last(ledger)
        self.handles = {r["key"]: r for r in ledger if r.get("key") and r.get("handle")}   # a withdrawal row has none
        self._cache: dict[str, Product] = {}
        self.shops_root = shops_root
        self._collected: dict[str, Any] | None = None

    def collected_line(self, key: str) -> dict[str, Any] | None:
        """The product's newest collected line (read once for the shop, on first need: a held product's options)."""
        if self._collected is None:
            try:
                from run_transform import latest_lines
                self._collected = {k: v[2] for k, v in latest_lines(self.shop, None, self.shops_root).items()}
            except (OSError, ValueError):
                self._collected = {}
        return self._collected.get(key)

    def keys(self) -> list[str]:
        return list(dict.fromkeys([*self.prepared, *self.ledger]))

    def get(self, key: str) -> Product:
        if key in self._cache:
            return self._cache[key]
        parts = key.split(":")
        pid, channel = (parts[3], parts[2]) if len(parts) > 3 else (parts[-1], "")
        p = Product(key=key, pid=pid, channel=channel)
        rec = self.prepared.get(key)
        if rec:
            prod = rec.get("product") or {}
            p.prepared, p.held = rec.get("status"), list(rec.get("held") or [])
            p.category = (rec.get("source") or {}).get("category_id")
            p.link = (rec.get("source") or {}).get("link") or ""
            title = next((t for t in rec.get("texts") or [] if t.get("kind") == "title"), {})
            p.title_ko = " ".join((title.get("ko") or prod.get("title_ko") or "").split())
            en = (self.translated.get(key) or {}).get("en") or {}
            p.title_en = " ".join((en.get(title.get("id") or "") or "").split())
            p.brand, p.brand_source = prod.get("brand_ko"), prod.get("brand_source")
            p.brand_en = next((v for k, v in en.items() if k.startswith("brand:")), None)
            variants = prod.get("variants") or []
            prices = [v.get("price_krw") for v in variants if v.get("price_krw")]
            p.price_krw = min(prices) if prices else (prod.get("pricing") or {}).get("base_krw")
            p.variants = len(variants)
            p.variant_values = [list(v.get("options_ko") or []) for v in variants]
            p.options = [f"{o.get('name_ko')}: {' / '.join(o.get('values_ko') or [])}" for o in prod.get("options") or []]
            seen: set[str] = set()
            for i in sorted(prod.get("images") or [], key=lambda i: i.get("position", 0)):
                path = os.path.join(self.dir, i["file"]) if i.get("file") else None
                if path and os.path.exists(path) and (i.get("sha256") or path) not in seen:   # gone: left out;
                    seen.add(i.get("sha256") or path)                                         # one image twice: once
                    p.photos.append(path)
        if not p.photos:                       # never prepared, or its prepared photos gone from disk
            p.photos = collected_photos(self.dir, pid)
        if not p.options and (rec is None or p.prepared == "held"):
            line = self.collected_line(key) or {}   # a held product's prepared record carries no variants
            values = [[str(o) for o in v.get("options") or [v.get("name") or ""]]
                      for v in (line.get("variants") or {}).get("variants") or []]
            if values:
                p.variant_values = values
                p.variants = p.variants or len(values)
                p.options = ["variants: " + " / ".join(" ".join(v) for v in values)]
            if not p.title_ko:
                p.title_ko = " ".join(str((line.get("listing") or {}).get("name") or "").split())
        place = self.placed.get(key)
        if place:
            p.placement = place.get("status")
            p.leaves = [leaf.get("leaf") for leaf in place.get("leaves") or [] if leaf.get("leaf")]
        row = self.ledger.get(key)
        if row:
            p.store, p.reason = row.get("status"), row.get("reason")
            p.handle, p.admin = row.get("handle") or "", row.get("admin_url") or ""
            if not p.handle and key in self.handles:
                p.handle, p.admin = self.handles[key]["handle"], self.handles[key].get("admin_url") or ""
        self._cache[key] = p
        return p

    def select(self, category: str | None = None, leaf: str | None = None, store: str | None = "published",
               keys: list[str] | None = None) -> list[Product]:
        """Products by category, section leaf and store status ("published", "withdrawn", "any"), in the order of
        `keys` when given, else the prepared file's."""
        out = []
        for key in keys if keys is not None else self.keys():
            p = self.get(key)
            if category and p.category != category:
                continue
            if leaf and leaf not in p.leaves:
                continue
            if store and store != "any" and p.store != store:
                continue
            out.append(p)
        return out


def job_events(job: str, jobs_root: str = JOBS_ROOT) -> list[dict[str, Any]]:
    return jsonl(os.path.join(jobs_root, job, "events.jsonl"))


def job_keys(job: str, jobs_root: str = JOBS_ROOT, event: str | None = None) -> list[str]:
    """The keys a job touched (or those with `event`), first seen first."""
    return list(dict.fromkeys(e["key"] for e in job_events(job, jobs_root)
                              if e.get("key") and (event is None or e.get("event") == event)))
