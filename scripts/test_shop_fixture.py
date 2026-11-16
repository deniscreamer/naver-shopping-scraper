"""The real-data shop fixture (fixtures/shop/, make_shop_fixture.py, 2026-11-16): its files parse as the tools read
them (shop_files.read_jsonl) and match our record types (shop_types / transform.Prepared, test_naver_types.mismatches),
and each case is what cases.json says it is, so a test may rely on it.

    .venv/bin/python -m pytest scripts/test_shop_fixture.py -q
"""
import glob
import json
import os
import re

import pytest

from shop_files import read_jsonl
from shop_types import CollectedLine, JobMeta, LedgerRow
from test_naver_types import mismatches
from transform import Prepared

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures", "shop")
META = json.load(open(os.path.join(FIX, "cases.json"), encoding="utf-8"))
SHOP_DIR = os.path.join(FIX, "shops", META["shop"])
REBUILT = ("prepared/products.jsonl", "translation/translated.jsonl", "placement/placements.jsonl")
APPENDED = ("publish/published.jsonl", "translation/texts.jsonl", "translation/descriptions.jsonl")


def rows(rel):
    return read_jsonl(os.path.join(SHOP_DIR, rel), tail_ok=rel in APPENDED)


def ledger():
    out = {}
    for r in rows("publish/published.jsonl"):
        out.setdefault(r["key"], []).append(r)
    return out


@pytest.mark.parametrize("rel", REBUILT + APPENDED)
def test_every_shop_file_parses_and_names_only_the_cases(rel):
    got = rows(rel)
    assert got and {r["key"] for r in got} <= set(META["cases"])


def test_every_case_is_prepared_translated_and_placed_once():
    for rel in REBUILT:
        assert sorted(r["key"] for r in rows(rel)) == sorted(META["cases"]), rel


def test_the_records_match_their_types():
    for r in rows("prepared/products.jsonl"):
        assert mismatches(r, Prepared) == [], r["key"]
    for r in rows("publish/published.jsonl"):
        assert mismatches(r, LedgerRow) == [], r["key"]
    for job in META["jobs"]:
        assert mismatches(json.load(open(os.path.join(FIX, "jobs", job, "job.json"), encoding="utf-8")), JobMeta) == []
    lines = glob.glob(os.path.join(SHOP_DIR, "collected", "*", "products.jsonl"))
    assert len(lines) == len(META["cases"])                          # one newest collected line a case
    for path in lines:
        for line in read_jsonl(path):
            assert mismatches(line, CollectedLine) == [], path


def test_the_jobs_files_parse():
    for job in META["jobs"]:
        d = os.path.join(FIX, "jobs", job)
        assert read_jsonl(os.path.join(d, "events.jsonl"), tail_ok=True)
        assert read_jsonl(os.path.join(d, "screened.jsonl"), tail_ok=True)
        assert json.load(open(os.path.join(d, "now.json"), encoding="utf-8"))
        assert json.load(open(os.path.join(d, "job.json"), encoding="utf-8"))["shops_root"] == "<fixture>"


def test_no_machine_path_and_no_preview_key():
    for path in glob.glob(os.path.join(FIX, "**", "*"), recursive=True):
        if os.path.isfile(path):
            text = open(path, encoding="utf-8").read()
            assert "/Users/" not in text and not re.search(r"preview_key=[0-9a-f]", text), path


def key(pid):
    return next(k for k in META["cases"] if k.endswith(":" + pid))


def test_the_cases_are_what_cases_json_says():
    led = ledger()
    prep = {r["key"]: r for r in rows("prepared/products.jsonl")}
    placed = {r["key"]: r for r in rows("placement/placements.jsonl")}
    last = {k: v[-1] for k, v in led.items()}
    assert last[key("13552318731")]["status"] == "published" and "store_status" not in last[key("13552318731")]
    draft = led[key("13016112970")]
    assert draft[0]["store_status"] == "DRAFT" and draft[-1]["store_status"] == "ACTIVE" and draft[-1]["activated"]
    assert last[key("13127601930")]["reason"].startswith("replaced_by:")
    assert last[key("12557420063")]["reason"].startswith("hold:")
    agency = led[key("12178430576")]
    assert agency[1]["reason"].startswith("agency_no_brand") and any(r.get("restored") for r in agency)
    assert last[key("12178430576")]["status"] == "published" and len({r["handle"] for r in agency}) == 2
    assert last[key("12080067974")]["status"] == "withdrawn" and any(r.get("restored")
                                                                     for r in led[key("12080067974")])
    assert len({r["handle"] for r in led[key("13830324906")]}) == 3
    assert prep[key("11097352600")]["status"] == "held" and key("11097352600") not in led
    assert prep[key("11097352600")]["held"][0]["code"] == "single_only"
    assert placed[key("13532274688")]["status"] == "unresolved" and key("13532274688") not in led
    assert key("5917858699") in led and key("5917858699") not in {
        e.get("key") for j in META["jobs"] for e in read_jsonl(os.path.join(FIX, "jobs", j, "events.jsonl"))}
    for pid in ("13292782760", "13492376357"):                     # not taken as a duplicate in both jobs
        for job in META["jobs"]:
            evs = read_jsonl(os.path.join(FIX, "jobs", job, "events.jsonl"))
            assert any(e.get("key") == key(pid) and str(e.get("reason", "")).startswith("duplicate_of:") for e in evs)
    a, b = (read_jsonl(os.path.join(FIX, "jobs", j, "events.jsonl")) for j in META["jobs"])
    assert {e["event"] for e in a if e.get("key") == key("12557420063")} >= {"not_taken"}
    assert {e["event"] for e in b if e.get("key") == key("12557420063")} >= {"published"}
    for pid in META["payloads"]:
        assert os.path.exists(os.path.join(SHOP_DIR, "publish", "payloads", f"{pid}.json"))
