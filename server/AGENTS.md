# server/: agent pointer

Before editing anything here, read [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md). It is binding: its MUST
rules win over anything else, including this file.

Docs (read the one that fits the change):

- [docs/DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md): the rulebook. Every change.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): layers, the transports (curl / Chrome box / extension, section 12), Naver specifics.
  Structural, transport or browser changes; debugging blocks and 502s.
- [docs/ENDPOINTS.md](docs/ENDPOINTS.md): the public HTTP contract, the only thing `scripts/` may rely on. Any change
  visible over HTTP updates it in the same commit.
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md): inherited defects. Read before "fixing" anything that looks wrong or
  upgrading dependencies; do not copy patterns listed there.
- [docs/EXTENSION.md](docs/EXTENSION.md): the extension transport (beta), search.shopping listing; rules R-EXT-*.
- [README.md](README.md): run on macOS, env vars and their real scope, tests.

Import root: `server/` is the import root. Imports are bare (`import config`, `from naver_shopping import api`).
Do not add `server/__init__.py` and do not write `from server import ...`.

Verify:

```
.venv/bin/python -m pytest -q                     # from the repo root, offline: 232 passed
.venv/bin/python server/run.py                    # then, in another shell:
.venv/bin/python scripts/smoke_endpoints.py       # live smoke; required for any transport or browser change
```
