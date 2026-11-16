---
name: collect-api
description: Collect from Naver Shopping through the running local API with the scripts. Use when writing or running a script that calls the API (search, product details, options, photos, reviews, listings), when a harvest or example_NN script is needed, when an answer's shape changed (naver_types.py, fixtures), or when checking a run against product pages.
---

# Collecting from the API

The stage: scripts call the running local API over HTTP (`NaverApiClient`) and save what it answers. Read the one
section of `scripts/COLLECT.md` the task needs; the scripts table and the boundary: `scripts/README.md`.

| Task | `scripts/COLLECT.md` section |
|---|---|
| Which script to start from | "Examples: start here" |
| Product details: the record or the page (`/products/specs`) | "Product details: two ways" |
| Options: free / paid / sold-out variants | "Product options" |
| Photos (`naver_images.py`, WebP) | "Product photos" |
| The listing screen, "already in the shop" (`listing_filter.py`, `shopify_catalog.py`) | "The listing screen and the shop check" |
| Check a run against product pages | "Checking a run against product pages" |
| Reviews: the endpoint or the page | "Reviews: two ways" |
| The answer types (`naver_types.py`) | "Response types" |
| Which links to harvest | "Link semantics for harvesting" |
| A listing harvest (`harvest_listing.py`), the full listing (`api.listing`) | "Listing harvest", "Full search listing through the API" |
| An error from a call | skill `api-error-triage` |

Commands (repo root, server running for anything networked):
- `.venv/bin/python scripts/example_01_health.py`, then the example closest to the task.
- `.venv/bin/python scripts/harvest_listing.py "<query>" --category <leaf id> --out <name>`.
- `.venv/bin/python -m pytest scripts -q` and `.venv/bin/python -m mypy` (offline).

Rules:
- `scripts/` talks to the server over HTTP only (`NaverApiClient`), never imports server modules (AGENTS.md rule 3).
- Use the typed client methods and guard every `X | None` (R-TYPE in `server/docs/DEVELOPMENT_RULES.md`).
- A shape change updates the type in `naver_types.py`, its fixture and the client method together (R-TYPE).
- Tests never hit the network. Never use browser tools on Naver during a job (`scripts/OWNER_RULES.md` section 3).

More: the contract `server/docs/ENDPOINTS.md`; blocks and 502s `server/docs/KNOWN_ISSUES.md`; a whole category as a
job: skill `run-a-job`; what sellers write: `scripts/SELLER_DATA.md`.
