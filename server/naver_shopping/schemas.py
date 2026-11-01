"""Marshmallow request schemas for every /naver-shopping/* route.

ONE param per input (never a sibling `url` / `id` pair):

    product    a channel product number (10352481064) OR a smartstore.naver.com /
               brand.naver.com product link
    store      a store slug (bauato) OR a store link
    catalog    a price-comparison id (nvMid, 61626354397) OR a
               search.shopping.naver.com/catalog/<id> link
    category   a Naver shopping category id (8 digits, 50000003); the same
               ids drive the search filter and DataLab

Search filters mirror the shopping widget's own (ns-portal params, verified
2026-10-24): price band, category, delivery / store-type booleans, review
floor. DataLab windows default to the last 30 days ending yesterday (the
site publishes nothing for today).
"""
from datetime import date, timedelta

from marshmallow import ValidationError, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CommaListField, DateField, Flag, PageField, Price,
                           QueryField, RefField)
from naver_shopping import refs

# The review backend's reviewSearchSortType values (the four sorts the store
# page offers). REVIEW_CREATE_DATE_ASC, REVIEW_ATTACH_RANKING and HELP_CNT
# answer an empty page (probed 2026-10-29), so oldest / photos / helpful are
# not offered.
REVIEW_SORTS = {
    "ranking": "REVIEW_RANKING", "recent": "REVIEW_CREATE_DATE_DESC",
    "score_high": "REVIEW_SCORE_DESC", "score_low": "REVIEW_SCORE_ASC",
}
BEST_PERIODS = {"realtime": "REALTIME", "daily": "DAILY", "weekly": "WEEKLY", "monthly": "MONTHLY"}
DATALAB_PERIODS = {"daily": "date", "weekly": "week", "monthly": "month"}
DATALAB_DEVICES = {"pc": "pc", "mobile": "mo"}
DATALAB_GENDERS = {"male": "m", "female": "f"}
DATALAB_AGES = ("10", "20", "30", "40", "50", "60")
DATALAB_FIRST_DAY = "2017-08-01"     # the site's own lower bound
MAX_REVIEW_PAGE = 500                # 20 reviews a page; the busiest products hold ~10k
MAX_RANK_PAGE = 25                   # 500 keywords at 20 a page is the site's own depth


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class StoreRefField(RefField):
    resolver = staticmethod(refs.resolve_store)


class CatalogRefField(RefField):
    resolver = staticmethod(refs.resolve_catalog)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


# ---- products -----------------------------------------------------------------------

class ProductsSearchSchema(BaseSchema):
    query = QueryField(metadata={"description": "search keywords (Korean or English, as on shopping.naver.com)"})
    min_price = Price(metadata={"description": "lowest price to include, in KRW"})
    max_price = Price(metadata={"description": "highest price to include, in KRW"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "restrict to a Naver shopping category id (8 digits, e.g. 50001519 자급제폰)"})
    min_rating = ChoiceField(["4.8"], metadata={"description": "only products rated at least this (the site offers 4.8)"})
    free_delivery = Flag(metadata={"description": "true: free delivery only"})
    fast_delivery = Flag(metadata={"description": "true: fast (today / arrival-guaranteed) delivery only"})
    arrival_guarantee = Flag(metadata={"description": "true: Naver arrival-guarantee delivery only"})
    brand_store = Flag(metadata={"description": "true: products sold by official brand stores only"})
    official_mall = Flag(metadata={"description": "true: official / certified malls only"})
    membership_benefit = Flag(metadata={"description": "true: products with a Naver Plus membership benefit only"})

    @validates_schema
    def _price_band(self, data, **kwargs):
        lo, hi = data.get("min_price"), data.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("min_price must not exceed max_price.", "min_price")


class ProductSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "channel product number, or a smartstore.naver.com / brand.naver.com product link"})


class ProductReviewsSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "channel product number, or a smartstore.naver.com / brand.naver.com product link"})
    page = PageField(max_page=MAX_REVIEW_PAGE, metadata={"description": "1-based page of 20 reviews"})
    sort = ChoiceField(REVIEW_SORTS, load_default="REVIEW_RANKING", metadata={
        "description": "ranking (the store's default), recent, score_high, score_low"})


# ---- stores ------------------------------------------------------------------------

class StoreSchema(BaseSchema):
    store = StoreRefField(metadata={"description": "store slug (bauato) or a smartstore.naver.com / brand.naver.com store link"})


class StoreProductsSchema(BaseSchema):
    store = StoreRefField(metadata={"description": "store slug (bauato) or a smartstore.naver.com / brand.naver.com store link"})
    list = ChoiceField(["popular", "best"], load_default="popular", metadata={
        "description": "popular (the store's popular-products rail, 20) or best (its best-seller ranking, 30 per period)"})
    period = ChoiceField(BEST_PERIODS, load_default="DAILY", metadata={
        "description": "best list period: realtime, daily, weekly or monthly (ignored for popular)"})


# ---- catalogs ----------------------------------------------------------------------

class CatalogSchema(BaseSchema):
    catalog = CatalogRefField(metadata={"description": "price-comparison catalog id (nvMid) or its search.shopping.naver.com/catalog/<id> link"})


# ---- DataLab -----------------------------------------------------------------------

def _yesterday():
    return (date.today() - timedelta(days=1)).isoformat()


def _month_ago():
    return (date.today() - timedelta(days=31)).isoformat()


class _DatalabWindow(BaseSchema):
    start_date = DateField(bound="past", load_default=_month_ago, metadata={
        "description": "first day of the window, YYYY-MM-DD (default: 31 days ago; the site starts 2017-08-01)"})
    end_date = DateField(bound="past", load_default=_yesterday, metadata={
        "description": "last day of the window, YYYY-MM-DD (default: yesterday)"})
    period = ChoiceField(DATALAB_PERIODS, load_default="date", metadata={
        "description": "aggregation: daily (default), weekly or monthly"})
    device = ChoiceField(DATALAB_DEVICES, metadata={"description": "pc or mobile (default: both)"})
    gender = ChoiceField(DATALAB_GENDERS, metadata={"description": "male or female (default: both)"})
    age = CommaListField(allowed=DATALAB_AGES, metadata={
        "description": "age bands, comma-separated: 10, 20, 30, 40, 50, 60 (default: all)"})

    @validates_schema
    def _window(self, data, **kwargs):
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and start > end:
            raise ValidationError("start_date must not be after end_date.", "start_date")
        if start and start < DATALAB_FIRST_DAY:
            raise ValidationError(f"DataLab starts on {DATALAB_FIRST_DAY}.", "start_date")


def _not_root(category):
    """DataLab ranks and charts per category: the root (0) is not served."""
    if category == "0":
        raise ValidationError("DataLab needs a category: pass one of the ids from /naver-shopping/categories/list "
                              "(e.g. 50000003 디지털/가전), not 0.", "category")


class KeywordsRankSchema(_DatalabWindow):
    category = CategoryRefField(metadata={"description": "Naver shopping category id (8 digits, e.g. 50000003 디지털/가전)"})

    @validates_schema
    def _needs_category(self, data, **kwargs):
        _not_root(data.get("category"))
    page = PageField(max_page=MAX_RANK_PAGE, metadata={"description": "1-based page of 20 keywords (25 pages = top 500)"})


class KeywordsTrendSchema(_DatalabWindow):
    keyword = QueryField(max_length=100, metadata={"description": "the shopping keyword to chart"})
    category = CategoryRefField(metadata={"description": "the category the keyword is charted in (8 digits, e.g. 50000003)"})

    @validates_schema
    def _needs_category(self, data, **kwargs):
        _not_root(data.get("category"))


class CategoriesTrendSchema(_DatalabWindow):
    category = CategoryRefField(metadata={"description": "Naver shopping category id (8 digits, e.g. 50000003)"})

    @validates_schema
    def _needs_category(self, data, **kwargs):
        _not_root(data.get("category"))


class CategoriesListSchema(BaseSchema):
    category = CategoryRefField(required=False, load_default="0", metadata={
        "description": "parent category id; 0 or omitted lists the top-level categories"})
