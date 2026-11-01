"""Live smoke over HTTP: /health, then one call per endpoint with inputs known
to work, run one after another with a pause in between. NETWORKED: every call
reaches Naver through the running server (and may launch its Chrome), so this
is a manual check, not part of any pytest run. It is also the live check after
a server refactor.

Sequential on purpose: the server keeps one Chrome per proxy and its box calls
serialize on that Chrome's lock, so parallel calls would only queue and raise
the block risk.

    .venv/bin/python server/run.py                       # in another terminal
    .venv/bin/python scripts/smoke_endpoints.py          # NAVER_API_URL or http://localhost:8000
    .venv/bin/python scripts/smoke_endpoints.py --delay 10 --base-url http://localhost:9000
"""
import argparse
import sys
import time

import requests

from naver_api_client import ApiError, NaverApiClient


# ---- inputs known to work --------------------------------------------------------------

PRODUCT = "https://smartstore.naver.com/dailyromantic/products/8087042745"

CALLS: list[tuple[str, dict]] = [
    ("/categories/list", {}),
    ("/products/search", {"query": "raspberry pi", "max_price": 100000}),
    ("/products/count", {"query": "목걸이"}),
    ("/stores/details", {"store": "dailyromantic"}),
    ("/keywords/rank", {"category": "50000002"}),
    ("/keywords/trend", {"keyword": "목걸이", "category": "50000001"}),
    ("/categories/trend", {"category": "50000003"}),
    ("/products/details", {"product": PRODUCT}),
    ("/products/reviews", {"product": PRODUCT}),
    ("/stores/products", {"store": "dailyromantic"}),
    ("/catalogs/reviews", {"catalog": "61626354397"}),
]


# ---- one call --------------------------------------------------------------------------

def summarize(data):
    """A one-line hint of what came back."""
    if not isinstance(data, dict):
        return type(data).__name__
    parts = []
    for key in ("status", "count", "total_count", "current_page", "name", "id"):
        if data.get(key) is not None and not isinstance(data.get(key), (dict, list)):
            parts.append(f"{key}={str(data[key])[:40]}")
    for key in ("results", "children", "endpoints"):
        if isinstance(data.get(key), list):
            parts.append(f"{key}[{len(data[key])}]")
    return " ".join(parts) or "keys=" + ",".join(sorted(data)[:8])


def run_one(api, path, params):
    started = time.time()
    try:
        data = api.get(path, **params)
        status, note = 200, summarize(data)
    except ApiError as e:
        status, note = e.status, (e.error or "")[:160]
    except requests.exceptions.RequestException as e:
        status, note = None, f"{type(e).__name__}: {e}"[:160]
    print(f"smoke: {status or 'ERR'} {time.time() - started:7.1f}s {path} {note}")
    return status == 200


# ---- run -------------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Live smoke of /health and the 11 endpoints (networked).")
    parser.add_argument("--base-url", help="server URL (default: NAVER_API_URL or http://localhost:8000)")
    parser.add_argument("--delay", type=float, default=5, help="seconds to pause between calls (default 5)")
    args = parser.parse_args(argv)

    api = NaverApiClient(base_url=args.base_url)
    print(f"smoke: {api.base_url}")
    calls: list[tuple[str, dict]] = [("/health", {})] + CALLS
    failed = []
    for i, (path, params) in enumerate(calls):
        if i and args.delay > 0:
            time.sleep(args.delay)
        if not run_one(api, path, params):
            failed.append(path)
    print(f"smoke: {len(calls) - len(failed)}/{len(calls)} ok" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
