"""Setup checklist: is this machine ready to work? Fast, read-only, one line per
check: OK / WARN / FAIL. Exit code 1 when anything FAILs.

    .venv/bin/python scripts/check_setup.py              # local + running server + extension
    .venv/bin/python scripts/check_setup.py --live       # + one plain-HTTP call and one Chrome call to Naver
    .venv/bin/python scripts/check_setup.py --notify     # + one test POST to NAVER_NOTIFY_WEBHOOK
    .venv/bin/python scripts/check_setup.py --no-server  # local checks only

A new requirement (an env var, a dependency, a service, a file) gets its
check here in the same commit (SETUP.md "Keep the checklist current").
"""
import argparse
import importlib.metadata
import importlib.util
import os
import socket
import sys

import requests

from naver_api_client import ENV_FILE, ApiError, NaverApiClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app"
BRIDGE_PORT = 8765                       # extension/background.js BRIDGE_URL, server/ext_bridge.py PORT
PACKAGES = ("bottle", "cheroot", "curl_cffi", "marshmallow", "requests", "patchright", "psutil", "websockets",
            "pytest")
PRODUCT = "https://smartstore.naver.com/dailyromantic/products/8087042745"

results: list[str] = []


def report(status, name, detail=""):
    results.append(status)
    print(f"{status:<4}  {name:<34} {detail}")


def masked(value):
    if not value:
        return "(empty)"
    return value if len(value) < 12 else value[:8] + "..." + f"({len(value)} chars)"


# ---- local --------------------------------------------------------------------------------

def check_local():
    ok = sys.version_info >= (3, 11)
    report("OK" if ok else "FAIL", "python >= 3.11", sys.version.split()[0])
    missing = [p for p in PACKAGES if importlib.util.find_spec(p) is None]
    report("FAIL" if missing else "OK", "packages (server/requirements.txt)",
           f"missing: {', '.join(missing)}" if missing else "all installed")
    if "curl_cffi" not in missing:
        version = importlib.metadata.version("curl_cffi")
        report("OK" if version.startswith("0.16") else "WARN", "curl_cffi 0.16.x", version)
    chrome = os.environ.get("PATCHRIGHT_EXECUTABLE") or CHROME
    report("OK" if os.path.exists(chrome) else "FAIL", "Google Chrome installed", chrome)
    report("OK" if os.path.exists(ENV_FILE) else "WARN", ".env", ENV_FILE if os.path.exists(ENV_FILE)
           else "missing: defaults in use (cp .env.example .env)")
    report("OK", "settings", f"PORT={os.environ.get('PORT') or 8000} "
           f"proxy={masked(os.environ.get('NAVER_SHOPPING_PROXY'))} "
           f"webhook={masked(os.environ.get('NAVER_NOTIFY_WEBHOOK'))}")
    report("OK" if os.path.exists(os.path.join(ROOT, "extension", "manifest.json")) else "FAIL",
           "extension/ folder", os.path.join(ROOT, "extension"))


# ---- server -------------------------------------------------------------------------------

def check_server(api, live):
    try:
        health = api.health()
    except Exception as e:
        report("FAIL", "API server reachable", f"{api.base_url}: {type(e).__name__} (start: .venv/bin/python "
               "server/run.py)")
        return
    with open(os.path.join(ROOT, "VERSION")) as f:
        version = f.read().strip()
    report("OK" if health.get("version") == version else "WARN", "API server reachable",
           f"{api.base_url} v{health.get('version')} (repo {version})")
    ext = health.get("extension")
    report("OK" if ext == "connected" else "FAIL", "browser extension connected",
           ext if ext == "connected" else f"{ext}: Chrome open + adapter loaded (extension/README.md)")
    with socket.socket() as s:
        bridge = s.connect_ex(("127.0.0.1", BRIDGE_PORT)) == 0
    report("OK" if bridge else "FAIL", f"bridge port {BRIDGE_PORT}", "listening" if bridge else "nothing listens")
    if not live:
        return
    try:
        count = api.count("골프채", category="50001102")
        report("OK", "Naver over plain HTTP", f"/products/count -> {count['total_count']}")
    except ApiError as e:
        report("FAIL", "Naver over plain HTTP", f"{e.status} {e.error} (418/429/502: this IP is refused)")
    try:
        product = api.product_details(PRODUCT)
        report("OK", "Naver through the server Chrome", f"/products/details -> {(product['name'] or '')[:30]}")
    except ApiError as e:
        report("FAIL", "Naver through the server Chrome", f"{e.status} {e.error}")


def check_notify():
    url = os.environ.get("NAVER_NOTIFY_WEBHOOK")
    if not url:
        report("WARN", "notify webhook", "NAVER_NOTIFY_WEBHOOK empty: macOS notifications only")
        return
    try:
        r = requests.post(url, json={"event": "test", "message": "naver-scrap check_setup", "details": {}},
                          timeout=10)
        report("OK" if r.status_code < 400 else "FAIL", "notify webhook", f"HTTP {r.status_code}")
    except requests.RequestException as e:
        report("FAIL", "notify webhook", f"{type(e).__name__}: {e}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Is this machine ready? (setup checklist)")
    parser.add_argument("--live", action="store_true", help="also call Naver once over HTTP and once via Chrome")
    parser.add_argument("--notify", action="store_true", help="also POST a test notice to NAVER_NOTIFY_WEBHOOK")
    parser.add_argument("--no-server", action="store_true", help="local checks only")
    args = parser.parse_args(argv)
    results.clear()
    check_local()
    if not args.no_server:
        check_server(NaverApiClient(read_timeout=180), args.live)
    if args.notify:
        check_notify()
    fails, warns = results.count("FAIL"), results.count("WARN")
    print(f"\n{'READY' if not fails else 'NOT READY'}: {fails} fail, {warns} warn")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
