"""Offline tests of the translation quality check (translate_eval.py): the sample, the judged pairs, the judge's
batches with a fake client, the report. No network.

    .venv/bin/python -m pytest scripts/test_translate_eval.py -q
"""
import json
from types import SimpleNamespace

import translate_eval as E
from test_translate import FIXTURES, fixture


def test_the_sample_is_varied_and_ready_only():
    prepared = [fixture(n) for n in FIXTURES[:20]] + [{**fixture(FIXTURES[0]), "key": "x:held", "status": "held"}]
    got = E.sample(prepared, 6)
    assert len(got) == 6 and all(p["status"] == "ready" for p in got)
    assert len({p["key"] for p in got}) == 6
    assert any(len(p["product"]["variants"]) >= 40 for p in got) == any(
        len(p["product"]["variants"]) >= 40 for p in prepared if p["status"] == "ready")


def test_pairs_are_unique_and_judged_kinds_only():
    p = fixture(FIXTURES[0])
    rec = {"key": p["key"], "status": "translated", "en": {t["id"]: "x" for t in p["texts"]}}
    got = E.pairs([p], [rec, rec])
    assert len(got) == len({(x["kind"], x["ko"]) for x in got})
    assert all(x["kind"] in E.JUDGED_KINDS for x in got) and not any(x["kind"] == "spec_label" for x in got)


def test_the_judge_batches_and_a_missing_answer():
    items = [{"key": "k", "kind": "review", "ko": f"좋아요 {n}", "en": "good"} for n in range(35)]
    sent = []

    def create(**kwargs):
        body = json.loads(kwargs["messages"][0]["content"])["items"]
        sent.append(len(body))
        answer = [{"id": i["id"], "ok": i["id"] != "2", "issues": [] if i["id"] != "2" else ["fact_lost"], "note": ""}
                  for i in body if i["id"] != "3"]
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps({"items": answer}))],
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    judged, usage = E.judge(items, client)
    assert sent == [30, 5] and len(judged) == 35 and usage == {"input": 20, "output": 10}
    assert judged[1]["issues"] == ["fact_lost"] and judged[2]["issues"] == ["judge_missing"]


def test_the_report_marks_flagged_rows():
    p = fixture(FIXTURES[0])
    t = p["texts"][0]
    rec = {"key": p["key"], "status": "translated", "en": {t["id"]: "English <b>"}}
    page = E.report([p], [rec], [{"key": p["key"], "kind": t["kind"], "ko": t["ko"], "ok": False, "issues": ["fact_lost"], "note": "n"}])
    assert "<tr class=bad>" in page and "English &lt;b&gt;" in page and "1 of 1 unique texts" in page


def test_a_failed_judge_batch_costs_only_its_rows():
    items = [{"key": "k", "kind": "review", "ko": f"좋아요 {n}", "en": "good"} for n in range(35)]
    calls = []

    def create(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("overloaded")
        body = json.loads(kwargs["messages"][0]["content"])["items"]
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps({"items": [
            {"id": i["id"], "ok": True, "issues": [], "note": ""} for i in body]}))],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    judged, _ = E.judge(items, SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert [x["issues"] for x in judged[:30]] == [["judge_missing"]] * 30 and all(x["ok"] for x in judged[30:])


def test_product_texts_are_judged_per_product():
    a, b = fixture(FIXTURES[0]), fixture(FIXTURES[0])
    b = {**b, "key": "other"}
    title = next(t for t in a["texts"] if t["kind"] == "title")
    recs = [{"key": a["key"], "status": "translated", "en": {title["id"]: "One"}},
            {"key": "other", "status": "translated", "en": {title["id"]: "Two"}}]
    got = [x["en"] for x in E.pairs([a, b], recs) if x["kind"] == "title"]
    assert got == ["One", "Two"]
