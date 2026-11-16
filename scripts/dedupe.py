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
  2b. two purchase-agency imports (구매대행, copies of one foreign listing; 2026-11-15, the wedge pilot) are also
     one product when their titles of LONG_TITLE+ words are alike word for word, or translated apart (alike(): the
     same numbers, club kinds, hand, gender and bag words, WORDS_ALIKE of the words after one spelling each).
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
LONG_TITLE = 12                                 # title words: an identical title this long is one product
ALIKE_MIN_WORDS = 6                             # a shorter title ("라즈러스 웨지 세트") says too little
WORDS_ALIKE = 0.7                               # two agency imports' title words alike (Jaccard) for one product
# an agency import's title is a machine translation of a foreign one; sellers translate one word several ways
# (2026-11-15, the wedge pilot: GoSports in 5 stores, "모래" / "샌드", "남성용" / "남성", "eAj" before it)
_SAME = {"모래": "샌드", "로브": "롭", "남성용": "남성", "여성용": "여성", "오른손잡이용": "오른손", "오른손잡이": "오른손",
         "우측": "오른손", "우타": "오른손", "right": "오른손", "rh": "오른손", "왼손잡이용": "왼손", "왼손잡이": "왼손",
         "좌타": "왼손", "left": "왼손", "lh": "왼손", "남여공용": "남녀공용", "남녀": "남녀공용"}
_FILLER = {"eaj", "골프", "golf", "세트", "set", "또는", "및", "u2013", "u2019", "도", "용", "더", "많은", "위한", "을", "를", "의"}
_KINDS = {"퍼터", "putter", "하이브리드", "hybrid", "드라이버", "driver", "우드", "wood", "아이언", "iron", "웨지", "wedge",
          "유틸", "치퍼", "가방", "bag", "오른손", "왼손", "남성", "여성", "남녀공용", "주니어", "미포함", "제외", "없음",
          "헤드", "중고", "캐디백", "스탠드백"}     # a set with or without its bag (캐디백 미포함) is another product
# Not kinds: colours. A title names its listing's first colour ("Orange Aged 3-5") while its variants hold them all;
# as kinds they split 4 real copies of the store's 2026-11-15 groups to keep one Black Edition apart. The title alone
# cannot tell a colour edition or a set with its bag from a plain one: the report marks the members joined only by
# title words (title_only), to be looked at on their photos before a withdrawal.
REPLACED = "replaced_by:"                       # the withdraw reason job.py writes for a replaced product
TOKEN = re.compile(r"[0-9a-z가-힣]+")
_AGENCY = re.compile(r"구매\s*대행")              # transform's purchase_agency: bought abroad, a copy of one listing


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
    from description_clean import decode_escapes
    name = decode_escapes(listing.get("name") or details.get("name"))   # "u2013" was a number (2013) of the title
    specs = line.get("specs") or {}
    delivery = specs.get("delivery") or details.get("delivery") or {}
    agency = bool(_AGENCY.search(json.dumps([specs.get("specs"), details.get("notice"), delivery.get("policy_text")],
                                            ensure_ascii=False)))
    words = {_SAME.get(w, w) for w in TOKEN.findall(unicodedata.normalize("NFKC", name or "").lower())} - _FILLER
    return {"key": key, "channel": parts[2] if len(parts) > 3 else str((listing.get("store") or {}).get("channel_no")),
            "category": category, "name": name, "tkey": title_key(name, category),
            "price": pricing.get("discounted_price") or pricing.get("sale_price"),
            "grade": (listing.get("store") or {}).get("grade"), "reviews": (listing.get("reviews") or {}).get("count") or 0,
            "first": files[0]["source_sha256"] if files else None, "shas": {f["source_sha256"] for f in files},
            "values": {"/".join(_norm(o) for o in v.get("options") or [v.get("name") or ""]) for v in variants},
            "variants": len(variants), "status": status, "agency": agency, "words": words,
            "numbers": " ".join(sorted(set(re.findall(r"\d+", unicodedata.normalize("NFKC", name or ""))))),
            # numbers standing alone, not inside a model code (a11n, db4p, g440, lh01, xj2): ages, sizes, counts
            "free": {m.group(1) for m in _FREE_NUM.finditer(unicodedata.normalize("NFKC", name or "").lower())}}


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
    # two agency imports with a long title alike word for word: copies of one foreign listing (2026-11-15, the wedge
    # pilot: four sellers of one Lazrus set, 19 words alike, photos re-encoded, variants 0.64 alike). Korean
    # sellers' long titles alike stay unconfirmed (Wilson JGI sizes, the junior sets of one photo)
    long_title = a.get("agency") and b.get("agency") and bool(a["tkey"]) and a["tkey"] == b["tkey"] \
        and len(a["tkey"].split("|", 1)[1].split()) >= LONG_TITLE
    return {"first_photo": first, "photos": photos, "variants": variants,
            "confirmed": first or photos >= PHOTOS_SHARED or variants >= VARIANTS_JACCARD or bool(long_title)}


def alike(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two agency imports of one foreign listing under titles translated apart: the same category, the same numbers
    (lofts, ages, sizes, counts), the same club kinds and hand, and their words alike (WORDS_ALIKE). The numbers and
    kinds keep the versions an agency lists apart (Olimar's putter and hybrid, sizes 3~5 and 5~8) two products."""
    if not (a.get("agency") and b.get("agency")) or a.get("category") != b.get("category"):
        return False
    wa, wb = a.get("words") or set(), b.get("words") or set()
    if min(len(wa), len(wb)) < ALIKE_MIN_WORDS or a.get("numbers") != b.get("numbers") \
            or wa & _KINDS != wb & _KINDS:
        return False
    return len(wa & wb) / len(wa | wb) >= WORDS_ALIKE


# copies under titles that share too few words: every photo and every variant alike (2026-11-15, the lenses: three
# A11N SPORTS wedge sets, one under the model line 핀클리, photos 1.0, variants black / bronze 1.0; the 6-8 challenger
# set of six sellers on one photo). What keeps an agency's versions of one photo apart: the variants (Olimar putter /
# hybrid 0.60, Wilson JGI sizes 0.00-0.75), then the title's dimensions and free numbers, a subset passing ("6-8세"
# against a title naming no age), two different sets clashing (Aged 3-5 / Aged 9-12, 9종 / 12종)
STRONG_PHOTOS = 0.8
_FREE_NUM = re.compile(r"(?<![a-z0-9])(\d+)")
_DIMS = [{"퍼터": "퍼터", "putter": "퍼터", "하이브리드": "하이브리드", "hybrid": "하이브리드", "유틸": "하이브리드",
          "드라이버": "드라이버", "driver": "드라이버", "우드": "우드", "wood": "우드", "아이언": "아이언", "iron": "아이언",
          "웨지": "웨지", "wedge": "웨지", "치퍼": "치퍼"},
         {"오른손": "오른손", "왼손": "왼손"},
         {"남성": "남성", "여성": "여성", "남녀공용": "남녀공용"},
         {"캐디백": "백", "스탠드백": "백", "가방": "백", "bag": "백", "미포함": "없음", "제외": "없음", "없음": "없음"}]


# a model's version word: two titles must agree on it, one naming none is another product too (스릭슨 27ZXI-RKT and its
# LS / MAX / TR of one dealer share the photo and the variant values; QI4D and QI4D MAX)
_MODEL_WORDS = {"max", "맥스", "ls", "tr", "hl", "lite", "라이트", "plus", "플러스", "pro", "프로", "tour", "투어", "sf",
                "lst", "hd", "x", "xd", "ti", "티"}


def _dim(d: dict[str, str], words: set[str]) -> set[str]:
    """A title's values on one dimension; "없음" (미포함, 제외) wins: "캐디백 미포함" is a set without its bag."""
    got = {d[w] for w in words if w in d}
    return {"없음"} if "없음" in got else got


def _clash(x: set, y: set) -> bool:
    return bool(x) and bool(y) and not (x <= y or y <= x)


def strong(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """One product whatever the titles: the same category, photos shared >= STRONG_PHOTOS, variants alike >=
    VARIANTS_JACCARD, and no clash of club kind, hand, gender, bag or free numbers between the titles."""
    if a.get("category") != b.get("category"):
        return False
    s = signals(a, b)
    if s["photos"] < STRONG_PHOTOS or s["variants"] < VARIANTS_JACCARD:
        return False
    wa, wb = a.get("words") or set(), b.get("words") or set()
    if any(_clash(_dim(d, wa), _dim(d, wb)) for d in _DIMS) \
            or wa & _MODEL_WORDS != wb & _MODEL_WORDS:
        return False
    return not _clash(a.get("free") or set(), b.get("free") or set())


def confirm(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    return signals(candidate, existing)["confirmed"] or alike(candidate, existing)


def possible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Step 1: the same title key, two agency imports alike, or every photo and variant alike (strong); another
    store; the price guard. The first photo alone is no match (2026-11-15:
    an agency lists each version of one foreign listing apart under its one photo: Olimar's left-hand putter and
    right-hand hybrid, junior sets of several sizes)."""
    same = bool(a["tkey"]) and a["tkey"] == b["tkey"] or alike(a, b) or strong(a, b)
    return same and a["channel"] != b["channel"] and a["key"] != b["key"] and price_ok(a, b)


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
    buckets: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        if e["tkey"]:
            buckets.setdefault("t:" + e["tkey"], []).append(i)
        if e.get("agency"):                    # alike() needs the same numbers: one bucket per category and numbers
            buckets.setdefault(f"a:{e.get('category')}:{e.get('numbers')}", []).append(i)
        for sha in e.get("shas") or ():        # strong() needs a shared photo: one bucket per category and photo
            buckets.setdefault(f"p:{e.get('category')}:{sha}", []).append(i)
    parent = list(range(len(entries)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for bucket in buckets.values():
        for x, i in enumerate(bucket):
            for j in bucket[x + 1:]:
                if possible(entries[i], entries[j]) and confirm(entries[i], entries[j]):
                    parent[root(i)] = root(j)
    joined: dict[int, list[dict[str, Any]]] = {}
    for i, e in enumerate(entries):
        joined.setdefault(root(i), []).append(e)
    out = []
    for g in joined.values():
        if len(g) > 1:
            out.append(sorted(g, key=lambda e: (-grade_rank(e["grade"]), -(e["reviews"] or 0), -(e["variants"] or 0),
                                                 e["key"])))   # a tie: the copy with more variants
    return sorted(out, key=lambda g: (g[0]["category"], g[0]["tkey"]))


def title_only(group: list[dict[str, Any]]) -> list[str]:
    """The members of a group joined to it by title words alone (alike, long_title): no shared photo, no variants
    alike. These are the ones to look at on their photos before a withdrawal (a colour edition, a set with its bag)."""
    strong: set[str] = set()
    for x, a in enumerate(group):
        for b in group[x + 1:]:
            s = signals(a, b)
            if possible(a, b) and (s["first_photo"] or s["photos"] >= PHOTOS_SHARED or s["variants"] >= VARIANTS_JACCARD):
                strong |= {a["key"], b["key"]}
    return [e["key"] for e in group if e["key"] not in strong]


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
            "by_category": by_cat, "list": found, "title_only": sum(len(title_only(g)) for g in found)}


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
              f"({r['extra_copies']} extra copies); same title in several stores: {r['same_title_groups']} titles; "
              f"joined by title words only (check their photos): {r['title_only']}")
        for cat, c in sorted(r["by_category"].items()):
            print(f"  {cat}: {c['groups']} groups, {c['products']} products")
        if a.list:
            for g in r["list"]:
                weak = set(title_only(g))
                print(f"{g[0]['category']}\t{g[0]['name']}")
                for i, e in enumerate(g):
                    print(f"  {'best' if i == 0 else '    '} {e['key']}\t{e['grade']}\t{e['reviews']} reviews\t"
                          f"{e['price']} KRW\t{e['variants']} variants{'  title only' if e['key'] in weak else ''}")
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
