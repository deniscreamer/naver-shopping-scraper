"""Five shipping fields per variant, from the seller's candidates (/products/specs `measures`) or the operator's
category averages (category_measures.json). The owner's rules, 2026-11-05:

  product_weight_g    net or unspecified weight, never a part's (component); in a set only the whole set's
                      (scope set); a weight per piece (scope unit) is not the product's
  package_weight_g    a weight with the package (kind packed) only
  package_length_mm   a size triple marked as the package (kind packed); a triple without that mark is not the
  package_width_mm    package (not_confirmed_packed). The three sides are taken longest first (length >= width >=
  package_height_mm   height), whatever order the seller wrote

A candidate belongs to a variant when its binding is `product`, or `variants` with that variant's id; `context`
lines are not values. So a set weight stated per composition ("중량: 약11.5kg / 4.7kg", bound by club count in
measures.py) is each variant's own. Candidates of one field that disagree (no common range, 2% allowed: 6.35 kg and
14 lb are one weight) are a contradiction: the field is not taken from the seller. Parts' weights (kind component)
are never added up into a set's (2026-11-06): the sums of the club spec tables leave out the bag, the head covers
and sometimes the putter, so they are not the product's weight, not even as a lower bound worth a field.
(description_measures.py does sum the clubs, plus the bag's weight, for a field the seller does not state: the
owner, 2026-11-10, a composition from the set's parts goes before the flat default; a value taken here is never
replaced by it.)

A field the seller does not give is filled from the category table (low / central / high, its version, who approved
it and its reliability level), `source: category_default`; a seller's value is never overwritten. A default package
weight below the seller's own product weight is flagged `below_stated_product` (the transform then keeps no product
weight above the package: description_measures.product_over_package, 2026-11-17). A row
may carry `plausible: {field: {min, max}}`, the operator's band: a stated value outside it is not taken
(contradiction, reason implausible_for_category) and the default fills the field; a box is one statement, so a
side out of its band refuses the other two as well (box_not_whole, 2026-11-17). No band is made up here: without
one, every stated value is taken. A row may also carry `baselines`, the operator's amounts for the parts of a set
of like items in a container (BASELINES: one item, the container, the carton, the longest item, the box's length
over it; BASELINE_SIDES: the box's width and height without the container and with it; approved_by, approved_at,
basis). With them description_measures.py composes a field the seller does not state from the set's parts, each
part from the product's own data when it is there and from the baseline when it is not; the flat default is then
the last resort. No amount is made up in code; a row without the block gets no composition. A row may also carry
`kinds` (the owner, 2026-11-11, 50002787 junior clubs: single clubs and sets in one category): [{kind, match,
alone, always, unless, strong, lofts, fields, basis}], a kind of product with its own low / central / high, taken by
default_kind() from the title and the variant's words; its defaults carry `kind`. `lofts` [min, max] (2026-11-17,
50002783 two_wedges / four_plus): a count kind, by the variant's own count or that many distinct lofts in its
value, else by the title's count when every variant names as many lofts. A row may also carry `compose_by_count`
(50002783, 2026-11-17; checked by _check_compose, read by description_measures.compose_by_count): a set's product
weight from its clubs' labelled weights; with it a stated weight is checked against the variant's count of clubs
(count_kind, count_band, off_count: 2026-11-17, the resend review D1). `reliability` today
has one level, `estimated_average` (the weakest: an average of estimates, not measured); delivery will apply its
own coefficient per level.

No table row for the product's leaf category: CategoryDefaultsMissing. The run stops that category and asks the
operator for its values; they are never made up. Product sizes (not the package) are kept apart and optional.
Each field carries `confidence`, 1-5 (the owner, 2026-11-10; 1-3 from 2026-11-06 until then, and records written
before the change carry the old scale: its 3 is today's 5, its 2 today's 4):
  5  the seller states it and says what it is (a net weight, a weight with the package, the box's sides)
  4  the seller states it, a weaker reading: its kind left open (a plain "중량 11.5kg": with or without the box is
     not said), or bound to the variant by club count, or worked out (a per-piece weight times the count); in
     description_measures.py also a value read from an image
  3  composed wholly from the seller's own figures, plus the operator's carton / margin (description_measures.py)
  2  composed with a baseline or a weak part (description_measures.py)
  1  the flat category default
The evidence (source, quote, kind, scope, binding, flags, contradiction) travels with it.

    from package_measures import load_table, variant_measures
    fields = variant_measures(specs, load_table())      # [{variant_id, fields, product_size}]
"""
import json
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any

TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "category_measures.json")
RELIABILITY = ("estimated_average",)    # weakest first; a default's level travels with it (a shipping coefficient
                                        # per level comes later, the owner 2026-11-05)
FIELDS = ("product_weight_g", "package_weight_g", "package_length_mm", "package_width_mm", "package_height_mm")
SIDES = FIELDS[2:]
# a row's optional `baselines` block (description_measures.compose): one item of the set, its container, the box
# and its packing, the longest item, the box's length over it; the box's [width, height] without the container
# and with it
BASELINES = ("item_g", "container_g", "carton_g", "longest_item_mm", "length_margin_mm")
BASELINE_SIDES = ("sides_mm", "sides_with_container_mm")
# a row's optional `own_box` block (description_measures.own_box, 2026-11-27, 50002791): an item that is its own
# container (a stand bag). The box is the item's stated size + the margins, the package weight its weight + the
# carton; the bands say which size and weight are the item's ([min, max] each)
OWN_BOX = ("carton_g", "length_margin_mm", "side_margin_mm")
OWN_BOX_BANDS = ("long_mm", "side_mm", "weight_g")


class CategoryDefaultsMissing(Exception):
    """No category defaults for this leaf category: stop the category; the agent writes the row (ONBOARDING.md E1)."""

    def __init__(self, category_id: str | None, category_name: str | None = None):
        super().__init__(f"no package averages for category {category_id} ({category_name or '?'}) in "
                         f"category_measures.json: write its low / central / high (ONBOARDING.md E1) of {', '.join(FIELDS)}")
        self.category_id = category_id


class CategoryDefaultsInvalid(Exception):
    """A table row is incomplete or out of order (low <= central <= high)."""


def load_table(path: str = TABLE) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        table = json.load(f)
    for row in table.get("rows", []):
        check_row(row)
    return table


def row_version(table: Mapping[str, Any], row: Mapping[str, Any]) -> Any:
    """The version a default of this row carries (`table_version`): the row's `defaults_version`, else the table's.
    2026-11-18: a new row (50002784) raised the table to 8 and would have restamped 92 products of other rows from 7
    to 8 with no number changed (current_defaults stamps a default whose numbers moved since its collection); each row
    now names the version of its own defaults, raised only with its own fields or kinds. 2026-11-25 (the owner): a
    kind's words alone (50002816's suit, table version 20) move no number and keep it, as a band does: a raise would
    have restamped 37 rainwear products 19 -> 20 for the stamp alone (it travels in the package metafield)."""
    return row.get("defaults_version") or table["version"]


def check_row(row: dict[str, Any]) -> None:
    where = f"category {row.get('category_id')}"
    if "defaults_version" in row and not (type(row["defaults_version"]) is int and row["defaults_version"] >= 1):
        raise CategoryDefaultsInvalid(f"{where}: defaults_version must be a whole number >= 1")
    if not row.get("category_id") or not row.get("approved_by") or not row.get("approved_at"):
        raise CategoryDefaultsInvalid(f"{where}: category_id, approved_by and approved_at are required")
    if row.get("reliability") not in RELIABILITY:
        raise CategoryDefaultsInvalid(f"{where}: reliability must be one of {', '.join(RELIABILITY)}")
    for name, band in (row.get("plausible") or {}).items():
        try:
            if name not in FIELDS or not 0 < band["min"] < band["max"]:
                raise CategoryDefaultsInvalid(f"{where}: plausible {name} must be a field with 0 < min < max")
        except (KeyError, TypeError):
            raise CategoryDefaultsInvalid(f"{where}: plausible {name} needs numbers min, max") from None
    base = row.get("baselines")
    if base is not None:                      # whole or not at all: a composition never mixes in a made-up amount
        try:
            amounts = [base[k] for k in BASELINES] + [side for k in BASELINE_SIDES for side in base[k]]
            good = set(base) == {*BASELINES, *BASELINE_SIDES, "approved_by", "approved_at", "basis"} \
                and all(type(a) in (int, float) and a > 0 for a in amounts) and all(base.values()) \
                and all(len(base[k]) == 2 and base[k][0] >= base[k][1] for k in BASELINE_SIDES)
        except (KeyError, TypeError):
            good = False
        if not good:
            raise CategoryDefaultsInvalid(
                f"{where}: baselines needs {', '.join(BASELINES)} (numbers > 0), {', '.join(BASELINE_SIDES)} "
                "([width, height], width >= height > 0), approved_by, approved_at and basis, and nothing else")
    own = row.get("own_box")
    if own is not None:                       # the same rule as baselines: whole, approved and explained
        try:
            good = set(own) == {*OWN_BOX, *OWN_BOX_BANDS, "approved_by", "approved_at", "basis"} \
                and all(type(own[k]) in (int, float) and own[k] > 0 for k in OWN_BOX) and all(own.values()) \
                and all(len(own[k]) == 2 and 0 < own[k][0] < own[k][1] for k in OWN_BOX_BANDS)
        except (KeyError, TypeError):
            good = False
        if not good or base is not None:
            raise CategoryDefaultsInvalid(
                f"{where}: own_box needs {', '.join(OWN_BOX)} (numbers > 0), {', '.join(OWN_BOX_BANDS)} ([min, max], "
                "0 < min < max), approved_by, approved_at and basis, and nothing else; never beside baselines")
    _check_fields(where, row.get("fields"))
    _check_compose(where, row.get("compose_by_count"))
    for kind in row.get("kinds") or []:
        named = f"{where} kind {kind.get('kind')}"
        if not kind.get("kind") or not kind.get("basis") or set(kind) - {"kind", "match", "alone", "unless",
                                                                          "strong", "always", "lofts", "fields",
                                                                          "basis"}:
            raise CategoryDefaultsInvalid(f"{named}: needs kind, match, fields and basis (alone, unless, strong, "
                                          "always, lofts optional)")
        span = kind.get("lofts")
        if span is not None and not (isinstance(span, list) and len(span) == 2
                                     and all(type(n) is int for n in span) and 2 <= span[0] <= span[1]):
            raise CategoryDefaultsInvalid(f"{named}: lofts must be [min, max], whole numbers, 2 <= min <= max")
        try:
            for key in ("match", "alone", "unless", "strong", "always"):
                if kind.get(key) is not None:
                    re.compile(kind[key])
            re.compile(kind["match"])
        except (KeyError, TypeError, re.error) as e:
            raise CategoryDefaultsInvalid(f"{named}: match / alone / unless must be regular expressions: {e}") \
                from None
        _check_fields(named, kind.get("fields"))


# the optional `compose_by_count` block (50002783, 2026-11-17; description_measures.compose_by_count reads it)
COMPOSE_KEYS = {"item_g", "writes", "confidence", "count_from", "skip", "approved_by", "approved_at", "basis"}
COMPOSE_CONFIDENCE = ("labelled_sum", "one_weight_times_count")
COMPOSE_COUNT_FROM = ("variant", "title_if_one_count")
COMPOSE_SKIPS = ("reference_club", "amazon_item_weight", "more_values_than_count", "mixed_gender",
                 "title_lofts_over_variant", "held", "single_club")


def _check_compose(where: str, block: Any) -> None:
    """The composition of a set's weight from its clubs' weights: the listed keys only, approved and explained; an
    item band 0 < min < max; it writes product_weight_g only (a box is never raised by it: PGM's 8 lofts x 462 g)."""
    if block is None:
        return
    try:
        good = set(block) == COMPOSE_KEYS and all(block[k] for k in ("approved_by", "approved_at", "basis")) \
            and 0 < block["item_g"]["min"] < block["item_g"]["max"] and block["writes"] == ["product_weight_g"] \
            and set(block["confidence"]) == set(COMPOSE_CONFIDENCE) \
            and all(type(c) is int and 1 <= c <= 3 for c in block["confidence"].values()) \
            and block["count_from"] and set(block["count_from"]) <= set(COMPOSE_COUNT_FROM) \
            and set(block["skip"]) <= set(COMPOSE_SKIPS)
    except (KeyError, TypeError):
        good = False
    if not good:
        raise CategoryDefaultsInvalid(
            f"{where}: compose_by_count needs {', '.join(sorted(COMPOSE_KEYS))} and nothing else: item_g {{min, max}} "
            f"(0 < min < max), writes [product_weight_g], confidence {{{', '.join(COMPOSE_CONFIDENCE)}}} (1-3), "
            f"count_from of {', '.join(COMPOSE_COUNT_FROM)}, skip of {', '.join(COMPOSE_SKIPS)}")


def _check_fields(where: str, fields: Any) -> None:
    for name in FIELDS:
        v = (fields or {}).get(name) or {}
        try:
            if not 0 < v["low"] <= v["central"] <= v["high"]:
                raise CategoryDefaultsInvalid(f"{where}: {name} must be 0 < low <= central <= high")
        except (KeyError, TypeError):
            raise CategoryDefaultsInvalid(f"{where}: {name} needs numbers low, central, high") from None


# an age, a height, a size, a loft or a year next to a club word is not a count of clubs (2026-11-12, junior clubs:
# "골프클럽 6~8세 드라이버" read as "클럽 6", three single GB clubs of 21-34,000 KRW took the set's box, $709-719;
# "웨지 클럽 56도웨지" the same, $729): taken out of the words before the kinds are read
_MEASURE = re.compile(r"\d+\s*(?:[~\-]\s*\d+\s*)?(?:세(?:\s*이상|\s*부터)?|cm|센치|mm|도|°|사이즈|size|년)"
                      r"|(?<!\d)20\d\d(?!\d)", re.I)


def _measure_words(text: str | None) -> str:
    return _MEASURE.sub(" ", text or "")


# A wedge's loft in a variant's value (44-72): "52 56 degree (2PCS)", "G 52도 + S 56도 + L 60도", "Black Set (52 56
# 60)", "Layer-50/56". Not a range ("52-56", "50~54": no count), a count or a size ("52개", "56cm", "60g"), nor
# glued ("5256"). 2026-11-17 (the W8 review, 50002783): "세" is an age ("6~8세"), never "세트" ("왼손 52 56 60 세트",
# "52/56세트" read 2 and 1); a dash after a model code is no range ("LH01-52 56 60 Degree" read 2): the range guard
# wants a number of one or two digits with no letter before it. A loft counts when it carries 도 / ° / degree or
# stands in a run of lofts (only separators and a letter or two between them, "52Y 56Y"): a lone bare number is a
# shaft's weight or flex ("50도 / Diamana 60 S", "52도 / 스틸파이버 / i70 A", "60 normal / 48°/52°/56°").
_LOFT = re.compile(r"(?<![\d.])(?<!(?<![A-Za-z])\d\d[~\-])(?<!(?<![A-Za-z\d])\d[~\-])(?<!\d\s[~\-])"
                   r"(4[4-9]|[56]\d|7[0-2])(?![\d.])(?!\s*[~\-]\s*\d)"
                   r"(?!\s*(?:g(?![a-z])|그램|개|종|cm|mm|kg|세(?!트)|%|원|만|p(?![a-z])|pcs|피스|자루|본|인치|inch|\"))", re.I)
_LOFT_MARK = re.compile(r"\s*(?:도|°|˚|deg)", re.I)
_LOFT_GAP = re.compile(r"[A-Za-z]{0,2}\s*(?:도|°|˚|deg(?:ree)?s?)?\s*[/,+&\-·\s]*\s*[A-Za-z]{0,2}\s*", re.I)


def lofts(text: str | None) -> int:
    """How many distinct lofts a variant's value names (read before _measure_words, which drops "52도"): a number
    marked as a loft, or a bare one next to another loft (_LOFT's comment)."""
    text = text or ""
    found = list(_LOFT.finditer(text))
    out: set[str] = set()
    for i, m in enumerate(found):
        gaps = ([text[found[i - 1].end():m.start()]] if i else []) + \
               ([text[m.end():found[i + 1].start()]] if i + 1 < len(found) else [])
        if _LOFT_MARK.match(text, m.end()) or any(_LOFT_GAP.fullmatch(g) for g in gaps):
            out.add(m.group(1))
    return len(out)


def default_kind(row: Mapping[str, Any], title: str | None, variant_name: str | None,
                 siblings: Sequence[str | None] | None = None) -> dict[str, Any] | None:
    """The row's kind of product (`kinds`) a variant is, for its defaults; None: the row's own fields. The title and
    the variant's words are read apart (glued, "...클럽" + "6~8세" read as "클럽 6", a count). A kind is taken when
`always` is in the variant's own words (단품: sold alone, whatever the title says); when
    `alone` is in the variant's own words, `unless` is not, and the title has no `strong` word (a variant that names
    one club of a "퍼터 클럽 세트" listing is that club; of a 풀세트 it is the set's choice); or when `match` is in the
    title or the variant and `unless` in neither (the owner, 2026-11-11: a single junior club gets a single club's
    box, a set the set's; in doubt the set's, the larger, box).
    A kind with `lofts` [min, max] counts a set (50002783 two_wedges / four_plus, 2026-11-17): the variant's own
    count first, its `match` or that many distinct lofts in its value (lofts()); a variant naming two or more lofts
    of another count is never the title's. Else the title's `match`, only when the listing has one variant or every
    variant (`siblings`: all the variants' values; None: not known) names as many lofts. `unless` in either blocks.
    2026-11-25 (the owner, 50002816 rainwear): `unless` is searched in the title and in the variant apart, so a `^`
    look-ahead reads one whole text ("names one coat or cape and no second garment": 레인슈트 typed as a search keyword
    on a coat is no suit), and a `match` may refuse a word by what stands before it (선물세트, 웨이스트백 세트)."""
    t, v = _measure_words(title), _measure_words(variant_name)
    own_lofts = lofts(variant_name)

    def has(key: str, text: str) -> bool:
        return bool(kind.get(key)) and re.search(kind[key], text) is not None
    for kind in row.get("kinds") or []:
        if has("always", v) or has("alone", v) and not has("unless", v) and not has("strong", t):
            return dict(kind)
        blocked = has("unless", t) or has("unless", v)
        span = kind.get("lofts")
        if span:
            if blocked:
                continue
            if has("match", v) or span[0] <= own_lofts <= span[1]:
                return dict(kind)
            alike = siblings is None or len(siblings) <= 1 or len({lofts(s) for s in siblings}) == 1
            if has("match", t) and own_lofts < 2 and alike:
                return dict(kind)
            continue
        if (has("match", t) or has("match", v)) and not blocked:
            return dict(kind)
    return None


def current_defaults(fields: dict[str, Any], specs: Mapping[str, Any], variant_id: str | None,
                     table: dict[str, Any]) -> dict[str, Any]:
    """A collected variant's fields with each category default as today's table gives it (the transform, 2026-11-11):
    a kept run is never rewritten, so a row changed after the collection (a new `kinds` entry, other low / central /
    high) reaches the product when it is prepared again. A default whose numbers and kind are today's is kept as it
    was collected (its table_version too: nothing changes for a product the change does not touch); a seller's value
    is never touched."""
    category = specs.get("category") or {}
    row = next((r for r in table.get("rows", []) if str(r["category_id"]) == str(category.get("id"))), None)
    if row is None:
        return fields
    name_of = {v.get("id"): v.get("name") for v in ((specs.get("options") or {}).get("variants") or [])}
    kind = default_kind(row, specs.get("name"), name_of.get(variant_id), list(name_of.values()))
    defaults = kind["fields"] if kind else row["fields"]
    out = dict(fields)
    for name, f in fields.items():
        if not isinstance(f, dict) or f.get("source") != "category_default" or name not in defaults:
            continue
        today = defaults[name]
        if all(f.get(k) == today[k] for k in ("low", "central", "high")) and f.get("kind") == (kind or {}).get("kind"):
            continue
        out[name] = {**{k: v for k, v in f.items() if k != "kind"}, **today,
                     **({"kind": kind["kind"]} if kind else {}), "table_version": row_version(table, row),
                     "approved_by": row["approved_by"], "approved_at": row["approved_at"]}
    return out


def current_bands(fields: dict[str, Any], specs: Mapping[str, Any], variant_id: str | None,
                  table: dict[str, Any]) -> dict[str, Any]:
    """A collected variant's seller values against today's band of its row (`plausible`), as variant_measures checks
    them at collection: a value outside is not taken (`contradiction`, `reason: implausible_for_category`; one side of
    a box out refuses the three, `box_not_whole`) and today's default fills the field. 2026-11-18, the chipper row's
    band came after its 59 collections: 7004743758's notice "중량: 962g" (an import's shipping weight) stayed the
    product weight; a band, like a default (current_defaults), reaches the product when it is prepared again. A value
    inside the band, a row without one: unchanged."""
    category = specs.get("category") or {}
    row = next((r for r in table.get("rows", []) if str(r["category_id"]) == str(category.get("id"))), None)
    bands = (row or {}).get("plausible") or {}
    out_of = [name for name, band in bands.items() if (f := fields.get(name)) and f.get("source") == "source_stated"
              and "value" in f and not band["min"] <= f["value"]["min"] <= f["value"]["max"] <= band["max"]]
    if not out_of or row is None:
        return fields
    reasons = {name: "implausible_for_category" for name in out_of}
    if any(name in SIDES for name in out_of):
        reasons.update({name: "box_not_whole" for name in SIDES if name not in reasons
                        and (fields.get(name) or {}).get("source") == "source_stated"})
    name_of = {v.get("id"): v.get("name") for v in ((specs.get("options") or {}).get("variants") or [])}
    kind = default_kind(row, specs.get("name"), name_of.get(variant_id), list(name_of.values()))
    out = dict(fields)
    for name, reason in reasons.items():
        out[name] = {**default_field(row, kind, row_version(table, row), name),
                     "contradiction": [{k: v for k, v in fields[name].items() if k != "also"}], "reason": reason}
    return out


# ---- a weight the listing states once, against the variant's count of clubs (2026-11-17, the resend review D1) ----
# A weight written once for the whole listing (a product-scope row of the server, a line of the description) lands
# on every variant; on a set-or-pair listing it is one count's figure: Yamato 13164555233's "Package Weight : 1.13
# Kilograms" (a pair's) on its 3-wedge sets, Mile High Life 12178280377's 1610 g (its 3-wedge set's) on its pairs,
# Majek 13383747280's "Item Weight : 4 Pounds" (1814 g, its 3-piece's: 13312228253, 13468925033) on a 2-piece. On a
# row with count kinds (`lofts`) and `compose_by_count`, a stated weight of n clubs is plausible from n x the club's
# lowest weight (item_g.min, 380 g: 760 for two, 1140 for three) to the count's kind's high (the base row's for the
# count no kind spans, 3: two_wedges 1100 / 2200, base 2800 / 3800, four_plus 2800 / 3600), or up to n + 1 clubs'
# lowest when that is more (Yamato's 2-packs state 1.11 and 1.13 kg: 13406052242, 13372272290; two_wedges' product
# band 760-1140). The count: the kind's
# (`lofts` [min, ...]; the variant's own when inside it); for the base row the variant's own (that many lofts, one
# count word); not known: no band. Never the title's: agency titles are cut ("마제크 ... 컴플리트 세트 52° 갭
# 웨지GW 56° 샌드", 13383747280, is the 3-piece of UPC 792713116504 with 13312228253 / 13468925033, its 1814 g right;
# Ram 13386317152 "스핀3 웨지세트 - 52° 간격 56° 모래 6") or list a menu ("52 56 60 72도 세트", 13372037781).
WEIGHTS = ("product_weight_g", "package_weight_g")
_COUNT_WORD = re.compile(r"(?i)(?<![0-9])([2-9])\s*(?:개|종|pcs?|p(?![a-z])|피스|자루|본|piece|wedges?)")


def _own_count(text: str | None) -> int:
    """The clubs a text counts: its distinct lofts when two or more, else its one count word ("3PCS", "2개"); 0."""
    n = lofts(text)
    words = {int(m.group(1)) for m in _COUNT_WORD.finditer(_measure_words(text))}
    return n if n >= 2 else words.pop() if len(words) == 1 else 0


def package_kind(row: Mapping[str, Any], fields: Mapping[str, Any], title: str | None, variant_name: str | None,
                 siblings: Sequence[str | None] | None = None) -> dict[str, Any] | None:
    """The kind whose defaults the variant's package carries (a category default's `kind`; none: the base row),
    else default_kind() when no field is a default."""
    named = [f.get("kind") for f in fields.values() if isinstance(f, dict) and f.get("source") == "category_default"]
    if named:
        return next((dict(k) for k in row.get("kinds") or [] if k["kind"] == named[0]), None)
    return default_kind(row, title, variant_name, siblings)


def count_kind(row: Mapping[str, Any], kind: Mapping[str, Any] | None,
               variant_name: str | None) -> tuple[int, dict[str, Any] | None] | None:
    """(n clubs, the variant's kind: None for the base row) of a variant of `kind` (package_kind), for count_band;
    None: the row counts no clubs, the kind is no count (single_club) or the base row's count is not named."""
    spans = [k for k in row.get("kinds") or [] if k.get("lofts")]
    if not spans or not row.get("compose_by_count"):
        return None
    own = _own_count(variant_name)
    if kind is not None:
        if not kind.get("lofts"):
            return None
        return (own if kind["lofts"][0] <= own <= kind["lofts"][1] else kind["lofts"][0]), dict(kind)
    covered = {c for k in spans for c in range(k["lofts"][0], k["lofts"][1] + 1)}
    base = {c for c in range(2, max(k["lofts"][1] for k in spans) + 1) if c not in covered}     # {3}
    return (own, None) if own in base else None


def count_band(row: Mapping[str, Any], counted: tuple[int, dict[str, Any] | None] | None
               ) -> dict[str, tuple[float, float]]:
    """{weight field: (low, high)} plausible for that many clubs (the comment above); {}: no count."""
    if not counted:
        return {}
    n, kind = counted
    fields = (kind or row)["fields"]
    club = row["compose_by_count"]["item_g"]["min"]
    return {name: (n * club, max(fields[name]["high"], (n + 1) * club)) for name in WEIGHTS if name in fields}


def default_field(row: Mapping[str, Any], kind: Mapping[str, Any] | None, version: Any, name: str) -> dict[str, Any]:
    """One field's category default as variant_measures writes it (the kind's numbers when a kind is given)."""
    defaults = kind["fields"] if kind else row["fields"]
    return {**defaults[name], "source": "category_default", "confidence": 1, **({"kind": kind["kind"]} if kind else {}),
            "reliability": row["reliability"], "table_version": version,
            "approved_by": row["approved_by"], "approved_at": row["approved_at"]}


def off_count(fields: dict[str, Any], band: Mapping[str, tuple[float, float]], row: Mapping[str, Any],
              kind: Mapping[str, Any] | None, version: Any) -> tuple[dict[str, Any], list[str]]:
    """The seller's product-scope weights (binding `product`: the listing's one statement) outside the count's band
    put back to the category default (`compared` the refused one, `rejected: implausible_for_count`) -> (fields,
    the names put back). A weight bound to the variant stays."""
    out, back = dict(fields), []
    for name, (low, high) in band.items():
        f = fields.get(name) or {}
        if f.get("source") != "source_stated" or (f.get("binding") or {}).get("scope") != "product" \
                or low <= f["value"]["max"] <= high:
            continue
        brief = {k: f[k] for k in ("source", "confidence", "from", "quote") if k in f}
        out[name] = {**default_field(row, kind, version, name),
                     "compared": {**brief, "value": f["value"]["max"], "rejected": "implausible_for_count"}}
        back.append(name)
    return out, back


def _belongs(candidate: dict[str, Any], variant_id: str | None) -> bool:
    binding = candidate.get("binding") or {}
    return binding.get("scope") == "product" or (binding.get("scope") == "variants"
                                                 and variant_id in binding.get("variant_ids", []))


INFERRED = {"bound_by_count_rank", "multiplied"}        # the value is stated, its binding / total worked out
OWN_KIND = {"product_weight_g": "net", "package_weight_g": "packed"}   # the sides come from packed boxes only


def confidence(field: str, c: dict[str, Any]) -> int:
    """5: stated with its kind; 4: stated, kind left open or the binding / total worked out (the scale is 1-5
    since 2026-11-10: the module's docstring)."""
    if INFERRED & set(c.get("flags") or []):
        return 4
    return 5 if c.get("kind") == OWN_KIND.get(field, "packed") else 4


def on_scale(fields: dict[str, Any]) -> dict[str, Any]:
    """A collected line's fields on today's scale: a seller's value (a contradiction's too) gets the confidence
    its own kind and flags give now. Lines collected before 2026-11-10 carry 1-3, and a prepared record must not
    mix the two scales (13389271367's typed box: 3 then, 5 now); a default is 1 on both, also on a line collected
    before the fields carried a confidence (2026-11-06)."""
    def level(name: str, f: dict[str, Any]) -> dict[str, Any]:
        f = {**f, "contradiction": [level(name, c) for c in f["contradiction"]]} if "contradiction" in f else f
        return {**f, "confidence": confidence(name, f)} if f.get("source") == "source_stated" else \
            {**f, "confidence": 1} if f.get("source") == "category_default" else f
    return {name: level(name, f) for name, f in fields.items()}


def _evidence(c: dict[str, Any], value: dict[str, float], field: str = "") -> dict[str, Any]:
    return {"value": value, "source": "source_stated", "confidence": confidence(field, c), "quote": c["quote"],
            "from": c["source"],
            "locator": c["locator"], "kind": c["kind"], "scope": c.get("scope"),
            "approximate": c.get("approximate", False), "flags": c.get("flags", []), "binding": c["binding"],
            **({"count": c["count"]} if c.get("count") else {})}


def _agree(values: list[dict[str, float]]) -> bool:
    return max(v["min"] for v in values) <= min(v["max"] for v in values) * 1.02      # 6.35 kg = 14 lb (6350.3 g)


def _pick(field: str, found: list[tuple[dict[str, Any], dict[str, float]]]) -> dict[str, Any] | None:
    """The first candidate (the most certain one first), or a contradiction note when they disagree."""
    if not found:
        return None
    if not _agree([v for _, v in found]):
        return {"contradiction": [_evidence(c, v, field) for c, v in found]}
    c, v = max(found, key=lambda f: confidence(field, f[0]))    # max keeps the first of equals
    return {**_evidence(c, v, field), "also": len(found) - 1}


def stated(measures: Mapping[str, Any], variant_id: str | None) -> dict[str, dict[str, Any]]:
    """The seller's values of the five fields for one variant (fields with none are left out)."""
    weights = [c for c in measures.get("weights", []) if _belongs(c, variant_id)]
    sizes = [c for c in measures.get("dimensions", []) if _belongs(c, variant_id)]
    product = [(c, c["value"]) for c in weights if c["kind"] in ("net", "unknown") and c["scope"] != "unit"
               and (c["scope"] == "set" or not measures.get("is_set"))]
    found = {"product_weight_g": product,
             "package_weight_g": [(c, c["value"]) for c in weights if c["kind"] == "packed"]}
    boxes = [c for c in sizes if c["kind"] == "packed" and len(c["values"]) == 3]
    for i, name in enumerate(SIDES):
        found[name] = [(c, {"min": s, "max": s}) for c in boxes for s in [sorted(c["values"], reverse=True)[i]]]
    return {name: picked for name, picked in ((n, _pick(n, f)) for n, f in found.items()) if picked}


def variant_measures(specs: Mapping[str, Any], table: dict[str, Any]) -> list[dict[str, Any]]:
    """[{variant_id, fields: {name: seller evidence | category default}, product_size}] per variant (one entry with
    variant_id null for a product without variants). Raises CategoryDefaultsMissing when a field needs the table and
    the leaf category has no row."""
    measures = specs.get("measures") or {}
    variants = [v.get("id") for v in ((specs.get("options") or {}).get("variants") or [])] or [None]
    category = specs.get("category") or {}
    row = next((r for r in table.get("rows", []) if str(r["category_id"]) == str(category.get("id"))), None)
    out = []
    names = {v.get("id"): v.get("name") for v in ((specs.get("options") or {}).get("variants") or [])}
    for variant_id in variants:
        kind = default_kind(row, specs.get("name"), names.get(variant_id), list(names.values())) if row else None
        fields: dict[str, Any] = stated(measures, variant_id)
        for name, band in ((row or {}).get("plausible") or {}).items():
            f = fields.get(name)
            if f and "value" in f and not band["min"] <= f["value"]["min"] <= f["value"]["max"] <= band["max"]:
                fields[name] = {"contradiction": [{k: v for k, v in f.items() if k != "also"}],
                                "reason": "implausible_for_category"}
        # a box is one statement: one side out of its band refuses the three (as description_measures.merge_fields;
        # 13372006463's one-wedge box 37.2 x 2 x 1 in on a set's page must not leave 945 x 51 mm beside a default)
        if any(fields.get(name, {}).get("reason") == "implausible_for_category" for name in SIDES):
            for name in SIDES:
                f = fields.get(name)
                if f and "value" in f:
                    fields[name] = {"contradiction": [{k: v for k, v in f.items() if k != "also"}],
                                    "reason": "box_not_whole"}
        for name in FIELDS:
            if name in fields and "contradiction" not in fields[name]:
                continue
            if row is None:
                raise CategoryDefaultsMissing(category.get("id"), category.get("name"))
            fields[name] = {**default_field(row, kind, row_version(table, row), name),
                            **({k: fields[name][k] for k in ("contradiction", "reason") if k in fields[name]}
                               if name in fields else {})}
        product, package = fields["product_weight_g"], fields["package_weight_g"]
        if product["source"] == "source_stated" and package["source"] == "category_default" \
                and package["central"] < product["value"]["max"]:
            package["flags"] = ["below_stated_product"]      # 6630856593: 7000 g default, 11.5 kg stated
        product_size = [c for c in measures.get("dimensions", []) if _belongs(c, variant_id)
                        and c["kind"] in ("product", "unknown")]          # sizes not marked as the package
        out.append({"variant_id": variant_id, "fields": {n: fields[n] for n in FIELDS}, "product_size": product_size})
    return out
