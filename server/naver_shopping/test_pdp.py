"""Offline tests for the product page parsers (naver_shopping/pdp.py) and
the product facts (parsers.product_facts).

    python -m pytest server/naver_shopping/test_pdp.py -q

Fixtures (captured 2026-11-01 in the owner's Chrome, trimmed to the 상품정보
block, tracking attributes removed): pdp_specs_ping_folded.html (9 rows and
the closed "상품정보 펼쳐보기" button), pdp_specs_ping_expanded.html (15 rows,
after the click), pdp_specs_honma.html (3 rows, no button); and
box_notice_ping.json, the store-backend notice of the same PING set.
"""
import json
import os

from naver_shopping import parsers as P, pdp

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


PING = {"name": "26년 핑 G440K 브리지스톤 V300 조합 남성 골프채풀세트 클럽11개", "brand": "핑",
        "manufacturer": "삼양인터내셔날", "model_name": None}
HONMA = {"name": "신품 혼마 D1 남성용 골프채 풀세트 S세트 2021 D1 500 S+950 S(병행)", "brand": None,
         "manufacturer": None, "model_name": None}


def test_spec_rows_expanded():
    rows = pdp.spec_rows(fixture("pdp_specs_ping_expanded.html"))
    assert len(rows) == 15
    assert rows[0] == {"label": "상품번호", "value": "13021362937"}      # the copy button's "복사" left out
    as_dict = {r["label"]: r["value"] for r in rows}
    assert as_dict["브랜드"] == "핑" and as_dict["원산지"] == "미국산(삼양인터내셔날)"
    assert as_dict["총클럽개수"] == "11개" and as_dict["골프백포함여부"] == "미포함"
    assert not pdp.specs_collapsed(fixture("pdp_specs_ping_expanded.html"))


def test_spec_rows_folded():
    """2026-11-01: the list shows 9 rows until "상품정보 펼쳐보기" is clicked."""
    html = fixture("pdp_specs_ping_folded.html")
    assert len(pdp.spec_rows(html)) == 9 and pdp.specs_collapsed(html)


def test_spec_rows_short_list_and_junk():
    rows = pdp.spec_rows(fixture("pdp_specs_honma.html"))
    assert [r["label"] for r in rows] == ["상품번호", "제조사", "원산지"]
    assert not pdp.specs_collapsed(fixture("pdp_specs_honma.html"))
    assert pdp.spec_rows("") == [] and pdp.spec_rows("<div><strong>상품정보</strong></div>") == []
    assert pdp.spec_rows("<ul><li><div>a") == []


def test_description_text():
    html = ('<div class="se-main-container"><p>첫 <b>줄</b>입니다</p><p>​</p>'
            '<div class="se-material">추천 상품</div><img alt="그림"><p>공지사항</p>'
            '<p>관련 태그</p><p>#골프 #풀세트</p><p>둘째<br>셋째</p><button>더보기</button></div>')
    assert pdp.description_text(html) == "첫 줄입니다\n둘째\n셋째"
    assert pdp.description_text(fixture("box_contents.json")["renderContent"]) is None   # images only
    assert pdp.description_text(None) is None and pdp.description_text("<p></p>") is None


def test_notice_placeholders():
    """2026-11-01, PING set: 8 of 13 basic notice rows read "상품상세참조"."""
    n = P.parse_notice(fixture("box_notice_ping.json"))
    flagged = [r["label"] for r in n["items"] if r["is_see_description"]]
    assert len(flagged) == 8 and "크기" in flagged and "제조국" not in flagged
    assert not any(r["is_see_description"] for r in n["terms"])
    assert P.is_see_description("상세페이지 참조") and P.is_see_description("상품 상세 참고")
    # Callaway XR26 set, same day
    assert P.is_see_description("[상세설명참조]") and P.is_see_description("크기 항목 참조")
    assert P.is_see_description("[상세설명참조] / 품명 항목 참조") and not P.is_see_description("베트남산(캘러웨이)")
    for pointer in ("상세페이지에 별도 표기", "상품상세페이지에 표기", "상품상세설명에 표시", "제품상세참조", "상세설명란 참조"):
        assert P.is_see_description(pointer), pointer
    assert not P.is_see_description("상세정보 참조, 중국") and not P.is_see_description("")
    assert not P.is_see_description("미국산") and not P.is_see_description(None)


def test_facts_from_specs():
    rows = pdp.spec_rows(fixture("pdp_specs_ping_expanded.html"))
    f = P.product_facts(PING, P.parse_notice(fixture("box_notice_ping.json")), rows)
    assert f["brand"] == {"value": "핑", "source": "specs:브랜드"}
    assert f["manufacturer"] == {"value": "삼양인터내셔날", "source": "specs:제조사"}
    assert f["origin"] == {"value": "미국산(삼양인터내셔날)", "source": "specs:원산지"}
    assert f["model_name"] is None


def test_facts_without_page():
    f = P.product_facts(PING, P.parse_notice(fixture("box_notice_ping.json")))
    assert f["brand"] == {"value": "핑", "source": "search_info.brandName"}
    assert f["manufacturer"] == {"value": "삼양인터내셔날", "source": "search_info.manufacturerName"}
    assert f["origin"] == {"value": "미국산(삼양인터내셔날)", "source": "notice:제조국"}
    assert P.product_facts(None) == {"brand": None, "manufacturer": None, "model_name": None, "origin": None}


def test_brand_from_manufacturer_only_when_named():
    """2026-11-01, Honma D1 set: no 브랜드 row, no brandName; 제조사 혼마 is in the name."""
    rows = pdp.spec_rows(fixture("pdp_specs_honma.html"))
    f = P.product_facts(HONMA, None, rows)
    assert f["brand"] == {"value": "혼마", "source": "specs:제조사"} and f["origin"]["value"] == "중국"
    other = dict(HONMA, name="남성 골프채 풀세트")
    assert P.product_facts(other, None, rows)["brand"] is None
    dash = P.product_facts(dict(HONMA, name="PING G440 - 풀세트", manufacturer="-"),
                           {"items": [{"label": "제조국", "value": "해당없음"}]})
    assert dash == {"brand": None, "manufacturer": None, "model_name": None, "origin": None}
    no_page = P.product_facts(dict(HONMA, manufacturer="혼마"))       # details only: manufacturerName
    assert no_page["brand"] == {"value": "혼마", "source": "search_info.manufacturerName"}
