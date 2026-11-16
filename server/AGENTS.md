# server/: agent pointer

Before editing anything here, read [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md). It is binding: its MUST
rules win over anything else, including this file.

Docs (read the one that fits the change; each opens with "How to use": what to run, what the answers mean, what to do):

- [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md): the rulebook. Every change.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, the transports (curl / Chrome box / extension, section 12), Naver specifics
  (section 13, one subsection per surface).
  Structural, transport or browser changes; debugging blocks and 502s.
- [docs/ENDPOINTS.md](docs/ENDPOINTS.md): the public HTTP contract, the only thing `scripts/` may rely on. Any change
  visible over HTTP updates it in the same commit.
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md): inherited defects, an index with each one's status. Read before "fixing" anything that looks wrong or
  upgrading dependencies; do not copy patterns listed there.
- [docs/EXTENSION.md](docs/EXTENSION.md): the extension adapter: the search.shopping listing, product page specs, the
  held listing tab (`/listing-tabs`), what to do on 409 / 410 / 503 and a captcha; rules R-EXT-*. Its HTTP contract is in
  ENDPOINTS.md.
- [README.md](README.md): run on macOS, env vars and their real scope, tests.

Import root: `server/` is the import root. Imports are bare (`import config`, `from naver_shopping import api`).
Do not add `server/__init__.py` and do not write `from server import ...`.

Verify:

```
.venv/bin/python -m pytest -q                     # from the repo root, offline: all pass (scripts/check.sh runs all three checks)
.venv/bin/python server/run.py                    # then, in another shell:
.venv/bin/python scripts/smoke_endpoints.py       # live smoke; when it is required: R-TEST-4
```
