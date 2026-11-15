"""Offline tests for review_grid.py: published products only, in the job's order, numbered sheets and index.tsv.

    .venv/bin/python -m pytest scripts/test_review_grid.py -q
"""
import json
import os

from PIL import Image

import review_grid as G

SHOP = "fairwardgolf"


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def shop(tmp_path, n=3):
    root = tmp_path / "shops"
    keys = [f"{SHOP}:naver:100:{i}" for i in range(1, n + 1)]
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"),
                [{"key": k, "source": {"category_id": "50002787"},
                  "texts": [{"kind": "title", "ko": f"주니어 세트 {i}"}]} for i, k in enumerate(keys, 1)])
    ledger = [{"key": k, "status": "published", "handle": f"h{i}", "admin_url": f"a{i}"}
              for i, k in enumerate(keys, 1)]
    ledger.append({"key": keys[1], "status": "withdrawn"})                     # withdrawn later: not shown
    write_jsonl(str(root / SHOP / "publish" / "published.jsonl"), ledger)
    photo_dir = root / SHOP / "collected" / "run" / "images" / "1"
    photo_dir.mkdir(parents=True)
    Image.new("RGB", (40, 30), "blue").save(photo_dir / f"{SHOP}-1-001-abc.webp")
    return str(root), keys


def test_only_published_products_in_the_job_order_with_their_photo(tmp_path):
    root, keys = shop(tmp_path)
    rows = G.items(SHOP, root, [keys[2], keys[1], keys[0]], None)
    assert [r["id"] for r in rows] == ["3", "1"]                                  # 2 was withdrawn
    assert rows[1]["photo"].endswith("-001-abc.webp") and rows[0]["photo"] is None
    assert rows[1]["title"] == "주니어 세트 1" and rows[1]["handle"] == "h1"


def test_sheets_and_index_are_numbered(tmp_path):
    root, keys = shop(tmp_path)
    rows = G.items(SHOP, root, None, "50002787")
    sheets = G.draw(rows, str(tmp_path / "out"), per_sheet=1, thumb=60)
    assert len(sheets) == 2 and all(os.path.exists(s) for s in sheets)
    with open(tmp_path / "out" / "index.tsv", encoding="utf-8") as f:
        lines = f.read().splitlines()
    assert lines[0].startswith("n\tkey") and lines[1].split("\t")[:3] == ["1", keys[0], "1"]
