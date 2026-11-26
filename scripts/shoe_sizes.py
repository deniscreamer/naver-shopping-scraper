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

VERSION = "shoe-sizes/1"                     # bump on a change of what resolve() returns
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


def mm_of(value: Any) -> int | None:
    """The one millimetre size a value states ("250", "255mm", "265(US 8.5)", "270 와이드"), else None (none, or two)."""
    text = _US_NOTE_RE.sub(" ", str(value or ""))
    found = {int(m.group(1)) for m in _MM_RE.finditer(text)}
    return found.pop() if len(found) == 1 and MM_MIN <= next(iter(found)) <= MM_MAX else None


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


def us_label(mm: int, gender: str, wide_word: str = "") -> str:
    """"US 9 (270 mm)" men's or women's; "US M 9 / W 10 (270 mm)" for a unisex, mixed or unstated pair."""
    if gender == "mens":
        us = f"US {_n(us_mens(mm))}"
    elif gender == "womens":
        us = f"US {_n(us_womens(mm))}"
    else:
        us = f"US M {_n(us_mens(mm))} / W {_n(us_womens(mm))}"
    return f"{us}{' ' + wide_word if wide_word else ''} ({mm} mm)"


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
    return sorted({m for v in (options[i].get("values_ko") or []) if (m := mm_of(v))}) if i is not None else []


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
            value_genders: dict[str, set[str]] | None = None) -> dict[str, Any]:
    """-> {"version", "kind": "shoes", "profile": shoes_mens | shoes_womens | shoes_unisex, "option": index or None,
    "values": [{ko, us, mm, wide, letter: None, chest_cm: None, basis: "mm"}] in size order, "merged": {}, "chart": None,
    "brand_row": None, "held": detail or None}. `stated`: the product's gender as stated (mens, womens, or anything
    else: both labels). `value_genders`: the genders of the variants that sell each size value (attributes' per-variant
    gender): a value only men's or only women's variants sell takes that gender's label (FootJoy 10239862675, 2026-11-25:
    "XW 240" its men's, "W 240" its women's)."""
    gender = stated if stated in ("mens", "womens") else "unisex"
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
        mm = mm_of(v)
        if mm is None:
            out["held"] = f"{v!r}: not read as a size in mm"
            return out
        own = (value_genders or {}).get(str(v)) or set()
        one = next(iter(own)) if split and len(own) == 1 else gender
        values.append({"ko": str(v), "us": us_label(mm, one, width(v)), "mm": mm, "wide": width(v), "letter": None,
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
    rows = [[v["us"].split(" (")[0], f"{v['mm']} mm", f"{v['mm'] / 25.4:.1f} in"]
            for v in sizes.get("values") or [] if v.get("mm")]
    if not rows:
        return ""
    block = _el("table", [_el("thead", [_el("tr", [_el("th", h) for h in ("Size", "Foot length", "Foot length (in)")])]),
                          _el("tbody", [_el("tr", [_el("td", c) for c in r]) for r in rows])], ' class="size-chart"')
    note = ("Korean shoe sizes are the foot length in millimetres; the US size is converted from it. "
            "Measure your foot heel to toe and pick the size whose foot length is the same or a little longer.")
    return f"{CHART_MARK}{block}<p>{note}</p>"
