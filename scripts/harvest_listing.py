"""Listing harvester: every Naver store product for a keyword (+ category),
past the search's 96-card ceiling, as JSONL of product links for the detail
stage. No details are fetched here, so no Chrome is needed: /products/count
and /products/search are both plain HTTP on the server.

Why price slicing: /products/search answers at most 96 cards (the ns-portal
widget's 4 pages x 24, server/naver_shopping/api.py SEARCH_MAX_CARDS) and has
no deeper paging. Worse, the widget returns FULL pages of 24 only: a slice
matching 45 answers 24 cards, 67 answers 48, 77 answers 72; under 24 it
answers all (probed live 2026-11-01 on 남성 골프채 풀세트 / 50002788: a 0-19,073
slice gave 24 of 45, its three sub-slices gave 24 + 3 + 18 = all 45). So a
slice is done only when its cards reach its total_count; otherwise the range
is split into up to SPLIT_WAYS equal, inclusive, disjoint parts and each part
is searched again. Cards from every search are kept (deduplicated by product
id), so no call is wasted. One call per slice: /products/search carries the
slice's total_count. A one-price slice that still answers fewer cards than
its total cannot be split: it is reported as saturated (coverage there is
partial).

Only Naver store products are kept (example_search_harvest.classify_card):
smartstore.naver.com / brand.naver.com cards, written with the canonical
`<store.link>/products/<product_id>` link that /products/details takes.
Catalog cards (price-comparison pages) and external malls (Coupang, Gmarket,
11st, ...) are dropped and only counted.

Output, under scripts/output/<run>/:
  listing.jsonl  one line per unique product: {product_id, link, name, store,
                 pricing, category_id, reviews, purchase_count, image, query,
                 slice, seen_at, card}; card is the raw search card.
  state.json     the checkpoint: pending ranges, finished slices, saturated
                 slices, counters. Rerun with the same --out to resume.

Calls are sequential with --delay between them (default 3 s): the server
keeps one curl session per thread and Naver answers 418/429 to bursts.
--max-requests bounds one run; the rest stays pending in state.json.

    .venv/bin/python scripts/harvest_listing.py "남성 골프채 풀세트" --category 50002788 --out golf-mens
    .venv/bin/python scripts/harvest_listing.py "여성 골프채 풀세트" --category 50002788 --out golf-womens --max-requests 100
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

from example_search_harvest import classify_card
from naver_api_client import NaverApiClient

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
SEARCH_MAX_CARDS = 96                # server/naver_shopping/api.py SEARCH_MAX_CARDS
PAGE_CARDS = 24                      # the widget answers whole pages of 24 only
SPLIT_WAYS = 8                       # most parts one oversized slice is cut into
MAX_PRICE = 9_999_999_999            # server/naver_shopping/api.py OPEN_MAX_PRICE


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- rows (pure, tested offline) --------------------------------------------------------

def listing_row(card, link, query, price_range):
    store = card.get("store") or {}
    images = card.get("images") or []
    return {
        "product_id": str(card.get("product_id")),
        "link": link,
        "name": card.get("name"),
        "store": {"name": store.get("name"), "id": store.get("id"), "link": store.get("link"),
                  "is_brand_store": store.get("is_brand_store")},
        "pricing": card.get("pricing"),
        "category_id": (card.get("category") or {}).get("id"),
        "reviews": card.get("reviews"),
        "purchase_count": card.get("purchase_count"),
        "image": images[0] if images else None,
        "query": query,
        "slice": list(price_range),
        "seen_at": _now(),
        "card": card,
    }


def split_range(a, b, total):
    """[a, b] -> up to SPLIT_WAYS equal, inclusive, disjoint parts, enough
    for every part to fit one 24-card page if prices were spread evenly."""
    ways = max(2, min(SPLIT_WAYS, -(-total // PAGE_CARDS), b - a + 1))
    step = (b - a + 1) / ways
    edges = [a + round(step * i) for i in range(ways)] + [b + 1]
    return [[lo, hi - 1] for lo, hi in zip(edges, edges[1:]) if lo <= hi - 1]


def skip_reason(card):
    """A short bucket for the run summary: catalog / external / other."""
    if (card or {}).get("type") == "catalog":
        return "catalog"
    _, _, reason = classify_card(card)
    return "external" if reason and reason.startswith("external") else "other"


# ---- checkpoint -------------------------------------------------------------------------

def new_state(query, category, lo, hi):
    return {"query": query, "category": category, "range": [lo, hi], "pending": [[lo, hi]],
            "slices": [], "saturated": [], "requests": 0, "kept": 0,
            "skipped": {"catalog": 0, "external": 0, "other": 0}, "skipped_ids": [], "created_at": _now()}


def load_state(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    state["updated_at"] = _now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)            # never leave a half-written checkpoint


def load_seen(path):
    seen = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["product_id"])
                except (ValueError, KeyError):
                    continue         # a line cut off by an interrupted run
    return seen


# ---- run --------------------------------------------------------------------------------

def harvest_listing(api, query, out_dir, category=None, lo=0, hi=MAX_PRICE, delay=3, max_requests=0,
                    sleep=time.sleep):
    os.makedirs(out_dir, exist_ok=True)
    state_path = os.path.join(out_dir, "state.json")
    listing_path = os.path.join(out_dir, "listing.jsonl")
    state = load_state(state_path)
    if state is None:
        state = new_state(query, category, lo, hi)
    elif (state["query"], state["category"]) != (query, category):
        raise SystemExit(f"listing: {out_dir} holds {state['query']!r} / {state['category']}; use another --out")
    seen = load_seen(listing_path)
    skipped_ids = set(state["skipped_ids"])
    params = {"query": query, "category": category}
    budget = [0]

    def call(path, **extra):
        if budget[0]:
            sleep(delay)
        budget[0] += 1
        state["requests"] += 1
        return api.get(path, **params, **extra)

    print(f"listing: {query!r} category={category} -> {listing_path} ({len(seen)} already kept, "
          f"{len(state['pending'])} ranges pending)")
    while state["pending"]:
        if max_requests and budget[0] >= max_requests:
            print(f"listing: request budget {max_requests} spent, {len(state['pending'])} ranges pending; "
                  f"rerun with --out to resume")
            break
        a, b = state["pending"].pop()
        answer = call("/products/search", min_price=a, max_price=b)
        total, cards = answer.get("total_count") or 0, answer.get("results") or []
        kept = 0
        with open(listing_path, "a", encoding="utf-8") as f:
            for card in cards:
                kind, link, _ = classify_card(card)
                if kind != "product":
                    if card.get("id") not in skipped_ids:            # a card seen in several slices counts once
                        skipped_ids.add(card.get("id"))
                        state["skipped_ids"].append(card.get("id"))
                        state["skipped"][skip_reason(card)] += 1
                    continue
                pid = str(card.get("product_id"))
                if pid in seen:
                    continue
                seen.add(pid)
                kept += 1
                f.write(json.dumps(listing_row(card, link, query, (a, b)), ensure_ascii=False) + "\n")
        state["kept"] += kept
        complete = len(cards) >= total
        parts = [] if complete or a == b else split_range(a, b, total)
        state["pending"] += parts[::-1]                          # lowest part next: stack order
        state["slices"].append({"range": [a, b], "count": total, "cards": len(cards), "kept": kept,
                                "split": len(parts)})
        if not complete and a == b:
            state["saturated"].append({"price": a, "count": total, "cards": len(cards)})
        print(f"listing: {a:>11,}-{b:<13,} count {total:>6} cards {len(cards):>2} kept {kept:>2} "
              f"{'split ' + str(len(parts)) if parts else 'done':<8} (total kept {state['kept']}, "
              f"requests {state['requests']})")
        save_state(state_path, state)
    save_state(state_path, state)
    done = not state["pending"]
    print(f"listing: {'done' if done else 'paused'}: kept {state['kept']} products, skipped {state['skipped']}, "
          f"{len(state['slices'])} slices, {len(state['saturated'])} saturated, {state['requests']} requests")
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect every Naver store product link for a keyword (+ category).")
    parser.add_argument("query", help="search keywords, as on shopping.naver.com")
    parser.add_argument("--category", help="Naver category id at any depth, e.g. 50002788")
    parser.add_argument("--out", help="run name under scripts/output/ (default: a timestamp); reuse to resume")
    parser.add_argument("--min-price", type=int, default=0, help="lowest price in KRW (default 0)")
    parser.add_argument("--max-price", type=int, default=MAX_PRICE, help="highest price in KRW (default: open)")
    parser.add_argument("--delay", type=float, default=3, help="seconds between API calls (default 3)")
    parser.add_argument("--max-requests", type=int, default=0, help="stop after this many API calls (default: no limit)")
    parser.add_argument("--base-url", help="server URL (default: NAVER_API_URL or http://localhost:8000)")
    args = parser.parse_args(argv)

    run = args.out or datetime.now().strftime("%Y%m%d-%H%M%S")
    state = harvest_listing(NaverApiClient(base_url=args.base_url), args.query, os.path.join(OUTPUT_ROOT, run),
                            category=args.category, lo=args.min_price, hi=args.max_price, delay=args.delay,
                            max_requests=args.max_requests)
    return 0 if not state["pending"] else 3


if __name__ == "__main__":
    sys.exit(main())
