---
name: recover-state
description: Recover the shop's state after a crash, a kill or an interrupted run, read only first: a torn or broken line in a .jsonl (LedgerError, "a cut-off last line ignored"), a "stop: <shop> is busy" refusal (a live holder or a leftover lock file), a job that died mid-product (job.py status, resume), the prepare cache disagreeing (run_transform.py --verify), a leftover .part file, restoring from a backup (state_backup.py --restore), a reboot or power cut mid-run. Use for "упало", "прервалось", "job умер", "мак перезагрузился", "выключился", "reboot", "power cut", "shop is busy", "LedgerError", "восстанови из бэкапа", "что-то сломалось в файлах".
---

# Recover the state after a crash

Find what the crash left, say it, and touch nothing. A state file is deleted, edited or replaced only on the owner's word
([scripts/OWNER_RULES.md](../../../scripts/OWNER_RULES.md), "3. Never": never edit a job's files by hand unasked).
`S=scripts/output/shops/<shop>`, `J=scripts/output/jobs`.

| Task | Doc "Section" |
|---|---|
| Atomic rewrites, appends, the readers, the lock | scripts/OPERATIONS.md "Shared files (`shop_files.py`, 2026-11-16)" |
| A job's STOP lines; resume | scripts/JOB_AGENT.md "What stops, and who acts", "4. Stop and resume", "1. Before" |
| The prepare cache, `--verify` | scripts/TRANSFORM.md "The prepare cache", "How to use" |
| A send cut off mid-product; the store vs the ledger | scripts/PUBLISH.md "Publication (`publish.py`, MVP, the owner 2026-11-08)", "Withdraw, hold, restore, activate (store actions)" |
| A backup: verify, restore | scripts/OPERATIONS.md "Backup (`state_backup.py`, the owner 2026-11-16)"; the backup folder's `RESTORE.md` |

1. **Who runs**: `.venv/bin/python scripts/job.py status [--job <id>]` (no `--job`: the newest job). `running (pid N)`
   only means some process has the pid in `now.json` (`Job.now`: `os.kill(pid, 0)`, not which program). Prove it:
   `ps -p <N> -o pid,etime,command` must show `job.py` for this job, started after the last boot (`sysctl -n
   kern.boottime`), and `lsof scripts/output/shops/.<shop>.lock` must name it. Proven: a runner is alive, wait or stop
   it (JOB_AGENT "4. Stop and resume"). Not proven (after a reboot, always): the job is dead; never kill that pid.
   `no runner`, `finished: False`: it died. A `last stop:` with a reason: an ordinary STOP (the JOB_AGENT table);
   no new stop event after the last product line: killed (kill -9, a power cut), no STOP was written.
2. **The lock** (`<tool>: stop: <shop> is busy: <holder> (pid N, since T)`, exit 2). `fcntl.flock` goes with its
   process (kill -9 too), so a refusal always means a live holder: `ps -p <N> -o pid,etime,command`. The file
   `scripts/output/shops/.<shop>.lock` keeps the last holder's text after it ends: that text alone is not a lock;
   `lsof scripts/output/shops/.<shop>.lock` printing nothing (exit 1) = nobody holds it. Never delete the file;
   never start a second runner; stopping a live one: its pid, on the owner's word for a job.
3. **A broken line**. Check one file, read only: `.venv/bin/python -c "import sys; sys.path.insert(0, 'scripts');
   from shop_files import read_jsonl; print(len(read_jsonl('<path>', tail_ok=<True|False>)))"` (`True` only for an
   append-only file: the ledger, `files.jsonl`, a job's `listing.jsonl`). `tail -c 1 <path> | od -c` not `\n`: the last
   line is cut off.
   - `warning: <path>:<n>: a cut-off last line ignored` (ledger, listing): harmless now, but the next append puts a
     line end after it and every strict read then stops with `LedgerError: <path>:<n>`. Tell the owner the file and
     line before the next send or `scroll --job`.
   - `LedgerError: <path>:<n>: not a JSON line (rebuild it: <command>)` (`products.jsonl`, `translated.jsonl`,
     `placements.jsonl`): rebuilt files, the command it names (`run_transform.py <shop>`, `translate.py <shop>
     --offline`, `placement.py <shop>`), when no job runs (they take the lock).
   - `LedgerError: ... (fix or remove it by hand)` (the ledger, `files.jsonl`, a listing's middle line): show the owner
     `sed -n '<n>p' <path>` and the rows around it; the fix by hand is his word (JOB_AGENT table, `LedgerError` row).
   - A job's `events.jsonl`, `texts.jsonl`, `descriptions.jsonl`, the journal skip bad lines: nothing to do.
4. **Leftovers**: `find $S $J -name '*.part'` and `find scripts/output/dictionaries -name '.*.tmp'` (a write killed
   before its rename; after a kill the file beside it is whole, a leftover is never read): list them for the owner. A scroll job killed with `-9` may leave its listing tab: JOB_AGENT
   table, `adapter busy` row.
5. **Mid-product**: resume picks up from the files (done stages are not repeated): `job.py run --job <id>` (old mode)
   or `job.py scroll --job <id>` (scroll); after a wall or captcha only on the owner's word with a small count
   (JOB_AGENT "4. Stop and resume"). A kill after Shopify took the product but before its ledger row: the next send
   finds it by its source key or handle and updates it, no second copy (`publish.py`, step 3); check with
   `.venv/bin/python scripts/store_diff.py <shop> --only <key>` (read only).
6. **The prepare cache**: `.venv/bin/python scripts/run_transform.py <shop> --verify` (writes nothing, runs beside a
   job): `identical` exit 0, nothing; `differs <key>: <field>` exit 1, a code fault: report it, `--full` until fixed
   (TRANSFORM "How to use"); `nothing compared: no current record`: run `run_transform.py <shop>` first. A broken
   cache record is prepared afresh by itself.
7. **From a backup** (files lost or damaged beyond a line): `.venv/bin/python scripts/state_backup.py --verify <folder>`,
   then `--restore <folder> --to <empty folder outside the repo> [--phase state,...]` (refused: `<to> is not empty`,
   `is the repository or holds it`, an archive missing or its sha256 changed). Then compare; moving folders into
   the repository is by hand, with every job stopped, on the owner's word (`RESTORE.md` step 3). `prepare_cache/` is
   not backed up: the next transform prepares the whole shop once.

**After a reboot or power cut**: `write_atomic` has no fsync (the `shop_files.py` docstring), so a rewritten file can
be empty or short. Check each with the step 3 one-liner: strict (`False`) `$S/prepared/products.jsonl`,
`$S/translation/translated.jsonl`, `$S/placement/placements.jsonl`; `True` `$S/publish/published.jsonl`,
`$S/publish/files.jsonl`, the job's `listing.jsonl`; `.venv/bin/python -m json.tool <J>/<id>/job.json`;
`.venv/bin/python scripts/translation_dicts.py status` (a broken dictionary raises `DictionaryError: <path>`).
A broken rebuilt file: its rebuild command; anything else: the backup (step 7); both on the owner's word. The
server and its Chrome are down too: skills `setup-machine` and `extension` before any resume.

Report: what died and when, each finding (file:line, holder pid, `.part` paths, the verify line), what is safe to
resume, and the exact command for each fix that waits for the owner's word.
