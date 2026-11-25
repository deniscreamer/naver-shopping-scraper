"""Size labels as sellers write them (Korean apparel), one parser for every garment profile (scripts/SIZES.md).

`parse_label("M(90)")` -> Label(letter M, chest 90); None when the text is no size (a colour, a type). The numbers are
classified, not converted: a Korean body chest (80..125), a Korean women's size (44..99, "66반" = 66.5), a Japanese
brand's 0..4. What a number means in US sizes is the profile's business (apparel_sizes.resolve, size_profiles/).
A profile whose numbers mean something else (trousers' waist 24..36, shoes' mm 220..290) gets its own reading here
beside these, chosen by the profile's "labels" kind, never by changing these.
"""
import contextlib
import contextvars
import re
from collections.abc import Iterator
from dataclasses import dataclass

_LETTERS = {"XS": "XS", "S": "S", "M": "M", "L": "L", "XL": "XL", "LL": "LL", "XXL": "XXL", "2XL": "XXL", "2XS": "XXS",
            "3L": "3L", "XXXL": "XXXL", "3XL": "XXXL", "XXS": "XXS"}
_FREE_RE = re.compile(r"^(?:FREE|F|프리|ONE\s*SIZE|원사이즈|FREESIZE|프리사이즈)$", re.I)
_FREE_RANGE_RE = re.compile(r"^(?:FREE|F|프리|ONESIZE|원사이즈)(?:SIZE|사이즈)?\(([^)]*)\)$")   # "FREE SIZE(44-77)"
_LETTER_RANGE_RE = re.compile(r"^(XXXL|3XL|XXL|2XL|XS|XL|LL|S|M|L)[/\-~](XXXL|3XL|XXL|2XL|XS|XL|LL|S|M|L)$")  # "S/M"
_SIZE_NAME_RE = re.compile(r"사이즈|치수|size", re.I)        # an option's name that says it holds the sizes
_LETTER_RE = re.compile(r"^(XXXL|3XL|XXL|2XL|XXS|2XS|XS|XL|LL|3L|S|M|L)$", re.I)
_NUM = r"\d{1,3}(?:\.\d)?(?:반)?"
_RANGE_RE = re.compile(rf"^({_NUM})\s*[-~]\s*({_NUM})$")
_OPEN_RE = re.compile(rf"^~?\s*({_NUM})\s*~?$")              # "77~", "~55": one end of a fit range, that number
_PAREN_RE = re.compile(r"[(\[]([^)\]]*)[)\]]")
_SIZE_WORD = {"투엑스라지": "XXL", "엑스라지": "XL", "라지": "L", "미디움": "M", "미디엄": "M", "스몰": "S", "프리": "F"}
_WORD_LETTER = {"XXL": "XXL", "2XL": "XXL", "XL": "XL", "L": "L", "M": "M", "S": "S", "F": "F", "FREE": "F"}
_SIZE_WORDS = "투엑스라지|엑스라지|라지|미디움|미디엄|스몰|프리"
_WORD_LETTERS = "FREE|XXL|2XL|XL|L|M|S|F"
_WOMEN = {33, 44, 55, 66, 77, 88, 99}            # 33: below 44 ("XS (33~44)", PXG 5429994082, 2026-11-20)


# a waist is read only for a profile keyed by the waist (skirts, 2026-11-22): in a top's chart "73" is a length, never
# a size; apparel_sizes.resolve and transform._sizes turn it on for such a profile
WOMENS_WAIST = (22.0, 38.0, 58.0, 79.0, False)
# men's trousers (Golf Pants 50002801, 2026-11-23): waists 26..44 inches, 66..112 cm, read before the women's sizes
# and the chest ("88", "85" are a men's waist in cm there, never a women's 88 or a chest); up to 46 inches since
# 2026-11-24 (6818506441: 30..46, its chart's 46 a flat 58 cm waist)
MENS_WAIST = (26.0, 46.0, 66.0, 112.0, True)
# (inches low, high, cm low, high, read first) or None
_WAIST: contextvars.ContextVar[tuple[float, float, float, float, bool] | None] = contextvars.ContextVar("waist",
                                                                                                      default=None)


@contextlib.contextmanager
def waist_labels(on: bool | tuple[float, float, float, float, bool] | None = True) -> Iterator[None]:
    """Read waists in the labels inside the block: True the women's (22..38 inches, 58..79 cm), a tuple its own
    ranges (MENS_WAIST), False / None none."""
    token = _WAIST.set(WOMENS_WAIST if on is True else (on or None))
    try:
        yield
    finally:
        _WAIST.reset(token)


def waist_reading() -> tuple[float, float, float, float, bool] | None:
    """The waist ranges read inside the current waist_labels block, or None."""
    return _WAIST.get()


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
    waist: tuple[float, ...] = ()             # a waist in cm: 22..38 inches (x 2.54) or 58..79 cm (skirts, 2026-11-22)

    @property
    def key(self) -> str:
        return "|".join([self.letter or "", self.upto or "", ",".join(f"{c:g}" for c in self.chest),
                         ",".join(f"{w:g}" for w in self.women), "" if self.jp is None else str(self.jp),
                         "F" if self.free else ""] + ([",".join(f"{w:g}" for w in self.waist)] if self.waist else []))


def _numbers(part: str, letter: str | None,
             jp: int | None) -> tuple[list[float], list[float], int | None, list[float]] | None:
    chest: list[float] = []
    women: list[float] = []
    waist: list[float] = []
    for piece in re.split(r"[,/]", part):
        piece = piece.strip()
        if not piece:
            continue
        r = _RANGE_RE.match(piece)
        o = _OPEN_RE.match(piece)
        nums = [_num(r.group(1)), _num(r.group(2))] if r else ([_num(o.group(1))] if o else None)
        if nums is None:
            return None
        w = _WAIST.get()
        # a women's waist profile: a range of inches up to 3 apart, whole or 반, is the body waist, even with a women's
        # 33 at one end ("2XL(32~33)", "M(26반~27)": 12370291326, 2026-11-24, held "not read"); never the men's
        if r and w and not w[4] and all(w[0] <= n <= w[1] and (n * 2) == int(n * 2) for n in nums) \
                and 0 < nums[1] - nums[0] <= 3:
            waist += [round(n * 2.54, 1) for n in nums]
            continue
        for n in nums:
            if w and w[4] and ((n == int(n) and w[0] <= n <= w[1]) or w[2] <= n <= w[3]) \
                    and not (letter and n >= 90 and n % 5 == 0):   # "M(95)": a top's chest beside a letter (a polo
                                                             # sold with the pants, 5534297375, 2026-11-23), never a
                                                             # waist; "2XL(92)" is one (92 cm)
                waist.append(round(n * 2.54, 1) if n <= w[1] and n == int(n) else n)   # men's: "32", "82"
            elif int(n) in _WOMEN and n < 100:
                women.append(n)
            elif 80 <= n <= 125:
                chest.append(n)
            elif n == int(n) and 0 <= n <= 4 and jp is None and letter is None:
                jp = int(n)
            elif w and n == int(n) and w[0] <= n <= w[1]:         # a waist in inches ("26", "M(27)", "25-26")
                waist.append(round(n * 2.54, 1))
            elif w and w[2] <= n <= w[3]:                         # a waist in cm ("64", "67(S)")
                waist.append(n)
            else:
                return None
    return chest, women, jp, waist


def parse_label(text: str) -> Label | None:
    """A size label, or None when the text is not one (a colour, a type)."""
    t = re.sub(r"\s+", "", str(text or "")).upper().replace("（", "(").replace("）", ")")
    t = t.replace("[", "(").replace("]", ")")       # "FREE[55~66]" (5932679597, 2026-11-20) is "FREE(55~66)"
    # a shipping note after the size, its bracket sometimes lost: "30(당일발송)", "30당일발송)" (2026-11-24, Callaway
    # 6486608544: held "not read as a size"); the size itself, one with the bare "30" beside it (merged)
    t = re.sub(r"\(?(?:당일|오늘|즉시)(?:발송|출고|출발)\)?$|\(빠른배송\)$", "", t)
    # 2026-11-21, the long-sleeve tops pilot: a seller's note after the size ("S(44)모델착용사이즈": the model wears it,
    # 7303524506, 6454520137), the word 사이즈 inside the brackets ("55(S사이즈)", 5857396168) and a size's number before
    # the women's sizes it fits ("1사이즈(44-55사이즈)", "2번(66-77)": 5627070774, 5660255053) read as the size itself
    # "FREE(44~55)모델착용컷": the model's photo (컷) wears it (5202996089, 2026-11-24)
    t = re.sub(r"(?:모델\s*착용(?:사이즈|컷)?|모델사이즈|추천)$", "", t)
    t = re.sub(r"(?:사이즈|SIZE)(?=\))", "", t)
    t = re.sub(r"^(?:\d{1,2}번|\d사이즈)(?=\()", "", t)    # "1사이즈(...)", "2번(...)"; never "55사이즈(S)"
    t = re.sub(r"\((?:UP|DOWN|업|다운)추천\)", "", t)   # "S(up추천)": size up advised, the size S (2026-11-23, 5117895030)
    t = re.sub(r"\(([A-Z0-9~\-]+)추천\)", r"(\1)", t)      # "55사이즈 (S 추천)": a recommended letter (5857396168)
    t = re.sub(r"(?<=\d)사이즈(?=\(|$)", "", t)
    # 2026-11-22, the men's tops pilot: a note in brackets after the size ("S(모델착용사이즈)", "S(상세사이즈 확인했습니다)"),
    # "about" after a chest ("XS (85 전후)", "S (95전후)"), a gender before the size ("여성 55(M)"; 남_M(95) beside
    # 여_S(55) stays two systems), a Korean letter word ("라지(77-88)") and the chest after a bare letter ("S 95사이즈",
    # "S 95~100사이즈": Nike 7973150842, Callaway 7184031093, 5033870845) read as the size they name
    t = re.sub(r"\((?:모델|상세|착용|확인|기준|정사이즈)[가-힣]*\)$", "", t)
    # who the chest fits after a dash in its brackets: "XL(100-여성77이상/남성M)" is XL(100) (5964063532, 2026-11-24);
    # the whole words 여성 / 남성 only, never a bare 여 / 남 ("L(100-남색)": navy stays unread)
    t = re.sub(r"\((\d{2,3})-(?:여성|남성)[^)]*\)$", r"(\1)", t)
    t = re.sub(r"날씬|통통", "", t)                       # "S（55~날씬66）": slim / chubby (8628740416, 2026-11-22)
    # "이상" (and over) after a women's size is the open end: "XL（통통66반이상）", "2XL（77이상）" (할로 5282622633,
    # 2026-11-25) are "66반~", "77~"
    t = re.sub(r"(?<!\d)((?:44|55|66|77|88|99)반?)이상(?=\)|$)", r"\1~", t)
    w = _WAIST.get()
    if w and w[4]:
        # adidas' Asian waist code with the inch the seller writes for it, in the men's trousers: "A82 (32인치)" is
        # 82 cm with its inch 32 (cm_inch takes the inch: 7191019224, 10159594995, 2026-11-24); 인치 must be written,
        # a bare "A79" stays unread
        t = re.sub(r"^A(\d{2,3})\((\d{2})인치\)$", r"\1(\2)", t)
    # "about" in the brackets after a letter and 사이즈: "XXS사이즈(약80)" is XXS with the chest 80 (Klattermusen rainwear
    # 5460564989, 2026-11-25); never 약 alone ("화이트(약기모)" is a light fleece)
    t = re.sub(r"^(XXXL|3XL|XXL|2XL|XXS|2XS|XS|XL|S|M|L)(?:사이즈)?\(약(\d{2,3})\)$", r"\1(\2)", t)
    t = re.sub(r"(?<=\d)인치", "", t)                     # "XS（25인치）", "XS (25인치 전후)" (J.Lindeberg, 2026-11-22)
    t = re.sub(r"(?<=\d)전후(?=\))", "", t)
    # a Japanese maker's chest in 호 after the letter: "S(90호)" (Titleist Japan rainwear 4819248041, 2026-11-24) is
    # S(90); a bare "0호" stays unread (a Japanese 0..4 written so is not taken)
    # LL / 3L too, the Japanese letters ("LL(105호)", "3L(110호)": the same product, 2026-11-24)
    t = re.sub(r"^(XXXL|3XL|XXL|2XL|XS|XL|LL|3L|S|M|L)\((\d{2,3})호\)$", r"\1(\2)", t)
    if not w:
        # outside the waist profiles (2026-11-24, the size_unmapped review):
        # a head number with a women's size and a letter in one bracket, "75(44/S)", "85(XS.44)" (pgr 4260789645 /
        # 4648580312, Hillcrest 12931719346): the women's size and the letter, the head number dropped
        t = re.sub(r"^\d{2,3}\((33|44|55|66|77|88|99)[/.](XXL|2XL|XL|XS|S|M|L)\)$", r"\1(\2)", t)
        t = re.sub(r"^\d{2,3}\((XXL|2XL|XL|XS|S|M|L)[/.](33|44|55|66|77|88|99)\)$", r"\2(\1)", t)
        # a European 46..54 with the Korean chest in brackets, "46(90)" (IKALOOK 7557074073): the chest; "44(85)"
        # stays the women's 44 with its chest
        t = re.sub(r"^(46|48|50|52|54)\((8[5-9]|9\d|1[01]\d)\)$", r"(\2)", t)
        # a women's letter, "WS / WM / WL" (13483086996: the brand's guide, WS for a 90 bust): the letter; the whole
        # label W and one letter only
        t = re.sub(r"^W(XS|S|M|L|XL)$", r"\1", t)
        # adidas' Asian letter with the Korean chest, "AL(95)", "AS (85)" (10861903381): the chest, 80..125 only
        t = re.sub(r"^A(?:XS|S|M|L|XL|2XL|3XL)\((\d{2,3})\)$",
                   lambda m: f"({m.group(1)})" if 80 <= int(m.group(1)) <= 125 else m.group(0), t)
    if w and w[4]:
        # the men's trousers (Golf Pants 50002801, 2026-11-24): J.Lindeberg writes the maker's waist with the Korean
        # one, an inch up, in brackets: "29(30인치)" (6780190931), "29(30)" (4720043508), "29인치(30인치전후)"
        # (7006521057), "30(국내31)" (4530831170: "한국사이즈 33 이시면 32로 주문"; the reviews "31(국내32)"): one
        # waist, the maker's (the first number), never a band from one to the other
        t = re.sub(r"^(\d{2})\((?:국내|한국)\d{2,3}\)$", r"\1", t)
        # a waist with a big letter of that style's own in brackets, "36(4XL)", "38(5XL)", "40(6XL)" (매일츄리닝
        # 7455950253, 2026-11-25: its 융기모패딩조거 sells "30(XL)" .. "40(6XL)", the 32-inch model wears "2XL(32)"): the
        # waist; "30(XL)" .. "34(3XL)" read so already, a bare "4XL" stays unread
        t = re.sub(r"^(\d{2})\((?:4|5|6)XL\)$", r"\1", t)
        m = re.match(r"^(\d{2})\((\d{2})\)$", t)
        if m and int(m.group(2)) == int(m.group(1)) + 1 and w[0] <= int(m.group(1)) < w[1]:
            t = m.group(1)
    t = re.sub(r"^(?:여성|남성|여자|남자|여|남)[_\-:]?(?=[0-9SMLX(])", "", t)
    # 2026-11-25 (핑크골프 7965635614): a Korean size word with its own letter in brackets, "라지(L)", "엑스라지(XL)",
    # "프리(F)", is that letter; its chart's "L-라지(66~77)", "F-프리(55~66)" the letter with that range; the word and
    # the letter must agree ("라지(XL)" stays unread)
    t = re.sub(rf"^({_SIZE_WORDS})\(({_WORD_LETTERS})\)$",
               lambda m: m.group(2) if _SIZE_WORD[m.group(1)] == _WORD_LETTER.get(m.group(2)) else m.group(0), t)
    t = re.sub(rf"^({_WORD_LETTERS})-({_SIZE_WORDS})(\([^)]*\))$",
               lambda m: m.group(1) + m.group(3) if _SIZE_WORD[m.group(2)] == _WORD_LETTER.get(m.group(1))
               else m.group(0), t)
    for word, said in (("투엑스라지", "XXL"), ("엑스라지", "XL"), ("라지", "L"), ("미디움", "M"), ("미디엄", "M"),
                         ("스몰", "S")):
        t = re.sub(rf"^{word}(?=\(|$)", said, t)
    # a one-size garment the seller files under a letter, the free word in brackets: "L（FREE）" (Rainwear 50002816,
    # 2026-11-24, the poncho 8731658115: one size, its spec row 사이즈) is one size, never a letter
    t = re.sub(r"^(?:XXXL|3XL|XXL|2XL|XL|S|M|L)\((FREE|F|프리|프리사이즈|FREESIZE|ONESIZE)\)$", r"\1", t)
    if _FREE_RE.match(t):                       # "ONE SIZE", "원사이즈": before the 사이즈 / SIZE suffix goes
        return Label(free=True)
    t = re.sub(r"사이즈$|SIZE$", "", t)
    t = re.sub(rf"^(XXXL|3XL|XXL|2XL|XXS|2XS|XS|XL|LL|S|M|L)({_NUM}(?:[-~]{_NUM})?)$", r"\1(\2)", t)   # "S95~100"
    if not t:
        return None
    if _FREE_RE.match(t):
        return Label(free=True)
    m = _FREE_RANGE_RE.match(t)                 # "FREE(44-66반)", "FREE SIZE(44-77)": one size, a fit range
    if m:
        got = _numbers(m.group(1), "F", None)
        return Label(free=True, chest=tuple(got[0]), women=tuple(got[1]), waist=tuple(got[3])) if got \
            else Label(free=True)
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
    waist: list[float] = []
    for part in rest:
        got = _numbers(part, letter, jp)
        if got is None:
            return None
        chest += got[0]
        women += got[1]
        jp = got[2]
        waist += got[3]
    if letter is None and not chest and not women and jp is None and not waist:
        return None
    return Label(letter=letter, chest=tuple(chest), women=tuple(women), jp=jp, waist=tuple(waist))


def is_size_name(name: str | None) -> bool:
    """An option or fact label that names the sizes (사이즈, 치수, size)."""
    return bool(_SIZE_NAME_RE.search(str(name or "")))
