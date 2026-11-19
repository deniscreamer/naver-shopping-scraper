"""What an improvement changes for the products already in the store, read only (the retro-sweep plan, 2026-11-19):
old model answers a rule, dictionary or prompt improvement now judges wrong (stage 1: the two-brand scan found 98
live titles by hand; re-preparing never reaches a cached answer, since translation/texts.jsonl keeps a title until
translate.plan asks it again and describe.py keeps a description), and the store lagging (stage 3): today's offline
build against what the store last got (publish/sent/), guards, verdicts and groups for the owner.

    .venv/bin/python scripts/sweep.py fairwardgolf [--json]                    # every published product, both parts
    .venv/bin/python scripts/sweep.py fairwardgolf --answers | --store         # one part alone
    .venv/bin/python scripts/sweep.py fairwardgolf --only <ref> [--keys-file F] [--job ID [--event E]]
    .venv/bin/python scripts/sweep.py fairwardgolf --seed-sent [--json]        # the store's "before", stage 2
    .venv/bin/python scripts/sweep.py fairwardgolf --decline --keys-file F [--check CODE] --reason "... (owner <date>)"
    .venv/bin/python scripts/sweep.py fairwardgolf --confirm <group id>        # before a group's resend, stage 4

--decline (stage 4, 2026-11-19) records the owner's "no" to what the last whole run showed: one line a key in
shops/<shop>/sweep/decisions.jsonl ({key, group, output, reason, at}; under the shop's lock); the key is then hidden
from that group (or, with --check, from that check) while its build output stays the one declined, and comes back
when it moves (every output declined for a key stays declined). Nothing else is written; a key in no group of the
last run (or not that check's finding), or whose build moved since, refuses the whole command (exit 2, nothing
written); a torn last line of decisions.jsonl is cut off before the append (named on stderr). --confirm re-builds a group's keys and drops those whose output moved since
the run, or that were sent, withdrawn or declined since: groups/<id>.confirmed.keys and <id>.plan.tsv, the publish
command printed (--force for a .force group); read only otherwise.

--seed-sent (stage 2, 2026-11-19) runs no check: it writes publish/sent/<id>.json for each published product whose
offline build (publish.build) gives the ledger's `output` (seed_sent) and counts the others as no_baseline by reason;
it writes nothing else; it takes the shop's lock while it writes (a job or send refused meanwhile; busy: exit 2).

Scope: every product the ledger (publish/published.jsonl) has as published, live (ACTIVE, or an old row with no
store_status) and drafts (store_status DRAFT) apart; withdrawn products (holds among them) are left out; the ready
products never published are counted, not checked. A selection narrows it; one that names no product is a usage
error (exit 2), never "every product".

The checks (CHECKS; SWEEP.md has the same table, test_sweep.py compares them), pure functions over local files. A
text whose last row a review wrote (by "review-...") is never flagged: only what the model or a rule wrote.

Out: a table a check (live / draft counts, up to EXAMPLES examples: key, handle, the text); then the store part
(store_run): per published product with a baseline (publish.load_sent) same / changed / worse, the changed in groups
(one key, one group: live or draft, the Naver category, the changed fields, the verdict improvement / eyeball, and
".force" when the inputs digest is the ledger's, so publish.py skips it unforced: COST_FORCE), the
worse (GUARDS) in none and printed first, the keys with no baseline one line by reason; per part what is new and
gone since the run before. --json: {"answers", "store"} (one part: its file's shape). Files in
shops/<shop>/sweep/latest/ (shop_files.write_atomic; a part's previous files moved to sweep/prev/ first):
answers.json (every finding), <check>.live.keys / <check>.draft.keys (one key a line, for a --keys-file),
title.set_single/ (its keys per store and Naver category, and the hand titles that match: set_single_files),
store.json and groups/<group id>.keys. A selection writes the same files to sweep/selection/ instead, compared with
nothing (latest/ and prev/ stay the whole shop's). Nothing else is written, the dictionaries
included (Dictionaries(write=False): the default one syncs the live copies). Refused while the shop's lock is held (a job
rewrites the files read here; shop_files.ensure_free: exit 2, the busy line); the lock is not taken, so a job may
start while it reads (a few seconds); --seed-sent takes it (it writes).

Exit codes, as the other read tools: 0 done; 1 a worse product (a guard tripped) or a shop file with a broken line
(LedgerError, the file and line named); 2 usage (an unknown shop, an empty selection, none of it published,
--seed-sent with a part flag, a decline or confirm naming what the last run did not show) or the shop busy.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
import time
from typing import Any, Iterable, Mapping

import describe
import publish as P
import shop_stores
import shopify_payload as sp
import store_diff
import translate
import translation_dicts as D
from brand_fallback import in_title
from shop_files import LedgerError, ShopBusy, append_line, ensure_free, locked, read_jsonl, write_atomic
from shop_view import add_ref_flags, keys_from_args, selection_asked
from translation_rules import HANGUL_RE

CHECKS = (
    ("title.pending_reask", "translate.plan already has the title among its pending items (the next translate.py "
                            "run with the product named asks it again)"),
    ("title.other_brand", "the English title names a dictionary brand that is not the vendor and that the Korean "
                          "title and spec values do not name"),
    ("title.set_single", "the description row's conflicts (describe.py's model) say the title promises a set while "
                         "one club or item is sold, and the English title still says set"),
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
# title.set_single (2026-11-19): describe.py's model writes "conflicts" on a description row when the seller's data
# disagree; on 92 live products (70 junior 50002787, 12 wedge sets 50002783, 10 full sets 50002788) one says the
# title promises a set while one club is sold: "The Title describes a set with driver, irons and putter, but the
# buyer picks one club type: iron, putter or driver" (13693475187), "The title calls it a set, but the seller's texts
# describe a single #7 iron" (13848307900). Kept tight: the clause before "but" / "while" / "whereas" names the title
# and a set (and no single item: "set or a single wedge" is the title offering both), the clause after it one item.
# Quiet the other way round ("a single 60° wedge in the specification rows, while the title ... gives a set of 3":
# the set may be what is sold) and with no title named ("The set composition row lists 3 fairway woods, but the
# buyer picks a single fairway wood")
# The review of the check (2026-11-19): "single", "only one", "one of" alone fired on gaps and mixed option lists
# ("only one loft (52°) is given and the number of wedges is not stated" 13312227353, "the size options are single
# wedges, pairs and three-wedge sets" 13754846756, "single-length shafts", "one of the irons has no loft"): the one
# thing must be a club or an item (single / one / only one + a club noun, a few words between at most, not "of" /
# "the"), or a buyer's pick of one (picks / chooses / sells one loft, size, style, type); quiet when the clause after
# also names sets (plural), pairs or N-piece / N-wedge choices, or the clause before says the count is unclear (13389324355
# "Number of wedges in the set is not clear: the title says set but names a single 52° AW wedge")
SET_SINGLE_SPLIT = re.compile(r",?\s+(?:but|while|whereas)\s+", re.I)
SET_SINGLE_TITLE = re.compile(r"\btitle\b", re.I)
SET_SINGLE_SET = re.compile(r"\bsets?\b", re.I)
_ITEM = r"(?:clubs?|irons?|wedges?|drivers?|putters?|woods?|hybrids?|chippers?|items?|products?)"
_FILL = r"(?:(?!(?:of|the|and|or)\b)[\w#°'’./-]+\s+){0,4}?"
SET_SINGLE_ONE = re.compile(
    rf"\b(?:(?:single|one)\s+{_FILL}{_ITEM}\b"
    rf"|(?:picks?|chooses?|selects?|sells?|sold\s+as|offers?)\s+(?:only\s+)?(?:one|a\s+single)\s+{_FILL}"
    rf"(?:{_ITEM}|lofts?|sizes?|styles?|types?)\b)", re.I)
SET_SINGLE_MANY = re.compile(r"\b(?:sets|pairs?|\d+-(?:piece|wedge|club)s?|[2-9]\s+pieces)\b", re.I)
SET_SINGLE_GAP = re.compile(r"\b(?:not clear|unclear|not stated|not given)\b", re.I)
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


def set_single(conflict: str) -> bool:
    """A describe.py conflict saying the title promises a set while one club or item is sold (SET_SINGLE_*)."""
    parts = SET_SINGLE_SPLIT.split(conflict or "", maxsplit=1)
    if len(parts) != 2:
        return False
    before, after = parts
    return (bool(SET_SINGLE_TITLE.search(before)) and bool(SET_SINGLE_SET.search(before))
            and not SET_SINGLE_ONE.search(before) and not SET_SINGLE_GAP.search(before)
            and bool(SET_SINGLE_ONE.search(after)) and not SET_SINGLE_MANY.search(after))


def set_single_conflict(row: Mapping[str, Any] | None, title: str) -> str | None:
    """The first conflict of the description row that set_single() flags, while the English title still says set
    (a title asked again since names no set: the stale conflict is no finding); None otherwise."""
    if not title or not SET_SINGLE_SET.search(title):
        return None
    conflicts = (row or {}).get("conflicts")
    return next((str(c) for c in conflicts if isinstance(c, str) and set_single(c)), None) \
        if isinstance(conflicts, list) else None


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


def store_of(row: Mapping[str, Any]) -> str:
    """A ledger row's side of the store: "draft" (store_status DRAFT) or "live"."""
    return "draft" if row.get("store_status") == "DRAFT" else "live"


# ---- the owner's declines (stage 4) -----------------------------------------------------------------------------

DECISIONS = "decisions.jsonl"                   # shops/<shop>/sweep/decisions.jsonl, append-only
REASON = re.compile(r"\S.*\(owner \d{4}-\d{2}-\d{2}\)\s*$")   # --reason: the owner's why, then his date
STORE_KIND = "store"                            # a decline of a group (its id is no check code)


def decisions_path(shops_root: str, shop: str) -> str:
    return os.path.join(shops_root, shop, "sweep", DECISIONS)


def declines(shops_root: str, shop: str) -> dict[tuple[str, str], set[str]]:
    """{(key, "store" or a check code): the outputs the owner declined} from decisions.jsonl (a torn last line
    ignored, a broken middle line LedgerError). A key stays hidden there while today's build output is one of them
    (the retro-sweep plan, stage 4, 2026-11-19: a no to what was shown, not to the key). Every output declined for
    a key stays declined: a build that comes back to an earlier declined output is hidden again."""
    out: dict[tuple[str, str], set[str]] = {}
    for r in read_jsonl(decisions_path(shops_root, shop), tail_ok=True):
        if isinstance(r, dict) and r.get("key") and r.get("output"):
            kind = r.get("group") if r.get("group") in CODES else STORE_KIND
            out.setdefault((str(r["key"]), str(kind)), set()).add(str(r["output"]))
    return out


def drop_torn_tail(path: str) -> bytes:
    """Cut a torn last line (no line end after it, not JSON: a run killed while appending) off `path` before an
    append, which would otherwise end it with a line end and make it a broken middle line (LedgerError on every later
    read). The caller holds the shop's lock. -> the bytes dropped (b"" when the file is whole), named on stderr."""
    if not os.path.exists(path):
        return b""
    with open(path, "rb+") as f:
        data = f.read()
        if not data or data.endswith(b"\n"):
            return b""
        cut = data.rfind(b"\n") + 1
        tail = data[cut:]
        try:
            json.loads(tail)
            return b""                              # a whole line missing only its line end: append_line adds it
        except ValueError:
            pass
        f.truncate(cut)
    print(f"warning: {path}: a cut-off last line dropped before the append: {tail[:80]!r}", file=sys.stderr)
    return tail


def today_output(shop_obj: P.Shop, key: str, ids: Mapping[str, Any], ready: set[str]) -> str | None:
    """The output today's offline build gives `key` (publish.build with `ids`), None when it is not ready or does
    not build (a broken shop file still raises)."""
    if key not in ready:
        return None
    try:
        return str(P.build(shop_obj, key, ids)["output"])
    except LedgerError:
        raise
    except Exception:
        return None


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
    where = {k: store_of(ledger[k]) for k in scope}
    findings: dict[str, list[dict[str, Any]]] = {c: [] for c in CODES}

    def hit(code: str, key: str, text: str, **extra: str) -> None:
        findings[code].append({"key": key, "store": where[key], "handle": ledger[key].get("handle"),
                               "text": _clip(text), **extra})

    # title.set_single on a hand title row: never a finding (no --reask reaches it), counted apart for the owner
    # (the review of the check, 2026-11-19: 29 live hand rows from brand fixes still promise a set)
    set_single_hand: list[dict[str, Any]] = []

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
        # 2b. the title promises a set while one club is sold (describe.py's conflicts); its Naver category kept, so
        # the keys split per category (a re-ask's --context is a category's)
        row = descriptions.get(key)
        conflict = set_single_conflict(row, title) if tid is not None else None
        if conflict:
            category = str((p.get("source") or {}).get("category_id") or "?")
            if title_by_model:
                hit("title.set_single", key, conflict, category=category)
            else:
                set_single_hand.append({"key": key, "store": where[key], "handle": ledger[key].get("handle"),
                                        "category": category, "text": _clip(conflict)})
        # 3. Hangul in the English (the title, the options), then the description's
        english: dict[str, str] = {}
        for x in p.get("texts") or []:
            if x["kind"] in ("title", "option_name", "option_value") and (key, x["id"]) not in fixed \
                    and en.get(x["id"]):
                english["title" if x["kind"] == "title" else f"{x['kind']} {x['ko']}"] = en[x["id"]]
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

    # the owner's declines of a check's finding (--decline --check): hidden while the key builds to what he declined
    said = {k: v for k, v in declines(shops_root, shop).items() if k[1] != STORE_KIND and k[0] in where}
    hidden: dict[str, list[str]] = {}
    if said:
        ids = send_ids(store_baselines(shop_obj, ledger)[0], dicts, tenant)
        ready = set(shop_obj.ready())
        today = {k: today_output(shop_obj, k, ids, ready) for k in {k for k, _ in said}}
        for code in CODES:
            gone = {f["key"] for f in findings[code]
                    if (f["key"], code) in said and today.get(f["key"]) in said[(f["key"], code)]}
            if gone:
                hidden[code] = sorted(gone)
                findings[code] = [f for f in findings[code] if f["key"] not in gone]

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
            "declined": hidden, "set_single_hand": set_single_hand, "ocr_errors": errors}


# ---- the store's "before" (stage 2) -------------------------------------------------------------------------

def seed_sent(shop: str, shops_root: str = P.SHOPS_ROOT, keys: Iterable[str] | None = None,
              dicts: D.Dictionaries | None = None) -> dict[str, Any]:
    """publish/sent/<id>.json for every published, not withdrawn product (or `keys` among them) whose offline build
    (publish.build) gives the ledger's `output`: today's build is then what the store has (the retro-sweep plan,
    stage 2, 2026-11-19: no Shopify read; stage 0 measured 2,263 of 2,265 equal). The others are no_baseline with
    the reason. Writes publish/sent/ only, a file only when its text changes (run again: nothing written). The
    vendor spellings are the dictionary's (read only), as the dry run's: a vendor the store spells otherwise is a
    differing output, no baseline (10476142508 LAROUGE, stage 0). main() runs it under the shop's lock: the ledger
    read once at the start stays the ledger while it writes."""
    started = time.monotonic()
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    dicts = dicts or read_dictionaries(DICTS_LIVE)
    ids = {"vendors": P.vendor_spellings({}, list(dicts.entries.get("brand", {}).values())), "tenant": tenant}
    shop_obj = P.Shop(shop, shops_root)
    ledger = shop_obj.ledger()
    wanted = list(keys) if keys is not None else None
    scope = sorted(k for k in (wanted if wanted is not None else ledger) if k in ledger)
    seeded: list[str] = []
    kept: list[str] = []
    no_baseline: dict[str, list[str]] = {}
    for key in scope:
        expected = ledger[key].get("output")
        if not expected:
            no_baseline.setdefault("the ledger row has no output", []).append(key)
            continue
        try:
            built = P.build(shop_obj, key, ids)
        except LedgerError:                         # a broken shop file: exit 1, not a product's reason
            raise
        except Exception as e:                      # a missing file or record, Untranslated, PayloadError
            no_baseline.setdefault(f"not buildable: {type(e).__name__}", []).append(key)
            continue
        if built["output"] != expected:
            no_baseline.setdefault("today's build differs from the ledger", []).append(key)
            continue
        (seeded if P.write_sent(shop_obj, key, built["product_input"]) else kept).append(key)
    folder = shop_obj.path(P.SENT)
    files = [os.path.join(folder, n) for n in os.listdir(folder)] if os.path.isdir(folder) else []
    return {"shop": shop, "seconds": round(time.monotonic() - started, 2), "selection": wanted,
            "published": len(scope), "named_not_published": sorted(set(wanted or ()) - set(ledger)),
            "seeded": len(seeded), "kept": len(kept),
            "no_baseline": {why: {"count": len(ks), "keys": ks} for why, ks in sorted(no_baseline.items())},
            "sent_files": len(files), "sent_bytes": sum(os.path.getsize(f) for f in files)}


def seed_lines(result: dict[str, Any]) -> list[str]:
    nb = result["no_baseline"]
    lines = [f"seed-sent {result['shop']}: {result['published']} published (withdrawn left out): "
             f"{result['seeded']} written, {result['kept']} already there, "
             f"{sum(v['count'] for v in nb.values())} no_baseline"]
    for why, v in nb.items():
        lines.append(f"    {why}: {v['count']} ({', '.join(v['keys'][:EXAMPLES])})")
    lines.append(f"-> publish/sent/: {result['sent_files']} files, {result['sent_bytes'] / 1e6:.1f} MB "
                 f"({result['seconds']} s)")
    return lines


# ---- the store lagging (stage 3) ----------------------------------------------------------------------------

# The guards (worse): a changed product that trips one is left out of every group, printed first, exit 1 (the
# retro-sweep plan, stage 3, 2026-11-19). SWEEP.md "Guards" has the same table (test_sweep.py compares them).
GUARDS = (
    ("not_buildable", "the product no longer builds or is no longer ready (prepared, translated, placed): "
                      "publish.py would leave it as the store has it"),
    ("vendor_lost", "the vendor became empty or the shop's own name where the store has a brand"),
    ("fewer_variants", "fewer variants than the store has"),
    ("fewer_photos", "fewer photos than the store has"),
    ("description_lost", "a description the store has is gone, or today's is a fallback (its intro only the title)"),
)
GUARD_CODES = tuple(c for c, _ in GUARDS)
# the stage-1 checks that judge a text a payload carries: one that fires on the store's and not on today's build is
# an improvement (pending_reask and stale judge the cached answers, not a payload)
TEXT_CHECKS = ("title.other_brand", "text.hangul", "description.old_brand", "description.patterns")
VERDICTS = ("improvement", "eyeball")
COST_FREE = "free: a resend only (store_diff.py --keys-file, then publish.py --keys-file, on the owner's word)"
# today's output differs but the inputs digest is the ledger's (a vendor spelling from the store, a payload code
# change without sp.VERSION, a review file's URL): publish_one skips such a key before it builds (publish.py, the
# digest check), so only --force sends it (the review of stage 3, 2026-11-19)
COST_FORCE = ("free, but publish.py skips it by its inputs digest: a resend needs --force (store_diff.py --keys-file, "
              "then publish.py --keys-file --force, on the owner's word)")
CHANGE_MAX = 300                                # one example's changes, clipped
GROUP_ID_MAX = 80
NO_OUTPUT, NO_FILE, NOT_LEDGER = ("the ledger row has no output", "no publish/sent file",
                                  "the publish/sent file is not the ledger's output")


def as_live(product_input: Mapping[str, Any]) -> dict[str, Any]:
    """A normalized product_input (publish/sent/) in the shape store_diff.QUERY reads from Shopify, so
    store_diff.compare judges a baseline against today's build as it judges the store against it."""
    return {
        **{f: product_input.get(f) for f in ("title", "vendor", "productType", "status", "descriptionHtml")},
        "tags": list(product_input.get("tags") or []),
        "seo": {"title": (product_input.get("seo") or {}).get("title")},
        "options": [{"name": o["name"], "values": [v["name"] for v in o["values"]]}
                    for o in product_input.get("productOptions") or []],
        "variants": {"nodes": [{"sku": v["sku"], "price": v["price"],
                                "selectedOptions": [{"name": o.get("optionName"), "value": o["name"]}
                                                    for o in v.get("optionValues") or []],
                                "metafields": {"nodes": list(v.get("metafields") or [])}}
                               for v in product_input.get("variants") or []]},
        "metafields": {"nodes": list(product_input.get("metafields") or [])}}


def _feed_value(product_input: Mapping[str, Any]) -> str | None:
    """The reviews feed metafield's value ("sha:<hash>" in a normalized input): compare's feed_sha for it."""
    return next((m["value"] for m in product_input.get("metafields") or []
                 if (m["namespace"], m["key"]) == ("custom", "reviews_feed_url")), None)


def field_of(change: str) -> str:
    """store_diff.compare's line (or one of changes()'s) -> the field's name, without values or SKUs."""
    for prefix in ("price ", "option values ", "weight ", "cost "):
        if change.startswith(prefix):
            return prefix.strip()
    if change.startswith("variant "):
        return " ".join(change.split(" ")[:2])
    return change.split(":")[0].removesuffix(" (deleted)")


def _grams(v: Mapping[str, Any]) -> Any:
    return (((v.get("inventoryItem") or {}).get("measurement") or {}).get("weight") or {}).get("value")


def changes(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """What today's build (`new`) changes against the store's (`old`, its publish/sent/ file), both normalized
    product_inputs: store_diff.compare's lines (what Shopify keeps and store_diff reads), then what it does not read
    (a variant's weight, cost and other fields, the SEO description, the photos' alt text, any other key), then
    "other" when the two differ and nothing above names it. Empty when they are equal (for a direct caller:
    store_run calls it only on outputs that differ)."""
    if sp.digest(dict(old)) == sp.digest(dict(new)):
        return []
    out = store_diff.compare(dict(new), as_live(old), _feed_value(new),
                             [f["id"] for f in new.get("files") or []], [f["id"] for f in old.get("files") or []])
    if "descriptionHtml" in out:
        a, b = text_of(old.get("descriptionHtml") or ""), text_of(new.get("descriptionHtml") or "")
        i = next((i for i in range(max(len(a), len(b))) if a[i:i + 1] != b[i:i + 1]), 0)
        out[out.index("descriptionHtml")] = (f"descriptionHtml: {_clip(a[i] if i < len(a) else '')!r} -> "
                                             f"{_clip(b[i] if i < len(b) else '')!r}")
    have = {v["sku"]: v for v in old.get("variants") or []}
    for v in new.get("variants") or []:
        h = have.get(v["sku"])
        if not h:
            continue
        if _grams(h) != _grams(v):
            out.append(f"weight {v['sku']}: {_grams(h)} -> {_grams(v)} g")
        hi, vi = dict(h.get("inventoryItem") or {}), dict(v.get("inventoryItem") or {})
        if hi.get("cost") != vi.get("cost"):
            out.append(f"cost {v['sku']}: {hi.get('cost')} -> {vi.get('cost')}")
        for k in sorted((set(hi) | set(vi)) - {"cost", "measurement"}):
            if hi.get(k) != vi.get(k):
                out.append(f"variant inventoryItem.{k}")
        for k in sorted(set(h) | set(v)):
            if k not in ("sku", "price", "optionValues", "metafields", "inventoryItem") and h.get(k) != v.get(k):
                out.append(f"variant {k}")
    if (old.get("seo") or {}).get("description") != (new.get("seo") or {}).get("description"):
        out.append("seo.description")
    named = {field_of(c) for c in out}
    if not named & {"title", "vendor", "photos"} and \
            [f.get("alt") for f in old.get("files") or []] != [f.get("alt") for f in new.get("files") or []]:
        out.append("photo alt")
    for k in sorted(set(old) | set(new)):
        if k not in ("title", "vendor", "productType", "status", "descriptionHtml", "tags", "seo", "productOptions",
                     "variants", "files", "metafields") and old.get(k) != new.get(k):
            out.append(k)
    return list(dict.fromkeys(out)) or ["other"]


def text_findings(product_input: Mapping[str, Any], vendor: str, prepared: dict[str, Any], brands: Brands) -> set[str]:
    """The TEXT_CHECKS that fire on a payload's texts (its title, option names and values, description), judged
    with today's vendor and Korean as stage 1 judges the cached answers."""
    out = set()
    title = product_input.get("title") or ""
    if title and other_brand(title, vendor, prepared, brands):
        out.add("title.other_brand")
    english = {"title": title}
    for o in product_input.get("productOptions") or []:
        english[f"option_name {o['name']}"] = o["name"]
        for v in o["values"]:
            english[f"option_value {v['name']}"] = v["name"]
    parts = text_of(product_input.get("descriptionHtml") or "")
    korean_left = next((x for x in parts if HANGUL_RE.search(x)), None)
    if korean_left:
        english["description"] = korean_left
    if hangul(english):
        out.add("text.hangul")
    if parts and other_brand(first_sentence(parts), vendor, prepared, brands):
        out.add("description.old_brand")
    if parts and description_patterns(parts):
        out.add("description.patterns")
    return out


def guards(old: Mapping[str, Any], new: Mapping[str, Any], description_row: Mapping[str, Any] | None,
           tenant: str) -> list[str]:
    """The GUARDS (but not_buildable, which needs no build) today's build trips against the store's, "code: why"."""
    out = []
    own = sp.brand_key(tenant)
    had, has = old.get("vendor") or "", new.get("vendor") or ""
    if had and sp.brand_key(had) != own and (not has or sp.brand_key(has) == own):
        out.append(f"vendor_lost: {had!r} -> {has!r}")
    if len(new.get("variants") or []) < len(old.get("variants") or []):
        out.append(f"fewer_variants: {len(old['variants'])} -> {len(new.get('variants') or [])}")
    if len(new.get("files") or []) < len(old.get("files") or []):
        out.append(f"fewer_photos: {len(old['files'])} -> {len(new.get('files') or [])}")
    body_was, body = old.get("descriptionHtml") or "", new.get("descriptionHtml") or ""
    if body_was and not body:
        out.append("description_lost: gone")
    elif body_was and body != body_was and (description_row or {}).get("status") == "fallback" \
            and not was_fallback(old, body):
        out.append("description_lost: a fallback now (its intro only the title)")
    return out


def was_fallback(old: Mapping[str, Any], body: str) -> bool:
    """The store's description was a fallback too (describe.settle: its intro only the title): its first text is
    the store's title, or today's fallback intro, as one sentence. A heuristic: nothing records the store's
    description status (SWEEP.md, Guards)."""
    first = text_of(old.get("descriptionHtml") or "")[:1]
    if not first:
        return False
    today = text_of(body)[:1]
    title = str(old.get("title") or "").rstrip(".") + "."
    return first[0].lower() in {title.lower(), *(t.lower() for t in today)}


def flags(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """What a reader weighs and no verdict decides: the price range, old -> new (a weight fixed moves a price
    lawfully, the plan: flags, not verdicts; each SKU's weight is changes()'s line)."""
    a, b = P.prices_of(dict(old)), P.prices_of(dict(new))
    return [f"price ${a[0]}-{a[1]} -> ${b[0]}-{b[1]}"] if a != b else []


def group_id(store: str, category: str, fields: list[str], verdict: str, force: bool = False) -> str:
    """A group's file name: <live|draft>.<category>.<verdict>[.force].<fields joined by +>, a hash in place of a
    long tail (.force: publish skips its keys by the inputs digest, COST_FORCE)."""
    slug = "+".join(re.sub(r"[^A-Za-z0-9._-]+", "_", f) for f in fields)
    base = f"{store}.{category}.{verdict}{'.force' if force else ''}."
    if len(base) + len(slug) > GROUP_ID_MAX:
        slug = slug[:GROUP_ID_MAX - len(base) - 9] + "-" + hashlib.sha1(slug.encode()).hexdigest()[:8]
    return base + slug


def store_baselines(shop_obj: P.Shop, ledger: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """{key: its publish/sent/ file} for the published keys load_sent trusts, {key: why not} for the others."""
    have: dict[str, dict[str, Any]] = {}
    why: dict[str, str] = {}
    for key in ledger:
        got = P.load_sent(shop_obj, key)
        if got is not None:
            have[key] = got
        elif not ledger[key].get("output"):
            why[key] = NO_OUTPUT
        else:
            why[key] = NOT_LEDGER if os.path.exists(P.sent_path(shop_obj, key)) else NO_FILE
    return have, why


def send_ids(baselines: Mapping[str, Mapping[str, Any]], dicts: D.Dictionaries, tenant: str) -> dict[str, Any]:
    """publish.build's ids as a real send has them, offline: the store's vendor spellings as the baselines show them
    (the ledger's order: first published first, as shopify_admin.vendor_spellings reads the store oldest first),
    then the brand dictionary's (read only), and the tenant. Stage 0 (2026-11-19): the dictionary's alone spells
    10476142508's LAROUGE otherwise than the store, a false vendor change. A gap (SWEEP.md): spellings only withdrawn
    or no-baseline products carry in the store are not read here."""
    store = {k: str(b["vendor"]) for k, b in baselines.items() if b.get("vendor")}
    return {"vendors": P.vendor_spellings(store, list(dicts.entries.get("brand", {}).values())), "tenant": tenant}


def store_run(shop: str, shops_root: str = P.SHOPS_ROOT, keys: Iterable[str] | None = None,
              dicts: D.Dictionaries | None = None) -> dict[str, Any]:
    """The store lagging (stage 3): for each published, not withdrawn product (or `keys` among them) with a baseline
    (publish.load_sent), today's offline build (publish.build) against it, field by field -> store.json's shape:
    same, changed by verdict (worse apart, in no group), the groups (one key, one group: live or draft, the Naver
    category, the changed fields, the verdict), the keys with no baseline by reason. The vendor spellings are the
    store's as the baselines show them (a real send's source: the store first), then the dictionary's (read only):
    a brand the store spells otherwise is no change (10476142508 LAROUGE, stage 0). Reads only; the caller writes."""
    started = time.monotonic()
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    dicts = dicts or read_dictionaries(DICTS_LIVE)
    shop_obj = P.Shop(shop, shops_root)
    prepared_all, _, _ = shop_obj.inputs()
    ledger = shop_obj.ledger()
    ready = set(shop_obj.ready())
    descriptions = describe.load_store(shop_obj.dir)
    brands = Brands(dicts, tenant)
    baselines, no_baseline_why = store_baselines(shop_obj, ledger)
    ids = send_ids(baselines, dicts, tenant)
    said = declines(shops_root, shop)
    hidden: list[dict[str, Any]] = []

    wanted = list(keys) if keys is not None else None
    scope = sorted(k for k in (wanted if wanted is not None else ledger) if k in ledger)
    where = {k: store_of(ledger[k]) for k in scope}
    same: list[str] = []
    worse: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    no_baseline: dict[str, list[str]] = {}
    for key in scope:
        old = baselines.get(key)
        if old is None:
            no_baseline.setdefault(no_baseline_why[key], []).append(key)
            continue
        p = prepared_all.get(key) or {}
        row: dict[str, Any] = {"key": key, "store": where[key], "handle": ledger[key].get("handle"),
               "category": str((p.get("source") or {}).get("category_id") or "?")}
        if key not in ready:
            worse.append({**row, "guards": [f"not_buildable: {shop_obj.not_ready(key)}"], "changes": []})
            continue
        try:
            built = P.build(shop_obj, key, ids)
        except LedgerError:                         # a broken shop file: exit 1, not a product's verdict
            raise
        except Exception as e:                      # a missing file or record, Untranslated, PayloadError
            worse.append({**row, "guards": [f"not_buildable: {type(e).__name__}: {_clip(str(e))}"], "changes": []})
            continue
        if built["output"] == ledger[key]["output"]:
            same.append(key)
            continue
        row["force"] = built["digest"] == ledger[key].get("digest")     # publish_one would skip it unforced
        row["output"], row["ledger"] = built["output"], ledger[key]["output"]     # what --confirm checks again
        new = built["product_input"]
        lines = changes(old, new)
        row["fields"] = sorted({field_of(c) for c in lines})
        row["changes"] = lines
        row["flags"] = flags(old, new) + ([f"review files not uploaded yet: {built['new_files']}"]
                                          if built["new_files"] else [])
        tripped = guards(old, new, descriptions.get(key), tenant)
        if tripped:
            worse.append({**row, "guards": tripped})
            continue
        vendor = translate._brand_en(p, dicts, tenant)
        before, after = text_findings(old, vendor, p, brands), text_findings(new, vendor, p, brands)
        row["improved"] = sorted(before - after)
        row["now_trips"] = sorted(after - before)
        row["flags"] += [f"now trips {c}" for c in row["now_trips"]]
        row["verdict"] = "improvement" if row["improved"] and not row["now_trips"] else "eyeball"
        row["group"] = group_id(row["store"], row["category"], row["fields"], row["verdict"], row["force"])
        if built["output"] in said.get((key, STORE_KIND), ()):     # the owner's no to this very build: hidden
            hidden.append({k: row[k] for k in ("key", "store", "handle", "group", "force")})
            continue
        changed.append(row)

    groups: dict[str, dict[str, Any]] = {}
    for row in changed:
        gid = row["group"]
        g = groups.setdefault(gid, {"id": gid, "store": row["store"], "category": row["category"],
                                    "fields": row["fields"], "verdict": row["verdict"], "force": row["force"],
                                    "cost": COST_FORCE if row["force"] else COST_FREE, "keys": [], "examples": [],
                                    "outputs": {}, "ledger": {}})
        g["keys"].append(row["key"])
        g["outputs"][row["key"]], g["ledger"][row["key"]] = row["output"], row["ledger"]
        if len(g["examples"]) < EXAMPLES:
            g["examples"].append({k: row[k] for k in ("key", "handle", "changes", "flags", "improved")})
    ordered = sorted(groups.values(), key=lambda g: (g["store"] != "live", VERDICTS.index(g["verdict"]), g["force"],
                                                     -len(g["keys"]), g["id"]))
    for g in ordered:
        g["count"] = len(g["keys"])
    return {"shop": shop, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "seconds": round(time.monotonic() - started, 2), "selection": wanted,
            "scope": {"live": sum(1 for k in scope if where[k] == "live"),
                      "draft": sum(1 for k in scope if where[k] == "draft"),
                      "baselines": sum(1 for k in scope if k in baselines),
                      "named_not_published": sorted(set(wanted or ()) - set(ledger))},
            "same": same, "worse": worse,
            "changed": {v: sum(1 for r in changed if r["verdict"] == v) for v in VERDICTS},
            "needs_force": sum(1 for r in changed if r["force"]),
            "no_baseline": {why: {"count": len(ks), "keys": ks} for why, ks in sorted(no_baseline.items())},
            "declined": hidden, "groups": ordered}


def store_lines(result: dict[str, Any], out: str | None) -> list[str]:
    """The store part's table (the worse keys are printed apart, first: worse_lines)."""
    s = result["scope"]
    nb = result["no_baseline"]
    lines = [f"store lagging {result['shop']}: {s['live']} live, {s['draft']} drafts; {s['baselines']} with a "
             f"baseline: {len(result['same'])} same, {sum(result['changed'].values())} changed "
             f"({', '.join(f'{v} {n}' for v, n in result['changed'].items())}; needing --force "
             f"{result['needs_force']}), {len(result['worse'])} worse; "
             f"no baseline {sum(v['count'] for v in nb.values())}"
             + ("" if not nb else " (" + "; ".join(f"{why}: {v['count']}, {', '.join(v['keys'][:EXAMPLES])}"
                                                    for why, v in nb.items()) + ")")]
    hidden = result.get("declined") or []
    if hidden:
        forced = sum(1 for h in hidden if h["force"])
        lines.append(f"declined by the owner, hidden: {len(hidden)} (back when a key's build moves: "
                     f"sweep/decisions.jsonl); a later send of them carries the declined change anyway, the owner's "
                     f"no is not a block (publish.py{f', --force for {forced} of them' if forced else ''}, "
                     f"reprice.py --apply): {', '.join(h['key'] for h in hidden[:EXAMPLES])}"
                     + (" ..." if len(hidden) > EXAMPLES else "") + " (declined.keys)")
    if result["groups"]:
        lines.append(f"{'group':<64}{'count':>6}  verdict")
    for g in result["groups"]:
        lines.append(f"{g['id']:<64}{g['count']:>6}  {g['verdict']}  [{', '.join(g['fields'])}]  {g['cost']}")
        for e in g["examples"]:
            said = "; ".join(e["changes"] + e["flags"] + [f"clears {c}" for c in e["improved"]])
            lines.append(f"    {e['key']}  {e['handle']}  {_clip_to(said, CHANGE_MAX)}")
    if out is not None:
        lines.append(f"-> {out} ({result['seconds']} s)")
    return lines


def worse_lines(result: dict[str, Any]) -> list[str]:
    """The worse keys, each with its guards (printed first; exit 1)."""
    if not result["worse"]:
        return []
    lines = [f"WORSE {len(result['worse'])} (a guard tripped: left out of every group, nothing to send; exit 1)"]
    for w in result["worse"]:
        lines.append(f"    {w['key']}  {w['store']}  {w['handle']}  {'; '.join(w['guards'])}"
                     + (f"  [{_clip_to('; '.join(w['changes']), CHANGE_MAX)}]" if w["changes"] else ""))
    return lines


def _clip_to(text: str, most: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= most else text[:most - 1] + "…"


# ---- latest/ and prev/: what is new and gone since the last run ------------------------------------------------

SET_SINGLE_DIR = "title.set_single"             # <live|draft>.<category>.keys and hand.<live|draft>.keys


def answer_files() -> list[str]:
    return ["answers.json", SET_SINGLE_DIR] + [f"{c}.{s}.keys" for c in CODES for s in ("live", "draft")]


def set_single_files(answers: Mapping[str, Any]) -> dict[str, list[str]]:
    """title.set_single/'s files -> their keys: the findings per store and Naver category (a re-ask's --context is
    a category's: a junior's "single junior golf club" never for a wedge set), and the hand title rows that match
    (hand.<store>.keys: no finding, the owner's new hand row)."""
    out: dict[str, list[str]] = {}
    for f in answers["checks"].get("title.set_single", {}).get("findings", []):
        out.setdefault(f"{f['store']}.{f.get('category') or '?'}.keys", []).append(f["key"])
    for h in answers.get("set_single_hand") or []:
        out.setdefault(f"hand.{h['store']}.keys", []).append(h["key"])
    return out


STORE_FILES = ["store.json", "groups", "declined.keys"]


def _sets_answers(answers: Mapping[str, Any]) -> dict[str, set[str]]:
    return {c: {f["key"] for f in v["findings"]} for c, v in answers["checks"].items()}


def _sets_store(result: Mapping[str, Any]) -> dict[str, set[str]]:
    out = {g["id"]: set(g["keys"]) for g in result["groups"]}
    out["worse"] = {w["key"] for w in result["worse"]}
    out["declined"] = {h["key"] for h in result.get("declined") or []}
    return out


def since(prev: Mapping[str, set[str]] | None, now: Mapping[str, set[str]]) -> dict[str, dict[str, int]] | None:
    """{check or group: {new, gone}} against the previous run's (None: no previous run). A rule change's "new"
    should be what the change meant to do (the plan: regression control)."""
    if prev is None:
        return None
    return {name: {"now": len(now.get(name, set())), "new": len(now.get(name, set()) - prev.get(name, set())),
                   "gone": len(prev.get(name, set()) - now.get(name, set()))}
            for name in sorted(set(prev) | set(now), key=lambda n: (n not in now, n))}


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def clear(folder: str, names: list[str]) -> None:
    """Each of `names` (a file or a folder) removed from `folder`, if there."""
    for name in names:
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)


def target(sweep_dir: str, result: Mapping[str, Any], names: list[str]) -> tuple[str, bool]:
    """Where a part writes -> (folder, compared): a whole run latest/, its previous files moved to prev/ first (since
    prev is counted); a selection (--only, --keys-file, --job) selection/, its own previous files removed, latest/
    and prev/ untouched (a part of the shop against the whole would call every other group gone, then new: the
    review of stage 3, 2026-11-19)."""
    if result.get("selection") is not None:
        out = os.path.join(sweep_dir, "selection")
        clear(out, names)
        return out, False
    rotate(sweep_dir, names)
    return os.path.join(sweep_dir, "latest"), True


def rotate(sweep_dir: str, names: list[str]) -> None:
    """latest/<name> -> prev/<name> for each of `names` (prev's old one removed first; a name latest lacks leaves
    prev without it): one part's files only, so a run of the other part alone keeps this part's prev."""
    latest, prev = os.path.join(sweep_dir, "latest"), os.path.join(sweep_dir, "prev")
    os.makedirs(prev, exist_ok=True)
    clear(prev, names)
    for name in names:
        src = os.path.join(latest, name)
        if os.path.exists(src):
            os.replace(src, os.path.join(prev, name))


def since_lines(title: str, diff: dict[str, dict[str, int]] | None, selection: bool = False) -> list[str]:
    if selection:
        return [f"since prev ({title}): a selection, not compared (written to sweep/selection/, latest/ kept)"]
    if diff is None:
        return [f"since prev ({title}): no previous run"]
    moved = {n: d for n, d in diff.items() if d["new"] or d["gone"]}
    if not moved:
        return [f"since prev ({title}): nothing new, nothing gone"]
    return [f"since prev ({title}):"] + [f"    {n}: {d['now']} now, {d['new']} new, {d['gone']} gone"
                                         for n, d in moved.items()]


def write(answers: dict[str, Any], shops_root: str) -> str:
    """answers.json and the keys files in shops/<shop>/sweep/latest/ -> that folder; the previous ones moved to
    prev/ first, and answers["since_prev"] set from them (per check: now, new, gone). A selection: selection/,
    since_prev None (target)."""
    sweep_dir = os.path.join(shops_root, answers["shop"], "sweep")
    prev = _read_json(os.path.join(sweep_dir, "latest", "answers.json"))
    out, compared = target(sweep_dir, answers, answer_files())
    answers["since_prev"] = since(_sets_answers(prev) if compared and prev and "checks" in prev else None,
                                  _sets_answers(answers))
    os.makedirs(out, exist_ok=True)
    write_atomic(os.path.join(out, "answers.json"), json.dumps(answers, ensure_ascii=False, indent=1) + "\n")
    for code, check in answers["checks"].items():
        for store in ("live", "draft"):
            keys = [f["key"] for f in check["findings"] if f["store"] == store]
            write_atomic(os.path.join(out, f"{code}.{store}.keys"), "".join(k + "\n" for k in keys))
    os.makedirs(os.path.join(out, SET_SINGLE_DIR), exist_ok=True)
    for name, keys in set_single_files(answers).items():
        write_atomic(os.path.join(out, SET_SINGLE_DIR, name), "".join(k + "\n" for k in keys))
    return out


def write_store(result: dict[str, Any], shops_root: str) -> str:
    """store.json and groups/<group id>.keys in shops/<shop>/sweep/latest/ -> that folder; the previous ones moved
    to prev/ first, and result["since_prev"] set from them (per group and for the worse keys: now, new, gone). A
    selection: selection/, since_prev None (target)."""
    sweep_dir = os.path.join(shops_root, result["shop"], "sweep")
    prev = _read_json(os.path.join(sweep_dir, "latest", "store.json"))
    out, compared = target(sweep_dir, result, STORE_FILES)
    result["since_prev"] = since(_sets_store(prev) if compared and prev and "groups" in prev else None,
                                 _sets_store(result))
    os.makedirs(os.path.join(out, "groups"), exist_ok=True)
    write_atomic(os.path.join(out, "store.json"), json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    for g in result["groups"]:
        write_atomic(os.path.join(out, "groups", f"{g['id']}.keys"), "".join(k + "\n" for k in g["keys"]))
    write_atomic(os.path.join(out, "declined.keys"), "".join(h["key"] + "\n" for h in result["declined"]))
    return out


def set_single_lines(answers: Mapping[str, Any]) -> list[str]:
    """title.set_single's split per category, and the hand title rows that match (never a finding)."""
    per: dict[tuple[str, str], int] = {}
    for f in answers["checks"]["title.set_single"]["findings"]:
        per[(f["store"], f.get("category") or "?")] = per.get((f["store"], f.get("category") or "?"), 0) + 1
    lines = []
    if per:
        lines.append(f"    by category ({SET_SINGLE_DIR}/<store>.<category>.keys): "
                     + ", ".join(f"{s} {c} {n}" for (s, c), n in sorted(per.items())))
    hand = answers.get("set_single_hand") or []
    if hand:
        live = sum(1 for h in hand if h["store"] == "live")
        lines.append(f"    hand titles that also match, not findings (no --reask reaches them; the owner: a new hand "
                     f"row): {live} live, {len(hand) - live} drafts ({SET_SINGLE_DIR}/hand.<store>.keys): "
                     + ", ".join(h["key"].rsplit(":", 1)[-1] for h in hand[:EXAMPLES])
                     + (" ..." if len(hand) > EXAMPLES else ""))
    return lines


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
        if code == "title.set_single":
            lines.extend(set_single_lines(answers))
    hidden = answers.get("declined") or {}
    if hidden:
        lines.append(f"declined by the owner, hidden: {sum(map(len, hidden.values()))} ("
                     + ", ".join(f"{c} {len(ks)}" for c, ks in hidden.items())
                     + "; back when a key's build moves: sweep/decisions.jsonl)")
    lines.append(f"OCR sidecars with an error (whole shop): {len(answers['ocr_errors'])}"
                 + (f" ({', '.join(answers['ocr_errors'][:5])})" if answers["ocr_errors"] else ""))
    lines.append(f"-> {out} ({answers['seconds']} s)")
    return lines


# ---- --decline and --confirm (stage 4) --------------------------------------------------------------------------

class Refused(Exception):
    """A decline or confirm naming what the last whole run did not show (exit 2, nothing written)."""


def _latest(shops_root: str, shop: str, name: str) -> dict[str, Any]:
    got = _read_json(os.path.join(shops_root, shop, "sweep", "latest", name))
    if got is None:
        raise Refused(f"no sweep/latest/{name}: run `sweep.py {shop}` first (the owner decides what a whole run "
                      f"showed)")
    return got


def decline(shop: str, shops_root: str, keys: list[str], reason: str, check: str | None = None,
            dicts: D.Dictionaries | None = None) -> list[dict[str, Any]]:
    """The owner's no, one decisions.jsonl line a key: {key, group, output, reason, at}. Without `check`: each key
    must be in a group of the last whole run (latest/store.json) and still build today to the output that run showed
    (what he saw; a build moved since is refused: run sweep again and show him the new change). With `check`: each
    key must be that check's finding in the last whole run (latest/answers.json); the output is today's build (the
    checks build nothing). Any key that does not qualify refuses the whole command (Refused, nothing written). A
    torn last line of decisions.jsonl is cut off first (drop_torn_tail), so the append never makes it a broken
    middle line. The caller holds the shop's lock. -> the rows written."""
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows: list[dict[str, Any]] = []
    bad: list[str] = []
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    shop_obj = P.Shop(shop, shops_root)
    if check is None:
        groups = _latest(shops_root, shop, "store.json").get("groups") or []
        if any("outputs" not in g for g in groups):
            raise Refused(f"the last run kept no outputs (before stage 4): run `sweep.py {shop}` again")
    found: set[str] = set()
    if check is not None:
        found = {f["key"] for f in ((_latest(shops_root, shop, "answers.json").get("checks") or {}).get(check) or {})
                 .get("findings") or []}
    ids = send_ids(store_baselines(shop_obj, shop_obj.ledger())[0], dicts or read_dictionaries(DICTS_LIVE), tenant)
    ready = set(shop_obj.ready())
    if check is None:
        where = {k: g for g in groups for k in g["keys"]}
        for key in keys:
            g = where.get(key)
            if g is None or not (g.get("outputs") or {}).get(key):
                bad.append(f"{key}: in no group of the last whole run (a check's finding: --check <code>)")
                continue
            if today_output(shop_obj, key, ids, ready) != g["outputs"][key]:
                bad.append(f"{key}: its build moved since the run: run `sweep.py {shop}` again and show the owner "
                           f"the new change")
                continue
            rows.append({"key": key, "group": g["id"], "output": g["outputs"][key], "reason": reason, "at": at})
    else:
        for key in keys:
            if key not in found:
                bad.append(f"{key}: not a {check} finding of the last whole run")
                continue
            out = today_output(shop_obj, key, ids, ready)
            if out is None:
                bad.append(f"{key}: does not build today ({shop_obj.not_ready(key) or 'the build raises'})")
                continue
            rows.append({"key": key, "group": check, "output": out, "reason": reason, "at": at})
    if bad:
        raise Refused("nothing declined: " + "; ".join(bad))
    path = decisions_path(shops_root, shop)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    drop_torn_tail(path)
    append_line(path, *(json.dumps(r, ensure_ascii=False) for r in rows))
    return rows


def confirm(shop: str, shops_root: str, gid: str, dicts: D.Dictionaries | None = None) -> dict[str, Any]:
    """A group of the last whole run checked again before its resend: each key re-built, kept only when it is still
    published with the ledger's output of the run (not sent or withdrawn since), not declined, and builds today to
    the output the run showed (what the owner said yes to). Writes groups/<id>.confirmed.keys and <id>.plan.tsv
    (key, active or draft: for shop_view.py check after the send) beside the group's keys; nothing else."""
    g = next((x for x in _latest(shops_root, shop, "store.json").get("groups") or [] if x["id"] == gid), None)
    if g is None:
        raise Refused(f"no group {gid!r} in the last whole run (sweep/latest/store.json)")
    if "outputs" not in g:
        raise Refused(f"the last run kept no outputs (before stage 4): run `sweep.py {shop}` again")
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    shop_obj = P.Shop(shop, shops_root)
    ledger = shop_obj.ledger()
    withdrawn = shop_obj.withdrawn()
    ids = send_ids(store_baselines(shop_obj, ledger)[0], dicts or read_dictionaries(DICTS_LIVE), tenant)
    ready = set(shop_obj.ready())
    said = declines(shops_root, shop)
    kept: list[str] = []
    dropped: dict[str, list[str]] = {}
    for key in g["keys"]:
        shown = g["outputs"].get(key)
        if key not in ledger:
            why = "withdrawn since the run" if key in withdrawn else "not published"
        elif ledger[key].get("output") != g["ledger"].get(key):
            why = "sent since the run"
        elif shown in said.get((key, STORE_KIND), ()):
            why = "declined"
        else:
            now = today_output(shop_obj, key, ids, ready)
            why = "" if now == shown else ("does not build today" if now is None else "its build moved since the run")
        if why:
            dropped.setdefault(why, []).append(key)
        else:
            kept.append(key)
    folder = os.path.join(shops_root, shop, "sweep", "latest", "groups")
    keys_file = os.path.join(folder, f"{gid}.confirmed.keys")
    plan_file = os.path.join(folder, f"{gid}.plan.tsv")
    write_atomic(keys_file, "".join(k + "\n" for k in kept))
    state = "draft" if g["store"] == "draft" else "active"
    write_atomic(plan_file, "".join(f"{k}\t{state}\n" for k in kept))
    return {"shop": shop, "group": gid, "force": bool(g.get("force")), "shown": len(g["keys"]), "kept": kept,
            "dropped": dropped, "keys_file": keys_file, "plan_file": plan_file}


def _shown(path: str) -> str:
    """`path` relative to the working folder (the repo root), absolute when outside it."""
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel


def confirm_lines(result: dict[str, Any]) -> list[str]:
    shop, rel = result["shop"], _shown(result["keys_file"])
    lines = [f"confirm {result['group']}: {len(result['kept'])} of {result['shown']} kept"
             + "".join(f"; {why} {len(ks)}: {', '.join(ks[:EXAMPLES])}" for why, ks in result["dropped"].items())]
    if not result["kept"]:
        return lines + ["nothing left to send"]
    return lines + [
        f"-> {rel}",
        f"on the owner's yes for this group, after state_backup.py as he decided and "
        f".venv/bin/python scripts/store_diff.py {shop} --keys-file {rel} (a key it flags: out of {rel} and the "
        f"plan, told; no --confirm again):",
        f"    .venv/bin/python scripts/publish.py {shop} --keys-file {rel}{' --force' if result['force'] else ''}",
        f"then: .venv/bin/python scripts/sweep.py {shop} (the proof: the group gone, worse 0) and "
        f".venv/bin/python scripts/shop_view.py check {shop} {_shown(result['plan_file'])} (the store states only)"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shop")
    ap.add_argument("--only", action="append", default=[], help="a product: its key, Naver product id, handle or "
                    "link (repeat for several)")
    ap.add_argument("--json", action="store_true", help="the results as JSON")
    ap.add_argument("--answers", action="store_true", help="only the old answers' checks (stage 1)")
    ap.add_argument("--store", action="store_true", help="only the store lagging: today's build against "
                    "publish/sent/, the guards and the groups (stage 3)")
    ap.add_argument("--shops-root", default=P.SHOPS_ROOT)
    ap.add_argument("--seed-sent", action="store_true", help="write publish/sent/<id>.json where today's offline "
                    "build gives the ledger's output (no checks run, nothing else written)")
    ap.add_argument("--decline", action="store_true", help="the owner's no to the named keys as the last whole run "
                    "showed them (their group, or --check's finding): one line a key in sweep/decisions.jsonl, "
                    "with --reason")
    ap.add_argument("--check", choices=CODES, help="with --decline: the check whose finding is declined")
    ap.add_argument("--reason", help="with --decline: the owner's why and the date, \"... (owner <date>)\"")
    ap.add_argument("--confirm", metavar="GROUP", help="a group of the last whole run re-built before its resend: "
                    "groups/<id>.confirmed.keys (and .plan.tsv), the publish command printed")
    add_ref_flags(ap)
    args = ap.parse_args(argv)
    if args.shop not in {s.value for s in shop_stores.StoreId}:
        ap.error(f"unknown shop {args.shop!r} (known: {', '.join(s.value for s in shop_stores.StoreId)})")
    modes = [m for m in ("seed_sent", "decline", "confirm") if getattr(args, m)]
    if len(modes) > 1 or (modes and (args.answers or args.store)):
        ap.error("--seed-sent, --decline and --confirm each run alone (no --answers / --store)")
    if (args.check or args.reason is not None) and not args.decline:
        ap.error("--check and --reason go with --decline")
    if args.decline and not REASON.search(args.reason or ""):
        ap.error("--decline needs --reason \"<the owner's why> (owner YYYY-MM-DD)\"")
    if args.decline and not (args.only or selection_asked(args)):
        ap.error("--decline needs the keys (--keys-file F, --only <ref>, --job ID)")
    if args.confirm and (args.only or selection_asked(args)):
        ap.error("--confirm takes the group's keys itself (no selection)")
    keys: list[str] | None = None
    if args.only or selection_asked(args):            # refs -> keys; an empty selection is exit 2 there
        keys = keys_from_args(ap, args, args.shop, args.only, args.shops_root)
    if args.decline:                                # it writes decisions.jsonl: under the shop's lock
        def say_no() -> int:
            try:
                rows = decline(args.shop, args.shops_root, keys or [], args.reason.strip(), args.check)
            except LedgerError as e:
                print(f"sweep: {e}", file=sys.stderr)
                return 1
            except Refused as e:
                print(f"sweep: {e}", file=sys.stderr)
                return 2
            groups = sorted({r["group"] for r in rows})
            print(f"declined {len(rows)} ({', '.join(groups)}) -> {_shown(decisions_path(args.shops_root, args.shop))}"
                  f": hidden while each builds to what was shown; any later send of them still carries the change")
            return 0
        return locked(args.shops_root, args.shop, "sweep.py --decline", say_no, "sweep")
    if args.confirm:
        try:
            ensure_free(args.shops_root, args.shop)
        except ShopBusy as e:
            print(f"sweep: stop: {e}", flush=True)
            return 2
        try:
            confirmed = confirm(args.shop, args.shops_root, args.confirm)
        except LedgerError as e:
            print(f"sweep: {e}", file=sys.stderr)
            return 1
        except Refused as e:
            print(f"sweep: {e}", file=sys.stderr)
            return 2
        print(json.dumps(confirmed, ensure_ascii=False, indent=1) if args.json else "\n".join(confirm_lines(confirmed)))
        return 0
    if args.seed_sent:                              # it writes: under the shop's lock for its ~14 s (2026-11-19), so
        def seed() -> int:                          # no send can write a newer file it would then overwrite
            try:
                seeded = seed_sent(args.shop, args.shops_root, keys)
            except LedgerError as e:
                print(f"sweep: {e}", file=sys.stderr)
                return 1
            if keys is not None and not seeded["published"]:
                print(f"sweep: none of the {len(keys)} named products is published here", file=sys.stderr)
                return 2
            print(json.dumps(seeded, ensure_ascii=False, indent=1) if args.json else "\n".join(seed_lines(seeded)))
            return 0
        return locked(args.shops_root, args.shop, "sweep.py --seed-sent", seed, "sweep")
    both = args.answers == args.store                 # neither flag or both: the default, both parts
    try:
        ensure_free(args.shops_root, args.shop)
    except ShopBusy as e:
        print(f"sweep: stop: {e}", flush=True)
        return 2
    dicts = read_dictionaries(DICTS_LIVE)
    try:
        answers = run(args.shop, args.shops_root, keys, dicts) if both or args.answers else None
        store = store_run(args.shop, args.shops_root, keys, dicts) if both or args.store else None
    except LedgerError as e:
        print(f"sweep: {e}", file=sys.stderr)
        return 1
    scope = (answers or store or {})["scope"]
    if keys is not None and not scope["live"] + scope["draft"]:
        print(f"sweep: none of the {len(keys)} named products is published here", file=sys.stderr)
        return 2
    lines: list[str] = []
    if store is not None:
        lines += worse_lines(store)                 # the worse first, whatever else is printed
    if answers is not None:
        out = write(answers, args.shops_root)
        lines += table(answers, out) + since_lines("checks", answers["since_prev"], keys is not None)
    if store is not None:
        out = write_store(store, args.shops_root)
        lines += store_lines(store, out) + since_lines("groups", store["since_prev"], keys is not None)
    if args.json:
        print(json.dumps({"answers": answers, "store": store} if both else answers or store, ensure_ascii=False,
                         indent=1))
    else:
        print("\n".join(lines))
    return 1 if store is not None and store["worse"] else 0


if __name__ == "__main__":
    sys.exit(main())
