"""Which listing rows to open: the screen before a product page is read.

A product page costs ~30-60 s in the owner's Chrome (search -> card -> page), so a row is screened on what the
listing already shows, and every row left out gets one reason code (the owner's list, 2026-11-05), checked in
this order:

  sponsored          an ad card (`is_ad`), when the exclusions file says exclude_sponsored
  title_unavailable  no product name: nothing to screen or search by
  rental             a rental offer: a stop word of listing_exclusions.json in the name
  category_mismatch  the row's category is not exactly the leaf category of the run (no parent matches)
  key_unavailable    no store number or product id: the shop check cannot be done, so the row is not taken
  already_published  the source key is in the shop's catalog snapshot (shopify_catalog), any product status
  deferred           the source key is deferred in the shop's journal (deferred_log) and no retry is allowed

Catalog (가격비교) cards and external malls never reach here: the server keeps Naver store products only.
Products are matched by the source key, never by name.

The stop words are the naver-harvester's file, copied byte for byte (listing_exclusions.json = its
store-scripts/fairwardgolf/fairwardgolf-catalog/mappings/listing-exclusions.json, schema
fairwardgolf-listing-exclusions/v1, checked 2026-11-05), matched the way its shared/src/naver/catalog-exclusions.ts
naverListingExclusion does: the name is NFKC-normalized and lower-cased; every occurrence of a token is tried; a
token matches anywhere (`none`) or as a latin word (`latin-word`: the characters around it are not ASCII letters or
digits); `notPrecededBy` / `notFollowedBy` list the text right next to it that makes it another word (대여성 is not
대여, 토렌트 is not 렌트). To update: copy the harvester's file again, never edit this copy.

    from listing_filter import Screen
    screen = Screen("50002788", namespace="fairwardgolf", published=catalog.keys(), deferred=journal.blocked())
    taken = [row for row in rows if screen.reason(row) is None]
    screen.counts            # {"sponsored": 3, "rental": 1, ...}
"""
import json
import os
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable

EXCLUSIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "listing_exclusions.json")
REASONS = ("sponsored", "title_unavailable", "rental", "category_mismatch", "key_unavailable",
           "already_published", "deferred")
_ASCII_WORD = re.compile(r"[a-z0-9]")


def load_exclusions(path: str = EXCLUSIONS) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize(text: str | None) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def _term_at(name: str, start: int, term: dict[str, Any]) -> bool:
    end = start + len(term["text"])
    if term.get("boundary") == "latin-word":
        if start and _ASCII_WORD.match(name[start - 1]) or end < len(name) and _ASCII_WORD.match(name[end]):
            return False
    if any(name[:start].endswith(normalize(p)) for p in term.get("notPrecededBy", ())):
        return False
    return not any(name[end:].startswith(normalize(p)) for p in term.get("notFollowedBy", ()))


def term_matches(name: str, term: dict[str, Any]) -> bool:
    """`name` (normalized) holds `term` at a place its rules allow."""
    text = normalize(term["text"])
    start = name.find(text)
    while start >= 0:
        if _term_at(name, start, term):
            return True
        start = name.find(text, start + 1)
    return False


def stop_word(name: str | None, rules: Iterable[dict[str, Any]]) -> str | None:
    """The code of the first rule whose term is in the name, or None."""
    text = normalize(name)
    for rule in rules:
        if any(term_matches(text, t) for t in rule["tokens"]):
            return rule["code"]
    return None


def source_key(row: Any, namespace: str) -> str | None:
    """`<namespace>:naver:<channelNo>:<productId>`: the key a shop product carries for its Naver offer
    (the harvester's format), or None when the row lacks either number."""
    channel = str((row.get("store") or {}).get("channel_no") or "")
    product = str(row.get("product_id") or "")
    return f"{namespace}:naver:{channel}:{product}" if channel.isdigit() and product.isdigit() else None


class Screen:
    """The screen of one run: one leaf category, one shop. `published` and `deferred` are sets of source keys
    (refresh `published` with set_published before each product: the snapshot is kept 5 minutes at most)."""

    def __init__(self, category_id: str, namespace: str, published: Iterable[str] = (),
                 deferred: Iterable[str] = (), exclusions: dict[str, Any] | None = None):
        rules = (exclusions or load_exclusions())["universal"]
        self.category_id = str(category_id)
        self.namespace = namespace
        self.exclude_sponsored = bool(rules.get("excludeSponsored"))
        self.rules = rules.get("rules", [])
        self.published = set(published)
        self.deferred = set(deferred)
        self.counts: Counter[str] = Counter()

    def set_published(self, keys: Iterable[str]) -> None:
        self.published = set(keys)

    def check(self, row: Any) -> str | None:
        """The reason the row is left out, or None (not counted)."""
        if self.exclude_sponsored and row.get("is_ad"):
            return "sponsored"
        name = (row.get("name") or "").strip()
        if not name:
            return "title_unavailable"
        word = stop_word(name, self.rules)
        if word:
            return word
        if str(row.get("category_id") or "") != self.category_id:
            return "category_mismatch"
        key = source_key(row, self.namespace)
        if key is None:
            return "key_unavailable"
        if key in self.published:
            return "already_published"
        return "deferred" if key in self.deferred else None

    def reason(self, row: Any) -> str | None:
        """check() and count the reason."""
        code = self.check(row)
        if code:
            self.counts[code] += 1
        return code
