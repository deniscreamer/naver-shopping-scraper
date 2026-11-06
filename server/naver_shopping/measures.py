"""Weight and size candidates of a product, from what the seller wrote. Pure: text in, candidates out, no I/O.

Collection only (the owner's rules, 2026-11-05, after the naver-harvester's weight / dimension evidence): every
value the text states is kept as a candidate with its exact quote, where it was found, what it measures and which
variant it belongs to. Nothing is chosen here, no average is filled in, no confidence level is computed (that is
scripts/package_measures.py with the operator's category table). No OCR: text only. The 상품정보 rows and `facts`
are not changed.

Sources, in this order (`source`):
  specs              the page's 상품정보 rows (label -> value)
  notice             the legal notice (상품정보제공고시) items and terms
  description        the description text, one line per block
  json_ld            the page's JSON-LD Product (weight, netWeight, grossWeight, shippingWeight,
                     additionalProperty), only when its productID or mpn is this product's id
  description_table  label / value pairs in the description HTML: li > strong + div, dt + dd, table rows (a row of
                     th cells is the header of the rows under it; so is a first row of 3+ td cells that are names,
                     "번호 | 드라이버 | 5i", for the weight / size rows under it, labelled "<row label> <column>")
The same quote with the same value is kept once, from the first source.

A line counts for weight only with a weight label (무게, 중량, weight, mass), or a weight unit in a size line
("크기: 7번 기준 93cm / 7번 기준 328g", "Package Dimensions: ...; 2.27 kg"), and for size only with a size label
(크기, 치수, 사이즈, 길이, ...), or a packed word and a size triple with a unit ("포장 박스 : 128 X 32 X 28 cm").
Per candidate:
  value    grams or millimetres, {min, max} (a range "9~10kg" gives both)
  kind     weight: net | packed | component | unknown; size: packed | component | product | unknown
  scope    weight: unit | set | unknown
  count    weight: the pieces of a multiplier ("45g x 12개": 12), else null
  flags    weight: alternate_unit (the same weight in a second unit, merged), lb_oz (lb and oz added up),
           multiplied (value x count, the second candidate of a multiplier), part_scale (a set's plain weight row
           under 1 kg: one part's), bag_excluded, bound_by_count_rank (see binding); size: axis_order_unresolved,
           not_confirmed_packed, two_sides
  binding  {scope: product | variants | context, variant_ids}: one variant or none -> product; several -> variants
           only when the line names option values of exactly one composition (variants that differ only in a
           colour / design group count as one); otherwise context
The words that decide kind and scope are the label and the value's segment holding the number (between '/', ',',
';', '|', ' 및 ' and the neighbouring numbers, plus a bracket right after it: "약 1.2kg(포장 포함)").

Sets (2026-11-06, research/rnd on the 40 golf sets and 86 saved pages): `is_set` comes from the name or category
(세트, set, a count: 6아이언, 12pcs, 3종, 11개 구성). In a set a part's weight is kind component: a part word or club
code (드라이버, 캐디백, 1W, 5i, #7, PW, 7번), a part named before the line's ':' ("#6 아이언: ... 418g"), a club
heading line above it in the description ("1. 드라이버 (1W)"), a reference club ("7번 기준", any "...기준" in a set).
A bare 총중량 is a club's total, not the set's. A plain weight row (중량, 무게, 제품 무게, Item Weight) in a structured
source (specs, notice, description_table, json_ld) is the product as sold: scope set from 1 kg, else component
(part_scale). Two or more such weights on one line are bound to variants by their own option names or club counts,
else heaviest to the most clubs (bound_by_count_rank) when the variants carry exactly that many counts.

A line whose words say two kinds at once, a unit in the label that differs from the value's, one line naming two
compositions, a value list that no variant split explains, a weight beside the 본품's own (another part), a decimal
comma in grams ("45,50g"), 근 (600 g or 375 g), a size range or a list of sizes goes to `review` (with a reason)
instead. A pointer such as "상세페이지 참조" goes to `references` (description_reference /
measurement_field_reference): no number. Loads and capacities (최대 하중, 사용자 최대 무게) are not weights.
"""
import json
import re
import unicodedata

from naver_shopping import parsers, pdp

# ---- words -------------------------------------------------------------------------------

WEIGHT_LABEL = re.compile(r"무게|중량|weight|mass|(?<![a-z])wt(?![a-z])", re.I)
SIZE_LABEL = re.compile(r"크기|치수|사이즈|길이|높이|가로|세로|폭(?![가-힣])|넓이|깊이|지름|직경|length|width|height|depth|diameter|"
                        r"dimensions?|size", re.I)
WEIGHT_SKIP = re.compile(r"스윙\s*웨이트|swing\s*weight|압축\s*강도|모델명|model\s*(?:name|number|no)", re.I)
# A load or capacity is not the product's weight ("사용자 최대 무게 120kg", 2026-11-06 probe); checked on the label
# and on the number's own segment only, so "12kg / 최대 하중 120kg" keeps 12 kg.
LOAD = re.compile(r"하중|적재|체중|(?:허용|최대)\s*(?:사용\s*)?(?:무게|중량|용량)|사용자\s*(?:최대\s*)?(?:무게|중량)|"
                  r"(?<![a-z])load(?![a-z])|capacity|max(?:imum)?\s*(?:user\s*)?weight|weight\s*limit", re.I)
SIZE_SKIP = re.compile(r"신발\s*사이즈|가슴|허리|엉덩이|둘레|헤드\s*체적|volume|이미지|resolution|"
                       r"무게\s*중심|비거리|탄도|스핀", re.I)     # golf talk: centre of gravity, carry, launch, spin
REFERENCE = re.compile(r"(?:상세\s*페이지|상품\s*상세|상세\s*설명|상품\s*페이지)\s*참[조고]|(?:크기|중량)\s*항목\s*참조")
FIELD_REFERENCE = re.compile(r"(?:크기|중량)\s*항목\s*참조")

# One club the figures were measured on: "7번 기준 36인치 , 332g", "#7 기준", "7번 R기준", "7i 기준" (golfzonmarket-style
# iron set notices, seen 2026-11-06 on 6712059632, 11236752052, 9747808561). Not "1개 기준" (per piece) or "270mm 기준".
REF_CLUB = re.compile(r"(?:#\s*\d{1,2}|(?<!\d)\d{1,2}\s*(?:번|i(?![a-z])))\s*(?:아이언|우드|유틸)?\s*(?:[A-Z]{1,2}\s*)?기준|"
                      r"(?:드라이버|아이언|퍼터|우드)\s*기준", re.I)
WEIGHT_KINDS = {
    "net": re.compile(r"순\s*(?:중량|무게)|net\s*(?:weight|wt)|본품|본체|제품\s*(?:자체\s*)?(?:무게|중량)", re.I),
    "packed": re.compile(r"포장\s*(?:포함|후|시|무게|중량|박스)|박스\s*(?:포함|무게|중량)|(?:배송|택배|발송)\s*(?:무게|중량)|"
                         r"패키지\s*(?:무게|중량)|gross\s*weight|shipping\s*weight|packed\s*weight|package\s*weight|"
                         r"package\s*dimensions", re.I),    # "Package Weight 7.71 Kilograms" (2026-11-05)
    "component": re.compile(r"샤프트|shaft|그립|grip|헤드\s*(?:중량|무게)|head\s*weight|캐디\s*백\s*(?:중량|무게)|"
                            r"골프\s*백\s*(?:중량|무게)|클럽\s*(?:무게|중량)|club\s*weight|" + REF_CLUB.pattern, re.I),
}
NOT_PACKED = re.compile(r"(?:박스|포장)\s*(?:박스\s*)?(?:미\s*포함|제외|별도)")     # "6kg (박스 미포함)"
# A part of a club set: its weight is not the set's. Club codes (1W, 5H, 5i, 5UT, #7, PW, FW, PT, 7번) and the bag.
SET_PARTS = re.compile(r"드라이버|아이언|우드|유틸|하이브리드|퍼터|웨지|헤드|driver|iron|wood|hybrid|putter|wedge|head|"
                       r"캐디\s*백|골프\s*백|스탠드\s*백|보스턴\s*백|헤드\s*커버|(?<![a-z])bag(?![a-z])|"
                       r"(?<![A-Za-z0-9])(?:[1-9]\s?[WH]|\d{1,2}\s?(?:UT|i)|#\s*\d{1,2}|[PAGS]W|UT|FW|PT)(?![A-Za-z])|"
                       r"(?<!\d)\d{1,2}\s*번", re.I)
NOT_A_PART = re.compile(r"세트|포함|제외|별도|(?<![a-z])set(?![a-z])", re.I)      # "캐디백 포함 9kg" is the set
BAG_EXCLUDED = re.compile(r"(?:골프|캐디|스탠드)\s*백\s*(?:제외|미\s*포함|별도)")
SCOPES = {
    "unit": re.compile(r"개당|낱개|1\s*개당|per\s*(?:piece|unit|item)", re.I),
    # A bare 총중량 / 전체 무게 is not here: in a club spec it is one club's total (13777887875 "총중량: Flex S 약
    # 312g", 2026-11-06). The set's total is "세트 ..." or a total in kg / lb (SET_TOTAL).
    "set": re.compile(r"(?:풀\s*)?세트\s*(?:전체|총)?\s*(?:무게|중량)|세트\s*(?:전체|총)|(?:complete|total)\s*set|set\s*weight",
                      re.I),
}
SET_TOTAL = re.compile(r"(?:전체|총)\s*(?:무게|중량)\s*[:：]?\s*(?:약\s*)?$")
UNIT_BEFORE = re.compile(r"(?<!\d)1\s*(?:개|구|알|ea)\s*(?:당|기준)?\s*(?:약\s*)?$", re.I)           # "1개 약 45g"
UNIT_AFTER = re.compile(r"\s*(?:/\s*(?:개|ea|pcs?|piece|구|알)(?![가-힣a-z])|\(\s*1\s*(?:개|ea|pcs?|구|알)\s*\))", re.I)
MULTIPLIER = re.compile(r"\s*[x×*]\s*(?P<count>\d{1,4})\s*(?:개입|개|팩|봉|입|구|ea|pcs?)(?![가-힣a-z])", re.I)
TOLERANCE = re.compile(r"(?:±|\+\s*/?\s*-)\s*$|오차")
PLAIN_WEIGHT_LABEL = re.compile(r"(?:(?:크기|치수|규격)\s*[,/·및]\s*)?(?:(?:제품|상품|본품|item|product)\s*)?(?:총\s*)?"
                                r"(?:무게|중량|weight)(?:\s*[,/·및]\s*(?:크기|치수|규격))?", re.I)
STRUCTURED = ("specs", "notice", "description_table", "json_ld")
SET_NAME = re.compile(r"세트|(?<![a-z])sets?(?![a-z])|"                       # not "Offset", "Headset"
                      r"(?<![#\d.])\d{1,2}아이언(?!\s*(?:기준|단품))|"           # 6아이언 = six irons; 7번 아이언 = one
                      r"(?<![\d.])(?:[2-9]|1\d|20)\s*(?:pcs?|피스|pieces?)(?![a-z])|"
                      r"(?<![\d.])(?:[2-9]|1\d|20)\s*종(?![가-힣])|(?<![\d.])(?:[2-9]|1\d|20)\s*종\s*(?:세트|구성)|"
                      r"(?<![\d.])\d{1,2}\s*개\s*(?:구성|클럽)", re.I)
APPROX = re.compile(r"약|대략|approx|about|around", re.I)
SIZE_KINDS = {
    "packed": re.compile(r"패키지|포장|박스|package|packed|carton|box", re.I),
    "component": re.compile(r"샤프트|헤드|그립", re.I),
    "product": re.compile(r"제품|본체|본품|product", re.I),
    "club": re.compile(r"클럽|club", re.I),                 # the product for a single club, a part in a set
}
UNFOLDED = re.compile(r"펼친|전개|unfolded", re.I)
FOLDED = re.compile(r"접은|접이|folded", re.I)
COSMETIC_GROUP = re.compile(r"색상|컬러|칼라|color|colour|디자인|design", re.I)
SHOE_NAME = re.compile(r"골프화|운동화|슈즈|신발|스파이크|shoes?", re.I)
HEADING_END = re.compile(r"세트|구성|(?<![a-z])set(?![a-z])|총|포함|스펙|spec", re.I)

# ---- numbers and units -------------------------------------------------------------------

# "1,5kg" is 1.5 kg (a decimal comma, imported listings); "1,500g" stays 1500 g; "1, 5kg" is a list.
NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\d,.])\d{1,2},\d{1,2}(?![\d,])|\d+(?:\.\d+)?)"
DECIMAL_COMMA = re.compile(r"\d{1,2},\d{1,2}")
DASH = r"[~～–—\-]"
GRAMS = [(r"kilograms?|kilos?|킬로그램|키로그램|kgs?|㎏|킬로|키로", 1000.0), (r"milligrams?|mg|㎎", 0.001),
         (r"grams?|그램|g", 1.0), (r"pounds?|lbs?\.?|파운드", 453.59237), (r"ounces?|oz|온스", 28.349523125)]
MM = [(r"밀리미터|mm|미리", 1.0), (r"센티미터|cm|센치|센티", 10.0), (r"인치|inch(?:es)?|in|\"", 25.4),
      (r"feet|foot|ft|피트", 304.8), (r"미터|m", 1000.0)]
IMPERIAL = (453.59237, 28.349523125)
_W_UNIT = "|".join(u for u, _ in GRAMS)
_S_UNIT = "|".join(u for u, _ in MM)
WEIGHT_RE = re.compile(rf"(?P<a>{NUM})(?:\s*(?P<ua>{_W_UNIT})(?![a-z]))?(?:\s*(?P<dash>{DASH})\s*(?P<b>{NUM}))?"
                       rf"\s*\(?\s*(?P<u>{_W_UNIT})(?![a-z])\s*\)?"
                       rf"(?P<area>\s*/\s*(?:m²|㎡|m2))?", re.I)
AMBIGUOUS_UNIT = re.compile(rf"{NUM}\s*근(?![가-힣])")      # 1근 = 600 g (meat) or 375 g (produce): a person decides
LABEL_UNIT = re.compile(rf"\(\s*(?:단위\s*[:：]?\s*)?(?P<u>{_W_UNIT}|{_S_UNIT})\s*\)|"
                        rf"단위\s*[:：]?\s*(?P<v>{_S_UNIT})(?![a-z])", re.I)
BARE_NUM = re.compile(rf"^\s*(?:약\s*)?(?P<a>{NUM})(?:\s*{DASH}\s*(?P<b>{NUM}))?\s*$")
AXIS = r"가로|세로|높이|길이|폭|깊이|두께|[LWHDT]"
AXES = {"가로": "width", "세로": "depth", "높이": "height", "길이": "length", "폭": "width", "깊이": "depth",
        "두께": "thickness", "l": "length", "w": "width", "h": "height", "d": "depth", "t": "thickness",
        "넓이": "width", "지름": "diameter", "직경": "diameter"}
# An axis may stand before the number (가로 120), in brackets after it (120(가로)) or right after the unit (48"L).
_PART = (rf"(?:(?P<p§>{AXIS})\s*[:=]?\s*)?(?P<n§>{NUM})\s*(?:\((?P<s§>{AXIS})\))?\s*(?P<u§>{_S_UNIT})?"
         rf"(?:\s?(?P<x§>[LWHD])(?![A-Za-z]))?")
TRIPLE_RE = re.compile(r"\s*[x×*X]\s*".join(_PART.replace("§", str(i)) for i in range(3))
                       + rf"(?:\s*\(\s*(?P<tail>(?:{AXIS})\s*[x×*X]\s*(?:{AXIS})\s*[x×*X]\s*(?:{AXIS}))\s*\))?"
                       + rf"(?:\s*\(\s*(?:단위\s*[:：]?\s*)?(?P<ut>{_S_UNIT})\s*\))?", re.I)
LABEL_AXES = re.compile(rf"({AXIS})\s*[x×*X]\s*({AXIS})\s*[x×*X]\s*({AXIS})", re.I)     # "L x W x H", "가로x세로x높이"
DOUBLE_RE = re.compile(rf"(?<![A-Za-z\d.])(?P<a>{NUM})\s*(?P<ua>{_S_UNIT})?\s*[x×*X]\s*(?P<b>{NUM})\s*(?P<u>{_S_UNIT})"
                       rf"(?![a-z])(?!\s*[x×*X]\s*\d)", re.I)          # "30x20cm", "9인치 x 46인치"; not "M8x20mm"
PAIR_RE = re.compile(rf"(?<![A-Za-z가-힣])(?P<a>{AXIS}|넓이|지름|직경)\s*[:=]?\s*(?P<n>{NUM})\s*(?P<u>{_S_UNIT})?(?![a-z])",
                     re.I)                      # 가로120 세로30 높이25cm: axis + number pairs
SINGLE_RE = re.compile(rf"(?P<n>{NUM})\s*(?P<u>{_S_UNIT})(?![a-z])", re.I)
# A size range needs a length unit: "(18-21호)" and iron numbers "(5~9, P)" are not sizes (2026-11-06).
SIZE_RANGE = re.compile(rf"{NUM}\s*(?P<u1>(?:{_S_UNIT})(?![a-z]))?\s*(?:{DASH}|부터)\s*{NUM}"
                        rf"\s*(?P<u2>(?:{_S_UNIT})(?![a-z]))?", re.I)
SEP = re.compile(r"\s*(?:[/;|]|,(?!\d)|(?<!\d),|\s및\s)\s*")
AFTER_BRACKET = re.compile(r"\s*\(([^()]{1,30})\)")


def _norm(text):
    return unicodedata.normalize("NFKC", text or "").replace("‎", "").replace("‏", "").strip()


def _num(text):
    if DECIMAL_COMMA.fullmatch(text):
        return float(text.replace(",", "."))
    return float(text.replace(",", ""))


def _factor(unit, table):
    for pattern, factor in table:
        if re.fullmatch(pattern, unit, re.I):
            return factor
    return None


def _span(lo, hi=None):
    hi = lo if hi is None else hi
    return {"min": round(min(lo, hi), 3), "max": round(max(lo, hi), 3)}


def _segment(value, start, end, lo=0, hi=None):
    """The words around value[start:end]: back to a separator (not before lo), on to a separator (not past hi),
    plus a bracket right after it."""
    hi = len(value) if hi is None else hi
    seps = [m.end() for m in SEP.finditer(value, lo, start)]
    begin = seps[-1] if seps else lo
    nxt = SEP.search(value, end, hi)
    finish = nxt.start() if nxt else hi
    bracket = AFTER_BRACKET.match(value, end)
    if bracket:
        finish = max(finish, bracket.end())
    return begin, finish


# ---- lines from the sources ---------------------------------------------------------------

def _lines(rows, notice, description, page_html, product_id):
    """(source, locator, label, value) in the source order."""
    for i, r in enumerate(rows or []):
        yield "specs", {"block": "상품정보", "row": i}, r.get("label") or "", r.get("value") or ""
    for part in ("items", "terms"):
        for i, r in enumerate((notice or {}).get(part) or []):
            yield "notice", {"block": part, "row": i}, r.get("label") or "", r.get("value") or ""
    for i, line in enumerate(((description or {}).get("text") or "").split("\n")):
        if line.strip():
            yield "description", {"block": "text", "row": i}, "", line
    for i, (label, value) in enumerate(json_ld_rows(page_html, product_id)):
        yield "json_ld", {"block": "Product", "row": i}, label, value
    for i, (label, value, cell) in enumerate(table_rows((description or {}).get("html"))):
        yield "description_table", {"block": "html", "row": i, "cell": cell}, label, value


def json_ld_rows(page_html, product_id):
    """(label, value) of the page's JSON-LD Product whose productID or mpn is `product_id`."""
    out = []
    for node in pdp.parse_html(page_html).descendants():
        if node.tag != "script" or "ld+json" not in node.attrs.get("type", ""):
            continue
        try:
            data = json.loads("".join(c for c in node.children if isinstance(c, str)))
        except ValueError:
            continue
        items = data if isinstance(data, list) else (data.get("@graph") or [data]) if isinstance(data, dict) else []
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "Product":
                continue
            if str(product_id) not in (str(item.get("productID") or ""), str(item.get("mpn") or "")):
                continue
            for key in ("weight", "netWeight", "grossWeight", "shippingWeight"):
                if item.get(key) is not None:
                    out.append((f"{key} weight", _ld_value(item[key])))
            for prop in item.get("additionalProperty") or []:
                if isinstance(prop, dict) and prop.get("name"):
                    out.append((str(prop["name"]), _ld_value(prop)))
    return out


LD_UNITS = {"KGM": "kg", "GRM": "g", "LBR": "lb", "ONZ": "oz", "MMT": "mm", "CMT": "cm", "MTR": "m", "INH": "inch"}


def _ld_value(v):
    if isinstance(v, dict):
        unit = v.get("unitText") or LD_UNITS.get(str(v.get("unitCode") or "").upper(), "")
        return f"{v.get('value', '')} {unit}".strip()
    return str(v)


def _is_column_header(texts):
    """A first td row "번호 | 드라이버 | #5 우드 | 5i ...": 3+ cells of names, no measure label, no number."""
    return len(texts) >= 3 and not WEIGHT_LABEL.search(texts[0]) and not SIZE_LABEL.search(texts[0]) \
        and not any(re.fullmatch(r"[\d.\s약~]+", t) for t in texts[1:]) \
        and not any(re.search(rf"\d\s*(?:{_W_UNIT}|{_S_UNIT})(?![a-z])", t, re.I) for t in texts)


def table_rows(html_text):
    """(label, value, cell) pairs of the description HTML: li > strong + div, dt + dd, table rows."""
    out = []
    root = pdp.parse_html(html_text)
    for node in root.descendants():
        kids = node.elements()
        if node.tag == "li":
            strong = next((k for k in kids if k.tag == "strong"), None)
            div = next((k for k in kids if k.tag == "div"), None)
            if strong and div:
                out.append((pdp._flat(strong), pdp._flat(div), "li"))
        elif node.tag == "dl":
            for dt, dd in zip(kids, kids[1:]):
                if dt.tag == "dt" and dd.tag == "dd":
                    out.append((pdp._flat(dt), pdp._flat(dd), "dt"))
        elif node.tag == "table":
            header, columns = None, None
            for n, tr in enumerate(d for d in node.descendants() if d.tag == "tr"):
                cells = [c for c in tr.elements() if c.tag in ("th", "td")]
                if cells and all(c.tag == "th" for c in cells):
                    header = [pdp._flat(c) for c in cells]
                    continue
                texts = [pdp._flat(c) for c in cells]
                if n == 0 and header is None and _is_column_header(texts):
                    columns = texts             # club spec tables (6774818843, 13049116377; seen 2026-11-06)
                    continue
                if columns:
                    if len(texts) == len(columns) and (WEIGHT_LABEL.search(texts[0]) or SIZE_LABEL.search(texts[0])):
                        out.extend((f"{texts[0]} {h}", t, "tr") for h, t in zip(columns[1:], texts[1:]) if t)
                elif header and len(header) == len(texts) and cells[0].tag != "th":
                    out.extend((h, t, "tr") for h, t in zip(header, texts) if h and t)
                elif len(texts) >= 2 and (cells[0].tag == "th" or len(texts) == 2):
                    out.append((texts[0], " ".join(texts[1:]), "tr"))
    return [(label, value, cell) for label, value, cell in out if label or value]


# ---- variant binding ----------------------------------------------------------------------

def _compact(text):
    return re.sub(r"\s+", "", _norm(text).lower())


def _named(value, line):
    """The option value is written in the line (latin values as whole words)."""
    v = _compact(value)
    if len(v) < 2:
        return False
    if re.fullmatch(r"[a-z0-9.\-+]+", v):
        return re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", _compact(line)) is not None
    return v in _compact(line)


def bind(line, options):
    """{scope, variant_ids} for a line, or None when it names two compositions (a contradiction)."""
    variants = [v for v in (options or {}).get("variants") or [] if v.get("options")]
    if len(variants) <= 1:
        return {"scope": "product", "variant_ids": [variants[0]["id"]] if variants else []}
    groups = [g for g in (options or {}).get("option_groups") or [] if g.get("type") not in ("CUSTOM", "SIMPLE")]
    cosmetic = {i for i, g in enumerate(groups) if COSMETIC_GROUP.search(g.get("name") or "")}
    named = {}
    for v in variants:
        for i, value in enumerate(v["options"]):
            if _named(value, line):
                named.setdefault(i, set()).add(value)
    if any(len(values) > 1 for i, values in named.items() if i not in cosmetic):
        return None
    if not named:
        return {"scope": "context", "variant_ids": []}
    hits = [v for v in variants if all(i < len(v["options"]) and v["options"][i] in values
                                       for i, values in named.items())]
    compositions = {tuple(o for i, o in enumerate(v["options"]) if i not in cosmetic) for v in hits}
    if len(compositions) == 1:
        return {"scope": "variants", "variant_ids": [v["id"] for v in hits]}
    return {"scope": "context", "variant_ids": []}


# A club count in an option value or a value segment: "4스틸 + 골프백", "12개", "9P", "13pcs"; not "10.5도", "9도SR",
# "2109 cmix", "8아이언" (6630856593, 2026-11-06).
COUNT_TOKEN = re.compile(r"(?<![\d.#])(\d{1,2})\s*(?:개|종|pcs?|p|피스|클럽|(?=\s*(?:스틸|카본|그라파이트|steel|graphite)))"
                         r"(?![a-z])", re.I)


def _count(text):
    found = {int(m.group(1)) for m in COUNT_TOKEN.finditer(text or "") if 2 <= int(m.group(1)) <= 20}
    return found.pop() if len(found) == 1 else None


def segment_binding(value, weights, options):
    """One binding per weight of a value list, or None. '12개 11.5kg / 4개 4.7kg', 'S세트 4.2kg / R세트 3.9kg': each
    segment names its composition. A bare '약11.5kg / 4.7kg' (6630856593) on variants that differ by club count (4, 12):
    heaviest to the most clubs, flag bound_by_count_rank (the text order, 11.5 then 4.7, is not the option order)."""
    variants = [v for v in (options or {}).get("variants") or [] if v.get("options")]
    if len(variants) < 2 or len(weights) < 2:
        return None
    segments = [s for s in SEP.split(value) if WEIGHT_RE.search(s)]
    if len(segments) != len(weights):
        return None
    counts = {v["id"]: _count(" ".join(v["options"])) for v in variants}
    out = []
    for seg in segments:
        b = bind(seg, options)
        n = _count(seg)
        ids = [i for i, c in counts.items() if n is not None and c == n]
        out.append(b if b and b["scope"] == "variants" else
                   {"scope": "variants", "variant_ids": ids} if ids else None)
    if all(out) and len({tuple(b["variant_ids"]) for b in out}) == len(out):
        return [(b, None) for b in out]
    distinct = sorted({c for c in counts.values() if c is not None}, reverse=True)
    grams = [w["value"]["min"] for w in weights]
    if None in counts.values() or len(distinct) != len(weights) or any(_count(s) for s in segments) \
            or len(set(grams)) != len(grams):
        return None
    ranked = sorted(range(len(grams)), key=lambda i: -grams[i])
    res = [None] * len(grams)
    for rank, i in enumerate(ranked):
        res[i] = ({"scope": "variants", "variant_ids": [v for v, c in counts.items() if c == distinct[rank]]},
                  "bound_by_count_rank")
    return res


# ---- parsing ------------------------------------------------------------------------------

def _kinds(text, table):
    return [k for k, rx in table.items() if rx.search(text)]


def _line_part(label, value, is_set, context_part):
    """In a set, the part a whole line is about: a club heading above it, the label, or a part before its first ':'
    ("#6 아이언: ... (중량: S 약 418g / R 약 382g)": both weights are the iron's)."""
    if not is_set:
        return False
    head = re.match(r"\s*([^:：]{1,24})[:：]", value)
    return bool(context_part or SET_PARTS.search(label) or (head and SET_PARTS.search(head.group(1))))


def _weights(label, value, is_set, context_part=None, plain=False, size_row=False):
    """-> ([candidate fields], [review reasons])."""
    if WEIGHT_SKIP.search(f"{label} {value}") or LOAD.search(label):
        return [], []
    label_unit = LABEL_UNIT.search(label)
    label_unit = label_unit and (label_unit["u"] or label_unit["v"])
    found, review = [], []
    matches = list(WEIGHT_RE.finditer(value))
    if not matches and label_unit and _factor(label_unit, GRAMS):
        bare = BARE_NUM.match(value)
        if bare:
            matches = [bare]
    if not matches and AMBIGUOUS_UNIT.search(value):
        return [], ["ambiguous_unit"]
    line_part = _line_part(label, value, is_set, context_part)
    for i, m in enumerate(matches):
        prev_end = matches[i - 1].end() if i else 0
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(value)
        if m.start() and value[m.start() - 1] in "-−" and not value[:m.start() - 1].rstrip()[-1:].isalnum():
            continue                                   # a negative number is not a weight (300g-350g is a range)
        if "area" in m.groupdict() and m["area"]:
            continue                                   # g/m²: a fabric weight
        if TOLERANCE.search(value[max(prev_end, m.start() - 8):m.start()]):
            continue                                   # "1200g(±50g)", "오차범위 ±50g": a tolerance
        unit = m.groupdict().get("u") or label_unit
        if label_unit and m.groupdict().get("u") and _factor(label_unit, GRAMS) and \
                _factor(label_unit, GRAMS) != _factor(m["u"], GRAMS):
            review.append("unit_conflict")
            continue
        factor = _factor(unit, GRAMS)
        if factor is None or (size_row and unit == "G"):
            continue                                   # in a size row "5G" is a network, not 5 g
        if factor == IMPERIAL[1] and re.search(r"fl\.?\s*$|액량|용량", value[max(0, m.start() - 6):m.start()], re.I):
            continue                                   # fl oz: a volume
        if factor <= 1 and any(DECIMAL_COMMA.fullmatch(x or "") for x in (m["a"], m.groupdict().get("b"))):
            review.append("decimal_comma")             # "45,50g대": 45.5 g or 45-50 g, a person reads it
            continue
        begin, finish = _segment(value, m.start(), m.end(), prev_end, next_start)
        segment = value[begin:finish]
        if LOAD.search(segment):
            continue
        head = re.match(r"\s*([^:：]{1,24})[:：]", value) if size_row and not label else None
        local = f"{label} {head.group(1) if head else ''} {segment}"    # "포장 박스 : 128 X 32 X 28 cm, 9kg"
        kinds = set(_kinds(local, WEIGHT_KINDS))
        if NOT_PACKED.search(local):
            kinds.discard("packed")
        scopes = _kinds(local, SCOPES)
        before = value[begin:m.start()]
        count = None
        multiplier = MULTIPLIER.match(value, m.end())
        if UNIT_AFTER.match(value, m.end()) or UNIT_BEFORE.search(before) or multiplier:
            scopes = ["unit"]
            count = int(multiplier["count"]) if multiplier else None
        if is_set and not scopes and factor >= IMPERIAL[0] and SET_TOTAL.search(before):
            scopes = ["set"]                           # "총 무게 약 9kg": a total in kg / lb is the whole set
        flags = []
        if "set" not in scopes and REF_CLUB.search(f"{label} {value[:m.start()]}"):
            kinds.add("component")                     # "7번 기준 36인치 , 332g": measured on one club
        if is_set and "set" not in scopes and "unit" not in scopes and "기준" in f"{label} {value[:m.start()]}":
            kinds.add("component")                     # "NS PRO950 R기준 약 405g": one club or shaft
        # In a set, "드라이버 300g" is a part's weight; "드라이버, 아이언 포함 세트 총 9.5kg" is the set's.
        if is_set and "component" not in kinds and "set" not in scopes and \
                (SET_PARTS.search(label) or SET_PARTS.search(segment) and not NOT_A_PART.search(segment)):
            kinds.add("component")
        if line_part and not re.search(r"세트|(?<![a-z])set(?![a-z])", segment, re.I):
            kinds.add("component")                     # under a club heading / after a club prefix: one club's
            scopes = [s for s in scopes if s != "set"]
        if len(kinds) > 1:
            review.append("kind_conflict")
            continue
        kind = next(iter(kinds), "unknown")
        if BAG_EXCLUDED.search(local):
            flags.append("bag_excluded")
        low_factor = _factor(m.groupdict().get("ua") or unit, GRAMS) or factor
        lo, hi = _num(m["a"]) * low_factor, _num(m["b"]) * factor if m.groupdict().get("b") else None
        if is_set and plain and not scopes and kind in ("net", "unknown"):
            if max(lo, hi or lo) >= 1000:              # a set's plain weight row: the product as sold
                scopes = ["set"]
            else:                                      # no set weighs under 1 kg, no club or part over it
                kind = "component"
                flags.append("part_scale")
        found.append({"value": _span(lo, hi), "unit": unit, "matched": m.group(0).strip(), "kind": kind,
                      "scope": scopes[0] if len(scopes) == 1 else "unknown",
                      "approximate": bool(APPROX.search(local) or m.groupdict().get("dash") in ("~", "～")),
                      "count": count, "flags": flags, "_span": (m.start(), m.end()), "_segment": (begin, finish),
                      "_factor": factor, "_multiplier": multiplier})
    found = _merge_units(value, found)
    out = []
    for f in found:
        multiplier = f.pop("_multiplier")
        out.append(f)
        if multiplier and f["scope"] == "unit":       # "500g x 2개": 500 g each, 1000 g in all (stated arithmetic)
            n = int(multiplier["count"])
            out.append({**f, "value": _span(f["value"]["min"] * n, f["value"]["max"] * n), "scope": "set",
                        "matched": value[f["_span"][0]:multiplier.end()].strip(), "flags": f["flags"] + ["multiplied"]})
    if any(f["kind"] == "net" for f in out):          # "본체 120g / 충전케이스 50g": the 50 g is another part's
        others = [f for f in out if f["kind"] == "unknown" and f["scope"] != "unit"]
        review += ["other_part"] * len(others)
        out = [f for f in out if f not in others]
    return out, review


def _merge_units(value, found):
    """3 lb 4 oz -> one weight (lb_oz); 6.35 kg / 14 lbs, 1.45kg (3.2lb): the same weight in a second unit, within 2%
    -> the first one written (alternate_unit). Different values ("7kg / 9lbs", "1kg (2kg 옵션)") stay apart."""
    out = []
    for f in found:
        prev = out[-1] if out else None
        if prev and prev["_factor"] == IMPERIAL[0] and f["_factor"] == IMPERIAL[1] and prev["kind"] == f["kind"] \
                and not value[prev["_span"][1]:f["_span"][0]].strip():
            prev["value"] = _span(prev["value"]["min"] + f["value"]["min"], prev["value"]["max"] + f["value"]["max"])
            prev["_span"] = (prev["_span"][0], f["_span"][1])
            prev["matched"] = value[prev["_span"][0]:prev["_span"][1]].strip()
            prev["flags"] = prev["flags"] + ["lb_oz"]
            continue
        if prev and prev["_factor"] != f["_factor"] and (prev["_factor"] in IMPERIAL) != (f["_factor"] in IMPERIAL) \
                and prev["kind"] == f["kind"] and prev["scope"] == f["scope"] and \
                abs(prev["value"]["min"] - f["value"]["min"]) <= 0.02 * max(prev["value"]["min"], f["value"]["min"]):
            prev["_span"] = (prev["_span"][0], f["_span"][1])
            prev["matched"] = value[prev["_span"][0]:prev["_span"][1]].strip()
            prev["approximate"] = prev["approximate"] or f["approximate"]
            prev["flags"] = prev["flags"] + ["alternate_unit"]
            continue
        out.append(f)
    return out


def _axis(token):
    return AXES.get((token or "").lower()) or AXES.get(token or "")


def _size_kind(text, is_set, part):
    kinds = set(_kinds(text, SIZE_KINDS))
    if "club" in kinds:
        kinds.discard("club")
        kinds.add("component" if is_set else "product")
    if part and "packed" not in kinds:
        return "component"                             # a club's length under a club heading
    if "packed" in kinds and "component" in kinds:
        return "unknown"
    return next((k for k in ("packed", "component", "product") if k in kinds), None)


def _sizes(label, value, is_set=False, part=False, name=""):
    text = f"{label} {value}"
    if SIZE_SKIP.search(text):
        return [], []
    label_kind = _size_kind(label, is_set, part)
    whole_kind = _size_kind(text, is_set, part) or "unknown"
    state = "unfolded" if UNFOLDED.search(text) else "folded" if FOLDED.search(text) else None
    noted = LABEL_UNIT.search(label) or LABEL_UNIT.search(value)
    noted = noted and (noted["u"] or noted["v"])
    noted = noted if noted and _factor(noted, MM) else None
    triples = list(TRIPLE_RE.finditer(value))
    if triples:
        label_axes = LABEL_AXES.search(label)
        out, review, prev = [], [], 0
        for t in triples:
            unit = t["u2"] or t["ut"] or t["u1"] or t["u0"] or noted
            factor = _factor(unit, MM) if unit else None
            if factor is None:
                review.append("unit_missing")
                prev = t.end()
                continue
            # Each triple takes its kind from its own words ("제품 크기 30x20x10cm / 포장 크기 35x25x15cm"), the label's
            # only when they name none.
            begin, finish = _segment(value, t.start(), t.end(), prev)
            kind = _size_kind(value[begin:t.start()] + " " + value[t.end():finish], is_set, part) or label_kind \
                or "unknown"
            tail = re.split(r"\s*[x×*X]\s*", t["tail"]) if t["tail"] else \
                list(label_axes.groups()) if label_axes else [None] * 3
            axes = [_axis(t[f"p{i}"] or t[f"s{i}"] or t[f"x{i}"] or tail[i]) for i in range(3)]
            values = [round(_num(t[f"n{i}"]) * factor, 3) for i in range(3)]
            last = out[-1] if out else None
            if last and re.fullmatch(r"\s*\(?\s*", value[prev:t.start()]) and all(
                    abs(a - b) <= 0.03 * max(a, b) for a, b in zip(sorted(last["values"]), sorted(values))):
                prev = t.end()
                continue                               # "48.2 x 12.7 x 8.5 inches (122 x 32 x 21 cm)": the same box
            flags = [] if all(axes) else ["axis_order_unresolved"]
            if kind != "packed":
                flags.append("not_confirmed_packed")
            out.append({"values": values, "axes": axes if all(axes) else None, "unit": unit,
                        "matched": t.group(0).strip(), "kind": kind, "state": state, "flags": flags})
            prev = t.end()
        return out, review if not out else []
    doubles = list(DOUBLE_RE.finditer(value))
    if doubles:
        out = []
        for d in doubles:
            factor_a = _factor(d["ua"] or d["u"], MM)
            factor_b = _factor(d["u"], MM)
            begin, finish = _segment(value, d.start(), d.end())
            kind = _size_kind(value[begin:finish], is_set, part) or label_kind or "unknown"
            out.append({"values": [round(_num(d["a"]) * factor_a, 3), round(_num(d["b"]) * factor_b, 3)],
                        "axes": None, "unit": d["u"], "matched": d.group(0).strip(), "kind": kind, "state": state,
                        "flags": ["two_sides"] + ([] if kind == "packed" else ["not_confirmed_packed"])})
        return out, []
    if any(r["u1"] or r["u2"] for r in SIZE_RANGE.finditer(value)):
        if re.search(r"치수|사이즈", label) and SHOE_NAME.search(name or ""):
            return [], []                              # 230~280mm under 치수 of a shoe: the sizes sold
        return [], ["manual_review"]                   # a range: read by a person
    kind = whole_kind
    pairs = list(PAIR_RE.finditer(value))
    if len(pairs) >= 2:                                # 가로120 세로30 높이25cm: one unit for all, given at the end
        units = [p["u"] for p in pairs if p["u"]]
        unit = units[-1] if units else noted
        axes = [_axis(p["a"]) for p in pairs]
        if not unit or len(set(units)) > 1 or len(set(axes)) < len(axes) or len(pairs) > 3:
            return [], ["manual_review"]
        factor = _factor(unit, MM)
        flags = [] if kind == "packed" else ["not_confirmed_packed"]
        return [{"values": [round(_num(p["n"]) * factor, 3) for p in pairs], "axes": axes, "unit": unit,
                 "matched": value[pairs[0].start():pairs[-1].end()], "kind": kind, "state": state, "flags": flags}], []
    if len(SINGLE_RE.findall(value)) > 1:
        return [], ["manual_review"]                   # a list of sizes: read by a person
    single = SINGLE_RE.search(value)
    if not single:
        return [], []
    # The axis is the word right before the number (in the value, else the label's last one).
    near = list(re.finditer(rf"(?<![A-Za-z가-힣])(?:{AXIS}|넓이|지름|직경)(?![A-Za-z]|[가-힣](?<!이))",
                            value[max(0, single.start() - 12):single.start()]))
    words = [m.group(0) for m in near] or re.findall(rf"(?<![A-Za-z])(?:{AXIS}|넓이|지름|직경)(?![A-Za-z])", label)
    axis = _axis(words[-1]) if words else None
    if not axis:
        return [], []
    factor = _factor(single["u"], MM)
    return [{"values": [round(_num(single["n"]) * factor, 3)], "axes": [axis], "unit": single["u"],
             "matched": single.group(0), "kind": kind, "state": state, "flags": []}], []


def _heading(value, context_part):
    """The club block a description line opens or closes: a short line naming a part ("1. 드라이버 (1W)") opens one;
    a short line naming none, or one that speaks of the set ("클럽 구성 (총 11개 세트)", "스펙 가이드"), closes it."""
    if len(value) > 40 or re.search(rf"\d\s*(?:{_W_UNIT}|{_S_UNIT})(?![a-z])", value, re.I):
        return context_part
    if HEADING_END.search(value):
        return None
    if SET_PARTS.search(value):
        return value
    return context_part if re.search(r"[:：]", value) else None


def measures(rows=(), notice=None, description=None, page_html="", product_id=None, options=None, name=None,
             category=None):
    """-> {is_set, weights[], dimensions[], references[], review[]} (see the module docstring)."""
    category_name = " ".join((category or {}).get("path") or []) + " " + ((category or {}).get("name") or "")
    is_set = bool(SET_NAME.search(f"{name or ''} {category_name}"))
    out = {"is_set": is_set, "weights": [], "dimensions": [], "references": [], "review": []}
    seen = set()
    context_part = None
    for source, locator, label, value in _lines(rows, notice, description, page_html, product_id):
        label, value = _norm(label), _norm(value)
        if source == "description":
            context_part = _heading(value, context_part)
        quote = f"{label}: {value}" if label else value
        has_weight = bool(WEIGHT_LABEL.search(quote))
        has_size = bool(SIZE_LABEL.search(quote)) or bool(
            SIZE_KINDS["packed"].search(quote) and any(t["u0"] or t["u1"] or t["u2"] or t["ut"]
                                                       for t in TRIPLE_RE.finditer(value)))
        size_row = has_size and not has_weight and bool(WEIGHT_RE.search(value))
        has_weight = has_weight or size_row            # "크기: 7번 R기준 93.345cm / 7번 기준 328g"
        if not (has_weight or has_size):
            continue
        place = {"quote": quote, "source": source, "locator": locator}
        if REFERENCE.search(value) or parsers.is_see_description(value):
            reason = "measurement_field_reference" if FIELD_REFERENCE.search(value) else "description_reference"
            by_label = (WEIGHT_LABEL.search(label), SIZE_LABEL.search(label))
            which = by_label if any(by_label) else (has_weight, has_size)      # 중량: 크기 항목 참조 is about weight
            for measure, has in zip(("weight", "size"), which):
                if has:
                    out["references"].append({**place, "measure": measure, "reason": reason})
            continue
        binding = bind(quote, options)
        part = context_part if source == "description" else None
        found = []
        if has_weight:
            plain = source in STRUCTURED and bool(PLAIN_WEIGHT_LABEL.fullmatch(LABEL_UNIT.sub("", label).strip()))
            weights, review = _weights(label, value, is_set, part, plain, size_row)
            out["review"] += [{**place, "measure": "weight", "reason": r} for r in review]
            weights = _bind_values(value, weights, binding, options, out["review"], place)
            found += [("weights", w) for w in weights]
        if has_size:
            sizes, review = _sizes(label, value, is_set, _line_part(label, value, is_set, part), name)
            found += [("dimensions", s) for s in sizes]
            out["review"] += [{**place, "measure": "size", "reason": r} for r in review]
        if any("_binding" not in f for _, f in found) and binding is None:
            out["review"].append({**place, "measure": "weight" if has_weight else "size",
                                  "reason": "two_compositions"})
            found = [(b, f) for b, f in found if "_binding" in f]
        for bucket, fields in found:
            own = fields.pop("_binding", None)
            key = (bucket, _compact(quote), json.dumps(fields.get("value") or fields.get("values")))
            if key in seen:
                continue
            seen.add(key)
            out[bucket].append({**fields, **place, "binding": own or binding, "origin": "source_stated"})
    return out


def _bind_values(value, weights, binding, options, review, place):
    """A value list ("약11.5kg / 4.7kg") on a line that names no single composition: each value its own variants
    (segment_binding), or the product-like ones go to review `value_list`. Drops the private keys."""
    if len(weights) >= 2 and (binding is None or binding["scope"] == "context"):
        per = segment_binding(value, weights, options)
        if per:
            for w, (b, flag) in zip(weights, per):
                w["_binding"] = b
                w["flags"] = w["flags"] + ([flag] if flag else [])
        elif binding is not None:
            whole = [w for w in weights if w["kind"] in ("net", "unknown") and w["scope"] != "unit"]
            if len({w["_segment"] for w in whole}) >= 2:
                review.append({**place, "measure": "weight", "reason": "value_list"})
                weights = [w for w in weights if w not in whole]
    for w in weights:
        for key in ("_span", "_segment", "_factor"):
            w.pop(key, None)
    return weights
