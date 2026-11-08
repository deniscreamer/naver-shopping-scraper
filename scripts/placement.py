"""Placement: the last stage before Shopify (the owner, 2026-11-08). Each prepared product of a shop -> the shop's
sections it goes to (collection handle, product type, tags), from the shop's profile (placement_rules.py) and the
product's neutral attributes (attributes.py, written by the transform). Pure over the files: no network, no Shopify
write; publication (later) reads its output.

Why here and not in the transform: one Naver category id can be several of the shop's sections (50002788 풀세트:
men's and women's sets), another shop may split it otherwise or not at all, and a profile may change after the
products were collected; the transform states what the seller says, placement decides what the shop does with it.

Per product, by its Naver category's placement:
  * no split (leaves[None]): that section;
  * split by an attribute: each value's section; a value implying others (unisex, stated: men's and women's) and a
    product whose variants carry several (`mixed`) go to each of their sections. Still ONE Shopify product shown in
    several collections (the leaf tags of all its sections; card, variants and stock shared, never a second copy);
    a section whose variants are only part of the card gets a start-variant hint (`start_variants`: from the men's
    collection the men's variant opens), never a removal of the other variants. An unknown value is not unisex;
  * the attribute unknown or in conflict: `unresolved` (the profile's "hold": not placed, the reason and the evidence
    listed for the owner / the agent; or its fallback section);
  * a held product (transform) is not placed; a category with no placement: `no_profile`.

    .venv/bin/python scripts/placement.py fairwardgolf [--shops-root DIR]

Files, shops/<shop>/placement/:
    placements.jsonl   {key, status: placed | unresolved | held | no_profile, tags (all its sections', for the one
                       Shopify product), product_type (the primary section's: the most variants, then profile order),
                       start_variants {leaf: sku} (for publication: the metafield of start variants per collection),
                       leaves: [{leaf, product_type, tags, fit_skus, start_sku}], attribute, value, reason, evidence,
                       flags}, sorted by key, rebuilt each run
    report.txt         counts per status and section, the unresolved ones with why
"""
import argparse
import json
import os
import sys
from collections import Counter
from typing import Any

import attributes as A
from keep_run import SHOPS_ROOT
from placement_rules import CategoryPlacement, PlacementProfile, PlacementRulesMissing, profile_for

FORMAT = "placement/1"


def _leaf(profile: PlacementProfile, cat: CategoryPlacement, value: str | None, fit: list[str],
          every: list[str]) -> dict[str, Any]:
    leaf = cat.leaves[value]
    shop = profile.shop.value
    return {"leaf": leaf.handle, "product_type": leaf.product_type,
            "tags": [t.format(shop=shop, leaf=leaf.handle, parent=cat.parent) for t in profile.tags],
            "fit_skus": fit, "start_sku": fit[0] if fit and fit != every else None}


def _placed(out: dict[str, Any], leaves: list[dict[str, Any]], **more: Any) -> dict[str, Any]:
    """One Shopify product for all its sections: the union of their tags, the primary section's product type, a
    start variant per section that shows only part of the card."""
    primary = max(leaves, key=lambda x: len(x["fit_skus"]))            # max keeps the first (profile order) on ties
    return {**out, **more, "status": "placed", "leaves": leaves,
            "tags": list(dict.fromkeys(t for x in leaves for t in x["tags"])), "product_type": primary["product_type"],
            "start_variants": {x["leaf"]: x["start_sku"] for x in leaves if x["start_sku"]}}


def place(prepared: dict[str, Any], profile: PlacementProfile) -> dict[str, Any]:
    """One prepared product -> its placement."""
    out: dict[str, Any] = {"format": FORMAT, "key": prepared["key"], "leaves": [], "tags": [], "product_type": None,
                           "start_variants": {}, "attribute": None, "value": None, "reason": None, "evidence": [],
                           "flags": []}
    if prepared.get("status") != "ready":
        return {**out, "status": "held", "reason": ",".join(h["code"] for h in prepared.get("held") or [])}
    product = prepared["product"]
    skus = [v["sku"] for v in product.get("variants") or []]
    try:
        cat = profile.category((prepared.get("source") or {}).get("category_id"))
    except PlacementRulesMissing as e:
        return {**out, "status": "no_profile", "reason": str(e)}
    if cat.split_by is None:
        return _placed(out, [_leaf(profile, cat, None, skus, skus)])
    attr = A.ATTRIBUTES[cat.split_by]
    stated = (product.get("attributes") or {}).get(cat.split_by) or {"value": "unknown", "variants": {},
                                                                    "evidence": [], "flags": []}
    value = stated["value"]
    out.update(attribute=cat.split_by, value=value, evidence=stated.get("evidence") or [],
               flags=stated.get("flags") or [])

    def sections(v: str | None) -> list[str]:
        return [x for x in attr.implies.get(v or "", (v or "",)) if x and x in cat.leaves]

    if value in ("unknown", "conflict") or not (value == "mixed" or sections(value)):
        if cat.unresolved != "hold":
            fallback = next(k for k, leaf in cat.leaves.items() if leaf.handle == cat.unresolved)
            return _placed(out, [_leaf(profile, cat, fallback, skus, skus)], reason=f"fallback: {value}")
        return {**out, "status": "unresolved", "reason": f"{cat.split_by} {value}"}
    per_variant = stated.get("variants") or {}
    leaves = []
    for key in cat.leaves:
        if key is None:
            continue
        if per_variant:
            fit = [s for s in skus if key in sections(per_variant.get(s))]
        else:
            fit = skus if key in sections(value) else []
        if fit:
            leaves.append(_leaf(profile, cat, key, fit, skus))
    if not leaves:
        return {**out, "status": "unresolved", "reason": f"{cat.split_by} {value}: no variant fits a section"}
    return _placed(out, leaves)


def run(shop: str, shops_root: str = SHOPS_ROOT) -> dict[str, Any]:
    profile = profile_for(shop)
    path = os.path.join(shops_root, shop, "prepared", "products.jsonl")
    with open(path, encoding="utf-8") as f:
        prepared = [json.loads(x) for x in f if x.strip()]
    placed = sorted((place(p, profile) for p in prepared), key=lambda x: x["key"])
    out_dir = os.path.join(shops_root, shop, "placement")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "placements.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in placed))
    status = Counter(x["status"] for x in placed)
    sections = Counter(l["leaf"] for x in placed for l in x["leaves"])
    flags = Counter(fl for x in placed for fl in x["flags"])
    lines = [f"placement {shop}: {len(placed)} products: {dict(status)}; sections {dict(sections)}; "
             f"flags {dict(flags) or 'none'}"]
    lines += [f"  unresolved {x['key']}: {x['reason']}; evidence {x['evidence']}" for x in placed
              if x["status"] == "unresolved"]
    lines += [f"  listing_disagrees {x['key']}: {x['value']}; evidence {x['evidence']}" for x in placed
              if "listing_disagrees" in x["flags"]]
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return {"placed": placed, "report": lines}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Place a shop's prepared products into its sections (before Shopify).")
    p.add_argument("shop")
    p.add_argument("--shops-root", default=SHOPS_ROOT)
    args = p.parse_args(argv)
    print("\n".join(run(args.shop, args.shops_root)["report"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
