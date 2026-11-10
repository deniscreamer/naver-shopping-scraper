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
weight below the seller's own product weight is flagged `below_stated_product` (kept: the operator decides). A row
may carry `plausible: {field: {min, max}}`, the operator's band: a stated value outside it is not taken
(contradiction, reason implausible_for_category) and the default fills the field. No band is made up here: without
one, every stated value is taken. A row may also carry `baselines`, the operator's amounts for the parts of a set
of like items in a container (BASELINES: one item, the container, the carton, the longest item, the box's length
over it; BASELINE_SIDES: the box's width and height without the container and with it; approved_by, approved_at,
basis). With them description_measures.py composes a field the seller does not state from the set's parts, each
part from the product's own data when it is there and from the baseline when it is not; the flat default is then
the last resort. No amount is made up in code; a row without the block gets no composition. `reliability` today
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
from collections.abc import Mapping
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


class CategoryDefaultsMissing(Exception):
    """No operator values for this leaf category: stop the category and ask the operator."""

    def __init__(self, category_id: str | None, category_name: str | None = None):
        super().__init__(f"no package averages for category {category_id} ({category_name or '?'}) in "
                         f"category_measures.json: ask the operator for low / central / high of {', '.join(FIELDS)}")
        self.category_id = category_id


class CategoryDefaultsInvalid(Exception):
    """A table row is incomplete or out of order (low <= central <= high)."""


def load_table(path: str = TABLE) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        table = json.load(f)
    for row in table.get("rows", []):
        check_row(row)
    return table


def check_row(row: dict[str, Any]) -> None:
    where = f"category {row.get('category_id')}"
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
    for name in FIELDS:
        v = (row.get("fields") or {}).get(name) or {}
        try:
            if not 0 < v["low"] <= v["central"] <= v["high"]:
                raise CategoryDefaultsInvalid(f"{where}: {name} must be 0 < low <= central <= high")
        except (KeyError, TypeError):
            raise CategoryDefaultsInvalid(f"{where}: {name} needs numbers low, central, high") from None


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
    for variant_id in variants:
        fields: dict[str, Any] = stated(measures, variant_id)
        for name, band in ((row or {}).get("plausible") or {}).items():
            f = fields.get(name)
            if f and "value" in f and not band["min"] <= f["value"]["min"] <= f["value"]["max"] <= band["max"]:
                fields[name] = {"contradiction": [{k: v for k, v in f.items() if k != "also"}],
                                "reason": "implausible_for_category"}
        for name in FIELDS:
            if name in fields and "contradiction" not in fields[name]:
                continue
            if row is None:
                raise CategoryDefaultsMissing(category.get("id"), category.get("name"))
            fields[name] = {**row["fields"][name], "source": "category_default", "confidence": 1,
                            "reliability": row["reliability"],
                            "table_version": table["version"],
                            "approved_by": row["approved_by"], "approved_at": row["approved_at"],
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
