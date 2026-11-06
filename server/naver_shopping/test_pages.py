"""Saved product pages replayed offline (fixtures/pages/<product id>/, cut by page_fixtures.py): the description
(parsers.parse_contents of the backend's contents answer) and the /products/specs answer (ext_product.
specs_from_page of the product record, the page and its product answer) must equal expected.json.

A deliberate change of a parser shows here as a diff: rewrite the expected answers with
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest server/naver_shopping/test_pages.py
and read the diff of fixtures/pages/*/expected.json before committing. The set grows only when the owner asks
(DEVELOPMENT_RULES R-TEST-5)."""
import json
import os

import pytest

import ext_product
from naver_shopping import page_fixtures, parsers

PAGES = page_fixtures.FIXTURES
NAMES = sorted(n for n in os.listdir(PAGES) if os.path.isdir(os.path.join(PAGES, n))) if os.path.isdir(PAGES) else []


def _load(name, file):
    with open(os.path.join(PAGES, name, file), encoding="utf-8") as f:
        return f.read() if file.endswith(".html") else json.load(f)


def replay(name):
    details = _load(name, "details.json")
    details["description"] = parsers.parse_contents(_load(name, "contents.json"))
    specs = ext_product.specs_from_page(details, _load(name, "page.html"), _load(name, "product.json"))
    specs.pop("read_at")
    return {"description": details["description"], "specs": specs}


@pytest.mark.parametrize("name", NAMES)
def test_page_replays(name):
    got = json.loads(json.dumps(replay(name), ensure_ascii=False))
    path = os.path.join(PAGES, name, "expected.json")
    if os.environ.get("UPDATE_GOLDEN"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=1)
            f.write("\n")
    with open(path, encoding="utf-8") as f:
        assert got == json.load(f)


def test_cut_page_reads_the_same():
    page = "<html><body><div><strong>상품정보</strong><ul><li><div>브랜드</div><div>핑</div></li></ul></div>" \
           "<div>광고</div><span>오늘출발</span><span>14:00 까지 결제 시 오늘 바로 발송</span></body></html>"
    small = page_fixtures.cut_page(page, "1")
    assert "광고" not in small and page_fixtures._reads(small, "1") == page_fixtures._reads(page, "1")
