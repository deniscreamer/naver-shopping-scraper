# AGENTS.md

Local HTTP API over Naver Shopping (fork of omkarcloud/naver-shopping-scraper).
Plain-HTTP endpoints use curl_cffi; store-backend endpoints run inside a real
headed Chrome driven by patchright. Human overview: [README.md](README.md).
**New machine? Follow [SETUP.md](SETUP.md) first** (ends with `scripts/check_setup.py --live` = READY).

## Repo map

```
server/            the API and its import root (bare imports, NO server/__init__.py)
  run.py routes.py config.py cache.py browser_client.py patchright_driver.py ...
  naver_shopping/  endpoint logic, fetch, parsers, schemas, offline tests, fixtures/
  docs/            DEVELOPMENT_RULES.md, ARCHITECTURE.md, ENDPOINTS.md, KNOWN_ISSUES.md
scripts/           HTTP-only consumers of the running API (example_01..12, 99: how to call it; naver_types.py: answer types)
extension/         Chrome adapter for the owner's browser (beta, search.shopping listing)
archive/docker/    retired Docker/Linux setup, not maintained
pyproject.toml     pytest config only (testpaths = pythonpath = ["server"])
```

## Branches

- `develop` is the development branch (cut from `master`, includes the server/ + scripts/ restructure).
- Never push, force-push or rewrite remote branches unless the user asks.

## Platform

macOS is the supported platform: the server runs natively and drives the installed
Google Chrome (a real window opens). Docker/Linux is archived in
[archive/docker/](archive/docker/README.md); do not add Docker instructions to the docs.

## Global rules

1. Read the nearest AGENTS.md before editing files in a directory.
2. [server/docs/DEVELOPMENT_RULES.md](server/docs/DEVELOPMENT_RULES.md) is
   MANDATORY for any change under `server/`.
3. `scripts/` talks to the server over HTTP only and never imports server modules.
4. Tests never hit the network.
   API answer types live in `scripts/naver_types.py`; a shape change updates type + fixture + client method (R-TYPE).
5. Move or rename tracked files with `git mv` so history follows them.
6. A behaviour change updates its doc in the same commit. A contract change goes in
   server/docs/ENDPOINTS.md. A new upstream fact is a dated comment at the code
   that handles it, plus one line in the ARCHITECTURE.md "Naver specifics" section.
7. AGENTS.md files stay under ~100 lines and link out instead of copying.

## Commands

Run from the repo root.

```bash
python -m venv .venv
.venv/bin/pip install -r server/requirements.txt -r scripts/requirements.txt
.venv/bin/python server/run.py              # http://localhost:8000, PORT=... to change
.venv/bin/python -m pytest -q               # offline suite, 158 tests
.venv/bin/python -m pytest scripts -q       # scripts/ client tests, offline, separate suite
```

Live check (server running, uses the network): `curl http://localhost:8000/health`
(unprefixed only), then one call per transport, e.g. `/products/search?query=...`
(HTTP) and `/products/details?product=<smartstore product link>` (Chrome).

## Docs

| Topic | Doc | When to read |
|---|---|---|
| Setup | [SETUP.md](SETUP.md), [.env.example](.env.example) | A new machine; a new requirement (R-SETUP) |
| Overview | [README.md](README.md) | First visit |
| Server pointer | [server/AGENTS.md](server/AGENTS.md) | Before editing under server/ |
| Rules (MANDATORY) | [server/docs/DEVELOPMENT_RULES.md](server/docs/DEVELOPMENT_RULES.md) | Before ANY change under server/ |
| Architecture, Naver specifics | [server/docs/ARCHITECTURE.md](server/docs/ARCHITECTURE.md) | Structural changes, transports, browser, debugging blocks or 502s |
| API contract | [server/docs/ENDPOINTS.md](server/docs/ENDPOINTS.md) | Adding or changing endpoints, writing scripts |
| Known issues | [server/docs/KNOWN_ISSUES.md](server/docs/KNOWN_ISSUES.md) | Before "fixing" anything that looks wrong, before upgrading deps |
| Operations | [server/README.md](server/README.md) | Running on macOS, env vars, tests |
| Consumer scripts, Shopify roadmap | [scripts/README.md](scripts/README.md) | Writing scripts against the API, starting Shopify work |
| Security | [SECURITY.md](SECURITY.md) | Reporting vulnerabilities |
| Releases | [CHANGELOG.md](CHANGELOG.md), `VERSION` | Cutting a release, what changed |
| Extension transport (beta) | [server/docs/EXTENSION.md](server/docs/EXTENSION.md), [extension/README.md](extension/README.md) | search.shopping listing, anything touching extension/ or ext_*.py |
| Archived Docker setup | [archive/docker/README.md](archive/docker/README.md) | Only if Linux deployment comes back |

`CLAUDE.md` and `server/CLAUDE.md` contain only `@AGENTS.md`: they load the AGENTS.md next to them and add nothing.
If two docs disagree, DEVELOPMENT_RULES.md wins; fix the other doc in the same commit.
