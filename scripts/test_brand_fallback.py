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
    ("(주)감씨", "감씨"), ("진월드스타 어린이용 주니어 골프 클럽 아이언 퍼터 드라이버", "진월드스타"),
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


def test_a_generic_word_is_never_a_shop_brand():
    # 2026-11-13: "주니어" in three brand rows became a shop brand, then the brand of 74 junior titles
    prepared = [{"product": {"brand_ko": B.clean("주니어"), "brand_source": "specs:브랜드"}},
                {"product": {"brand_ko": "인파로", "brand_source": "specs:브랜드"}}]
    assert B.shop_brands(prepared) == ["인파로"]
    assert B.decide("초등학생골프채 주니어 드라이버 퍼터", None, ["인파로"], [])[1] == "none"


def test_the_origin_names_no_partner_or_mall():
    assert B.distributors("중국(협력사)") == []
    assert B.distributors("중국(해외몰)") == []
    assert B.distributors("중국(새롭다 협력사)") == ["새롭다"]


def test_a_spec_tables_headings_are_no_latin_brand():
    rows = ["DEGREE LOFT"] * 6 + ["BEN SAYERS"] * 5                    # 13024208178
    assert B.decide("주니어 세트", None, [], rows)[:2] == ("BEN SAYERS", "images_text_latin")
    assert B.decide("주니어 세트", None, [], ["DEGREE LOFT"] * 6)[1] == "none"
