"""Store-wide description banners found across one transform run (run_transform.py, after the per-product prepare).

A seller's header / footer banners often have numeric or hashed file names that no name rule can tell from a
product photo (seen 2026-11-07, store 100568453, run40b: 30434463209514390_345786175.jpg opens and
60948062508870618_280838627.jpg + 22313003105171778_1094441035.jpg close 17 of its 18 listings). They show only as
repetition: the same image in most listings of one store. A description image is a store banner when, in one run,

  * it is in at least MIN_PRODUCTS sets of the same store (source.channel_no) and in at least MIN_SHARE of them,
    where listings sharing more than half (SAME_SET) of their description images are one set listed again and
    count once (seen 2026-11-07, 101773735: PGM steel 9 / steel 12 / carbon 12 share their last 12 photos), and
  * it opens or closes the product's description (in the leading or trailing run of shared images).

It moves from description_images to description_dropped (rule shared_store_image), note description_shared_images.
A shared image inside the product's own photos stays (named in the note). A store with fewer listings is untouched.

"The same image": the link without its query (?type=w860 is only the size). The seller uploads a banner again for
each batch of listings, so one banner has several links (100568453: 5-6 upload folders for one file name); a
distinctive file name (12+ characters, 8+ digits: camera, phone, export or hash names) is one source file and
merges those links. Generic names (image.png, 1.jpg, 상세.jpg, 최종.jpg) stay one image per link: 102412170
(run40-replay) has 34 different image.png in 3 listings.

Thresholds from the 99 products of three checked runs (2026-11-07): pairs of listings sharing
every photo are common (101773735, 102412170, 100249211: one set listed twice) and never a banner, hence 3 sets;
the PGM listings above share 12/22 = 0.55 of their images, two different products of 100568453 at most 0.47 (its
banners and a model line's spec images), hence more than half is one set; in 100568453 (19 listings, 7 sets) the
banners are in 6-7 of 7 sets, the most shared own photos in 1, hence a half.
"""
import copy
import re
from collections import defaultdict
from typing import Any, Iterable, Mapping, TypeVar, cast
from urllib.parse import unquote, urlparse

from description_clean import image_name

MIN_PRODUCTS = 3
MIN_SHARE = 0.5
SAME_SET = 0.5                  # listings sharing more than this part of their images are one set
RULE = "shared_store_image"
NOTE = "description_shared_images"
_DIGIT_RE = re.compile(r"\d")
P = TypeVar("P", bound=Mapping[str, Any])        # a prepared product (transform.Prepared or a plain dict)


def _distinctive(name: str) -> bool:
    stem = name.rsplit(".", 1)[0]
    return len(stem) >= 12 and len(_DIGIT_RE.findall(stem)) >= 8 and len(set(stem)) >= 6


def image_identity(link: str) -> str:
    """What makes two description image links the same image: the distinctive file name, else host + path."""
    name = image_name(link)
    if _distinctive(name):
        return "name:" + name
    u = urlparse(link if "//" in link else "//" + link)
    return "link:" + u.netloc.lower() + unquote(u.path)


def _edges(flags: list[bool]) -> set[int]:
    """Indexes of the leading and trailing run of True."""
    out: set[int] = set()
    for order in (range(len(flags)), range(len(flags) - 1, -1, -1)):
        for i in order:
            if not flags[i]:
                break
            out.add(i)
    return out


def _sets(descriptions: list[frozenset[str]]) -> list[frozenset[str]]:
    """One store's descriptions -> one per set: listings sharing more than half of the smaller description's images
    are one set listed again (joined transitively), their images merged."""
    parent = list(range(len(descriptions)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for a in range(len(descriptions)):
        for b in range(a + 1, len(descriptions)):
            if len(descriptions[a] & descriptions[b]) > SAME_SET * min(len(descriptions[a]), len(descriptions[b])):
                parent[root(a)] = root(b)
    merged: dict[int, frozenset[str]] = defaultdict(frozenset)
    for i, d in enumerate(descriptions):
        merged[root(i)] |= d
    return [merged[k] for k in sorted(merged)]


def shared_identities(products: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, tuple[int, int]]]:
    """channel_no -> {identity: (listing groups holding it, groups of the store)} for the store banners of a run. A product
    without description images does not count."""
    descriptions: dict[str, set[frozenset[str]]] = defaultdict(set)
    for p in products:
        images = (p.get("product") or {}).get("description_images") or []
        if images:
            descriptions[str(p["source"]["channel_no"])].add(frozenset(image_identity(x) for x in images))
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for channel, unique in descriptions.items():
        sets = _sets(sorted(unique, key=sorted))
        count: dict[str, int] = defaultdict(int)
        for s in sets:
            for i in s:
                count[i] += 1
        found = {i: (c, len(sets)) for i, c in count.items() if c >= MIN_PRODUCTS and c >= MIN_SHARE * len(sets)}
        if found:
            out[channel] = found
    return out


def drop_shared_images(products: list[P]) -> list[P]:
    """Prepared products of one run -> the same list (order kept), store banners moved to description_dropped.
    Pure: changed products are copies, the others are the same objects."""
    shared = shared_identities(products)
    out: list[P] = []
    for p in products:
        found = shared.get(str(p["source"]["channel_no"])) or {}
        images = (p.get("product") or {}).get("description_images") or []
        flags = [image_identity(x) in found for x in images]
        if not any(flags):
            out.append(p)
            continue
        edges = _edges(flags)
        q = cast(dict[str, Any], copy.deepcopy(p))
        q["product"]["description_images"] = [x for i, x in enumerate(images) if i not in edges]
        q["product"]["description_dropped"] = list(q["product"].get("description_dropped") or []) + [
            {"rule": RULE, "text": images[i]} for i in sorted(edges)]
        def told(i: int) -> str:
            held, of = found[image_identity(images[i])]
            return f"{image_name(images[i])} ({held} of {of} listing groups)"
        detail = "dropped: " + ", ".join(told(i) for i in sorted(edges)) if edges else ""
        middle = [i for i, f in enumerate(flags) if f and i not in edges]
        if middle:
            detail += ("; " if detail else "") + "kept in the middle: " + ", ".join(told(i) for i in middle)
        q["notes"] = list(q.get("notes") or []) + [{"code": NOTE, "detail": detail}]
        out.append(cast(P, q))
    return out
