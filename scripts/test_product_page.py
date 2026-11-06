"""Offline test for product_page.py: what is saved from a /products/page answer.

    .venv/bin/python -m pytest scripts/test_product_page.py -q
"""
import json
import os

from product_page import save


def test_save(tmp_path):
    page = {"id": "42", "link": "l", "query": "q", "url": "u", "title": "t", "search_url": "s",
            "html": "<html>상품</html>", "product_answer": {"id": 42}, "saved_to": "/x", "read_at": "r"}
    folder = save(page, str(tmp_path))
    assert sorted(os.listdir(folder)) == ["meta.json", "page.html", "product.json"]
    assert open(os.path.join(folder, "page.html"), encoding="utf-8").read() == "<html>상품</html>"
    meta = json.load(open(os.path.join(folder, "meta.json")))
    assert meta["title"] == "t" and "html" not in meta and json.load(open(os.path.join(folder, "product.json"))) == {"id": 42}
