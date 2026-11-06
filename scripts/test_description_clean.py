"""Offline tests for description_clean.py: the seller's boilerplate in a description's text and images.

Every input is a real quote from the 40 collected golf sets (category 50002788, research 2026-11-06), the product id
beside it; every rule has its real false-positive guards (lines that look like boilerplate and are the product).

    .venv/bin/python -m pytest scripts/test_description_clean.py -q
"""
import base64

import pytest

from description_clean import body_notes, clean, clean_images, qwerty_hangul, sentences


def text(t, **kw):
    return clean(t, **kw)["text"]


def rules(t, **kw):
    return [d["rule"] for d in clean(t, **kw)["dropped"]]


# ---- sentences over SmartEditor visual lines ---------------------------------------------------------------------

def test_sentences_join_connective_lines():
    """A <p> is a visual line: "...유선 전화로" / "안내해 드리겠습니다:)" is one sentence (11256507948)."""
    lines = ["* 추가적으로 궁금하신 내용은 네이버 톡톡 또는 유선 전화로", "안내해 드리겠습니다:)",
             "야마모토 쇼군 풀세트는 극가성비 풀세트입니다."]
    assert list(sentences(lines)) == [lines[:2], lines[2:]]
    # a phone line ends on digits: the next line is not part of it (10302181901)
    assert list(sentences(["제품 상담 문의 010 4667 2057", "(실 제 제 품 사 진)"])) == [
        ["제품 상담 문의 010 4667 2057"], ["(실 제 제 품 사 진)"]]


def test_contact_sentence_dropped_across_the_wrap():
    t = ("* 추가적으로 궁금하신 내용은 네이버 톡톡 또는 유선 전화로\n안내해 드리겠습니다:)\n"
         "야마모토 쇼군 풀세트는 극가성비 풀세트입니다.")
    out = clean(t)
    assert out["text"] == "야마모토 쇼군 풀세트는 극가성비 풀세트입니다."
    assert out["dropped"] == [{"rule": "contact",
                               "text": "* 추가적으로 궁금하신 내용은 네이버 톡톡 또는 유선 전화로\n안내해 드리겠습니다:)"}]


# ---- policy blocks -----------------------------------------------------------------------------------------------

def test_policy_block_to_component_end():
    t = "●반품 및 교환 관련 안내\n당사 특성상 네이버페이 자동수거 요청이 불가합니다.\n●반품 시 주의사항\n-제이디스포츠-\n\n스탠드 백 포함"
    assert text(t) == "스탠드 백 포함"                                        # 11256507948
    t = "◆ 해당 상품 관부가세 및 배송 공지◆\n배송은 9~14일가량 소요됩니다.\n감사합니다.\n듀벨로 올림\n\n호평의 캘러웨이 클럽 세트"
    out = clean(t)                                                              # 6774818843
    assert out["text"] == "호평의 캘러웨이 클럽 세트" and [d["rule"] for d in out["dropped"]] == ["policy"]
    assert out["dropped"][0]["text"].endswith("듀벨로 올림")


@pytest.mark.parametrize("kept", [
    "[안내사항]\n스틸 세트\n- 아이언&퍼터 클럽: 스틸샤프트",                       # 12391346892, product content
    "- 세트 설명 -\n- 사이즈 설명 -\n- 샤프트 설명 -\n옵션 설명",                   # 6999516176
    "4종 골프백 블랙색상 랜덤 발송..",                                           # 10563381788
    "그립 1회 무상 교환(1회)",                                                   # 12434254421
])
def test_policy_block_must_not_match(kept):
    assert text(kept) == kept


def test_policy_block_without_component_end_stops_at_the_cap():
    """A body with no component boundaries (editor NONE) has no block end: the block stops after a few lines and
    a note asks a human to look."""
    body = ["●배송 안내", "주문 후 2~3일 이내 발송됩니다."] + [f"제품 설명 {i}" for i in range(1, 30)]
    out = clean("\n".join(body))
    assert out["text"].startswith("제품 설명 ") and "제품 설명 29" in out["text"]
    assert {"code": "description_policy_block_unbounded", "detail": "●배송 안내"} in out["notes"]


# ---- contact, phone, TalkTalk, Naver Pay -------------------------------------------------------------------------

def test_phone_and_contact():
    assert clean("제품 상담 문의 010 4667 2057")["text"] is None                # 10302181901
    assert rules("제품 상담 문의 010 4667 2057") == ["phone"]
    assert text("캐디백구조의 아이언은 관용성이 좋아 방향성 잘 잡아줍니다.\n제품 상담 문의 010 4667 2057\n"
                "(실 제 제 품 사 진)") == "캐디백구조의 아이언은 관용성이 좋아 방향성 잘 잡아줍니다.\n(실 제 제 품 사 진)"
    assert text('모든 문의는 " 네이버톡톡 " H/P : 051 324 6360 으로 문의 주세요!\n9아이언세트') == "9아이언세트"  # 10649210920
    assert text("아래 톡톡주시면 상세히 안내드립니다.~\n던롭스포츠코리아 100% 정품") == "던롭스포츠코리아 100% 정품"   # 12931402258
    assert rules("당사 특성상 네이버페이 자동수거 요청이 불가합니다.") == ["naverpay"]
    assert rules("02-123-4567 로 연락주세요") == ["phone"] and rules("1588-1234") == ["phone"]


@pytest.mark.parametrize("kept", [
    "UPC\n‎190228623812\nGlobal Trade Identification Number\n‎00190228623812",   # 10639350746
    "클럽 길이(inch)\n45.5\n38.375",
    "Package Weight\n‎7.71 Kilograms",
    "드라이버: 10.5도 SR\n8아이언세트: 5번~9번,PW,AW,SW",
])
def test_phone_must_not_match(kept):
    assert text(kept) == kept


# ---- greeting, thanks, signature ---------------------------------------------------------------------------------

def test_greeting_thanks_signature():
    assert text("안녕하세요. 제이디스포츠:)입니다.\n야마모토 쇼군 풀세트는 극가성비 풀세트입니다.") == \
        "야마모토 쇼군 풀세트는 극가성비 풀세트입니다."                            # 11256507948
    assert text("스탠드 백 포함\n-제이디스포츠-") == "스탠드 백 포함"
    assert rules("감사합니다.") == ["thanks"] and rules("항상 감사합니다^^") == ["thanks"]
    assert rules("듀벨로 올림") == ["signature"]                                 # 6774818843


@pytest.mark.parametrize("kept", [
    "- 추가선택 -\n보스턴백",                                                    # 13498941795
    "- 세트 설명 -",                                                            # two tokens
    "안녕하세요 캘러웨이 XR26 풀세트 12개 구성의 남성용 세트로 스탠드백 포함입니다",   # not a greeting-only line
])
def test_greeting_signature_must_not_match(kept):
    assert text(kept) == kept


# ---- duties, lead time, promo, store claim, monitor --------------------------------------------------------------

def test_duties_leadtime_promo_storeclaim_monitor():
    assert text("현지 공장 직구로 온라인 최저가와\n초고속 배송으로 득템해 보세요:D\nPGM은 중국 Tmall 골프 부문\n"
                "판매량 1위 브랜드입니다.") == "PGM은 중국 Tmall 골프 부문\n판매량 1위 브랜드입니다."  # 6630856593
    assert text("저희 비비가월드는 국내 온라인\n최초 PGM 정식 판매권을 받은 업체입니다.\n460cc 대용량 클럽 헤드") == \
        "460cc 대용량 클럽 헤드"
    assert text("*측정 방법과 모니터 사양에 따라 사이즈와\n컬러는 다소 차이가 있을 수 있습니다\n- 세트 설명 -") == \
        "- 세트 설명 -"
    assert text("현지배송비+관세&부가세+국내배송비 모두 포함 금액고객님께서 추가적으로 지불하시는 금액은 없습니다!!!!!\n"
                "Callaway Golf Men’s Strata Complete Set") == "Callaway Golf Men’s Strata Complete Set"   # 10639350746
    assert text("마제스티 공식 온라인 대리점\n마제스티 골프 100% 정품\n무상 A/S 3년 보장\n그립 1회 무상 교환(1회)") == \
        "마제스티 골프 100% 정품\n무상 A/S 3년 보장\n그립 1회 무상 교환(1회)"          # 12434254421
    assert text("쓸모있는 상점은 PGM의\n정식 수입업체입니다.\n정품만을 취급하고 있으니,\n안심하고 구매하세요!\n[안내사항]",
                store_name="쓸모있는 상점") == "[안내사항]"                          # 12391346892
    assert rules("배송은 9~14일가량 소요됩니다.") == ["lead_time"]


@pytest.mark.parametrize("kept", [
    "(정식통관및 품질AS보증라벨 부착)",                                           # 12231586028, 10302181901
    "국내 AS 가능한 정품입니다!!",                                               # 11164222651
    "2021 중국 티몰 골프 부문\n매출 1위 - PGM",                                  # a brand claim, not the store's
    "※드라이버, 페어웨이 우드, 퍼터, 전용 헤드 커버 부속.",
    "Package Weight ‎7.71 Kilograms",
    "무상 A/S 3년 보장",
    "5번~9번 아이언: 쉽고 편안하게 플레이할 수 있는 디자인",
    "배송은 빠르게",
])
def test_claims_must_not_match(kept):
    assert text(kept, store_name="굿바이골프") == kept


def test_store_name_rule():
    assert rules("굿바이골프에서 만나보세요", store_name="굿바이골프") == ["store_name"]
    assert rules("따봉몰 추천 상품", store_name="따봉몰.") == ["store_name"]     # 12274419597: the name ends on "."
    # a brand's own store: its name is the product's brand, so the rule is off
    assert text("캘러웨이 XR26 풀세트", store_name="캘러웨이", brand="캘러웨이") == "캘러웨이 XR26 풀세트"
    assert text("캘러웨이 XR26 풀세트", store_name="캘러웨이골프", brand="캘러웨이") == "캘러웨이 XR26 풀세트"
    assert text("XR26 풀세트 K", store_name="K") == "XR26 풀세트 K"               # one letter is not a name


# ---- gifts (only when Naver's promotion rows are hidden) ---------------------------------------------------------

def test_gift_block_when_promo_hidden():
    t = "사은품 최다 증정(소진시 대체품)\n볼빅마블모자 랜덤1,파우치 랜덤1,볼빅 비비드우드티\n\n캘러웨이 패러다임"   # 8978750961
    assert text(t, promo_hidden=True) == "캘러웨이 패러다임"
    assert rules(t, promo_hidden=True) == ["gift"]
    assert text(t) == t


@pytest.mark.parametrize("kept", [
    "☆ 캐디백 증정 ☆",                                                          # 6999516176, part of the set
    "오보로 아이언커버 증정해드립니다",                                            # 13049116377
    "26년형 오디세이 퍼터 1개 증정!",                                             # 12931402258
    "그립 1회 무상 교환(1회)",
    "랜덤 발송",
])
def test_gift_must_not_match(kept):
    assert text(kept, promo_hidden=True) == kept


# ---- jump links, blocks, shape -----------------------------------------------------------------------------------

def test_jump_lines_fallback():
    assert text("캘러웨이 XR 26 풀세트 남성용\n▲ 이동(상단)\n캘러웨이 XR 24 풀세트 남성용") == \
        "캘러웨이 XR 26 풀세트 남성용\n캘러웨이 XR 24 풀세트 남성용"                   # 12696567111
    for jump in ("▲TOP", "맨 위로", "▲ 맨위로 가기", "TOP ▲"):
        assert rules(jump) == ["jump"], jump
    assert text("TOP 브랜드") == "TOP 브랜드"


def test_blocks_kept_and_empty():
    assert text("a 세트\n\n\n\nb 세트") == "a 세트\n\nb 세트"
    assert text("감사합니다.\n\nb 세트") == "b 세트"
    out = clean("감사합니다.\n\n듀벨로 올림")
    assert out["text"] is None and {"code": "description_all_boilerplate", "detail": "2 dropped"} in out["notes"]
    assert clean(None) == {"text": None, "dropped": [], "notes": []}
    assert clean("") == {"text": None, "dropped": [], "notes": []}


# ---- images by file name -----------------------------------------------------------------------------------------

def proxy(path):
    return "https://proxy-smartstore.naver.net/img/" + base64.b64encode(path.encode()).decode() + "?token=3d21"


def test_clean_images_by_name():
    review = "https://shop-phinf.pstatic.net/20260101_1/1_PNG/%EB%A6%AC%EB%B7%B0%EC%9D%B4%EB%B2%A4%ED%8A%B8.png"
    names = ["https://gi.esmplus.com/x/foot_info.jpg", "https://gi.esmplus.com/x/as.jpg",
             "https://shop-phinf.pstatic.net/a/%EB%94%B0%EB%B4%89%EB%AA%B0_%ED%95%98%EB%8B%A8%EB%B0%B0%EB%84%88.jpg",
             "https://shop-phinf.pstatic.net/a/%ED%86%B5%EA%B4%80%EB%B2%88%ED%98%B8_%EC%95%88%EB%82%B4.jpg?type=w860",
             "https://shop-phinf.pstatic.net/a/%25ED%2595%25B4%25EC%2599%25B8%25EB%25B0%25B0%25EC%2586%25A1.jpg",
             proxy("majorgolf.cafe24.com/shose/sangse_main/image/event/event_main.jpg")]
    out = clean_images([review] + names)
    assert out["images"] == []
    assert [d["name"] for d in out["dropped"]] == ["리뷰이벤트.png", "foot_info.jpg", "as.jpg", "따봉몰_하단배너.jpg",
                                                   "통관번호_안내.jpg", "해외배송.jpg", "event_main.jpg"]
    assert all(d["rule"] == "boilerplate_name" and d["link"] for d in out["dropped"])


@pytest.mark.parametrize("kept", [
    "https://shop-phinf.pstatic.net/a/KakaoTalk_20260205_173853802_01.jpg",            # 13099257309, a phone photo
    "https://shop-phinf.pstatic.net/a/PGM-%EB%B0%B0%EB%84%88.jpg",                        # PGM-배너.jpg
    "https://shop-phinf.pstatic.net/a/PGM%EC%9D%B8%EC%A6%9D%EC%84%9C%EC%B5%9C%EC%A2%85(%E6%B7%BB%E5%8A%A0%E6%B0%B4%E5%8D%B0).jpg",
    "https://shop-phinf.pstatic.net/20260105_1/p-12639506238-s-6-A-0.jpg",                # a snap tile
    "https://shop-phinf.pstatic.net/a/canvas_bag.jpg", "https://shop-phinf.pstatic.net/a/Gas_cap.jpg",
    "https://shop-phinf.pstatic.net/a/prevent_slice.jpg",
    proxy("not base64 at all"),
    "https://proxy-smartstore.naver.net/img/%%%%not-base64?token=1",
])
def test_clean_images_must_not_match(kept):
    assert clean_images([kept]) == {"images": [kept], "dropped": []}


def test_clean_images_empty():
    assert clean_images(None) == {"images": [], "dropped": []}


# ---- notes from the description HTML -----------------------------------------------------------------------------

def test_body_notes_several_products():
    """12696567111: a 모음전 page, four models behind in-page anchors #product1..#product4."""
    html = ''.join(f'<a href="#product{i}"><img src="x"></a>' for i in range(1, 5)) + \
        ''.join(f'<div id="product{i}"><div>모델 {i}</div><a href="#top">▲ 이동(상단)</a></div>' for i in range(1, 5))
    assert {"code": "description_covers_several_products", "detail": "4 in-page sections"} in body_notes(html)
    # one section, or anchors with no target in the body, are not a 모음전
    assert body_notes('<a href="#product1">x</a><div id="product1">y</div><a href="#top">top</a>') == []
    assert body_notes('<a href="#a">x</a><a href="#b">y</a>') == []
    assert body_notes(None) == []


def test_body_notes_tiles_include_banners():
    """Snap tiles (editor NONE) are Naver's pictures of the whole body: seller banners are inside them and cannot be
    cut per image (6153061020: notice01.jpg; 12696567111: the HTML comment "하단 안내 이미지")."""
    tiles = ["https://shop-phinf.pstatic.net/20260105_1/p-6153061020-s-6-A-0.jpg"]
    html = '<img src="https://proxy-smartstore.naver.net/img/x"><img src="https://a.b/c/notice01.jpg"><p>세트</p>'
    assert body_notes(html, tiles) == [{"code": "description_tiles_include_banners", "detail": "notice01.jpg"}]
    assert body_notes("<!-- 하단 안내 이미지 --><img src='https://a.b/p.jpg'>", tiles) == [
        {"code": "description_tiles_include_banners", "detail": "하단 안내 이미지"}]
    assert body_notes(html, ["https://shop-phinf.pstatic.net/a/b.jpg"]) == []   # not tiles: clean_images does it
    assert body_notes("<img src='https://a.b/club.jpg'>", tiles) == []


def test_clean_images_store_banners_seen_on_the_rerun():
    # 2026-11-06 re-check of the 40: store notices and company banners named in the file
    names = ["https://gi.esmplus.com/jayfocus/ktksports/ktksports%20%EC%95%88%EB%82%B4%EB%AC%B811.jpg",
             "https://shop-phinf.pstatic.net/a/%ED%9A%8C%EC%82%AC%EC%9D%B4%EB%AF%B8%EC%A7%80.jpg",
             "https://gi.esmplus.com/x/%ED%83%9D%EB%B0%B0_Nope_AS.jpg", "https://ai.esmplus.com/x/brand.jpg",
             "https://ai.esmplus.com/x/customer.jpg", "https://www.akgolf.co.kr/x/bottom_img_all.jpg"]
    assert [d["name"] for d in clean_images(names)["dropped"]] == [
        "ktksports 안내문11.jpg", "회사이미지.jpg", "택배_Nope_AS.jpg", "brand.jpg", "customer.jpg", "bottom_img_all.jpg"]
    kept = ["https://ai.esmplus.com/x/brand_logo_g430.jpg", "https://ai.esmplus.com/x/customer_fit_chart.jpg"]
    assert clean_images(kept)["images"] == kept


# ---- pilot 20 (research 2026-11-06, research/PILOT20-FINDINGS.md T1 / T2) ----------------------------------------

def test_junk_only_description_is_none():
    """13741767690: the whole description text is "o" (editor NONE): no word, nothing to translate."""
    out = clean("o")
    assert out["text"] is None and out["dropped"] == [{"rule": "junk", "text": "o"}]
    assert {"code": "description_junk", "detail": "o"} in out["notes"]
    assert clean(" . \n-\n\n1")["text"] is None


@pytest.mark.parametrize("kept", [
    "골프클럽 남성용 풀세트\n좌타 스틸 샤프트",                                   # 8396163567, the shortest real text
    "PGM-G300",
    "XR26 풀세트",
])
def test_junk_must_not_match(kept):
    assert text(kept) == kept


def test_krw_price_promo():
    """8958060680: a KRW price promotion; our prices are USD."""
    t = ("일본 브리지스톤 BG-100 골프 풀세트\n무려 190,300원 할인!\n정상가 865,000원\n할인가 674,700원\n"
         "정상가 대비 22% 할인 혜택\n믿을 수 있는 브리지스톤의 골프 풀세트를")
    out = clean(t)
    assert out["text"] == "일본 브리지스톤 BG-100 골프 풀세트\n믿을 수 있는 브리지스톤의 골프 풀세트를"
    assert [d["rule"] for d in out["dropped"]] == ["price_krw"] * 4


@pytest.mark.parametrize("kept", [
    "쉽게 초원거리 구현",                                                       # 10569099959
    "반발력 10% 향상",
    "Flex R (Regular): 골프 입문자나 부담 없이 편안하고 경쾌한 스윙을 원하시는 골퍼에게 추천합니다.",   # 13777887875
    "로프트각(°)\nR: 10.5 / S: 9.5",                                             # 8958060680
    "클럽 무게(g)\nR: 294 / S: 297",
])
def test_krw_price_must_not_match(kept):
    assert text(kept) == kept


def test_cross_sell_line():
    """8958060680: the line points at a product card the parser left out."""
    t = "⛳블랙 컬러 모델은 2026년 9월에 출시되었습니다.\n해당 상품은 아래 링크에서 구매하실 수 있습니다."
    assert text(t) == "⛳블랙 컬러 모델은 2026년 9월에 출시되었습니다."
    assert rules(t) == ["cross_sell"]
    assert text("아래 이미지로 직접 확인하십시오!") == "아래 이미지로 직접 확인하십시오!"      # 12931402258


def test_contact_sentence_goes_whole():
    """8958060680: "...만큼" / "...있으시면" go on in the next line; the whole sentence is the contact."""
    t = "고가의 해외구매대행 상품인 만큼\n궁금한 점이 있으시면\n네이버 톡톡으로 문의해 주세요.\n\n아이언"
    out = clean(t)
    assert out["text"] == "아이언"
    assert out["dropped"] == [{"rule": "contact", "text": "고가의 해외구매대행 상품인 만큼\n궁금한 점이 있으시면\n"
                                                          "네이버 톡톡으로 문의해 주세요."}]


def test_face_noun_is_not_a_conditional():
    """"타격면" (the club face) ends on 면 and is a noun: it does not go on in the next line (10569099959)."""
    assert list(sentences(["고강도 타격면", "쉽게 원거리 실현"])) == [["고강도 타격면"], ["쉽게 원거리 실현"]]
    assert list(sentences(["460CC 대형 타격면", "x"])) == [["460CC 대형 타격면"], ["x"]]   # 12391346892


def test_contact_closings():
    """8958060680: the closing lines ask the buyer to write to the seller."""
    t = "※ 네임 플레이트는 수기 작성 타입입니다.\n\n궁금하신 내용을 편하게 여쭤봐주세요!\n언제나 빠르고 친절하게 답변드리겠습니다!"
    assert text(t) == "※ 네임 플레이트는 수기 작성 타입입니다."
    assert rules(t) == ["contact", "contact"]


@pytest.mark.parametrize("kept", [
    "가볍고 미스샷에도 강해 편하게\n비거리를 낼 수 있도록 설계되었습니다.",              # 8958060680
    "네임 스티커 서비스!!!\n주문시 성함을 입력해주세요~",                           # 13099257309
])
def test_contact_closing_must_not_match(kept):
    assert text(kept) == kept


def test_store_name_without_its_prefix():
    """8958060680: the store is "일본 구매대행 해피마로", the text says "해피마로는"."""
    t = "해피마로는 일본 현지에서\n정식 유통되는 제품만 취급하며,\n일본 내 공식 A/S 대상인 정품만 판매합니다.\n\n아이언"
    assert text(t, store_name="일본 구매대행 해피마로") == "아이언"
    assert rules(t, store_name="일본 구매대행 해피마로") == ["store_name"]
    # a store named after products keeps its whole name: no word of it alone is the store
    assert text("풀세트 드라이버 10.5도", store_name="씨에스골프 풀세트 드라이버") == "풀세트 드라이버 10.5도"
    assert text("좋은 상점 풀세트", store_name="쓸모있는 상점") == "좋은 상점 풀세트"


# ---- banner images: names, SmartEditor linkdata, QWERTY-typed Hangul ------------------------------------------

def _ld(src, w, h, link="", use=False):
    """A SmartEditor image component as the description HTML carries it (attribute JSON, HTML-escaped)."""
    data = (f'{{"id" : "SE-1", "src" : "{src}", "originalWidth" : "{w}", "originalHeight" : "{h}", '
            f'"linkUse" : "{str(use).lower()}", "link" : "{link}", "fileSize": "1" }}')
    return ('<a class="se-module-image-link" data-linktype="img" data-linkdata="' +
            data.replace('"', "&quot;") + '"><img src="data:image/png;base64,x"></a>')


PH = "https://shop-phinf.pstatic.net/20260330_300/"


def test_link_banners_by_linkdata():
    """13446843026: the store's Band / blog / Instagram buttons; 8958060680: the TalkTalk banner; a banner that
    opens the store's own page (6630856593 links to smartstore.naver.com/viviga_world/search?q=PGM)."""
    cases = [("Frame_1297.png", "https://www.band.us/@adpargolf"),
             ("Frame_1298.png", "https://blog.naver.com/andrian59"),
             ("Frame_1306.png", "https://www.instagram.com/adpargolf_official/"),
             ("talk.jpg", "https://talk.naver.com/ct/w43ac1"),
             ("ch.jpg", "https://pf.kakao.com/_xabc"), ("yt.jpg", "https://www.youtube.com/@shop"),
             ("store.jpg", "https://smartstore.naver.com/viviga_world/search?q=PGM&st=REVIEW&free=")]
    html = "".join(_ld(PH + n + "?type=w860", 700, 160, link, True) for n, link in cases)
    urls = [PH + n + "?type=w848" for n, _ in cases]
    out = clean_images(urls, html)
    assert out["images"] == []
    assert [(d["rule"], d["name"]) for d in out["dropped"]] == [("link_banner", n) for n, _ in cases]


@pytest.mark.parametrize("link,use", [
    ("https://smartstore.naver.com/main/products/13785630702", True),     # another product: not a store banner
    ("https://www.band.us/@adpargolf", False),                            # linkUse false: the link is not active
    ("", False),
])
def test_link_banners_must_not_match(link, use):
    html = _ld(PH + "Frame_22248.png", 1080, 326, link, use)
    assert clean_images([PH + "Frame_22248.png?type=w848"], html)["dropped"] == []


def test_spacer_strips():
    """13446843026: Rectangle_421.png 1080x12 and Frame_2218.png 1080x30 are spacer and divider strips."""
    html = _ld(PH + "Rectangle_421.png", 1080, 12) + _ld(PH + "Frame_2218.png?type=w860", 1080, 30) + \
        _ld(PH + "Frame_22248.png", 1080, 326)
    urls = [PH + "Rectangle_421.png?type=w848", PH + "Frame_2218.png?type=w848", PH + "Frame_22248.png?type=w848"]
    out = clean_images(urls, html)
    assert out["images"] == [urls[2]]
    assert [(d["rule"], d["name"]) for d in out["dropped"]] == [("spacer", "Rectangle_421.png"),
                                                                ("spacer", "Frame_2218.png")]


def test_spacer_must_not_match_unknown_size():
    """An outside image the editor did not measure has originalHeight 1 (8396163567 727_01.jpg, 860x1, the
    product's photo; 12945108653 golfzon_top.jpg): no size known, not a spacer. http vs https is one image."""
    html = _ld("http://ai.esmplus.com/yyuu88/dysys/pgm/727x6/727_01.jpg", 860, 1) + \
        _ld("https://shop-phinf.pstatic.net/a/OPTION00.jpg", 860, 100)
    urls = ["https://ai.esmplus.com/yyuu88/dysys/pgm/727x6/727_01.jpg", "https://shop-phinf.pstatic.net/a/OPTION00.jpg"]
    assert clean_images(urls, html)["dropped"] == []


def test_banner_names_pilot():
    """8958060680 "..._네이버톡톡_복사.jpg", "..._하단_상페_복사.jpg"; 13734679551 "하단고정배너(860)문구O.jpg"."""
    names = ["https://a.b/230826_happy_maro_%EB%84%A4%EC%9D%B4%EB%B2%84%ED%86%A1%ED%86%A1_%EB%B3%B5%EC%82%AC.jpg",
             "https://a.b/230826_happy_maro_%ED%95%98%EB%8B%A8_%EC%83%81%ED%8E%98_%EB%B3%B5%EC%82%AC.jpg",
             "https://a.b/%ED%95%98%EB%8B%A8%EA%B3%A0%EC%A0%95%EB%B0%B0%EB%84%88(860)%EB%AC%B8%EA%B5%ACO.jpg"]
    assert [d["name"] for d in clean_images(names)["dropped"]] == [
        "230826_happy_maro_네이버톡톡_복사.jpg", "230826_happy_maro_하단_상페_복사.jpg", "하단고정배너(860)문구O.jpg"]


@pytest.mark.parametrize("name", [
    "%EB%AF%BC%ED%8A%B8_%EB%93%9C%EB%9D%BC%EC%9D%B4%EB%B2%84_%EC%83%81%ED%8E%98.jpeg",    # 민트_드라이버_상페: the product's
    "PGM-%EB%B0%B0%EB%84%88.jpg",                                                          # PGM-배너.jpg
    "%EB%84%A4%EC%9E%84%EC%8A%A4%ED%8B%B0%EC%BB%A4_%EC%84%B1%ED%95%A8_%EC%9E%91%EC%84%B1_%EB%B0%B0%EB%84%88.jpg",  # 네임스티커 배너
])
def test_banner_names_pilot_must_not_match(name):
    assert clean_images(["https://a.b/" + name])["dropped"] == []


def test_qwerty_hangul():
    """Hangul typed with the keyboard left on Latin (2-set layout): "gkeksqpsj" is 하단베너 (6540695739)."""
    assert qwerty_hangul("gkeksqpsj") == "하단베너"
    assert qwerty_hangul("gkeksqosj") == "하단배너"
    assert qwerty_hangul("qothd") == "배송" and qwerty_hangul("rhdwl") == "공지"
    assert qwerty_hangul("dkssudgktpdy") == "안녕하세요"
    assert qwerty_hangul("ekfrrhrl") == "닭고기"                          # a double final consonant
    assert qwerty_hangul("Tkdeh") == "쌍도"                               # shifted: a double consonant


@pytest.mark.parametrize("word", ["brand", "logo", "csgolf", "sfhhhgsdehy", "touredge", "bottom", "frame",
                                  "rectangle", "delivery", "notice", "wistella", "yamamoto", "choice", "edge",
                                  "lc", "g", "a", "bag", "main", "sub"])
def test_qwerty_hangul_not_for_latin_words(word):
    assert qwerty_hangul(word) is None


def test_qwerty_banner_name():
    """6540695739: the tile body's bottom banner daumgolf.cafe24.com/daumgood/tee/gkeksqpsj.jpg."""
    link = proxy("daumgolf.cafe24.com/daumgood/tee/gkeksqpsj.jpg")
    assert [d["name"] for d in clean_images([link])["dropped"]] == ["gkeksqpsj.jpg"]
    tiles = ["https://shop-phinf.pstatic.net/20260105_1/p-6540695739-s-6-A-0.jpg"]
    assert body_notes(f'<img data-src="{link}"><img src="https://a.b/sfhhhgsdehy.PNG">', tiles) == [
        {"code": "description_tiles_include_banners", "detail": "gkeksqpsj.jpg"}]


@pytest.mark.parametrize("name", ["brand_logo_g430.jpg", "g430.jpg", "csgolf.jpg", "sfhhhgsdehy.PNG",
                                  "Frame_1294.jpg", "Rectangle_421.png", "touredge_woman.jpg", "choice_m.jpg",
                                  "lc01.jpg", "gbk01.jpg", "IR_SIM2_MAX.jpg", "staticmap.bin", "main0.jpg",
                                  # Latin runs that do type whole syllables (찯야색, 터도뿋), no banner word in them
                                  "ckeditor_202603100624083429_0.jpg", "O1CN01eZnhbN1xy5XjehQYG_3694786511.jpg"])
def test_qwerty_banner_name_must_not_match(name):
    assert clean_images(["https://a.b/" + name])["dropped"] == []
