"""Run the transform for one shop: every kept run (keep_run.py) -> scripts/output/shops/<shop>/prepared/.

A product in several runs is taken from the newest run. After the per-product prepare, steps look across the
products: store-wide description banners (the same image opening or closing most listings of one store) move to
description_dropped (shared_images.py); the images' Korean text is written for translation (image_texts); a product
with no brand stated gets one from the shop's own brands in its title, 원산지's importer, the images' text, or
노브랜드 (brand_fallback.py); the owner's spec rows of one product replace or drop a row the photo contradicts
(<shop>/specs_by_owner.json: apply_specs_by_owner, notes specs_by_owner / specs_by_owner_unused). The shop's
sections are not here: placement.py reads prepared/ afterwards. The output is rebuilt each time from the kept runs and the
rules (same input + same rules = the same bytes: sorted by key, no time inside):

    prepared/products.jsonl   one prepared product per line (transform.Prepared, ready or held)
    prepared/report.txt       counts, held products with their codes, texts to translate
    translation/<product id>/description_images.ko.txt|.ko.json
                              the description images' Korean text for the translation step, and the flag
                              product.description_images_text.state on each product (image_texts below);
                              a .ko file is rewritten only when its bytes change

The prepare cache (run(cache=True), 2026-11-16): each product's prepare() output and its images' text (image_read:
off / not_read / the blocks) are kept in <shop>/prepare_cache/<product id>.json (line 1 its signature, then the JSON record; derived data, not backed up) and
reused while the signature holds: the code (the bytes of every non-test scripts/*.py, taken at import), the base
rules and the measures table as loaded, the shop, the run id and line number, the bytes of the collected line and of
the images' sidecar, and the rules variant of the product's paid choice. prepare() and image_read() read no other
file (test_prepared_golden pins it). Never from the cache: the choice of the newest line, paid_choices, the
store-wide banners, the .ko files and the flag (shared blocks, en.json), the brand fallback, the owner's spec rows,
the agency hold, the report.

    .venv/bin/python scripts/run_transform.py fairwardgolf            # every kept run (through the cache)
    .venv/bin/python scripts/run_transform.py fairwardgolf 50002788-20261105T193000Z
    .venv/bin/python scripts/run_transform.py fairwardgolf --full     # every product prepared afresh, no cache
    .venv/bin/python scripts/run_transform.py fairwardgolf --verify   # each record vs a fresh prepare; writes nothing
    .venv/bin/python scripts/run_transform.py fairwardgolf --diff     # then what changed, product by product

--diff keeps the summaries of prepared/products.jsonl before the run (under the same shop lock) and prints, after the
report, "run_transform: diff: <counts>" and prepared_diff.py's TSV (key, change, field, old, new); the exit code
stays the run's. --shops-root DIR: another folder of shops (a copy, a test), default scripts/output/shops. A copy of
the real shops is prepared as the real one only with --copy-of scripts/output/shops (2026-11-16): the paid choices
come from the jobs made for that root (job.json's shops_root) and the brand dictionary is loaded for it alone, so
without --copy-of a copy is prepared with no paid variant and no dictionary brand (a false diff: 752 of 2,451
"changed"). --jobs-root DIR: the jobs whose paid choices count (default scripts/output/jobs).
"""
import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from typing import Any

import attributes
import description_image_text as image_text
from description_images import current, load_sidecar
from keep_run import SHOPS_ROOT, kept_run_ids
import brand_fallback
import prepared_diff
from shop_files import LedgerError, locked, read_jsonl, write_atomic
from description_images import image_rows
from shared_images import RULE as SHARED_RULE, drop_shared_images
import transform
from transform import _texts, prepare
from transform_shops import ShopRulesMissing, rules_for, without_paid, without_paid_addons

CACHE = "prepare_cache"                 # <shop>/prepare_cache/<product id>.json: derived data, not backed up
CACHE_FORMAT = "prepare_cache/1"


def _code_signature() -> str:
    """The code part of a cache record's signature: the Python version, the record format and the bytes of every
    non-test scripts/*.py (whatever prepare imports is among them)."""
    here = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256(f"{CACHE_FORMAT}\0{sys.version}\0".encode())
    for name in sorted(os.listdir(here)):
        if name.endswith(".py") and not name.startswith("test_") and name != "conftest.py":
            with open(os.path.join(here, name), "rb") as f:
                h.update(name.encode() + b"\0" + f.read() + b"\0")
    profiles = os.path.join(here, "size_profiles")             # the size profiles prepare reads (apparel_sizes.py)
    for name in sorted(os.listdir(profiles)) if os.path.isdir(profiles) else []:
        if name.endswith(".json"):
            with open(os.path.join(profiles, name), "rb") as f:
                h.update(b"size_profiles/" + name.encode() + b"\0" + f.read() + b"\0")
    return h.hexdigest()


# Taken here, in the module body right after the imports, never lazily (2026-11-16): the signature hashes the files on
# disk, the process runs the code it loaded; taken at the first cached run, a job that had already loaded transform
# would store old-code output under a new-code signature for any file edited meanwhile.
_CODE_SIG = _code_signature()


def kept_runs(shop: str, shops_root: str = SHOPS_ROOT) -> list[str]:
    return kept_run_ids(os.path.join(shops_root, shop, "collected"))


def latest_lines(shop: str, runs: list[str] | None = None, shops_root: str = SHOPS_ROOT) -> dict[str, tuple]:
    """{key: (run id, line number, line)}: each product from the newest of the chosen kept runs."""
    return {k: v[:3] for k, v in _latest(shop, runs, shops_root, False).items()}


def _latest(shop: str, runs: list[str] | None, shops_root: str, digest: bool) -> dict[str, tuple]:
    """latest_lines with a 4th item: the sha256 of the line's bytes (digest) or None."""
    chosen = runs or kept_runs(shop, shops_root)
    latest: dict[str, tuple[str, int, dict, str | None]] = {}
    for run_id in sorted(chosen, key=lambda r: r.split("-")[-1]):        # newest last: it wins
        path = os.path.join(shops_root, shop, "collected", run_id, "products.jsonl")
        with open(path, "rb") as f:
            for n, raw in enumerate(f.read().split(b"\n"), 1):          # \n only, as keep_run counted them
                if raw.strip():
                    line = json.loads(raw)
                    latest[line["key"]] = (run_id, n, line, hashlib.sha256(raw).hexdigest() if digest else None)
    return latest


def _read_record(path: str, sig: str) -> dict | None:
    """The cache record at `path` when its first line is `sig`; None for a miss: absent, another signature, cut off
    (in the middle of a Hangul character too) or not JSON; never an exception."""
    try:
        with open(path, "rb") as f:
            head, _, body = f.read().partition(b"\n")
        if head.decode("utf-8") != sig:
            return None
        record = json.loads(body)
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and "prepared" in record and "image_read" in record else None


def _setup(shop: str, shops_root: str, choices: dict[str, str] | None) -> tuple[Any, Any]:
    """-> (the shop's base rules, product id -> the rules variant of its paid choice)."""
    choices = paid_choices(shop, shops_root) if choices is None else choices
    rules = rules_for(shop)
    by_choice = {PAID: rules, VARIANTS: without_paid_addons(rules)}
    free = without_paid(rules)
    return rules, lambda pid: by_choice.get(choices.get(pid, ""), free)


def _base_sig(rules: Any) -> str:
    """The signature's part of one run() call: the code (taken at import), the base rules and the measures table as
    this process loaded it (transform._measures_table, not the file on disk)."""
    return hashlib.sha256("\0".join([_CODE_SIG, repr(rules), json.dumps(
        transform._measures_table(), ensure_ascii=False, sort_keys=True)]).encode()).hexdigest()


def _records(shop: str, shops_root: str, latest: dict[str, tuple], variant: Any, base: Any) -> Any:
    """For each latest line: (key, record path, signature, the stored record or None, a function computing the
    record's text afresh). The signature: _base_sig + shop, run id, line number, the line's bytes, the sidecar's
    bytes and repr() of the rules variant the product gets (its paid choice); image_read takes the base rules. The
    sidecar is read once, for the hash and for the record (each part its own json.loads)."""
    base_sig = _base_sig(base)
    folder = os.path.join(shops_root, shop, CACHE)
    reprs: dict[int, str] = {}
    for key, (run_id, n, line, line_sha) in latest.items():
        pid = key.split(":")[3]
        rules = variant(pid)
        try:
            with open(os.path.join(shops_root, shop, "description_images", f"{pid}.json"), "rb") as f:
                side_raw: bytes | None = f.read()
        except FileNotFoundError:
            side_raw = None
        sig = hashlib.sha256("\0".join([
            base_sig, shop, run_id, str(n), line_sha,
            "absent" if side_raw is None else hashlib.sha256(side_raw).hexdigest(),
            reprs.setdefault(id(rules), repr(rules))]).encode()).hexdigest()
        path = os.path.join(folder, f"{pid}.json")

        def fresh(line: Any = line, rules: Any = rules, run_id: str = run_id, n: int = n,   # a CollectedLine
                  side_raw: bytes | None = side_raw) -> str:
            def sidecar() -> Any:
                return None if side_raw is None else json.loads(side_raw)
            return json.dumps({"prepared": prepare(line, rules, run_id, n, sidecar()),
                               "image_read": image_read(line, base, sidecar())},
                              ensure_ascii=False)                       # no sort_keys: .ko.json keeps this order
        yield key, path, sig, _read_record(path, sig), fresh


def _prepared_cached(shop: str, shops_root: str, latest: dict[str, tuple], variant: Any, base: Any
                     ) -> tuple[list[Any], dict[str, Any], dict[str, int]]:
    """prepare() and image_read() of each latest line through its record in <shop>/prepare_cache/ (_records)
    -> (prepared, {key: image read}, {hit, miss}). A miss writes the record (write_atomic); a hit and a miss both
    hand on json.loads of the stored text, so a warm and a cold run give the run-level steps the same objects."""
    os.makedirs(os.path.join(shops_root, shop, CACHE), exist_ok=True)
    out: list[Any] = []
    reads: dict[str, Any] = {}
    count = {"hit": 0, "miss": 0}
    for key, path, sig, record, fresh in _records(shop, shops_root, latest, variant, base):
        if record is None:
            text = fresh()
            write_atomic(path, f"{sig}\n{text}\n")
            record = json.loads(text)
            count["miss"] += 1
        else:
            count["hit"] += 1
        out.append(record["prepared"])
        reads[key] = record["image_read"]
    return out, reads, count


def _first_diff(a: Any, b: Any, at: str = "") -> str:
    """Where two JSON values first differ: a dotted path ("(key order)" when only the order differs)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            if k not in a or k not in b or a[k] != b[k]:
                return _first_diff(a.get(k), b.get(k), f"{at}.{k}" if at else str(k))
        return f"{at} (key order)".strip() if list(a) != list(b) else at
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return next((_first_diff(x, y, f"{at}[{i}]") for i, (x, y) in enumerate(zip(a, b)) if x != y), at)
    return at


def verify(shop: str, runs: list[str] | None = None, shops_root: str = SHOPS_ROOT,
           choices: dict[str, str] | None = None) -> tuple[int, list[str]]:
    """Each cache record the next cached run would use, against prepare() and image_read() computed afresh (an input
    missing from the signature shows here). Writes nothing. -> (0 all identical / 1 a record differs, lines)."""
    rules, variant = _setup(shop, shops_root, choices)
    latest = _latest(shop, runs, shops_root, True)
    same, absent, differ = 0, 0, []
    for key, _, _, record, fresh in _records(shop, shops_root, latest, variant, rules):
        if record is None:
            absent += 1
            continue
        text = fresh()
        if json.dumps(record, ensure_ascii=False) == text:
            same += 1
        else:
            differ.append(f"  differs {key}: {_first_diff(record, json.loads(text)) or 'key order'}")
    lines = [f"verify {shop}: {len(latest)} products: {same} records identical, {len(differ)} differ, {absent} "
             f"without a current record (prepared afresh at the next run)"] + differ[:20]
    if len(differ) > 20:
        lines.append(f"  ... and {len(differ) - 20} more")
    lines.append("differs: a cache record is stale (an input missing from its signature)" if differ else
                 "identical" if same else "nothing compared: no current record (run run_transform.py first)")
    return (1 if differ else 0), lines


def _write_if_changed(path: str, text: str) -> bool:
    """Write `text` (write_atomic: a .<pid>.part renamed) only when the file's bytes differ. -> written.
    2026-11-16: every run rewrote all 4,576 .ko files of the shop; an unchanged one now keeps its mtime (incremental
    backups) and a reader never sees half of one."""
    try:
        with open(path, "rb") as f:
            if f.read() == text.encode("utf-8"):
                return False
    except OSError:
        pass
    write_atomic(path, text)
    return True


def image_read(line: dict, rules: Any, sidecar: dict | None) -> Any:
    """The product's own half of image_texts: "off" (the category does not read its images), "not_read" (the sidecar
    is not of this line's links) or description_image_text.blocks(); kept in the product's cache record."""
    category = ((line.get("specs") or {}).get("category") or {})
    try:
        on = rules.category(category.get("id"), category.get("name")).description_images
    except ShopRulesMissing:
        on = False
    if not on:
        return "off"
    if not current(sidecar, line):
        return "not_read"
    details = line.get("details") or {}
    return image_text.blocks(sidecar, (details.get("store") or {}).get("name"), details.get("brand"))


def image_texts(shop: str, prepared: list[Any], reads: dict[str, Any], shops_root: str) -> None:
    """The description images' Korean text for describe.py (description_image_text): written to
    <shop>/translation/<product id>/description_images.ko.txt (to read) and .ko.json (blocks with ids), and one
    flag on each prepared product, product["description_images_text"]["state"]:

      off           the category does not read its images (CategoryRules.description_images)
      not_read      it does, but description_images.py has not read this product's current links
      empty         read, nothing left to translate (photos, the shop's own blocks)
      to_translate  the .ko files are written: the normal final state (describe.py reads the Korean blocks)
      translated    an old description_images.en.json exists with source_sha256 = this text's sha256

    describe.py reads the flag (not the folder) and the .ko blocks; since the owner's decision of 2026-11-10 the
    images' text is not translated and nothing writes description_images.en.json (one written before is read here
    only for the state). A product left with no text loses its .ko files (an .en file is kept).
    reads: {key: image_read()} of each product (from its cache record or computed)."""
    folder = os.path.join(shops_root, shop, "translation")
    read: dict[str, tuple[str, dict]] = {}
    state: dict[str, str] = {}
    for p in prepared:
        got = reads[p["key"]]
        if isinstance(got, str):
            state[p["key"]] = got
        else:
            read[p["key"]] = (p["source"]["channel_no"], got)
    shared = image_text.mark_shared(read)
    for p in prepared:
        product_id = p["source"]["product_id"]
        where = os.path.join(folder, product_id)
        ko_txt, ko_json, en_json = (os.path.join(where, f"description_images.{x}") for x in ("ko.txt", "ko.json",
                                                                                           "en.json"))
        rel = f"translation/{product_id}/description_images"
        flag: dict = {"state": state.get(p["key"]), "ko": None, "en": f"{rel}.en.json"}
        got = shared.get(p["key"])
        if got is not None:
            digest = image_text.sha(got["blocks"])
            flag.update(blocks=len(got["blocks"]), chars=sum(len(b["text"]) for b in got["blocks"]),
                        sha256=digest, dropped=got["dropped"])
            if got["blocks"]:
                os.makedirs(where, exist_ok=True)
                glossary = image_text.glossary_for(p["source"].get("category_id"))
                _write_if_changed(ko_txt, image_text.as_text(product_id, got["blocks"], digest, glossary))
                _write_if_changed(ko_json, json.dumps(
                    {"format": image_text.FORMAT, "product_id": product_id, "key": p["key"], "sha256": digest,
                     "instructions": list(image_text.INSTRUCTIONS), "glossary": glossary, "blocks": got["blocks"]},
                    ensure_ascii=False, indent=1))
                flag.update(state="to_translate", ko=f"{rel}.ko.json")
                try:
                    with open(en_json, encoding="utf-8") as f:
                        if json.load(f).get("source_sha256") == digest:
                            flag["state"] = "translated"
                except (OSError, ValueError):
                    pass
            else:
                flag["state"] = "empty"
        if flag["ko"] is None:
            for old in (ko_txt, ko_json):
                if os.path.exists(old):
                    os.remove(old)
        p["product"]["description_images_text"] = flag


JOBS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "jobs")
PAID, VARIANTS = "paid", "variants"


def paid_choices(shop: str, shops_root: str = SHOPS_ROOT, jobs_root: str = JOBS_ROOT) -> dict[str, str]:
    """Product id -> the paid choices its job took: PAID (a job made with --paid: the category's paid variants and
    add-ons) or VARIANTS (--paid-variants: paid variants, no paid add-on); a product of no such job takes only what
    costs nothing extra. The latest job of a product decides. Read from the jobs' own files, so a job's choice stays
    with its products whoever prepares the shop again (2026-11-11: the transform prepares the whole shop, and a
    --paid job of 50002787 turned the paid variants of 101 published full sets on; a run by hand did the same). Jobs
    from before the choice was recorded (no `free_only` in job.json, before 2026-11-09) count as free: their products
    were prepared free since. A job of another shops root (a trial) does not count."""
    found: list[tuple[str, str | None, list[str]]] = []
    for name in sorted(os.listdir(jobs_root)) if os.path.isdir(jobs_root) else []:
        folder = os.path.join(jobs_root, name)
        if name.startswith("_") or not os.path.isfile(os.path.join(folder, "job.json")):
            continue
        with open(os.path.join(folder, "job.json"), encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("shop") != shop or "free_only" not in meta or \
                os.path.abspath(meta.get("shops_root") or SHOPS_ROOT) != os.path.abspath(shops_root):
            continue
        choice = VARIANTS if meta.get("paid_variants") else None if meta["free_only"] else PAID
        rows = os.path.join(folder, "listing.jsonl")
        # a cut-off last line (a scroll job killed while appending) must not stop the shop's prepare (2026-11-16)
        ids = [str(r["product_id"]) for r in read_jsonl(rows, tail_ok=True)]
        found.append((meta.get("created_at") or "", choice, ids))
    out: dict[str, str] = {}
    for _, choice, ids in sorted(found, key=lambda f: f[0]):
        for pid in ids:
            if choice:
                out[pid] = choice
            else:
                out.pop(pid, None)
    return out


def brand_by_owner(shop: str, shops_root: str = SHOPS_ROOT) -> dict[str, str]:
    """{key: brand} the owner set by hand where only the photo names the brand (<shop>/brand_by_owner.json: {"entries":
    {key: {"brand": ..., "why": ..., "at": ...}}}; none when the file is absent)."""
    path = os.path.join(shops_root, shop, "brand_by_owner.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: v["brand"] for k, v in json.load(f).get("entries", {}).items() if v.get("brand")}


def specs_by_owner(shop: str, shops_root: str = SHOPS_ROOT) -> dict[str, dict[str, str | None]]:
    """{key: {label_ko: value_ko | None}} the owner set by hand where only the photo contradicts a spec row
    (<shop>/specs_by_owner.json: {"entries": {key: {"rows": {label_ko: value_ko | null}, "why": ..., "at": ...}}};
    none when the file is absent; an entry without rows is skipped). 2026-11-18, LABOUM 12748958315: the golfup
    ZESTAIM Ponytail template's 성별 남성용 on a women's build (L-flex 40 g LABOUM shaft, pink ferrules)."""
    path = os.path.join(shops_root, shop, "specs_by_owner.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {k: dict(v["rows"]) for k, v in json.load(f).get("entries", {}).items() if v.get("rows")}


def apply_specs_by_owner(prepared: list[Any], by_owner: dict[str, dict[str, str | None]],
                         lines: dict[str, dict]) -> dict[str, int]:
    """The owner's spec rows (specs_by_owner) on the prepared products, run-level after the brand fallback (never in
    the prepare cache). Per row the product shows (product.specs, after check_specs and the title-model rows): a
    string replaces value_ko (order and for_ko kept), None drops the row; a row is never added. Notes specs_by_owner
    "<label>: <old> -> <new | dropped>" and specs_by_owner_unused "<label>" (a label the product does not show); a
    value equal to the row's changes nothing and adds no note. Then the texts are rebuilt and, when a changed label
    is one an attribute reads (attributes.GENDER: 성별), product.attributes is extracted again exactly as prepare
    does (the line's raw rows with the owner's values, its title and listing query: the listing evidence kept),
    the changed row's evidence named "owner:<label>". `lines`: {key: the collected line} (the run's latest).
    Returns {entries, applied, unused, not_prepared}."""
    counts = {"entries": len(by_owner), "applied": 0, "unused": 0, "not_prepared": 0}
    by_key = {p["key"]: p for p in prepared}
    counts["not_prepared"] = sum(1 for k in by_owner if k not in by_key or not by_key[k].get("product"))
    attr_rows = {label for a in attributes.ATTRIBUTES.values() for label in a.rows}
    for key, rows in by_owner.items():
        p = by_key.get(key)
        if not p or not p.get("product"):
            continue
        specs = p["product"].get("specs") or []
        shown = {r.get("label_ko") for r in specs}
        changed: dict[str, str | None] = {}
        kept = []
        for r in specs:
            label = r.get("label_ko")
            if label not in rows or rows[label] == r.get("value_ko"):
                kept.append(r)
                continue
            new = rows[label]
            changed[label] = new
            p["notes"].append({"code": "specs_by_owner",
                               "detail": f"{label}: {r.get('value_ko')} -> {new if new is not None else 'dropped'}"})
            if new is not None:
                kept.append({**r, "value_ko": new})
        for label in rows:
            if label not in shown:
                p["notes"].append({"code": "specs_by_owner_unused", "detail": label})
                counts["unused"] += 1
        if not changed:
            continue
        counts["applied"] += 1
        p["product"]["specs"] = kept
        p["texts"] = _texts(p["product"])
        if set(changed) & attr_rows:
            line = lines.get(key) or {}
            raw = []
            for r in ((line.get("specs") or {}).get("specs") or []):
                if r.get("label") in changed:
                    if changed[r["label"]] is None:
                        continue
                    r = {**r, "value": changed[r["label"]]}
                raw.append(r)
            stated = attributes.extract(
                [(v["sku"], list(v.get("options_ko") or [])) for v in p["product"].get("variants") or []],
                raw, (line.get("details") or {}).get("name"), (line.get("listing") or {}).get("query"))
            for got in stated.values():
                for e in got["evidence"]:
                    if e["source"].startswith("row:") and e["source"][4:] in changed:
                        e["source"] = "owner:" + e["source"][4:]
            p["product"]["attributes"] = stated
    return counts


def _known_brands(shops_root: str) -> list[str]:
    """The Korean names of the brand dictionary and its Latin spellings (brand_fallback steps 3b, 3c); none for another
    shops root (a test's)."""
    if os.path.abspath(shops_root) != os.path.abspath(SHOPS_ROOT):
        return []
    try:
        from translation_dicts import Dictionaries
        entries = Dictionaries().entries["brand"]
        return sorted({k for k in entries if re.search(r"[가-힣]", k)}
                      | {v for v in entries.values() if re.fullmatch(r"[A-Za-z][A-Za-z0-9 .&'-]{2,}", v or "")})
    except Exception:                                                   # a test's shops root: no dictionary
        return []


def _store_names(line: dict) -> set[str]:
    """The seller's shop name and legal name, normalized (a brand row naming the shop: brand_fallback.store_named)."""
    store = (line.get("details") or {}).get("store") or {}
    return {re.sub(r"\s+", "", str(x or "")).casefold()
            for x in (store.get("name"), (store.get("business") or {}).get("legal_name"))} - {""}


def _release_row(line: dict) -> str | None:
    """The notice's 동일 모델의 출시연월 value (a seller may write the brand there: brand_fallback.release_brand)."""
    return next((str(r.get("value") or "") for r in ((line.get("details") or {}).get("notice") or {}).get("items") or []
                 if isinstance(r, dict) and r.get("label") == "동일 모델의 출시연월"), None)


def run(shop: str, runs: list[str] | None = None, shops_root: str = SHOPS_ROOT,
        choices: dict[str, str] | None = None, cache: bool = False, brands: list[str] | None = None) -> dict:
    """Prepare the shop's latest lines. Each product with the paid choices of its job (`choices`, default
    paid_choices(): the jobs' files), every other one with what costs nothing extra (the owner, 2026-11-09).
    `brands`: the brand dictionary's names for the fallback (default _known_brands(shops_root)).
    cache: each product's prepare through its record in <shop>/prepare_cache/ (_prepared_cached; job.py and the
    CLI); result["cache"] = {hit, miss}. The steps across products below always run over the whole shop."""
    rules, variant = _setup(shop, shops_root, choices)
    chosen = runs or kept_runs(shop, shops_root)
    latest = _latest(shop, runs, shops_root, cache)
    counts = None
    if cache:
        prepared, reads, counts = _prepared_cached(shop, shops_root, latest, variant, rules)
    else:
        prepared = [prepare(line, variant(line["key"].split(":")[3]), run_id, n,
                            load_sidecar(shop, line["key"].split(":")[3], shops_root))
                    for run_id, n, line, _ in latest.values()]
        reads = {key: image_read(line, rules, load_sidecar(shop, key.split(":")[3], shops_root))
                 for key, (_, _, line, _) in latest.items()}
    prepared.sort(key=lambda p: p["key"])
    prepared = drop_shared_images(prepared)                             # run-level: needs the store's other listings
    image_texts(shop, prepared, reads, shops_root)                      # run-level: blocks a store repeats
    brand_fallback.fill(                                                # run-level: the shop's own brands
        prepared,
        lambda key: [r for img in image_rows(load_sidecar(shop, key.split(":")[3], shops_root)) for r in img],
        {k: (((line[2].get("specs") or {}).get("facts") or {}).get("origin") or {}).get("value")
         for k, line in latest.items()},
        _texts,
        _known_brands(shops_root) if brands is None else brands,
        brand_by_owner(shop, shops_root),
        {k: _release_row(line[2]) for k, line in latest.items()},
        {k: _store_names(line[2]) for k, line in latest.items()},
        {p["key"]: (latest[p["key"]][2].get("details") or {}).get("store") or {} for p in prepared    # step 5b: only
         if (c := rules.categories.get(str(p["source"].get("category_id")))) and c.own_brand_wordmark})   # where asked
    owner_specs = apply_specs_by_owner(                                 # run-level: the owner's word, never cached
        prepared, specs_by_owner(shop, shops_root), {k: line[2] for k, line in latest.items()})
    for p in prepared:                                                 # after the brand: needs the fallback's answer
        cat = rules.categories.get(str(p["source"].get("category_id")))
        if cat and cat.agency_needs_brand and p["status"] == "ready" \
                and p["product"].get("brand_source") == "none" \
                and any(n["code"] == "purchase_agency" for n in p["notes"]):
            p["held"].append({"code": "agency_no_brand", "detail": "a purchase agency's import with no brand"})
            p["status"] = "held"
    out_dir = os.path.join(shops_root, shop, "prepared")
    os.makedirs(out_dir, exist_ok=True)
    write_atomic(os.path.join(out_dir, "products.jsonl"),         # a reader never sees half (shop_files)
                 "".join(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n" for p in prepared))
    status = Counter(p["status"] for p in prepared)
    codes = Counter(h["code"] for p in prepared for h in p["held"])
    notes = Counter(n["code"] for p in prepared for n in p["notes"])
    texts = {t["id"] for p in prepared if p["status"] == "ready" for t in p["texts"]}
    lines = [f"transform {shop}: {len(prepared)} products from {len(chosen)} run(s): {status['ready']} ready, "
             f"{status['held']} held {dict(sorted(codes.items()))}, notes {dict(sorted(notes.items()))}, "
             f"{len(texts)} distinct texts to translate"]
    shared = [(p["source"]["channel_no"],
               sum(d["rule"] == SHARED_RULE for d in p["product"].get("description_dropped") or []))
              for p in prepared]
    if any(n for _, n in shared):
        lines.append(f"  shared store images: {sum(n for _, n in shared)} dropped from "
                     f"{sum(1 for _, n in shared if n)} products of {len({c for c, n in shared if n})} store(s)")
    if owner_specs["entries"]:
        lines.append(f"  specs_by_owner: {owner_specs['entries']} entries, {owner_specs['applied']} applied, "
                     f"{owner_specs['unused']} unused, {owner_specs['not_prepared']} keys not prepared")
    states = Counter(p["product"].get("description_images_text", {}).get("state") for p in prepared)
    if set(states) - {"off"}:
        lines.append(f"  description image text: {dict(sorted(states.items()))} (translation/<product id>/)")
    lines += [f"  held {p['key']}: " + "; ".join(f"{h['code']} ({h['detail']})" for h in p["held"])
              for p in prepared if p["held"]]
    write_atomic(os.path.join(out_dir, "report.txt"), "\n".join(lines) + "\n")
    result: dict[str, Any] = {"prepared": prepared, "report": lines, "out_dir": out_dir}
    if counts is not None:
        result["cache"] = counts
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a shop's kept collection runs for translation.")
    parser.add_argument("shop", help="shop id, e.g. fairwardgolf")
    parser.add_argument("runs", nargs="*", help="kept run ids (default: every kept run)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="prepare every product afresh, no cache record read or "
                                                          "written")
    mode.add_argument("--verify", action="store_true", help="compare each cache record with prepare computed "
                                                            "afresh; writes nothing; exit 1 on a difference")
    parser.add_argument("--shops-root", default=SHOPS_ROOT, metavar="DIR",
                        help="the folder holding the shops (default scripts/output/shops)")
    parser.add_argument("--copy-of", metavar="ROOT", help="--shops-root is a copy of ROOT (scripts/output/shops): "
                        "take the paid choices of ROOT's jobs and the brand dictionary as for ROOT, so the copy is "
                        "prepared as ROOT would be")
    parser.add_argument("--jobs-root", default=JOBS_ROOT, metavar="DIR", help="the folder holding the jobs whose "
                        "paid choices count (default scripts/output/jobs)")
    parser.add_argument("--diff", action="store_true", help="after the run, what changed in prepared/products.jsonl "
                        "(prepared_diff.py: a summary line, then its TSV); not with --verify")
    args = parser.parse_args(argv)
    if args.diff and args.verify:
        parser.error("--diff is not with --verify (it writes nothing to compare)")
    as_root = args.copy_of or args.shops_root          # the jobs and the dictionary of the root this one copies
    try:
        choices = paid_choices(args.shop, as_root, args.jobs_root)
    except LedgerError as e:
        print(f"run_transform: stop: {e}")
        return 2
    brands = _known_brands(as_root)
    if args.verify:                                                     # reads only: allowed while a job runs
        try:
            code, lines = verify(args.shop, args.runs or None, args.shops_root, choices)
        except ShopRulesMissing as e:
            print(f"run_transform: stop: {e}")
            return 2
        for line in lines:
            print(f"run_transform: {line}")
        return code

    def body() -> int:
        before = None
        if args.diff:                       # the snapshot, under the same lock: its summaries (prepared_diff)
            try:
                before = prepared_diff.summaries_of(read_jsonl(
                    os.path.join(args.shops_root, args.shop, "prepared", "products.jsonl")))
            except LedgerError as e:
                print(f"run_transform: stop: --diff: {e}")
                return 2
        try:
            result = run(args.shop, args.runs or None, shops_root=args.shops_root, choices=choices,
                         cache=not args.full, brands=brands)
        except ShopRulesMissing as e:
            print(f"run_transform: stop: {e}")
            return 2
        for line in result["report"]:
            print(f"run_transform: {line}")
        if "cache" in result:
            print(f"run_transform: cache: {result['cache']['hit']} records used, {result['cache']['miss']} "
                  f"prepared afresh ({CACHE}/)")
        print(f"run_transform: -> {result['out_dir']}")
        if before is not None:
            after = prepared_diff.summaries_of(result["prepared"])
            products = prepared_diff.diff(before, after)
            print(f"run_transform: diff: {prepared_diff.summary_line(prepared_diff.counts(before, after, products))}")
            for line in prepared_diff.tsv_lines(products):
                print(line)
        return 0
    return locked(args.shops_root, args.shop, "run_transform.py", body, "run_transform")   # not while a job runs


if __name__ == "__main__":
    sys.exit(main())
