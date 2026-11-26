"""Korean apparel sizes -> US sizes, per product (the owner, 2026-11-19; the doc: scripts/SIZES.md).

Pure and offline. `resolve()` takes what one prepared product says about its sizes and returns the size option's US
values, the Korean value each came from, and the seller's garment measurements; transform.prepare stores it as
product.sizes (CategoryRules.sizes names the profile), shopify_payload shows it (the option values, the size chart
block, the variants' and the product's fairwardgolf metafields). The Korean values never reach the storefront.

Inputs (each optional except the options):
  options        the prepared options [{name_ko, values_ko}]: the size option is found by its values, not its name
                 (13665521998 "PIL[핑크]" holds XS-L);
  texts          the description's text lines and the OCR rows of its images: the seller's own size chart;
  brand, title   for a brand row (the profile's "brands");
  profile        the garment kind (size_profiles/<name>.json: its fallback grid, its brands, its measures).

One value's Korean chest (cm of body chest, the number Korean labels carry) is taken, in order, from:
  1. the seller's chart, a "US" row (an explicit US size per column): the US letter as written; then a brand row
     with system "us" (PXG): its letter is the US letter;
  2. the value itself: "90", "M(90)", "0(85)", "S(55)" (women's 55 -> 90 by the profile's kr_women), "L(55-66)";
  3. the seller's chart pairing a letter with a number ("85 (S)", "Size / XS / S" over "Korea Size / 85 / 90");
  4. the brand row's letters (WAAC S = 90); a letter range "S/M" takes both letters' chests;
  5. the profile's letters (S = 90): the fallback, said in `basis`.
FREE / F / 프리 is One Size. A value none of these reads, or two Korean sizes landing on one US size, holds the product
(size_unmapped): an invented size is worse than none.
"""
import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Callable

from size_chart import NOT_CHART_RE, ONE, Chart, measure_names, read_chart  # noqa: F401  (re-exported: the callers' one module)
from size_labels import (MENS_WAIST, WOMENS_WAIST, Label, is_size_name, japanese_ladder,  # noqa: F401
                         japanese_letters, parse_label, waist_labels, waist_reading)

_COLOUR_NAME_RE = re.compile(r"색상|컬러|칼라|색깔|color|colour", re.I)    # not a type's section (size_chart sections)
# a colour value under any option name ("선택: 블랙 / 네이비"): never a type's section
_COLOUR_VALUE_RE = re.compile(r"블랙|화이트|아이보리|네이비|그레이|회색|베이지|브라운|카키|그린|민트|블루|스카이|레드|와인|버건디|핑크|"
                              r"퍼플|옐로우|오렌지|차콜|크림|카멜|실버|골드|색$|black|white|navy|gr[ae]y|beige|pink|blue|red",
                              re.I)
PROFILES_DIR = Path(__file__).with_name("size_profiles")    # one <name>.json a garment profile, its <name>.md
VERSION = "sizes/2"                          # bump on a change of what resolve() returns
# a letter paired with a Korean women's size in the seller's text or OCR, outside any chart row: "L[55~66]/XL[77]",
# "M(55), L(66), XL(77)", an OCR row "L(55-66) / 48 / 20 / 58" whose measures are not read (2026-11-20 review:
# 10036686854, 11016233632, 12220300865); the label's own parse decides what the token is
_LETTER_ALT = r"XXXL|3XL|XXL|2XL|XXS|2XS|XS|XL|LL|S|M|L"      # deliberately narrow: these sellers' letters
_WOMEN_TOKEN = r"\d{2}(?:\.5|반)?(?:\s*[-~]\s*\d{2}(?:\.5|반)?)?"
# the closing bracket ends a pair: a letter right after it is the next pair ("M(55)L(66)", the OCR glued them:
# Toosom 12566658191 sold M as US M, one size too big, 2026-11-21); a digit after it is no pair
# "S(44사이즈)" too (2026-11-24, 10997837767: S/M/L/XL went out one US size over by the bare letter)
_TEXT_PAIR_RE = re.compile(rf"(?<![A-Za-z0-9])(?:(?:{_LETTER_ALT})\s*[(\[]\s*{_WOMEN_TOKEN}\s*(?:사이즈)?\s*[)\]]|"
                           rf"{_WOMEN_TOKEN}\s*[(\[]\s*(?:{_LETTER_ALT})\s*[)\]])(?!\d)", re.I)
# a women's size beside a letter in a chart row or a two-row table, with the seller's body word ("M / 보통55 / 91",
# "~마른 55 / 보통55 / 보통66 / 통통77" under "S / M / L / XL": 6033600342, 2026-11-24); the word and "~" are dropped
_BODY_WORD_RE = re.compile(r"마른|보통|날씬|통통|~|\s")
_WOMEN_CELL_RE = re.compile(r"^(?:44|55|66|77|88|99)$")
_WOMEN_RANGE_CELL_RE = re.compile(r"^(?:44|55|66|77|88)-(?:55|66|77|88|99)$")   # letter_cells' "55-66" (2026-11-25)
_WAIST_CELL_RE = re.compile(r"^(\d{2})\s*[-~]\s*(\d{2})$")         # "25-26" under "S / M / L" (11318914118)
_SIZE_WORDS_RE = re.compile(r"^(?:x*-?small|medium|x*-?large|\d?x-?large)$", re.I)   # "Small / Medium / Large"
# the same letters, for a value whose colour and size are joined ("Ivory/085", "블랙 100 L": 12487887784, 10940191023)
_JOIN_SPLIT_RE = re.compile(r"[\s/_]+")             # "_" too: "티셔츠 55_아이보리" (6354978708, 2026-11-21)
# a waist or a letter glued to a Hangul colour or a closing bracket, no separator (2026-11-24, Golf Pants: promore
# "블랙34", "151(블랙)30", "SW.422/01(그레이)30" 4954391160 / 5536196761 held "no size option"; 내추럴모드 "크림M",
# "카키3XL" 10821435743 went out unsized): split there in the waist profiles only (a waist read is on)
_GLUED_RE = re.compile(rf"^(.*[가-힣)])(\d{{2}}|{_LETTER_ALT})$")
# a trousers' length before the size ("9부 S", "10부 M": 9/10 of full length, cropped / full; 2026-11-24, 엔조이핏
# 10107163054 held "'9부 S': not read as a size"); a bare size beside them states no length: NO_LENGTH
_LENGTH_RE = re.compile(r"^\d{1,2}부(?:\([^)]*\))?$")
NO_LENGTH = "기본"
LENGTH_NAME = "기장"


_INSEAM_RE = re.compile(r"^기장\d{2}$")      # a length in inches split off a waist ("33-30" -> 기장30, 2026-11-24)


def length_word(text: str) -> bool:
    """A trousers' length ("9부", "10부(롱)", "기장30") or NO_LENGTH."""
    return text == NO_LENGTH or bool(_LENGTH_RE.match(text)) or bool(_INSEAM_RE.match(text))


_WOMEN_TAIL = {"44", "55", "66", "77", "88", "99"}
# 2026-11-24, the size_unmapped review: a letter after a Hangul colour and a dash ("화이트-S", 7124536208); never a
# number ("블랙-95") or a size before the dash ("S-M")
_DASH_LETTER_RE = re.compile(rf"^(.*[가-힣])-({_LETTER_ALT})$")
# "옐로우ㅡL": the jamo ㅡ as a dash (2026-11-25), only before a letter size that ends the value: a number after it
# ("블랙ㅡ 95") keeps its space split, read as before (the fixer, 2026-11-25)
_JAMO_DASH_RE = re.compile(rf"(?<=[가-힣)])\s*ㅡ\s*(?=(?:{_LETTER_ALT})\s*$)")
_A_CM_RE = re.compile(r"^A\d{2,3}$")                            # adidas' Asian waist code "A82"
_INCH_NOTE_RE = re.compile(r"^[(（]\d{2}인치[)）]$")              # ... and its inch "(32인치)"
_A_LETTER_RE = re.compile(r"^A(?:XS|S|M|L|XL|2XL|3XL)$")          # adidas' Asian letter "AS"
_BRACKET_NUM_RE = re.compile(r"^[(（]\d{2,3}[)）]$")               # ... and its chest "(85)"
# a plain letter and its women's size or chest in brackets after a space, "체크 A라인 M (55)" (Pinkpang rainwear
# 5691897960, 2026-11-25: the words were 체크 / A라인 / M / (55), no split): one word, outside the waist profiles
_PLAIN_LETTER_RE = re.compile(rf"^(?:{_LETTER_ALT})$")
_BRACKET_SIZE_RE = re.compile(r"^[(（]\d{2,3}(?:\s*[-~]\s*\d{2,3})?[)）]$")


def _words(value: str) -> list[str]:
    """A value's words for a colour / size split: by space, "/", "_"; in a waist profile a size glued to the end of a
    Hangul word or a closing bracket is a word of its own ("블랙34" -> 블랙, 34)."""
    # the Hangul vowel ㅡ (U+3161) a seller types as a dash between a colour and its size, "형광 옐로우ㅡL", "블랙ㅡXXL"
    # (5706906040, 6672050974, 2026-11-25, the owner: "Все рекомендации"): a "-" (_DASH_LETTER_RE splits it)
    value = _JAMO_DASH_RE.sub("-", str(value or ""))
    words = [w for w in _JOIN_SPLIT_RE.split(value.strip()) if w]
    w = waist_reading()
    # adidas' size and its bracket after a space are one word (2026-11-24): "A82 (32인치)" in the men's trousers
    # (7191019224, 10159594995), "AS (85)" outside the waist profiles (10861903381)
    if len(words) >= 2 and ((w and w[4] and _A_CM_RE.match(words[-2]) and _INCH_NOTE_RE.match(words[-1]))
                            or (not w and _A_LETTER_RE.match(words[-2]) and _BRACKET_NUM_RE.match(words[-1]))
                            or (not w and len(words) >= 3 and _PLAIN_LETTER_RE.match(words[-2])
                                and _BRACKET_SIZE_RE.match(words[-1]))):
        words[-2:] = [f"{words[-2]} {words[-1]}"]
    m = _GLUED_RE.match(words[-1]) if words else None
    # a women's size glued to a Hangul word is a word of its own, in any profile ("블랙하운드55" 5895988627, "긴팔55"
    # 10968014964, 2026-11-24); a waist or a letter glued only in a waist profile
    women = bool(m and m.group(2) in _WOMEN_TAIL and re.search(r"[가-힣]$", m.group(1)))
    # the men's trousers: a cm waist 66..99 glued to a Hangul colour too, "네이비82" beside "네이비 85" (adidas by soneva
    # 10076109143, 2026-11-25); never after ")" ("바지(봄/가을)25") nor three digits ("카본120")
    cm_glued = bool(m and w and w[4] and m.group(2).isdigit() and 66 <= int(m.group(2)) <= 99
                    and re.search(r"[가-힣]$", m.group(1)))
    if m and (women or cm_glued or (w and (not m.group(2).isdigit() or w[0] <= int(m.group(2)) <= w[1]))):
        words[-1:] = [m.group(1), m.group(2)]
    elif words and (d := _DASH_LETTER_RE.match(words[-1])):
        words[-1:] = [d.group(1), d.group(2)]
    return words

# --- resolving -----------------------------------------------------------------------------------------------------

def grids(folder: Path = PROFILES_DIR) -> dict[str, Any]:
    """{"profiles": {name: profile}}: every size_profiles/<name>.json (format size-profile/1)."""
    out: dict[str, Any] = {}
    for f in sorted(folder.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("format") != "size-profile/1" or data.get("name") != f.stem:
            raise ValueError(f"{f}: not a size profile named {f.stem}")
        out[f.stem] = data
    return {"profiles": out}


def waist_read(profile: dict[str, Any]) -> tuple[float, float, float, float, bool] | None:
    """The waists a profile reads in its labels (size_labels.waist_labels): none for the tops, the women's for the
    skirts, the men's for the men's trousers ("waist_read": "mens", 2026-11-23)."""
    if profile.get("key") != "waist":
        return None
    return MENS_WAIST if profile.get("waist_read") == "mens" else WOMENS_WAIST


def _norm(text: str | None) -> str:
    return re.sub(r"[\s\[\]()]+", "", str(text or "")).upper()


def brand_row(profile: dict[str, Any], brand: str | None, title: str | None) -> tuple[str, dict[str, Any]] | None:
    """The brand's row: brand_ko equal to an alias; else (no brand_ko row matched) the title starting with an alias
    as a word of its own ("[왁] 여성 ...", "PXG 여성 ..."; never "왁스 코팅 ...")."""
    rows = [(name, row) for name, row in profile.get("brands", {}).items() if not name.startswith("_")]
    b = _norm(brand)
    for name, row in rows:
        if b and any(_norm(a) == b for a in row.get("aliases", [])):
            return name, row
    lead = re.sub(r"^[\s\[(]+", "", str(title or "")).upper()
    for name, row in rows:
        for alias in row.get("aliases", []):
            a = alias.upper()
            if len(a) >= 1 and lead.startswith(a) and (len(lead) == len(a) or not re.match(r"[가-힣A-Z0-9]", lead[len(a)])):
                return name, row
    return None


def size_option(options: list[dict[str, Any]]) -> int | None:
    """The option whose every value is a size label (the last such, a colour comes first); else one named a size
    (사이즈 / size) or with most of its values sizes: resolve() holds it on the value it cannot read, rather than send
    "L(77~)" as it is (2026-11-19 review)."""
    whole = [i for i, o in enumerate(options) if o.get("values_ko") and all(parse_label(v) for v in o["values_ko"])]
    if whole:
        return whole[-1]
    for i in range(len(options) - 1, -1, -1):
        values = options[i].get("values_ko") or []
        read = sum(1 for v in values if parse_label(v))
        # an option named a size is chosen even when none of its values reads (2026-11-21, the second windbreaker
        # pilot: "WS / WM / WL" 13483086996, "A.0 / B.1 / C.2" 11966824855, "0호 / 1호 / 2호" 12300620164, "S(상세사이즈
        # 확인했습니다)" 11734583917 went out raw with no US size and no hold): resolve() holds it on the first value
        if values and (is_size_name(options[i].get("name_ko")) or (read and read * 2 > len(values))):
            return i
    return None


def inch_of(cm: float, profile: dict[str, Any] | None = None) -> int:
    """A waist in cm as the inch size it stands for: the nearest inch; in the men's pants (`cm_round` 0.3, 2026-11-23)
    a Korean cm size as Korea writes it (82 = 32, 85 = 33, 88 = 34, 91 = 36: the pants pilot, Adidas 88(34))."""
    return int(cm / 2.54 + float((profile or {}).get("cm_round", 0.5)))


_CM_INCH_RE = re.compile(r"^\s*(\d{2,3})\s*\(\s*(\d{2})\s*\)\s*$")
# adidas' Asian waist code with its inch, "A82 (32인치)" (7191019224, 10159594995, 2026-11-24): 인치 written
_A_CM_INCH_RE = re.compile(r"^\s*A(\d{2,3})\s*[(（]\s*(\d{2})\s*인치\s*[)）]\s*$")


def cm_inch(text: str | None) -> tuple[int, int] | None:
    """A cm waist written with the seller's inch, "77(29)" -> (77, 29) (Kim Young Joo's 호칭 row, 5912038354,
    2026-11-24: the inch is the US waist, cm_round made 77 W30); None for anything else ("30(76)" is an inch first)."""
    m = _CM_INCH_RE.match(str(text or "")) or _A_CM_INCH_RE.match(str(text or ""))
    if not m:
        return None
    cm, inch = int(m.group(1)), int(m.group(2))
    return (cm, inch) if 60 <= cm <= 115 and 24 <= inch <= 46 and abs(cm / 2.54 - inch) <= 2 else None


def _same(a: Label, b: Label, profile: dict[str, Any] | None = None) -> bool:
    """Two labels of one size: the same chest or women's numbers; else, the same letter where one has no number."""
    if a.free and b.free:
        return True
    if a.chest and b.chest:
        return a.chest == b.chest
    if a.women and b.women:
        return a.women == b.women
    if a.jp is not None and b.jp is not None:
        return a.jp == b.jp
    if a.waist and b.waist:                      # "30" and "30(76)": the same waist in inches (2026-11-23, trousers)
        return {inch_of(w, profile) for w in a.waist} == {inch_of(w, profile) for w in b.waist}
    return bool(a.letter) and a.letter == b.letter


def _grid_row(profile: dict[str, Any], chest: float) -> dict[str, Any] | None:
    if profile.get("pick") == "band":            # each row's number is its band's lower edge (the skirts' waist): the
        rows = sorted(profile["grid"], key=lambda r: r["chest_cm"])          # last row at or under the value, so an
        under = [r for r in rows if r["chest_cm"] <= chest + 0.05]          # edge goes to the larger size
        # the last band ends an inch past its body range (2026-11-24, 6818506441: W46 in the 4XL's 41-46; it was 6 cm
        # past the band's edge), and a value past it is no size, never the smallest one
        top = (rows[-1]["bust_in"][-1] + 1) * 2.54 if rows[-1].get("bust_in") else rows[-1]["chest_cm"] + 6
        return under[-1] if under and chest < top else (rows[0] if 0 <= rows[0]["chest_cm"] - chest <= 3 else None)
    best = min(profile["grid"], key=lambda r: abs(r["chest_cm"] - chest))
    return best if abs(best["chest_cm"] - chest) <= 2.5 else None


def _us_range(text: str) -> tuple[float, float]:
    ends = [float(x) for x in str(text).split("-")]
    return (-1.0, -1.0) if text == "00" else (ends[0], ends[-1])


def _brand_us(hit: tuple[str, dict[str, Any]] | None, rows: list[dict[str, Any]],
              profile: dict[str, Any]) -> tuple[str, str] | None:
    """The maker's own US number for one Korean chest (a brand row's `us_by_chest`, its printed table: 2026-11-21,
    Superior 085..105 = US 2..10, one to two sizes under the grid's) -> ("S (US 6)", "S"): the grid's letter whose US
    numbers hold it; None without such a row or that chest (the grid's then)."""
    if not hit or len(rows) != 1:
        return None
    num = (hit[1].get("us_by_chest") or {}).get(str(int(rows[0]["chest_cm"])))
    if num is None:
        return None
    n = float(num)
    row = next((r for r in profile["grid"] if r.get("us_num")
                and _us_range(r["us_num"])[0] <= n <= _us_range(r["us_num"])[1]), None)
    return (f"{row['us']} (US {num})", row["us"]) if row else None


def _us_text(rows: list[dict[str, Any]]) -> str:
    if not all(r.get("us_num") for r in rows):     # men's tops: the US letter alone (2026-11-21)
        return rows[0]["us"] if len(rows) == 1 else f"{rows[0]['us']}-{rows[-1]['us']}"
    pre = rows[0].get("us_num_prefix", "US ")      # men's trousers: the waist alone, "W32-33" (2026-11-23)
    lo, hi = rows[0], rows[-1]
    num = lo["us_num"] if len(rows) == 1 else f"{lo['us_num'].split('-')[0]}-{hi['us_num'].split('-')[-1]}"
    if lo.get("us_num_only"):
        return f"{pre}{num}"
    return f"{lo['us']} ({pre}{num})" if len(rows) == 1 else f"{lo['us']}-{hi['us']} ({pre}{num})"


def _merge_key(label: Label, profile: dict[str, Any]) -> str:
    """One size written twice has one key: the label's; in a waist profile a waist by the inch it rounds to ("M(32)"
    and "M(82)": one size in inches and in cm, Adidas 5979440160, 2026-11-23)."""
    if profile.get("key") == "waist" and label.waist and not (label.chest or label.women):
        return f"{label.letter or ''}|W" + ",".join(sorted({str(inch_of(w, profile)) for w in label.waist}))
    return label.key


def _chest_of(label: Label, profile: dict[str, Any]) -> list[float]:
    """The Korean chest of the label's numbers; [] when a women's size is not in kr_women (a half size, "66반", sits
    between two US sizes: held unless the profile names it). A profile keyed by the waist ("key": "waist", the
    skirts, 2026-11-22) reads the label's waist (cm, inches made cm) and a number 80..95 as a waist in cm; a profile of
    tops never reads a waist."""
    if profile.get("key") == "waist":
        # a number 80..95 beside a letter is the maker's hip or top numbering, never the waist ("S(90)", Kappa
        # 11871883753, 2026-11-22: S went out as XXL); alone it is a waist in cm
        chest = [] if label.letter else [c for c in label.chest if c <= 95]
        if len(label.waist) > 1 and not chest and len({inch_of(w, profile) for w in label.waist}) == 1:
            return [round(inch_of(label.waist[0], profile) * 2.54, 1)]   # "34(86)": one waist, 34 in (2026-11-23)
        if label.waist or chest:
            return list(label.waist) + chest
        if label.chest and label.letter:
            return []
    elif label.chest:
        return list(label.chest)
    out = []
    for w in label.women:
        key = f"{w:g}"
        if key not in profile["kr_women"]:
            return []
        out.append(profile["kr_women"][key])
    return out


def _typed_rows(chart: Chart, sections: list[str]) -> list[dict[str, Any]]:
    """The one-size rows per type when the chart tied blocks to types; the block read before any type's heading
    keeps its place: named by the one type left untied, else unnamed (never dropped)."""
    tied = [n for n in chart.rows if n in chart.sections]
    if not tied:
        return []
    out = []
    if ONE in chart.rows:
        left = [v for v in dict.fromkeys(sections) if v not in chart.sections.values()]
        row: dict[str, Any] = {"us": "One Size", "cm": dict(chart.rows[ONE])}
        if len(left) == 1:
            row["section_ko"] = left[0]
        out.append(row)
    out += [{"us": "One Size", "section_ko": chart.sections[n], "cm": dict(chart.rows[n])} for n in tied]
    return out


FREE_KEY = "FREE"


def _waist_key(label: Label, free: bool = False) -> str | None:
    """The key waist_text_pairs gives a value's waist under: its letter ("S", "S (55)"), else its one women's size
    ("55"); FREE when `free` (the seller wrote FREE a waist, 5282622633, 2026-11-25); None for a value with a chest,
    a waist, a letter range or FREE."""
    if label.free and free and not (label.upto or label.chest or label.waist):
        return FREE_KEY
    if label.upto or label.chest or label.waist or label.free:
        return None
    if label.letter:
        return label.letter
    return f"{label.women[0]:g}" if len(label.women) == 1 and label.jp is None else None


def _letter_chest(letter: str, pairs: dict[str, float], hit: tuple[str, dict[str, Any]] | None,
                  profile: dict[str, Any]) -> float | None:
    if letter in pairs:
        return pairs[letter]
    if hit and letter in (hit[1].get("letters") or {}):
        return float(hit[1]["letters"][letter])
    return float(profile["letters"][letter]) if letter in profile["letters"] else None


def _cells(line: str) -> list[str]:
    return [c.strip() for c in re.split(r"\s*[|/]\s*", line.strip()) if c.strip()]


def _bare_letter(cell: str) -> str | None:
    lab = parse_label(cell) if re.fullmatch(_LETTER_ALT, cell.strip(), re.I) else None
    return lab.letter if lab else None


def letter_cells(texts: list[str]) -> list[tuple[str, str]]:
    """(letter, what the seller writes for it) from a chart row whose second cell is a women's size with a body word
    ("M / 보통55 / 91 / 34.5" -> ("M", "55")) and from a two-row table: a line of bare letters, then (past one line of
    "Small / Medium / Large") a line of as many cells, each a women's size ("~마른 55 / 보통55 / 보통66 / 통통77") or
    an inch waist range ("25-26 / 27-28 / 29-30") -> ("S", "55"), ("S", "25-26"). 2026-11-24: 6033600342,
    11318914118. Model and shop lines are skipped."""
    out: list[tuple[str, str]] = []
    ranged: dict[str, str] = {}
    for i, line in enumerate(texts):
        if NOT_CHART_RE.search(line):
            continue
        cells = _cells(line)
        if len(cells) >= 2 and (letter := _bare_letter(cells[0])) and re.search(r"마른|보통|날씬|통통", cells[1]) \
                and _WOMEN_CELL_RE.match(_BODY_WORD_RE.sub("", cells[1])):
            out.append((letter, _BODY_WORD_RE.sub("", cells[1])))
            continue
        letters = [_bare_letter(c) for c in cells]
        if len(cells) < 2 or not all(letters) or len(set(letters)) != len(letters):
            continue
        below = texts[i + 1:i + 3]
        if below and len(_cells(below[0])) == len(cells) and all(_SIZE_WORDS_RE.match(c) for c in _cells(below[0])):
            below = below[1:]
        if not below or NOT_CHART_RE.search(below[0]):
            continue
        raw = _cells(below[0])
        women = [_BODY_WORD_RE.sub("", c) for c in raw]
        if len(raw) != len(cells):
            continue
        if all(_WOMEN_CELL_RE.match(c) for c in women):
            upper = [_BODY_WORD_RE.sub("", c) for c in _cells(below[1])] if len(below) > 1 \
                and not NOT_CHART_RE.search(below[1]) else []
            if 0 < len(upper) < len(cells) and all(_WOMEN_CELL_RE.match(c) for c in upper) \
                    and all(int(hi) > int(lo) for lo, hi in zip(women[len(women) - len(upper):], upper)):
                # a second line of body sizes under the last letters, right-aligned: each letter's upper end ("보통55"
                # over "날씬66": M is 55-66); a first letter written "~마른 55" alone is the size under it, 44
                # (매일츄리닝 6033600342, 2026-11-25: S and M were both 55, held on one US size)
                first = len(cells) - len(upper)
                low = [("44" if raw[k].startswith("~") and women[k] == "55" else women[k]) for k in range(first)]
                out += [(str(x), c) for x, c in zip(letters[:first], low)]
                out += [(str(x), f"{lo}-{hi}") for x, lo, hi in zip(letters[first:], women[first:], upper)]
                ranged.update({str(x): lo for x, lo in zip(letters[first:], women[first:])})
            else:
                out += [(str(x), c) for x, c in zip(letters, women)]
        elif all(_WAIST_CELL_RE.match(c) for c in raw):
            out += [(str(x), c) for x, c in zip(letters, raw)]
    # a chart row's one women's size that is the lower end of the letter's range above ("M / 보통55" beside M 55-66):
    # the range's
    return [(x, c) for x, c in out if not (x in ranged and c == ranged[x])]


_TIP_FLOOR_RE = re.compile(rf"\(\s*({_LETTER_ALT})\s*\)\s*(?:사이즈)?\s*-\s*정?\s*(44|55|66|77|88|99)\s*이상", re.I)


def tip_floors(texts: list[str]) -> dict[str, float]:
    """The women's size a seller's size tip gives as a letter's lower end, "엑스라지(XL)사이즈 - 88이상" -> {XL: 88}
    (핑크골프 7965635614, 2026-11-25); a letter written with two such floors is left out."""
    seen: dict[str, set[float]] = {}
    for line in texts:
        if NOT_CHART_RE.search(line):
            continue
        for m in _TIP_FLOOR_RE.finditer(line):
            lab = parse_label(m.group(1))
            if lab and lab.letter:
                seen.setdefault(lab.letter, set()).add(float(m.group(2)))
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def size_line(texts: list[str], letters: list[str], chart: Chart) -> dict[str, Label]:
    """The seller's size line, "사이즈 / S(55), M(66), L(77)": one line pairing exactly the option's letters, each with
    one women's size, rising, when the chart's rows are lettered otherwise ("M(55) / L(66) / XL(77)": a letter not
    sold, a sold one missing) over the same women's sizes (로로얼로이 9317474764, 2026-11-25: the chart's M(55) made
    M the S of the line). -> {letter: its label}, or {} (a chart lettered as the option keeps winning)."""
    rows = [lab for lab in chart.labels.values() if lab and lab.letter and len(lab.women) == 1 and not lab.chest]
    if not rows or {lab.letter for lab in rows} == set(letters) or len(set(letters)) != len(letters):
        return {}
    for line in texts:
        if NOT_CHART_RE.search(line):
            continue
        labels = [parse_label(t) for t in _TEXT_PAIR_RE.findall(line)]
        if not labels or any(lb is None or not lb.letter or len(lb.women) != 1 or lb.chest or lb.upto for lb in labels):
            continue
        got = {str(lb.letter): lb for lb in labels if lb}
        if len(got) != len(labels) or set(got) != set(letters) \
                or {lb.women[0] for lb in got.values()} != {lab.women[0] for lab in rows}:
            continue
        ladder = sorted(got.values(), key=lambda lb: _LADDER.index(lb.letter) if lb.letter in _LADDER else 99)
        if all(a.women[0] < b.women[0] for a, b in zip(ladder, ladder[1:])):
            return got
    return {}


def text_pairs(texts: list[str]) -> dict[str, Label]:
    """The letters the seller's text pairs with one Korean women's size ("L[55~66]", "M(55)", "77(XL)", "S(44사이즈)",
    letter_cells' "M / 보통55"); a letter written with two different numbers is left out (never a guess: today's
    reading stays). Model and shop lines (size_chart.NOT_CHART_RE) are skipped."""
    seen: dict[str, set[str]] = {}
    got: dict[str, Label] = {}
    tokens = [t for line in texts if not NOT_CHART_RE.search(line) for t in _TEXT_PAIR_RE.findall(line)]
    tokens += [f"{x}({c})" for x, c in letter_cells(texts) if _WOMEN_CELL_RE.match(c) or _WOMEN_RANGE_CELL_RE.match(c)]
    for token in tokens:
        label = parse_label(token)
        if label is None or not label.letter or not label.women or label.chest or label.upto:
            continue
        seen.setdefault(label.letter, set()).add(label.key)
        got[label.letter] = label
    return {k: v for k, v in got.items() if len(seen[k]) == 1}


# a letter with the body waist in inches the seller gives it (2026-11-23, the pants pilot: 4 of 13 women's drafts
# sized one or two sizes over by the bare letter): "S(24-26), M(27-28)" (5530496945), "M사이즈 (27-28)" (5392170005),
# "S(25-26) | M(27-28)L(29-30)" (5305209427), and the other way round "25-26 : S / 27-29 : M" (5814395263)
_WAIST_PAIR_RE = re.compile(rf"(?<![A-Za-z0-9])({_LETTER_ALT})\s*(?:사이즈)?\s*[(\[]\s*(\d{{2}})(?:\s*[-~]\s*(\d{{2}}))?"
                            rf"\s*(?:인치|inch|in)?\s*[)\]]", re.I)
_WAIST_PAIR_BACK_RE = re.compile(rf"(?<![\d.])(\d{{2}})\s*[-~]\s*(\d{{2}})\s*(?:인치|inch)?\s*[:=]\s*({_LETTER_ALT})(?![A-Za-z])",
                                 re.I)
# ... and with the inch written and no separator, FREE too: "25-27인치 free / 28-30인치 XL / 30-31인치2XL" (할로
# 5282622633, 2026-11-25: the seller's own recommendation, its labels' women's sizes are the stretch range)
_WAIST_PAIR_INCH_RE = re.compile(rf"(?<![\d.])(\d{{2}})\s*[-~]\s*(\d{{2}})\s*(?:인치|inch)\s*(FREE|프리|{_LETTER_ALT})"
                                 rf"(?![A-Za-z])", re.I)
# a Korean women's size with the body waist in inches: "55(25-26),66(27-28),77(29-30),88(31-32)권장드립니다" (Toosom
# 4716253463, 2026-11-24: 55..88 went out by kr_women, the seller's waist unread); the key is the size, "55"
_WOMEN_WAIST_RE = re.compile(r"(?<![\d.])(44|55|66|77|88|99)\s*(?:사이즈)?\s*[(\[]\s*(\d{2})(?:\s*[-~]\s*(\d{2}))?"
                             r"\s*(?:인치|inch|in)?\s*[)\]]", re.I)


# a women's waist written with a half inch, "M(26반~27)" (투엘라 12370291326, 2026-11-25): the women's waist profiles
_WAIST_PAIR_HALF_RE = re.compile(rf"(?<![A-Za-z0-9])({_LETTER_ALT})\s*[(\[]\s*(\d{{2}}반?)\s*[-~]\s*(\d{{2}}반?)\s*[)\]]",
                                 re.I)


def _half(text: str) -> float:
    return int(text.rstrip("반")) + (0.5 if text.endswith("반") else 0)


def waist_text_pairs(texts: list[str], profile: dict[str, Any]) -> dict[str, list[float]]:
    """The letters the seller's text gives a body waist in inches (the waist profiles): {letter: [cm, ...]}, a range
    its two ends; a women's size the same, keyed by its number ("55"); a two-row table of letters over waist ranges
    (letter_cells); a key written with two different waists is left out (unless _ladder_pick takes one), as are model
    and shop lines."""
    return _waist_pairs(texts, profile)[0]


def _waist_pairs(texts: list[str], profile: dict[str, Any]) -> tuple[dict[str, list[float]], set[str]]:
    """waist_text_pairs and the letters whose waist _ladder_pick chose between two."""
    w = waist_read(profile)
    if not w:
        return {}, set()
    seen: dict[str, dict[tuple[float, ...], int]] = {}
    found: list[tuple[str, str, str | None]] = []
    for line in texts:
        if NOT_CHART_RE.search(line):
            continue
        found += [(m.group(1), m.group(2), m.group(3)) for m in _WAIST_PAIR_RE.finditer(line)]
        found += [(m.group(3), m.group(1), m.group(2)) for m in _WAIST_PAIR_BACK_RE.finditer(line)]
        found += [(m.group(3), m.group(1), m.group(2)) for m in _WAIST_PAIR_INCH_RE.finditer(line)]
        if not w[4]:                             # the men's "88(34)" is a cm waist with its inch, no women's size
            found += [(m.group(1), m.group(2), m.group(3)) for m in _WOMEN_WAIST_RE.finditer(line)]
            found += [(m.group(1), m.group(2), m.group(3)) for m in _WAIST_PAIR_HALF_RE.finditer(line)
                      if "반" in m.group(0)]
    found += [(x, m.group(1), m.group(2)) for x, c in letter_cells(texts) if (m := _WAIST_CELL_RE.match(c))]
    for key, lo, hi in found:
        nums = [_half(lo)] + ([_half(hi)] if hi else [])
        if key.isdigit():
            name: str | None = key
        else:
            lab = parse_label(key)
            name = lab.letter if lab else None
            name = FREE_KEY if lab and lab.free else name
        if not name or not all(w[0] <= n <= w[1] for n in nums):
            continue
        ends = tuple(round(n * 2.54, 1) for n in nums)
        seen.setdefault(name, {})[ends] = seen.get(name, {}).get(ends, 0) + 1
    out = {k: list(next(iter(v))) for k, v in seen.items() if len(v) == 1}
    picked = _ladder_pick(seen, out)
    return {**out, **picked}, set(picked)


def _ladder_pick(seen: dict[str, dict[tuple[float, ...], int]], one: dict[str, list[float]]) -> dict[str, list[float]]:
    """A letter written with two inch ranges ("L(28~29)" twice in the text, "L(27~29)" in the chart's row label,
    투엘라 12370291326, 2026-11-25): the range that neither overlaps nor leaves a gap (over an inch) with its
    neighbours' single ranges on the letter ladder, when exactly one does and it is written at least as often as
    the other; else none (left out, as before)."""
    order = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]
    out: dict[str, list[float]] = {}
    for name, ranges in seen.items():
        if len(ranges) < 2 or name not in order or any(len(r) != 2 for r in ranges):
            continue
        k = order.index(name)
        lower = one.get(order[k - 1]) if k else None
        upper = one.get(order[k + 1]) if k + 1 < len(order) else None
        if lower is None and upper is None:
            continue

        def fits(r: tuple[float, ...]) -> bool:
            lo, hi = r[0] / 2.54, r[1] / 2.54
            return (lower is None or 0 < lo - lower[-1] / 2.54 <= 1.01) and \
                (upper is None or 0 < upper[0] / 2.54 - hi <= 1.01)
        good = [r for r in ranges if fits(r)]
        if len(good) == 1 and ranges[good[0]] >= max(n for r, n in ranges.items() if r != good[0]):
            out[name] = list(good[0])
    return out


def _joined_size(value: str, free: bool = False) -> Label | None:
    """The size of one value that joins a colour and a size, or None: a size tail after a head that is no size
    ("Black/090", "아이보리 M"), or a size head before a tail that is no size ("FREE/그레이", "XL/크림": 2026-11-21,
    Mineflow 9969597394); a letter, a chest or a women's size, FREE only when `free`."""
    words = _words(value)
    if len(words) < 2:
        return None
    with waist_labels():                                 # one size with its note ("XS (25인치 전후)"): no colour,
        if parse_label(str(value)):                      # whatever the profile
            return None
    middle = [(words[i], words[:i] + words[i + 1:]) for i in range(1, len(words) - 1)]   # "티셔츠 55_아이보리"
    for size, rest in ((words[-1], words[:-1]), (words[0], words[1:]), *middle):
        label = parse_label(size)
        if label and (label.letter or label.chest or label.women or label.waist or (free and label.free)) \
                and (free or not label.free) and not parse_label(" ".join(rest)):
            return label
    return None


def split_joined(options: list[dict[str, Any]], asian: bool = False) -> tuple[int, list[tuple[str, str]]] | None:
    """The option that joins a colour and a size in every value, as _joined reads it, and each value's (rest, size
    word): ("Ivory/085" -> ("Ivory", "085"), "남성 골프 이너웨어__블랙 95" -> ("남성 골프 이너웨어 블랙", "95"),
    "티셔츠 55_아이보리" -> ("티셔츠 아이보리", "55")); None when no option does (2026-11-22, the men's tops pilot: 20
    apparel products held for it, transform._sizes splits it in two options). A trousers' length before the size
    ("9부 S" -> ("9부", "S")), a bare size beside them (NO_LENGTH, "S"): split_length."""
    waist_length = split_waist_length(options)
    if waist_length:
        return waist_length
    length = split_length(options)
    if length:
        return length
    lettered = number_letter_split(options)
    if lettered:
        return lettered[0], [(head, num) for head, num, _ in lettered[1]]
    coded = _adidas_codes_split(options)
    if coded:
        return coded
    if asian and (lettered_a := _asian_letters_split(options)):   # the owner's adidas letters (2026-11-25)
        return lettered_a
    if _joined(options) is None:
        return None
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        out: list[tuple[str, str]] = []
        for v in values:
            words = _words(v)
            label = _joined_size(v, free=True)
            if label is None:
                break
            for k in (len(words) - 1, 0, *range(1, len(words) - 1)):
                rest = words[:k] + words[k + 1:]          # a second size word in the rest ("오프화이트 85 XS"): no split
                if parse_label(words[k]) == label and not parse_label(" ".join(rest)) \
                        and not any(parse_label(w) or (len(w) > 1 and w[0] in "AaWw" and parse_label(w[1:]))
                                    for w in rest):    # adidas' Asian letters "AXL (110)", a women's "WS": no colour
                    out.append((" ".join(rest), words[k]))
                    break
            else:
                break
        if len(out) == len(values) and len({sz for _, sz in out}) >= 2:
            return i, out
    return None


_A_BARE_RE = re.compile(r"^A\d{2,3}$")


def _adidas_codes_split(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """In the men's trousers, the option whose values end in adidas' waist code, some with the inch written ("IQ2921
    블랙 A82 (33인치)") and the others bare ("IQ2921 블랙 A79"), and each value's (rest, code): the bare code is a size
    word beside the written ones (majorgolf 11493370731, 2026-11-25: held "no size option"); resolve() sizes a bare
    code only by the product's size table (order_pairs), else holds it "not read as a size"."""
    w = waist_reading()
    if not (w and w[4]):
        return None
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        words = [_words(v) for v in values]
        if not values or any(len(ws) < 2 for ws in words):
            continue
        written = [ws for ws in words if _A_CM_INCH_RE.match(ws[-1])]
        bare = [ws for ws in words if _A_BARE_RE.match(ws[-1])]
        if not written or not bare or len(written) + len(bare) != len(values) \
                or any(parse_label(" ".join(ws[:-1])) for ws in words):
            continue
        out = [(" ".join(ws[:-1]), ws[-1]) for ws in words]
        if len({sz for _, sz in out}) >= 2:
            return i, out
    return None


def _adidas_code_inches(option: dict[str, Any], texts: list[str], profile: dict[str, Any]) -> dict[str, int]:
    """{bare code: its inch} for adidas' bare waist codes ("A79") of the size option, from the product's size table
    (order_pairs: "주문사이즈 / A76 / A79 ..." over "(31) / (32) ..."), only when every read of the table gives the code
    one inch and every value that writes its inch ("A82 (33인치)") says what the table says (11493370731, 2026-11-25:
    A79 = 32, A85 = 34 there; A82 is 33 in this model family, 31 or 32 elsewhere: never cm_round, no brand row)."""
    if profile.get("waist_read") != "mens":
        return {}
    values = [str(v).strip() for v in option.get("values_ko") or []]
    bare = [v for v in values if _A_BARE_RE.match(v)]
    if not bare:
        return {}
    table = order_pairs(texts)
    for v in values:
        m = _A_CM_INCH_RE.match(v)
        if m and table.get(f"A{m.group(1)}") != {int(m.group(2))}:
            return {}
    got = {v: next(iter(table[v])) for v in bare if len(table.get(v) or ()) == 1}
    return got if len(got) == len(bare) else {}


_WAIST_LENGTH_RE = re.compile(r"^(\d{2})\s*-\s*(\d{2})$")


def split_waist_length(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """The men's trousers' option of a waist and a length in inches, "33-30" (waist 33, length 30), and each value's
    ("기장30", "33"); the waist first, 26..44, the length 28..36, one value at least with its waist not under its length
    (a waist range "30-31" stays one). 2026-11-24, 9918112671: held as two Korean sizes on one US size. "기장30", never
    "L30" (a size) or "W33" (unread): the length option must not read as the size option."""
    w = waist_reading()
    if not (w and w[4]):
        return None
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        got = [_WAIST_LENGTH_RE.match(v.strip()) for v in values]
        if not values or not all(got):
            continue
        pairs = [(int(m.group(1)), int(m.group(2))) for m in got if m]
        if all(26 <= a <= 44 and 28 <= b <= 36 for a, b in pairs) and any(a >= b for a, b in pairs):
            return i, [(f"{LENGTH_NAME}{m.group(2)}", m.group(1)) for m in got if m]
    return None


_NUMBER_LETTER_RE = re.compile(r"^(.*\S)\s+(\d{2,3})\s+(XS|S|M|L|XL|XXL|2XL|3XL)$")


def number_letter_split(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str, str]]] | None:
    """The option whose every value is a colour, a chest and its letter, "오프화이트 85 XS" .. "블랙 100 L"
    (10940191023, 2026-11-24: held as a second size word in the rest), and each value's (colour, number, letter): two
    pairs at least, each number with one letter and each letter with one number, the letters rising with the
    numbers, each number a chest and no colour a size; else None. transform._sizes holds the product when the US
    letter the number gets is not the seller's."""
    order = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        got = [_NUMBER_LETTER_RE.match(v.strip()) for v in values]
        if not values or not all(got):
            continue
        out = [(m.group(1), m.group(2), {"2XL": "XXL", "3XL": "XXXL"}.get(m.group(3), m.group(3))) for m in got if m]
        by_num: dict[str, set[str]] = {}
        by_letter: dict[str, set[str]] = {}
        for _, n, x in out:
            by_num.setdefault(n, set()).add(x)
            by_letter.setdefault(x, set()).add(n)
        if len(by_num) < 2 or any(len(v) > 1 for v in by_num.values()) or any(len(v) > 1 for v in by_letter.values()):
            continue
        ranked = sorted((int(n), order.index(next(iter(x)))) for n, x in by_num.items())
        if any(b[1] <= a[1] for a, b in zip(ranked, ranked[1:])):
            continue
        if not all((lab := parse_label(n)) and lab.chest and not lab.letter for n in by_num) \
                or any(parse_label(h) for h, _, _ in out):
            continue
        return i, out
    return None


def split_length(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """The option whose values put a trousers' length before the size ("9부 S", "10부 2XL", "9부(숏) S"), a bare
    size ("S") beside them standing for NO_LENGTH, and each value's (length, size); two sizes or more and one length
    written at least (2026-11-24, 엔조이핏 10107163054: "9부 S" .. "10부 2XL" beside its joggers' "S / M / L / XL")."""
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        out: list[tuple[str, str]] = []
        for v in values:
            words = v.split()
            lab = parse_label(words[1]) if len(words) == 2 and _LENGTH_RE.match(words[0]) else None
            if lab and (lab.letter or lab.chest or lab.women or lab.waist):
                out.append((words[0], words[1]))
                continue
            lab = parse_label(v)
            if not (lab and (lab.letter or lab.chest or lab.women or lab.waist)):
                break
            out.append((NO_LENGTH, v.strip()))
        if values and len(out) == len(values) and any(r != NO_LENGTH for r, _ in out) \
                and len({sz for _, sz in out}) >= 2:
            return i, out
    return None


_ORDER_HEAD_RE = re.compile(r"^주문\s*사이즈$")
_ORDER_NUM_RE = re.compile(r"^\((\d{2,3})\)$")


def order_pairs(texts: list[str]) -> dict[str, set[int]]:
    """adidas' (majorgolf's) size table: a "주문사이즈 / S / M / L / XL" line over "(100) / (105) / (110) / (115)", or
    "주문사이즈 / A76 / A79 ..." over "(31) / (32) ..." -> {S: {100}, A79: {32}, ...}, every read of the table in the
    product (2026-11-25, the size_unmapped review: 9998916822, 11493370731). A header with fewer cells than its numbers
    (the OCR lost a letter, "s / M / L" over four numbers) is paired only by another line of the product that writes
    the whole row ("주문사이즈 / S / M / L / XL") starting with those cells; else nothing."""
    out: dict[str, set[int]] = {}
    rows = [_cells(t) for t in texts]
    full = [[c.upper() for c in r[1:]] for r in rows if len(r) >= 3 and _ORDER_HEAD_RE.match(r[0])]
    for i, cells in enumerate(rows[:-1]):
        if len(cells) < 3 or not _ORDER_HEAD_RE.match(cells[0]):
            continue
        nums = [m.group(1) for c in rows[i + 1] if (m := _ORDER_NUM_RE.match(c))]
        if len(nums) != len(rows[i + 1]) or len(nums) < 2:
            continue
        heads = [c.upper() for c in cells[1:]]
        if len(heads) < len(nums):
            whole = [f for f in full if len(f) == len(nums) and f[:len(heads)] == heads]
            heads = whole[0] if whole else []
        if len(heads) != len(nums):
            continue
        for h, n in zip(heads, nums):
            out.setdefault(h, set()).add(int(n))
    return out


def single_joined(value: str | None, pairs: dict[str, set[int]] | None = None) -> tuple[str, str] | None:
    """One value joining a colour and a size with a number (a chest or a women's size), as (rest, size word):
    "Dark Navy/090" -> ("Dark Navy", "090") (halfclub 12487907002, 2026-11-24); None for a letter or FREE alone
    ("CW4742 화이트 L"), adidas' Asian size ("AL (110)"), a rest that reads as a size, adidas' or a women's prefixed
    letter in the rest."""
    label = _joined_size(str(value or ""))
    if label is None or not (label.chest or label.women):
        return None
    words = _words(str(value))
    for k in (len(words) - 1, 0, *range(1, len(words) - 1)):
        rest = words[:k] + words[k + 1:]
        if asian := _ASIAN_RE.match(re.sub(r"\s+", "", words[k]).upper()):
            # adidas' "AL (110)": its number differs by listing (9998916822 / 5176506757), held; read when the
            # product's own size table pairs that letter with that number, every read (9998916822: L = (110),
            # 2026-11-25)
            if (pairs or {}).get(asian.group(1)) != {int(asian.group(2))} or parse_label(" ".join(rest)) \
                    or any(parse_label(w) for w in rest):
                return None
            return " ".join(rest), words[k]
        if parse_label(words[k]) == label and not parse_label(" ".join(rest)) \
                and not any(parse_label(w) or (len(w) > 1 and w[0] in "AaWw" and parse_label(w[1:])) for w in rest):
            return " ".join(rest), words[k]
    return None


# a gender, a colour and a size in one value, "남성용-그레이L(100)", "여성용-핑크M(66)" (Kasco KSRWL-002 505840359,
# 2026-11-25, the owner: "Все рекомендации"): the colour Hangul only, the size a letter with its number or bare
_GENDER_COLOUR_RE = re.compile(r"^\s*(?P<g>남성용|여성용)\s*-\s*(?P<colour>[가-힣](?:[가-힣\s]*[가-힣])?)\s*"
                               rf"(?P<size>(?:{_LETTER_ALT})(?:\s*[(（]\s*\d{{2,3}}\s*[)）])?)\s*$")


def gender_colour_split(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """The option whose every value is "<남성용|여성용>-<colour><size>" and each value's (colour, "<gender> <size>"):
    "남성용-그레이L(100)" -> ("그레이", "남성 L(100)"); the size keeps its gender (남성 / 여성, as parse_label and
    transform._value_genders read it: "남성 L(100)" is L(100), men's), so _sizes_by_gender sizes it on that gender's
    profile; one spelling under both genders stays two sizes. None when no option is so (two or more values, every
    one a size parse_label reads, no colour read as a size)."""
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        out: list[tuple[str, str]] = []
        for v in values:
            m = _GENDER_COLOUR_RE.match(v)
            size = m.group("g")[:2] + " " + re.sub(r"\s+", "", m.group("size")) if m else ""   # "남성 L(100)"
            if not m or not parse_label(size) or parse_label(m.group("colour")):
                break
            out.append((m.group("colour").strip(), size))
        else:
            if len(out) >= 2:
                return i, out
    return None


def joined_value(value: str | None) -> bool:
    """One value that joins a colour and a size ("Black/090", "아이보리 M", "XL/크림"): never FREE alone."""
    return _joined_size(str(value or "")) is not None


def _joined(options: list[dict[str, Any]]) -> str | None:
    """An option whose values join a colour and a size ("Ivory/085", "오프화이트 85 XS"): every value ends in a size
    (a letter, a chest or a women's size, never FREE or a bare 0..4) after a head that is no size, two sizes or more."""
    for o in options:
        values = [str(v) for v in o.get("values_ko") or []]
        tails: list[str] = []
        for v in values:
            label = _joined_size(v, free=True)
            if not label:
                tails = []
                break
            tails.append(label.key)
        # two sizes or more, FREE counted only beside another ("FREE/그레이", "XL/크림", 2026-11-21)
        if len(set(tails)) >= 2:
            return f"{o.get('name_ko')!r}: colour and size in one option ({values[0]!r} ...)"
    return None


def _by_position(resolved: list[dict[str, Any]], chart: Chart, profile: dict[str, Any]) -> None:
    """Bare letters only on the profile's fallback, over a chart whose rows are numbers alone, as many: the seller's
    sizes in order ("S / M / L" sold, "호칭 / 95 / 100 / 105" charted: S is 95). 2026-11-20, the windbreaker pilot
    (Kim Young Joo DOFLJP01 11074837484: the fallback made S = 90, one size too small, and the chart was dropped).
    Rewritten in place, basis `chart_position`; anything else (a count that differs, a lettered row) is left alone."""
    if not resolved or any(r.get("basis") != "fallback_letters" for r in resolved):
        return
    numbered = sorted(((lab.chest[0], n) for n, lab in chart.labels.items()
                       if n in chart.rows and lab and len(lab.chest) == 1 and not lab.letter and not lab.women),
                      key=lambda x: x[0])
    if len(numbered) != len(resolved) or len({c for c, _ in numbered}) != len(numbered):
        return
    ordered = sorted(resolved, key=lambda r: r["chest_cm"] or 0)
    rows = [_grid_row(profile, c) for c, _ in numbered]
    if not all(rows):
        return
    for item, (chest, name), row in zip(ordered, numbered, rows):
        assert row is not None
        item.update(us=_us_text([row]), letter=row["us"], chest_cm=row["chest_cm"], basis="chart_position",
                    chart_label=name)


def _ordered_rows(resolved: list[dict[str, Any]], chart: Chart) -> None:
    """The chart's rows all labelled one letter (Chart.ordered: "S - 총장 91 ..." four times, 6484235370, 2026-11-24)
    go to the option's letters in size order, when as many and the smallest is that letter and no value has a row
    of its own; otherwise none is shown."""
    if not chart.ordered or len(chart.ordered) != len(resolved) or any(r.get("chart_label") in chart.rows
                                                                       for r in resolved):
        return
    labs = [parse_label(r["ko"]) for r in resolved]
    if any(not lb or not lb.letter or lb.upto for lb in labs) or labs[0] is None \
            or labs[0].letter != chart.ordered_letter:
        return
    for i, (r, row) in enumerate(zip(resolved, chart.ordered)):
        name = f"{chart.ordered_letter}#{i + 1}"
        chart.rows[name] = row
        r["chart_label"] = name


def _cm_inch_collisions(option: dict[str, Any], profile: dict[str, Any]) -> dict[str, int]:
    """The men's trousers' "cm(inch)" values a seller wrote two ways (2026-11-25, the size_unmapped review, adidas
    trousers sold by one seller in several listings) -> {value: the inch it takes, basis cm_round}:
    - one cm with two inches, "85(33)" and "85(35)", "88(34)" and "88(35)" (5815131892: each colour of one design has
      one row per cm, its text chart 85 = 84-85 cm, 88 = 87-88 cm): the spelling whose inch is not the profile's
      cm_round takes the cm_round's (85(35) -> W33), when exactly one spelling has it; each keeps its own Korean value
      (never merged: 2026-11-25, the correctness review: the merge rewrote 블랙's "85(35)" to "85(33)", a size 블랙
      does not sell on Naver); _resolve lets them share the US waist only when no choice of the other options sells
      both (combos), else the product holds;
    - two cm on one inch, "85(34)" and "88(34)" (11017948766: its charts give 85 a waist of 85.0 cm, the seller writes
      85(33) elsewhere): the one whose inch is cm_round (88 -> 34) keeps it, the other takes its own cm_round (85 -> 33)
      when no value has that inch; else nothing (held as two Korean sizes on one US size).
    Only "cm(inch)" written so (never adidas' "A76 (31인치)": two codes on one inch stay two sizes and hold), only the
    men's waist profile; the seller's inch wins wherever the inches do not collide."""
    if profile.get("waist_read") != "mens":
        return {}
    got = [(str(v), ci) for v in option.get("values_ko") or [] if _CM_INCH_RE.match(str(v)) and (ci := cm_inch(str(v)))]
    taken: dict[str, int] = {}
    by_cm: dict[int, list[tuple[str, int]]] = {}
    for v, (cm, inch) in got:
        by_cm.setdefault(cm, []).append((v, inch))
    for cm, spellings in by_cm.items():
        if len({i for _, i in spellings}) < 2:
            continue
        rounded = [v for v, i in spellings if i == inch_of(cm, profile)]
        if len(rounded) == 1:
            taken.update({v: inch_of(cm, profile) for v, _ in spellings if v != rounded[0]})
    left = [(v, ci) for v, ci in got if v not in taken]
    by_inch: dict[int, list[tuple[str, int]]] = {}
    for v, (cm, inch) in left:
        by_inch.setdefault(inch, []).append((v, cm))
    inches_used = set(by_inch)
    for inch, spellings in by_inch.items():
        if len({cm for _, cm in spellings}) != 2 or len(spellings) != 2:
            continue
        keep = [v for v, cm in spellings if inch_of(cm, profile) == inch]
        other = [(v, cm) for v, cm in spellings if inch_of(cm, profile) != inch]
        if len(keep) == 1 and len(other) == 1 and (own := inch_of(other[0][1], profile)) not in inches_used \
                and own not in taken.values():
            taken[other[0][0]] = own
    return taken


_ASIAN_RE = re.compile(r"^A(XS|S|M|L|XL|2XL|3XL)\((\d{2,3})\)$")


def _asian_two_numbers(option: dict[str, Any]) -> str | None:
    """adidas' Asian sizes ("AL(95)", read as the chest outside the waist profiles) one to one with their numbers, or
    the hold: "AM (100)" beside "AM (105)" and "AL (105)" (5176506757, 2026-11-24) would merge AM into AL and rewrite
    the Naver option the owner orders."""
    if waist_reading():
        return None
    by_letter: dict[str, set[str]] = {}
    by_num: dict[str, set[str]] = {}
    for v in option.get("values_ko") or []:
        m = _ASIAN_RE.match(re.sub(r"\s+", "", str(v)).upper())
        if m:
            by_letter.setdefault(m.group(1), set()).add(m.group(2))
            by_num.setdefault(m.group(2), set()).add(m.group(1))
    bad = [f"A{k} ({', '.join(sorted(v))})" for k, v in by_letter.items() if len(v) > 1] \
        + [f"{k} (A{', A'.join(sorted(v))})" for k, v in by_num.items() if len(v) > 1]
    return f"{option.get('name_ko')!r}: an adidas Asian size with two numbers ({'; '.join(bad)})" if bad else None


_ASIAN_ANY_RE = re.compile(r"^(A(?:XS|S|M|L|XL|2XL|3XL))(?:\((\d{2,3})\))?$")


def _owner_asian(option: dict[str, Any], hit: tuple[str, dict[str, Any]] | None) -> dict[str, int]:
    """{value: chest} for adidas' Asian letters, bare ("AS") or with a number ("AM (105)"), by the brand row's
    `asian_letters` (the owner, 2026-11-25: AS = 95, AM = 100, AL = 105, AXL = 110, A2XL = 115 for adidas' men's tops;
    the letter wins over the number in brackets, which differs by model: IT7211's chart pairs AM with 105, IM7295's
    with 100, 5176506757); {} without such a row or when a value of the option is no such letter."""
    row = (hit[1].get("asian_letters") or {}) if hit else {}
    values = [str(v) for v in option.get("values_ko") or []]
    got = {v: m.group(1) for v in values if (m := _ASIAN_ANY_RE.match(re.sub(r"\s+", "", v).upper()))}
    if not row or not values or len(got) != len(values) or any(a not in row for a in got.values()):
        return {}
    return {v: int(row[a]) for v, a in got.items()}


def asian_letter_row(profile_name: str, brand: str | None, title: str | None) -> bool:
    """The product's brand row in its profile carries the owner's Asian letters (adidas in mens_tops, 2026-11-25)."""
    hit = brand_row(grids()["profiles"][profile_name], brand, title)
    return bool(hit and hit[1].get("asian_letters"))


def _asian_letters_split(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """The option whose every value ends in a bare adidas Asian letter after a colour ("KG2154 화이트 AS" .. "KG2156 블랙
    A2XL", 13740514016) and each value's (rest, letter); only where the brand row gives the letters (split_joined's
    `asian`), else the A-letter stays no size word (held)."""
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        words = [_words(v) for v in values]
        if not values or any(len(ws) < 2 or not _ASIAN_ANY_RE.match(ws[-1].upper()) or "(" in ws[-1]
                             or parse_label(" ".join(ws[:-1])) for ws in words):
            continue
        out = [(" ".join(ws[:-1]), ws[-1]) for ws in words]
        if len({sz for _, sz in out}) >= 2:
            return i, out
    return None


_LADDER = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
_LADDER_RE = re.compile(r"^(XS|S|M|L|XL|2XL|XXL|3XL|XXXL)\((\d{2,3})\)$")


def _waist_ladder(option: dict[str, Any], profile: dict[str, Any]) -> dict[str, Label]:
    """{value: its label as a waist in cm} for a men's trousers' letter ladder written with its waist in cm from
    under 80 ("S(75) / M(80) / L(85) / XL(90) / 2XL(95)", Nike 10522424335, 2026-11-24: XL(90) read as a top's chest
    and held): consecutive letters, the numbers 66..112 rising in one step, the smallest 80 or under and two under 90;
    else {} (a top's "M(95) / L(100)" stays a chest)."""
    if profile.get("waist_read") != "mens":
        return {}
    values = [str(v) for v in option.get("values_ko") or []]
    got = [(v, _LADDER_RE.match(re.sub(r"\s+", "", v).upper())) for v in values]
    if len(got) < 2 or not all(m for _, m in got):
        return {}
    steps = sorted((_LADDER.index({"2XL": "XXL", "3XL": "XXXL"}.get(m.group(1), m.group(1))), int(m.group(2)), v)
                   for v, m in got if m)
    idx, nums = [x[0] for x in steps], [x[1] for x in steps]
    gaps = {b - a for a, b in zip(nums, nums[1:])}
    if any(b - a != 1 for a, b in zip(idx, idx[1:])) or len(gaps) != 1 or min(gaps) <= 0 \
            or not all(66 <= n <= 112 for n in nums) or min(nums) > 80 or sum(n < 90 for n in nums) < 2:
        return {}
    out = {}
    for _, n, v in steps:
        lab = parse_label(v)
        if lab and lab.chest:
            out[v] = dataclasses.replace(lab, waist=(float(n),), chest=())
    return out


def _merge_bare_letter(resolved: list[dict[str, Any]], merged: dict[str, str], relabel: dict[str, Label]) -> None:
    """A bare letter beside the same letter with its number, both on one US size, is one size written twice ("L"
    beside "L（66사이즈）", 7864006253, 2026-11-24): merged into the numbered one, only when the bare one was sized by
    the chart's or the text's pairing (never the fallback, a brand row or a text waist: 7496732129), both on one
    chest and the bare one's chart row none or the same (9435597606's winter "S" row stays its own)."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in resolved:
        groups.setdefault(r["us"], []).append(r)
    for items in groups.values():
        if len(items) != 2:
            continue
        labs = [relabel.get(r["ko"]) or parse_label(r["ko"]) for r in items]
        for k in (0, 1):
            bare, num, lb, ln = items[k], items[1 - k], labs[k], labs[1 - k]
            if not (lb and ln and lb.letter and not (lb.upto or lb.chest or lb.women or lb.waist or lb.free)
                    and lb.jp is None and ln.letter == lb.letter and (ln.chest or ln.women or ln.waist)):
                continue
            if bare.get("basis") not in ("chart_pair", "text_pair") or bare.get("chest_cm") != num.get("chest_cm") \
                    or bare.get("chart_label") not in (None, num.get("chart_label")):
                continue
            for x, kept in list(merged.items()):
                if kept == bare["ko"]:
                    merged[x] = num["ko"]
            merged[bare["ko"]] = num["ko"]
            resolved.remove(bare)
            break


_BIG_LETTER_WAIST_RE = re.compile(r"^\d{2}\([4-6]XL\)$")   # size_labels reads it as the bare waist (2026-11-25)
_US_SPAN_RE = re.compile(r"(?:US |W)(\d+)(?:-(\d+))?")


def _ladder_broken(resolved: list[dict[str, Any]], relabel: dict[str, Label]) -> str | None:
    """Two letters next to each other on the ladder (XL, 2XL) read two ways (one by the profile's fallback, the other
    by a chart pairing) whose US sizes overlap: "2XL" as "XL-XXL (US 16-18)" beside "XL (US 16)" (2026-11-25, the
    correctness review: 티앤드 5587004670, the OCR misread XL's "XL(31~33)" as "XL(3]~33)", so S..XL fell to the
    fallback while 2XL took the chart's "2XL(33~35)", another style's row with a smaller hip than XL's) -> the hold's
    detail, else None. Bare letters only; one basis for both, a letter range ("S/M"), a gap: never."""
    rungs = []
    for r in resolved:
        lab = relabel.get(r["ko"]) or parse_label(r["ko"])
        letter = {"2XL": "XXL", "3XL": "XXXL"}.get(lab.letter or "", lab.letter) if lab else None
        span = _US_SPAN_RE.search(str(r.get("us") or ""))
        if lab and letter in _LADDER and not lab.upto and span:
            rungs.append((_LADDER.index(letter), r, int(span.group(1)), int(span.group(2) or span.group(1))))
    rungs.sort(key=lambda x: x[0])
    for (i, a, _, a_hi), (j, b, b_lo, _) in zip(rungs, rungs[1:]):
        if j == i + 1 and b_lo <= a_hi and a.get("basis") != b.get("basis"):
            return (f"{b['ko']!r} {b['us']} ({b.get('basis')}) overlaps {a['ko']!r} {a['us']} ({a.get('basis')}): "
                    f"one ladder read two ways")
    return None


# one chest number on a line ("총길이:96,가슴:62,소매길이:76"): a body range ("가슴 82-92") or a row of cells ("가슴 / 46
# / 48") is none
_CHEST_ONE_RE = re.compile(r"(?:가슴|(?<![가-힣])품)(?:\s*(?:단면|너비|폭|둘레))?\s*[:：]?\s*(\d{2,3}(?:\.\d)?)\s*(?:cm)?"
                           r"(?!\s*[-~\d.])(?!\s*[/|]\s*\d)")
_ONE_CHEST_SPAN = 1.5                          # cm: "one chest" when every size's lies this close


def one_chest(texts: list[str], count: int) -> list[float] | None:
    """The chest the seller writes for each of `count` sizes when they are one chest: one number per line, as many
    lines as sizes (two or more), all within _ONE_CHEST_SPAN cm (2026-11-25, 6672050974: an EVA coat's L / XL / XXL
    by height "150-165cm / 165-175cm / 175-190cm", each "가슴:62" / 62 / 63, its kg lines never a chart) -> the
    numbers, else None."""
    found = [float(m.group(1)) for line in texts if (m := _CHEST_ONE_RE.search(str(line)))]
    if count >= 2 and len(found) == count and max(found) - min(found) <= _ONE_CHEST_SPAN:
        return found
    return None


def resolve(options: list[dict[str, Any]], texts: list[str], brand: str | None, title: str | None,
            profile_name: str, table: dict[str, Any] | None = None, has_fact: bool = False,
            combos: list[list[str]] | None = None) -> dict[str, Any]:
    """The sizes of a product (_resolve), waists read when the profile is keyed by the waist (size_labels); a
    Japanese maker's ladder ("S / M / L / O / XO", "SS .. LL / 3L") read as its letters, the chart's labels too, when
    an option holds it (size_labels.japanese_ladder, 2026-11-25)."""
    table = table or grids()
    japanese = {k: v for o in options for k, v in japanese_ladder([str(x) for x in o.get("values_ko") or []]).items()}
    with waist_labels(waist_read(table["profiles"][profile_name])), japanese_letters(japanese):
        return _resolve(options, texts, brand, title, profile_name, table, has_fact, combos)


def _one_combination(values: list[str], index: int, combos: list[list[str]]) -> bool:
    """Two of these size values sold under one choice of the other options (a variant's options without the size)."""
    groups: dict[tuple[str, ...], set[str]] = {}
    for c in combos:
        if len(c) > index:
            groups.setdefault(tuple(c[:index] + c[index + 1:]), set()).add(c[index])
    return any(len(g & set(values)) > 1 for g in groups.values())


def _resolve(options: list[dict[str, Any]], texts: list[str], brand: str | None, title: str | None,
             profile_name: str, table: dict[str, Any] | None = None, has_fact: bool = False,
             combos: list[list[str]] | None = None) -> dict[str, Any]:
    """-> {"version", "profile", "option": index or None, "values": [{ko, us, letter, chest_cm, basis}] in size
    order, "merged": {ko: ko kept}, "chart": {kinds, rows: [{us, cm: {...}}]} or None, "held": detail or None}.
    `has_fact`: the product states its one size as a fact (transform._sizes resolves it): no size option is then
    no unknown size. `combos`: the variants' option values; in the men's trousers two values on one US size are
    allowed when no variant choice of the other options sells both (two models, 82 and M(32), 10076109143)."""
    table = table or grids()
    profile = table["profiles"][profile_name]
    index = size_option(options)
    sections = [v for i, o in enumerate(options) if i != index and not _COLOUR_NAME_RE.search(str(o.get("name_ko") or ""))
                and not any(_COLOUR_VALUE_RE.search(str(x)) for x in o.get("values_ko") or [])
                and not all(parse_label(x) for x in o.get("values_ko") or [])
                for v in o.get("values_ko") or []]
    chart = read_chart(texts, profile.get("measures", "tops"), sections)
    hit = brand_row(profile, brand, title)
    # a row of only the owner's Asian letters (adidas, 2026-11-25) is named only where it sized a value (below)
    asian_only = bool(hit and hit[1].get("asian_letters") and not (set(hit[1]) & {"letters", "system", "us_by_chest"}))
    out: dict[str, Any] = {"version": VERSION, "profile": profile_name, "option": None, "values": [], "merged": {},
                           "brand_row": hit[0] if hit and not asian_only else None, "chart": None, "held": None}
    rows_by_label = [(n, chart.labels.get(n) or parse_label(n), m) for n, m in chart.rows.items()]
    if chart.conflicts:
        out["chart_conflicts"] = list(chart.conflicts)
    typed = _typed_rows(chart, sections)
    if index is None:                                # no size option: one size, its measurements if the chart has
        joined = _joined(options)
        if joined:                                   # "Ivory/085": the Korean size would reach the store (2026-11-20)
            out["held"] = joined
            return out
        listed = list(dict.fromkeys(lab.key for _, lab, _ in rows_by_label
                                    if lab and not lab.free and (lab.chest or lab.women or lab.waist or lab.letter)))
        # ... and the chart's size labels without measures (2026-11-21, the second tops pilot: Nike 13660201494
        # sells only S, written in its title, while its chart names S, M, XL, 2XL: no size reached the store)
        labelled = [n for n, lab in chart.labels.items()
                    if lab and not lab.free and (lab.chest or lab.women or lab.waist or lab.letter)]
        if len(listed) < 2 and len({chart.labels[n].key for n in labelled}) >= 2:
            listed = list(dict.fromkeys(chart.labels[n].key for n in labelled))
            rows_by_label = [(n, chart.labels[n], chart.rows.get(n) or {}) for n in labelled]
        if not has_fact and len(listed) >= 2:       # the chart has rows of several sizes, the product sells one
            names = [n for n, lab, _ in rows_by_label if lab and not lab.free]     # (13004790971: 95..110, 2026-11-20)
            out["held"] = f"no size option, the chart lists {', '.join(names[:6])}: which size is sold is unknown"
            return out
        if typed:                                    # one block per type ("앞면로고" / "뒷면로고": 10885610305)
            out["chart"] = {"kinds": dict(chart.kinds), "rows": typed}
            return out
        one = [r for r in rows_by_label if r[1] and r[1].free] or (rows_by_label if len(rows_by_label) == 1 else [])
        if one:
            out["chart"] = {"kinds": dict(chart.kinds), "rows": [{"us": "One Size", "cm": dict(one[0][2])}]}
        return out
    out["option"] = index
    owner_asian = _owner_asian(options[index], hit)
    if owner_asian and hit:
        out["brand_row"] = hit[0]
    if not owner_asian and (asian := _asian_two_numbers(options[index])):
        out["held"] = asian
        return out
    relabel = _waist_ladder(options[index], profile)
    relabel.update({v: Label(chest=(float(c),)) for v, c in owner_asian.items()})
    # a bare "4XL" where the profile gives it a chest (mens_tops 120, the grid's XXXL: a rain suit's M..4XL,
    # 11859489664, 2026-11-25); parse_label does not read it, so no other profile or joined value changes
    relabel.update({v: Label(letter="4XL") for v in options[index].get("values_ko") or []
                    if re.sub(r"\s+", "", str(v)).upper() in ("4XL", "XXXXL") and "4XL" in profile["letters"]})
    code_inch = _adidas_code_inches(options[index], texts, profile)
    relabel.update({v: Label(waist=(float(v[1:]), round(n * 2.54, 1))) for v, n in code_inch.items()})
    pairs: dict[str, float] = {}                     # the chart's letter -> chest pairings (85 (S), Korea Size row)
    for n, lab in chart.labels.items():
        chest = chart.korea.get(n) or (lab.chest[0] if lab and lab.chest else None)
        if lab and lab.letter and chest and profile.get("key") != "waist":   # "S(90)" over a skirt: no waist
            pairs[lab.letter] = chest
    floors = tip_floors(texts)                       # "엑스라지(XL)사이즈 - 88이상" (7965635614, 2026-11-25)
    bare = [lb.letter for v in options[index]["values_ko"] if (lb := parse_label(v)) and lb.letter
            and not (lb.upto or lb.chest or lb.women or lb.waist or lb.free) and lb.jp is None]
    sized_line = size_line(texts, bare, chart) if bare and len(bare) == len(options[index]["values_ko"]) \
        and profile.get("key") != "waist" else {}
    written = text_pairs(texts)                      # "L[55~66]/XL[77]": the seller's text pairs a letter
    waists, picked = _waist_pairs(texts, profile)    # "S(24-26), M(27-28)": a letter's body waist (2026-11-23)
    # the letters (a women's size beside one too: "S (55)", 11318914118, 2026-11-24) and the women's sizes alone ("55",
    # Toosom 4716253463) the seller's waist may size: every one has its waist, or none is taken (no mix)
    keyed = [_waist_key(lb, FREE_KEY in waists) for v in options[index]["values_ko"] if (lb := parse_label(v))]
    keyed = [k for k in keyed if k]
    if not keyed or not all(x in waists for x in keyed):
        waists = {}
    inch_by_label: dict[str, int] = {}               # the seller's inch per chart label: "77(29)", a 인치 row
    if profile.get("key") == "waist":
        inch_by_label = {n: ci[1] for n in chart.labels if (ci := cm_inch(n))} | dict(chart.inch)

    by_cm_round = _cm_inch_collisions(options[index], profile)

    def seller_inch(ko: str, label: Label) -> int | None:
        """The inch the seller gives this value: its own "77(29)", else its chart label's (a "77(29)" column over
        the bare "77", a 인치 row under its 호칭: 10694535049, 2026-11-24): it wins over cm_round."""
        if profile.get("key") != "waist" or label.letter:
            return None
        if ko in by_cm_round:
            return by_cm_round[ko]
        if ko in code_inch:                          # adidas' bare "A79": its size table's inch (11493370731)
            return code_inch[ko]
        if ci := cm_inch(ko):
            return ci[1]
        for n, inch in inch_by_label.items():
            ci, lab = cm_inch(n), chart.labels.get(n)
            if (ci and label.waist == (float(ci[0]),)) or (n in chart.inch and lab and lab.key == label.key):
                return inch
        return None
    # a letter's women's size from the seller ("55~66(L)", "L[55~66]") counts only when every bare letter of the option
    # has one: M/L/XL over "L[55~66]/XL[77]" would mix two systems (L=S-M before M=M); today's letters then stay
    # (2026-11-20 review)
    for use_women in (True, False):
        out["merged"] = {}
        paired = unpaired = 0
        seen: dict[str, str] = {}                        # the label's key -> the first Korean value with it
        resolved = []
        for ko in options[index]["values_ko"]:
            label = relabel.get(ko) or parse_label(ko)
            if label is None:
                out["held"] = f"{ko!r}: not read as a size"
                return out
            inch = seller_inch(ko, label)
            # a cm size by the inch its chart gives it and its cm: 86 (34) and 88 (35) are two sizes, never one
            # (10694535049); a value written "82(32)" merges as before (_merge_key)
            cm = next((w for w in label.waist if w == int(w)), 0.0)
            same = f"|W{inch}|{cm:g}" if inch and not cm_inch(ko) else _merge_key(label, profile)
            if _A_CM_INCH_RE.match(ko) or ko in code_inch or ko in owner_asian:   # adidas' "A76 (31인치)" and "A79 (31인치)": two codes on one
                same = "A|" + re.sub(r"\s+", "", ko)      # inch are two sizes, never merged (2026-11-24, 8116691038)
            if _BIG_LETTER_WAIST_RE.match(re.sub(r"\s+", "", ko).upper()):   # "36(4XL)" beside another style's "36":
                same = "L|" + re.sub(r"\s+", "", ko)      # its own Naver value, like "30(XL)" (7455950253, 2026-11-25)
            if same in seen:                             # "M (66)" and "M(66)": one size written twice
                out["merged"][ko] = seen[same]
                continue
            seen[same] = ko
            matches = [n for n, lab in chart.labels.items() if lab and (_same(lab, label, profile) or (
                inch and (ci := cm_inch(n)) and label.waist == (float(ci[0]),)) or (   # "77" under "77(29)"
                inch and (ko in code_inch or _A_CM_INCH_RE.match(ko)) and lab.waist and not lab.letter  # adidas' code
                and {inch_of(x, profile) for x in lab.waist} == {inch}))]              # under its "(32)" column
            # the chart's label with measurements, then the one written as the value is, then one with its letter: a
            # bare header label ("SIZE / S / M") or a model line never takes the size's row (2026-11-19 review)
            read = label
            matches.sort(key=lambda n: (n not in chart.rows, chart.labels[n].key != read.key,
                                        chart.labels[n].letter != read.letter))
            own = matches[0] if matches else None
            if label.letter in sized_line:               # the size line's letter: the chart row of its number
                by_number = [n for n, lab in chart.labels.items() if lab and lab.women == sized_line[label.letter].women
                             and n in chart.rows]
                own = by_number[0] if len(by_number) == 1 else None
            item: dict[str, Any] = {"ko": ko}
            # FREE with its range beside another size ("Free(55-66)" and "L", 5875520955, 2026-11-22) is that range,
            # never "One Size" (a US buyer reads it as fitting all); alone it stays One Size
            ranged = label.free and (label.women or label.chest or label.waist) and len(options[index]["values_ko"]) > 1
            free_rows = [n for n in matches if (fm := chart.labels[n]) and fm.free and (fm.women or fm.chest or fm.waist)]
            if label.free and not ranged and len(options[index]["values_ko"]) > 1 and len(free_rows) == 1:
                # a bare "프리(F)" beside "라지(L)" takes its chart row's range, "F-프리(55~66)" (7965635614,
                # 2026-11-25): never One Size beside other sizes
                own = free_rows[0]
                label, ranged = chart.labels[own] or label, True
            if label.free and not ranged:
                item.update(us="One Size", letter=None, chest_cm=None, basis="free")
            elif own and own in chart.us:
                letter = chart.us[own]
                row = next((r for r in profile["grid"] if r["us"] == letter), None)
                item.update(us=_us_text([row]) if row else letter, letter=letter,
                            chest_cm=row["chest_cm"] if row else None, basis="chart_us")
            elif hit and hit[1].get("system") == "us" and label.letter:
                row = next((r for r in profile["grid"] if r["us"] == label.letter), None)
                item.update(us=_us_text([row]) if row else label.letter, letter=label.letter,
                            chest_cm=None, basis=f"brand_us:{hit[0]}")
            else:
                chests, basis, women = _chest_of(label, profile), "label", False
                if inch:                                   # its own "77(29)": a waist label; a chart's inch
                    chests, basis = [round(inch * 2.54, 1)], ("cm_round" if ko in by_cm_round
                                                              else "waist" if cm_inch(ko) else "chart_inch")
                elif label.women and (wk := _waist_key(label, FREE_KEY in waists)) and wk in waists:   # the seller's waist over the
                    # women's size: "S (55)", "55" (a bare letter takes it below, after the chart's pairing)
                    chests, basis = list(waists[wk]), "text_waist"
                if not chests and label.jp is not None and own and chart.korea.get(own):
                    chests, basis = [chart.korea[own]], "chart_korea"
                if not chests and label.upto and label.letter:     # "S/M": both letters' chests, a range
                    ends = [_letter_chest(x, pairs, hit, profile) for x in (label.letter, label.upto)]
                    if all(ends):
                        chests, basis = [e for e in ends if e], "letter_range"
                mate = chart.labels.get(own) if own else None
                if not chests and label.letter in sized_line:   # "S(55), M(66), L(77)" over the chart's M(55)
                    chests, basis, women = _chest_of(sized_line[label.letter], profile), "text_line", True   # 9317474764
                floor = floors.get(label.letter or "")
                if use_women and not chests and mate and mate.women and mate.letter == label.letter and floor \
                        and len(mate.women) == 1 and mate.women[0] != floor:
                    # the chart's open "XL(77~)" against the seller's tip "엑스라지(XL)사이즈 - 88이상" (7965635614,
                    # 2026-11-25): the size both allow, the tip's 88 (the chart's 77 is inside L's "66~77")
                    chests, basis, women = _chest_of(Label(letter=label.letter, women=(floor,)), profile), "text_tip", True
                if not chests and mate and mate.chest and profile.get("key") != "waist":
                    chests, basis = list(mate.chest), "chart_pair"
                if not chests and label.letter in picked and label.letter in waists and not label.upto:
                    # the ladder's range over the chart's row label "L(27~29)" (12370291326, 2026-11-25)
                    chests, basis = list(waists[label.letter]), "text_waist"
                if not chests and mate and profile.get("key") == "waist" and _chest_of(mate, profile):
                    chests, basis = _chest_of(mate, profile), "chart_pair"     # a waist the chart pairs ("S(25)")
                if use_women and not chests and mate and mate.women and mate.letter == label.letter:
                    chests, basis, women = _chest_of(mate, profile), "chart_pair", True   # "55~66(L)" (9353856438)
                if not chests and label.letter and label.letter in pairs:
                    chests, basis = [pairs[label.letter]], "chart_pair"
                if not chests and label.letter and not label.upto and label.letter in waists:
                    chests, basis = list(waists[label.letter]), "text_waist"
                if use_women and not chests and label.letter and not label.upto and label.letter in written:
                    chests, basis, women = _chest_of(written[label.letter], profile), "text_pair", True
                if not chests and label.letter and hit and label.letter in (hit[1].get("letters") or {}):
                    chests, basis = [hit[1]["letters"][label.letter]], f"brand:{hit[0]}"
                if not chests and label.letter and label.letter in profile["letters"] and not label.women \
                        and not (label.chest and profile.get("waist_read") == "mens"):   # "M(95)" in pants: a top
                    # a women's size the profile cannot map ("XL(66~66반)" in the tops) holds, never its bare
                    # letter (2026-11-22, the skirts review: XL(66~66반) went out XL, two sizes over the 66)
                    chests, basis = [profile["letters"][label.letter]], "fallback_letters"
                grid_rows = [r for c in sorted(set(chests)) if (r := _grid_row(profile, c))]
                if not chests or len(grid_rows) != len(set(chests)):
                    out["held"] = f"{ko!r}: no US size ({'chest ' + str(chests) if chests else 'not read'})"
                    return out
                grid_rows = sorted({r["chest_cm"]: r for r in grid_rows}.values(), key=lambda r: r["chest_cm"])
                item.update(us=_us_text(grid_rows), letter=grid_rows[0]["us"] if len(grid_rows) == 1 else None,
                            chest_cm=grid_rows[0]["chest_cm"], basis=basis)
                own_us = _brand_us(hit, grid_rows, profile)
                if own_us and hit:                           # the maker's own US number for its Korean size
                    item.update(us=own_us[0], letter=own_us[1], basis=f"brand_us_num:{hit[0]}")
                elif (basis == "label" and len({inch_of(w, profile) for w in label.waist}) == 1
                      and len(grid_rows) == 1 and not label.women) or (inch and len(grid_rows) == 1):
                    # a waist size ("26", "27", "67"): the US number of that waist, so 26 and 27 stay two sizes
                    # (S (US 4), S (US 6)); the skirts, 2026-11-22; one waist in inches and cm ("30(76)", the men's
                    # trousers 2026-11-23) is one; the seller's inch as written ("77(29)": W29, 2026-11-24)
                    num = (profile.get("us_by_waist_in") or {}).get(str(inch or inch_of(label.waist[0], profile)))
                    row = next((r for r in profile["grid"] if num and r.get("us_num")
                                and _us_range(r["us_num"])[0] <= _us_range(num)[0] <= _us_range(r["us_num"])[1]), None)
                    if num and row:                          # the letter whose US numbers hold it (70 cm: US 8, M)
                        pre = row.get("us_num_prefix", "US ")
                        item.update(us=f"{pre}{num}" if row.get("us_num_only") else f"{row['us']} ({pre}{num})",
                                    letter=row["us"],
                                    chest_cm=row["chest_cm"],
                                    basis="waist" if basis in ("label", "waist") else basis)
                elif basis == "label" and len(label.waist) == 2 \
                        and (span := [inch_of(w, profile) for w in label.waist])[1] == span[0] + 1 \
                        and not (label.letter or label.women or label.chest) \
                        and all(r.get("us_num_only") for r in grid_rows) \
                        and item["us"] != f"{grid_rows[0].get('us_num_prefix', 'US ')}{span[0]}-{span[1]}":
                    # a seller's inch range is the US waist as written, never the bands it touches joined: "33~34인치"
                    # W33-34, not W32-35 beside "32~33인치" W32-33 and "34~35인치" W34-35; "38~39인치" W38-39 (Nike
                    # 8000226696, 2026-11-24); one inch apart, low to high: "33-30", "32-34" are a waist and a
                    # length (9918112671), never a waist range
                    item.update(us=f"{grid_rows[0].get('us_num_prefix', 'US ')}{span[0]}-{span[1]}", basis="waist")
                if women:
                    paired += 1
                elif label.letter and not (label.upto or label.chest or label.women or label.waist) \
                        and (basis == "fallback_letters" or basis.startswith("brand:")):
                    unpaired += 1                    # a bare letter the seller left without a women's size
            item["chart_label"] = own
            resolved.append(item)
        if not (paired and unpaired):
            break
    _by_position(resolved, chart, profile)
    _merge_bare_letter(resolved, out["merged"], relabel)
    us = [r["us"] for r in resolved]
    dup = sorted({u for u in us if us.count(u) > 1})
    for r in resolved:                               # the owner's letter, never the bracket (2026-11-25)
        if r["ko"] in owner_asian and hit:
            r["basis"] = f"brand_asian:{hit[0]}"
    if owner_asian:                                  # the charts' numbers differ by model (5176506757): none shown
        out["chart_left_out"] = "adidas' Asian letters sized by the owner's row (AM = 100 ...), not the charts' numbers"
    if dup and combos is not None and (profile.get("waist_read") == "mens"
                                       or all(r["ko"] in owner_asian for r in resolved if r["us"] in dup)) \
            and not any(_one_combination([r["ko"] for r in resolved if r["us"] == u], index, combos) for u in dup) \
            and all(r["ko"] not in out["merged"].values() for r in resolved if r["us"] in dup):
        # two models of one listing, each with its own spelling of one waist: the fleece "82" and the plain "M(32)"
        # are both W32, no colour of a model sells both (soneva 10076109143, 2026-11-25: its text gives both a waist
        # of 81 cm); each stays its own Naver value, never merged. Their chart: only when each shared waist is one
        # cm written with two inches ("85(33)" / "85(35)", 5815131892: one row); else none (2026-11-25, the
        # correctness review: the plain model's XL(35) showed the fleece 88's row, the same garment waist as W34)
        shared = [[r["ko"] for r in resolved if r["us"] == u] for u in dup]
        if not all(len({(cm_inch(k) or (None,))[0] for k in group}) == 1 and all(cm_inch(k) for k in group)
                   for group in shared):
            out["chart_left_out"] = "two models' sizes on one US size: " + "; ".join(" / ".join(g) for g in shared)
        dup = []
    if dup:
        out["held"] = f"two Korean sizes on one US size: {', '.join(dup)}"
        return out
    if broken := _ladder_broken(resolved, relabel):
        out["held"] = broken
        return out
    if len(resolved) >= 2 and all(r["basis"] == "fallback_letters" for r in resolved) \
            and (chests_said := one_chest(texts, len(resolved))):
        # bare letters sized by the profile's chests while the seller gives every one the same chest: the letters
        # are lengths or height classes of one garment (6672050974's EVA coat, 2026-11-25), never a US size each
        out["held"] = (f"one chest for every size ({', '.join(f'{c:g}' for c in chests_said)} cm): the letters "
                       f"{', '.join(r['ko'] for r in resolved)} are no chest sizes")
        return out
    order = {r["us"]: i for i, r in enumerate(profile["grid"])}
    resolved.sort(key=lambda r: (r["chest_cm"] is None, r["chest_cm"] or 0, order.get(r["letter"] or "", 99),
                                 int(m.group(1)) if (m := re.search(r"(?:W|US )(\d+)", str(r.get("us") or "")))
                                 else 0))                                      # W34 before W35 in one band (2026-11-23)
    out["values"] = resolved
    _ordered_rows(resolved, chart)
    if typed and all(r["us"] == "One Size" for r in resolved):      # FREE sold in types: a row per type
        out["chart"] = {"kinds": dict(chart.kinds), "rows": typed}
        return out
    rows = [{"us": r["us"], "cm": dict(chart.rows[r["chart_label"]])} for r in resolved
            if r["chart_label"] and chart.rows.get(r["chart_label"])]
    if rows and not out.get("chart_left_out"):
        out["chart"] = {"kinds": dict(chart.kinds), "rows": rows}
    return out


# --- the storefront's size chart -----------------------------------------------------------------------------------

def inches(cm: float) -> float:
    return round(cm / 2.54 * 2) / 2


def _in(x: float) -> str:
    return f"{x:g}"


CHART_MARK = "<h3>Size chart (US)</h3>"       # the block's start: sweep reads the description without it


def chart_html(sizes: dict[str, Any], table: dict[str, Any] | None = None,
               section_en: Callable[[str], str] | None = None) -> str:
    """The size chart block at the end of the description (US sizes, inches); "" when there is nothing to show.
    Garment chest laid flat (단면) is doubled; the body bust is the profile's band for the size. `section_en`: the
    English of a type's Korean value, for a one-size chart per type ("One Size (Front Logo)")."""
    if sizes.get("kind") == "shoes":                 # shoes: the foot length (shoe_sizes.py, 2026-11-25)
        import shoe_sizes
        return shoe_sizes.chart_html(sizes)
    table = table or grids()
    profile = table["profiles"][sizes["profile"]]
    values = sizes.get("values") or []
    # a mixed product sized per gender (2026-11-25, 7266270685): each value's band from its own profile
    own = {v["us"]: table["profiles"][v.get("profile") or sizes["profile"]] for v in values}
    fits_words = list(dict.fromkeys(p.get("fit", "bust") for p in own.values())) or [profile.get("fit", "bust")]
    chart = sizes.get("chart") or {}
    measured = {r["us"]: r["cm"] for r in chart.get("rows") or []}
    kinds = chart.get("kinds") or {}
    rows_in = chart.get("rows") or []
    fields = [f for f in measure_names(profile.get("measures", "tops")) if any(f in r["cm"] for r in rows_in)]
    names = {"chest": "Garment chest", "length": "Length", "shoulder": "Shoulder", "sleeve": "Sleeve",
             "waist": "Garment waist", "hip": "Hip", "thigh": "Thigh", "rise": "Rise", "hem": "Leg opening",
             "inseam": "Inseam"}                                                     # trousers (2026-11-23)
    # a value laid flat (단면) is doubled; with no word, under this
    flat_under = {"chest": 75, "waist": 53, "hip": 72, "thigh": 42, "hem": 32}

    def garment(field_: str, cm: float) -> float:
        if field_ not in flat_under:
            return inches(cm)
        flat = kinds.get(field_) == "flat" or (kinds.get(field_) in (None, "mixed") and cm < flat_under[field_])
        return inches(cm * 2 if flat else cm)

    rows = []
    if values:
        fits = f"Fits {' / '.join(fits_words)}"             # "Fits chest" for men's tops (2026-11-21)
        head = ["Size", fits] + [names.get(f, f.title()) for f in fields]
        shown: set[str] = set()
        for v in values:
            if v["us"] in shown:                             # two models' spellings of one waist (10076109143)
                continue
            shown.add(v["us"])
            vp = own[v["us"]]
            band = {r["us"]: r["bust_in"] for r in vp["grid"]}.get(v["letter"] or "") if v.get("letter") else None
            if v["us"] != "One Size" and band is None and v.get("chest_cm"):
                lo = _grid_row(vp, v["chest_cm"])
                band = lo["bust_in"] if lo else None
            cells = [v["us"], f"{_in(band[0])}–{_in(band[1])} in" if band else "—"]
            m = measured.get(v["us"]) or {}
            cells += [f"{_in(garment(f, m[f]))} in" if f in m else "—" for f in fields]
            rows.append(cells)
    elif rows_in:
        head = ["Size"] + [names.get(f, f.title()) for f in fields]
        for row in rows_in:
            us, m = row["us"], row["cm"]
            if row.get("section_ko"):
                us = f"{us} ({section_en(row['section_ko']) if section_en else row['section_ko']})"
            rows.append([us] + [f"{_in(garment(f, m[f]))} in" if f in m else "—" for f in fields])
    else:
        return ""
    fit_note = (f"Fits {' / '.join(fits_words)} is the body measurement each size is made for; " if values
                else "")
    rounds = [{"hem": "leg opening"}.get(f, f) for f in ("chest", "waist", "hip", "thigh", "hem") if f in fields] \
        or ["chest"]
    round_ = rounds[0] if len(rounds) == 1 else ", ".join(rounds[:-1]) + " and " + rounds[-1]
    note = (f"{fit_note}the garment measurements are the maker's, the {round_} all the way round, to within about 1 in."
            if fields else f"{fit_note}the maker gave no garment measurements.")
    note = note[0].upper() + note[1:]
    block = _el("table", [_el("thead", [_el("tr", [_el("th", h) for h in head])]),
                          _el("tbody", [_el("tr", [_el("td", c) for c in r]) for r in rows])], ' class="size-chart"')
    return f"{CHART_MARK}{block}<p>{note}</p>"


def _el(tag: str, inner: str | list[str], attrs: str = "") -> str:
    """An element as Shopify stores it (2026-11-19: it rewrote the table with line breaks, so every draft read as
    changed): text inline; one child inline ("<thead><tr>"); several children each on a line of its own."""
    if isinstance(inner, str):
        return f"<{tag}{attrs}>{inner}</{tag}>"
    if len(inner) == 1:
        return f"<{tag}{attrs}>{inner[0]}</{tag}>"
    return f"<{tag}{attrs}>\n" + "\n".join(inner) + f"\n</{tag}>"
