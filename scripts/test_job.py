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

    def fake_read(api, store, queries, category, batches, skip, known, leaf=None):
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


def test_heartbeat_of_a_reused_pid_is_not_a_live_runner(tmp_path):
    job = make_job(tmp_path)
    job.beat(key=KEYS[0], n=1, stage="collect", since="t")
    with open(os.path.join(job.folder, "now.json"), encoding="utf-8") as f:
        now = json.load(f)
    assert now["started"]                                                       # the runner's start time is written
    now["started"] = "Thu Jan  1 00:00:00 1970"                                 # the pid now belongs to another start
    with open(os.path.join(job.folder, "now.json"), "w") as f:
        json.dump(now, f)
    assert job.now() is None
    del now["started"]                                                          # a now.json from before the field:
    with open(os.path.join(job.folder, "now.json"), "w") as f:                  # the live pid runs pytest, not job.py
        json.dump(now, f)
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


def test_a_product_prepared_before_with_no_sidecar_reads_its_images_first(tmp_path, monkeypatch):
    """2026-11-17, the wedge pilot: 20 products an earlier job had prepared, never read for their description
    images, went to the store with the category's default package (description_images_missing). A prepared
    product of a category that reads images, with no sidecar of this collection, goes back to "collected"; one
    with its sidecar stays prepared; one in the store already is never sent back."""
    import description_images as DI
    job = _translating_job(tmp_path, {KEYS[0]: "translated", KEYS[1]: "untranslated", KEYS[2]: "translated"})
    job.meta["publish"] = True
    job.save_meta()
    shop = tmp_path / "shops" / SHOP
    (shop / "collected").mkdir()
    line = {"specs": {"category": {"id": "50002783"}}, "details": {"description": {}}}
    monkeypatch.setattr("run_transform.latest_lines", lambda *a, **k: {k: (None, None, line) for k in KEYS})
    (shop / "publish").mkdir()
    (shop / "publish" / "published.jsonl").write_text(json.dumps({"key": KEYS[2], "status": "published"}) + "\n")
    read = {KEYS[1].split(":")[3]}
    monkeypatch.setattr(DI, "load_sidecar", lambda s, pid, root=None: {"pid": pid} if pid in read else None)
    monkeypatch.setattr(DI, "current", lambda sidecar, ln: sidecar is not None)
    got = J.stages(job)
    assert got == {KEYS[0]: "collected", KEYS[1]: "prepared", KEYS[2]: "published"}


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
    monkeypatch.setattr(PB.Shop, "not_ready", lambda self, k: None if k == KEYS[1] else "translation held")
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
    seen = []                                                   # --draft (2026-11-16): passed on to publish_one
    monkeypatch.setattr(PB, "publish_one", lambda shop, key, *a, **k: seen.append(k.get("draft")) or
                        {"key": key, "status": "published", "handle": "h", "prices_usd": [1]})
    J.publish_step(job, {}, KEYS[1])
    job.meta["draft"] = True
    J.publish_step(job, {}, KEYS[1])
    assert seen == [False, True]


def test_a_product_the_shop_withdrew_is_done_for_the_job_but_not_counted(tmp_path, monkeypatch):
    """2026-11-18, the chipper scroll: 5 products replaced by a better copy (replaced_by, withdrawn) fell back to
    "translated", and the end-of-run drain sent each to publish_step again ("not ready to publish (placement placed:
    None)"). A withdrawn product (replaced_by, a hold, the owner) is done; --count counts the live and draft ones, as
    before; publish_step names the gate a product fails."""
    import publish as PB
    job = _translating_job(tmp_path, {KEYS[0]: "translated", KEYS[1]: "translated", KEYS[2]: "translated"})
    job.meta.update(publish=True, count=2)
    job.save_meta()
    shop = tmp_path / "shops" / SHOP
    (shop / "collected").mkdir()
    monkeypatch.setattr("run_transform.latest_lines", lambda *a, **k: {k: (None, None, {}) for k in KEYS})
    (shop / "publish").mkdir()
    (shop / "publish" / "published.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (
        {"key": KEYS[0], "status": "published"}, {"key": KEYS[1], "status": "published"},
        {"key": KEYS[1], "status": "withdrawn", "reason": f"replaced_by:{KEYS[2]}"},
        {"key": KEYS[2], "status": "published"})))
    got = J.stages(job)
    assert got == {KEYS[0]: "published", KEYS[1]: "published", KEYS[2]: "published"}
    assert J.next_key(job, got, staged=True) is None                           # the drain has nothing left
    assert J.counted(job, got) == 2 and J.wanted(job, got) is None and J._reached(job)
    job.meta["count"] = 3
    assert J.wanted(job, got) == 1                                              # the withdrawn one is not counted
    monkeypatch.setattr("placement.run", lambda *a, **k: None)
    what = J.publish_step(job, {}, KEYS[1])
    assert what == f"not ready to publish (withdrawn (replaced_by:{KEYS[2]}))"
    assert job.events()[-1] == {**job.events()[-1], "event": "not_taken", "reason": what}
    assert PB.Shop(SHOP, str(tmp_path / "shops")).not_ready(KEYS[1]).startswith("withdrawn")


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
    monkeypatch.setattr(PB.Shop, "not_ready", lambda self, k: None if k in KEYS[:2] else "translation held")
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


def test_an_ad_card_is_not_clicked_and_its_product_is_taken_as_an_ordinary_card(tmp_path, monkeypatch, no_sleep):
    """2026-11-14 (골프채 풀세트): an ad card links through Naver's ad redirect, the tab cannot click it. It is logged
    (reason ad) and left; the same product as an ordinary card later is taken."""
    from listing_filter import Screen
    job = scroll_job(tmp_path)
    p = Pipeline(monkeypatch)
    batches = [tab_answer(1, [1, 2]), tab_answer(2, [2, 3], has_more=False)]
    batches[0]["results"][0]["is_ad"] = True                                          # product 1: an ad only
    batches[0]["results"][1]["is_ad"] = True                                          # product 2: an ad, then ordinary
    tab = J.Tab(job, TabApi(batches))
    ctx = {"api": tab.api, "catalog": Catalog(), "specs": tab.specs}
    screen = Screen("50002788", SHOP, exclusions={"universal": {"rules": []}})
    assert J.run_scroll(job, ctx, tab, screen, set()) == 0
    assert [key for key, _ in p.taken] == [k(2), k(3)]
    with open(os.path.join(job.folder, "screened.jsonl"), encoding="utf-8") as f:
        assert [(x["product_id"], x["reason"]) for x in map(json.loads, f)] == [("1", "ad"), ("2", "ad")]


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


def test_a_job_appends_whole_lines_after_a_tail_with_no_line_end(tmp_path):
    job = make_job(tmp_path)
    with open(os.path.join(job.folder, "listing.jsonl"), "rb+") as f:            # the last line end lost
        f.seek(-1, 2)
        f.truncate()
    J.append_line(os.path.join(job.folder, "listing.jsonl"), json.dumps({"key": "x", "product_id": "9"}))
    job.log(KEYS[0], "failed", reason="x")
    assert [r["key"] for r in job.rows()] == KEYS + ["x"] and job.events()[0]["event"] == "failed"


def test_rows_forgive_a_cut_off_last_line(tmp_path):
    job = make_job(tmp_path)
    with open(os.path.join(job.folder, "listing.jsonl"), "a") as f:
        f.write('{"key": "x", "prod')                                           # scroll killed while appending
    assert [r["key"] for r in job.rows()] == KEYS


def _run(job):
    return {"taken": 0, "started": 0.0, "again": f"run --job {job.id}"}


def test_a_broken_shop_file_stops_the_run_naming_it(tmp_path, monkeypatch, no_sleep, capsys):
    job = make_job(tmp_path)

    def one(job, ctx, key, stage_now, n=0):
        raise J.LedgerError("/x/publish/published.jsonl:7: not a JSON line (fix or remove it by hand)")
    monkeypatch.setattr(J, "one", one)
    assert J.take(job, {}, KEYS[0], None, _run(job)) == 3
    assert job.events()[-1]["event"] == "stop" and "published.jsonl:7" in job.events()[-1]["reason"]
    assert "STOP at" in capsys.readouterr().out


# ---- no run dies silently (2026-11-16) -----------------------------------------------------------------------

KEYS4 = KEYS + [f"{SHOP}:naver:100:14"]


def _cmd_run(job, monkeypatch, one, items=0):
    """cmd_run over a stand-in one(): a product it returns for is at the job's final stage."""
    import argparse
    state: dict = {}

    def done(job, ctx, key, stage_now, n=0):
        what = one(job, ctx, key, stage_now, n)
        state[key] = job.final
        return what
    monkeypatch.setattr(J, "_context", lambda job: ({"store": None}, 0))
    monkeypatch.setattr(J, "stages", lambda job: dict(state))
    monkeypatch.setattr(J, "wanted", lambda job, done: None)
    monkeypatch.setattr(J, "one", done)
    return J.cmd_run(argparse.Namespace(job=job.folder, items=items))


def test_an_unexpected_error_fails_the_product_and_the_run_goes_on(tmp_path, monkeypatch, no_sleep, capsys):
    job = make_job(tmp_path, KEYS4)
    taken = []

    def one(job, ctx, key, stage_now, n=0):
        taken.append(key)
        if key == KEYS4[0]:
            return {}["missing"]                                                # a code defect in one product
        return "prepared: ready"
    assert _cmd_run(job, monkeypatch, one, items=3) == 0
    assert taken == KEYS4                                                       # the next products taken
    failed = [e for e in job.events() if e["event"] == "failed"]
    assert len(failed) == 1 and failed[0]["key"] == KEYS4[0] and failed[0]["stage"] == "unexpected"
    assert failed[0]["reason"].startswith("KeyError: 'missing' @ test_job.py:")
    out = capsys.readouterr()
    assert "11 failed (unexpected): KeyError" in out.out and "Traceback" in out.err
    assert not any(e["event"] == "stop" for e in job.events())


def test_three_unexpected_failures_in_a_row_stop_the_run(tmp_path, monkeypatch, no_sleep, capsys):
    job = make_job(tmp_path, KEYS4)
    taken = []

    def one(job, ctx, key, stage_now, n=0):
        taken.append(key)
        raise TypeError("bad operand")
    assert _cmd_run(job, monkeypatch, one) == 3
    assert taken == KEYS4[:3]                                                   # the fourth not taken
    events = job.events()
    assert [e["event"] for e in events] == ["failed", "failed", "failed", "stop"]
    assert events[-1]["reason"].startswith("3 products in a row failed unexpectedly (the last: TypeError")
    assert "STOP: 3 products in a row failed unexpectedly" in capsys.readouterr().out


def test_a_product_that_ends_otherwise_resets_the_breaker(tmp_path, monkeypatch, no_sleep):
    job = make_job(tmp_path, KEYS4)

    def one(job, ctx, key, stage_now, n=0):
        if key == KEYS4[2]:
            return "not taken: x"
        raise TypeError("bad operand")
    assert _cmd_run(job, monkeypatch, one) == 3               # 11, 12 fail, 13 taken, 14, 11 fail, 12: the third
    assert [e["event"] for e in job.events()] == ["failed"] * 5 + ["stop"]


def test_a_transform_defect_is_still_a_stop_not_a_failed_product(tmp_path, monkeypatch, no_sleep):
    import run_transform
    job = make_job(tmp_path)
    monkeypatch.setattr(run_transform, "run", lambda *a, **k: {}["x"])
    with pytest.raises(J.Stop, match="prepare: KeyError"):
        J.one(job, {}, KEYS[0], "images")
    assert J.take(job, {}, KEYS[0], "images", _run(job)) == 3
    assert [e["event"] for e in job.events()] == ["stop"]


def test_prepare_goes_through_the_cache_and_the_product_comes_from_the_runs_result(tmp_path, monkeypatch):
    """2026-11-16, the prepare cache: one() asks run() for the cache, logs its misses, and takes the product from
    the result (prepared/products.jsonl is not read: here it does not even exist)."""
    import run_transform
    job = make_job(tmp_path)
    calls = []

    def run(shop, runs, shops_root, **k):
        calls.append(k)
        return {"prepared": [{"key": KEYS[0], "status": "held", "held": [{"code": "x", "detail": "y"}]}],
                "cache": {"hit": 2443, "miss": 1}}
    monkeypatch.setattr(run_transform, "run", run)
    assert J.one(job, {}, KEYS[0], "images").startswith("prepared: held ['x']")
    assert calls == [{"cache": True}]
    event = job.events()[-1]
    assert event["event"] == "prepared" and event["cache_miss"] == 1 and event["held"] == ["x"]


def test_a_broken_ledger_at_the_start_is_a_stop_naming_it_without_a_traceback(tmp_path, monkeypatch, capsys):
    import argparse
    job = make_job(tmp_path)

    def context(job):
        raise J.LedgerError("/x/published.jsonl:9: not a JSON line (fix or remove it by hand)")
    monkeypatch.setattr(J, "_context", context)
    assert J.cmd_run(argparse.Namespace(job=job.folder, items=0)) == 3
    out = capsys.readouterr()
    assert "STOP: LedgerError: /x/published.jsonl:9:" in out.out and "Traceback" not in out.err
    assert job.events()[-1]["event"] == "stop" and "published.jsonl:9" in job.events()[-1]["reason"]


def test_an_unexpected_error_outside_a_product_is_a_stop_event(tmp_path, monkeypatch, capsys):
    import argparse
    job = make_job(tmp_path)
    monkeypatch.setattr(J, "_context", lambda job: {}["ctx"])
    assert J.cmd_run(argparse.Namespace(job=job.folder, items=0)) == 3
    assert job.events()[-1]["reason"].startswith("unexpected: KeyError: 'ctx' @ test_job.py:")
    assert "STOP: unexpected: KeyError" in capsys.readouterr().out


# ---- the owner told how a run ended (2026-11-16) ---------------------------------------------------------------

def test_a_stopped_run_tells_the_owner_once_with_the_reason_and_the_resume(tmp_path, monkeypatch, no_sleep,
                                                                           notified):
    job = make_job(tmp_path, KEYS4)
    monkeypatch.setattr(J, "_context", lambda job: ({"store": None}, 0))
    monkeypatch.setattr(J, "stages", lambda job: {})
    monkeypatch.setattr(J, "one", lambda *a, **k: {}["x"])
    assert J.main(["run", "--job", job.folder]) == 3
    assert len(notified) == 1
    event, message, details = notified[0]
    assert event == "job_stop" and message.startswith("j1: 3 products in a row failed unexpectedly")
    assert details["resume"] == "job.py run --job j1" and details["key"] == KEYS4[2]


@pytest.mark.parametrize("code, last, sent", [(0, "done", "job_done"), (0, "failed", None), (2, None, None),
                                              (130, "stop", None), (3, "stop", "job_stop")])
def test_only_a_stop_or_a_finished_job_is_told(tmp_path, monkeypatch, notified, code, last, sent):
    job = make_job(tmp_path)

    def cmd(args):
        if code != 2:
            args.ran = job.folder
        if last:
            job.log(None, last, reason="r")
        return code
    monkeypatch.setattr(J, "cmd_scroll" if code == 130 else "cmd_run", cmd)
    assert J.main(["scroll" if code == 130 else "run", "--job", job.folder]) == code
    assert [n[0] for n in notified] == ([sent] if sent else [])


def test_a_failed_notice_never_raises(monkeypatch, notified, capsys):
    import requests
    monkeypatch.setenv("NAVER_NOTIFY_WEBHOOK", "https://example.invalid/hook")

    def refused(*a, **k):
        raise requests.exceptions.ConnectionError("no route")
    monkeypatch.setattr(requests, "post", refused)
    notified.real("job_stop", "j1: wall")
    assert "webhook failed: ConnectionError" in capsys.readouterr().out


def test_a_scroll_stopped_by_the_shop_check_logs_a_stop_event(tmp_path, monkeypatch):
    """2026-11-16, the phase 2 review: exit 3 at the shop check left no stop event, so the owner's notice carried an
    older stop's reason."""
    job = scroll_job(tmp_path)

    class Broken:
        def keys(self):
            raise RuntimeError("catalog down")
    monkeypatch.setattr(J, "_context", lambda j: ({"store": __import__("shop_stores").get_store(SHOP),
                                                   "catalog": Broken()}, 0))
    assert J._scroll_run(job) == 3
    stops = [e for e in job.events() if e["event"] == "stop"]
    assert stops and stops[-1]["reason"] == "shop check: RuntimeError: catalog down"


def test_job_imports_run_transform_first_so_the_code_signature_is_taken_at_start():
    """2026-11-16, the phase 3 review: the prepare cache's code signature is taken when run_transform is imported;
    job.py imports it at its top, before _context loads other modules of prepare's path."""
    import importlib
    import sys
    src = open(J.__file__, encoding="utf-8").read()
    assert src.index("import run_transform") < src.index("def _context")
    assert "run_transform" in sys.modules and importlib.import_module("run_transform")._CODE_SIG


# ---- draft first: activate (2026-11-16) ------------------------------------------------------------------------

def _drafts_job(tmp_path):
    """KEYS[0] a draft, KEYS[1] live, KEYS[2] a draft then withdrawn; a key of another job a draft too."""
    import publish as PB
    job = make_job(tmp_path)
    shop = PB.Shop(SHOP, str(tmp_path / "shops"))
    for key, extra in ((KEYS[0], {"store_status": "DRAFT"}), (KEYS[1], {}), (KEYS[2], {"store_status": "DRAFT"}),
                       (f"{SHOP}:naver:100:99", {"store_status": "DRAFT"})):
        PB._append(shop.ledger_path, {"key": key, "status": "published", "product_id": f"gid://{key[-2:]}",
                                      "admin_url": "a", **extra})
    PB._append(shop.ledger_path, {"key": KEYS[2], "status": "withdrawn", "product_id": "gid://13"})
    return job, shop


class StatusAdmin:
    def __init__(self, fail=()):
        self.calls, self.fail = [], fail

    def set_status(self, pid, status):
        from shopify_catalog import CatalogError
        self.calls.append((pid, status))
        if pid in self.fail:
            raise CatalogError("refused")
        return status

    def check_shop(self):
        pass


def _activate(monkeypatch, job, admin, *flags):
    import shopify_admin
    import shop_stores
    monkeypatch.setattr(shopify_admin, "ProductsAdmin", lambda store: admin)
    monkeypatch.setattr(shop_stores, "get_store", lambda shop=None: None)
    return J.main(["activate", "--job", job.folder, *flags])         # a full path: open_job joins it as is


def test_activate_dry_run_lists_the_jobs_drafts_and_calls_nothing(tmp_path, monkeypatch, capsys):
    job, _ = _drafts_job(tmp_path)
    admin = StatusAdmin()
    assert J.drafts(job) == [KEYS[0]]                          # not the live, the withdrawn, another job's
    assert _activate(monkeypatch, job, admin, "--dry-run") == 0 and admin.calls == []
    out = capsys.readouterr().out
    assert f"{KEYS[0]}: would be activated" in out and "1 drafts" in out
    assert "category 50002788" not in out                      # reviewed: no reminder


def test_activate_sets_the_drafts_live_without_a_job_event(tmp_path, monkeypatch, capsys):
    job, shop = _drafts_job(tmp_path)
    job.log(None, "done")
    admin = StatusAdmin()
    assert _activate(monkeypatch, job, admin) == 0 and admin.calls == [("gid://11", "ACTIVE")]
    assert shop.ledger()[KEYS[0]]["store_status"] == "ACTIVE" and J.drafts(job) == []
    assert J.summary(job)["finished"] and "1 activated, 0 failed" in capsys.readouterr().out


def test_activate_goes_on_past_a_refused_one_and_exits_1(tmp_path, monkeypatch, capsys):
    import publish as PB
    job, shop = _drafts_job(tmp_path)
    PB._append(shop.ledger_path, {"key": KEYS[1], "status": "published", "product_id": "gid://12",
                                  "store_status": "DRAFT"})
    admin = StatusAdmin(fail=("gid://11",))
    monkeypatch.setattr("transform_shops.reviewed", lambda shop, category: False)
    assert _activate(monkeypatch, job, admin) == 1
    assert admin.calls == [("gid://11", "ACTIVE"), ("gid://12", "ACTIVE")]
    out = capsys.readouterr().out
    assert "1 activated, 1 failed" in out and "set reviewed=True in transform_shops.py on the owner's word" in out


# ---- draft first: the review hints (2026-11-16) ----------------------------------------------------------------

def _publishing_job(tmp_path, n_drafts, n_rows=None):
    import publish as PB
    keys = [f"{SHOP}:naver:100:{i}" for i in range(1, (n_rows or n_drafts) + 1)]
    job = make_job(tmp_path, keys)
    job.meta.update(translate=True, publish=True)
    job.save_meta()
    shop = PB.Shop(SHOP, str(tmp_path / "shops"))
    for i, key in enumerate(keys):
        PB._append(shop.ledger_path, {"key": key, "status": "published", "product_id": f"gid://{i}",
                                      **({"store_status": "DRAFT"} if i < n_drafts else {})})
    return job


def test_no_review_hint_for_a_job_without_drafts_or_publication(tmp_path, capsys):
    assert J.review_due(make_job(tmp_path / "a")) is None
    job = _publishing_job(tmp_path / "b", 0, 3)
    assert J.review_due(job) is None and J.summary(job)["review"] is None
    J._review_reminder(job)
    J._draft_first_line(True, SHOP, "50002788")
    assert capsys.readouterr().out == ""
    assert "drafts" not in J.progress(job, 1, 60)


def test_the_review_is_due_at_review_after_drafts_or_when_done(tmp_path, capsys):
    job = _publishing_job(tmp_path / "a", 3)
    r = J.review_due(job)
    assert r["drafts"] == 3 and not r["due"] and r["category_reviewed"]
    assert f"lens.py section {SHOP} --job j1" in r["commands"][0] and "--category 50002788" in r["commands"][1]
    J._review_reminder(job, due_only=True)                              # the progress line: not yet
    assert capsys.readouterr().out == "" and "; 3 drafts await the review" in J.progress(job, 1, 60)
    J._review_reminder(job)                                             # status / done: one line
    assert "3 drafts await the lens review" in capsys.readouterr().out
    job.log(None, "done")
    assert J.review_due(job)["due"]
    job = _publishing_job(tmp_path / "b", J.REVIEW_AFTER)
    assert J.review_due(job)["due"]
    J._review_reminder(job, due_only=True)
    out = capsys.readouterr().out
    assert "review due: 20 drafts" in out and "visual-review" in out and "lens.py dupes" in out
    assert "job.py activate --job j1" in out and "on the owner's word only" in out


def test_status_prints_the_review_and_its_json_carries_it(tmp_path, monkeypatch, capsys):
    job = _publishing_job(tmp_path, J.REVIEW_AFTER)
    monkeypatch.setattr("transform_shops.reviewed", lambda shop, category: False)
    J.main(["status", "--job", job.folder])
    out = capsys.readouterr().out
    assert "review due: 20 drafts" in out and "reviewed=True in transform_shops.py" in out
    J.main(["status", "--job", job.folder, "--json"])
    assert json.loads(capsys.readouterr().out)["review"]["drafts"] == 20


def test_the_done_line_marks_a_draft_and_the_creation_line_says_draft_first(tmp_path, monkeypatch, capsys):
    import publish as PB
    from test_publish import FakeFiles, FakeProducts
    job = _publishing_job(tmp_path, 0, 1)
    key = job.rows()[0]["key"]
    monkeypatch.setattr(PB, "clients", lambda shop_name: (FakeProducts(), FakeFiles(), {}))
    monkeypatch.setattr(PB.Shop, "not_ready", lambda self, k: None if k in [key] else "translation held")
    monkeypatch.setattr("placement.run", lambda *a, **k: None)
    status = [None]
    monkeypatch.setattr(PB, "publish_one", lambda *a, **k: {"key": key, "status": "published", "handle": "h",
                                                            "prices_usd": [5, 5], "store_status": status[0]})
    assert J.publish_step(job, {}, key) == "published h $5"
    status[0] = "DRAFT"
    assert J.publish_step(job, {}, key) == "published (draft) h $5"
    monkeypatch.setattr("transform_shops.reviewed", lambda shop, category: False)
    J._draft_first_line(True, SHOP, "999")
    assert "draft first: category 999 is not marked reviewed" in capsys.readouterr().out
    J._draft_first_line(False, SHOP, "999")
    assert capsys.readouterr().out == ""


def test_status_says_a_sweep_is_due_when_its_last_run_is_older(tmp_path, monkeypatch, capsys):
    """sweep due (2026-11-19): a commit to the build code, the live dictionaries or the job's finish newer than
    sweep/latest/'s older part; a part missing is due; nothing when latest/ is newer, the shop has no publish ledger
    or a runner holds the shop. The git call is faked."""
    import shop_files
    import translation_dicts
    dicts = tmp_path / "dicts"
    dicts.mkdir()
    monkeypatch.setattr(translation_dicts, "LIVE_ROOT", str(dicts))
    when = {"code": None}
    monkeypatch.setattr(J, "code_changed_at", lambda: when["code"])
    assert J.sweep_due(make_job(tmp_path / "none")) is None                 # no publish ledger: nothing
    job = _publishing_job(tmp_path, 0, 1)
    assert J.sweep_due(job) == "no sweep run yet"
    latest = tmp_path / "shops" / SHOP / "sweep" / "latest"
    latest.mkdir(parents=True)
    t = 1_790_000_000
    (latest / "answers.json").write_text("{}")
    os.utime(latest / "answers.json", (t, t))
    assert J.sweep_due(job) == "no store part yet"                           # --answers alone: the store part due
    (latest / "store.json").write_text("{}")
    os.utime(latest / "store.json", (t + 600, t + 600))                     # the newer part: not the sweep's time
    J.main(["status", "--job", job.folder])
    assert "sweep due" not in capsys.readouterr().out                        # nothing newer
    when["code"] = t + 60
    (dicts / "brand.json").write_text("{}")
    os.utime(dicts / "brand.json", (t - 60, t - 60))                         # older: not a reason
    (dicts / ".brand.x.tmp").write_text("{}")                                # a writer's temp file: not a dictionary
    os.utime(dicts / ".brand.x.tmp", (t + 900, t + 900))
    J.main(["status", "--job", job.folder])
    line = [x for x in capsys.readouterr().out.splitlines() if "sweep due" in x]
    assert line == ["  sweep due: since the last sweep (2026-09-21 14:13Z): a commit to the build code "
                    "2026-09-21 14:14Z (skill sweep)"]
    with shop_files.shop_lock(str(tmp_path / "shops"), SHOP, "job.py run j2"):  # a runner holds the shop
        J.main(["status", "--job", job.folder, "--json"])
        assert json.loads(capsys.readouterr().out)["sweep_due"] is None
    when["code"] = t - 60
    os.utime(dicts / "brand.json", (t + 120, t + 120))
    job.log(None, "done")                                                    # now: newer than t
    J.main(["status", "--job", job.folder, "--json"])
    due = json.loads(capsys.readouterr().out)["sweep_due"]
    assert "the live dictionaries 2026-09-21 14:15Z" in due and "job j1 done" in due and "build code" not in due
    for n in ("answers.json", "store.json"):
        os.utime(latest / n, None)                                           # a sweep just now: newer than all
    os.utime(dicts / "brand.json", (t, t))
    J.main(["status", "--job", job.folder, "--json"])
    assert json.loads(capsys.readouterr().out)["sweep_due"] is None
    monkeypatch.setattr(J, "sweep_due", lambda job: 1 / 0)                   # a hint never breaks status
    assert J.main(["status", "--job", job.folder]) == 0
    assert "sweep due" not in capsys.readouterr().out


def test_code_changed_at_asks_git_for_the_build_paths_only(monkeypatch):
    """code_changed_at: `git log -1 --format=%ct -- <SWEEP_PATHS>` at the repo root, the tests excluded; no git, a
    failure or no commit: None (the reason is skipped quietly)."""
    import subprocess
    seen = {}

    def run(argv, **kw):
        seen.update(argv=argv, cwd=kw.get("cwd"))
        return subprocess.CompletedProcess(argv, 0, "1790000000\n", "")
    monkeypatch.setattr(J.subprocess, "run", run)
    assert J.code_changed_at() == 1_790_000_000.0
    argv = seen["argv"]
    assert argv[:4] == ["git", "log", "-1", "--format=%ct"] and argv[4] == "--"
    assert set(argv[5:]) >= {":(glob)scripts/*.py", ":(glob,exclude)scripts/test_*.py",
                             ":(glob,exclude)scripts/conftest.py", ":(glob)scripts/*.json", "scripts/prompts",
                             "scripts/dictionaries"}
    assert os.path.samefile(seen["cwd"], os.path.dirname(J.SCRIPTS))
    for result in (subprocess.CompletedProcess([], 128, "", "not a git repository"),
                   subprocess.CompletedProcess([], 0, "", "")):
        monkeypatch.setattr(J.subprocess, "run", lambda argv, r=result, **kw: r)
        assert J.code_changed_at() is None

    def no_git(argv, **kw):
        raise FileNotFoundError("git")
    monkeypatch.setattr(J.subprocess, "run", no_git)
    assert J.code_changed_at() is None


def test_a_windbreaker_job_collects_a_jacket_row_as_its_own_category(tmp_path):
    """2026-11-21, the owner: a job of 점퍼 50002798 takes 재킷 50002799 rows too (listing_title_rules `together`):
    such a row is collected as 50002799 (its page must say 50002799), any other row as the job's category; both have
    a category_measures row."""
    job = make_job(tmp_path)
    job.category, job.also = "50002798", ["50002799"]
    assert job.category_of({"category_id": "50002799"}) == "50002799"
    assert job.category_of({"category_id": "50002797"}) == "50002798" and job.category_of({}) == "50002798"
    assert J.Job(job.folder).also == []                                        # 50002788 takes nothing with it
    assert J._no_measures("50002798") == [] and J._no_measures("50002799") == []


def test_the_review_block_covers_both_categories_of_a_windbreaker_job(tmp_path, monkeypatch):
    """2026-11-21 (the review of the 재킷 change): a job of 점퍼 that takes 재킷 shows price and brand lenses for both,
    and names every category not marked reviewed."""
    job = make_job(tmp_path)
    job.category, job.also = "50002798", ["50002799"]
    monkeypatch.setattr(J, "drafts", lambda j: [KEYS[0]])
    monkeypatch.setattr(J.Job, "final", property(lambda self: "published"))
    r = J.review_due(job)
    assert r is not None
    assert r["unreviewed"] == ["50002799"] and not r["category_reviewed"]      # 점퍼 reviewed 2026-11-21, 재킷 not
    assert any("price fairwardgolf --category 50002799" in c for c in r["commands"])
    assert any("brand fairwardgolf --source none --category 50002799" in c for c in r["commands"])
    assert J._unreviewed("fairwardgolf", "50002797") == []
