"""Product page HTML -> plain data. Pure functions over a small stdlib DOM
(html.parser), no I/O: the page is read elsewhere (ext_product.py, the
owner's Chrome through the adapter), the description HTML comes from the
store backend (contents/<origin>/PC renderContent).

Two jobs:

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
  * description_text: the readable text of a description by walking its text
    nodes; block elements end a line, inline ones do not split words. Images,
    video controls (.pzp), embedded product cards (.se-material), buttons and
    hidden nodes are skipped; structural labels (공지사항 / Notice, 관련 태그,
    상품정보 펼쳐보기) are dropped.
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
_SKIP_CLASSES = {"pzp", "se-material"}
_WS_RE = re.compile(r"\s+")
_ZERO_WIDTH_RE = re.compile("[​﻿]")
_RELATED_TAGS_RE = re.compile(r"^(?:관련\s*태그|Related tags)(?:\s*#[^#\s]+)*$", re.I)
_HASHTAGS_RE = re.compile(r"^(?:\s*#[^#\s]+)+$")
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


# ---- description text -------------------------------------------------------------------

def description_text(html_text):
    """Description HTML -> its text, one line per block, or None when empty."""
    if not html_text:
        return None
    parts = []

    def walk(node):
        for c in node.children:
            if isinstance(c, str):
                parts.append(_WS_RE.sub(" ", c))
            elif not _skipped(c):
                block = c.tag in _BLOCK
                if block:
                    parts.append("\n")
                walk(c)
                if block:
                    parts.append("\n")
    walk(parse_html(html_text))
    lines, related = [], False
    for line in "".join(parts).split("\n"):
        line = _WS_RE.sub(" ", _ZERO_WIDTH_RE.sub("", line)).strip()
        if not line:
            continue
        if _RELATED_TAGS_RE.match(line):
            related = True
            continue
        if related and _HASHTAGS_RE.match(line):
            continue
        related = False
        if not _LABEL_LINE_RE.match(line):
            lines.append(line)
    return "\n".join(lines) or None
