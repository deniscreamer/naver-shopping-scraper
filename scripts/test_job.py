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


def test_heartbeat_is_shown_only_while_the_runner_lives(tmp_path):
    job = make_job(tmp_path)
    job.beat(key=KEYS[0], n=1, stage="collect", since="t")
    assert job.now()["stage"] == "collect"                                      # this process is alive
    with open(os.path.join(job.folder, "now.json"), "w") as f:
        json.dump({"pid": 999_999_999, "stage": "collect"}, f)
    assert job.now() is None
