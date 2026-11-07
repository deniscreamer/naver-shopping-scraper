"""Collected product lines as offline fixtures (fixtures/collected/<product id>.json) for test_prepared_golden.py.
A development tool, no network: it reads files only.

    .venv/bin/python scripts/collected_fixtures.py add <products.jsonl> <product id> ...
    .venv/bin/python scripts/collected_fixtures.py refresh

`add` copies a collected line (the photo / review file entries kept, their files are not needed; the description
HTML kept: the transform reads its image links and the banners' linkdata). Both take the
line's `details.description` and `specs` from the server's replay of the same saved page when there is one
(server/naver_shopping/fixtures/pages/<id>/expected.json, the file only, R-1: scripts never import server code),
and compute `package` and `variants` again the way collection does (package_measures, naver_variants). So after a
parser change: refresh the server answers (UPDATE_GOLDEN=1 pytest server/naver_shopping/test_pages.py), then
`refresh` here, then UPDATE_GOLDEN=1 pytest scripts/test_prepared_golden.py, and read both diffs.
"""
import json
import os
import sys
from typing import Any

from naver_variants import choose_variants
from package_measures import load_table, variant_measures

HERE = os.path.dirname(os.path.abspath(__file__))
COLLECTED = os.path.join(HERE, "fixtures", "collected")
SERVER_PAGES = os.path.join(HERE, "..", "server", "naver_shopping", "fixtures", "pages")


def _rebuild(line: dict[str, Any], table: dict[str, Any]) -> dict[str, Any]:
    pid = line["key"].split(":")[3]
    replay = os.path.join(SERVER_PAGES, pid, "expected.json")
    if os.path.exists(replay):
        with open(replay, encoding="utf-8") as f:
            page = json.load(f)
        line["details"]["description"] = page["description"]
        line["specs"] = {**page["specs"], "query": line["specs"].get("query"), "read_at": line["specs"].get("read_at")}
    options = line["specs"].get("options")
    line["variants"] = choose_variants(options, line["details"]["pricing"]["discounted_price"], paid=True) \
        if options else None
    line["package"] = variant_measures(line["specs"], table)
    return line


def _relative_files(value: Any) -> Any:
    """Saved file paths as "images/<product id>/<file>": no local folder (a home path) in a fixture."""
    if isinstance(value, dict):
        return {k: (f"images/{v.split('/images/', 1)[1]}" if k == "file" and isinstance(v, str) and "/images/" in v
                    else _relative_files(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_relative_files(v) for v in value]
    return value


def _write(line: dict[str, Any]) -> str:
    line = _relative_files(line)
    os.makedirs(COLLECTED, exist_ok=True)
    path = os.path.join(COLLECTED, line["key"].split(":")[3] + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(line, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path


def add(lines_path: str, ids: list[str]) -> None:
    table = load_table()
    with open(lines_path, encoding="utf-8") as f:
        lines = {json.loads(x)["key"].split(":")[3]: json.loads(x) for x in f if x.strip()}
    for pid in ids:
        print(_write(_rebuild(lines[pid], table)))


def refresh() -> None:
    table = load_table()
    for name in sorted(os.listdir(COLLECTED)):
        with open(os.path.join(COLLECTED, name), encoding="utf-8") as f:
            print(_write(_rebuild(json.load(f), table)))


if __name__ == "__main__":
    if sys.argv[1:2] == ["add"]:
        add(sys.argv[2], sys.argv[3:])
    elif sys.argv[1:2] == ["refresh"]:
        refresh()
    else:
        sys.exit(__doc__)
