"""Offline tests for shop_files.py: the atomic rewrite, the append after a line with no line end, the strict and the
tail-tolerant read, and the shop's lock (refused while held, free again after its holder is killed).

    .venv/bin/python -m pytest scripts/test_shop_files.py -q
"""
import json
import os
import signal
import subprocess
import sys
import time

import pytest

import shop_files as F

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def test_write_atomic_replaces_the_file_and_leaves_no_part(tmp_path):
    path = tmp_path / "products.jsonl"
    path.write_text("old\n")
    with open(path, encoding="utf-8") as reader:             # a reader that opened the old file (status, a lens)
        F.write_atomic(str(path), "new\n")
        assert reader.read() == "old\n"                          # still reads the whole old text
    assert path.read_text() == "new\n" and os.listdir(tmp_path) == ["products.jsonl"]


def test_write_atomic_cut_off_mid_write_leaves_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "products.jsonl"
    path.write_text("old\n")
    real = os.replace

    def killed(*a):                                              # the process dies before the rename
        raise KeyboardInterrupt
    monkeypatch.setattr(F.os, "replace", killed)
    with pytest.raises(KeyboardInterrupt):
        F.write_atomic(str(path), "new\n" * 1000)
    monkeypatch.setattr(F.os, "replace", real)
    assert path.read_text() == "old\n" and os.listdir(tmp_path) == ["products.jsonl"]


def test_the_part_file_carries_the_pid(tmp_path, monkeypatch):
    seen = []
    real = os.replace
    monkeypatch.setattr(F.os, "replace", lambda a, b: seen.append(a) or real(a, b))
    F.write_atomic(str(tmp_path / "job.json"), "{}")
    assert seen == [f"{tmp_path / 'job.json'}.{os.getpid()}.part"]


def test_append_line_after_a_tail_with_no_line_end_keeps_the_new_row_readable(tmp_path):
    path = tmp_path / "published.jsonl"
    path.write_text('{"key": "a"}\n{"key": "b"}')                # a hand edit without the last line end
    F.append_line(str(path), json.dumps({"key": "c"}), json.dumps({"key": "d"}))
    assert [r["key"] for r in F.read_jsonl(str(path))] == ["a", "b", "c", "d"]
    path.write_text('{"key": "a"}\n{"key": "b", "pho')           # cut off by a killed run
    F.append_line(str(path), json.dumps({"key": "c"}))
    assert path.read_text().endswith('"pho\n{"key": "c"}\n')     # the fragment is a middle line now: named
    with pytest.raises(F.LedgerError, match=r"published.jsonl:2:"):
        F.read_jsonl(str(path), tail_ok=True)


def test_append_line_creates_the_file(tmp_path):
    F.append_line(str(tmp_path / "events.jsonl"), "{}")
    assert (tmp_path / "events.jsonl").read_text() == "{}\n"


def test_read_jsonl_a_bad_middle_line_names_the_file_and_line(tmp_path):
    path = tmp_path / "published.jsonl"
    path.write_text('{"key": "a"}\n{"key": \n{"key": "c"}\n')
    with pytest.raises(F.LedgerError, match=r"published.jsonl:2: not a JSON line \(fix or remove it by hand\)"):
        F.read_jsonl(str(path), tail_ok=True)


def test_read_jsonl_a_cut_off_tail_only_with_tail_ok(tmp_path, capsys):
    path = tmp_path / "listing.jsonl"
    path.write_text('{"key": "a"}\n\n{"key": "b"}\n{"key": "c", "na')
    assert [r["key"] for r in F.read_jsonl(str(path), tail_ok=True)] == ["a", "b"]
    assert F.read_jsonl(str(path), tail_ok=True) == [{"key": "a"}, {"key": "b"}]
    assert capsys.readouterr().err.count("cut-off last line") == 1          # one warning a process
    with pytest.raises(F.LedgerError, match=r"listing.jsonl:4:"):
        F.read_jsonl(str(path))
    assert F.read_jsonl(str(tmp_path / "none.jsonl")) == []


def test_a_rebuilt_file_with_a_cut_off_tail_is_an_error_with_the_command_to_rebuild_it(tmp_path):
    path = tmp_path / "products.jsonl"
    path.write_text('{"key": "a"}\n{"key": "b", ')
    with pytest.raises(F.LedgerError, match=r"products.jsonl:2: .*rebuild it: run_transform.py"):
        F.read_jsonl(str(path))


def test_shop_lock_refused_while_held_and_taken_again_after(tmp_path):
    root = str(tmp_path / "shops")
    with F.shop_lock(root, "shop", "job.py run j1"):
        with pytest.raises(F.ShopBusy, match=r"shop is busy: job.py run j1 \(pid \d+, since .*\): wait for it"):
            with F.shop_lock(root, "shop", "translate.py"):
                pass
        with F.shop_lock(root, "other", "translate.py"):          # another shop: its own lock
            pass
    with F.shop_lock(root, "shop", "translate.py"):              # released; taken twice in a row in one process
        pass
    with F.shop_lock(root, "shop", "translate.py"):
        pass
    assert sorted(os.listdir(root)) == [".other.lock", ".shop.lock"]


def test_shop_lock_is_free_after_its_holder_is_killed(tmp_path):
    root = str(tmp_path / "shops")
    code = (f"import sys, time; sys.path.insert(0, {SCRIPTS!r}); import shop_files as F\n"
            f"with F.shop_lock({root!r}, 'shop', 'job.py run j1'):\n"
            "    print('held', flush=True)\n"
            "    time.sleep(60)\n")
    child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdout.readline().strip() == "held"
        with pytest.raises(F.ShopBusy, match=f"pid {child.pid}"):
            with F.shop_lock(root, "shop", "translate.py"):
                pass
    finally:
        child.send_signal(signal.SIGKILL)
        child.wait()
    for _ in range(50):                                          # the kernel frees it with the process
        try:
            with F.shop_lock(root, "shop", "translate.py"):
                break
        except F.ShopBusy:
            time.sleep(0.1)
    else:
        pytest.fail("the lock stayed after its holder was killed")
