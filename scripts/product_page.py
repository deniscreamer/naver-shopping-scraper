"""Save a product page as the owner's Chrome renders it, for developing parsers and checking collected data
against the page: GET /products/page (search -> card photo -> page, never a direct open of the product link).

    .venv/bin/python scripts/product_page.py https://smartstore.naver.com/thegolf/products/5543745139
    .venv/bin/python scripts/product_page.py <link> --query "남성 골프채 풀세트"

-> scripts/output/pages/<product id>-<UTC time>/ page.html, product.json (the page's own answer), meta.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from naver_api_client import ApiError, NaverApiClient

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "pages")


def save(page: Any, root: str = OUTPUT) -> str:
    folder = os.path.join(root, f"{page['id']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    os.makedirs(folder)
    with open(os.path.join(folder, "page.html"), "w", encoding="utf-8") as f:
        f.write(page["html"])
    with open(os.path.join(folder, "product.json"), "w", encoding="utf-8") as f:
        json.dump(page["product_answer"], f, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in page.items() if k not in ("html", "product_answer")}, f, ensure_ascii=False,
                  indent=1)
    return folder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save a product page as the owner's Chrome renders it.")
    parser.add_argument("product", help="a smartstore / brand store product link or a product number")
    parser.add_argument("--query", help="the search that lists it (default: its name)")
    args = parser.parse_args(argv)
    try:
        page = NaverApiClient().product_page(args.product, query=args.query)
    except ApiError as e:
        print(f"product_page: {e.status} {e.error}")
        return 1
    folder = save(page)
    print(f"product_page: {page['title']!r}, {len(page['html']):,} chars, answer "
          f"{'yes' if page['product_answer'] else 'NO'} -> {folder}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
