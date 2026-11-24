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
  1a. the spaced key (2026-11-17): the title key with adjacent Hangul words joined ('샤프트 선택' = '샤프트선택') and a
     brand+코리아 word dropped when the brand is in the title; the same spaced key is a possible duplicate as well.
  1b. the tail key (2026-11-18): the title key without the title's first word (a store's name in front), when that
     word is no version word and ALIKE_MIN_WORDS words are left; the same tail key is a possible duplicate as well.
  2. confirmed by the collected records: the first photo is the same file (source_sha256), or >= PHOTOS_SHARED of
     the smaller gallery are the same files, or the variants' values agree >= VARIANTS_JACCARD (Jaccard over each
     variant's options, case and spaces ignored; no variants on either side: no signal). Not confirmed: an ordinary
     product (a renamed copy is not caught: a copy, as before).
  2a. strong: any two products with most photos and variants alike and no clash in the titles, or one listing copied
     (same_listing, 2026-11-16: the same first photos in order and the same variants sold).
  2b. two purchase-agency imports (구매대행, copies of one foreign listing; 2026-11-15, the wedge pilot) are also
     one product when their titles of LONG_TITLE+ words are alike word for word, or translated apart (alike(): the
     same numbers, club kinds, hand, gender and bag words, WORDS_ALIKE of the words after one spelling each; with the
     same sets sold, the numbers those sets spell out set aside, 2026-11-17). In a sets_only category two agency
     imports matched by title that sell the same sets are confirmed (sold_equal, 2026-11-17).
  2c. strong by UPC (2026-11-17): two listings with no variants, every photo shared (LEAD_PHOTOS+) and one UPC.
  3. who is better (better(a, b), strict): the store's grade (GRADES), then the product's review count. Price never
     decides (only the x2 guard).
  4. same UPC, no confirmed match (2026-11-17): a hold candidate only (upc_suspect, decide()'s `same_upc`); never a
     duplicate_of / duplicate_better: the job holds the product as a draft for the owner (--dedupe on).
  5. the same Naver catalog or style code, no confirmed match and no same UPC (2026-11-20): a hold candidate only
     (same_item, decide()'s `same_item` / `why`): the page answer's catalog (specs.catalog, else the shop's
     catalog_ids.json backfill; a catalog of more than CATALOG_LOOSE published products ignored) or a maker's style
     code with the same brand (a store-name brand counts as none); no combo set, no clash of kind, bag, hand, gender,
     length, ages or piece counts; held like 4. In apparel also an article code in both products' option values
     (option_codes, 2026-11-24: Adidas IQ2919 listed twice by one seller), one store or two.

Index: built at a job's start from the publication ledger (published products, drafts awaiting review included
(draft first, 2026-11-16), withdrawn ones, and those withdrawn as replaced_by:<key>, which stand for the live end of
their chain (2026-11-16): a copy matching only them is a copy of their replacement) plus the job's own collected
products, each with its latest collected record; add() takes in a product the job collected, so a later seller of it
in the same job is compared with it; replace(old, new) after a replacement keeps old leading to new. decide() gives
the decision for a candidate:
  duplicate_of_withdrawn  a confirmed match was withdrawn by the owner: never taken
  duplicate_of            the candidate is not strictly better than the best confirmed match: not taken
  duplicate_better        it is strictly better: taken, and the match is withdrawn once the candidate is published
                          (job.py: still published, and the new product has no fewer variants)
  None                    no confirmed match (`matches` still lists the title matches and their signals;
                          `same_upc` the products sharing its UPC under upc_suspect: a hold candidate)
"""
from __future__ import annotations

import argparse
import functools
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


@functools.lru_cache(maxsize=None)
def dedupe_category(category: str) -> str:
    """The category dedupe compares: the lowest of a category and those listing_title_rules.json `together` takes
    with it (2026-11-21, the owner: 점퍼 50002798 and 재킷 50002799 feed one section, and Naver files the same
    windbreaker under either leaf: a copy across them is a copy). Any other category: itself."""
    from listing_filter import together
    return min((category, *together(category))) if category else category


def entry(line: dict[str, Any], status: str = "job", catalogs: dict[str, str | None] | None = None) -> dict[str, Any]:
    """What the rule needs of a collected record (job.py's kept line): key, store, category, title key, price, grade,
    review count, photos' source hashes (the first one apart), variant values, variant count; the Naver catalog
    (/products/specs `catalog.id`, else `catalogs`: the shop's backfill by product id) and the style codes."""
    listing = line.get("listing") or {}
    details = line.get("details") or {}
    key = line.get("key") or listing.get("key") or ""
    parts = key.split(":")
    leaf = str(listing.get("category_id") or ((line.get("specs") or {}).get("category") or {}).get("id") or "")
    category = dedupe_category(leaf)                 # the section's (2026-11-21); per-leaf shop rules read `leaf`
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
            "category": category, "leaf": leaf, "name": name, "tkey": title_key(name, category),
            "price": pricing.get("discounted_price") or pricing.get("sale_price"),
            "grade": (listing.get("store") or {}).get("grade"), "reviews": (listing.get("reviews") or {}).get("count") or 0,
            "first": files[0]["source_sha256"] if files else None, "shas": {f["source_sha256"] for f in files},
            "values": {"/".join(_norm(o) for o in v.get("options") or [v.get("name") or ""]) for v in variants},
            "variants": len(variants), "status": status, "agency": agency, "words": words,
            "numbers": " ".join(sorted(set(re.findall(r"\d+", unicodedata.normalize("NFKC", name or ""))))),
            # numbers standing alone, not inside a model code (a11n, db4p, g440, lh01, xj2): ages, sizes, counts
            "free": {m.group(1) for m in _FREE_NUM.finditer(unicodedata.normalize("NFKC", name or "").lower())},
            # the free numbers that count clubs or pieces ("10개", "9종", "14pcs"): a variant spelling them is no excuse
            "counts": {m.group(1) for m in _COUNT_NUM.finditer(unicodedata.normalize("NFKC", name or "").lower())},
            # same_listing (2026-11-16): the first photos in order, the variants the shop sells, the variants' numbers
            "lead": tuple(f["source_sha256"] for f in files[:LEAD_PHOTOS]),
            "sold": _sold(variants, leaf, parts[0] if len(parts) > 3 else "", _axes(specs)),
            "vnums": set(re.findall(r"\d+", unicodedata.normalize("NFKC", " ".join(
                str(o) for v in variants for o in v.get("options") or [v.get("name") or ""])))),
            "skey": spaced_key(name, category),
            "tail": tail_key(name, category),
            "upc": upcs(((details.get("description") or {}).get("text")) or ""),
            "catalog": ((specs.get("catalog") or {}).get("id")) or (catalogs or {}).get(parts[3] if len(parts) > 3
                                                                                       else ""),
            "codes": style_codes(((specs.get("facts") or details.get("facts") or {}).get("model_name") or {})
                                 .get("value") or details.get("model_name"), name),
            "ocodes": option_codes(variants, parts[0] if len(parts) > 3 else "", leaf),
            "brand":_own_brand(((specs.get("facts") or details.get("facts") or {}).get("brand") or {}).get("value")
                                or details.get("brand") or "", (listing.get("store") or details.get("store") or {})
                                .get("name"))}


# ---- one item, by Naver's catalog or the maker's style code (2026-11-20) -------------------------------------
#
# The two exact keys a seller cannot reword (the owner, 2026-11-20: strong flags, no complicated rule). Checked on the
# store's records the same day: the catalog (the page's epInfo.matchingModelId, /products/specs `catalog`) joined 30
# groups of our products across stores; without the loose ones (37 junior sets of every age in one catalog), 196 pairs,
# of the live pairs about 23 of 31 one item the title rule had missed (Yamaha Femina 6 times live, Mutsumi Honma 2-star
# 3, Yamaha CS 3, TaylorMade Glory, Honma Kiwami5, Kolon VWX), the rest versions Naver files together (left / right
# hand, men / women, standard / petite length, junior ages). The style code (521F4SD304, MR322LSJ92_BRWN: the maker's,
# brand apparel; 4 club groups, all one item) joins what Naver files under two catalogs. So a match is a hold
# candidate, never a decision: the job publishes it as a draft held for the owner (OWNER_RULES rule 2).
_COMBO = re.compile(r"조합|\+")
CATALOG_LOOSE = 15                              # more of our products in one catalog: Naver's loose filing, ignored
_CODE_TOKEN = re.compile(r"[A-Za-z0-9]+")
# a shaft's model, not the club's (2026-11-20 review: Cleveland chippers of two heads on KBS MAX105)
_SHAFT_CODE = re.compile(r"^(?:MAX|MODUS|NSPRO|ZELOS|KBS|DG|TOUR|SPEEDER|VENTUS|TENSEI)\d")
_CODE_CUT = re.compile(r"[_\s,/]")              # "MR322LSJ92_BRWN", "GWKW08445 0000", "RWSCN8208,N8208": the code first
# the versions a catalog files together (the 2026-11-20 check): hand, gender, length, beside _DIMS' kinds and bag
_ITEM_DIMS = [{"오른손": "오른손", "right": "오른손", "우타": "오른손", "왼손": "왼손", "left": "왼손", "좌타": "왼손"},
              {"남성": "남성", "남자": "남성", "men": "남성", "여성": "여성", "여자": "여성", "레이디스": "여성",
               "women": "여성", "ladies": "여성"},
              {"쇼트": "쇼트", "short": "쇼트", "쁘띠": "쇼트", "petite": "쇼트", "스탠다드": "표준", "standard": "표준",
               "표준": "표준"}]


def _own_brand(brand: str, store: str | None) -> str:
    """The brand as compared, empty when it is the seller's own store name (resellers write their store as the brand:
    SNGR15702 under 대량가성비추천할인몰, 브론즈폭스, 스완굿즈, 2026-11-20 review)."""
    b, s = _norm(brand), _norm(store or "")
    return "" if not b or (s and (b in s or s in b)) else b


def judged(shop: str, shops_root: str = SHOPS_ROOT) -> list[set[str]]:
    """The groups the owner judged versions, not copies (<shop>/lens/reviewed.jsonl, `lens.py dupes --versions`):
    a same-item pair inside one never comes back (2026-11-20)."""
    out = []
    for row in _jsonl(os.path.join(shops_root, shop, "lens", "reviewed.jsonl")):
        if row.get("verdict") == "versions" and row.get("keys"):
            out.append(set(row["keys"]))
    return out


def is_judged(a: str, b: str, groups: list[set[str]]) -> bool:
    return any(a in g and b in g for g in groups)


def loose_catalogs(entries: Iterable[dict[str, Any]]) -> set[str]:
    """The catalogs holding more than CATALOG_LOOSE of the published products (status "published"): Naver's loose
    filing (one held 37 junior sets of every age), ignored by same_item."""
    counts: dict[str, int] = {}
    for e in entries:
        if e.get("catalog") and e.get("status") == "published":
            counts[e["catalog"]] = counts.get(e["catalog"], 0) + 1
    return {k for k, n in counts.items() if n > CATALOG_LOOSE}


def style_codes(model_name: Any, title: str | None) -> set[str]:
    """The maker's style codes of a listing: its model name's first part and the title's tokens, upper case, 6+
    characters with 3+ digits and a letter, no Hangul (a model name that copies the title gives its codes only)."""
    out = set()
    model = str(model_name or "")
    if model and not re.search(r"[가-힣]", model):
        model = _CODE_CUT.split(model.strip())[0]
    for text in (model, str(title or "")):
        for t in _CODE_TOKEN.findall(unicodedata.normalize("NFKC", text)):
            t = t.upper()
            if len(t) >= 6 and len(re.findall(r"\d", t)) >= 3 and re.search(r"[A-Z]", t) and not _SHAFT_CODE.match(t):
                out.add(t)
    return out


# an apparel article code in the option values (2026-11-24, 9987280360 / 4577303476, the golf pants review): one
# seller (mastersgolf) lists the Adidas article IQ2919 twice, its draft 'IQ2919 블랙 / IS0600 그레이 / IU2826 헴프' and
# its live 'HY0248 그레이5 / IQ2919 블랙' (model name F8_PT_M, no code in the live title). A brand's article code names
# one garment in one colour, so two listings selling it share a variant, one store or two. Apparel only (a category
# with `sizes`): a club's options name its shaft (젝시오14 'MP1400K' in one store's carbon / steel / left-hand sets).
# Measured on the store's ledger the same day: 4 new pairs, each one article sold twice (IQ2919; Adidas GR0759 of one
# seller; J.Lindeberg GWJT10709 of one store, GWJT06333 in a multi-model listing of another)
def option_codes(variants: list[dict[str, Any]], shop: str, leaf: str) -> set[str]:
    """The style codes (style_codes' test) in the option values of an apparel category's variants (else none)."""
    if not variants or not _apparel(shop, leaf):
        return set()
    return style_codes(None, " ".join(str(o) for v in variants for o in v.get("options") or [v.get("name") or ""]))


@functools.lru_cache(maxsize=None)
def _apparel(shop: str, category: str) -> bool:
    """The shop sizes this category's garments (transform_shops `sizes`: apparel)."""
    from transform_shops import ShopRulesMissing, rules_for
    try:
        rules = rules_for(shop).categories.get(category)
    except ShopRulesMissing:
        return False
    return bool(rules and rules.sizes)


_AGE_RE = re.compile(r"(\d{1,2})\s*(?:[~\-]|\s)\s*(\d{1,2})\s*세|(\d{1,2})\s*세\s*(이하|이상)?")


def _ages(title: str) -> set[str]:
    """A junior title's ages, one string per range ("3-5", "3-", "12+"): Naver files one line's ages together."""
    out = set()
    for m in _AGE_RE.finditer(title):
        if m.group(1):
            out.add(f"{int(m.group(1))}-{int(m.group(2))}")
        else:
            out.add(m.group(3) + {"이하": "-", "이상": "+"}.get(m.group(4) or "", ""))
    return out


def same_item(a: dict[str, Any], b: dict[str, Any], loose: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Why a and b look like one item ("catalog <id>", "code <code>", "option code <code>"), None when they do not:
    the same category, another store, the price guard, the same catalog (not a `loose` one) or a style code in common
    (the same brand when both name one), or an apparel article code in both products' option values (the same brand
    when both name one; one store too), and no clash of club kind, hand, gender, length or bag between the titles."""
    if a.get("category") != b.get("category") or a.get("key") == b.get("key"):
        return None
    if not price_ok(a, b):
        return None
    why = None
    same_brand = not a.get("brand") or not b.get("brand") or a["brand"] == b["brand"]
    if a.get("channel") != b.get("channel"):
        if a.get("catalog") and a.get("catalog") == b.get("catalog") and a["catalog"] not in loose:
            why = f"catalog {a['catalog']}"
        else:
            common = (a.get("codes") or set()) & (b.get("codes") or set())
            if common and same_brand:
                why = f"code {sorted(common)[0]}"
    if why is None:
        common = (a.get("ocodes") or set()) & (b.get("ocodes") or set())
        if common and same_brand:
            why = f"option code {sorted(common)[0]}"
    if why is None:
        return None
    if why.startswith("code") and (_COMBO.search(a.get("name") or "") or _COMBO.search(b.get("name") or "")):
        return None                             # "퀀텀 맥스 / 미즈노 JPX925 조합": the code is one part's model
    ta, tb = (unicodedata.normalize("NFKC", x.get("name") or "").lower() for x in (a, b))
    for d in (_DIMS[0], _DIMS[3], *_ITEM_DIMS):  # read inside words too: "남성골프채풀세트", "유틸리티"
        if _clash({v for k, v in d.items() if k in ta}, {v for k, v in d.items() if k in tb}):
            return None
    if _clash(_ages(ta), _ages(tb)):
        return None                             # "3세 이하" / "3-5세": a junior version of another age
    if _clash(a.get("counts") or set(), b.get("counts") or set()):
        return None                             # "4종" / "12종", "5개" / "7개": another set of one line
    return why


# an agency import copies its Amazon spec table into the description ("UPC | 792713117044", "Global Trade
# Identification Number | 00792713117044", several codes in one row; 2026-11-17, the wedge review: 420 of 3173 records)
_UPC = re.compile(r"(?:UPC|Global Trade Identification Number|GTIN)[\s\u200e]*[:|][\s\u200e]*((?:\d{8,14}[ ,/\u200e]*)+)",
                  re.I)


def upcs(text: str) -> set[str]:
    """The UPC / GTIN codes a description's spec rows name, leading zeros stripped (a GTIN-14 is its UPC)."""
    out = set()
    for m in _UPC.finditer(text or ""):
        for n in re.findall(r"\d{8,14}", m.group(1)):
            n = n.lstrip("0")
            if 8 <= len(n) <= 13:
                out.add(n)
    return out


# the spaced key (2026-11-17, the wedge review: Miura Forged Black QPQ 11585620683 / 11585678496, variants 1.0, both
# 1,360,000 KRW, titles apart only by '샤프트 선택' / '샤프트선택' and '미우라코리아'). Only Hangul words next to each
# other are joined: across a digit '(3~5세)' would become '35세' (Olimar ATS 13363834375 / 13420006081 stay apart); a
# brand+코리아 word goes only when the brand itself is in the title (던롭코리아정품 stays)
_IMPORTER = re.compile(r"^([가-힣]{2,})코리아$")
_HANGUL = re.compile(r"^[가-힣]+$")


def spaced_key(name: str | None, category: str | None) -> str | None:
    """'<category>|<sorted tokens>' with runs of adjacent Hangul tokens joined and a brand+코리아 token whose brand is
    a token of the title dropped (None without a token)."""
    toks = TOKEN.findall(unicodedata.normalize("NFKC", name or "").lower())
    toks = [t for t in toks if not ((m := _IMPORTER.match(t)) and m.group(1) in toks)]
    out: list[str] = []
    run = ""
    for t in toks:
        if _HANGUL.match(t):
            run += t
            continue
        if run:
            out.append(run)
            run = ""
        out.append(t)
    if run:
        out.append(run)
    return f"{category or ''}|{' '.join(sorted(set(out)))}" if out else None


# the tail key (2026-11-18, the chipper scroll: the double-sided TTY / PGM chipper 11360733287 / 6414820248, one
# photo each, re-encoded, the same two variants '01.TTY 치퍼' / '02.PGM 치퍼', titles apart only by the store's name in
# front: 홈스월드 / 지아이엘; the store's Gold Bunker junior set 13193526523 / 13293885011 아동 / 유아, Finchley /
# 핀클리 wedges 13830310368 / 13764351072). The first word only, never a version word (a club kind, hand, gender,
# bag, model word, a number: 퍼터 / 웨지, 왼손 / 오른손, MAX / LS, 2025 / 2024), and ALIKE_MIN_WORDS words left (DR / YR /
# BF / SW 여자골프채 여성골프채풀세트 are four lines under one generic title). A match still needs a confirmation
def tail_key(name: str | None, category: str | None) -> str | None:
    """'<category>|<sorted tokens after the first>' when the first token is no version word and ALIKE_MIN_WORDS
    distinct tokens are left (else None)."""
    toks = TOKEN.findall(unicodedata.normalize("NFKC", name or "").lower())
    if len(toks) < 2 or _version_word(toks[0]):
        return None
    rest = set(toks[1:])
    return f"{category or ''}|{' '.join(sorted(rest))}" if len(rest) >= ALIKE_MIN_WORDS else None


def _version_word(token: str) -> bool:
    """A token that names a version, not a seller: a digit in it, a club kind, a hand, gender or bag word, a model's
    version word (or one of their spellings)."""
    word = _SAME.get(token, token)
    return any(c.isdigit() for c in token) or word in _KINDS or word in _MODEL_WORDS \
        or any(word in d for d in _DIMS)


@functools.lru_cache(maxsize=None)
def _sets_only(shop: str, category: str) -> bool:
    """The shop sells this category's sets only (transform_shops sets_only: a single club's variant is left out)."""
    from transform_shops import ShopRulesMissing, rules_for
    try:
        rules = rules_for(shop).categories.get(category)
    except ShopRulesMissing:                            # no rules for this shop: every variant sold
        return False
    return bool(rules and rules.sets_only)


def _axes(specs: dict[str, Any]) -> list[str]:
    """The page's option axes' names, as transform.options_and_variants reads them (club slots count each loft)."""
    return [g.get("name") or "" for g in ((specs.get("options") or {}).get("option_groups") or [])
            if g.get("type") not in ("CUSTOM", "SIMPLE")]


def _sold(variants: list[dict[str, Any]], category: str, shop: str, axes: list[str] | None = None) -> frozenset[str]:
    """The variants' values the shop sells: in a sets_only category without the single clubs transform leaves out
    (Lazrus 13016648376 / 12079160628: 7 collected variants each, 6 alike; the same 3 sets sold). `axes`: the option
    axes' names, so club-slot axes count as transform counts them."""
    opts = [[str(o) for o in v.get("options") or [v.get("name") or ""]] for v in variants]
    if opts and _sets_only(shop, category):
        from transform import single_club
        opts = [o for o in opts if not single_club(o, axes or [])]
    return frozenset("/".join(_norm(o) for o in v) for v in opts)


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
    sold = sold_equal(a, b)
    return {"first_photo": first, "photos": photos, "variants": variants, "sold_equal": sold,
            "confirmed": first or photos >= PHOTOS_SHARED or variants >= VARIANTS_JACCARD or bool(long_title) or sold}


# two agency imports matched by title that sell the same sets in a sets_only category (2026-11-17, the wedge review:
# pron 13408226321 / 13566632407 variants 0.22 over the page list, the sets sold '50 54 58 Degree Legal' and '52 56 60
# Degree Legal' equal; MAZEL 13391641875 / 13204525652, Yamato LH01 13370261145 / 13016883852). Equal, not >= 0.8 (the
# store's data gives the same 3 pairs); a match by photos or variants alone (strong) is not enough here
def sold_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two agency imports of one category, the same title key or alike(), the same non-empty sold sets, and the
    shop sells that category's sets only."""
    if not (a.get("agency") and b.get("agency")) or a.get("category") != b.get("category"):
        return False
    if not a.get("sold") or a.get("sold") != b.get("sold"):
        return False
    if not (bool(a.get("tkey")) and a.get("tkey") == b.get("tkey")) and not alike(a, b):
        return False
    return _sets_only(str(a.get("key") or "").split(":")[0], str(a.get("leaf") or a.get("category") or ""))


def alike(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two agency imports of one foreign listing under titles translated apart: the same category, the same numbers
    (lofts, ages, sizes, counts), the same club kinds and hand, and their words alike (WORDS_ALIKE). The numbers and
    kinds keep the versions an agency lists apart (Olimar's putter and hybrid, sizes 3~5 and 5~8) two products."""
    if not (a.get("agency") and b.get("agency")) or a.get("category") != b.get("category"):
        return False
    wa, wb = a.get("words") or set(), b.get("words") or set()
    na, nb = set((a.get("numbers") or "").split()), set((b.get("numbers") or "").split())
    # the same sets sold: a title's numbers that those sets spell out are the listing's (2026-11-17, the wedge review:
    # AM20XX 13016628843 / 13363498942, Yamato LH01 13204919973 / 13261508936, PGM junior 12556346985 / 13209604493).
    # Only when the sold sets are equal: one agency family selling other sets stays apart (Pinkley '옵션 1' / Black)
    if a.get("sold") and a.get("sold") == b.get("sold"):
        spelt = ((a.get("vnums") or set()) | (b.get("vnums") or set())) - (a.get("counts") or set()) \
            - (b.get("counts") or set())
        na, nb = na - spelt, nb - spelt
    if min(len(wa), len(wb)) < ALIKE_MIN_WORDS or na != nb or wa & _KINDS != wb & _KINDS:
        return False
    return len(wa & wb) / len(wa | wb) >= WORDS_ALIKE


# copies under titles that share too few words: every photo and every variant alike (2026-11-15, the lenses: three
# A11N SPORTS wedge sets, one under the model line 핀클리, photos 1.0, variants black / bronze 1.0; the 6-8 challenger
# set of six sellers on one photo). What keeps an agency's versions of one photo apart: the variants (Olimar putter /
# hybrid 0.60, Wilson JGI sizes 0.00-0.75), then the title's dimensions and free numbers, a subset passing ("6-8세"
# against a title naming no age), two different sets clashing (Aged 3-5 / Aged 9-12, 9종 / 12종)
STRONG_PHOTOS = 0.8
_FREE_NUM = re.compile(r"(?<![a-z0-9])(\d+)")
_COUNT_NUM = re.compile(r"(?<![a-z0-9.])(\d+)\s*(?:개|종|피스|pcs?\b|pieces?\b)")
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
    VARIANTS_JACCARD, and no clash of club kind, hand, gender, bag or free numbers between the titles; or one
    listing copied (same_listing)."""
    if a.get("category") != b.get("category"):
        return False
    s = signals(a, b)
    if s["photos"] < STRONG_PHOTOS:
        return False
    wa, wb = a.get("words") or set(), b.get("words") or set()
    if any(_clash(_dim(d, wa), _dim(d, wb)) for d in _DIMS) \
            or wa & _MODEL_WORDS != wb & _MODEL_WORDS:
        return False
    if s["variants"] >= VARIANTS_JACCARD and not _clash(a.get("free") or set(), b.get("free") or set()):
        return True
    return same_listing(a, b) or same_upc_listing(a, b)


# listings with no variants, every photo shared and one UPC (2026-11-17, the wedge review: agency copies of one Amazon
# listing under titles shuffled apart, GoSports 815898026403, STIX 840244361587, Pinemeadow 091966124145, Majek per
# UPC: 25 pairs, all copies). Not the title's lofts: 52/56/60 is in almost every title and one Majek photo set serves
# its women's, senior and men's sets (UPCs 792713116382 / 792713117044 / 792713116504). Not under LEAD_PHOTOS photos
def same_upc_listing(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """No variants on either side, the same first photo, every photo shared (LEAD_PHOTOS at least), no clash of the
    free numbers, a UPC in common (the kinds and model words: strong)."""
    if a.get("variants") or b.get("variants") or not (a.get("upc") or set()) & (b.get("upc") or set()):
        return False
    if min(len(a.get("shas") or ()), len(b.get("shas") or ())) < LEAD_PHOTOS:
        return False
    s = signals(a, b)
    return s["first_photo"] and s["photos"] == 1.0 and not _clash(a.get("free") or set(), b.get("free") or set())


# one listing copied by several resellers (2026-11-16, the owner's wedge review: Lazrus 13016648376 / 12079160628 /
# 12557380462, three stores, the same 3 photos byte for byte, the same 3 sets sold; 6-7 of 7-11 collected variants
# alike (single wedges by loft, which transform leaves out: 0.64-0.75), titles listing other lofts ("50 52 54 56 58",
# "52, 56, 60도"). The first LEAD_PHOTOS photos the same files in the same order and the sold variants equal; a title's
# numbers that the variants spell out (lofts, ages, club numbers) are the listing's, not another product's. Not a
# colour edition: its variants or its photos differ (BG-100 Black / white, lens/reviewed.jsonl)
LEAD_PHOTOS = 3


def same_listing(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """The same first LEAD_PHOTOS photos in order, photos shared >= STRONG_PHOTOS, the same variants sold (one at
    least), and the titles' numbers not spelt out by the variants not clashing (the kinds and model words: strong)."""
    lead = a.get("lead") or ()
    if len(lead) < LEAD_PHOTOS or lead != b.get("lead") or signals(a, b)["photos"] < STRONG_PHOTOS:
        return False
    if not a.get("sold") or a.get("sold") != b.get("sold"):
        return False
    # a count in a title stays the title's own even when a variant writes that number (2026-11-16: Mizuno JPX QII
    # 13826383159 "골프채 10개" / 13826377851 "9개 세트", variants "7irons(6-9...)" spell 9: not one listing)
    spelt = ((a.get("vnums") or set()) | (b.get("vnums") or set())) - (a.get("counts") or set()) \
        - (b.get("counts") or set())
    return not _clash((a.get("free") or set()) - spelt, (b.get("free") or set()) - spelt)


def confirm(candidate: dict[str, Any], existing: dict[str, Any]) -> bool:
    return signals(candidate, existing)["confirmed"] or alike(candidate, existing)


def possible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Step 1: the same title key, two agency imports alike, or every photo and variant alike (strong); another
    store; the price guard. The first photo alone is no match (2026-11-15:
    an agency lists each version of one foreign listing apart under its one photo: Olimar's left-hand putter and
    right-hand hybrid, junior sets of several sizes)."""
    same = bool(a["tkey"]) and a["tkey"] == b["tkey"] or bool(a.get("skey")) and a.get("skey") == b.get("skey") \
        or bool(a.get("tail")) and a.get("tail") == b.get("tail") or alike(a, b) or strong(a, b)
    return same and a["channel"] != b["channel"] and a["key"] != b["key"] and price_ok(a, b)


# one UPC under titles that agree (2026-11-17, the wedge review: 14 groups of published wedge sets, 25 extra copies,
# Majek / Pinemeadow / Bermuda / STIX / BombTech / Orlimar; their titles shuffled apart, no variants). Never a match
# of step 1: an agency copies the parent listing's UPC onto its versions (Olimar ATS Iron / Putter 810022120200,
# Hireko 4-piece / 3-piece 810022123058, BombTech Silver / Black 850064238204). Only a hold candidate for the owner
# (OWNER_RULES rule 2). The kinds are read from the title only (a description's 'Style Name' row lists every edition)
_UPC_KINDS = (("퍼터", "putter"), ("putter", "putter"), ("드라이버", "driver"), ("driver", "driver"),
              ("하이브리드", "hybrid"), ("hybrid", "hybrid"), ("유틸", "hybrid"), ("아이언", "iron"), ("iron", "iron"),
              ("우드", "wood"), ("wood", "wood"), ("웨지", "wedge"), ("wedge", "wedge"), ("치퍼", "chipper"))
_UPC_PIECES = re.compile(r"(?<![a-z0-9.])(\d)\s*-?\s*(?:개|종|피스|piece|pc|pcs|팩)(?![a-z])")
_COLOURS = {"black": "black", "블랙": "black", "silver": "silver", "실버": "silver", "chrome": "chrome", "크롬": "chrome",
            "satin": "satin", "새틴": "satin", "bronze": "bronze", "브론즈": "bronze", "gold": "gold", "골드": "gold",
            "blue": "blue", "블루": "blue", "red": "red", "레드": "red", "white": "white", "화이트": "white",
            "raw": "raw", "로우": "raw", "copper": "copper", "nickel": "nickel", "gunmetal": "gunmetal",
            "건메탈": "gunmetal"}


def _title_kinds(name: str) -> set[str]:
    t = unicodedata.normalize("NFKC", name or "").lower().replace("유틸리티 웨지", "웨지")
    return {v for k, v in _UPC_KINDS if k in t}


def upc_suspect(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """A UPC in common, the same category, another store, the price guard, the same club kinds named in both titles,
    the same piece count (none is one), the same colour when both titles name one, no clash of hand, gender or bag,
    the same model words, the lofts and ages not clashing (unless the same sets are sold), one sold set inside the
    other."""
    if not (a.get("upc") or set()) & (b.get("upc") or set()) or a.get("category") != b.get("category"):
        return False
    if a.get("channel") == b.get("channel") or a.get("key") == b.get("key") or not price_ok(a, b):
        return False
    ta, tb = a.get("name") or "", b.get("name") or ""
    ka, kb = _title_kinds(ta), _title_kinds(tb)
    if not ka or ka != kb:
        return False
    pieces = [set(_UPC_PIECES.findall(unicodedata.normalize("NFKC", t).lower())) for t in (ta, tb)]
    if pieces[0] != pieces[1]:
        return False
    wa, wb = a.get("words") or set(), b.get("words") or set()
    ca, cb = {_COLOURS[w] for w in wa if w in _COLOURS}, {_COLOURS[w] for w in wb if w in _COLOURS}
    if ca and cb and ca != cb:
        return False
    if any(_clash(_dim(d, wa), _dim(d, wb)) for d in _DIMS[1:]) or wa & _MODEL_WORDS != wb & _MODEL_WORDS:
        return False
    sa, sb = a.get("sold") or frozenset(), b.get("sold") or frozenset()
    short = [{n for n in e.get("free") or set() if len(n) <= 2} for e in (a, b)]
    if _clash(short[0], short[1]) and not (sa and sa == sb):
        return False
    return not (sa and sb and not (sa <= sb or sb <= sa))


def _brief(e: dict[str, Any]) -> dict[str, Any]:
    return {"key": e["key"], "status": e["status"], "grade": e["grade"], "reviews": e["reviews"], "price": e["price"],
            "variants": e["variants"]}


class Index:
    """The products a candidate is compared with, by title key. A product withdrawn as replaced_by:<key> stays in
    (status "replaced"): a copy that matches only it is a copy of the live end of its chain (2026-11-16, the owner's
    wedge review: GoSports 12557420063 not taken as a copy of 13619939279 on 2026-11-15, published as new on
    2026-11-16 once 13619939279 was replaced by 13379851400 and that by 12918511112; A11N 13512885159 the same through
    13405976594 -> 13552318731)."""

    def __init__(self, entries: Iterable[dict[str, Any]] = ()):
        self.by_key: dict[str, dict[str, Any]] = {}
        self.replaced: dict[str, str] = {}          # a key withdrawn as replaced_by: -> its replacement's key
        self.loose: set[str] | None = None          # the loose catalogs, fixed once (loose_catalogs, first use)
        for e in entries:
            self.add(e)

    def add(self, e: dict[str, Any]) -> None:
        if e.get("key") and e.get("tkey"):
            self.by_key[e["key"]] = e

    def drop(self, key: str) -> None:
        self.by_key.pop(key, None)

    def replace(self, old: str, new: str, e: dict[str, Any] | None = None) -> None:
        """`old` withdrawn as replaced_by:`new`: it stays in to lead its copies to `new` (`e`: its entry, when it has
        no entry here yet)."""
        self.replaced[old] = new
        e = self.by_key.get(old) or e
        if e is not None:
            self.add({**e, "status": "replaced", "replaced_by": new})

    def live(self, key: str) -> tuple[str, dict[str, Any] | None]:
        """The end of `key`'s replaced_by chain and its entry (None: not in the index; a cycle ends where it closes)."""
        seen = {key}
        while key in self.replaced and self.replaced[key] not in seen:
            key = self.replaced[key]
            seen.add(key)
        e = self.by_key.get(key)
        return key, (e if e is not None and e.get("status") != "replaced" else None)

    def matches(self, c: dict[str, Any]) -> list[dict[str, Any]]:
        return [e for e in self.by_key.values() if possible(c, e)]

    def same_upc(self, c: dict[str, Any]) -> dict[str, Any]:
        """{same_upc: [keys], upc: [codes]} of the products sharing c's UPC under upc_suspect, published ones first
        (a replaced one stands for its live end), {} when none: a hold candidate, never a decision (2026-11-17)."""
        if not c.get("upc"):
            return {}
        found: dict[str, dict[str, Any]] = {}
        codes: set[str] = set()
        for e in self.by_key.values():
            if not upc_suspect(c, e):
                continue
            target: dict[str, Any] | None = e
            if e["status"] == "replaced":
                target = self.live(e["key"])[1]
            if target is not None and target["key"] != c["key"]:
                found.setdefault(target["key"], target)
                codes |= c["upc"] & e["upc"]
        if not found:
            return {}
        order = {"published": 0, "job": 1, "withdrawn": 2}
        keys = sorted(found, key=lambda k: (order.get(found[k]["status"], 3), k))
        return {"same_upc": keys, "upc": sorted(codes)}

    def same_items(self, c: dict[str, Any]) -> dict[str, Any]:
        """{same_item: [keys], why: [reasons]} of the products that look like c's item (same_item), published ones
        first (a replaced one stands for its live end), {} when none: a hold candidate, never a decision (2026-11-20)."""
        if not c.get("catalog") and not c.get("codes") and not c.get("ocodes"):
            return {}
        if self.loose is None:                      # once, from the published products: a job's own holds and
            self.loose = loose_catalogs(self.by_key.values())   # takes never turn a catalog loose mid-run
        found: dict[str, tuple[dict[str, Any], str]] = {}
        for e in self.by_key.values():
            why = same_item(c, e, self.loose)
            if why is None:
                continue
            target: dict[str, Any] | None = e
            if e["status"] == "replaced":           # the live end must pass the guards itself (as decide(), 11-16)
                target = self.live(e["key"])[1]
                if target is not None and (not price_ok(c, target) or target.get("channel") == c.get("channel")
                                           and not why.startswith("option code")):
                    target = None
            if target is not None and target["key"] != c["key"]:
                found.setdefault(target["key"], (target, why))
        if not found:
            return {}
        order = {"published": 0, "job": 1, "withdrawn": 2}
        keys = sorted(found, key=lambda k: (order.get(found[k][0]["status"], 3), k))
        return {"same_item": keys, "why": [found[k][1] for k in keys]}

    def decide(self, c: dict[str, Any]) -> dict[str, Any]:
        """{decision, of, matches: [{key, status, grade, reviews, price, variants, first_photo, photos, variants_j,
        confirmed[, live, live_price]}]} (decision None: no confirmed match). A confirmed match withdrawn as replaced_by:
        counts as its live replacement (`live` in its row) when the prices are within PRICE_RATIO of the live one
        (else `live_price` False and no match); one whose chain ends outside the index is never let through."""
        found = [(e, signals(c, e)) for e in self.matches(c)]
        rows = []
        confirmed: dict[str, dict[str, Any]] = {}
        lost: list[str] = []                        # chains ending at a product not in the index
        for e, s in found:
            row = {**_brief(e), **{("variants_j" if k == "variants" else k): v for k, v in s.items()}}
            target: dict[str, Any] | None = e
            if e["status"] == "replaced":
                end, target = self.live(e["key"])
                row["live"] = end
                # the price guard holds against the live end too, as at step 1 (2026-11-16, the review of the chain:
                # the match was priced against the replaced product only; the real ones are within it, 13826709716
                # at 44,000 KRW against its live end 13623397378 at 26,160, x1.68)
                if target is not None and not price_ok(c, target):
                    row["live_price"] = False
                    target = None
                    rows.append(row)
                    continue
                if s["confirmed"] and target is None and end != c["key"]:
                    lost.append(end)
            rows.append(row)
            if s["confirmed"] and target is not None and target["key"] != c["key"]:
                confirmed.setdefault(target["key"], target)
        out: dict[str, Any] = {"decision": None, "of": None, "matches": rows}
        withdrawn = [e for e in confirmed.values() if e["status"] == "withdrawn"]
        if withdrawn:
            return {**out, "decision": "duplicate_of_withdrawn", "of": withdrawn[0]["key"]}
        if lost:                                    # its live copy unknown here: not compared, not taken
            return {**out, "decision": "duplicate_of", "of": lost[0]}
        if not confirmed:
            return {**out, **(self.same_upc(c) or self.same_items(c))}
        best = max(confirmed.values(), key=lambda e: (grade_rank(e["grade"]), e["reviews"] or 0))
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
    from shop_files import read_jsonl
    last: dict[Any, dict[str, Any]] = {}             # a row with no key (none written) under None
    # strict (2026-11-16): a bad middle line dropped silently was a published product missing from the index
    for row in read_jsonl(os.path.join(shops_root, shop, "publish", "published.jsonl"), tail_ok=True):
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
    cats = catalogs(shop, shops_root)
    index = Index()
    for key in job_keys:
        if key in records:
            index.add(entry(records[key], "job", cats))
    for key, row in ledger(shop, shops_root).items():
        status = ledger_status(row)
        if status and key in records and (withdrawn or status == "published"):
            index.add(entry(records[key], status, cats))
        elif withdrawn and key and row.get("status") == "withdrawn" and str(row.get("reason") or "").startswith(REPLACED):
            index.replace(key, str(row["reason"])[len(REPLACED):].strip(),
                          entry(records[key], "replaced", cats) if key in records else None)
    return index


CATALOGS_FILE = "catalog_ids.json"               # <shop>/catalog_ids.json: {"ids": {product id: catalog id | null}}


def catalogs(shop: str, shops_root: str = SHOPS_ROOT) -> dict[str, str | None]:
    """The catalog of products collected before /products/specs gave it (2026-11-20): the backfill read once from the
    page answers the server had saved (DEDUPE.md "The catalog backfill"); {} without the file."""
    try:
        with open(os.path.join(shops_root, shop, CATALOGS_FILE), encoding="utf-8") as f:
            return dict(json.load(f).get("ids") or {})
    except (OSError, ValueError):
        return {}


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
        if e.get("skey"):
            buckets.setdefault("k:" + e["skey"], []).append(i)
        if e.get("tail"):
            buckets.setdefault("h:" + e["tail"], []).append(i)
        if e.get("agency"):                    # alike() needs the same numbers: one bucket per category and numbers
            buckets.setdefault(f"a:{e.get('category')}:{e.get('numbers')}", []).append(i)
            if e.get("sold"):                  # or the same sets sold, their numbers set aside (2026-11-17)
                buckets.setdefault(f"s:{e.get('category')}:{sorted(e['sold'])}", []).append(i)
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


def _union(n: int, pairs: Iterable[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in pairs:
        parent[root(i)] = root(j)
    joined: dict[int, list[int]] = {}
    for i in range(n):
        joined.setdefault(root(i), []).append(i)
    return [g for g in joined.values() if len(g) > 1]


def same_upc_groups(entries: list[dict[str, Any]], found: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
    """Hold candidates in the store (2026-11-17): products joined by upc_suspect pairs that no duplicate group holds
    together already; each group best first. Only listed: holding a copy is the owner's word (OWNER_RULES rule 2)."""
    group_of = {e["key"]: n for n, g in enumerate(found) for e in g}
    by_upc: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        for u in e.get("upc") or ():
            by_upc.setdefault(u, []).append(i)
    pairs = set()
    for idx in by_upc.values():
        for x, i in enumerate(idx):
            for j in idx[x + 1:]:
                a, b = entries[i], entries[j]
                same = a["key"] in group_of and group_of.get(a["key"]) == group_of.get(b["key"])
                if not same and upc_suspect(a, b):
                    pairs.add((i, j))
    out = [sorted((entries[i] for i in g), key=lambda e: (-grade_rank(e["grade"]), -(e["reviews"] or 0),
                                                         -(e["variants"] or 0), e["key"]))
           for g in _union(len(entries), pairs)]
    return sorted(out, key=lambda g: (g[0]["category"], g[0]["key"]))


def same_item_groups(entries: list[dict[str, Any]], found: list[list[dict[str, Any]]],
                     judged_groups: list[set[str]] | None = None) -> list[list[dict[str, Any]]]:
    """Hold candidates in the store (2026-11-20): products joined by same_item pairs (the same Naver catalog, not a
    loose one, or a style code) that no duplicate group holds together already; each group best first. Only listed:
    holding a copy is the owner's word (OWNER_RULES rule 2)."""
    group_of = {e["key"]: n for n, g in enumerate(found) for e in g}
    loose = loose_catalogs(entries)
    pairs = set()
    for i, a in enumerate(entries):
        for j in range(i + 1, len(entries)):
            b = entries[j]
            if a["key"] in group_of and group_of.get(a["key"]) == group_of.get(b["key"]):
                continue
            if same_item(a, b, loose) and not is_judged(a["key"], b["key"], judged_groups or []):
                pairs.add((i, j))
    out = []
    for g in _union(len(entries), pairs):           # no chaining: a member pairs with every other of its group
        ranked = sorted((entries[i] for i in g), key=lambda e: (-grade_rank(e["grade"]), -(e["reviews"] or 0),
                                                               -(e["variants"] or 0), e["key"]))
        cliques: list[list[dict[str, Any]]] = []
        for e in ranked:
            home = next((c for c in cliques if all(same_item(e, m, loose)
                                                   and not is_judged(e["key"], m["key"], judged_groups or [])
                                                   for m in c)), None)
            if home is None:
                cliques.append([e])
            else:
                home.append(e)
        out += [c for c in cliques if len(c) > 1]
    return sorted(out, key=lambda g: (g[0]["category"], g[0]["key"]))


# a report-only list (2026-11-17, the wedge review, C41 part 3): two agency imports in a sets_only category, the same
# Korean brand and the same sold sets of 2+ values with digits, no clash of kind, hand, gender or bag: 32 pairs of the
# store's records, 31 copies (PGM, POSSOT, AM20XX, Alvo, XINGGM, Lazrus) and 1 not (MAZEL 'DS-VH 4 Iron' / '7 Iron',
# both held). Never a match nor a confirmation: equal sold sets can coincide, so the owner looks at each
def brand_sold_pairs(entries: list[dict[str, Any]], brands: dict[str, str],
                     found: list[list[dict[str, Any]]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Pairs of products no duplicate group holds together: both agency imports, another store, the price guard, a
    sets_only category, the same brand_ko (`brands`: key -> the prepared brand_ko), the same sold sets with >= 2
    values holding a digit, no _DIMS clash."""
    group_of = {e["key"]: n for n, g in enumerate(found) for e in g}
    buckets: dict[tuple[str, str, frozenset[str]], list[dict[str, Any]]] = {}
    for e in entries:
        brand = (brands.get(e["key"]) or "").strip().casefold()
        if e.get("agency") and brand and sum(1 for v in e.get("sold") or () if re.search(r"\d", v)) >= 2 \
                and _sets_only(e["key"].split(":")[0], e.get("leaf") or e["category"]):
            buckets.setdefault((e["category"], brand, e["sold"]), []).append(e)
    out = []
    for es in buckets.values():
        for x, a in enumerate(es):
            for b in es[x + 1:]:
                if a["channel"] == b["channel"] or not price_ok(a, b) \
                        or (a["key"] in group_of and group_of.get(a["key"]) == group_of.get(b["key"])):
                    continue
                if any(_clash(_dim(d, a.get("words") or set()), _dim(d, b.get("words") or set())) for d in _DIMS):
                    continue
                out.append((a, b) if a["key"] < b["key"] else (b, a))
    return sorted(out, key=lambda p: (p[0]["category"], p[0]["key"], p[1]["key"]))


def _brands(shop: str, shops_root: str) -> dict[str, str]:
    """key -> the prepared product's brand_ko."""
    out = {}
    for p in _jsonl(os.path.join(shops_root, shop, "prepared", "products.jsonl")):
        brand = (p.get("product") or {}).get("brand_ko")
        if p.get("key") and brand:
            out[p["key"]] = str(brand)
    return out


def report(shop: str, shops_root: str = SHOPS_ROOT, category: str | None = None) -> dict[str, Any]:
    index = load(shop, shops_root, withdrawn=False)
    entries = [e for e in index.by_key.values() if category is None or e["category"] == dedupe_category(category)]
    found = groups(entries)
    upc = same_upc_groups(entries, found)
    item = same_item_groups(entries, found, judged(shop, shops_root))
    brand_sold = brand_sold_pairs(entries, _brands(shop, shops_root), found)
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
            "by_category": by_cat, "list": found, "title_only": sum(len(title_only(g)) for g in found),
            "same_upc": upc, "same_upc_extra": sum(len(g) - 1 for g in upc), "brand_sold": brand_sold,
            "same_item": item, "same_item_extra": sum(len(g) - 1 for g in item)}


# ---- --pairs -------------------------------------------------------------------------------------------------

PAIR_EVENTS = ("duplicate_seen", "duplicate_better", "not_taken")


def pairs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every (candidate, match) a job looked at: n, decision, candidate, match and its signals. A same-UPC hold
    candidate (`same_upc`, usually no title match) gives one row per product sharing its UPC, decision
    `same_upc:<that key>`, never confirmed (2026-11-17, the W7 review: the pilot shows these pairs too); a same-item
    one (`same_item`, 2026-11-20) one row per product of its catalog or style code, decision `same_item:<key>`."""
    out: list[dict[str, Any]] = []
    for e in events:
        if e.get("event") not in PAIR_EVENTS or not (e.get("matches") or e.get("same_upc") or e.get("same_item")):
            continue
        decision = e.get("decision") or (e.get("reason") if e["event"] == "not_taken" else
                                         f"duplicate_better:{e.get('replaces')}")
        matches = e.get("matches") or []
        for m in matches:
            out.append({"n": len(out) + 1, "event": e["event"], "decision": decision, "candidate": e["key"], **m})
        seen = {m.get("key") for m in matches}      # a title match sharing the UPC has its row already
        for k in e.get("same_upc") or []:
            if k not in seen:
                out.append({"n": len(out) + 1, "event": e["event"], "decision": f"same_upc:{k}", "candidate": e["key"],
                            "key": k, "status": "", "confirmed": False, "upc": e.get("upc")})
                seen.add(k)
        for k, why in zip(e.get("same_item") or [], e.get("why") or []):    # the same catalog or code (2026-11-20)
            if k not in seen:
                out.append({"n": len(out) + 1, "event": e["event"], "decision": f"same_item:{k}", "candidate": e["key"],
                            "key": k, "status": "", "confirmed": False, "why": why})
                seen.add(k)
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
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
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
                    with Image.open(path) as src:
                        im = src.convert("RGB")
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
        print(f"hold candidates, not groups (the owner decides each): same UPC {len(r['same_upc'])} groups "
              f"({r['same_upc_extra']} extra copies); same brand and sets sold {len(r['brand_sold'])} pairs")
        print(f"same-item candidates, a flag for the agent's review (same Naver catalog or style code, never held): "
              f"{len(r['same_item'])} groups ({r['same_item_extra']} extra copies)")
        if a.list:
            def line(i: int, e: dict[str, Any], weak: set[str] = set()) -> str:
                return (f"  {'best' if i == 0 else '    '} {e['key']}\t{e['grade']}\t{e['reviews']} reviews\t"
                        f"{e['price']} KRW\t{e['variants']} variants{'  title only' if e['key'] in weak else ''}")
            for g in r["list"]:
                weak = set(title_only(g))
                print(f"{g[0]['category']}\t{g[0]['name']}")
                for i, e in enumerate(g):
                    print(line(i, e, weak))
            for g in r["same_upc"]:
                print(f"same UPC {' '.join(sorted(set.intersection(*(set(e['upc']) for e in g)) or g[0]['upc']))}"
                      f"\t{g[0]['category']}\t{g[0]['name']}")
                for i, e in enumerate(g):
                    print(line(i, e))
            for g in r["same_item"]:
                print(f"same item ({'catalog ' + g[0]['catalog'] if g[0].get('catalog') else 'style code'})"
                      f"\t{g[0]['category']}\t{g[0]['name']}")
                for i, e in enumerate(g):
                    print(line(i, e))
            for x, y in r["brand_sold"]:
                print(f"same brand and sets sold\t{x['category']}\t{x['key']}\t{y['key']}\t{x['name']} | {y['name']}")
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
