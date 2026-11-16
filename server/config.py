"""Configuration for the Naver Shopping Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                  port the API listens on (default 8000)
    API_HOST              address the API listens on (default 127.0.0.1: this
                          machine only; 0.0.0.0 = every interface, as before
                          2026-11-15)
    NAVER_SHOPPING_PROXY  proxy URL, e.g. http://user:pass@host:port (default:
                          none — your own IP). Used for every request: the
                          plain-HTTP calls (search, store pages, DataLab) and
                          the Chrome window that serves product details,
                          reviews, store product lists and catalog reviews.
                          Naver answers most connections directly, so you
                          very likely don't need it. Set it only if Naver
                          starts refusing your IP (HTTP 418 / 429 errors);
                          a STICKY proxy keeps one exit for Chrome's life.

Values can also sit in a `.env` file at the repo root (KEY=value lines, see
/.env.example); it is read once here at import and never overrides a variable
already set in the environment. Everything else below is a plain constant
with a working default — edit it here if you need to.
"""
import os

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def load_env_file(path=ENV_FILE):
    """KEY=value lines of `path` into os.environ (no override, # comments,
    optional quotes). No dependency: python-dotenv is not needed for this."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip().removeprefix("export ").strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if key and value and key not in os.environ:
                os.environ[key] = value


load_env_file()

PORT = int(os.environ.get("PORT", "8000"))

# The listen address. 127.0.0.1 by default (2026-11-15): the routes have no auth and drive a Chrome that may be
# logged in, and every client (scripts/naver_api_client.py, the extension's bridge on its own port) is on this
# machine. API_HOST=0.0.0.0 restores the old bind on every interface.
# the variable is API_HOST, not HOST: zsh keeps the machine's name in $HOST (an `export HOST` would bind it)
DEFAULT_HOST = "127.0.0.1"


def listen_host(env=None):
    """The address run.main binds: $API_HOST, else DEFAULT_HOST."""
    return ((os.environ if env is None else env).get("API_HOST") or "").strip() or DEFAULT_HOST


HOST = listen_host()

# The release version, from /VERSION at the repo root (shown by /health).
_VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")
VERSION = open(_VERSION_FILE).read().strip() if os.path.exists(_VERSION_FILE) else "dev"

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

NAVER_SHOPPING_PROXY = os.environ.get("NAVER_SHOPPING_PROXY") or None

# Seconds the adapter waits for a human to answer a captcha in the owner's Chrome (at the Mac, or from a phone
# through a remote-desktop app) before it stops the job.
NAVER_CAPTCHA_WAIT_S = int(os.environ.get("NAVER_CAPTCHA_WAIT_S") or 600)

# Chromes kept open for the product / review / store-list calls (one per
# proxy; one is plenty).
NAVER_SHOPPING_BROWSER_SLOTS = 1
# Attempts per call when Naver refuses the browser (each one relaunches
# Chrome; with one fixed exit, retrying rarely helps, so keep it low).
NAVER_SHOPPING_BOX_ATTEMPTS = 2


def naver_shopping_proxy():
    """The exit for the plain-HTTP calls (None = your own IP)."""
    return os.environ.get("NAVER_SHOPPING_PROXY") or None


def naver_shopping_browser_proxy():
    """The exit Chrome uses (None = your own IP)."""
    return os.environ.get("NAVER_SHOPPING_PROXY") or None


def exit_geo(proxy, timeout=12):
    """Geo of a proxy's exit IP, looked up THROUGH the proxy (ip-api.com).
    Returns {countryCode, regionName, city, timezone, query} or None on any
    failure — Chrome then keeps the clock of the proxy's country tag, else
    this machine's."""
    try:
        import requests
        r = requests.get("http://ip-api.com/json/?fields=status,countryCode,regionName,city,timezone,query",
                         proxies={"http": proxy, "https": proxy}, timeout=timeout)
        d = r.json()
        if d.get("status") == "success" and d.get("timezone"):
            return d
    except Exception:
        pass
    return None
