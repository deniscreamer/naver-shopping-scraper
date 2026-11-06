"""Offline tests for the Naver Shopping parsers and reference resolvers.

    python -m pytest server/naver_shopping/test_parsers.py -q

Fixtures (naver_shopping/fixtures/, captured 2026-10-24): ns-portal search
slots (plain, filtered, a nonsense query), two smartstore /best pages and a
brand /best page, a brand product page, the store-backend answers for one
smartstore product (summary, options, description, notice, review
summary, two review pages, popular / best lists, category tree, unknown
ids) plus catalog reviews, and the DataLab JSON (categories, keyword rank,
trends, device / gender / age shares). No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from naver_shopping import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---- refs --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("10352481064", "https://smartstore.naver.com/main/products/10352481064"),
    ("https://smartstore.naver.com/bauato/products/10352481064", "https://smartstore.naver.com/bauato/products/10352481064"),
    ("https://m.smartstore.naver.com/bauato/products/10352481064?NaPm=x", "https://smartstore.naver.com/bauato/products/10352481064"),
    ("smartstore.naver.com/main/products/10352481064", "https://smartstore.naver.com/main/products/10352481064"),
    ("https://brand.naver.com/drbrian/products/4685898105", "https://brand.naver.com/drbrian/products/4685898105"),
    ("https://m.brand.naver.com/drbrian/products/4685898105/", "https://brand.naver.com/drbrian/products/4685898105"),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "123", "https://example.com/x/products/10352481064",
                                   "https://smartstore.naver.com/bauato", "https://search.shopping.naver.com/catalog/61626354397"])
def test_resolve_product_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


def test_split_product_link():
    assert refs.split_product_link("https://smartstore.naver.com/main/products/1") == {"id": "1", "slug": None, "is_brand": False}
    assert refs.split_product_link("https://brand.naver.com/drbrian/products/4685898105") == \
        {"id": "4685898105", "slug": "drbrian", "is_brand": True}


@pytest.mark.parametrize("value,expected", [
    ("bauato", "https://smartstore.naver.com/bauato"),
    ("https://smartstore.naver.com/bauato/products/10352481064", "https://smartstore.naver.com/bauato"),
    ("https://m.smartstore.naver.com/seragio?x=1", "https://smartstore.naver.com/seragio"),
    ("https://brand.naver.com/samsung", "https://brand.naver.com/samsung"),
])
def test_resolve_store(value, expected):
    assert refs.resolve_store(value) == expected


@pytest.mark.parametrize("value", ["", "10352481064", "https://smartstore.naver.com/main/products/1", "https://example.com/bauato", "a b"])
def test_resolve_store_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_store(value)


@pytest.mark.parametrize("value,expected", [
    ("61626354397", "61626354397"),
    ("https://search.shopping.naver.com/catalog/61626354397?query=x", "61626354397"),
    ("https://msearch.shopping.naver.com/catalog/61626354397", "61626354397"),
    ("https://cr3.shopping.naver.com/v2/bridge/searchGate?nv_mid=61626354397&cat_id=50001519", "61626354397"),
])
def test_resolve_catalog(value, expected):
    assert refs.resolve_catalog(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "https://smartstore.naver.com/bauato", "https://example.com/catalog/61626354397"])
def test_resolve_catalog_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_catalog(value)


@pytest.mark.parametrize("value,ok", [("50000003", True), ("0", True), ("5000003", False), ("60000003", False), ("", False)])
def test_resolve_category(value, ok):
    if ok:
        assert refs.resolve_category(value) == value
    else:
        with pytest.raises(ValueError):
            refs.resolve_category(value)


# ---- helpers ------------------------------------------------------------------------

def test_value_helpers():
    assert P._clean("  ********  ") is None
    assert P._clean("&amp; x") == "& x"
    assert P._text("<mark>아이폰</mark> 18") == "아이폰 18"
    assert P._rich_text("a<br><br>b &amp; c<b>!</b>") == "a\n\nb & c!"
    assert P._price(0) is None and P._price("1200") == 1200
    assert P._date("20261024") == "2026-10-24"
    assert P._date("2026.10.24.") == "2026-10-24"
    assert P._date("2026-10-24T09:40:03.578+00:00") == "2026-10-24"
    assert P._datetime("2026-10-24T09:40:03.578+09:00") == "2026-10-24T00:40:03Z"
    assert P._datetime(None) is None


# ---- search -------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cards():
    return P.parse_search_slots(fixture("search_slots.json"))


def test_search_cards_shape(cards):
    assert 60 <= len(cards) <= 96
    kinds = {c["type"] for c in cards}
    assert "product" in kinds and "catalog" in kinds
    product = next(c for c in cards if c["type"] == "product" and c["store"]["is_smart_store"])
    assert product["id"].isdigit() and product["product_id"].isdigit() and product["origin_product_id"].isdigit()
    assert product["link"].startswith("https://smartstore.naver.com/main/products/")
    assert product["store"]["link"].startswith("https://smartstore.naver.com/") or product["store"]["link"].startswith("https://brand.naver.com/")
    assert product["store"]["merchant_id"].isdigit()
    assert product["pricing"]["discounted_price"] > 0 and product["pricing"]["currency"] == "KRW"
    assert product["reviews"]["count"] >= 0 and product["images"]
    assert product["category"]["id"].startswith("5") and len(product["category"]["path_ids"]) >= 3
    assert "<mark>" not in product["name"]
    catalog = next(c for c in cards if c["type"] == "catalog")
    assert catalog["store"] is None and catalog["catalog_id"] == catalog["id"]
    assert catalog["link"] == f"https://search.shopping.naver.com/catalog/{catalog['id']}"
    assert catalog["mall_count"] is not None


def test_search_filtered_and_nonsense():
    filtered = P.parse_search_slots(fixture("search_slots_filtered.json"))
    assert filtered and all(c["category"]["path_ids"][-1] == "50001519" or "50001519" in c["category"]["path_ids"] for c in filtered)
    assert all(100000 <= c["pricing"]["discounted_price"] <= 300000 for c in filtered)
    assert P.parse_search_slots(fixture("search_slots_nonsense.json")) == []
    assert P.parse_search_slots(None) == []
    assert P.parse_search_slots([{"slots": [{"slotType": "CARD", "data": None}]}]) == []


def test_search_card_sparse():
    card = P.parse_search_card({"nvMid": 1, "productName": "x"})
    assert card["id"] == "1" and card["name"] == "x" and card["pricing"]["discounted_price"] is None
    assert card["store"]["name"] is None and card["images"] == []


# ---- stores -------------------------------------------------------------------------

def test_store_page_smartstore():
    page = P.parse_store_page(fixture("store_best_seragio.html"))
    store = page["store"]
    assert store["uid"] == "2sWDvOMJt8KO2RJAoa750" and store["id"] == "500009638"
    assert store["merchant_id"] == "500009638" and store["slug"] == "seragio"
    assert store["name"] == "대우침장" and store["type"] == "smart_store"
    assert store["link"] == "https://smartstore.naver.com/seragio"
    assert store["grade"] == "THIRD" and store["sale_count"] == 200
    assert store["business"]["legal_name"] == "대우침장" and store["business"]["phone"] is None   # masked
    assert store["business"]["address"] is None and store["business"]["type"] == "PRIVATE"
    assert store["social"]["instagram"] == ["houzy_bedding"]
    assert page["categories"] and page["categories"][0]["name"] and page["categories"][0]["level"] == 1


def test_store_page_brand_host():
    page = P.parse_store_page(fixture("brand_best_drbrian.html"))
    assert page["store"]["uid"] == "2sWDvfJXl0MkfnLYNaaXS" and page["store"]["type"] == "brand_store"
    assert page["store"]["link"] == "https://brand.naver.com/drbrian" and page["store"]["slug"] == "ibs"
    assert page["store"]["brand_ids"] == ["256828"]


def test_store_page_without_state():
    assert P.parse_store_page("<html><title>NAVER 로그인</title></html>") is None
    assert P.parse_state("") == {}


def test_category_tree():
    tree = P.parse_category_tree(fixture("box_category_tree.json"))
    assert tree and tree[0]["name"] and "children" in tree[0]
    assert P.parse_category_tree(None) == []


# ---- products -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def product():
    return P.parse_simple_product(fixture("box_simple_product.json")[0], "bauato")


def test_simple_product(product):
    assert product["id"] == "10352481064" and product["origin_product_id"] == "10302552667"
    assert product["link"] == "https://smartstore.naver.com/bauato/products/10352481064"
    assert product["catalog_id"] == "87896985537"
    assert product["pricing"]["sale_price"] == 60800 and product["pricing"]["discounted_price"] == 37800
    assert product["pricing"]["discount_ratio"] == 37 and product["pricing"]["seller_discount"] == 23000
    assert product["category"]["path"] == ["디지털/가전", "휴대폰액세서리", "휴대폰배터리", "보조배터리"]
    assert product["brand"] == "바우아토" and product["model_name"]
    assert len(product["images"]) >= 5 and product["reviews"]["count"] > 6000
    assert product["delivery"]["is_free"] is True and product["delivery"]["company"]
    assert product["store"]["uid"] == "2tM2sBNWRoB8NdZLNZItU" and product["store"]["slug"] == "bauato"
    assert product["is_displayed"] is True and product["has_options"] is True


def test_simple_product_without_slug_has_no_link():
    sp = dict(fixture("box_simple_product.json")[0])
    sp["channel"] = {"channelNo": 1, "accountId": "ncp_x"}
    assert P.parse_simple_product(sp)["link"] is None
    assert P.parse_simple_product({})["id"] is None


def test_brand_product_page():
    page = P.parse_brand_product_page(fixture("brand_product_drbrian.html"), "drbrian")
    assert page["store"]["uid"] == "2sWDvfJXl0MkfnLYNaaXS" and page["store"]["merchant_id"] == "500094507"
    assert page["product"]["id"] == "4685898105" and page["product"]["origin_product_id"] == "4674276092"
    assert page["product"]["link"] == "https://brand.naver.com/drbrian/products/4685898105"
    assert page["product"]["pricing"]["discounted_price"] == 11900
    assert P.parse_brand_product_page("<html></html>", "x") is None


def test_validation():
    v = P.parse_validation(fixture("box_validation.json"))
    assert v["status"] == "SALE" and v["stock_quantity"] > 0
    assert v["option_groups"][0]["name"] and v["variants"]
    first = v["variants"][0]
    assert first["id"] and first["name"] and first["stock_quantity"] is not None and first["extra_price"] == 0
    assert first["is_available"] is (first["stock_quantity"] > 0)
    assert v["delivery"]["company"]
    empty = P.parse_validation(None)
    assert empty["variants"] == [] and empty["option_groups"] == []


def test_contents_and_notice():
    """2026-11-01: an image-only description (SmartEditor ONE, textContent blank)
    has no text; it used to come out as "\u200b \u200b ..." from a tag strip."""
    c = P.parse_contents(fixture("box_contents.json"))
    assert c["html"] and c["text"] is None and c["editor_type"]
    n = P.parse_notice(fixture("box_notice.json"))
    assert n["type"] and n["items"] and n["items"][0]["label"] and n["terms"]
    assert P.parse_contents({})["html"] is None
    assert P.parse_notice({})["items"] == []


def test_review_summary():
    s = P.parse_review_summary(fixture("box_review_summary.json"))
    assert s["count"] > 6000 and 4 < s["average_score"] <= 5
    assert set(s["score_counts"]) == {"1", "2", "3", "4", "5"}
    assert s["recent"]["count"] > 0 and s["representative_reviews"][0]["text"]
    assert P.parse_review_summary(None)["count"] is None


def test_review_video_attachment():
    """2026-11-01, bauato power bank: a video is reviewAttachmentType "M" + video/mp4 (was read as an image)."""
    video = {"reviewAttachmentType": "M", "mimeTypeName": "video/mp4", "attachWidth": 1920, "attachHeight": 1080,
             "attachUrl": "https://phinf.pstatic.net/image.nmv/shopnbuyer_2026_10_19_2747/WmRzkCe9dg_03.jpg"}
    photo = {"reviewAttachmentType": "I", "attachUrl": "https://phinf.pstatic.net/checkout.phinf/x.jpeg"}
    r = P.parse_review({"id": 1, "reviewAttaches": [photo, video]})
    assert [a["type"] for a in r["attachments"]] == ["image", "video"] and r["attachments"][1]["width"] == 1920


def test_review_placeholder_avatar_is_null():
    """2026-11-01: a writer without an avatar comes as profile-phinf.pstatic.net/404/default.png."""
    reviews, _ = P.parse_reviews_page(fixture("box_reviews_page1.json"))
    avatars = [r["writer"]["profile_image"] for r in reviews]
    assert avatars.count(None) == 13 + sum(1 for r in fixture("box_reviews_page1.json")["contents"]
                                           if not r.get("writerProfileImageUrl"))
    assert all(a is None or "/404/" not in a for a in avatars)


def test_reviews_page():
    reviews, pagination = P.parse_reviews_page(fixture("box_reviews_page1.json"))
    assert len(reviews) == 20 and pagination["total_count"] > 6000 and pagination["total_pages"] > 300
    assert pagination["page"] == 1 and pagination["items_per_page"] == 20
    r = reviews[0]
    assert r["id"] and r["score"] in (1, 2, 3, 4, 5) and r["created_at"].endswith("Z")
    assert r["writer"]["masked_id"] and r["product"]["id"] == "10352481064"
    assert isinstance(r["attachments"], list)
    past = fixture("box_reviews_page_past_end.json")
    assert past is None or past == {} or P.parse_reviews_page(past)[0] == []


def test_store_products():
    popular = P.parse_store_products(fixture("box_popular_products.json"), slug="bauato")
    assert len(popular) == 20 and popular[0]["link"].startswith("https://smartstore.naver.com/bauato/products/")
    best = P.parse_store_products(fixture("box_best_products.json"), key="WEEKLY", slug="bauato")
    assert 20 <= len(best) <= 30 and best[0]["pricing"]["discounted_price"]
    assert P.parse_store_products(fixture("box_best_products.json"), key="NOPE") == []


def test_unknown_product_answers():
    assert fixture("box_validation_unknown.json") is None
    assert fixture("box_simple_product_unknown.json") == []


# ---- catalogs ------------------------------------------------------------------------

def test_catalog_reviews():
    rows = P.parse_catalog_reviews(fixture("box_catalog_reviews.json"), "61626354397")
    assert rows and rows[0]["score"] == 5 and "<br>" not in rows[0]["text"] and "\n" in rows[0]["text"]
    assert rows[0]["created_at"] == "2026-09-29" and rows[0]["writer"] and rows[0]["attachments"]
    assert P.parse_catalog_reviews(fixture("box_catalog_reviews_unknown.json"), "1234567890") == []


# ---- DataLab ---------------------------------------------------------------------------

def test_datalab_categories():
    root = P.parse_datalab_categories(fixture("datalab_category_root.json"))
    assert root["category"]["id"] == "0" and root["category"]["parent_id"] is None
    assert len(root["children"]) == 12 and root["children"][0]["id"] == "50000000"
    child = P.parse_datalab_categories(fixture("datalab_category_child.json"))
    assert child["category"]["id"] == "50000003" and child["category"]["parent_id"] == "0"
    assert child["children"] and child["children"][0]["parent_id"] == "50000003" and child["children"][0]["path"]


def test_datalab_rank():
    ranks = P.parse_datalab_rank(fixture("datalab_keyword_rank.json"))
    assert len(ranks) == 20 and ranks[0] == {"rank": 1, "keyword": ranks[0]["keyword"]} and ranks[0]["keyword"]
    assert P.parse_datalab_rank(fixture("datalab_keyword_rank_last.json")) == []


def test_datalab_series_and_ratios():
    series = P.parse_datalab_series(fixture("datalab_category_trend.json"))
    assert len(series) == 31 and series[0]["date"] == "2026-09-23" and 0 <= series[0]["value"] <= 100
    week = P.parse_datalab_series(fixture("datalab_category_trend_week.json"))
    assert week and week[0]["date"].count("-") == 2
    assert P.parse_datalab_series(fixture("datalab_keyword_trend_empty.json")) == []
    device = P.parse_datalab_ratios(fixture("datalab_category_device.json"))
    assert {d["code"] for d in device} == {"pc", "mo"} and max(d["ratio"] for d in device) == 100.0
    age = P.parse_datalab_ratios(fixture("datalab_category_age.json"))
    assert len(age) == 6 and age[0]["label"]
    assert P.datalab_range(fixture("datalab_category_trend.json")) == {"start_date": "2026-09-23", "end_date": "2026-10-23"}


# ---- transport --------------------------------------------------------------------------

def test_session_carries_an_nnb_cookie(monkeypatch):
    """ns-portal 418s a request with no naver.com cookie (2026-10-29): every
    curl session starts with its own NNB browser-id cookie."""
    import re
    from naver_shopping import fetch as F
    monkeypatch.setattr(F.config, "naver_shopping_proxy", lambda: None)
    F._drop_session()
    try:
        first = F._session().cookies.get("NNB", domain=".naver.com")
        F._drop_session()
        second = F._session().cookies.get("NNB", domain=".naver.com")
    finally:
        F._drop_session()
    assert re.fullmatch(r"[A-Z0-9]{13}", first) and re.fullmatch(r"[A-Z0-9]{13}", second)
    assert first != second


def test_reviews_send_the_sort_as_review_search_sort_type(monkeypatch):
    """The review backend sorts by reviewSearchSortType only; under any other
    key every sort came back newest-first (2026-10-29)."""
    from naver_shopping import api as A
    sent = {}
    record = {"base": {"id": "8087042745", "origin_product_id": "8048440943", "name": "n", "link": "l"},
              "store": {"merchant_id": "500278691"}, "review_summary": None}
    monkeypatch.setattr(A, "_record", lambda product: record)
    monkeypatch.setattr(A, "box_post", lambda path, body, label: sent.update(body) or None)
    A._reviews(product="https://smartstore.naver.com/dailyromantic/products/8087042745", page=1,
               sort="REVIEW_SCORE_ASC")
    assert sent["reviewSearchSortType"] == "REVIEW_SCORE_ASC" and "reviewSort" not in sent


def test_search_price_range_always_has_both_bounds():
    """ns-portal ignores "|100000" / "50000|" and answers unfiltered results
    (2026-10-29), so an open bound is filled in."""
    from naver_shopping import api as A
    assert A._filters({"max_price": 100000})["price"] == "0|100000"
    assert A._filters({"min_price": 50000.0})["price"] == f"50000|{A.OPEN_MAX_PRICE}"
    assert A._filters({"min_price": 50000, "max_price": 100000})["price"] == "50000|100000"
    assert "price" not in A._filters({"free_delivery": True})


def test_seone_description_images():
    # a SmartEditor ONE body (taylormade set 13229257286, 2026-11-05): no snapImages, photos in data-src
    with open(os.path.join(FX, "contents_seone_images.html"), encoding="utf-8") as f:
        c = P.parse_contents({"renderContent": f.read(), "editorType": "SEONE", "snapImages": []})
    assert len(c["images"]) == 2 and all(u.startswith("https://shop-phinf.pstatic.net/") for u in c["images"])
    assert P.parse_contents({"renderContent": "<p>x</p>", "snapImages": [{"url": "https://a/b.jpg"}]})["images"] \
        == ["https://a/b.jpg"]


def test_page_delivery_overseas():
    d = P.parse_page_delivery(fixture("page_delivery_overseas.json"))   # callaway set 6774818843, 2026-11-05
    assert (d["fee_type"], d["base_fee"], d["is_free"], d["is_overseas"]) == ("UNIT_QUANTITY_PAID", 99000, False, True)
    assert d["scope"] == "international" and d["lead_time"]["seller_average_days"] == 5.0
    assert d["lead_time"]["product_average_days"] is None                # 0 = no average yet
    assert P.parse_page_delivery({**fixture("page_delivery_overseas.json"), "customsTaxType": "EXCLUDED"})[
        "customs_tax_type"] == "EXCLUDED"                                   # at the answer's top level
    assert d["extra_fee_area2"] == 3000 and "1개마다" in d["policy_text"]
    assert P.parse_page_delivery({}) is None
    assert d["lead_time"]["today_cutoff"] is None and d["lead_time"]["arrival_date_text"] is None
    today = fixture("page_delivery_overseas.json")
    today["productDeliveryInfo"] = {**today["productDeliveryInfo"], "todayDelivery": True,
                                    "thisDayDispatchBasisTime": "05:30:00.000+0000"}   # UTC: 14:30 in Korea
    assert P.parse_page_delivery(today)["lead_time"]["today_cutoff"] == "14:30"
    assert P.parse_page_delivery(today, {"today_cutoff": "16:00"})["lead_time"]["today_cutoff"] == "16:00"
    assert P.parse_page_delivery(today)["lead_time"]["today_off"] is None              # no box read: not known


def test_page_delivery_day_off_skips_the_dispatch_time():
    """"오늘출발 휴무" (10816781893, 13302492097, 6540695739, 10816904599 read 2026-11-06 after KST midnight): the
    answer still says todayDelivery true with thisDayDispatchBasisTime, which would read as a same-day dispatch."""
    off = fixture("page_delivery_overseas.json")
    off["productDeliveryInfo"] = {**off["productDeliveryInfo"], "todayDelivery": True,
                                  "thisDayDispatchBasisTime": "04:00:00.000+0000"}
    lead = P.parse_page_delivery(off, {"today_cutoff": None, "today_off": True, "ship_date_text": "11.9.(월)"})[
        "lead_time"]
    assert (lead["today_cutoff"], lead["today_off"], lead["ship_date_text"]) == (None, True, "11.9.(월)")
    lead = P.parse_page_delivery(off, {"today_cutoff": None, "today_off": False})["lead_time"]
    assert (lead["today_cutoff"], lead["today_off"]) == ("13:00", False)          # a box without the cutoff line


def test_description_images_inline_plain_and_map():
    body = ('<div><img class="se-image-resource" src="data:image/png;base64,x" data-src="https://a.pstatic.net/1.jpg">'
            '<table><tr><td><img class="se-inline-image-resource" src="data:image/png;base64,x" '
            'data-src="https://ai.esmplus.com/2.jpg"></td></tr></table>'
            '<img class="se-map-image" src="https://simg.pstatic.net/static.map/v2/map/staticmap.bin?x=1">'
            '<img src="https://shop-phinf.pstatic.net/3.jpg"><img src="https://shop-phinf.pstatic.net/3.jpg"></div>')
    assert P.parse_contents({"renderContent": body, "snapImages": []})["images"] == [   # 2026-11-06 shapes
        "https://a.pstatic.net/1.jpg", "https://ai.esmplus.com/2.jpg", "https://shop-phinf.pstatic.net/3.jpg"]


def test_description_images_skip_cards():
    """2026-11-06: images follow the same components as the text. An se-oglink thumbnail (dthumb-phinf, another
    product or the TalkTalk logo), an se-material poster (shopping-phinf main_*: other products of 12274419597) and the
    se-placesMap map are not the product's photos."""
    oglink = ('<div class="se-component se-oglink"><img data-src="https://dthumb-phinf.pstatic.net/?src=%22https%3A%2F%2F'
              'shop-phinf.pstatic.net%2Fa.jpg%22" class="se-oglink-thumbnail-resource"></div><div class="se-component '
              'se-image"><img data-src="https://shop-phinf.pstatic.net/b.jpg" class="se-image-resource"></div>')
    assert P._body_images(oglink) == ["https://shop-phinf.pstatic.net/b.jpg"]
    material = ('<div class="se-component se-material"><a href="https://smartstore.naver.com/main/products/12270862728">'
                '<img class="se-material-poster-resource" data-src="https://shopping-phinf.pstatic.net/main_8981537/'
                '89815373444.2.jpg"></a></div><div class="se-component se-image"><img class="se-image-resource" '
                'data-src="https://shop-phinf.pstatic.net/c.jpg"></div>')
    assert P._body_images(material) == ["https://shop-phinf.pstatic.net/c.jpg"]
    # the card's own image class, even outside its component
    stray = ('<img class="se-oglink-thumbnail-resource" data-src="https://dthumb-phinf.pstatic.net/x.jpg">'
             '<img class="se-material-poster-resource" data-src="https://shopping-phinf.pstatic.net/y.jpg">'
             '<img src="https://simg.pstatic.net/static.map/v2/map/staticmap.bin?x=1">'
             '<img class="se-map-image" data-src="https://simg.pstatic.net/z.png">')
    assert P._body_images(stray) == []


def test_description_images_keep_inline_and_plain():
    body = ('<table><td><img class="se-inline-image-resource" data-src="https://shop-phinf.pstatic.net/d.jpg"></td>'
            '</table><img src="data:image/png;base64,x" data-src="https://smartfic.co.kr/upload/product/imgdetail/3170.jpg">'
            "<div class='se-component se-imageStrip'><img class='se-image-resource' data-src='https://shop-phinf.pstatic.net/e.jpg?type=w860'></div>"
            '<IMG SRC="https://shop-phinf.pstatic.net/f.jpg">')
    assert P._body_images(body) == ["https://shop-phinf.pstatic.net/d.jpg",
                                    "https://smartfic.co.kr/upload/product/imgdetail/3170.jpg",
                                    "https://shop-phinf.pstatic.net/e.jpg?type=w860", "https://shop-phinf.pstatic.net/f.jpg"]
    assert P._body_images('<img src="data:image/png;base64,x">') == [] and P._body_images(None) == []


def test_description_cards_fixture_images():
    with open(os.path.join(FX, "contents_seone_cards.html"), encoding="utf-8") as f:
        c = P.parse_contents({"renderContent": f.read(), "editorType": "SEONE", "snapImages": []})
    assert c["images"] == ["https://shop-phinf.pstatic.net/20260201_192/17699187726654ipjH_PNG/"
                           "20019506300428036_252033136.png?type=w848"]
    assert "굿바이골프" not in c["text"] and "따봉몰" not in c["text"]
