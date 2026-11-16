"""Offline tests for the shop lock in the commands' main() (shop_files.locked): a command that rewrites a shop's
shared files or sends its products is refused while another process holds the shop (a job), with the busy line and
exit 2, and leaves the files as they were; the read-only or one-append commands still run.

    .venv/bin/python -m pytest scripts/test_shop_lock.py -q
"""
import argparse
import json
import os

import pytest

import job as J
import shop_files

SHOP = "fairwardgolf"
PREPARED = '{"key": "fairwardgolf:naver:100:1", "status": "ready"}\n'


@pytest.fixture
def busy(tmp_path):
    """A shops root with a shop's three rebuilt files, its lock held as a running job holds it."""
    root = tmp_path / "shops"
    row = '{"key": "fairwardgolf:naver:100:1", "status": "x"}\n'
    for rel, text in (("prepared/products.jsonl", PREPARED), ("translation/translated.jsonl", row),
                      ("placement/placements.jsonl", row)):
        (root / SHOP / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / SHOP / rel).write_text(text)
    with shop_files.shop_lock(str(root), SHOP, "job.py run j1"):
        yield str(root)


def _files(root):
    return {rel: open(os.path.join(root, SHOP, rel), "rb").read() for rel in (
        "prepared/products.jsonl", "translation/translated.jsonl", "placement/placements.jsonl")}


def _refused(capsys, tool):
    out = capsys.readouterr()
    assert f"{tool}stop: {SHOP} is busy: job.py run j1 (pid {os.getpid()}, since " in out.out + out.err
    assert "wait for it (job.py status) or stop it" in out.out


def test_translate_and_placement_are_refused_and_leave_the_files(busy, capsys):
    import placement
    import translate
    before = _files(busy)
    assert translate.main([SHOP, "--shops-root", busy, "--offline"]) == 2
    _refused(capsys, "translate: ")
    assert placement.main([SHOP, "--shops-root", busy]) == 2
    _refused(capsys, "placement: ")
    assert _files(busy) == before


def test_run_transform_and_description_images_are_refused(busy, capsys, monkeypatch):
    import description_images
    import run_transform
    monkeypatch.setattr(run_transform, "SHOPS_ROOT", busy)
    monkeypatch.setattr(description_images, "SHOPS_ROOT", busy)
    before = _files(busy)
    assert run_transform.main([SHOP]) == 2
    _refused(capsys, "run_transform: ")
    assert description_images.main([SHOP]) == 2
    _refused(capsys, "description_images: ")
    assert _files(busy) == before


def test_publish_sending_is_refused_its_dry_run_is_not(busy, capsys, monkeypatch):
    import publish
    assert publish.main([SHOP, "--shops-root", busy]) == 2
    _refused(capsys, "publish: ")
    monkeypatch.setattr(publish, "offline_ids", lambda shop: {"vendors": {}, "tenant": "T"})
    assert publish.main([SHOP, "--shops-root", busy, "--dry-run", "--only", "nosuchkey"]) == 0
    assert "publish fairwardgolf: 0 products" in capsys.readouterr().out


def test_publish_withdraw_is_not_locked(busy, monkeypatch):
    """The owner withdraws by hand while a job runs: one ledger line through append_line."""
    import publish
    import shopify_admin
    shop = publish.Shop(SHOP, busy)
    publish._append(shop.ledger_path, {"format": publish.FORMAT, "key": "k1", "status": "published",
                                       "product_id": "gid://1", "handle": "h"})

    class Admin:
        def __init__(self, store):
            pass

        def check_shop(self):
            pass

        def set_status(self, product_id, status):
            return status
    monkeypatch.setattr(shopify_admin, "ProductsAdmin", Admin)
    assert publish.main([SHOP, "--shops-root", busy, "--withdraw", "k1", "--reason", "x"]) == 0
    assert shop.withdrawn() == {"k1"}


def test_describe_with_a_model_reprice_apply_and_store_diff_adopt_are_refused(busy, capsys):
    import describe
    import reprice
    import store_diff
    assert describe.main([SHOP, "--shops-root", busy]) == 2
    _refused(capsys, "describe: ")
    assert reprice.main([SHOP, "--shops-root", busy, "--apply"]) == 2
    _refused(capsys, "reprice: ")
    assert store_diff.main([SHOP, "--shops-root", busy, "--adopt"]) == 2
    _refused(capsys, "store_diff: ")


def _job(root, jobs):
    folder = jobs / "j2"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(json.dumps({"shop": SHOP, "category": "50002788", "paid": False,
                                                 "reviews": 20, "shops_root": root}))
    (folder / "listing.jsonl").write_text("")
    return folder


def test_a_second_runner_of_the_shop_is_refused_and_writes_nothing(busy, tmp_path, capsys):
    folder = _job(busy, tmp_path / "jobs")
    assert J.cmd_run(argparse.Namespace(job=str(folder), items=0)) == 2
    _refused(capsys, "")
    assert J.cmd_refresh(argparse.Namespace(job=str(folder), more=50)) == 2
    _refused(capsys, "")
    assert sorted(os.listdir(folder)) == ["job.json", "listing.jsonl"]           # no event, no now.json


def test_a_new_scroll_job_refused_makes_no_job_folder(busy, capsys, monkeypatch):
    monkeypatch.setattr(J, "new_scroll_job", lambda *a, **k: pytest.fail("a job folder made"))
    args = argparse.Namespace(job=None, query="q", category="50002788", count=0, paid=False, paid_variants=False,
                              reviews=20, exclude_known=False, shops_root=busy, no_translate=True, publish=False,
                              describe=False, dedupe="off")
    assert J.cmd_scroll(args) == 2
    _refused(capsys, "")
