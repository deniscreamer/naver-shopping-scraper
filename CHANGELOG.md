# Changelog

Versions follow `VERSION` at the repo root; `/health` reports it. The browser adapter in `extension/` has its own
version in `extension/manifest.json`.

## 0.1.0 (2026-11-01)

First release of this fork (based on [omkarcloud/naver-shopping-scraper](https://github.com/omkarcloud/naver-shopping-scraper)).

- **Structure**: the API server lives in `server/` (import root), HTTP-only consumers in `scripts/`, docs in
  `server/docs/` with a binding rulebook (`DEVELOPMENT_RULES.md`); root `README.md` / `AGENTS.md` index everything.
  Docker moved to `archive/docker/`; macOS is the supported platform.
- **Fix**: the search category filter works at any category depth (`categoryIds` = depth + id; was a fixed `03`).
- **Listing (beta)**: `POST /listings` reads the whole search.shopping listing for a query through the owner's own
  Chrome with the adapter extension (`extension/` 0.4.2, `server/docs/EXTENSION.md`); `GET /listings/<id>` and
  `/listings/<id>/products` report and page the rows. Captchas are notified and waited for, bans stop the job.
- **Scripts**: `NaverApiClient` (`get`, `pages`, `listing`, `health`), runnable examples `example_01..07`,
  `harvest_listing.py` (widget listing past 96 cards by price slices), `smoke_endpoints.py`.
- **Tests**: 129 server + 42 scripts offline tests.
