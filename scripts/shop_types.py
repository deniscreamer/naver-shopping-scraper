"""Types of our own records, for scripts and mypy: TypedDicts only, no runtime code (naver_types.py is the API's
answers; this file is what the pipeline writes from them).

Each type mirrors the one place that builds the record today, and the real files (checked 2026-11-16 over the
golden fixtures and the shop's products.jsonl): a key the builder may leave out is NotRequired, or the whole type
is total=False when a record may be empty (a held product's `product` is {}). Nothing here is checked when a
file is read: the files stay plain JSON, the types only name their shape. A shape change updates its type in the
same commit; test_shop_types.py checks the golden prepared products against PreparedProduct.

    PreparedProduct   transform.prepare's `product` (+ description_images_text, set by run_transform.image_texts)
    LedgerRow         a line of <shop>/publish/published.jsonl (publish.py; store_diff --adopt)
"""
from typing import Any, NotRequired, Required, TypedDict


# ==== the prepared product (transform.prepare, prepared/products.jsonl) ===============================

class PreparedOption(TypedDict):
    """product.options[]: an option axis that varies across the sold variants (transform.options_and_variants)."""
    name_ko: str
    values_ko: list[str]


class PreparedFact(TypedDict):
    """product.facts[]: a one-value axis or a simple choice; label_ko "" when the axis name is a placeholder."""
    label_ko: str
    value_ko: str


class PreparedVariant(TypedDict):
    """product.variants[] (transform._variant)."""
    source_id: str                     # "observed:" + the Korean option tuple, or the product id
    naver_variant_id: str | None
    options_ko: list[str]
    price_krw: int | None
    price_usd: str | None              # "1970.00"; None when the price is unknown
    sku: str
    available: bool
    package: dict[str, Any] | None     # package_measures.current_defaults: {product_weight_g: {...}, ...}
    today_dispatch: bool | None


class PreparedPricing(TypedDict):
    """product.pricing."""
    base_krw: int | None
    original_krw: int | None
    krw_per_usd: int
    rounding: str                      # "ceil-cent"
    taxable: bool
    compare_at: None


class PreparedImage(TypedDict):
    """product.images[]: a gallery photo saved by the collector (transform.images)."""
    position: int
    file: str | None                   # collected/<run>/images/<product id>/<name>; None without a file
    sha256: str
    width: int
    height: int


class PreparedSpec(TypedDict):
    """product.specs[]: a 상품정보 row shown (spec_variants.check_specs); for_ko when it is true of some variants."""
    label_ko: str
    value_ko: str
    for_ko: NotRequired[list[str]]


class PreparedPersonalization(TypedDict):
    """product.personalization[]: a text field of the order (transform.personalization)."""
    label_ko: str
    required: bool
    max_length: int | None
    placeholder_ko: str | None


class PreparedAddon(TypedDict):
    """product.addons[] (transform.addons)."""
    group_ko: str
    name_ko: str
    required: bool
    price_krw: int
    price_usd: str


class PreparedRating(TypedDict):
    """product.rating (transform.reviews); None when the product has no review."""
    value: float | None
    count: int | None


class PreparedImageText(TypedDict, total=False):
    """product.description_images_text: run_transform.image_texts' flag; state is always there, the rest when the
    description images were read."""
    state: str | None                  # off | not_read | empty | to_translate | translated
    ko: str | None                     # translation/<product id>/description_images.ko.json, or None
    en: str
    blocks: int
    chars: int
    sha256: str
    dropped: dict[str, int]            # rule -> blocks dropped


class PreparedProduct(TypedDict, total=False):
    """Prepared.product: every key for a product built (ready or held), {} for collect_incomplete.
    reviews: review_clean.clean_reviews' rows; attributes: attributes.extract; delivery: the delivery answer's
    scope, fee_type, base_fee, is_overseas, customs_tax_type, extra_fee_area2/3, policy_text, lead_time,
    extra_fee_text."""
    title_ko: str
    brand_ko: str | None               # None until run_transform's brand_fallback names one
    brand_source: str | None
    attributes: dict[str, dict[str, Any]]
    options: list[PreparedOption]
    facts: list[PreparedFact]
    variants: list[PreparedVariant]
    pricing: PreparedPricing
    specs: list[PreparedSpec]
    personalization: list[PreparedPersonalization]
    addons: list[PreparedAddon]
    rating: PreparedRating | None
    reviews: list[dict[str, Any]]
    images: list[PreparedImage]
    delivery: dict[str, Any]
    description_ko: str | None
    description_images: list[str]
    description_dropped: list[dict[str, Any]]    # {rule, text}: the seller's boilerplate, for audit
    description_images_text: PreparedImageText   # run_transform.image_texts, not prepare


class PreparedSource(TypedDict):
    """Prepared.source: where the product was collected."""
    run: str
    line: int
    link: str | None
    channel_no: str
    product_id: str
    category_id: str | None


# ==== the publication ledger (publish.py, <shop>/publish/published.jsonl) ===============================

class LedgerPhoto(TypedDict):
    """LedgerRow.photos[]: a gallery photo on the Shopify product, by its file's hash."""
    sha256: str
    media_id: str


class LedgerRow(TypedDict, total=False):
    """One line of the ledger; the last line of a key is its state. Written by publish.publish_one (published),
    withdraw (withdrawn: format, key, product_id, handle, admin_url, store_status, reason), restore (the last
    published line again, digest "", restored), activate (the published line again, store_status ACTIVE,
    activated) and store_diff --adopt (the published line again, output, adopted)."""
    format: str
    key: Required[str]
    status: Required[str]              # published | withdrawn
    at: Required[str]                  # UTC ISO time of the line
    digest: str | None                 # publish.inputs_digest; None after a failed photo, "" after a restore
    output: str | None                 # publish.output_digest of what productSet sent; None after a failed photo
    product_id: str                    # gid://shopify/Product/...
    handle: str
    created: bool
    photos: list[LedgerPhoto]
    photos_failed: list[str]
    reviews: int
    feed_url: str | None
    pricing: str                       # shop_pricing's version
    prices_usd: list[int]              # [lowest, highest]
    admin_url: str
    preview_url: str | None
    store_status: str                  # only when not ACTIVE (a draft, a withdrawal), or after a restore / activation
    reason: str                        # withdrawn: why
    restored: str                      # restore: why
    activated: str                     # activate: when
    adopted: str                       # store_diff --adopt: when
