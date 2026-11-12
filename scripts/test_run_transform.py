"""Offline tests for run_transform.py's run-level steps (the per-product prepare is in test_transform.py).

fixtures/collected/<id>.json: real collected lines (research run20 / run40b, 2026-11-07); ten are store 100568453,
whose header and footer banners repeat on its listings (shared_images.py).

    .venv/bin/python -m pytest scripts/test_run_transform.py -q
"""
import json
import os

import keep_run
import run_transform

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "collected")
STORE = "100568453"


def collected():
    """The full sets' fixtures (a kept run holds one category; the junior clubs' are 50002787, 2026-11-12)."""
    out = []
    for name in sorted(os.listdir(FX)):
        with open(os.path.join(FX, name), encoding="utf-8") as f:
            line = json.load(f)
        if str(((line.get("specs") or {}).get("category") or {}).get("id")) == "50002788":
            out.append(line)
    return out


def kept(tmp_path, ls):
    src = tmp_path / "full-50002788"
    src.mkdir()
    (src / "products.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ls),
                                        encoding="utf-8")
    shops = tmp_path / "shops"
    keep_run.keep(str(src), str(shops))
    return str(shops)


def test_store_banners_leave_the_run_before_the_files_are_written(tmp_path):
    ls = collected()
    assert sum(x["key"].split(":")[2] == STORE for x in ls) == 10
    shops = kept(tmp_path, ls)
    result = run_transform.run("fairwardgolf", None, shops)
    with open(os.path.join(result["out_dir"], "products.jsonl"), encoding="utf-8") as f:
        written = {json.loads(x)["key"].split(":")[3]: json.loads(x) for x in f}
    assert written == {p["key"].split(":")[3]: p for p in result["prepared"]}
    p = written["13058280430"]
    dropped = [d["text"] for d in p["product"]["description_dropped"] if d["rule"] == "shared_store_image"]
    assert [x.split("?")[0].rsplit("/", 1)[-1] for x in dropped] == [
        "30434463209514390_345786175.jpg", "60948062508870618_280838627.jpg", "22313003105171778_1094441035.jpg"]
    assert not set(dropped) & set(p["product"]["description_images"])
    assert "description_shared_images" in [n["code"] for n in p["notes"]]
    shared = [p for p in written.values() if any(n["code"] == "description_shared_images" for n in p["notes"])]
    assert {p["source"]["channel_no"] for p in shared} == {STORE} and len(shared) == 10
    assert sum(d["rule"] == "shared_store_image" for p in written.values()
               for d in p["product"]["description_dropped"]) == 26
    assert "description_shared_images': 10" in result["report"][0]
    assert result["report"][1] == "  shared store images: 26 dropped from 10 products of 1 store(s)"


def test_a_run_without_the_store_is_unchanged(tmp_path):
    ls = [x for x in collected() if x["key"].split(":")[2] != STORE]
    result = run_transform.run("fairwardgolf", None, kept(tmp_path, ls))
    assert not any(d["rule"] == "shared_store_image" for p in result["prepared"]
                   for d in p["product"]["description_dropped"])
    assert not any(line.startswith("  shared store images") for line in result["report"])


def _job(root, name, shops_root, ids, created, **meta):
    folder = root / name
    folder.mkdir()
    (folder / "job.json").write_text(json.dumps({"shop": "fairwardgolf", "shops_root": str(shops_root),
                                                 "created_at": created, **meta}))
    (folder / "listing.jsonl").write_text("".join(json.dumps({"product_id": i}) + "\n" for i in ids))


def test_each_product_keeps_its_own_jobs_paid_choice(tmp_path):
    """2026-11-11: the transform prepares the whole shop, and a --paid job of 50002787 turned the paid variants of
    101 published full sets on; a job's choice now goes with its own products only."""
    jobs, shops = tmp_path / "jobs", tmp_path / "shops"
    jobs.mkdir()
    _job(jobs, "a-old", shops, ["1"], "2026-11-08T00:00:00+00:00", paid=True)               # no free_only: free
    _job(jobs, "b-free", shops, ["2", "3"], "2026-11-10T00:00:00+00:00", paid=False, free_only=True)
    _job(jobs, "c-variants", shops, ["3", "4"], "2026-11-11T12:00:00+00:00", paid=True, paid_variants=True,
         free_only=True)
    _job(jobs, "d-paid", shops, ["5"], "2026-11-12T05:00:00+00:00", paid=True, paid_variants=False, free_only=False)
    _job(jobs, "e-trial", tmp_path / "trial", ["6"], "2026-11-12T06:00:00+00:00", paid=True, free_only=False)
    _job(jobs, "_superseded-x", shops, ["7"], "2026-11-12T07:00:00+00:00", paid=True, free_only=False)
    got = run_transform.paid_choices("fairwardgolf", str(shops), str(jobs))
    assert got == {"3": run_transform.VARIANTS, "4": run_transform.VARIANTS, "5": run_transform.PAID}
