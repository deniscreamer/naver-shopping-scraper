# AGENTS.md

Local HTTP API over Naver Shopping (fork of omkarcloud/naver-shopping-scraper). Plain-HTTP endpoints use curl_cffi;
store-backend endpoints run inside a real headed Chrome driven by patchright. Human overview: [README.md](README.md).
**New machine? Follow [SETUP.md](SETUP.md) first** (ends with `scripts/check_setup.py --live` = READY; skill `setup-machine`).

## Repo map

```
server/            the API and its import root (bare imports, NO server/__init__.py)
  run.py routes.py config.py cache.py browser_client.py patchright_driver.py ...
  naver_shopping/  endpoint logic, fetch, parsers, schemas, offline tests, fixtures/
  docs/            DEVELOPMENT_RULES.md, ARCHITECTURE.md, ENDPOINTS.md, KNOWN_ISSUES.md
scripts/           HTTP-only consumers of the running API (example_01..15, 99: how to call it; naver_types.py: answer types; shop_types.py: record types)
extension/         Chrome adapter for the owner's browser (search.shopping listing, product page specs, the scroll tab)
archive/docker/    retired Docker/Linux setup, not maintained
pyproject.toml     pytest and mypy config only
```

## Branches

- `develop` is the development branch (cut from `master`, includes the server/ + scripts/ restructure).
- Never push, force-push or rewrite remote branches unless the user asks.

## Platform

macOS is the supported platform: the server runs natively and drives the installed Google Chrome (a real window
opens). Docker/Linux is archived in [archive/docker/](archive/docker/README.md); do not add Docker instructions to the docs.

## Global rules

1. Read the nearest AGENTS.md before editing files in a directory.
2. [server/docs/DEVELOPMENT_RULES.md](server/docs/DEVELOPMENT_RULES.md) is MANDATORY for any change under `server/`.
3. `scripts/` talks to the server over HTTP only and never imports server modules. The only other outside calls
   (each dated at its code): Naver's image CDN (`naver_images.py`), the sellers' description image hosts
   (`description_images.py`), our Shopify store, read (`shopify_catalog.py`, `store_diff.py`) and written only by
   `publish.py` through `shopify_admin.py`, the model APIs (`translate.py`, `describe.py`), ShopNShip's calculator
   by hand, never in the price path (`shopnship_*.py`), the owner's notice webhook (`notify.py`).
4. Tests never hit the network (in scripts/, `scripts/conftest.py` fails a test that tries).
   API answer types live in `scripts/naver_types.py`; a shape change updates type + fixture + client method (R-TYPE).
5. Move or rename tracked files with `git mv` so history follows them.
6. A behaviour change updates its doc in the same commit. A contract change goes in server/docs/ENDPOINTS.md. A new
   upstream fact is a dated comment at the code that handles it, plus one line in the ARCHITECTURE.md "Naver specifics" section.
7. AGENTS.md files stay under ~100 lines and link out instead of copying.

## Commands

Run from the repo root.

```bash
python -m venv .venv
.venv/bin/pip install -r server/requirements.txt -r scripts/requirements.txt
.venv/bin/python server/run.py              # http://localhost:8000, PORT=... to change
.venv/bin/python -m pytest -q               # offline suite, all pass
.venv/bin/python -m pytest scripts -q       # scripts/ client tests, offline, separate suite
.venv/bin/python -m mypy                    # static check of scripts/ ([tool.mypy] in pyproject.toml), 0 errors
scripts/check.sh                            # before a commit: the three above, separate processes, non-zero on a failure
UPDATE_GOLDEN=1 .venv/bin/python -m pytest server/naver_shopping/test_pages.py scripts/test_prepared_golden.py
                                            # after a deliberate parser / transform change: read the diff (R-TEST-5)
```

Live check (server running, uses the network): `curl http://localhost:8000/health`
(unprefixed only), then one call per transport, e.g. `/products/search?query=...`
(HTTP) and `/products/details?product=<smartstore product link>` (Chrome). Every endpoint: skill `live-smoke`.

## Working with products

What waits for the owner (republishing, activating, withdrawing, holding, the Never list):
[scripts/OWNER_RULES.md](scripts/OWNER_RULES.md). Read the skill first; it names its doc sections.

| Request | Skill | First command |
|---|---|---|
| Start / watch a scroll ("Запусти scroll"), a job stopped or printed an error | `run-a-job`, `api-error-triage` | `curl -s localhost:8000/health`; `scripts/job.py status` |
| Review drafts, a section, duplicates | `visual-review` | `scripts/lens.py <lens> <shop> [scope]` |
| Activate, withdraw, hold, restore | `store-actions` | `scripts/job.py activate --job <id> --dry-run` |
| Why is a product missing / held / odd | `product-trace` | `grep <id> scripts/output/shops/<shop>/publish/published.jsonl` |
| Fix a product's brand, title, price, section | `fix-a-product` | `scripts/store_diff.py <shop> --only <key>` |
| Reprice; back up the state | `store-actions`, `price`, `operations` | `scripts/reprice.py <shop>` (a table, sends nothing); `scripts/state_backup.py --dry-run` |
| A dictionary backup due, a term or brand wrong for many products | `dictionaries` | `scripts/translation_dicts.py status` |
| A crash, `LedgerError`, `shop is busy`, a job died, restore a backup | `recover-state` | `scripts/job.py status` |
| A new Mac, nothing starts, the extension disconnected, a listing tab hangs | `setup-machine`, `extension` | `curl -s localhost:8000/health`; `scripts/check_setup.py` |
| A new category or shop | `new-category-or-shop` | [scripts/ONBOARDING.md](scripts/ONBOARDING.md) |

## Changing code

| Topic | Doc, skill |
|---|---|
| Setup, a new requirement (R-SETUP) | [SETUP.md](SETUP.md), [.env.example](.env.example) |
| server/ (rules MANDATORY, read first; skill `server-change`) | [server/AGENTS.md](server/AGENTS.md), [DEVELOPMENT_RULES.md](server/docs/DEVELOPMENT_RULES.md), [ARCHITECTURE.md](server/docs/ARCHITECTURE.md), [ENDPOINTS.md](server/docs/ENDPOINTS.md), [KNOWN_ISSUES.md](server/docs/KNOWN_ISSUES.md), [EXTENSION.md](server/docs/EXTENSION.md) |
| scripts/ stages: collect, job, duplicates, transform, package weight and size, translation, description, placement, price, publication | [scripts/README.md](scripts/README.md) (the docs map: one doc and one skill per stage), [SELLER_DATA.md](scripts/SELLER_DATA.md) |
| Running the scripts, check.sh, shared files, conventions | [scripts/OPERATIONS.md](scripts/OPERATIONS.md), skill `operations` |
| An API or job error: what it means, retry or not, what to tell the owner | skill `api-error-triage`, [ENDPOINTS.md](server/docs/ENDPOINTS.md) "Errors" |
| A seller pattern -> rule -> test; a model prompt (translate, describe); the duplicate rule; the live smoke (R-TEST-4) | skills `seller-pattern-rule`, `prompt-change`, `dedupe-rule`, `live-smoke` |
| A release (no CHANGELOG entries since 0.18.0, the owner 2026-11-14) | `VERSION`, skill `release` |
| Overview, security, extension, archived Docker | [README.md](README.md), [SECURITY.md](SECURITY.md), [extension/README.md](extension/README.md), [archive/docker/](archive/docker/README.md) |

`CLAUDE.md` and `server/CLAUDE.md` contain only `@AGENTS.md`: they load the AGENTS.md next to them and add nothing.
If two docs disagree, DEVELOPMENT_RULES.md wins; fix the other doc in the same commit.
