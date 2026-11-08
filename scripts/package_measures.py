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
(The description images' guess, description_measures.py, does sum the clubs, plus a bag weight the images state,
as a lower bound compared with these fields in the transform: the owner, 2026-11-07, the larger wins.)

A field the seller does not give is filled from the category table (low / central / high, its version, who approved
it and its reliability level), `source: category_default`; a seller's value is never overwritten. A default package
weight below the seller's own product weight is flagged `below_stated_product` (kept: the operator decides). A row
may carry `plausible: {field: {min, max}}`, the operator's band: a stated value outside it is not taken
(contradiction, reason implausible_for_category) and the default fills the field. No band is made up here: without
one, every stated value is taken. `reliability` today has one level, `estimated_average` (the weakest: an average of
estimates, not measured); delivery will apply its own coefficient per level.

No table row for the product's leaf category: CategoryDefaultsMissing. The run stops that category and asks the
operator for its values; they are never made up. Product sizes (not the package) are kept apart and optional.
Each field carries `confidence` (the owner, 2026-11-06): 3 = the seller states it and says what it is (a net weight,
a weight with the package, the box's sides); 2 = the seller states it but leaves its kind open (a plain "중량 11.5kg":
with or without the box is not said), or it was bound to the variant by club count, or worked out (a per-piece
weight times the count); 1 = the category default. The evidence (source, quote, kind, scope, binding, flags,
contradiction) travels with it.

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
    """3: stated with its kind; 2: stated, kind left open or the binding / total worked out."""
    if INFERRED & set(c.get("flags") or []):
        return 2
    return 3 if c.get("kind") == OWN_KIND.get(field, "packed") else 2


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
