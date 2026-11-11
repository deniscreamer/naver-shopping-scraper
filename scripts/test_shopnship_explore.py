"""Offline tests for shopnship_explore.py: its model replays the saved explorations, and a run asks every row of its
list once without a crash (a fake calculator, no network).

    .venv/bin/python -m pytest scripts/test_shopnship_explore.py -q
"""
import json
import os

import pytest

import shopnship_explore as E

HERE = os.path.dirname(os.path.abspath(__file__))
SAVED = sorted(f for f in os.listdir(os.path.join(HERE, "fixtures", "shopnship")) if f.startswith("shopnship-explore-"))


@pytest.mark.parametrize("name", SAVED)
def test_the_model_predicts_what_the_saved_exploration_recorded(name):
    with open(os.path.join(HERE, "fixtures", "shopnship", name), encoding="utf-8") as f:
        rows = json.load(f)["requests"]
    assert rows and all(E.predicted(r["form"]) == r["predicted"] for r in rows)


def test_a_run_asks_every_row_once_and_keeps_the_forms_it_does_not_model(monkeypatch):
    asked = []
    monkeypatch.setattr(E.SR, "ask", lambda form, *a, **k: asked.append(form) or "0.00/48.51/0.00/0.00/37.20")
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    rows = E.rows()
    data = E.run(say=lambda s: None, todo=rows)
    assert len(asked) == len(rows) == len(data["requests"]) == 264
    unmodelled = [r for r in data["requests"] if r["predicted"] is None]
    assert {r["group"] for r in unmodelled} >= {"no_sides", "pounds_inches"} and "error" not in json.dumps(data)
    assert "no_sides" in E.report(data)
