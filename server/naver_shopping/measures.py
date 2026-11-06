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
                     th cells is the header of the rows under it)
The same quote with the same value is kept once, from the first source.

A line counts for weight only with a weight label (무게, 중량, weight, mass) and for size only with a size label
(크기, 치수, 사이즈, 길이, ...), in the row label or in the line. Per candidate:
  value    grams or millimetres, {min, max} (a range "9~10kg" gives both)
  kind     weight: net | packed | component | unknown; size: packed | component | product | unknown
  scope    weight: unit | set | unknown
  binding  {scope: product | variants | context, variant_ids}: one variant or none -> product; several -> variants
           only when the line names option values of exactly one composition (variants that differ only in a
           colour / design group count as one); otherwise context
A line whose words say two kinds at once, a unit in the label that differs from the value's, one line naming two
compositions, a size range or a list of sizes goes to `review` (with a reason) instead. A pointer such as
"상세페이지 참조" goes to `references` (description_reference / measurement_field_reference): no number.
"""
import json
import re
import unicodedata

from naver_shopping import parsers, pdp

# ---- words -------------------------------------------------------------------------------

WEIGHT_LABEL = re.compile(r"무게|중량|weight|mass", re.I)
SIZE_LABEL = re.compile(r"크기|치수|사이즈|길이|높이|가로|세로|폭(?![가-힣])|넓이|깊이|지름|직경|length|width|height|depth|diameter|"
                        r"dimensions?|size", re.I)
WEIGHT_SKIP = re.compile(r"스윙\s*웨이트|swing\s*weight|압축\s*강도|모델명|model\s*(?:name|number|no)", re.I)
SIZE_SKIP = re.compile(r"신발\s*사이즈|가슴|허리|엉덩이|둘레|헤드\s*체적|volume|이미지|resolution|"
                       r"무게\s*중심|비거리|탄도|스핀", re.I)     # golf talk: centre of gravity, carry, launch, spin
REFERENCE = re.compile(r"(?:상세\s*페이지|상품\s*상세|상세\s*설명|상품\s*페이지)\s*참[조고]|(?:크기|중량)\s*항목\s*참조")
FIELD_REFERENCE = re.compile(r"(?:크기|중량)\s*항목\s*참조")

WEIGHT_KINDS = {
    "net": re.compile(r"순\s*중량|net\s*weight", re.I),
    "packed": re.compile(r"포장\s*(?:포함|후)|포장\s*박스\s*포함|패키지\s*무게|gross\s*weight|shipping\s*weight|"
                         r"packed\s*weight", re.I),
    "component": re.compile(r"샤프트|shaft|그립|grip|헤드\s*(?:중량|무게)|head\s*weight|캐디\s*백\s*(?:중량|무게)|"
                            r"골프\s*백\s*(?:중량|무게)", re.I),
}
SET_PARTS = re.compile(r"드라이버|아이언|우드|유틸|하이브리드|퍼터|웨지|헤드|driver|iron|wood|hybrid|putter|wedge|head",
                       re.I)                    # a part of a club set: its weight is not the set's
SCOPES = {
    "unit": re.compile(r"개당|낱개|1\s*개당|per\s*(?:piece|unit|item)", re.I),
    "set": re.compile(r"(?:풀\s*)?세트\s*(?:전체|총)?\s*(?:무게|중량)|세트\s*(?:전체|총)|(?:전체|총)\s*(?:무게|중량)|"
                      r"(?:complete|total)\s*set|set\s*weight", re.I),
}
SET_NAME = re.compile(r"세트|(?<![a-z])sets?(?![a-z])", re.I)       # not "Offset", "Headset"
APPROX = re.compile(r"약|대략|approx|about|around", re.I)
SIZE_KINDS = {
    "packed": re.compile(r"패키지|포장|박스|package|packed|carton|box", re.I),
    "component": re.compile(r"샤프트|헤드|그립", re.I),
    "product": re.compile(r"제품|클럽|product|club", re.I),
}
UNFOLDED = re.compile(r"펼친|전개|unfolded", re.I)
FOLDED = re.compile(r"접은|접이|folded", re.I)
COSMETIC_GROUP = re.compile(r"색상|컬러|칼라|color|colour|디자인|design", re.I)

# ---- numbers and units -------------------------------------------------------------------

NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
DASH = r"[~～–—\-]"
GRAMS = [(r"kilograms?|킬로그램|키로그램|kg|㎏|킬로", 1000.0), (r"milligrams?|mg|㎎", 0.001), (r"grams?|그램|g", 1.0),
         (r"pounds?|lbs?", 453.59237), (r"ounces?|oz", 28.349523125)]
MM = [(r"밀리미터|mm", 1.0), (r"센티미터|cm", 10.0), (r"인치|inch(?:es)?|in|\"", 25.4), (r"미터|m", 1000.0)]
_W_UNIT = "|".join(u for u, _ in GRAMS)
_S_UNIT = "|".join(u for u, _ in MM)
WEIGHT_RE = re.compile(rf"(?P<a>{NUM})(?:\s*(?P<ua>{_W_UNIT})(?![a-z]))?(?:\s*(?P<dash>{DASH})\s*(?P<b>{NUM}))?"
                       rf"\s*\(?\s*(?P<u>{_W_UNIT})(?![a-z])\s*\)?"
                       rf"(?P<area>\s*/\s*(?:m²|㎡|m2))?", re.I)
LABEL_UNIT = re.compile(rf"\(\s*(?P<u>{_W_UNIT}|{_S_UNIT})\s*\)", re.I)
BARE_NUM = re.compile(rf"^\s*(?:약\s*)?(?P<a>{NUM})(?:\s*{DASH}\s*(?P<b>{NUM}))?\s*$")
AXIS = r"가로|세로|높이|길이|폭|깊이|두께|[LWHDT]"
AXES = {"가로": "width", "세로": "depth", "높이": "height", "길이": "length", "폭": "width", "깊이": "depth",
        "두께": "thickness", "l": "length", "w": "width", "h": "height", "d": "depth", "t": "thickness",
        "넓이": "width", "지름": "diameter", "직경": "diameter"}
_PART = rf"(?:(?P<p§>{AXIS})\s*[:=]?\s*)?(?P<n§>{NUM})\s*(?:\((?P<s§>{AXIS})\))?\s*(?P<u§>{_S_UNIT})?"
TRIPLE_RE = re.compile(r"\s*[x×*X]\s*".join(_PART.replace("§", str(i)) for i in range(3))
                       + rf"(?:\s*\(\s*(?P<tail>(?:{AXIS})\s*[x×*X]\s*(?:{AXIS})\s*[x×*X]\s*(?:{AXIS}))\s*\))?"
                       + rf"(?:\s*\(\s*(?P<ut>{_S_UNIT})\s*\))?", re.I)
PAIR_RE = re.compile(rf"(?<![A-Za-z가-힣])(?P<a>{AXIS}|넓이|지름|직경)\s*[:=]?\s*(?P<n>{NUM})\s*(?P<u>{_S_UNIT})?(?![a-z])",
                     re.I)                      # 가로120 세로30 높이25cm: axis + number pairs
SINGLE_RE = re.compile(rf"(?P<n>{NUM})\s*(?P<u>{_S_UNIT})(?![a-z])", re.I)
SIZE_RANGE = re.compile(rf"{NUM}\s*(?:{_S_UNIT})?\s*(?:{DASH}|부터)\s*{NUM}", re.I)


def _norm(text):
    return unicodedata.normalize("NFKC", text or "").strip()


def _num(text):
    return float(text.replace(",", ""))


def _factor(unit, table):
    for pattern, factor in table:
        if re.fullmatch(pattern, unit, re.I):
            return factor
    return None


def _span(lo, hi=None):
    hi = lo if hi is None else hi
    return {"min": round(min(lo, hi), 3), "max": round(max(lo, hi), 3)}


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
            header = None
            for tr in (d for d in node.descendants() if d.tag == "tr"):
                cells = [c for c in tr.elements() if c.tag in ("th", "td")]
                if cells and all(c.tag == "th" for c in cells):
                    header = [pdp._flat(c) for c in cells]
                    continue
                texts = [pdp._flat(c) for c in cells]
                if header and len(header) == len(texts) and cells[0].tag != "th":
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


# ---- parsing ------------------------------------------------------------------------------

def _kinds(text, table):
    return [k for k, rx in table.items() if rx.search(text)]


def _weights(label, value, is_set):
    """-> ([candidate fields], [review reasons])."""
    text = f"{label} {value}"
    if WEIGHT_SKIP.search(text):
        return [], []
    label_unit = LABEL_UNIT.search(label)
    found, review, start = [], [], 0
    matches = list(WEIGHT_RE.finditer(value))
    if not matches and label_unit and _factor(label_unit["u"], GRAMS):
        bare = BARE_NUM.match(value)
        if bare:
            matches = [bare]
    for m in matches:
        if m.start() and value[m.start() - 1] in "-−" and not value[:m.start() - 1].rstrip()[-1:].isalnum():
            continue                                   # a negative number is not a weight (300g-350g is a range)
        if "area" in m.groupdict() and m["area"]:
            continue                                   # g/m²: a fabric weight
        unit = m.groupdict().get("u") or label_unit["u"]
        if label_unit and m.groupdict().get("u") and _factor(label_unit["u"], GRAMS) and \
                _factor(label_unit["u"], GRAMS) != _factor(m["u"], GRAMS):
            review.append("unit_conflict")
            continue
        factor = _factor(unit, GRAMS)
        if factor is None:
            continue
        local = f"{label} {value[start:m.end()]}"
        segment = value[start:m.start()]               # the words right before this number
        start = m.end()
        kinds = _kinds(local, WEIGHT_KINDS)
        scopes = _kinds(local, SCOPES)
        # In a set, "드라이버 300g" is a part's weight; "드라이버, 아이언 포함 세트 총 9.5kg" is the set's.
        if is_set and "component" not in kinds and "set" not in scopes and \
                (SET_PARTS.search(label) or SET_PARTS.search(segment) and not re.search(r"세트|포함|set", segment, re.I)):
            kinds.append("component")
        if len(kinds) > 1:
            review.append("kind_conflict")
            continue
        low_factor = _factor(m.groupdict().get("ua") or unit, GRAMS) or factor
        lo, hi = _num(m["a"]) * low_factor, _num(m["b"]) * factor if m["b"] else None
        found.append({"value": _span(lo, hi), "unit": unit, "matched": m.group(0).strip(),
                      "kind": kinds[0] if kinds else "unknown",
                      "scope": scopes[0] if len(scopes) == 1 else "unknown",
                      "approximate": bool(APPROX.search(local) or m.groupdict().get("dash") in ("~", "～"))})
    return found, review


def _axis(token):
    return AXES.get((token or "").lower()) or AXES.get(token or "")


def _sizes(label, value):
    text = f"{label} {value}"
    if SIZE_SKIP.search(text):
        return [], []
    kinds = _kinds(text, SIZE_KINDS)
    if "packed" in kinds and "component" in kinds:
        kind = "unknown"
    else:
        kind = next((k for k in ("packed", "component", "product") if k in kinds), "unknown")
    state = "unfolded" if UNFOLDED.search(text) else "folded" if FOLDED.search(text) else None
    label_unit = LABEL_UNIT.search(label)
    triple = TRIPLE_RE.search(value)
    if triple:
        unit = (triple["u2"] or triple["ut"] or triple["u1"] or triple["u0"]
                or (label_unit["u"] if label_unit and _factor(label_unit["u"], MM) else None))
        factor = _factor(unit, MM) if unit else None
        if factor is None:
            return [], ["unit_missing"]
        tail = re.split(r"\s*[x×*X]\s*", triple["tail"]) if triple["tail"] else [None] * 3
        axes = [_axis(triple[f"p{i}"] or triple[f"s{i}"] or tail[i]) for i in range(3)]
        values = [round(_num(triple[f"n{i}"]) * factor, 3) for i in range(3)]
        flags = [] if all(axes) else ["axis_order_unresolved"]
        if kind != "packed":
            flags.append("not_confirmed_packed")
        return [{"values": values, "axes": axes if all(axes) else None, "unit": unit, "matched": triple.group(0),
                 "kind": kind, "state": state, "flags": flags}], []
    if SIZE_RANGE.search(value):
        return [], ["manual_review"]                   # a range: read by a person
    pairs = list(PAIR_RE.finditer(value))
    if len(pairs) >= 2:                                # 가로120 세로30 높이25cm: one unit for all, given at the end
        units = [p["u"] for p in pairs if p["u"]]
        unit = units[-1] if units else (label_unit["u"] if label_unit and _factor(label_unit["u"], MM) else None)
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


def measures(rows=(), notice=None, description=None, page_html="", product_id=None, options=None, name=None,
             category=None):
    """-> {is_set, weights[], dimensions[], references[], review[]} (see the module docstring)."""
    category_name = " ".join((category or {}).get("path") or []) + " " + ((category or {}).get("name") or "")
    is_set = bool(SET_NAME.search(f"{name or ''} {category_name}"))
    out = {"is_set": is_set, "weights": [], "dimensions": [], "references": [], "review": []}
    seen = set()
    for source, locator, label, value in _lines(rows, notice, description, page_html, product_id):
        label, value = _norm(label), _norm(value)
        quote = f"{label}: {value}" if label else value
        has_weight = bool(WEIGHT_LABEL.search(quote))
        has_size = bool(SIZE_LABEL.search(quote))
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
        found = []
        if has_weight:
            weights, review = _weights(label, value, is_set)
            found += [("weights", w) for w in weights]
            out["review"] += [{**place, "measure": "weight", "reason": r} for r in review]
        if has_size:
            sizes, review = _sizes(label, value)
            found += [("dimensions", s) for s in sizes]
            out["review"] += [{**place, "measure": "size", "reason": r} for r in review]
        if found and binding is None:
            out["review"].append({**place, "measure": "weight" if has_weight else "size",
                                  "reason": "two_compositions"})
            continue
        for bucket, fields in found:
            key = (bucket, _compact(quote), json.dumps(fields.get("value") or fields.get("values")))
            if key in seen:
                continue
            seen.add(key)
            out[bucket].append({**fields, **place, "binding": binding, "origin": "source_stated"})
    return out
