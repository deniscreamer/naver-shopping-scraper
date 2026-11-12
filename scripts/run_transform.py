"""Run the transform for one shop: every kept run (keep_run.py) -> scripts/output/shops/<shop>/prepared/.

A product in several runs is taken from the newest run. After the per-product prepare, steps look across the
products: store-wide description banners (the same image opening or closing most listings of one store) move to
description_dropped (shared_images.py); the images' Korean text is written for translation (image_texts); a product
with no brand stated gets one from the shop's own brands in its title, 원산지's importer, the images' text, or
노브랜드 (brand_fallback.py). The shop's sections are not here: placement.py reads prepared/ afterwards. The output is rebuilt each time from the kept runs and the
rules (same input + same rules = the same bytes: sorted by key, no time inside):

    prepared/products.jsonl   one prepared product per line (transform.Prepared, ready or held)
    prepared/report.txt       counts, held products with their codes, texts to translate
    translation/<product id>/description_images.ko.txt|.ko.json
                              the description images' Korean text for the translation step, and the flag
                              product.description_images_text.state on each product (image_texts below)

    .venv/bin/python scripts/run_transform.py fairwardgolf            # every kept run
    .venv/bin/python scripts/run_transform.py fairwardgolf 50002788-20261105T193000Z
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from typing import Any

import description_image_text as image_text
from description_images import current, load_sidecar
from keep_run import SHOPS_ROOT, kept_run_ids
import brand_fallback
from description_images import image_rows
from shared_images import RULE as SHARED_RULE, drop_shared_images
from transform import _texts, prepare
from transform_shops import ShopRulesMissing, rules_for, without_paid, without_paid_addons


def kept_runs(shop: str, shops_root: str = SHOPS_ROOT) -> list[str]:
    return kept_run_ids(os.path.join(shops_root, shop, "collected"))


def latest_lines(shop: str, runs: list[str] | None = None, shops_root: str = SHOPS_ROOT) -> dict[str, tuple]:
    """{key: (run id, line number, line)}: each product from the newest of the chosen kept runs."""
    chosen = runs or kept_runs(shop, shops_root)
    latest: dict[str, tuple[str, int, dict]] = {}
    for run_id in sorted(chosen, key=lambda r: r.split("-")[-1]):        # newest last: it wins
        path = os.path.join(shops_root, shop, "collected", run_id, "products.jsonl")
        with open(path, "rb") as f:
            for n, raw in enumerate(f.read().split(b"\n"), 1):          # \n only, as keep_run counted them
                if raw.strip():
                    line = json.loads(raw)
                    latest[line["key"]] = (run_id, n, line)
    return latest


def image_texts(shop: str, rules: Any, prepared: list[Any], latest: dict[str, tuple], shops_root: str) -> None:
    """The description images' Korean text for the translation step (description_image_text): written to
    <shop>/translation/<product id>/description_images.ko.txt (to read) and .ko.json (blocks with ids), and one
    flag on each prepared product, product["description_images_text"]["state"]:

      off           the category does not read its images (CategoryRules.description_images)
      not_read      it does, but description_images.py has not read this product's current links
      empty         read, nothing left to translate (photos, the shop's own blocks)
      to_translate  the .ko files are written; no translation of this text yet
      translated    description_images.en.json exists with source_sha256 = this text's sha256

    The translation step reads the flag (not the folder), writes description_images.en.json
    {format, source_sha256, blocks: [{id, text}]} next to the .ko files; the next run_transform sets translated.
    A product left with no text loses its .ko files (an .en file is the translator's and is kept)."""
    folder = os.path.join(shops_root, shop, "translation")
    read: dict[str, tuple[str, dict]] = {}
    state: dict[str, str] = {}
    for p in prepared:
        line = latest[p["key"]][2]
        category = ((line.get("specs") or {}).get("category") or {})
        try:
            on = rules.category(category.get("id"), category.get("name")).description_images
        except ShopRulesMissing:
            on = False
        if not on:
            state[p["key"]] = "off"
            continue
        sidecar = load_sidecar(shop, p["source"]["product_id"], shops_root)
        if not current(sidecar, line):
            state[p["key"]] = "not_read"
            continue
        details = line.get("details") or {}
        read[p["key"]] = (p["source"]["channel_no"], image_text.blocks(
            sidecar, (details.get("store") or {}).get("name"), details.get("brand")))
    shared = image_text.mark_shared(read)
    for p in prepared:
        product_id = p["source"]["product_id"]
        where = os.path.join(folder, product_id)
        ko_txt, ko_json, en_json = (os.path.join(where, f"description_images.{x}") for x in ("ko.txt", "ko.json",
                                                                                           "en.json"))
        rel = f"translation/{product_id}/description_images"
        flag: dict = {"state": state.get(p["key"]), "ko": None, "en": f"{rel}.en.json"}
        got = shared.get(p["key"])
        if got is not None:
            digest = image_text.sha(got["blocks"])
            flag.update(blocks=len(got["blocks"]), chars=sum(len(b["text"]) for b in got["blocks"]),
                        sha256=digest, dropped=got["dropped"])
            if got["blocks"]:
                os.makedirs(where, exist_ok=True)
                glossary = image_text.glossary_for(p["source"].get("category_id"))
                with open(ko_txt, "w", encoding="utf-8") as f:
                    f.write(image_text.as_text(product_id, got["blocks"], digest, glossary))
                with open(ko_json, "w", encoding="utf-8") as f:
                    json.dump({"format": image_text.FORMAT, "product_id": product_id, "key": p["key"],
                               "sha256": digest, "instructions": list(image_text.INSTRUCTIONS),
                               "glossary": glossary, "blocks": got["blocks"]}, f, ensure_ascii=False, indent=1)
                flag.update(state="to_translate", ko=f"{rel}.ko.json")
                try:
                    with open(en_json, encoding="utf-8") as f:
                        if json.load(f).get("source_sha256") == digest:
                            flag["state"] = "translated"
                except (OSError, ValueError):
                    pass
            else:
                flag["state"] = "empty"
        if flag["ko"] is None:
            for old in (ko_txt, ko_json):
                if os.path.exists(old):
                    os.remove(old)
        p["product"]["description_images_text"] = flag


JOBS_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "jobs")
PAID, VARIANTS = "paid", "variants"


def paid_choices(shop: str, shops_root: str = SHOPS_ROOT, jobs_root: str = JOBS_ROOT) -> dict[str, str]:
    """Product id -> the paid choices its job took: PAID (a job made with --paid: the category's paid variants and
    add-ons) or VARIANTS (--paid-variants: paid variants, no paid add-on); a product of no such job takes only what
    costs nothing extra. The latest job of a product decides. Read from the jobs' own files, so a job's choice stays
    with its products whoever prepares the shop again (2026-11-11: the transform prepares the whole shop, and a
    --paid job of 50002787 turned the paid variants of 101 published full sets on; a run by hand did the same). Jobs
    from before the choice was recorded (no `free_only` in job.json, before 2026-11-09) count as free: their products
    were prepared free since. A job of another shops root (a trial) does not count."""
    found: list[tuple[str, str | None, list[str]]] = []
    for name in sorted(os.listdir(jobs_root)) if os.path.isdir(jobs_root) else []:
        folder = os.path.join(jobs_root, name)
        if name.startswith("_") or not os.path.isfile(os.path.join(folder, "job.json")):
            continue
        with open(os.path.join(folder, "job.json"), encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("shop") != shop or "free_only" not in meta or \
                os.path.abspath(meta.get("shops_root") or SHOPS_ROOT) != os.path.abspath(shops_root):
            continue
        choice = VARIANTS if meta.get("paid_variants") else None if meta["free_only"] else PAID
        rows = os.path.join(folder, "listing.jsonl")
        ids = [str(json.loads(line)["product_id"]) for line in open(rows, encoding="utf-8")] \
            if os.path.exists(rows) else []
        found.append((meta.get("created_at") or "", choice, ids))
    out: dict[str, str] = {}
    for _, choice, ids in sorted(found, key=lambda f: f[0]):
        for pid in ids:
            if choice:
                out[pid] = choice
            else:
                out.pop(pid, None)
    return out


def _known_brands(shops_root: str) -> list[str]:
    """The Korean names of the brand dictionary (brand_fallback step 3b); none for another shops root (a test's)."""
    if os.path.abspath(shops_root) != os.path.abspath(SHOPS_ROOT):
        return []
    try:
        from translation_dicts import Dictionaries
        return sorted(k for k in Dictionaries().entries["brand"] if re.search(r"[가-힣]", k))
    except Exception:                                                   # a test's shops root: no dictionary
        return []


def run(shop: str, runs: list[str] | None = None, shops_root: str = SHOPS_ROOT,
        choices: dict[str, str] | None = None) -> dict:
    """Prepare the shop's latest lines. Each product with the paid choices of its job (`choices`, default
    paid_choices(): the jobs' files), every other one with what costs nothing extra (the owner, 2026-11-09)."""
    choices = paid_choices(shop, shops_root) if choices is None else choices
    rules = rules_for(shop)
    by_choice = {PAID: rules, VARIANTS: without_paid_addons(rules)}
    free = without_paid(rules)
    chosen = runs or kept_runs(shop, shops_root)
    latest = latest_lines(shop, runs, shops_root)
    prepared = [prepare(line, by_choice.get(choices.get(line["key"].split(":")[3], ""), free), run_id, n,
                        load_sidecar(shop, line["key"].split(":")[3], shops_root))
                for run_id, n, line in latest.values()]
    prepared.sort(key=lambda p: p["key"])
    prepared = drop_shared_images(prepared)                             # run-level: needs the store's other listings
    image_texts(shop, rules, prepared, latest, shops_root)              # run-level: blocks a store repeats
    brand_fallback.fill(                                                # run-level: the shop's own brands
        prepared,
        lambda key: [r for img in image_rows(load_sidecar(shop, key.split(":")[3], shops_root)) for r in img],
        {k: (((line[2].get("specs") or {}).get("facts") or {}).get("origin") or {}).get("value")
         for k, line in latest.items()},
        _texts,
        _known_brands(shops_root))
    for p in prepared:                                                  # after the brand: needs the fallback's answer
        cat = rules.categories.get(str(p["source"].get("category_id")))
        if cat and cat.agency_needs_brand and p["status"] == "ready" \
                and p["product"].get("brand_source") == "none" \
                and any(n["code"] == "purchase_agency" for n in p["notes"]):
            p["held"].append({"code": "agency_no_brand", "detail": "a purchase agency's import with no brand"})
            p["status"] = "held"
    out_dir = os.path.join(shops_root, shop, "prepared")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "products.jsonl"), "w", encoding="utf-8") as f:
        for p in prepared:
            f.write(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n")
    status = Counter(p["status"] for p in prepared)
    codes = Counter(h["code"] for p in prepared for h in p["held"])
    notes = Counter(n["code"] for p in prepared for n in p["notes"])
    texts = {t["id"] for p in prepared if p["status"] == "ready" for t in p["texts"]}
    lines = [f"transform {shop}: {len(prepared)} products from {len(chosen)} run(s): {status['ready']} ready, "
             f"{status['held']} held {dict(sorted(codes.items()))}, notes {dict(sorted(notes.items()))}, "
             f"{len(texts)} distinct texts to translate"]
    shared = [(p["source"]["channel_no"],
               sum(d["rule"] == SHARED_RULE for d in p["product"].get("description_dropped") or []))
              for p in prepared]
    if any(n for _, n in shared):
        lines.append(f"  shared store images: {sum(n for _, n in shared)} dropped from "
                     f"{sum(1 for _, n in shared if n)} products of {len({c for c, n in shared if n})} store(s)")
    states = Counter(p["product"].get("description_images_text", {}).get("state") for p in prepared)
    if set(states) - {"off"}:
        lines.append(f"  description image text: {dict(sorted(states.items()))} (translation/<product id>/)")
    lines += [f"  held {p['key']}: " + "; ".join(f"{h['code']} ({h['detail']})" for h in p["held"])
              for p in prepared if p["held"]]
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return {"prepared": prepared, "report": lines, "out_dir": out_dir}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a shop's kept collection runs for translation.")
    parser.add_argument("shop", help="shop id, e.g. fairwardgolf")
    parser.add_argument("runs", nargs="*", help="kept run ids (default: every kept run)")
    args = parser.parse_args(argv)
    try:
        result = run(args.shop, args.runs or None)
    except ShopRulesMissing as e:
        print(f"run_transform: stop: {e}")
        return 2
    for line in result["report"]:
        print(f"run_transform: {line}")
    print(f"run_transform: -> {result['out_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
