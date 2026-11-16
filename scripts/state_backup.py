"""Backup of the data the pipeline keeps on disk (the owner, 2026-11-16): tar + zstd archives by phase, outside the
repository, for the owner to upload to the cloud himself. Reads the sources only; writes nothing next to them.

Phases (archive names carry the date; paths inside are relative to the repository root):

    01-state        scripts/output/shops/<shop>/ without photos, description images and prepare_cache/,
                    scripts/output/jobs, journal, dictionaries (the live ones)                      zstd-19
    02-photos       scripts/output/shops/<shop>/collected/<run>/images/                             zstd-3
    03-description-images-partNN
                    scripts/output/shops/<shop>/description_images/<sub>/ (cache/<product id>/),
                    parts of at most --part-size uncompressed, by sorted path, a product never split  zstd-3
    04-server-pages server/output/                                                                  zstd-19
    05-archive      the rest of scripts/output/ (archive-*, trial-*, dumps, old dictionaries ...)   zstd-19

Text compresses 17-37x at level 19; the images are compressed already, level 3 takes 4-8% almost for free
(measured 2026-11-16, research). Left out by name: .env*, secret / credential / token / apikey / key.json,
*.part, *.lock, prepare_cache/, __pycache__/, .venv/ (printed). MANIFEST.json keeps per archive the phase, files,
bytes before / after, sha256 and path roots; RESTORE.md says how to check and unpack.

    .venv/bin/python scripts/state_backup.py --dry-run                       # the plan and sizes, writes nothing
    .venv/bin/python scripts/state_backup.py [--dest DIR] [--phase state,photos,description-images,server,archive]
                                             [--part-size 4G]
    .venv/bin/python scripts/state_backup.py --verify DIR                    # sha256 + every archive read through
    .venv/bin/python scripts/state_backup.py --restore DIR --to ROOT [--phase ...]   # into an empty folder

The default folder is ~/Desktop/naver-backups/<YYYY-MM-DD>/; a folder inside the repository is refused, an archive
that exists already is never overwritten (another folder, or delete it yourself). A running job (jobs/*/now.json
with a live pid) is only warned about: run the backup between jobs so the state is one moment.
Unpacking without this script: `zstd -d < 01-state-....tar.zst | tar x` (any zstd tool).
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import date, datetime, timezone
from typing import Any, Iterator

import zstandard

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PARENT = os.path.expanduser("~/Desktop/naver-backups")

PHASES = ("state", "photos", "description-images", "server", "archive")
NUMBER = {"state": "01", "photos": "02", "description-images": "03", "server": "04", "archive": "05"}
ARCHIVE_NAME = {"state": "state", "photos": "photos", "description-images": "description-images",
                "server": "server-pages", "archive": "archive"}
LEVEL = {"state": 19, "photos": 3, "description-images": 3, "server": 19, "archive": 19}
RATIO = {19: 0.25, 3: 1.0}          # a cautious guess of archive / source for the space check (text gave 1/17+)
STATE_DIRS = ("jobs", "journal", "dictionaries")     # under scripts/output, besides shops/

SKIP_DIRS = {"prepare_cache", "__pycache__", ".venv"}
SKIP_GLOBS = (".env*", "*.part", "*.lock")
SECRET = re.compile(r"secret|credential|token|apikey|key\.json", re.IGNORECASE)
CHUNK = 1 << 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def parse_size(text: str) -> int:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMG]?)B?\s*", text, re.IGNORECASE)
    if not m:
        raise argparse.ArgumentTypeError(f"not a size: {text!r} (e.g. 4G, 500M)")
    return int(float(m.group(1)) * 1024 ** "_KMG".index(m.group(2).upper() or "_"))


def skip_reason(name: str, is_dir: bool) -> str | None:
    """Why a file or folder stays out of every archive, or None."""
    if is_dir and name in SKIP_DIRS:
        return "folder"
    if any(fnmatch.fnmatch(name, g) for g in SKIP_GLOBS):
        return "name"
    if SECRET.search(name):
        return "secret-like name"
    return None


def phase_of(rel: str) -> str:
    """The phase of a file by its path relative to the repository root."""
    parts = rel.split("/")
    if parts[0] == "server":
        return "server"
    if len(parts) > 3 and parts[2] == "shops":
        # scripts/output/shops/<shop>/collected/<run>/images/...
        if len(parts) > 7 and parts[4] == "collected" and parts[6] == "images":
            return "photos"
        # scripts/output/shops/<shop>/description_images/<sub>/... (the sidecars <id>.json stay in state)
        if len(parts) > 6 and parts[4] == "description_images":
            return "description-images"
        return "state"
    if len(parts) > 3 and parts[2] in STATE_DIRS:
        return "state"
    return "archive"


def _unit(rel: str) -> str:
    """The piece a description-images part never splits: one product's folder (or a loose file)."""
    parts = rel.split("/")
    return "/".join(parts[:7]) if len(parts) > 7 else rel


def _root(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:4] if parts[:3] == ["scripts", "output", "shops"] else parts[:3])


def scan(root: str) -> tuple[dict[str, list[tuple[str, int]]], list[tuple[str, str]]]:
    """Every file under scripts/output and server/output -> {phase: [(rel, bytes)]} sorted, and what was left out."""
    files: dict[str, list[tuple[str, int]]] = {p: [] for p in PHASES}
    excluded: list[tuple[str, str]] = []
    for top in ("scripts/output", "server/output"):
        base = os.path.join(root, top)
        for here, dirs, names in os.walk(base):
            rel_here = os.path.relpath(here, root).replace(os.sep, "/")
            keep = []
            for d in sorted(dirs):
                why = skip_reason(d, True)
                if why or os.path.islink(os.path.join(here, d)):
                    excluded.append((f"{rel_here}/{d}/", why or "symlink"))
                else:
                    keep.append(d)
            dirs[:] = keep
            for n in sorted(names):
                path = os.path.join(here, n)
                rel = f"{rel_here}/{n}"
                why = skip_reason(n, False) or ("symlink" if os.path.islink(path) else None)
                if why is None and not os.path.isfile(path):
                    why = "not a regular file"
                if why:
                    excluded.append((rel, why))
                    continue
                files[phase_of(rel)].append((rel, os.path.getsize(path)))
    for p in PHASES:
        files[p].sort()
    return files, excluded


def plan(files: dict[str, list[tuple[str, int]]], phases: list[str], day: str,
         part_size: int) -> list[dict[str, Any]]:
    """The archives to write: [{name, phase, part, level, files: [(rel, bytes)]}], empty phases left out."""
    out = []
    for phase in phases:
        items = files[phase]
        if not items:
            continue
        stem = f"{NUMBER[phase]}-{ARCHIVE_NAME[phase]}-{day}"
        if phase != "description-images":
            out.append({"name": stem + ".tar.zst", "phase": phase, "part": None, "level": LEVEL[phase], "files": items})
            continue
        units: dict[str, list[tuple[str, int]]] = {}
        for rel, size in items:
            units.setdefault(_unit(rel), []).append((rel, size))
        parts: list[list[tuple[str, int]]] = [[]]
        used = 0
        for key in sorted(units):
            size = sum(s for _, s in units[key])
            if parts[-1] and used + size > part_size:
                parts.append([])
                used = 0
            parts[-1].extend(units[key])
            used += size
        for i, chunk in enumerate(parts, 1):
            out.append({"name": f"{stem}-part{i:02d}.tar.zst", "phase": phase, "part": i, "level": LEVEL[phase],
                        "files": chunk})
    return out


def _inside(path: str, folder: str) -> bool:
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder + os.sep)


def _free(path: str) -> int:
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    return shutil.disk_usage(probe).free


def _git_sha(root: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except OSError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def running_jobs(root: str) -> list[str]:
    """Jobs whose runner is alive now (now.json with a live pid), as job.py status sees them."""
    out = []
    jobs = os.path.join(root, "scripts", "output", "jobs")
    for name in sorted(os.listdir(jobs)) if os.path.isdir(jobs) else []:
        try:
            with open(os.path.join(jobs, name, "now.json"), encoding="utf-8") as f:
                os.kill(int(json.load(f)["pid"]), 0)
            out.append(name)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return out


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def write_archive(root: str, archive: dict[str, Any], dest: str) -> dict[str, Any]:
    """One archive: <name>.part written, then renamed. -> its MANIFEST entry."""
    final = os.path.join(dest, archive["name"])
    tmp = final + ".part"
    cctx = zstandard.ZstdCompressor(level=archive["level"], threads=-1, write_checksum=True)
    count = total = 0
    with open(tmp, "wb") as raw:
        with cctx.stream_writer(raw, closefd=False) as zw:
            with tarfile.open(fileobj=zw, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for rel, _ in archive["files"]:
                    path = os.path.join(root, rel)
                    info = tar.gettarinfo(path, arcname=rel)
                    with open(path, "rb") as fh:
                        tar.addfile(info, fh)
                    count += 1
                    total += info.size
        raw.flush()
        os.fsync(raw.fileno())
    os.replace(tmp, final)
    return {"file": archive["name"], "phase": archive["phase"], "part": archive["part"], "level": archive["level"],
            "files": count, "bytes_in": total, "bytes_out": os.path.getsize(final), "sha256": sha256(final),
            "roots": sorted({_root(rel) for rel, _ in archive["files"]}), "written_at": _now()}


def _load_manifest(dest: str) -> dict[str, Any]:
    try:
        with open(os.path.join(dest, "MANIFEST.json"), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"created": _now(), "archives": []}


def _save_manifest(dest: str, manifest: dict[str, Any]) -> None:
    path = os.path.join(dest, "MANIFEST.json")
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(path + ".part", path)


RESTORE = """# Restoring this backup

Made by `scripts/state_backup.py` (git {sha}). Every path inside the archives is relative to the repository
root (`scripts/output/...`, `server/output/...`), so unpacking into the repository root puts each file back where
it was. MANIFEST.json lists each archive's phase, number of files, bytes and sha256.

1. Check: `.venv/bin/python scripts/state_backup.py --verify <this folder>` (sha256 of each file, then every
   archive read through; zstd checks each frame's checksum).
2. Unpack into an EMPTY folder first, never over a working repository:
   `.venv/bin/python scripts/state_backup.py --restore <this folder> --to <empty folder> [--phase state,...]`
   Without the script: `zstd -d < 01-state-<date>.tar.zst | tar x -C <empty folder>` (any zstd tool).
3. Compare, then move the folders you need into the repository by hand (stop any job first).

| Archive | Phase | What |
|---|---|---|
| `01-state-*` | state | shops without photos / description images / prepare_cache, jobs, journal, live dictionaries |
| `02-photos-*` | photos | `collected/<run>/images/` |
| `03-description-images-*-partNN` | description-images | `description_images/cache/<product id>/`, each part on its own |
| `04-server-pages-*` | server | `server/output/` (saved Naver pages) |
| `05-archive-*` | archive | the rest of `scripts/output/` (old runs, dumps, old dictionaries) |

Left out on purpose: `.env*`, secret-like names, `*.part`, `*.lock`, `prepare_cache/` (rebuilt by the transform).
"""


def backup(root: str, dest: str, phases: list[str], part_size: int, dry_run: bool = False,
           day: str | None = None, out: Any = None) -> int:
    out = out or sys.stdout
    day = day or date.today().isoformat()
    if _inside(dest, root) or _inside(dest, REPO):
        print(f"refused: {dest} is inside the repository; the backup goes outside it", file=out)
        return 2
    files, excluded = scan(root)
    archives = plan(files, phases, day, part_size)
    print(f"left out ({len(excluded)}):", file=out)
    for rel, why in excluded[:50]:
        print(f"  {rel}  ({why})", file=out)
    if len(excluded) > 50:
        print(f"  ... and {len(excluded) - 50} more", file=out)
    estimate = 0
    print(f"plan -> {dest}", file=out)
    for a in archives:
        size = sum(s for _, s in a["files"])
        guess = int(size * RATIO[a["level"]])
        estimate += guess
        print(f"  {a['name']:<52} {len(a['files']):>7} files  {human(size):>9}  -> up to {human(guess)}"
              f"  (zstd-{a['level']})", file=out)
    free = _free(dest)
    print(f"estimate up to {human(estimate)}; free {human(free)}", file=out)
    jobs = running_jobs(root)
    if jobs:
        print(f"WARNING: a job is running ({', '.join(jobs)}): the state may change while it is read; "
              f"better between jobs", file=out)
    if dry_run:
        print("dry run: nothing written", file=out)
        return 0
    if free < estimate * 1.1:
        print(f"refused: {human(free)} free, {human(estimate * 1.1)} needed (estimate + 10%)", file=out)
        return 2
    there = [a["name"] for a in archives if os.path.exists(os.path.join(dest, a["name"]))]
    if there:
        print(f"refused: already in {dest}: {', '.join(there)} (never overwritten: another --dest, "
              f"or delete them yourself)", file=out)
        return 2
    os.makedirs(dest, exist_ok=True)
    manifest = _load_manifest(dest)
    sha = _git_sha(root)
    for a in archives:
        print(f"writing {a['name']} ...", file=out, flush=True)
        entry = write_archive(root, a, dest)
        entry["git_sha"] = sha
        manifest["archives"] = [e for e in manifest["archives"] if e["file"] != entry["file"]] + [entry]
        manifest.update(updated=_now(), git_sha=sha, excluded=[f"{r} ({w})" for r, w in excluded])
        _save_manifest(dest, manifest)
        print(f"  {entry['files']} files, {human(entry['bytes_in'])} -> {human(entry['bytes_out'])}", file=out)
    with open(os.path.join(dest, "RESTORE.md"), "w", encoding="utf-8") as f:
        f.write(RESTORE.format(sha=sha or "unknown"))
    print("for the cloud:", file=out)
    for e in sorted(manifest["archives"], key=lambda e: e["file"]):
        print(f"  {e['file']:<52} {human(e['bytes_out']):>9}", file=out)
    for name in ("MANIFEST.json", "RESTORE.md"):
        print(f"  {name:<52} {human(os.path.getsize(os.path.join(dest, name))):>9}", file=out)
    return 0


def _members(path: str) -> Iterator[tuple[tarfile.TarFile, tarfile.TarInfo]]:
    with open(path, "rb") as fh:
        with zstandard.ZstdDecompressor().stream_reader(fh) as zr:
            with tarfile.open(fileobj=zr, mode="r|") as tar:
                for m in tar:
                    yield tar, m


def verify(dest: str, phases: list[str] | None = None, out: Any = None) -> int:
    """sha256 of each archive against MANIFEST, then each read through: its files and bytes match."""
    out = out or sys.stdout
    manifest = _load_manifest(dest)
    if not manifest["archives"]:
        print(f"no MANIFEST.json archives in {dest}", file=out)
        return 1
    bad = 0
    listed = {e["file"] for e in manifest["archives"]}
    for name in sorted(os.listdir(dest)):
        if name.endswith(".tar.zst") and name not in listed:
            print(f"  {name}: not in MANIFEST.json", file=out)
            bad += 1
    for e in sorted(manifest["archives"], key=lambda e: e["file"]):
        if phases and e["phase"] not in phases:
            continue
        path = os.path.join(dest, e["file"])
        problem = None
        if not os.path.exists(path):
            problem = "missing"
        elif sha256(path) != e["sha256"]:
            problem = "sha256 differs"
        else:
            try:
                count = total = 0
                for _, m in _members(path):
                    if m.isfile():
                        count += 1
                        total += m.size
                if (count, total) != (e["files"], e["bytes_in"]):
                    problem = f"{count} files / {total} bytes inside, MANIFEST says {e['files']} / {e['bytes_in']}"
            except (tarfile.TarError, zstandard.ZstdError, OSError) as exc:
                problem = f"unreadable: {exc}"
        bad += problem is not None
        print(f"  {e['file']:<52} {'ok' if problem is None else 'FAIL: ' + problem}", file=out)
    print("verify: ok" if not bad else f"verify: {bad} FAILED", file=out)
    return 0 if not bad else 1


def restore(dest: str, to: str, phases: list[str], root: str = REPO, out: Any = None) -> int:
    """Unpack the chosen phases into an empty (or new) folder outside the repository, each archive checked first."""
    out = out or sys.stdout
    if _inside(to, root) or _inside(root, to):
        print(f"refused: {to} is the repository or holds it; restore into an empty folder elsewhere", file=out)
        return 2
    if os.path.isdir(to) and os.listdir(to):
        print(f"refused: {to} is not empty", file=out)
        return 2
    manifest = _load_manifest(dest)
    chosen = [e for e in sorted(manifest["archives"], key=lambda e: e["file"]) if e["phase"] in phases]
    if not chosen:
        print(f"nothing to restore from {dest} for {', '.join(phases)}", file=out)
        return 1
    for e in chosen:
        path = os.path.join(dest, e["file"])
        if sha256(path) != e["sha256"]:
            print(f"refused: {e['file']}: sha256 differs from MANIFEST.json", file=out)
            return 1
    os.makedirs(to, exist_ok=True)
    for e in chosen:
        count = 0
        for tar, m in _members(os.path.join(dest, e["file"])):
            tar.extract(m, to, filter="data")
            count += m.isfile()
        print(f"  {e['file']}: {count} files -> {to}", file=out)
    return 0


def _phases(text: str | None) -> list[str]:
    chosen = [p.strip() for p in text.split(",")] if text else list(PHASES)
    unknown = [p for p in chosen if p not in PHASES]
    if unknown:
        raise SystemExit(f"unknown phase(s): {', '.join(unknown)}; known: {', '.join(PHASES)}")
    return [p for p in PHASES if p in chosen]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dest", help=f"backup folder (default {DEFAULT_PARENT}/<YYYY-MM-DD>)")
    ap.add_argument("--phase", help=f"comma list of {','.join(PHASES)} (default all)")
    ap.add_argument("--part-size", type=parse_size, default=parse_size("4G"),
                    help="description images: uncompressed bytes per part (default 4G)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and sizes, write nothing")
    ap.add_argument("--verify", metavar="DIR", help="check a backup folder")
    ap.add_argument("--restore", metavar="DIR", help="unpack a backup folder (with --to)")
    ap.add_argument("--to", help="--restore: an empty folder outside the repository")
    args = ap.parse_args(argv)
    phases = _phases(args.phase)
    if args.verify:
        return verify(args.verify, phases if args.phase else None)
    if args.restore:
        if not args.to:
            ap.error("--restore needs --to")
        return restore(args.restore, args.to, phases)
    dest = args.dest or os.path.join(DEFAULT_PARENT, date.today().isoformat())
    return backup(REPO, dest, phases, args.part_size, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
