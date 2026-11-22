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
  3c. a brand the dictionary knows as a word of its own  "title_word": three letters at least, the whole word
      anywhere in the title                               ("남성 또는 개인용 라즈러스 ...", "GoSports Illegal Max
                                                        Spin ...": 2026-11-15, the wedge pilot); a Latin one by its
                                                        dictionary spelling, any case
  3d. a Brand row of the description                   "description_row": the spec table an agency import copies
                                                        ("Brand | WENGH", "Brand Name | WENGH", "브랜드: MAZEL":
                                                        2026-11-15, about 90 products, where the images gave
                                                        "CNC MILLED" or "EVEN"); the first that names a firm;
                                                        "- Brand : X" and "브랜드 이름 | X" too; a bare number
                                                        ("69") takes the Manufacturer row that starts with it
                                                        ("69 Golf", 2026-11-16)
  4. the importer / distributor in 원산지's brackets   "origin" ("일본산(혼마코리아)": 혼마코리아)
  5. a brand of the shop in the images' text           "images_text": the one read most often (a Korean
                                                        brand only where a word starts: 쇼핑 is not 핑)
  5b. the shop's own brand: the shop's name           "shop_wordmark" (own_brand_shown: its slug read 3 times in its
                                                        texts, or "브랜드 <name>", "<name>의 상표권"; Tee And Golf,
                                                        2026-11-19); transform.prepare keeps a brand row the reseller
                                                        rule dropped the same way (Grehip)
  6. a Latin brand phrase the images repeat            "images_text_latin": two words or more, read MIN_LATIN times
                                                        or more (13425122164: "BEN SAYERS" 24 times)
  7. 노브랜드 (no brand)                                "none": an unbranded product (13464713764: an indoor putter
                                                        with the store's logo only)

Steps 3-7 add the note brand_fallback (the source and the other candidates: the vendor step can still choose). The
vendor's spelling (캘러웨이 / 캘러웨이골프, 젝시오 / XXIO) is decided later for every product.
"""
import functools
import itertools
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
                         r"|스토어\s*$|잡화점?\s*$|몰\s*$"             # 해외몰 (an overseas mall, origin brackets)
                         # a department store or a mall is never a label (2026-11-21, the review of shop_label: a title
                         # "[현대백화점] ..." or a shop 하프클럽mall would make it the brand)
                         r"|백화점\s*$|(?i:mall)\s*$")
# ... and a trailing "co." / ".co." after it ("수수협력사 co.", "수수랜드협력사.co.": 2026-11-18, the chipper review,
# 13800679830 went out as the vendor "Susu Partner Co.", a Ben Sayers M5 by the shop 수수)
_PARTNER = re.compile(r"\s*(?:협력\s*(?:사|업체)|제휴(?:\s*(?:사|업체))?)(?:\s*\.?\s*co\.?)?"   # 빅토르몰 제휴 (2026-11-13)
                      # ... and the factory in brackets after it ("벤시아 협력업체(PG골프클럽)": 2026-11-21, the vendor
                      # "Bensia Partner (PG Golf Club)", 11174080985)
                      r"(?:\s*\([^()]*\))?\s*$", re.I)
# a brand row that goes on into the product's words (5140543074, 2026-11-12: "진월드스타 어린이용 주니어 골프 클럽 아이언
# 퍼터 드라이버") keeps the words before them; one that is only an age and a club ("6~8세 퍼터", 4194532081) is none
# ... and the chipper itself (2026-11-18, the chipper review: 11158899277's 브랜드 / 제조사 rows say 치퍼, it became a shop
# brand, then the brand of every title with 치퍼: vendor "Chipper" on MAZEL 10179980640, Pinemeadow 13478213249, TTY / PGM
# 7518807949, CHIPPER Lab 11664750138); "CHIPPER Lab" is a maker and stays, as 치퍼랩 / 치퍼 랩: the chipper words end
# there (치퍼용, 칩퍼터 still go; the review of 569b77f: "XYZ 치퍼랩" was cut to "XYZ", "치퍼 랩" read as no brand)
_WORDS = (r"(?:어린이|유아|아동|주니어|키즈|골프\s*클럽|골프채|클럽|퍼터|아이언|드라이버|우드|웨지|유틸|세트"
          r"|(?:치퍼|칩퍼)(?:용|터)?(?![가-힣]|\s*랩)|(?i:chipper)(?!\s*(?i:lab)))")
# ... and one that starts with them as a word of its own ("주니어", "주니어 어린이용 골프채": 2026-11-13) is none;
# a brand that only starts like one (키즈짐) stays
_PRODUCT_WORD = re.compile(r"\s" + _WORDS + r"|^" + _WORDS + r"(?:용)?(?=\s|$)")
_NOT_A_NAME = re.compile(r"^[\d\s~\-.,세cmCM]*$|^\d+\s*[~\-]?\s*\d*\s*세")
# words a seller writes in the 브랜드 / 제조사 row that name no firm (2026-11-13, the junior pilot: "주니어" in 3 brand
# rows became a shop brand, then the brand of 74 junior titles and "PGM" in the dictionary; "별도표기" (stated
# elsewhere) in 6, "중국" / "중국 브랜드" (a country) in 9, a bare "협력사" (a contract maker) in 2, "알수없음" (unknown)
# in the origin's brackets, 7659269727)
# ... and the sport itself (10979283479, 2026-11-14: "골프" in the 브랜드 row became a shop brand, then the brand of
# every title that says 골프: 55 junior and full sets published with the vendor "Golf", 183 more would have followed)
_NO_FIRM = re.compile(r"(?i)^(?:별도\s*표기|알\s*수\s*없음|미상|불명|없음|모름|브랜드\s*없음|제조(?:자|사)\s*미상|(?:중국|한국|국산|일본|대만|베트남|태국|미국)(?:\s*(?:산|브랜드|제조사?|oem|OEM))?"
                      r"|골프(?:\s*(?:용품|클럽|채|스포츠))?|golf|스포츠|sports?"
                      # who it is for, a lone letter, an authenticity claim (2026-11-15: 남성용 / 여성용 in two brand
                      # rows became the brand of 32 titles that say 남성용 / 여성용, vendor "Yoshino" on a TaylorMade
                      # set; "ㅊ" on a Callaway set; "정식수입정품 또는 정식제조정품" as a maker)
                      r"|(?:남성|여성|남자|여자|남녀|공용|남녀\s*공용|유니섹스)(?:\s*용)?|[ㄱ-ㅎㅏ-ㅣ]+|.*정품.*"
                      # Amazon's word for no brand (2026-11-15: two Bermuda wedge sets, 13370440703 and 13099713088,
                      # published under the vendor "Generic" from their 브랜드 rows)
                      r"|generic|제네릭"
                      # a machine-translated spec table's "none" and "others" (2026-11-16: "브랜드 이름 | NONE" and
                      # "브랜드 이름 | 다른 사람들" in agency full sets, 13024224352, 13024206977, once the label was read)
                      r"|none|n/?a|others?|다른\s*사람들?"
                      # Naver's "other brand" and the word "brand" itself (2026-11-17, the wedge sets' dictionary
                      # review: "기타 BRAND" in 3 agency rows went out as the vendor "Other BRAND", 12789751830; "상표"
                      # (trademark) in a 브랜드 / 제조사 row as "Brand" on 5 live sets, 12619693409)
                      r"|기타(?:\s*(?:brand|브랜드))?|상표|브랜드"
                      # ... and the English word alone, any case (2026-11-18, the chipper review: rakuraku00 writes
                      # 브랜드=brand and 제조사=brand, 9991649397 / 9993129226 / 9993149923 went out as the vendor "brand",
                      # "brand CH809 Left-Handed Chipper")
                      r"|brand"
                      # Naver's placeholder for a brand it could not name, "UnKnown_" and a katakana name (2026-11-17,
                      # the wedge-set review C23: 13104702775 went out with the vendor "UnKnown_ピン" and the title
                      # "UnKnown_ピン Yonex …"; "Artist Unknown" is a name and stays)
                      r"|unknown_.*"
                      # Naver's "made in-house" (2026-11-21, the second windbreaker pilot: "자체제작 상품" in the 브랜드
                      # row went out as the vendor "In-House Product", 7309508576, 10674911182)
                      r"|자체\s*제작(?:\s*(?:상품|제품))?"
                      # ... and "our own brand" (2026-11-22, the men's tops pilot: 자체브랜드 in the 브랜드 row of 케간지골프's
                      # three sweatshirts went out as the vendor "Unbranded", the title "Unbranded Men's ...", 9723948321)
                      r"|자체\s*브랜드)$")
# a maker's "OEM" / "ODM" (2026-11-21): glued to a label it is that label's contract making ("필드가OEM": Fieldga,
# 10780424641); after a company's form (주식회사, (주), ㈜) it is the contract factory, no brand ("주식회사 더살림oem" became
# the vendor "The Sallim OEM" of 수아무아's 10669638240)
_OEM = re.compile(r"(?i)(?<![a-z])\s*(?:oem|odm)\s*$")        # never inside a Latin name ("901MOEM", "POEM")
_COMPANY = re.compile(r"^(?:주식회사|\(주\)|㈜)")
_COMPANY_FORM = re.compile(r"주식회사|\(주\)|㈜")
_CODE = re.compile(r"\s*\((?:\d+|자체\s*제작[^()]*)\)\s*$")       # 코알라(200874), 지브이골프코리아(자체제작 상품)
# a wholesaler or a store many sellers name in their 브랜드 / 제조사 rows, never a maker (2026-11-19, the seller-vendor
# review: (주)감씨 is the "공급사정보 (주식회사 감씨)" of dozens of shops reselling Inparo, whose images say "인파로만의
# 유니크한 컬러로 생산" and "인파로 제품은 … PL 보험"; 골드벙커 a store ("골드벙커 다른 상품 보기에서 구매 가능"); 40 live
# junior products went out as the vendors Gamssi and Gold Bunker): no brand there, the fallback goes on (the images: 인파로)
_SUPPLIERS = re.compile(r"^(?:감씨|gamssi|골[드프]\s*벙커|gold\s*bunker)$", re.I)          # 골프벙커: a seller's typo


def contract_factory(name: str | None) -> bool:
    """A company's contract making ("주식회사 더살림oem", "(주)위스트OEM"): a firm, so a 제조사 row of it stays a fact, but
    never the brand (clean gives None)."""
    value = re.sub(r"\s+", " ", name or "").strip()
    return bool(_OEM.search(value) and _COMPANY.match(value))


def trade_name(name: str | None) -> bool:
    """A shop's or a trading company's name, never a brand."""
    base = _PARTNER.sub("", (name or "").strip())                           # "X 협력업체": X's contract maker
    return bool(_TRADE_NAME.search(base))


# "our own brand" in the 브랜드 row (2026-11-22, the men's tops pilot: 케간지골프's three sweatshirts went out as the vendor
# "Unbranded"; as a no-firm word the run-level fallback then took the origin's city 광저우 or none): the seller's own
# label, the shop's name (shop_label, own_row), as a reseller's own shop
_OWN_LABEL = re.compile(r"자체\s*브랜드\s*$")


def resellers_own(name: str | None, maker: str | None, store: dict[str, Any] | None) -> bool:
    """`name` is the seller's own shop, and the seller says it only resells: its 제조사 is "<its shop> 협력사 /
    협력업체" (a contract maker of the shop's); or `name` is 자체브랜드, the shop's own label (2026-11-22). 11674983361, 2026-11-12: 재팬 도코도코 wrote its shop as the brand and
    "재팬도코도코협력사" as the maker; 홈앤컴, 굿세라, 구띵상점, 유무상회 the same. A shop selling its own brand (스컬독,
    버디온, 아화골프, US키즈골프) writes no 협력: it stays."""
    if _OWN_LABEL.match((name or "").strip()):
        return True
    store = store or {}
    # a company's form is no part of its name ("(주) 한앤코", the legal name of 김영주골프's store: its maker "한앤코
    # 협력업체" became the vendor "Han & Co.", 6521205918, 2026-11-21)
    own = {_norm(_COMPANY_FORM.sub("", str(x or ""))) for x in (store.get("name"),
                                                               (store.get("business") or {}).get("legal_name"))} - {""}
    partner = _PARTNER.search(maker or "")
    # the brand row may be the partner phrase itself ("수수협력사 co." by the shop 수수, 2026-11-18): the shop's own
    return bool(partner and _norm(_PARTNER.sub("", maker or "")) in own and _norm(_PARTNER.sub("", name or "")) in own)


# the shop sells its own brand (2026-11-19, the knit cardigan pilot): 그레힙 wrote "그레힙 협력업체" as the maker (so
# resellers_own dropped its brand row) while its images say "GREHIP OFFICIAL SHOP", "그레힙의 상표권" and "grehip" 9
# times (13759750310, 9992270463); 티앤드 골프 gave no brand row and its images "골프웨어 브랜드 티앤드입니다", so the
# slogan "EVER YDAY" embroidered on the cardigan became the vendor (11519647149). The shop's Latin address (its slug)
# read as a word MIN_WORDMARK times in its own texts, or its name next to 브랜드 / 상표권 / 공식 판매처, is a brand.
MIN_WORDMARK = 3
_SLUG_FILLER = {"golf", "shop", "store", "mall", "outlet", "official", "korea", "kr", "co", "the", "www"}
_OWN_WORDS = re.compile(r"상표권|상표\s*등록|공식\s*(?:정품\s*)?판매처|공식\s*(?:스토어|몰)|official\s*(?:shop|store)", re.I)


def own_brand_shown(store: dict[str, Any] | None, texts: list[str]) -> str | None:
    """The shop's name when its own texts (description, images) show it as a brand; None otherwise. The slug counts
    as a word of its own, not inside a web or mail address (www.x.com, x@gmail.com, x16); a slug of filler words only
    (golf, shop, outlet ...) or under 4 letters says nothing. The Korean name counts next to the words that make it
    the brand ("브랜드 티앤드", "그레힙의 상표권", "그레힙 공식 스토어"), never "<name>는 X 공식 판매처"."""
    store = store or {}
    name = clean(str(store.get("name") or ""))
    if not name:
        return None
    words = [w for w in re.split(r"[^a-z]+", str(store.get("slug") or "").lower()) if w]
    if sum(len(w) for w in words if w not in _SLUG_FILLER) >= 4:
        mark = re.compile(r"(?<![a-z0-9./@_-])" + r"[\s_-]*".join(map(re.escape, words)) + r"(?![a-z0-9@_-]|\.[a-z])",
                          re.I)
        if sum(len(mark.findall(t)) for t in texts) >= MIN_WORDMARK:
            return name
    names = {_norm(name)} | ({_norm(re.sub(r"\s*골프\s*$", "", name))} - {""})
    for t in texts:
        row = _norm(t)
        for n in names:
            if len(n) >= 2 and (f"브랜드{n}" in row or f"{n}브랜드" in row
                                or re.search(re.escape(n) + r"(?:의)?(?:상표권|상표등록|공식(?:스토어|몰|쇼핑몰|정품판매처|판매처))",
                                             row)):
                return name
    return None


def shop_label(shop: dict[str, Any] | None, title: str | None, own_row: bool = False) -> str | None:
    """The shop's name as its own label (apparel, see decide): `own_row`, or the title's first word (a [tag] counts)
    is the shop's name; None for no shop or a name under 2 letters."""
    name = clean(str((shop or {}).get("name") or "")) if shop else None
    if not name or len(_norm(name)) < 2:
        return None
    if own_row:
        return name
    words = re.sub(r"[\[\]()]", " ", title or "").split()                # "[카멜브리즈]썸씽 ...": its first word
    return name if words and _norm(words[0]) == _norm(name) else None


def clean(name: str | None) -> str | None:
    """A seller's brand or maker as a brand: "X 협력사 / 협력 업체" names X, a trailing code or "(자체제작 상품)" goes,
    a word written twice once (던롭 던롭), the product's own words after it go; None: no brand there (empty, an age,
    a shop's or a trader's name)."""
    value = _PARTNER.sub("", re.sub(r"\s+", " ", name or "").strip())
    if _OEM.search(value):
        if _COMPANY.match(value):
            return None
        value = _OEM.sub("", value)
    value = re.sub(r"^(?:\(주\)|㈜)\s*", "", _CODE.sub("", value)).strip()
    cut = _PRODUCT_WORD.search(value)
    if cut:
        value = value[:cut.start()].strip()
    words = value.split(" ")
    value = " ".join(w for i, w in enumerate(words) if i == 0 or w != words[i - 1])
    bare = value.strip(" .,;:·-")              # "브랜드." is no brand (2026-11-18, the chipper scroll 10029117508);
    if not value or _NOT_A_NAME.search(value) or _NO_FIRM.search(bare) or trade_name(value) \
            or _SUPPLIERS.search(bare):                                                     # "Golf Co." stays
        return None
    return value


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def shop_brands(prepared: list[Any]) -> list[str]:
    """The brands the shop's products state (step 1), longest first (혼마 must not hide 무쯔미혼마)."""
    found = {p["product"]["brand_ko"] for p in prepared
             if p["product"].get("brand_ko") and str(p["product"].get("brand_source") or "").startswith(
                 ("specs:", "search_info."))}
    found = {b for b in found if clean(b)}          # a record prepared before a word joined _NO_FIRM ("골프")
    return sorted(found, key=lambda b: (-len(_norm(b)), b))


def in_title(title: str | None, brands: list[str]) -> list[str]:
    """The shop's brands the title names, in title order (a longer name wins over one inside it)."""
    t = _norm(title)
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for b in brands:
        n = _norm(b)
        if not n:
            continue
        if _HANGUL_BRAND.match(n):
            # a Korean brand only where a word starts, as in the images (_count): 2026-11-15, 이디스 (Edis) was read
            # in "시니어 레이디스" (ladies) and a Majek K5 set (13469043292) was published as Edis; 기가 in "성장기
            # 가슴패드". One of one syllable also ends its word or goes on with 골프 (_count_pattern): 2026-11-18, the
            # chipper review: 핑 (PING) was read in 핑크 (pink) on 15 Intech EZ Roll / Extreme 5 chippers and the
            # junior set 13848307900 (published as PING); 핑골프, 핑 치퍼, 핑(골프) still match
            pattern = _count_pattern(b)
            raw = title or ""
            starts = [len(_norm(raw[:m.start()])) for m in pattern.finditer(raw)] if pattern else []
        else:
            starts, at = [], t.find(n)
            while at >= 0:
                starts.append(at)
                at = t.find(n, at + 1)
        for at in starts:
            if not any(s <= at < e for s, e in taken):
                hits.append((at, b))
                taken.append((at, at + len(n)))
                break
    # a brand inside a Korean distributor's name comes last: "던롭스포츠코리아 젝시오 12" (7202588289, 2026-11-12) is
    # an XXIO set Dunlop's Korean branch imports, not a Dunlop one
    return [b for at, b in sorted(hits, key=lambda h: (_in_distributor(t[h[0]:], _norm(h[1])), h[0]))]


def _in_distributor(rest: str, brand: str) -> bool:
    """The title from the brand on (spaces out) goes on into a Korean branch's name: 던롭스포츠코리아, 캘러웨이코리아."""
    return re.match(re.escape(brand) + r"[가-힣]{0,4}코리아", rest) is not None


# a part of the brackets that names the making, not a firm: "중국산(중국 oem / 인파로)" (5859220164, 2026-11-12) names
# 인파로; the brackets are split on "/" and "," and such parts go
_MAKING = re.compile(r"(?i)\b(?:oem|odm)\b|^(?:중국|한국|국산|일본|대만|베트남|태국|미국)(?:산|\s|$)|제조|생산|수입")
# a Korean address in the brackets names a place, never a firm (2026-11-20, the knit cardigan review: 카멜브리즈 writes
# "국산(서울특별시 동대문구)" and "국산(인천광역시 서구)", 8212382236 and 5932679597 went out as the brands
# "Dongdaemun-gu, Seoul" and 인천광역시 서구): a province or metropolitan city (서울, 경기도, 인천광역시 ...), a country
# word (국내, 대한민국), then a city, county, district, town or village (…시 …군 …구 …읍 …면 …동 …리). The whole part
# is places, and one of them a province / city or a country word, or two places and more ("동대문구 장안동"); a
# firm ending in one of those syllables alone (인파로, DGB, 지아이엘) stays
_REGION = (r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청[남북]|전라[남북]"
           r"|경상[남북])(?:특별자치시|특별자치도|특별시|광역시|시|도)?|국내|대한민국|한국")
_PLACE = r"[가-힣]{1,6}(?:특별자치시|특별자치도|특별시|광역시|시|군|구|읍|면|동|리|도)"
# ... and a bare country, alone or with 등 ("홍콩", "日本", "China", "인도네시아 등" in the shop's brackets)
_COUNTRY = r"(?i:홍콩|중국|일본|대만|미국|영국|베트남|태국|인도네시아|日本|中国|china|japan|usa?|uk|hong\s*kong)(?:\s*등)?"
# ... and a Chinese making city or province (2026-11-22, the men's tops pilot: "중국(광저우)" by 케간지골프 became the brand
# 광저우, Guangzhou, 9723948321), with 시 / 성 or a country word before it ("중국 광저우")
_CN_PLACE = (r"(?:(?:중국|china)\s*)?(?:광저우|광주우|심천|선전|상해|상하이|청도|칭다오|항주|항저우|이우|동관|둥관|소주|쑤저우|북경|베이징"
             r"|하문|샤먼|복건|푸젠|절강|저장|강소|장쑤|산동|산둥|광동|광둥|천진|톈진|대련|다롄|연대|옌타이|위해|웨이하이)(?:시|성)?")
_ADDRESS_PART = re.compile(rf"^(?:(?:{_REGION})(?:\s+(?:{_REGION}|{_PLACE}))*|(?:{_PLACE})(?:\s+(?:{_PLACE}))+"
                           rf"|{_COUNTRY}|(?i:{_CN_PLACE}))$")


def distributors(origin: str | None) -> list[str]:
    # a company mark inside the brackets is no bracket of its own ("중국산((주)감씨)" read as the brand "주": 2026-11-19)
    origin = re.sub(r"\(주\)|㈜", "", origin or "")
    parts = [p.strip() for x in _BRACKETS.findall(origin) for p in re.split(r"[/,]", x)]
    # a bare 협력사 or a word that names no firm is none either (2026-11-13: "(협력사)", "(해외몰)")
    return [c for p in parts if p and (c := clean(p)) and not trade_name(p) and not _POINTER.search(p)
            and not _AGENCY.search(p) and not _MAKING.search(p) and not _ADDRESS_PART.match(p)]


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


@functools.lru_cache(maxsize=None)
def _count_pattern(brand: str) -> re.Pattern[str] | None:
    """The compiled pattern _count looks for (None: a plain substring count). Cached by brand: compiled once a run, not
    once per product and brand (2026-11-15: ~95 000 compilations, 29 s of a 63 s prepare; 339 brands are more than
    re's own cache holds)."""
    n = _norm(brand)
    if _HANGUL_BRAND.match(n):
        tail = r"(?:(?![가-힣])|(?=\s*골프))" if len(n) == 1 else ""
        return re.compile(r"(?<![가-힣])" + r"\s*".join(map(re.escape, n)) + tail)
    if _LATIN_BRAND.match(n):
        # a Latin brand is counted as whole words only: 13425122164, 2026-11-12, a junior seller's brand GB was read
        # in "golf bag" (spaces taken out: "golfbag") and a Ben Sayers set became GB. Its own words may be written
        # apart or together ("U.S. Kids Golf", "US KIDS GOLF"); a word of it is never cut.
        words = re.findall(r"[a-z0-9]+", brand.casefold())
        return re.compile(r"(?<![a-z0-9])" + r"[\s.\-&']*".join(map(re.escape, words)) + r"(?![a-z0-9])")
    return None


def _count(text: str, spaced: str, brand: str) -> int:
    pattern = _count_pattern(brand)
    return len(pattern.findall(spaced)) if pattern else text.count(_norm(brand))


def _counts(rows: list[str], brands: list[str]) -> dict[str, int]:
    spaced = _ADDRESS.sub(" ", " ".join(rows)).casefold()
    text = _norm(spaced)
    return {b: _count(text, spaced, b) for b in brands if _norm(b)}


# a Latin brand read once, inside a Latin phrase of three or more words, is a slogan: 2026-11-15, "PRECISE AIMING
# FEEDBACK" in a description image made PRECISE (a real shop brand) the vendor of a XINGGM wedge set (13830322401)
_SLOGAN_WORD = re.compile(r"[A-Za-z]{2,}")


def _slogan(row: str) -> bool:
    row = _ADDRESS.sub(" ", row)
    return len(_SLOGAN_WORD.findall(row)) >= 3 and not re.search(r"[가-힣]", row)


def in_images(rows: list[str], brands: list[str]) -> Counter:
    counts = _counts(rows, brands)
    for b, c in list(counts.items()):
        if c == 1 and _LATIN_BRAND.match(_norm(b)):
            hit = [r for r in rows if _counts([r], [b]).get(b)]
            if hit and all(_slogan(r) for r in hit):
                counts[b] = 0
    return Counter({b: c for b, c in counts.items() if c})


# a spec table's headings, not a brand (13024208178, 2026-11-13: "DEGREE LOFT"); a page's section headings too
# (13848307900, 2026-11-18: "DETAILED DESIGN" read 10 times on a junior set once 핑크 no longer gave it PING)
_SPEC_WORDS = {"DEGREE", "LOFT", "LIE", "ANGLE", "LENGTH", "SHAFT", "FLEX", "GRIP", "WEIGHT", "HEAD", "CLUB", "IRON",
               "DRIVER", "PUTTER", "WEDGE", "WOOD", "SIZE", "AGE", "HEIGHT", "TOTAL", "MODEL", "TYPE", "COLOR", "SPEC",
               "DETAIL", "DETAILED", "DESIGN", "PRODUCT", "PARAMETER", "PARAMETERS"}


def latin_phrases(rows: list[str]) -> Counter:
    return Counter(u for r in rows for m in _LATIN_PHRASE.findall(r)
                   if not set((u := m.upper()).split()) <= _SPEC_WORDS)


def leading(title: str | None, known: list[str]) -> str | None:
    """A brand the shop's brand dictionary knows that starts the title ("프랭클린 스포츠 조절 가능한 유소년 골프 세트":
    13324651260, 2026-11-12, an import with no brand row, maker or importer), the longest; two letters at least."""
    t = _norm(title)
    found = [b for b in known if len(_norm(b)) >= 2 and t.startswith(_norm(b)) and clean(b)]   # 골프 is in it
    return max(found, key=lambda b: len(_norm(b))) if found else None


def as_word(title: str | None, known: list[str]) -> str | None:
    """A brand the dictionary knows (its Korean name, or its Latin spelling) standing as a word of its own anywhere in
    the title, the longest; three letters at least (2026-11-15: 라즈러스, 야마토, 버뮤다, GoSports in agency imports'
    titles after 남성용 or before a model). A Hangul brand is not inside a longer Hangul word, a Latin one not inside
    a longer Latin word or number."""
    t = title or ""
    found = [b for b in known if (pattern := _word_pattern(b)) and pattern.search(t)]
    return max(found, key=lambda b: len(_norm(b))) if found else None


@functools.lru_cache(maxsize=None)
def _word_pattern(brand: str) -> re.Pattern[str] | None:
    """The compiled pattern as_word looks for (None: too short or not a firm). Cached by brand, as _count_pattern."""
    n = _norm(brand)
    if len(n) < 3 or not clean(brand):
        return None
    if _HANGUL_BRAND.match(n):
        return re.compile(r"(?<![가-힣])" + r"\s*".join(map(re.escape, n)) + r"(?![가-힣])", re.I)
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(brand) + r"(?![A-Za-z0-9])", re.I)


_GOLF_END = re.compile(r"\s*(?:golf|골프)\s*$", re.I)


def title_stem(title: str | None, brands: list[str], known: list[str]) -> str | None:
    """A shop's or the dictionary's brand that ends in Golf / 골프 whose stem starts the title ("Vice Golf" for
    "VICE 프로 웨지 세트", "미스테리골프" for "미스테리 R라인 …"; 2026-11-17, the wedge-set review C27: 13830312401,
    13000456333 went out under a description row's or no brand). The stem is a firm of its own (clean), three Hangul
    letters or four Latin at least, a whole word at the start of the title; the longest wins."""
    found: list[tuple[int, str]] = []
    for b in [*brands, *known]:
        if not _GOLF_END.search(b):
            continue
        stem = _GOLF_END.sub("", b).strip()
        n = _norm(stem)
        if not clean(stem) or (len(n) < 3 if _HANGUL_BRAND.match(n) else len(re.sub(r"[^a-z]", "", n)) < 4):
            continue
        pattern = _stem_pattern(stem)
        if pattern.search(title or ""):
            found.append((len(n), b))
    return max(found)[1] if found else None


@functools.lru_cache(maxsize=None)
def _stem_pattern(stem: str) -> re.Pattern[str]:
    n = _norm(stem)
    if _HANGUL_BRAND.match(n):
        return re.compile(r"^\s*" + r"\s*".join(map(re.escape, n)) + r"(?![가-힣])")
    return re.compile(r"^\s*" + re.escape(stem) + r"(?![A-Za-z0-9])", re.I)


# a row may start with a bullet ("- Brand : 69", 13370257430) and the Korean label may be "브랜드 이름" (a machine
# translation of "Brand Name": "브랜드 이름 | pgm", 12178085899; both 2026-11-16, the wedge-set review)
_ROW_LEAD = r"(?im)^[ \t]*(?:[-•·*][ \t]*)?"
_ROW_VALUE = r"[ \t]*[|:：][ \t]*([^\n|]{2,60}?)[ \t]*$"
_BRAND_ROW = re.compile(_ROW_LEAD + r"(?:brand(?:[ \t]*name)?|브랜드(?:[ \t]*(?:명|이름))?)" + _ROW_VALUE)
# the maker's row of the same table: a Brand row that is a bare number takes it when it starts with that number
# ("Brand Name | 69" + "Manufacturer | 69 Golf": 13370257430, 13016152694, 2026-11-16; the specs' 브랜드 and 제조사
# rows say "69" only, and a bare number is no brand)
_MAKER_ROW = re.compile(_ROW_LEAD + r"(?:manufacturer(?:[ \t]*name)?|maker|제조(?:사|자|업체|원)(?:\(사\))?)" + _ROW_VALUE)
# a factory's or a trader's name in a Manufacturer row (Amazon imports: "Shenzhen … Technology Co., Ltd."), not a brand
_FACTORY = re.compile(r"(?i)trading|shenzhen|guangzhou|dongguan|xiamen|ningbo|technology|\btech\b|industr|manufactur"
                      r"|factory|import|export|e-?commerce|international|group|enterprise|co\.,|有限|公司|china|중국")
_ROW_TAIL = re.compile(r"\s*(?:품목|부품|모델)\s*번호.*$|\s*(?:item|part|model)\s*(?:no|number|#).*$", re.I)


def described(description: str | None) -> list[str]:
    """The firms the description's Brand rows name, in order (a part number after the name cut; a slogan of five
    words or more, no firm: out; a bare number: the maker's row that starts with it, else out)."""
    out = []
    makers = [_ROW_TAIL.sub("", m).strip(" .,-") for m in _MAKER_ROW.findall(description or "")]
    brand_rows = _BRAND_ROW.findall(description or "")
    for raw in brand_rows:
        name = _ROW_TAIL.sub("", raw).strip(" .,-")
        if name.replace(" ", "").isdigit():
            number = name.replace(" ", "")
            name = next((m for m in makers if re.match(re.escape(number) + r"\s+[^\d\s]", m)), "")
        if not name or len(name.split()) > 4 or not (kept := clean(name)):
            continue
        # the name as clean() keeps it: "Brand Name | Money Club Chipper" names Money Club (2026-11-18, the chipper
        # review: 18 chippers went out as the vendor "Money Club Chipper", 2 as "Money Club"); a Korean name the cut
        # would shorten at another word stays whole ("머니 클럽" is not "머니")
        if not re.search(r"[가-힣]", re.sub(r"치퍼|칩퍼", "", name[len(kept):])):
            name = kept
        if name not in out:
            out.append(name)
    if not out and brand_rows and all(_NO_FIRM.search(_ROW_TAIL.sub("", r).strip(" .,-")) for r in brand_rows):
        # every Brand row names no firm ("Brand | Generic"): the maker's row, as written ("Manufacturer | Alpha Golf",
        # 13382512411; "Bermuda Golf Company", 12178263465; 2026-11-17, the wedge-set review C31). A factory or a
        # trading firm ("Shenzhen … Technology Co., Ltd.") is not the brand; Co. / Company stay (the dictionary's).
        out = [m for m in makers if m and len(m.split()) <= 4 and not _FACTORY.search(m) and clean(m)][:1]
    return out


# a page pointer, not a value ("상세설명참조", "별도표기", "문의")
_POINTER = re.compile(r"참조|참고|상세|표기|페이지|설명|별도|문의|확인")
_LEAD_TAGS = re.compile(r"^\s*(?:[(\[][^)\]]*[)\]]\s*)*")


def release_brand(value: str | None, title: str | None) -> str | None:
    """The brand a seller wrote in the notice's 동일 모델의 출시연월 row (the model's release month) when it is the
    title's first word (2026-11-17, the wedge-set review C03: agency 100217952 writes "USPA" / "페스트니스" there,
    13582215582, 12872703429). No digit (a date), no page pointer, a firm (clean), the title's first word after its
    bracket tags ("(병행)")."""
    if not value or re.search(r"\d", value) or _POINTER.search(value):
        return None
    name = clean(value)
    words = _LEAD_TAGS.sub("", title or "").split()
    return name if name and words and _norm(words[0]) == _norm(name) else None


def _own_shop(name: str, store: set[str]) -> bool:
    words = name.split()
    return len(words) <= 3 and any(_norm("".join(w)) in store for w in itertools.permutations(words))


def decide(title: str | None, origin: str | None, brands: list[str], rows: list[str],
           known: list[str] | None = None, description: str | None = None,
           release: str | None = None, store: set[str] | None = None,
           shop: dict[str, Any] | None = None, own_row: bool = False) -> tuple[str, str, list[str]]:
    """-> (brand, source, other candidates) for a product with no brand of its own (steps 3-7; known: the brand
    dictionary's Korean names, for a title that starts with one; release: the notice's 동일 모델의 출시연월 row;
    own_row: its 브랜드 row named the seller's own shop and the reseller rule dropped it, in a category with
    own_brand_wordmark: no Latin phrase of the images then)."""
    titled = in_title(title, brands)
    if titled:
        return titled[0], "title", titled[1:]
    first = leading(title, known or [])
    if first:
        return first, "title_known", []
    word = as_word(title, known or [])
    if word:
        return word, "title_word", []
    stem = title_stem(title, brands, known or [])
    if stem:
        return stem, "title_stem", []
    # a row's Latin brand in the dictionary's spelling ("브랜드 이름 | pgm": PGM, as the shop's other PGM products, so
    # the brand does not change by its case alone; 2026-11-16)
    rows_named = [next((k for k in known or [] if not _HANGUL_BRAND.match(_norm(k)) and _norm(k) == _norm(n)), n)
                  for n in described(description)]
    if rows_named:
        return rows_named[0], "description_row", rows_named[1:3]
    # the seller's own shop in the brackets is no importer ("중국산(수수협력사 co.)" by the shop 수수: 2026-11-18, once
    # resellers_own dropped the same phrase from the brand row; store: the shop's name and legal name, normalized), its
    # words in any order too ("중국산(프롬 조이 협력사)" by the shop 조이프롬, 12657977112)
    dist = [d for d in distributors(origin) if not _own_shop(d, store or set())]
    if dist:
        return dist[0], "origin", dist[1:]
    if own_row:                                   # the shop's own label before a brand its photos show (2026-11-21: a
        label = shop_label(shop, title, own_row)  # "Volvik" prop in 봉선댁's photos became the vendor, 6465420393)
        if label:
            return label, "shop_label", []
    seen = in_images(rows, brands)
    if seen:
        top = [b for b, _ in seen.most_common()]
        return top[0], "images_text", top[1:3]
    own = own_brand_shown(shop, rows + (description or "").splitlines())   # before a slogan the images repeat
    if own:                                                                  # ("EVER YDAY": 11519647149, 2026-11-19)
        return own, "shop_wordmark", []
    # the shop's own label in apparel (`shop` is given only in a category with own_brand_wordmark; 2026-11-21, the
    # second windbreaker pilot's review, the owner: fix the brands): its 브랜드 row named the shop and its maker is
    # "<shop> 협력업체" (`own_row`: a contract factory sewing the shop's label, 카멜브리즈 x6, 투솜, 프롬그레이), or the title
    # starts with the shop's name (락골프, 수아무아); a club reseller (재팬도코도코: no own_brand_wordmark there) stays none
    label = shop_label(shop, title, own_row)
    if label:
        return label, "shop_label", []
    # ... and when the 브랜드 row named the shop's own label (dropped: "<shop> 협력업체" the maker) and its texts do not
    # show it as above, the slogan is still no brand: none, the house vendor (2026-11-20, the knit cardigan review:
    # 카멜브리즈's "EVER YDAY", 11573884405; 내추럴모드's "WHITE TEE", 11442719270); the owner may name the label
    latin = [] if own_row else [(p, n) for p, n in latin_phrases(rows).most_common() if n >= MIN_LATIN]
    if latin:
        return latin[0][0], "images_text_latin", [p for p, _ in latin[1:3]]
    released = release_brand(release, title)
    if released:
        return released, "release_row", []
    return NO_BRAND, "none", []


def _description(value: Any) -> str:
    return "\n".join(map(str, value)) if isinstance(value, list) else str(value or "")


# the parts' makers a title names beside the club's brand (shafts, grips): never the brand of the set
_COMPONENT = re.compile(r"(?i)다이나믹\s*골드|다골|트루\s*템퍼|엔에스\s*프로|n\.?s\.?\s*pro|모듀스|modus|kbs|프로젝트\s*x"
                        r"|project\s*x|후지쿠라|fujikura|미쯔비시|mitsubishi|그라파이트\s*디자인|투어\s*ad|골프\s*프라이드"
                        r"|golf\s*pride|dynamic\s*gold|true\s*temper|aldila|\bust\b")


def store_named(brand: str | None, title: str | None, store_names: set[str], known: list[str]) -> bool:
    """The brand row (or the maker) is the seller's own shop name while the title names another brand: the shop, not
    the brand (2026-11-17, the wedge-set review C02: 제우스골프, the shop, as the maker of a 팀요시무라 wedge set,
    10149539327; 메가스피어 on a PGM set, 13245513614). Exact equality with the shop's name or its legal name only; a
    shop that writes its own name in the title sells its brand (아화골프, US키즈골프, 스컬독: stays); a combination set
    (조합) and a part's maker in the title (a shaft, a grip) are not another brand."""
    n = _norm(brand)
    if not n or n not in store_names or n in _norm(title) or "조합" in (title or ""):
        return False
    # ... or a Korean one glued to the next word ("SW 마젤치퍼": 2026-11-18, the chipper review, 13861214656, 12896056499,
    # 13393153836, MAZEL C9 went out as the shops Swan Goods, Yellow Swan, Yellow Rabbit): in_title, word start
    other = leading(title, known) or as_word(title, known) \
        or next(iter(in_title(title, [k for k in known if _HANGUL_BRAND.match(_norm(k))])), None)
    return bool(other) and _norm(other) != n and not _COMPONENT.search(other or "")


def fill(prepared: list[Any], rows_of: Callable[[str], list[str]],
         origins: dict[str, str | None], texts: Callable[[Any], list[dict[str, str]]],
         known: list[str] | None = None, by_owner: dict[str, str] | None = None,
         releases: dict[str, str | None] | None = None, stores: dict[str, set[str]] | None = None,
         shops: dict[str, dict[str, Any]] | None = None, own_rows: set[str] | None = None) -> int:
    """Give every product without a brand one (steps 3-7), add the note and the brand to its texts. rows_of(key): the
    images' OCR rows of the product; origins: {key: 원산지 as the page states it}; by_owner: {key: brand} the owner
    read on the photos (source "owner", before every step; 2026-11-15: ALVO stamped on the heads, no text naming it);
    releases: {key: the notice's 동일 모델의 출시연월 value} (the last step before 노브랜드); stores: {key: the seller's
    shop name and legal name, normalized} (a brand that is the shop's name: store_named); own_rows: the keys whose
    브랜드 row the reseller rule dropped, in a category with own_brand_wordmark (decide's own_row). -> how many were
    filled."""
    by_owner = by_owner or {}
    shop_named: dict[str, str] = {}
    for p in prepared:                                  # before the shop's brands: the shop's name is none of them
        product = p["product"]
        if p["key"] not in by_owner and str(product.get("brand_source") or "").startswith(("specs:", "manufacturer:")) \
                and store_named(product.get("brand_ko"), product.get("title_ko"), (stores or {}).get(p["key"], set()),
                                known or []):
            shop_named[p["key"]] = product["brand_ko"]
            product["brand_ko"] = product["brand_source"] = None
    brands = shop_brands(prepared)
    n = 0
    for p in prepared:
        product = p["product"]
        if product.get("brand_ko") and p["key"] not in by_owner:
            continue
        others: list[str]
        if p["key"] in by_owner:
            brand, source, others = by_owner[p["key"]], "owner", []
        else:
            brand, source, others = decide(product.get("title_ko"), origins.get(p["key"]), brands, rows_of(p["key"]),
                                           known, _description(product.get("description_ko")),
                                           (releases or {}).get(p["key"]), (stores or {}).get(p["key"]),
                                           (shops or {}).get(p["key"]), p["key"] in (own_rows or set()))
        p["product"]["brand_ko"], p["product"]["brand_source"] = brand, source
        p["notes"] = [x for x in p["notes"] if x["code"] != "brand_fallback"] + [
            {"code": "brand_fallback", "detail": f"{source}: {brand}" + (f"; also {', '.join(others)}" if others else "")
             + (f"; not the seller's shop {shop_named[p['key']]}" if p["key"] in shop_named else "")}]
        p["texts"] = texts(p["product"])
        n += 1
    return n
