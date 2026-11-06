"""Offline tests for the deferred journal (deferred_log.py) and the run rules (collect_guard.py).

    .venv/bin/python -m pytest scripts/test_deferred_log.py -q
"""
import json

import pytest

from collect_guard import CollectGuard, Outcome, RunStopped
from deferred_log import DeferredLog, main

A, B, C = (f"fairwardgolf:naver:100:{n}" for n in (1, 2, 3))


def outcomes(*items):
    seq = list(items)
    return lambda: seq.pop(0)


def test_partial_twice_is_deferred_with_the_first_error(tmp_path):
    log = DeferredLog("fairwardgolf", str(tmp_path))
    guard = CollectGuard(log)
    out = guard.run(A, outcomes(Outcome.partial("specs_missing", "404"), Outcome.partial("specs_missing", "503")))
    assert out.status == "deferred" and out.attempts == 2 and out.first == {"reason": "specs_missing", "error": "404"}
    assert log.blocked() == {A}
    [event] = log.events()
    assert event["event"] == "deferred" and event["first_error"]["error"] == "404"


def test_one_retry_that_works_is_not_deferred(tmp_path):
    log = DeferredLog("fairwardgolf", str(tmp_path))
    out = CollectGuard(log).run(A, outcomes(Outcome.partial("photos_incomplete"), Outcome("complete")))
    assert out.status == "complete" and out.attempts == 2 and not log.events()


def test_same_reason_on_two_products_in_a_row_stops_the_run(tmp_path):
    guard = CollectGuard(DeferredLog("fairwardgolf", str(tmp_path)))
    bad = lambda: Outcome.partial("specs_missing")        # noqa: E731
    guard.run(A, bad)
    with pytest.raises(RunStopped, match="specs_missing"):
        guard.run(B, bad)


def test_other_reason_or_a_good_product_between_keeps_going(tmp_path):
    guard = CollectGuard(DeferredLog("fairwardgolf", str(tmp_path)))
    guard.run(A, lambda: Outcome.partial("specs_missing"))
    guard.run(B, lambda: Outcome.partial("photos_incomplete"))
    guard.run(C, lambda: Outcome("complete"))
    assert guard.run(A, lambda: Outcome.partial("photos_incomplete")).status == "deferred"


def test_owner_allows_one_retry_and_it_is_spent(tmp_path):
    log = DeferredLog("fairwardgolf", str(tmp_path))
    log.defer(A, "specs_missing", {"error": "x"})
    with pytest.raises(ValueError, match="is not deferred"):
        log.allow(B, "owner")
    with pytest.raises(ValueError, match="--by"):
        log.allow(A, " ")
    log.allow(A, "owner", "the page works again")
    assert A not in log.blocked() and log.retry_allowed(A)
    with pytest.raises(ValueError, match="it is retry_allowed"):
        log.allow(A, "owner")
    CollectGuard(log).run(A, lambda: Outcome("complete"))
    assert A not in log.blocked() and not log.retry_allowed(A)     # spent, and the retry worked: taken again
    assert [e["event"] for e in log.events()] == ["deferred", "retry_allowed", "retried"]


def test_an_allowed_retry_that_fails_again_is_deferred_anew(tmp_path):
    log = DeferredLog("fairwardgolf", str(tmp_path))
    log.defer(A, "specs_missing", None)
    log.allow(A, "owner")
    out = CollectGuard(log).run(A, lambda: Outcome.partial("specs_missing"))
    assert out.status == "deferred" and A in log.blocked()
    assert [e["event"] for e in log.events()] == ["deferred", "retry_allowed", "retried", "deferred"]
    assert log.events()[2]["outcome"] == "deferred"
    log.allow(A, "owner", "once more")                               # the owner may allow again


def test_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("deferred_log.JOURNAL_DIR", str(tmp_path))
    monkeypatch.setattr(DeferredLog.__init__, "__defaults__", (str(tmp_path),))
    DeferredLog("fairwardgolf").defer(A, "specs_missing", None)
    assert main(["--store", "fairwardgolf", "allow", A, "--by", "owner"]) == 0
    assert main(["--store", "fairwardgolf", "allow", A, "--by", "owner"]) == 2
    assert main(["--store", "fairwardgolf", "list"]) == 0
    assert f"{A}  retry_allowed  specs_missing" in capsys.readouterr().out
    lines = (tmp_path / "deferred-fairwardgolf.jsonl").read_text().splitlines()
    assert [json.loads(x)["event"] for x in lines] == ["deferred", "retry_allowed"]
