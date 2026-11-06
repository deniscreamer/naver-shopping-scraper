"""Keep a collection run: copy example_99's output (scripts/output/full-<category>/) into the shop's own store of
collected runs, byte for byte, read-only. The transform reads only kept runs, so a later collection (example_99
opens its file with "w") never changes what was already prepared.

    scripts/output/shops/<shop>/collected/<category>-<UTC time of products.jsonl>/
        products.jsonl   images/<product id>/*.webp   manifest.json {shop, category, source, lines, sha256, kept_at}

The shop is the namespace of the lines' source keys (<shop>:naver:<channelNo>:<productId>), never SHOP_STORE; all
lines must share one shop and one category. A run already kept (same sha256) is refused, so is an existing run id.
A run that is not kept before the next collection is lost.

    .venv/bin/python scripts/keep_run.py scripts/output/full-50002788
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from datetime import datetime, timezone

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SHOPS_ROOT = os.path.join(OUTPUT_ROOT, "shops")


class KeepError(Exception):
    """The run cannot be kept as it is (mixed shops or categories, already kept, nothing in it)."""


def _read_only(path: str) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def keep(source: str, shops_root: str = SHOPS_ROOT) -> str:
    """-> the kept run's folder."""
    lines_path = os.path.join(source, "products.jsonl")
    if not os.path.isfile(lines_path):
        raise KeepError(f"{source}: no products.jsonl")
    with open(lines_path, "rb") as f:
        raw = f.read()
    lines = []
    for n, x in enumerate(raw.split(b"\n"), 1):     # \n only: Korean text may hold U+2028 (example_99 writes it raw)
        if x.strip():
            try:
                line = json.loads(x)
                line["key"].split(":")[3]
            except (ValueError, KeyError, TypeError, IndexError):
                raise KeepError(f"{lines_path}:{n}: not a collected product line") from None
            lines.append(line)
    if not lines:
        raise KeepError(f"{lines_path}: no products")
    shops = {line["key"].split(":")[0] for line in lines}
    categories = {((line.get("specs") or {}).get("category") or {}).get("id") for line in lines}
    if len(shops) != 1 or len(categories) != 1:
        raise KeepError(f"{lines_path}: one shop and one category per run, found {sorted(shops)} / "
                        f"{sorted(map(str, categories))}")
    shop, category = shops.pop(), categories.pop()
    sha = hashlib.sha256(raw).hexdigest()
    collected = os.path.join(shops_root, shop, "collected")
    for manifest in _manifests(collected):
        if manifest["sha256"] == sha:
            raise KeepError(f"{lines_path}: already kept as {manifest['run']}")
    mtime = datetime.fromtimestamp(os.path.getmtime(lines_path), timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = f"{category}-{mtime}"
    final = os.path.join(collected, run)
    if os.path.exists(final):
        raise KeepError(f"{final} exists")
    target = final + ".partial"                     # renamed when complete: a stopped copy is never a run
    if os.path.exists(target):
        shutil.rmtree(target)
    os.makedirs(target)
    shutil.copy2(lines_path, os.path.join(target, "products.jsonl"))
    for product_id in sorted({line["key"].split(":")[3] for line in lines}):   # only this run's products: the
        photos = os.path.join(source, "images", product_id)                  # source folder keeps older runs' too
        if os.path.isdir(photos):
            shutil.copytree(photos, os.path.join(target, "images", product_id))
    manifest = {"run": run, "shop": shop, "category": category, "source": os.path.abspath(source),
                "lines": len(lines), "sha256": sha, "kept_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(os.path.join(target, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    with open(os.path.join(target, "products.jsonl"), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != sha:
            raise KeepError(f"{lines_path} changed while it was kept; keep it again")
    for folder, _, files in os.walk(target):
        for name in files:
            _read_only(os.path.join(folder, name))
    os.rename(target, final)
    return final


def kept_run_ids(collected: str) -> list[str]:
    """The finished runs: folders with a manifest.json (a .partial copy or a stray file is not a run)."""
    if not os.path.isdir(collected):
        return []
    return sorted(r for r in os.listdir(collected) if os.path.isfile(os.path.join(collected, r, "manifest.json")))


def _manifests(collected: str) -> list[dict]:
    out = []
    for run in kept_run_ids(collected):
        with open(os.path.join(collected, run, "manifest.json"), encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Keep a collection run (example_99 output) for the transform.")
    parser.add_argument("source", help="the run folder, e.g. scripts/output/full-50002788")
    args = parser.parse_args(argv)
    try:
        target = keep(args.source)
    except KeepError as e:
        print(f"keep_run: {e}")
        return 2
    with open(os.path.join(target, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    photos = sum(len(files) for _, _, files in os.walk(os.path.join(target, "images")))
    print(f"keep_run: kept {manifest['lines']} products, {photos} photo files -> {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
