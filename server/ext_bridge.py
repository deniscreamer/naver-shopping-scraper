"""Bridge to the owner's own Chrome through the adapter extension (extension/).
BETA (2026-11-01): not wired into the API yet.

Why: search.shopping.naver.com answers our patchright Chrome with a captcha
and then a network-wide 418 ban page ("쇼핑 서비스 접속이 일시적으로 제한"),
while the owner's everyday Chrome browses it. Its page builds the
x-wtm-ncaptcha-token / x-nstore-* headers and cursors itself, so we drive
that Chrome like a person and only READ the answers its page gets.

The extension is a dumb executor: it connects to ws://127.0.0.1:PORT, takes
{id, op, args} and answers {id, ok, result | error}. Every decision (which
page, what to click, when to stop) is made here in Python. Ops are listed in
extension/background.js (OPS).

Safety: listens on 127.0.0.1 only and accepts a handshake only from a
chrome-extension:// origin (a web page cannot open it). One extension
connection at a time; a new one replaces the old.

    bridge = ExtBridge().start()
    bridge.wait_connected(120)
    tab = bridge.call("tab_open", url="https://www.naver.com/")["tabId"]
"""
import itertools
import json
import threading

PORT = 8765
CALL_TIMEOUT = 90           # seconds for one op (typing a long query, a slow load)


class ExtError(Exception):
    """The extension answered ok=false, or did not answer in time."""


class ExtBridge:
    def __init__(self, host="127.0.0.1", port=PORT):
        self.host, self.port = host, port
        self._conn = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending = {}              # id -> [threading.Event, answer]
        self._connected = threading.Event()
        self.version = None
        self._server = None

    # ---- server -------------------------------------------------------------------

    def start(self):
        from websockets.sync.server import serve

        def only_extensions(connection, request):
            origin = request.headers.get("Origin") or ""
            if not origin.startswith("chrome-extension://"):
                return connection.respond(403, "extension origins only\n")
            return None

        self._server = serve(self._handler, self.host, self.port, process_request=only_extensions,
                             ping_interval=None, max_size=32 * 1024 * 1024)
        threading.Thread(target=self._server.serve_forever, daemon=True, name="ext-bridge").start()
        print(f"ext-bridge: listening on ws://{self.host}:{self.port}")
        return self

    def stop(self):
        """Close the extension's connection too: its handler thread is not a
        daemon, so an open connection would keep the process alive on Ctrl+C."""
        with self._lock:
            conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        if self._server is not None:
            self._server.shutdown()

    def _handler(self, conn):
        with self._lock:
            self._conn = conn
        try:
            for raw in conn:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if "hello" in msg:
                    self.version = (msg["hello"] or {}).get("version")
                    self._connected.set()
                    print(f"ext-bridge: extension connected (v{self.version})")
                elif "id" in msg:
                    slot = self._pending.get(msg["id"])
                    if slot is not None:
                        slot[1] = msg
                        slot[0].set()
        finally:
            with self._lock:
                if self._conn is conn:
                    self._conn = None
                    self._connected.clear()
                    print("ext-bridge: extension disconnected")

    # ---- calls --------------------------------------------------------------------

    def wait_connected(self, timeout=None):
        return self._connected.wait(timeout)

    def call(self, op, timeout=CALL_TIMEOUT, **args):
        """One op in the extension -> its result; ExtError on ok=false / timeout."""
        with self._lock:
            conn = self._conn
        if conn is None:
            raise ExtError("the extension is not connected (is Chrome open with the adapter loaded?)")
        mid = next(self._ids)
        slot = self._pending[mid] = [threading.Event(), None]
        try:
            conn.send(json.dumps({"id": mid, "op": op, "args": args}, ensure_ascii=False))
            if not slot[0].wait(timeout):
                raise ExtError(f"{op}: no answer in {timeout}s")
            answer = slot[1]
        finally:
            self._pending.pop(mid, None)
        if not answer.get("ok"):
            raise ExtError(f"{op}: {answer.get('error')}")
        return answer.get("result")
