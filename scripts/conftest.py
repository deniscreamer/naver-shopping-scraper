"""The scripts' tests never reach the network (AGENTS.md rule 4): opening a connection or resolving a name fails the
test. The guard is set when this file is imported, before any test module, so a module-level client is caught too.
No test sends a notice either: `notified` replaces notify.notify for every test (and records the calls).
`shop_fixture`: a tmp copy of the real-data shop fixture (fixtures/shop/, make_shop_fixture.py)."""
import json
import os
import shutil
import socket
from types import SimpleNamespace

import pytest


def _refuse(*args, **kwargs):
    raise AssertionError("a test tried to reach the network")


for _name in ("connect", "connect_ex"):
    setattr(socket.socket, _name, _refuse)
socket.create_connection = _refuse
socket.getaddrinfo = _refuse


class Notified(list):
    """The notices a test's code sent (event, message, details); `real` is scripts/notify.py's own function."""
    real = None


@pytest.fixture(autouse=True)
def notified(monkeypatch):
    """No test reaches osascript or the webhook (2026-11-16: job.main() tells the owner how a run ended)."""
    import notify
    assert os.path.dirname(os.path.abspath(notify.__file__)) == os.path.dirname(os.path.abspath(__file__))
    calls = Notified()
    calls.real = notify.notify
    monkeypatch.setattr(notify, "notify", lambda event, message, **details: calls.append((event, message, details)))
    return calls


@pytest.fixture
def shop_fixture(tmp_path):
    """A copy of fixtures/shop/ (16 real products of fairwardgolf and two of its jobs, make_shop_fixture.py) in
    tmp_path, its jobs' shops_root set to the copy: .shops (shops root), .jobs (jobs root), .shop, .cases
    ({key: case}), .jobs_ids, .key(pid) -> the case's key. Write freely: the fixture in git is never touched."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "shop")
    dst = tmp_path / "shop_fixture"
    shutil.copytree(src, dst)
    with open(dst / "cases.json", encoding="utf-8") as f:
        meta = json.load(f)
    for job in meta["jobs"]:
        path = dst / "jobs" / job / "job.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"<fixture>"', json.dumps(str(dst / "shops"))),
                        encoding="utf-8")
    cases = meta["cases"]
    return SimpleNamespace(shops=str(dst / "shops"), jobs=str(dst / "jobs"), shop=meta["shop"], cases=cases,
                           jobs_ids=list(meta["jobs"]), root=str(dst),
                           key=lambda pid: next(k for k in cases if k.endswith(":" + pid)))
