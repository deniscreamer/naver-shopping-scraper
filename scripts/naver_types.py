"""Types of the API's JSON answers, for scripts (and IDEs / type checkers).

TypedDicts only, no runtime code: the server sends plain JSON, these name its
shape. Written from real answers captured live 2026-11-01 (fixtures/*.json)
and the server's parser code (server/naver_shopping/parsers.py, api.py,
composite.py, routes.paginate, listing_jobs.py); test_naver_types.py checks
every fixture against them, strictly (missing / unknown keys fail).

`X | None` where the server may send null; NotRequired where it may omit the
key. Contract in words: server/docs/ENDPOINTS.md. When a response changes,
refresh its fixture (scripts/README.md) and the type in the same commit.
"""
from typing import Literal, NotRequired, TypedDict


# ==== products: search, count, details, reviews ======================================

# ---- shared ----------------------------------------------------------------------------

ReviewSort = Literal["ranking", "recent", "score_high", "score_low"]   # schemas.REVIEW_SORTS public names
StoreType = Literal["smart_store", "brand_store"]                      # parsers.parse_channel "type"
CardType = Literal["catalog", "product", "ad"]                          # parsers.parse_search_card "type"
AttachmentType = Literal["image", "video"]                              # parsers.parse_review attachments[].type


class ReviewStats(TypedDict):
    """Search card `reviews`: count and average score."""
    count: int | None
    average_score: float | None


class SimpleReviewStats(ReviewStats):
    """Product details `reviews` fallback (simple-product reviewAmount) when no review summary came back."""
    premium_count: int | None


# ---- /products/search and /products/count ----------------------------------------------

class SearchFilters(TypedDict):
    """products/search + products/count `filters`: only the params the caller set (False flags dropped)."""
    min_price: NotRequired[float]
    max_price: NotRequired[float]
    category: NotRequired[str]
    min_rating: NotRequired[Literal["4.8"]]
    free_delivery: NotRequired[Literal[True]]
    fast_delivery: NotRequired[Literal[True]]
    arrival_guarantee: NotRequired[Literal[True]]
    brand_store: NotRequired[Literal[True]]
    official_mall: NotRequired[Literal[True]]
    membership_benefit: NotRequired[Literal[True]]


class SearchPricing(TypedDict):
    """products/search results[].pricing."""
    sale_price: int | None
    discounted_price: int | None
    discount_ratio: int
    currency: str
    membership_point: int | None


class SearchStore(TypedDict):
    """products/search results[].store (null on catalog cards)."""
    name: str | None
    id: str | None
    channel_id: str | None
    merchant_id: str | None
    link: str | None
    is_smart_store: bool | None
    is_brand_store: bool | None
    is_official: bool
    is_individual_seller: bool | None


class PurchaseOption(TypedDict):
    """products/search results[].purchase_options[] (catalog sub-options)."""
    id: str | None
    name: str | None
    lowest_price: int | None


class SearchCategory(TypedDict):
    """products/search results[].category: leaf id + l/m/s/ss ids."""
    id: str | None
    path_ids: list[str] | None


class SearchDelivery(TypedDict):
    """products/search results[].delivery."""
    fee: int | None
    fee_types: list[str] | None
    fast_delivery_type: str | None
    is_membership_free: bool | None


class SearchCard(TypedDict):
    """products/search results[]: one search card (product, ad or catalog)."""
    id: str | None
    product_id: str | None
    origin_product_id: str | None
    catalog_id: str | None
    name: str | None
    link: str | None
    type: CardType
    is_ad: bool
    rank: int | None
    pricing: SearchPricing
    images: list[str]
    store: SearchStore | None
    mall_count: int | None
    purchase_options: list[PurchaseOption] | None
    reviews: ReviewStats
    purchase_count: int | None
    keep_count: int | None
    category: SearchCategory
    delivery: SearchDelivery
    promotion_types: list[str] | None
    is_hot_deal: bool | None
    is_new: bool | None
    is_overseas: bool | None
    is_adult_restricted: bool | None
    has_membership_benefit: bool | None


class CountResult(TypedDict):
    """products/count response."""
    query: str
    filters: SearchFilters | None
    total_count: int | None


class SearchResult(CountResult):
    """products/search response (count = cards returned, at most 96)."""
    count: int
    results: list[SearchCard]


# ---- /products/details -----------------------------------------------------------------

class Points(TypedDict):
    """products/details pricing.points."""
    purchase: int
    text_review: int | None
    photo_video_review: int | None
    after_use_text_review: int | None
    after_use_photo_video_review: int | None
    store_member_review: int | None


class Pricing(TypedDict):
    """products/details pricing (also stores/products results[].pricing)."""
    sale_price: int | None
    discounted_price: int | None
    discount_ratio: int
    seller_discount: int
    manager_discount: int
    currency: str
    points: Points | None


class ProductCategory(TypedDict):
    """products/details category (names and ids root -> leaf)."""
    id: str | None
    name: str | None
    path: list[str] | None
    path_ids: list[str] | None


class Delivery(TypedDict):
    """products/details delivery."""
    fee_type: str | None
    base_fee: int | None
    is_free: bool | None
    policy_text: str | None
    method_types: list[str] | None
    attribute: str | None
    is_today_delivery: bool | None
    company: str | None
    extra_fee_area2: int | None
    extra_fee_area3: int | None


class OptionGroup(TypedDict):
    """products/details option_groups[]."""
    id: str | None
    name: str | None
    type: str | None


class Variant(TypedDict):
    """products/details variants[]: one option combination."""
    id: str | None
    name: str | None
    options: list[str] | None
    extra_price: int
    stock_quantity: int | None
    is_today_dispatch: bool | None
    registered_at: str | None


class Supplement(TypedDict):
    """products/details supplements[]: an add-on product."""
    id: str | None
    group: str | None
    name: str | None
    price: int | None
    stock_quantity: int | None
    status: str | None


class Description(TypedDict):
    """products/details description (the product page body)."""
    html: str | None
    text: str | None
    editor_type: str | None
    images: list[str] | None


class NoticeRow(TypedDict):
    """products/details notice.items[] / notice.terms[]."""
    label: str
    value: str | None


class Notice(TypedDict):
    """products/details notice: the legal product-information notice."""
    type: str | None
    items: list[NoticeRow]
    terms: list[NoticeRow]


# score_counts keys are "1".."5", so the functional form is required.
ScoreCounts = TypedDict("ScoreCounts", {
    "1": int | None, "2": int | None, "3": int | None, "4": int | None, "5": int | None,
})
"""products/details reviews.score_counts / products/reviews summary.score_counts."""


class RecentReviews(TypedDict):
    """ReviewSummary.recent."""
    count: int | None
    average_score: float | None


class EvaluationAnswer(TypedDict):
    """ReviewSummary.evaluations[].answers[]."""
    name: str | None
    count: int | None
    percent: int | None


class Evaluation(TypedDict):
    """ReviewSummary.evaluations[]: one review survey question."""
    question: str | None
    answers: list[EvaluationAnswer]


class RepresentativeReview(TypedDict):
    """ReviewSummary.representative_reviews[]."""
    id: str | None
    score: int | None
    text: str | None
    image: str | None


class ReviewSummary(TypedDict):
    """products/details reviews and products/reviews summary."""
    count: int | None
    average_score: float | None
    score_counts: ScoreCounts | None
    text_count: int | None
    photo_count: int | None
    video_count: int | None
    after_use_count: int | None
    best_count: int | None
    recent: RecentReviews | None
    evaluations: list[Evaluation] | None
    representative_reviews: list[RepresentativeReview] | None


class Business(TypedDict):
    """products/details store.business (also stores/details business); masked values are null."""
    legal_name: str | None
    representative: str | None
    type: str | None
    is_business: bool | None
    is_overseas: bool | None
    phone: str | None
    email: str | None
    address: str | None


class StoreDetailsInProduct(TypedDict):
    """products/details store."""
    id: str | None
    uid: str | None
    name: str | None
    slug: str | None
    link: str | None
    type: StoreType
    grade: str | None
    sale_count: int | None
    merchant_id: str | None
    business: Business


class ProductDetails(TypedDict):
    """products/details response."""
    id: str | None
    origin_product_id: str | None
    name: str | None
    link: str | None
    catalog_id: str | None
    catalog_link: str | None
    status: str | None
    sale_type: str | None
    is_displayed: bool | None
    pricing: Pricing
    stock_quantity: int | None
    has_options: bool | None
    has_supplements: bool | None
    images: list[str]
    category: ProductCategory
    brand: str | None
    brand_id: str | None
    manufacturer: str | None
    model_name: str | None
    tags: list[str] | None
    page_title: str | None
    reviews: ReviewSummary | SimpleReviewStats | None
    delivery: Delivery | None
    is_free_delivery: bool | None
    is_today_delivery: bool | None
    has_arrival_guarantee: bool | None
    has_regular_subscription: bool | None
    has_free_return_insurance: bool | None
    is_minor_purchasable: bool | None
    is_adult_restricted: bool | None
    is_in_naver_shopping: bool | None
    option_groups: list[OptionGroup] | None
    variants: list[Variant] | None
    supplements: list[Supplement] | None
    description: Description | None
    notice: Notice | None
    store: StoreDetailsInProduct


# ---- /products/reviews -----------------------------------------------------------------

class ReviewWriter(TypedDict):
    """products/reviews results[].writer."""
    masked_id: str | None
    profile_image: str | None


class ReviewAttachment(TypedDict):
    """products/reviews results[].attachments[]."""
    type: AttachmentType
    link: str | None
    width: int | None
    height: int | None


class ReviewProduct(TypedDict):
    """products/reviews results[].product: the reviewed product / option."""
    id: str | None
    origin_product_id: str | None
    name: str | None


class Review(TypedDict):
    """products/reviews results[]."""
    id: str | None
    score: int | None
    text: str | None
    created_at: str | None
    type: str | None
    content_type: str | None
    option: str | None
    is_repurchase: bool | None
    is_free_trial: bool | None
    event_title: str | None
    writer: ReviewWriter
    attachments: list[ReviewAttachment]
    product: ReviewProduct
    likes: int | None


class ProductRef(TypedDict):
    """products/reviews product."""
    id: str | None
    name: str | None
    link: str | None


class ReviewsPage(TypedDict):
    """products/reviews response (pagination flattened by routes.paginate)."""
    count: int | None
    per_page: int
    current_page: int
    total_pages: int | None
    next: str | None
    previous: str | None
    product: ProductRef
    sort: ReviewSort
    summary: ReviewSummary | None
    results: list[Review]


# ==== stores and catalogs =================================================================

StoreProductsList = Literal["popular", "best"]
StoreBestPeriod = Literal["realtime", "daily", "weekly", "monthly"]
CatalogAttachmentType = Literal["image", "video"]


# ---- /stores/details ----------------------------------------------------------------

class StoreBusiness(TypedDict):
    """/stores/details .business: seller's legal info (masked values -> None)."""
    legal_name: str | None
    representative: str | None
    type: str | None
    is_business: bool | None
    is_overseas: bool | None
    phone: str | None
    email: str | None
    address: str | None


class StoreCategory(TypedDict):
    """/stores/details .categories[]: a node of the store's own category menu (recursive)."""
    id: str | None
    name: str | None
    level: int | None
    type: str | None
    is_all_products: bool | None
    sort_type: str | None
    children: list["StoreCategory"]


class StoreDetails(TypedDict):
    """/stores/details response: the store record plus its category tree."""
    id: str | None
    uid: str | None
    name: str | None
    slug: str | None
    link: str | None
    type: StoreType
    description: str | None
    image: str | None
    grade: str | None
    sale_count: int | None
    open_duration: str | None
    merchant_id: str | None
    account_id: str | None
    mall_seq: int | None
    brand_ids: list[str] | None
    business: StoreBusiness
    talk_id: str | None
    social: dict[str, list[str]] | None  # lowercased network ("instagram", "naverblog", ...) -> handles
    product_auth_categories: list[str] | None
    has_arrival_guarantee: bool | None
    has_free_return_insurance: bool | None
    has_regular_subscription: bool | None
    has_lounge: bool | None
    is_exhibiting: bool | None
    categories: list[StoreCategory]


# ---- /stores/products ---------------------------------------------------------------

class StoreRef(TypedDict):
    """/stores/products .store and .results[].store: the short store summary."""
    id: str | None
    uid: str | None
    name: str | None
    slug: str | None
    link: str | None


class StorePoints(TypedDict):
    """/stores/products .results[].pricing.points: Naver Pay points per action."""
    purchase: int
    text_review: int | None
    photo_video_review: int | None
    after_use_text_review: int | None
    after_use_photo_video_review: int | None
    store_member_review: int | None


class StorePricing(TypedDict):
    """/stores/products .results[].pricing: KRW prices and discounts."""
    sale_price: int | None
    discounted_price: int | None
    discount_ratio: int
    seller_discount: int
    manager_discount: int
    currency: Literal["KRW"]
    points: StorePoints | None


class StoreProductCategory(TypedDict):
    """/stores/products .results[].category: leaf category with its full path."""
    id: str | None
    name: str | None
    path: list[str] | None
    path_ids: list[str] | None


class StoreDelivery(TypedDict):
    """/stores/products .results[].delivery: shipping terms."""
    fee_type: str | None
    base_fee: int | None
    is_free: bool | None
    policy_text: str | None
    method_types: list[str] | None
    attribute: str | None
    is_today_delivery: bool | None
    company: str | None
    extra_fee_area2: int | None
    extra_fee_area3: int | None


class StoreProductReviews(TypedDict):
    """/stores/products .results[].reviews: review counters."""
    count: int | None
    average_score: float | None
    premium_count: int | None


class StoreProduct(TypedDict):
    """/stores/products .results[]: one store-backend simple product."""
    id: str | None
    origin_product_id: str | None
    name: str | None
    link: str | None
    catalog_id: str | None
    catalog_link: str | None
    status: str | None
    sale_type: str | None
    is_displayed: bool | None
    pricing: StorePricing
    stock_quantity: int | None
    has_options: bool | None
    has_supplements: bool | None
    images: list[str]
    category: StoreProductCategory
    brand: str | None
    brand_id: str | None
    manufacturer: str | None
    model_name: str | None
    tags: list[str] | None
    page_title: str | None
    reviews: StoreProductReviews | None
    delivery: StoreDelivery | None
    is_free_delivery: bool | None
    is_today_delivery: bool | None
    has_arrival_guarantee: bool | None
    has_regular_subscription: bool | None
    has_free_return_insurance: bool | None
    is_minor_purchasable: bool | None
    is_adult_restricted: bool | None
    is_in_naver_shopping: bool | None
    editor_type: str | None
    store: StoreRef | None


class StoreProducts(TypedDict):
    """/stores/products response: popular rail or best-seller list of a store."""
    store: StoreRef
    list: StoreProductsList
    period: StoreBestPeriod | None  # None when list == "popular"
    count: int
    results: list[StoreProduct]


# ---- /catalogs/reviews --------------------------------------------------------------

class CatalogReviewAttachment(TypedDict):
    """/catalogs/reviews .results[].attachments[]: a photo or video of a review."""
    type: CatalogAttachmentType
    link: str | None


class CatalogReview(TypedDict):
    """/catalogs/reviews .results[]: one review listed under a catalog."""
    id: str | None
    score: int | None
    text: str | None
    created_at: str | None  # YYYY-MM-DD
    writer: str | None
    mall_name: str | None
    product_id: str | None
    catalog_product_id: str | None
    option: str | None
    attachments: list[CatalogReviewAttachment]


class CatalogReviews(TypedDict):
    """/catalogs/reviews response (not paginated)."""
    catalog_id: str
    link: str
    count: int
    results: list[CatalogReview]


# ==== categories, DataLab, health, listing jobs ===========================================

# ---- shared ---------------------------------------------------------------------------

# schemas.DATALAB_PERIODS / DATALAB_DEVICES / DATALAB_GENDERS / DATALAB_AGES (public names echoed back)
DataLabPeriod = Literal["daily", "weekly", "monthly"]
DataLabDevice = Literal["pc", "mobile"]
DataLabGender = Literal["male", "female"]
DataLabAge = Literal["10", "20", "30", "40", "50", "60"]

# listing_jobs.start / _run / get / ext_listing.check: every status a job can report
ListingStatus = Literal["running", "captcha", "done", "stopped"]


class Paging(TypedDict):
    """routes.paginate: the flat page fields shared by every paginated answer."""
    per_page: int
    current_page: int
    next: str | None
    previous: str | None


class DataLabWindow(TypedDict):
    """api._window_echo: the DataLab query window echoed by /keywords/* and /categories/trend."""
    category_id: str
    start_date: str
    end_date: str
    period: DataLabPeriod
    device: DataLabDevice | None
    gender: DataLabGender | None
    age: list[DataLabAge] | None


# ---- /categories/list -----------------------------------------------------------------

class Category(TypedDict):
    """/categories/list children[] (parsers.parse_datalab_categories node)."""
    id: str | None
    name: str | None
    parent_id: str | None
    level: int | None
    path: str | None
    is_leaf: bool | None
    order: int | None


class CategoryList(Category):
    """/categories/list: the category itself plus its direct children."""
    count: int
    children: list[Category]


# ---- /keywords/rank -------------------------------------------------------------------

class KeywordRank(TypedDict):
    """/keywords/rank results[] (parsers.parse_datalab_rank)."""
    rank: int | None
    keyword: str | None


class KeywordRankPage(Paging, DataLabWindow):
    """/keywords/rank: one page of 20 keywords; DataLab publishes no totals."""
    count: None
    total_pages: None
    category_name: str | None
    results: list[KeywordRank]


# ---- /keywords/trend and /categories/trend --------------------------------------------

class TrendPoint(TypedDict):
    """series[] of /keywords/trend and /categories/trend (relative click index, 100 = peak)."""
    date: str | None
    value: float | None


class KeywordTrend(DataLabWindow):
    """/keywords/trend: click series of one keyword in a category."""
    keyword: str
    category_name: str | None
    series: list[TrendPoint]


class Share(TypedDict):
    """/categories/trend device_share[] / gender_share[] / age_share[] (100 = largest)."""
    code: str | None
    label: str | None
    ratio: float | None


class CategoryTrend(DataLabWindow):
    """/categories/trend: click series plus device / gender / age shares."""
    category_name: str | None
    category_path: str | None
    series: list[TrendPoint]
    device_share: list[Share]
    gender_share: list[Share]
    age_share: list[Share]


# ---- /health --------------------------------------------------------------------------

class Health(TypedDict):
    """/health (and /): server version, mounted paths, extension bridge state."""
    status: Literal["ok"]
    version: str
    endpoints: list[str]
    extension: Literal["off", "connected", "disconnected"]


# ---- /listings ------------------------------------------------------------------------

class ListingJob(TypedDict):
    """POST /listings and GET /listings/<id> (listing_jobs.view: every key present, any may be null)."""
    id: str
    query: str | None
    status: ListingStatus
    max_batches: int | None
    batches: int | None
    kept: int | None
    ads: int | None
    total: int | None
    cursor: int | None
    has_more: bool | None
    stop: str | None
    started_at: str | None
    finished_at: str | None


class ListingStore(TypedDict):
    """/listings/<id>/products results[].store (composite.listing_row)."""
    name: str | None
    slug: str
    link: str
    grade: str | None
    is_brand_store: bool


class ListingPricing(TypedDict):
    """/listings/<id>/products results[].pricing (composite.listing_row, raw upstream ints)."""
    sale_price: int | None
    discounted_price: int | None
    discount_ratio: int | None
    currency: Literal["KRW"]


class ListingReviews(TypedDict):
    """/listings/<id>/products results[].reviews (composite.listing_row, raw upstream values)."""
    count: int | None
    average_score: float | int | None


class ListingRow(TypedDict):
    """/listings/<id>/products results[] (composite.listing_row + ext_listing.Listing.add)."""
    product_id: str
    nv_mid: str | None
    link: str
    name: str | None
    store: ListingStore
    pricing: ListingPricing
    category_id: str | None
    reviews: ListingReviews
    stock_quantity: int | None
    image: str | None
    is_ad: bool
    query: str
    batch: int
    seen_at: str


class ListingProductsPage(Paging):
    """/listings/<id>/products: one page of 50 listing rows (listing_jobs.products)."""
    count: int
    total_pages: int
    job_id: str
    status: ListingStatus
    results: list[ListingRow]


class ListingResult(TypedDict):
    """scripts/naver_api_client.NaverApiClient.listing(): the final job and every row."""
    job: ListingJob
    results: list[ListingRow]
