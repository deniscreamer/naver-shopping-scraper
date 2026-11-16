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


def test_a_jobs_cut_off_listing_tail_does_not_stop_the_shops_prepare(tmp_path):
    """2026-11-16 (shop_files): a scroll job killed while appending a row left half a line; paid_choices read every
    job's listing with a bare json.loads, and every product of the shop stopped at prepare."""
    jobs, shops = tmp_path / "jobs", tmp_path / "shops"
    jobs.mkdir()
    _job(jobs, "a-paid", shops, ["5", "6"], "2026-11-12T05:00:00+00:00", paid=True, free_only=False)
    with open(jobs / "a-paid" / "listing.jsonl", "a") as f:
        f.write('{"product_id": "7", "na')
    got = run_transform.paid_choices("fairwardgolf", str(shops), str(jobs))
    assert got == {"5": run_transform.PAID, "6": run_transform.PAID}


def _junior_agency_imports(tmp_path):
    ls = []
    for name in ("11674983361", "5396141262", "5140543074"):
        with open(os.path.join(FX, name + ".json"), encoding="utf-8") as f:
            ls.append(json.load(f))
    src = tmp_path / "full-50002787"
    src.mkdir()
    (src / "products.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ls),
                                        encoding="utf-8")
    shops = tmp_path / "shops"
    keep_run.keep(str(src), str(shops))
    return str(shops)


def test_a_no_brand_agency_import_goes_on_under_the_shops_name(tmp_path):
    """2026-11-15, the owner: a purchase agency's import with no brand is no longer held; 노브랜드 becomes the shop's
    name as its vendor (translation_rules: Store.publisher)."""
    result = run_transform.run("fairwardgolf", None, _junior_agency_imports(tmp_path), choices={})
    by_id = {p["key"].split(":")[3]: p for p in result["prepared"]}
    assert by_id["11674983361"]["status"] == "ready" and by_id["11674983361"]["product"]["brand_source"] == "none"


def test_a_shop_may_still_hold_a_no_brand_agency_import(tmp_path, monkeypatch):
    """CategoryRules.agency_needs_brand (2026-11-12, three no-name US sets at $1499-1899): kept for a shop that wants
    it; held once the brand fallback found nothing."""
    import dataclasses
    from transform_shops import rules_for
    rules = rules_for("fairwardgolf")
    cats = {k: dataclasses.replace(v, agency_needs_brand=True) for k, v in rules.categories.items()}
    monkeypatch.setattr(run_transform, "rules_for", lambda shop: dataclasses.replace(rules, categories=cats))
    result = run_transform.run("fairwardgolf", None, _junior_agency_imports(tmp_path), choices={})
    by_id = {p["key"].split(":")[3]: p for p in result["prepared"]}
    assert by_id["11674983361"]["status"] == "held"
    assert [h["code"] for h in by_id["11674983361"]["held"]] == ["agency_no_brand"]
    assert by_id["5396141262"]["status"] == by_id["5140543074"]["status"] == "ready"
    assert "held fairwardgolf:naver:102563157:11674983361: agency_no_brand" in "\n".join(result["report"])


def test_a_brand_the_owner_set_by_hand_comes_first(tmp_path):
    """2026-11-15, the lens review: ALVO stamped on the heads of 13830321960, no text naming it; XINGGM on 13830322401
    whose images' PRECISE was a slogan. The owner's file wins over every step, the product's own row too."""
    import json as _json
    import brand_fallback
    from run_transform import brand_by_owner
    shop = tmp_path / "fairwardgolf"
    shop.mkdir()
    assert brand_by_owner("fairwardgolf", str(tmp_path)) == {}
    (shop / "brand_by_owner.json").write_text(_json.dumps({"entries": {
        "k1": {"brand": "Alvo Golf", "why": "photo", "at": "2026-11-15"}, "k2": {"brand": "", "why": "none"}}}))
    owner = brand_by_owner("fairwardgolf", str(tmp_path))
    assert owner == {"k1": "Alvo Golf"}
    prepared = [{"key": "k1", "notes": [], "texts": [], "product": {"title_ko": "남성 골프 웨지 세트", "brand_ko": None}},
                {"key": "k3", "notes": [], "texts": [], "product": {"title_ko": "웨지 세트", "brand_ko": None}}]
    brand_fallback.fill(prepared, lambda k: [], {}, lambda p: [], [], owner)
    assert (prepared[0]["product"]["brand_ko"], prepared[0]["product"]["brand_source"]) == ("Alvo Golf", "owner")
    assert prepared[1]["product"]["brand_source"] == "none"
