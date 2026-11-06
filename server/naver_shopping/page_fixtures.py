"""Cut a saved product page into a small offline fixture (naver_shopping/fixtures/pages/<product id>/), for the
regression tests in test_pages.py. Pure helpers plus a command line; no network.

A page as the owner's Chrome rendered it is 1-2 MB. The parsers read only a few parts of it: the 상품정보 box
(pdp.spec_rows, specs_collapsed), the text fields (pdp.text_fields), the purchase box lines (pdp.delivery_promise)
and the JSON-LD (measures.json_ld_rows). cut_page keeps those subtrees in page order; cut_answer drops the parts
of the page's product answer no parser reads. Each cut is checked: the parsers must give the same answer on the
cut as on the whole, else the cleaned whole page is kept.

    .venv/bin/python server/naver_shopping/page_fixtures.py <saved page folder> <collected products.jsonl> [<name>]

The folder is one of server/output/ext-product/<time>-<id>/ (product.html, product.json) or scripts/output/pages/
(page.html, product.json); the line with that product id in products.jsonl gives the product record (details) and
the raw description. Writes details.json, contents.json, page.html, product.json; the expected answers are written
by `UPDATE_GOLDEN=1 pytest server/naver_shopping/test_pages.py`.
"""
import html as html_lib
import json
import os
import re
import sys

from naver_shopping import measures, parsers, pdp

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "pages")
_PROMISE_RE = re.compile(r"오늘출발|도착\s*확률|발송\s*예정|까지\s*결제|해외직배송")
_HEAVY_KEYS = {"productAttributes", "interestFreePlans", "benefitsPolicy", "seoInfo", "epInfo", "productImages",
               "representImage", "productVideos", "view360Image", "product3dImageConfig", "rmids", "channel",
               "sellerTags", "naverShoppingSearchInfo", "purchaseReviewInfo", "reviewAmount"}
_SNAP_RE = re.compile(r"/p-\d+-s-\d+-[A-Z]-\d+")


def _serialize(node):
    attrs = "".join(f' {k}="{html_lib.escape(v)}"' if v else f" {k}" for k, v in node.attrs.items())
    if node.tag == "script":
        inner = "".join(c for c in node.children if isinstance(c, str))
    else:
        inner = "".join(_serialize(c) if isinstance(c, pdp._Node) else html_lib.escape(c, quote=False)
                        for c in node.children)
    return f"<{node.tag}{attrs}>" if node.tag in pdp._VOID else f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def _regions(root):
    """The subtrees the parsers read, outermost only, in page order."""
    keep = []
    for n in root.descendants():
        a = n.attrs
        if n.tag == "script" and "ld+json" in a.get("type", ""):
            keep.append(n)
        elif n.tag in ("strong", "h2", "h3", "h4") and pdp._flat(n) == pdp.SPEC_HEADING:
            box = n.parent
            while box is not None and not any(d.tag == "ul" for d in box.descendants()):
                box = box.parent
            keep.append(box or n)
        elif n.tag == "button" and a.get("aria-expanded") is not None:
            keep.append(n)
        elif n.tag == "label" and a.get("for") or n.tag == "input" and a.get("data-tag") == "textOption":
            keep.append(n)
        elif any(isinstance(c, str) and _PROMISE_RE.search(c) for c in n.children):
            keep.append(n)
    ids = {h for n in keep for h in n.attrs.get("aria-describedby", "").split()}
    keep += [n for n in root.descendants() if n.attrs.get("id") in ids]
    chosen = set(map(id, keep))

    def inside(n):
        p = n.parent
        while p is not None:
            if id(p) in chosen:
                return True
            p = p.parent
        return False
    order = {id(n): i for i, n in enumerate(root.descendants())}
    return sorted((n for n in keep if n is not None and not inside(n)), key=lambda n: order[id(n)])


def _reads(page_html, product_id):
    return (pdp.spec_rows(page_html), pdp.specs_collapsed(page_html), pdp.text_fields(page_html),
            pdp.delivery_promise(page_html), measures.json_ld_rows(page_html, product_id))


def _cleaned(page_html):
    h = re.sub(r"<script\b(?![^>]*ld\+json)[^>]*>.*?</script>", "", page_html, flags=re.S | re.I)
    h = re.sub(r"<(style|svg|noscript|iframe)\b[^>]*>.*?</\1>", "", h, flags=re.S | re.I)
    h = re.sub(r"<!--.*?-->|<(?:link|meta)\b[^>]*>", "", h, flags=re.S | re.I)
    return re.sub(r'\s(?:data-(?:shp|nlog|nclick)[\w-]*|style|srcset)="[^"]*"', "", h)


def cut_page(page_html, product_id):
    """-> a small HTML the page parsers read the same as `page_html`."""
    root = pdp.parse_html(page_html)
    body = "".join(_serialize(n) for n in _regions(root))
    small = f"<html><body>{body}</body></html>"
    if _reads(small, product_id) == _reads(page_html, product_id):
        return small
    cleaned = _cleaned(page_html)
    if _reads(cleaned, product_id) != _reads(page_html, product_id):
        raise ValueError(f"product {product_id}: the page reads differently once cut")
    return cleaned


def cut_answer(answer):
    """-> the page's product answer without the parts no parser reads (checked)."""
    small = {k: v for k, v in answer.items() if k not in _HEAVY_KEYS}
    if parsers.parse_page_options(small) != parsers.parse_page_options(answer) or \
            parsers.parse_page_delivery(small) != parsers.parse_page_delivery(answer):
        return answer
    return small


def contents_from(description):
    """The backend's contents answer back from a collected `details.description` (html, editor_type, images:
    Naver's snapshot tiles are snapImages, other images come from the body)."""
    images = description.get("images") or []
    snaps = [u for u in images if _SNAP_RE.search(u)]
    return {"renderContent": description.get("html"), "editorType": description.get("editor_type"),
            "snapImages": [{"url": u} for u in snaps] if snaps and len(snaps) == len(images) else []}


def write(folder, lines_path, name=None):
    page_file = next(os.path.join(folder, f) for f in ("page.html", "product.html")
                     if os.path.exists(os.path.join(folder, f)))
    answer = json.load(open(os.path.join(folder, "product.json"), encoding="utf-8"))
    product_id = str(answer.get("id") or answer.get("productNo"))
    line = next(json.loads(x) for x in open(lines_path, encoding="utf-8")
                if x.strip() and json.loads(x)["key"].split(":")[3] == product_id)
    details = {k: v for k, v in line["details"].items() if k not in ("description", "reviews")}
    out = os.path.join(FIXTURES, name or product_id)
    os.makedirs(out, exist_ok=True)
    page_html = open(page_file, encoding="utf-8").read()
    with open(os.path.join(out, "page.html"), "w", encoding="utf-8") as f:
        f.write(cut_page(page_html, product_id))
    for file, data in (("product.json", cut_answer(answer)), ("details.json", details),
                       ("contents.json", contents_from(line["details"].get("description") or {}))):
        with open(os.path.join(out, file), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    print(write(*sys.argv[1:4]))
