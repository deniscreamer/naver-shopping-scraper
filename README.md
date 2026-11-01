# Naver Shopping API (local)

A local HTTP API over Naver Shopping, forked from
[omkarcloud/naver-shopping-scraper](https://github.com/omkarcloud/naver-shopping-scraper).
Search, product counts, store profiles and the DataLab insights are fetched over
plain HTTP. Product details, product reviews, store product lists and catalog
reviews come from Naver's store backend, which answers only inside a real browser
page, so the server drives a real headed Google Chrome for those calls. The first
browser call opens a Chrome window; later calls reuse it, and it is relaunched if
Naver refuses it. The supported platform is macOS.

## Quick start

Requires macOS, Python 3 and Google Chrome installed in /Applications. macOS
details (the Chrome window, timings, profiles): [server/README.md](server/README.md#macos).

```bash
python -m venv .venv
.venv/bin/pip install -r server/requirements.txt -r scripts/requirements.txt
.venv/bin/python server/run.py            # http://localhost:8000 (PORT=9000 to change)
```

```bash
curl "http://localhost:8000/health"
curl "http://localhost:8000/products/search?query=raspberry%20pi"
```

If Naver starts refusing your IP (HTTP 418/429), restart with a proxy:
`NAVER_SHOPPING_PROXY="http://user:pass@host:port" .venv/bin/python server/run.py`.

Offline tests (no network, no Chrome):

```bash
.venv/bin/python -m pytest -q             # 106 passed
.venv/bin/python -m pytest scripts -q     # scripts/ client tests, separate suite
```

## Endpoints

Every endpoint is served at `/path` and at `/naver-shopping/path`. `/` and
`/health` exist only unprefixed. Parameters, limits and response shapes:
[server/docs/ENDPOINTS.md](server/docs/ENDPOINTS.md).

| Path | Needs Chrome | Returns |
|---|---|---|
| `/products/details` | yes | Price, options with stock, description, specs, review stats |
| `/products/search` | no | Up to 96 products per keyword, with filters |
| `/products/count` | no | Number of products matching a keyword and filters |
| `/products/reviews` | yes | One page of a product's reviews (paginated) |
| `/stores/details` | no | Store profile |
| `/stores/products` | yes | A store's popular products or best-sellers |
| `/catalogs/reviews` | yes | Review sample of a price-comparison catalog |
| `/keywords/rank` | no | Top trending keywords of a category (paginated) |
| `/keywords/trend` | no | A keyword's click trend (DataLab) |
| `/categories/trend` | no | A category's click trend with device, gender and age split |
| `/categories/list` | no | Child categories of a parent category (0 or omitted = top level), with their IDs |

## Repository layout

```
server/             the API; import root (bare imports, no __init__.py)
  run.py            entry point (bottle + cheroot)
  routes.py         HTTP routes and error mapping
  naver_shopping/   endpoint logic, fetchers, parsers, schemas, offline tests + fixtures
  docs/             rules, architecture, endpoint contract, known issues
scripts/            HTTP-only consumers of the running API (never import server code)
pyproject.toml      pytest config only (testpaths/pythonpath = server)
archive/docker/     retired Docker/Linux setup (not maintained)
```

## Documentation

| Doc | Contents |
|---|---|
| [AGENTS.md](AGENTS.md) | Rules and map for coding agents |
| [server/README.md](server/README.md) | Running on macOS, environment variables, tests |
| [server/docs/ENDPOINTS.md](server/docs/ENDPOINTS.md) | HTTP contract |
| [server/docs/ARCHITECTURE.md](server/docs/ARCHITECTURE.md) | How requests flow, transports, browser, cache |
| [server/docs/DEVELOPMENT_RULES.md](server/docs/DEVELOPMENT_RULES.md) | Mandatory rules for changes under server/ |
| [server/docs/KNOWN_ISSUES.md](server/docs/KNOWN_ISSUES.md) | Known defects and stale references |
| [scripts/README.md](scripts/README.md) | Writing scripts against the API, Shopify roadmap |
| [SECURITY.md](SECURITY.md) | Usage disclaimer and vulnerability reporting |
| [archive/docker/README.md](archive/docker/README.md) | Retired Docker setup and how to restore it |

## Credits and license

Based on [omkarcloud/naver-shopping-scraper](https://github.com/omkarcloud/naver-shopping-scraper).
Licensed under the terms in [LICENSE](LICENSE).
