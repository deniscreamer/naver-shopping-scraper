---
name: live-smoke
description: Run and read the live smoke of the API (scripts/smoke_endpoints.py: /health plus 11 endpoints over curl and the server's Chrome box), compare versions with KNOWN_ISSUES K-17 and record the result. Use after a pip install or upgrade, a Google Chrome update, a change to transport, browser, config or requirements (R-TEST-4), or when every call suddenly fails. Triggers: "прогони smoke", "проверь API вживую", "после обновления Chrome / pip всё сломалось", "всё вдруг сломалось", "live smoke".
---

# The live smoke

It reaches Naver through the running server (and may launch its Chrome): run it only on the owner's say or as part
of a change the owner asked for, never during a job, never twice in a row on a 502 (a
retried block raises the ban risk: ARCHITECTURE.md "13.4 Walls and blocking"). Calls run one at a time on purpose.

| Task | Doc "Section" |
|---|---|
| When it is required, what the commit records | DEVELOPMENT_RULES R-TEST-4; "Checklist: changing transport or browser code" (step 5: which calls a box or curl change needs) |
| After pip / a Chrome update; the versions table | DEVELOPMENT_RULES R-DEP-2; KNOWN_ISSUES "K-17 Unpinned dependencies" |
| Which endpoint uses which transport | ENDPOINTS.md "Transports" and "How to use"; ARCHITECTURE.md "5. The two transports" |
| What a status means, what is retried | ENDPOINTS.md "Errors (`routes.call`)"; ARCHITECTURE.md "7. Retry topology"; skill `api-error-triage` |
| Why a 200 may prove nothing | ARCHITECTURE.md "8. Cache" (process memory, a restart empties it) |
| A wall, a block | ARCHITECTURE.md "13.4 Walls and blocking"; OWNER_RULES.md "3. Never" |

Procedure (repo root):
1. No job runs: `scripts/job.py status`. Versions now: `.venv/bin/python --version`, `.venv/bin/python -m pip list`,
   `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version`; diff them against the K-17 tables.
2. Offline first: `scripts/check.sh` (a failure here is not the network; fix it before any live call).
3. Restart the server (`.venv/bin/python server/run.py`, in its own terminal) so no cached answer hides the transport.
4. `.venv/bin/python scripts/smoke_endpoints.py` (`--base-url`, `--delay` seconds between calls, default 5). Each line:
   `smoke: <status|ERR> <secs>s <path> <hint>`; last: `smoke: N/12 ok[; failed: ...]`, exit 1 on any failure.
   A 502 is printed only after the client's own two retries (10 s, 30 s).

Per endpoint (the script's `CALLS`): curl `/products/search`, `/products/count`, `/stores/details`, `/categories/list`,
`/keywords/rank`, `/keywords/trend`, `/categories/trend`; box `/products/reviews`, `/catalogs/reviews`; both
`/products/details`, `/stores/products`. Not covered: `/products/specs`, `/products/page`, `/products/reviews/selected`,
listings, `/listing-tabs`, `/captcha` (the extension: `server/docs/EXTENSION.md` "How to use"; `scripts/check_setup.py`
shows `extension` and the bridge port).

| Result | Means | Do |
|---|---|---|
| `12/12 ok` | both transports work on these versions | record it (below) |
| `/health` `ERR` | server down or wrong `--base-url` | start it; nothing else ran usefully |
| curl group 502 `blocked`, box fine | Naver refuses this IP over plain HTTP | stop; tell the owner (proxy: `server/README.md`) |
| box group 502 `browser box unavailable` / `failed:` (or `blocked`: refused on both attempts), curl fine | Chrome cannot start or wedged (K-05): Chrome or patchright changed? | stop; tell the owner with both versions |
| everything 502 | the network, or the whole IP refused | stop; tell the owner |
| one 404 | the fixed input is gone upstream, not the transport | a new known-good input in `CALLS` (a script change, in its own commit) |
| 400 on one endpoint | Naver rejected the params (a DataLab 500 maps here) | ENDPOINTS "Param rules (all endpoints)"; report, no retry |
| 500 | a parser surprise | skill `server-change`; reproduce offline |

Record: a transport / browser / config / requirements change puts the last line (and each failed line) in its commit
message (R-TEST-4). A new pip set that passes updates the K-17 tables (date, Python version, `pip list` rows) in the
same commit (R-DEP-2); write the Chrome version in that commit message (K-17 has no Chrome row).

Tell the owner: before running it (it uses the network and Naver); any failure above that is not a dead input; a
version change that made the box fail. Do not pin, downgrade or reinstall anything without their word (pinning needs a
"Decision log" entry, R-DEP-2). A machine that will not start at all: skill `setup-machine`; the adapter: skill `extension`.
