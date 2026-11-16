"""The visual lenses' regression fixture (2026-11-15): real records of the cases the lenses were built on, cut to what
shop_view.py, lens.py and dedupe.py read, into fixtures/lens/cases.json. test_lens_fixture.py rebuilds a shop and
two jobs from it in a tmp folder (photos drawn there: no seller photo is kept in git) and pins what each lens shows.

    .venv/bin/python -I scripts/make_lens_fixture.py          # again after a deliberate change, then read the diff

Reads scripts/output/shops/fairwardgolf (prepared, translation, placement, publish, collected) and
scripts/output/jobs (events): offline. A collected line is kept only for COLLECTED (dedupe's BG-100 and REVA groups, a held
product, a duplicate pair), cut to the listing, photos' hashes, variants and the origin / agency rows.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import run_transform  # noqa: E402
from shop_view import JOBS_ROOT, SHOPS_ROOT, jsonl  # noqa: E402

SHOP = "fairwardgolf"
# product id -> why it is here (what a lens must show for it)
CASES = {
    "13127601930": "wedge set published, brand from the specs (Bermuda)",
    "13016152694": "wedge set published under the shop's name (brand none)",
    "12731471202": "the cheapest wedge 'set' at ₩89,000: price lens flags the foot",
    "12951827729": "a wedge set or a single (Yamato 'or individual'), brand title_known",
    "5305572105": "MacGregor NV201 two wedges at ₩99,000",
    "11097352600": "prepared but held single_only (mirai MW-25)",
    "12178049211": "not taken: placement held single_only, never published",
    "13292782760": "not taken: duplicate_of a published BombTech (prepared on an earlier run)",
    "13619604371": "the published BombTech the duplicate matched",
    "13619939279": "GoSports kept copy, later withdrawn: a duplicate_of a withdrawn product",
    "8958060680": "BG-100 white, PREMIUM 98 reviews: the kept copy",
    "12215613033": "BG-100 copy withdrawn replaced_by the kept one",
    "13785630702": "BG-100 Black Edition, same seller as the kept one: left live on purpose",
    "13809756465": "BG-100 black of another seller, grouped by title words only with a white set",
    "13827555559": "BG-100 white, the other half of that title-only pair",
    "13325799991": "REVA 2025 clubs only, PREMIUM: kept",
    "11989527841": "REVA 2025 'clubs only' copy, withdrawn replaced_by",
    "11989518458": "REVA 2025 with its bags: same title words, another product",
    "13261457036": "not taken: duplicate_of GoSports 13619939279, a match withdrawn since (held lens: red)",
    "12921931106": "the second Yamato 'set or single' import: every variant one wedge on two axes (Size, Style Name)",
    "13405976594": "A11N SPORTS wedge set, a copy by every photo and variant (dedupe strong route)",
    "13552318731": "A11N SPORTS wedge set, the kept copy of the three (SPROUT)",
    "13207840596": "the same A11N set under its model line 핀클리 (vendor Finchley, title with u2013)",
    "4385835200": "junior set with age options, paid shipping",
    "13770121877": "a woodwork bar clamp live among junior sets (brand none): section lens must show it",
    "13475342948": "junior set, brand title_word (Elevon)",
    "13324729995": "junior set, brand description_row",
}
JOBS = ["fairwardgolf-50002783-20261115T150124Z", "fairwardgolf-50002787-20261112T155753Z",
        "fairwardgolf-50002670-20261115T045151Z",
        "fairwardgolf-50002788-20261113T043522Z"]      # two failed at translate (an option too long), never published
EXTRA_REASONS = ("card_not_found", "title:not_golf", "category_mismatch")   # a real line of each, keys kept as found
EXTRA_EVENTS = ("failed", "deferred")          # the first of each in a job, with every event of its key
COLLECTED = ("8958060680", "12215613033", "13785630702", "13809756465", "13827555559", "13325799991", "11989527841",
             "11989518458",                    # dedupe's groups
             "11097352600",                    # a held product: its options come from the collected line
             "13261457036", "13619939279",     # a duplicate and its match: the pair's signals
             "13405976594", "13552318731", "13207840596")   # one A11N set under three titles (dedupe.strong)


def cut_prepared(r):
    prod = r.get("product") or {}
    return {"key": r["key"], "status": r.get("status"), "held": r.get("held") or [],
            "source": {k: (r.get("source") or {}).get(k) for k in ("category_id", "channel_no", "product_id", "link")},
            "texts": [t for t in r.get("texts") or [] if t.get("kind") == "title"],
            "product": {"title_ko": prod.get("title_ko"), "brand_ko": prod.get("brand_ko"),
                        "brand_source": prod.get("brand_source"),
                        "pricing": {"base_krw": (prod.get("pricing") or {}).get("base_krw")},
                        "options": prod.get("options") or [],
                        "variants": [{"options_ko": v.get("options_ko"), "price_krw": v.get("price_krw")}
                                     for v in prod.get("variants") or []],
                        "images": [{"file": i.get("file"), "position": i.get("position")} for i in prod.get("images") or []]}}


def cut_translated(r):
    return {"key": r["key"], "status": r.get("status"),
            "en": {k: v for k, v in (r.get("en") or {}).items() if k.startswith(("title:", "brand:"))}}


def cut_collected(line):
    listing, specs = line.get("listing") or {}, line.get("specs") or {}
    return {"key": line["key"],
            "listing": {k: listing.get(k) for k in ("key", "product_id", "name", "category_id", "pricing", "store",
                                                     "reviews")},
            # the rows dedupe reads for an agency import (구매대행: an 인증정보 or 원산지 row), the others left out
            "specs": {"specs": [s for s in specs.get("specs") or [] if any(w in json.dumps(s, ensure_ascii=False)
                                                                              for w in ("원산지", "구매대행", "구매 대행"))]},
            "photos": {"files": [{"position": f.get("position"), "source_sha256": f.get("source_sha256")}
                                 for f in (line.get("photos") or {}).get("files") or []]},
            "variants": {"variants": [{"options": v.get("options"), "name": v.get("name")}
                                      for v in (line.get("variants") or {}).get("variants") or []]}}


def main():
    shop_dir = os.path.join(SHOPS_ROOT, SHOP)
    def by_pid(rows):
        return {r["key"].split(":")[3]: r for r in rows if r.get("key")}
    prepared = by_pid(jsonl(os.path.join(shop_dir, "prepared", "products.jsonl")))
    translated = by_pid(jsonl(os.path.join(shop_dir, "translation", "translated.jsonl")))
    placed = by_pid(jsonl(os.path.join(shop_dir, "placement", "placements.jsonl")))
    ledger = jsonl(os.path.join(shop_dir, "publish", "published.jsonl"))
    keys = {}
    events = {}
    for job in JOBS:
        evs = jsonl(os.path.join(JOBS_ROOT, job, "events.jsonl"))
        for e in evs:
            k = e.get("key") or ""
            if k.split(":")[-1] in CASES:
                keys[k.split(":")[-1]] = k
        extra_keys = set()
        published = {e.get("key") for e in evs if e.get("event") == "published"}
        for kind in EXTRA_EVENTS:      # one that recovered (published later) and one that never did, when the job has
            for recovered in (True, False):
                hit = next((e for e in evs if e.get("event") == kind and (e.get("key") in published) == recovered),
                           None)
                if hit:
                    extra_keys.add(hit["key"])
        picked = [e for e in evs if (e.get("key") or "").split(":")[-1] in CASES or e.get("key") in extra_keys]
        for reason in EXTRA_REASONS:
            hit = next((e for e in evs if e.get("event") == "not_taken" and str(e.get("reason", "")).startswith(reason)),
                       None)
            if hit and hit not in picked:
                picked.append(hit)
        events[job] = [{k: v for k, v in e.items() if k != "matches"} for e in picked]
    for pid in CASES:
        for src in (prepared, translated, placed):
            if pid in src:
                keys.setdefault(pid, src[pid]["key"])
        keys.setdefault(pid, next((r["key"] for r in ledger if (r.get("key") or "").endswith(":" + pid)), None))
    missing = [pid for pid, k in keys.items() if not k] + [pid for pid in CASES if pid not in keys]
    if missing:
        sys.exit(f"stop: not found in the shop's files: {missing}")
    want = set(keys.values())
    dedupe_keys = {keys[p] for p in COLLECTED}
    lines = run_transform.latest_lines(SHOP)
    out = {"made": "2026-11-15", "shop": SHOP, "cases": {keys[p]: why for p, why in CASES.items()},
           "prepared": [cut_prepared(prepared[p]) for p in CASES if p in prepared],
           "translated": [cut_translated(translated[p]) for p in CASES if p in translated],
           "placements": [{k: placed[p].get(k) for k in ("key", "status", "leaves", "product_type")}
                          for p in CASES if p in placed],
           "ledger": [{k: r.get(k) for k in ("key", "status", "reason", "handle", "admin_url", "at")}
                      for r in ledger if r.get("key") in want],
           "collected": [cut_collected(lines[k][2]) for k in sorted(dedupe_keys) if k in lines],
           "events": events}
    path = os.path.join(HERE, "fixtures", "lens", "cases.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{path}: {len(out['cases'])} cases, {len(out['prepared'])} prepared, {len(out['ledger'])} ledger rows, "
          f"{len(out['collected'])} collected lines, {sum(len(v) for v in events.values())} events")


if __name__ == "__main__":
    main()
