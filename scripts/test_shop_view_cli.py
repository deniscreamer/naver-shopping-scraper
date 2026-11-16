"""shop_view.py show / query / ledger / history / check (2026-11-16, the owner's five tools) on the real-data shop
fixture (conftest `shop_fixture`, fixtures/shop/): the fields of a product, one file's record (--raw, --path), the
filters of query, the ledger's events, a product's history, a plan checked against the files; the edges: a cut-off
last ledger line, a broken prepared line, an empty or missing shop, an unknown or ambiguous ref, missing files, a
big prepared file. Offline, read only.

    .venv/bin/python -m pytest scripts/test_shop_view_cli.py -q
"""
import json
import os
import time

import pytest

import shop_view as V
from shop_files import read_jsonl

LIVE, DRAFTED, RESTORED, THREE = "13552318731", "13016112970", "5917858699", "13830324906"
SINGLE, UNRESOLVED, HOLD, REPLACED = "11097352600", "13532274688", "12557420063", "13127601930"


def run(capsys, fx, *argv):
    """(exit code, stdout, stderr) of shop_view.py on the fixture."""
    code = V.main([*argv[:2], "--shops-root", fx.shops, *argv[2:]])
    out = capsys.readouterr()
    return code, out.out, out.err


def run_json(capsys, fx, *argv):
    code, out, _ = run(capsys, fx, *argv, "--json")
    return code, json.loads(out)


def usage(capsys, fx, *argv):
    with pytest.raises(SystemExit) as e:
        V.main([*argv[:2], "--shops-root", fx.shops, *argv[2:]])
    assert e.value.code == 2
    return capsys.readouterr().err


def prepared_path(fx):
    return os.path.join(fx.shops, fx.shop, "prepared", "products.jsonl")


def ledger_path(fx):
    return os.path.join(fx.shops, fx.shop, "publish", "published.jsonl")


# ---- the pieces ------------------------------------------------------------------------------------------------

def test_store_state_and_ledger_event():
    assert V.store_state(None) == "none"
    assert V.store_state({"status": "published"}) == "active"               # the old rows: no store_status
    assert V.store_state({"status": "published", "store_status": "DRAFT"}) == "draft"
    assert V.store_state({"status": "withdrawn", "store_status": "DRAFT"}) == "withdrawn"
    assert V.state_matches("draft", "published") and V.state_matches("active", "published")
    assert not V.state_matches("withdrawn", "published") and V.state_matches("none", "any")
    assert V.ledger_event({"status": "withdrawn"}) == "withdrawn"
    assert V.ledger_event({"status": "published", "created": True}) == "created"
    assert V.ledger_event({"status": "published", "created": False}) == "sent"
    assert V.ledger_event({"status": "published", "digest": "", "restored": "owner"}) == "restored"
    assert V.ledger_event({"status": "published", "at": "2026-11-16T07:21:12Z",
                           "activated": "2026-11-16T07:21:26Z"}) == "activated"
    # a restore of an activated row keeps `activated` (earlier than its at): a restore, not an activation
    assert V.ledger_event({"status": "published", "digest": "", "restored": "x", "at": "2026-11-16T08:22:38Z",
                           "activated": "2026-11-16T07:21:26Z"}) == "restored"
    assert V.row_time({"at": "2026-11-16T08:43:25Z", "activated": "2026-11-16T08:52:36Z"}) == "2026-11-16T08:52:36Z"
    assert V.cell(None) == "" and V.cell(["a", "b"]) == "a,b" and V.cell("a\tb\nc") == "a b c"


def test_fields_of_every_case(shop_fixture):
    fx = shop_fixture
    files = V.ShopFiles(fx.shop, fx.shops)
    assert set(files.keys()) == set(fx.cases)
    rows = {k: V.fields(files, k) for k in fx.cases}
    assert all(set(r) == set(V.FIELDS) for r in rows.values())
    live = rows[fx.key(LIVE)]
    assert (live["state"], live["store_status"], live["prepared"], live["placement"]) == \
        ("active", None, "ready", "placed")
    assert live["leaves"] == ["wedge-sets"] and live["description"] == "ok" and live["handle"]
    assert rows[fx.key(DRAFTED)]["state"] == "active" and rows[fx.key(DRAFTED)]["store_status"] == "ACTIVE"
    assert rows[fx.key(SINGLE)]["held"] == ["single_only"] and rows[fx.key(SINGLE)]["state"] == "none"
    assert rows[fx.key(UNRESOLVED)]["placement"] == "unresolved"
    assert rows[fx.key(HOLD)]["reason"].startswith("hold: copy of live")
    assert rows[fx.key(RESTORED)]["description"] is None
    pending = rows[fx.key("13292782760")]
    assert pending["translation"] == "pending" and pending["title_en"] == "" and pending["title"] == pending["title_ko"]
    assert "brand_fallback" in rows[fx.key(UNRESOLVED)]["notes"]
    states = [r["state"] for r in rows.values()]
    assert (states.count("active"), states.count("withdrawn"), states.count("none")) == (7, 5, 4)


# ---- show -------------------------------------------------------------------------------------------------------

def test_show_blocks_fields_and_json(shop_fixture, capsys):
    fx = shop_fixture
    code, out, _ = run(capsys, fx, "show", fx.shop, THREE)
    lines = out.splitlines()
    assert code == 0 and lines[0] == f"== {fx.key(THREE)}"
    assert "state\tactive" in lines and "leaves\twedge-sets" in lines
    assert len(lines) == len(V.FIELDS)                     # the header line, then every field but key
    code, out, _ = run(capsys, fx, "show", fx.shop, THREE, LIVE, "--fields", "key,state,status,held")
    assert out.splitlines() == ["key\tstate\tprepared\theld", f"{fx.key(THREE)}\tactive\tready\t",
                                f"{fx.key(LIVE)}\tactive\tready\t"]
    code, rows = run_json(capsys, fx, "show", fx.shop, SINGLE, "--fields", "held,note")
    assert rows == [{"held": ["single_only"],
                     "notes": ["reviews_cleaned", "paid_addons_left_out"]}]


def test_show_raw_and_path(shop_fixture, capsys):
    fx = shop_fixture
    code, out, _ = run(capsys, fx, "show", fx.shop, DRAFTED, "--raw", "ledger", "--path", "store_status")
    assert (code, out) == (0, "ACTIVE\n")
    code, out, _ = run(capsys, fx, "show", fx.shop, DRAFTED, "--raw", "prepared")
    assert json.loads(out)["key"] == fx.key(DRAFTED)
    code, rows = run_json(capsys, fx, "show", fx.shop, DRAFTED, LIVE, "--raw", "placement", "--path", "leaves.0.leaf")
    assert rows == [{"key": fx.key(DRAFTED), "value": "wedge-sets"}, {"key": fx.key(LIVE), "value": "wedge-sets"}]
    code, out, _ = run(capsys, fx, "show", fx.shop, DRAFTED, LIVE, "--raw", "description", "--path", "status")
    assert out.splitlines() == [f"== {fx.key(DRAFTED)}", "ok", f"== {fx.key(LIVE)}", "ok"]
    code, out, _ = run(capsys, fx, "show", fx.shop, DRAFTED, "--raw", "collected", "--path", "listing.product_id")
    assert (code, out) == (0, DRAFTED + "\n")                       # the newest collected run's line
    code, out, _ = run(capsys, fx, "show", fx.shop, DRAFTED, "--raw", "translated", "--path", "status")
    assert (code, out) == (0, "translated\n")


def test_show_missing_record_or_path_is_exit_1(shop_fixture, capsys):
    fx = shop_fixture
    code, out, err = run(capsys, fx, "show", fx.shop, RESTORED, "--raw", "description")
    assert code == 1 and out == "null\n" and "no description record" in err
    code, out, err = run(capsys, fx, "show", fx.shop, LIVE, "--raw", "ledger", "--path", "nope.0")
    assert code == 1 and "no nope.0 in its ledger record" in err
    code, out, err = run(capsys, fx, "show", fx.shop, LIVE, "--raw", "placement", "--path", "leaves.9")
    assert code == 1


def test_show_unknown_and_ambiguous_refs(shop_fixture, capsys):
    fx = shop_fixture
    code, out, err = run(capsys, fx, "show", fx.shop, "no-such-handle", LIVE, "--fields", "key")
    assert code == 1 and "no-such-handle: no product of fairwardgolf matches" in err
    assert out.splitlines() == ["key", fx.key(LIVE)]                 # the others still shown
    row = next(r for r in read_jsonl(prepared_path(fx)) if r["key"] == fx.key(LIVE))
    with open(prepared_path(fx), "a", encoding="utf-8") as f:
        f.write(json.dumps({**row, "key": f"{fx.shop}:naver:999:{LIVE}"}, ensure_ascii=False) + "\n")
    code, out, err = run(capsys, fx, "show", fx.shop, LIVE)
    assert code == 1 and out == "" and "2 products match" in err and f"{fx.shop}:naver:999:{LIVE}" in err


def test_show_usage_errors(shop_fixture, capsys):
    fx = shop_fixture
    assert "--path needs --raw" in usage(capsys, fx, "show", fx.shop, LIVE, "--path", "a")
    assert "unknown field nope" in usage(capsys, fx, "show", fx.shop, LIVE, "--fields", "key,nope")
    assert "one or more refs" in usage(capsys, fx, "show", fx.shop)
    assert "one or the other" in usage(capsys, fx, "show", fx.shop, LIVE, "--raw", "ledger", "--fields", "key")
    assert "no shop folder" in usage(capsys, fx, "show", "noshop", LIVE)


def test_show_keys_file_and_job(shop_fixture, capsys, tmp_path):
    fx = shop_fixture
    keys = tmp_path / "keys.tsv"
    keys.write_text(f"# picked\n{LIVE}\tlive\n\n{fx.key(SINGLE)}\n", encoding="utf-8")
    code, out, _ = run(capsys, fx, "show", fx.shop, "--keys-file", str(keys), "--fields", "key")
    assert out.splitlines() == ["key", fx.key(LIVE), fx.key(SINGLE)]
    job_b = fx.jobs_ids[1]
    code, out, _ = run(capsys, fx, "show", fx.shop, "--job", job_b, "--event", "published", "--jobs-root", fx.jobs,
                       "--fields", "key")
    published = [e["key"] for e in read_jsonl(os.path.join(fx.jobs, job_b, "events.jsonl"), tail_ok=True)
                 if e.get("event") == "published"]
    assert code == 0 and out.splitlines()[1:] == list(dict.fromkeys(published))


# ---- query -------------------------------------------------------------------------------------------------------

def keys_of(out):
    return [x.split("\t")[0] for x in out.splitlines()]


def test_query_all_and_columns(shop_fixture, capsys):
    fx = shop_fixture
    code, out, _ = run(capsys, fx, "query", fx.shop)
    assert code == 0 and set(keys_of(out)) == set(fx.cases)
    assert all(len(x.split("\t")) == len(V.QUERY_COLUMNS) for x in out.splitlines())
    code, rows = run_json(capsys, fx, "query", fx.shop, "--fields", "key,state")
    assert {r["key"]: r["state"] for r in rows}[fx.key(HOLD)] == "withdrawn"


def test_query_where(shop_fixture, capsys):
    fx = shop_fixture
    _, out, _ = run(capsys, fx, "query", fx.shop, "--where", "status=held")
    assert sorted(keys_of(out)) == sorted([fx.key(SINGLE), fx.key("13762670577")])
    _, out, _ = run(capsys, fx, "query", fx.shop, "--where", "held=single_only", "--where", "state=none")
    assert keys_of(out) == [fx.key(SINGLE)]
    _, out, _ = run(capsys, fx, "query", fx.shop, "--where", "note=BRAND_FALLBACK", "--where", "brand_source=title")
    want = [r["key"] for r in read_jsonl(prepared_path(fx)) if r["product"]["brand_source"] == "title"
            and any(n["code"] == "brand_fallback" for n in r["notes"])]
    assert keys_of(out) == want and fx.key("13830312765") in want
    _, out, _ = run(capsys, fx, "query", fx.shop, "--where", "reason=", "--where", "store!=")   # sent, no reason
    assert len(keys_of(out)) == 7
    _, out, _ = run(capsys, fx, "query", fx.shop, "--where", "translation!=translated")
    assert len(keys_of(out)) == 5                                      # 3 pending, 2 held
    assert "not F=V" in usage(capsys, fx, "query", fx.shop, "--where", "status")
    assert "unknown field" in usage(capsys, fx, "query", fx.shop, "--where", "colour=red")


def test_query_store_category_leaf_grep(shop_fixture, capsys):
    fx = shop_fixture
    counts = {}
    for store in V.STORES:
        _, out, _ = run(capsys, fx, "query", fx.shop, "--store", store)
        counts[store] = len(keys_of(out))
    assert counts == {"published": 7, "withdrawn": 5, "draft": 0, "active": 7, "none": 4, "any": 16}
    _, out, _ = run(capsys, fx, "query", fx.shop, "--category", "50002788")
    assert sorted(keys_of(out)) == sorted([fx.key(RESTORED), fx.key(UNRESOLVED)])
    _, out, _ = run(capsys, fx, "query", fx.shop, "--leaf", "junior-clubs-sets", "--store", "published")
    assert keys_of(out) == [fx.key("12178430576")]
    _, out, _ = run(capsys, fx, "query", fx.shop, "--grep", "YAMATO", "--fields", "key")
    assert sorted(keys_of(out)) == sorted([fx.key(DRAFTED), fx.key("13830312765")])
    _, out, _ = run(capsys, fx, "query", fx.shop, "--grep", "^pgm-", "--in", "handle")
    assert keys_of(out) == []                       # pgm- were older handles; the last is fairward-golf-...
    assert "--grep" in usage(capsys, fx, "query", fx.shop, "--grep", "(")


def test_query_count_by_and_keys_out(shop_fixture, capsys, tmp_path):
    fx = shop_fixture
    _, out, _ = run(capsys, fx, "query", fx.shop, "--count-by", "state")
    assert out.splitlines() == ["active\t7", "withdrawn\t5", "none\t4"]
    _, counts = run_json(capsys, fx, "query", fx.shop, "--count-by", "held")
    assert counts == {"(none)": 14, "single_only": 2}
    target = tmp_path / "picked.txt"
    _, out, _ = run(capsys, fx, "query", fx.shop, "--store", "withdrawn", "--keys-out", str(target))
    assert V.read_refs(str(target)) == keys_of(out) and len(keys_of(out)) == 5
    assert target.read_text(encoding="utf-8").startswith("# shop_view.py query fairwardgolf: 5 products")


def test_query_within_a_job(shop_fixture, capsys):
    fx = shop_fixture
    job_a = fx.jobs_ids[0]
    touched = set(V.job_keys(job_a, fx.jobs))
    _, out, _ = run(capsys, fx, "query", fx.shop, "--job", job_a, "--jobs-root", fx.jobs, "--where", "status=held")
    want = [r["key"] for r in read_jsonl(prepared_path(fx)) if r["status"] == "held" and r["key"] in touched]
    assert sorted(keys_of(out)) == sorted(want) and fx.key(SINGLE) in want
    _, out, _ = run(capsys, fx, "query", fx.shop, "--job", job_a, "--jobs-root", fx.jobs, "--fields", "key")
    assert set(keys_of(out)) == touched and fx.key(UNRESOLVED) not in touched     # in no job


# ---- ledger / history ------------------------------------------------------------------------------------------

def test_ledger_rows_filters_counts(shop_fixture, capsys):
    fx = shop_fixture
    code, out, _ = run(capsys, fx, "ledger", fx.shop)
    lines = out.splitlines()
    assert code == 0 and len(lines) == 31 and all(len(x.split("\t")) == len(V.LEDGER_COLUMNS) for x in lines)
    _, out, _ = run(capsys, fx, "ledger", fx.shop, "--status", "withdrawn")
    assert len(out.splitlines()) == 8
    _, out, _ = run(capsys, fx, "ledger", fx.shop, "--status", "restored")
    assert len(out.splitlines()) == 3
    _, out, _ = run(capsys, fx, "ledger", fx.shop, "--status", "draft")         # store_status, any case
    assert all("\tDRAFT\t" in x for x in out.splitlines()) and out
    _, out, _ = run(capsys, fx, "ledger", fx.shop, "--since", "2026-11-16T08:40Z")
    assert [x.split("\t")[1] for x in out.splitlines()] == ["created", "activated", "withdrawn"]
    _, same, _ = run(capsys, fx, "ledger", fx.shop, "--since", "2026-11-16T17:40+09:00")   # any zone, as UTC
    assert same == out
    _, counts = run_json(capsys, fx, "ledger", fx.shop, "--count-by", "reason_code")
    assert counts["agency_no_brand"] == 2 and counts["replaced_by"] == 2 and counts["hold"] == 1
    assert sum(counts.values()) == 31
    _, out, _ = run(capsys, fx, "ledger", fx.shop, "--count-by", "day")
    assert out.splitlines()[0].startswith("2026-11-1")
    assert "--since" in usage(capsys, fx, "ledger", fx.shop, "--since", "yesterday")
    assert "--count-by" in usage(capsys, fx, "ledger", fx.shop, "--count-by", "colour")


def test_history(shop_fixture, capsys):
    fx = shop_fixture
    code, out, _ = run(capsys, fx, "history", fx.shop, RESTORED)
    lines = out.splitlines()
    assert code == 0 and lines[0] == f"== {fx.key(RESTORED)} (active; prepared ready)"
    assert [x.split("\t")[1] for x in lines[1:]] == ["created", "sent", "activated", "withdrawn", "restored"]
    code, out, _ = run(capsys, fx, "history", fx.shop, UNRESOLVED)
    assert out.splitlines()[1] == "(never sent)"
    code, rows = run_json(capsys, fx, "history", fx.shop, THREE, "nope")
    assert code == 1 and len(rows) == 1 and len({r["handle"] for r in rows[0]["rows"]}) == 3


# ---- check -----------------------------------------------------------------------------------------------------

def test_check_plan(shop_fixture, capsys, tmp_path):
    fx = shop_fixture
    plan = tmp_path / "plan.tsv"
    plan.write_text("key\tstatus\treason\n"
                    f"{REPLACED}\twithdrawn\treplaced_by:\n"
                    f"# a comment\n\n"
                    f"{fx.key(HOLD)}\twithdrawn\tHOLD:\n"
                    f"{SINGLE}\theld\n"
                    f"{THREE}\tpublished\n", encoding="utf-8")
    code, out, err = run(capsys, fx, "check", fx.shop, str(plan))
    assert code == 0 and [x.split("\t")[0] for x in out.splitlines()] == ["ok"] * 4 and "4 ok, 0 not" in err
    plan.write_text(f"{fx.key(HOLD)}\tdraft\n{LIVE}\tactive\treplaced_by:\nnope\tactive\n{LIVE}\tactivee\n{LIVE}\n",
                    encoding="utf-8")
    code, rows = run_json(capsys, fx, "check", fx.shop, str(plan))
    assert code == 1 and [r["result"] for r in rows] == ["FAIL", "FAIL", "ERROR", "ERROR", "ERROR"]
    assert rows[0]["got"] == "withdrawn" and "no product" in rows[2]["error"]
    assert "missing.tsv" in usage(capsys, fx, "check", fx.shop, str(tmp_path / "missing.tsv"))


# ---- the edges: broken files, empty or missing shop, big input ---------------------------------------------------

def test_cut_off_last_ledger_line_is_ignored(shop_fixture, capsys):
    fx = shop_fixture
    with open(ledger_path(fx), "a", encoding="utf-8") as f:
        f.write('{"format": "published/1", "key": "fairwardgolf:naver:1:2", "sta')
    code, out, err = run(capsys, fx, "ledger", fx.shop)
    assert code == 0 and len(out.splitlines()) == 31


def test_broken_prepared_line_is_exit_1(shop_fixture, capsys):
    fx = shop_fixture
    with open(prepared_path(fx), "a", encoding="utf-8") as f:
        f.write("not json\n")
    code, out, err = run(capsys, fx, "query", fx.shop)
    assert code == 1 and out == "" and "products.jsonl:17: not a JSON line" in err
    code, out, err = run(capsys, fx, "key", fx.shop, LIVE)              # key reads the same files: 1, no traceback
    assert code == 1 and out == "" and "products.jsonl:17: not a JSON line" in err


def test_shared_pieces_of_the_read_tools(tmp_path):
    """One TSV cell, one keys file, one time parser, one gid / admin link reader for shop_view, job_report,
    prepared_diff and shopify_catalog."""
    assert V.cell(None) == "" and V.cell(["a", "b c"]) == "a,b c" and V.cell("x\ty\n  z") == "x y z"
    path = tmp_path / "keys.txt"
    V.write_keys(str(path), ["a:b:1:2", "a:b:1:3"], "a test")
    assert path.read_text(encoding="utf-8").startswith("# a test: 2 products\n")
    assert V.read_refs(str(path)) == ["a:b:1:2", "a:b:1:3"]
    assert V.iso_time("2026-11-16T08:40Z") == V.iso_time("2026-11-16T17:40:00+09:00")
    assert V.store_number("gid://shopify/Product/15497202729027") == "15497202729027"
    assert V.store_number("https://admin.shopify.com/store/x/products/15497202729027?a=1") == "15497202729027"
    assert V.store_number("12557420063") is None and V.store_number("https://shop.example/products/h") is None
    import job_report
    import prepared_diff
    import shopify_catalog
    assert job_report.one_line is V.cell and job_report.iso_time is V.iso_time and prepared_diff._clean is V.cell
    assert shopify_catalog._row(["a", "b"], "x\ty") == "a,b\tx y"


def test_empty_shop_and_missing_files(shop_fixture, capsys, tmp_path):
    fx = shop_fixture
    os.makedirs(os.path.join(fx.shops, "empty"))
    for argv in (("query", "empty"), ("ledger", "empty"), ("query", "empty", "--count-by", "state")):
        code, out, _ = run(capsys, fx, *argv)
        assert (code, out) == (0, "")
    code, out, err = run(capsys, fx, "show", "empty", LIVE)
    assert code == 1 and "no product of empty matches" in err
    code, out, _ = run(capsys, fx, "show", "empty", fx.key(LIVE), "--fields", "key,state,prepared")
    assert out.splitlines()[1] == f"{fx.key(LIVE)}\tnone\t"            # a full key, known or not: as before
    os.remove(os.path.join(fx.shops, fx.shop, "translation", "descriptions.jsonl"))
    os.remove(os.path.join(fx.shops, fx.shop, "placement", "placements.jsonl"))
    code, rows = run_json(capsys, fx, "show", fx.shop, LIVE, "--fields", "description,placement,leaves,state")
    assert rows == [{"description": None, "placement": None, "leaves": [], "state": "active"}]
    assert "no shop folder" in usage(capsys, fx, "ledger", "nowhere")


def test_big_prepared_file(shop_fixture, capsys):
    fx = shop_fixture
    row = next(r for r in read_jsonl(prepared_path(fx)) if r["key"] == fx.key(LIVE))
    with open(prepared_path(fx), "a", encoding="utf-8") as f:
        for n in range(3000):
            f.write(json.dumps({**row, "key": f"{fx.shop}:naver:7:{9000000 + n}"}, ensure_ascii=False) + "\n")
    started = time.monotonic()
    code, out, _ = run(capsys, fx, "query", fx.shop, "--count-by", "state")
    assert code == 0 and out.splitlines()[0] == "none\t3004" and time.monotonic() - started < 20
    code, out, _ = run(capsys, fx, "show", fx.shop, "9001234", "--fields", "key")
    assert out.splitlines()[1] == f"{fx.shop}:naver:7:9001234"
