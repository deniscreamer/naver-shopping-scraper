"""Translation dictionaries: Korean -> English, one file per kind of text (the owner, 2026-11-08). A text repeated
across products (a brand, an option name, a spec row) is translated once, by the model or by hand, and read from
its dictionary afterwards.

Two copies of each dictionary:
  live     scripts/output/dictionaries/<kind>.json   grows during runs; ignored by git (runs never commit)
  backup   scripts/dictionaries/<kind>.json          in git; updated by hand from the live copy (`backup`)

Entries are only added, never dropped, by the sync: a run takes the backup's entries the live copy lacks (seeded,
pulled from git, added in git by hand), and `backup` writes the live entries over the backup's, keeping the
backup's others. A wrong entry is fixed (or deleted) in the live copy; the next backup carries a fix to git. To
delete an entry for good, delete it in both copies.

Scopes (2026-11-11, after the first new category: an entry of 50002787 changed four products of 50002788, and
`호수` -> "Club Number" or `선택하세요` -> "Club Type" would have read wrong anywhere else): a brand is the shop's,
one spelling for every category (`<root>/brand.json`); every other kind is a category's own, `<root>/<Naver
category id>/<kind>.json` (live and backup alike). A new category starts empty: the model translates its texts once,
and nothing it learns reaches another category. `get` / `add` take the product's category; status and backup cover
every scope (a row's kind reads "<category>/<kind>").

`status` is the sync helper: when the live copies were last written, the last backup (`backup` stamps each backup
file `backed_up`, UTC), what the backup lacks (new entries, changed ones: live and git differ), what only git has
(the next run takes it) and the advice: nothing to do, wait, back up, or read the changed entries first (a backup
writes the live English over git's). A backup is due at BACKUP_AT_CHANGES entries waiting, or BACKUP_AFTER_DAYS
after the last backup with any waiting. `--json` gives the same as one object (for a script or an agent).

    .venv/bin/python scripts/translation_dicts.py status [--json]
    .venv/bin/python scripts/translation_dicts.py backup        # then commit scripts/dictionaries/
"""
import argparse
import json
import re
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(HERE, "dictionaries")
LIVE_ROOT = os.path.join(HERE, "output", "dictionaries")
FORMAT = "dictionary/1"
BACKUP_AT_CHANGES = 20          # entries the backup lacks (new, changed): back up
BACKUP_AFTER_DAYS = 7           # days since the last backup with any entry waiting: back up

# the kinds whose texts repeat across products; title and review are one product's text (translate.py keeps them
# per product), so they have no dictionary
KINDS = ("brand", "option_name", "option_value", "spec_label", "spec_value", "fact_label", "fact_value",
         "addon_group", "addon_name", "text_label", "text_placeholder")


SHARED = ("brand",)            # one per shop; the other kinds are per Naver category (a scope)


def scopes(*roots: str) -> list[str]:
    """The category scopes (sub-folders) any of the roots has."""
    return sorted({d for r in roots if os.path.isdir(r) for d in os.listdir(r) if os.path.isdir(os.path.join(r, d))
                   and not d.startswith(".")})


def _files(live_root: str, backup_root: str) -> list[tuple[str, str, str, str]]:
    """(label, kind, live path, backup path) of every dictionary: the shared kinds at the roots, every other kind
    under each category's folder."""
    out = [(kind, kind, os.path.join(live_root, f"{kind}.json"), os.path.join(backup_root, f"{kind}.json"))
           for kind in SHARED]
    for scope in scopes(live_root, backup_root):
        out += [(f"{scope}/{kind}", kind, os.path.join(live_root, scope, f"{kind}.json"),
                 os.path.join(backup_root, scope, f"{kind}.json")) for kind in KINDS if kind not in SHARED]
    return out


class DictionaryError(Exception):
    """A dictionary file that cannot be read: fix or restore it by hand."""


def _read(path: str, kind: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise DictionaryError(f"{path}: {type(e).__name__}: {e}") from None
    if data.get("format") != FORMAT or data.get("kind") != kind or not isinstance(data.get("entries"), dict):
        raise DictionaryError(f"{path}: not a {FORMAT} dictionary of {kind}")
    return {str(k): str(v) for k, v in data["entries"].items()}


def _write(path: str, kind: str, entries: dict[str, str], backed_up: str | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    head: dict[str, Any] = {"format": FORMAT, "kind": kind}
    if backed_up:
        head["backed_up"] = backed_up                # a backup file: when it was last taken from the live copy
    body = json.dumps({**head, "entries": dict(sorted(entries.items()))}, ensure_ascii=False, indent=1) + "\n"
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=f".{kind}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    os.replace(tmp, path)


class Dictionaries:
    """The live dictionaries of every kind, seeded from the backups; entries a backup has and a live copy lacks are
    added to it (a newer backup from git), never the other way round."""

    def __init__(self, live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT, kinds: tuple[str, ...] = SHARED):
        self.live_root, self.backup_root, self.kinds = live_root, backup_root, kinds
        self.entries: dict[str, dict[str, str]] = {k: {} for k in KINDS}
        self.added: dict[str, dict[str, str]] = {k: {} for k in KINDS}      # this run's new entries
        self._scopes: dict[str, "Dictionaries"] = {}
        for kind in kinds:
            live = self.path(kind)
            if not os.path.exists(live):
                backup = os.path.join(backup_root, f"{kind}.json")
                if os.path.exists(backup):
                    os.makedirs(live_root, exist_ok=True)
                    shutil.copyfile(backup, live)
            self.entries[kind] = _read(live, kind) if os.path.exists(live) else {}
            backup = os.path.join(backup_root, f"{kind}.json")
            if os.path.exists(live) and os.path.exists(backup):
                pulled = {k: v for k, v in _read(backup, kind).items() if k not in self.entries[kind]}
                if pulled:
                    self.entries[kind] = {**_read(live, kind), **pulled}
                    _write(live, kind, self.entries[kind])

    def path(self, kind: str) -> str:
        return os.path.join(self.live_root, f"{kind}.json")

    def scope(self, category: str | None) -> "Dictionaries":
        """The dictionaries of one Naver category (its own folder; created by the first entry it learns)."""
        name = str(category or "none")
        if name not in self._scopes:
            self._scopes[name] = Dictionaries(os.path.join(self.live_root, name), os.path.join(self.backup_root, name),
                                              tuple(k for k in KINDS if k not in SHARED))
        return self._scopes[name]

    def get(self, kind: str, ko: str, category: str | None = None) -> str | None:
        if kind not in SHARED and kind not in self.kinds:
            return self.scope(category).get(kind, ko)
        return self.entries.get(kind, {}).get(ko)

    def add(self, kind: str, ko: str, en: str, category: str | None = None) -> None:
        if kind not in KINDS:
            raise KeyError(kind)
        if kind not in SHARED and kind not in self.kinds:
            self.scope(category).add(kind, ko, en)
            return
        if kind == "brand":                     # one brand, one spelling whatever the case the model wrote it in
            en = self.brand_spelling(en)        # (the owner, 2026-11-09: "YONEX" stays YONEX, "Yonex" Yonex)
        if self.entries[kind].get(ko) != en:
            self.entries[kind][ko] = en
            self.added[kind][ko] = en

    def save(self) -> None:
        """This run's new entries over the file as it is now (another run may have added its own meanwhile)."""
        for scoped in self._scopes.values():
            scoped.save()
        for kind in self.kinds:
            if self.added[kind]:
                path = self.path(kind)
                current = _read(path, kind) if os.path.exists(path) else {}
                self.entries[kind] = {**current, **self.added[kind]}
                _write(path, kind, self.entries[kind])

    def all_added(self) -> dict[str, dict[str, str]]:
        """This run's new entries by "<kind>" (shared) and "<category>/<kind>"."""
        out = {k: v for k, v in self.added.items() if v}
        for name, scoped in self._scopes.items():
            out.update({f"{name}/{k}": v for k, v in scoped.added.items() if v})
        return out

    def brand_spelling(self, name: str) -> str:
        """The dictionary's spelling of this brand, compared without case; the name itself for a new brand."""
        def key(s: str) -> str:                  # letters and digits only: "U.S.KIDSGOLF" is "U.S. Kids Golf"
            return re.sub(r"[^0-9a-z가-힣]", "", (s or "").lower())
        for v in self.entries["brand"].values():
            if key(v) == key(name):
                return v
        return name

    def vendors(self) -> list[str]:
        """The canonical brand spellings (the model reuses one of them for the same brand)."""
        return sorted(set(self.entries["brand"].values()))


def status(live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT) -> list[dict[str, Any]]:
    """Per kind: entries in the live copy that the backup lacks (new) or has with another English (changed), and
    entries only the backup has (git_only: the next run takes them into the live copy; a backup keeps them). A live
    file not written yet (seeded from the backup on the first run) differs in nothing."""
    out = []
    for label, kind, live_path, backup_path in _files(live_root, backup_root):
        backup = _read(backup_path, kind) if os.path.exists(backup_path) else {}
        live = _read(live_path, kind) if os.path.exists(live_path) else dict(backup)
        new = {k: v for k, v in live.items() if k not in backup}
        changed = {k: (backup[k], v) for k, v in live.items() if k in backup and backup[k] != v}
        git_only = {k: v for k, v in backup.items() if k not in live}
        out.append({"kind": label, "live": len(live), "backup": len(backup), "new": new, "changed": changed,
                    "git_only": git_only})
    return out


def _utc(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def live_updated(live_root: str = LIVE_ROOT) -> str | None:
    """When a live copy was last written (UTC), None before the first run."""
    times = [os.path.getmtime(f[2]) for f in _files(live_root, BACKUP_ROOT) if os.path.exists(f[2])]
    return _utc(max(times)) if times else None


def sync(live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT, now: datetime | None = None) -> dict[str, Any]:
    """The sync state and the advice. `action`: "none" (in sync), "wait" (entries waiting, below the thresholds),
    "backup" (due), "review" (due, and changed entries: the backup writes the live English over git's, read them
    first). Entries only git has wait for no backup (a backup keeps them)."""
    rows = status(live_root, backup_root)
    now = now or datetime.now(timezone.utc)
    last = backed_up(backup_root)
    days = None
    if last:
        days = round((now - datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
                     .total_seconds() / 86400, 1)
    count = {x: sum(len(r[x]) for r in rows) for x in ("new", "changed", "git_only")}
    waiting = count["new"] + count["changed"]
    why = None
    if not waiting:
        action, advice = "none", "in sync: nothing to back up"
        if count["git_only"]:
            advice += f" ({count['git_only']} entries only in git: the next run takes them)"
    else:
        why = ("never backed up" if last is None
               else f"{waiting} entries waiting (at {BACKUP_AT_CHANGES})" if waiting >= BACKUP_AT_CHANGES
               else f"{days} days since the last backup (at {BACKUP_AFTER_DAYS})" if (days or 0) >= BACKUP_AFTER_DAYS
               else None)
        if why is None:
            action = "wait"
            advice = (f"not yet: {waiting} of {BACKUP_AT_CHANGES} entries, {days} of {BACKUP_AFTER_DAYS} days since "
                      f"the last backup")
        elif count["changed"]:
            action = "review"
            advice = (f"back up ({why}), but first read the {count['changed']} changed entries above (git -> live): "
                      f"the backup writes the live English over git's; fix a wrong one in the live copy, then "
                      f"`backup` and commit scripts/dictionaries/")
        else:
            action = "backup"
            advice = f"back up ({why}): read the new entries above, then `backup` and commit scripts/dictionaries/"
    return {"last_backup": last, "days_since_backup": days, "live_updated": live_updated(live_root),
            **count, "waiting": waiting, "action": action, "reason": why, "advice": advice,
            "kinds": [{k: r[k] for k in ("kind", "live", "backup")} | {x: len(r[x]) for x in count} for r in rows
                      if r["live"] or r["backup"]],
            "entries": {r["kind"]: {"new": r["new"], "changed": {k: list(v) for k, v in r["changed"].items()},
                                    "git_only": r["git_only"]}
                        for r in rows if r["new"] or r["changed"] or r["git_only"]}}


def reminder(live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT, now: datetime | None = None) -> str | None:
    """One line for the end of a run when a backup is due, else None. Never stops a run: a file it cannot read is
    `status`'s to report."""
    try:
        s = sync(live_root, backup_root, now)
    except Exception:                                    # a broken or hand-edited file: `status` shows it
        return None
    if s["action"] in ("backup", "review"):
        first = ", the changed ones first" if s["action"] == "review" else ""
        return f"dictionaries: a backup is due ({s['reason']}): read `translation_dicts.py status`{first}"
    return None


def backup(live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT, at: str | None = None) -> list[str]:
    """The live copies -> the backups (in git), each stamped `backed_up` with the time (UTC): the live entries over
    the backup's, the backup's others kept. Returns the kinds written."""
    at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = []
    for label, kind, live_path, backup_path in _files(live_root, backup_root):
        if os.path.exists(live_path):
            kept = _read(backup_path, kind) if os.path.exists(backup_path) else {}
            _write(backup_path, kind, {**kept, **_read(live_path, kind)}, backed_up=at)
            written.append(label)
    return written


def backed_up(backup_root: str = BACKUP_ROOT) -> str | None:
    """The time of the last backup (the latest `backed_up` of the backup files), None before the first one."""
    stamps = []
    for _, _, _, path in _files(backup_root, backup_root):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                stamps.append(json.load(f).get("backed_up") or "")
    return max((x for x in stamps if x), default=None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Translation dictionaries: what the live copies added; back them up.")
    p.add_argument("command", choices=("status", "backup"))
    p.add_argument("--live-root", default=LIVE_ROOT)
    p.add_argument("--backup-root", default=BACKUP_ROOT)
    p.add_argument("--json", action="store_true", help="status: one JSON object (state, advice, entries)")
    args = p.parse_args(argv)
    if args.command == "backup":
        print("backed up: " + (", ".join(backup(args.live_root, args.backup_root)) or "nothing")
              + "; commit scripts/dictionaries/")
        return 0
    s = sync(args.live_root, args.backup_root)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    since = f" ({s['days_since_backup']} days ago)" if s["last_backup"] else ""
    print(f"last backup: {s['last_backup'] or 'never (the seeds only)'}{since}; "
          f"live updated: {s['live_updated'] or 'never (no run yet)'}")
    for row in status(args.live_root, args.backup_root):
        print(f"{row['kind']}: live {row['live']}, backup {row['backup']}, new {len(row['new'])}, "
              f"changed {len(row['changed'])}, only in git {len(row['git_only'])}")
        for ko, en in row["new"].items():
            print(f"  + {ko} -> {en}")
        for ko, (old, en) in row["changed"].items():
            print(f"  ~ {ko}: {old} -> {en}")
        for ko, en in row["git_only"].items():
            print(f"  < {ko} -> {en} (only in git)")
    print(f"waiting for a backup: {s['new']} new, {s['changed']} changed; only in git: {s['git_only']}")
    print(f"advice: {s['advice']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
