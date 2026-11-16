---
name: api-error-triage
description: Read an error from the local API or a job and decide what it means, whether to retry, and what to tell the owner: an HTTP 400 / 404 / 409 / 410 / 500 / 502 / 503 body, a captcha, a wall or ban page, a timeout, an empty answer, the extension not connected, a listing tab or Chrome reopened, a job's STOP line. Use when a script, curl call or job.py prints an error, or while watching a job.
---

# An error from the API or a job

The contract and the client policy: `server/docs/ENDPOINTS.md` "Errors (`routes.call`)" (the source: `routes.call`).
A job's lines: `scripts/JOB_AGENT.md` "What stops, and who acts". Rules: `scripts/OWNER_RULES.md` section 3, "Never".

| Seen | Means | Retry | Tell the owner |
|---|---|---|---|
| 400 `Invalid parameters` / `rejected the request` | our call is wrong (ENDPOINTS "Param rules") | no | nothing; fix the caller |
| 400 with a bare message (neither of the two above) | may be a server bug: a `ValueError` while serving maps to 400, not logged (KNOWN_ISSUES K-11) | no | report the body; skill `server-change` |
| 404 | the product / store is gone; a job: `not_taken not_found` (`card_not_found` for a card the tab did not show) | no | nothing |
| 409 `the adapter is busy` | a listing job, a held tab or another read holds Chrome | when it is done (a job: 30 s, 12 times) | a dead scroll holds it: JOB_AGENT row `adapter busy` |
| 410 `listing tab <id>` | the held tab is gone | not that tab: a new one (scroll does it itself, event `reopen`) | only on its `STOP` |
| 503 `wall: ...` (ban page, login gate twice, stall, refused) | Naver walls the owner's Chrome | **no**: a ban risk (R-EXT-3) | yes; run again only on their word |
| 503 `wall: captcha` / `a captcha was not answered in time` | the owner did not answer in Chrome | read again (a job: up to 6 times) | ask them to answer it; never solve it |
| a pending captcha (`scripts/captcha_watch.py [--once]`, `GET /captcha`, the server log's `ext-listing: CAPTCHA ...`) | a read waits for the owner, `NAVER_CAPTCHA_WAIT_S` (600 s); nothing in a job's log yet | the read waits by itself | at once: relay the question (server/docs/EXTENSION.md, Effects and limits, Captcha) |
| 503 `naver error page:` / `adapter error:` | Naver's passing error page (K-21) or a failed read | after ~120 s, at most twice; a job then marks it `failed`, again at the end | no |
| 503 with no kind (the extension not connected) | Chrome or the adapter is off | a job polls `/health` for 15 min | ask them to open Chrome / start the server |
| 502 `blocked the request, retry later` | Naver refuses this machine (curl or box) | after a pause (the client: 10 s, 30 s); a job: `STOP` after those two | when it persists: the IP is refused, a proxy (`server/README.md`); a job: tell the owner, resume on their word |
| 502 `failed: ... browser box unavailable` | Chrome cannot start, or a box call wedged (R-ERR-3, K-05) | after a pause | when it persists: a proxy does not help; Chrome updated? live smoke (R-DEP-2) |
| 502 other `failed:` | transport, upstream 5xx, empty upstream answer | after a pause | when it persists |
| 500 | a server bug (a parser surprise) | no | report the body; a fix: skill `server-change` |
| in a job: `partial` / `deferred` `api_500` (also `api_502` left after the retries, `api_400`) | the server answered that status for one product; the guard reads it once more, then defers it; two products in a row for one reason: `STOP at <key>: two products in a row partial for ...` (RunStopped) | no | report it; the evidence: the server's terminal line `api: <status> <path> (<label>): <Type>: <detail>` (no traceback; reproduce offline from a saved page or fixture). After the fix the deferred ones are lifted by the owner (`deferred_log.py allow`) |
| connection refused | the server is down | the client: twice; a job waits 15 min | ask them to start `server/run.py` |
| a read timeout (900 s) | the server still works on it | **no** (`naver_api_client` docstring: duplicate work) | when repeated |
| bottle HTML 404 / 405 | wrong path or method | no | nothing |

Not errors:
- A 200 with `results: []`: no products, or past the last page (ENDPOINTS "Pagination").
- A box Chrome closing and opening again: a refusal rotates the exit (R-ERR-3, ARCHITECTURE "7. Retry topology").
- `network down (...): try N in S s`: Shopify or every model down; a job waits, doubling up to 15 min, for 2 h.

Report: the command or job, the status and the error's first words, its row here, what was retried, what is
waiting on the owner. During a job: never edit code, never retry a wall, never use browser tools on Naver
(OWNER_RULES "Never"). Why the server answers as it does: `server/docs/KNOWN_ISSUES.md` "How to use".
