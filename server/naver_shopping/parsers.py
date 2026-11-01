"""Naver Shopping parsers: raw JSON / HTML -> clean dicts. Pure functions,
no I/O. Fixtures in naver_shopping/fixtures/ were captured 2026-10-24
(search slots from ns-portal, a smartstore best page, a brand product
page, the store-backend answers for a smartstore product, DataLab JSON).

Masked values ("********": phone numbers, addresses, e-mails Naver hides
from logged-out visitors) become null. Prices are KRW integers.
"""
import html as html_lib
import json
import re
from datetime import datetime
from urllib.parse import parse_qs, unquote, urlparse

from naver_shopping.refs import BRAND, SMARTSTORE, catalog_link, product_link, store_link

MASK = "********"
CURRENCY = "KRW"

_STATE_RE = re.compile(r"window\.__PRELOADED_STATE__\s*=\s*")
_TAG_RE = re.compile(r"<[^>]+>")
_UNDEFINED_RE = re.compile(r":\s*undefined\b")


# ---- small helpers -----------------------------------------------------------------

def _clean(value):
    """Strings: strip, HTML-unescape, masked / empty -> None. Others as is."""
    if isinstance(value, str):
        value = html_lib.unescape(value).strip()
        return None if value in ("", MASK) else value
    return value


def _text(value):
    """Strip <mark> and other tags from a highlighted search title."""
    value = _clean(value)
    return _clean(_TAG_RE.sub("", value)) if value else None


_BR_RE = re.compile(r"<br\s*/?>", re.I)


def _rich_text(value):
    """Review bodies: <br> -> newline, other tags dropped, entities decoded."""
    if not isinstance(value, str):
        return None
    value = _TAG_RE.sub("", _BR_RE.sub("\n", value))
    value = html_lib.unescape(value).strip()
    return value or None


def _int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _price(value):
    """A KRW amount; 0 means "none" on every surface (a catalog card's
    salePrice, a missing discount)."""
    value = _int(value)
    return value if value else None


def _bool(value):
    return value if isinstance(value, bool) else None


def _date(value):
    """'2026-10-24T09:40:03.578+00:00' -> '2026-10-24'; '20261024' -> '2026-10-24';
    '2026.10.24.' -> '2026-10-24'."""
    value = _clean(value)
    if not value:
        return None
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    match = re.match(r"(\d{4})[-.](\d{2})[-.](\d{2})", value)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else value


def _datetime(value):
    """'2026-10-24T09:40:03.578+00:00' -> '2026-10-24T09:40:03Z' (UTC)."""
    value = _clean(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(tz=__import__("datetime").timezone.utc).replace(tzinfo=None)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


# ---- page state ----------------------------------------------------------------------

def parse_state(page_html):
    """window.__PRELOADED_STATE__ of a smartstore / brand page -> dict ({} when
    absent). It is a JS literal (`:undefined` inside), not strict JSON."""
    match = _STATE_RE.search(page_html or "")
    if not match:
        return {}
    text = _UNDEFINED_RE.sub(":null", page_html[match.end():])
    try:
        return json.JSONDecoder().raw_decode(text)[0]
    except (ValueError, IndexError):
        return {}


# ---- stores --------------------------------------------------------------------------

def _social(info):
    exposure = _dict(_dict(info).get("exposureInfo"))
    out = {}
    for key, handles in exposure.items():
        if isinstance(handles, list) and handles:
            out[key.lower()] = handles
    return out or None


def parse_channel(channel, brand_slug=None):
    """The store record (page state `channel`, a product's `channel`)."""
    ch = _dict(channel)
    slug = _clean(ch.get("url")) or _clean(ch.get("accountId"))
    is_brand = _clean(ch.get("storeExhibitionType")) == "BRAND_STORE"
    brand_url = _clean(ch.get("brandUrl")) if is_brand else None
    link_slug = brand_url or brand_slug or slug
    return {
        "id": _clean(str(ch.get("channelNo") or ch.get("id") or "")) or None,
        "uid": _clean(ch.get("channelUid")),
        "name": _clean(ch.get("channelName")),
        "slug": slug,
        "link": store_link(link_slug, brand=bool(is_brand and brand_url)) if link_slug else None,
        "type": "brand_store" if is_brand else "smart_store",
        "description": _clean(ch.get("description")),
        "image": _clean(ch.get("representativeImageUrl")),
        "grade": _clean(ch.get("actionGrade")),
        "sale_count": _int(ch.get("saleCount")),
        "open_duration": _clean(ch.get("storeOpenDuration")),
        "merchant_id": _clean(str(ch.get("payReferenceKey") or ch.get("naverPayNo") or "")) or None,
        "account_id": _clean(ch.get("accountId")),
        "mall_seq": _int(ch.get("mallSeq")),
        "brand_ids": [str(b) for b in _list(ch.get("brandIds"))] or None,
        "business": {
            "legal_name": _clean(ch.get("representName")),
            "representative": _clean(ch.get("representativeName")),
            "type": _clean(ch.get("businessType")),
            "is_business": _bool(ch.get("isBusiness")),
            "is_overseas": _bool(_dict(ch.get("businessAddressInfo")).get("overseas")),
            "phone": _clean(_dict(_dict(ch.get("contactInfo")).get("telNo")).get("formattedNumber")),
            "email": _clean(ch.get("chrgrEmail")),
            "address": _clean(_dict(ch.get("businessAddressInfo")).get("fullAddressInfo")),
        },
        "talk_id": _clean(ch.get("talkAccountId")),
        "social": _social(ch.get("storeExposureInfo")),
        "product_auth_categories": _list(ch.get("productAuthCategoryTypes")) or None,
        "has_arrival_guarantee": _bool(ch.get("arrivalGuaranteeUseYn")),
        "has_free_return_insurance": _clean(ch.get("freeReturnInsuranceStatusType")) == "COMPLETE"
        if ch.get("freeReturnInsuranceStatusType") is not None else None,
        "has_regular_subscription": _bool(ch.get("regularSubscriptionYn")),
        "has_lounge": _bool(ch.get("loungeOperateYn")),
        "is_exhibiting": _bool(ch.get("exhibitionYn")),
    }


def store_summary(channel, slug=None):
    ch = _dict(channel)
    slug = slug or _clean(ch.get("url"))
    return {
        "id": _clean(str(ch.get("channelNo") or ch.get("id") or "")) or None,
        "uid": _clean(ch.get("channelUid")),
        "name": _clean(ch.get("channelName")),
        "slug": slug,
        "link": store_link(slug) if slug else None,
    }


def _category_tree(items):
    """Flat store categories (level, parentStoreCategoryId) -> nested list."""
    nodes = {}
    for item in _list(items):
        nodes[item.get("id")] = {
            "id": _clean(item.get("id")), "name": _clean(item.get("name")), "level": _int(item.get("level")),
            "type": _clean(item.get("type")), "is_all_products": _bool(item.get("allProductCategory")),
            "sort_type": _clean(item.get("productSortType")), "children": [],
        }
    roots = []
    for item in _list(items):
        parent = item.get("parentStoreCategoryId")
        node = nodes[item.get("id")]
        if parent in nodes and parent != item.get("id"):
            nodes[parent]["children"].append(node)
        else:
            roots.append(node)
    return roots


def parse_store_page(page_html):
    """A /<slug>/best page -> {store, categories} or None (no store state)."""
    state = parse_state(page_html)
    channel = _dict(state.get("channel"))
    if not channel.get("channelUid"):
        return None
    return {
        "store": parse_channel(channel),
        "categories": _category_tree(_dict(state.get("categoryMenu")).get("firstCategories")),
    }


def parse_category_tree(tree):
    """The /categories/tree/DISPLAY answer -> nested list (root dropped)."""
    def node(item):
        return {
            "id": _clean(item.get("id")), "name": _clean(item.get("name")), "level": _int(item.get("level")),
            "type": _clean(item.get("type")), "is_all_products": _bool(item.get("allProductCategory")),
            "children": [node(c) for c in _list(item.get("subCategories"))],
        }
    return [node(c) for c in _list(_dict(tree).get("subCategories"))]


# ---- products --------------------------------------------------------------------------

def _category(cat):
    cat = _dict(cat)
    names = [_clean(n) for n in (cat.get("wholeCategoryName") or "").split(">") if _clean(n)]
    ids = [_clean(i) for i in (cat.get("wholeCategoryId") or "").split(">") if _clean(i)]
    return {
        "id": _clean(cat.get("categoryId")) or (ids[-1] if ids else None),
        "name": _clean(cat.get("categoryName")) or (names[-1] if names else None),
        "path": names or None,
        "path_ids": ids or None,
    }


def _delivery(info):
    d = _dict(info)
    company = _dict(d.get("deliveryCompany"))
    bundle = _dict(d.get("deliveryBundleGroup"))
    return {
        "fee_type": _clean(d.get("deliveryFeeType")),
        "base_fee": _int(d.get("baseFee")),
        "is_free": _clean(d.get("deliveryFeeType")) == "FREE" if d.get("deliveryFeeType") else None,
        "policy_text": _clean(d.get("deliveryFeePolicyText")),
        "method_types": _list(d.get("deliveryMethodTypes")) or None,
        "attribute": _clean(d.get("deliveryAttributeType")),
        "is_today_delivery": _bool(d.get("todayDelivery")),
        "company": _clean(company.get("name")),
        "extra_fee_area2": _int(d.get("area2ExtraFee") or bundle.get("area2ExtraFee")),
        "extra_fee_area3": _int(d.get("area3ExtraFee") or bundle.get("area3ExtraFee")),
    } if d else None


def _pricing(sp):
    bv = _dict(sp.get("benefitsView"))
    sale = _price(sp.get("salePrice")) or _price(sp.get("dispSalePrice"))
    discounted = _price(bv.get("discountedSalePrice")) or _price(bv.get("dispDiscountedSalePrice"))
    return {
        "sale_price": sale,
        "discounted_price": discounted or sale,
        "discount_ratio": _int(bv.get("discountedRatio")) or 0,
        "seller_discount": _int(bv.get("sellerImmediateDiscountAmount")) or 0,
        "manager_discount": _int(bv.get("managerImmediateDiscountAmount")) or 0,
        "currency": CURRENCY,
        "points": {
            "purchase": (_int(bv.get("sellerPurchasePoint")) or 0) + (_int(bv.get("managerPurchasePoint")) or 0)
            + (_int(bv.get("managerPurchaseExtraPoint")) or 0),
            "text_review": _int(bv.get("textReviewPoint")),
            "photo_video_review": _int(bv.get("photoVideoReviewPoint")),
            "after_use_text_review": _int(bv.get("afterUseTextReviewPoint")),
            "after_use_photo_video_review": _int(bv.get("afterUsePhotoVideoReviewPoint")),
            "store_member_review": _int(bv.get("storeMemberReviewPoint")),
        } if bv else None,
    }


def parse_simple_product(sp, slug=None, is_brand=False):
    """A store-backend simple product (simple-products, popular-products,
    best-products, a brand page's simpleProductForDetailPage) -> record."""
    sp = _dict(sp)
    channel = _dict(sp.get("channel"))
    product_id = _clean(str(sp.get("id") or "")) or None
    store_slug = slug or _clean(channel.get("url"))
    seo = _dict(sp.get("seoInfo"))
    search_info = _dict(sp.get("naverShoppingSearchInfo"))
    ep = _dict(sp.get("epInfo"))
    images = [u for u in [_clean(sp.get("representativeImageUrl"))] + [_clean(u) for u in _list(sp.get("optionalImageUrls"))] if u]
    reviews = _dict(sp.get("reviewAmount"))
    catalog_id = _clean(str(ep.get("syncNvMid") or "")) or None
    return {
        "id": product_id,
        "origin_product_id": _clean(str(sp.get("productNo") or "")) or None,
        "name": _clean(sp.get("name")) or _clean(sp.get("dispName")),
        "link": product_link(product_id, store_slug, brand=is_brand) if product_id and store_slug else None,
        "catalog_id": catalog_id,
        "catalog_link": catalog_link(catalog_id) if catalog_id else None,
        "status": _clean(sp.get("productStatusType")),
        "sale_type": _clean(sp.get("saleType")),
        "is_displayed": _clean(sp.get("channelProductDisplayStatusType")) == "ON" if sp.get("channelProductDisplayStatusType") else _bool(sp.get("displayable")),
        "pricing": _pricing(sp),
        "stock_quantity": _int(sp.get("stockQuantity")),
        "has_options": _bool(sp.get("optionUsable")),
        "has_supplements": _bool(sp.get("supplementProductUsable")),
        "images": images,
        "category": _category(sp.get("category")),
        "brand": _clean(search_info.get("brandName")),
        "brand_id": _clean(str(search_info.get("brandId") or "")) or None,
        "manufacturer": _clean(search_info.get("manufacturerName")),
        "model_name": _clean(search_info.get("modelName")),
        "tags": [_clean(t.get("text")) for t in _list(seo.get("sellerTags")) if _clean(_dict(t).get("text"))] or None,
        "page_title": _clean(seo.get("pageTitle")),
        "reviews": {
            "count": _int(reviews.get("totalReviewCount")),
            "average_score": _float(reviews.get("averageReviewScore")),
            "premium_count": _int(reviews.get("premiumReviewCount")),
        } if reviews else None,
        "delivery": _delivery(sp.get("productDeliveryInfo")),
        "is_free_delivery": _bool(sp.get("freeDelivery")),
        "is_today_delivery": _bool(sp.get("todayDelivery")),
        "has_arrival_guarantee": _bool(sp.get("arrivalGuarantee")),
        "has_regular_subscription": _bool(sp.get("regularSubscription")),
        "has_free_return_insurance": _bool(_dict(sp.get("claimDeliveryInfo")).get("freeReturnInsurance")),
        "is_minor_purchasable": _bool(sp.get("minorPurchasable")),
        "is_adult_restricted": _clean(sp.get("adultAuthorizationType")) not in (None, "NOT_LOGIN")
        if sp.get("adultAuthorizationType") else None,
        "is_in_naver_shopping": _bool(ep.get("naverShoppingExposure")),
        "editor_type": _clean(_dict(sp.get("detailContents")).get("editorType")),
        "store": store_summary(channel, store_slug) if channel else None,
    }


def parse_brand_product_page(page_html, slug):
    """brand.naver.com/<slug>/products/<id> -> {store, product} or None when
    the state carries no product (the page is a shell / unknown product)."""
    state = parse_state(page_html)
    sp = _dict(state.get("simpleProductForDetailPage"))
    channel = _dict(state.get("channel"))
    if not sp.get("id") or not channel.get("channelUid"):
        return None
    return {"store": parse_channel(channel, brand_slug=slug), "product": parse_simple_product(sp, slug, is_brand=True)}


def parse_validation(v):
    """validation-products -> options / variants / supplements / stock."""
    v = _dict(v)
    groups = [{"id": _clean(str(g.get("id") or "")) or None, "name": _clean(g.get("groupName")),
               "type": _clean(g.get("optionType"))} for g in _list(v.get("options")) if isinstance(g, dict)]
    variants = []
    for c in _list(v.get("optionCombinations")):
        if not isinstance(c, dict):
            continue
        names = [_clean(c.get(k)) for k in ("optionName1", "optionName2", "optionName3", "optionName4") if _clean(c.get(k))]
        variants.append({
            "id": _clean(str(c.get("id") or "")) or None,
            "name": " / ".join(names) if names else None,
            "options": names or None,
            "extra_price": _int(c.get("price")) or 0,
            "stock_quantity": _int(c.get("stockQuantity")),
            "is_today_dispatch": _bool(c.get("todayDispatch")),
            "registered_at": _date(c.get("registerDate")),
        })
    supplements = [{
        "id": _clean(str(s.get("id") or "")) or None, "group": _clean(s.get("groupName")), "name": _clean(s.get("name")),
        "price": _int(s.get("price")), "stock_quantity": _int(s.get("stockQuantity")), "status": _clean(s.get("productStatusType")),
    } for s in _list(v.get("supplementProducts")) if isinstance(s, dict)]
    return {
        "status": _clean(v.get("productStatusType")),
        "stock_quantity": _int(v.get("stockQuantity")),
        "uses_external_stock": _bool(v.get("useExternalStock")),
        "option_groups": groups,
        "variants": variants,
        "supplements": supplements,
        "delivery": _delivery(v.get("productDeliveryInfo")),
        "authentication_type": _clean(v.get("authenticationType")),
    }


def parse_contents(c):
    """The product description (contents/<origin>/PC)."""
    c = _dict(c)
    html_body = c.get("renderContent") or None
    text = _clean(c.get("textContent"))
    if not text and html_body:
        text = _clean(_TAG_RE.sub(" ", html_body))
        text = re.sub(r"\s+", " ", text) if text else None
    return {
        "html": html_body,
        "text": text,
        "editor_type": _clean(c.get("editorType")),
        "images": [u for u in (_clean(s.get("url") if isinstance(s, dict) else s) for s in _list(c.get("snapImages"))) if u] or None,
    }


def parse_notice(n):
    """The legal product-information notice -> label/value rows."""
    n = _dict(n)
    view = _dict(n.get("productInfoProvidedNoticeView"))

    def rows(section):
        return [{"label": _clean(k), "value": _clean(v)} for k, v in _dict(view.get(section)).items() if _clean(k)]
    return {
        "type": _clean(n.get("productInfoProvidedNoticeType")),
        "items": rows("basic"),
        "terms": rows("additional"),
    }


def parse_review_summary(s):
    s = _dict(s)
    info = _dict(s.get("productReviewInfo"))
    recent = _dict(s.get("recentProductReviewInfo"))
    evaluations = []
    for ev in _list(s.get("reviewEvaluations")):
        if not isinstance(ev, dict):
            continue
        evaluations.append({
            "question": _clean(ev.get("reviewEvaluationPhrase")) or _clean(ev.get("reviewEvaluationName")),
            "answers": [{"name": _clean(v.get("reviewEvaluationValueName")), "count": _int(v.get("count")),
                         "percent": _int(v.get("percent"))} for v in _list(ev.get("reviewEvaluationValues")) if isinstance(v, dict)],
        })
    representative = []
    for r in _list(s.get("representativeProductReviews")):
        if not isinstance(r, dict):
            continue
        attach = _dict(_dict(r.get("reviewAttach")).get("representAttach"))
        representative.append({
            "id": _clean(str(r.get("id") or "")) or None, "score": _int(r.get("reviewScore")),
            "text": _rich_text(r.get("contents")), "image": _clean(attach.get("attachPath")),
        })
    return {
        "count": _int(info.get("reviewCount")),
        "average_score": _float(info.get("averageReviewScore")),
        "score_counts": {str(n): _int(info.get(f"score{n}ReviewCount")) for n in range(1, 6)} if info else None,
        "text_count": _int(info.get("textReviewCount")),
        "photo_count": _int(info.get("photoReviewCount")),
        "video_count": _int(info.get("videoReviewCount")),
        "after_use_count": _int(info.get("afterUseReviewCount")),
        "best_count": _int(info.get("bestReviewCount")),
        "recent": {"count": _int(recent.get("recentReviewCount")),
                   "average_score": _float(recent.get("recentAverageReviewScore"))} if recent else None,
        "evaluations": evaluations or None,
        "representative_reviews": representative or None,
    }


def parse_review(r):
    r = _dict(r)
    attaches = [{"type": "video" if _clean(a.get("reviewAttachmentType")) == "V" else "image",
                 "link": _clean(a.get("attachUrl")) or _clean(a.get("attachPath")),
                 "width": _int(a.get("attachWidth")), "height": _int(a.get("attachHeight"))}
                for a in _list(r.get("reviewAttaches")) if isinstance(a, dict)]
    return {
        "id": _clean(str(r.get("id") or "")) or None,
        "score": _int(r.get("reviewScore")),
        "text": _rich_text(r.get("reviewContent")),
        "created_at": _datetime(r.get("createDate")),
        "type": _clean(r.get("reviewType")),
        "content_type": _clean(r.get("reviewContentClassType")),
        "option": _clean(r.get("productOptionContent")),
        "is_repurchase": _bool(r.get("repurchase")),
        "is_free_trial": _bool(r.get("freeTrial")),
        "event_title": _clean(r.get("eventTitle")),
        "writer": {"masked_id": _clean(r.get("maskedWriterId")) or _clean(r.get("writerId")),
                   "profile_image": _clean(r.get("writerProfileImageUrl"))},
        "attachments": attaches,
        "product": {"id": _clean(str(r.get("productNo") or "")) or None,
                    "origin_product_id": _clean(str(r.get("originProductNo") or "")) or None,
                    "name": _clean(r.get("productName"))},
        "likes": _int(r.get("helpCount")),
    }


def parse_reviews_page(page, page_size=20):
    page = _dict(page)
    reviews = [parse_review(r) for r in _list(page.get("contents"))]
    total = _int(page.get("totalElements"))
    return reviews, {
        "page": _int(page.get("page")) or 1,
        "items_per_page": _int(page.get("size")) or page_size,
        "total_pages": _int(page.get("totalPages")) if total is not None else None,
        "total_count": total,
    }


# ---- store product lists ----------------------------------------------------------------

def parse_store_products(payload, key=None, slug=None, is_brand=False):
    """popular-products ({products}) or best-products ({REALTIME,...}) -> list."""
    payload = _dict(payload)
    items = payload.get(key) if key else payload.get("products")
    return [parse_simple_product(p, slug, is_brand=is_brand) for p in _list(items) if isinstance(p, dict)]


# ---- catalogs -----------------------------------------------------------------------------

def parse_catalog_reviews(payload, catalog_id):
    """/v1/catalog-reviews -> the reviews listed under `catalog_id`."""
    rows = _list(_dict(payload).get(str(catalog_id)))
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        attaches = [{"type": "video" if _clean(a.get("reviewAttachmentType")) == "V" else "image",
                     "link": _clean(a.get("attachUrl")) or _clean(a.get("attachPath"))}
                    for a in _list(r.get("reviewAttaches")) if isinstance(a, dict)]
        out.append({
            "id": _clean(str(r.get("id") or "")) or None,
            "score": _int(r.get("reviewScore") or r.get("score")),
            "text": _rich_text(r.get("reviewContent") or r.get("contents") or r.get("content")),
            "created_at": _date(r.get("createDate")),
            "writer": _clean(r.get("writerMemberMaskedId") or r.get("maskedWriterId") or r.get("writerMemberId")),
            "mall_name": _clean(r.get("mallName")),
            "product_id": _clean(str(r.get("knowledgeShoppingMallProductId") or "")) or None,
            "catalog_product_id": _clean(str(r.get("productNo") or "")) or None,
            "option": _clean(r.get("productOptionContent")),
            "attachments": attaches,
        })
    return out


# ---- search cards ---------------------------------------------------------------------------

CARD_TYPES = {"CATALOG_CARD": "catalog", "ORGANIC_CARD": "product", "AD_CARD": "ad", "SUPER_POINT_CARD": "product"}


def _store_link_from_mall_url(mall_url):
    """The card's mallUrl is an outlink wrapper around the store home."""
    raw = _clean(_dict(mall_url).get("pcUrl"))
    if not raw:
        return None
    inner = parse_qs(urlparse(raw).query).get("url")
    target = unquote(inner[0]) if inner else raw
    parsed = urlparse(target)
    if parsed.hostname and "naver.com" in parsed.hostname and parsed.path.strip("/"):
        slug = parsed.path.strip("/").split("/")[0]
        return store_link(slug, brand="brand.naver.com" in parsed.hostname)
    return target


def parse_search_card(card):
    c = _dict(card)
    extra = _dict(c.get("shoppingExtraInfo"))
    nv_mid = _clean(str(c.get("nvMid") or "")) or None
    product_id = _clean(c.get("channelProductId"))
    product_url = _clean(_dict(c.get("productUrl")).get("pcUrl"))
    bridge = _clean(_dict(c.get("productClickUrl")).get("pcUrl"))
    kind = CARD_TYPES.get(c.get("cardType"), "product")
    is_catalog = kind == "catalog" or (_clean(c.get("mallId")) == "naver_model")
    delivery = _dict(c.get("productDeliveryInfo"))
    purchase_options = [{
        "id": _clean(str(o.get("id") or "")) or None, "name": _clean(o.get("name")),
        "lowest_price": _price(o.get("lowestPrice")),
    } for o in _list(_dict(extra.get("subInfo")).get("purchaseOptions")) if isinstance(o, dict)]
    return {
        "id": nv_mid,
        "product_id": product_id or None,
        "origin_product_id": _clean(c.get("originalMallProductId")) or None,
        "catalog_id": _clean(str(c.get("catalogMatchingId") or "")) or (nv_mid if is_catalog else None),
        "name": _text(c.get("productName")),
        "link": product_url or (catalog_link(nv_mid) if is_catalog and nv_mid else bridge),
        "type": "catalog" if is_catalog else kind,
        "is_ad": c.get("sourceType") == "AD",
        "rank": _int(c.get("rank")),
        "pricing": {
            "sale_price": _price(c.get("salePrice")),
            "discounted_price": _price(c.get("discountedSalePrice")) or _price(extra.get("discountedKRWSalePrice")),
            "discount_ratio": _int(c.get("discountedRatio")) or 0,
            "currency": _clean(c.get("priceCurrency")) or CURRENCY,
            "membership_point": _int(_dict(c.get("membershipSavingPoint")).get("point")) or None,
        },
        "images": [u for u in (_clean(_dict(i).get("imageUrl")) for i in _list(c.get("images"))) if u],
        "store": {
            "name": _clean(c.get("mallName")),
            "id": _clean(c.get("mallId")) if not is_catalog else None,
            "channel_id": _clean(c.get("channelNo")),
            "merchant_id": _clean(str(c.get("merchantNo") or "")) or None,
            "link": _store_link_from_mall_url(c.get("mallUrl")),
            "is_smart_store": _bool(c.get("isSmartStoreProduct")),
            "is_brand_store": _bool(c.get("isBrandStore")),
            "is_official": _clean(c.get("mallDescription")) == "공식" if c.get("mallDescription") else False,
            "is_individual_seller": _bool(c.get("isIndividualSeller")),
        } if not is_catalog else None,
        "mall_count": _int(c.get("mallCount") or extra.get("mallCount")) if is_catalog else None,
        "purchase_options": purchase_options or None,
        "reviews": {"count": _int(c.get("totalReviewCount")), "average_score": _float(c.get("averageReviewScore"))},
        "purchase_count": _int(c.get("purchaseCount")),
        "keep_count": _int(c.get("keepCount") or extra.get("keepCount")),
        "category": {
            "id": _clean(c.get("leafCategoryId")) or _clean(c.get("ssCatId")) or _clean(c.get("sCatId")),
            "path_ids": [i for i in (_clean(c.get(k)) for k in ("lCatId", "mCatId", "sCatId", "ssCatId")) if i] or None,
        },
        "delivery": {
            "fee": _int(delivery.get("deliveryFee")),
            "fee_types": _list(delivery.get("deliveryFeeTypes")) or None,
            "fast_delivery_type": _clean(c.get("fastDeliveryType")) if _clean(c.get("fastDeliveryType")) != "NONE" else None,
            "is_membership_free": _bool(c.get("isMembershipFreeDelivery")),
        },
        "promotion_types": _list(c.get("promotionTypes")) or None,
        "is_hot_deal": _bool(c.get("isHotDeal")),
        "is_new": _bool(c.get("isNewProduct")),
        "is_overseas": _bool(c.get("isOverseaProduct")),
        "is_adult_restricted": _bool(c.get("isAdultContentRestricted")),
        "has_membership_benefit": _bool(c.get("isMembershipBenefit")),
    }


def parse_search_slots(pages):
    """ns-portal slot pages -> flat card list (HORIZONTAL_LIST slots flattened)."""
    cards = []
    for page in _list(pages):
        for slot in _list(_dict(page).get("slots")):
            slot = _dict(slot)
            data = slot.get("data")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and (item.get("nvMid") or item.get("productName")):
                    cards.append(parse_search_card(item))
    return cards


# ---- DataLab --------------------------------------------------------------------------

def parse_datalab_categories(payload):
    """getCategory -> {category, children}."""
    payload = _dict(payload)

    def node(item):
        item = _dict(item)
        return {
            "id": _clean(str(item.get("cid") if item.get("cid") is not None else "")) or None,
            "name": _clean(item.get("name")),
            "parent_id": _clean(str(item.get("pid"))) if item.get("pid") is not None and int(item.get("pid")) >= 0 else None,
            "level": _int(item.get("level")),
            "path": _clean(item.get("fullPath")) or _clean(item.get("name")),
            "is_leaf": _bool(item.get("leaf")),
            "order": _int(item.get("expsOrder")),
        }
    return {"category": node(payload), "children": [node(c) for c in _list(payload.get("childList"))]}


def parse_datalab_rank(payload):
    payload = _dict(payload)
    return [{"rank": _int(r.get("rank")), "keyword": _clean(r.get("keyword"))}
            for r in _list(payload.get("ranks")) if isinstance(r, dict)]


def _datalab_range(payload):
    text = _clean(_dict(payload).get("range")) or ""
    parts = [p.strip(" .") for p in text.split("~")]
    return {"start_date": _date(parts[0]) if parts and parts[0] else None,
            "end_date": _date(parts[1]) if len(parts) > 1 and parts[1] else None}


def parse_datalab_series(payload):
    """A lineChart result -> [{date, value}] (relative click index, 100 = peak)."""
    result = _list(_dict(payload).get("result"))
    series = _dict(result[0]) if result else {}
    return [{"date": _date(d.get("period")), "value": _float(d.get("value"))}
            for d in _list(series.get("data")) if isinstance(d, dict)]


def parse_datalab_ratios(payload):
    """A donut / bar chart result -> [{code, label, ratio}] (100 = largest)."""
    result = _list(_dict(payload).get("result"))
    series = _dict(result[0]) if result else {}
    return [{"code": _clean(d.get("code")), "label": _clean(d.get("label")), "ratio": _float(d.get("ratio"))}
            for d in _list(series.get("data")) if isinstance(d, dict)]


def datalab_range(payload):
    return _datalab_range(payload)
