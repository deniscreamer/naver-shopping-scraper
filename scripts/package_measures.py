"""Five shipping fields per variant, from the seller's candidates (/products/specs `measures`) or the operator's
category averages (category_measures.json). The owner's rules, 2026-11-05:

  product_weight_g    net or unspecified weight, never a part's (component); in a set only the whole set's
                      (scope set); a weight per piece (scope unit) is not the product's
  package_weight_g    a weight with the package (kind packed) only
  package_length_mm   a size triple marked as the package (kind packed); a triple without that mark is not the
  package_width_mm    package (not_confirmed_packed). The three sides are taken longest first (length >= width >=
  package_height_mm   height), whatever order the seller wrote

A candidate belongs to a variant when its binding is `product`, or `variants` with that variant's id; `context`
lines are not values. Candidates of one field that disagree (no common range) are a contradiction: the field is
not taken from the seller. A field the seller does not give is filled from the category table (low / central /
high, its version, who approved it and its reliability level), `source: category_default`; a seller's value is never
overwritten. `reliability` today has one level, `estimated_average` (the weakest: an average of estimates, not
measured); delivery will apply its own coefficient per level.

No table row for the product's leaf category: CategoryDefaultsMissing. The run stops that category and asks the
operator for its values; they are never made up. Product sizes (not the package) are kept apart and optional.
Confidence levels (0-3) are not computed here: each field keeps what they need (source, quote, kind, scope,
binding, contradiction).

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


def _evidence(c: dict[str, Any], value: dict[str, float]) -> dict[str, Any]:
    return {"value": value, "source": "source_stated", "quote": c["quote"], "from": c["source"],
            "locator": c["locator"], "kind": c["kind"], "scope": c.get("scope"),
            "approximate": c.get("approximate", False), "flags": c.get("flags", []), "binding": c["binding"]}


def _agree(values: list[dict[str, float]]) -> bool:
    return max(v["min"] for v in values) <= min(v["max"] for v in values)


def _pick(found: list[tuple[dict[str, Any], dict[str, float]]]) -> dict[str, Any] | None:
    """The first candidate, or a contradiction note when they disagree."""
    if not found:
        return None
    if not _agree([v for _, v in found]):
        return {"contradiction": [_evidence(c, v) for c, v in found]}
    c, v = found[0]
    return {**_evidence(c, v), "also": len(found) - 1}


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
    return {name: picked for name, picked in ((n, _pick(f)) for n, f in found.items()) if picked}


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
        for name in FIELDS:
            if name in fields and "contradiction" not in fields[name]:
                continue
            if row is None:
                raise CategoryDefaultsMissing(category.get("id"), category.get("name"))
            fields[name] = {**row["fields"][name], "source": "category_default", "reliability": row["reliability"],
                            "table_version": table["version"],
                            "approved_by": row["approved_by"], "approved_at": row["approved_at"],
                            **({"contradiction": fields[name]["contradiction"]} if name in fields else {})}
        product_size = [c for c in measures.get("dimensions", []) if _belongs(c, variant_id)
                        and c["kind"] in ("product", "unknown")]          # sizes not marked as the package
        out.append({"variant_id": variant_id, "fields": {n: fields[n] for n in FIELDS}, "product_size": product_size})
    return out
