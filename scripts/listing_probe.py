"""A listing probe before a category or a section is added, and after its title screen changes (the owner,
2026-11-22: "the flow of adding a category probes the listings: search keywords, the words in the titles, the
filters and the adjacent category ids; the agent decides, the operator is asked only when the agent is unsure").

    .venv/bin/python scripts/listing_probe.py --category 50002796 --leaf mens-fall-long-sleeve-tops \\
        --query "남성 골프 가을 긴팔 티셔츠" --query "남성 골프 긴팔 카라티" [--batches 3] [--alt-rules FILE]

For each query the server reads the listing the jobs read (POST /listings: the owner's Chrome, sorted 리뷰 많은순, the
first --batches batches; one adapter user: never while a job runs, 409) with the page's own filters. Per query:
  * where the products are: the rows by Naver category (the leaf, the categories `together` takes, the others with
    their paths from the page's category tree), the adjacent leaves of the tree (ids to look at);
  * the screen of the section (listing_filter.title_rule with the category's rules for --leaf): kept, every reason
    with its count and example titles; the same rules on the rows of the OTHER categories (would they fit?);
  * --alt-rules (a JSON list of rules for the same category, e.g. a wider required group): its counts and the
    titles it adds or drops against today's rules;
  * the reviews of the kept rows (median, none), the sellers' attributes the page offers (특징: 긴팔 / 반팔 ...),
    the default order's size against the sorted one;
  * flags for the agent (`attention`): see FLAGS. A flag is a question for the agent first; it asks the operator
    only when the probe cannot settle it (ONBOARDING.md "B0. Probe the listing").

Contact sheets (the owner, 2026-11-22: the agent judges by eye whether its probes fit the category, the adjacent
leaves first): per query <folder>/q<n>/sheet*.jpg and index.tsv, the listing cards' own photos (Naver's image CDN, a 300 px
rendition) in groups: "kept" (grey), each reason of the screen (red: did it drop what fits?), each other leaf
(blue: its rows the screen would keep; red: the rest), with index.tsv; --no-sheets skips them. The agent looks at
every sheet and writes its verdict in <folder>/decision.md (ONBOARDING.md "B0. Probe the listing").

Read only for the shop: nothing is collected, prepared or published. Output: scripts/output/probes/<category>-<leaf or
default>-<UTC>/probe.json and report.md, the path printed. Exit 0; 2 on bad arguments; 3 when the server refused.
"""
import argparse
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import listing_filter as LF
import sheet as S
from naver_api_client import ApiError, NaverApiClient

OUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "probes")
EXAMPLES = 6
# when the agent looks closer before it decides (and asks the operator only if the look settles nothing)
KEPT_LOW = 0.5            # under half of the query's rows in the category kept: the query or the rules miss
ADJACENT_SHARE = 0.2      # another category holds this share of the rows and its titles pass the screen
REQUIRE_SHARE = 0.25      # a `requires` rule drops this share of the category's rows: the required words miss
FLAGS = ("kept_low", "adjacent_category", "requires_drops", "attribute_filter", "off_category")


def _row_category(row: dict[str, Any]) -> str:
    return str(row.get("category_id") or "")


def analyze(rows: list[dict[str, Any]], filters: dict[str, Any] | None, category: str, leaf: str | None,
            rules: list[dict[str, Any]] | None = None, alt_rules: list[dict[str, Any]] | None = None,
            totals: dict[str, Any] | None = None) -> dict[str, Any]:
    """One query's rows and filters -> the probe's findings (pure; the tests call it with fixture rows)."""
    rules = LF.title_rules(category, leaf=leaf) if rules is None else rules
    taken = {category, *LF.together(category)}
    paths = {c["id"]: " > ".join(c.get("path") or []) for c in (filters or {}).get("categories") or []}
    by_cat = Counter(_row_category(r) for r in rows)
    mine = [r for r in rows if _row_category(r) in taken]
    others = [r for r in rows if _row_category(r) not in taken]

    def screen(sample: list[dict[str, Any]], with_rules: list[dict[str, Any]]) -> dict[str, Any]:
        reasons: Counter[str] = Counter()
        examples: dict[str, list[str]] = {}
        kept = []
        for r in sample:
            code = LF.title_rule(r.get("name"), with_rules) or "kept"
            reasons[code] += 1
            examples.setdefault(code, [])
            if len(examples[code]) < EXAMPLES:
                examples[code].append(str(r.get("name") or "")[:90])
            if code == "kept":
                kept.append(r)
        return {"rows": len(sample), "kept": len(kept), "reasons": dict(reasons.most_common()),
                "examples": examples, "_kept": kept}

    today = screen(mine, rules)
    reviews = [int(((r.get("reviews") or {}).get("count")) or 0) for r in today["_kept"]]
    out: dict[str, Any] = {
        "rows": len(rows), "in_category": len(mine), "totals": totals or {},
        "categories": [{"id": c, "rows": n, "path": paths.get(c), "taken": c in taken} for c, n in by_cat.most_common()],
        "adjacent": [{"id": c["id"], "path": " > ".join(c["path"])} for c in (filters or {}).get("categories") or []
                     if c.get("depth") == 4 and c["id"] not in taken],
        "attributes": [a["name"] for a in (filters or {}).get("attributes") or []],
        "screen": {k: v for k, v in today.items() if not k.startswith("_")},
        "kept_reviews": {"median": statistics.median(reviews) if reviews else 0,
                         "none": sum(1 for x in reviews if not x)},
        "others_screen": {c: {k: v for k, v in screen([r for r in others if _row_category(r) == c], rules).items()
                              if k in ("rows", "kept", "examples")} for c in {_row_category(r) for r in others}},
    }
    if alt_rules is not None:
        alt = screen(mine, alt_rules)
        now = {r.get("name") for r in today["_kept"]}
        then = {r.get("name") for r in alt["_kept"]}
        out["alt"] = {**{k: v for k, v in alt.items() if not k.startswith("_")},
                      "added": sorted(str(t)[:90] for t in then - now)[:40],
                      "dropped": sorted(str(t)[:90] for t in now - then)[:40]}
    out["attention"] = attention(out, rules)
    return out


def attention(found: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The flags of one query's findings: what the agent looks at before it decides."""
    flags = []
    screen = found["screen"]
    if screen["rows"] and screen["kept"] / screen["rows"] < KEPT_LOW:
        flags.append({"flag": "kept_low", "why": f"{screen['kept']} of {screen['rows']} rows of the category kept: "
                      "read the reasons' examples: the query brings another kind, or a rule drops what fits"})
    requires = {f"title:{r['code']}" for r in rules if r.get("requires")}
    for code, n in screen["reasons"].items():
        if code in requires and screen["rows"] and n / screen["rows"] >= REQUIRE_SHARE:
            flags.append({"flag": "requires_drops", "why": f"{code} drops {n} of {screen['rows']}: read its examples; "
                          "a fitting title the required words miss -> widen the group (try --alt-rules)"})
    for cat, got in found["others_screen"].items():
        if found["rows"] and got["rows"] / found["rows"] >= ADJACENT_SHARE and got["kept"]:
            path = next((c["path"] for c in found["categories"] if c["id"] == cat), None)
            flags.append({"flag": "adjacent_category", "why": f"{cat} ({path}) holds {got['rows']} of the "
                          f"{found['rows']} rows, {got['kept']} pass the screen: the same goods under another leaf "
                          "(`together`, or a section of its own)"})
    if found["attributes"]:
        flags.append({"flag": "attribute_filter", "why": "the page offers the sellers' attributes "
                      f"({', '.join(found['attributes'][:8])}): one may say what the title words guess (sleeve, "
                      "fibre, model year); the screen does not read them yet"})
    if found["rows"] and found["in_category"] / found["rows"] < KEPT_LOW:
        flags.append({"flag": "off_category", "why": f"only {found['in_category']} of {found['rows']} rows are in "
                      "the category: the query belongs elsewhere, or the category is the wrong leaf"})
    return flags


THUMB = "?type=f300"     # a 300 px rendition of the listing card's photo (shopping-phinf)


def cards(rows: list[dict[str, Any]], category: str, rules: list[dict[str, Any]]) -> list[S.Card]:
    """The query's rows as sheet cards, grouped: kept, each reason, each other leaf (blue: the screen keeps it)."""
    taken = {category, *LF.together(category)}
    out = []
    for r in rows:
        code = LF.title_rule(r.get("name"), rules)
        cat = _row_category(r)
        if cat in taken:
            group, mark = (code or "kept"), (None if code is None else "flag")
        else:
            group, mark = f"other leaf {cat}", ("info" if code is None else "flag")
        reviews = int(((r.get("reviews") or {}).get("count")) or 0)
        out.append(S.Card(n=0, key=str(r.get("product_id") or ""), photos=[], group=group, mark=mark,
                          lines=[f"{cat} · {reviews} reviews", str(r.get("name") or "")[:60], code or ""],
                          data={"name": r.get("name"), "category_id": cat, "reason": code or "kept",
                                "reviews": reviews, "image": r.get("image"), "link": r.get("link")}))
    order = {"kept": 0}
    out.sort(key=lambda c: (order.get(c.group or "", 1 if not str(c.group).startswith("other") else 2), str(c.group)))
    for i, c in enumerate(out, 1):
        c.n = i
    return out


def draw(query_cards: list[S.Card], folder: str, prefix: str, fetch: Any = None) -> list[str]:
    """The cards' photos fetched once into <folder>/images/, the sheets drawn -> their paths."""
    import naver_images
    fetch = fetch or naver_images.fetch
    os.makedirs(os.path.join(folder, "images"), exist_ok=True)
    session = naver_images.new_session()
    for c in query_cards:
        url = c.data.get("image")
        path = os.path.join(folder, "images", f"{c.key}.jpg")
        if url and not os.path.exists(path):
            try:
                _, _, data, _ = fetch(str(url).split("?")[0] + THUMB, session=session)
                with open(path, "wb") as f:
                    f.write(data)
            except Exception as e:                  # noqa: BLE001: a missing photo draws "no photo"
                print(f"listing_probe: photo of {c.key}: {e}")
        c.photos = [path if os.path.exists(path) else None]
    sheets = S.grid(query_cards, folder, prefix=prefix, label_lines=3)
    S.write_index(query_cards, folder, ["name", "category_id", "reason", "reviews", "link"], {"prefix": prefix})
    return sheets


def report(category: str, leaf: str | None, probes: dict[str, dict[str, Any]]) -> str:
    """The findings as a short Markdown report for the agent and the operator."""
    lines = [f"# Listing probe: {category} {leaf or '(default section)'}", ""]
    for query, f in probes.items():
        s = f["screen"]
        t = f.get("totals") or {}
        lines += [f"## {query}", "",
                  f"- rows read: {f['rows']} (sorted total {t.get('sorted')}, default order {t.get('default')}); "
                  f"in the category: {f['in_category']}; kept by the screen: {s['kept']} of {s['rows']}; kept reviews "
                  f"median {f['kept_reviews']['median']}, none {f['kept_reviews']['none']}",
                  "- by category: " + "; ".join(f"{c['id']} {c['path'] or ''} {c['rows']}{' (taken)' if c['taken'] else ''}"
                                                 for c in f["categories"]),
                  "- reasons: " + ", ".join(f"{k} {v}" for k, v in s["reasons"].items())]
        for code, ex in s["examples"].items():
            lines.append(f"  - {code}: " + " | ".join(ex))
        if f.get("alt"):
            a = f["alt"]
            lines += [f"- alt rules: kept {a['kept']} of {a['rows']}; adds {len(a['added'])}, drops {len(a['dropped'])}"]
            lines += [f"  - + {t}" for t in a["added"][:15]] + [f"  - - {t}" for t in a["dropped"][:15]]
        if f["attributes"]:
            lines.append("- the page's attributes: " + ", ".join(f["attributes"]))
        if f["adjacent"]:
            lines.append("- adjacent leaves: " + "; ".join(f"{a['id']} {a['path']}" for a in f["adjacent"][:20]))
        for flag in f["attention"]:
            lines.append(f"- **{flag['flag']}**: {flag['why']}")
        if f.get("sheets"):
            lines.append("- sheets: " + ", ".join(os.path.relpath(x, os.path.dirname(os.path.dirname(x)))
                                                   for x in f["sheets"]))
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--category", required=True)
    p.add_argument("--leaf", help="the section (listing_title_rules.json `leaves`); none: the default section")
    p.add_argument("--query", action="append", required=True, help="a query the jobs would read (repeat)")
    p.add_argument("--batches", type=int, default=3, help="sorted batches read per query (~48 rows each)")
    p.add_argument("--alt-rules", help="a JSON list of rules for the category, compared with today's")
    p.add_argument("--out", default=OUT_ROOT)
    p.add_argument("--no-sheets", action="store_true", help="no contact sheets (no photo is fetched)")
    a = p.parse_args(argv)
    if a.leaf and a.leaf not in LF.leaves_of(a.category):
        print(f"stop: --leaf {a.leaf}: no such section of {a.category}")
        return 2
    alt = None
    if a.alt_rules:
        with open(a.alt_rules, encoding="utf-8") as f:
            alt = json.load(f)
    api = NaverApiClient()
    probes = {}
    rows_of: dict[str, list[dict[str, Any]]] = {}
    for query in a.query:
        try:
            got = api.listing(query, max_batches=a.batches)
        except ApiError as e:
            print(f"stop: the server refused the listing for {query!r}: {e.status} {e.error}")
            return 3
        job = got["job"]
        rows = rows_of[query] = [dict(r) for r in got["results"]]
        page = job.get("filters")
        filters = dict(page) if page is not None else None
        probes[query] = analyze(rows, filters, a.category, a.leaf, alt_rules=alt,
                                totals={"sorted": job.get("total"), "default": job.get("default_total"),
                                        "sort": job.get("sort"), "stop": job.get("stop")})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = os.path.join(a.out, f"{a.category}-{a.leaf or 'default'}-{stamp}")
    os.makedirs(folder, exist_ok=True)
    if not a.no_sheets:
        rules = LF.title_rules(a.category, leaf=a.leaf)
        for i, (query, rows) in enumerate(rows_of.items(), 1):
            probes[query]["sheets"] = draw(cards(rows, a.category, rules), os.path.join(folder, f"q{i}"), "sheet")
    with open(os.path.join(folder, "probe.json"), "w", encoding="utf-8") as f:
        json.dump({"category": a.category, "leaf": a.leaf, "queries": probes}, f, ensure_ascii=False, indent=1)
    text = report(a.category, a.leaf, probes)
    with open(os.path.join(folder, "report.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"-> {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
