"""Offline tests for the listing jobs and their HTTP routes (/listings).
A fake bridge and a fake ext_listing.walk stand in for Chrome; requests go
straight into bottle's WSGI app. No network, no browser.

    python -m pytest server/test_listing_jobs.py -q
"""
import io
import json
import os
import threading
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import bottle
import pytest

import ext_listing
import listing_jobs
import routes  # noqa: F401  (mounts the routes)


class FakeBridge:
    def __init__(self, connected=True):
        self.connected = connected

    def wait_connected(self, timeout=None):
        return self.connected


def call(method, path, **params):
    env = {}
    setup_testing_defaults(env)
    env.update({"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": urlencode(params),
                "wsgi.input": io.BytesIO(), "wsgi.errors": io.StringIO()})
    out = {}
    body = b"".join(bottle.default_app()(env, lambda status, headers, exc_info=None: out.update(
        status=int(status.split()[0]))))
    assert out["status"] != 500, env["wsgi.errors"].getvalue()[-2000:]
    return out["status"], json.loads(body)


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    """Fresh job registry in a temp dir; walk blocks until `release` is set."""
    release = threading.Event()

    def fake_walk(bridge, query, out_dir, max_batches, keep_tab, summary):
        with open(os.path.join(out_dir, "listing.jsonl"), "w", encoding="utf-8") as f:
            for i in range(120):
                f.write(json.dumps({"product_id": str(1000 + i), "query": query}) + "\n")
        summary.update(batches=3, kept=120, total=4385, cursor=111, has_more=True)
        release.wait(5)
        summary["stop"] = "--max-batches 3"
        return ext_listing.finish(summary, out_dir, 0)

    monkeypatch.setattr(listing_jobs, "OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(listing_jobs, "_jobs", {})
    monkeypatch.setattr(listing_jobs, "_bridge", FakeBridge())
    monkeypatch.setattr(ext_listing, "walk", fake_walk)
    yield release
    release.set()


def wait_status(job_id, want):
    for _ in range(100):
        if listing_jobs.get(job_id)["status"] == want:
            return
        threading.Event().wait(0.02)
    raise AssertionError(f"job never reached {want}")


def test_start_poll_and_page(jobs):
    status, job = call("POST", "/listings", query="남성 골프채 풀세트", max_batches=3)
    assert status == 202 and job["status"] == "running" and job["max_batches"] == 3
    status, busy = call("POST", "/naver-shopping/listings", query="x")
    assert status == 409 and busy["job_id"] == job["id"]
    jobs.set()
    wait_status(job["id"], "done")
    status, got = call("GET", f"/listings/{job['id']}")
    assert status == 200 and got["kept"] == 120 and got["stop"] == "--max-batches 3"
    status, page2 = call("GET", f"/listings/{job['id']}/products", page=2)
    assert status == 200 and page2["count"] == 120 and page2["total_pages"] == 3 and len(page2["results"]) == 50
    assert page2["results"][0]["product_id"] == "1050" and page2["next"] and page2["previous"]


def test_finished_job_survives_a_restart(jobs, monkeypatch):
    _, job = call("POST", "/listings", query="q", max_batches=3)
    jobs.set()
    wait_status(job["id"], "done")
    monkeypatch.setattr(listing_jobs, "_jobs", {})             # memory gone, files stay
    assert listing_jobs.get(job["id"])["status"] == "done"


def test_no_extension_is_503(jobs, monkeypatch):
    monkeypatch.setattr(listing_jobs, "_bridge", FakeBridge(connected=False))
    status, body = call("POST", "/listings", query="q")
    assert status == 503 and "extension" in body["error"]


def test_bad_params_and_unknown_job(jobs):
    assert call("POST", "/listings")[0] == 400
    assert call("POST", "/listings", query="q", max_batches=999)[0] == 400
    assert call("GET", "/listings/20261101-000000-abcd")[0] == 404
    assert call("GET", "/listings/not-a-job-id")[0] == 404
    assert listing_jobs.get("../../etc") is None and listing_jobs.products("../x", 1) is None
    assert call("GET", "/listings/20261101-000000-abcd/products")[0] == 404


def test_health_reports_the_extension(jobs):
    status, body = call("GET", "/health")
    assert status == 200 and body["extension"] == "connected" and "/listings" in body["endpoints"]
