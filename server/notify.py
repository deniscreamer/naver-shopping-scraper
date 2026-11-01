"""Tell the owner something needs a human (a captcha) or a run stopped, with
no Claude session in the loop. BETA (2026-11-01).

    NAVER_NOTIFY_WEBHOOK  URL that gets a JSON POST {event, message, details,
                          at}; any webhook receiver (Slack/Telegram bridge,
                          n8n, your own endpoint). Unset: a macOS notification
                          (osascript) on this machine, else just the console.

Never raises: a failed notification must not stop a harvest.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def notify(event, message, **details):
    payload = {"event": event, "message": message, "details": details,
               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    print(f"notify: [{event}] {message} {json.dumps(details, ensure_ascii=False)[:300]}", flush=True)
    url = os.environ.get("NAVER_NOTIFY_WEBHOOK")
    if url:
        try:
            import requests
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"notify: webhook failed: {type(e).__name__}: {e}", flush=True)
        return
    if sys.platform == "darwin":
        script = f"display notification {json.dumps(message)} with title {json.dumps('naver-scrap: ' + event)}"
        try:
            subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
        except Exception:
            pass
