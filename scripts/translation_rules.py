"""Deterministic rules applied before a text goes to the model (the owner, 2026-11-08: templates for units and
sizes, the model only as the fallback). A text the rules turn into no Hangul at all is done without the model; a
text with Hangul left goes to the model already partly converted ("9도SR 스틸R" -> "9°SR 스틸R").

  10.5도 -> 10.5°        33인치 -> 33 in        83.82cm -> 83.82 cm        7,5인치 -> 7.5 in
  22호 -> Size 22        22~25호 -> Size 22–25  3번 -> #3
  7개 -> 7 (the whole text) / 7 pcs           12종 -> 12 pcs           2026년형 -> 2026 model
  노브랜드: the whole text -> the tenant's name (a brand, a spec / fact value); inside a text -> removed
  기타 ("other") as the whole brand -> the tenant's name (the owner, 2026-11-11; transform.NOT_A_BRAND keeps it
  out of the brand already, this is the last guard: the model once gave it a maker's name)

A unit is taken only right after a number and not before another Hangul syllable (강도, 제주도, 1호점 and 3번째
stay). Reviews are left as written: "3번 썼는데" is three times, not club #3.

Checks the stage runs on the model's answer use the same helpers: Hangul left, the numbers and the Latin codes of
the source.
"""
import re
from typing import Any

HANGUL_RE = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")
NO_BRAND = "노브랜드"
NO_BRAND_KINDS = ("brand", "spec_value", "fact_value")     # whole text 노브랜드 there: the tenant's name
OTHER_BRAND = "기타"                                     # the whole brand 기타: the tenant's name (only the brand:
UNTOUCHED_KINDS = ("review",)                            # 기타 as a spec / fact value is "Other")

_NUM = r"(\d+(?:\.\d+)?)"
_FREE = r"(?![가-힣])"                             # not followed by another Hangul syllable
_RULES: list[tuple[re.Pattern[str], str]] = [
    # a decimal comma before a unit, one digit each side ("볼빅 7,5인치 ...": the stand-bag 100 review, 2026-11-27,
    # 10326037559 went out "7,5 in"): "7.5 인치", before the unit rules; every category. Two digits a side stay as
    # written: "30,31인치", "34,36,38cm", "41,46cm" are lists in the shop's texts as often as "45,75인치" is a decimal
    (re.compile(r"(?<![\d,.])(\d),(\d)(?![\d,])(?=\s*(?:인치|cm|kg))", re.I), r"\1.\2"),
    (re.compile(_NUM + r"\s*도" + _FREE), r"\1°"),
    (re.compile(r"°(?=[A-Za-z])"), "° "),                    # 9.5°R -> 9.5° R, as 10.5도 R
    (re.compile(_NUM + r"\s*인치" + _FREE), r"\1 in"),
    (re.compile(_NUM + r"\s*cm\b", re.I), r"\1 cm"),
    (re.compile(r"(\d+)\s*[~\-–]\s*(\d+)\s*호" + _FREE), r"Size \1–\2"),
    (re.compile(r"(\d+)\s*호" + _FREE), r"Size \1"),
    (re.compile(r"(\d+)\s*번" + _FREE + r"\s*"), r"#\1 "),
    (re.compile(r"(\d{4})\s*년형" + _FREE), r"\1 model"),
    (re.compile(r"(\d+)\s*종" + _FREE), r"\1 pcs "),
    (re.compile(r"(\d+)\s*개" + _FREE), r"\1 pcs "),
    # a seller's typo for silver, a word of its own (2026-11-17, the wedge-set review C55: "7 Sliver 52 56 60 Degree",
    # 14 texts of the shop): every category's texts, its case kept
    (re.compile(r"(?<![A-Za-z])([Ss])liver(?![A-Za-z])"), r"\1ilver"),
]
_WHOLE_COUNT_RE = re.compile(r"^\s*(\d+)\s*개\s*$")
_WHOLE_YEAR_RE = re.compile(r"^\s*(\d{4})\s*년형\s*$")             # the whole value (출시 2018년형): the year
_SPACES_RE = re.compile(r"\s{2,}")
_CODE_RE = re.compile(r"[A-Za-z]*\d[A-Za-z0-9]*|[A-Z]{2,}")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def has_hangul(text: str) -> bool:
    return bool(HANGUL_RE.search(text or ""))


def _tidy(text: str) -> str:
    return _SPACES_RE.sub(" ", text).strip(" ,/")


# Rules of one Naver category, before the general ones. 50002788 (golf sets): a glued spec run
# "10.5R유틸4번R8아이언R퍼터" is split after each flex letter (it belongs to the club before it):
# "10.5R, 유틸4번R, 8아이언R, 퍼터" (the 2026-11-08 eval: the model attached the letters to the wrong clubs)
_CLUB = r"(?:드라이버|유틸|우드|아이언|퍼터|웨지|\d)"
CATEGORY_RULES: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "50002788": [(re.compile(r"(?<=[0-9가-힣°])(SR|R|S|L|A|X)(?=" + _CLUB + ")"), r"\1, ")],
}
CATEGORY_RULES["50002787"] = CATEGORY_RULES["50002788"]       # junior clubs write their specs the same way (2026-11-11)
CATEGORY_RULES["50002670"] = CATEGORY_RULES["50002788"]       # women's iron sets write their specs the same way (2026-11-14)
CATEGORY_RULES["50002783"] = CATEGORY_RULES["50002788"]       # wedge sets write their specs the same way (2026-11-15)
CATEGORY_RULES["50002784"] = CATEGORY_RULES["50002788"]       # chippers: the clubs' rule (2026-11-18, none collected yet)


def _loft_run(m: re.Match[str]) -> str:
    """"525660도" -> "52°/56°/60°" when the run is lofts going up (46-72, two digits each), else as written."""
    run = m.group("run")
    lofts = [int(run[i:i + 2]) for i in range(0, len(run), 2)]
    if any(a >= b for a, b in zip(lofts, lofts[1:])):
        return m.group(0)
    # two lofts only ("4856") may be a model or a code: a list only next to 도 / ° or right after 세트 ("세트5460",
    # 13370257430), not "모델 4856" or "6072 스핀" (2026-11-16, the review of this rule)
    if len(lofts) == 2 and not m.group("deg") and not m.string[:m.start()].rstrip().endswith("세트"):
        return m.group(0)
    return " " * (m.group("glued") is not None) + "/".join(f"{x}°" for x in lofts)


# Title rules of one Naver category (titles only, before the category's and the general rules). 50002783 (wedge
# sets, the owner's review 2026-11-16):
# - the shop sells sets only (transform_shops sets_only: a one-club variant is never kept), so the agency
#   titles' "세트 또는 개별 / 또는 개인(용) / 및 개별 / 세트 개인용" ("a set or a single", "개인용" is the machine
#   translation of "single") is dropped: it promised "or Single Wedge" (13016551520, 13016648376, 13016883852,
#   13372276089);
# - a glued run of lofts ("525660도", "505458", "48505254565860", "세트5460") is the list "52°/56°/60°": the
#   model read "5256606468" as "6468" (13566630297) or kept "525660°" (13389307551, 13372006463). Two digits a
#   loft, 46-72, at least two, going up; next to a letter, a digit, "." or "-" it is a code and stays; a run
#   followed by a 도 that starts a Korean word stays ("5256 도매", "525660도클럽"); two lofts only need 도 / ° or 세트 next to them.
#   Up to ten lofts (2026-11-17, the wedge-set review C24: "48505254565860687072°" of 13163033790, 13377515123 and
#   "485052545860687072°" of 13364055281 have nine and ten; a run of seven or more is still read, 13372276089).
_LOFT2 = r"(?:4[6-9]|5\d|6\d|7[0-2])"
TITLE_RULES: dict[str, list[tuple[re.Pattern[str], Any]]] = {
    "50002783": [
        # "or" a word of its own (not the end of "Razor", "Color", "For"); "/" only right after 세트 / 웨지 (not
        # "스틸/싱글 벤드"; both 2026-11-16, the review of this rule)
        (re.compile(r"(?:\s*(?:또는|및|(?<![A-Za-z])or(?![A-Za-z]))|(?<=세트|웨지)\s*/)\s*"
                    r"(?:개별|개인용|개인|싱글|낱개|단품)(?![가-힣])(?:\s*웨지)?"), " "),
        (re.compile(r"(?<=세트)\s*(?:개인용|개인|개별)(?![가-힣])"), " "),
        (re.compile(r"(?i)\s*\bor\s+singles?(?:\s+wedges?)?\b"), " "),
        (re.compile(r"(?<![0-9A-Za-z.\-])(?P<glued>(?<=[가-힣]))?(?P<run>" + _LOFT2 + r"{2,10})(?![0-9.A-Za-z])"
                    r"(?!\s*도[가-힣])(?P<deg>\s*(?:도|°))?"), _loft_run),
    ],
}
# Option values of one Naver category, after the general rules (option_value only). 50002783 (wedge sets, the
# wedge-set review C54, 2026-11-17): raw lofts as sellers and Amazon write them, as the list the titles use; 204
# values of 49 products, no two values of an axis made the same:
# - a whole value of two or three glued lofts going up, even ones ("5056", "525660" -> "50°/56°", 619693409 19);
# - a whole value "loft.bounce" with a grind letter (TaylorMade MG5 "56.12 SB" -> "56° (Bounce 12°) SB");
# - lofts glued with their degree signs ("50°56°" -> "50°/56°");
# - a run of lofts going up before Degree / ° ("52 56 60 Degree Set" -> "52°/56°/60° Set", "56 60° (2 pcs )");
# - an import's " 1 pcs" tail after a set, that is right after "(2 pcs )" or "Set" ("52 56° (2 pcs ) 1 pcs" ->
#   "52°/56° (2 pcs )"); any other value keeps its count ("블랙 1개" -> "블랙 1 pcs", as in other categories).
# A dictionary hit is not sanitized (2026-11-17: the 5 live values with "1 pcs" are single wedges, "52도 웨지 블랙 1개",
# and keep their count, as the rule does: no hand fix due).
_OV_LOFT = r"(?:4[4-9]|5\d|6[0-4])"


def _rising(xs: list[int]) -> bool:
    return all(a < b for a, b in zip(xs, xs[1:]))


def _glued_lofts(text: str) -> str:
    if not re.fullmatch(r"(?:%s){2,3}" % _OV_LOFT, text):
        return text
    xs = [int(text[i:i + 2]) for i in range(0, len(text), 2)]
    return "/".join(f"{x}°" for x in xs) if _rising(xs) and all(x % 2 == 0 for x in xs) else text


def _loft_bounce(text: str) -> str:
    m = re.fullmatch(r"(%s)\.(0[4-9]|1\d)( [A-Z]{1,2})?" % _OV_LOFT, text)
    return f"{m.group(1)}° (Bounce {int(m.group(2))}°)" + (m.group(3) or "") if m else text


def _loft_list(m: re.Match[str]) -> str:
    xs = [int(x) for x in re.findall(r"\d+", m.group("run"))]
    return "/".join(f"{x}°" for x in xs) + (" " if m.group("tail") else "") if _rising(xs) else m.group(0)


OPTION_VALUE_RULES: dict[str, list[tuple[Any, Any]]] = {
    "50002783": [
        (None, _glued_lofts),
        (None, _loft_bounce),
        (re.compile(r"(?<!\d)(%s)°(?=(%s)°)" % (_OV_LOFT, _OV_LOFT)), r"\1°/"),
        (re.compile(r"(?<![\d.])(?P<run>%s(?:[ ]+%s){1,4})\s*(?:°|[Dd]egrees?)(?![A-Za-z])(?P<tail>/\s*)?"
                    % (_OV_LOFT, _OV_LOFT)), _loft_list),
        (re.compile(r"(?:(?<=pcs \))|(?<=pcs\))|(?<=\bSet))\s+1\s*pcs\s*$"), ""),  # only after "(2 pcs )" or the word Set
    ],
}


# A seller's marker token in agency titles (2026-11-16, agencies of one import tool: "db4P" 13552318731, "dbQF"
# 13552339143, "db9N" 13555308677, "dbT1" 13555299850): lower-case "db" and two capitals or digits, a word of its
# own; no other title of 2,451 writes one (an upper-case "DB6" is Orlimar's model and stays). Every category's titles.
_SELLER_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z])db[0-9A-Z]{2}(?![0-9A-Za-z])")
# A seller's product code at the end of a title (2026-11-17, the wedge-set review C07): agency 100217952 ends its titles
# with "WA3817562" / "SA…" (W or S, A, seven digits), shops 100646003 / 102108469 with "품번 4567"; each code is the
# 상품코드 of the product's description, never the model's name. Only at the end of the title (a model code inside
# the title stays); 19 titles of the shop (16 wedge sets, 3 of other categories), no false hit. Every category's titles.
_SELLER_CODE_RE = re.compile(r"\s*(?:(?<![0-9A-Za-z])[WS]A\d{7}|(?<![가-힣A-Za-z])품번\s*\d{3,5})\s*$")


def sanitize(kind: str, ko: str, tenant: str, category_id: str | None = None) -> str:
    """The text with the templates applied (it may still hold Hangul: the model translates the rest)."""
    if kind in UNTOUCHED_KINDS:
        return ko
    if kind == "title":
        for pattern, repl in TITLE_RULES.get(str(category_id or ""), []):
            ko = pattern.sub(repl, ko)
        ko = _SELLER_TOKEN_RE.sub(" ", ko)
        ko = _SELLER_CODE_RE.sub("", ko)
    for pattern, repl in CATEGORY_RULES.get(str(category_id or ""), []):
        ko = pattern.sub(repl, ko)
    text = ko.strip()
    if (text == NO_BRAND and kind in NO_BRAND_KINDS) or (text == OTHER_BRAND and kind == "brand"):
        return tenant
    text = text.replace(NO_BRAND, " ")
    whole = _WHOLE_COUNT_RE.match(text) or _WHOLE_YEAR_RE.match(text)
    if whole:
        return whole.group(1)
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    if kind == "option_value":
        # the general rules leave "1개" as "1 pcs " (a trailing space): strip first, so the anchored rules match
        text = _SPACES_RE.sub(" ", text).strip()
        for value_rule, repl in OPTION_VALUE_RULES.get(str(category_id or ""), []):
            text = repl(text) if value_rule is None else value_rule.sub(repl, text)
        text = _SPACES_RE.sub(" ", text).strip()
    return _tidy(text)


def numbers(text: str) -> list[str]:
    """The numbers of a text, as written ("10.5", "2027"), sorted."""
    return sorted(_NUMBER_RE.findall(text or ""))


def codes(text: str) -> set[str]:
    """The Latin codes of a text the translation must keep: words with a digit (G440, 7i) or capitals (PW, SR, XXIO).
    Upper-cased, so "pgm" in the source and "PGM" in the English match."""
    return {c.upper() for c in _CODE_RE.findall(text or "")
            if not c.isdigit() and not re.fullmatch(r"\d+(?:pcs?|ea|p|pc)", c, re.I)}   # 11pc -> "11 pcs": a count
