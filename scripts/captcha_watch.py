"""Watch for a Naver captcha the adapter is waiting on, and say so: one line per event. Independent of any
collection: the collection only waits (NAVER_CAPTCHA_WAIT_S) and goes on by itself once the page shows no captcha;
this watcher only reads GET /captcha and reports, so a human (at the Mac, or from a phone through a remote-desktop
app) or an agent relaying to the owner's chat knows at once. It never types into the captcha (R-EXT-3).

    .venv/bin/python scripts/captcha_watch.py            # until Ctrl-C
    .venv/bin/python scripts/captcha_watch.py --once     # print the current state and exit

Lines:  captcha_watch: CAPTCHA #<attempt> at <step>: <question> | screenshot <path> | answer within <n> s
        captcha_watch: solved at <step> after <n> s     /  timed out ...  /  blocked ...
"""
import argparse
import sys
import time
from collections.abc import Mapping
from typing import Any

from naver_api_client import ApiError, NaverApiClient

POLL = 3.0                       # seconds between reads of /captcha


def event(state: Mapping[str, Any]) -> str | None:
    """The line for a state, or None when there is nothing to say."""
    status = state.get("status")
    if status == "waiting":
        return (f"CAPTCHA #{state.get('attempt')} at {state.get('step')}: {state.get('question') or '(no question text)'}"
                f" | screenshot {state.get('screenshot')} | answer within {state.get('wait_s')} s")
    if status in ("solved", "timed_out", "blocked"):
        word = {"solved": "solved", "timed_out": "timed out", "blocked": "blocked (a ban page) "}[status]
        return f"{word} at {state.get('step')} after {state.get('after_s')} s"
    return None


def watch(api: NaverApiClient, once: bool = False, sleep=time.sleep, out=print) -> None:
    last = None
    while True:
        try:
            state = api.captcha()
        except (ApiError, OSError) as e:
            out(f"captcha_watch: the server does not answer: {e}")
            state = None
        mark = state and (state.get("status"), state.get("attempt"), state.get("at"))
        if state and mark != last:
            line = event(state)
            if line and (last is not None or state.get("status") == "waiting" or once):
                out(f"captcha_watch: {line}")
            last = mark
        if once:
            return
        sleep(POLL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report Naver captchas the adapter waits on.")
    parser.add_argument("--once", action="store_true", help="print the current state and exit")
    args = parser.parse_args(argv)
    try:
        watch(NaverApiClient(), once=args.once)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
