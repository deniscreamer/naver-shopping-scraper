"""Translation dictionaries: Korean -> English, one file per kind of text (the owner, 2026-11-08). A text repeated
across products (a brand, an option name, a spec row) is translated once, by the model or by hand, and read from
its dictionary afterwards.

Two copies of each dictionary:
  live     scripts/output/dictionaries/<kind>.json   grows during runs; ignored by git (runs never commit)
  backup   scripts/dictionaries/<kind>.json          in git; updated by hand from the live copy (`backup`)

A missing live file is seeded from its backup. `status` lists what the live copies have that the backups do not
(new entries, changed ones) so the owner reads them before `backup`; `backup` stamps each backup file `backed_up`
(UTC), and `status` prints the last one.

    .venv/bin/python scripts/translation_dicts.py status
    .venv/bin/python scripts/translation_dicts.py backup
"""
import argparse
import json
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

# the kinds whose texts repeat across products; title and review are one product's text (translate.py keeps them
# per product), so they have no dictionary
KINDS = ("brand", "option_name", "option_value", "spec_label", "spec_value", "fact_label", "fact_value",
         "addon_group", "addon_name", "text_label", "text_placeholder")


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
    """The live dictionaries of every kind, seeded from the backups."""

    def __init__(self, live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT):
        self.live_root, self.backup_root = live_root, backup_root
        self.entries: dict[str, dict[str, str]] = {}
        self.added: dict[str, dict[str, str]] = {k: {} for k in KINDS}      # this run's new entries
        for kind in KINDS:
            live = self.path(kind)
            if not os.path.exists(live):
                backup = os.path.join(backup_root, f"{kind}.json")
                if os.path.exists(backup):
                    os.makedirs(live_root, exist_ok=True)
                    shutil.copyfile(backup, live)
            self.entries[kind] = _read(live, kind) if os.path.exists(live) else {}

    def path(self, kind: str) -> str:
        return os.path.join(self.live_root, f"{kind}.json")

    def get(self, kind: str, ko: str) -> str | None:
        return self.entries.get(kind, {}).get(ko)

    def add(self, kind: str, ko: str, en: str) -> None:
        if kind not in KINDS:
            raise KeyError(kind)
        if self.entries[kind].get(ko) != en:
            self.entries[kind][ko] = en
            self.added[kind][ko] = en

    def save(self) -> None:
        """This run's new entries over the file as it is now (another run may have added its own meanwhile)."""
        for kind in KINDS:
            if self.added[kind]:
                path = self.path(kind)
                current = _read(path, kind) if os.path.exists(path) else {}
                self.entries[kind] = {**current, **self.added[kind]}
                _write(path, kind, self.entries[kind])

    def vendors(self) -> list[str]:
        """The canonical brand spellings (the model reuses one of them for the same brand)."""
        return sorted(set(self.entries["brand"].values()))


def status(live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT) -> list[dict[str, Any]]:
    """Per kind: entries in the live copy that the backup lacks (new) or has with another English (changed)."""
    out = []
    for kind in KINDS:
        live_path, backup_path = os.path.join(live_root, f"{kind}.json"), os.path.join(backup_root, f"{kind}.json")
        live = _read(live_path, kind) if os.path.exists(live_path) else {}
        backup = _read(backup_path, kind) if os.path.exists(backup_path) else {}
        new = {k: v for k, v in live.items() if k not in backup}
        changed = {k: (backup[k], v) for k, v in live.items() if k in backup and backup[k] != v}
        out.append({"kind": kind, "live": len(live), "backup": len(backup), "new": new, "changed": changed})
    return out


def backup(live_root: str = LIVE_ROOT, backup_root: str = BACKUP_ROOT, at: str | None = None) -> list[str]:
    """The live copies -> the backups (in git), each stamped `backed_up` with the time (UTC). Returns the kinds
    written."""
    at = at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = []
    for kind in KINDS:
        live_path = os.path.join(live_root, f"{kind}.json")
        if os.path.exists(live_path):
            _write(os.path.join(backup_root, f"{kind}.json"), kind, _read(live_path, kind), backed_up=at)
            written.append(kind)
    return written


def backed_up(backup_root: str = BACKUP_ROOT) -> str | None:
    """The time of the last backup (the latest `backed_up` of the backup files), None before the first one."""
    stamps = []
    for kind in KINDS:
        path = os.path.join(backup_root, f"{kind}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                stamps.append(json.load(f).get("backed_up") or "")
    return max((x for x in stamps if x), default=None)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Translation dictionaries: what the live copies added; back them up.")
    p.add_argument("command", choices=("status", "backup"))
    p.add_argument("--live-root", default=LIVE_ROOT)
    p.add_argument("--backup-root", default=BACKUP_ROOT)
    args = p.parse_args(argv)
    if args.command == "backup":
        print("backed up: " + (", ".join(backup(args.live_root, args.backup_root)) or "nothing"))
        return 0
    print(f"last backup: {backed_up(args.backup_root) or 'never (the seeds only)'}")
    for row in status(args.live_root, args.backup_root):
        print(f"{row['kind']}: live {row['live']}, backup {row['backup']}, new {len(row['new'])}, "
              f"changed {len(row['changed'])}")
        for ko, en in row["new"].items():
            print(f"  + {ko} -> {en}")
        for ko, (old, en) in row["changed"].items():
            print(f"  ~ {ko}: {old} -> {en}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
