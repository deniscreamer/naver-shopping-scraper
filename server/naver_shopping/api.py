"""The /naver-shopping/* endpoint functions (route_glue's route_table calls
them with the schema's loaded kwargs).

Two cached bundles are shared across endpoints:

  * naver_shopping.store   the store record from the /<slug>/best page
                           (stores/details, stores/products, and every
                           smartstore product's details / reviews, which
                           need the store's channelUid + merchant id)
  * naver_shopping.product the product record: the store-backend answers
                           (summary, options, description, notice, review
                           summary) in one box round trip — products/details
                           slices it, products/reviews reads its ids
"""
from urllib.parse import quote

from cache import cached_call
from naver_shopping import cache_config as ttl
from naver_shopping import parsers, review_select
from naver_shopping.fetch import (NaverBadRequest, NaverNotFound, box_get, box_get_many, box_post, fetch_brand_product_page,
                                  fetch_datalab, fetch_search, fetch_search_count, fetch_store_page)
from naver_shopping.refs import catalog_link, split_product_link, split_store_link, store_link
from naver_shopping.schemas import DATALAB_DEVICES, DATALAB_GENDERS, DATALAB_PERIODS, REVIEW_MEDIA, REVIEW_SORTS

REVIEW_PAGE_SIZE = 20       # the backend's maximum: 50 / 100 answer 204, no pageSize gives 10 (probed 2026-11-01)
SELECT_MAX_PAGES = 25       # per filter pass of reviews/selected: 500 reviews
SEARCH_MAX_CARDS = 96        # the widget's TREND view: 4 pages x 24, no deeper paging exists
# ... and WHOLE pages only: 45 matches answer 24 cards, 67 answer 48, under 24
# answer all (probed 2026-11-01, 남성 골프채 풀세트 / 50002788, 0-19073 KRW:
# 24 of 45; its sub-slices 24 + 3 + 18 = 45). total_count is the real match
# count; scripts/harvest_listing.py slices by price until cards == total.


def _public(mapping, upstream):
    """The public name of an upstream token ({public: upstream} choice maps)."""
    return next((k for k, v in mapping.items() if v == upstream), upstream)


# ---- search -----------------------------------------------------------------------

# ns-portal ignores a price range with an open end ("|100000", "50000|") and
# answers the unfiltered results, so a missing bound is filled in (probed
# 2026-10-29: "0|100000" and "50000|9999999999" both filter).
OPEN_MAX_PRICE = 9_999_999_999


def _filters(data):
    lo, hi = data.get("min_price"), data.get("max_price")
    out = {}
    if lo is not None or hi is not None:
        out["price"] = f"{int(lo) if lo is not None else 0}|{int(hi) if hi is not None else OPEN_MAX_PRICE}"
    if data.get("category") and data["category"] != "0":      # 0 = the whole tree, no filter
        out["categoryIds"] = _category_filter(data["category"])
    if data.get("min_rating"):
        out["reviewScoreLowLimit"] = data["min_rating"]
    for param, key in (("free_delivery", "isFreeDelivery"), ("fast_delivery", "isFastDelivery"),
                       ("arrival_guarantee", "isArriveGuarantee"), ("brand_store", "isBrandStore"),
                       ("official_mall", "isOfficialOrCertified"), ("membership_benefit", "isMembershipBenefit")):
        if data.get(param):
            out[key] = True
    return out


def _category_filter(category):
    """ns-portal's categoryIds is the category's tree depth as two digits +
    its id, NOT a fixed "03" (probed 2026-11-01 on "남성 골프채 풀세트":
    0450002788 -> 28936, 0350002788 -> 0; 0350001102 -> 29695, 0250000029 ->
    30556, 0150000007 -> 30561; a bare id is refused). The depth is DataLab's
    `level`, cached with the category list; an unknown id is a 404."""
    level = categories_list(category)["level"]
    if not level:
        raise NaverNotFound(f"category {category} has no level")
    return f"{level:02d}{category}"


def _applied(data):
    return {k: v for k, v in data.items() if k != "query" and v is not None and v is not False}


def _search(**data):
    filters = _filters(data)
    cards = parsers.parse_search_slots(fetch_search(data["query"], filters))
    total = fetch_search_count(data["query"], filters)
    return {
        "query": data["query"],
        "filters": _applied(data) or None,
        "total_count": total,
        "count": len(cards),
        "results": cards,
    }


def products_search(**data):
    return cached_call("naver_shopping.search", data, _search, ttl.SEARCH_CACHE)


def _search_count(**data):
    return {"query": data["query"], "filters": _applied(data) or None,
            "total_count": fetch_search_count(data["query"], _filters(data))}


def products_count(**data):
    return cached_call("naver_shopping.search_count", data, _search_count, ttl.SEARCH_COUNT_CACHE)


# ---- stores -----------------------------------------------------------------------

def _store_record(store):
    ref = split_store_link(store)
    slug = ref["slug"]
    hosts = (True, False) if ref["is_brand"] else (False, True)
    last = None
    for is_brand in hosts:
        try:
            page = parsers.parse_store_page(fetch_store_page(slug, is_brand=is_brand))
        except NaverNotFound as e:
            last = e
            continue
        if page is not None:
            return page
        last = NaverNotFound(f"store {slug} not found")
    raise last


def _store(store):
    return cached_call("naver_shopping.store", {"store": store}, _store_record, ttl.STORE_CACHE)


def store_details(store):
    record = _store(store)
    return {**record["store"], "categories": record["categories"]}


def _store_products(**data):
    record = _store(data["store"])
    uid = record["store"]["uid"]
    slug = record["store"]["slug"]
    if data["list"] == "best":
        payload = box_get(f"/n/v2/channels/{uid}/best-products/products", f"store {uid} best")
        products = parsers.parse_store_products(payload, key=data["period"], slug=slug)
    else:
        payload = box_get(f"/n/v2/channels/{uid}/popular-products?count=20", f"store {uid} popular")
        products = parsers.parse_store_products(payload, slug=slug)
    return {
        "store": {k: record["store"][k] for k in ("id", "uid", "name", "slug", "link")},
        "list": data["list"],
        "period": data["period"].lower() if data["list"] == "best" else None,
        "count": len(products),
        "results": products,
    }


def store_products(**data):
    return cached_call("naver_shopping.store_products", data, _store_products, ttl.STORE_PRODUCTS_CACHE)


# ---- the product record -------------------------------------------------------------

def _find_store_for_product(product_id, name):
    """A slug-less product link (smartstore.naver.com/main/products/<id>):
    search the product's own name and take the card that carries its id."""
    if not name:
        return None
    for card in parsers.parse_search_slots(fetch_search(name)):
        if card.get("product_id") == str(product_id) and card.get("store") and card["store"].get("link"):
            return split_store_link(card["store"]["link"])
    return None


def _product_record(product):
    ref = split_product_link(product)
    product_id, slug = ref["id"], ref["slug"]
    if ref["is_brand"]:
        page = parsers.parse_brand_product_page(fetch_brand_product_page(slug, product_id), slug)
        if page is None:
            raise NaverNotFound(f"product {product_id} not found")
        store, base = page["store"], page["product"]
    else:
        if not slug:
            validation = box_get(f"/n/v1/validation-products/{product_id}", f"product {product_id} validation")
            if not validation:
                raise NaverNotFound(f"product {product_id} not found")
            found = _find_store_for_product(product_id, parsers._clean(validation.get("name")))
            if not found:
                raise NaverNotFound(f"product {product_id}: its store could not be resolved from the search index; "
                                    "pass the store product link (https://smartstore.naver.com/<store>/products/<id>)")
            slug = found["slug"]
            store = _store(store_link(slug, brand=found["is_brand"]))["store"]
        else:
            store = _store(store_link(slug))["store"]
        summary = box_get(f"/n/v2/channels/{store['uid']}/simple-products?ids[]={product_id}",
                          f"product {product_id} summary")
        if not summary:
            raise NaverNotFound(f"product {product_id} not found in store {slug}")
        base = parsers.parse_simple_product(summary[0], slug)
    origin = base["origin_product_id"]
    uid, merchant = store["uid"], store["merchant_id"]
    leaf = (base.get("category") or {}).get("id") or ""
    validation, contents, notice, summary = box_get_many([
        f"/n/v1/validation-products/{product_id}",
        f"/n/v2/channels/{uid}/products/{product_id}/contents/{origin}/PC?isResponsive=true",
        f"/n/v2/channels/{uid}/products/{origin}/provided-notice",
        f"/n/v1/contents/reviews/product-summary/{origin}?leafCategoryId={quote(leaf)}&checkoutMerchantNo={merchant}",
    ], f"product {product_id}")
    return {
        "base": base,
        "store": store,
        "validation": parsers.parse_validation(validation) if validation else None,
        "contents": parsers.parse_contents(contents) if contents else None,
        "notice": parsers.parse_notice(notice) if notice else None,
        "review_summary": parsers.parse_review_summary(summary) if summary else None,
    }


def _record(product):
    return cached_call("naver_shopping.product", {"product": product}, _product_record, ttl.PRODUCT_CACHE)


# ---- products/details -----------------------------------------------------------------

def product_details(product):
    record = _record(product)
    base, validation = dict(record["base"]), record["validation"] or {}
    store = record["store"]
    reviews = record["review_summary"] or base.get("reviews")
    base.pop("store", None)
    base.pop("editor_type", None)
    return {
        **base,
        "stock_quantity": validation.get("stock_quantity", base.get("stock_quantity")),
        "status": validation.get("status") or base.get("status"),
        "option_groups": validation.get("option_groups"),
        "variants": validation.get("variants"),
        "supplements": validation.get("supplements"),
        "description": record["contents"],
        "notice": record["notice"],
        "facts": parsers.product_facts(base, record["notice"]),
        "reviews": reviews,
        "store": {k: store.get(k) for k in ("id", "uid", "name", "slug", "link", "type", "grade", "sale_count",
                                             "merchant_id", "business")},
    }


# ---- products/reviews -----------------------------------------------------------------

def _reviews(**data):
    record = _record(data["product"])
    base, store = record["base"], record["store"]
    body = {
        "checkoutMerchantNo": int(store["merchant_id"]), "originProductNo": int(base["origin_product_id"]),
        "page": data["page"], "pageSize": REVIEW_PAGE_SIZE,
        "reviewSearchSortType": data["sort"],
    }
    # reviewContentClassTypes filters by media (the page's 포토/동영상 filter
    # sends it; probed 2026-11-01: PHOTO,VIDEO 91 of 202, TEXT 111); other
    # keys tried (reviewContentClassType, reviewSearchType) are ignored
    media = data.get("media") or "ALL"
    if media != "ALL":
        body["reviewContentClassTypes"] = media.split(",")
    payload = box_post("/n/v1/contents/reviews/query-pages", body, f"product {base['id']} reviews page {data['page']}")
    reviews, pagination = parsers.parse_reviews_page(payload or {}, REVIEW_PAGE_SIZE)
    pagination["page"] = data["page"]
    pagination["items_per_page"] = REVIEW_PAGE_SIZE
    if payload is None:          # past the end: the backend answers 204
        pagination.update({"total_pages": None, "total_count": None, "has_next": False})
    return {
        "product": {"id": base["id"], "name": base["name"], "link": base["link"]},
        "sort": _public(REVIEW_SORTS, data["sort"]),
        "media": _public(REVIEW_MEDIA, media),
        "summary": record["review_summary"],
        "results": reviews,
        "pagination": pagination,
    }


def product_reviews(**data):
    return cached_call("naver_shopping.reviews", data, _reviews, ttl.REVIEWS_CACHE)


# ---- products/reviews/selected ----------------------------------------------------------

def _review_pass(product, media, enough):
    """Newest-first pages of one media filter until enough(reviews), the last page or SELECT_MAX_PAGES."""
    reviews, pages, total, exhausted = [], 0, None, False
    for page in range(1, SELECT_MAX_PAGES + 1):
        answer = product_reviews(product=product, page=page, sort=REVIEW_SORTS["recent"], media=REVIEW_MEDIA[media])
        pagination = answer["pagination"]
        pages, total = page, pagination.get("total_count")
        reviews.extend(answer["results"])
        total_pages = pagination.get("total_pages")       # None when the backend leaves out totalElements
        if len(answer["results"]) < REVIEW_PAGE_SIZE or (total_pages is not None and page >= total_pages):
            exhausted = True
            break
        if enough(reviews):
            break
    return {"media": media, "pages": pages, "total_count": total, "is_exhausted": exhausted}, reviews


def product_reviews_selected(product, count):
    """Up to `count` reviews worth showing (review_select): photo + long text +
    a real avatar first, then photo + text, then long text; every review with
    text when the product has 20 or fewer. Reads the photo/video filter first,
    then text-only reviews, newest first, only as far as needed (cached pages)."""
    record = _record(product)
    base = record["base"]
    # no review summary for a product without reviews (2026-11-01, GV Tour set 7583123963): the base count says 0
    total = (record["review_summary"] or base.get("reviews") or {}).get("count")
    origin = base["origin_product_id"]
    passes, seen = [], []

    def chosen(extra=()):
        return review_select.select(seen + list(extra), origin, total, count)[0]

    if total is not None and total <= review_select.SMALL_SOURCE:
        plan = [("all", lambda rs: False)]
    else:
        plan = [("photo_video", lambda rs: review_select.primary_count(rs, origin) >= count),
                ("text", lambda rs: len(chosen(rs)) >= count)]
    for media, enough in plan:
        if passes and len(chosen()) >= count:
            break
        if total != 0:
            info, reviews = _review_pass(product, media, enough)
            passes.append(info)
            seen.extend(reviews)
    results, mode = review_select.select(seen, origin, total, count)
    return {
        "product": {"id": base["id"], "name": base["name"], "link": base["link"]},
        "summary": record["review_summary"],
        "mode": mode,
        "count": len(results),
        "scanned": len({r["id"] for r in seen}),
        "passes": passes,
        "is_complete": len(results) >= count or all(p["is_exhausted"] for p in passes),
        "results": results,
    }


# ---- catalogs/reviews -------------------------------------------------------------------

def _catalog_reviews(catalog):
    payload = box_get(f"/n/v1/catalog-reviews?ids[]={catalog}", f"catalog {catalog} reviews")
    reviews = parsers.parse_catalog_reviews(payload or {}, catalog)
    if not reviews and not (payload or {}).get(str(catalog)):
        raise NaverNotFound(f"catalog {catalog} has no reviews or does not exist")
    return {"catalog_id": catalog, "link": catalog_link(catalog), "count": len(reviews), "results": reviews}


def catalog_reviews(catalog):
    return cached_call("naver_shopping.catalog_reviews", {"catalog": catalog}, _catalog_reviews,
                       ttl.CATALOG_REVIEWS_CACHE)


# ---- DataLab ------------------------------------------------------------------------------

def _window_form(data):
    return {
        "cid": data["category"], "timeUnit": data["period"],
        "startDate": data["start_date"], "endDate": data["end_date"],
        "device": data.get("device") or "", "gender": data.get("gender") or "",
        "age": ",".join(data["age"]) if data.get("age") else "",
    }


def _window_echo(data):
    return {
        "category_id": data["category"], "start_date": data["start_date"], "end_date": data["end_date"],
        "period": _public(DATALAB_PERIODS, data["period"]),
        "device": _public(DATALAB_DEVICES, data["device"]) if data.get("device") else None,
        "gender": _public(DATALAB_GENDERS, data["gender"]) if data.get("gender") else None,
        "age": data.get("age"),
    }


def _known_category(category):
    """The DataLab record of a category id (cached a week); an unknown id is
    a 404 here rather than the empty series DataLab answers it with."""
    try:
        return categories_list(category)
    except NaverBadRequest:
        raise NaverNotFound(f"category {category} not found")


def _keywords_rank(**data):
    category = _known_category(data["category"])
    payload = fetch_datalab("getCategoryKeywordRank", {**_window_form(data), "page": data["page"], "count": 20})
    keywords = parsers.parse_datalab_rank(payload)
    return {
        **_window_echo(data),
        "category_name": category["name"],
        "results": keywords,
        "pagination": {"page": data["page"], "items_per_page": 20, "has_next": len(keywords) == 20 and data["page"] < 25,
                       "total_pages": None, "total_count": None},
    }


def keywords_rank(**data):
    return cached_call("naver_shopping.keywords_rank", data, _keywords_rank, ttl.DATALAB_CACHE)


def _keywords_trend(**data):
    category = _known_category(data["category"])
    payload = fetch_datalab("getKeywordClickTrend", {**_window_form(data), "keyword": data["keyword"]})
    return {"keyword": data["keyword"], **_window_echo(data), "category_name": category["name"],
            "series": parsers.parse_datalab_series(payload)}


def keywords_trend(**data):
    return cached_call("naver_shopping.keywords_trend", data, _keywords_trend, ttl.DATALAB_CACHE)


def _categories_trend(**data):
    category = _known_category(data["category"])
    form = _window_form(data)
    clicks = fetch_datalab("getCategoryClickTrend", form)
    device = fetch_datalab("getCategoryDeviceRate", form)
    gender = fetch_datalab("getCategoryGenderRate", form)
    age = fetch_datalab("getCategoryAgeRate", form)
    return {
        **_window_echo(data),
        "category_name": category["name"],
        "category_path": category["path"],
        "series": parsers.parse_datalab_series(clicks),
        "device_share": parsers.parse_datalab_ratios(device),
        "gender_share": parsers.parse_datalab_ratios(gender),
        "age_share": parsers.parse_datalab_ratios(age),
    }


def categories_trend(**data):
    return cached_call("naver_shopping.categories_trend", data, _categories_trend, ttl.DATALAB_CACHE)


def _categories_list(category):
    try:
        payload = fetch_datalab("getCategory", {"cid": category})
    except NaverBadRequest:          # DataLab 500s an unknown id
        raise NaverNotFound(f"category {category} not found")
    if not isinstance(payload, dict) or payload.get("cid") is None:
        raise NaverNotFound(f"category {category} not found")
    parsed = parsers.parse_datalab_categories(payload)
    return {**parsed["category"], "count": len(parsed["children"]), "children": parsed["children"]}


def categories_list(category):
    return cached_call("naver_shopping.categories", {"category": category}, _categories_list, ttl.CATEGORIES_CACHE)
