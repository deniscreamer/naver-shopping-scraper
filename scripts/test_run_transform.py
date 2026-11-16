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


def test_a_ko_file_is_rewritten_only_when_its_bytes_change(tmp_path):
    """2026-11-16: every run rewrote all 4,576 .ko files of the shop; an unchanged one keeps its mtime."""
    path = str(tmp_path / "description_images.ko.json")
    assert run_transform._write_if_changed(path, "한글 text\n") is True
    os.utime(path, (1_000_000, 1_000_000))
    assert run_transform._write_if_changed(path, "한글 text\n") is False
    assert os.stat(path).st_mtime == 1_000_000
    assert run_transform._write_if_changed(path, "한글 other\n") is True
    assert open(path, encoding="utf-8").read() == "한글 other\n" and os.stat(path).st_mtime != 1_000_000
    assert os.listdir(tmp_path) == ["description_images.ko.json"]                  # no .part left


# ---- the prepare cache (run(cache=True), 2026-11-16) -----------------------------------------------------------

SIDECARS = os.path.join(os.path.dirname(FX), "description_images")


def _cached_shop(tmp_path, ls):
    """A kept run of `ls` with the fixtures' description image sidecars."""
    import shutil
    shops = kept(tmp_path, ls)
    side = os.path.join(shops, "fairwardgolf", "description_images")
    os.makedirs(side, exist_ok=True)
    for x in ls:
        name = x["key"].split(":")[3] + ".json"
        if os.path.exists(os.path.join(SIDECARS, name)):
            shutil.copy(os.path.join(SIDECARS, name), side)
    return shops


def _add_run(tmp_path, shops, ls, n):
    """A newer kept run of `ls` (keep_run names a run by its file's mtime)."""
    src = tmp_path / f"later-{n}"
    src.mkdir()
    (src / "products.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ls),
                                        encoding="utf-8")
    os.utime(src / "products.jsonl", (1_900_000_000 + n * 60, 1_900_000_000 + n * 60))
    return os.path.basename(keep_run.keep(str(src), shops))


def _files(shops):
    """{path: bytes} of prepared/ and translation/: what a build writes."""
    out = {}
    for sub in ("prepared", "translation"):
        for d, _, names in os.walk(os.path.join(shops, "fairwardgolf", sub)):
            for name in names:
                with open(os.path.join(d, name), "rb") as f:
                    out[os.path.relpath(os.path.join(d, name), shops)] = f.read()
    return out


def _cached_vs_full(shops, choices=None):
    """run(cache=True), then a full build; both must write the same bytes. -> (cached result, {hit, miss})."""
    got = run_transform.run("fairwardgolf", None, shops, choices or {}, cache=True)
    cached = _files(shops)
    full = run_transform.run("fairwardgolf", None, shops, choices or {})
    assert cached == _files(shops)
    assert got["prepared"] == full["prepared"] and got["report"] == full["report"]
    return got, got["cache"]


def test_a_warm_cache_writes_the_same_bytes_as_a_full_build(tmp_path):
    ls = collected()
    shops = _cached_shop(tmp_path, ls)
    full = run_transform.run("fairwardgolf", None, shops, {})
    before = _files(shops)
    assert "cache" not in full and not os.path.exists(os.path.join(shops, "fairwardgolf", "prepare_cache"))
    cold = run_transform.run("fairwardgolf", None, shops, {}, cache=True)
    assert cold["cache"] == {"hit": 0, "miss": len(ls)} and _files(shops) == before
    warm = run_transform.run("fairwardgolf", None, shops, {}, cache=True)
    assert warm["cache"] == {"hit": len(ls), "miss": 0} and _files(shops) == before
    assert warm["prepared"] == full["prepared"]
    ko = [k for k in before if k.endswith(".ko.json")]
    assert len(ko) == len(ls)                                           # the record keeps the blocks' key order
    assert list(json.loads(before[ko[0]])["blocks"][0]) == ["id", "kind", "image", "text", "key", "shared"]
    records = os.listdir(os.path.join(shops, "fairwardgolf", "prepare_cache"))
    assert sorted(records) == sorted(x["key"].split(":")[3] + ".json" for x in ls)
    assert run_transform.latest_lines("fairwardgolf", None, shops)[ls[0]["key"]][:2] == (
        os.listdir(os.path.join(shops, "fairwardgolf", "collected"))[0], 1)            # still (run, n, line)


def test_each_input_of_a_product_misses_only_that_product(tmp_path, monkeypatch):
    import dataclasses
    import transform
    ls = collected()[:8]                                                # 8 products keep it quick
    shops = _cached_shop(tmp_path, ls)
    _cached_vs_full(shops)
    newer = dict(ls[0], details={**ls[0]["details"], "title": ls[0]["details"].get("title", "") + " 신상"})
    _add_run(tmp_path, shops, [newer], 1)                              # a newer collection of the product
    assert _cached_vs_full(shops)[1] == {"hit": len(ls) - 1, "miss": 1}
    run_id = _add_run(tmp_path, shops, [ls[1]], 2)                     # the same bytes, another run and line
    got, count = _cached_vs_full(shops)
    assert count == {"hit": len(ls) - 1, "miss": 1}
    assert next(p for p in got["prepared"] if p["key"] == ls[1]["key"])["source"]["run"] == run_id
    side = os.path.join(shops, "fairwardgolf", "description_images", ls[2]["key"].split(":")[3] + ".json")
    with open(side, encoding="utf-8") as f:
        sc = json.load(f)
    with open(side, "w", encoding="utf-8") as f:                       # the sidecar read again: other bytes
        json.dump(sc, f, ensure_ascii=False, indent=2)
    assert _cached_vs_full(shops)[1] == {"hit": len(ls) - 1, "miss": 1}
    os.remove(side)                                                     # no sidecar any more
    assert _cached_vs_full(shops)[1] == {"hit": len(ls) - 1, "miss": 1}
    paid = {ls[3]["key"].split(":")[3]: run_transform.PAID}            # its job's choice: free -> paid
    assert _cached_vs_full(shops, paid)[1] == {"hit": len(ls) - 1, "miss": 1}
    assert _cached_vs_full(shops, paid)[1] == {"hit": len(ls), "miss": 0}
    monkeypatch.setattr(run_transform, "_CODE_SIG", "another code")    # a change of scripts/*.py
    assert _cached_vs_full(shops, paid)[1] == {"hit": 0, "miss": len(ls)}
    table = transform._measures_table()
    monkeypatch.setattr(transform, "_measures_table", lambda: {**table, "edited": True})   # the table as loaded
    assert _cached_vs_full(shops, paid)[1] == {"hit": 0, "miss": len(ls)}
    rules = run_transform.rules_for("fairwardgolf")                    # the base rules: images' text off
    cats = {k: dataclasses.replace(v, description_images=False) for k, v in rules.categories.items()}
    monkeypatch.setattr(run_transform, "rules_for", lambda shop: dataclasses.replace(rules, categories=cats))
    assert _cached_vs_full(shops, paid)[1] == {"hit": 0, "miss": len(ls)}


def test_the_steps_across_products_never_come_from_the_cache(tmp_path):
    """A product whose record is a hit still gets what the shop's other products, files and the owner decide."""
    ls = [x for x in collected() if x["key"].split(":")[2] in (STORE, "101921971")]
    late = [x for x in ls if x["key"].split(":")[3] in ("8958060680", "13002235969", "12975257923", "12999501692")]
    shops = _cached_shop(tmp_path, [x for x in ls if x not in late])
    _cached_vs_full(shops)
    _cached_vs_full(shops)
    _add_run(tmp_path, shops, late, 1)
    import shutil
    for x in late:
        name = x["key"].split(":")[3] + ".json"
        shutil.copy(os.path.join(SIDECARS, name), os.path.join(shops, "fairwardgolf", "description_images"))
    got, count = _cached_vs_full(shops)
    assert count == {"hit": len(ls) - len(late), "miss": len(late)}
    by_id = {p["key"].split(":")[3]: p for p in got["prepared"]}
    with open(os.path.join(shops, "fairwardgolf", "translation", "13785630702", "description_images.ko.json"),
              encoding="utf-8") as f:                                   # 8958060680 of its store came: shared 2
        assert {b["shared"] for b in json.load(f)["blocks"]} >= {2}
    assert len([d for d in by_id["13058280430"]["product"]["description_dropped"]
                if d["rule"] == "shared_store_image"]) == 3
    flag = by_id["13785630702"]["product"]["description_images_text"]
    where = os.path.join(shops, "fairwardgolf", "translation", "13785630702")
    with open(os.path.join(where, "description_images.en.json"), "w", encoding="utf-8") as f:
        json.dump({"format": "x", "source_sha256": flag["sha256"], "blocks": []}, f)
    key = by_id["13058280430"]["key"]
    with open(os.path.join(shops, "fairwardgolf", "brand_by_owner.json"), "w", encoding="utf-8") as f:
        json.dump({"entries": {key: {"brand": "Alvo Golf", "why": "photo", "at": "2026-11-16"}}}, f)
    got, count = _cached_vs_full(shops)
    assert count == {"hit": len(ls), "miss": 0}
    by_id = {p["key"].split(":")[3]: p for p in got["prepared"]}
    assert by_id["13785630702"]["product"]["description_images_text"]["state"] == "translated"
    assert (by_id["13058280430"]["product"]["brand_ko"], by_id["13058280430"]["product"]["brand_source"]) == (
        "Alvo Golf", "owner")


def test_a_broken_record_is_a_miss_and_is_written_again(tmp_path):
    ls = collected()[:8]
    shops = _cached_shop(tmp_path, ls)
    _cached_vs_full(shops)
    folder = os.path.join(shops, "fairwardgolf", "prepare_cache")
    paths = [os.path.join(folder, x["key"].split(":")[3] + ".json") for x in ls[:4]]
    with open(paths[0], "rb") as f:
        data = f.read()
    cut = data.index("브".encode()) + 1                                 # in the middle of a Hangul character
    with open(paths[0], "wb") as f:
        f.write(data[:cut])
    with open(paths[1], "wb") as f:
        f.write(b"\x00garbage")
    with open(paths[2], "wb") as f:
        f.write(b"0" * 64 + data[data.index(b"\n"):])                  # another signature, the same body
    with open(paths[3], "wb") as f:
        f.write(data.split(b"\n")[0] + b"\n[1, 2]\n")                  # its signature, not a record
    assert _cached_vs_full(shops)[1] == {"hit": len(ls) - 4, "miss": 4}
    assert _cached_vs_full(shops)[1] == {"hit": len(ls), "miss": 0}
    assert not [n for n in os.listdir(folder) if n.endswith(".part")]


def test_verify_finds_a_record_that_differs_from_a_fresh_prepare(tmp_path):
    ls = collected()[:6]
    shops = _cached_shop(tmp_path, ls)
    assert run_transform.verify("fairwardgolf", None, shops, {}) == (0, [
        "verify fairwardgolf: 6 products: 0 records identical, 0 differ, 6 without a current record (prepared afresh "
        "at the next run)", "nothing compared: no current record (run run_transform.py first)"])   # not "identical"
    _cached_vs_full(shops)
    code, lines = run_transform.verify("fairwardgolf", None, shops, {})
    assert code == 0 and lines[0].startswith("verify fairwardgolf: 6 products: 6 records identical, 0 differ, 0 ")
    folder = os.path.join(shops, "fairwardgolf", "prepare_cache")
    before = {n: open(os.path.join(folder, n), "rb").read() for n in os.listdir(folder)}
    pid = ls[2]["key"].split(":")[3]
    path = os.path.join(folder, pid + ".json")
    with open(path, encoding="utf-8") as f:
        sig, body = f.read().split("\n", 1)
    record = json.loads(body)
    record["prepared"]["product"]["title_ko"] += " (stale)"             # the same signature, another output
    with open(path, "w", encoding="utf-8") as f:
        f.write(sig + "\n" + json.dumps(record, ensure_ascii=False) + "\n")
    code, lines = run_transform.verify("fairwardgolf", None, shops, {})
    assert code == 1 and lines[1] == f"  differs {ls[2]['key']}: prepared.product.title_ko"
    assert run_transform.verify("fairwardgolf", None, shops, {})[0] == 1   # verify wrote nothing
    assert {n for n in os.listdir(folder)} == set(before)
    assert run_transform._first_diff({"a": 1, "b": 2}, {"b": 2, "a": 1}) == "(key order)"
