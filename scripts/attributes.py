"""Neutral product attributes for the shops' placement (placement.py): what the seller states, with its evidence,
no shop's collections (the owner, 2026-11-08: a shop is split into its sections at the last stage before Shopify,
by the shop's profile, not while a job collects). One Naver category id can hold what a shop sells in two sections
(50002788 풀세트: men's and women's sets); the attribute is the seller's statement that splits it.

An attribute is data (ATTRIBUTES): values and their words, the 상품정보 rows that state it, what a value implies
(unisex: both). A new kind of split (another category, another attribute) is a new entry here and a profile entry in
placement_rules.py, no code. Every product gets every attribute it states; placement reads only the one its profile
names.

How a value is decided (gender, checked 2026-11-08 on the 143 trial sets):

  variants  the words in each sold variant's option values ("여성용 10.5도 L" -> womens): the most specific;
            a product whose variants carry both genders is `mixed`, each variant keeps its own value
  row       the 상품정보 row (성별: "남성용" / "여성용" / "남녀공용"): the seller's declared value for the product
  title     words in the product's name ("여성", "레이디스", "LADIES")
  listing   the search the product was listed under (a job's query): never decides, only checked against

The variants decide when any of them names a value; a variant naming none takes the product's own value (row, else
title) when that is one gender; when the product's own value is unisex or none and the variants mark one gender
only, the unmarked ones are the other (a seller marks "(여성용)" beside the plain men's model). With no variant naming one: the row, else the title. Disagreement: a row and a title that name opposite
values, or variants naming only the opposite of the row, is `conflict`; nothing names a value: `unknown`. The
listing's query naming the opposite of the value adds the flag `listing_disagrees` (evidence, not a veto). No value
is guessed from a shaft flex, a colour or a model: a word must say it.

    from attributes import extract
    extract(variants, rows, title, listing_query) -> {"gender": {value, variants, evidence, flags}}
"""
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Attribute:
    name: str
    words: dict[str, tuple[str, ...]]            # value -> the words that state it (longest matched first)
    rows: tuple[str, ...] = ()                   # 상품정보 labels that state it
    implies: dict[str, tuple[str, ...]] = field(default_factory=dict)   # unisex -> (mens, womens)
    opposite: dict[str, str] = field(default_factory=dict)              # a value and the one it excludes


GENDER = Attribute(
    "gender",
    words={
        "unisex": ("남녀공용", "남여공용", "남녀", "남여", "공용", "유니섹스", "UNISEX"),
        "womens": ("여성용", "여성", "여자", "레이디스", "레이디", "WOMEN'S", "WOMENS", "WOMEN", "LADIES", "LADY"),
        "mens": ("남성용", "남성", "남자", "MEN'S", "MENS", "MEN"),
    },
    rows=("성별",),
    implies={"unisex": ("mens", "womens")},
    opposite={"mens": "womens", "womens": "mens"},
)
ATTRIBUTES = {a.name: a for a in (GENDER,)}


def _compiled(attr: Attribute) -> list[tuple[re.Pattern[str], str]]:
    pairs = [(w, v) for v, ws in attr.words.items() for w in ws]
    pairs.sort(key=lambda p: -len(p[0]))
    # a Latin word stands alone ("MEN" not inside "WOMEN" / "MENTOR"); a Korean word anywhere
    return [(re.compile(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])" if w.isascii() else re.escape(w), re.I), v)
            for w, v in pairs]


_PATTERNS = {name: _compiled(a) for name, a in ATTRIBUTES.items()}


def values_in(attr: Attribute, text: str | None) -> list[str]:
    """The values a text names, in order, a matched span never matched again ("남녀공용" is unisex, not also 남녀)."""
    text = text or ""
    taken: list[tuple[int, int]] = []
    found: list[tuple[int, str]] = []
    for pattern, value in _PATTERNS[attr.name]:
        for m in pattern.finditer(text):
            if not any(s < m.end() and m.start() < e for s, e in taken):
                taken.append((m.start(), m.end()))
                found.append((m.start(), value))
    return list(dict.fromkeys(v for _, v in sorted(found)))


def _one(attr: Attribute, values: list[str]) -> str | None:
    """One value for a set the text named: one value, or the value that implies them all (남녀 -> unisex)."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    for v, implied in attr.implies.items():
        if set(values) <= {v, *implied}:
            return v
    return "conflict"


def _covers(attr: Attribute, value: str | None) -> set[str]:
    return set(attr.implies.get(value, (value,))) if value else set()


def decide(attr: Attribute, variants: list[tuple[str, list[str]]], rows: list[dict[str, Any]], title: str | None,
           listing_query: str | None = None) -> dict[str, Any]:
    """variants: [(sku, option values)]; rows: the page's 상품정보 rows ({label, value}) -> the attribute."""
    evidence: list[dict[str, str]] = []
    row = None
    for r in rows:
        if r.get("label") in attr.rows:
            row = _one(attr, values_in(attr, r.get("value")))
            if row:
                evidence.append({"source": f"row:{r['label']}", "value": row, "text": str(r.get("value"))[:80]})
    titled = _one(attr, values_in(attr, title))
    if titled:
        evidence.append({"source": "title", "value": titled, "text": (title or "")[:80]})
    own = row or (titled if titled != "conflict" else None)
    per_variant: dict[str, str] = {}
    for sku, values in variants:
        v = _one(attr, values_in(attr, " ".join(values)))
        if v and v != "conflict":
            per_variant[sku] = v
    if per_variant:
        evidence.append({"source": "variants", "value": ",".join(sorted(set(per_variant.values()))),
                         "text": f"{len(per_variant)} of {len(variants)} variants"})
    flags: list[str] = []
    if per_variant:
        named = set().union(*(_covers(attr, v) for v in per_variant.values()))
        marked = {v for v in per_variant.values() if v in attr.opposite}
        unmarked = own if own in attr.opposite else None
        if unmarked is None and len(marked) == 1 and set(per_variant.values()) == marked:
            # the seller marks one gender's variants only ("뉴GR-V 백포함 (여성용)" beside "뉴GR-V 백포함", the 성별
            # row 남녀공용: 8514409092): the unmarked ones are the other
            unmarked = attr.opposite[next(iter(marked))]
        variant_values = {sku: per_variant.get(sku, unmarked or own or "unknown") for sku, _ in variants}
        value: str | None
        if row and row in attr.opposite and named == {attr.opposite[row]}:
            value = "conflict"                                   # the row says one, every variant the other
        else:
            covered = set().union(*(_covers(attr, v) for v in variant_values.values() if v != "unknown"))
            value = _one(attr, sorted(covered)) if len(covered) <= 1 else (
                "unisex" if all(v == "unisex" for v in per_variant.values()) else "mixed")
    else:
        variant_values = {}
        value = row or titled
        if row and titled and titled != "conflict" and attr.opposite.get(row) == titled:
            value = "conflict"
    value = value or "unknown"
    if listing_query and value not in ("unknown", "conflict"):
        asked = _one(attr, values_in(attr, listing_query))
        if asked and asked in attr.opposite and _covers(attr, value) == {attr.opposite[asked]}:
            flags.append("listing_disagrees")
        evidence.append({"source": "listing", "value": asked or "-", "text": listing_query[:80]})
    return {"value": value, "variants": variant_values, "evidence": evidence, "flags": flags}


def extract(variants: list[tuple[str, list[str]]], rows: list[dict[str, Any]], title: str | None,
            listing_query: str | None = None) -> dict[str, dict[str, Any]]:
    """Every attribute the product states (an attribute nothing states is left out)."""
    out = {}
    for name, attr in ATTRIBUTES.items():
        got = decide(attr, variants, rows, title, listing_query)
        if got["value"] != "unknown" or got["evidence"]:
            out[name] = got
    return out
