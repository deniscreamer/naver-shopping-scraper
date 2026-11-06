"""Offline tests for the product page parsers (naver_shopping/pdp.py) and
the product facts (parsers.product_facts).

    python -m pytest server/naver_shopping/test_pdp.py -q

Fixtures (captured 2026-11-01 in the owner's Chrome, trimmed to the 상품정보
block, tracking attributes removed): pdp_specs_ping_folded.html (9 rows and
the closed "상품정보 펼쳐보기" button), pdp_specs_ping_expanded.html (15 rows,
after the click), pdp_specs_honma.html (3 rows, no button); and
box_notice_ping.json, the store-backend notice of the same PING set.
page_product_*.json (2026-11-02): the product page's own product answer as the adapter copied it, trimmed to
the option fields, lists to 5 rows (idmakers ball marker on brand.naver.com; Honma D1, Majesty Royal, Callaway REVA, PRGR Sweep and
the PING G440K golf sets, an XXIO13 iron set with a SIMPLE choice, on smartstore). pdp_text_fields.html
(2026-11-02): the text fields of the PRGR Sweep and XXIO14 set pages, trimmed, tracking attributes removed.
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
NO_FIELD = dict.fromkeys(("label", "required", "placeholder", "hint", "min_length", "max_length", "pattern"))
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


def test_page_options_brand():
    """2026-11-02, brand.naver.com/idmakers/products/11696178500 (ball marker): the page's own product answer.
    Three COMBINATION groups plus a CUSTOM text the buyer types; paid rows (+1000, +2000) and a sold-out row."""
    o = P.parse_page_options(fixture("page_product_idmakers.json"))
    assert o["has_options"] is True and o["status"] == "SALE" and o["is_sold_out"] is False
    assert [g["type"] for g in o["option_groups"]] == ["CUSTOM", "COMBINATION", "COMBINATION", "COMBINATION"]
    assert o["text_options"] == [{"id": "11800253335", "name": "필수작성(미각인or각인:내용)후 옵션선택", **NO_FIELD}]
    assert o["simple_options"] == []
    v = {x["id"]: x for x in o["variants"]}
    assert len(v) == 5 and v["56035243441"]["name"] == "선물세트(1p) / 실버블루 / 각인없음"
    assert v["56035243441"]["extra_price"] == 0 and v["56035243441"]["is_available"] is True
    assert sorted(x["extra_price"] for x in o["variants"]) == [0, 0, 1000, 1000, 2000]
    sold = [x for x in o["variants"] if x["stock_quantity"] == 0]
    assert len(sold) == 1 and sold[0]["is_available"] is False
    assert o["supplements"][0] == {"id": "3678604239", "group": "선물포장", "name": "쇼핑백", "price": 1500,
                                   "stock_quantity": 5000, "status": "SALE"}


def test_page_options_golf_sets():
    """2026-11-02, golf full sets from the 남성 골프채 풀세트 search, the page's own answers (trimmed)."""
    honma = P.parse_page_options(fixture("page_product_honma.json"))      # thegolf/5543745139
    s_set, r_set = honma["variants"]
    assert s_set["name"] == "S 세트 (D1 500 S+950 S)" and s_set["extra_price"] == 0 and s_set["is_available"]
    assert r_set["extra_price"] == 60000 and r_set["stock_quantity"] == 0 and r_set["is_available"] is False
    majesty = P.parse_page_options(fixture("page_product_majesty.json"))  # samsung-golf/12434254421
    assert [g["type"] for g in majesty["option_groups"]] == ["CUSTOM", "COMBINATION", "COMBINATION", "COMBINATION"]
    assert majesty["text_options"] == [{"id": "11832983056", "name": "네임택용 성함", **NO_FIELD}]
    assert majesty["variants"][0]["is_available"] is False and all(v["is_available"] for v in majesty["variants"][1:])
    assert len(majesty["variants"][0]["options"]) == 3 and majesty["supplements"][0]["price"] == 0
    ping = P.parse_page_options(fixture("page_product_ping.json"))        # scarabee/13021362937: no options
    assert ping["has_options"] is False and ping["variants"] == [] and ping["option_groups"] == []
    assert ping["stock_quantity"] == 17 and len(ping["supplements"]) == 1
    reva = P.parse_page_options(fixture("page_product_reva.json"))        # thegolf/13413924099: cheaper without bag
    assert [(v["extra_price"], v["is_available"]) for v in reva["variants"]] == [
        (0, True), (-100000, False), (0, True), (-100000, False)]
    assert reva["variants"][1]["name"] == "피치/서프 클럽 10PCS (캐디백 미포함)"
    prgr = P.parse_page_options(fixture("page_product_prgr.json"))        # adpargolf/13751285162: a text only
    assert prgr["has_options"] is True and prgr["variants"] == []
    assert prgr["option_groups"] == [{"id": "11888379649", "name": "네임스티커 성함", "type": "CUSTOM"}]
    assert prgr["text_options"] == [{"id": "11888379649", "name": "네임스티커 성함", **NO_FIELD}]
    xxio = P.parse_page_options(fixture("page_product_xxio_simple.json"))  # gatagolf/13553833826: a SIMPLE choice
    assert xxio["variants"] == [] and xxio["option_groups"][0]["type"] == "SIMPLE"
    assert xxio["simple_options"] == [{"id": "11721898461", "group": "강도", "name": "L", "extra_price": 0}]


def test_page_options_empty():
    o = P.parse_page_options(None)
    assert o["variants"] == [] and o["option_groups"] == [] and o["has_options"] is None
    assert P.parse_page_options({"simpleOptions": [{"groupName": "g", "options": None}, "x"]})["simple_options"] == []
    rows = P.parse_page_options({"standardCombinations": [{"id": 1, "optionName1": "M", "stockQuantity": None}]})
    assert rows["variants"][0]["name"] == "M" and rows["variants"][0]["is_available"] is None


def test_text_fields():
    """2026-11-02, the PRGR Sweep (adpargolf/13751285162) and XXIO14 (koogolfsotre/12931417088) set pages: a text
    field per CUSTOM option, its label marked (필수), 20 characters at most; the purchase box is rendered twice."""
    fields = pdp.text_fields(fixture("pdp_text_fields.html"))
    assert [f["id"] for f in fields] == ["11888379649", "11205247591"]            # one per id, the search box left out
    assert fields[0] == {"id": "11888379649", "label": "네임스티커 성함 (필수)", "required": True,
                         "placeholder": "입력해주세요", "hint": None, "min_length": None, "max_length": 20,
                         "pattern": None}
    assert fields[1]["label"] == "네임스티커 성함과 장갑사이즈(18호~21호) (필수)"
    assert pdp.text_fields("") == [] and pdp.text_fields(fixture("pdp_specs_honma.html")) == []


def test_text_fields_other_attributes():
    """Synthetic markup: the attributes the naver-harvester also reads (required, aria-required, minlength,
    pattern, an aria-describedby hint), not seen on a page yet; a field without (필수) is optional."""
    html = ('<label for="1">각인 문구</label><input data-tag="textOption" id="1" minlength="2" maxlength="x" '
            'pattern="[A-Z]+" aria-describedby="h1 h9"><p id="h1">영문 대문자만</p>'
            '<label for="2">메모</label><input data-tag="textOption" id="2" aria-required="true">'
            '<input data-tag="textOption" id="3" required><label for="4">이름</label><input data-tag="textOption" id="4">'
            '<input data-tag="textOption">')
    one, two, three, four = pdp.text_fields(html)
    assert one["required"] is False and one["min_length"] == 2 and one["max_length"] is None
    assert one["pattern"] == "[A-Z]+" and one["hint"] == "영문 대문자만" and one["placeholder"] is None
    assert two["required"] is True and three["required"] is True and three["label"] is None
    assert four["required"] is False


def test_page_options_with_the_page_fields():
    """The answer's textOptions joined with the page's fields by id (PRGR Sweep, 2026-11-02)."""
    fields = pdp.text_fields(fixture("pdp_text_fields.html"))
    prgr = P.parse_page_options(fixture("page_product_prgr.json"), fields)
    assert prgr["text_options"] == [{"id": "11888379649", "name": "네임스티커 성함", "label": "네임스티커 성함 (필수)",
                                     "required": True, "placeholder": "입력해주세요", "hint": None,
                                     "min_length": None, "max_length": 20, "pattern": None}]
    majesty = P.parse_page_options(fixture("page_product_majesty.json"), fields)   # its field is not in the HTML
    assert majesty["text_options"][0]["required"] is None


def test_delivery_promise():
    with open(os.path.join(FX, "pdp_delivery_promise.html"), encoding="utf-8") as f:   # honma 5543745139, 2026-11-05
        promise = pdp.delivery_promise(f.read())
    assert promise == {"today_cutoff": "16:00", "arrival_days": 2, "arrival_date_text": None, "arrival_probability": 96,
                       "ship_date_text": "11.6.(금)", "overseas_text": False}
    assert pdp.delivery_promise("<div><span>해외직배송</span></div>")["overseas_text"] is True
    with open(os.path.join(FX, "pdp_delivery_promise_today.html"), encoding="utf-8") as f:   # the same set, 2026-11-06
        promise = pdp.delivery_promise(f.read())
    assert promise == {"today_cutoff": "16:00", "arrival_days": None, "arrival_date_text": "11.11.(수)",
                       "arrival_probability": 98, "ship_date_text": None, "overseas_text": False}


# ---- description junk (research 2026-11-06, 40 golf sets + 86 saved products) ----------------------------------

def test_description_skips_card_components():
    """Naver's own detailContentText leaves out exactly se-oglink, se-placesMap and se-material: a link card to
    another product or TalkTalk, the store's map card, a shopping card. Quotes from 6630856593, 13049116377,
    12434254421."""
    oglink = ('<div class="se-component se-oglink"><a class="se-oglink-info" href="https://smartstore.naver.com/'
              'viviga_world/products/6611413859"><strong class="se-oglink-title">PGM 남성용 드라이버 : 비비가월드</strong>'
              '<p class="se-oglink-url">smartstore.naver.com</p></a></div><div class="se-component se-text"><p>460cc 헤드</p></div>')
    assert pdp.description_text(oglink) == "460cc 헤드"
    places = ('<div class="se-component se-placesMap"><img src="https://simg.pstatic.net/static.map/v2/map/staticmap.bin?x=1" '
              'class="se-map-image"><a class="se-map-info"><strong class="se-map-title">굿바이골프</strong>'
              '<p class="se-map-address">경기도 군포시 삼성로87번길 4-24 1층</p></a></div>'
              '<div class="se-component se-text"><p>캘러웨이 XR26</p></div>')
    assert pdp.description_text(places) == "캘러웨이 XR26"
    talk = ('<div class="se-component se-oglink"><a href="https://talk.naver.com/ct/wc1l7o"><strong class="se-oglink-title">'
            '삼성골프 - 네이버톡톡</strong><p class="se-oglink-summary">부산 학장동에 위치한 골프용품 전문 할인매장</p></a></div>'
            '<div class="se-component se-text"><p>마제스티 골프 100% 정품</p></div>')
    assert pdp.description_text(talk) == "마제스티 골프 100% 정품"
    assert pdp.description_text('<p>스틸 <span class="se-blind">네이버페이</span>세트</p>') == "스틸 세트"


def test_description_keeps_text_quotation_table_and_links():
    body = ('<div class="se-component se-quotation"><blockquote><p>PGM은 중국 Tmall 골프 부문</p></blockquote></div>'
            '<div class="se-component se-table"><table><tr><td>로프트</td><td>10.5</td></tr></table></div>'
            '<div class="se-component se-text"><p><a class="se-link" href="https://www.callawaygolf.com">캘러웨이</a> 정품</p></div>')
    assert pdp.description_text(body) == "PGM은 중국 Tmall 골프 부문\n\n로프트\n10.5\n\n캘러웨이 정품"


def test_description_cards_fixture():
    """Real components cut from 12274419597 (se-material), 13049116377 (se-placesMap) and 6630856593 (se-oglink)."""
    text = pdp.description_text(fixture("contents_seone_cards.html"))
    for junk in ("굿바이골프", "경기도 군포시", "따봉몰", "네이버페이", "smartstore.naver.com", "1호 우드 초보자용"):
        assert junk not in text, junk
    assert text.startswith("캘러웨이 XR26\n남성 골프채 12개 풀세트 구성") and text.endswith("온라인 최저가로 만나보세요:)")
    assert "골프백: 스탠드백\n\nPGM 남성용 좌타 1번 우드 연습용\n골프 드라이브\n\nPGM은 중국 Tmall 골프 부문" in text


def test_description_skips_jump_anchors():
    """12696567111 (editor NONE): "▲ 이동(상단)" is an <a href="#top"> link, in-page navigation."""
    html = ('<div id="product1"><div>캘러웨이 XR 26 풀세트 남성용</div><p><a href="#top"><b><font color="red" size="4">'
            '▲ 이동(상단)</font></b></a></p></div>')
    assert pdp.description_text(html) == "캘러웨이 XR 26 풀세트 남성용"
    assert pdp.description_text('<p><a href="#" class="se-module-image-link">사진 설명</a></p>') == "사진 설명"
    assert pdp.description_text('<p><a href="https://brand.naver.com/x">링크</a> 글</p>') == "링크 글"


def test_description_drops_bare_hashtag_lines():
    """10639350746: a hashtag line with no "관련 태그" label in front. Club numbers (#PW, #5-#9, #7) stay."""
    html = "<p>#골린이#남성좌타골프채#풀세트#스탠드백#헤드커버</p><p>Callaway Golf Men’s Strata Complete Set</p>"
    assert pdp.description_text(html) == "Callaway Golf Men’s Strata Complete Set"
    html = "<p>#PW</p><p>10개 세트(1W, 5W, #5-#9, PW, SW, PT) + 캐디백</p><p>#4H</p>"
    assert pdp.description_text(html) == "#PW\n10개 세트(1W, 5W, #5-#9, PW, SW, PT) + 캐디백\n#4H"
    for kept in ("#PW #PT", "#52 #4H", "오디세이 EYE TRAX #7 (34인치)", "#6 아이언: 로프트각 28.0°", "#골프"):
        assert pdp.description_text(f"<p>{kept}</p>") == kept, kept


def test_description_blank_line_between_components():
    """One empty line between top-level SmartEditor components (6774818843): the transform ends a notice block at
    its component. Empty spacer components collapse; a body without components is unchanged."""
    html = ('<div class="se-component se-quotation"><p>◆ 해당 상품 관부가세 및 배송 공지◆</p><p>감사합니다.</p></div>'
            '<div class="se-component se-text"><p>​</p></div><div class="se-component se-image"><img data-src="x"></div>'
            '<div class="se-component se-text"><p>호평의 캘러웨이 클럽 세트</p></div><div class="se-component se-text"><p></p></div>')
    assert pdp.description_text(html) == "◆ 해당 상품 관부가세 및 배송 공지◆\n감사합니다.\n\n호평의 캘러웨이 클럽 세트"
    assert pdp.description_text("<p>첫 줄입니다</p><p>둘째</p>") == "첫 줄입니다\n둘째"
    nested = ('<div class="se-component se-table"><table><tr><td><div class="se-component se-text"><p>a</p></div>'
              '</td><td><p>b</p></td></tr></table></div><div class="se-component se-text"><p>c</p></div>')
    assert pdp.description_text(nested) == "a\nb\n\nc"
