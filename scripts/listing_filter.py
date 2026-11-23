"""Which listing rows to open: the screen before a product page is read.

A product page costs ~30-60 s in the owner's Chrome (search -> card -> page), so a row is screened on what the
listing already shows, and every row left out gets one reason code (the owner's list, 2026-11-05), checked in
this order:

  sponsored          an ad card (`is_ad`), only when the run asks for it (exclude_sponsored=True): ads are kept
                     by default (the owner, 2026-11-06: an ad card is a product like the others); the
                     harvester file's excludeSponsored is not followed
  title_unavailable  no product name: nothing to screen or search by
  rental             a rental offer: a stop word of listing_exclusions.json in the name
  title:<code>       a word the run's category does not sell (listing_title_rules.json, ours, per Naver leaf
                     category; the owner, 2026-11-11: toys, gloves, loose heads in junior clubs, park golf in
                     full sets), or no word of a group the category requires (`requires`, 2026-11-19: a women's
                     word and a cardigan word for knit cardigans): matched on the name without spaces
  category_mismatch  the row's category is not exactly the leaf category of the run (no parent matches), nor one
                     the file's `together` takes with it (2026-11-21, the owner: 점퍼 50002798 and 재킷 50002799,
                     one section): such a row is screened by its own category's title rules
  key_unavailable    no store number or product id: the shop check cannot be done, so the row is not taken
  already_published  the source key is in the shop's catalog snapshot (shopify_catalog), any product status
  deferred           the source key is deferred in the shop's journal (deferred_log) and no retry is allowed

Catalog (가격비교) cards and external malls never reach here: the server keeps Naver store products only.
The screen matches products by the source key, never by name; the same product sold by another store (the same
title, another key) is dedupe.py's, after collect (job.py --dedupe, the owner 2026-11-15).

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
TITLE_RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "listing_title_rules.json")
REASONS = ("sponsored", "title_unavailable", "rental", "category_mismatch", "key_unavailable",
           "already_published", "deferred")
_ASCII_WORD = re.compile(r"[a-z0-9]")


def title_rules(category_id: str, path: str = TITLE_RULES, leaf: str | None = None) -> list[dict[str, Any]]:
    """The category's own title rules (listing_title_rules.json), [] for a category without any. A rule with
    `leaves` binds only a job of one of those shop sections (2026-11-21: 50002796 feeds the women's and the men's
    long-sleeve tops, each its own query and its own required words); a job that names no section is the
    category's `default_leaf` one (the jobs before)."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    leaf = leaf or data.get("default_leaf", {}).get(str(category_id))
    return [r for r in data.get("categories", {}).get(str(category_id), [])
            if not r.get("leaves") or leaf in r["leaves"]]


def together(category_id: str, path: str = TITLE_RULES, leaf: str | None = None) -> list[str]:
    """The categories a job of `category_id` also takes (listing_title_rules.json `together`, 2026-11-21: the same
    shop section from two Naver leaves), and for a job of section `leaf` its `together_leaf` ones (2026-11-22: the men's
    long-sleeve tops of 50002796 take the men's knits of 50002797, the women's tops job does not), [] for none."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = [str(c) for c in data.get("together", {}).get(str(category_id), [])]
    if leaf:
        out += [str(c) for c in data.get("together_leaf", {}).get(leaf, {}).get(str(category_id), []) if c not in out]
    return out


def _bare(word: str | None) -> str:
    return re.sub(r"\s+", "", normalize(word))


def title_rule(name: str | None, rules: Iterable[dict[str, Any]], store: str | None = None) -> str | None:
    """`title:<code>` of the first category rule whose term is in the name without spaces, or that `requires` a
    group of words none of which is in it (all of the groups, any word of each; 2026-11-19, knit cardigans: a women's
    word and a cardigan word), or None. A rule's `unless_stores` (store slugs: a maker's own store whose titles name
    neither the maker nor the sport, Callaway's callawaygolf_korea, 2026-11-23) leaves out the rule for its rows."""
    text = _bare(name)
    for rule in rules:
        if any(_bare(u) in text for u in rule.get("unless", ())):
            continue                                # a word that says the row is what the section sells
        if store and store in rule.get("unless_stores", ()):
            continue
        if any(not any(_word_in(w, text) for w in group) for group in rule.get("requires", ())):
            return f"title:{rule['code']}"
        if any(term_matches(text, {**t, "text": re.sub(r"\s+", "", t["text"])}) for t in rule.get("tokens", ())):
            return f"title:{rule['code']}"
    return None


def leaves_of(category_id: str, path: str = TITLE_RULES) -> set[str]:
    """The sections a job of the category may name (--leaf): its rules' `leaves` and its `default_leaf`."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {x for r in data.get("categories", {}).get(str(category_id), []) for x in r.get("leaves") or []}
    default = data.get("default_leaf", {}).get(str(category_id))
    return out | ({default} if default else set())


def _word_in(word: Any, text: str) -> bool:
    """A required word in the bare title: a plain word anywhere, or a token with its rules ("men" not after "wo")."""
    if isinstance(word, dict):
        return term_matches(text, {**word, "text": re.sub(r"\s+", "", word["text"])})
    return _bare(word) in text


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
                 deferred: Iterable[str] = (), exclusions: dict[str, Any] | None = None,
                 exclude_sponsored: bool = False, category_rules: list[dict[str, Any]] | None = None,
                 leaf: str | None = None):
        rules = (exclusions or load_exclusions())["universal"]
        self.category_rules = title_rules(category_id, leaf=leaf) if category_rules is None else category_rules
        self.category_id = str(category_id)
        self.also = together(category_id, leaf=leaf)   # rows of these categories are taken too (their own rules)
        self.rules_of = {c: (title_rules(c, leaf=leaf) if category_rules is None else category_rules) for c in self.also}
        self.namespace = namespace
        self.exclude_sponsored = exclude_sponsored    # ads kept (the owner, 2026-11-06), whatever the file says
        self.rules = rules.get("rules", [])
        self.published = set(published)
        self.deferred = set(deferred)
        self.counts: Counter[str] = Counter()

    def takes(self, category_id: Any) -> bool:
        """The run's category or one taken with it."""
        return str(category_id or "") in (self.category_id, *self.also)

    def set_published(self, keys: Iterable[str]) -> None:
        self.published = set(keys)

    def check(self, row: Any) -> str | None:
        """The reason the row is left out, or None (not counted)."""
        if self.exclude_sponsored and row.get("is_ad"):
            return "sponsored"
        name = (row.get("name") or "").strip()
        if not name:
            return "title_unavailable"
        category = str(row.get("category_id") or "")
        word = stop_word(name, self.rules) or title_rule(name, self.rules_of.get(category, self.category_rules),
                                                         ((row.get("store") or {}).get("slug")))
        if word:
            return word
        if category != self.category_id and category not in self.also:
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
