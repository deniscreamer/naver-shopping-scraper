"""Example 15: collect ONE golf full set with everything we have, its description images included, and prepare it.

The whole chain on one product, in its own folder (the operator's kept runs and shop output are not touched):

  1. pick      the 남성 골프채 풀세트 search listing (your Chrome through the adapter), screened like example_99
               (category 50002788 exactly, no rental, not deferred; "already in the shop" when the store's Shopify
               values are set); the first product this example has not collected yet. Or pass a product link.
  2. collect   /products/details, /products/reviews/selected (20), /products/specs (the page, by the product's
               name first), the variant choice (paid ones too: the category's transform rule), the five package
               fields (package_measures), the gallery and review photos as the store's WebP
  3. keep      keep_run into scripts/output/description-example/shops/ (read-only, like a real run)
  4. images    description_images: the description images (Naver's CDN first), RapidOCR in a worker process,
               the sidecar (needs `pip install -r scripts/requirements.txt`; the models download on first use)
  5. prepare   run_transform: the prepared product (prepared/5: attributes, no shop sections, reviews sanitized) with the description's size / weight merged in
               (stated, else composed from the set's parts), and the images' Korean text for the translation step with its flag
  6. print     what came out: status and notes, the five package fields and where each came from, the page text
               and the images' text (state, blocks, the file), the description photos kept

Needs the server running and Chrome open with the adapter (example_01: extension connected). A captcha on the way:
solve it in that Chrome (the run waits). ~1-3 min for the product, plus ~10-150 s for its description images.

    .venv/bin/python scripts/example_15_description_collect.py
    .venv/bin/python scripts/example_15_description_collect.py https://smartstore.naver.com/majorgolf/products/7583123963
"""
import json
import os
import sys
from typing import Any

import description_images
import keep_run
import run_transform
from deferred_log import DeferredLog
from listing_filter import Screen, source_key
from naver_api_client import ApiError, NaverApiClient
from naver_images import download_gallery, download_review_media, posters_as_photos
from naver_variants import choose_variants
from package_measures import load_table, variant_measures
from shop_stores import get_store
from shopify_catalog import CatalogError, ShopCatalog, ShopNotConfigured
from transform_shops import rules_for

QUERY = "남성 골프채 풀세트"
CATEGORY_ID = "50002788"                      # 스포츠/레저 > 골프 > 골프클럽 > 풀세트
REVIEWS = 20
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "output", "description-example")
SHOPS = os.path.join(ROOT, "shops")

api = NaverApiClient()
store = get_store()
namespace = store.shopify.namespace if store.shopify else store.id.value
shop = store.id.value
rules = rules_for(shop).category(CATEGORY_ID)


def collected_before() -> set[str]:
    """Product ids this example kept already: each run takes a new one."""
    ids = set()
    collected = os.path.join(SHOPS, shop, "collected")
    for run in keep_run.kept_run_ids(collected):
        with open(os.path.join(collected, run, "products.jsonl"), "rb") as f:
            ids |= {json.loads(x)["key"].split(":")[3] for x in f.read().split(b"\n") if x.strip()}
    return ids


def pick() -> Any:
    """A listing row: the product link given, or the first screened card not collected before."""
    if len(sys.argv) > 1:
        link = sys.argv[1]
        details = api.product_details(link)
        store_info = details.get("store") or {}
        return {"link": link, "product_id": str(details["id"]), "name": details.get("name"),
                "store": {"channel_no": store_info.get("id") or store_info.get("channel_no"),
                          "link": store_info.get("link")}, "category": details.get("category")}
    published: Any = set()
    try:
        published = ShopCatalog(store).keys()
    except (ShopNotConfigured, CatalogError) as e:
        print(f"(no shop check: {e})")
    screen = Screen(CATEGORY_ID, namespace, published, DeferredLog(shop).blocked())
    listing = api.listing(QUERY, max_batches=1)
    seen = collected_before()
    for row in listing["results"]:
        if screen.reason(row) is None and str(row.get("product_id")) not in seen:
            return row
    sys.exit(f"stop: no new product in the first listing batch for {QUERY!r} (left out: {dict(screen.counts)})")


def specs_for(link: str) -> Any:
    for query in (None, QUERY):                 # the product's name first (example_99)
        try:
            return api.product_specs(link, query=query)
        except ApiError as e:
            if e.status != 404:
                raise
    sys.exit(f"stop: {link}: the card was on neither search")



def main() -> None:
    row = pick()
    link = row["link"]
    print(f"1. product: {row.get('name') or link}\n   {link}")
    details = api.product_details(link)
    reviews = api.selected_reviews(link, count=REVIEWS)
    specs = specs_for(link)
    if (specs.get("category") or {}).get("id") != CATEGORY_ID:
        sys.exit(f"stop: the page's category is {(specs.get('category') or {}).get('id')}, not {CATEGORY_ID}")
    key = source_key(row, namespace) or f"{namespace}:naver:{(details.get('store') or {}).get('id')}:{details['id']}"
    options = specs["options"]
    variants = choose_variants(options, details["pricing"]["discounted_price"], paid=rules.paid_variants) \
        if options else None
    package = variant_measures(specs, load_table())
    src = os.path.join(ROOT, f"full-{CATEGORY_ID}")
    media = os.path.join(src, "images", str(details["id"]))
    photos = download_gallery(details["images"], media, store, details["id"])
    review_media = download_review_media(reviews["results"], media, store)
    reviews["results"] = [posters_as_photos(r) for r in reviews["results"]]
    description: Any = details.get("description") or {}
    print(f"2. collected: {details['pricing']['discounted_price']} KRW, "
          f"{len(variants['variants']) if variants else 0} variants, {len(specs['specs'])} spec rows, "
          f"{len(photos['files'])}/{photos['total']} photos, {reviews['count']} reviews chosen, "
          f"description: {len(description.get('text') or '')} characters of page text, "
          f"{len(description.get('images') or [])} images")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "products.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "listing": row, "details": details, "specs": specs, "variants": variants,
                            "package": package, "reviews": reviews, "photos": photos, "review_media": review_media},
                           ensure_ascii=False) + "\n")
    kept = keep_run.keep(src, SHOPS)
    print(f"3. kept: {kept}")
    result = description_images.run(shop, products=[str(details["id"])], shops_root=SHOPS,
                                     log=lambda m: print("   " + m))
    print(f"4. description images: {result['counts']}")
    prepared = run_transform.run(shop, None, SHOPS)["prepared"]
    p = next(x for x in prepared if x["key"] == key)
    product = p["product"]
    print(f"5. prepared ({p['format']}): {p['status']}"
          + (f", held: {', '.join(h['code'] for h in p['held'])}" if p["held"] else ""))
    for n in p["notes"]:
        print(f"   note {n['code']}: {n['detail']}")
    first = (product.get("variants") or [{}])[0]
    print(f"   package of variant {first.get('options_ko') or '(the product)'}:")
    for name, field in (first.get("package") or {}).items():
        value = field.get("value", {}).get("max") if "value" in field else field.get("central")
        other = field.get("compared") or {}
        print(f"     {name:18} {value:>7}  {field['source']:17} conf {field.get('confidence')}"
              + (f"  {field['how']}" if field.get("how") else "")
              + (f"  | compared {other.get('source')} {other.get('value')}" if other else ""))
    text = product.get("description_images_text") or {}
    print(f"   page text: {len(product.get('description_ko') or '')} characters; description photos kept: "
          f"{len(product.get('description_images') or [])}")
    print(f"   images' text: state {text.get('state')}, {text.get('blocks')} blocks, {text.get('chars')} characters")
    if text.get("ko"):
        ko_txt = os.path.join(SHOPS, shop, text["ko"].replace(".ko.json", ".ko.txt"))
        print(f"   -> {ko_txt}")
        with open(ko_txt, encoding="utf-8") as f:
            body = f.read().split("\n\n", 1)[-1]
        print("   " + "\n   ".join(body[:900].splitlines()))
    print(f"\n-> {os.path.join(SHOPS, shop, 'prepared', 'products.jsonl')}")


# a guard is required: description_images reads each product in a spawned worker, which imports this script again
if __name__ == "__main__":
    main()
