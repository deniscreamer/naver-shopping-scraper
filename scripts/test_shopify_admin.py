"""Offline tests for shopify_admin.py's batched uploads: a fake GraphQL and a fake staging bucket, no network.

    .venv/bin/python -m pytest scripts/test_shopify_admin.py -q
"""
import threading

import pytest

import shopify_admin as SA


class Bucket:
    """The staging bucket: answers per file name in order (default 204); records every upload."""

    def __init__(self, answers=None):
        self.answers, self.calls, self.lock = dict(answers or {}), [], threading.Lock()

    def post(self, url, data, files, timeout, allow_redirects):
        name = files["file"][0]
        with self.lock:
            self.calls.append(name)
            queue = self.answers.get(name) or []
            status = queue.pop(0) if queue else 204
        if isinstance(status, Exception):
            raise status
        return type("R", (), {"status_code": status})()


class FakeGraphQL:
    """stagedUploadsCreate / fileCreate / nodes / files answers; records each call's kind and size."""

    def __init__(self, existing=(), polls_until_ready=1):
        self.existing, self.calls, self.polls = set(existing), [], {}
        self.until = polls_until_ready

    def __call__(self, query, variables=None, token=None):
        v = variables or {}
        if "stagedUploadsCreate" in query:
            self.calls.append(("stage", len(v["input"])))
            return {"stagedUploadsCreate": {"userErrors": [], "stagedTargets": [
                {"url": "https://bucket", "resourceUrl": f"staged:{i['filename']}", "parameters": []}
                for i in v["input"]]}}
        if "fileCreate" in query:
            self.calls.append(("create", len(v["files"])))
            return {"fileCreate": {"userErrors": [], "files": [{"id": f"gid:{f['filename']}"} for f in v["files"]]}}
        if "nodes(ids" in query:
            self.calls.append(("poll", len(v["ids"])))
            out = []
            for i in v["ids"]:
                self.polls[i] = self.polls.get(i, 0) + 1
                ready = self.polls[i] >= self.until
                out.append({"id": i, "fileStatus": "READY" if ready else "PROCESSING",
                            "image": {"url": f"https://cdn/{i[4:]}?v=1"} if ready else None})
            return {"nodes": out}
        if "files(first" in query:
            self.calls.append(("find", v["q"].count("filename:")))
            names = [part.split(":", 1)[1].rstrip("*") for part in v["q"].split(" OR ")]
            return {"files": {"nodes": [{"fileStatus": "READY", "image": {"url": f"https://cdn/{n}.webp?v=1"}}
                                        for n in names if n in self.existing]}}
        raise AssertionError(query)


def files_admin(graphql, bucket):
    f = SA.FilesAdmin.__new__(SA.FilesAdmin)        # no credentials: the transport is faked
    f._post, f._upload, f._sleep = graphql, bucket, (lambda s: None)
    return f


@pytest.fixture
def photos(tmp_path):
    out = []
    for i in range(12):
        p = tmp_path / f"r{i}.webp"
        p.write_bytes(b"x" * (i + 1))
        out.append((str(p), f"r{i}.webp", True))
    return out


def test_many_files_in_few_graphql_calls(photos, monkeypatch):
    monkeypatch.setattr(SA, "BATCH", 5)
    graphql, bucket = FakeGraphQL(existing={"r0", "r1"}, polls_until_ready=2), Bucket()
    out = files_admin(graphql, bucket).create_many(photos)
    assert out == {f"r{i}.webp": (f"https://cdn/r{i}.webp" if i < 2 else f"https://cdn/r{i}.webp") for i in range(12)}
    assert sorted(bucket.calls) == sorted(f"r{i}.webp" for i in range(2, 12))     # found ones not uploaded again
    kinds = [k for k, _ in graphql.calls]
    assert kinds.count("find") == 2 and kinds.count("stage") == 2 and kinds.count("create") == 2   # 10 new, 5 a batch
    assert kinds.count("poll") == 4                                     # two polls a batch, all its files at once


def test_a_throttled_or_failing_upload_is_repeated(photos):
    bucket = Bucket({"r3.webp": [503, 429], "r4.webp": [SA.requests.ConnectionError()]})
    out = files_admin(FakeGraphQL(), bucket).create_many(photos[:6])
    assert len(out) == 6 and bucket.calls.count("r3.webp") == 3 and bucket.calls.count("r4.webp") == 2


def test_a_refused_upload_stops_with_the_files_name(photos):
    with pytest.raises(SA.AdminError, match="r2.webp: HTTP 403"):
        files_admin(FakeGraphQL(), Bucket({"r2.webp": [403]})).create_many(photos[:4])
    with pytest.raises(SA.AdminError, match="r1.webp: failed"):
        files_admin(FakeGraphQL(), Bucket({"r1.webp": [503] * SA.RETRIES})).create_many(photos[:2])


def test_a_failed_file_is_named():
    class Failing(FakeGraphQL):
        def __call__(self, query, variables=None, token=None):
            if "nodes(ids" in query:
                return {"nodes": [{"id": i, "fileStatus": "FAILED"} for i in variables["ids"]]}
            return super().__call__(query, variables, token)
    f = files_admin(Failing(), Bucket())
    with pytest.raises(SA.AdminError, match="fileCreate r0.webp: FAILED"):
        f._ready({"gid:r0.webp": "r0.webp"})


def test_stage_many_keeps_the_order(photos):
    p = SA.ProductsAdmin.__new__(SA.ProductsAdmin)
    p._post, p._upload, p._sleep = FakeGraphQL(), Bucket(), (lambda s: None)
    out = p.stage_many([(path, "IMAGE", None) for path, _, _ in photos])
    assert out == [f"staged:r{i}.webp" for i in range(12)]
