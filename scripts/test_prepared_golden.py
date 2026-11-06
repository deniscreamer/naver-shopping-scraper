"""Collected lines of real products (fixtures/collected/, made by collected_fixtures.py from saved pages) through
the transform: prepare() must equal fixtures/prepared/<product id>.json.

A deliberate change of the transform shows here as a diff: rewrite the expected products with
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_prepared_golden.py
and read the diff of fixtures/prepared/ before committing. The set grows only when the owner asks."""
import json
import os

import pytest

from transform import prepare
from transform_shops import rules_for

HERE = os.path.dirname(os.path.abspath(__file__))
COLLECTED = os.path.join(HERE, "fixtures", "collected")
PREPARED = os.path.join(HERE, "fixtures", "prepared")
NAMES = sorted(n[:-5] for n in os.listdir(COLLECTED) if n.endswith(".json")) if os.path.isdir(COLLECTED) else []
RULES = rules_for("fairwardgolf")


@pytest.mark.parametrize("name", NAMES)
def test_prepared_as_expected(name):
    with open(os.path.join(COLLECTED, name + ".json"), encoding="utf-8") as f:
        got = json.loads(json.dumps(prepare(json.load(f), RULES, "50002788-fixtures", 1), ensure_ascii=False))
    path = os.path.join(PREPARED, name + ".json")
    if os.environ.get("UPDATE_GOLDEN"):
        os.makedirs(PREPARED, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=1)
            f.write("\n")
    with open(path, encoding="utf-8") as f:
        assert got == json.load(f)
