"""A brand for every prepared product (run-level, after transform.prepare): the vendor of a Shopify product is never
empty (the owner, 2026-11-08: "no brand: at least the manufacturer").

Why a fallback is needed: a seller who links no Naver brand leaves no 브랜드 row and no brandName; Naver then knows
none anywhere (checked 2026-11-08 on the 6 of 143 sets: the product answer, the page's own answer, the raw search
cards, the 상품정보제공고시 rows, the page's ld+json and meta tags: none). What is left is the seller's words. In
order, the first that gives a value (`brand_source` says which):

  1. the 브랜드 row / brandName                        transform.prepare (specs:브랜드, search_info.brandName)
  2. the manufacturer (제조사 row, manufacturerName,   transform.prepare ("manufacturer:<source>"); never Naver's
     the notice's 제조자)                               M0000000 or a pointer ("상세정보참조")
  3. a brand of the same shop found in the title       "title"; the shop's brands are the values of step 1 over its
                                                        kept products (no list kept by hand: brands are not known
                                                        ahead); the first in the title. Checked on 187 branded sets:
                                                        89 % the same brand, most others the same brand spelled
                                                        another way (피지엠 / PGM, 캘러웨이골프 / 캘러웨이); a
                                                        combination set (조합, 32 titles) names several: the first
  4. the importer / distributor in 원산지's brackets   "origin" ("일본산(혼마코리아)": 혼마코리아)
  5. a brand of the shop in the images' text           "images_text": the one read most often
  6. a Latin brand phrase the images repeat            "images_text_latin": two words or more, read MIN_LATIN times
                                                        or more (13425122164: "BEN SAYERS" 24 times)
  7. 노브랜드 (no brand)                                "none": an unbranded product (13464713764: an indoor putter
                                                        with the store's logo only)

Steps 3-7 add the note brand_fallback (the source and the other candidates: the vendor step can still choose). The
vendor's spelling (캘러웨이 / 캘러웨이골프, 젝시오 / XXIO) is decided later for every product.
"""
import re
from collections import Counter
from typing import Any, Callable

NO_BRAND = "노브랜드"
MIN_LATIN = 5
_LATIN_PHRASE = re.compile(r"\b[A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,})+\b")
_BRACKETS = re.compile(r"\(([^()]+)\)")
_POINTER = re.compile(r"상세|참조|페이지|설명")
_AGENCY = re.compile(r"구매\s*대행|병행\s*수입|해외\s*직구")


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def shop_brands(prepared: list[Any]) -> list[str]:
    """The brands the shop's products state (step 1), longest first (혼마 must not hide 무쯔미혼마)."""
    found = {p["product"]["brand_ko"] for p in prepared
             if p["product"].get("brand_ko") and str(p["product"].get("brand_source") or "").startswith(
                 ("specs:", "search_info."))}
    return sorted(found, key=lambda b: (-len(_norm(b)), b))


def in_title(title: str | None, brands: list[str]) -> list[str]:
    """The shop's brands the title names, in title order (a longer name wins over one inside it)."""
    t = _norm(title)
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for b in brands:
        n = _norm(b)
        at = t.find(n) if n else -1
        while at >= 0:
            if not any(s <= at < e for s, e in taken):
                hits.append((at, b))
                taken.append((at, at + len(n)))
                break
            at = t.find(n, at + 1)
    return [b for _, b in sorted(hits)]


def distributors(origin: str | None) -> list[str]:
    return [x.strip() for x in _BRACKETS.findall(origin or "")
            if x.strip() and not _POINTER.search(x) and not _AGENCY.search(x)]


def in_images(rows: list[str], brands: list[str]) -> Counter:
    text = _norm(" ".join(rows))
    return Counter({b: text.count(_norm(b)) for b in brands if _norm(b) and text.count(_norm(b))})


def latin_phrases(rows: list[str]) -> Counter:
    return Counter(m.upper() for r in rows for m in _LATIN_PHRASE.findall(r))


def decide(title: str | None, origin: str | None, brands: list[str], rows: list[str]) -> tuple[str, str, list[str]]:
    """-> (brand, source, other candidates) for a product with no brand of its own (steps 3-7)."""
    titled = in_title(title, brands)
    if titled:
        return titled[0], "title", titled[1:]
    dist = distributors(origin)
    if dist:
        return dist[0], "origin", dist[1:]
    seen = in_images(rows, brands)
    if seen:
        top = [b for b, _ in seen.most_common()]
        return top[0], "images_text", top[1:3]
    latin = [(p, n) for p, n in latin_phrases(rows).most_common() if n >= MIN_LATIN]
    if latin:
        return latin[0][0], "images_text_latin", [p for p, _ in latin[1:3]]
    return NO_BRAND, "none", []


def fill(prepared: list[Any], rows_of: Callable[[str], list[str]],
         origins: dict[str, str | None], texts: Callable[[Any], list[dict[str, str]]]) -> int:
    """Give every product without a brand one (steps 3-7), add the note and the brand to its texts. rows_of(key): the
    images' OCR rows of the product; origins: {key: 원산지 as the page states it}. -> how many were filled."""
    brands = shop_brands(prepared)
    n = 0
    for p in prepared:
        product = p["product"]
        if product.get("brand_ko"):
            continue
        brand, source, others = decide(product.get("title_ko"), origins.get(p["key"]), brands, rows_of(p["key"]))
        p["product"]["brand_ko"], p["product"]["brand_source"] = brand, source
        p["notes"] = [x for x in p["notes"] if x["code"] != "brand_fallback"] + [
            {"code": "brand_fallback", "detail": f"{source}: {brand}" + (f"; also {', '.join(others)}" if others else "")}]
        p["texts"] = texts(p["product"])
        n += 1
    return n
