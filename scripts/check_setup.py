"""Setup checklist: is this machine ready to work? Fast, read-only, one line per
check: OK / WARN / FAIL. Exit code 1 when anything FAILs.

    .venv/bin/python scripts/check_setup.py              # local + running server + extension
    .venv/bin/python scripts/check_setup.py --live       # + one plain-HTTP call and one Chrome call to Naver,
                                                         #   and a Shopify token for a read-only shop check
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
           f"webhook={masked(os.environ.get('NAVER_NOTIFY_WEBHOOK'))} "
           f"captcha_wait={os.environ.get('NAVER_CAPTCHA_WAIT_S') or 600}s")
    check_photos()
    report("OK" if os.path.exists(os.path.join(ROOT, "extension", "manifest.json")) else "FAIL",
           "extension/ folder", os.path.join(ROOT, "extension"))


def check_ocr():
    """scripts/requirements.txt: rapidocr + onnxruntime and the Korean models (description_images.py, optional:
    a WARN, the rest works without it). The models are downloaded once, by the first run of the stage."""
    missing = [p for p in ("rapidocr", "onnxruntime") if importlib.util.find_spec(p) is None]
    if missing:
        report("WARN", "OCR (description_images.py)", f"missing: {', '.join(missing)}: pip install -r "
               "scripts/requirements.txt")
        return
    spec = importlib.util.find_spec("rapidocr")
    models = os.path.join(os.path.dirname((spec and spec.origin) or ""), "models")
    need = ("ch_PP-OCRv5_det_mobile.onnx", "korean_PP-OCRv5_rec_mobile.onnx")
    absent = [m for m in need if not os.path.isfile(os.path.join(models, m))]
    report("WARN" if absent else "OK", "OCR (description_images.py)",
           f"rapidocr {importlib.metadata.version('rapidocr')}" + (
               f"; models not downloaded yet ({', '.join(absent)}): the stage's first run fetches them"
               if absent else ", Korean models present"))


def check_translation():
    """translate.py: the anthropic and openai packages and the key file (TRANSLATE_KEY_FILE: 0600, ignored by git). A
    WARN only: --offline and the other scripts work without it. The keys are read to check they are there, never
    printed; no call."""
    missing = [p for p in ("anthropic", "openai") if importlib.util.find_spec(p) is None]
    if missing:
        report("WARN", "translation (translate.py)", f"missing: {', '.join(missing)}: pip install -r "
               "scripts/requirements.txt")
        return
    from translate import TranslateError, build_chain, keys_from_env
    from translate_keys import looks_right
    try:
        keys = keys_from_env()
        wrong = looks_right(keys)
        chain = " -> ".join(m.name for m in build_chain(keys).models)
        report("WARN" if wrong or len(keys) < 2 else "OK", "translation (translate.py)",
               f"chain {chain}" + (f"; check {', '.join(wrong)}" if wrong else "")
               + ("" if len(keys) == 2 else f"; only {', '.join(keys)}: no fallback"))
    except TranslateError as e:
        report("WARN", "translation (translate.py)", str(e))


def check_photos():
    """scripts/requirements.txt: Pillow with WebP (image_prep.py) and a known SHOP_STORE (shop_stores.py)."""
    try:
        from PIL import features
        webp = features.check("webp")
        detail = importlib.metadata.version("Pillow") if webp else "no WebP in Pillow: reinstall scripts/requirements.txt"
        report("OK" if webp else "FAIL", "Pillow with WebP (photo scripts)", detail)
    except ImportError:
        report("FAIL", "Pillow with WebP (photo scripts)", "missing: pip install -r scripts/requirements.txt")
    check_ocr()
    check_translation()
    report("OK" if importlib.util.find_spec("tenacity") else "FAIL", "tenacity (job.py network retries)",
           importlib.metadata.version("tenacity") if importlib.util.find_spec("tenacity")
           else "missing: pip install -r scripts/requirements.txt")
    from shop_stores import get_store
    try:
        store = get_store()
        report("OK", "SHOP_STORE", f"{store.id.value} ({store.publisher}, {store.site})")
    except ValueError as e:
        report("FAIL", "SHOP_STORE", str(e))


def check_shop(live):
    """The shop check of example_99 (shopify_catalog.py): the store's Shopify values and its credentials file (0600,
    ignored by git); with --live a token is minted and checked (shop, read_products, a first product). A WARN only:
    the other scripts do not need it."""
    from shop_stores import get_store
    from shopify_catalog import CatalogError, ShopCatalog, ShopNotConfigured
    try:
        store = get_store()
    except ValueError:
        return                                   # SHOP_STORE already failed above
    try:
        catalog = ShopCatalog(store)
        if live:
            catalog.check_shop()                 # mints and verifies the token first
        report("OK", "Shopify shop check", catalog.shop.domain + (": token minted, read_products, products readable"
                                                                  if live else " (credentials file found)"))
    except (ShopNotConfigured, CatalogError) as e:
        report("WARN", "Shopify shop check", f"{e} (only example_99 needs it)")
        return
    # publication (publish.py, job.py new --publish): the two writing apps of the same credentials file
    from shopify_admin import FilesAdmin, ProductsAdmin
    for name, client in (("products app, write_products", ProductsAdmin), ("files app, write_files", FilesAdmin)):
        try:
            admin = client(store)
            if live:
                admin.check_shop()               # mints the app's token and checks its scope
            report("OK", f"Shopify publication ({name})", "token minted, scope granted" if live
                   else f"{', '.join(client.NAMES)} found")
        except (ShopNotConfigured, CatalogError) as e:
            report("WARN", f"Shopify publication ({name})", f"{e} (only publish.py / job.py --publish need it)")


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
    check_shop(args.live)
    if not args.no_server:
        check_server(NaverApiClient(read_timeout=180), args.live)
    if args.notify:
        check_notify()
    fails, warns = results.count("FAIL"), results.count("WARN")
    print(f"\n{'READY' if not fails else 'NOT READY'}: {fails} fail, {warns} warn")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
