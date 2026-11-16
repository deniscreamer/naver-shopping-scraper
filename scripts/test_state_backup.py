"""Offline tests for the backup (state_backup.py): a small tree in tmp -> archives -> --verify -> --restore.

    .venv/bin/python -m pytest scripts/test_state_backup.py -q
"""
import io
import json
import os

import pytest

import state_backup as sb

SHOP = "scripts/output/shops/shopa"
TREE = {
    f"{SHOP}/publish/ledger.jsonl": b'{"key": "a"}\n' * 50,
    f"{SHOP}/translation/1/texts.jsonl": "번역 텍스트\n".encode() * 40,
    f"{SHOP}/description_images/1.json": b'{"rows": []}',
    f"{SHOP}/description_images/cache/1/a.bin": b"\x01" * 3000,
    f"{SHOP}/description_images/cache/1/b.bin": b"\x02" * 3000,
    f"{SHOP}/description_images/cache/2/a.bin": b"\x03" * 3000,
    f"{SHOP}/description_images/cache/3/a.bin": b"\x04" * 7000,
    f"{SHOP}/collected/run1/products.jsonl": b'{"product_id": 1}\n',
    f"{SHOP}/collected/run1/images/1/01.webp": b"RIFF" + b"\x00" * 500,
    "scripts/output/jobs/job1/job.json": b'{"shop": "shopa"}',
    "scripts/output/journal/deferred-shopa.jsonl": b"",
    "scripts/output/dictionaries/brand.json": b"{}",
    "scripts/output/dictionaries.old/brand.json": b"{}",
    "scripts/output/trial-1/x.json": b"[]" * 100,
    "server/output/listings/page.html": b"<html>" * 300,
    # left out
    "scripts/output/.env": b"SECRET=1",
    f"{SHOP}/publish/token.json": b"{}",
    f"{SHOP}/publish/ledger.jsonl.part": b"half",
    f"{SHOP}/description_images/.lock": b"",
    f"{SHOP}/prepare_cache/1.json": b"{}",
    "scripts/output/jobs/job1/__pycache__/x.pyc": b"",
}
LEFT_OUT = [k for k in TREE if any(s in k for s in (".env", "token", ".part", ".lock", "prepare_cache", "__pycache__"))]


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    for rel, data in TREE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return str(root)


def run(repo, dest, **kw):
    out = io.StringIO()
    code = sb.backup(repo, str(dest), list(kw.pop("phases", sb.PHASES)), kw.pop("part_size", 1 << 30),
                     day="2026-11-16", out=out, **kw)
    return code, out.getvalue()


def files_under(folder):
    out = {}
    for here, _, names in os.walk(folder):
        for n in names:
            path = os.path.join(here, n)
            out[os.path.relpath(path, folder).replace(os.sep, "/")] = open(path, "rb").read()
    return out


def test_phases_by_path():
    assert sb.phase_of(f"{SHOP}/collected/run1/images/1/01.webp") == "photos"
    assert sb.phase_of(f"{SHOP}/collected/run1/products.jsonl") == "state"
    assert sb.phase_of(f"{SHOP}/description_images/cache/1/a.bin") == "description-images"
    assert sb.phase_of(f"{SHOP}/description_images/1.json") == "state"
    assert sb.phase_of("scripts/output/jobs/job1/job.json") == "state"
    assert sb.phase_of("scripts/output/dictionaries/brand.json") == "state"
    assert sb.phase_of("scripts/output/dictionaries.old/brand.json") == "archive"
    assert sb.phase_of("scripts/output/notes.md") == "archive"
    assert sb.phase_of("server/output/listings/page.html") == "server"
    assert sb.phase_of("research/hardening-2026-11/PLAN.md") == "state"      # the plans outside git


def test_backup_verify_restore_round_trip(repo, tmp_path):
    dest = tmp_path / "backup"
    code, text = run(repo, dest)
    assert code == 0, text
    names = sorted(os.listdir(dest))
    assert names == ["01-state-2026-11-16.tar.zst", "02-photos-2026-11-16.tar.zst",
                     "03-description-images-2026-11-16-part01.tar.zst", "04-server-pages-2026-11-16.tar.zst",
                     "05-archive-2026-11-16.tar.zst", "MANIFEST.json", "RESTORE.md"]
    assert "for the cloud:" in text
    out = io.StringIO()
    assert sb.verify(str(dest), out=out) == 0 and "verify: ok" in out.getvalue()
    target = tmp_path / "restored"
    assert sb.restore(str(dest), str(target), list(sb.PHASES), root=repo, out=io.StringIO()) == 0
    expected = {k: v for k, v in TREE.items() if k not in LEFT_OUT}
    assert files_under(target) == expected


def test_left_out_files_are_not_archived_and_are_printed(repo, tmp_path):
    code, text = run(repo, tmp_path / "b")
    assert code == 0
    manifest = json.loads((tmp_path / "b" / "MANIFEST.json").read_text())
    assert sum(e["files"] for e in manifest["archives"]) == len(TREE) - len(LEFT_OUT)
    for rel in (".env", "token.json", "ledger.jsonl.part", "description_images/.lock", "prepare_cache/",
                "__pycache__/"):
        assert rel in text


def test_manifest_sha256_matches_the_files(repo, tmp_path):
    dest = tmp_path / "b"
    run(repo, dest)
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    for e in manifest["archives"]:
        assert e["sha256"] == sb.sha256(str(dest / e["file"]))
        assert e["bytes_out"] == os.path.getsize(dest / e["file"])
    state = next(e for e in manifest["archives"] if e["phase"] == "state")
    assert state["roots"] == ["scripts/output/dictionaries", "scripts/output/jobs", "scripts/output/journal", SHOP]


def test_description_images_split_into_parts_a_product_never_split(repo, tmp_path):
    dest = tmp_path / "b"
    code, _ = run(repo, dest, phases=["description-images"], part_size=6500)
    assert code == 0
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    parts = sorted(manifest["archives"], key=lambda e: e["file"])
    # products 1 (6000), 2 (3000), 3 (7000, bigger than a part, alone)
    assert [(e["part"], e["files"], e["bytes_in"]) for e in parts] == [(1, 2, 6000), (2, 1, 3000), (3, 1, 7000)]
    assert sb.verify(str(dest), out=io.StringIO()) == 0


def test_refuses_a_folder_inside_the_repository(repo):
    code, text = run(repo, os.path.join(repo, "backup"))
    assert code == 2 and "inside the repository" in text
    assert not os.path.exists(os.path.join(repo, "backup"))


def test_dry_run_writes_nothing(repo, tmp_path):
    dest = tmp_path / "b"
    code, text = run(repo, dest, dry_run=True)
    assert code == 0 and "nothing written" in text and "01-state-2026-11-16.tar.zst" in text
    assert not dest.exists()


def test_an_existing_archive_is_never_overwritten(repo, tmp_path):
    dest = tmp_path / "b"
    run(repo, dest, phases=["state"])
    before = (dest / "01-state-2026-11-16.tar.zst").read_bytes()
    code, text = run(repo, dest, phases=["state", "server"])
    assert code == 2 and "never overwritten" in text
    assert (dest / "01-state-2026-11-16.tar.zst").read_bytes() == before
    assert not (dest / "04-server-pages-2026-11-16.tar.zst").exists()


def test_phases_one_by_one_add_to_one_manifest(repo, tmp_path):
    dest = tmp_path / "b"
    run(repo, dest, phases=["state"])
    run(repo, dest, phases=["server"])
    manifest = json.loads((dest / "MANIFEST.json").read_text())
    assert sorted(e["phase"] for e in manifest["archives"]) == ["server", "state"]
    assert sb.verify(str(dest), out=io.StringIO()) == 0


def test_verify_finds_a_changed_archive(repo, tmp_path):
    dest = tmp_path / "b"
    run(repo, dest, phases=["state"])
    path = dest / "01-state-2026-11-16.tar.zst"
    path.write_bytes(path.read_bytes()[:-8] + b"\x00" * 8)
    out = io.StringIO()
    assert sb.verify(str(dest), out=out) == 1 and "sha256 differs" in out.getvalue()


def test_restore_refuses_a_non_empty_folder_and_the_repository(repo, tmp_path):
    dest = tmp_path / "b"
    run(repo, dest, phases=["state"])
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x")
    assert sb.restore(str(dest), str(full), ["state"], root=repo, out=io.StringIO()) == 2
    assert sb.restore(str(dest), repo, ["state"], root=repo, out=io.StringIO()) == 2
    assert sb.restore(str(dest), os.path.join(repo, "scripts"), ["state"], root=repo, out=io.StringIO()) == 2


def test_parse_size():
    assert sb.parse_size("4G") == 4 << 30 and sb.parse_size("500M") == 500 << 20 and sb.parse_size("123") == 123
    with pytest.raises(Exception):
        sb.parse_size("big")


def test_research_goes_in_the_state_archive_and_a_missing_archive_refuses_a_restore(repo, tmp_path):
    """2026-11-16, the phase 0 review: research/ (plans outside git) was in no backup; a restore with an archive
    gone from the folder ended in a traceback."""
    plan = os.path.join(repo, "research", "x", "PLAN.md")
    os.makedirs(os.path.dirname(plan))
    with open(plan, "w") as f:
        f.write("plan")
    dest = tmp_path / "b"
    run(repo, dest, phases=["state"])
    to = tmp_path / "r"
    assert sb.restore(str(dest), str(to), ["state"], root=repo, out=io.StringIO()) == 0
    assert (to / "research" / "x" / "PLAN.md").read_text() == "plan"
    (dest / "01-state-2026-11-16.tar.zst").unlink()
    out = io.StringIO()
    assert sb.restore(str(dest), str(tmp_path / "r2"), ["state"], root=repo, out=out) == 1
    assert "missing" in out.getvalue()
