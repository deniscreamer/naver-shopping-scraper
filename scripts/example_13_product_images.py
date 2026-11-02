"""Example 13: a product's photos, the full gallery, as a store's WebP files.

Step 1 - api.product_details(link)["images"]: the seller's gallery in order,
main photo first, as original-file URLs (no `?type=` rendition). The server
reads them from the store backend; no adapter, no page.
Step 2 - naver_images.download_gallery(): each file with a plain HTTP GET from
Naver's image CDN, a request every 2 s; a 403 / 429 stops the rest. Only if the
original fails is the same photo taken as a re-encode at that size, then as the
1000 px display version (`rendition` says which). Each photo is prepared in
memory (image_prep) and only the WebP is written: the short side down to 1500
(Merchant Center's recommendation; never enlarged), <= 1 MB,
old metadata dropped, the store as publisher in XMP. The source is not kept.
Step 3 - a manifest.json lists every file in gallery order with its source.

The store comes from SHOP_STORE in .env (default fairwardgolf; shop_stores).
File names: <slug>-001-<sha16>.webp. With no reviewed English name the slug is
<store>-<product id>; pass an ImageSeo (slug, title, alt, brand) when there is one,
as SEO below shows (it also writes title / alt / brand into the file's XMP).

    .venv/bin/python scripts/example_13_product_images.py [product link]
"""
import json
import os
import sys

from image_prep import ImageSeo
from naver_api_client import NaverApiClient
from naver_images import download_gallery
from shop_stores import get_store

PRODUCT = sys.argv[1] if len(sys.argv) > 1 else "https://brand.naver.com/idmakers/products/11696178500"
SEO: ImageSeo | None = None      # e.g. ImageSeo("idmakers-womens-golf-bag", "IDMAKERS Women's Golf Bag",
                                 #               "IDMAKERS women's golf bag", "IDMAKERS")

api = NaverApiClient()
store = get_store()
product = api.product_details(PRODUCT)                   # -> naver_types.ProductDetails
print(f"{product['name']}\n{len(product['images'])} photos in the gallery, store {store.publisher}")

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", f"images-{product['id'] or 'product'}")
result = download_gallery(product["images"], out_dir, store, product["id"], SEO)
for f in result["files"]:
    print(f"  {f['position']}. {f['source_width']}x{f['source_height']} {f['source_format']} {f['source_bytes']:>9,} B"
          f" -> {f['width']}x{f['height']} q{f['quality']} {f['bytes']:>7,} B  {f['rendition']:<8} "
          f"{os.path.basename(f['file'])}")
for f in result["failed"]:
    print(f"  {f['position']}. FAILED {f['error']}")
if result["stopped"]:
    print(f"stopped: {result['stopped']}")
print(("complete" if result["is_complete"] else "INCOMPLETE") + f", {result['originals']} from the original file")

manifest = {"product": {"id": product["id"], "name": product["name"], "link": product["link"]},
            "images": product["images"], **result}
with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=1)
print(f"-> {out_dir}/manifest.json")
