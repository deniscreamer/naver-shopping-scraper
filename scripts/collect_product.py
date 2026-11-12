"""Collect one product of a listing: everything the API knows about it, as one collected line (example_99's
per-product step, moved here so a job can call it one product at a time; example_99 and job.py share it).

    details   /products/details           prices, stock, category path, notice, description, facts
    reviews   /products/reviews/selected  up to `reviews` worth showing, with photos; more than review_pick.KEEP: the
                                          best of them by what they say, their photos capped (review_pick)
    specs     /products/specs             the page's 상품정보 rows, options, weight / size candidates (the owner's
                                          Chrome: search -> card -> page); by the product's name first, then the
                                          listing's query (2026-11-05: the listing's search did not show the card on
                                          its first page for 27 of 40)
    variants  naver_variants.choose_variants (paid ones too with `paid`)
    package   package_measures: five shipping fields per variant
    photos    the gallery and the chosen reviews' photos as the store's WebP (naver_images)

-> collect_guard.Outcome: complete / partial (with the data) / not_taken. Raises SourceStopped(status, error) when
the whole source must stop or wait: a busy adapter (409), any 503 from the adapter (its error starts with the
kind: "wall:", "naver error page:", "adapter error:"; ENDPOINTS.md), a 502 "blocked the request", a refused CDN.

    outcome = guard.run(key, lambda: collect(api, store, table, row, media_dir, query=QUERY, category=CATEGORY))
"""
from typing import Any, cast

import naver_types as T
from collect_guard import Outcome, SourceStopped
from naver_api_client import ApiError, NaverApiClient
from naver_images import download_gallery, download_review_media, posters_as_photos
from naver_variants import choose_variants
from package_measures import variant_measures
from review_pick import pick


def specs_for(api: NaverApiClient, link: str, query: str | None) -> T.ProductSpecs | None:
    """The specs, or None when the card is on neither search; a wall / busy adapter raises ApiError."""
    for q in (None, query) if query else (None,):
        try:
            return api.product_specs(link, query=q)
        except ApiError as e:
            if e.status != 404:
                raise
    return None


def stopped(e: ApiError) -> bool:
    """A wall (503 from the adapter, 502 "blocked the request" from the box: captcha, login, 403/418/429) or a busy
    adapter (409): the whole source stops (or the caller waits), no product is marked."""
    return e.status in (409, 503) or e.status == 502 and "blocked the request" in (e.error or "")


def collect(api: NaverApiClient, store: Any, table: dict, row: T.ListingRow, media_dir: str, *,
            query: str | None, category: str, paid: bool = False, reviews: int = 20) -> Outcome:
    try:
        details = api.product_details(row["link"])     # -> naver_types.ProductDetails
        picked = api.selected_reviews(row["link"], count=reviews)
        specs = specs_for(api, row["link"], query)
    except ApiError as e:
        if stopped(e):
            raise SourceStopped(f"{e.status} {e.error}", status=e.status, error=e.error)
        if e.status == 404:
            return Outcome("not_taken", "not_found", e.error)
        return Outcome.partial(f"api_{e.status}", e.error)
    if specs is None:
        return Outcome("not_taken", "card_not_found")
    options = specs["options"]
    variants = choose_variants(options, details["pricing"]["discounted_price"], paid=paid) if options else None
    page_category = (specs["category"] or {}).get("id")
    if page_category != category:                    # the page's category differs from the listing card's
        return Outcome("not_taken", "category_mismatch", f"page category {page_category}")
    package = variant_measures(specs, table)          # the run's table row was checked before the run
    kept, summary = pick(picked["results"], category)  # many reviews: the best KEEP, their photos capped, before any
    if summary:                                        # photo is fetched (review_pick; the owner, 2026-11-11)
        picked = cast(T.SelectedReviews, {**picked, "results": kept, "count": len(kept), "picked": summary})
    photos = download_gallery(details["images"], media_dir, store, details["id"])
    if photos["stopped"]:
        raise SourceStopped(f"image CDN: {photos['stopped']}", status=None, error=photos["stopped"])
    review_media = download_review_media(picked["results"], media_dir, store)
    if review_media["stopped"]:
        raise SourceStopped(f"image CDN: {review_media['stopped']}", status=None, error=review_media["stopped"])
    picked["results"] = [posters_as_photos(r) for r in picked["results"]]   # a video is stored as its poster
    data = {"listing": row, "details": details, "specs": specs, "variants": variants, "package": package,
            "reviews": picked, "photos": photos, "review_media": review_media}
    if options is None:
        return Outcome.partial("options_missing", "the page gave no product answer", data)
    if not specs["is_complete"]:                     # the 상품정보 list stayed folded: seller rows missing
        return Outcome.partial("specs_folded", f"{len(specs['specs'])} rows", data)
    if not photos["is_complete"]:
        return Outcome.partial("photos_incomplete", photos["failed"][:3], data)
    return Outcome("complete", data=data)
