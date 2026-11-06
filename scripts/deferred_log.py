"""The journal of deferred products, one per shop: append-only JSONL, never edited, never trimmed.

A product is deferred automatically (the owner's rule, 2026-11-05, as in the naver-harvester): its collection came
out partial, it was tried once more, and the retry was partial too. The journal keeps the reason and a snapshot of
the first error. A deferred product is not taken again (listing_filter reason `deferred`) until the owner allows
one retry of that product; the allowance is written to the journal with who gave it, and it is spent by the next
attempt: complete (or not taken) unblocks the product, partial again defers it anew (the owner may allow again). There is no "ignore the journal" switch, and lines are never removed: the journal
is the history of these decisions.

Not deferred, by the same rule: a captcha, a 418 / 429 or a login wall (the whole source stops, no product is
marked), and a card not found on the listing (the product is simply not taken).

Lines: {"event": "deferred", key, reason, first_error, at}, {"event": "retry_allowed", key, by, note, at},
{"event": "retried", key, outcome, at}.

    .venv/bin/python scripts/deferred_log.py list                       # SHOP_STORE's journal
    .venv/bin/python scripts/deferred_log.py allow fairwardgolf:naver:100568453:8450665186 --by owner --note "fixed"
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from shop_stores import get_store

JOURNAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "journal")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DeferredLog:
    def __init__(self, store_id: str, directory: str = JOURNAL_DIR):
        self.path = os.path.join(directory, f"deferred-{store_id}.jsonl")

    def events(self) -> list[dict[str, Any]]:
        out = []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue                 # a line cut off by an interrupted run
        return out

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        event = {**event, "at": _now()}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def state(self) -> dict[str, dict[str, Any]]:
        """key -> {status: deferred | retry_allowed | retried, last deferred event}."""
        out: dict[str, dict[str, Any]] = {}
        for e in self.events():
            key = e.get("key")
            if not key:
                continue
            if e.get("event") == "deferred":
                out[key] = {"status": "deferred", "deferred": e}
            elif key in out and e.get("event") in ("retry_allowed", "retried"):
                out[key]["status"] = e["event"]
        return out

    def blocked(self) -> set[str]:
        """Keys not to take: the last word on them is "deferred" (no allowance given since, or the allowed retry
        came out partial again and deferred it anew). A retry that came out complete or not taken unblocks it."""
        return {k for k, s in self.state().items() if s["status"] == "deferred"}

    def retry_allowed(self, key: str) -> bool:
        return self.state().get(key, {}).get("status") == "retry_allowed"

    def defer(self, key: str, reason: str, first_error: Any) -> dict[str, Any]:
        return self._append({"event": "deferred", "key": key, "reason": reason, "first_error": first_error})

    def allow(self, key: str, by: str, note: str | None = None) -> dict[str, Any]:
        """The owner's one-time retry of one deferred product."""
        status = self.state().get(key, {}).get("status")
        if status != "deferred":
            raise ValueError(f"{key} is not deferred" + (f" (it is {status})" if status else ""))
        if not by.strip():
            raise ValueError("say who allows the retry (--by)")
        return self._append({"event": "retry_allowed", "key": key, "by": by.strip(), "note": note})

    def retried(self, key: str, outcome: str) -> dict[str, Any] | None:
        """Spend an allowance (call when a product with one was attempted)."""
        if self.retry_allowed(key):
            return self._append({"event": "retried", "key": key, "outcome": outcome})
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The deferred products of a shop: list, or allow one retry.")
    parser.add_argument("--store", help="shop id (default: SHOP_STORE, else fairwardgolf)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="deferred products and their state")
    allow = sub.add_parser("allow", help="allow one retry of one deferred product (the owner only)")
    allow.add_argument("key", help="<shop>:naver:<channelNo>:<productId>")
    allow.add_argument("--by", required=True, help="who allows it")
    allow.add_argument("--note", help="why")
    args = parser.parse_args(argv)
    log = DeferredLog(get_store(args.store).id.value)
    if args.command == "list":
        for key, s in sorted(log.state().items()):
            d = s["deferred"]
            print(f"deferred_log: {key}  {s['status']}  {d.get('reason')}  {d.get('at')}")
        print(f"deferred_log: {log.path}")
        return 0
    try:
        log.allow(args.key, args.by, args.note)
    except ValueError as e:
        print(f"deferred_log: {e}")
        return 2
    print(f"deferred_log: one retry allowed for {args.key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
