"""Collected lines of real products (fixtures/collected/, made by collected_fixtures.py from saved pages) through
the transform: prepare() must equal fixtures/prepared/<product id>.json.

A deliberate change of the transform shows here as a diff: rewrite the expected products with
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_prepared_golden.py
and read the diff of fixtures/prepared/ before committing. The set grows only when the owner asks (2026-11-12:
five junior clubs of 50002787 for the brand, bag and two-club rules: a shop's name as the brand, a supplier in
the origin, U.S.KIDSGOLF, two clubs, a club and a glove; five more of the 100-run for the brand rows and the
package kind: a reselling shop's own name, a code, a title as the brand, an age after 클럽). 2026-11-18: an Amazon
axis named for another kind (13390487313 "Shaft Material" over lengths) and its look-alikes kept (12079165169,
9703030793, 13164548371 "Hand Orientation"), each with its description-images sidecar; two loft sets offered only in
the text (10504295292, held choice_in_text_only) and its look-alikes kept (10482586862, 12178280377, 13683785691,
13278647591, 11006400319), with their sidecars. 2026-11-18, the chipper review (50002784, no sidecars): the word "brand"
and 치퍼 as the 브랜드 / 제조사 rows (9991649397, 11158899277), 치퍼 as the title's shop brand (10179980640), a notice's
962 g out of the row's band (7004743758), a free glove's sizes as the only axis (10421264752).

fixtures/description_images/<product id>.json: the description images' OCR sidecars of the same products
(description_images.py with RapidOCR on the images downloaded 2026-11-07), read by the transform as
run_transform passes them (the size / weight guess of description_measures.py)."""
import json
import os

import pytest

from transform import prepare
from transform_shops import rules_for

HERE = os.path.dirname(os.path.abspath(__file__))
COLLECTED = os.path.join(HERE, "fixtures", "collected")
PREPARED = os.path.join(HERE, "fixtures", "prepared")
SIDECARS = os.path.join(HERE, "fixtures", "description_images")
NAMES = sorted(n[:-5] for n in os.listdir(COLLECTED) if n.endswith(".json")) if os.path.isdir(COLLECTED) else []
RULES = rules_for("fairwardgolf")


@pytest.mark.parametrize("name", NAMES)
def test_prepared_as_expected(name):
    sidecar = os.path.join(SIDECARS, name + ".json")
    images_text = None
    if os.path.isfile(sidecar):
        with open(sidecar, encoding="utf-8") as f:
            images_text = json.load(f)
    with open(os.path.join(COLLECTED, name + ".json"), encoding="utf-8") as f:
        got = json.loads(json.dumps(prepare(json.load(f), RULES, "50002788-fixtures", 1, images_text),
                                    ensure_ascii=False))
    path = os.path.join(PREPARED, name + ".json")
    if os.environ.get("UPDATE_GOLDEN"):
        os.makedirs(PREPARED, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=1)
            f.write("\n")
    with open(path, encoding="utf-8") as f:
        assert got == json.load(f)


def _fixture(name):
    sidecar = os.path.join(SIDECARS, name + ".json")
    images_text = None
    if os.path.isfile(sidecar):
        with open(sidecar, encoding="utf-8") as f:
            images_text = json.load(f)
    with open(os.path.join(COLLECTED, name + ".json"), encoding="utf-8") as f:
        return json.load(f), images_text


def test_prepare_is_json_native_and_reads_only_the_measures_table(monkeypatch):
    """The prepare cache (run_transform._prepared_cached, 2026-11-16) hands on json.loads of a stored record, and
    its key holds only the line, the sidecar, the rules, the measures table and the code: prepare's output must
    survive a JSON round trip unchanged (no tuple, no non-string key), and prepare must open no other file; the same
    for image_read, the record's images' text."""
    import builtins
    import io
    import transform
    from run_transform import image_read
    from transform_shops import without_paid, without_paid_addons
    fixtures = {name: _fixture(name) for name in NAMES}
    transform._measures_table.cache_clear()
    opened = []
    real_open = builtins.open

    def spy(file, *a, **k):
        opened.append(os.path.basename(str(file)))
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    for rules in (RULES, without_paid(RULES), without_paid_addons(RULES)):
        for name, (line, images_text) in fixtures.items():
            got = prepare(line, rules, "50002788-fixtures", 1, images_text)
            assert json.loads(json.dumps(got, ensure_ascii=False)) == got, name
    for name, (line, images_text) in fixtures.items():                  # the record's other half
        got = image_read(line, RULES, images_text)
        assert json.loads(json.dumps(got, ensure_ascii=False)) == got, name
    monkeypatch.undo()
    assert "category_measures.json" in opened and set(opened) <= {"category_measures.json"}, (
        f"prepare opened {sorted(set(opened))}: add it to run_transform's cache signature")
