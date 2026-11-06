"""Spec rows vs the sold variants, and the title words that name one variant. Pure, offline, no AI: transform.py
calls check_specs() on the shown spec rows and title_one_variant() on the title.

A spec row is shown once for the whole product, but on a product with options it can be true of some variants only
(아이언샤프트소재 카본 with 스틸 and 카본 sets sold), or of none. A word match cannot see a row that names a fact while
the values name a rival fact, or none at all, so each check reads ONE fact the same way from the row and from each
sold variant (research 2026-11-06, 40 golf sets of category 50002788 and 86 more saved pages):

  * material (R-MAT): 아이언샤프트소재 class STEEL / CARBON vs the class a variant's values name; 그라파이트/카본
    conflicts with "남성용 SR스틸" though they share no word. Bare R / S values get a class from the description only
    when it writes the material on that whole value: "스틸(S) / 카본(R)" (R-DESC, 6774818843).
  * count (R-COUNT, R-PARTS): 총클럽개수 vs the total a variant states (12종 / 9P / 13PCS / 10개세트 / "4스틸") or the
    clubs of a full part list ("드라이버 우드 유틸 7아이언 퍼터" = 11).
  * composition (R-FAMILY): 아이언개수, 아이언 구성 and 풀세트구성 describe one set; they follow 총클럽개수, or the
    fewest clubs they imply (their floor), to one group of variant counts.
  * model year (R-YEAR): 출시 2026년형 vs XR26 / "XR 24" / "X HOT 23" in the values.

The decision per row (Shopify has no per-variant spec rows; the option values are the SKU source, never changed):
  fits no variant                                -> dropped, note specs_fit_no_variant
  every variant's own value states the fact      -> dropped, note specs_stated_by_variants (the variant title says it)
  some variants silent, or a composition row     -> kept with for_ko (the option values it fits, as written),
                                                    note specs_bound_to_variants
  composition rows with no decidable set         -> dropped, note specs_composition_undecided
  other rows (모델명 ...) still word-matched       -> kept, note specs_name_one_variant (checked by hand)

    from spec_variants import check_specs, title_one_variant
    checked = check_specs(spec_rows(specs), ov["options"], ov["variants"], description_text)
    product["specs"], notes = checked["specs"], notes + checked["notes"]
"""
import re
from itertools import product as cartesian
from typing import Any, Callable

# ---- words (moved from transform.py: the title check and the row word match share them) ----------------------

# words of a title / value: "10.5R", "13PCS", "4번", "스틸", "SR": a number keeps its decimals and its unit, a
# word glued to it is a word of its own ("4스틸" = 4 + 스틸, "12카본" = 12 + 카본; 2026-11-06)
_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?(?:(?:PCS|Pcs|pcs|PC|SR|P|p|R|S|X)(?![A-Za-z])|피스|개|종|도|번)?|[A-Za-z]+|[가-힣]+")
_COUNT_RE = re.compile(r"^(\d+)(?:개|종|P|p|PC|PCS|pcs|Pcs|피스)?$")     # 12개 / 12종 / 12P / 12스틸: one count
_GENERIC_WORDS = {"풀세트", "세트", "골프채", "골프클럽", "클럽"}       # what every set is, whoever names it
_GENDER_RE = re.compile(r"^(?:여성|남성|여자|남자)(?:용)?$")
_FEMALE_RE = re.compile(r"여성|여자|레이디")
_MALE_RE = re.compile(r"남성|남자")
_HANGUL_WORD_RE = re.compile(r"[가-힣]{2,}")
# as in transform.py: a seller's numbering ("선택1 9도SR", "선택3) ...") and a name that says nothing ("선택2")
_NUMBERING_RE = re.compile(r"^(?:(?:선택|옵션)\s*\d+\s*[).:\-]?|\d+(?:-\d+)?[.)](?!\d))\s*")
_PLACEHOLDER_NAME_RE = re.compile(r"^(?:선택|옵션)(?:사항|선택)?\s*\d*(?:\s*[+/].*)?$")
_COUNT_UNIT = r"(?:PCS|Pcs|pcs|PC|P|p|피스|개|종)?"


def words(text: str, both_genders: bool = False) -> dict[str, str]:
    """A value's / row's words, counts made comparable (12개 = 12종 = 12P); 여성 / 남성 dropped when the title
    names both (it then names the choice). -> {comparable word: as written}"""
    out: dict[str, str] = {}
    for t in _TOKEN_RE.findall(_NUMBERING_RE.sub("", text or "")):
        if (len(t) < 2 and not t.isalpha()) or _PLACEHOLDER_NAME_RE.match(t) or both_genders and _GENDER_RE.match(t) \
                or t in _GENERIC_WORDS:
            continue
        if len(t) < 2 and re.match(r"[가-힣]", t):
            continue
        m = _COUNT_RE.match(t)
        out.setdefault(f"{m.group(1)}#" if m else t, t)
    return out


def in_text(word: str, text: str) -> bool:
    """`word` in `text` as a whole word on its Latin / digit edges (Hangul words join freely: 카본샤프트)."""
    if word.endswith("#"):
        return word in words(text)
    return re.search(_word_pattern(word), text) is not None


def _word_pattern(word: str) -> str:
    if word.endswith("#"):                         # a count: the number with the unit the text writes
        return r"(?<![0-9.])" + re.escape(word[:-1]) + _COUNT_UNIT + r"(?![0-9]|\.\d)"
    left = r"(?<![0-9.])" if word[0].isdigit() else r"(?<![A-Za-z])" if word[0].isascii() else ""
    right = r"(?![0-9]|\.\d)" if word[-1].isdigit() else r"(?![A-Za-z])" if word[-1].isascii() else ""
    return left + re.escape(word) + right


# ---- R-MAT material class -------------------------------------------------------------------

_STEEL_RE = re.compile(r"스틸|steel|N\.?S\.?\s*PRO|다이나믹\s*골드|DYNAMIC\s*GOLD|모듀스|MODUS", re.I)
_CARBON_RE = re.compile(r"카본|그라파이트|graphite|carbon", re.I)
# "스틸(S) / 카본(R)" in the description: a material written on a WHOLE option value (6774818843, 2026-11-06);
# "카본(R) 샤프트" with the value "4종-카본(R) 샤프트" or "카본샤프트(강도: R)" bind nothing
_BIND_RE = re.compile(r"(스틸|카본|그라파이트)\s*(?:샤프트)?\s*\(\s*([A-Za-z]{1,2})\s*\)")


def material(text: str | None) -> str | None:
    """STEEL / CARBON, or None when the text names neither or both ("스틸 or 카본")."""
    steel, carbon = bool(_STEEL_RE.search(text or "")), bool(_CARBON_RE.search(text or ""))
    return "STEEL" if steel and not carbon else "CARBON" if carbon and not steel else None


def description_materials(description: str | None, values: list[str]) -> dict[str, str]:
    """{option value: STEEL | CARBON} where the description writes a material on that whole value; a value it
    binds to both classes is left out."""
    found: dict[str, set[str]] = {}
    for m in _BIND_RE.finditer(description or ""):
        cls = material(m.group(1))
        if m.group(2) in values and cls:
            found.setdefault(m.group(2), set()).add(cls)
    return {v: c.pop() for v, c in found.items() if len(c) == 1}


# ---- R-COUNT / R-PARTS club counts ------------------------------------------------------------

# a stated total: 12종 / 9P / 13PCS / 12pc / 11개 / 10피스 / 10개세트, and a count glued to a shaft word: 4스틸;
# not "8개 아이언" (irons), "7개구성" (the irons of an iron axis), "10.5도", "4번유틸"
_TOTAL_RE = re.compile(r"(?<![\d.#])(\d{1,2})\s*(?:종|P|PC|PCS|pcs|Pcs|pc|피스|개(?!\s*아이언))(?:\s*세트)?(?![A-Za-z가-힣])"
                       r"|(?<![\d.#])(\d{1,2})(?=스틸|카본|그라파이트)")
_LOFT_FLEX_RE = re.compile(r"(?<![\d#])\d{1,2}(?:\.\d)?\s*도?\s*(?:R|SR|S|X)(?![A-Za-z])|\d{1,2}(?:\.\d)?\s*도")
_IRONS_RE = re.compile(r"(?<![\d.#번])(\d{1,2})\s*(?:개\s*)?아이언")       # 7아이언 / 8개 아이언, not 7번 아이언
_PART_RES = (re.compile(r"우드|페어웨이"), re.compile(r"유틸|하이브리드"), re.compile(r"퍼터"))
_DRIVER_RE = re.compile(r"드라이버")
_PUTTER_RE = re.compile(r"퍼터")


def stated_total(text: str | None) -> int | None:
    """The one club total a text states; None when it states none or two ("11PC+(사은품 7종 세트 포함)")."""
    found = {int(a or b) for a, b in _TOTAL_RE.findall(text or "")}
    found = {n for n in found if 3 <= n <= 16}
    return found.pop() if len(found) == 1 else None


def part_count(text: str | None) -> int | None:
    """Clubs of a full part list: one N아이언 and a putter, plus one each for 우드/페어웨이, 유틸/하이브리드, 퍼터 and a
    driver (the word, or a loft "9R" / "10.5도"): "드라이버 우드 유틸 7아이언 퍼터" = 11; None when not a full list."""
    t = text or ""
    irons = [int(n) for n in _IRONS_RE.findall(t)]
    if len(irons) != 1 or not _PUTTER_RE.search(t):
        return None
    driver = bool(_DRIVER_RE.search(t) or _LOFT_FLEX_RE.search(t))
    return irons[0] + sum(len(p.findall(t)) for p in _PART_RES) + int(driver)


def _one(found: set[Any]) -> Any:
    found = found - {None}
    return found.pop() if len(found) == 1 else None


# ---- R-FAMILY composition rows ----------------------------------------------------------------

FAMILY = ("아이언개수", "아이언 구성", "풀세트구성")
_IRON_SET_RE = re.compile(r"(\d+)\s*아이언세트")
_NON_IRON_RE = re.compile(r"드라이버|페어웨이|우드|유틸리티|하이브리드|퍼터")


def _checklist(composition: str) -> bool:
    """"7아이언세트, ..., 6아이언세트": a checklist of several sets, not one composition (11164222651)."""
    return len(_IRON_SET_RE.findall(composition or "")) > 1


def family_floor(rows: dict[str, str]) -> int | None:
    """Fewest clubs the composition rows describe: irons (the 아이언 구성 list, else 아이언개수, else N아이언세트) plus
    the non-iron parts 풀세트구성 names (웨지 counts only without an iron list); a checklist 풀세트구성 is left out."""
    comp = "" if _checklist(rows.get("풀세트구성", "")) else rows.get("풀세트구성", "")
    if "아이언 구성" in rows:
        irons = len([x for x in rows["아이언 구성"].split(",") if x.strip()])
    elif m := re.match(r"\s*(\d+)", rows.get("아이언개수", "")):
        irons = int(m.group(1))
    elif m := _IRON_SET_RE.search(comp):
        irons = int(m.group(1))
    else:
        return None
    parts = [p.strip() for p in comp.split(",") if p.strip()]
    others = sum(1 for p in parts if _NON_IRON_RE.search(p))
    if "아이언 구성" not in rows and "아이언개수" not in rows:
        others += sum(1 for p in parts if p == "웨지")
    return irons + others


# ---- R-YEAR model year ------------------------------------------------------------------------

# 2024 / 23년 / a 2-digit number right after a Latin word of 2+ letters (XR26, "XR 24", "X HOT 23"), not a loft,
# an iron, a count or a flex (10.5도, 4번, 13PCS, 26S); "젝시오14", "G430", "ST-MAX 230" are model numbers
_YEAR_RE = re.compile(r"(?<!\d)(20[1-3]\d)(?!\d)|(?<!\d)(\d{2})\s*년"
                      r"|(?<=[A-Za-z]{2})\s?(\d{2})(?![\d.]|\s*(?:도|번|개|종|[Pp]|PC|pc|S|R|아이언))")


def years(text: str | None) -> set[int]:
    out = set()
    for a, b, c in _YEAR_RE.findall(text or ""):
        y = int(a) % 100 if a else int(b or c)
        if 10 <= y <= 35:
            out.add(y)
    return out


def row_year(value: str | None) -> int | None:
    m = re.match(r"\s*(20\d\d)\s*년", value or "")
    return int(m.group(1)) % 100 if m else None


# ---- the check --------------------------------------------------------------------------------

def _combos(options: list[dict[str, Any]], variants: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    """The sold combinations: the variants' option tuples (observed rows), else every combination of the values."""
    n = len(options)
    rows = [tuple(v.get("options_ko") or []) for v in variants or []]
    if rows and all(len(r) == n for r in rows):
        return list(dict.fromkeys(rows))
    return [tuple(c) for c in cartesian(*[o["values_ko"] for o in options])] if options else []


def _for_values(options: list[dict[str, Any]], combos: list[tuple[str, ...]], fits: list[tuple[str, ...]]) -> list[str]:
    """The option values a row fits, as written: those of the one axis that tells the fitting combinations from the
    others (12종 of 소재 x 세트), else the fitting combinations "카본 / 12종"."""
    rest = [c for c in combos if c not in fits]
    for i, o in enumerate(options):
        yes, no = {c[i] for c in fits}, {c[i] for c in rest}
        if not yes & no and all(c in fits for c in combos if c[i] in yes):
            return [v for v in o["values_ko"] if v in yes]
    return [" / ".join(c) for c in fits]


def _row(label: str, value: str) -> str:
    return f"{label} {value}"


def check_specs(spec_rows: list[dict[str, str]], options: list[dict[str, Any]], variants: list[dict[str, Any]],
                description_text: str | None) -> dict[str, Any]:
    """Spec rows vs the sold variants -> {"specs": the rows kept, in order, a bound one with "for_ko",
    "notes": [{code, detail}]}. A product without two sold combinations is never touched."""
    combos = _combos(options, variants)
    if len(combos) < 2:
        return {"specs": list(spec_rows), "notes": []}
    rows = {r["label_ko"]: r["value_ko"] for r in spec_rows}
    names = [o["name_ko"] for o in options]
    drop: dict[str, tuple[str, str]] = {}                 # label -> (note code, detail)
    bind: dict[str, list[tuple[str, ...]]] = {}           # label -> the combinations it fits
    handled: set[str] = set()                             # rows a fact check read: no word match after it

    def decide(label: str, fits: list[tuple[str, ...]], stated: bool, rival: str) -> None:
        if not fits:
            drop[label] = ("specs_fit_no_variant", f"{_row(label, rows[label])}: the variants are {rival}")
        elif stated:
            drop[label] = ("specs_stated_by_variants", f"{_row(label, rows[label])}: every variant states it")
        else:
            bind[label] = fits

    # material: the class a combination's values name, or the one the description writes on a bare value
    row_class = material(rows.get("아이언샤프트소재"))
    if row_class:
        handled.add("아이언샤프트소재")
        bound: dict[str, str] = {}
        for o in options:
            bound.update(description_materials(description_text, o["values_ko"]))
        named = [_one({material(v) for v in c}) for c in combos]
        classes = [n or _one({bound.get(v) for v in c}) for c, n in zip(combos, named)]
        if any(k and k != row_class for k in classes):
            rival = "스틸" if row_class == "CARBON" else "카본"
            decide("아이언샤프트소재", [c for c, k in zip(combos, classes) if k in (None, row_class)],
                   all(named), rival)

    # count: the total a combination's values (or the axis names) state, else the clubs of a full part list
    stated = [_one({stated_total(t) for t in (*c, *names)}) for c in combos]
    counts = [s or _one({part_count(v) for v in c}) for c, s in zip(combos, stated)]
    groups = sorted({n for n in counts if n})
    total = stated_total(rows.get("총클럽개수")) if "총클럽개수" in rows else None
    if total and groups:
        handled.add("총클럽개수")
        if any(n and n != total for n in counts):
            decide("총클럽개수", [c for c, n in zip(combos, counts) if n in (None, total)], all(stated),
                   ", ".join(map(str, groups)))

    # composition: one set; it follows the total, else the group its floor names
    family = [k for k in FAMILY if k in rows]
    if family and len(groups) > 1:
        handled.update(family)
        floor = family_floor(rows)
        above = [g for g in groups if floor is not None and g >= floor]
        target = (total if total is not None and total in groups and (floor is None or floor <= total)
                  else floor if floor in groups else above[0] if len(above) == 1 else None)
        for k in family:
            if k == "풀세트구성" and _checklist(rows[k]):
                continue                                  # a checklist of several sets stays product-wide
            if target is None:
                drop[k] = ("specs_composition_undecided", f"{_row(k, rows[k])}: sets of "
                           f"{', '.join(map(str, groups))}, the rows need {floor if floor is not None else '?'}")
            else:
                bind[k] = [c for c, n in zip(combos, counts) if n == target]

    # model year: fires only when some combination has the row's year and another a different one
    ry = row_year(rows.get("출시"))
    if ry is not None:
        handled.add("출시")
        ys = [set().union(*(years(v) for v in c)) for c in combos]
        if any(ry in y for y in ys) and any(y and ry not in y for y in ys):
            bind["출시"] = [c for c, y in zip(combos, ys) if ry in y]

    # other rows: the word match (a row word of part of an axis' values), for a check by hand
    named_rows = []
    for r in spec_rows:
        if r["label_ko"] in handled:
            continue
        row_words = words(r["value_ko"])
        hits = _names_some(lambda w: w in row_words, options, False)
        if hits:
            named_rows.append(f"{_row(r['label_ko'], r['value_ko'])}: {', '.join(_spans(hits, r['value_ko']))}")

    out: list[dict[str, Any]] = []
    notes: dict[str, list[str]] = {}
    for r in spec_rows:
        label = r["label_ko"]
        if label in drop:
            code, detail = drop[label]
            notes.setdefault(code, []).append(detail)
        elif label in bind:
            fits = _for_values(options, combos, bind[label])
            out.append({**r, "for_ko": fits})
            notes.setdefault("specs_bound_to_variants", []).append(f"{_row(label, r['value_ko'])} -> {', '.join(fits)}")
        else:
            out.append(dict(r))
    if named_rows:
        notes["specs_name_one_variant"] = named_rows
    order = ("specs_fit_no_variant", "specs_stated_by_variants", "specs_composition_undecided",
             "specs_bound_to_variants", "specs_name_one_variant")
    return {"specs": out, "notes": [{"code": c, "detail": "; ".join(notes[c])} for c in order if c in notes]}


# ---- R-TITLE: words of the title (or of a row) that name part of the variants -------------------

def _value_words(value: str, both_genders: bool) -> dict[str, str]:
    """A value's words, plus the club count of a full part list as a count ("드라이버 우드 유틸 7아이언 퍼터" -> 11개)."""
    out = words(value, both_genders)
    n = part_count(value)
    if n:
        out.setdefault(f"{n}#", f"{n}개")
    return out


def _gender(word: str) -> str | None:
    return "M" if _MALE_RE.search(word) else "F" if _FEMALE_RE.search(word) else None


def _names_some(found_in: Callable[[str], bool], options: list[dict[str, Any]],
                both_genders: bool) -> list[tuple[str, str]]:
    """Words for which `found_in(word)` holds that belong to some values of an axis but not all, when together
    they point at part of the values (12종 + 카본 -> 12종 카본); words of different values name the choice. Not a
    difference: a gender word unless every value without it names the other gender (an unmarked value is not a
    gender), and a Hangul word every value without it writes with the same last two syllables (백포함 /
    백세트포함 / 캐디백포함: 12696567111, 2026-11-06)."""
    found = []
    for o in options:
        vals = o["values_ko"]
        value_words = [_value_words(v, both_genders) for v in vals]
        written = {k: v for ws in reversed(value_words) for k, v in ws.items()}
        n = len(value_words)

        def counts(w: str) -> bool:
            has = [i for i, ws in enumerate(value_words) if w in ws]
            if not 0 < len(has) < n or not found_in(w):
                return False
            lack = [vals[i] for i in range(n) if i not in has]
            if _GENDER_RE.match(w):
                other = _FEMALE_RE if _gender(w) == "M" else _MALE_RE
                return all(other.search(v) for v in lack)
            if re.fullmatch(r"[가-힣]{3,}", w):
                return not all(any(x.endswith(w[-2:]) for x in _HANGUL_WORD_RE.findall(v)) for v in lack)
            return True

        hits = sorted(w for w in set().union(*value_words) if counts(w))
        if not hits:
            continue
        common = set(range(n))
        for w in hits:
            common &= {i for i, ws in enumerate(value_words) if w in ws}
        if 0 < len(common) < n:
            found += [(w, written[w]) for w in hits]
    return list(dict.fromkeys(found))


def _spans(hits: list[tuple[str, str]], text: str) -> list[str]:
    """The hits as `text` writes them, in its order; hits that touch are one span ("XR" + "26" -> "XR26"). An
    occurrence inside a longer hit ("R" of "10.5R") is not one of its own; a hit also written inside a merged
    span is not repeated alone (모델명 "26캘러웨이 ... XR26" -> "XR26")."""
    found = [(m.start(), m.end(), k) for k in dict.fromkeys(k for k, _ in hits)
             for m in re.finditer(_word_pattern(k), text)]
    found = [f for f in found if not any(g[0] <= f[0] and f[1] <= g[1] and g[1] - g[0] > f[1] - f[0] for g in found)]
    found.sort()
    merged: list[list[Any]] = []
    for a, b, k in found:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2].add(k)
        else:
            merged.append([a, b, {k}])
    in_long = set().union(*[m[2] for m in merged if len(m[2]) > 1]) if merged else set()
    out = [text[a:b] for a, b, ks in merged if len(ks) > 1 or not ks & in_long]
    missing = [w for k, w in hits if not any(k in m[2] for m in merged)]
    return list(dict.fromkeys(out + missing))


def title_one_variant(title: str, options: list[dict[str, Any]]) -> list[str]:
    """Words of the title that fit part of the values only, while the product sells others too ("12종" in the
    title, values 12종 / 9종; "10.5R" with 10.5 / 9 and R / S), as the title writes them, touching ones as one span
    ("XR26"): the translation must not promise that one. A title naming words of two values (여성용 / 남성용)
    names the choice; "선택1" numbering is not a word; a title count can name a part list ("(클럽10개)" with
    "드라이버 유틸 7아이언 퍼터" = 10 / "드라이버 우드 유틸 7아이언 퍼터" = 11: 5182294301)."""
    title = re.sub(r"(\d)\s+(?=[A-Za-z]{2,}\b)", r"\1", title or "")         # "13 PCS" -> "13PCS"
    both = bool(re.search(r"여성|여자", title)) and bool(re.search(r"남성|남자", title))
    hits = _names_some(lambda w: in_text(w, title), options, both)
    return _spans(hits, title) if hits else []
