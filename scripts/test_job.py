"""Offline tests for job.py: the job folder and its events, which product comes next, the waits and stops around
collect, a one-line kept run (and a crash between keep and the log), and the stage read from the files.

    .venv/bin/python -m pytest scripts/test_job.py -q
"""
import json
import os

import pytest

import job as J
from collect_guard import Outcome, SourceStopped

SHOP = "fairwardgolf"
KEYS = [f"{SHOP}:naver:100:{n}" for n in (11, 12, 13)]


def make_job(tmp_path, rows=KEYS):
    folder = tmp_path / "jobs" / "j1"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps({"shop": SHOP, "category": "50002788", "paid": False, "reviews": 20,
                                                 "shops_root": str(tmp_path / "shops")}))
    (folder / "listing.jsonl").write_text("".join(json.dumps({"key": k, "product_id": k.split(":")[3], "query": "q",
                                                              "link": "l"}) + "\n" for k in rows))
    return J.Job(str(folder))


def test_events_ignore_a_torn_line(tmp_path):
    job = make_job(tmp_path)
    job.log(KEYS[0], "failed", reason="x")
    with open(os.path.join(job.folder, "events.jsonl"), "a") as f:
        f.write('{"at": "t", "key": "')                                         # a crash while writing
    assert [e["event"] for e in job.events()] == ["failed"]


def test_next_key_skips_closed_and_puts_failed_last(tmp_path):
    job = make_job(tmp_path)
    assert J.next_key(job, {}) == KEYS[0]
    job.log(KEYS[0], "failed", reason="naver error page")
    assert J.next_key(job, {}) == KEYS[1]                                       # fresh ones first
    job.log(KEYS[1], "not_taken", reason="card_not_found")
    assert J.next_key(job, {KEYS[2]: "prepared"}) == KEYS[0]                    # then the one that failed once
    job.log(KEYS[0], "failed", reason="again")
    assert J.next_key(job, {KEYS[2]: "prepared"}) is None                       # failed MAX_FAILS times: closed
    assert J.closed(job)[KEYS[0]].startswith("failed 2x")


class Guard:
    """Raises the given SourceStopped errors in turn, then returns a complete outcome."""
    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0

    def run(self, key, collect):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return Outcome("complete", data={})


@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(J.time, "sleep", lambda s: waits.append(s))
    return waits


def test_busy_adapter_waits(tmp_path, no_sleep):
    job = make_job(tmp_path)
    guard = Guard(SourceStopped("409", status=409, error="busy"), SourceStopped("409", status=409, error="busy"))
    out = J.collect_with_waits(job, None, None, {}, guard, job.rows()[0], str(tmp_path))
    assert out.status == "complete" and no_sleep == [J.BUSY_WAIT_S, J.BUSY_WAIT_S]


def test_naver_error_page_waits_then_fails_the_product(tmp_path, no_sleep):
    job = make_job(tmp_path)
    err = lambda: SourceStopped("503", status=503, error="naver error page: product 11: Cannot access")  # noqa: E731
    guard = Guard(*[err() for _ in range(J.ERROR_TRIES + 1)])
    assert J.collect_with_waits(job, None, None, {}, guard, job.rows()[0], str(tmp_path)) is None
    assert no_sleep == [J.ERROR_WAIT_S] * J.ERROR_TRIES
    assert [e["event"] for e in job.events()] == ["failed"]


@pytest.mark.parametrize("error", [
    SourceStopped("503", status=503, error="wall: captcha at search not solved"),
    SourceStopped("image CDN: 403", status=None, error="403"),
    SourceStopped("502", status=502, error="naver-shopping blocked the request"),
])
def test_walls_stop_the_run(tmp_path, no_sleep, error):
    job = make_job(tmp_path)
    with pytest.raises(J.Stop):
        J.collect_with_waits(job, None, None, {}, Guard(error), job.rows()[0], str(tmp_path))
    assert no_sleep == []                                                       # a wall is never waited out


def line(key):
    return {"key": key, "details": {"id": key.split(":")[3]}, "specs": {"category": {"id": "50002788"}}}


def test_keep_line_and_a_crash_before_the_log(tmp_path):
    job = make_job(tmp_path)
    tmp = tmp_path / "jobs" / "j1" / "tmp" / "11"
    tmp.mkdir(parents=True)
    kept = J.keep_line(job, line(KEYS[0]), str(tmp))
    assert os.path.isfile(os.path.join(kept, "manifest.json"))
    again = J.keep_line(job, line(KEYS[0]), str(tmp))                          # the same bytes: already kept
    assert os.path.basename(again) == os.path.basename(kept)


def test_two_products_in_one_second_get_two_runs(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    real_keep = J.__dict__.get("keep")
    import keep_run
    original = keep_run.keep

    pinned = set()

    def same_second(source, root):                    # both files written in the same second
        if source not in pinned:
            pinned.add(source)
            os.utime(os.path.join(source, "products.jsonl"), (1_700_000_000, 1_700_000_000))
        return original(source, root)
    monkeypatch.setattr(keep_run, "keep", same_second)
    runs = []
    for key in KEYS[:2]:
        tmp = tmp_path / "t" / key.split(":")[3]
        tmp.mkdir(parents=True)
        runs.append(J.keep_line(job, line(key), str(tmp)))
    assert real_keep is None and len(set(runs)) == 2


def test_import_has_no_side_effects(tmp_path):
    import importlib
    importlib.reload(J)                                                         # no api, store or catalog at import
    assert not os.path.exists(os.path.join(J.JOBS_ROOT, "j1"))


class Api:
    """/health and /captcha for the waits."""
    def __init__(self, health=("connected",), captcha="none"):
        self.health_states, self.captcha_status = list(health), captcha

    def health(self):
        state = self.health_states.pop(0) if len(self.health_states) > 1 else self.health_states[0]
        if state == "down":
            import requests
            raise requests.exceptions.ConnectionError("refused")
        return {"extension": state}

    def captcha(self):
        return {"status": self.captcha_status}


def test_extension_gone_waits_for_it_then_goes_on(tmp_path, no_sleep):
    job = make_job(tmp_path)
    guard = Guard(SourceStopped("503", status=503, error="the browser extension is not connected: open Chrome"))
    api = Api(health=("down", "disconnected", "connected"))
    out = J.collect_with_waits(job, api, None, {}, guard, job.rows()[0], str(tmp_path))
    assert out.status == "complete" and no_sleep == [J.RECONNECT_WAIT_S] * 3
    assert [e["event"] for e in job.events()] == ["waiting", "back"]


def test_extension_never_back_stops(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    clock = iter(range(0, 100_000, 60))
    monkeypatch.setattr(J.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(J.time, "sleep", lambda s: None)
    guard = Guard(SourceStopped("503", status=503, error="the browser extension is not connected"))
    with pytest.raises(J.Stop, match="not connected"):
        J.collect_with_waits(job, Api(health=("disconnected",)), None, {}, guard, job.rows()[0], str(tmp_path))


def test_captcha_not_answered_is_asked_again_not_a_stop(tmp_path, no_sleep):
    job = make_job(tmp_path)
    guard = Guard(SourceStopped("503", status=503, error="wall: captcha at search not solved"))
    out = J.collect_with_waits(job, Api(captcha="timed_out"), None, {}, guard, job.rows()[0], str(tmp_path))
    assert out.status == "complete" and [e["event"] for e in job.events()] == ["captcha_again"]


def test_a_ban_is_not_taken_for_a_captcha(tmp_path, no_sleep):
    job = make_job(tmp_path)
    guard = Guard(SourceStopped("503", status=503, error="wall: wall at the search page"))
    with pytest.raises(J.Stop):
        J.collect_with_waits(job, Api(captcha="blocked"), None, {}, guard, job.rows()[0], str(tmp_path))


def test_more_batches_doubles_while_there_is_more():
    done = [{"status": "done", "has_more": True}]
    assert J.more_batches(done, 2) == 4 and J.more_batches(done, 30) == J.MAX_BATCHES
    assert J.more_batches(done, J.MAX_BATCHES) is None
    assert J.more_batches([{"status": "done", "has_more": False}], 2) is None
    assert J.more_batches([{"status": "stopped", "has_more": True}], 2) is None     # a stopped listing: not deeper


def test_an_all_job_reads_to_the_listings_end(tmp_path):
    """`new --all` (2026-11-12): no count, every new row taken, the depth capped by the server, not MAX_BATCHES."""
    job = make_job(tmp_path)
    assert J.wanted(job, {}) is None                                             # count 0, no --all: the snapshot
    job.meta["count"] = 5
    assert J.wanted(job, {KEYS[0]: job.final}) == 4
    job.meta.update(count=0, until_end=True)
    assert J.wanted(job, {k: job.final for k in KEYS}) == 0                      # 0: every new row
    more = [{"status": "done", "has_more": True}]
    assert J.more_batches(more, J.MAX_BATCHES, J.batch_cap(job.meta)) == J.MAX_BATCHES * 2
    assert J.more_batches(more, J.MAX_BATCHES_ALL, J.batch_cap(job.meta)) is None
    assert J.more_batches([{"status": "done", "has_more": False}], 4, J.batch_cap(job.meta)) is None


def test_refresh_with_need_0_appends_every_new_row(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    job.meta.update(until_end=True, batches=40, queries=["q"], listings=[{"status": "done", "has_more": True}])
    new = [{"key": f"{SHOP}:naver:100:{n}", "product_id": str(n), "query": "q", "link": "l"} for n in range(20, 70)]
    seen = {}

    def fake_read(api, store, queries, category, batches, skip, known):
        seen.update(batches=batches, skip=set(skip))
        return new, [{"status": "done", "has_more": False, "batches": batches}], {}
    monkeypatch.setattr(J, "read_listings", fake_read)
    assert J.refresh(job, None, None, 0) == 50
    assert seen == {"batches": 80, "skip": set(KEYS)}                           # past MAX_BATCHES, the job's rows skipped
    job = J.Job(job.folder)
    assert len(job.rows()) == 53 and job.meta["batches"] == 80
    assert J.refresh(job, None, None, 0) == 0                                   # the listing ended: no deeper read


def test_heartbeat_is_shown_only_while_the_runner_lives(tmp_path):
    job = make_job(tmp_path)
    job.beat(key=KEYS[0], n=1, stage="collect", since="t")
    assert job.now()["stage"] == "collect"                                      # this process is alive
    with open(os.path.join(job.folder, "now.json"), "w") as f:
        json.dump({"pid": 999_999_999, "stage": "collect"}, f)
    assert job.now() is None


# ---- the translate stage (offline: a fake model) --------------------------------------------------------------

def _translating_job(tmp_path, statuses=None):
    """A job taken to translated, its products prepared from fixtures, translated.jsonl with the given statuses."""
    from test_translate import fixture, FIXTURES
    job = make_job(tmp_path)
    job.meta["translate"] = True
    job.save_meta()
    products = []
    for key, name in zip(KEYS, FIXTURES):
        p = fixture(name)
        products.append({**p, "key": key})
    shop = tmp_path / "shops" / SHOP
    (shop / "prepared").mkdir(parents=True)
    (shop / "prepared" / "products.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in products), encoding="utf-8")
    if statuses:
        (shop / "translation").mkdir()
        (shop / "translation" / "translated.jsonl").write_text(
            "".join(json.dumps({"key": k, "status": s}) + "\n" for k, s in statuses.items()), encoding="utf-8")
    return job


def test_a_job_without_the_flag_stops_at_prepared(tmp_path):
    job = make_job(tmp_path)
    assert job.final == "prepared" and J.next_key(job, {k: "prepared" for k in KEYS}) is None


def test_a_translating_job_takes_prepared_products_on(tmp_path):
    job = _translating_job(tmp_path)
    assert job.final == "translated"
    assert J.next_key(job, {KEYS[0]: "translated", KEYS[1]: "prepared"}) == KEYS[1]


def test_translate_one_closes_fails_or_stops(tmp_path, monkeypatch):
    import translate as T
    from test_translate import FakeModel
    import translation_dicts as D
    monkeypatch.setattr(D, "LIVE_ROOT", str(tmp_path / "live"))              # the job's run uses the live default
    monkeypatch.setattr(T, "Dictionaries", lambda: D.Dictionaries(str(tmp_path / "live")))
    job = _translating_job(tmp_path)
    what = J.translate_one(job, {"translator": T.Chain([FakeModel()])}, KEYS[0])
    assert what.startswith("translated (") and [e["event"] for e in job.events()] == ["translated"]
    rows = [json.loads(x) for x in open(tmp_path / "shops" / SHOP / "translation" / "translated.jsonl")]
    assert {r["key"]: r["status"] for r in rows}[KEYS[1]] == "pending"       # only the one product was asked

    def korean(items):
        from test_translate import answer
        return answer(items, lambda rows: [{**r, "en": "레드"} for r in rows])
    what = J.translate_one(job, {"translator": T.Chain([FakeModel(korean)])}, KEYS[1])
    assert what.startswith("translate failed") and job.events()[-1]["event"] == "failed"

    class Down:
        name = "down"

        def send(self, system, messages):
            raise T.ProviderDown("overloaded")
    with pytest.raises(J.Stop, match="no provider answered"):
        J.translate_one(job, {"translator": T.Chain([Down()])}, KEYS[2])


def test_stages_read_the_translation(tmp_path, monkeypatch):
    job = _translating_job(tmp_path, {KEYS[0]: "translated", KEYS[1]: "untranslated", KEYS[2]: "held"})
    (tmp_path / "shops" / SHOP / "collected").mkdir()
    monkeypatch.setattr("run_transform.latest_lines", lambda *a, **k: {k: (None, None, {}) for k in KEYS})
    got = J.stages(job)
    assert got == {KEYS[0]: "translated", KEYS[1]: "prepared", KEYS[2]: "translated"}   # held: nothing to translate


def test_a_job_without_translation_never_reads_translated(tmp_path, monkeypatch):
    job = _translating_job(tmp_path, {KEYS[0]: "translated"})
    job.meta["translate"] = False
    (tmp_path / "shops" / SHOP / "collected").mkdir()
    monkeypatch.setattr("run_transform.latest_lines", lambda *a, **k: {k: (None, None, {}) for k in KEYS})
    assert J.stages(job)[KEYS[0]] == "prepared"


# ---- the publish stage (offline: fake Shopify clients) -------------------------------------------------------

def test_a_publishing_job_reads_the_ledger_and_publishes_one(tmp_path, monkeypatch):
    import publish as PB
    from test_publish import FakeFiles, FakeProducts
    job = _translating_job(tmp_path, {KEYS[0]: "translated", KEYS[1]: "translated", KEYS[2]: "held"})
    job.meta["publish"] = True
    job.save_meta()
    assert job.final == "published"
    shop = tmp_path / "shops" / SHOP
    (shop / "collected").mkdir()
    monkeypatch.setattr("run_transform.latest_lines", lambda *a, **k: {k: (None, None, {}) for k in KEYS})
    (shop / "publish").mkdir()
    (shop / "publish" / "published.jsonl").write_text(json.dumps({"key": KEYS[0], "status": "published"}) + "\n")
    got = J.stages(job)
    assert got[KEYS[0]] == "published" and got[KEYS[1]] == "translated"
    assert J.next_key(job, got) == KEYS[1]
    calls = []
    monkeypatch.setattr(PB, "clients", lambda shop_name: (FakeProducts(), FakeFiles(), {}))
    monkeypatch.setattr(PB.Shop, "ready", lambda self: [KEYS[1]])
    prices = [[819, 829]]
    monkeypatch.setattr(PB, "publish_one", lambda shop, key, *a, **k: calls.append(key) or
                        {"key": key, "status": "published", "handle": "h", "product_id": "gid://shopify/Product/1",
                         "prices_usd": prices[0]})
    monkeypatch.setattr("placement.run", lambda *a, **k: None)
    assert J.publish_step(job, {}, KEYS[1]) == "published h $819-829" and calls == [KEYS[1]]
    assert job.events()[-1]["event"] == "published" and job.events()[-1]["prices_usd"] == [819, 829]
    prices[0] = [1099, 1099]                                    # one price: shown once
    assert J.publish_step(job, {}, KEYS[1]) == "published h $1099"
    calls.pop()
    what = J.publish_step(job, {}, KEYS[2])                     # not ready (held): closed, not sent
    assert what.startswith("not ready") and calls == [KEYS[1]] and job.events()[-1]["event"] == "not_taken"


def test_a_describing_job_writes_the_description_before_it_publishes(tmp_path, monkeypatch):
    import describe as D
    import publish as PB
    import translate
    from test_publish import FakeFiles, FakeProducts
    job = _translating_job(tmp_path, {KEYS[0]: "translated", KEYS[1]: "translated"})
    job.meta.update(publish=True, describe=True)
    job.save_meta()
    order = []
    row = {"key": KEYS[1], "status": "trimmed", "dropped": [{"where": "highlights"}], "conflicts": ["a", "b"],
           "origin": None, "origin_note": "origin not stated (sources disagree: row: USA; text: Vietnam)"}
    answers = [{"rows": [row], "usage": {}}, {"rows": [], "usage": {}}]

    def described(shop, model, root, only=None):
        order.append(("describe", only, model))
        return answers.pop(0)
    monkeypatch.setattr(D, "run", described)
    monkeypatch.setattr(PB, "clients", lambda shop_name: (FakeProducts(), FakeFiles(), {}))
    monkeypatch.setattr(PB.Shop, "ready", lambda self: [KEYS[0], KEYS[1]])
    monkeypatch.setattr(PB, "publish_one", lambda shop, key, *a, **k: order.append(("publish", key)) or
                        {"key": key, "status": "published", "handle": "h", "product_id": "gid://shopify/Product/1"})
    monkeypatch.setattr("placement.run", lambda *a, **k: None)
    ctx = {"describer": "CHAIN"}
    assert J.publish_step(job, ctx, KEYS[1]).startswith("described (trimmed, 1 cut); published h")
    assert order == [("describe", KEYS[1], "CHAIN"), ("publish", KEYS[1])]          # described first, by the chain
    event = next(e for e in job.events() if e["event"] == "described")
    assert event["status"] == "trimmed" and event["cut"] == 1 and event["conflicts"] == 2
    assert "sources disagree" in event["origin_note"]
    assert J.publish_step(job, ctx, KEYS[0]).startswith("description kept; published h")   # it has one already

    def down(*a, **k):
        raise D.NoProvider("no provider answered")
    monkeypatch.setattr(D, "run", down)
    with pytest.raises(J.Stop, match="describe: no provider answered"):               # not published without it
        J.publish_step(job, ctx, KEYS[1])
    monkeypatch.setattr(D, "run", lambda *a, **k: (_ for _ in ()).throw(translate.TranslateError("key refused")))
    with pytest.raises(J.Stop, match="describe: key refused"):
        J.publish_step(job, ctx, KEYS[1])
    assert [o for o in order if o[0] == "publish"] == [("publish", KEYS[1]), ("publish", KEYS[0])]

    job.meta["describe"] = False                                # a job made without --describe asks nothing
    monkeypatch.setattr(D, "run", lambda *a, **k: order.append("asked"))
    assert J.publish_step(job, ctx, KEYS[1]).startswith("published h") and "asked" not in order


# ---- the network down: tried again with growing waits (tenacity, 2026-11-13) ------------------------------------

def test_a_network_stop_is_tried_again_with_growing_waits(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    waits, calls = [], []
    monkeypatch.setattr(J.time, "sleep", waits.append)
    monkeypatch.setattr(J, "NET_JITTER_S", 0)

    def flaky():
        calls.append(1)
        if len(calls) < 4:
            raise J.NetworkStop("translate: no provider answered")
        return "ok"
    for attempt in J.net_retry(job, KEYS[0]):
        with attempt:
            out = flaky()
    assert out == "ok" and len(calls) == 4
    assert waits == [J.NET_WAIT_S, J.NET_WAIT_S * 2, J.NET_WAIT_S * 4]          # doubled each time
    assert [e["attempt"] for e in job.events() if e["event"] == "network_wait"] == [1, 2, 3]


def test_the_wait_is_capped_and_the_run_gives_up(tmp_path, monkeypatch):
    import requests
    job = make_job(tmp_path)
    monkeypatch.setattr(J, "NET_JITTER_S", 0)
    monkeypatch.setattr(J.time, "sleep", lambda s: None)
    retrying = J.net_retry(job, KEYS[0])
    assert retrying.wait.max == J.NET_MAX_WAIT_S
    monkeypatch.setattr(J, "NET_GIVE_UP_S", 0)
    with pytest.raises(requests.exceptions.ConnectionError):                    # given up: the error goes up
        for attempt in J.net_retry(job, KEYS[0]):
            with attempt:
                raise requests.exceptions.ConnectionError("down")


def test_a_plain_stop_is_not_tried_again(tmp_path, monkeypatch):
    job = make_job(tmp_path)
    calls = []
    monkeypatch.setattr(J.time, "sleep", lambda s: None)
    with pytest.raises(J.Stop):
        for attempt in J.net_retry(job, KEYS[0]):
            with attempt:
                calls.append(1)
                raise J.Stop("wall: ban page")
    assert calls == [1]


def test_the_shop_check_tells_the_network_from_the_shop(tmp_path):
    from shopify_catalog import CatalogError
    job = make_job(tmp_path)

    class Catalog:
        def __init__(self, error):
            self.error = error

        def keys(self):
            raise self.error
    net = CatalogError("shop.myshopify.com: request failed: ConnectionError")
    with pytest.raises(J.NetworkStop):
        J.one(job, {"catalog": Catalog(net)}, KEYS[0], None)
    with pytest.raises(J.Stop) as e:
        J.one(job, {"catalog": Catalog(CatalogError("shop.myshopify.com: HTTP 403 (the token is refused)"))},
              KEYS[0], None)
    assert not isinstance(e.value, J.NetworkStop)


# ---- scroll: a held listing tab, its cards clicked (2026-11-14) -------------------------------------------------

def tab_row(n, batch=1, category="50002788"):
    return {"product_id": str(n), "nv_mid": None, "link": f"https://smartstore.naver.com/s/products/{n}",
            "name": f"상품 {n}", "store": {"channel_no": "100"}, "category_id": category, "query": "q",
            "batch": batch}


def tab_answer(batch, ns, has_more=True, total=7, tab_id="20261114-070000-aaaa"):
    return {"id": tab_id, "query": "q", "batch": batch, "has_more": has_more, "total": total,
            "results": [tab_row(n, batch) for n in ns]}


class TabApi:
    """The /listing-tabs routes: each open starts the scripted listing from its top; a step may be an ApiError
    to raise instead of the batch (`fail`: the call number -> the error)."""
    def __init__(self, batches, fail=None):
        self.batches, self.fail, self.calls = batches, dict(fail or {}), []
        self.at = 0

    def _step(self, name, *a):
        self.calls.append((name, *a))
        error = self.fail.pop(len(self.calls), None)
        if error is not None:
            raise error

    def listing_tab_open(self, query):
        self._step("open", query)
        self.at = 1
        return self.batches[0]

    def listing_tab_next(self, tab_id):
        self._step("next", tab_id)
        self.at += 1
        return self.batches[self.at - 1]

    def listing_tab_specs(self, tab_id, product):
        self._step("specs", tab_id, product)
        return {"specs": []}

    def listing_tab_close(self, tab_id):
        self.calls.append(("close", tab_id))
        return {"id": tab_id, "closed": True}

    def health(self):
        return {"extension": "connected"}

    def captcha(self):
        return {"status": "none"}

    def names(self):
        return [c[0] for c in self.calls]


def scroll_job(tmp_path, **flags):
    import argparse
    args = argparse.Namespace(**{"query": "q", "category": "50002788", "count": 0, "paid": False,
                                 "paid_variants": False, "reviews": 20, "exclude_known": False, "no_translate": True,
                                 "publish": False, "describe": False, **flags})
    return J.new_scroll_job(args, SHOP, str(tmp_path / "shops"), str(tmp_path / "jobs"))


class Pipeline:
    """one() stood in for: each product to the job's final stage at once (stages() read from `state`); `lost`:
    keys whose first read loses the tab; `fail`: keys whose first read fails at translate (prepared, failed)."""
    def __init__(self, monkeypatch, lost=(), fail=()):
        self.state, self.taken, self.lost, self.fail = {}, [], set(lost), set(fail)
        monkeypatch.setattr(J, "stages", lambda job: dict(self.state))
        monkeypatch.setattr(J, "one", self.one)
        monkeypatch.setattr(J.random, "uniform", lambda a, b: a)

    def one(self, job, ctx, key, stage_now, n=0):
        self.taken.append((key, stage_now))
        if key in self.lost:
            self.lost.discard(key)
            raise J.TabLost("/listing-tabs/x/specs -> 410: a login gate on product")
        if key in self.fail:
            self.fail.discard(key)
            self.state[key] = "prepared"
            job.log(key, "failed", stage="translate", reason="x")
            return "translate failed"
        self.state[key] = job.final
        return "done"


def screen():
    from listing_filter import Screen
    return Screen("50002788", SHOP, exclusions={"universal": {"rules": []}}, category_rules=[])


class Catalog:
    def keys(self):
        return set()


def run_scroll(job, api):
    tab = J.Tab(job, api)
    ctx = {"api": api, "catalog": Catalog(), "specs": tab.specs}
    return J.run_scroll(job, ctx, tab, screen(), set())


def k(n):
    return f"{SHOP}:naver:100:{n}"


def test_a_scroll_job_reads_the_listing_batch_by_batch_to_its_end(tmp_path, monkeypatch, no_sleep):
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch)
    batches = [tab_answer(1, [1, 2]), tab_answer(2, [3, 4]), tab_answer(3, [5], has_more=False)]
    batches[1]["results"][1]["category_id"] = "999"                             # left out by the screen
    batches[1]["results"].append(tab_row(2, 2))                                 # a repeat of a done product
    api = TabApi(batches)
    assert run_scroll(job, api) == 0
    assert [key for key, _ in p.taken] == [k(1), k(2), k(3), k(5)]
    assert api.names() == ["open", "next", "next", "close"]                    # no scroll after has_more false
    job = J.Job(job.folder)
    assert [r["key"] for r in job.rows()] == [k(1), k(2), k(3), k(5)]
    assert job.meta["mode"] == "scroll" and job.meta["total"] == 7 and job.meta["tab"] is None
    assert job.meta["screen"] == {"category_mismatch": 1}
    events = [e["event"] for e in job.events()]
    assert events.count("batch") == 3 and events[-1] == "done"


def test_a_scroll_job_writes_every_row_left_out_to_screened_jsonl(tmp_path, monkeypatch, no_sleep):
    """The owner, 2026-11-14: a lenient screen, and every leave-out on file for the audit (once a product a run)."""
    from listing_filter import Screen
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch)
    batches = [tab_answer(1, [1, 2, 3]), tab_answer(2, [4, 2], has_more=False)]
    batches[0]["results"][1]["name"] = "어린이용 발광 피클볼 라켓 세트 야간용 초보자용 라켓"    # title:accessory
    batches[0]["results"][2]["category_id"] = "999"
    batches[1]["results"][1]["name"] = batches[0]["results"][1]["name"]              # the same product again
    tab = J.Tab(job, TabApi(batches))
    ctx = {"api": tab.api, "catalog": Catalog(), "specs": tab.specs}
    screen = Screen("50002788", SHOP, exclusions={"universal": {"rules": []}})
    assert J.run_scroll(job, ctx, tab, screen, set()) == 0
    assert [key for key, _ in p.taken] == [k(1), k(4)]
    with open(os.path.join(job.folder, "screened.jsonl"), encoding="utf-8") as f:
        lines = [json.loads(x) for x in f]
    assert [(x["batch"], x["product_id"], x["reason"]) for x in lines] == [
        (1, "2", "title:accessory"), (1, "3", "category_mismatch")]
    assert lines[0]["name"].startswith("어린이용 발광 피클볼") and lines[0]["at"]


def test_a_scroll_job_stops_at_its_count_mid_batch_and_closes_the_tab(tmp_path, monkeypatch, no_sleep):
    job = scroll_job(tmp_path, count=2)
    p = Pipeline(monkeypatch)
    api = TabApi([tab_answer(1, [1, 2, 3]), tab_answer(2, [4])])
    assert run_scroll(job, api) == 0
    assert [key for key, _ in p.taken] == [k(1), k(2)] and api.names() == ["open", "close"]
    assert len(J.Job(job.folder).rows()) == 2 and job.events()[-1]["event"] == "done"


def test_a_lost_tab_is_opened_again_and_done_products_are_skipped(tmp_path, monkeypatch, no_sleep):
    from naver_api_client import ApiError
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch)
    api = TabApi([tab_answer(1, [1, 2]), tab_answer(2, [3], has_more=False)],
                 fail={2: ApiError(410, "listing tab x: the listing tab was closed; open a new one")})
    assert run_scroll(job, api) == 0
    assert [key for key, _ in p.taken] == [k(1), k(2), k(3)]                    # 1 and 2 not read again
    assert api.names() == ["open", "next", "open", "next", "close"]
    assert no_sleep.count(J.REOPEN_WAIT_S[0]) == 1
    reopen = next(e for e in job.events() if e["event"] == "reopen")
    assert reopen["batch"] == 1 and "closed" in reopen["reason"]
    assert len(J.Job(job.folder).meta["reopens"]) == 1


def test_a_product_cut_off_by_a_lost_tab_is_read_again_when_its_card_comes(tmp_path, monkeypatch, no_sleep):
    """Fable review 1: a row already in listing.jsonl but with no stage is not skipped, nor written twice."""
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch, lost={k(2)})
    api = TabApi([tab_answer(1, [1, 2, 3], has_more=False)])
    assert run_scroll(job, api) == 0
    assert [key for key, _ in p.taken] == [k(1), k(2), k(2), k(3)]
    assert [r["key"] for r in J.Job(job.folder).rows()] == [k(1), k(2), k(3)]
    assert api.names() == ["open", "open", "close"]


def test_the_third_lost_tab_in_an_hour_stops(tmp_path, monkeypatch, no_sleep):
    from naver_api_client import ApiError
    job = scroll_job(tmp_path)
    now = J.time.time()
    job.meta["reopens"] = [{"t": now - 600}, {"t": now - 60}, {"t": now - 4000}]  # the last one is too old to count
    job.save_meta()
    Pipeline(monkeypatch)
    api = TabApi([tab_answer(1, [1]), tab_answer(2, [2])], fail={2: ApiError(410, "gone")})
    assert run_scroll(job, api) == 3
    assert job.events()[-1]["event"] == "stop" and "lost 3 times" in job.events()[-1]["reason"]
    assert api.names() == ["open", "next"]                                      # nothing left open to close


def test_a_wall_while_scrolling_stops_and_closes_the_tab(tmp_path, monkeypatch, no_sleep):
    from naver_api_client import ApiError
    job = scroll_job(tmp_path)
    Pipeline(monkeypatch)
    api = TabApi([tab_answer(1, [1]), tab_answer(2, [2])],
                 fail={3: ApiError(503, "wall: listing tab x: stalled, the page loaded no batch 2")})
    assert run_scroll(job, api) == 3
    assert api.names() == ["open", "next", "next", "close"] and "stalled" in job.events()[-1]["reason"]


def test_scroll_job_resumes_and_takes_the_ones_with_a_stage_first_and_a_failed_one_at_the_end(
        tmp_path, monkeypatch, no_sleep):
    job = scroll_job(tmp_path, no_translate=False)
    with open(os.path.join(job.folder, "listing.jsonl"), "w") as f:            # an earlier run of the job
        f.write("".join(json.dumps({**tab_row(n), "key": k(n)}) + "\n" for n in (1, 2, 3)))
    p = Pipeline(monkeypatch, fail={k(4)})
    p.state.update({k(1): job.final, k(2): "collected"})                        # 3: cut off before its stage
    api = TabApi([tab_answer(1, [1, 2, 3, 4], has_more=False)])
    assert run_scroll(J.Job(job.folder), api) == 0
    assert p.taken == [(k(2), "collected"), (k(3), None), (k(4), None), (k(4), "prepared")]
    assert api.names() == ["open", "close"]
    assert J.Job(job.folder).events()[-1]["event"] == "done"


def test_sigterm_closes_the_tab(tmp_path, monkeypatch, no_sleep):
    import signal
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch)
    real = p.one

    def killed(job, ctx, key, stage_now, n=0):
        os.kill(os.getpid(), signal.SIGTERM)
        return real(job, ctx, key, stage_now, n)
    monkeypatch.setattr(J, "one", killed)
    before = signal.getsignal(signal.SIGTERM)
    api = TabApi([tab_answer(1, [1, 2])])
    assert run_scroll(job, api) == 130
    assert api.names() == ["open", "close"] and J.Job(job.folder).meta["tab"] is None
    assert signal.getsignal(signal.SIGTERM) is before and job.events()[-1]["event"] == "stop"


def test_run_and_refresh_refuse_a_scroll_job(tmp_path, capsys):
    import argparse
    job = scroll_job(tmp_path)
    assert J.cmd_run(argparse.Namespace(job=job.folder, items=0)) == 2
    assert J.cmd_refresh(argparse.Namespace(job=job.folder, more=50)) == 2
    assert f"scroll --job {job.id}" in capsys.readouterr().out
    assert not J._scroll_job(make_job(tmp_path / "old"))                          # an old job.json has no mode


def test_paid_choices_read_a_scroll_job(tmp_path):
    import run_transform
    job = scroll_job(tmp_path, paid=True, paid_variants=True)
    with open(os.path.join(job.folder, "listing.jsonl"), "w") as f:
        f.write(json.dumps({**tab_row(5), "key": k(5)}) + "\n")
    got = run_transform.paid_choices(SHOP, str(tmp_path / "shops"), str(tmp_path / "jobs"))
    assert got == {"5": run_transform.VARIANTS}


def test_tab_specs_read_by_the_click_and_a_missing_card_is_none(tmp_path):
    from naver_api_client import ApiError
    job = scroll_job(tmp_path)
    api = TabApi([tab_answer(1, [1])], fail={
        3: ApiError(404, "product 1 has no card in the listing tab for 'q' (batch 1)"),
        4: ApiError(404, "product 1: card_opened_nothing: its card in the listing for 'q' opened no page"),
        5: ApiError(404, "product 1 is not found")})                         # the product itself: collect's
    tab = J.Tab(job, api)
    with pytest.raises(ApiError) as e:
        tab.specs(api, "l", "q")                                                # no tab open yet: as a lost one
    assert e.value.status == 410
    tab.open()
    assert tab.specs(api, "link", "q") == {"specs": []} and api.calls[-1] == ("specs", tab.id, "link")
    assert tab.specs(api, "link", "q") is None and tab.specs(api, "link", "q") is None
    with pytest.raises(ApiError, match="not found"):
        tab.specs(api, "link", "q")
    assert J.Job(job.folder).meta["tab"] == tab.id


def test_a_lost_tab_while_collecting_is_tab_lost(tmp_path, no_sleep):
    job = make_job(tmp_path)
    guard = Guard(SourceStopped("410", status=410, error="listing tab x is gone"))
    with pytest.raises(J.Stop) as e:                                           # the old mode: a plain stop
        J.collect_with_waits(job, Api(), None, {}, guard, job.rows()[0], str(tmp_path))
    assert not isinstance(e.value, J.TabLost)
    job.meta["mode"] = "scroll"
    guard = Guard(SourceStopped("410", status=410, error="listing tab x is gone"))
    with pytest.raises(J.TabLost):
        J.collect_with_waits(job, Api(), None, {}, guard, job.rows()[0], str(tmp_path), specs=lambda *a: None)


def test_a_connection_lost_during_next_opens_a_new_tab_not_a_second_next(tmp_path, monkeypatch, no_sleep):
    """The server may have handed out the batch before the connection dropped: sent again, next would skip it."""
    import requests
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch)
    api = TabApi([tab_answer(1, [1]), tab_answer(2, [2], has_more=False)],
                 fail={2: requests.exceptions.ConnectionError("connection aborted mid-body")})
    assert run_scroll(job, api) == 0
    assert api.names() == ["open", "next", "open", "next", "close"]
    assert [key for key, _ in p.taken] == [k(1), k(2)]
    assert any(e["event"] == "reopen" and "connection" in e["reason"] for e in job.events())


def test_an_open_cut_off_says_how_the_adapter_is_freed(tmp_path, capsys):
    job = scroll_job(tmp_path)
    api = TabApi([tab_answer(1, [1])], fail={1: KeyboardInterrupt()})
    tab = J.Tab(job, api)
    with pytest.raises(KeyboardInterrupt):
        tab.open()
    tab.close()
    assert "open of the listing tab was cut off" in capsys.readouterr().out and api.names() == ["open"]


def test_scroll_asks_again_only_on_the_servers_captcha_words(tmp_path, no_sleep):
    """Fable review 5: /captcha stays timed_out until the next captcha; a ban after one is not read again."""
    job = make_job(tmp_path)
    job.meta["mode"] = "scroll"
    guard = Guard(SourceStopped("503", status=503, error="wall: captcha not answered on product 11; the listing "
                                                         "tab is kept"))
    out = J.collect_with_waits(job, Api(captcha="none"), None, {}, guard, job.rows()[0], str(tmp_path))
    assert out.status == "complete" and [e["event"] for e in job.events()] == ["captcha_again"]
    guard = Guard(SourceStopped("503", status=503, error="wall: ban page at product 11; the listing tab is closed"))
    with pytest.raises(J.Stop):
        J.collect_with_waits(job, Api(captcha="timed_out"), None, {}, guard, job.rows()[0], str(tmp_path))


def test_collect_reads_specs_its_way_and_a_410_stops_the_source():
    from collect_product import collect, stopped
    from naver_api_client import ApiError

    class Box:
        def product_details(self, link):
            return {"id": "11"}

        def selected_reviews(self, link, count):
            return {"results": []}
    asked = []
    out = collect(Box(), None, {}, {"link": "l"}, "/nowhere", query="q", category="50002788",  # type: ignore
                  specs=lambda api, link, query: asked.append((link, query)))
    assert out.status == "not_taken" and out.reason == "card_not_found" and asked == [("l", "q")]

    def gone(api, link, query):
        raise ApiError(410, "listing tab x is gone")
    with pytest.raises(SourceStopped) as e:
        collect(Box(), None, {}, {"link": "l"}, "/nowhere", query="q", category="50002788", specs=gone)  # type: ignore
    assert e.value.status == 410 and stopped(ApiError(410)) and not stopped(ApiError(404))
