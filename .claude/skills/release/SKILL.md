---
name: release
description: Cut a release of this repo (developer): VERSION bump, docs, check.sh, the release commit, fast-forward master, annotated tag, push, then the state backup for the owner. Use when the owner asks for a release ("выпусти релиз", "релиз", "bump VERSION", "tag"), or before telling the owner a version is out.
---

# A release

The owner's rule (2026-11-14): **no CHANGELOG entries and no "Unreleased"** (CHANGELOG.md is frozen at 0.18.0). A
release is VERSION + docs + a commit and a tag. The owner asking for the release is the go-ahead to push.

1. **Start clean on `develop`**: `git status` clean, `git log --oneline master..develop` lists what goes out. No
   job may be running (`.venv/bin/python scripts/job.py status`): the backup in step 7 wants quiet files.
2. **Version**: `X.Y.Z` in `VERSION` (`/health` reports it); a new feature raises Y, a fix only Z. The adapter's
   own version (`extension/manifest.json`) changes only when `extension/` changed.
3. **Docs**: every behaviour change of the release already updated its doc (AGENTS.md rule 6); read the commit
   list against the docs map (AGENTS.md) and fix what is missing. No test counts in docs.
4. **Checks**: `scripts/check.sh` must end with server, scripts and mypy `ok`. A failure stops the release.
5. **Commit and tag**:
   - `git commit -am "Release X.Y.Z: <the main changes, comma-separated>"` (the trailer the session gives);
   - `git checkout master && git merge --ff-only develop` (never a merge commit; not fast-forward: stop, tell the owner);
   - `git tag -a vX.Y.Z -m "Release X.Y.Z"`;
   - `git push origin develop master vX.Y.Z`, then `git checkout develop`.
6. **Never** force-push, rewrite or delete a remote branch or tag (AGENTS.md, Branches).
7. **State backup** (skill `operations`): `.venv/bin/python scripts/state_backup.py --dry-run --dest
   ~/Desktop/naver-backups/release-X.Y.Z`, then the same without `--dry-run`, then
   `.venv/bin/python scripts/state_backup.py --verify ~/Desktop/naver-backups/release-X.Y.Z` (must pass).
8. **Report**: the version, the tag and its commit, what went out (one line each), the checks, and for the owner:
   "upload the whole folder `~/Desktop/naver-backups/release-X.Y.Z` (archives, MANIFEST.json, RESTORE.md), <size>".

More: backup details `scripts/OPERATIONS.md` "Backup"; the docs map `AGENTS.md`.
