"""The shop fixture (2026-11-16, the owner: "a fixture copied from real products"): a small real slice of
scripts/output/shops/fairwardgolf and two of its jobs, in the real layout, for the tests of the tools that read a
shop's files (shop_view.resolve / show / query, job_report.py, prepared_diff.py, ...).

    .venv/bin/python -I scripts/make_shop_fixture.py      # again after a deliberate change, then read the git diff

Writes scripts/fixtures/shop/ (everything under it is replaced):
    cases.json                            {key: the case it stands for}, the jobs, when it was made
    shops/fairwardgolf/prepared/products.jsonl            the cases' lines, whole, in the shop file's order
    shops/fairwardgolf/translation/translated.jsonl       the same for translated, placements and the ledger
    shops/fairwardgolf/translation/texts.jsonl            (every history row of a case: the ledger, texts,
    shops/fairwardgolf/translation/descriptions.jsonl      descriptions)
    shops/fairwardgolf/placement/placements.jsonl
    shops/fairwardgolf/publish/published.jsonl
    shops/fairwardgolf/publish/payloads/<id>.json         PAYLOADS only (a dry run's payload)
    shops/fairwardgolf/publish/sent/<id>.json             each case's that the shop has (publish.load_sent: the
                                          store's "before", stage 2, 2026-11-19), whole: its sha256 is the ledger's
    shops/fairwardgolf/translation/<id>/, description_images/<id>.json    PAYLOADS only (describe's blocks)
    shops/fairwardgolf/collected/<run>/products.jsonl + manifest.json   each case's newest collected line, its long
                                          strings and lists cut (TRIM): the keys and types stay; manifest's sha256 is
                                          the cut file's, its source path dropped
Every copied line is scrubbed (scrub): this repository's folder taken out of a path (made relative), a draft
preview link's preview_key replaced by "<removed>".
    jobs/<job>/job.json, now.json, events.jsonl, screened.jsonl         JOBS, whole (shops_root: "<fixture>")

job.json's shops_root is "<fixture>": a test copies the fixture (conftest.py `shop_fixture`) and sets it to the copy.
Reads only the shop's and the jobs' folders (no .env, no photo, no store call); about 1 MB. A case that is gone
from the shop's files stops the script (pick another, change CASES).
"""
import hashlib
import json
import os
import re
import shutil
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import publish  # noqa: E402
import run_transform  # noqa: E402
from shop_files import read_jsonl  # noqa: E402

SHOP = "fairwardgolf"
SRC_SHOPS = os.path.join(HERE, "output", "shops")
SRC_JOBS = os.path.join(HERE, "output", "jobs")
OUT = os.path.join(HERE, "fixtures", "shop")
P = SHOP + ":naver:"
# key -> the case it stands for (what a test may rely on)
CASES = {
    P + "102683547:13552318731": "live (published, ACTIVE by the old shape: no store_status); payload; described; "
                                 "published by job A",
    P + "102454334:13370257430": "live, published by job A, one ledger row",
    P + "102329146:13016112970": "a draft (DRAFT) activated later (ACTIVE, activated); payload; published by job B",
    P + "102682314:13127601930": "withdrawn replaced_by: (job A: not_taken, then published)",
    P + "102770910:12557420063": "withdrawn 'hold: copy of live ...'; in two jobs (A: not_taken duplicate_of, "
                                 "B: published)",
    P + "102709004:12178430576": "agency_no_brand withdrawal, restored, live again with a second handle",
    P + "102642513:12080067974": "agency_no_brand withdrawal, restored, withdrawn again (owner lens review)",
    P + "100416178:5917858699": "restored and activated, 5 ledger rows, no description; in no job here",
    P + "1100167681:13830324906": "live, rehandled twice (three handles in its history)",
    P + "1100167681:13830312765": "live, the same channel as the one above (a sibling, another product id)",
    P + "102750441:13762670577": "prepared held single_only now; was published and withdrawn single_only:",
    P + "101365130:11097352600": "prepared held single_only, never published; not_taken in both jobs",
    P + "101812134:13532274688": "placement unresolved (gender unknown), never published, in no job",
    P + "102697674:13292782760": "not taken: duplicate_of in both jobs; prepared ready, translation pending",
    P + "102206584:13492376357": "not taken: duplicate_of in both jobs (another match each time)",
    P + "102783573:13207840596": "withdrawn replaced_by:, its translation pending",
}
JOBS = {"fairwardgolf-50002783-20261115T150124Z": "job A: wedge sets scroll, stop / waiting / reopen events",
        "fairwardgolf-50002783-20261116T083154Z": "job B: the same category again, done; duplicate_of_withdrawn"}
JOB_FILES = ("job.json", "now.json", "events.jsonl", "screened.jsonl")
PAYLOADS = ("13552318731", "13016112970")
TRIM = {"str": 300, "list": 12}       # a collected line's longer string / list cut to this (details, reviews, ...)


REPO = os.path.dirname(HERE) + os.sep


def scrub(text: str) -> str:
    """No machine path (this repository's folder: relative), no draft preview key (a link that opens a draft)."""
    return re.sub(r"preview_key=[0-9a-f]+", "preview_key=<removed>", text.replace(REPO, ""))


def trim(v: Any) -> Any:
    if isinstance(v, str):
        return v[:TRIM["str"]]
    if isinstance(v, list):
        return [trim(x) for x in v[:TRIM["list"]]]
    if isinstance(v, dict):
        return {k: trim(x) for k, x in v.items()}
    return v


def _key(raw: bytes) -> str | None:
    try:
        return json.loads(raw).get("key")
    except ValueError:                                   # a cut-off last line (read_jsonl allowed it)
        return None


def dump_jsonl(path: str, rows: list[Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(scrub(json.dumps(r, ensure_ascii=False)) + "\n" for r in rows))


def main() -> int:
    src = os.path.join(SRC_SHOPS, SHOP)
    dst = os.path.join(OUT, "shops", SHOP)
    want = set(CASES)
    files = {"prepared/products.jsonl": False, "translation/translated.jsonl": False,
             "placement/placements.jsonl": False, "publish/published.jsonl": True,
             "translation/texts.jsonl": True, "translation/descriptions.jsonl": True}     # path: append-only
    picked: dict[str, list[bytes]] = {}
    for rel, appended in files.items():
        read_jsonl(os.path.join(src, rel), tail_ok=appended)          # a bad line stops here, as in the tools
        with open(os.path.join(src, rel), "rb") as f:
            raw = [x for x in f.read().split(b"\n") if x.strip()]
        picked[rel] = [scrub(x.decode("utf-8")).encode("utf-8") for x in raw   # the lines as written, scrubbed
                       if _key(x) in want]
    missing = want - {_key(x) for x in picked["prepared/products.jsonl"]}
    if missing:
        sys.exit(f"stop: not in the shop's prepared file any more: {sorted(missing)} (change CASES)")
    lines = run_transform.latest_lines(SHOP)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for rel, rows in picked.items():
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        with open(os.path.join(dst, rel), "wb") as fb:
            fb.write(b"".join(x + b"\n" for x in rows))
    for pid in PAYLOADS:
        for rel in (f"publish/payloads/{pid}.json", f"description_images/{pid}.json"):
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copyfile(os.path.join(src, rel), os.path.join(dst, rel))
        if os.path.isdir(os.path.join(src, "translation", pid)):
            shutil.copytree(os.path.join(src, "translation", pid), os.path.join(dst, "translation", pid))
    for key in sorted(want):                        # the store's "before" as sent, byte for byte (no path in it)
        rel = publish.sent_rel(key)
        if os.path.exists(os.path.join(src, rel)):
            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
            shutil.copyfile(os.path.join(src, rel), os.path.join(dst, rel))
    for key in sorted(want):
        if key not in lines:
            continue
        run, _, line = lines[key]
        path = os.path.join(dst, "collected", run, "products.jsonl")
        dump_jsonl(path, [{**trim(line), "key": key}])
        with open(os.path.join(src, "collected", run, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        with open(path, "rb") as f:
            manifest.update(lines=1, sha256=hashlib.sha256(f.read()).hexdigest(), source="<fixture>")
        with open(os.path.join(dst, "collected", run, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
            f.write("\n")
    for job in JOBS:
        os.makedirs(os.path.join(OUT, "jobs", job))
        for name in JOB_FILES:
            s = os.path.join(SRC_JOBS, job, name)
            if not os.path.exists(s):
                continue
            if name == "job.json":
                with open(s, encoding="utf-8") as f:
                    meta = json.load(f)
                meta["shops_root"] = "<fixture>"
                with open(os.path.join(OUT, "jobs", job, name), "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=1)
                    f.write("\n")
            else:
                with open(s, encoding="utf-8") as f, open(os.path.join(OUT, "jobs", job, name), "w",
                                                          encoding="utf-8") as g:
                    g.write(scrub(f.read()))
    with open(os.path.join(OUT, "cases.json"), "w", encoding="utf-8") as f:
        json.dump({"made": "2026-11-16", "shop": SHOP, "cases": CASES, "jobs": JOBS, "payloads": list(PAYLOADS)},
                  f, ensure_ascii=False, indent=1)
        f.write("\n")
    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(OUT) for n in ns)
    print(f"{OUT}: {len(CASES)} cases, {len(JOBS)} jobs, "
          + ", ".join(f"{rel} {len(rows)}" for rel, rows in picked.items()) + f"; {size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
