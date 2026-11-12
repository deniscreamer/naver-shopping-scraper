"""Offline tests for brand_fallback.py: a brand for every prepared product. Cases are the 6 sets of the 100-run
check (2026-11-08) with no brand stated.

    .venv/bin/python -m pytest scripts/test_brand_fallback.py -q
"""
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
