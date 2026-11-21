"""Offline tests for brand_fallback.py: a brand for every prepared product. Cases are the 6 sets of the 100-run
check (2026-11-08) with no brand stated.

    .venv/bin/python -m pytest scripts/test_brand_fallback.py -q
"""
import pytest

import brand_fallback as B
from transform import _texts

BRANDS = ["무쯔미혼마", "테일러메이드", "캘러웨이", "젝시오", "야마하", "혼마", "핑"]


def test_shop_brands_are_the_stated_ones_longest_first():
    prepared = [{"product": {"brand_ko": b, "brand_source": s}} for b, s in [
        ("혼마", "specs:브랜드"), ("무쯔미혼마", "search_info.brandName"), ("(주)삼양", "manufacturer:x"), ("노브랜드", "none")]]
    assert B.shop_brands(prepared) == ["무쯔미혼마", "혼마"]


def test_title_first_brand_and_a_combination():
    assert B.decide("혼마코리아 비즐3 남성골프채풀세트", None, BRANDS, []) == ("혼마", "title", [])
    assert B.decide("던롭스포츠코리아 젝시오 12 야마하 남성 조합골프채", None, BRANDS, []) == ("젝시오", "title", ["야마하"])
    assert B.decide("TAYLORMADE 테일러메이드풀세트", None, BRANDS, [])[0] == "테일러메이드"
    assert B.in_title("무쯔미혼마 풀세트", BRANDS) == ["무쯔미혼마"]          # not also 혼마 inside it


def test_origin_importer_then_images():
    assert B.decide("골프 풀세트", "일본산(혼마코리아)", ["캘러웨이"], []) == ("혼마코리아", "origin", [])
    assert B.decide("골프 풀세트", "중국산(상세정보참조)", ["캘러웨이"], ["캘러웨이 정품", "캘러웨이"])[:2] == \
        ("캘러웨이", "images_text")
    rows = ["BEN SAYERS M15"] * 6 + ["Benny Ladies"]
    assert B.decide("초중급 남성 골프채 풀세트", "중국산(상세정보참조)", BRANDS, rows)[:2] == ("BEN SAYERS", "images_text_latin")
    assert B.decide("입문용 성인 골프채", "국내산", BRANDS, ["Golf1004"]) == (B.NO_BRAND, "none", [])


def test_korean_brand_only_where_a_word_starts():
    """13445783517, 2026-11-11: "쇼핑골프처음" (a shop's name) is not 핑 (Ping); the Latin brand the images repeat wins."""
    rows = ["믿을수있는브랜드골프전문쇼핑골프처음", "www.houma.co.kr / 안심"] + ["BEN SAYERS 2026"] * 6
    assert B.in_images(rows, ["핑", "핑골프", "HOUMA"]) == {}               # nor the retailer's web address
    assert B.decide("초중급 남성 골프채 풀세트", None, ["핑", "HOUMA"], rows)[:2] == ("BEN SAYERS", "images_text_latin")
    assert B.in_images(["핑 G430 정품", "정품 핑골프"], ["핑", "핑골프"]) == {"핑": 2, "핑골프": 1}
    assert B.in_images(["무쯔미혼마 정품"], ["혼마", "무쯔미혼마"]) == {"무쯔미혼마": 1}
    assert B.in_images(["정품캘러웨이", "CALLAWAY"], ["캘러웨이", "Callaway"]) == {"Callaway": 1}   # glued: missed
    assert B.in_images(["어프로치부터 / 치핑까지!", "핑크 그립", "핑거 가드"], ["핑"]) == {}    # 13625754692
    assert B.in_images(["테일러 메이드 정품", "펜타곤 야마모토"], ["테일러메이드", "펜타곤 야마모토"]) == \
        {"테일러메이드": 1, "펜타곤 야마모토": 1}
    assert B.in_images(["핑골프공식대리점www.pinggolf.co.kr"], ["핑골프"]) == {"핑골프": 1}  # only the address goes
    assert B.in_images(["T.M 5.5 정품"], ["T.M"]) == {"T.M": 1}


def test_other_is_not_a_shop_brand():
    """10697131625, 2026-11-11: transform drops a 브랜드 row of 기타, so it never becomes a shop brand the images'
    text could find (it had given three Ben Sayers sets the brand 기타 -> TaylorMade)."""
    other = {"key": "a", "notes": [], "product": {"brand_ko": None, "brand_source": None}}
    assert B.shop_brands([other]) == []


def test_fill_adds_the_brand_its_text_and_a_note():
    known = {"key": "a", "notes": [], "product": {"brand_ko": "혼마", "brand_source": "specs:브랜드"}}
    product = {"title_ko": "혼마코리아 비즐3", "brand_ko": None, "brand_source": None, "options": [], "facts": [],
               "specs": [], "personalization": [], "addons": [], "reviews": []}
    missing = {"key": "b", "notes": [], "product": product, "texts": []}
    assert B.fill([known, missing], lambda k: [], {"b": "일본산(혼마코리아)"}, _texts) == 1
    assert (product["brand_ko"], product["brand_source"]) == ("혼마", "title")
    assert missing["notes"] == [{"code": "brand_fallback", "detail": "title: 혼마"}]
    assert {"kind": "brand", "ko": "혼마"}.items() <= next(t for t in missing["texts"] if t["kind"] == "brand").items()


@pytest.mark.parametrize("name, trade", [
    # 2026-11-12, the junior clubs' first 30: a shop's or a supplier's name is no brand
    ("세모물상점", True), ("세모물상점 협력업체", True), ("스퀘어홀딩", True), ("(주)삼양인터내셔날", True),
    ("석교상사", True), ("내면무역", True), ("한국유통", True), ("삼양인터내셔널", True),
    ("혼마코리아", False), ("던롭코리아", False), ("스컬독", False), ("아화", False), ("PGM", False),
    ("유니코스 협력사", False), ("캘러웨이골프", False), ("", False),
])
def test_a_trading_name_is_no_brand(name, trade):
    assert B.trade_name(name) is trade


def test_a_trading_company_in_the_origin_is_no_distributor():
    assert B.distributors("중국산(세모물상점 협력업체)") == []
    assert B.distributors("중국(스퀘어홀딩)") == []
    assert B.distributors("일본산(혼마코리아)") == ["혼마코리아"]


def _rows(name):
    import json
    import os
    from description_images import image_rows
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "description_images", name + ".json")
    with open(path, encoding="utf-8") as f:
        return [r for img in image_rows(json.load(f)) for r in img]


@pytest.mark.parametrize("name, title, origin, brand", [
    # 2026-11-12: the shop's name (세모물상점) and a supplier (스퀘어홀딩) were the brands; the images name the maker
    ("9498347018", "주니어골프채 어린이골프채 초등학생 7번아이언 세트 아동", "중국(세모물상점 협력업체)", "인파로"),
    ("7151166811", "PMG 아동용 주니어 어린이 골프채 유아 초등학생 골프클럽세트", "중국(스퀘어홀딩)", "PGM"),
])
def test_the_images_name_the_maker_when_the_seller_names_a_trader(name, title, origin, brand):
    got, source, _ = B.decide(title, origin, ["인파로", "PGM", "스컬독", "아화"], _rows(name))
    assert (got, source) == (brand, "images_text")


@pytest.mark.parametrize("name, brand", [
    # 2026-11-12, junior clubs: what sellers write in the 브랜드 / 제조사 rows
    ("코알라(200874)", "코알라"), ("지브이골프코리아(자체제작 상품)", "지브이골프코리아"), ("던롭 던롭", "던롭"),
    ("(주)감씨", None), ("진월드스타 어린이용 주니어 골프 클럽 아이언 퍼터 드라이버", "진월드스타"),
    ("6~8세 퍼터", None), ("우리쇼핑하자 협력 업체", None), ("유무상회", None), ("건이네 만물상", None),
    ("상아네", None), ("세모물상점", None), ("유니코스 협력사", "유니코스"),
    ("GB", "GB"), ("핑", "핑"), ("아화골프", "아화골프"), ("U.S. Kids Golf", "U.S. Kids Golf"),
    ("혼마코리아", "혼마코리아"), ("US키즈골프", "US키즈골프"), ("", None),
    # 2026-11-13, the junior pilot: words that name no firm, the seller's shop
    ("주니어", None), ("주니어 어린이용 골프채 클럽", None), ("어린이용", None), ("키즈짐", "키즈짐"),
    ("별도표기", None), ("중국", None), ("중국 브랜드", None), ("중국 제조사", None), ("중국산", None),
    ("협력사", None), ("협력업체", None), ("막팔아스토어", None), ("보라잡화점", None), ("해외몰", None),
    ("빅토르몰 제휴", None), ("EVEN", "EVEN"), ("알수없음", None), ("미상", None),
])
def test_a_sellers_brand_row_cleaned(name, brand):
    assert B.clean(name) == brand


def test_a_wholesaler_or_a_store_in_the_rows_is_no_brand():
    """2026-11-19, the seller-vendor review: (주)감씨, the 공급사 of dozens of shops reselling Inparo, and 골드벙커, a
    store, in the 브랜드 / 제조사 rows: 40 live junior products went out as the vendors Gamssi and Gold Bunker. No brand
    there; the images name the maker (13826709716: "인파로만의 유니크한 컬러", "인파로 제품은 … PL 보험"). (주) inside the
    origin's brackets is no firm of its own ("중국산((주)감씨)" was read as the brand 주)."""
    for name in ("(주)감씨", "감씨", "㈜감씨", "골드벙커", "골드 벙커", "골프벙커", "Gold Bunker", "GAMSSI"):
        assert B.clean(name) is None, name
    assert B.distributors("중국산((주)감씨)") == [] and B.distributors("중국산(골드벙커)") == []
    assert B.distributors("일본산((주)혼마코리아)") == ["혼마코리아"]
    got, source, _ = B.decide("주니어 골프 클럽 9-12세 - 아이언/퍼터/드라이버", "중국산(골드벙커)",
                              ["인파로", "PGM", "GB"], _rows("13826709716"))      # the title without its Inparo JR.
    assert (got, source) == ("인파로", "images_text")


def test_a_latin_brand_is_read_as_whole_words_only():
    # 13425122164: the junior brand GB inside "golf bag" made a Ben Sayers set GB
    rows = ["BEN SAYERS golf bag included", "GOLF BAG", "Stand bag"]
    assert B.in_images(rows, ["GB", "PGM"]) == {}
    assert B.in_images(["GB Junior driver", "gb"], ["GB"]) == {"GB": 2}
    assert B.in_images(["US KIDS GOLF ultralight", "U.S.Kids Golf"], ["U.S. Kids Golf"]) == {"U.S. Kids Golf": 2}
    assert B.in_images(["PGM골프 정품"], ["PGM"]) == {"PGM": 1}           # a Korean word after it: still a word end


def test_the_origin_names_the_firm_not_the_making():
    assert B.distributors("중국산(중국 oem / 인파로)") == ["인파로"]       # 5859220164
    assert B.distributors("중국(OEM)") == []


def test_a_brand_inside_a_korean_branch_name_comes_last():
    # 7202588289: "던롭스포츠코리아 젝시오 12" is an XXIO set, imported by Dunlop's Korean branch
    assert B.in_title("던롭스포츠코리아 젝시오 12 여성골프채", ["젝시오", "던롭"]) == ["젝시오", "던롭"]
    assert B.in_title("던롭 클리브랜드 골프 주니어 세트", ["클리브랜드", "던롭"]) == ["던롭", "클리브랜드"]
    assert B.in_title("캘러웨이코리아 정품 주니어", ["캘러웨이"]) == ["캘러웨이"]


@pytest.mark.parametrize("name, maker, store, own", [
    # 11674983361, 2026-11-12: the reselling shop's own name in the brand row, "<shop>협력사" as the maker
    ("재팬도코도코", "재팬도코도코협력사", {"name": "재팬 도코도코", "business": {"legal_name": "재팬도코도코"}}, True),
    ("홈앤컴", "홈앤컴협력사", {"name": "홈앤컴"}, True),
    ("굿세라", "굿세라 협력사", {"name": "굿세라"}, True),
    ("스컬독", "스컬독", {"name": "스컬독"}, False),                  # a shop selling its own brand: no 협력
    ("버디온", "B tree", {"name": "버디온"}, False),
    ("인파로", "모아와치협력사", {"name": "모아와치"}, False),          # the brand is another's: it stays
    ("유니코스", "유니코스 협력사", {"name": "골프마켓"}, False),       # a maker's contract maker, another shop
])
def test_a_reselling_shops_own_name_is_no_brand(name, maker, store, own):
    assert B.resellers_own(name, maker, store) is own


def test_a_known_brand_starting_the_title():
    # 13324651260: an import with no brand row, maker or importer; the title starts with the brand
    known = ["프랭클린 스포츠", "아화", "핑", "인파로"]
    assert B.leading("프랭클린 스포츠 조절 가능한 유소년 골프 세트 Red", known) == "프랭클린 스포츠"
    assert B.leading("주니어 골프채 프랭클린 스포츠", known) is None          # only where the title starts
    assert B.leading("핑크 주니어 골프채", known) is None                     # one syllable: never
    assert B.decide("프랭클린 스포츠 조절 가능한 유소년 골프 세트", None, [], [], known) == (
        "프랭클린 스포츠", "title_known", [])
    assert B.decide("프랭클린 스포츠 유소년 세트", None, [], [])[1] == "none"   # no dictionary: as before


def test_a_known_brand_as_a_word_of_its_own_anywhere_in_the_title():
    # 2026-11-15, the wedge pilot: agency imports held as agency_no_brand with the maker in the title
    known = ["라즈러스", "야마토", "버뮤다", "GoSports", "핑", "PGM"]
    assert B.as_word("남성 또는 개인용 라즈러스 프리미엄 단조 골프 웨지 세트", known) == "라즈러스"
    assert B.as_word("남성용 버뮤다 프리미엄 골프 웨지 세트 - 52 56 60도", known) == "버뮤다"
    assert B.as_word("GoSports Illegal Max Spin 골프 웨지 세트", known) == "GoSports"
    assert B.as_word("gosports 웨지", known) == "GoSports"                    # any case
    assert B.as_word("야마토골프 웨지", known) is None                          # inside a longer word: no
    assert B.as_word("핑크 웨지 세트", known) is None and B.as_word("핑 웨지", known) is None   # three letters at least
    assert B.as_word("XPGMX 웨지", known) is None
    assert B.decide("남성용 버뮤다 웨지 세트", None, [], [], known) == ("버뮤다", "title_word", [])


def test_the_cached_patterns_answer_each_text_anew():
    # 2026-11-15: the patterns are compiled once per brand (lru_cache); a second text must not reuse a first match
    known = ["라즈러스", "GoSports", "PGM"]
    for _ in range(2):
        assert B.as_word("남성용 라즈러스 웨지", known) == "라즈러스"
        assert B.as_word("남성용 웨지 세트", known) is None
        assert B.as_word("GOSPORTS 웨지", known) == "GoSports"
        assert B.in_images(["핑 G430", "핑 골프"], ["핑"]) == {"핑": 2}
        assert B.in_images(["쇼핑골프 치핑"], ["핑"]) == {}
        assert B.in_images(["golf bag"], ["GB"]) == {}
        assert B.in_images(["US KIDS GOLF 정품"], ["U.S. Kids Golf"]) == {"U.S. Kids Golf": 1}
    assert B._word_pattern("핑") is None and B._word_pattern("야마토") is not None
    assert B._word_pattern("주니어") is None                                    # not a firm
    assert B._count_pattern("T.M") is not None and B._count_pattern("혼마 코리아") is not None


def test_a_brand_row_of_the_description():
    # 2026-11-15: agency imports copy the spec table ("Brand | WENGH", 13468853832) where the images gave "EVEN"
    assert B.described("Golf Club Loft | 56 Degrees\nBrand | WENGH\nBrand Name | WENGH") == ["WENGH"]
    assert B.described("브랜드: pgm 품목 번호: MTG025") == ["pgm"]
    assert B.described("Brand | 69\nBrand | 69 Golf") == ["69 Golf"]                         # a bare number: no
    assert B.described("Brand | PGF LABS FORGING THE FUTURE OF GOLF\nBrand | PGF LAB") == ["PGF LAB"]
    assert B.described("Brand | 골프\nbrand new design") == []
    assert B.decide("골프 웨지 세트", None, [], ["EVEN EVEN EVEN"], [], "Brand | WENGH") == (
        "WENGH", "description_row", [])


def test_a_generic_word_is_never_a_shop_brand():
    # 2026-11-13: "주니어" in three brand rows became a shop brand, then the brand of 74 junior titles
    prepared = [{"product": {"brand_ko": B.clean("주니어"), "brand_source": "specs:브랜드"}},
                {"product": {"brand_ko": "인파로", "brand_source": "specs:브랜드"}}]
    assert B.shop_brands(prepared) == ["인파로"]
    assert B.decide("초등학생골프채 주니어 드라이버 퍼터", None, ["인파로"], [])[1] == "none"


@pytest.mark.parametrize("word", ["골프", "골프 용품", "골프클럽", "GOLF", "Golf", "스포츠", "남성용", "여성용", "남녀공용",
                                  "ㅊ", "정식수입정품 또는 정식제조정품", "브랜드없음", "제조자 미상",
                                  "UnKnown_ピン", "UnKnown_ヨネックス"])
def test_the_sport_is_no_brand(word):
    # 10979283479, 2026-11-14: "골프" in the 브랜드 row became a shop brand, then the brand of every title saying 골프
    # (55 products published with the vendor "Golf"); a record prepared before, and the dictionary's "골프" -> "Golf"
    assert B.clean(word) is None
    prepared = [{"product": {"brand_ko": word, "brand_source": "specs:브랜드"}},
                {"product": {"brand_ko": "인파로", "brand_source": "specs:브랜드"}}]
    assert B.shop_brands(prepared) == ["인파로"]
    assert B.leading("골프 주니어 세트 인파로", [word, "인파로"]) is None
    assert B.clean("아화골프") == "아화골프" and B.clean("골프존") == "골프존"     # a name with the word stays
    assert B.clean("Artist Unknown") == "Artist Unknown"                    # C23: only Naver's "UnKnown_…" placeholder


def test_the_origin_names_no_partner_or_mall():
    assert B.distributors("중국(협력사)") == []
    assert B.distributors("중국(해외몰)") == []
    assert B.distributors("중국(새롭다 협력사)") == ["새롭다"]


def test_a_spec_tables_headings_are_no_latin_brand():
    rows = ["DEGREE LOFT"] * 6 + ["BEN SAYERS"] * 5                    # 13024208178
    assert B.decide("주니어 세트", None, [], rows)[:2] == ("BEN SAYERS", "images_text_latin")
    assert B.decide("주니어 세트", None, [], ["DEGREE LOFT"] * 6)[1] == "none"


def test_generic_is_no_brand():
    """2026-11-15: two Bermuda wedge sets (13370440703, 13099713088) went out under the vendor "Generic"."""
    import brand_fallback as bf
    assert bf.clean("Generic") is None and bf.clean("generic") is None and bf.clean("제네릭") is None
    assert bf.clean("Generic Golf Co") == "Generic Golf Co"                   # only the whole value


def test_other_brand_and_the_word_brand_are_no_brand():
    """2026-11-17: "기타 BRAND" went out as the vendor "Other BRAND" (12789751830) and "상표" as "Brand" (12619693409)."""
    import brand_fallback as bf
    for word in ("기타 BRAND", "기타 brand", "기타브랜드", "기타", "상표", "브랜드"):
        assert bf.clean(word) is None, word
    assert bf.clean("상표골프") == "상표골프" and bf.clean("기타스") == "기타스"         # only the whole value


def test_a_korean_brand_inside_a_longer_word_is_no_brand_of_the_title():
    """2026-11-15: 이디스 (Edis) was read in "시니어 레이디스" (ladies), a Majek K5 set (13469043292) went out as Edis;
    기가 in "성장기 가슴패드". A Korean brand counts where a word starts, as in the images."""
    import brand_fallback as bf
    brands = ["이디스", "기가", "야마토", "PRECISE"]
    assert bf.in_title("시니어 레이디스 골프 웨지 세트 52 56 60도", brands) == []
    assert bf.in_title("스포츠브라 주니어 성장기 가슴패드", brands) == []
    assert bf.in_title("이디스 주니어 골프 세트", brands) == ["이디스"]
    assert bf.in_title("[야마토] 웨지 세트", brands) == ["야마토"] and bf.in_title("야 마 토 웨지", brands) == ["야마토"]


def test_a_latin_brand_read_once_in_a_slogan_is_no_brand_of_the_images():
    """2026-11-15: "PRECISE AIMING FEEDBACK" in a description image made PRECISE (a real shop brand) the vendor of a
    XINGGM wedge set (13830322401). A lone logo row, or the brand twice, still counts."""
    import brand_fallback as bf
    brands = ["PRECISE", "XXIO"]
    assert not bf.in_images(["PRECISE AIMING FEEDBACK", "로프트 52 56"], brands)
    assert bf.in_images(["PRECISE", "로프트 52"], brands) == {"PRECISE": 1}
    assert bf.in_images(["PRECISE 정밀 웨지 세트"], brands) == {"PRECISE": 1}                 # Hangul in the row
    assert bf.in_images(["PRECISE AIMING FEEDBACK", "PRECISE GOLF"], brands) == {"PRECISE": 2}


def test_a_title_that_starts_with_a_golf_brands_stem():
    """C27 (2026-11-17, the wedge-set review): "Vice Golf" / "미스테리 골프" whose stem starts the title (13830312401
    "Vice Boost Plus 남성 골프 웨지 세트", 13000456333 "미스테리 R라인 웨지 세트") was not found: the shop brand is
    not in the title whole, the dictionary's name does not start it."""
    assert B.decide("Vice Boost Plus 남성 골프 웨지 세트", None, ["Vice Golf"], []) == ("Vice Golf", "title_stem", [])
    assert B.decide("미스테리 R라인 웨지 세트 52도,57도 골프채", None, [], [], ["미스테리 골프"]) == (
        "미스테리 골프", "title_stem", [])
    assert B.decide("VICE 프로 웨지", None, ["Vice Golf"], [])[1] == "title_stem"          # any case
    # a stem too short (Latin under four letters, Hangul under three), not at the start, inside a longer word
    assert B.decide("AGX 웨지 세트", None, ["AGXGOLF"], [])[1] == "none"
    assert B.decide("기가 웨지 세트", None, [], [], ["기가골프"])[1] == "none"
    assert B.decide("웨지 세트 Vice Boost", None, ["Vice Golf"], [])[1] == "none"
    assert B.decide("Vicex 웨지 세트", None, ["Vice Golf"], [])[1] == "none"
    assert B.decide("미스테리아 웨지 세트", None, [], [], ["미스테리 골프"])[1] == "none"
    # a step before it wins: the shop brand whole in the title
    assert B.decide("Vice Golf 웨지 세트", None, ["Vice Golf"], [])[:2] == ("Vice Golf", "title")


def test_a_generic_brand_row_takes_the_makers_row():
    """C31 (2026-11-17, the wedge-set review): Amazon's "Brand | Generic" with "Manufacturer | Alpha Golf" (13382512411)
    went out with no brand; the maker is taken as written when every Brand row names no firm."""
    desc = "Brand | Generic\nManufacturer | Alpha Golf\nBrand | Generic"
    assert B.described(desc) == ["Alpha Golf"]
    assert B.decide("골프 웨지 세트", None, [], [], [], desc) == ("Alpha Golf", "description_row", [])
    assert B.described("Brand Name | Generic\nManufacturer | Bermuda Golf Company") == ["Bermuda Golf Company"]
    # a factory or a trader is no brand; a real Brand row wins over the maker; no Brand row: the maker is not read
    assert B.described("Brand | Generic\nManufacturer | Shenzhen Golf Technology Co., Ltd.") == []
    assert B.described("Brand | Generic\nManufacturer | Xiamen Sports Trading") == []
    assert B.described("Brand | WENGH\nManufacturer | Alpha Golf") == ["WENGH"]
    assert B.described("Manufacturer | Alpha Golf") == []
    assert B.described("Brand | Generic\nManufacturer | Generic") == []


def test_the_release_row_names_the_brand_the_title_starts_with():
    """C03 (2026-11-17, the wedge-set review): agency 100217952 writes the brand in the notice's 동일 모델의 출시연월
    row ("USPA" for "(병행) USPA P200T 웨지세트", 13582215582); the last step before 노브랜드."""
    title = "(병행) USPA P200T 웨지세트 (Aw Sw) R WA3640999"
    assert B.decide(title, None, [], [], [], None, "USPA") == ("USPA", "release_row", [])
    assert B.decide("(병행) 페스트니스 웨지세트 50도 56도", None, [], [], [], None, "페스트니스")[:2] == (
        "페스트니스", "release_row")
    # a date, a page pointer, no firm, a word the title does not start with: no brand
    for value in ("2024.03", "상세설명참조", "매월생산", "BridgeStone", "골프", ""):
        assert B.decide("(병행) USPA P200T 웨지세트", None, [], [], [], None, value)[1] == "none", value
    assert B.release_brand("BridgeStone", "(병행) 브리지스톤 투어B 웨지세트") is None
    # a step before it wins: the description's Brand row
    assert B.decide(title, None, [], [], [], "Brand | Mystery", "USPA")[:2] == ("Mystery", "description_row")


def test_a_brand_that_is_the_sellers_shop_gives_way_to_the_titles_brand():
    """C02 (2026-11-17, the wedge-set review): the brand row 메가스피어 is the seller's shop (13245513614, "PGM 왼손 웨지
    골프채세트 …"); 제우스골프, the shop, as the maker of a 팀요시무라 set (10149539327). Exact equality with the shop's
    name, another brand in the title, no 조합 and no part's maker."""
    stores = {"m": {"메가스피어"}}
    assert B.store_named("메가스피어", "PGM 왼손 웨지 골프채세트 56도 60도", {"메가스피어"}, ["PGM"])
    assert not B.store_named("아화골프", "아화골프 주니어 세트", {"아화골프"}, ["아화골프", "PGM"])   # its own brand
    assert not B.store_named("US키즈골프", "주니어 골프 세트 7세", {"us키즈골프"}, ["PGM"])           # no other brand
    assert not B.store_named("메가스피어", "야마하 핑 조합 골프채", {"메가스피어"}, ["야마하"])        # a combination
    assert not B.store_named("메가스피어", "웨지 세트 다이나믹골드 S200", {"메가스피어"}, ["다이나믹골드"])  # a shaft
    assert not B.store_named("메가", "PGM 웨지 세트", {"메가스피어"}, ["PGM"])                      # not exact
    product = {"title_ko": "PGM 왼손 웨지 골프채세트 56도 60도", "brand_ko": "메가스피어", "brand_source": "specs:브랜드",
               "options": [], "facts": [], "specs": [], "personalization": [], "addons": [], "reviews": []}
    p = {"key": "m", "notes": [], "product": product, "texts": []}
    assert B.fill([p], lambda k: [], {}, _texts, ["PGM"], stores=stores) == 1
    assert (product["brand_ko"], product["brand_source"]) == ("PGM", "title_known")
    assert p["notes"][-1]["detail"] == "title_known: PGM; not the seller's shop 메가스피어"
    kept = {"key": "m", "notes": [], "product": {**product, "brand_ko": "메가스피어", "brand_source": "specs:브랜드"}}
    assert B.fill([kept], lambda k: [], {}, _texts, ["PGM"], {"m": "Megasphere"}, stores=stores) == 1   # the owner's
    assert kept["product"]["brand_ko"] == "Megasphere"


def _prepared_fixture(pid):
    """A real collected chipper (fixtures/collected/<pid>.json) through transform.prepare, as run_transform does."""
    import json
    import os

    from transform import prepare
    from transform_shops import rules_for
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures", "collected", pid + ".json"), encoding="utf-8") as f:
        return json.loads(json.dumps(prepare(json.load(f), rules_for("fairwardgolf"), "50002784-fixtures", 1),
                                     ensure_ascii=False))


@pytest.mark.parametrize("word", ["brand", "Brand", "BRAND", "브랜드.", "brand.", "치퍼", "칩퍼", "Chipper", "CHIPPER", "치퍼 CEAF"])
def test_the_word_brand_and_the_chipper_are_no_brand(word):
    """2026-11-18, the chipper review: rakuraku00 writes 브랜드=brand and 제조사=brand (9991649397, 9993129226,
    9993149923 went out as the vendor "brand", "brand CH809 Left-Handed Chipper"); 11158899277's rows say 치퍼, which
    became a shop brand and then the vendor "Chipper" of every title saying 치퍼 (MAZEL 10179980640, Pinemeadow
    13478213249, 7518807949, CHIPPER Lab 11664750138)."""
    assert B.clean(word) is None
    prepared = [{"product": {"brand_ko": word, "brand_source": "specs:브랜드"}},
                {"product": {"brand_ko": "월드이글", "brand_source": "specs:브랜드"}}]
    assert B.shop_brands(prepared) == ["월드이글"]                    # a record prepared before the rule
    assert B.decide("치퍼 칩퍼 어프로치웨지 시니어 칩퍼터 37도 CHIPPER", None, B.shop_brands(prepared), [],
                    [word])[1] == "none"                             # nor the dictionary's 치퍼 -> Chipper


def test_a_name_with_the_word_stays():
    assert B.clean("CHIPPER Lab") == "CHIPPER Lab" and B.clean("치퍼랩") == "치퍼랩"   # the maker of 11664750138
    assert B.clean("MAZEL 치퍼") == "MAZEL" and B.clean("Brandon") == "Brandon" and B.clean("브랜드명") == "브랜드명"
    # the chipper words end at a word (the review of 569b77f): a maker's 치퍼랩 is not cut mid-word, nor "치퍼 랩" lost
    assert B.clean("XYZ 치퍼랩") == "XYZ 치퍼랩" and B.clean("치퍼 랩") == "치퍼 랩"
    assert B.clean("XYZ 치퍼용") == "XYZ" and B.clean("XYZ 칩퍼터") == "XYZ" and B.clean("칩퍼터") is None


@pytest.mark.parametrize("pid", ["9991649397", "11158899277"])
def test_a_placeholder_row_leaves_the_brand_to_the_fallback(pid):
    """The real lines: neither the 브랜드 nor the 제조사 row ("brand" / "치퍼") is the brand or a spec row; the fallback
    takes the title's maker (월드 이글 CH809, as the shop's World Eagle) or none (일본 골프 치퍼: 노브랜드)."""
    p = _prepared_fixture(pid)
    assert p["product"]["brand_ko"] is None
    assert not [r for r in p["product"]["specs"] or [] if r["label_ko"] in ("브랜드", "제조사")]
    B.fill([p], lambda key: [], {}, _texts, known=["월드이글"])
    want = {"9991649397": ("월드이글", "title_known"), "11158899277": (B.NO_BRAND, "none")}[pid]
    assert (p["product"]["brand_ko"], p["product"]["brand_source"]) == want


def test_a_one_syllable_brand_ends_its_word_in_the_title():
    """2026-11-18, the chipper review: the shop brand 핑 (PING) was read in 핑크 (pink): 15 Intech EZ Roll / Extreme 5
    chippers (13241334423, 13762752610, ...) and the junior set 13848307900, published as PING. The real titles."""
    shop = ["무쯔미혼마", "마젤", "온오프", "핑"]
    for title in ["여성용 핑크 세트 골프채 7번아이언 주니어골프채 연습용 카본 클럽 샤프트",
                  "인텍 이지 롤 시니어 여성 오른손 핑크 골프 치퍼 - 33 인치",
                  "여성용 익스트림 5 골프 치퍼 36도 유틸리티 웨지 핑크 그래파이트 샤프트"]:
        assert B.in_title(title, shop) == []
    assert B.in_title("핑 PING 여성 G LE 3 골프채", shop) == ["핑"]             # 13110012279, a real PING
    assert B.in_title("핑골프 치퍼", shop) == ["핑"] and B.in_title("핑(골프) 치퍼", shop) == ["핑"]
    assert B.in_title("핑크 그립 핑 치퍼", shop) == ["핑"]                          # the word, not the colour
    assert B.in_title("SW 마젤치퍼 골프치퍼", shop) == ["마젤"]                     # two syllables: a word start only
    assert B.in_title("시니어 레이디스 세트", ["이디스"]) == []                       # as before (13469043292)
    assert B.in_title("핑크 무쯔미혼마 치퍼", ["무쯔미혼마", "혼마", "핑"]) == ["무쯔미혼마"]   # 혼마 not inside it


def test_a_brand_row_keeps_the_name_without_the_chipper():
    """2026-11-18, the chipper review: "Brand Name | Money Club Chipper" made 18 chippers the vendor "Money Club
    Chipper" (13551974523, 13552012620), 2 others "Money Club"; a Korean name the cut would shorten stays whole."""
    assert B.described("Brand Name | Money Club Chipper\nManufacturer | Money Club") == ["Money Club"]
    assert B.described("브랜드 | 머니 클럽") == ["머니 클럽"]
    assert B.described("Brand | MAZEL 치퍼") == ["MAZEL"]
    assert B.described("Brand | CHIPPER Lab") == ["CHIPPER Lab"]


def test_a_sellers_shop_glued_to_the_chipper_gives_way():
    """2026-11-18, the chipper review: MAZEL C9 went out as the sellers' shops 스완굿즈 / 옐로스완 / 옐로래빗
    (13861214656, 12896056499, 13393153836): the title glues the maker to 치퍼 ("SW 마젤치퍼 골프치퍼")."""
    known = ["마젤", "MAZEL", "스완굿즈"]
    assert B.store_named("스완굿즈", "SW 마젤치퍼 골프치퍼", {"스완굿즈", "블랙스완"}, known)
    assert B.store_named("옐로스완", "YS 마젤치퍼 골프치퍼 골프용품 남성골프채", {"옐로스완"}, known)
    assert not B.store_named("옐로스완", "YS 골프치퍼 골프용품", {"옐로스완"}, known)        # no other brand
    assert not B.store_named("옐로스완", "YS 치마젤 치퍼", {"옐로스완"}, known)              # not a word start


@pytest.mark.parametrize("name", ["수수협력사 co.", "수수랜드협력사.co.", "수수 협력사 Co", "수수협력사"])
def test_a_partner_phrase_with_co(name):
    """2026-11-18, the chipper review: the shop 수수 writes "수수협력사 co." in 브랜드, 제조사 and 원산지's brackets
    (13800679830 went out as the vendor "Susu Partner Co."; 13841633023 "수수랜드협력사.co.")."""
    store = {"name": "글로벌수수", "business": {"legal_name": "수수"}}
    assert B.clean(name) in ("수수", "수수랜드")
    assert B.resellers_own(name, name, store) is (B.clean(name) == "수수")
    assert B.clean("Golf Co.") == "Golf Co."                                          # a firm's Co. stays


def test_the_sellers_own_shop_is_no_importer():
    """2026-11-18: 원산지 "중국산(수수협력사 co.)" by the shop 수수, "중국산(프롬 조이 협력사)" by the shop 조이프롬
    (12657977112): the images' maker comes next (벤세이어스, read 9 times on 13800679830's images)."""
    rows = ["벤세이어스M5치퍼", "벤세이어스 정품", "BEN SAYERS"]
    assert B.decide("M5 골프 치퍼 라운딩 주변 어프로치 연습 골프채 그린 실버", "중국산(수수협력사 co.)", ["벤세이어스"],
                    rows, store={"글로벌수수", "수수"})[:2] == ("벤세이어스", "images_text")
    assert B.decide("주니어아이언", "중국산(프롬 조이 협력사)", [], [], store={"조이프롬"})[:2] == (B.NO_BRAND, "none")
    assert B.decide("주니어아이언", "일본산(혼마코리아)", [], [], store={"조이프롬"})[:2] == ("혼마코리아", "origin")


def test_a_pages_section_heading_is_no_latin_brand():
    # 13848307900, 2026-11-18: "DETAILED DESIGN" read 10 times once 핑크 no longer gave the junior set PING
    assert B.decide("여성용 핑크 세트 골프채 7번아이언", "기타/해외", ["핑"], ["DETAILED DESIGN"] * 10)[:2] == (
        B.NO_BRAND, "none")


def test_a_reselling_shops_partner_phrase_on_the_real_line():
    """13800679830 (the real line): 브랜드 and 제조사 "수수협력사 co." by the shop 수수 name no brand; the fallback
    reads the images (here: a few of its OCR rows)."""
    p = _prepared_fixture("13800679830")
    assert p["product"]["brand_ko"] is None
    other = {"key": "b", "notes": [], "product": {"brand_ko": "벤세이어스", "brand_source": "specs:브랜드"}}
    B.fill([p, other], lambda key: ["벤세이어스M5치퍼", "BEN SAYERS"], {p["key"]: "중국산(수수협력사 co.)"}, _texts,
           stores={p["key"]: {"글로벌수수", "수수"}})
    assert (p["product"]["brand_ko"], p["product"]["brand_source"]) == ("벤세이어스", "images_text")


# 2026-11-19, the knit cardigan pilot: the shop's own brand, from its own texts (OCR rows as read)
GREHIP = {"name": "그레힙", "slug": "grehip", "business": {"legal_name": "주식회사 단아한뷰"}}
TEE_AND = {"name": "티앤드 골프", "slug": "tee_and", "business": {"legal_name": "티앤드"}}


def test_a_shop_whose_slug_its_images_repeat_sells_its_own_brand():
    rows = ["grehip / 본판매처는그레힘에서직접운영하는공식정품판매처입니다.", "grehip", "GREHIP OFFICIAL SHOP",
            "grehip / grehip / grehip / grehip"]
    assert B.own_brand_shown(GREHIP, rows) == "그레힙"


def test_a_shop_that_calls_itself_a_brand():
    rows = ["골프웨어 브랜드 티앤드입니다.", "EVER YDAY", "EVER YDAY", "EVER YDAY", "EVER YDAY", "EVER YDAY"]
    assert B.own_brand_shown(TEE_AND, rows) == "티앤드 골프"
    # before the slogan the images repeat (images_text_latin): 11519647149 went out as the vendor "EVER YDAY"
    assert B.decide("여성골프니트집업 가디건 간절기 점퍼", None, [], rows, [], None, None, set(), TEE_AND)[:2] == (
        "티앤드 골프", "shop_wordmark")


def test_a_shop_that_does_not_show_its_name_is_no_brand():
    assert B.own_brand_shown(GREHIP, ["여성 니트 가디건", "grehip"]) is None            # once is not a wordmark
    assert B.own_brand_shown({"name": "골프아울렛", "slug": "golf_outlet"}, ["golf outlet"] * 5) is None  # filler slug
    assert B.own_brand_shown(None, ["브랜드 그레힙"]) is None


def test_a_stronger_step_wins_over_the_shops_wordmark():
    """Placed first, the step took 8 clubs' brands (TaylorMade read in the images, a Kirkland description row): it
    comes after them."""
    rows = ["TaylorMade", "TaylorMade", "bluenotion", "bluenotion", "bluenotion"]
    shop = {"name": "블노션", "slug": "bluenotion"}
    assert B.decide("드라이버 헤드커버", None, ["TaylorMade"], rows, [], None, None, set(), shop)[:2] == (
        "TaylorMade", "images_text")


def test_a_resellers_address_and_notice_are_no_wordmark():
    """The 2026-11-19 review: 56 club resellers' banners repeat their slugs in URLs, mails and Kakao ids."""
    shop = {"name": "렉스골프", "slug": "rexgolf"}
    assert B.own_brand_shown(shop, ["www.rexgolf.co.kr", "rexgolf@naver.com", "카톡 rexgolf16", "rexgolf.com"]) is None
    tokyo = {"name": "도쿄피아", "slug": "tokyopia"}
    assert B.own_brand_shown(tokyo, ["도쿄피아는 미즈노 공식 판매처입니다", "도쿄피아 100% 정품만 취급"]) is None
    assert B.own_brand_shown(GREHIP, ["그레힙 공식 스토어"]) == "그레힙"


# 2026-11-20, the knit cardigan review: an address in 원산지's brackets is no importer
@pytest.mark.parametrize("origin", ["국산(서울특별시 동대문구)", "국산(인천광역시 서구)",      # 8212382236, 5932679597
                                    "국산(서울특별시 강남구)", "국산(대전광역시 서구)", "국산(부산광역시 사상구)",
                                    "국산(경기도 안양시)", "중국(홍콩)", "중국산(인도네시아 등)"])
def test_an_address_or_a_country_in_the_origin_is_no_distributor(origin):
    assert B.distributors(origin) == []


def test_a_firm_in_the_origin_stays_beside_the_address_rule():
    assert B.distributors("중국산(DGB)") == ["DGB"]                                  # 10972881555
    assert B.distributors("중국산(지아이엘)") == ["지아이엘"]                          # 7518807949
    assert B.distributors("일본산(THE SIXTY NINERS JAPAN)") == ["THE SIXTY NINERS JAPAN"]   # 3807654657
    assert B.distributors("중국산(비트리)") == ["비트리"]                             # one word ending in 리: a firm
    assert B.distributors("일본산(이토보리)") == ["이토보리"]


def test_the_camel_breeze_cardigan_with_an_address_origin_is_the_shops_label():
    """8212382236 went out as the vendor "Dongdaemun-gu, Seoul": its 브랜드 row "카멜브리즈 협력업체" was dropped; never the
    address. 2026-11-21 (the owner: fix the brands): in apparel the title starting with the shop's name is its label."""
    assert B.decide("카멜브리즈 GQ 여성 배색 골프 가디건", "국산(서울특별시 동대문구)", [], [], [], None, None,
                    {"카멜브리즈", "올라운드"}, {"name": "카멜브리즈", "slug": "camelbreeze"})[:2] == ("카멜브리즈",
                                                                                        "shop_label")


CAMEL = {"name": "카멜브리즈", "slug": "camelbreeze", "business": {"legal_name": "올라운드"}}
NATURAL = {"name": "내추럴모드", "slug": "naturalmode", "business": {"legal_name": "내추럴드레스"}}


def test_a_slogan_is_no_brand_when_the_shops_own_label_row_was_dropped():
    """11573884405 (브랜드 카멜브리즈, 제조사 "카멜브리즈 협력업체") went out as "EVER YDAY", 11442719270 (내추럴모드,
    "내추럴모드협력사") as "WHITE TEE": the OCR rows as read. Their own label row was dropped (resellers_own)."""
    camel = ["EVERYDAY", "EVER YDAY", "EVER YDAY", "EVER YOAY", "EVER YOAY", "EVER YDAY", "EVER YDAY", "EVER YDAY"]
    assert B.resellers_own("카멜브리즈", "카멜브리즈 협력업체", CAMEL)
    # 2026-11-21 (the second windbreaker pilot, the owner: fix the brands): the dropped row is the shop's own label in
    # apparel (a contract factory sews it), never the slogan
    assert B.decide("[카멜브리즈]썸씽 골프집업 여성골프 니트집업 가디건", "국산", [], camel, [], None, None,
                    {"카멜브리즈", "올라운드"}, CAMEL, own_row=True)[:2] == ("카멜브리즈", "shop_label")
    natural = ["White Tee"] * 6 + ["EVER YOAY", "EVER YDAY", "EVER YOAY", "EVERYDAY", "EVER YOAY"]
    assert B.resellers_own("내추럴모드", "내추럴모드협력사", NATURAL)
    assert B.decide("여성골프가디건 여자골프니트 빅사이즈골프웨어 집업", "중국산(중국산)", [], natural, [], None, None,
                    {"내추럴모드", "내추럴드레스"}, NATURAL, own_row=True)[:2] == ("내추럴모드", "shop_label")
    # without the dropped row the Latin step is as before (BEN SAYERS on 13425122164)
    assert B.decide("여성골프가디건", None, [], natural, [], None, None, set(), NATURAL)[:2] == (
        "WHITE TEE", "images_text_latin")


def test_fill_passes_the_dropped_own_row_to_decide():
    rows = ["EVER YDAY"] * 6
    prepared = [{"key": k, "product": {"brand_ko": None, "brand_source": None, "title_ko": "여성 니트 가디건"},
                 "notes": [], "texts": []} for k in ("a", "b")]
    B.fill(prepared, lambda key: rows, {}, lambda product: [], own_rows={"a"})
    assert [(p["product"]["brand_ko"], p["product"]["brand_source"]) for p in prepared] == [
        (B.NO_BRAND, "none"), ("EVER YDAY", "images_text_latin")]


@pytest.mark.parametrize("name, want", [
    ("자체제작 상품", None), ("자체 제작", None), ("자체제작", None),                     # 7309508576 (2026-11-21)
    ("필드가OEM", "필드가"), ("주식회사 더살림oem", None), ("(주)대한ODM", None),          # 10780424641, 10669638240
    ("벤시아 협력업체(PG골프클럽)", "벤시아"),                                               # 11174080985
    ("PXG", "PXG"), ("루이까스텔", "루이까스텔"),
    ("901MOEM", "901MOEM"), ("POEM", "POEM"), ("진월드스타 OEM", "진월드스타"),             # OEM never inside a name
    ("현대백화점", None), ("하프클럽mall", None),                                             # a store is no label
])
def test_in_house_oem_and_a_partners_factory_are_no_brand(name, want):
    """2026-11-21, the second windbreaker pilot: vendors "In-House Product", "Fieldga OEM", "The Sallim OEM" and
    "Bensia Partner (PG Golf Club)" reached the drafts."""
    assert B.clean(name) == want


def test_the_title_starting_with_the_shops_name_is_its_label_only_in_apparel():
    """락골프 8643564529 and 수아무아 10669638240 (2026-11-21): no brand row, the title starts with the shop's name: the
    shop's label where `shop` is given (a category with own_brand_wordmark); a club shop (no `shop`) stays none."""
    rak = {"name": "락골프", "slug": "rakgolf"}
    assert B.decide("락골프 여성 프릴 후드 점퍼 바람막이", "국산", [], [], [], None, None, {"락골프"}, rak)[:2] == (
        "락골프", "shop_label")
    assert B.decide("[락골프] 여성 프릴 후드 점퍼", "국산", [], [], [], None, None, {"락골프"}, rak)[:2] == (
        "락골프", "shop_label")
    assert B.decide("락골프 여성 프릴 후드 점퍼 바람막이", "국산", [], [], [], None, None, {"락골프"}, None)[:2] == (
        B.NO_BRAND, "none")
    assert B.decide("여성 프릴 후드 점퍼 락골프", "국산", [], [], [], None, None, {"락골프"}, rak)[:2] == (B.NO_BRAND, "none")
