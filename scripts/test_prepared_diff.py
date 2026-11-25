"""Offline tests for prepared_diff.py and run_transform.py --diff / --shops-root.

fixtures/prepared_diff/: two real versions of a few prepared products (cases.json says where each side came from:
the state backup of 2026-11-15 vs the prepared file of 2026-11-16, and fixtures/prepared/ at two commits); the shop
fixture (conftest.shop_fixture) gives a real ledger for --published-only.

    .venv/bin/python -m pytest scripts/test_prepared_diff.py -q
"""
import json
import os
import time

import pytest

import prepared_diff
import run_transform
import shop_files
import shop_view
from test_run_transform import collected, kept

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "prepared_diff")
OLD, NEW = os.path.join(FX, "old.jsonl"), os.path.join(FX, "new.jsonl")
K = "fairwardgolf:naver:"


def rows_of(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def write(path, rows, tail=""):
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows) + tail)
    return str(path)


def run(capsys, *argv):
    code = prepared_diff.main([str(a) for a in argv])
    out, err = capsys.readouterr()
    return code, [x.split("\t") for x in out.splitlines()], out, err


# --- the real pairs -------------------------------------------------------------------------------------------------

def test_the_real_pairs_show_each_kind_of_change(capsys):
    code, rows, _, err = run(capsys, OLD, NEW)
    assert code == 1
    got = {(r[0][len(K):], r[1], r[2]): (r[3], r[4]) for r in rows}
    assert got[("102750441:13762670577", "changed", "status")] == ("ready", "held")
    assert got[("102750441:13762670577", "changed", "held")] == (
        "-", "single_only: the title sells one piece (1개, 1pc)")
    assert got[("1100167681:13830308222", "changed", "brand")] == ("Gowolf (title_known)", "Gowolf (title)")
    assert got[("1100167681:13830308222", "changed", "notes")] == (
        "brand_fallback: title_known: Gowolf", "brand_fallback: title: Gowolf")
    assert got[("100342675:13446843026", "changed", "package.package_weight_g")] == (
        "9784 (composed c2)", "9818 (composed c2)")
    assert got[("100342675:13446843026", "changed", "package.product_weight_g")] == (
        "7784 (composed c2)", "7818 (composed c2)")
    old_v, new_v = got[("101054995:13099257309", "changed", "variants")]
    assert old_v.split(" | ") == ["10.5도 R+아이언 R / 5번 R / 4번 SR", "10.5도 R+아이언 R / 5번 R / 5번 S"]
    assert new_v.split(" | ") == ["10.5도 R+아이언 R / 4번 R / 4번 R", "10.5도 R+아이언 R / 3번 R / 3번 R"]
    assert got[("1100071177:13312194411", "changed", "other")] == (      # the names once, in the new column
        "-", "product.description_dropped | product.description_images")
    assert got[("1100071177:13312194411", "changed", "notes")][0] == "-"
    assert "(7 of 7 listing groups)" in got[("102206584:13492376357", "changed", "notes")][0]
    assert got[("1100071177:13312174622", "added", "status")] == ("-", "held")
    assert got[("100113347:13780241403", "removed", "status")] == ("ready", "-")
    assert not any(k[0] == "100416178:5917858699" for k in got)            # the same on both sides
    assert [r[0] for r in rows] == sorted(r[0] for r in rows)
    assert err.strip() == ("prepared_diff: 8 old, 8 new, 9 compared: 1 added, 1 removed, 6 changed (brand 1, held 1, "
                           "notes 3, other 2, package 2, status 1, variants 1), 1 the same")


def test_fields_limit_what_is_compared(capsys):
    code, rows, _, _ = run(capsys, OLD, NEW, "--fields", "status,brand")
    assert code == 1
    assert sorted((r[0][len(K):], r[2]) for r in rows) == [
        ("100113347:13780241403", "status"), ("102750441:13762670577", "status"),
        ("1100071177:13312174622", "status"), ("1100167681:13830308222", "brand")]
    assert run(capsys, OLD, NEW, "--fields", "price")[1] == [r for r in rows if r[1] != "changed"]
    code, _, _, err = run(capsys, OLD, NEW, "--fields", "status,colour")
    assert code == 2 and "unknown colour" in err


def test_json_and_keys_out(capsys, tmp_path):
    out_keys = tmp_path / "changed.txt"
    code, _, out, _ = run(capsys, OLD, NEW, "--json", "--keys-out", out_keys)
    assert code == 1
    data = json.loads(out)
    assert data["counts"]["changed"] == 6 and data["counts"]["same"] == 1
    by_key = {p["key"]: p for p in data["products"]}
    assert by_key[K + "102750441:13762670577"]["fields"]["status"] == {"old": "ready", "new": "held"}
    assert shop_view.read_refs(str(out_keys)) == [p["key"] for p in data["products"]]   # a --keys-file
    assert len(shop_view.read_refs(str(out_keys))) == 8


def test_the_same_file_twice_is_exit_0_and_prints_nothing(capsys):
    code, rows, out, err = run(capsys, NEW, NEW)
    assert (code, out) == (0, "")
    assert "0 added, 0 removed, 0 changed, 8 the same" in err


# --- --published-only over the shop fixture's real ledger -------------------------------------------------------

def test_published_only_keeps_the_products_whose_last_ledger_row_is_published(capsys, tmp_path, shop_fixture):
    prepared = os.path.join(shop_fixture.shops, shop_fixture.shop, "prepared", "products.jsonl")
    rows = rows_of(prepared)
    for r in rows:
        r["product"]["brand_ko"] = "changed"
    edited = write(tmp_path / "edited.jsonl", rows)
    code, all_rows, _, _ = run(capsys, prepared, edited, "--fields", "brand")
    assert code == 1 and len(all_rows) == len(rows)
    code, got, _, _ = run(capsys, prepared, edited, "--fields", "brand", "--published-only",
                          "--shops-root", shop_fixture.shops)              # the shop: the new file's records'
    last = {}
    for r in rows_of(os.path.join(shop_fixture.shops, shop_fixture.shop, "publish", "published.jsonl")):
        last[r["key"]] = r["status"]
    live = {k for k, s in last.items() if s == "published"}
    assert {r[0] for r in got} == live & {r["key"] for r in rows}
    assert shop_fixture.key("13762670577") not in {r[0] for r in got}     # withdrawn
    assert shop_fixture.key("13830324906") in {r[0] for r in got}         # live, rehandled twice


def test_a_torn_last_ledger_line_is_ignored_as_the_other_readers_do(capsys, shop_fixture):
    ledger = os.path.join(shop_fixture.shops, shop_fixture.shop, "publish", "published.jsonl")
    before = prepared_diff.published_keys(shop_fixture.shop, shop_fixture.shops)
    withdrawn = shop_fixture.key("13762670577")
    assert withdrawn not in before and len(before) == 7
    with open(ledger, "a", encoding="utf-8") as f:
        f.write('{"key": "' + withdrawn + '", "status": "publi')         # a stopped run's cut-off line
    shop_files._WARNED.discard(ledger)
    assert prepared_diff.published_keys(shop_fixture.shop, shop_fixture.shops) == before
    assert "a cut-off last line ignored" in capsys.readouterr().err


def test_published_only_with_no_shop_named_or_found_stops(capsys, tmp_path):
    empty = write(tmp_path / "empty.jsonl", [])
    code, _, _, err = run(capsys, empty, empty, "--published-only")
    assert code == 2 and "--published-only needs --shop" in err
    code, _, _, _ = run(capsys, empty, empty, "--published-only", "--shop", "nosuchshop", "--shops-root", tmp_path)
    assert code == 0                                                     # no ledger: nothing published, nothing listed


# --- broken, missing, empty, big ----------------------------------------------------------------------------------

def test_a_missing_file_is_exit_2(capsys, tmp_path):
    for argv in ((tmp_path / "nope.jsonl", NEW), (OLD, tmp_path / "nope.jsonl")):
        code, _, out, err = run(capsys, *argv)
        assert (code, out) == (2, "") and "no file" in err and "nope.jsonl" in err


def test_a_torn_last_line_of_a_prepared_file_is_an_error(capsys, tmp_path):
    torn = write(tmp_path / "torn.jsonl", rows_of(NEW), tail='{"key": "fairwardgolf:naver:1:2", "stat')
    code, _, out, err = run(capsys, OLD, torn)
    assert (code, out) == (2, "")
    assert "torn.jsonl:9: not a JSON line" in err


def test_an_empty_side_lists_every_product_as_added_or_removed(capsys, tmp_path):
    empty = write(tmp_path / "products.jsonl", [])
    code, rows, _, _ = run(capsys, empty, NEW)
    assert code == 1 and {r[1] for r in rows} == {"added"} and len(rows) == 8
    code, rows, _, _ = run(capsys, OLD, empty)
    assert code == 1 and {r[1] for r in rows} == {"removed"} and len(rows) == 8
    assert run(capsys, empty, empty)[0] == 0


def test_a_key_twice_counts_its_last_line(capsys, tmp_path):
    old = rows_of(OLD)
    stale = json.loads(json.dumps(old[0]))
    stale["status"] = "held"
    path = write(tmp_path / "dup.jsonl", [stale, *old])
    assert run(capsys, OLD, path)[0] == 0


def test_notes_in_another_order_and_long_lists(capsys, tmp_path):
    old = rows_of(OLD)
    new = json.loads(json.dumps(old))
    p = next(r for r in new if len(r["notes"]) > 1)
    p["notes"].reverse()
    q = next(r for r in new if len(r["product"].get("variants") or []) > 1)
    base = q["product"]["variants"][0]
    q["product"]["variants"] = [dict(base, options_ko=[f"opt {i}"]) for i in range(14)]
    q["product"]["variants"][3]["available"] = False
    code, rows, _, _ = run(capsys, OLD, write(tmp_path / "new.jsonl", new), "--fields", "notes,variants")
    got = {(r[0], r[2]): (r[3], r[4]) for r in rows}
    assert got[(p["key"], "notes")] == ("(order)", "(order)")
    shown = got[(q["key"], "variants")][1].split(" | ")
    assert len(shown) == 11 and shown[-1] == "(+4 more)" and shown[3] == "opt 3 [sold out]"


def test_a_shop_sized_file_is_read_in_seconds(capsys, tmp_path):
    base = rows_of(NEW)
    old, new = [], []
    for i in range(3000):
        r = json.loads(json.dumps(base[i % len(base)]))
        r["key"] = f"fairwardgolf:naver:{i}:{i}"
        old.append(r)
        if i % 500 == 0:
            r = json.loads(json.dumps(r))
            r["status"] = "held" if r["status"] == "ready" else "ready"
        new.append(r)
    a, b = write(tmp_path / "a.jsonl", old), write(tmp_path / "b.jsonl", new)
    start = time.monotonic()
    code, rows, _, err = run(capsys, a, b, "--fields", "status")
    assert time.monotonic() - start < 20
    assert code == 1 and len(rows) == 6 and "6 changed (status 6), 2994 the same" in err


# --- run_transform.py --diff / --shops-root -----------------------------------------------------------------------

def test_run_transform_diff_compares_with_the_file_before_the_run(tmp_path, capsys):
    shops = kept(tmp_path, collected()[:3])
    assert run_transform.main(["fairwardgolf", "--shops-root", shops, "--diff"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "run_transform: diff: 0 old, 3 new, 3 compared: 3 added, 0 removed, 0 changed, 0 the same" in out
    assert len([x for x in out if "\tadded\tstatus\t-\t" in x]) == 3
    path = os.path.join(shops, "fairwardgolf", "prepared", "products.jsonl")
    rows = rows_of(path)
    rows[0]["product"]["brand_ko"] = "edited by hand"
    gone = json.loads(json.dumps(rows[1]))
    gone["key"] = "fairwardgolf:naver:1:1"
    write(path, [*rows, gone])
    assert run_transform.main(["fairwardgolf", "--shops-root", shops, "--diff"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert "run_transform: diff: 4 old, 3 new, 4 compared: 0 added, 1 removed, 1 changed (brand 1), 2 the same" in out
    tsv = [x.split("\t") for x in out if "\t" in x]
    assert [(r[0], r[1], r[2]) for r in tsv] == [(rows[0]["key"], "changed", "brand"),
                                                 ("fairwardgolf:naver:1:1", "removed", "status")]
    assert tsv[0][3].startswith("edited by hand")


def test_run_transform_without_diff_prints_no_diff(tmp_path, capsys):
    shops = kept(tmp_path, collected()[:2])
    assert run_transform.main(["fairwardgolf", "--shops-root", shops]) == 0
    out = capsys.readouterr().out
    assert "diff" not in out and "\t" not in out
    assert os.path.exists(os.path.join(shops, "fairwardgolf", "prepared", "products.jsonl"))


def test_run_transform_diff_waits_for_no_one_under_the_shops_lock(tmp_path, capsys):
    shops = kept(tmp_path, collected()[:2])
    with shop_files.shop_lock(shops, "fairwardgolf", "job.py run x"):
        assert run_transform.main(["fairwardgolf", "--shops-root", shops, "--diff"]) == 2
    assert "run_transform: stop: fairwardgolf is busy" in capsys.readouterr().out
    assert not os.path.exists(os.path.join(shops, "fairwardgolf", "prepared"))


def test_run_transform_diff_stops_on_a_broken_prepared_file(tmp_path, capsys):
    shops = kept(tmp_path, collected()[:2])
    os.makedirs(os.path.join(shops, "fairwardgolf", "prepared"))
    path = os.path.join(shops, "fairwardgolf", "prepared", "products.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"key": "a"}\nnot json\n{"key": "b"}\n')
    assert run_transform.main(["fairwardgolf", "--shops-root", shops, "--diff"]) == 2
    assert "run_transform: stop: --diff:" in capsys.readouterr().out
    with open(path, encoding="utf-8") as f:
        assert f.read().startswith('{"key": "a"}')                       # nothing written


def test_run_transform_diff_is_not_with_verify(tmp_path):
    with pytest.raises(SystemExit) as e:
        run_transform.main(["fairwardgolf", "--verify", "--diff"])
    assert e.value.code == 2


def test_run_transform_verify_reads_the_shops_root_given(tmp_path, capsys):
    shops = kept(tmp_path, collected()[:2])
    assert run_transform.main(["fairwardgolf", "--shops-root", shops]) == 0
    capsys.readouterr()
    assert run_transform.main(["fairwardgolf", "--shops-root", shops, "--verify"]) == 0
    assert capsys.readouterr().out.startswith("run_transform: ")


def test_other_names_a_part_once_and_says_which_side_has_it_alone():
    import prepared_diff as D
    old = {"key": "k", "status": "ready", "source": {"a": 1}, "gone": 1, "product": {}}
    new = {"key": "k", "status": "ready", "source": {"a": 2}, "came": 1, "product": {}}
    got = D.compare(D.summary(old), D.summary(new), ["other"])
    assert got == {"other": {"old": "", "new": "came (new only) | gone (old only) | source"}}
    assert D.tsv_lines([{"key": "k", "change": "changed", "fields": got}]) == [
        "k\tchanged\tother\t-\tcame (new only) | gone (old only) | source"]


def test_published_only_says_so_in_the_summary(capsys, shop_fixture):
    import prepared_diff as D
    path = os.path.join(shop_fixture.shops, shop_fixture.shop, "prepared", "products.jsonl")
    assert D.main([path, path, "--published-only", "--shops-root", shop_fixture.shops]) == 0
    assert "compared (published only): 0 added" in capsys.readouterr().err


def test_a_prepare_of_a_copy_with_copy_of_equals_the_prepare_in_place(shop_fixture, tmp_path, monkeypatch, capsys):
    """2026-11-16 review: `--shops-root <clone> --diff` prepared the clone with no paid variant (the jobs belong to the
    real root) and no brand dictionary (loaded for the real root only): a false diff. --copy-of ROOT takes both as
    for ROOT. The fixture's real products: job B made with paid variants takes 5 of them (a listing.jsonl added)."""
    import shutil
    fx = shop_fixture
    job = os.path.join(fx.jobs, fx.jobs_ids[1])
    with open(os.path.join(job, "job.json"), encoding="utf-8") as f:
        meta = json.load(f)
    meta["free_only"] = False                                       # paid_variants: the paid variants, no add-on
    with open(os.path.join(job, "job.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    pids = ["5917858699", "11097352600", "13016112970", "13552318731", "13830324906"]   # their prepare depends on it
    with open(os.path.join(job, "listing.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps({"product_id": p}) + "\n" for p in pids))
    real = os.path.abspath(fx.shops)
    seen = []
    def known_brands(root):
        seen.append(root)
        return ["테스트브랜드"] if os.path.abspath(root) == real else []
    monkeypatch.setattr(run_transform, "_known_brands", known_brands)
    clone = str(tmp_path / "clone")
    shutil.copytree(fx.shops, clone)

    def prepared(root, *flags):
        assert run_transform.main([fx.shop, "--shops-root", root, "--jobs-root", fx.jobs, "--full", *flags]) == 0
        capsys.readouterr()
        with open(os.path.join(root, fx.shop, "prepared", "products.jsonl"), encoding="utf-8") as f:
            return f.read()
    in_place = prepared(fx.shops)
    assert run_transform.paid_choices(fx.shop, fx.shops, fx.jobs) == {p: run_transform.VARIANTS for p in pids}
    assert prepared(clone) != in_place                              # the clone alone: no paid variant (the bug)
    assert run_transform.paid_choices(fx.shop, clone, fx.jobs) == {}
    seen.clear()
    assert prepared(clone, "--copy-of", fx.shops) == in_place
    assert seen == [fx.shops]                                       # the dictionary loaded as for the real root


def test_a_category_defaults_kind_and_numbers_show():
    """2026-11-25 (50002816's suit kind narrowed): 9595746260's rain skirt moved from the suit's 850 g box to the light
    kind's 280 g at the same table_version; --diff read only value / source / confidence and called it the same."""
    import prepared_diff as D

    def rec(kind, low, central, high):
        field = {"source": "category_default", "confidence": 1, "low": low, "central": central, "high": high,
                 "table_version": 19, **({"kind": kind} if kind else {})}
        return {"key": "k", "status": "ready", "product": {"variants": [{"package": {"package_weight_g": field}}]}}
    got = D.compare(D.summary(rec("suit", 600, 850, 1200)), D.summary(rec("light", 200, 280, 450)), ["package"])
    assert got == {"package.package_weight_g": {"old": "850 of 600-1200 (category_default suit c1)",
                                                "new": "280 of 200-450 (category_default light c1)"}}
    assert D.compare(D.summary(rec(None, 300, 450, 800)), D.summary(rec("suit", 300, 450, 800)), ["package"]) == {
        "package.package_weight_g": {"old": "450 of 300-800 (category_default c1)",
                                     "new": "450 of 300-800 (category_default suit c1)"}}
    assert D.compare(D.summary(rec("suit", 600, 850, 1200)), D.summary(rec("suit", 600, 850, 1200)), ["package"]) == {}
