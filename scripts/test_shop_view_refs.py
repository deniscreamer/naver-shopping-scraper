"""Naming a product (shop_view.resolve, selected_keys, the --keys-file / --job flags; 2026-11-16) on the real-data
shop fixture (conftest `shop_fixture`, fixtures/shop/): a key, a Naver product id, a handle (the last or an older
one), a store / admin / Naver link, a gid; an id two keys share, an unknown ref, a keys file with comments, a job
and its events; and the CLIs that take them (publish, translate, describe, store_diff, reprice, lens), offline,
nothing sent: publish's store actions only with --dry-run, the store clients replaced by ones that fail the test.

    .venv/bin/python -m pytest scripts/test_shop_view_refs.py -q
"""
import json
import os

import pytest

import shop_view as V
from shop_files import read_jsonl

LIVE, AGENCY, THREE = "13552318731", "12178430576", "13830324906"
WITHDRAWN = "12080067974"


def handles(fx, pid):
    rows = read_jsonl(os.path.join(fx.shops, fx.shop, "publish", "published.jsonl"), tail_ok=True)
    return list(dict.fromkeys(r["handle"] for r in rows if r["key"] == fx.key(pid) and r.get("handle")))


def number(fx, pid):
    rows = read_jsonl(os.path.join(fx.shops, fx.shop, "publish", "published.jsonl"), tail_ok=True)
    return next(r["product_id"] for r in rows if r["key"] == fx.key(pid)).rsplit("/", 1)[-1]


def add_twin(fx, pid, channel="999"):
    """The same Naver product id under another channel (a seller's product moved to another store): prepared only."""
    path = os.path.join(fx.shops, fx.shop, "prepared", "products.jsonl")
    row = next(r for r in read_jsonl(path) if r["key"] == fx.key(pid))
    twin = f"{fx.shop}:naver:{channel}:{pid}"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({**row, "key": twin}, ensure_ascii=False) + "\n")
    return twin


# ---- resolve ---------------------------------------------------------------------------------------------------

def test_a_full_key_is_returned_as_it_is_known_or_not(shop_fixture):
    fx = shop_fixture
    k = fx.key(LIVE)
    assert V.resolve(fx.shop, k, fx.shops) == k
    assert V.resolve(fx.shop, f"{fx.shop}:naver:1:2", fx.shops) == f"{fx.shop}:naver:1:2"    # as before: no lookup
    assert V.resolve(fx.shop, f"  {k}\n", fx.shops) == k


def test_a_naver_product_id_names_its_key(shop_fixture):
    fx = shop_fixture
    for pid in [k.split(":")[-1] for k in fx.cases]:                  # every case, by its id alone
        assert V.resolve(fx.shop, pid, fx.shops) == fx.key(pid)


def test_a_handle_the_last_or_an_older_one(shop_fixture):
    fx = shop_fixture
    old, new = handles(fx, AGENCY)
    assert V.resolve(fx.shop, new, fx.shops) == V.resolve(fx.shop, old, fx.shops) == fx.key(AGENCY)
    assert len(handles(fx, THREE)) == 3
    assert {V.resolve(fx.shop, h, fx.shops) for h in handles(fx, THREE)} == {fx.key(THREE)}


def test_links_and_a_gid(shop_fixture):
    fx = shop_fixture
    h, n, k = handles(fx, LIVE)[-1], number(fx, LIVE), fx.key(LIVE)
    for ref in (f"https://fairwardgolf.com/products/{h}", f"https://checkout.fairwardgolf.com/products/{h}?variant=1#x",
                f"www.fairwardgolf.com/collections/wedges/products/{h}",
                f"https://admin.shopify.com/store/93r1y5-tt/products/{n}", f"admin.shopify.com/store/s/products/{n}/",
                f"gid://shopify/Product/{n}", n,                       # the Shopify product number alone
                f"https://smartstore.naver.com/somestore/products/{LIVE}?NaPm=ct",
                f"https://brand.naver.com/b/products/{LIVE}"):
        assert V.resolve(fx.shop, ref, fx.shops) == k, ref


def test_a_link_without_products_and_an_unknown_ref_name_no_product(shop_fixture):
    fx = shop_fixture
    for ref, said in (("https://fairwardgolf.com/collections/wedges", "without /products/"),
                      ("https://fairwardgolf.com/products/no-such-handle", "no product of fairwardgolf matches"),
                      ("12345", "no product of fairwardgolf matches"), ("no-such-handle", "no product"),
                      ("gid://shopify/Product/1", "no product"), ("  ", "an empty ref")):
        with pytest.raises(V.RefError, match=said):
            V.resolve(fx.shop, ref, fx.shops)


def test_an_id_two_keys_share_is_an_error_naming_both_never_the_first(shop_fixture):
    fx = shop_fixture
    twin = add_twin(fx, LIVE)
    with pytest.raises(V.RefError) as e:
        V.resolve(fx.shop, LIVE, fx.shops)
    msg = str(e.value)
    assert "2 products match" in msg and fx.key(LIVE) in msg and twin in msg
    assert "published" in msg and handles(fx, LIVE)[-1] in msg and "not sent" in msg      # how to tell them apart
    assert V.resolve(fx.shop, twin, fx.shops) == twin                                      # the key chooses
    assert V.resolve(fx.shop, handles(fx, LIVE)[-1], fx.shops) == fx.key(LIVE)              # the handle is one


def test_a_view_and_an_index_resolve_as_the_shop_name_does(shop_fixture):
    fx = shop_fixture
    view = V.ShopView(fx.shop, fx.shops)
    h = handles(fx, AGENCY)[0]
    assert V.resolve(view, h) == V.resolve(V.RefIndex.of_shop(fx.shop, fx.shops), h) == fx.key(AGENCY)
    assert V.resolve(view, LIVE) == fx.key(LIVE) and view._refs is not None                 # built once a view


def test_a_short_key_the_files_spell_so_is_that_key(tmp_path):
    d = tmp_path / "s" / "publish"
    d.mkdir(parents=True)
    (d / "published.jsonl").write_text('{"key": "k1", "status": "published"}\n{"key": "k2", "sta')   # torn tail
    assert V.resolve("s", "k1", str(tmp_path)) == "k1"


# ---- keys file, job, selected_keys -----------------------------------------------------------------------------

def test_a_keys_file_with_comments_blanks_and_columns(tmp_path, shop_fixture):
    fx = shop_fixture
    f = tmp_path / "keys.txt"
    f.write_text(f"# the owner's list\n\n{LIVE}\n   \n  # indented comment\n{fx.key(AGENCY)}\tpublished\tnote\n"
                 f"{handles(fx, THREE)[0]}  # an older handle\n{LIVE}\n", encoding="utf-8")
    assert V.read_refs(str(f)) == [LIVE, fx.key(AGENCY), handles(fx, THREE)[0], LIVE]
    assert V.selected_keys(fx.shop, [], str(f), shops_root=fx.shops) == [fx.key(LIVE), fx.key(AGENCY), fx.key(THREE)]


def test_a_job_and_its_event(shop_fixture):
    fx = shop_fixture
    a, b = fx.jobs_ids
    published = V.selected_keys(fx.shop, job=b, event="published", shops_root=fx.shops, jobs_root=fx.jobs)
    assert published == V.job_keys(b, fx.jobs, "published") and len(published) == 5
    assert fx.key("12557420063") in published and fx.key("13016112970") in published
    every = V.selected_keys(fx.shop, job=b, shops_root=fx.shops, jobs_root=fx.jobs)
    assert set(published) < set(every) and fx.key("13292782760") in every                  # not taken too
    both = V.selected_keys(fx.shop, [LIVE, fx.key("12557420063")], job=b, event="published", shops_root=fx.shops,
                           jobs_root=fx.jobs)
    assert both[:2] == [fx.key(LIVE), fx.key("12557420063")] and len(both) == 6             # refs first, each once


def test_selection_errors_are_reported_together(tmp_path, shop_fixture):
    fx = shop_fixture
    add_twin(fx, LIVE)
    f = tmp_path / "keys.txt"
    f.write_text("nope-handle\n", encoding="utf-8")
    with pytest.raises(V.RefError) as e:
        V.selected_keys(fx.shop, [LIVE, AGENCY], str(f), shops_root=fx.shops)
    assert str(e.value).count("\n") == 1 and "2 products match" in str(e.value) and "nope-handle" in str(e.value)
    with pytest.raises(V.RefError, match="--event needs --job"):
        V.selected_keys(fx.shop, event="published", shops_root=fx.shops)
    with pytest.raises(V.RefError, match="no-such-job"):
        V.selected_keys(fx.shop, job="no-such-job", shops_root=fx.shops, jobs_root=fx.jobs)
    with pytest.raises(V.RefError, match="no key with event nothing"):
        V.selected_keys(fx.shop, job=fx.jobs_ids[0], event="nothing", shops_root=fx.shops, jobs_root=fx.jobs)
    with pytest.raises(V.RefError, match="--keys-file"):
        V.selected_keys(fx.shop, keys_file=str(tmp_path / "missing.txt"), shops_root=fx.shops)


def test_full_keys_alone_read_no_file(tmp_path):
    keys = ["a:naver:1:2", "a:naver:1:3", "a:naver:1:2"]
    assert V.selected_keys("a", keys, shops_root=str(tmp_path / "none")) == keys[:2]       # no shop folder needed


# ---- shop_view.py key -------------------------------------------------------------------------------------------

def test_the_key_command(tmp_path, shop_fixture, capsys):
    fx = shop_fixture
    f = tmp_path / "k.txt"
    f.write_text(f"# c\n{handles(fx, AGENCY)[0]}\n", encoding="utf-8")
    assert V.main(["key", fx.shop, "--shops-root", fx.shops, LIVE, "--keys-file", str(f)]) == 0
    assert capsys.readouterr().out.splitlines() == [f"{LIVE}\t{fx.key(LIVE)}",
                                                    f"{handles(fx, AGENCY)[0]}\t{fx.key(AGENCY)}"]
    assert V.main(["key", fx.shop, "--shops-root", fx.shops, LIVE, "nope", "--json"]) == 1
    out = capsys.readouterr()
    rows = json.loads(out.out)
    assert rows[0] == {"ref": LIVE, "key": fx.key(LIVE)} and "no product" in rows[1]["error"]
    assert V.main(["key", fx.shop, "--shops-root", fx.shops, "nope"]) == 1
    assert "nope: no product" in capsys.readouterr().err
    assert V.main(["key", fx.shop, "--shops-root", fx.shops, "--job", fx.jobs_ids[1], "--event", "published",
                   "--jobs-root", fx.jobs]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 5
    with pytest.raises(SystemExit) as e:
        V.main(["key", fx.shop, "--shops-root", fx.shops])
    assert e.value.code == 2


# ---- the CLIs that take refs ------------------------------------------------------------------------------------

@pytest.fixture
def no_store(monkeypatch):
    """Any store client a test's code builds fails the test."""
    import shopify_admin

    def refuse(*a, **k):
        raise AssertionError("a store client was built")
    monkeypatch.setattr(shopify_admin, "ProductsAdmin", refuse)
    monkeypatch.setattr(shopify_admin, "FilesAdmin", refuse)


def test_publish_withdraw_by_product_id_dry_run_names_the_key_and_sends_nothing(shop_fixture, no_store, capsys):
    import publish
    fx = shop_fixture
    ledger = os.path.join(fx.shops, fx.shop, "publish", "published.jsonl")
    before = open(ledger, encoding="utf-8").read()
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--withdraw", LIVE, "--reason", "r", "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == f"{fx.key(LIVE)}: would withdraw (dry run: nothing sent)"
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--restore", handles(fx, AGENCY)[0],
                         "--withdraw", "x", "--reason", "r", "--dry-run"]) == 1       # one action a run: restore first
    # AGENCY was restored already: the real call would stop with "not withdrawn here", and so does the dry run
    assert capsys.readouterr().out.strip() == f"{fx.key(AGENCY)}: not withdrawn here (dry run)"
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--restore", WITHDRAWN, "--reason", "r",
                         "--dry-run"]) == 0
    assert capsys.readouterr().out.strip() == f"{fx.key(WITHDRAWN)}: would restore (dry run: nothing sent)"
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--activate", "--job", fx.jobs_ids[1], "--event",
                         "published", "--jobs-root", fx.jobs, "--dry-run"]) == 0
    out = capsys.readouterr().out.splitlines()        # all active by now: as the real call, "not a draft here"
    assert len(out) == 5 and all(x.endswith(": not a draft here (dry run)") for x in out)
    assert open(ledger, encoding="utf-8").read() == before


def test_publish_dry_run_store_action_on_an_unknown_full_key_says_what_the_real_call_would(shop_fixture, no_store,
                                                                                           capsys):
    import publish
    fx = shop_fixture
    typo = f"{fx.shop}:naver:9:999"
    for action, said, code in (("--withdraw", "not published here", 1), ("--restore", "not withdrawn here", 1),
                               ("--activate", "not a draft here", 0)):
        argv = [fx.shop, "--shops-root", fx.shops, action, typo, "--dry-run"]
        assert publish.main(argv + (["--reason", "r"] if action != "--activate" else [])) == code
        assert capsys.readouterr().out.strip() == f"{typo}: {said} (dry run)"


@pytest.mark.parametrize("argv", [
    ["--only", ""], ["--only", " "], ["--only", "", "--only", LIVE], ["--keys-file", ""], ["--event", "published"],
    ["--job", ""], ["--withdraw", LIVE, "--withdraw", "", "--reason", "r"],
])
def test_publish_an_empty_or_lone_selection_never_widens_to_every_product(shop_fixture, no_store, monkeypatch,
                                                                         capsys, argv):
    import publish
    fx = shop_fixture
    monkeypatch.setattr(publish, "_publish", lambda *a: pytest.fail("built payloads for a selection that is empty"))
    with pytest.raises(SystemExit) as e:
        publish.main([fx.shop, "--shops-root", fx.shops, "--dry-run", *argv])
    assert e.value.code == 2
    capsys.readouterr()


def test_publish_only_an_unknown_ref_is_not_ready_as_before(shop_fixture, no_store, monkeypatch, capsys):
    import publish
    fx = shop_fixture
    monkeypatch.setattr(publish, "offline_ids", lambda shop: {"vendors": {}, "tenant": "Fairward Golf"})
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--dry-run", "--only", "nosuchkey"]) == 0
    out = capsys.readouterr()
    assert "nosuchkey: not ready" in out.err and f"publish {fx.shop}: 0 products" in out.out


def test_publish_refuses_an_ambiguous_or_unknown_ref_before_any_store_call(shop_fixture, no_store, capsys):
    import publish
    fx = shop_fixture
    twin = add_twin(fx, LIVE)
    with pytest.raises(SystemExit) as e:
        publish.main([fx.shop, "--shops-root", fx.shops, "--withdraw", LIVE, "--reason", "r"])
    err = capsys.readouterr().err
    assert e.value.code == 2 and fx.key(LIVE) in err and twin in err
    for argv in (["--activate", "nope"], ["--withdraw", "--reason", "r"], ["--only", LIVE]):   # a twin: 2
        with pytest.raises(SystemExit) as e:
            publish.main([fx.shop, "--shops-root", fx.shops, *argv])
        assert e.value.code == 2


def test_publish_only_by_ref_dry_run(shop_fixture, no_store, monkeypatch, capsys, tmp_path):
    import publish
    fx = shop_fixture
    monkeypatch.setattr(publish, "offline_ids", lambda shop: {"vendors": {}, "tenant": "Fairward Golf"})
    f = tmp_path / "keys.txt"
    f.write_text(f"# two\n{LIVE}\n{handles(fx, '13016112970')[-1]}\n", encoding="utf-8")
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--dry-run", "--keys-file", str(f)]) == 0
    out = capsys.readouterr().out
    assert f"{fx.key(LIVE)}: dry-run" in out and f"{fx.key('13016112970')}: dry-run" in out
    assert "2 products" in out
    empty = tmp_path / "empty.txt"
    empty.write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:                    # an empty list never widens to every product
        publish.main([fx.shop, "--shops-root", fx.shops, "--dry-run", "--keys-file", str(empty)])
    assert e.value.code == 2 and "no product selected" in capsys.readouterr().err


def test_publish_full_keys_behave_as_before(shop_fixture, no_store, monkeypatch, capsys):
    import publish
    fx = shop_fixture
    monkeypatch.setattr(publish, "offline_ids", lambda shop: {"vendors": {}, "tenant": "Fairward Golf"})
    unknown = f"{fx.shop}:naver:1:2"
    assert publish.main([fx.shop, "--shops-root", fx.shops, "--dry-run", "--only", fx.key(LIVE), "--only",
                         unknown]) == 0
    out = capsys.readouterr()
    assert f"{unknown}: not ready" in out.err and "1 products" in out.out


def test_translate_and_describe_take_refs_a_file_and_a_job(shop_fixture, monkeypatch, tmp_path):
    import describe
    import translate
    fx = shop_fixture
    seen = []
    monkeypatch.setattr(translate, "run", lambda shop, model, root, only=None, limit=None: seen.append(only) or
                        {"report": []})
    assert translate.main([fx.shop, "--shops-root", fx.shops, "--offline", "--only", LIVE]) == 0
    assert translate.main([fx.shop, "--shops-root", fx.shops, "--offline", "--job", fx.jobs_ids[1], "--event",
                           "published", "--jobs-root", fx.jobs]) == 0
    assert translate.main([fx.shop, "--shops-root", fx.shops, "--offline"]) == 0
    assert seen[0] == [fx.key(LIVE)] and len(seen[1]) == 5 and seen[2] is None
    got = []
    monkeypatch.setattr(describe, "run", lambda shop, model, root, only=None, **k: got.append(only) or
                        {"report": []})
    assert describe.main([fx.shop, "--shops-root", fx.shops, "--offline", "--only", handles(fx, AGENCY)[0]]) == 0
    assert describe.main([fx.shop, "--shops-root", fx.shops, "--offline"]) == 0
    assert got == [[fx.key(AGENCY)], None]


def test_the_only_of_run_takes_several_keys(shop_fixture, monkeypatch):
    """describe.run with a set of keys: each named one counts (a product already in the shop too)."""
    import describe
    fx = shop_fixture
    bare = fx.key("5917858699")                              # in the shop, no description yet
    assert bare not in describe.run(fx.shop, None, fx.shops)["waiting"]            # not named: left alone
    r = describe.run(fx.shop, None, fx.shops, only=[bare, fx.key(LIVE)])           # LIVE has a fresh one
    assert r["waiting"] == [bare] and r["rows"] == []


def test_store_diff_and_reprice_take_refs(shop_fixture, monkeypatch, capsys):
    import reprice
    import store_diff
    fx = shop_fixture
    got = []
    monkeypatch.setattr(store_diff, "_diff", lambda args: got.append(args.only) or 0)
    assert store_diff.main([fx.shop, "--shops-root", fx.shops, "--only", LIVE, "--only", fx.key(AGENCY)]) == 0
    assert store_diff.main([fx.shop, "--shops-root", fx.shops]) == 0
    assert got == [[fx.key(LIVE), fx.key(AGENCY)], []]
    assert reprice.main([fx.shop, "--shops-root", fx.shops, "--only",
                         f"https://admin.shopify.com/store/s/products/{number(fx, LIVE)}"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(fx.key(LIVE)) and "1 products" in out and "dry run: nothing sent" in out


def test_lens_products_by_handle_and_an_ambiguous_id(shop_fixture, capsys):
    import lens
    fx = shop_fixture
    twin = add_twin(fx, LIVE)
    plan = lens.products(V.ShopView(fx.shop, fx.shops), [handles(fx, AGENCY)[0], LIVE, "nope"])
    assert [c.key for c in plan.cards] == [fx.key(AGENCY)]
    out = capsys.readouterr().out
    assert twin in out and fx.key(LIVE) in out and "nope" in out


# ---- review fixes (2026-11-16): an empty or lone flag, a broken shop file -------------------------------------

def break_middle_line(path):
    """A bad line in the middle of a .jsonl (not a cut-off last line): a LedgerError for the strict readers."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    lines.insert(1, "{not json\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))


def test_query_event_alone_or_an_empty_keys_file_path_is_usage_not_every_product(shop_fixture, capsys):
    fx = shop_fixture
    for argv in (["--event", "published"], ["--keys-file", ""], ["--job", ""],
                 ["--job", fx.jobs_ids[1], "--jobs-root", fx.jobs, "--event", ""]):
        with pytest.raises(SystemExit) as e:
            V.main(["query", fx.shop, "--shops-root", fx.shops, *argv])
        assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--event needs --job" in err and "--keys-file: an empty path" in err and "--job: an empty id" in err
    with pytest.raises(SystemExit) as e:
        V.main(["key", fx.shop, "--shops-root", fx.shops, "--event", "published"])
    assert e.value.code == 2


@pytest.mark.parametrize("rel", ["prepared/products.jsonl", "publish/published.jsonl"])
def test_an_acting_cli_names_a_broken_shop_file_exit_2_not_a_traceback(shop_fixture, capsys, rel):
    import reprice
    fx = shop_fixture
    break_middle_line(os.path.join(fx.shops, fx.shop, rel))
    with pytest.raises(SystemExit) as e:
        reprice.main([fx.shop, "--shops-root", fx.shops, "--only", LIVE])
    assert e.value.code == 2 and rel.split("/")[-1] in capsys.readouterr().err


def test_lens_products_skips_a_bad_middle_ledger_line_as_its_view_does(shop_fixture, capsys):
    import lens
    fx = shop_fixture
    handle = handles(fx, AGENCY)[-1]
    break_middle_line(os.path.join(fx.shops, fx.shop, "publish", "published.jsonl"))
    plan = lens.products(V.ShopView(fx.shop, fx.shops), [handle, LIVE])
    assert [c.key for c in plan.cards] == [fx.key(AGENCY), fx.key(LIVE)]
