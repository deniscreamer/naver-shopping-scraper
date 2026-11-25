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
    empty = {p["source"]["product_id"] for p in full["prepared"]
             if p["product"]["description_images_text"]["state"] == "empty"}
    assert empty == {"9703030793"}                  # every image text dropped (2026-11-18 fixture): no .ko files
    assert sorted(k.split("/")[2] for k in ko) == sorted(x["key"].split(":")[3] for x in ls
                                                         if x["key"].split(":")[3] not in empty)
    # the record keeps the blocks' key order
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
    owner_key = by_id["12950788305"]["key"]                             # 50002788, 성별 남성용 (2026-11-18)
    with open(os.path.join(shops, "fairwardgolf", "specs_by_owner.json"), "w", encoding="utf-8") as f:
        json.dump({"entries": {owner_key: {"rows": {"성별": "여성용"}, "why": "test", "at": "2026-11-18"}}}, f)
    got, count = _cached_vs_full(shops)
    assert count == {"hit": len(ls), "miss": 0}
    by_id = {p["key"].split(":")[3]: p for p in got["prepared"]}
    assert by_id["13785630702"]["product"]["description_images_text"]["state"] == "translated"
    assert (by_id["13058280430"]["product"]["brand_ko"], by_id["13058280430"]["product"]["brand_source"]) == (
        "Alvo Golf", "owner")
    owned = by_id["12950788305"]["product"]                             # the owner's row, through the cache
    assert {"label_ko": "성별", "value_ko": "여성용"} in owned["specs"] and owned["attributes"]["gender"]["value"] == "womens"
    assert "  specs_by_owner: 1 entries, 1 applied, 0 unused, 0 keys not prepared" in got["report"]


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


# ---- the owner's spec rows (specs_by_owner.json, 2026-11-18) ------------------------------------------------------

def _fixture_prepared(pid):
    """A collected fixture through prepare with its description images sidecar, as run() does."""
    from transform import prepare
    with open(os.path.join(FX, pid + ".json"), encoding="utf-8") as f:
        line = json.load(f)
    side = os.path.join(SIDECARS, pid + ".json")
    images = json.load(open(side, encoding="utf-8")) if os.path.isfile(side) else None
    return line, prepare(line, run_transform.rules_for("fairwardgolf"), "fixtures", 1, images)


def test_the_owner_corrects_a_spec_row(tmp_path):
    """2026-11-18: a string replaces the row's value (order and for_ko kept), None drops it, a row is never added;
    a label the product does not show, or a value equal to the row's, changes nothing (the latter adds no note)."""
    import copy
    from transform import _texts, text_id
    shop = tmp_path / "fairwardgolf"
    shop.mkdir()
    assert run_transform.specs_by_owner("fairwardgolf", str(tmp_path)) == {}
    (shop / "specs_by_owner.json").write_text(json.dumps({"entries": {
        "k1": {"rows": {"성별": "여성용", "없는라벨": "x"}, "why": "photo", "at": "2026-11-18"},
        "k2": {"rows": {"성별": None}, "why": "photo"}, "k3": {"rows": {"성별": "남성용"}}, "k4": {"why": "no rows"},
        "k9": {"rows": {"성별": "여성용"}}}}, ensure_ascii=False), encoding="utf-8")
    owner = run_transform.specs_by_owner("fairwardgolf", str(tmp_path))
    assert owner == {"k1": {"성별": "여성용", "없는라벨": "x"}, "k2": {"성별": None}, "k3": {"성별": "남성용"},
                     "k9": {"성별": "여성용"}}

    def product(key):
        p = {"title_ko": "웨지 세트", "brand_ko": None, "options": [], "facts": [], "personalization": [], "addons": [],
             "reviews": [], "variants": [], "attributes": {},
             "specs": [{"label_ko": "제조사", "value_ko": "A"}, {"label_ko": "성별", "value_ko": "남성용", "for_ko": ["A"]},
                       {"label_ko": "사용방향", "value_ko": "오른손용"}]}
        return {"key": key, "notes": [], "texts": _texts(p), "product": p}

    prepared = [product("k1"), product("k2"), product("k3"), product("k5")]
    untouched = copy.deepcopy(prepared[2:])
    lines = {k: {"specs": {"specs": [{"label": "성별", "value": "남성용"}]}, "details": {"name": "웨지 세트"},
                 "listing": {"query": "골프 웨지 세트"}} for k in ("k1", "k2", "k3", "k5")}
    counts = run_transform.apply_specs_by_owner(prepared, owner, lines)
    assert counts == {"entries": 4, "applied": 2, "unused": 1, "not_prepared": 1}
    p1, p2 = prepared[0], prepared[1]
    assert p1["product"]["specs"] == [{"label_ko": "제조사", "value_ko": "A"},
                                      {"label_ko": "성별", "value_ko": "여성용", "for_ko": ["A"]},
                                      {"label_ko": "사용방향", "value_ko": "오른손용"}]
    assert p1["notes"] == [{"code": "specs_by_owner", "detail": "성별: 남성용 -> 여성용"},
                           {"code": "specs_by_owner_unused", "detail": "없는라벨"}]
    ids = {t["id"] for t in p1["texts"]}
    assert text_id("spec_value", "여성용") in ids and text_id("spec_value", "남성용") not in ids
    assert p1["product"]["attributes"]["gender"]["value"] == "womens"
    assert p1["product"]["attributes"]["gender"]["evidence"][0] == {"source": "owner:성별", "value": "womens",
                                                                    "text": "여성용"}
    assert [r["label_ko"] for r in p2["product"]["specs"]] == ["제조사", "사용방향"]
    assert p2["notes"] == [{"code": "specs_by_owner", "detail": "성별: 남성용 -> dropped"}]
    assert "gender" not in p2["product"]["attributes"]          # the row was the only word: unknown, not stated
    assert prepared[2:] == untouched                            # the same value (no-op, no note); no entry


def test_the_owners_spec_row_on_the_ponytail_template():
    """2026-11-18, the wedge review: golfup's ZESTAIM Ponytail listings all carry the template row 성별 남성용; LABOUM
    12748958315 is a women's build by its photos (L-flex 40 g LABOUM shaft, pink ferrules) and its title row already
    says Women's, while the describe packet said "Gender: Men's". The owner's entry corrects that product only:
    12748958200 (same seller, same template, no entry) stays as the seller wrote it; placement is unchanged
    (50002783 is not split by gender)."""
    import copy
    import placement as PL
    from transform import text_id
    from placement_rules import profile_for
    line315, p315 = _fixture_prepared("12748958315")
    line200, p200 = _fixture_prepared("12748958200")
    for p in (p315, p200):
        assert {"label_ko": "성별", "value_ko": "남성용"} in p["product"]["specs"]
        assert p["product"]["attributes"]["gender"]["value"] == "mens"
    lines = {p315["key"]: line315, p200["key"]: line200}
    before315, before200 = copy.deepcopy(p315), copy.deepcopy(p200)
    prepared = [p315, p200]
    run_transform.apply_specs_by_owner(prepared, {p315["key"]: {"성별": "여성용"}}, lines)
    assert {"label_ko": "성별", "value_ko": "여성용"} in p315["product"]["specs"]
    assert [r["label_ko"] for r in p315["product"]["specs"]] == [r["label_ko"] for r in before315["product"]["specs"]]
    gender = p315["product"]["attributes"]["gender"]
    assert gender["value"] == "womens"
    assert {"source": "owner:성별", "value": "womens", "text": "여성용"} in gender["evidence"]
    assert {"source": "listing", "value": "-", "text": "골프 웨지 세트"} in gender["evidence"]
    gone, new = ({t["id"] for t in a["texts"]} - {t["id"] for t in b["texts"]} for a, b in
                 ((before315, p315), (p315, before315)))
    assert (gone, new) == ({text_id("spec_value", "남성용")}, {text_id("spec_value", "여성용")})
    assert p315["notes"][len(before315["notes"]):] == [{"code": "specs_by_owner", "detail": "성별: 남성용 -> 여성용"}]
    assert p200 == before200
    profile = profile_for("fairwardgolf")
    got = PL.place(p315, profile)
    assert got["status"] == "placed" and [x["leaf"] for x in got["leaves"]] == ["wedge-sets"]
    _, dropped = _fixture_prepared("12748958315")
    run_transform.apply_specs_by_owner([dropped], {p315["key"]: {"성별": None}}, lines)
    assert "성별" not in [r["label_ko"] for r in dropped["product"]["specs"]]
    assert "gender" not in dropped["product"]["attributes"]
    got = PL.place(dropped, profile)
    assert got["status"] == "placed" and [x["leaf"] for x in got["leaves"]] == ["wedge-sets"]


def test_the_owners_gender_row_keeps_the_listing_evidence_of_a_conflict():
    """2026-11-18: Bridgestone 12497168529 (50002788, split by gender) writes 성별 남성용 against a 여성 title: gender
    conflict, unresolved, no listing evidence today. Without an entry it stays so; with the owner's 여성용 the gender is
    extracted again from the line, as prepare does, so the listing's query comes back as evidence."""
    import copy
    import placement as PL
    from placement_rules import profile_for
    line, p = _fixture_prepared("12497168529")
    gender = p["product"]["attributes"]["gender"]
    assert gender["value"] == "conflict" and not [e for e in gender["evidence"] if e["source"] == "listing"]
    before = copy.deepcopy(p)
    run_transform.apply_specs_by_owner([p], {}, {p["key"]: line})
    assert p == before
    profile = profile_for("fairwardgolf")
    assert PL.place(p, profile)["status"] == "unresolved"
    run_transform.apply_specs_by_owner([p], {p["key"]: {"성별": "여성용"}}, {p["key"]: line})
    gender = p["product"]["attributes"]["gender"]
    assert gender["value"] == "womens" and gender["flags"] == []
    assert gender["evidence"] == [{"source": "owner:성별", "value": "womens", "text": "여성용"},
                                  {"source": "title", "value": "womens", "text": line["details"]["name"][:80]},
                                  {"source": "listing", "value": "womens", "text": "여성 골프채 풀세트"}]
    got = PL.place(p, profile)
    assert got["status"] == "placed" and [x["leaf"] for x in got["leaves"]] == ["womens-complete-sets"]


def test_own_row_is_the_shops_own_label_the_reseller_rule_drops():
    """2026-11-20, the knit cardigan review: 11573884405's rows (카멜브리즈 / "카멜브리즈 협력업체") are the shop's own
    label; a brand row of another firm is not."""
    def line(brand: str, maker: str) -> dict:
        return {"specs": {"facts": {"brand": {"value": brand}, "manufacturer": {"value": maker}}},
                "details": {"store": {"name": "카멜브리즈", "slug": "camelbreeze", "business": {"legal_name": "올라운드"}}}}
    assert run_transform._own_row(line("카멜브리즈", "카멜브리즈 협력업체"))
    assert not run_transform._own_row(line("DGB", "카멜브리즈 협력업체"))
    assert not run_transform._own_row(line("카멜브리즈", "카멜브리즈"))


# ---- the owner's variants left out (variants_by_owner.json, 2026-11-25) --------------------------------------------

def test_the_owners_variants_are_left_out_through_the_cache(tmp_path):
    """The owner's yes to the Fable size review (2026-11-25): a product's variants named in <shop>/variants_by_owner.json
    are left out in prepare (before the options and the sizes); the entry is in the record's signature, so a cached
    product is prepared afresh when its entry comes, changes or goes, and the others stay hits."""
    ls = collected()[:12]
    shops = _cached_shop(tmp_path, ls)
    assert run_transform.variants_by_owner("fairwardgolf", shops) == {}
    _cached_vs_full(shops)
    key = next(x["key"] for x in ls if x["key"].endswith(":10954221464"))     # 아이언샤프트 선택: 그라파이트 R .. 스틸
    path = os.path.join(shops, "fairwardgolf", "variants_by_owner.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"entries": {key: {"drop": {"아이언샤프트 선택": ["스틸", "없는값"]}, "why": "test", "at": "2026-11-25"},
                               "k-none": {"why": "no drop"}, "k-gone": {"drop": {"0": ["x"]}}}}, f, ensure_ascii=False)
    assert run_transform.variants_by_owner("fairwardgolf", shops) == {
        key: {"아이언샤프트 선택": ["스틸", "없는값"]}, "k-gone": {"0": ["x"]}}
    got, count = _cached_vs_full(shops)
    assert count == {"hit": len(ls) - 1, "miss": 1}
    p = next(p for p in got["prepared"] if p["key"] == key)
    assert "스틸" not in p["product"]["options"][0]["values_ko"]
    assert {"code": "variants_left_out_by_owner", "detail": "1 variants: 아이언샤프트 선택: 스틸"} in p["notes"]
    assert {"code": "variants_by_owner_unused", "detail": "아이언샤프트 선택: 없는값"} in p["notes"]
    assert "  variants_by_owner: 2 entries, 1 applied, 1 with a value unused, 1 keys not prepared" in got["report"]
    os.remove(path)                                                     # the entry gone: that product afresh again
    got, count = _cached_vs_full(shops)
    assert count == {"hit": len(ls) - 1, "miss": 1}
    assert not any(n["code"].startswith("variants_") and "owner" in n["code"] for p in got["prepared"] for n in p["notes"])
    assert run_transform.verify("fairwardgolf", None, shops, {})[0] == 0
