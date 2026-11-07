"""Product page HTML -> plain data. Pure functions over a small stdlib DOM
(html.parser), no I/O: the page is read elsewhere (ext_product.py, the
owner's Chrome through the adapter), the description HTML comes from the
store backend (contents/<origin>/PC renderContent).

Three jobs:

  * spec_rows: the "상품정보" list of a smartstore product page, label -> value
    (상품번호, 제조사, 브랜드, 모델명, 원산지 and the seller's category attributes
    such as 종류, 성별, 총클럽개수). Observed 2026-11-01 on
    smartstore.naver.com/scarabee/products/13021362937: the list is server
    rendered as <strong>상품정보</strong> + <ul><li><div>label</div><div>value</div></li>,
    with hashed class names, so it is found by its heading text and its shape,
    never by class. The list starts collapsed after 9 rows behind a
    "상품정보 펼쳐보기" button (aria-expanded="false"); 15 rows after the click.
    The page's own __PRELOADED_STATE__ carries no product data at that point
    (product.* all null: the page loads it later), so the rendered list is the source.
  * text_fields: the purchase box's text fields (a text the buyer types), with
    what only the page shows: the label, required, the length limit.
  * description_text: the readable text of a description by walking its text
    nodes; block elements end a line, inline ones do not split words, and one
    empty line separates two top-level SmartEditor ONE components (.se-component),
    so a later stage can end a seller's notice block where its component ends.
    A table is one line per row, its cells joined by " | " (a per-club spec
    table keeps its columns; measures.table_rows reads the HTML, not this text).
    Images, video controls (.pzp), buttons, hidden nodes and the SmartEditor
    cards that are not the product's own text are skipped: .se-material (a
    shopping card), .se-oglink (a link card: another product of the store, a
    TalkTalk chat), .se-placesMap (the store's map and address), .se-blind
    (screen-reader text). Checked 2026-11-06 on 86 saved products: Naver's own
    detailContentText leaves out exactly these three cards (12 of 12 with text).
    In-page jump links (<a href="#top">, "▲ 이동(상단)") are skipped too: they do
    nothing off Naver. Structural labels (공지사항 / Notice, 관련 태그,
    상품정보 펼쳐보기) and lines made only of hashtags are dropped.
"""
import re
from html.parser import HTMLParser

SPEC_HEADING = "상품정보"
MAX_SPEC_ROWS = 100

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_BLOCK = {"address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption", "figure", "footer",
          "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
          "td", "th", "tr", "ul"}
_SKIP_TAGS = {"img", "picture", "svg", "script", "style", "iframe", "video", "button", "noscript", "template"}
# SmartEditor ONE component classes seen 2026-11-06 (40 golf sets, 86 saved products): se-material (shopping card,
# se-l-material_basic), se-oglink (link card, se-l-large_image: another product of the store, talk.naver.com),
# se-placesMap (map image + store name + address), se-blind (hidden "네이버페이" inside se-material-npay).
_SKIP_CLASSES = {"pzp", "se-material", "se-oglink", "se-placesMap", "se-blind"}
_COMPONENT_CLASS = "se-component"
_WS_RE = re.compile(r"\s+")
_ZERO_WIDTH_RE = re.compile("[​﻿]")
_RELATED_TAGS_RE = re.compile(r"^(?:관련\s*태그|Related tags)(?:\s*#[^#\s]+)*$", re.I)
_HASHTAGS_RE = re.compile(r"^(?:\s*#[^#\s]+)+$")
# a seller's tag line with no "관련 태그" label (10639350746, 2026-11-06: "#골린이#남성좌타골프채#풀세트#스탠드백"):
# 2+ tags, each starting with a letter, one of them Hangul. Club numbers (#PW, #5-#9, "#7 (34인치)") stay.
_TAG_LINE_RE = re.compile(r"^(?:#[가-힣A-Za-z][^#\s]*\s*){2,}$")
_HANGUL_RE = re.compile(r"[가-힣]")
_LABEL_LINE_RE = re.compile(r"^(?:공지사항|Notice|(?:상품정보|상세정보)\s*(?:펼쳐보기|접기))$", re.I)
_MORE_RE = re.compile(r"(?:상품정보|상세정보)\s*펼쳐보기")


# ---- a small DOM -----------------------------------------------------------------------

class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, attrs or {}, [], parent

    def elements(self):
        return [c for c in self.children if isinstance(c, _Node)]

    def descendants(self):
        stack = list(reversed(self.elements()))
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.elements()))


class _Builder(HTMLParser):
    """Lenient tree builder: an end tag closes up to its open match, a stray one is ignored."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _Node("#root")

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(_Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(html_text):
    builder = _Builder()
    try:
        builder.feed(html_text or "")
        builder.close()
    except Exception:                       # malformed markup: keep what was built
        pass
    return builder.root


def _skipped(node):
    if node.tag in _SKIP_TAGS or "hidden" in node.attrs:
        return True
    if node.attrs.get("role") == "button" or node.attrs.get("aria-hidden") == "true":
        return True
    return bool(_SKIP_CLASSES & set(node.attrs.get("class", "").split()))


def _flat(node):
    """Visible text of a node on one line (skipped subtrees left out)."""
    parts = []

    def walk(n):
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif not _skipped(c):
                walk(c)
    walk(node)
    return _WS_RE.sub(" ", _ZERO_WIDTH_RE.sub("", "".join(parts))).strip()


# ---- 상품정보 rows ------------------------------------------------------------------------

def spec_rows(page_html):
    """The product page's 상품정보 list -> [{label, value}] (rows with an empty
    label or value left out; at most MAX_SPEC_ROWS). [] when there is none."""
    root = parse_html(page_html)
    for heading in root.descendants():
        if heading.tag not in ("strong", "h2", "h3", "h4") or _flat(heading) != SPEC_HEADING:
            continue
        box = heading.parent
        while box is not None and not any(d.tag == "ul" for d in box.descendants()):
            box = box.parent
        if box is None:
            continue
        ul = next(d for d in box.descendants() if d.tag == "ul")
        rows = []
        for li in ul.elements():
            cells = [c for c in li.elements() if c.tag == "div"] if li.tag == "li" else []
            if len(cells) < 2:
                continue
            label, value = _flat(cells[0]), _flat(cells[1])   # the 상품번호 copy button is skipped
            if label and value:
                rows.append({"label": label, "value": value})
        if rows:
            return rows[:MAX_SPEC_ROWS]
    return []


def specs_collapsed(page_html):
    """True while the page still shows its "상품정보 펼쳐보기" button closed."""
    for node in parse_html(page_html).descendants():
        if node.tag == "button" and node.attrs.get("aria-expanded") == "false":
            text = _WS_RE.sub(" ", "".join(c for c in node.children if isinstance(c, str)))
            if _MORE_RE.search(text):
                return True
    return False


# ---- text fields (a text the buyer types) -----------------------------------------------

_REQUIRED_RE = re.compile(r"\(\s*필수\s*\)")
_DIGITS_RE = re.compile(r"^\d+$")


def _length(value):
    return int(value) if value is not None and _DIGITS_RE.match(value) else None


def text_fields(page_html):
    """The product page's text fields (CUSTOM options: a name on a tag, an engraving) -> [{id, label, required,
    placeholder, hint, min_length, max_length, pattern}], one per field id in page order. [] when there is none.

    Observed 2026-11-02 (PRGR Sweep, Majesty Royal, XXIO14 golf sets on smartstore): each field is
    <label for=ID>네임스티커 성함 (필수)</label> + <input type="text" id=ID maxlength="20" data-tag="textOption"
    placeholder="입력해주세요">, ID the textOptions id of the product answer. The purchase box is rendered twice (the
    page and the floating bar), so a field repeats. "(필수)" in the label marks a required field; `required`,
    `aria-required`, `minlength`, `pattern` and an `aria-describedby` hint are read too (the naver-harvester
    reads them), not seen on a page yet."""
    root = parse_html(page_html)
    nodes = list(root.descendants())
    labels, by_id = {}, {}
    for n in nodes:
        if n.tag == "label" and n.attrs.get("for"):
            labels.setdefault(n.attrs["for"], _flat(n))
        if n.attrs.get("id"):
            by_id.setdefault(n.attrs["id"], n)
    fields, seen = [], set()
    for n in nodes:
        a = n.attrs
        field_id = a.get("id")
        if n.tag != "input" or a.get("data-tag") != "textOption" or not field_id or field_id in seen:
            continue
        seen.add(field_id)
        label = labels.get(field_id) or None
        hint = " ".join(t for t in (_flat(by_id[h]) for h in a.get("aria-describedby", "").split() if h in by_id)
                        if t) or None
        fields.append({
            "id": field_id,
            "label": label,
            "required": "required" in a or a.get("aria-required") == "true" or bool(_REQUIRED_RE.search(label or "")),
            "placeholder": _WS_RE.sub(" ", a.get("placeholder", "")).strip() or None,
            "hint": hint,
            "min_length": _length(a.get("minlength")),
            "max_length": _length(a.get("maxlength")),
            "pattern": a.get("pattern") or None,
        })
    return fields


# ---- delivery promise (the purchase box) --------------------------------------------------

# Seen 2026-11-05 on 40 golf sets, each as its own text node of the rendered page: "오늘출발 16:00 마감" (14),
# "평균 2일 이내 도착 확률 92%" (15), "지금 결제 시 11.6.(금) 발송 예정" (14), "해외직배송" (9: exactly the sets whose
# page answer says overseasShipping). "관부가세 별도" also shows on domestic sets, so it is not read.
# Seen 2026-11-06 on 13 of 40 (todayDelivery true): "오늘출발" alone, then "14:00 까지 결제 시 오늘 바로 발송" and
# either "11.11.(수) 도착 확률 98%" (a dated arrival) or the "평균 N일" line.
# Seen 2026-11-06 after KST midnight / on a weekend (10816781893, 13302492097, 6540695739, 10816904599, 13553116678):
# "오늘출발 휴무", then "지금 결제 시 11.9.(월) 발송 예정": no dispatch today although the page answer still says
# todayDelivery with its thisDayDispatchBasisTime. Seen 2026-11-02 / 11-06 on "네이버 배송" and "네이버 내일배송" boxes
# (13369469193, 8811427777, 10829550821, 12945108653, 13462928946): the arrival date alone, a whole line with no
# probability, "11.11.(수) 도착" or "내일 11.4.(수) 도착" (the option panel's 배송지 line repeats it).
_TODAY_RE = re.compile(r"오늘출발\s*(\d{1,2}:\d{2})\s*마감|(\d{1,2}:\d{2})\s*까지\s*결제\s*시\s*오늘")
_ARRIVE_RE = re.compile(r"평균\s*(\d+)\s*일\s*이내\s*도착\s*확률\s*(\d+)\s*%")
_ARRIVE_ON_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\([^)]{1,2}\))\s*도착\s*확률\s*(\d+)\s*%")
_SHIP_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.\([^)]{1,2}\))\s*발송\s*예정")
_TODAY_OFF_RE = re.compile(r"^오늘출발\s*휴무$")
_ARRIVE_DATE_RE = re.compile(r"^(?:내일\s*)?(\d{1,2}\.\d{1,2}\.\([^)]{1,2}\))\s*도착$")


def delivery_promise(page_html):
    """-> {today_cutoff, today_off, arrival_days, arrival_date_text, arrival_probability, ship_date_text,
    overseas_text}, None where not shown; today_off and overseas_text are booleans."""
    lines = [_WS_RE.sub(" ", t).strip() for t in _text_nodes(parse_html(page_html))]
    def first(rx):
        return next((m for m in (rx.search(t) for t in lines) if m), None)
    today, arrive, arrive_on, ship = first(_TODAY_RE), first(_ARRIVE_RE), first(_ARRIVE_ON_RE), first(_SHIP_RE)
    arrive_date = arrive_on or first(_ARRIVE_DATE_RE)
    return {"today_cutoff": (today.group(1) or today.group(2)) if today else None,
            "today_off": first(_TODAY_OFF_RE) is not None,
            "arrival_days": int(arrive.group(1)) if arrive else None,
            "arrival_date_text": arrive_date.group(1) if arrive_date else None,
            "arrival_probability": int(arrive.group(2)) if arrive else int(arrive_on.group(2)) if arrive_on else None,
            "ship_date_text": ship.group(1) if ship else None,
            "overseas_text": any(t == "해외직배송" for t in lines)}


def _text_nodes(node):
    out = []

    def walk(n):
        for c in n.children:
            if isinstance(c, str):
                if c.strip():
                    out.append(c)
            elif c.tag not in ("script", "style", "noscript", "template"):
                walk(c)
    walk(node)
    return out


# ---- description text -------------------------------------------------------------------

_BOUNDARY = "\x00"          # a component boundary in the joined parts; becomes one empty line


def _jump_link(node):
    """<a href="#top"> / "#product1": an in-page jump (12696567111, 2026-11-06). A bare "#" is SmartEditor's image
    link, which wraps an image or its caption, and stays."""
    return node.tag == "a" and node.attrs.get("href", "").startswith("#") and len(node.attrs.get("href", "")) > 1


def _tag_line(line):
    return bool(_TAG_LINE_RE.match(line)) and bool(_HANGUL_RE.search(line))


def _cell_text(cell):
    """A table cell on one line: its blocks (paragraphs, a nested table's cells) joined by "; "."""
    parts = []

    def walk(n):
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif not _skipped(c) and not _jump_link(c):
                block = c.tag in _BLOCK
                parts.append("\n" if block else "")
                walk(c)
                parts.append("\n" if block else "")
    walk(cell)
    lines = (_WS_RE.sub(" ", _ZERO_WIDTH_RE.sub("", x)).strip() for x in "".join(parts).split("\n"))
    return "; ".join(x for x in lines if x)


def _table_lines(table):
    """A table -> one line per row, cells joined by " | " (the header row too; an empty cell keeps its column, an
    empty row goes). Seen 2026-11-07 on SmartEditor se-table (8958060680, 13728190518, 7166885441, 13657325637):
    per-club spec tables of 4-11 columns, one cell per line lost which number is the loft and which the lie.
    The rows of a nested table are cells of the outer one (_cell_text)."""
    rows, stack = [], list(reversed(table.elements()))
    while stack:
        node = stack.pop()
        if node.tag == "tr":
            cells = [_cell_text(c) for c in node.elements() if c.tag in ("td", "th") and not _skipped(c)]
            if any(cells):
                rows.append(" | ".join(cells))
        elif node.tag != "table" and not _skipped(node):
            stack.extend(reversed(node.elements()))
    return rows


def description_text(html_text):
    """Description HTML -> its text, one line per block (a table: one line per row), an empty line between
    SmartEditor components, or None when empty."""
    if not html_text:
        return None
    parts = []

    def walk(node, in_component):
        for c in node.children:
            if isinstance(c, str):
                parts.append(_WS_RE.sub(" ", c))
            elif c.tag == "table" and not _skipped(c):
                parts.append("\n" + "".join(row + "\n" for row in _table_lines(c)))
            elif not _skipped(c) and not _jump_link(c):
                component = not in_component and _COMPONENT_CLASS in c.attrs.get("class", "").split()
                block = c.tag in _BLOCK
                if component:
                    parts.append(f"\n{_BOUNDARY}\n")
                elif block:
                    parts.append("\n")
                walk(c, in_component or component)
                if block:
                    parts.append("\n")
    walk(parse_html(html_text), False)
    lines, related = [], False
    for line in "".join(parts).split("\n"):
        if line == _BOUNDARY:
            if lines and lines[-1]:
                lines.append("")
            continue
        line = _WS_RE.sub(" ", _ZERO_WIDTH_RE.sub("", line)).strip()
        if not line:
            continue
        if _RELATED_TAGS_RE.match(line):
            related = True
            continue
        if related and _HASHTAGS_RE.match(line):
            continue
        related = False
        if not _LABEL_LINE_RE.match(line) and not _tag_line(line):
            lines.append(line)
    return "\n".join(lines).strip("\n") or None
