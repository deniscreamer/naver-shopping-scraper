"""The scripts' tests never reach the network (AGENTS.md rule 4): opening a connection or resolving a name fails the
test. The guard is set when this file is imported, before any test module, so a module-level client is caught too.
No test sends a notice either: `notified` replaces notify.notify for every test (and records the calls)."""
import os
import socket

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
