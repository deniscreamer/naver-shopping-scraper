"""Size labels as sellers write them (Korean apparel), one parser for every garment profile (scripts/SIZES.md).

`parse_label("M(90)")` -> Label(letter M, chest 90); None when the text is no size (a colour, a type). The numbers are
classified, not converted: a Korean body chest (80..125), a Korean women's size (44..99, "66반" = 66.5), a Japanese
brand's 0..4. What a number means in US sizes is the profile's business (apparel_sizes.resolve, size_profiles/).
A profile whose numbers mean something else (trousers' waist 24..36, shoes' mm 220..290) gets its own reading here
beside these, chosen by the profile's "labels" kind, never by changing these.
"""
import re
from dataclasses import dataclass

_LETTERS = {"XS": "XS", "S": "S", "M": "M", "L": "L", "XL": "XL", "LL": "LL", "XXL": "XXL", "2XL": "XXL",
            "3L": "3L", "XXXL": "XXXL", "3XL": "XXXL", "XXS": "XXS"}
_FREE_RE = re.compile(r"^(?:FREE|F|프리|ONE\s*SIZE|원사이즈|FREESIZE|프리사이즈)$", re.I)
_FREE_RANGE_RE = re.compile(r"^(?:FREE|F|프리|ONESIZE|원사이즈)(?:SIZE|사이즈)?\(([^)]*)\)$")   # "FREE SIZE(44-77)"
_LETTER_RANGE_RE = re.compile(r"^(XXXL|3XL|XXL|2XL|XS|XL|LL|S|M|L)[/\-~](XXXL|3XL|XXL|2XL|XS|XL|LL|S|M|L)$")  # "S/M"
_SIZE_NAME_RE = re.compile(r"사이즈|치수|size", re.I)        # an option's name that says it holds the sizes
_LETTER_RE = re.compile(r"^(XXXL|3XL|XXL|2XL|XXS|XS|XL|LL|3L|S|M|L)$", re.I)
_NUM = r"\d{1,3}(?:\.\d)?(?:반)?"
_RANGE_RE = re.compile(rf"^({_NUM})\s*[-~]\s*({_NUM})$")
_OPEN_RE = re.compile(rf"^~?\s*({_NUM})\s*~?$")              # "77~", "~55": one end of a fit range, that number
_PAREN_RE = re.compile(r"[(\[]([^)\]]*)[)\]]")
_WOMEN = {44, 55, 66, 77, 88, 99}


def _num(text: str) -> float:
    return float(text.replace("반", "")) + (0.5 if text.endswith("반") else 0)


@dataclass(frozen=True)
class Label:
    """One size label as written: "M(90)" -> letter M, chest 90; "L(55-66)" -> letter L, women 55 and 66."""
    letter: str | None = None
    upto: str | None = None                   # the second letter of a letter range ("S/M": S up to M)
    chest: tuple[float, ...] = ()             # Korean body chest numbers written (80..125)
    women: tuple[float, ...] = ()             # Korean women's numbers (44..99, 66.5 for "66반")
    jp: int | None = None                     # a Japanese brand's 0..4
    free: bool = False

    @property
    def key(self) -> str:
        return "|".join([self.letter or "", self.upto or "", ",".join(f"{c:g}" for c in self.chest),
                         ",".join(f"{w:g}" for w in self.women), "" if self.jp is None else str(self.jp),
                         "F" if self.free else ""])


def _numbers(part: str, letter: str | None, jp: int | None) -> tuple[list[float], list[float], int | None] | None:
    chest: list[float] = []
    women: list[float] = []
    for piece in re.split(r"[,/]", part):
        piece = piece.strip()
        if not piece:
            continue
        r = _RANGE_RE.match(piece)
        o = _OPEN_RE.match(piece)
        nums = [_num(r.group(1)), _num(r.group(2))] if r else ([_num(o.group(1))] if o else None)
        if nums is None:
            return None
        for n in nums:
            if int(n) in _WOMEN and n < 100:
                women.append(n)
            elif 80 <= n <= 125:
                chest.append(n)
            elif n == int(n) and 0 <= n <= 4 and jp is None and letter is None:
                jp = int(n)
            else:
                return None
    return chest, women, jp


def parse_label(text: str) -> Label | None:
    """A size label, or None when the text is not one (a colour, a type)."""
    t = re.sub(r"\s+", "", str(text or "")).upper().replace("（", "(").replace("）", ")")
    if _FREE_RE.match(t):                       # "ONE SIZE", "원사이즈": before the 사이즈 / SIZE suffix goes
        return Label(free=True)
    t = re.sub(r"사이즈$|SIZE$", "", t)
    if not t:
        return None
    if _FREE_RE.match(t):
        return Label(free=True)
    m = _FREE_RANGE_RE.match(t)                 # "FREE(44-66반)", "FREE SIZE(44-77)": one size, a fit range
    if m:
        got = _numbers(m.group(1), "F", None)
        return Label(free=True, chest=tuple(got[0]), women=tuple(got[1])) if got else Label(free=True)
    m = _LETTER_RANGE_RE.match(t)
    if m:                                       # "S/M", "M-L": one garment for two sizes
        return Label(letter=_LETTERS[m.group(1)], upto=_LETTERS[m.group(2)])
    inner = _PAREN_RE.findall(t)
    head = _PAREN_RE.sub("", t).strip("-_:")
    letter: str | None = None
    jp: int | None = None
    rest: list[str] = []
    if _LETTER_RE.match(head):
        letter = _LETTERS[head.upper()]
    elif head:
        rest.append(head)
    for part in inner:
        if _LETTER_RE.match(part) and letter is None:       # "85(S)", "100(LL)"
            letter = _LETTERS[part.upper()]
        else:
            rest.append(part)
    chest: list[float] = []
    women: list[float] = []
    for part in rest:
        got = _numbers(part, letter, jp)
        if got is None:
            return None
        chest += got[0]
        women += got[1]
        jp = got[2]
    if letter is None and not chest and not women and jp is None:
        return None
    return Label(letter=letter, chest=tuple(chest), women=tuple(women), jp=jp)


def is_size_name(name: str | None) -> bool:
    """An option or fact label that names the sizes (사이즈, 치수, size)."""
    return bool(_SIZE_NAME_RE.search(str(name or "")))
