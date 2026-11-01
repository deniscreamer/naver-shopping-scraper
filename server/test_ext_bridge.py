"""Offline tests for ext_bridge: the call round trip with a fake extension,
error answers, and the origin gate. Local sockets only, no Chrome, no network.

    python -m pytest server/test_ext_bridge.py -q
"""
import json
import socket
import threading

import pytest

pytest.importorskip("websockets")
from websockets.exceptions import InvalidStatus  # noqa: E402
from websockets.sync.client import connect  # noqa: E402

from ext_bridge import ExtBridge, ExtError  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def bridge():
    b = ExtBridge(port=free_port()).start()
    yield b
    b.stop()


def fake_extension(bridge, answers):
    """Connects like the extension and answers each op from `answers`."""
    ws = connect(f"ws://127.0.0.1:{bridge.port}", origin="chrome-extension://testid")
    ws.send(json.dumps({"hello": {"version": "test"}}))

    def serve():
        try:
            for raw in ws:
                msg = json.loads(raw)
                result = answers[msg["op"]](msg["args"])
                ws.send(json.dumps({"id": msg["id"], **result}))
        except Exception:
            pass
    threading.Thread(target=serve, daemon=True).start()
    return ws


def test_call_round_trip(bridge):
    ws = fake_extension(bridge, {"tab_open": lambda a: {"ok": True, "result": {"tabId": 7, "url": a["url"]}}})
    assert bridge.wait_connected(5) and bridge.version == "test"
    assert bridge.call("tab_open", url="https://www.naver.com/") == {"tabId": 7, "url": "https://www.naver.com/"}
    ws.close()


def test_error_answer_raises(bridge):
    ws = fake_extension(bridge, {"click": lambda a: {"ok": False, "error": "no visible element"}})
    bridge.wait_connected(5)
    with pytest.raises(ExtError, match="no visible element"):
        bridge.call("click", tabId=1, selector="#x")
    ws.close()


def test_no_answer_times_out(bridge):
    ws = fake_extension(bridge, {})                 # KeyError in the fake: never answers
    bridge.wait_connected(5)
    with pytest.raises(ExtError, match="no answer"):
        bridge.call("page", timeout=0.5, tabId=1)
    ws.close()


def test_not_connected_raises(bridge):
    with pytest.raises(ExtError, match="not connected"):
        bridge.call("tabs")


def test_web_origin_is_refused(bridge):
    with pytest.raises(InvalidStatus):
        connect(f"ws://127.0.0.1:{bridge.port}", origin="https://evil.example")


def test_stop_closes_the_extension_connection():
    b = ExtBridge(port=free_port()).start()
    fake_extension(b, {})
    assert b.wait_connected(5)
    b.stop()
    for _ in range(50):                       # the handler thread sees the close and lets go
        if not b.wait_connected(0):
            break
        threading.Event().wait(0.05)
    assert not b.wait_connected(0)
