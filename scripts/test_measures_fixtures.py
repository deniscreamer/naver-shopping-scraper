"""Regression fixtures for the five package fields (package_measures.py, description_measures.py, the transform's
hook _image_measures): real golf sets cut down to what that code reads, with the fields each variant must get.

fixtures/measures/<product id>.json:
  covers    the path of the rules the product is here for (the owner's order of 2026-11-10: the seller's statement,
            the composition from the set's parts, the flat category default)
  checked   the product's own lines the expected values were checked against by hand (2026-11-10)
  note      what is left out or approximate, when something is
  input     cut from the collected line and the description_images sidecar: title, category, spec_rows (상품정보),
            facts (the one-value options), variants (id, option words), supplements (add-ons), typed (the typed
            description's lines), images (the read images' OCR rows, [text, confidence]; a number N stands for N
            rows the code reads nothing in), measures (the server path's candidates, specs.measures). Sellers'
            phone numbers, addresses and shop names are "x"; no photos, reviews or prices
  expected  [{variants: [option words, ...], fields: {name: {value, source, confidence, how, from, quote, parts}}}]

A fixture pins one of two things, and says which. Without a word in its `note`: a value verified by hand against
the lines in `checked`, not what the code printed. Where the `note` says "approximate": the rule's present
approximation, a value the page's own figures do not give and the rule cannot do better on today (7583123963: 13
x a median that holds no iron, 4258 g where the seller's tables add up to about 4.9-5.4 kg; the S 세트 variants of
5543663553: the R set's row, 350 g under their own; 13302492097: 3 x the baseline club, 1020 g for three clubs
of 825 g; 12736318849: 12 x the baseline club, 4080 g, where the page's twelve weights sum 4973 g and OCR lost
seven). Such a pin holds the rule still so that a change shows; it does not call the value right, and a rule
that reads the page better should move it.

A deliberate change of the rules shows here as a failure that names the product, the variant, the field and both
values. Rewrite the expected part with
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_measures_fixtures.py
and read the diff of fixtures/measures/ against the products' lines before committing (R-TEST-5)."""
import json
import os
from typing import Any

import pytest

import transform
from description_measures import COMPOSED, SOURCE, today_value
from package_measures import FIELDS, load_table, on_scale, variant_measures

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "measures")
NAMES = sorted(n[:-5] for n in os.listdir(FIXTURES) if n.endswith(".json")) if os.path.isdir(FIXTURES) else []
PINNED = ("source", "confidence", "how", "from", "quote", "parts")


def measured(given: dict[str, Any]) -> list[dict[str, Any]]:
    """Each variant's five fields from a fixture's input, the way a product gets them: the server path's fields
    (collect_product: variant_measures with the real category_measures.json; on today's scale, as the transform
    reads a collected line), then the transform's hook over the description."""
    specs = {"category": given["category"], "measures": given["measures"],
             "options": {"variants": [{"id": v["id"]} for v in given["variants"] if v["id"]]}}
    package = {p["variant_id"]: on_scale(p["fields"]) for p in variant_measures(specs, load_table())}
    ov = {"facts": given["facts"],
          "variants": [{"options_ko": v["options_ko"], "package": package[v["id"]]} for v in given["variants"]]}
    blank = {"text": "", "conf": 1.0}                   # a cut row keeps its place: the rows' numbers stay the page's
    sidecar = {"images": [{"status": "read", "slices": [{"rows": [
        r for row in image for r in ([blank] * row if isinstance(row, int) else [{"text": row[0], "conf": row[1]}])
    ]}]} for image in given["images"]]}
    model, pieces = transform._model_pieces(given["title"], given["spec_rows"])
    transform._image_measures(ov, sidecar, given["title"], model, pieces, given["spec_rows"],
                              given["category"]["id"], "\n".join(given["typed"]), given["supplements"])
    return [v["package"] for v in ov["variants"]]


def pinned(field: dict[str, Any]) -> dict[str, Any]:
    """What a fixture pins of a field: its value (a default's central), its source and level, how it was built."""
    return {"value": today_value(field), **{k: field[k] for k in PINNED if field.get(k) is not None}}


def grouped(given: dict[str, Any], got: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The variants that get the same fields, as one entry of `expected`."""
    out: list[dict[str, Any]] = []
    for v, fields in zip(given["variants"], got):
        same = next((g for g in out if g["fields"] == fields), None)
        if same is None:
            out.append(same := {"variants": [], "fields": fields})
        same["variants"].append(v["options_ko"])
    return out


def dumps(o: Any, pad: str = "") -> str:
    """JSON a person reads: one line for what is short, for a dict of plain values and for an OCR row."""
    flat = json.dumps(o, ensure_ascii=False)
    if not isinstance(o, (dict, list)) or len(flat) <= 110:
        return flat
    values = list(o.values()) if isinstance(o, dict) else o
    if not any(isinstance(v, (dict, list)) for v in values) and (isinstance(o, dict) or len(o) <= 2):
        return flat
    items = [f"{json.dumps(k, ensure_ascii=False)}: {dumps(v, pad + ' ')}" for k, v in o.items()] \
        if isinstance(o, dict) else [dumps(v, pad + " ") for v in o]
    return f"{'{' if isinstance(o, dict) else '['}\n{pad} " + f",\n{pad} ".join(items) + \
        f"\n{pad}{'}' if isinstance(o, dict) else ']'}"


def load(name: str) -> dict[str, Any]:
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("name", NAMES)
def test_fields_as_pinned(name):
    fixture = load(name)
    given = fixture["input"]
    got = [{n: pinned(fields[n]) for n in FIELDS} for fields in measured(given)]
    got = json.loads(json.dumps(got, ensure_ascii=False))
    if os.environ.get("UPDATE_GOLDEN"):
        fixture["expected"] = grouped(given, got)
        with open(os.path.join(FIXTURES, name + ".json"), "w", encoding="utf-8") as f:
            f.write(dumps(fixture) + "\n")
    want = {json.dumps(v, ensure_ascii=False): g["fields"] for g in fixture["expected"] for v in g["variants"]}
    assert len(want) == len(given["variants"]), f"{name}: every variant of the input needs its expected fields"
    wrong = [f"{name} {words} {n}:\n   got    {json.dumps(fields[n], ensure_ascii=False)}\n"
             f"   pinned {json.dumps(want[words].get(n), ensure_ascii=False)}"
             for v, fields in zip(given["variants"], got) for words in [json.dumps(v["options_ko"], ensure_ascii=False)]
             for n in FIELDS if fields[n] != want[words].get(n)]
    assert not wrong, "\n".join(wrong)


def test_fixtures_cover_every_level_and_source():
    """Together the fixtures hold every confidence level and every source a field can have."""
    seen = {(f["source"], f["confidence"]) for name in NAMES for g in load(name)["expected"]
            for f in g["fields"].values()}
    assert {level for _, level in seen} == {1, 2, 3, 4, 5}
    assert {source for source, _ in seen} == {"source_stated", SOURCE, COMPOSED, "category_default"}
