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
    clubs of a full part list ("드라이버 우드 유틸 7아이언 퍼터" = 11). A count after a part word ("아이언 선택 (8개)",
    "아이언 6개") is that part's, never the total (run 40b, 2026-11-07).
  * contradiction (R-CONTRA): 총클럽개수 N with N irons or more in 아이언개수 / 아이언 구성 on a set with other clubs:
    the title's total, else 풀세트구성 or the option axes (axis_floor) counting N, says which row is wrong.
  * composition (R-FAMILY): 아이언개수, 아이언 구성 and 풀세트구성 describe one set; they follow 총클럽개수, or the
    fewest clubs they imply (their floor), to one group of variant counts.
  * model year (R-YEAR): 출시 2026년형 vs XR26 / "XR 24" / "X HOT 23" in the values.
  * driver loft (R-LOFT): 드라이버 로프트각 10.5도 vs "9도 SR" / "9.5 SR" / "10.5R" in the values; a row listing every
    loft sold ("11.5도, 10.5도") stays product-wide (pilot 2026-11-06: 11635855564, 13369469193).

Numbers with units are one word in the title check: "11.5" / "11.5L" names the value "11.5도", "유틸4" / "4U" the
value "4번" of a 유틸리티 axis, "+골프백" the values with a 캐디백 when others are "캐디백 미포함" (R-TITLE).

Whole values count too: "NS PRO950GH NEO R" names the value "NS PRO950GH NEO(R)", "우드3번55S" the value "3번 55S" of
the 우드 axis (value_spans; spacing, brackets and case aside).

The decision per row (Shopify has no per-variant spec rows; the option values are the SKU source, never changed):
  proved wrong by the product's own rows / title -> dropped, note specs_contradict (needs the title)
  fits no variant                                -> dropped, note specs_fit_no_variant
  every variant's own value states the fact      -> dropped, note specs_stated_by_variants (the variant title says it)
  a sold loft half a degree from the row's       -> kept as is, note specs_loft_near_miss (9도 sold, row 9.5도)
  several lofts on a product of one variant      -> kept as is, note specs_lists_unsold
  some variants silent, or a composition row     -> kept with for_ko (the option values it fits, as written),
                                                    note specs_bound_to_variants
  composition rows with no decidable set         -> dropped, note specs_composition_undecided
  other rows (모델명 ...) still word-matched       -> kept, note specs_name_one_variant (checked by hand)

    from spec_variants import check_specs, title_one_variant
    checked = check_specs(spec_rows(specs), ov["options"], ov["variants"], description_text, details["name"])
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


# a loft word "11.5도" is also written "11.5", "11.5L", "10.5 R" (a flex may follow), not "10K", "10개", "9아이언",
# "Qi10" (10816781893 title "드라이버11.5L" vs the value "11.5도 L", 2026-11-06)
_LOFT_WORD_RE = re.compile(r"(\d{1,2}(?:\.\d)?)도")
_FLEX_NEXT = r"(?=\s*(?:SR|R|S|X|L|A)(?![A-Za-z]))"
_NOT_A_LOFT_NEXT = r"(?![0-9A-Za-z가-힣]|\.\d|\s*(?:개|종|번|아이언|피스|[Pp]C?S?(?![A-Za-z])))"


def _word_pattern(word: str) -> str:
    if word.endswith("#"):                         # a count: the number with the unit the text writes
        return r"(?<![0-9.])" + re.escape(word[:-1]) + _COUNT_UNIT + r"(?![0-9]|\.\d)"
    if word in (BAG, NO_BAG):
        return _BAG_PATTERN if word == BAG else _NO_BAG_PATTERN
    if word.startswith("~"):                       # a club number "~U4": 유틸4 / 4U / 4번 유틸
        return _club_pattern(word[1], word[2:])
    if m := _LOFT_WORD_RE.fullmatch(word):
        return rf"(?<![0-9.A-Za-z#]){re.escape(m.group(1))}(?:\s*도|°|{_FLEX_NEXT}|{_NOT_A_LOFT_NEXT})"
    left = r"(?<![0-9.])" if word[0].isdigit() else r"(?<![A-Za-z])" if word[0].isascii() else ""
    right = r"(?![0-9]|\.\d)" if word[-1].isdigit() else r"(?![A-Za-z])" if word[-1].isascii() else ""
    return left + re.escape(word) + right


# ---- club numbers and the bag (R-TITLE words with a unit of their own) ----------------------------

# a club number: 유틸4 / 우드5 / 5W / 4U / 4번유틸 / 유틸 4번 / 우드9번(33도) -> "~U4" / "~W5"; not "8아이언" (irons),
# "3유틸리티" (a count of utilities), "유틸 8아이언" (the irons after the part); a bare "4번" is one on an axis named
# after one part ("유틸리티 선택": 4번 L / 5번 L; 10816781893, 13553116678 "5W" / "4U", 2026-11-06)
_PART_WORDS = {"W": r"우드|페어웨이", "U": r"유틸리티|유틸|하이브리드"}
_PART_LATIN = {"W": r"FW|W", "U": r"UT|U|H"}
_NOT_CLUB_NEXT = r"(?![0-9.]|\s*(?:아이언|개|종|[Pp](?![A-Za-z])|PC|피스|도|[iI](?![A-Za-z])))"


def _club_pattern(part: str, n: str | None = None) -> str:
    """The forms of club number `n` of `part`; without `n`, any single digit (groups a, b, c)."""
    w, latin = _PART_WORDS[part], _PART_LATIN[part]
    a, b, c = (re.escape(n),) * 3 if n else (r"(?P<a>\d)", r"(?P<b>\d)", r"(?P<c>\d)")
    return (rf"(?:{w})\s*#?{a}(?:\s*번)?{_NOT_CLUB_NEXT}|(?<![0-9.]){b}\s*번\s*(?:{w})"
            rf"|(?<![0-9.]){c}\s*(?:{latin})(?![A-Za-z])")


_CLUB_RES = {p: re.compile(_club_pattern(p)) for p in _PART_WORDS}


def club_numbers(text: str | None) -> dict[str, str]:
    """{"~U4": "유틸4"}: the club numbers a text writes with their part."""
    out: dict[str, str] = {}
    for p, rx in _CLUB_RES.items():
        for m in rx.finditer(text or ""):
            out.setdefault(f"~{p}{m.group('a') or m.group('b') or m.group('c')}", m.group(0))
    return out


def axis_part(name: str | None) -> str | None:
    """The one club part an axis name names ("유틸리티 선택" -> U, "우드 선택" / "페어웨이우드" -> W), else None."""
    found = [p for p, w in _PART_WORDS.items() if re.search(w, name or "")]
    return found[0] if len(found) == 1 else None


# the bag: 골프백 / 캐디백 / 스탠드백 are one thing; "캐디백 미포함" is a value without it (13413924099 title
# "+골프백" with "캐디백 미포함" values, 2026-11-06). A 하프백 / 보스턴백 is an extra bag, not the set's.
BAG, NO_BAG = "~BAG", "~NOBAG"
_BAG_WORD = r"(?:(?:골프|캐디|스탠드|카트)백|(?<![가-힣])백)"
_NO_BAG_PATTERN = _BAG_WORD + r"\s*(?:세트\s*)?(?:미포함|불포함|제외|없음|별도)"
_BAG_PATTERN = (r"(?:골프|캐디|스탠드|카트)백(?!\s*(?:세트\s*)?(?:미포함|불포함|제외|없음|별도))"
                r"|백\s*(?:세트\s*)?포함")
_BAG_WORD_RE = re.compile(r"^(?:골프|캐디|스탠드|카트)?백$")


def bag_word(text: str | None) -> tuple[str, str] | None:
    """(NO_BAG, "캐디백 미포함") when the text says without the bag, (BAG, "캐디백") when it names it, None: silent."""
    for key, pattern in ((NO_BAG, _NO_BAG_PATTERN), (BAG, _BAG_PATTERN)):
        if m := re.search(pattern, text or ""):
            return key, m.group(0)
    return None


# ---- R-MAT material class -------------------------------------------------------------------

_STEEL_RE = re.compile(r"스틸|steel|N\.?S\.?\s*PRO|다이나믹\s*골드|DYNAMIC\s*GOLD|모듀스|MODUS", re.I)
_CARBON_RE = re.compile(r"카본|그라파이트|graphite|carbon", re.I)
# "스틸(S) / 카본(R)" in the description: a material written on a WHOLE option value (6774818843, 2026-11-06);
# "카본(R) 샤프트" with the value "4종-카본(R) 샤프트" or "카본샤프트(강도: R)" bind nothing
_BIND_RE = re.compile(r"(스틸|카본|그라파이트)\s*(?:샤프트)?\s*\(\s*([A-Za-z]{1,2})\s*\)")
# "※플렉스 R 모델의 아이언에는 카본 샤프트, 플렉스 S 모델의 아이언에는 스틸 샤프트 장착": a whole value, 모델 / 플렉스 /
# 사양, then in the same clause (no comma, period, line break) the shaft material, of no part but the irons
# (7166885441, 2026-11-06)
_BIND_SENTENCE_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]{1,2})\s*(?:모델|플렉스|사양|스펙)([^,.\n]{0,20}?)"
                               r"(스틸|카본|그라파이트)\s*샤프트")
_OTHER_PART_RE = re.compile(r"드라이버|우드|페어웨이|유틸|하이브리드|퍼터|웨지")


def material(text: str | None) -> str | None:
    """STEEL / CARBON, or None when the text names neither or both ("스틸 or 카본")."""
    steel, carbon = bool(_STEEL_RE.search(text or "")), bool(_CARBON_RE.search(text or ""))
    return "STEEL" if steel and not carbon else "CARBON" if carbon and not steel else None


def description_materials(description: str | None, values: list[str]) -> dict[str, str]:
    """{option value: STEEL | CARBON} where the description writes a material on that whole value; a value it
    binds to both classes is left out."""
    found: dict[str, set[str]] = {}
    pairs = [(m.group(2), m.group(1)) for m in _BIND_RE.finditer(description or "")]
    pairs += [(m.group(1), m.group(3)) for m in _BIND_SENTENCE_RE.finditer(description or "")
              if not _OTHER_PART_RE.search(m.group(2))]
    for value, word in pairs:
        cls = material(word)
        if value in values and cls:
            found.setdefault(value, set()).add(cls)
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


# a count right after a part word is that part's count, not the set's total: "아이언 선택 (8개)" (an axis name),
# "아이언 6개 NS PRO 950GH NEO(R)", "웨지2개퍼터"; not "아이언포함 11개", "클럽11개", "드라이버+8개 아이언" (seen
# 2026-11-07: 12999501692, 13002235969, 12979780461, 12975257923, 13002228030, 12999388634 lost a true 총클럽개수)
_PART_LETTERS = (("D", "드라이버"), ("W", "우드|페어웨이"), ("U", "유틸리티|유틸|하이브리드"), ("I", "아이언"), ("P", "퍼터"),
                 ("G", "웨지"))
_PART_COUNT_RE = re.compile(r"(드라이버|우드|페어웨이|유틸리티|유틸|하이브리드|아이언|퍼터|웨지)(?:\s*세트)?(?:\s*선택)?"
                            r"\s*[(\[]?\s*(\d{1,2})\s*(?:개|PCS|pcs|P|피스)(?![A-Za-z\d])")


def _letter(word: str) -> str:
    return next(k for k, w in _PART_LETTERS if re.fullmatch(w, word))


def part_counts(text: str | None) -> dict[str, int]:
    """{"I": 8} for "아이언 선택 (8개)": the counts a text writes after a part word (D W U I P G)."""
    return {_letter(m.group(1)): int(m.group(2)) for m in _PART_COUNT_RE.finditer(text or "")}


def axis_floor(names: list[str]) -> int | None:
    """Fewest clubs the option axes sell: the irons an iron axis counts ("아이언 선택 (8개)") plus one for each other
    part an axis names (드라이버 / 우드 / 유틸리티 ..., once however many axes name it); None when no axis names a part
    or an iron axis does not say how many ("드라이버 로프트 선택", "드라이버 강도 선택", "아이언 선택 (8개)" = 9)."""
    parts: set[str] = set()
    irons = 0
    for name in names:
        counted = part_counts(name)
        for k, w in _PART_LETTERS:
            if re.search(w, name or ""):
                if k == "I" and "I" not in counted:
                    return None
                parts.add(k)
        irons = counted.get("I", irons)
    if not parts:
        return None
    return irons + len(parts - {"I"})


def stated_total(text: str | None) -> int | None:
    """The one club total a text states; None when it states none or two ("11PC+(사은품 7종 세트 포함)"). A part's
    count ("아이언 선택 (8개)") is not one."""
    found = {int(a or b) for a, b in _TOTAL_RE.findall(_PART_COUNT_RE.sub(" ", text or ""))}
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


# ---- R-LOFT driver loft ------------------------------------------------------------------------

LOFT_ROW = "드라이버 로프트각"
# a driver loft in a value: "10.5도", "9도 SR", "9.5 SR", "10.5R", "(L) 11.5도"; 7-14 degrees (a wood's "(33도)" or
# a "4번 R" utility is not one; 11635855564, 13369469193, 2026-11-06)
_LOFT_RE = re.compile(r"(?<![\d.#])(\d{1,2}(?:\.\d)?)\s*(?:도|°|(?=(?:SR|R|S|X|L|A)(?![A-Za-z])))")


def lofts(text: str | None) -> set[float]:
    return {x for x in map(float, _LOFT_RE.findall(text or "")) if 7 <= x <= 14}


def _deg(x: float) -> str:
    return f"{x:g}도"


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


# "8i" / "8아이언" / "아이언 8개" in a title: the irons it says (13780241403 "12pc/8i", 2026-11-07)
_TITLE_IRONS_RE = re.compile(r"(?<![\d.])(\d{1,2})\s*(?:i(?![A-Za-z])|아이언(?!\s*세트)|개\s*아이언)")


def _contradictions(rows: dict[str, str], names: list[str], title: str | None) -> dict[str, str]:
    """{label: detail} of the count rows the product's own rows and title prove wrong. 총클럽개수 N while 아이언개수 /
    아이언 구성 give N irons or more on a set with other clubs: the title's total decides (12pc: the total row is wrong;
    = N: the iron rows are); a title without one leaves it to 풀세트구성 or the option axes counting N clubs, unless the
    title backs the irons ("8i"). Seen 2026-11-07: 13780241403 총클럽개수 3개 on a 12pc/8i set with 8 irons listed,
    12975223812 아이언개수 8개 on a driver + wood + utility set of 3, 13026991307 아이언개수 11개 = 총클럽개수 11개."""
    n = stated_total(rows.get("총클럽개수")) if title is not None else None
    if not n:
        return {}
    irons: dict[str, int] = {}
    if m := re.match(r"\s*(\d+)\s*개?\s*$", rows.get("아이언개수", "")):
        irons["아이언개수"] = int(m.group(1))
    if rows.get("아이언 구성", "").strip():
        irons["아이언 구성"] = len([x for x in rows["아이언 구성"].split(",") if x.strip()])
    comp = rows.get("풀세트구성", "")
    others = bool(_NON_IRON_RE.search(comp)) or LOFT_ROW in rows or any(_DRIVER_RE.search(x) for x in names)
    bad = {k: v for k, v in irons.items() if v > n or v == n and others}
    if not bad:
        return {}
    total_row = _row("총클럽개수", rows["총클럽개수"])
    t = stated_total(title)
    if t and t != n:
        if t <= max(bad.values()):
            return {}
        listed = ", ".join(f"{k} lists {v} irons" for k, v in bad.items())
        return {"총클럽개수": f"{total_row}: {listed}, the title says {t}"}
    if t == n:
        return {k: f"{_row(k, rows[k])}: {total_row}, the title says {t}" for k in bad}
    said = {int(x) for x in _TITLE_IRONS_RE.findall(title or "")} | set(part_counts(title).values())
    if any(v in said for v in bad.values()) or _checklist(comp):
        return {}
    parts = [p.strip() for p in comp.split(",") if p.strip()]
    sets = [int(x) for x in _IRON_SET_RE.findall(comp)]
    by_comp = sum(1 for p in parts if _NON_IRON_RE.search(p)) + sum(sets) if parts else None
    if by_comp == n:
        return {k: f"{_row(k, rows[k])}: {total_row}, {_row('풀세트구성', comp)}" for k in bad}
    if axis_floor(names) == n:
        return {k: f"{_row(k, rows[k])}: {total_row}, the option axes sell {n} clubs" for k in bad}
    return {}


def check_specs(spec_rows: list[dict[str, str]], options: list[dict[str, Any]], variants: list[dict[str, Any]],
                description_text: str | None, title: str | None = None) -> dict[str, Any]:
    """Spec rows vs the sold variants -> {"specs": the rows kept, in order, a bound one with "for_ko",
    "notes": [{code, detail}]}. Count rows the product's own rows and `title` prove wrong are dropped
    (specs_contradict; no title: not checked); a driver loft row listing several lofts on a product of one variant
    is noted (specs_lists_unsold). Otherwise a product without two sold combinations is never touched."""
    names = [o["name_ko"] for o in options]
    contra = _contradictions({r["label_ko"]: r["value_ko"] for r in spec_rows}, names, title)
    combos = _combos(options, variants)
    if len(combos) < 2:
        kept = [dict(r) for r in spec_rows if r["label_ko"] not in contra]
        one = [{"code": "specs_contradict", "detail": "; ".join(contra.values())}] if contra else []
        many = next((r for r in kept if r["label_ko"] == LOFT_ROW and len(lofts(r["value_ko"])) > 1), None)
        if many:                                          # "10도, 9도" on the one variant (12863028632)
            one.append({"code": "specs_lists_unsold",
                          "detail": f"{_row(LOFT_ROW, many['value_ko'])}: one variant is sold"})
        return {"specs": kept if contra else list(spec_rows), "notes": one}
    spec_rows = [r for r in spec_rows if r["label_ko"] not in contra]
    rows = {r["label_ko"]: r["value_ko"] for r in spec_rows}
    drop: dict[str, tuple[str, str]] = {}                 # label -> (note code, detail)
    bind: dict[str, list[tuple[str, ...]]] = {}           # label -> the combinations it fits
    handled: set[str] = set()                             # rows a fact check read: no word match after it
    extra: dict[str, list[str]] = {}                      # notes of rows kept as they are

    def decide(label: str, fits: list[tuple[str, ...]], stated: bool, rival: str, found: str) -> None:
        if not fits:
            drop[label] = ("specs_fit_no_variant", f"{_row(label, rows[label])}: the variants are {rival}")
        elif stated:                                      # the row is one of the values: the variant titles say each
            drop[label] = ("specs_stated_by_variants",
                           f"{_row(label, rows[label])}: each variant states its own value ({found})")
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
            found = ", ".join(w for k, w in (("STEEL", "스틸"), ("CARBON", "카본")) if k in classes)
            decide("아이언샤프트소재", [c for c, k in zip(combos, classes) if k in (None, row_class)],
                   all(named), rival, found)

    # count: the total a combination's values (or the axis names) state, else the clubs of a full part list
    stated = [_one({stated_total(t) for t in (*c, *names)}) for c in combos]
    counts = [s or _one({part_count(v) for v in c}) for c, s in zip(combos, stated)]
    groups = sorted({n for n in counts if n})
    total = stated_total(rows.get("총클럽개수")) if "총클럽개수" in rows else None
    if total and groups:
        handled.add("총클럽개수")
        if any(n and n != total for n in counts):
            decide("총클럽개수", [c for c, n in zip(combos, counts) if n in (None, total)], all(stated),
                   ", ".join(map(str, groups)), ", ".join(f"{g}개" for g in groups))

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

    # driver loft: the loft a combination's values name; a row listing every loft sold changes nothing. A sold loft
    # half a degree from a row loft is a near miss (row "9.5도, 10.5도", values "9도R" / "10.5도R": 12999487292,
    # 12999388634, 2026-11-07): the row stays, noted, those variants are not called rivals
    row_lofts = lofts(rows.get(LOFT_ROW))
    if row_lofts:
        handled.add(LOFT_ROW)
        sold = [_one(set().union(*(lofts(v) for v in c))) for c in combos]
        other = {x for x in sold if x is not None and x not in row_lofts}
        near = sorted({x for x in other if any(abs(x - y) <= 0.5 for y in row_lofts)}, reverse=True)
        rivals = sorted(other - set(near), reverse=True)
        if near:
            extra.setdefault("specs_loft_near_miss", []).append(
                f"{_row(LOFT_ROW, rows[LOFT_ROW])}: the variants sell {', '.join(map(_deg, near))}")
        if rivals:
            decide(LOFT_ROW, [c for c, x in zip(combos, sold) if x is None or x in row_lofts or x in near],
                   all(x is not None for x in sold) and not near, ", ".join(map(_deg, rivals)),
                   ", ".join(map(_deg, sorted({x for x in sold if x is not None}, reverse=True))))

    # other rows: the word match (a row word of part of an axis' values), for a check by hand
    named_rows = []
    for r in spec_rows:
        if r["label_ko"] in handled:
            continue
        row_words, value = words(r["value_ko"]), r["value_ko"]
        hits = _names_some(lambda w: w in row_words or _has_unit(w) and in_text(w, value), options, False)
        if hits:
            named_rows.append(f"{_row(r['label_ko'], r['value_ko'])}: {', '.join(_spans(hits, r['value_ko']))}")

    out: list[dict[str, Any]] = []
    notes: dict[str, list[str]] = {"specs_contradict": list(contra.values())} if contra else {}
    notes.update(extra)
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
    order = ("specs_contradict", "specs_fit_no_variant", "specs_stated_by_variants", "specs_composition_undecided",
             "specs_bound_to_variants", "specs_loft_near_miss", "specs_name_one_variant")
    return {"specs": out, "notes": [{"code": c, "detail": "; ".join(notes[c])} for c in order if c in notes]}


# ---- R-TITLE: words of the title (or of a row) that name part of the variants -------------------

_LOFT_FLEX_WORD_RE = re.compile(r"(\d{1,2}(?:\.\d)?)(?:SR|R|S|X)")


def _has_unit(word: str) -> bool:
    """A word the text may write another way: a loft "11.5도" ("11.5L"), a club number, the bag."""
    return word.startswith("~") or _LOFT_WORD_RE.fullmatch(word) is not None


def _value_words(value: str, both_genders: bool, part: str | None = None) -> dict[str, str]:
    """A value's words, plus the club count of a full part list as a count ("드라이버 우드 유틸 7아이언 퍼터" -> 11개),
    its club numbers ("4번" of a 유틸리티 axis -> ~U4) and the bag (~BAG; "캐디백 미포함" -> ~NOBAG, its bag word
    left out)."""
    out = words(value, both_genders)
    n = part_count(value)
    if n:
        out.setdefault(f"{n}#", f"{n}개")
    for k, w in list(out.items()):                 # "10.5R" is the loft 10.5도 too (9343324012: "10.5R" / "10.5도")
        if (m := _LOFT_FLEX_WORD_RE.fullmatch(k)) and 7 <= float(m.group(1)) <= 14:
            out.setdefault(f"{m.group(1)}도", w)
    clubs = club_numbers(value)
    if part and not clubs:
        for m in re.finditer(r"(?<![0-9.])(\d)\s*번", value):
            out.pop(f"{m.group(1)}번", None)
            clubs[f"~{part}{m.group(1)}"] = m.group(0)
    out.update(clubs)
    bag = bag_word(value)
    if bag:
        out[bag[0]] = bag[1]
    if bag and bag[0] == NO_BAG:
        for k in [k for k in out if _BAG_WORD_RE.match(k)]:
            del out[k]
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
        value_words = [_value_words(v, both_genders, axis_part(o["name_ko"])) for v in vals]
        if not any(NO_BAG in ws for ws in value_words):        # the bag tells values apart only by a 미포함
            for ws in value_words:
                ws.pop(BAG, None)
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


def _spans(hits: list[tuple[str, str]], text: str, whole: list[tuple[int, int]] | None = None) -> list[str]:
    """The hits as `text` writes them, in its order; hits that touch are one span ("XR" + "26" -> "XR26"). An
    occurrence inside a longer hit ("R" of "10.5R") is not one of its own; a hit also written inside a merged
    span is not repeated alone (모델명 "26캘러웨이 ... XR26" -> "XR26"). `whole`: (start, end) of values `text`
    writes whole (value_spans): one with no span inside is a span of its own, the spans inside one with no word
    between them are one ("NS" "PRO" "950GH" "NEO" -> "NS PRO 950GH NEO", "유틸3" "65S" -> "유틸3번65S")."""
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
    shown = [(a, b) for a, b, ks in merged if len(ks) > 1 or not ks & in_long]
    for wa, wb in whole or []:
        inside = [x for x in shown if wa <= x[0] and x[1] <= wb]
        if not inside:
            shown.append((wa, wb))
        elif len(inside) > 1 and not any(words(text[x[1]:y[0]]) for x, y in zip(inside, inside[1:])):
            shown = [x for x in shown if x not in inside] + [(inside[0][0], inside[-1][1])]
    out = [text[a:b] for a, b in sorted(set(shown))]
    missing = [w for k, w in hits if not any(k in m[2] for m in merged)]
    return list(dict.fromkeys(out + missing))


# a value's whole written span in the title, spacing, brackets and case aside: "NS PRO950GH NEO R" is the value
# "NS PRO950GH NEO(R)", "우드3번55S" the value "3번 55S" of the 우드 axis (not "3번 65 S": the "3번65S" there
# follows 유틸). Seen 2026-11-07: 13002289437, 13002279921 (the "G" of G440 hid the word match), 12950788305.
_LOOSE = set(" \t()[]{}-_")
_ANY_PART = "|".join(_PART_WORDS.values())


def _loose(text: str) -> tuple[str, list[int]]:
    keep = [(i, ch.lower()) for i, ch in enumerate(text) if ch not in _LOOSE and not ch.isspace()]
    return "".join(ch for _, ch in keep), [i for i, _ in keep]


def _edge(a: str, b: str) -> bool:
    """True when the two characters would join one word: digit + digit / ".", Latin + Latin."""
    return bool(a and b) and (a.isdigit() and (b.isdigit() or b == ".") or b.isdigit() and a == "."
                              or a.isascii() and a.isalpha() and b.isascii() and b.isalpha())


def value_spans(title: str, options: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """(start, end) in `title` of each value of two words or more the title writes whole, on an axis where it writes
    part of the values only; a value that starts with a club number must follow its axis' part word ("우드3번55S"),
    no other part's; one followed by "/" is a list of choices ("NEO R/S")."""
    flat, at = _loose(title)
    out: list[tuple[int, int]] = []
    for o in options:
        part = axis_part(o["name_ko"])
        found: dict[str, tuple[int, int]] = {}
        for v in o["values_ko"]:
            lv, _ = _loose(v)
            if len(words(v)) < 2 or not lv:
                continue
            for m in re.finditer(re.escape(lv), flat):
                a, b = m.start(), m.end()
                before, after = flat[a - 1] if a else "", flat[b] if b < len(flat) else ""
                if _edge(before, lv[0]) or _edge(lv[-1], after) or after == "/":
                    continue
                if lv[0].isdigit():
                    lead = re.search(rf"(?:{_PART_WORDS[part] if part else _ANY_PART})$", flat[:a])
                    if bool(part) != bool(lead):
                        continue
                    a -= len(lead.group(0)) if lead else 0
                found.setdefault(v, (at[a], at[b - 1] + 1))
                break
        if 0 < len(found) < len(o["values_ko"]):
            out += found.values()
    return out


def title_one_variant(title: str, options: list[dict[str, Any]]) -> list[str]:
    """Words of the title that fit part of the values only, while the product sells others too ("12종" in the
    title, values 12종 / 9종; "10.5R" with 10.5 / 9 and R / S), as the title writes them, touching ones as one span
    ("XR26"): the translation must not promise that one. A title naming words of two values (여성용 / 남성용)
    names the choice; "선택1" numbering is not a word; a title count can name a part list ("(클럽10개)" with
    "드라이버 유틸 7아이언 퍼터" = 10 / "드라이버 우드 유틸 7아이언 퍼터" = 11: 5182294301)."""
    title = re.sub(r"(\d)\s+(?=[A-Za-z]{2,}\b)", r"\1", title or "")         # "13 PCS" -> "13PCS"
    both = bool(re.search(r"여성|여자", title)) and bool(re.search(r"남성|남자", title))
    hits = _names_some(lambda w: in_text(w, title), options, both)
    whole = value_spans(title, options)
    return _spans(hits, title, whole) if hits or whole else []
