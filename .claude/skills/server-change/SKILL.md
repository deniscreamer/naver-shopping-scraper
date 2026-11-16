---
name: server-change
description: Change code under server/ (developer): a new endpoint, a parser or answer shape, the curl fetch / transport, the Chrome box or driver, the extension adapter, errors, the cache, config or a new requirement, a dependency, a file move. Use before editing any file in server/, to find which DEVELOPMENT_RULES sections bind the change and which docs, types, fixtures and tests change in the same commit.
---

# A change under server/

The rulebook is `server/docs/DEVELOPMENT_RULES.md`: binding, it wins over every other doc. Read its opening (MUST /
SHOULD, "Known defects are not rules") and the rows below for the change, not the whole file. Before "fixing"
anything that looks wrong: `server/docs/KNOWN_ISSUES.md` "How to use".

| Change | Read (DEVELOPMENT_RULES unless named) | Same commit |
|---|---|---|
| A new endpoint | "Checklist: adding a new endpoint"; R-ARCH, R-CACHE, R-OUT, R-TYPE | its checklist steps 2-9; step 10: add the route to `smoke_endpoints.CALLS` (a hand-written list) and run the live smoke when the network is allowed; ENDPOINTS.md: its section and its row in "How to use"; a surface that needs the owner's Chrome: R-EXT-6, EXTENSION.md, a "Decision log" entry (R-NAVER-1) |
| A parser, an answer's shape | R-ARCH-2, R-OUT, R-TYPE, R-TEST-2, R-TEST-5 | fixture + test; ENDPOINTS.md (R-OUT-3); type, fixture, client method (R-TYPE-2); golden diff read |
| A new upstream fact (status, header, param, marker) | R-NAVER-4; ARCHITECTURE.md "13. Naver specifics" | dated comment at the code, one line in that section |
| Which surface, which transport | R-NAVER-1, R-NAVER-2, R-NAVER-3; ARCHITECTURE.md "5. The two transports" | |
| curl fetch (`fetch.py`) | R-HTTP, R-ERR-2, "Checklist: changing transport or browser code" | the live smoke result in the commit message (R-TEST-4) |
| Chrome box, driver | R-BOX, R-ERR-3, the same checklist; ARCHITECTURE.md "6. Box mechanics, step by step" | live A/B for anything Naver sees; ARCHITECTURE / KNOWN_ISSUES |
| The extension adapter, composite reads | R-EXT; `server/docs/EXTENSION.md` "How to use" | adapter version (R-EXT-5), `extension/README.md` op table |
| Errors, HTTP mapping | R-ERR; ENDPOINTS.md "Errors" | ENDPOINTS.md; skill `api-error-triage` if a meaning moved |
| Cache, a TTL | R-CACHE | the named TTL with its why (R-CACHE-2) |
| Config, an env var, any new requirement | R-SETUP; ARCHITECTURE.md "10. Config and environment" | `check_setup.py`, `.env.example`, `SETUP.md` (R-SETUP-1) |
| A dependency, an upgrade | R-DEP; KNOWN_ISSUES.md K-17 | `server/requirements.txt`, live smoke, the K-17 table |
| A module, import, move | R-LAYOUT | `test_import_smoke.MODULES`; a move is a pure `git mv` commit |
| Style, logging | R-STYLE | |
| Breaking a MUST | the opening | a "Decision log" entry |

Checks:
- `scripts/check.sh` (the server suite, the scripts suite, mypy; offline); the test count only goes up (R-TEST-4).
- The live smoke when R-TEST-4 asks (a new endpoint, transport, browser, config, requirements): server running,
  `.venv/bin/python scripts/smoke_endpoints.py`. It uses the network: only when the task allows it, never
  during a job.
- After a deliberate parser change: `UPDATE_GOLDEN=1 .venv/bin/python -m pytest server/naver_shopping/test_pages.py`,
  then read the diff (R-TEST-5); then `scripts/collected_fixtures.py refresh` and the prepared golden: skill
  `seller-pattern-rule` step 5.

Fixtures (R-TEST-2, R-TYPE-6):
- a product page in the owner's Chrome: `scripts/product_page.py <link>`, then
  `server/naver_shopping/page_fixtures.py <saved page folder> <products.jsonl>` (R-TEST-5; `/products/page` in
  ENDPOINTS.md);
- a consumer's answer (`scripts/fixtures/`): `scripts/COLLECT.md` "Response types";
- a raw curl or box answer (`naver_shopping/fixtures/box_*.json`, `datalab_*`, ...): no tool. A one-off probe
  outside git saves the raw answer, live only when the task allows the network; trim it (R-TYPE-6, R-EXT-4).

Rules:
- Every behaviour change updates its doc in the same commit (AGENTS.md rule 6). Docs disagree: fix the other doc.
- `scripts/` reaches the server over HTTP only; never make a script import server code (AGENTS.md rule 3).
- Never read `.env*`; secrets never go into code, fixtures, docs or commits (R-SETUP-2).

More: `server/AGENTS.md` (the docs map); an error's meaning skill `api-error-triage`; calling the API skill `collect-api`.
