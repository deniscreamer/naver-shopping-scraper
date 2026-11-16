"""job_report.py (job.py report / where / watch) over the real-data fixture's two jobs (conftest shop_fixture): job A
fairwardgolf-50002783-20261115T150124Z (434 events: stop, waiting, reopen, network_wait, duplicate_of), job B
fairwardgolf-50002783-20261116T083154Z (93 events, done, duplicate_of_withdrawn). watch runs on a fake clock and a
fake runner; the "runner" is the test appending lines between two polls. Offline."""
import json
import os

import pytest

import job as J
import job_report as R
from shop_files import LedgerError

JOB_A = "fairwardgolf-50002783-20261115T150124Z"
JOB_B = "fairwardgolf-50002783-20261116T083154Z"
LIVE_TWICE = "fairwardgolf:naver:102770910:12557420063"      # A: not_taken duplicate_of, B: published
HANDLE_TWICE = "gosports-illegal-max-spin-mens-right-handed-wedge-set-sand-lob-gap-wedges"
NOT_PREPARED = "fairwardgolf:naver:102709004:12178049211"    # not_taken in the jobs, in no shop file of the fixture


def folder(fx, job):
    return os.path.join(fx.jobs, job)


def append(path, *events, raw=None):
    with open(path, "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps({"at": "2026-11-16T09:00:00+00:00", "key": None, **e}) + "\n")
        if raw is not None:
            f.write(raw)


# ---- reason codes, times ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("reason,code", [
    ("duplicate_of:fairwardgolf:naver:1100142898:13619604371", "duplicate_of"),
    ("duplicate_of_withdrawn:fairwardgolf:naver:102337501:13363811363", "duplicate_of_withdrawn"),
    ("not ready to publish (placement held: single_only)", "placement held: single_only"),
    ("not ready to publish (placement unresolved: gender unknown)", "placement unresolved: gender unknown"),
    ("title:not_golf (a cable-pulling grip; the rule added after the snapshot)", "title:not_golf"),
    ("card_not_found", "card_not_found"),
    (None, "-"),
    ("", "-"),
])
def test_reason_code(reason, code):
    assert R.reason_code(reason) == code


def test_iso_time_no_zone_is_utc_and_bad_raises():
    assert R.iso_time("2026-11-16").isoformat() == "2026-11-16T00:00:00+00:00"
    assert R.iso_time("2026-11-16T08:40:00Z") == R.iso_time("2026-11-16T08:40:00+00:00")
    with pytest.raises(ValueError):
        R.iso_time("yesterday")


# ---- report ----------------------------------------------------------------------------------------------------

def test_report_job_a(shop_fixture):
    r = R.report(folder(shop_fixture, JOB_A))
    assert (r["job"], r["shop"], r["mode"], r["final"], r["finished"]) == (JOB_A, "fairwardgolf", "scroll",
                                                                           "published", False)
    assert r["events"] == 434 and r["counts"]["published"] == 62 and r["counts"]["stop"] == 3
    assert r["reasons"]["not_taken"]["duplicate_of"] >= 1
    assert "placement held: single_only" in r["reasons"]["not_taken"]
    assert r["held"]["single_only"] >= 1
    assert [s["reason"] for s in r["stops"]] == ["interrupted (SIGTERM)"] * 3
    assert {w["event"] for w in r["waits"]} == {"waiting", "back", "reopen", "network_wait"}
    assert r["cost"]["translated"] > 0 and r["cost"]["described"] > 0
    lines = R.report_lines(r)
    assert f"job\tjob\t{JOB_A}" in lines and "event\tpublished\t62" in lines
    assert all(len(x.split("\t")) == 3 for x in lines)            # section, name, value: stable TSV


def test_report_job_b_done_and_withdrawn_duplicates(shop_fixture):
    r = R.report(folder(shop_fixture, JOB_B))
    assert r["finished"] and r["events"] == 93 and r["counts"]["done"] == 1
    assert r["reasons"]["not_taken"].get("duplicate_of_withdrawn", 0) >= 1


def test_report_filters_event_and_since(shop_fixture):
    f = folder(shop_fixture, JOB_A)
    r = R.report(f, event="published")
    assert r["counts"] == {"published": 62} and r["events"] == 62 and not r["stops"]
    late = R.report(f, since=R.iso_time("2026-11-15T17:00:00"))
    assert 0 < late["events"] < 434 and late["first"] >= "2026-11-15T17:00:00"
    assert R.report(f, since=R.iso_time("2030-01-01"))["events"] == 0


def test_table_one_row_a_key(shop_fixture):
    rows = R.table(R.events(folder(shop_fixture, JOB_B)))
    assert len(rows) == len({r["key"] for r in rows}) == R.report(folder(shop_fixture, JOB_B))["keys"]
    row = next(r for r in rows if r["key"] == LIVE_TWICE)
    assert (row["last_event"], row["status"], row["handle"]) == ("published", "published", HANDLE_TWICE)
    text = R.table_text(rows)
    assert text.splitlines()[0].split("\t") == list(R.TABLE)
    assert all(len(x.split("\t")) == len(R.TABLE) for x in text.splitlines())


def test_report_torn_last_line_ignored_bad_middle_line_raises(shop_fixture):
    f = folder(shop_fixture, JOB_A)
    append(os.path.join(f, "events.jsonl"), raw='{"at": "2026-11-16T09:00:00+00:00", "event": "publi')
    assert R.report(f)["events"] == 434
    with open(os.path.join(f, "events.jsonl"), "a", encoding="utf-8") as fh:
        fh.write("\n" + json.dumps({"event": "published"}) + "\n")     # the torn line is now a middle line
    with pytest.raises(LedgerError):
        R.report(f)
    assert J.main(["report", "--job", f]) == R.EXIT_BROKEN


def test_report_empty_job(shop_fixture):
    f = folder(shop_fixture, JOB_B)
    os.remove(os.path.join(f, "events.jsonl"))
    r = R.report(f)
    assert (r["events"], r["counts"], r["finished"], r["first"]) == (0, {}, False, None)
    assert R.table([]) == []


def test_report_big_input(tmp_path):
    f = tmp_path / "big"
    f.mkdir()
    (f / "job.json").write_text(json.dumps({"shop": "s", "category": "1", "publish": True}), encoding="utf-8")
    with open(f / "events.jsonl", "w", encoding="utf-8") as fh:
        for n in range(60000):
            fh.write(json.dumps({"at": f"2026-11-16T{n // 3600 % 24:02d}:00:00+00:00", "key": f"s:naver:1:{n % 5000}",
                                 "event": ("published", "not_taken", "prepared")[n % 3],
                                 "reason": f"duplicate_of:s:naver:1:{n}", "held": [], "status": "ready"}) + "\n")
    r = R.report(str(f))
    assert r["events"] == 60000 and r["keys"] == 5000 and r["reasons"]["not_taken"] == {"duplicate_of": 20000}
    assert len(R.table(R.events(str(f)))) == 5000


def test_main_report_table_and_json(shop_fixture, tmp_path, capsys):
    f, out = folder(shop_fixture, JOB_B), tmp_path / "t.tsv"
    assert J.main(["report", "--job", f, "--event", "published", "--table", str(out)]) == 0
    rows = out.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 + 5 and rows[0].startswith("key\tlast_event")
    assert "event\tpublished\t5" in capsys.readouterr().out
    assert J.main(["report", "--job", f, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["finished"] is True
    assert J.main(["report", "--job", f, "--table", "-"]) == 0
    assert capsys.readouterr().out.startswith("key\tlast_event")


def test_main_report_no_such_job_and_bad_since(shop_fixture, capsys):
    assert J.main(["report", "--job", os.path.join(shop_fixture.jobs, "nope")]) == R.EXIT_USAGE
    with pytest.raises(SystemExit) as e:
        J.main(["report", "--job", folder(shop_fixture, JOB_A), "--since", "yesterday"])
    assert e.value.code == 2


# ---- where -----------------------------------------------------------------------------------------------------

def where_main(fx, *args):
    return J.main(["where", *args, "--jobs-root", fx.jobs])


def test_where_pid_in_both_jobs(shop_fixture, capsys):
    folders = R.job_folders(shop_fixture.jobs)
    assert [os.path.basename(x) for x in folders] == [JOB_A, JOB_B]
    key = R.where_key("12557420063", folders)
    assert key == LIVE_TWICE
    rows = R.where(key, folders)
    assert {r["job"] for r in rows} == {JOB_A, JOB_B}
    assert [r["at"] for r in rows] == sorted(r["at"] for r in rows)
    assert any(r["event"] == "not_taken" and "duplicate_of" in r["detail"] for r in rows)
    assert rows[-1]["event"] == "published"
    assert where_main(shop_fixture, "12557420063") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"key\t{LIVE_TWICE}" and all(len(x.split("\t")) == 4 for x in out[1:])


def test_where_handle_and_store_link(shop_fixture):
    folders = R.job_folders(shop_fixture.jobs)
    assert R.where_key(HANDLE_TWICE, folders) == LIVE_TWICE
    assert R.where_key(f"https://fairwardgolf.com/products/{HANDLE_TWICE}", folders) == LIVE_TWICE


def test_where_pid_no_shop_file_knows(shop_fixture):
    folders = R.job_folders(shop_fixture.jobs)
    pid = NOT_PREPARED.split(":")[-1]
    assert R.where_key(pid, folders) == pid                    # left out before it was prepared: by its id
    rows = R.where(pid, folders)
    assert rows and all(r["key"] == NOT_PREPARED for r in rows)


def test_where_screened_only(shop_fixture, capsys):
    with open(os.path.join(folder(shop_fixture, JOB_A), "screened.jsonl"), encoding="utf-8") as f:
        pid = json.loads(f.readline())["product_id"]
    assert where_main(shop_fixture, pid) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[1].split("\t")[2] == "screened" and len(out) >= 3       # left out in both jobs (ad)


def test_where_unknown_ref_and_unknown_pid(shop_fixture, capsys):
    assert where_main(shop_fixture, "no-such-handle") == 1
    assert "no product of fairwardgolf matches" in capsys.readouterr().err
    assert where_main(shop_fixture, "999999999999") == 1
    assert "no job touched it" in capsys.readouterr().err


def test_where_ambiguous_pid_lists_candidates(shop_fixture, capsys):
    twin = "fairwardgolf:naver:999:12557420063"
    path = os.path.join(shop_fixture.shops, "fairwardgolf", "prepared", "products.jsonl")
    with open(path, encoding="utf-8") as f:
        line = json.loads(f.readline())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({**line, "key": twin}) + "\n")
    with pytest.raises(R.WhereError) as e:
        R.where_key("12557420063", R.job_folders(shop_fixture.jobs))
    assert "2 products match" in str(e.value) and twin in str(e.value) and LIVE_TWICE in str(e.value)
    assert where_main(shop_fixture, "12557420063") == 1
    assert twin in capsys.readouterr().err
    assert where_main(shop_fixture, LIVE_TWICE) == 0                 # the full key settles it


def test_where_torn_events_line_and_missing_screened(shop_fixture):
    f = folder(shop_fixture, JOB_B)
    os.remove(os.path.join(f, "screened.jsonl"))
    append(os.path.join(f, "events.jsonl"), raw='{"key": "' + LIVE_TWICE + '", "ev')
    rows = R.where(LIVE_TWICE, R.job_folders(shop_fixture.jobs))
    assert {r["job"] for r in rows} == {JOB_A, JOB_B}


def test_where_no_jobs(tmp_path, capsys):
    assert R.job_folders(str(tmp_path)) == []
    assert J.main(["where", "123", "--jobs-root", str(tmp_path)]) == 1


# ---- watch -----------------------------------------------------------------------------------------------------

class Clock:
    """A fake clock: sleep() moves it on and lets the test's runner write its lines."""

    def __init__(self, steps=()):
        self.t, self.steps, self.slept = 0.0, list(steps), []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s
        if self.steps:
            self.steps.pop(0)()


def run_watch(fx, job, steps, runner=lambda: {"pid": 1}, **kw):
    clock = Clock(steps)
    r = R.watch(folder(fx, job), runner, clock=clock, sleep=clock.sleep, **kw)
    return r, clock


def adds(fx, job, *events, raw=None):
    return lambda: append(os.path.join(folder(fx, job), "events.jsonl"), *events, raw=raw)


def test_watch_every_nth_published(shop_fixture):
    pub = {"event": "published", "key": LIVE_TWICE, "status": "published", "handle": "h"}
    # job A has 62 published: with --every 4 the next multiple is 64, the second new one
    r, clock = run_watch(shop_fixture, JOB_A, [adds(shop_fixture, JOB_A, pub), adds(shop_fixture, JOB_A, pub)],
                         every=4)
    assert (r["exit"], r["published"], r["new_published"]) == (R.EXIT_PUBLISHED, 64, 2)
    assert len(clock.slept) == 2 and clock.slept[0] == R.POLL_S
    assert R.watch_line(r).startswith(f"watch {JOB_A}: published") and "(+2)" in R.watch_line(r)


def test_watch_many_published_in_one_read_stops_at_the_first_multiple(shop_fixture):
    pub = {"event": "published", "key": "k", "status": "published"}
    r, _ = run_watch(shop_fixture, JOB_A, [adds(shop_fixture, JOB_A, *[pub] * 25)], every=20)
    assert (r["exit"], r["published"]) == (R.EXIT_PUBLISHED, 80)


@pytest.mark.parametrize("event,code", [
    ({"event": "stop", "reason": "wall: captcha"}, R.EXIT_STOP),
    ({"event": "waiting", "reason": "the API server does not answer"}, R.EXIT_WAITING),
    ({"event": "network_wait", "attempt": R.LONG_TRY, "wait_s": 120, "reason": "x"}, R.EXIT_WAITING),
    ({"event": "captcha_again", "attempt": 1}, R.EXIT_CAPTCHA),
    ({"event": "reopen", "batch": 3, "reason": "410 listing tab gone"}, R.EXIT_REOPEN),
    ({"event": "done", "total": 1}, R.EXIT_DONE),
])
def test_watch_exits_on_each_kind(shop_fixture, event, code):
    r, _ = run_watch(shop_fixture, JOB_A, [adds(shop_fixture, JOB_A, {"event": "collected", "key": "k"}),
                                           adds(shop_fixture, JOB_A, event)])
    assert r["exit"] == code and r["event"]["event"] == event["event"]
    assert r["new"] == {"collected": 1, event["event"]: 1}


def test_watch_short_network_wait_and_old_events_do_not_count(shop_fixture):
    # job A's own stop / waiting / reopen are before the start: not reported again
    r, clock = run_watch(shop_fixture, JOB_A, [adds(shop_fixture, JOB_A, {"event": "network_wait", "attempt": 1}),
                                               adds(shop_fixture, JOB_A, {"event": "back", "after_s": 3})],
                         timeout=35)
    assert r["exit"] == R.EXIT_TIMEOUT and r["new"] == {"back": 1, "network_wait": 1}
    assert sum(clock.slept) == 35                     # the last sleep cut to the time left


def test_watch_done_at_start(shop_fixture):
    r, clock = run_watch(shop_fixture, JOB_B, [], runner=lambda: None)
    assert r["exit"] == R.EXIT_DONE and clock.slept == []


def test_watch_runner_gone_after_its_last_line(shop_fixture):
    seen = iter([{"pid": 1}])                                    # alive at the first poll, gone at the second
    r, clock = run_watch(shop_fixture, JOB_A, [lambda: None], runner=lambda: next(seen, None))
    assert r["exit"] == R.EXIT_NO_RUNNER and clock.t < R.START_GRACE_S


def test_watch_runner_logs_stop_then_dies(shop_fixture):
    # the read comes after the runner check: a stop written just before the exit is the reason, not "no runner"
    state = {"alive": True}

    def die():
        append(os.path.join(folder(shop_fixture, JOB_A), "events.jsonl"), {"event": "stop", "reason": "x"})
        state["alive"] = False
    r, _ = run_watch(shop_fixture, JOB_A, [die], runner=lambda: {"pid": 1} if state["alive"] else None)
    assert r["exit"] == R.EXIT_STOP


def test_watch_no_runner_ever_waits_the_grace(shop_fixture):
    r, clock = run_watch(shop_fixture, JOB_A, [], runner=lambda: None)
    assert r["exit"] == R.EXIT_NO_RUNNER and clock.t >= R.START_GRACE_S


def test_watch_torn_line_seen_once_complete(shop_fixture):
    path = os.path.join(folder(shop_fixture, JOB_A), "events.jsonl")

    def finish():
        with open(path, "a", encoding="utf-8") as f:
            f.write('"reason": "x"}\n')
    r, clock = run_watch(shop_fixture, JOB_A, [adds(shop_fixture, JOB_A, raw='{"event": "stop", '), finish])
    assert r["exit"] == R.EXIT_STOP and len(clock.slept) == 2


def test_watch_empty_job_then_events(shop_fixture):
    os.remove(os.path.join(folder(shop_fixture, JOB_A), "events.jsonl"))
    r, _ = run_watch(shop_fixture, JOB_A, [adds(shop_fixture, JOB_A, {"event": "published", "key": "k"})], every=1)
    assert (r["exit"], r["published"]) == (R.EXIT_PUBLISHED, 1)


def test_main_watch_wires_exit_codes(shop_fixture, monkeypatch, capsys):
    monkeypatch.setattr(J.Job, "now", lambda self: None)          # never a real pid
    assert J.main(["watch", "--job", folder(shop_fixture, JOB_A), "--timeout", "0"]) == R.EXIT_TIMEOUT
    assert "timeout" in capsys.readouterr().out
    assert J.main(["watch", "--job", folder(shop_fixture, JOB_B), "--json"]) == R.EXIT_DONE
    assert json.loads(capsys.readouterr().out)["exit"] == R.EXIT_DONE
    assert J.main(["watch", "--job", os.path.join(shop_fixture.jobs, "nope")]) == R.EXIT_USAGE


def test_watch_never_locks_or_writes(shop_fixture, monkeypatch):
    import shop_files
    monkeypatch.setattr(shop_files, "shop_lock", lambda *a, **k: pytest.fail("watch took the shop lock"))
    f = folder(shop_fixture, JOB_A)
    before = {n: os.path.getmtime(os.path.join(f, n)) for n in os.listdir(f)}
    run_watch(shop_fixture, JOB_A, [], timeout=0)
    R.report(f)
    assert {n: os.path.getmtime(os.path.join(f, n)) for n in os.listdir(f)} == before
