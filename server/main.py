"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. Inputs go through the same schemas the API uses, so links,
IDs and defaults are accepted exactly as in an API call.
"""
import json
import os

from naver_shopping import api, schemas

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


def load(schema_cls, **params):
    return schema_cls().load(params)


if __name__ == "__main__":
    # up to 96 products per keyword, with price / category / delivery filters
    save("search_raspberry_pi.json", api.products_search(**load(schemas.ProductsSearchSchema, query="raspberry pi")))

    # a product link (or bare product ID): price, options, stock, description, specs, review stats
    save("product_8087042745.json", api.product_details(**load(
        schemas.ProductSchema, product="https://smartstore.naver.com/dailyromantic/products/8087042745")))

    # the top trending keywords of a category (Cosmetics & Beauty), 20 per page
    save("keywords_rank_50000002.json", api.keywords_rank(**load(schemas.KeywordsRankSchema, category="50000002")))
