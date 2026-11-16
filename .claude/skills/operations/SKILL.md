---
name: operations
description: Running the scripts and their checks, the state backup (state_backup.py), the shop's shared files and lock (shop_files.py), and the scripts' conventions. Use when setting up or running scripts, before a commit (check.sh), making or restoring a backup, after a release, writing code that reads or writes the shop's files, or when unsure of a scripts/ convention.
---

# Operations

Running the scripts and keeping their state safe. The doc: `scripts/OPERATIONS.md`.

| Task | `scripts/OPERATIONS.md` section |
|---|---|
| The server, the scripts' requirements, the entry points, smoke and harvest examples, the offline checks | "Running" |
| Back up `scripts/output`, `server/output` and `research/` into archives outside the repo; verify; restore | "Backup" |
| Code that writes a shop's files: atomic writes, appended lines, `read_jsonl`, `shop_lock` | "Shared files" |
| Typed calls, sequential by default, the server cache, status handling, pagination, naming, style | "Conventions" |
| An error from the API or a job | skill `api-error-triage` |

Commands (repo root):
- `scripts/check.sh` (server suite, scripts suite, mypy; offline) before a commit
- `.venv/bin/python scripts/state_backup.py --dry-run`, then without it; `--verify <folder>`
- `.venv/bin/python scripts/smoke_endpoints.py` (live, server running)

Rules:
- Tests never hit the network; `scripts/` talks to the server over HTTP only (AGENTS.md rules 3, 4).
- New code that writes a shop's files goes through `shop_files.py` (`write_atomic`, `append_line`, `shop_lock`).
- A backup after each release; restore only into an empty folder.
- What waits for the owner, and Never (no `.env*`, no secrets printed): `scripts/OWNER_RULES.md`.

More: a release skill `release`; setup `SETUP.md`; server operations `server/README.md`; API calls skill `collect-api`; jobs skill `run-a-job`.
