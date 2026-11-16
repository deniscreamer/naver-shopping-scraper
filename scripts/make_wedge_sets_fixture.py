"""The wedge-sets fixture (2026-11-16): every listing of Naver category 50002783 (wedge sets) the shop has collected,
cut to what transform.not_wedge_set reads (the title and the variant rows' option values, as options_and_variants
sees them: the category's paid_variants, its choice, the delivery-note / contact rows left out) plus its state at the
time (prepared status, held codes, store state), into fixtures/wedge_sets/50002783.json. test_wedge_sets.py pins which
of them the rule holds by key: the iron sets and the full sets filed under wedges, and none of the real wedge sets.
The state columns are a snapshot (first made 2026-11-16, before the rule): the tests read them only to name the
listings published then; a regeneration after the rule is live or after a withdrawal changes them and the tests
still hold (they pin keys, not counts).

    .venv/bin/python -I scripts/make_wedge_sets_fixture.py        # again after a deliberate change, then read the diff

Reads scripts/output/shops/fairwardgolf (collected, prepared, the ledger): offline. Titles and option values only:
no photo, no description, no seller's contact.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import run_transform  # noqa: E402
import transform  # noqa: E402
from transform_shops import rules_for  # noqa: E402
from description_clean import decode_line  # noqa: E402
from naver_variants import choose_variants  # noqa: E402
from shop_view import ShopFiles, fields  # noqa: E402

SHOP, CATEGORY = "fairwardgolf", "50002783"
OUT = os.path.join(HERE, "fixtures", "wedge_sets", f"{CATEGORY}.json")


def main() -> int:
    files = ShopFiles(SHOP)
    paid = rules_for(SHOP).categories[CATEGORY].paid_variants
    out = []
    for key, (_, _, raw) in sorted(run_transform.latest_lines(SHOP).items()):
        line = decode_line(raw)
        details, specs = line.get("details") or {}, line.get("specs") or {}
        if not details or str((specs.get("category") or {}).get("id")) != CATEGORY:    # the transform's category
            continue
        options = specs.get("options")
        variants = choose_variants(options, details["pricing"]["discounted_price"], paid=paid)["variants"] \
            if options else []
        chosen = [tuple(r.get("options") or []) for r in variants or [] if r.get("options")]
        real = [r for r in chosen                    # as options_and_variants: no delivery-note / contact row
                if not any(transform._DELIVERY_NOTE_RE.search(v) or transform._contact_only(v) for v in r)]
        rows = list(dict.fromkeys(real or chosen))
        f = fields(files, key)
        out.append({"key": key, "title": re.sub(r"\s+", " ", details.get("name") or ""),
                    "rows": [list(r) for r in rows], "prepared": f["prepared"], "held": f["held"],
                    "state": f["state"]})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n]\n")
    print(f"{len(out)} listings -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
