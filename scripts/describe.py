"""The product's description for the shop: one model request per product, checked and rendered to HTML here.

    .venv/bin/python scripts/describe.py <shop> [--only KEY] [--limit N] [--published] [--force] [--packet]

The owner, 2026-11-10: a minimalist English description in HTML for Shopify's own description field
(descriptionHtml), written by the model API from the product's title, the seller's typed text and the text read from
the seller's images; the script cleans the data before the request and checks the answer after it; one request and
one answer per product (no fix rounds); a product always gets a description, at the least one sentence from its
title.

Before the request (packet): what is sold first (the facts and the options of the variants we publish), the English
the shop already shows (title, brand, spec rows, option values), then the seller's Korean texts and, apart, the
tables read from the images (digits are lost in them, but the set's clubs are listed there), with this removed:
blocks about paid extras, gifts and buyers' reviews, and every line about the country of manufacture. The country is decided here (origin): stated when the sources name one
country, left out and reported when they disagree (the owner, 2026-11-10).

After the answer (settle): each sentence of the intro and each list item is checked alone (no Hangul, no link, phone
or price, no shop talk, no talk about the listing, every number is one the model was given, no country but the
decided one); a failing
highlight or intro sentence is dropped, a failing item of another list drops that list (half a list of what is in
the box misleads). An intro with nothing left is the title as one sentence. The HTML is built here from p, h3, ul,
li with the text escaped: the model never writes markup.

The answers are kept in <shop>/translation/descriptions.jsonl (append-only, the last row of a key stands). A
product with a row is not asked again; a row whose source changed is reported as stale and kept (--force asks
again). Products already in the shop are left alone unless --published or --only names them: a new description
changes the product's publish digest, and the next publish.py run sends it (ask the owner first, JOB_AGENT.md).
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from typing import Any

import shop_stores
import shopify_payload as sp
import translate
from translate import Chain, Model, ProviderDown, TranslateError
from translation_rules import HANGUL_RE

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
PROMPTS = os.path.join(SCRIPTS, "prompts")
FORMAT = "description/1"
STORE = "descriptions.jsonl"
REPORT = "descriptions_report.txt"

EFFORT, EFFORT_ENV = "medium", "DESCRIBE_EFFORT"    # with thinking on: the answer needs the sources compared and
                                                    # the clubs counted. The translation's "low" without thinking
                                                    # made real errors; "medium" was as good as "high" on 35
                                                    # products at two thirds of the price (README, model comparison)
INTRO_MAX, ITEM_MAX, TOTAL_MAX = 400, 220, 1500        # characters of text (Google reads the first 160-500)
OCR_MAX = 12000                                        # characters of image text sent (the longest of 105: 11,410)
TABLES_MAX = 8000                                      # characters of image tables sent

# A kind of product: the Naver leaf categories it covers, its lists (key, heading, most items) and its brief
# (prompts/describe/<name>.md: what each list holds, what a buyer of this kind of product must be told).
# A category with no profile gets `default`: an intro and highlights, nothing about what is in the box.
PROFILES: dict[str, dict[str, Any]] = {
    "golf_set": {"categories": ("50002788",),
                 "lists": (("included", "What's included", 12), ("highlights", "Highlights", 4))},
    "default": {"categories": (), "lists": (("highlights", "Highlights", 4),)},
}


class NoProvider(Exception):
    """No provider answered (all down): the product waits, the run stops (as the translation does)."""


def build_chain(keys: dict[str, str], env: Any = os.environ) -> Chain:
    """translate.py's providers and models (the same keys and .env names), at this stage's effort and with
    thinking on. DESCRIBE_EFFORT in .env changes the effort (low | medium | high | xhigh | max)."""
    effort = (env.get(EFFORT_ENV) or EFFORT).strip().lower()
    models: list[Model] = []
    for provider, name, _ in translate.settings(env):
        if provider == "anthropic" and keys.get(translate.ANTHROPIC_KEY):
            models.append(translate.AnthropicModel(keys[translate.ANTHROPIC_KEY], name, effort, thinking="adaptive"))
        elif provider == "openai" and keys.get(translate.OPENAI_KEY):
            models.append(translate.OpenAIModel(keys[translate.OPENAI_KEY], name, effort))
    if not models:
        raise TranslateError(f"no key in the key file for the providers of {translate.PROVIDERS_ENV}")
    return Chain(models)


def profile_of(category_id: Any) -> tuple[str, dict[str, Any]]:
    for name, p in PROFILES.items():
        if str(category_id or "") in p["categories"]:
            return name, p
    return "default", PROFILES["default"]


def system_prompt(profile: str) -> str:
    return translate._prompt("describe_system.md") + "\n\n" + translate._prompt(os.path.join("describe", f"{profile}.md"))


def schema(profile: dict[str, Any]) -> dict[str, Any]:
    """The answer: the points the sources disagree on (first: the model settles them before it writes), the intro,
    one array per list of the profile."""
    lists = {key: {"type": "array", "items": {"type": "string"}} for key, _, _ in profile["lists"]}
    props = {"conflicts": {"type": "array", "items": {"type": "string"}}, "intro": {"type": "string"}, **lists}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


# ---- before the request: the packet ------------------------------------------------------------------------------

# the country of manufacture, as sellers and Naver's 원산지 row write it -> as the description says it
COUNTRIES = {"일본": "Japan", "중국": "China", "미국": "USA", "베트남": "Vietnam", "대만": "Taiwan", "타이완": "Taiwan",
             "한국": "Korea", "대한민국": "Korea", "태국": "Thailand", "인도네시아": "Indonesia", "멕시코": "Mexico",
             "말레이시아": "Malaysia", "홍콩": "Hong Kong", "japan": "Japan", "china": "China", "usa": "USA",
             "u.s.a": "USA", "vietnam": "Vietnam", "taiwan": "Taiwan", "korea": "Korea", "thailand": "Thailand",
             "indonesia": "Indonesia", "mexico": "Mexico", "malaysia": "Malaysia"}
_COUNTRY_RE = re.compile("|".join(sorted(map(re.escape, COUNTRIES), key=len, reverse=True)), re.I)
_ORIGIN_RE = re.compile(r"제조국|원산지|원산국|생산국|made\s+in", re.I)
_UNSURE_RE = re.compile(r"아닌|아님|아닙|변동|변경|상이|다를|기타|제3국|조립|등")   # "not Japan", "may change", "and others"
_PRODUCED_RE = re.compile(r"에서\s*생산")                                   # "베트남, 타이완, 중국에서생산됩니다"
ORIGIN_LABEL = "원산지"
ORIGIN_WINDOW = 40

# a block of image text (or a line of the seller's text) that is not about the product sold
_EXTRA_RE = re.compile(r"추가\s*구매|추가\s*주문|추가\s*선택|별도\s*구매|별도\s*선택|별도\s*판매|별매|사은품|증정|1\s*\+\s*1")
_REVIEW_RE = re.compile(r"리뷰|후기|REVIEW", re.I)
_MASKED_RE = re.compile(r"[A-Za-z0-9]{2,}\*{2,}")                       # a buyer's masked id in a review screenshot

# a prepared note -> one line for the model (the transform already knows this about the listing)
HINTS = {"paid_addons_left_out": "The seller's texts also offer paid extras: they are not part of this product.",
         "paid_variants_left_out": "The listing also sells other configurations at other prices: only the one under "
                                   "\"What is sold\" is ours.",
         "gift_hidden": "The seller's texts mention gifts: leave them out.",
         "description_covers_several_products": "The seller's texts describe several products: describe only the "
                                                "one in the title.",
         "title_names_one_variant": "The title names one configuration; the buyer's choices are under \"What is "
                                    "sold\"."}


def _countries(text: str) -> set[str]:
    return {COUNTRIES[m.group(0).lower()] for m in _COUNTRY_RE.finditer(text or "")}


def origin(row: str | None, texts: list[str]) -> tuple[str | None, str | None]:
    """(the country to state, why none is stated). One country named by the 원산지 row and by every "made in" /
    제조국 line of the texts: stated. Several, or a line that hedges ("may differ", "not Japan", "and others"): none,
    with the reason for the report. No source names one: (None, None)."""
    found: dict[str, set[str]] = {}
    unsure = False
    if row:
        found["row"] = _countries(row)
        unsure = bool(_UNSURE_RE.search(row)) or not found["row"]         # a country this table does not know
    for text in texts:
        for m in _ORIGIN_RE.finditer(text or ""):
            window = text[m.end():m.end() + ORIGIN_WINDOW].split("\n\n")[0]
            got = _countries(window.split("(")[0]) or _countries(window)    # "중국 (일본 정식 유통제품)": China
            if got:
                found.setdefault("text", set()).update(got)
            if got or re.search("변경|변동|상이", window):                  # "제조국: 변동될 수 있음": nobody knows
                unsure = unsure or bool(_UNSURE_RE.search(window))
        for line in (text or "").splitlines():                            # "... 베트남에서 생산됩니다" (11635694901)
            if _PRODUCED_RE.search(line):
                found.setdefault("text", set()).update(_countries(line))
    named = set().union(*found.values()) if found else set()
    if not named:
        return None, ("origin not stated (hedged)" if unsure else None)
    if len(named) == 1 and not unsure:
        return next(iter(named)), None
    said = "; ".join(f"{k}: {', '.join(sorted(v)) or '-'}" for k, v in sorted(found.items()))
    return None, f"origin not stated ({'hedged' if len(named) == 1 else 'sources disagree'}: {said})"


def _lines_kept(text: str) -> str:
    """The seller's text without the lines on the country of manufacture (origin decides it). A line that marks an
    item as a paid extra or a gift stays: the item is often on the line under it (9266336330: "골프백 별매", then
    the bag), and the label is what tells the model to leave it out."""
    return "\n".join(x for x in (text or "").splitlines()
                     if not _ORIGIN_RE.search(x) and not _PRODUCED_RE.search(x)).strip()


def _is_table(block: dict[str, Any]) -> bool:
    """A table of figures (sent apart: OCR loses digits in them). One or two rows whose cells are mostly Korean
    words are text laid out in columns: "NEW 2019 | 여성 | 카본10pcs | 클럽만" (5479607864: clubs only, no bag),
    "우드:1 | 아이언:7 | S | 퍼터:PT"."""
    if block.get("kind") != "table":
        return False
    rows = (block.get("text") or "").strip().splitlines()
    cells = [c for row in rows for c in row.split("|") if c.strip()]
    return len(rows) > 2 or 2 * sum(1 for c in cells if HANGUL_RE.search(c)) <= len(cells)


def image_text(blocks: list[dict[str, Any]]) -> tuple[str, str, dict[str, int]]:
    """(the image text to send, the image tables to send, what was left out: {extra, review, over}). Tables of
    figures go apart, with a warning: OCR loses digits in them, but they are where the seller lists the clubs of
    the set, and the Naver spec rows are often wrong about that (2026-11-10: "#5 ... SW" in the seller's table,
    "#6 ... AW" in the row). A block headed by an offer of an extra (its first two lines) goes whole; a block that
    names an extra further down stays, with that line: it often holds the set's composition too (11635694901). An
    image that shows buyers' reviews (masked ids with dates: "kdse***23.12.25.") goes whole, the reviews being in
    blocks of their own (11061911792)."""
    reviews = {b.get("image") for b in blocks if len(_MASKED_RE.findall(b.get("text") or "")) >= 2}
    out: dict[bool, list[str]] = {False: [], True: []}
    size = {False: 0, True: 0}
    dropped: dict[str, int] = {}
    for b in blocks:
        text, table = (b.get("text") or "").strip(), _is_table(b)
        why = ("extra" if _EXTRA_RE.search("\n".join(text.splitlines()[:2])) else
               "review" if _REVIEW_RE.search(text) or b.get("image") in reviews else None)
        if why is None:
            text = _lines_kept(text)
            if not text:
                continue
            if size[table] + len(text) > (TABLES_MAX if table else OCR_MAX):
                why = "over"
        if why:
            dropped[why] = dropped.get(why, 0) + 1
            continue
        out[table].append(text)
        size[table] += len(text)
    return "\n\n".join(out[False]), "\n\n".join(out[True]), dropped


def load_blocks(shop_dir: str, product: dict[str, Any]) -> list[dict[str, Any]]:
    """The cleaned OCR blocks of the product's description images (description_image_text.py wrote them)."""
    pointer = product.get("description_images_text") or {}
    if pointer.get("state") not in ("to_translate", "translated") or not pointer.get("ko"):
        return []
    path = os.path.join(shop_dir, pointer["ko"])
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("blocks") or []


def packet(prepared: dict[str, Any], translated: dict[str, Any], blocks: list[dict[str, Any]],
           vendors: dict[str, str] | None = None, tenant: str | None = None) -> dict[str, Any]:
    """What the model is given: {message, title, brand, origin, origin_note, dropped}. The English comes from the
    translation the shop already shows, so the description names the product as its title does."""
    en = sp.English(translated)
    product = sp._twins(prepared["product"], en)
    title, brand = sp.title_vendor(product, en, vendors, tenant)
    notes = {n["code"] for n in prepared.get("notes") or []}
    seller = product.get("description_ko") or ""
    raw_images = "\n\n".join((b.get("text") or "") for b in blocks)
    row = next((s["value_ko"] for s in product.get("specs") or [] if s["label_ko"] == ORIGIN_LABEL), None)
    country, origin_note = origin(row, [seller, raw_images])

    sold: list[str] = []
    free: list[str] = []                                  # a gift fact or group is not what is sold (sp._single)
    for f in product.get("facts") or []:
        line = ": ".join(x for x in (en("fact_label", f.get("label_ko")), en("fact_value", f["value_ko"])) if x)
        (free if sp._GIFT_RE.search((f.get("label_ko") or "") + f["value_ko"]) else sold).append(line)
    picks = [f"{o['name']}: " + " | ".join(v["name"] for v in o["values"])
             for o in (sp._options(product, en)[0] if product.get("options") else [])]
    groups: dict[tuple[str, bool], list[str]] = {}
    for a in product.get("addons") or []:
        gift = bool(sp._GIFT_RE.search((a.get("group_ko") or "") + a["name_ko"]))
        groups.setdefault((en("addon_group", a.get("group_ko")), gift), []).append(en("addon_name", a["name_ko"]))
    for (g, gift), names in groups.items():
        (free if gift else picks).append(f"{g or 'Selection'}: " + " | ".join(names))
    specs = [f"{en('spec_label', s['label_ko'])}: {en('spec_value', s['value_ko'])}"
             for s in product.get("specs") or [] if s["label_ko"] != ORIGIN_LABEL]
    images, tables, dropped = image_text(blocks)

    parts = ["# Product", f"Title: {title}", f"Brand: {brand}", f"Title in Korean: {product['title_ko']}",
             "", "# What is sold"]
    parts += [f"Fixed: {x}" for x in sold]
    parts += [f"The buyer picks: {x}" for x in picks]
    if not sold and not picks:
        parts.append("One configuration, as the title says.")
    parts.append(f"Origin: made in {country}" if country else "Origin: do not state")
    parts += [HINTS[c] for c in HINTS if c in notes]
    if free:
        parts += ["", "# Gifts of the seller: the buyer gets these free. Never list or describe them, and never "
                  "write that the product has no such item"] + free
    if specs:
        parts += ["", "# Specifications (rows typed by the seller)"] + specs
    seller = _lines_kept(seller)
    if seller:
        parts += ["", "# Seller's text (Korean)", seller]
    if images:
        parts += ["", "# Text read from the seller's images (Korean, OCR: letters and digits may be wrong)", images]
    if tables:
        parts += ["", "# Tables read from the seller's images (OCR: a digit or a cell may be lost; rows are cells "
                  "\"a | b | c\")", tables]
    return {"message": "\n".join(parts), "title": title, "brand": brand, "origin": country,
            "origin_note": origin_note, "dropped": dropped}


# ---- after the answer: checks, trimming, the HTML ----------------------------------------------------------------

_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")                 # kana and han (Hangul: translation_rules.HANGUL_RE)
_SHAPES = (("link", re.compile(r"https?://|www\.|\b[\w-]+\.(?:com|net|kr|co|org|jp)\b", re.I)),
           ("phone", re.compile(r"\b\d{2,4}[-.\s]\d{3,4}[-.\s]\d{4}\b")),
           ("price", re.compile(r"[₩$€¥]|\bKRW\b|\bUSD\b|\bwon\b|\d\s*원", re.I)),
           ("markup", re.compile(r"<[a-zA-Z/][^>]*>|\*\*|^#+\s|\.\.\.|…", re.M)))    # tags, markdown, a trailing-off "..."
_BANNED_RE = re.compile(
    r"\b(?:warrant\w*|guarantee\w*|refund\w*|coupon\w*|discount\w*|shipping|delivery|customs|import dut\w+|"
    r"authentic\w*|100% genuine|genuine\w*|parallel[- ]import\w*|gr[ae]y[- ](?:import\w*|market)|"
    r"import(?:s|ed|er|ers)?|official\w*|authori[sz]ed|"
    r"gifts?|giveaway|buy one|same[- ]day|in stock|sold out|limited[- ]time|on sale|sale price|after[- ]sales?|"
    r"naver|smartstore|kakao\w*|reviews?|reviewers?|contact us|call us)\b|1\s*\+\s*1|(?<![\w/])A/S(?![\w/])", re.I)
# talk about the listing instead of the product ("per the specifications", "depending on the option chosen")
_META_RE = re.compile(r"\b(?:listings?|sellers?|the title|specifications? (?:say|list|state|give)s?|per the|according to|"
                      r"(?:is|are|not) (?:mentioned|stated|listed|specified)|unclear|unknown|option chosen|"
                      r"depending on the option|as shown|the sources?|who wants?|looking for|"
                      r"may (?:differ|vary|change)|subject to change|actual product)\b", re.I)
_MADE_RE = re.compile(r"\b(?i:made|manufactured|produced|built|assembled|crafted)\s+(?i:in)\s+(?i:the\s+)?"
                      r"([A-Z][A-Za-z.]*(?:\s[A-Z][a-z]+)?)")
_ORIGIN_NAMES = {"USA": ("usa", "u.s", "u.s.a", "us", "united states", "america")}
# a country (or its adjective) named in any other way: "Japanese-made", "Forged in Japan", "a product of Japan".
# Not "Japan-market model" / "Japan spec": the version made for a market is a fact of its own (the brief).
_ADJECTIVES = {"Japan": "Japanese", "China": "Chinese", "Korea": "Korean", "Vietnam": "Vietnamese",
               "Taiwan": "Taiwanese", "USA": r"American|America|United States|U\.S\.A?\.?", "Thailand": "Thai",
               "Indonesia": "Indonesian", "Mexico": "Mexican", "Malaysia": "Malaysian"}
_NAMED_RE = {c: re.compile(rf"\b(?:{re.escape(c)}|{_ADJECTIVES.get(c, c)})\b(?![- ](?:market|spec))")
             for c in sorted(set(COUNTRIES.values()))}
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_RANGE_RE = re.compile(r"(?<![\d.])#?(\d{1,2})\s*[-~–]\s*#?(\d{1,2})(?![\d.])")
_YEAR2_RE = re.compile(r"(?<!\d)(\d{2})\s*년")                         # 23년 -> 2023 is the same year
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“'])")
_SPACES_RE = re.compile(r"\s+")


def _norm(number: str) -> str:
    return number.rstrip("0").rstrip(".") if "." in number else number.lstrip("0") or "0"


def allowed_numbers(message: str) -> set[str]:
    """The numbers the model was given (as written, "10.50" as "10.5"), the club numbers inside a range it was
    given, and 20yy for a "yy년" of the Korean."""
    out = {_norm(n) for n in _NUMBER_RE.findall(message)}
    for a, b in _RANGE_RE.findall(message):                    # "(7-9,P,S)", "#5~9": the clubs in between
        if int(a) < int(b) <= 13:
            out |= {str(n) for n in range(int(a), int(b) + 1)}
    return out | {f"20{yy}" for yy in _YEAR2_RE.findall(message)}


def _given(number: str, numbers: set[str]) -> bool:
    """The number is one the model was given, or the end of a run OCR glued together ("#418°" is #4, 18°)."""
    return number in numbers or (len(number) >= 2 and any(n.endswith(number) for n in numbers if "." not in n))


def problems(text: str, numbers: set[str], country: str | None) -> list[str]:
    """Why this sentence or list item cannot be shown ([]: it can)."""
    out = []
    if HANGUL_RE.search(text) or _CJK_RE.search(text):
        out.append("not English")
    out += [name for name, rx in _SHAPES if rx.search(text)]
    banned = _BANNED_RE.search(text)
    if banned:
        out.append(f"shop talk: {banned.group(0)}")
    meta = _META_RE.search(text)
    if meta:
        out.append(f"about the listing: {meta.group(0)}")
    strange = sorted({n for n in _NUMBER_RE.findall(text) if not _given(_norm(n), numbers)})
    if strange:
        out.append("numbers not in the source: " + ", ".join(strange))
    for m in _MADE_RE.finditer(text):
        said = m.group(1).split(". ")[0].strip(". ")
        if not country or said.lower() not in (country.lower(), *_ORIGIN_NAMES.get(country, ())):
            out.append(f"origin: {said}")
    if not any(x.startswith("origin: ") for x in out):
        out += [f"origin: {c}" for c, rx in _NAMED_RE.items() if c != country and rx.search(text)]
    return out


def _clean(value: Any) -> str:
    return _SPACES_RE.sub(" ", value).strip() if isinstance(value, str) else ""


def settle(answer: Any, profile: dict[str, Any], pkt: dict[str, Any]) -> dict[str, Any]:
    """The model's answer -> {status, fields, html, dropped, conflicts}: what is shown and what was cut.
    status: ok (as answered) | trimmed (something cut) | fallback (the intro is the title)."""
    answer = answer if isinstance(answer, dict) else {}
    numbers, country = allowed_numbers(pkt["message"]), pkt["origin"]
    dropped: list[dict[str, Any]] = []

    def bad(where: str, text: str) -> bool:
        why = problems(text, numbers, country) or (["too long"] if len(text) > (
            INTRO_MAX if where == "intro" else ITEM_MAX) else [])
        if why:
            dropped.append({"where": where, "text": text[:200], "why": why})
        return bool(why)

    intro: list[str] = []
    for s in _SENTENCE_RE.split(_clean(answer.get("intro"))):
        if not s or bad("intro", s):
            continue
        if len(" ".join(intro + [s])) > INTRO_MAX:
            dropped.append({"where": "intro", "text": s[:200], "why": ["intro too long"]})
            continue
        intro.append(s)
    status = "ok"
    fields: dict[str, Any] = {"intro": " ".join(intro)}
    if not fields["intro"]:
        fields["intro"], status = pkt["title"].rstrip(".") + ".", "fallback"
    for key, _, most in profile["lists"]:
        raw = answer.get(key)
        items = [x for x in map(_clean, raw if isinstance(raw, list) else []) if x]
        if key == "highlights":
            kept = [x for x in items if not bad(key, x)]
        else:                                       # one bad item: the list is not shown (a partial list misleads)
            kept = [] if any([bad(key, x) for x in items]) else items
        if len(kept) > most:
            dropped.append({"where": key, "text": f"{len(kept)} items, {most} at most", "why": ["too many"]})
            kept = kept[:most] if key == "highlights" else []       # the first 12 of 14 would hide the putter
        fields[key] = kept
    order = [key for key, _, _ in profile["lists"]]
    while _size(fields, order) > TOTAL_MAX and any(fields[k] for k in order):
        last = next(k for k in reversed(order) if fields[k])
        dropped.append({"where": last, "text": fields[last].pop()[:200], "why": ["description too long"]})
    if dropped and status == "ok":
        status = "trimmed"
    conflicts = [x for x in map(_clean, answer.get("conflicts") if isinstance(answer.get("conflicts"), list) else [])
                 if x][:10]
    return {"status": status, "fields": fields, "html": render(fields, profile), "dropped": dropped,
            "conflicts": conflicts}


def _size(fields: dict[str, Any], order: list[str]) -> int:
    return len(fields["intro"]) + sum(len(x) for k in order for x in fields[k])


def render(fields: dict[str, Any], profile: dict[str, Any]) -> str:
    """p, h3, ul, li; the text escaped; a line break between blocks (Google gets the text with the tags removed)."""
    out = [f"<p>{html.escape(fields['intro'], quote=False)}</p>"]
    for key, heading, _ in profile["lists"]:
        if fields.get(key):
            out.append(f"<h3>{html.escape(heading, quote=False)}</h3>")
            out.append("<ul>\n" + "\n".join(f"<li>{html.escape(x, quote=False)}</li>" for x in fields[key])
                       + "\n</ul>")
    return "\n".join(out)


# ---- the request -------------------------------------------------------------------------------------------------

def ask(model: "Model | Chain", system: str, message: str, answer_schema: dict[str, Any],
        usage: dict[str, dict[str, int]]) -> tuple[Any, str | None]:
    """One request -> (the parsed answer or None, the model that answered). A provider that is down is skipped (the
    chain rests it); a refusal, a cut answer or broken JSON from the last one is None: the caller's fallback.
    NoProvider: nobody answered at all."""
    providers: list[Model] = model.available() if isinstance(model, Chain) else [model]
    answered: str | None = None
    for n, m in enumerate(providers):
        try:
            reply = m.send(system, [{"role": "user", "content": message}], answer_schema)
        except ProviderDown as e:
            if isinstance(model, Chain):
                model.mark_down(m, str(e))
            continue
        answered = m.name
        mine = usage.setdefault(m.name, {})
        for k, v in reply.usage.items():
            mine[k] = mine.get(k, 0) + v
        if reply.stop_reason in ("refusal", "max_tokens"):
            continue                                 # the next provider tries
        try:
            return json.loads(reply.text), m.name
        except ValueError:
            continue
    if answered is None:
        raise NoProvider("no provider answered")
    return None, answered


# ---- the shop ----------------------------------------------------------------------------------------------------

def load_store(shop_dir: str) -> dict[str, dict[str, Any]]:
    """{key: its last description row}."""
    return _jsonl(os.path.join(shop_dir, "translation", STORE))


def _jsonl(path: str) -> dict[str, dict[str, Any]]:
    """{key: the last row of a .jsonl}; a torn last line (a run killed while writing) is ignored."""
    out: dict[str, dict[str, Any]] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    out[row["key"]] = row
                except (ValueError, KeyError, TypeError):
                    continue
    return out


def describe_product(prepared: dict[str, Any], translated: dict[str, Any], blocks: list[dict[str, Any]],
                     model: "Model | Chain", tenant: str | None, vendors: dict[str, str] | None, now: str,
                     usage: dict[str, dict[str, int]]) -> dict[str, Any]:
    """One product -> its description row (the model is asked once)."""
    name, profile = profile_of((prepared.get("source") or {}).get("category_id"))
    pkt = packet(prepared, translated, blocks, vendors, tenant)
    answer, by = ask(model, system_prompt(name), pkt["message"], schema(profile), usage)
    done = settle(answer, profile, pkt)
    if answer is None:
        done["dropped"].append({"where": "answer", "text": "", "why": ["no usable answer"]})
    return {"format": FORMAT, "key": prepared["key"], "status": done["status"], "profile": name,
            "source_sha256": hashlib.sha256(pkt["message"].encode()).hexdigest(), "fields": done["fields"],
            "html": done["html"], "dropped": done["dropped"], "conflicts": done["conflicts"],
            "origin": pkt["origin"], "origin_note": pkt["origin_note"], "left_out": pkt["dropped"],
            "by": by, "generated": "model", "at": now}


def run(shop: str, model: "Model | Chain | None", shops_root: str = SHOPS_ROOT, only: str | None = None,
        limit: int | None = None, published: bool = False, force: bool = False,
        clock: Any = time.gmtime) -> dict[str, Any]:
    """Describe the shop's products that are ready and translated and have no description yet. `only`: this key
    (a product already in the shop too: naming it is the go-ahead). Without it, products already in the shop are
    left alone unless `published`. `model` None: nothing is asked, the report says what would be."""
    import publish
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    shop_dir = os.path.join(shops_root, shop)
    prepared = _jsonl(os.path.join(shop_dir, "prepared", "products.jsonl"))
    translated = _jsonl(os.path.join(shop_dir, "translation", "translated.jsonl"))
    store = load_store(shop_dir)
    in_shop = set(publish.Shop(shop, shops_root).ledger())
    vendors = publish.vendor_spellings({})
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", clock())
    usage: dict[str, dict[str, int]] = {}
    rows: list[dict[str, Any]] = []
    stale: list[str] = []
    waiting: list[str] = []
    for key in sorted(prepared):
        p, t = prepared[key], translated.get(key) or {}
        if only and key != only:
            continue
        if p.get("status") != "ready" or t.get("status") != "translated":
            continue
        if key in in_shop and not (published or only):
            continue
        blocks = load_blocks(shop_dir, p["product"])
        have = store.get(key)
        if have and not force:
            sha = hashlib.sha256(packet(p, t, blocks, vendors, tenant)["message"].encode()).hexdigest()
            if have.get("source_sha256") != sha:
                stale.append(key)
            continue
        if model is None or (limit is not None and len(rows) >= limit):
            waiting.append(key)
            continue
        row = describe_product(p, t, blocks, model, tenant, vendors, now, usage)
        os.makedirs(os.path.join(shop_dir, "translation"), exist_ok=True)
        with open(os.path.join(shop_dir, "translation", STORE), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        rows.append(row)
    status: dict[str, int] = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    usage = {name: u for name, u in usage.items() if any(u.values())}
    dollars, unpriced = translate.cost(usage)
    lines = [f"describe {shop}: {len(rows)} described: {status or 'none'}; waiting {len(waiting)}; "
             f"stale (source changed, kept) {len(stale)}; tokens {usage or 0}, cost ${dollars:.4f}"
             + (f" (+ {', '.join(unpriced)}: no price set)" if unpriced else "")]
    for r in rows:
        if r["status"] != "ok" or r["origin_note"] or r["conflicts"]:
            lines.append(f"  {r['key']}: {r['status']}"
                         + "".join(f"; cut {d['where']}: {', '.join(d['why'])}" for d in r["dropped"][:4])
                         + (f"; {r['origin_note']}" if r["origin_note"] else "")
                         + (f"; conflicts: {' | '.join(r['conflicts'][:3])}" if r["conflicts"] else ""))
    lines += [f"  stale {k}" for k in stale[:20]]
    if isinstance(model, Chain):
        lines += [f"  {e}" for e in model.events]
    if not only:                                     # a job's one-product run: its event carries this
        with open(os.path.join(shop_dir, "translation", REPORT), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return {"rows": rows, "report": lines, "usage": usage, "waiting": waiting, "stale": stale}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write the shop's product descriptions (one model request a product).")
    ap.add_argument("shop")
    ap.add_argument("--shops-root", default=SHOPS_ROOT)
    ap.add_argument("--only", help="this product key only (a product already in the shop too)")
    ap.add_argument("--limit", type=int, help="ask the model for at most N products")
    ap.add_argument("--published", action="store_true", help="products already in the shop too (the next publish.py "
                    "run then sends them: the owner's go-ahead first)")
    ap.add_argument("--force", action="store_true", help="ask again for a product that has a description")
    ap.add_argument("--offline", action="store_true", help="ask nothing: report what would be asked")
    ap.add_argument("--packet", action="store_true", help="with --only: print what the model would be given")
    args = ap.parse_args(argv)
    shop_dir = os.path.join(args.shops_root, args.shop)
    prepared = _jsonl(os.path.join(shop_dir, "prepared", "products.jsonl"))
    if args.only and args.only not in prepared:
        ap.error(f"--only {args.only}: no such product key in {args.shop} (the whole key, shop:source:channel:id)")
    if args.packet:
        if not args.only:
            ap.error("--packet needs --only KEY")
        import publish
        p = prepared[args.only]
        t = _jsonl(os.path.join(shop_dir, "translation", "translated.jsonl")).get(args.only) or {}
        tenant = shop_stores.STORES[shop_stores.StoreId(args.shop)].publisher
        print(packet(p, t, load_blocks(shop_dir, p["product"]), publish.vendor_spellings({}), tenant)["message"])
        return 0
    try:
        model = None if args.offline else build_chain(translate.keys_from_env())
        r = run(args.shop, model, args.shops_root, only=args.only, limit=args.limit, published=args.published,
                force=args.force)
    except (TranslateError, NoProvider) as e:
        print(f"describe: {e}", file=sys.stderr)
        return 2
    print("\n".join(r["report"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
