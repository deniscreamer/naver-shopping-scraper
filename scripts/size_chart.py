"""The seller's size chart from text lines: the description's text and the OCR rows of its images (the cells of one
visual line joined left to right with " / "; no x positions are kept, and none are needed: the 36 tables of the
knit pilot all split right on " / " or "|", 2026-11-19 study). Shared by every garment profile; which measures a
profile reads, their words and their plausible ranges, is its "measures" set (MEASURE_SETS). scripts/SIZE_CHARTS.md.

The layouts read (SIZE_CHARTS.md "The layouts", P1-P5):
  P1  by row under a header of measure names: "사이즈 | 어깨너비 | 가슴둘레" / "85 (S) | 39 | 95"
  P2  the same with a header without the size cell, cm and inches in a cell: "총장 / 어깨너비" / "90 (S) / 55cm (21.7in)"
  P3  by column, the sizes across: "사이즈 / M(90) / L(95)" / "가슴너비 / 46 / 48.5"; one size column too ("호칭 / FREE")
  P4  a label then name+number pairs: "L 총장 61 어깨 35 가슴 44", "S(90)-총장56/어깨37/가슴48"
  P5  a FREE product's lines with no label: "총장59/어깨54/가슴56", "어깨(cm): 40", "가슴 / 46"
Never read: the model, the buyer, the shop, size lists, recommendation tables, measuring-method text (NOT_CHART_RE,
the ranges), a model block's Bust line, a number before 사이즈; an exact cell count or no row: a dropped cell skips
the row, never shifts it; a value that breaks its table's run is dropped from its row (_breaks, 2026-11-20).
"""
import re
from dataclasses import dataclass, field
from typing import Any

from size_labels import _LETTER_RE, _LETTERS, Label, parse_label


@dataclass(frozen=True)
class Measure:
    name: str                                # the field: chest, length, shoulder, sleeve (tops)
    words: re.Pattern[str]                   # a cell that names it
    flat: tuple[float, float]                # plausible cm laid flat (a chest's half)
    round_: tuple[float, float]              # plausible cm all the way round, or along the garment


# the first measure whose words match a cell names it: sleeve before length ("Sleeve Length")
MEASURE_SETS: dict[str, tuple[Measure, ...]] = {
    "tops": (
        # 품 alone or as 품단면 / 품너비, never inside a word (상품, 제품, 반품: a shop's policy line read as chest 7)
        Measure("chest", re.compile(r"가슴|가습|(?<![가-힣])품(?:\s*(?:단면|너비|폭|둘레))?(?![가-힣])|bust|chest", re.I),
                (30, 80), (70, 160)),
        # 소매 길이 / 기장, 팔길이 (9717223659); never 소매통 / 소매단 / 팔둘레 / 화장 / a bare "Sleeve" (팔둘레, 11160224814)
        Measure("sleeve", re.compile(r"^소매$|소매\s*(?:길이|기장)|팔\s*(?:길이|기장)|sleeve\s*length", re.I), (10, 95), (10, 95)),
        Measure("length", re.compile(r"총\s*장|총\s*기장|총\s*길이|^기장|상의\s*길이|length", re.I), (30, 120), (30, 120)),
        Measure("shoulder", re.compile(r"어깨|shoulder", re.I), (25, 75), (25, 75)),
    ),
    # skirts (2026-11-22, Golf Skirts & Culottes 50002802): the waist and the hip, laid flat or round, and the length
    "bottoms": (
        Measure("waist", re.compile(r"허리(?!\s*밴딩)|waist", re.I), (28, 52), (55, 110)),
        Measure("hip", re.compile(r"엉덩이|힙(?!업)|hip", re.I), (38, 70), (76, 140)),
        Measure("length", re.compile(r"총\s*장|총\s*기장|총\s*길이|^기장|치마\s*(?:길이|기장)|스커트\s*(?:길이|기장)|length",
                                    re.I), (30, 110), (30, 110)),
    ),
}
_FLAT_RE = re.compile(r"단면|너비|넓이|폭|width", re.I)        # ("가슴/2" never reaches here: "/" splits cells)
_CIRC_RE = re.compile(r"둘레|들레|circ", re.I)          # 들레: OCR's 둘레 (11206784343)
# the corner cell: a word for the size, or the unit alone ("CM / 90 / 95 / 100 / 105", 13021502381, 2026-11-20)
_SIZE_HEAD_RE = re.compile(r"^(?:(?:사이즈|size|치수|호\s*칭|구\s*분|단\s*위)(?:\s*\(?\s*cm\s*\)?)?(?:\s*[:：]?\s*cm)?|"
                           r"\(?\s*cm\s*\)?)$", re.I)
_KOREA_HEAD_RE = re.compile(r"^(?:korea(?:n)?\s*size|kr|kor|한국|국내)", re.I)
_US_HEAD_RE = re.compile(r"^(?:us|usa|미국)(?:\s*size)?$", re.I)
_CELL_SPLIT_RE = re.compile(r"\s*[|/\t]\s*")
_UNIT_RE = re.compile(r"\(\s*(?:단위\s*[:：]?\s*)?cm\s*\)", re.I)                    # "어깨(cm): 40" -> "어깨: 40"
# a number before 사이즈 / size is a women's size, never a measure ("어깨가넓은 마른66사이즈": 11573884405, 2026-11-20)
_PAIR_RE = re.compile(r"([가-힣A-Za-z]+)\s*[:\-]?\s*(\d{1,3}(?:\.\d{1,2})?)(?![\d.]*(?:사이즈|[sS][iI][zZ][eE]))")
_CELL_VALUE_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,2})?)\s*(?:cm|㎝)?\s*(?:\(\s*\d{1,3}(?:\.\d{1,2})?\s*(?:in|inch|inches|\")"
                            r"\s*\))?$", re.I)          # "55cm (21.7in)" -> 55 (13722416544); "21.7in" alone: none
# one cell written twice, "53/53" with no space ("85 (S) | 36 | 92 | 58 | 53/53", 11377634969): one value; an OCR row
# joins its cells with " / ", spaces both sides, so it never matches
_TWIN_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,2})?)/\1(?![\d./])")
# the body measures of a model block ("Height : 173cm" / "Bust : 83cm" / "Waist : 62cm" / "Hip : 90cm", 10940191023):
# a Bust line with another of these within _BODY_NEAR lines is the model's, never a chart (2026-11-20)
_BODY_RE = re.compile(r"^\s*(height|bust|waist|hips?)\s*[:：]", re.I)
_BODY_NEAR = 4
_FIGURE_RE = re.compile(r"^(?:\d{1,2}\s*[.)]|[①-⑳])\s*")
_ITEM_RE = re.compile(r"^[a-h]$")             # an OCR'd figure letter before a row ("b / 가슴둘레 / 86 / 91")
ONE = "__one_size__"                          # the measurements written with no size label (a FREE product)
# a line about the model, the buyer or the shop, never a garment's measurements ("모델 신장 165 / 가슴둘레 82",
# "66 착용 / 키 165", "구매상품금액 7만원", "체형 가슴 90", 2026-11-19 review and study)
NOT_CHART_RE = re.compile(r"모델|착용|(?<![가-힣])키\s*:?\s*\d|신장|체중|몸무게|체형|신체|\d\s*kg|\d\s*만?\s*원|배송|반품|교환|"
                           r"상품\s*번호|model|wear", re.I)
_FLAT_NOTE_RE = re.compile(r"단면\s*(?:을\s*)?기준|cm\s*/\s*단면|단면\s*\)")         # "*상세치수는 단면기준 cm"
_CIRC_NOTE_RE = re.compile(r"(?:둘레|들레)는|[x×]\s*2")                              # "둘레는 ... ×2사이즈입니다"
_SECTION_MAX = 24                             # a line naming a type's section ("(앞면 로고형)") is short
# what a type's heading may carry beside the type's value: brackets, 형 / 타입, the garment's noun
_HEADING_REST_RE = re.compile(r"[\s()\[\]\-_:·.,/]|형|타입|버전|ver|가디건|카디건|니트|집업|자켓|재킷|점퍼|베스트|조끼|스웨터|"
                              r"상세|사이즈|size", re.I)
_BREAK_MIN = 3.0                              # cm: the least span a run's neighbours allow (_breaks)
_SPACED_HANGUL_RE = re.compile(r"(?<=[가-힣])\s+(?=[가-힣])")          # "소매 기장 58" -> "소매기장 58"


def _value(cell: str) -> float | None:
    m = _CELL_VALUE_RE.match(cell.strip())
    return float(m.group(1)) if m else None


@dataclass
class Chart:
    """What the seller's chart says: per label, the measurements (cm) and the pairings it shows."""
    rows: dict[str, dict[str, float]] = field(default_factory=dict)      # label text -> {field: cm}
    labels: dict[str, Label] = field(default_factory=dict)
    kinds: dict[str, str | None] = field(default_factory=dict)           # field -> flat / circ / None
    us: dict[str, str] = field(default_factory=dict)                     # label text -> US letter written
    korea: dict[str, float] = field(default_factory=dict)                # label text -> Korean chest written
    sections: dict[str, str] = field(default_factory=dict)               # ONE#<value> -> the type's Korean value
    conflicts: list[str] = field(default_factory=list)                   # a second one-size block nothing ties

    def add(self, label: str, values: dict[str, float]) -> None:
        if label not in self.rows:
            self.rows[label] = {}
        for k, v in values.items():
            self.rows[label].setdefault(k, v)


class _Reader:
    def __init__(self, measures: tuple[Measure, ...], sections: list[str]) -> None:
        self.measures = measures
        self.by_name = {m.name: m for m in measures}
        self.sections = {re.sub(r"\s+", "", s): s for s in sections
                         if s and len(re.sub(r"\s+", "", s)) >= 2 and parse_label(s) is None}
        self.chart = Chart()
        self.hints: dict[str, str] = {}
        self.table = 0                                   # the table being read: a new header or columns line opens one
        self.origin: dict[tuple[str, str], int] = {}     # (label, field) -> the table its kept value came from

    def measure(self, cell: str) -> tuple[str, str | None] | None:
        for m in self.measures:
            if m.words.search(cell):
                kind = "flat" if _FLAT_RE.search(cell) else "circ" if _CIRC_RE.search(cell) else None
                return m.name, kind
        return None

    def kind(self, m: tuple[str, str | None]) -> None:
        """The field's kind from the word of the value kept (put() calls it only for a value it stores); two values
        of one field with different words make it "mixed" (chart_html then judges each value by its size)."""
        have = self.chart.kinds.get(m[0])
        if m[1] is None:
            self.chart.kinds.setdefault(m[0], None)
        elif have is None:
            self.chart.kinds[m[0]] = m[1]
        elif have != m[1]:
            self.chart.kinds[m[0]] = "mixed"

    def plausible(self, name: str, cm: float, kind: str | None) -> bool:
        m = self.by_name[name]
        lo, hi = (m.flat if kind == "flat" else m.round_ if kind == "circ" else (min(m.flat[0], m.round_[0]),
                                                                                 max(m.flat[1], m.round_[1])))
        return lo <= cm <= hi

    def put(self, label: str, values: dict[str, tuple[float, str | None]]) -> bool:
        """The values that are plausible for their field; False (nothing kept) when one is not: a row with a "2"
        for a chest is no chart row (2026-11-19 study: "가슴 / 2")."""
        if not values or not all(self.plausible(k, v, kind) for k, (v, kind) in values.items()):
            return False
        have = self.chart.rows.get(label) or {}
        for k, (_, kind) in values.items():
            if k not in have:                    # the value kept is the first: its word is the kind (a second
                self.kind((k, kind))             # table's 둘레 never relabels a first table's 단면 values)
                self.origin[(label, k)] = self.table
        self.chart.add(label, {k: v for k, (v, _) in values.items()})
        return True

    def heading(self, raw: str) -> str | None:
        """The type a short line heads ("(앞면 로고형)", "니트집업가디건 (뒷면로고형)"): no digit, exactly one type's
        value, nothing else but brackets, 형 / 타입 and the garment's noun ("앞면로고 타입은 ... 보다" is prose)."""
        squeezed = re.sub(r"\s+", "", raw)
        if not self.sections or len(squeezed) > _SECTION_MAX or re.search(r"\d", squeezed):
            return None
        hits = [v for k, v in self.sections.items() if k in squeezed]
        if len(hits) != 1:
            return None
        rest = _HEADING_REST_RE.sub("", squeezed.replace(re.sub(r"\s+", "", hits[0]), "", 1))
        return hits[0] if not rest else None


def _row_cells(line: str) -> list[str]:
    return [c.strip() for c in _CELL_SPLIT_RE.split(line.strip()) if c.strip()]


def read_chart(lines: list[str], measures: str = "tops", sections: list[str] | None = None) -> Chart:
    """The seller's size chart from text lines (description text, OCR rows "a / b / c"); `measures`: the profile's
    set; `sections`: the Korean values of a type option (not a size, not a colour), whose one-size blocks are told
    apart ("니트집업가디건 (뒷면로고형)": 10885610305)."""
    r = _Reader(MEASURE_SETS[measures], sections or [])
    chart = r.chart
    header: list[tuple[str, str | None] | None] | None = None      # row layout: the measure of each column
    header_has_size = True                                         # its first cell is the size column's
    columns: list[str] | None = None                              # column layout: the size label of each column
    one_column = False                                            # a one-size column ("호칭 / FREE(66-88)")
    last_was_header = False
    header_rows = 0                                               # rows read under the current header
    section: str | None = None
    body = {i: b.group(1).lower() for i, line in enumerate(lines) if (b := _BODY_RE.match(line))}
    for i, raw in enumerate(lines):
        if i in body and any(body.get(j) not in (None, body[i]) for j in range(i - _BODY_NEAR, i + _BODY_NEAR + 1)):
            last_was_header = False
            continue
        text = _TWIN_RE.sub(r"\1", _UNIT_RE.sub("", raw))
        cells = _row_cells(text)
        if len(cells) > 2 and _ITEM_RE.match(cells[0]) and r.measure(cells[1]):
            cells = cells[1:]
        # a diagram's number before a measure's name ("1.어깨 / 2.가슴 / 3.소매 / 7.총길이": 2026-11-21, the tops
        # pilot, 5378291032's chart was lost): the name; a cell of a size or a number keeps it
        cells = [c2 if (c2 := _FIGURE_RE.sub("", c)) != c and r.measure(c2) else c for c in cells]
        hit = r.heading(raw)
        if hit:
            section = hit
            continue
        if not cells or NOT_CHART_RE.search(raw):
            last_was_header = False
            continue
        if _FLAT_NOTE_RE.search(raw) and not _CIRC_RE.search(raw):        # kind hints outside the table (F8)
            for spec in r.measures:                                       # the fields laid flat or round: the
                if spec.flat != spec.round_:                              # chest; the waist and hip (skirts)
                    r.hints.setdefault(spec.name, "flat")
        elif _CIRC_RE.search(raw) and _CIRC_NOTE_RE.search(raw):
            for spec in r.measures:
                if spec.flat != spec.round_:
                    r.hints.setdefault(spec.name, "circ")
        if len(cells) == 1 and not re.search(r"\d", cells[0]) and (m := r.measure(cells[0])) and m[1]:
            r.hints.setdefault(m[0], m[1])                               # a diagram's "가슴단면"
        measures_of = [r.measure(c) for c in cells]
        first = parse_label(cells[0])
        values = [_value(c) for c in cells]
        # a column-layout header: "사이즈 / XS / S / M / L", "XS / S / M / L", "호칭 / FREE(66-88)"
        sized = bool(_SIZE_HEAD_RE.match(cells[0]))
        labels = [parse_label(c) for c in cells[1:]] if sized else [first] + [parse_label(c) for c in cells[1:]]
        # a line whose corner is a size word ("사이즈 / 90 / 95 / 100 / 105") is a column header, never a row under a
        # header of measure names: a diagram's labels ("총길이 / 소매길이 / 총길이 / 총길이") of as many cells came right
        # before the chart of PING 12361710158 (2026-11-20, the windbreaker pilot) and swallowed it
        under_header = not sized and bool(header) and all(v is not None for v in values[1:]) and \
            len(cells) - 1 == len(header or []) - (1 if header_has_size else 0)
        if len(cells) >= 3 and all(labels) and not any(measures_of[1:]) and not under_header:   # "S | 92 | 88" is a row
            columns = cells[1:] if sized else cells
            r.table += 1
            for n, lab in zip(columns, labels):
                chart.labels[n] = lab              # type: ignore[assignment]
            header, one_column, last_was_header = None, False, False
            continue
        if sized and len(cells) == 2 and "," not in cells[1] and (lab := parse_label(cells[1])) \
                and (lab.free or len(lab.chest) <= 1) and len(lab.women) <= 2:   # one size column (13823433220)
            columns, one_column, header, last_was_header = [cells[1]], True, None, False
            r.table += 1
            chart.labels[cells[1]] = lab
            continue
        if columns and len(cells) == len(columns) + 1:
            vals = cells[1:]
            if _US_HEAD_RE.match(cells[0]) and all(_LETTER_RE.match(v) for v in vals):
                chart.us.update({c: _LETTERS[v.upper()] for c, v in zip(columns, vals)})
                continue
            nums = [_value(v) for v in vals]
            if _KOREA_HEAD_RE.match(cells[0]) and all(n is not None for n in nums):
                chart.korea.update({c: float(n) for c, n in zip(columns, nums) if n is not None})
                continue
            m = r.measure(cells[0])
            if m and all(n is not None for n in nums):
                for col, num in zip(columns, nums):
                    r.put(col, {m[0]: (float(num or 0), m[1])})
                continue
        if one_column and len(cells) == 2:          # the one-size column ends at a row that is not its measure
            columns, one_column = None, False
        # a row-layout header: two or more measure names ("사이즈 | 어깨너비 | 가슴둘레 | 총길이"; "총장 / 어깨너비"
        # with no size cell, 13722416544); a second header line of as many cells straight after (Korean then
        # English) is the same columns: merged
        if sum(1 for m in measures_of if m) >= 2 and not first and not any(re.search(r"\d", c) for c in cells[1:]):
            new_has_size = measures_of[0] is None
            if last_was_header and header and len(header) == len(measures_of) and header_has_size == new_has_size:
                merged: list[tuple[str, str | None] | None] = []
                for x, y in zip(header, measures_of):
                    merged.append((x[0], x[1] or y[1]) if x and y and x[0] == y[0] else x or y)
                header = merged
            else:
                header, header_has_size, header_rows = measures_of, new_has_size, 0
                r.table += 1
            columns, one_column, last_was_header = None, False, True
            continue
        last_was_header = False
        # a row: a size label first, then numbers (under the header) or name+number pairs
        lead = re.match(r"^\s*([A-Za-z0-9()\[\].~\-반]+(?:\s*\([^)]*\))?)\s*[-:]?\s*(.*)$", cells[0])
        label = parse_label(cells[0]) if len(cells) > 1 else None
        rest = cells[1:]
        if label is None and lead:
            label = parse_label(lead.group(1))
            rest = ([lead.group(2)] if lead.group(2) else []) + cells[1:]
        if label is None:
            # "총장59 어깨53 가슴54 소매54", "어깨: 40", "가슴 / 46": a FREE product's measurements, no size written;
            # read when no table is open (a header nothing was read under is a diagram's labels) or into the one
            # size column ("사이즈 | FREE" then "총장59/어깨54/...")
            if (columns is None or one_column) and (header is None or header_rows == 0):
                loose: dict[str, tuple[float, str | None]] = {}
                if len(cells) == 2 and (m := r.measure(cells[0])) and (one_value := _value(cells[1])) is not None:
                    loose[m[0]] = (one_value, m[1])
                for word, number in _PAIR_RE.findall(_SPACED_HANGUL_RE.sub("", text)):
                    if (m := r.measure(word)) and m[0] not in loose:
                        loose[m[0]] = (float(number), m[1])
                if loose and one_column and columns:
                    r.put(columns[0], loose)
                elif loose:
                    _one(r, loose, section)
            continue
        name = re.sub(r"[-:]+$", "", cells[0] if parse_label(cells[0]) else lead.group(1) if lead else cells[0])
        nums = [_value(v) for v in rest]
        if header and all(n is not None for n in nums):
            cols = header[1:] if header_has_size else header
            if len(rest) == len(cols):
                if r.put(name, {m[0]: (float(n or 0), m[1]) for m, n in zip(cols, nums) if m}):
                    chart.labels[name] = label
                    header_rows += 1
                continue
        pairs: dict[str, tuple[float, str | None]] = {}
        for piece in rest:
            for word, number in _PAIR_RE.findall(_SPACED_HANGUL_RE.sub("", piece)):
                if (m := r.measure(word)) and m[0] not in pairs:
                    pairs[m[0]] = (float(number), m[1])
        if r.put(name, pairs):
            chart.labels[name] = label
    _drop_breaks(r)
    for k, v in r.hints.items():                    # a note's kind only where the table said none, and only when
        seen_cm = [row[k] for row in chart.rows.values() if k in row]         # every value fits it (spec F8:
        known = r.by_name.get(k)                                                # a "flat" note over a 92 cm chest
        lo, hi = (known.flat if v == "flat" else known.round_) if known else (0.0, 0.0)   # is no flat chest)
        if chart.kinds.get(k) is None and seen_cm and all(lo <= x <= hi for x in seen_cm):
            chart.kinds[k] = v
    return chart


def _breaks(values: list[float]) -> set[int]:
    """The place in one table's run of a measure (its sizes in the table's order) whose value breaks the run: the
    others rise (or fall) all the way, and this one, a middle value of a run of 4 or more, lies outside its two
    neighbours by more than their span, 3 cm at least. An end value is never dropped: a bigger last step is real
    grading as often as a misread (88, XL, 2XL; the review of 2026-11-20).
    "어깨너비 / 35.5 / 57 / 38.5 / 40.5" (13338110183, OCR): 57 breaks it. Two places breaking: none is told."""
    out: set[int] = set()
    n = len(values)
    for i, v in enumerate(values):
        rest = values[:i] + values[i + 1:]
        steps = [b - a for a, b in zip(rest, rest[1:])]
        if n < 4 or not (all(d >= 0 for d in steps) or all(d <= 0 for d in steps)):
            continue
        if not 0 < i < n - 1:
            continue
        lo, hi = sorted((values[i - 1], values[i + 1]))
        span = max(hi - lo, _BREAK_MIN)
        if v < lo - span or v > hi + span:
            out.add(i)
    return out if len(out) == 1 else set()


def _drop_breaks(r: _Reader) -> None:
    """A value that breaks its table's run (_breaks) leaves that row: never shown (2026-11-20 lens review)."""
    runs: dict[tuple[int, str], list[str]] = {}
    for (label, k), table in r.origin.items():
        if not label.startswith(ONE) and k in r.chart.rows.get(label, {}):
            runs.setdefault((table, k), []).append(label)
    for (_, k), labels in runs.items():
        for i in _breaks([r.chart.rows[n][k] for n in labels]):
            del r.chart.rows[labels[i]][k]


def _one(r: _Reader, loose: dict[str, tuple[float, str | None]], section: str | None) -> None:
    """A one-size line: into ONE, or ONE#<section> when its type's section is known; a second block that disagrees
    with ONE and has no section is a conflict (the first kept)."""
    chart = r.chart
    key = f"{ONE}#{section}" if section else ONE
    have = chart.rows.get(key)
    if have and any(k in have and have[k] != v for k, (v, _) in loose.items()):
        chart.conflicts.append(" ".join(f"{k} {v:g}" for k, (v, _) in loose.items()))
        return
    if r.put(key, loose):
        chart.labels[key] = Label(free=True)
        if section:
            chart.sections[key] = section


def measure_names(measures: str = "tops") -> list[str]:
    return [m.name for m in MEASURE_SETS[measures]]


def describe_sets() -> dict[str, Any]:
    """The measure sets, for the docs and a test: {set: [field ...]}."""
    return {k: [m.name for m in v] for k, v in MEASURE_SETS.items()}
