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
  3b. a brand the dictionary knows starting the title "title_known" ("프랭클린 스포츠 ...", 2026-11-12)
  4. the importer / distributor in 원산지's brackets   "origin" ("일본산(혼마코리아)": 혼마코리아)
  5. a brand of the shop in the images' text           "images_text": the one read most often (a Korean
                                                        brand only where a word starts: 쇼핑 is not 핑)
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
# a trading company's name, not a maker's brand (2026-11-11, junior clubs: a seller wrote its shop 세모물상점 as the
# 브랜드, another's 원산지 named its supplier 스퀘어홀딩 where the title says PMG): a shop, a holding, a trader, a
# distributor. 혼마코리아 (a maker's Korean branch) stays.
_TRADE_NAME = re.compile(r"(?:상점|상사|상회|만물상|홀딩스?|무역|유통|인터내셔[널날]|코퍼레이션|컴퍼니)(?:\s*\(주\)|\s*㈜)?\s*$"
                         # 2026-11-12, junior clubs: 유무상회 (a trading house), 건이네 만물상 (a general store),
                         # 우리쇼핑하자 (a shop: "let's go shopping"), 상아네 / 건이네 ("Sang-a's place": a family shop)
                         r"|쇼핑|^[가-힣]{1,3}네(?:\s|$)"
                         # 2026-11-13, the junior pilot: 막팔아스토어, 보라잡화점 (the seller's shop in the 브랜드 row)
                         r"|스토어\s*$|잡화점?\s*$|몰\s*$")             # 해외몰 (an overseas mall, origin brackets)
_PARTNER = re.compile(r"\s*(?:협력\s*(?:사|업체)|제휴(?:\s*(?:사|업체))?)\s*$")   # 빅토르몰 제휴 (2026-11-13)
# a brand row that goes on into the product's words (5140543074, 2026-11-12: "진월드스타 어린이용 주니어 골프 클럽 아이언
# 퍼터 드라이버") keeps the words before them; one that is only an age and a club ("6~8세 퍼터", 4194532081) is none
_WORDS = r"(?:어린이|유아|아동|주니어|키즈|골프\s*클럽|골프채|클럽|퍼터|아이언|드라이버|우드|웨지|유틸|세트)"
# ... and one that starts with them as a word of its own ("주니어", "주니어 어린이용 골프채": 2026-11-13) is none;
# a brand that only starts like one (키즈짐) stays
_PRODUCT_WORD = re.compile(r"\s" + _WORDS + r"|^" + _WORDS + r"(?:용)?(?=\s|$)")
_NOT_A_NAME = re.compile(r"^[\d\s~\-.,세cmCM]*$|^\d+\s*[~\-]?\s*\d*\s*세")
# words a seller writes in the 브랜드 / 제조사 row that name no firm (2026-11-13, the junior pilot: "주니어" in 3 brand
# rows became a shop brand, then the brand of 74 junior titles and "PGM" in the dictionary; "별도표기" (stated
# elsewhere) in 6, "중국" / "중국 브랜드" (a country) in 9, a bare "협력사" (a contract maker) in 2, "알수없음" (unknown)
# in the origin's brackets, 7659269727)
_NO_FIRM = re.compile(r"^(?:별도\s*표기|알\s*수\s*없음|미상|불명|없음|모름|(?:중국|한국|국산|일본|대만|베트남|태국|미국)(?:\s*(?:산|브랜드|제조사?|oem|OEM))?)$")
_CODE = re.compile(r"\s*\((?:\d+|자체\s*제작[^()]*)\)\s*$")       # 코알라(200874), 지브이골프코리아(자체제작 상품)


def trade_name(name: str | None) -> bool:
    """A shop's or a trading company's name, never a brand."""
    base = _PARTNER.sub("", (name or "").strip())                           # "X 협력업체": X's contract maker
    return bool(_TRADE_NAME.search(base))


def resellers_own(name: str | None, maker: str | None, store: dict[str, Any] | None) -> bool:
    """`name` is the seller's own shop, and the seller says it only resells: its 제조사 is "<its shop> 협력사 /
    협력업체" (a contract maker of the shop's). 11674983361, 2026-11-12: 재팬 도코도코 wrote its shop as the brand and
    "재팬도코도코협력사" as the maker; 홈앤컴, 굿세라, 구띵상점, 유무상회 the same. A shop selling its own brand (스컬독,
    버디온, 아화골프, US키즈골프) writes no 협력: it stays."""
    store = store or {}
    own = {_norm(store.get("name")), _norm((store.get("business") or {}).get("legal_name"))} - {""}
    partner = _PARTNER.search(maker or "")
    return bool(partner and _norm(_PARTNER.sub("", maker or "")) in own and _norm(name) in own)


def clean(name: str | None) -> str | None:
    """A seller's brand or maker as a brand: "X 협력사 / 협력 업체" names X, a trailing code or "(자체제작 상품)" goes,
    a word written twice once (던롭 던롭), the product's own words after it go; None: no brand there (empty, an age,
    a shop's or a trader's name)."""
    value = _PARTNER.sub("", re.sub(r"\s+", " ", name or "").strip())
    value = re.sub(r"^(?:\(주\)|㈜)\s*", "", _CODE.sub("", value)).strip()
    cut = _PRODUCT_WORD.search(value)
    if cut:
        value = value[:cut.start()].strip()
    words = value.split(" ")
    value = " ".join(w for i, w in enumerate(words) if i == 0 or w != words[i - 1])
    if not value or _NOT_A_NAME.search(value) or _NO_FIRM.search(value) or trade_name(value):
        return None
    return value


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
    # a brand inside a Korean distributor's name comes last: "던롭스포츠코리아 젝시오 12" (7202588289, 2026-11-12) is
    # an XXIO set Dunlop's Korean branch imports, not a Dunlop one
    return [b for at, b in sorted(hits, key=lambda h: (_in_distributor(t[h[0]:], _norm(h[1])), h[0]))]


def _in_distributor(rest: str, brand: str) -> bool:
    """The title from the brand on (spaces out) goes on into a Korean branch's name: 던롭스포츠코리아, 캘러웨이코리아."""
    return re.match(re.escape(brand) + r"[가-힣]{0,4}코리아", rest) is not None


# a part of the brackets that names the making, not a firm: "중국산(중국 oem / 인파로)" (5859220164, 2026-11-12) names
# 인파로; the brackets are split on "/" and "," and such parts go
_MAKING = re.compile(r"(?i)\b(?:oem|odm)\b|^(?:중국|한국|국산|일본|대만|베트남|태국|미국)(?:산|\s|$)|제조|생산|수입")


def distributors(origin: str | None) -> list[str]:
    parts = [p.strip() for x in _BRACKETS.findall(origin or "") for p in re.split(r"[/,]", x)]
    # a bare 협력사 or a word that names no firm is none either (2026-11-13: "(협력사)", "(해외몰)")
    return [clean(p) for p in parts if p and clean(p) and not trade_name(p) and not _POINTER.search(p)
            and not _AGENCY.search(p) and not _MAKING.search(p)]


# a Korean brand (핑, 핑골프, 혼마) is counted in the images' text only where a word starts: 13445783517, 2026-11-11,
# "쇼핑골프처음" (a shop's name, "shopping") counted as 핑 and 핑골프 (Ping), 13625754692 "치핑" (chipping) as 핑;
# a brand glued after another word ("정품캘러웨이") is then missed, and the next step decides. A brand of one
# syllable must also end the word or go on with 골프 (핑크 "pink", 핑거 "finger" are not 핑). Spaces inside the brand
# are free ("테일러 메이드", "펜타곤 야마모토").
_HANGUL_BRAND = re.compile(r"^[가-힣]+$")
_LATIN_BRAND = re.compile(r"^[a-z0-9.\-&']*[a-z][a-z0-9.\-&']*$")
# a web address in the images names the shop that made them, not the product's brand: 13445783517, 2026-11-11,
# "www.houma.co.kr" (a retailer) counted as HOUMA on a Ben Sayers set; only the address's own characters go
_ADDRESS = re.compile(r"https?://[^\s가-힣]+|www\.[A-Za-z0-9.-]+|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*"
                      r"\.(?:co\.kr|com|net|kr)\b", re.I)


def _count(text: str, spaced: str, brand: str) -> int:
    n = _norm(brand)
    if _HANGUL_BRAND.match(n):
        tail = r"(?:(?![가-힣])|(?=\s*골프))" if len(n) == 1 else ""
        return len(re.findall(r"(?<![가-힣])" + r"\s*".join(map(re.escape, n)) + tail, spaced))
    if _LATIN_BRAND.match(n):
        # a Latin brand is counted as whole words only: 13425122164, 2026-11-12, a junior seller's brand GB was read
        # in "golf bag" (spaces taken out: "golfbag") and a Ben Sayers set became GB. Its own words may be written
        # apart or together ("U.S. Kids Golf", "US KIDS GOLF"); a word of it is never cut.
        words = re.findall(r"[a-z0-9]+", brand.casefold())
        return len(re.findall(r"(?<![a-z0-9])" + r"[\s.\-&']*".join(map(re.escape, words)) + r"(?![a-z0-9])", spaced))
    return text.count(n)


def in_images(rows: list[str], brands: list[str]) -> Counter:
    spaced = _ADDRESS.sub(" ", " ".join(rows)).casefold()
    text = _norm(spaced)
    counts = {b: _count(text, spaced, b) for b in brands if _norm(b)}
    return Counter({b: c for b, c in counts.items() if c})


# a spec table's headings, not a brand (13024208178, 2026-11-13: "DEGREE LOFT")
_SPEC_WORDS = {"DEGREE", "LOFT", "LIE", "ANGLE", "LENGTH", "SHAFT", "FLEX", "GRIP", "WEIGHT", "HEAD", "CLUB", "IRON",
               "DRIVER", "PUTTER", "WEDGE", "WOOD", "SIZE", "AGE", "HEIGHT", "TOTAL", "MODEL", "TYPE", "COLOR", "SPEC"}


def latin_phrases(rows: list[str]) -> Counter:
    return Counter(u for r in rows for m in _LATIN_PHRASE.findall(r)
                   if not set((u := m.upper()).split()) <= _SPEC_WORDS)


def leading(title: str | None, known: list[str]) -> str | None:
    """A brand the shop's brand dictionary knows that starts the title ("프랭클린 스포츠 조절 가능한 유소년 골프 세트":
    13324651260, 2026-11-12, an import with no brand row, maker or importer), the longest; two letters at least."""
    t = _norm(title)
    found = [b for b in known if len(_norm(b)) >= 2 and t.startswith(_norm(b))]
    return max(found, key=lambda b: len(_norm(b))) if found else None


def decide(title: str | None, origin: str | None, brands: list[str], rows: list[str],
           known: list[str] | None = None) -> tuple[str, str, list[str]]:
    """-> (brand, source, other candidates) for a product with no brand of its own (steps 3-7; known: the brand
    dictionary's Korean names, for a title that starts with one)."""
    titled = in_title(title, brands)
    if titled:
        return titled[0], "title", titled[1:]
    first = leading(title, known or [])
    if first:
        return first, "title_known", []
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
         origins: dict[str, str | None], texts: Callable[[Any], list[dict[str, str]]],
         known: list[str] | None = None) -> int:
    """Give every product without a brand one (steps 3-7), add the note and the brand to its texts. rows_of(key): the
    images' OCR rows of the product; origins: {key: 원산지 as the page states it}. -> how many were filled."""
    brands = shop_brands(prepared)
    n = 0
    for p in prepared:
        product = p["product"]
        if product.get("brand_ko"):
            continue
        brand, source, others = decide(product.get("title_ko"), origins.get(p["key"]), brands, rows_of(p["key"]),
                                       known)
        p["product"]["brand_ko"], p["product"]["brand_source"] = brand, source
        p["notes"] = [x for x in p["notes"] if x["code"] != "brand_fallback"] + [
            {"code": "brand_fallback", "detail": f"{source}: {brand}" + (f"; also {', '.join(others)}" if others else "")}]
        p["texts"] = texts(p["product"])
        n += 1
    return n
