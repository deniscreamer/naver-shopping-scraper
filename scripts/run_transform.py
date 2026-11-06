"""Run the transform for one shop: every kept run (keep_run.py) -> scripts/output/shops/<shop>/prepared/.

A product in several runs is taken from the newest run. The output is rebuilt each time from the kept runs and the
rules (same input + same rules = the same bytes: sorted by key, no time inside):

    prepared/products.jsonl   one prepared product per line (transform.Prepared, ready or held)
    prepared/report.txt       counts, held products with their codes, texts to translate

    .venv/bin/python scripts/run_transform.py fairwardgolf            # every kept run
    .venv/bin/python scripts/run_transform.py fairwardgolf 50002788-20261105T193000Z
"""
import argparse
import json
import os
import sys
from collections import Counter

from keep_run import SHOPS_ROOT, kept_run_ids
from transform import prepare
from transform_shops import ShopRulesMissing, rules_for


def kept_runs(shop: str, shops_root: str = SHOPS_ROOT) -> list[str]:
    return kept_run_ids(os.path.join(shops_root, shop, "collected"))


def run(shop: str, runs: list[str] | None = None, shops_root: str = SHOPS_ROOT) -> dict:
    rules = rules_for(shop)
    chosen = runs or kept_runs(shop, shops_root)
    latest: dict[str, tuple[str, int, dict]] = {}
    for run_id in sorted(chosen, key=lambda r: r.split("-")[-1]):        # newest last: it wins
        path = os.path.join(shops_root, shop, "collected", run_id, "products.jsonl")
        with open(path, "rb") as f:
            for n, raw in enumerate(f.read().split(b"\n"), 1):          # \n only, as keep_run counted them
                if raw.strip():
                    line = json.loads(raw)
                    latest[line["key"]] = (run_id, n, line)
    prepared = [prepare(line, rules, run_id, n) for run_id, n, line in latest.values()]
    prepared.sort(key=lambda p: p["key"])
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
