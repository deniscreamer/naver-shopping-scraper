"""One read-only view of a shop's products for the visual lenses (lens.py): what the pipeline's files say about each
product, joined by key. Local files only, nothing is sent anywhere, nothing is written.

Sources (all under scripts/output/shops/<shop>/): prepared/products.jsonl (titles, brand, variants, prices, photos),
translation/translated.jsonl (English title), placement/placements.jsonl (section), publish/published.jsonl (the
store: published / withdrawn, handle, admin link), collected/<run>/images/<id>/ (photos of a product never prepared).
A job's events (scripts/output/jobs/<job>/events.jsonl) give its order and its held / not taken products.

Naming a product (2026-11-16, the owner's five tools): resolve(view_or_shop, ref) -> its key, for every tool that takes
a product. A ref is a full key (shop:source:channel:id, returned as it is, known or not: as before), a Naver product
id, a Shopify handle (any the ledger ever had), a link (the store's /products/<handle>, the admin's
/products/<number>, a Naver product page) or a gid://shopify/Product/<number>. No match or several is a RefError
that names the candidates (never "the first"). selected_keys() joins refs, a keys file and a job's keys;
add_ref_flags() / keys_from_args() give a CLI --keys-file F and --job ID [--event E].

    .venv/bin/python scripts/shop_view.py key <shop> <ref> [<ref> ...] [--keys-file F] [--job ID [--event E]] [--json]

prints `ref<TAB>key` a line (a key from --keys-file / --job: the key twice). Exit codes: 0 every ref resolved, 1 one
or more did not (each on stderr as `<ref>: ...`, the others still printed), 2 usage (argparse).

The shop's files by hand (2026-11-16), read only (only `query --keys-out F` writes, that file). Every command takes
--shops-root DIR and --json; show, query and history take --keys-file F and --job ID [--event E] too:

    shop_view.py show <shop> <ref...> [--fields f,g] [--raw KIND [--path a.b.0]]
    shop_view.py query <shop> [--where F=V|F!=V ...] [--category C] [--leaf L] [--store S] [--grep RE [--in f,g]]
                               [--fields f,g] [--count-by F] [--keys-out F]
    shop_view.py ledger <shop> [--status S] [--since ISO] [--count-by event|status|store_status|key|day|reason_code]
    shop_view.py history <shop> <ref...>
    shop_view.py check <shop> plan.tsv

- show: a block a product (`== key`, then `field<TAB>value`); with --fields a TSV with a header; --raw the last
  record of one file (prepared, translated, placement, ledger, description, collected: the newest run's line) as
  JSON, a string bare; --path a part of it. The fields (FIELDS): key pid channel category prepared held notes brand
  brand_source brand_en title (English, else Korean) title_ko title_en price_krw variants translation description
  placement leaves state store store_status reason handle admin link at. A list prints comma-joined.
- state: none (never sent), withdrawn, draft (store_status DRAFT), active (ACTIVE, or an old row with none);
  --store published = draft or active, any = all (query's default).
- query: `key<TAB>prepared<TAB>placement<TAB>state<TAB>handle<TAB>title` a product (or --fields), every product the
  files know (prepared first); --where on any field, case ignored (status = prepared, note = notes, leaf = leaves; a
  list: V among its items; `F=` empty); --count-by: `value<TAB>count`, most first, "(none)" for empty.
- ledger: `at<TAB>event<TAB>key<TAB>status<TAB>store_status<TAB>handle<TAB>reason` a row, file order; at = the row's
  time (an activation's `activated`); event = created, sent (an update), withdrawn, restored, activated; --status
  matches the status, the store status or the event, case ignored; --since compares UTC times (2026-11-16[T08:30]).
- history: `== key (state; prepared S)` then its ledger rows (without key), or `(never sent)`.
- check: a plan line is `ref<TAB>status[<TAB>reason]` (# comments, a first line starting `key` is a header); status
  is a state (published, withdrawn, draft, active, none, any) or ready / held (the prepared status); reason, when
  given, must start the ledger's reason (case ignored). Prints `ok|FAIL<TAB>key<TAB>want<TAB>got<TAB>want reason<TAB>
  got reason`, or `ERROR<TAB>ref<TAB>message`; a count on stderr.

Exit codes (show, query, ledger, history, check): 0 done (query and ledger also when nothing matched); 1 a ref did
not resolve or a --raw record / --path is missing (on stderr, the rest printed), check: a line not ok; 2 usage (bad
flag, field, --where, --since, regex, no shop folder, unreadable plan); a shop file with a broken line (LedgerError,
named on stderr; the ledger's and descriptions' cut-off last line is only a warning, as everywhere) is 1 too.

The same for every read tool of the five (shop_view, job.py report / where, shopify_catalog): 0 done, 1 a ref that
names no product or several (the candidates named, never "the first") or a broken shop file, 2 usage; a command's
own codes come after 2. The commands that act (publish, translate, describe, store_diff, reprice) refuse such a ref
before anything is done, as a usage error (exit 2). prepared_diff.py keeps diff's codes (1 = differences).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from shop_files import LedgerError, read_jsonl

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

    def __init__(self, shop: str, shops_root: str = SHOPS_ROOT, strict: bool = False):
        """`strict` (the show / query / ledger commands): read as the rest of the code does (shop_files.read_jsonl:
        a bad line is a LedgerError, the ledger forgives a cut-off last line); without it a bad line is skipped."""
        self.shop, self.dir = shop, os.path.join(shops_root, shop)
        read = (lambda p: read_jsonl(p, tail_ok=p.endswith("published.jsonl"))) if strict else jsonl
        self.prepared = _last(read(os.path.join(self.dir, "prepared", "products.jsonl")))
        self.translated = _last(read(os.path.join(self.dir, "translation", "translated.jsonl")))
        self.placed = _last(read(os.path.join(self.dir, "placement", "placements.jsonl")))
        ledger = read(os.path.join(self.dir, "publish", "published.jsonl"))
        self.ledger_rows: list[dict[str, Any]] = ledger
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
            title: dict[str, Any] = next((t for t in rec.get("texts") or [] if t.get("kind") == "title"), {})
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


# ==== naming a product: resolve, selected_keys, the shared CLI flags (2026-11-16) ============================

class RefError(ValueError):
    """A ref that names no product of the shop, or several (the message lists them), or a bad keys file / job."""


def is_key(ref: str) -> bool:
    """A full key: shop:source:channel:id, four parts, none empty."""
    parts = ref.split(":")
    return len(parts) == 4 and all(parts)


_ADMIN = re.compile(r"/store/[^/]+/products/(\d+)")          # admin.shopify.com/store/<store>/products/<number>
_GID = re.compile(r"^gid://shopify/Product/(\d+)$")
_PRODUCTS = re.compile(r"/products/([^/?#]+)")                # the store: /products/<handle>; Naver: /products/<id>


def store_number(ref: str) -> str | None:
    """The Shopify product number of a gid or an admin link, else None (shopify_catalog show uses it too)."""
    ref = ref.strip()
    m = _GID.match(ref)
    if m:
        return m.group(1)
    if "admin.shopify.com" in ref:
        m = _ADMIN.search(unquote(urlparse(ref if "://" in ref else "https://" + ref).path))
        return m.group(1) if m else None
    return None


class RefIndex:
    """What a ref can match, from the shop's files: every key (prepared, translated, placed, the ledger), the Naver
    product id of each, every handle and Shopify product number the ledger ever had for it."""

    def __init__(self, keys: Iterable[str], ledger: list[dict[str, Any]], shop: str = ""):
        self.shop = shop
        known = dict.fromkeys(keys)
        self.by_pid: dict[str, set[str]] = {}
        self.by_handle: dict[str, set[str]] = {}
        self.by_number: dict[str, set[str]] = {}
        self.handle: dict[str, str] = {}                     # key -> its last handle
        self.status: dict[str, str] = {}                     # key -> its last ledger status (+ store_status)
        for row in ledger:
            k = row.get("key")
            if not k:
                continue
            known.setdefault(k)
            if row.get("handle"):
                self.by_handle.setdefault(row["handle"], set()).add(k)
                self.handle[k] = row["handle"]
            number = str(row.get("product_id") or "").rsplit("/", 1)[-1]
            if number.isdigit():
                self.by_number.setdefault(number, set()).add(k)
            self.status[k] = row.get("status", "") + (f" {row['store_status']}" if row.get("store_status") else "")
        self.keys = list(known)
        self.known = set(known)
        for k in self.keys:
            self.by_pid.setdefault(k.split(":")[-1], set()).add(k)

    @classmethod
    def of_shop(cls, shop: str, shops_root: str = SHOPS_ROOT) -> "RefIndex":
        d = os.path.join(shops_root, shop)
        keys: list[str] = []
        for rel in ("prepared/products.jsonl", "translation/translated.jsonl", "placement/placements.jsonl"):
            keys += [r["key"] for r in read_jsonl(os.path.join(d, rel)) if r.get("key")]
        return cls(keys, read_jsonl(os.path.join(d, "publish", "published.jsonl"), tail_ok=True), shop)

    @classmethod
    def of_view(cls, view: "ShopView") -> "RefIndex":
        ledger = read_jsonl(os.path.join(view.dir, "publish", "published.jsonl"), tail_ok=True)
        return cls([*view.prepared, *view.translated, *view.placed], ledger, view.shop)

    def matches(self, ref: str) -> set[str]:
        """The keys `ref` names (a full key is not looked up here: resolve returns it as it is)."""
        number = store_number(ref)
        if number:
            return set(self.by_number.get(number, ()))
        if "://" in ref or ref.startswith(("www.", "admin.shopify.com", "smartstore.", "brand.naver")):
            url = urlparse(ref if "://" in ref else "https://" + ref)
            host, path = url.netloc.lower(), unquote(url.path)
            admin = _ADMIN.search(path)
            if host.endswith("shopify.com") and admin:
                return set(self.by_number.get(admin.group(1), ()))
            m = _PRODUCTS.search(path)
            if not m:
                raise RefError(f"{ref}: a link without /products/<handle or id>")
            if host.endswith("naver.com"):
                return set(self.by_pid.get(m.group(1), ()))
            return set(self.by_handle.get(m.group(1), ()))
        if ref.isdigit():                    # a Naver product id; a Shopify product number too (13 digits today)
            return set(self.by_pid.get(ref, ())) | set(self.by_number.get(ref, ()))
        return set(self.by_handle.get(ref, ()))

    def describe(self, key: str) -> str:
        return f"{key} ({self.status.get(key) or 'not sent'}{', ' + self.handle[key] if key in self.handle else ''})"


def _index(view_or_shop: "ShopView | RefIndex | str", shops_root: str) -> RefIndex:
    if isinstance(view_or_shop, RefIndex):
        return view_or_shop
    if isinstance(view_or_shop, ShopView):
        if getattr(view_or_shop, "_refs", None) is None:
            view_or_shop._refs = RefIndex.of_view(view_or_shop)        # type: ignore[attr-defined]
        return view_or_shop._refs                                       # type: ignore[attr-defined]
    return RefIndex.of_shop(view_or_shop, shops_root)


def resolve(view_or_shop: "ShopView | RefIndex | str", ref: str, shops_root: str = SHOPS_ROOT) -> str:
    """The key `ref` names (see the module's docstring); RefError when it names none or several."""
    ref = ref.strip()
    if is_key(ref):
        return ref
    if not ref:
        raise RefError("an empty ref")
    index = _index(view_or_shop, shops_root)
    if ref in index.known:                      # a key of the files' own spelling (a test's "k1" too)
        return ref
    found = sorted(index.matches(ref))
    if len(found) == 1:
        return found[0]
    if not found:
        raise RefError(f"{ref}: no product of {index.shop or 'the shop'} matches (a key, a Naver product id, "
                       f"a handle, a store / admin / Naver link)")
    raise RefError(f"{ref}: {len(found)} products match, name one by its key: "
                   + "; ".join(index.describe(k) for k in found))


def write_keys(path: str, keys: Iterable[str], header: str | None = None) -> None:
    """A keys file read_refs (--keys-file) reads back: `# <header>: N products`, then one key a line."""
    keys = list(keys)
    with open(path, "w", encoding="utf-8") as f:
        f.write((f"# {header}: {len(keys)} products\n" if header else "") + "".join(k + "\n" for k in keys))


def iso_time(text: str) -> datetime:
    """An ISO date or time as an aware datetime (no zone: UTC); ValueError when it is not one (--since)."""
    t = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def read_refs(path: str) -> list[str]:
    """A keys file: one ref a line, its first word (a TSV whose first column is the key works); blank lines and
    lines starting with # left out."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise RefError(f"--keys-file {path}: {e.strerror or e}") from None
    return [x.split()[0] for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]


def selected_keys(view_or_shop: "ShopView | RefIndex | str", refs: Iterable[str] = (), keys_file: str | None = None,
                  job: str | None = None, event: str | None = None, shops_root: str = SHOPS_ROOT,
                  jobs_root: str = JOBS_ROOT) -> list[str]:
    """The keys of `refs`, then of the keys file's refs, then the job's keys (with `event`: those with that event),
    each once, first seen first. Every ref that does not resolve is reported in one RefError (nothing selected)."""
    if event and not job:
        raise RefError("--event needs --job")
    wanted = [*refs, *(read_refs(keys_file) if keys_file else [])]
    out, errors = [], []
    index: RefIndex | None = None
    for ref in wanted:
        if is_key(ref.strip()):
            out.append(ref.strip())
            continue
        try:
            index = index or _index(view_or_shop, shops_root)
            out.append(resolve(index, ref))
        except RefError as e:
            errors.append(str(e))
    if job:
        if not os.path.exists(os.path.join(jobs_root, job, "events.jsonl")):
            errors.append(f"--job {job}: no {os.path.join(jobs_root, job, 'events.jsonl')}")
        else:
            got = job_keys(job, jobs_root, event)
            if not got:
                errors.append(f"--job {job}: no key{' with event ' + event if event else ''}")
            out += got
    if errors:
        raise RefError("\n".join(errors))
    return list(dict.fromkeys(out))


def add_ref_flags(ap: argparse.ArgumentParser) -> None:
    """--keys-file F and --job ID [--event E]: more products for the command, besides its refs."""
    ap.add_argument("--keys-file", help="products from a file: one ref a line (key, product id, handle, link), "
                    "# comments")
    ap.add_argument("--job", dest="ref_job", metavar="ID", help="the products a job touched (its events.jsonl)")
    ap.add_argument("--event", dest="ref_event", metavar="E", help="with --job: only those with this event "
                    "(published, not_taken, ...)")
    ap.add_argument("--jobs-root", dest="ref_jobs_root", default=JOBS_ROOT, metavar="DIR",
                    help="the folder holding the jobs (default scripts/output/jobs)")


def selection_asked(args: argparse.Namespace) -> bool:
    return bool(args.keys_file or args.ref_job)


def keys_from_args(ap: argparse.ArgumentParser, args: argparse.Namespace, view_or_shop: "ShopView | RefIndex | str",
                   refs: Iterable[str], shops_root: str = SHOPS_ROOT) -> list[str]:
    """selected_keys over `refs` and the flags of add_ref_flags; a RefError, or nothing selected, ends the command
    (argparse's exit 2). Call it only when something was named (refs or selection_asked)."""
    try:
        keys = selected_keys(view_or_shop, [r for r in refs if r], args.keys_file, args.ref_job, args.ref_event,
                             shops_root, args.ref_jobs_root)
    except RefError as e:
        ap.error(str(e))
    if not keys:                       # an empty keys file must not widen the command to every product
        ap.error("no product selected (the keys file has no ref)")
    return keys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="A shop's products, read only.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    parsers: dict[str, argparse.ArgumentParser] = {}

    def command(name: str, help: str, refs: bool = False) -> argparse.ArgumentParser:
        p = parsers[name] = sub.add_parser(name, help=help)
        p.add_argument("shop")
        if refs:
            p.add_argument("refs", nargs="*")
        p.add_argument("--shops-root", default=SHOPS_ROOT)
        p.add_argument("--json", action="store_true")
        return p

    k = command("key", "each ref's key: ref<TAB>key", refs=True)
    add_ref_flags(k)
    s = command("show", "products' fields, or one file's record (--raw)", refs=True)
    s.add_argument("--fields", help="comma-separated fields (a TSV with a header): " + ",".join(FIELDS))
    s.add_argument("--raw", choices=RAW, help="that file's record of each product, as JSON")
    s.add_argument("--path", help="with --raw: only this part of it (a.b.0.c: keys, list positions)")
    add_ref_flags(s)
    q = command("query", "the products whose fields match: key<TAB>fields")
    q.add_argument("--where", action="append", default=[], metavar="F=V",
                   help="F=V or F!=V on a field (repeat: all must hold; a list field: V among its items; "
                   "F= : empty), e.g. status=held, held=single_only, note=brand_fallback, brand_source=title")
    q.add_argument("--category", help="the Naver category id")
    q.add_argument("--leaf", help="a section leaf the product is placed in")
    q.add_argument("--store", choices=STORES, default="any",
                   help="published (draft or active), withdrawn, draft, active, none (never sent), any (default)")
    q.add_argument("--grep", metavar="RE", help="a regular expression (any case) one of the --in fields matches")
    q.add_argument("--in", dest="grep_in", default=",".join(GREP_IN), help=f"fields for --grep ({','.join(GREP_IN)})")
    q.add_argument("--fields", help="the columns (default " + ",".join(QUERY_COLUMNS) + ")")
    q.add_argument("--count-by", metavar="FIELD", help="counts per value of FIELD instead of the rows")
    q.add_argument("--keys-out", metavar="F", help="also write the matching keys to F (a --keys-file)")
    add_ref_flags(q)
    lg = command("ledger", "the ledger's rows: at, event, key, status, store_status, handle, reason")
    lg.add_argument("--status", help="published, withdrawn, a store status (DRAFT, ACTIVE) or an event "
                    "(created, sent, restored, activated)")
    lg.add_argument("--since", metavar="ISO", help="rows at or after this UTC time (2026-11-16, 2026-11-16T08:30Z)")
    lg.add_argument("--count-by", metavar="FIELD", help="counts per value: " + ",".join(LEDGER_COUNT))
    h = command("history", "each product's ledger rows, oldest first", refs=True)
    add_ref_flags(h)
    c = command("check", "a plan (ref<TAB>status[<TAB>reason]) against the files: ok / FAIL a line")
    c.add_argument("plan")
    a, extra = ap.parse_known_args(argv)        # refs after the flags too (a subparser's positionals stop at a flag)
    if any(x.startswith("-") for x in extra) or (extra and not hasattr(a, "refs")):
        ap.error(f"unrecognized arguments: {' '.join(extra)}")
    if hasattr(a, "refs"):
        a.refs += extra
    p = parsers[a.cmd]
    if a.cmd != "key" and not os.path.isdir(os.path.join(a.shops_root, a.shop)):
        p.error(f"no shop folder {os.path.join(a.shops_root, a.shop)}")
    try:
        if a.cmd == "key":
            return _cmd_key(p, a)
        files = ShopFiles(a.shop, a.shops_root)
        run = {"show": _cmd_show, "query": _cmd_query, "ledger": _cmd_ledger, "history": _cmd_history,
               "check": _cmd_check}[a.cmd]
        return run(p, a, files)
    except LedgerError as e:
        print(f"shop_view: {e}", file=sys.stderr)
        return 1


def _cmd_key(ap: argparse.ArgumentParser, a: argparse.Namespace) -> int:
    if not (a.refs or selection_asked(a)):
        ap.error("key: one or more refs, --keys-file or --job")
    rows: list[dict[str, str]] = []
    index: RefIndex | None = None
    try:
        refs = [*a.refs, *(read_refs(a.keys_file) if a.keys_file else [])]
        extra = selected_keys(a.shop, (), None, a.ref_job, a.ref_event, a.shops_root, a.ref_jobs_root) \
            if a.ref_job else []
    except RefError as e:
        ap.error(str(e))
    for ref in refs:
        try:
            if not is_key(ref.strip()):
                index = index or RefIndex.of_shop(a.shop, a.shops_root)
            rows.append({"ref": ref, "key": resolve(index or a.shop, ref, a.shops_root)})
        except RefError as e:
            rows.append({"ref": ref, "error": str(e)})
    rows += [{"ref": key, "key": key} for key in extra]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            if "key" in r:
                print(f"{r['ref']}\t{r['key']}")
            else:
                print(r["error"], file=sys.stderr)
    return 1 if any("error" in r for r in rows) else 0


# ==== show / query / ledger / history / check: the shop's files by hand, read only (2026-11-16) ==============

FIELDS = ("key", "pid", "channel", "category", "prepared", "held", "notes", "brand", "brand_source", "brand_en",
          "title", "title_ko", "title_en", "price_krw", "variants", "translation", "description", "placement",
          "leaves", "state", "store", "store_status", "reason", "handle", "admin", "link", "at")
LIST_FIELDS = ("held", "notes", "leaves")
ALIASES = {"status": "prepared", "note": "notes", "leaf": "leaves"}      # --where status=held, note=CODE
RAW = ("prepared", "translated", "placement", "ledger", "description", "collected")
STORES = ("published", "withdrawn", "draft", "active", "none", "any")
GREP_IN = ("title_ko", "title_en", "brand", "brand_en", "handle")
QUERY_COLUMNS = ("key", "prepared", "placement", "state", "handle", "title")
LEDGER_COLUMNS = ("at", "event", "key", "status", "store_status", "handle", "reason")
LEDGER_COUNT = ("event", "status", "store_status", "key", "day", "reason_code")
PLAN_STATES = (*STORES, "ready", "held")


class ShopFiles:
    """A ShopView read strictly, plus the descriptions (describe.py's append-only file), on first need."""

    def __init__(self, shop: str, shops_root: str = SHOPS_ROOT):
        self.shop, self.shops_root = shop, shops_root
        self.view = ShopView(shop, shops_root, strict=True)
        self._descriptions: dict[str, dict[str, Any]] | None = None

    def descriptions(self) -> dict[str, dict[str, Any]]:
        if self._descriptions is None:
            self._descriptions = _last(read_jsonl(os.path.join(self.view.dir, "translation", "descriptions.jsonl"),
                                                  tail_ok=True))
        return self._descriptions

    def keys(self) -> list[str]:
        """Every key the files know: prepared first (its order), then translated, placed, the ledger."""
        v = self.view
        return list(dict.fromkeys([*v.prepared, *v.translated, *v.placed,
                                   *(r["key"] for r in v.ledger_rows if r.get("key"))]))

    def raw(self, kind: str, key: str) -> Any:
        v = self.view
        if kind == "collected":
            return v.collected_line(key)
        if kind == "description":
            return self.descriptions().get(key)
        return {"prepared": v.prepared, "translated": v.translated, "placement": v.placed,
                "ledger": v.ledger}[kind].get(key)


def row_time(row: dict[str, Any]) -> str:
    """When a ledger row happened: its `at`, or its `activated` when later (an activation keeps the row's `at`)."""
    return max(str(row.get("at") or ""), str(row.get("activated") or ""))


def ledger_event(row: dict[str, Any]) -> str:
    """What a ledger row records: withdrawn, restored (digest "" and `restored`), activated (`activated` after `at`),
    created (a new store product) or sent (an update of one)."""
    if row.get("status") == "withdrawn":
        return "withdrawn"
    if row.get("restored") and row.get("digest") == "":
        return "restored"
    if row.get("activated") and str(row["activated"]) > str(row.get("at") or ""):
        return "activated"
    return "created" if row.get("created") else "sent"


def store_state(row: dict[str, Any] | None) -> str:
    """none (never sent), withdrawn, draft (store_status DRAFT) or active (ACTIVE, or the old rows with none)."""
    if not row:
        return "none"
    if row.get("status") == "withdrawn":
        return "withdrawn"
    return "draft" if row.get("store_status") == "DRAFT" else "active"


def state_matches(state: str, want: str) -> bool:
    return want == "any" or state == want or (want == "published" and state in ("draft", "active"))


def _codes(items: Any) -> list[str]:
    return [str(i.get("code")) if isinstance(i, dict) else str(i) for i in items or []]


def fields(files: ShopFiles, key: str) -> dict[str, Any]:
    """One product as flat fields (FIELDS), from the files' last row of each kind; no photo, no collected line read."""
    v = files.view
    rec = v.prepared.get(key) or {}
    prod, src = rec.get("product") or {}, rec.get("source") or {}
    title: dict[str, Any] = next((t for t in rec.get("texts") or [] if t.get("kind") == "title"), {})
    tr = v.translated.get(key) or {}
    en = tr.get("en") or {}
    place = v.placed.get(key) or {}
    row = v.ledger.get(key)
    sent = v.handles.get(key) or {}
    desc = files.descriptions().get(key) or {}
    variants = prod.get("variants") or []
    prices = [x.get("price_krw") for x in variants if x.get("price_krw")]
    parts = key.split(":")
    title_ko = " ".join((title.get("ko") or prod.get("title_ko") or "").split())
    title_en = " ".join((en.get(title.get("id") or "") or "").split())
    return {
        "key": key, "pid": parts[-1], "channel": parts[2] if len(parts) > 3 else "",
        "category": src.get("category_id"), "prepared": rec.get("status"),
        "held": _codes(rec.get("held")), "notes": _codes(rec.get("notes")),
        "brand": prod.get("brand_ko"), "brand_source": prod.get("brand_source"),
        "brand_en": next((x for k, x in en.items() if k.startswith("brand:")), None),
        "title": title_en or title_ko, "title_ko": title_ko, "title_en": title_en,
        "price_krw": min(prices) if prices else (prod.get("pricing") or {}).get("base_krw"),
        "variants": len(variants) if rec else None,
        "translation": tr.get("status"), "description": desc.get("status"),
        "placement": place.get("status"),
        "leaves": [x.get("leaf") for x in place.get("leaves") or [] if x.get("leaf")],
        "state": store_state(row), "store": (row or {}).get("status"),
        "store_status": (row or {}).get("store_status"), "reason": (row or {}).get("reason"),
        "handle": (row or {}).get("handle") or sent.get("handle") or "",
        "admin": (row or {}).get("admin_url") or sent.get("admin_url") or "",
        "link": src.get("link") or "", "at": row_time(row) if row else None,
    }


def cell(value: Any) -> str:
    """A TSV cell (every read tool of the five prints its cells so): nothing for None, a list's items joined by
    commas, every run of whitespace (a tab, a line end) one space."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ",".join(cell(x) for x in value)
    return " ".join(str(value).split())


def _field_list(ap: argparse.ArgumentParser, text: str | None, default: Iterable[str],
                allowed: Iterable[str] = FIELDS) -> list[str]:
    names = [ALIASES.get(x.strip(), x.strip()) for x in (text.split(",") if text else default) if x.strip()]
    bad = [x for x in names if x not in allowed]
    if bad:
        ap.error(f"unknown field {', '.join(bad)} (fields: {', '.join(allowed)})")
    return names


def _where(ap: argparse.ArgumentParser, clauses: list[str]) -> list[tuple[str, bool, str]]:
    out = []
    for c in clauses:
        m = re.match(r"^([a-z_]+)(!?=)(.*)$", c)
        if not m:
            ap.error(f"--where {c}: not F=V or F!=V")
        name = _field_list(ap, m.group(1), ())[0]
        out.append((name, m.group(2) == "=", m.group(3).strip().lower()))
    return out


def _holds(row: dict[str, Any], name: str, equal: bool, want: str) -> bool:
    value = row.get(name)
    items = [str(x).lower() for x in value] if isinstance(value, list) else \
        ([] if value in (None, "") else [str(value).lower()])
    hit = (not items) if want == "" else want in items
    return hit == equal


def _counts(values: Iterable[Any]) -> list[tuple[str, int]]:
    got: dict[str, int] = {}
    for value in values:
        for x in (value if isinstance(value, list) else [value]) or [None]:
            name = cell(x) or "(none)"
            got[name] = got.get(name, 0) + 1
    return sorted(got.items(), key=lambda kv: (-kv[1], kv[0]))


def _print_counts(counts: list[tuple[str, int]], as_json: bool) -> None:
    if as_json:
        print(json.dumps(dict(counts), ensure_ascii=False, indent=1))
    else:
        for name, n in counts:
            print(f"{name}\t{n}")


def _named_keys(ap: argparse.ArgumentParser, a: argparse.Namespace, files: ShopFiles) -> tuple[list[str], list[str]]:
    """The keys of the command's refs (and --keys-file / --job), and the errors of those that did not resolve."""
    keys, errors = [], []
    for ref in a.refs:
        try:
            keys.append(resolve(files.view, ref))
        except RefError as e:
            errors.append(str(e))
    if selection_asked(a):
        keys += keys_from_args(ap, a, files.view, (), files.shops_root)
    return list(dict.fromkeys(keys)), errors


def _dig(value: Any, path: str) -> tuple[bool, Any]:
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and re.fullmatch(r"-?\d+", part) and -len(value) <= int(part) < len(value):
            value = value[int(part)]
        else:
            return False, None
    return True, value


def _cmd_show(ap: argparse.ArgumentParser, a: argparse.Namespace, files: ShopFiles) -> int:
    if not (a.refs or selection_asked(a)):
        ap.error("show: one or more refs, --keys-file or --job")
    if a.path and not a.raw:
        ap.error("--path needs --raw")
    if a.raw and a.fields:
        ap.error("--raw and --fields: one or the other")
    names = _field_list(ap, a.fields, FIELDS)
    keys, errors = _named_keys(ap, a, files)
    for e in errors:
        print(e, file=sys.stderr)
    failed = bool(errors)
    if a.raw:
        out = []
        for key in keys:
            value = files.raw(a.raw, key)
            if value is None:
                print(f"{key}: no {a.raw} record", file=sys.stderr)
                failed = True
            elif a.path:
                found, value = _dig(value, a.path)
                if not found:
                    print(f"{key}: no {a.path} in its {a.raw} record", file=sys.stderr)
                    failed = True
            out.append({"key": key, "value": value})
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=1))
        for r in [] if a.json else out:
            if len(out) > 1:
                print(f"== {r['key']}")
            v = r["value"]
            print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
        return 1 if failed else 0
    rows = [{n: fields(files, key)[n] for n in names} for key in keys]
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    elif a.fields:
        print("\t".join(names))
        for r in rows:
            print("\t".join(cell(r[n]) for n in names))
    else:
        for i, r in enumerate(rows):
            print(("\n" if i else "") + f"== {r['key']}")
            for n in names[1:] if names[0] == "key" else names:
                print(f"{n}\t{cell(r[n])}")
    return 1 if failed else 0


def _cmd_query(ap: argparse.ArgumentParser, a: argparse.Namespace, files: ShopFiles) -> int:
    where = _where(ap, a.where)
    names = _field_list(ap, a.fields, QUERY_COLUMNS)
    count_by = _field_list(ap, a.count_by, ())[0] if a.count_by else None
    grep_in = _field_list(ap, a.grep_in, ())
    try:
        pattern = re.compile(a.grep, re.I) if a.grep else None
    except re.error as e:
        ap.error(f"--grep {a.grep}: {e}")
    keys = keys_from_args(ap, a, files.view, ()) if selection_asked(a) else files.keys()
    rows = []
    for key in keys:
        r = fields(files, key)
        if a.category and r["category"] != a.category:
            continue
        if a.leaf and a.leaf not in r["leaves"]:
            continue
        if not state_matches(r["state"], a.store):
            continue
        if not all(_holds(r, *w) for w in where):
            continue
        if pattern and not any(pattern.search(cell(r[n])) for n in grep_in):
            continue
        rows.append(r)
    if a.keys_out:
        write_keys(a.keys_out, [r["key"] for r in rows], f"shop_view.py query {a.shop}")
    if count_by:
        _print_counts(_counts(r[count_by] for r in rows), a.json)
    elif a.json:
        print(json.dumps([{n: r[n] for n in names} for r in rows], ensure_ascii=False, indent=1))
    else:
        for r in rows:
            print("\t".join(cell(r[n]) for n in names))
    return 0


def ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    """A ledger row as the ledger / history commands print it (LEDGER_COLUMNS)."""
    return {"at": row_time(row), "event": ledger_event(row), "key": row.get("key"), "status": row.get("status"),
            "store_status": row.get("store_status"), "handle": row.get("handle"), "reason": row.get("reason")}


def _since(ap: argparse.ArgumentParser, text: str) -> str:
    """--since as the ledger writes its times (UTC, 2026-11-16T08:30:00Z), so the rows compare as text."""
    try:
        return iso_time(text).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        ap.error(f"--since {text}: an ISO date or time, 2026-11-16 or 2026-11-16T08:30[:00][Z] (no zone: UTC)")


def _reason_code(reason: Any) -> str:
    m = re.match(r"^([a-z_]+):", str(reason or ""))
    return m.group(1) if m else ("(text)" if reason else "(none)")


def _cmd_ledger(ap: argparse.ArgumentParser, a: argparse.Namespace, files: ShopFiles) -> int:
    since = _since(ap, a.since) if a.since else None
    if a.count_by and a.count_by not in LEDGER_COUNT:
        ap.error(f"--count-by {a.count_by}: one of {', '.join(LEDGER_COUNT)}")
    want = (a.status or "").lower()
    rows = []
    for raw in files.view.ledger_rows:
        if not raw.get("key"):
            continue
        r = ledger_row(raw)
        if want and want not in (str(r["status"]).lower(), str(r["store_status"]).lower(), r["event"]):
            continue
        if since and r["at"] < since:
            continue
        rows.append(r)
    if a.count_by:
        _print_counts(_counts(r["at"][:10] if a.count_by == "day" else _reason_code(r["reason"])
                              if a.count_by == "reason_code" else r[a.count_by] for r in rows), a.json)
    elif a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        for r in rows:
            print("\t".join(cell(r[n]) for n in LEDGER_COLUMNS))
    return 0


def _cmd_history(ap: argparse.ArgumentParser, a: argparse.Namespace, files: ShopFiles) -> int:
    if not (a.refs or selection_asked(a)):
        ap.error("history: one or more refs, --keys-file or --job")
    keys, errors = _named_keys(ap, a, files)
    for e in errors:
        print(e, file=sys.stderr)
    out: list[dict[str, Any]] = []
    for key in keys:
        rows = [ledger_row(r) for r in files.view.ledger_rows if r.get("key") == key]
        out.append({"key": key, "state": store_state(files.view.ledger.get(key)),
                    "prepared": (files.view.prepared.get(key) or {}).get("status"), "rows": rows})
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    for i, h in enumerate([] if a.json else out):
        print(("\n" if i else "") + f"== {h['key']} ({h['state']}; prepared {h['prepared'] or '-'})")
        if not h["rows"]:
            print("(never sent)")
        for r in h["rows"]:
            print("\t".join(cell(r[n]) for n in LEDGER_COLUMNS if n != "key"))
    return 1 if errors else 0


def _cmd_check(ap: argparse.ArgumentParser, a: argparse.Namespace, files: ShopFiles) -> int:
    try:
        with open(a.plan, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as e:
        ap.error(f"{a.plan}: {e.strerror or e}")
    out = []
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = [x.strip() for x in line.split("\t")]
        if n == 1 and cols[0].lower() in ("key", "ref"):          # a header
            continue
        ref, want = cols[0], (cols[1].lower() if len(cols) > 1 else "")
        want_reason = cols[2] if len(cols) > 2 else ""
        r: dict[str, Any] = {"line": n, "ref": ref, "key": None, "want": want, "got": None,
                             "want_reason": want_reason, "got_reason": None}
        if want not in PLAN_STATES:
            r.update(result="ERROR", error=f"line {n}: status {want or '(none)'}: one of {', '.join(PLAN_STATES)}")
            out.append(r)
            continue
        try:
            r["key"] = resolve(files.view, ref)
        except RefError as e:
            r.update(result="ERROR", error=f"line {n}: {e}")
            out.append(r)
            continue
        row = files.view.ledger.get(r["key"])
        prepared = (files.view.prepared.get(r["key"]) or {}).get("status")
        r["got"] = prepared if want in ("ready", "held") else store_state(row)
        r["got_reason"] = (row or {}).get("reason")
        ok = (r["got"] == want) if want in ("ready", "held") else state_matches(r["got"], want)
        if want_reason:
            ok = ok and str(r["got_reason"] or "").lower().startswith(want_reason.lower())
        r["result"] = "ok" if ok else "FAIL"
        out.append(r)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    for r in [] if a.json else out:
        if r["result"] == "ERROR":
            print(f"ERROR\t{r['ref']}\t{r['error']}")
        else:
            print("\t".join(cell(r[n]) for n in ("result", "key", "want", "got", "want_reason", "got_reason")))
    bad = sum(r["result"] != "ok" for r in out)
    print(f"check: {len(out) - bad} ok, {bad} not", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
