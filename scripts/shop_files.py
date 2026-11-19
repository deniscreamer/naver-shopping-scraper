"""Safe writes and reads of a shop's shared files, and the shop's lock (2026-11-16, the hardening plan's phase 2).

    write_atomic(path, text)       a rewritten file (products.jsonl, translated.jsonl, placements.jsonl, job.json,
                                   now.json): written to <path>.<pid>.part beside it, then renamed over it
    append_line(path, *lines)      an append-only file (the ledger, events.jsonl, listing.jsonl, texts.jsonl ...):
                                   one write of whole lines; a line end first when the file does not end with one
    read_jsonl(path, tail_ok)      rows of a .jsonl; a bad line is LedgerError naming <path>:<n>, except a bad LAST
                                   line of an append-only file with tail_ok (a run killed while appending)
    shop_lock(root, shop, what)    the shop's lock for a command's whole life; held elsewhere -> ShopBusy, no wait
    locked(root, shop, what, body) a command's main under the lock; refused -> the busy line printed, exit 2
    ensure_free(root, shop)        a read tool that must not read files a run is rewriting (sweep.py): ShopBusy
                                   while another process holds the lock; takes no lock, writes nothing

Why each is so:
- write_atomic: an open(path, "w") cut off by a killed process left a short file (products.jsonl is 68 MB and
  rewritten for every product of a job), and a reader in another process (status, a lens) saw half of it. The
  rename is atomic on one file system; the .part name is description_images._write's, so no glob of the real name
  picks it up. No fsync: it protects against a killed process, not a power cut (the backups cover that).
- append_line: one write() of a string is one system call whatever its size (measured 2026-11-16 on Python 3.11,
  70 KB), and mode O_APPEND keeps two processes' writes apart, so no flock is needed. The one thing to add: a file
  whose last line has no line end (cut off, or a hand edit) would glue the new row to it; the line end first turns
  that into one bad middle line that read_jsonl names, instead of two lost rows.
- read_jsonl: the readers disagreed (some raised on any bad line, some dropped any, also in the middle: a dropped
  ledger row means a product published twice). A rebuilt file (products / translated / placements) is all or
  nothing: a bad line anywhere, the last included, is an error with the command that rebuilds it.
- shop_lock: fcntl.flock on <shops_root>/.<shop>.lock (outside the shop folder: a mistyped shop makes no folder),
  the holder written inside. The kernel frees it when the process dies, kill -9 included: no stale lock, no pid
  check. Refused at once, never waited for: a job holds it for hours and a waiting command would hang a shell.
"""
import fcntl
import json
import os
import sys
import time
from typing import IO, Any, Callable

REBUILD = {"products.jsonl": "run_transform.py <shop>", "translated.jsonl": "translate.py <shop> --offline",
           "placements.jsonl": "placement.py <shop>"}


class LedgerError(Exception):
    """A .jsonl line that is not JSON (and not a cut-off last line that may be ignored): fix the file by hand."""


class ShopBusy(Exception):
    """Another process holds the shop's lock; the message names it."""


def write_atomic(path: str, text: str) -> None:
    """`text` as the whole new content of `path`, or nothing at all (a kill mid-write leaves the old file)."""
    part = f"{path}.{os.getpid()}.part"
    try:
        with open(part, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)


def append_line(path: str, *lines: str) -> None:
    """Each of `lines` (no line end of its own) appended as one line, in one write."""
    data = "".join(x + "\n" for x in lines).encode("utf-8")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            data = b"\n" + data
        os.write(fd, data)
    finally:
        os.close(fd)


_WARNED: set[str] = set()


def read_jsonl(path: str, tail_ok: bool = False) -> list[Any]:
    """The rows of a .jsonl ([] when it does not exist). A line that is not JSON raises LedgerError("<path>:<n>:
    ..."); with `tail_ok` (append-only files: published, files, listing, lens/reviewed) a bad last line with no line
    end after it is ignored with one warning a process."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        lines = f.read().split(b"\n")
    out = []
    for n, x in enumerate(lines, 1):
        if not x.strip():
            continue
        try:
            out.append(json.loads(x))
        except ValueError:
            if tail_ok and n == len(lines):          # no line end after it: cut off by a stopped run
                if path not in _WARNED:
                    _WARNED.add(path)
                    print(f"warning: {path}:{n}: a cut-off last line ignored", file=sys.stderr)
                continue
            how = REBUILD.get(os.path.basename(path))
            raise LedgerError(f"{path}:{n}: not a JSON line ("
                              + (f"rebuild it: {how})" if how else "fix or remove it by hand)")) from None
    return out


def _busy(shop: str, holder: str) -> ShopBusy:
    """The refusal every busy check gives (shop_lock, ensure_free): the holder's line, what to do."""
    return ShopBusy(f"{shop} is busy: {holder}: wait for it (job.py status) or stop it")


def shop_lock(shops_root: str, shop: str, what: str) -> IO[str]:
    """The shop's lock, held until the returned file is closed (`with shop_lock(...):`); ShopBusy at once when another
    process holds it. `what` (e.g. "job.py run <id>") is what a refused command is told."""
    os.makedirs(shops_root, exist_ok=True)
    f = open(os.path.join(shops_root, f".{shop}.lock"), "a+", encoding="utf-8")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.seek(0)
        holder = f.read().strip() or "another run"
        f.close()
        raise _busy(shop, holder) from None
    f.seek(0)
    f.truncate()
    f.write(f"{what} (pid {os.getpid()}, since {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})")
    f.flush()
    return f


def ensure_free(shops_root: str, shop: str) -> None:
    """ShopBusy (the message shop_lock gives) while another process holds the shop's lock; returns when it is free.
    It takes no lock and writes nothing, the lock file included (2026-11-19, sweep.py: a read of the shop's files
    taken while a job rewrites three of them would report false findings, and a lock held for the whole read
    would refuse a job started meanwhile). A shared lock tried and dropped at once: it fails while an exclusive one
    is held. A shop_lock tried inside that window (microseconds) is refused as busy too, naming the last holder's
    leftover line: run the command again."""
    path = os.path.join(shops_root, f".{shop}.lock")
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:                       # never locked: free
        return
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            holder = f.read().strip() or "another run"
            raise _busy(shop, holder) from None
        fcntl.flock(f, fcntl.LOCK_UN)


def locked(shops_root: str, shop: str, what: str, body: Callable[[], int], tool: str = "") -> int:
    """A command's main: body() under the shop's lock -> its exit code; refused: "<tool>: stop: <shop> is busy: ..."
    printed and 2 (the message, not the code, is what the agent reads: some tools use 2 for other stops too)."""
    try:
        lock = shop_lock(shops_root, shop, what)
    except ShopBusy as e:
        print(f"{tool + ': ' if tool else ''}stop: {e}", flush=True)
        return 2
    with lock:
        return body()
