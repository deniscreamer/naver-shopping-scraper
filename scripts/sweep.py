"""Old model answers a rule, dictionary or prompt improvement now judges wrong, read only (the retro-sweep plan, stage
1, 2026-11-19: the two-brand scan found 98 live titles by hand; re-preparing never reaches a cached answer, since
translation/texts.jsonl keeps a title until translate.plan asks it again and describe.py keeps a description).

    .venv/bin/python scripts/sweep.py fairwardgolf [--json]                    # every published product
    .venv/bin/python scripts/sweep.py fairwardgolf --only <ref> [--keys-file F] [--job ID [--event E]]

Scope: every product the ledger (publish/published.jsonl) has as published, live (ACTIVE, or an old row with no
store_status) and drafts (store_status DRAFT) apart; withdrawn products (holds among them) are left out; the ready
products never published are counted, not checked. A selection narrows it; one that names no product is a usage
error (exit 2), never "every product".

The checks (CHECKS; SWEEP.md has the same table, test_sweep.py compares them), pure functions over local files. A
text whose last row a review wrote (by "review-...") is never flagged: only what the model or a rule wrote.

Out: a table a check (live / draft counts, up to EXAMPLES examples: key, handle, the text), with --json the same as
JSON; files in shops/<shop>/sweep/latest/ (shop_files.write_atomic): answers.json (every finding) and
<check>.live.keys / <check>.draft.keys (one key a line, for a --keys-file). Nothing else is written, the dictionaries
included (Dictionaries(write=False): the default one syncs the live copies). Refused while the shop's lock is held (a job
rewrites the files read here; shop_files.ensure_free: exit 2, the busy line); the lock is not taken, so a job may
start while it reads (a few seconds).

Exit codes, as the other read tools: 0 done; 1 a shop file with a broken line (LedgerError, the file and line named);
2 usage (an unknown shop, an empty selection, none of it published) or the shop busy.
"""
import argparse
import html
import json
import os
import re
import sys
import time
from typing import Any, Iterable

import describe
import publish as P
import shop_stores
import shopify_payload as sp
import translate
import translation_dicts as D
from brand_fallback import in_title
from shop_files import LedgerError, ShopBusy, ensure_free, write_atomic
from shop_view import add_ref_flags, keys_from_args, selection_asked
from translation_rules import HANGUL_RE

CHECKS = (
    ("title.pending_reask", "translate.plan already has the title among its pending items (the next translate.py "
                            "run with the product named asks it again)"),
    ("title.other_brand", "the English title names a dictionary brand that is not the vendor and that the Korean "
                          "title and spec values do not name"),
    ("text.hangul", "Hangul left in the English title, an option name or value, or the description"),
    ("description.old_brand", "the description's first sentence (where it names the product) names a dictionary "
                              "brand that is not the vendor and that the Korean title and spec values do not name"),
    ("description.patterns", "the description trips describe.py's checks that need no packet: shop talk, talk "
                             "about the listing, kana / han, a link, phone, price or markup"),
    ("description.stale", "the description was written from another packet than today's (one number and a keys "
                          "file: the owner, 2026-11-19, only descriptions with an explicit error are rewritten)"),
)
CODES = tuple(c for c, _ in CHECKS)
EXAMPLES = 3
TEXT_MAX = 160
# the rows the transform reads for the brand: what they name was weighed there and may have been judged no brand
# (2026-11-19, the two-brand scan: 13510579139's 브랜드 row 퐁당스윔 is the seller's shop, its title "Pongdang Swim
# Kids' ..." under Inparo; 13826709716's 원산지 brackets named the wholesaler 감씨 and the store 골드벙커): they do not
# vouch for a brand in the English
BRAND_ROWS = ("브랜드", "제조사", "원산지", "수입원")
# a mixed set: the seller's word for clubs of several makers in one set; the other makers' Korean names are often
# spelled as the dictionary does not have them (2026-11-19, the first sweep: 6 of the 7 title findings, "핑 G440
# 브릿지스톤 V300 ... 조합" 12079565200, "타이틀리스트 GT2 테일러 SIM2 조합" 12863003091, "요넥엘리트 조합" 7471640512).
# Looked for in the Korean title and the spec values (korean_texts): the review of the first sweep, 9275189943 says it
# only in its 종류 row ("조합풀세트"; "PXG/ 테일러메이드/ 골프채 풀세트", a Callaway wood in it)
MIXED_RE = re.compile(r"조합")
BRAND_MIN = 3                                   # letters and digits of a brand looked for (brand_key): "GB" never
DICTS_LIVE = D.LIVE_ROOT                        # the live dictionaries read (a test points it at a copy)
_TAG_RE = re.compile(r"<[^>]+>")


def read_dictionaries(live_root: str = D.LIVE_ROOT, backup_root: str = D.BACKUP_ROOT) -> D.Dictionaries:
    """The dictionaries as translate.py sees them (the live copy, with the backup's entries it lacks), nothing
    written: the default Dictionaries() seeds a missing live copy and writes the pulled entries into it."""
    return D.Dictionaries(live_root, backup_root, write=False)


# ---- the checks ----------------------------------------------------------------------------------------------

class Brands:
    """The brand dictionary for the brand checks: each English spelling (the shop's: vendor_name), the Korean keys
    that give it, and one pattern finding any of them as whole words in an English text."""

    def __init__(self, dicts: D.Dictionaries, tenant: str):
        self.tenant = tenant
        self.korean: dict[str, list[str]] = {}          # brand_key -> its Korean keys
        self.spelling: dict[str, str] = {}              # brand_key -> the first spelling (vendor_spellings' rule)
        for ko, en in dicts.entries.get("brand", {}).items():
            name = sp.vendor_name(en)
            k = sp.brand_key(name)
            if len(k) < BRAND_MIN or k == sp.brand_key(tenant):
                continue
            self.spelling.setdefault(k, name)
            self.korean.setdefault(k, []).append(ko)
        parts = []
        for name in sorted(self.spelling.values(), key=lambda n: (-len(n), n)):
            words = re.findall(r"[a-z0-9]+", name.casefold())
            if words:                                   # "U.S. Kids Golf" as "US KIDS GOLF" or "U.S.Kids Golf" too
                parts.append(r"[\s.\-&']*".join(map(re.escape, words)))
        self.pattern = re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])") if parts else None

    def named(self, english: str) -> list[str]:
        """The dictionary brands `english` names, in its order (a longer name first where two start together)."""
        if not self.pattern or not english:
            return []
        out = []
        for m in self.pattern.finditer(english.casefold()):
            name = self.spelling.get(sp.brand_key(m.group(0)))
            if name and name not in out:
                out.append(name)
        return out

    def other(self, english: str, vendor: str, korean: str) -> list[str]:
        """The brands `english` names that are not `vendor` (nor a line of it or it of them: Maruman Majesty) and that
        `korean` (the Korean title and spec values) does not name: no Korean key of the brand, nor its Latin spelling,
        where a word starts (brand_fallback.in_title: 핑 is not in 핑크). None when the vendor is unknown (a Hangul
        brand with no dictionary entry: _brand_en gives ""), as translate._stale_lead."""
        own = sp.brand_key(vendor)
        if not own:
            return []
        out = []
        for name in self.named(english):
            k = sp.brand_key(name)
            if k == own or translate.same_brand_line(name, vendor):
                continue
            if in_title(korean, [*self.korean.get(k, []), name]):
                continue
            out.append(name)
        return out


def korean_texts(prepared: dict[str, Any]) -> str:
    """The Korean title and the spec values but the brand rows (BRAND_ROWS), one text."""
    product = prepared.get("product") or {}
    rows = [s.get("value_ko") or "" for s in product.get("specs") or [] if s.get("label_ko") not in BRAND_ROWS]
    return " | ".join([product.get("title_ko") or "", *rows])


def title_id(prepared: dict[str, Any]) -> str | None:
    return next((t["id"] for t in prepared.get("texts") or [] if t["kind"] == "title"), None)


def pending_reask(prepared: dict[str, Any], dicts: D.Dictionaries, store: dict[tuple[str, str], str], tenant: str,
                  brands: dict[tuple[str, str], str], fixed: set[tuple[str, str]]) -> str | None:
    """The title's pending item as translate.plan gives it today (its context, else its source), None when the title
    is not pending. A hand correction (`fixed`) plan never asks again."""
    tid = title_id(prepared)
    if tid is None:
        return None
    _, _, pending = translate.plan(prepared, dicts, store, tenant, brands, False, fixed)
    item = next((i for i in pending if i["id"] == tid), None)
    if item is None:
        return None
    return f"{store.get((prepared['key'], tid), '')} <- {item.get('context') or item.get('source')}"


def other_brand(english: str, vendor: str, prepared: dict[str, Any], brands: Brands) -> list[str]:
    """The brands `english` names that the product is not (Brands.other); none for a mixed set (MIXED_RE in the
    Korean title or a spec value)."""
    korean = korean_texts(prepared)
    if MIXED_RE.search(korean):
        return []
    return brands.other(english, vendor, korean)


def first_sentence(texts: list[str]) -> str:
    """The description's first sentence: where it names the product, as its title does (describe.packet's Title).
    2026-11-19, the first sweep: the whole description named another brand on 330 products, most of them what the
    set holds (an Odyssey putter in 99 Callaway sets, True Temper shafts); the first sentence on 124, the old vendor
    class among them ("Gold Bunker junior golf club ..." 25, Gamssi 13, "Pongdang Swim Kids' ...", "PING junior #7
    iron ...")). `texts`: text_of(the html)."""
    return describe._SENTENCE_RE.split(texts[0])[0] if texts else ""


def text_of(description_html: str) -> list[str]:
    """The description's texts, one a paragraph, heading or list item, unescaped."""
    return [t for t in (html.unescape(x).strip() for x in _TAG_RE.split(description_html or "")) if t]


def hangul(english: dict[str, str]) -> list[str]:
    """The texts (where: text) with Hangul left in them."""
    return [f"{where}: {text}" for where, text in english.items() if HANGUL_RE.search(text or "")]


def description_patterns(texts: list[str]) -> list[str]:
    """describe.packet_free_problems (problems() but the numbers and the origin, which need what the model was given)
    on each text of the stored description (`texts`: text_of(the html)). Hangul alone is text.hangul's, not here."""
    out = []
    for text in texts:
        why = [w for w in describe.packet_free_problems(text) if w != "not English" or describe._CJK_RE.search(text)]
        if why:
            out.append(f"{', '.join(why)}: {text}")
    return out


def is_review(row: dict[str, Any] | None) -> bool:
    """A description row written by hand: `by: review-<date>-<why>`, as a hand title row (DESCRIBE.md, "Hand rows";
    none exists yet, 2026-11-19)."""
    return str((row or {}).get("by") or "").startswith("review-")


# ---- the shop ------------------------------------------------------------------------------------------------

def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= TEXT_MAX else text[:TEXT_MAX - 1] + "…"


def ocr_errors(shop_dir: str) -> list[str]:
    """The description images' sidecars (description_images/<id>.json) that carry an error: their keys."""
    folder = os.path.join(shop_dir, "description_images")
    out = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                row = json.load(f)
        except (OSError, ValueError):
            out.append(name[:-5])
            continue
        if row.get("error"):
            out.append(str(row.get("key") or name[:-5]))
    return out


def run(shop: str, shops_root: str = P.SHOPS_ROOT, keys: Iterable[str] | None = None,
        dicts: D.Dictionaries | None = None) -> dict[str, Any]:
    """The checks over the shop's published products (or `keys` among them) -> the answers (answers.json's shape).
    Reads only; the caller writes."""
    started = time.monotonic()
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    dicts = dicts or read_dictionaries(DICTS_LIVE)
    shop_obj = P.Shop(shop, shops_root)
    prepared_all, translated_all, _ = shop_obj.inputs()
    ledger = shop_obj.ledger()
    withdrawn = shop_obj.withdrawn()
    texts_path = os.path.join(shop_obj.dir, "translation", "texts.jsonl")
    store = translate._load_store(texts_path)
    asked_with = translate._load_brands(texts_path, tenant)
    fixed = translate._load_fixed(texts_path)
    descriptions = describe.load_store(shop_obj.dir)
    vendors = P.vendor_spellings({}, list(dicts.entries.get("brand", {}).values()))
    brands = Brands(dicts, tenant)

    wanted = list(keys) if keys is not None else None
    scope = sorted(k for k in (wanted if wanted is not None else ledger) if k in ledger)
    where = {k: "draft" if ledger[k].get("store_status") == "DRAFT" else "live" for k in scope}
    findings: dict[str, list[dict[str, Any]]] = {c: [] for c in CODES}

    def hit(code: str, key: str, text: str) -> None:
        findings[code].append({"key": key, "store": where[key], "handle": ledger[key].get("handle"),
                               "text": _clip(text)})

    not_checked: dict[str, str] = {}
    for key in scope:
        p, t = prepared_all.get(key), translated_all.get(key) or {}
        if not p:
            not_checked[key] = "no prepared record"
            continue
        en = t.get("en") or {}
        tid = title_id(p)
        title = en.get(tid or "") or ""
        title_by_model = tid is not None and (key, tid) not in fixed
        vendor = translate._brand_en(p, dicts, tenant)
        # 1. the title translate.plan would ask again
        if title_by_model:
            why = pending_reask(p, dicts, store, tenant, asked_with, fixed)
            if why:
                hit("title.pending_reask", key, why)
        # 2. another brand in the title
        if title_by_model and title:
            other = other_brand(title, vendor, p, brands)
            if other:
                hit("title.other_brand", key, f"{', '.join(other)} (vendor {vendor or 'none'}): {title}")
        # 3. Hangul in the English (the title, the options), then the description's
        english: dict[str, str] = {}
        for x in p.get("texts") or []:
            if x["kind"] in ("title", "option_name", "option_value") and (key, x["id"]) not in fixed \
                    and en.get(x["id"]):
                english["title" if x["kind"] == "title" else f"{x['kind']} {x['ko']}"] = en[x["id"]]
        row = descriptions.get(key)
        body = (row or {}).get("html") or ""
        by_model = bool(row) and not is_review(row) and bool(body)
        parts = text_of(body) if by_model else []
        korean_left = next((x for x in parts if HANGUL_RE.search(x)), None)
        if korean_left:
            english["description"] = korean_left
        left = hangul(english)
        if left:
            hit("text.hangul", key, "; ".join(left))
        if row and by_model:
            # 4. another brand in the description
            lead = first_sentence(parts)
            other = other_brand(lead, vendor, p, brands)
            if other:
                hit("description.old_brand", key, f"{', '.join(other)} (vendor {vendor or 'none'}): {lead}")
            # 5. describe.py's packet-free checks
            bad = description_patterns(parts)
            if bad:
                hit("description.patterns", key, "; ".join(bad))
            # 6. the packet changed since (what describe.py --offline --published counts as stale)
            if p.get("status") == "ready" and t.get("status") == "translated":
                blocks = describe.load_blocks(shop_obj.dir, p["product"])
                if row.get("source_sha256") != describe.source_sha256(p, t, blocks, vendors, tenant):
                    hit("description.stale", key, "source changed")

    ready_unpublished = len(set(shop_obj.ready()) - set(ledger)) if wanted is None else None
    errors = ocr_errors(shop_obj.dir)
    inputs = {}
    for rel in ("prepared/products.jsonl", "translation/translated.jsonl", "translation/texts.jsonl",
                "translation/descriptions.jsonl", "publish/published.jsonl"):
        path = os.path.join(shop_obj.dir, rel)
        inputs[rel] = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(path)))
                       if os.path.exists(path) else None)
    return {"shop": shop, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "seconds": round(time.monotonic() - started, 2), "inputs": inputs,
            "selection": wanted, "scope": {"live": sum(1 for k in scope if where[k] == "live"),
                                           "draft": sum(1 for k in scope if where[k] == "draft"),
                                           "withdrawn_left_out": len(withdrawn) if wanted is None else None,
                                           "ready_not_published": ready_unpublished,
                                           "named_not_published": sorted(set(wanted or ()) - set(ledger)),
                                           "not_checked": not_checked},
            "checks": {c: {"live": sum(1 for f in findings[c] if f["store"] == "live"),
                           "draft": sum(1 for f in findings[c] if f["store"] == "draft"),
                           "findings": findings[c]} for c in CODES},
            "ocr_errors": errors}


def write(answers: dict[str, Any], shops_root: str) -> str:
    """answers.json and the keys files in shops/<shop>/sweep/latest/ -> that folder."""
    out = os.path.join(shops_root, answers["shop"], "sweep", "latest")
    os.makedirs(out, exist_ok=True)
    write_atomic(os.path.join(out, "answers.json"), json.dumps(answers, ensure_ascii=False, indent=1) + "\n")
    for code, check in answers["checks"].items():
        for store in ("live", "draft"):
            keys = [f["key"] for f in check["findings"] if f["store"] == store]
            write_atomic(os.path.join(out, f"{code}.{store}.keys"), "".join(k + "\n" for k in keys))
    return out


def table(answers: dict[str, Any], out: str) -> list[str]:
    s = answers["scope"]
    lines = [f"sweep {answers['shop']}: {s['live']} live, {s['draft']} drafts checked"
             + (f"; {s['withdrawn_left_out']} withdrawn left out" if s["withdrawn_left_out"] is not None else "")
             + (f"; {s['ready_not_published']} ready, not published (not checked)"
                if s["ready_not_published"] is not None else "")
             + (f"; named, not published: {len(s['named_not_published'])}" if s["named_not_published"] else "")
             + (f"; not checked {len(s['not_checked'])}" if s["not_checked"] else ""),
             "  inputs: " + ", ".join(f"{os.path.basename(k)} {v}" for k, v in answers["inputs"].items()),
             f"{'check':<24}{'live':>6}{'draft':>7}"]
    for code in CODES:
        c = answers["checks"][code]
        lines.append(f"{code:<24}{c['live']:>6}{c['draft']:>7}")
        for f in c["findings"][:EXAMPLES]:
            lines.append(f"    {f['key']}  {f['handle']}  {f['text']}")
    lines.append(f"OCR sidecars with an error (whole shop): {len(answers['ocr_errors'])}"
                 + (f" ({', '.join(answers['ocr_errors'][:5])})" if answers["ocr_errors"] else ""))
    lines.append(f"-> {out} ({answers['seconds']} s)")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shop")
    ap.add_argument("--only", action="append", default=[], help="a product: its key, Naver product id, handle or "
                    "link (repeat for several)")
    ap.add_argument("--json", action="store_true", help="the answers as JSON")
    ap.add_argument("--shops-root", default=P.SHOPS_ROOT)
    add_ref_flags(ap)
    args = ap.parse_args(argv)
    if args.shop not in {s.value for s in shop_stores.StoreId}:
        ap.error(f"unknown shop {args.shop!r} (known: {', '.join(s.value for s in shop_stores.StoreId)})")
    keys: list[str] | None = None
    if args.only or selection_asked(args):            # refs -> keys; an empty selection is exit 2 there
        keys = keys_from_args(ap, args, args.shop, args.only, args.shops_root)
    try:
        ensure_free(args.shops_root, args.shop)
    except ShopBusy as e:
        print(f"sweep: stop: {e}", flush=True)
        return 2
    try:
        answers = run(args.shop, args.shops_root, keys)
    except LedgerError as e:
        print(f"sweep: {e}", file=sys.stderr)
        return 1
    if keys is not None and not answers["scope"]["live"] + answers["scope"]["draft"]:
        print(f"sweep: none of the {len(keys)} named products is published here", file=sys.stderr)
        return 2
    out = write(answers, args.shops_root)
    print(json.dumps(answers, ensure_ascii=False, indent=1) if args.json else "\n".join(table(answers, out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
