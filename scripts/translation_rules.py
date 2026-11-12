"""Deterministic rules applied before a text goes to the model (the owner, 2026-11-08: templates for units and
sizes, the model only as the fallback). A text the rules turn into no Hangul at all is done without the model; a
text with Hangul left goes to the model already partly converted ("9도SR 스틸R" -> "9°SR 스틸R").

  10.5도 -> 10.5°        33인치 -> 33 in        83.82cm -> 83.82 cm
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

HANGUL_RE = re.compile(r"[ᄀ-ᇿ㄰-㆏가-힣]")
NO_BRAND = "노브랜드"
NO_BRAND_KINDS = ("brand", "spec_value", "fact_value")     # whole text 노브랜드 there: the tenant's name
OTHER_BRAND = "기타"                                     # the whole brand 기타: the tenant's name (only the brand:
UNTOUCHED_KINDS = ("review",)                            # 기타 as a spec / fact value is "Other")

_NUM = r"(\d+(?:\.\d+)?)"
_FREE = r"(?![가-힣])"                             # not followed by another Hangul syllable
_RULES: list[tuple[re.Pattern[str], str]] = [
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


def sanitize(kind: str, ko: str, tenant: str, category_id: str | None = None) -> str:
    """The text with the templates applied (it may still hold Hangul: the model translates the rest)."""
    if kind in UNTOUCHED_KINDS:
        return ko
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
    return _tidy(text)


def numbers(text: str) -> list[str]:
    """The numbers of a text, as written ("10.5", "2027"), sorted."""
    return sorted(_NUMBER_RE.findall(text or ""))


def codes(text: str) -> set[str]:
    """The Latin codes of a text the translation must keep: words with a digit (G440, 7i) or capitals (PW, SR, XXIO).
    Upper-cased, so "pgm" in the source and "PGM" in the English match."""
    return {c.upper() for c in _CODE_RE.findall(text or "")
            if not c.isdigit() and not re.fullmatch(r"\d+(?:pcs?|ea|p|pc)", c, re.I)}   # 11pc -> "11 pcs": a count
