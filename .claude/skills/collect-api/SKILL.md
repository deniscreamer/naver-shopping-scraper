---
name: collect-api
description: Collect from Naver Shopping through the running local API with the scripts. Use when writing or running a script that calls the API (search, product details, options, photos, reviews, listings), when a harvest or example_NN script is needed, when an answer's shape changed (naver_types.py, fixtures), or when checking a run against product pages.
---

# Collecting from the API

Read `scripts/COLLECT.md` first; this skill is only the map. The scripts table and the boundary: `scripts/README.md`.

What the doc covers:
- product details two ways, options (free / paid / sold-out variants), photos (`naver_images.py`, WebP);
- the listing screen and the "already in the shop" check (`listing_filter.py`, `shopify_catalog.py`);
- checking a run against product pages, reviews two ways, the examples (start there);
- the answer types (`naver_types.py`), link semantics, listing harvests (`harvest_listing.py`, `api.listing`).

Commands (repo root, server running for anything networked):
- `.venv/bin/python scripts/example_01_health.py`, then the example closest to the task.
- `.venv/bin/python scripts/harvest_listing.py "<query>" --category <leaf id> --out <name>`.
- `.venv/bin/python -m pytest scripts -q` and `.venv/bin/python -m mypy` (offline).

Rules:
- `scripts/` talks to the server over HTTP only (`NaverApiClient`), never imports server modules (AGENTS.md rule 3).
- Use the typed client methods and guard every `X | None` (R-TYPE in `server/docs/DEVELOPMENT_RULES.md`).
- A shape change updates the type in `naver_types.py`, its fixture and the client method together (R-TYPE).
- Tests never hit the network.

More: the contract `server/docs/ENDPOINTS.md`; blocks and 502s `server/docs/KNOWN_ISSUES.md`; a whole category as a
job: skill `run-a-job`; what sellers write: `scripts/SELLER_DATA.md`.
