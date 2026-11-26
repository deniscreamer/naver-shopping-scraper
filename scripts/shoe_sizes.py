"""Korean shoe sizes (mm) -> US sizes, per product, and the section a pair goes to (the owner, 2026-11-25; the doc:
scripts/SIZES.md "Shoes").

Pure and offline. A Korean shoe size is the foot length in millimetres ("250", "255mm", "265(US 8.5)"); the owner's
chart (2026-11-25, "окей, лучше конечно трансформировать в размеры для аудитории США"):

    men's    250 = US 7, 255 = 7.5, 260 = 8 ... 280 = 10, 290 = 11, 300 = 12   (US = (mm - 180) / 10)
    women's  220 = US 5, 225 = 5.5, 230 = 6 ... 250 = 8, 260 = 9              (US = (mm - 170) / 10)

A pair stated men's shows "US 9 (270 mm)", stated women's "US 8 (250 mm)"; a unisex, mixed or unstated pair shows
both, "US M 9 / W 10 (270 mm)". The seller's own value stays the Naver value the owner orders (variant
fairwardgolf.source sizeKo). A width word beside the size (와이드, EEE, 2E; FootJoy's W / XW before it) follows the US
size: "US 9 Wide (270 mm)", "US 9 Extra Wide (270 mm)". A value with no millimetre size, or two values on one US size, holds the product (size_unmapped): an invented
size is worse than none.

The section (section_gender): the two sections split by gender, one section a product (the owner, 2026-11-25). A pair
stated men's or women's goes there unless its sizes say the other (a men's pair sold only up to 245 mm, a women's pair
only from 260 mm: held, the title or the row is a keyword); a unisex, mixed or unstated pair by its largest size:
270 mm or more men's, 250 mm or less women's; between, a unisex or mixed pair men's (the owner: "если не
определилось, кладём в мужской"), an unstated one unknown (placement holds it).
"""
import re
from typing import Any

VERSION = "shoe-sizes/2"                     # bump on a change of what resolve() returns
MM_MIN, MM_MAX = 200, 320                    # a foot length a golf shoe is sold in
MENS_FROM, WOMENS_UPTO = 270, 250            # section_gender: a largest size at or over / at or under
MENS_FLOOR, WOMENS_CEILING = 245, 260        # a stated gender its sizes contradict (all under / all over)

_SIZE_NAME_RE = re.compile(r"사이즈|size|치수|mm|발길이|문수", re.I)
# a size in mm: three digits 200-320 ending in 0 or 5, not part of a longer number or a model code ("GY8525")
_MM_RE = re.compile(r"(?<![\d.A-Za-z])(2\d[05]|3[01][05]|320)(?:\s*(?:mm|㎜|미리))?(?![\d.])", re.I)
_WIDE_RE = re.compile(r"와이드|wide|광폭|(?<![A-Za-z])(?:EEEE|EEE|EE|4E|3E|2E)(?![A-Za-z])", re.I)
# FootJoy's width letter before the size, "XW 240", "W 220" (10239862675, 2026-11-25: XW the men's extra wide, W the
# women's wide, M medium): only right before the number, never a lone W elsewhere ("화이트(W)")
_WIDTH_CODE_RE = re.compile(r"(?<![A-Za-z])(XW|W|M|N)\s*(?=(?:2\d[05]|3[01][05])(?!\d))")
_US_NOTE_RE = re.compile(r"[(\[]?\s*(?:US|미국)\s*\d{1,2}(?:\.5)?\s*[)\]]?", re.I)


# a size range, "255~260" (ECCO 9887518096, 2026-11-25: one EU size covering two Korean sizes), 5 or 10 mm wide
_RANGE_RE = re.compile(r"(?<![\d.A-Za-z])(2\d[05]|3[01][05])\s*(?:mm)?\s*[~-]\s*(2\d[05]|3[01][05])(?:\s*mm)?(?![\d.])", re.I)
# a size in centimetres, "24.5", "25.0cm", "22.5cm 3E" (purchase agencies, New Balance 13723837420, adidas 13559414510,
# 2026-11-26): 20.0-32.0 with .0 or .5, read as its mm; never a US size (under 16) or a bare "25"
_CM_RE = re.compile(r"(?<![\d.A-Za-z])(2\d|3[0-2])\.([05])\s*(?:cm|㎝|센티)?(?![\d.])", re.I)
# two Korean sizes one EU size covers, "235/240(37)", "40호 (255/260mm)" (ECCO 9204921561 / 12089884228, 2026-11-26):
# a range, only 5 mm apart ("250/260", "250/270" stay two sizes)
_PAIR_RE = re.compile(r"(?<![\d.A-Za-z])(2\d[05]|3[01][05])\s*/\s*(2\d[05]|3[01][05])(?:\s*mm)?(?![\d.])", re.I)
# a pair sold as seconds beside the sound ones, "스크래치 280" (MNX15 5402813627, 2026-11-25): never sold
SECONDS_RE = re.compile(r"스크래치|scratch|B급|하자|리퍼|전시|반품|중고", re.I)


def seconds_listing(options: list[dict[str, Any]], title: str | None) -> str | None:
    """The whole listing sells seconds: an option named so ("스크래치상품", 4767184925, 2026-11-25: every pair B급) or
    the title says it. -> the word's place, or None."""
    for o in options:
        if SECONDS_RE.search(str(o.get("name_ko") or "")):
            return f"option {o.get('name_ko')!r}"
    if SECONDS_RE.search(str(title or "")):
        return "the title"
    return None


# a spiked variant of a spikeless listing, "스파이크유무: 스파이크 / 스파이크리스" (Eagle Eyed 11574034936, 2026-11-25)
SPIKED_VALUE_RE = re.compile(r"^\s*(?:스파이크|스파이크형|스파이크화|징|spike|spiked|cleated)\s*$", re.I)
# a laced pair sold beside the BOA one, "2.UG슈즈(끈타입)" (Prito 6510500952, 2026-11-26): left out like a spiked one;
# "레트로크로스 슈레이스" (adidas Retrocross 13635116576, the 100 pilot's review 2026-11-26)
LACED_VALUE_RE = re.compile(r"끈\s*타입|\(끈\)|레이스\s*업|슈\s*레이스|shoe\s*lace|lace[\s-]?up|laced", re.I)


def mm_span(value: Any) -> tuple[int, int] | None:
    """(the smallest, the largest) mm size a value states: one size ("250", "255mm", "265(US 8.5)", "270 와이드") is
    (250, 250), a range "255~260" (255, 260); None for none, two unrelated sizes or a value outside MM_MIN-MM_MAX."""
    text = _CM_RE.sub(lambda m: str(int(m.group(1)) * 10 + int(m.group(2))), _US_NOTE_RE.sub(" ", str(value or "")))
    if (p := _PAIR_RE.search(text)) and int(p.group(2)) - int(p.group(1)) == 5:
        text = text[:p.start()] + f"{p.group(1)}~{p.group(2)}" + text[p.end():]
    if (r := _RANGE_RE.search(text)) and 5 <= int(r.group(2)) - int(r.group(1)) <= 10:
        lo, hi = int(r.group(1)), int(r.group(2))
        if not _MM_RE.search(text[:r.start()] + " " + text[r.end():]):
            return (lo, hi) if MM_MIN <= lo and hi <= MM_MAX else None
    found = {int(m.group(1)) for m in _MM_RE.finditer(text)}
    one = next(iter(found)) if len(found) == 1 else None
    return (one, one) if one is not None and MM_MIN <= one <= MM_MAX else None


def mm_of(value: Any) -> int | None:
    """The millimetre size a value states (a range's smallest), else None."""
    span = mm_span(value)
    return span[0] if span else None


# a colour and a size joined in one value, "JQ0993 화이트실버 245", "블랙(01001)_255~260", "여) JQ0996 화이트블랙 225"
# (adidas SPW 13103847433 / 13335983300, ECCO 9887518096, 2026-11-25): the size at the end after a space, "_" or "/",
# or right after a closing bracket, "(화이트그레이)250" (2026-11-26)
_JOINED_RE = re.compile(r"^(?P<rest>.*\S)(?:[\s_/]+|(?<=\)))(?P<size>(?:XW|W)?\s*(?:2\d[05]|3[01][05])(?:\s*mm)?"
                        r"(?:\s*[~-]\s*(?:2\d[05]|3[01][05])(?:\s*mm)?)?)$", re.I)


def split_joined(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """(the option, [(the rest, the size)] per value) when no option is a size option and one option's every value
    ends in a mm size after a colour or a code; else None."""
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        # "(화이트그레이)250" (FootJoy Flow 2.0 11442646718, New Balance 574B 12148138149, 2026-11-26): the colour in
        # brackets right before the size, the brackets dropped
        parts = [(re.sub(r"^\((.+)\)$", r"\1", m.group("rest").strip()), m.group("size").strip())
                 if (m := _JOINED_RE.match(v.strip())) else None for v in values]
        # FootJoy's width after its style code, "51143 W 화이트실버 245" (Versafit 11886292855): the width goes with the
        # size ("W 245": Wide), the colour keeps the code and the name
        parts = [((m.group(1) + " " + m.group(3)).strip(), f"{m.group(2)} {p[1]}") if p and (m := _FJ_WIDTH_RE.match(p[0]))
                 else p for p in parts]
        if values and all(p and mm_span(p[1]) and not mm_span(p[0]) and not _WIDTH_ONLY_RE.match(p[0])
                          and not SECONDS_RE.fullmatch(p[0]) for p in parts) \
                and len({p[0] for p in parts if p}) < len(values) \
                and not any(size_option([x]) is not None for k, x in enumerate(options) if k != i):
            return i, [p for p in parts if p]
    return None


_FJ_WIDTH_RE = re.compile(r"^(\d{5})\s+(XW|W|M)\s+(.+)$")
_WIDTH_ONLY_RE = re.compile(r"^(?:XW|W|M|N|와이드|광폭|wide|EEEE|EEE|EE|4E|3E|2E)$", re.I)


def width(value: Any) -> str:
    """The width a value names: "Extra Wide" (XW), "Wide" (와이드, EEE, 2E, W before the size), "" (medium, none)."""
    text = _US_NOTE_RE.sub(" ", str(value or ""))
    code = _WIDTH_CODE_RE.search(text)
    if code and code.group(1).upper() == "XW":
        return "Extra Wide"
    if (code and code.group(1).upper() == "W") or _WIDE_RE.search(text):
        return "Wide"
    return ""


def wide(value: Any) -> bool:
    return bool(width(value))


def us_mens(mm: int) -> float:
    return (mm - 180) / 10


def us_womens(mm: int) -> float:
    return (mm - 170) / 10


def _n(x: float) -> str:
    return f"{x:g}"


def us_label(mm: int, gender: str, wide_word: str = "", hi: int | None = None, mark: bool = False) -> str:
    """"US 9 (270 mm)" men's or women's; "US M 9 / W 10 (270 mm)" for a unisex, mixed or unstated pair; a range
    "US 7.5-8 (255-260 mm)"; `mark`: a men's or a women's value of a mixed product, "US M 7 (250 mm)" / "US W 7 (240 mm)"
    (the men's pilot review 2026-11-25: 4978188842's "230 [여성용]" and "250 [남성용]" read "US 7" twice)."""
    def us(f: Any) -> str:
        return _n(f(mm)) + (f"-{_n(f(hi))}" if hi and hi != mm else "")
    if gender == "mens":
        label = f"US {'M ' if mark else ''}{us(us_mens)}"
    elif gender == "womens":
        label = f"US {'W ' if mark else ''}{us(us_womens)}"
    else:
        label = f"US M {us(us_mens)} / W {us(us_womens)}"
    mms = f"{mm}-{hi}" if hi and hi != mm else f"{mm}"
    return f"{label}{' ' + wide_word if wide_word else ''} ({mms} mm)"


def size_option(options: list[dict[str, Any]]) -> int | None:
    """The size option: the one whose values are mostly millimetre sizes (its name only breaks a tie)."""
    best: tuple[int, int, int] | None = None
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        sized = sum(1 for v in values if mm_of(v))
        if values and sized * 2 > len(values):
            score = (sized, 1 if _SIZE_NAME_RE.search(str(o.get("name_ko") or "")) else 0, -i)
            best = max(best, score) if best else score
    return -best[2] if best else None


def sizes_mm(options: list[dict[str, Any]]) -> list[int]:
    i = size_option(options)
    return sorted({m for v in (options[i].get("values_ko") or []) if (sp := mm_span(v)) for m in sp}) \
        if i is not None else []


def section_gender(stated: str | None, mm: list[int]) -> tuple[str, str]:
    """(the section's gender or "unknown" or "conflict", why) of a pair stated `stated` (attributes' gender value)
    selling the sizes `mm`."""
    if stated in ("mens", "womens"):
        if mm and stated == "mens" and max(mm) <= MENS_FLOOR:
            return "conflict", f"stated men's, sold only up to {max(mm)} mm"
        if mm and stated == "womens" and min(mm) >= WOMENS_CEILING:
            return "conflict", f"stated women's, sold only from {min(mm)} mm"
        return stated, f"stated {stated}"
    if not mm:
        return "unknown", f"{stated or 'no gender'} stated, no size in mm"
    span = f"{min(mm)}-{max(mm)} mm"
    if max(mm) >= MENS_FROM:
        return "mens", f"{stated or 'no gender'} stated, sizes {span}"
    if max(mm) <= WOMENS_UPTO:
        return "womens", f"{stated or 'no gender'} stated, sizes {span}"
    if stated in ("unisex", "mixed"):
        return "mens", f"{stated} stated, sizes {span}: men's (the owner 2026-11-25)"
    return "unknown", f"no gender stated, sizes {span}"


def resolve(options: list[dict[str, Any]], stated: str | None,
            value_genders: dict[str, set[str]] | None = None, unisex_said: bool = False) -> dict[str, Any]:
    """-> {"version", "kind": "shoes", "profile": shoes_mens | shoes_womens | shoes_unisex, "option": index or None,
    "values": [{ko, us, mm, wide, letter: None, chest_cm: None, basis: "mm"}] in size order, "merged": {}, "chart": None,
    "brand_row": None, "held": detail or None}. `stated`: the product's gender as stated (mens, womens, or anything
    else: both labels). `value_genders`: the genders of the variants that sell each size value (attributes' per-variant
    gender): a value only men's or only women's variants sell takes that gender's label (FootJoy 10239862675, 2026-11-25:
    "XW 240" its men's, "W 240" its women's). `unisex_said`: the title or the 성별 row says unisex beside one gender
    (adidas 13575338957, 2026-11-25: row 남성용, title 남녀공용, sizes 220-295): both labels, never a woman's 230 as "US 5"."""
    gender = stated if stated in ("mens", "womens") and not unisex_said else "unisex"
    out: dict[str, Any] = {"version": VERSION, "kind": "shoes", "profile": f"shoes_{gender}", "option": None,
                           "values": [], "merged": {}, "chart": None, "brand_row": None, "held": None}
    i = size_option(options)
    if i is None:
        named = [o for o in options if _SIZE_NAME_RE.search(str(o.get("name_ko") or ""))]
        out["held"] = (f"{named[0].get('name_ko')!r} ({', '.join(map(str, (named[0].get('values_ko') or [])[:4]))}"
                       "): not read as sizes in mm" if named else "no size option: which size is sold is unknown")
        return out
    out["option"] = i
    values: list[dict[str, Any]] = []
    # per value only when every value is one gender's: a shared size list with "US 7.5 (245 mm)" women's beside "US 7.5
    # (255 mm)" men's would read as one size twice (adidas S2G 13171935653, 낫소 4822059321: both labels then)
    split = bool(value_genders) and all(len(g := (value_genders or {}).get(str(v)) or set()) == 1
                                        and g <= {"mens", "womens"} for v in options[i].get("values_ko") or [])
    for v in options[i].get("values_ko") or []:
        span = mm_span(v)
        if span is None:
            out["held"] = f"{v!r}: not read as a size in mm"
            return out
        mm, hi = span
        own = (value_genders or {}).get(str(v)) or set()
        one = next(iter(own)) if split and len(own) == 1 else gender
        values.append({"ko": str(v), "us": us_label(mm, one, width(v), hi, mark=split), "mm": mm, **({"mm_hi": hi} if hi != mm else {}), "wide": width(v), "letter": None,
                       "chest_cm": None, "basis": "mm"})
    us = [x["us"] for x in values]
    if dup := sorted({u for u in us if us.count(u) > 1}):
        out["held"] = f"two Korean sizes on one US size: {', '.join(dup)}"
        return out
    out["values"] = sorted(values, key=lambda x: (["", "Wide", "Extra Wide"].index(x["wide"]), x["mm"]))
    return out


def chart_html(sizes: dict[str, Any]) -> str:
    """The size chart block at the end of the description: the US size and the foot length it fits."""
    from apparel_sizes import CHART_MARK, _el
    rows = [[v["us"].split(" (")[0], f"{v['mm']}-{v['mm_hi']} mm" if v.get("mm_hi") else f"{v['mm']} mm",
             f"{v['mm'] / 25.4:.1f}-{v['mm_hi'] / 25.4:.1f} in" if v.get("mm_hi") else f"{v['mm'] / 25.4:.1f} in"]
            for v in sizes.get("values") or [] if v.get("mm")]
    if not rows:
        return ""
    block = _el("table", [_el("thead", [_el("tr", [_el("th", h) for h in ("Size", "Foot length", "Foot length (in)")])]),
                          _el("tbody", [_el("tr", [_el("td", c) for c in r]) for r in rows])], ' class="size-chart"')
    note = ("Korean shoe sizes are the foot length in millimetres; the US size is converted from it. "
            "Measure your foot heel to toe and pick the size whose foot length is the same or a little longer.")
    return f"{CHART_MARK}{block}<p>{note}</p>"
