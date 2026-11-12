"""Offline tests for publication: shop_pricing.py, shopify_payload.py and publish.py with fake Shopify clients.
No network.

    .venv/bin/python -m pytest scripts/test_publish.py -q
"""
import json
import os
import re

import pytest

import publish as PB
import shopify_payload as sp
from shop_pricing import Policy, policy
from transform import text_id

KEY = "fairwardgolf:naver:100:555"


def _en(pairs):
    return {text_id(kind, ko): en for kind, ko, en in pairs}


def _product(options=True, available=(True, False), reviews=True, extras=True):
    variants = []
    for i, ok in enumerate(available):
        variants.append({"available": ok, "naver_variant_id": f"9{i}", "options_ko": ["빨강", f"{i + 1}번"] if options
                         else [], "price_krw": 5560 + i * 1000, "price_usd": "5.56", "sku": f"FW-{i}",
                         "source_id": f"s{i}", "today_dispatch": None,
                         "package": {f: {"central": c, "confidence": 1, "source": "category_default"} for f, c in
                                     (("package_weight_g", 4500), ("package_length_mm", 1250),
                                      ("package_width_mm", 280), ("package_height_mm", 230))}})
    product = {
        "title_ko": "[오늘출고] 캘러웨이 레바 풀세트", "brand_ko": "캘러웨이",
        "options": [{"name_ko": "색상", "values_ko": ["빨강"]},
                    {"name_ko": "번호", "values_ko": [f"{i + 1}번" for i in range(len(available))]}] if options else [],
        "variants": variants, "pricing": {"base_krw": 5560, "original_krw": 9000, "taxable": False},
        "images": [{"file": "collected/r/images/555/a.webp", "sha256": "a" * 64, "position": 0},
                   {"file": "collected/r/images/555/b.webp", "sha256": "b" * 64, "position": 1}],
        "rating": {"value": 4.86, "count": 7} if reviews else None,
        "reviews": [{"id": "77", "score": 5, "text_ko": "좋아요", "created_at": "2026-10-01T00:00:00Z",
                     "writer": "abc***", "avatar": "collected/r/images/555/av.webp",
                     "photos": ["collected/r/images/555/p1.webp"]}] if reviews else [],
        "personalization": [{"label_ko": "이름", "required": True, "max_length": 20, "placeholder_ko": "입력"}]
        if extras else [],
        "addons": [{"group_ko": "장갑", "name_ko": "M", "price_krw": 12340, "price_usd": "12.34", "required": False},
                   {"group_ko": "장갑", "name_ko": "L", "price_krw": 0, "price_usd": "0.00", "required": False},
                   {"group_ko": "가방", "name_ko": "검정", "price_krw": 5000, "price_usd": "5.00", "required": True}]
        if extras else [],
        "facts": [{"label_ko": "증정", "value_ko": "퍼터"}], "specs": [], "delivery": {"fee_type": "FREE"},
    }
    prepared = {"format": "prepared/4", "key": KEY, "shop": "fairwardgolf", "status": "ready",
                "source": {"product_id": "555", "channel_no": "100", "category_id": "50002788", "run": "r",
                           "link": "https://smartstore.naver.com/x/products/555?a=1"},
                "product": product, "texts": []}
    en = _en([("title", product["title_ko"], "Callaway REVA Complete Set"), ("brand", "캘러웨이", "Callaway"),
              ("option_name", "색상", "Color"), ("option_value", "빨강", "Red"), ("option_name", "번호", "Number"),
              ("option_value", "1번", "#1"), ("option_value", "2번", "#2"), ("review", "좋아요", "Nice."),
              ("text_label", "이름", "Name"), ("text_placeholder", "입력", "Enter"), ("addon_group", "장갑", "Glove"),
              ("addon_name", "M", "M"), ("addon_name", "L", "L"), ("addon_group", "가방", "Bag"),
              ("addon_name", "검정", "Black")])
    translated = {"key": KEY, "status": "translated", "en": en}
    placement = {"key": KEY, "status": "placed", "leaves": [
        {"leaf": "womens-complete-sets", "product_type": "Women’s Complete Golf Sets", "skus": ["FW-0", "FW-1"],
         "tags": ["fairwardgolf:leaf:womens-complete-sets", "fairwardgolf:parent:clubs"]}]}
    return prepared, translated, placement


def _mf(items, ns, key):
    return next((m for m in items if m["namespace"] == ns and m["key"] == key), None)


def _build(prepared, translated, placement, **kw):
    urls = {f: f"https://cdn.shopify.com/{os.path.basename(f)}" for f in sp.review_files(prepared)}
    rows = sp.reviews(prepared, sp.English(translated), urls)
    return sp.product_input(prepared, translated, placement, policy("fairwardgolf"), "gid://shopify/Location/1",
                            [{"originalSource": "s1"}, {"id": "gid://shopify/MediaImage/2"}],
                            "https://cdn.shopify.com/feed.json", rows, **kw)


# ---- pricing ----------------------------------------------------------------------------------------------------

def test_cost_rounds_up_to_a_dollar_at_1000_krw():
    p = Policy()
    assert p.cost_usd(5560) == 6 and p.cost_usd(5000) == 5 and p.cost_usd(1_449_900) == 1450 and p.cost_usd(0) == 0


def test_a_shop_without_the_delivery_rule_sells_at_the_cost():
    q = Policy().quote({"price_krw": 5560}, {})
    assert (q.cost, q.price, q.breakdown) == (6, 6, None) and Policy().price_usd(6) == 6
    assert policy("another")  == Policy() and policy("another").describe()["version"] == "krw-cost/1"


# ---- payload ----------------------------------------------------------------------------------------------------

def test_core_fields_title_vendor_type_tags_no_description():
    out = _build(*_product())
    assert out["title"] == "Callaway REVA Complete Set" and out["vendor"] == "Callaway"
    assert out["handle"] == "callaway-reva-complete-set" and out["status"] == "ACTIVE"
    assert out["descriptionHtml"] == "" and out["productType"] == "Women’s Complete Golf Sets"
    assert out["tags"] == ["fairwardgolf:leaf:womens-complete-sets", "fairwardgolf:parent:clubs"]


def test_every_variant_buyable_sold_out_on_naver_too():
    out = _build(*_product())
    for v, available in zip(out["variants"], (True, False)):
        assert v["inventoryPolicy"] == "CONTINUE" and v["inventoryItem"]["tracked"] is False
        assert "inventoryQuantities" not in v
        assert json.loads(v["metafields"][0]["value"])["available"] is available       # what Naver said


def test_a_repeated_option_at_one_price_is_one_option():
    prepared, translated, placement = _product(available=(True, True, True, True))
    p = prepared["product"]
    p["options"] = [{"name_ko": "옵션 1", "values_ko": ["S", "SR"]}, {"name_ko": "옵션 2", "values_ko": ["S", "SR"]}]
    for v, pick in zip(p["variants"], (["S", "S"], ["S", "SR"], ["SR", "S"], ["SR", "SR"])):
        v["options_ko"], v["price_krw"], v["available"] = pick, 880000, pick != ["SR", "SR"]
    translated["en"].update(_en([("option_name", "옵션 1", "Flex"), ("option_name", "옵션 2", "Flex"),
                                 ("option_value", "S", "S"), ("option_value", "SR", "SR")]))
    out = _build(prepared, translated, placement)
    assert out["productOptions"] == [{"name": "Flex", "values": [{"name": "S"}, {"name": "SR"}]}]
    assert [v["sku"] for v in out["variants"]] == ["FW-0", "FW-3"]          # the repeat equal to the option
    assert [json.loads(v["metafields"][0]["value"])["available"] for v in out["variants"]] == [True, True]
    p["variants"][1]["price_krw"] = 900000                                    # the repeat changes the price
    out = _build(prepared, translated, placement)
    assert [o["name"] for o in out["productOptions"]] == ["Flex", "Flex 2"] and len(out["variants"]) == 4


def test_variant_price_cost_weight_and_metafields():
    v = _build(*_product())["variants"][0]
    assert v["price"] == "819.00" and v["inventoryItem"]["cost"] == "9.00" and "compareAtPrice" not in v
    assert v["inventoryItem"]["measurement"] == {"weight": {"value": 4500, "unit": "GRAMS"}}
    assert v["optionValues"] == [{"optionName": "Color", "name": "Red"}, {"optionName": "Number", "name": "#1"}]
    source = json.loads(_mf(v["metafields"], "fairwardgolf", "source")["value"])
    assert source["priceKrw"] == 5560 and source["costUsd"] == 9 and source["priceUsd"] == 819
    assert source["available"] is True
    price = json.loads(_mf(v["metafields"], "fairwardgolf", "price")["value"])      # the default box, level 1
    assert price["schemaVersion"] == "fairwardgolf-variant-price/1" and price["level"] == 1
    assert (price["purchaseUsd"], price["dutyUsd"], price["costUsd"], price["gridUsd"], price["coefficient"],
            price["deliveryUsd"], price["feeUsd"], price["marginUsd"], price["priceUsd"]) == (
        6, "0.75", "9.00", "258.78", "2.50", "646.95", "35.60", "101.15", 819)
    package = json.loads(_mf(v["metafields"], "fairwardgolf", "package")["value"])
    assert package["fields"]["package_weight_g"]["confidence"] == 1


def test_no_options_get_the_universal_fallback():
    out = _build(*_product(options=False, available=(True,)))
    assert out["productOptions"] == [{"name": "Option", "values": [{"name": "Standard"}]}]
    assert out["variants"][0]["optionValues"] == [{"optionName": "Option", "name": "Standard"}]


def test_two_values_with_one_english_stay_distinct():
    prepared, translated, placement = _product()
    translated["en"][text_id("option_value", "2번")] = "#1"
    values = [v["name"] for v in _build(prepared, translated, placement)["productOptions"][1]["values"]]
    assert values == ["#1", "#1 (2)"]


def test_photos_alt_brand_once_and_numbered():
    files = _build(*_product())["files"]
    assert files[0] == {"originalSource": "s1", "contentType": "IMAGE", "alt": "Callaway REVA Complete Set - photo 1"}
    assert files[1] == {"id": "gid://shopify/MediaImage/2", "alt": "Callaway REVA Complete Set - photo 2"}
    assert sp.alt("PING", "G430 Set", 3) == "PING G430 Set - photo 3"


def test_product_metafields_reviews_text_fields_addons_source():
    mfs = _build(*_product())["metafields"]
    assert json.loads(_mf(mfs, "custom", "review")["value"]) == {"scale_min": "1.0", "scale_max": "5.0",
                                                                  "value": "4.9"}
    assert _mf(mfs, "custom", "rating_count")["value"] == "7"
    row = json.loads(_mf(mfs, "custom", "reviews_seo")["value"])[0]
    assert row["createdAt"] == "2026-10-01T00:00:00Z" and "date" not in row
    assert row["customer"] == {"name": "abc***", "avatarUrl": "https://cdn.shopify.com/av.webp"}
    assert row["images"] == ["https://cdn.shopify.com/p1.webp"] and row["description"] == "Nice."
    assert row["id"] == sp.review_id("77")
    assert _mf(mfs, "custom", "reviews_feed_url")["value"] == "https://cdn.shopify.com/feed.json"
    fields = json.loads(_mf(mfs, "custom", "personalization_fields")["value"])["fields"]
    assert fields[0]["label"] == "Name" and fields[0]["constraints"] == {"maxLength": 20}
    site = json.loads(_mf(mfs, "custom", "optional_addons")["value"])
    assert site == {"schemaVersion": "product-optional-addons/v1", "groups": [               # the site: free only,
        {"key": site["groups"][0]["key"], "label": "Glove",                                  # its exact keys
         "choices": [{"key": site["groups"][0]["choices"][0]["key"], "label": "L", "priceKrw": 0}]}]}
    every = json.loads(_mf(mfs, "fairwardgolf", "addons")["value"])["groups"]
    assert [(g["label"], g["required"], [(c["label"], c["priceKrw"], c["priceUsd"], c["free"]) for c in g["choices"]])
            for g in every] == [("Glove", False, [("M", 12340, 13, False), ("L", 0, 0, True)]),
                                ("Bag", True, [("Black", 5000, 5, False)])]
    source = json.loads(_mf(mfs, "fairwardgolf", "source")["value"])
    assert source["url"] == "https://smartstore.naver.com/x/products/555" and source["priceKrw"] == 5560
    assert _mf(mfs, "fairwardgolf", "source_offer_id")["value"] == KEY
    pricing = json.loads(_mf(mfs, "fairwardgolf", "pricing")["value"])
    assert pricing["schemaVersion"] == "fairwardgolf-pricing/2" and pricing["krwPerUsd"] == 1000
    assert pricing["coefficients"] == {"5": "1.00", "4": "1.10", "3": "1.20", "2": "1.40", "1": "2.50"}
    assert not [m for m in mfs if "gender" in m["key"] or "fact" in m["key"] or "deliver" in m["key"]]


def test_a_variant_without_a_box_holds_the_product():
    prepared, translated, placement = _product()
    del prepared["product"]["variants"][1]["package"]["package_width_mm"]
    with pytest.raises(sp.PayloadError, match="FW-1: no package box"):
        _build(prepared, translated, placement)


def test_no_reviews_no_review_metafields():
    mfs = _build(*_product(reviews=False, extras=False))["metafields"]
    assert {m["key"] for m in mfs if m["namespace"] == "custom"} == {"reviews_feed_url"}   # _build passes a feed
    assert _mf(mfs, "custom", "personalization_fields") is None and _mf(mfs, "custom", "optional_addons") is None


def test_feed_rows_name_the_date_date():
    prepared, translated, _ = _product()
    rows = sp.reviews(prepared, sp.English(translated), {})
    assert rows[0]["date"] == "2026-10-01T00:00:00Z" and rows[0]["images"] == [] and "avatarUrl" not in \
        rows[0]["customer"]


def test_untranslated_and_unplaced_are_held():
    prepared, translated, placement = _product()
    del translated["en"][text_id("title", prepared["product"]["title_ko"])]
    with pytest.raises(sp.Untranslated):
        _build(prepared, translated, placement)
    prepared, translated, placement = _product()
    with pytest.raises(sp.PayloadError):
        _build(prepared, translated, {"status": "unresolved", "reason": "x"})


def test_handle_ascii_brand_in_front():
    assert sp.handle("Women’s REVA Set™", "Callaway") == "callaway-womens-reva-set"
    assert sp.handle("Callaway REVA", "Callaway") == "callaway-reva"


# ---- publish.py with fake clients ----------------------------------------------------------------------------------

class FakeFiles:
    def __init__(self):
        self.created = []

    def create(self, path, filename, image=True):
        self.created.append(filename)
        return f"https://cdn.shopify.com/files/{filename}"

    def create_many(self, items):
        return {name: self.create(path, name, image) for path, name, image in items}


class FakeProducts:
    class shop:
        domain = "93r1y5-tt.myshopify.com"

    def __init__(self, existing=None):
        self.existing, self.sent, self.published, self.staged = existing or {}, [], [], []

    def keys(self):
        return self.existing

    def stage(self, path):
        self.staged.append(os.path.basename(path))
        return f"staged:{os.path.basename(path)}"

    def stage_many(self, items):
        return [self.stage(path) for path, _, _ in items]

    owners = {"callaway-reva-complete-set": ("gid://shopify/Product/other", "fairwardgolf:naver:1:1")}
    failed_media = ()

    def handle_owner(self, handle):
        return self.owners.get(handle)

    def product_set(self, payload, product_id=None):
        self.sent.append((payload, product_id))
        return {"id": product_id or "gid://shopify/Product/1", "handle": payload.get("handle", "kept-handle"),
                "onlineStorePreviewUrl": "https://preview"}

    def media_ready(self, product_id):
        return {"media": {"nodes": [{"id": f"gid://shopify/MediaImage/{i}",
                                     "status": "FAILED" if i in self.failed_media else "READY"} for i in (1, 2)]}}

    def publish(self, product_id, publication_ids):
        self.published.append((product_id, publication_ids))

    def delete_metafields(self, product_id, keys):
        self.deleted = (product_id, keys)


def _shop(tmp_path):
    prepared, translated, placement = _product()
    d = tmp_path / "fairwardgolf"
    for sub, row in (("prepared/products.jsonl", prepared), ("translation/translated.jsonl", translated),
                     ("placement/placements.jsonl", placement)):
        (d / sub).parent.mkdir(parents=True, exist_ok=True)
        (d / sub).write_text(json.dumps(row, ensure_ascii=False) + "\n")
    for f in ("a.webp", "b.webp", "av.webp", "p1.webp"):
        p = d / "collected/r/images/555" / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f.encode())
    return PB.Shop("fairwardgolf", str(tmp_path))


IDS = {"publications": ["gid://shopify/Publication/9", "gid://shopify/Publication/10"],
       "location": "gid://shopify/Location/1"}


def test_publish_creates_then_skips_then_updates_keeping_photos(tmp_path):
    shop = _shop(tmp_path)
    assert shop.ready() == [KEY]
    products, files = FakeProducts(), FakeFiles()
    row = PB.publish_one(shop, KEY, products, files, IDS)
    payload, pid = products.sent[0]
    assert row["status"] == "published" and row["created"] and pid is None
    assert payload["handle"] == "callaway-reva-complete-set-2"           # taken by another product
    assert products.staged == ["a.webp", "b.webp"] and products.published == [("gid://shopify/Product/1",
                                                                                IDS["publications"])]
    assert files.created[:2] == ["av.webp", "p1.webp"] and files.created[2].startswith("fairwardgolf-reviews-555-")
    assert row["admin_url"] == "https://admin.shopify.com/store/93r1y5-tt/products/1"
    assert PB.publish_one(shop, KEY, products, files, IDS)["status"] == "skipped"
    assert len(products.sent) == 1
    PB.publish_one(shop, KEY, products, files, IDS, force=True)
    payload, pid = products.sent[1]
    assert pid == "gid://shopify/Product/1" and "handle" not in payload        # an update keeps the shop's
    assert [f.get("id") for f in payload["files"]] == ["gid://shopify/MediaImage/1", "gid://shopify/MediaImage/2"]
    assert products.staged == ["a.webp", "b.webp"]                       # no second upload
    assert files.created.count("av.webp") == 1                           # review files once (files.jsonl)
    assert products.deleted == ("gid://shopify/Product/1", [("custom", "required_selections")])  # what is gone


def test_publish_updates_a_product_already_in_the_shop(tmp_path):
    shop = _shop(tmp_path)
    products = FakeProducts({KEY: "gid://shopify/Product/77"})
    PB.publish_one(shop, KEY, products, FakeFiles(), IDS)
    assert products.sent[0][1] == "gid://shopify/Product/77"


def test_dry_run_sends_nothing(tmp_path):
    shop = _shop(tmp_path)
    row = PB.publish_one(shop, KEY, None, None, {}, dry_run=True)
    assert row["status"] == "dry-run" and os.path.exists(row["payload"])
    assert not os.path.exists(shop.ledger_path)


def test_text_field_without_a_limit_or_label():
    prepared, translated, placement = _product()
    prepared["product"]["personalization"] = [
        {"label_ko": "이름", "required": False, "max_length": None, "placeholder_ko": None},
        {"label_ko": "없는", "required": True, "max_length": 5, "placeholder_ko": "입력"}]
    translated["en"][text_id("text_label", "없는")] = "  "
    fields = json.loads(_mf(_build(prepared, translated, placement)["metafields"], "custom",
                            "personalization_fields")["value"])["fields"]
    assert len(fields) == 1 and fields[0]["constraints"] == {} and fields[0]["placeholder"] is None


def test_only_paid_addons_leave_the_site_field_out_and_mark_it_stale():
    prepared, translated, placement = _product()
    prepared["product"]["addons"] = [a for a in prepared["product"]["addons"] if a["price_krw"]]
    out = _build(prepared, translated, placement)
    assert _mf(out["metafields"], "custom", "optional_addons") is None
    assert _mf(out["metafields"], "fairwardgolf", "addons") is not None
    assert ("custom", "optional_addons") in sp.stale(out) and ("custom", "review") not in sp.stale(out)


def test_a_retry_after_a_failed_create_updates_the_product_it_made(tmp_path):
    shop = _shop(tmp_path)
    products = FakeProducts()
    products.owners = {"callaway-reva-complete-set": ("gid://shopify/Product/5", KEY)}     # made, no ledger line
    PB.publish_one(shop, KEY, products, FakeFiles(), IDS)
    assert products.sent[0][1] == "gid://shopify/Product/5" and "handle" not in products.sent[0][0]


def test_a_failed_photo_is_sent_again_next_run(tmp_path):
    shop = _shop(tmp_path)
    products = FakeProducts()
    products.failed_media = (2,)
    row = PB.publish_one(shop, KEY, products, FakeFiles(), IDS)
    assert row["digest"] is None and [p["media_id"] for p in row["photos"]] == ["gid://shopify/MediaImage/1"]
    PB.publish_one(shop, KEY, products, FakeFiles(), IDS)                               # not skipped
    files = products.sent[1][0]["files"]
    assert files[0] == {"id": "gid://shopify/MediaImage/1", "alt": files[0]["alt"]} and "originalSource" in files[1]


def test_contract_edges_keys_labels_rows():
    prepared, translated, placement = _product()
    prepared["product"]["addons"] = [{"group_ko": "장갑", "name_ko": "L", "price_krw": 0, "required": False}] * 2
    prepared["product"]["personalization"] = [{"label_ko": "이름", "required": True, "max_length": True,
                                               "placeholder_ko": "입력"}] * 2
    translated["en"][text_id("addon_group", "장갑")] = "\ufeffGlove "
    prepared["product"]["reviews"] += [{"id": None, "score": 5, "created_at": "2026-01-01T00:00:00Z"},
                                       {"id": 88, "score": None, "created_at": "2026-01-01T00:00:00Z"},
                                       {"id": 99, "score": 4, "created_at": None}]
    mfs = _build(prepared, translated, placement)["metafields"]
    group = json.loads(_mf(mfs, "custom", "optional_addons")["value"])["groups"][0]
    assert group["label"] == "Glove" and len({c["key"] for c in group["choices"]}) == 2
    fields = json.loads(_mf(mfs, "custom", "personalization_fields")["value"])["fields"]
    assert len({f["key"] for f in fields}) == 2 and all(f["constraints"] == {} for f in fields)
    rows = json.loads(_mf(mfs, "custom", "reviews_seo")["value"])
    assert [r["source"]["reviewId"] for r in rows] == ["77"]                    # the three broken rows left out


def test_a_variant_value_not_among_the_options_holds_the_product():
    prepared, translated, placement = _product()
    prepared["product"]["variants"][0]["options_ko"] = ["빨강 ", "1번"]
    with pytest.raises(sp.PayloadError):
        _build(prepared, translated, placement)


def test_deduplicated_values_stay_within_shopifys_length():
    assert [len(v) for v in sp._unique(["x" * 300, "x" * 300])] == [255, 255]


def test_an_option_name_never_holds_a_spaced_slash():
    prepared, translated, placement = _product()
    translated["en"][text_id("option_name", "색상")] = "Color / Flex"
    assert _build(prepared, translated, placement)["productOptions"][0]["name"] == "Color/Flex"


def test_vendor_company_form_cut_and_the_shops_spelling_used():
    assert sp.vendor_name("Prokenex / SJG Co., Ltd.") == "Prokenex"
    assert sp.vendor_name("Acme Inc.") == "Acme" and sp.vendor_name("PING") == "PING"
    assert sp.vendor_name("CALLAWAY", {"callaway": "Callaway"}) == "Callaway"


def test_a_title_without_its_brand_gets_it_in_front_but_not_the_tenants_name():
    prepared, translated, placement = _product()
    translated["en"][text_id("title", prepared["product"]["title_ko"])] = "Men's Beginner Golf Club Set"
    out = _build(prepared, translated, placement)
    assert out["title"] == "Callaway Men's Beginner Golf Club Set"
    out = _build(prepared, translated, placement, tenant="Callaway")
    assert out["title"] == "Men's Beginner Golf Club Set"


def test_select_prefix_out_of_option_names_and_rating_only_rows_out_of_the_feed():
    prepared, translated, placement = _product()
    translated["en"][text_id("option_name", "색상")] = "Select Driver (REAX MR 50)"
    prepared["product"]["reviews"].append({"id": "78", "score": 5, "text_ko": "", "created_at": "2026-01-01T00:00:00Z",
                                           "writer": "x", "avatar": None, "photos": []})
    out = _build(prepared, translated, placement)
    assert out["productOptions"][0]["name"] == "Driver (REAX MR 50)"
    assert [r["source"]["reviewId"] for r in json.loads(_mf(out["metafields"], "custom", "reviews_seo")["value"])] \
        == ["77"]


def test_rehandle_sends_the_new_handle_with_a_redirect(tmp_path):
    shop = _shop(tmp_path)
    products = FakeProducts()
    products.owners = {}
    PB.publish_one(shop, KEY, products, FakeFiles(), IDS)
    PB.publish_one(shop, KEY, products, FakeFiles(), IDS, rehandle=True)
    payload, pid = products.sent[1]
    assert pid == "gid://shopify/Product/1" and payload["handle"] == "callaway-reva-complete-set"
    assert payload["redirectNewHandle"] is True


def test_weight_from_the_description_images_range():
    v = {"package": {"package_weight_g": {"confidence": 2, "source": "description_image",
                                          "value": {"min": 8000, "max": 8655}}}}
    assert sp._weight_g(v) == 8655 and sp._weight_g({"package": {"package_weight_g": {"value": 4200}}}) == 4200
    assert sp._weight_g({"package": {}}) is None


def test_pilot_payload_rules():
    assert sp.clean_title("Tour Edge Edge Complete Set") == "Tour Edge Complete Set"
    assert sp.clean_title("Bridgestone BG-100 BG100 Set (Parallel Import)") == "Bridgestone BG-100 Set"
    assert sp.vendor_name("Mizuno, Hillcreek") == "Mizuno"
    assert sp.close_review("Lightweight and") == "Lightweight." and sp.close_review("Great, but?") == "Great, but?"
    assert sp.close_review("The design looks sharp, and") == "The design looks sharp."
    assert sp._text_label("Name to Attach (ex. John Doe)") == "Name to Attach (e.g., John Doe)"
    assert sp._value("01. 12 pcs Black") == "12 pcs Black" and sp._value("SPEC 10.5 R") == "10.5 R"
    assert sp._value("10.5°") == "10.5°" and sp._value("9.5° / R") == "9.5° / R" and sp._value("3) Red") == "Red"


def test_one_variant_named_by_its_remaining_choice_and_required_free_choice():
    prepared, translated, placement = _product(options=False, available=(True,))
    prepared["product"]["facts"] = [{"label_ko": "세트", "value_ko": "12P 캐디백"}]
    prepared["product"]["addons"] = [
        {"group_ko": "유틸", "name_ko": n, "price_krw": 0, "required": True} for n in ("4번", "5번", "추가안함")]
    translated["en"].update(_en([("fact_label", "세트", "Set"), ("fact_value", "12P 캐디백", "12 Pcs + Caddie Bag"),
                                 ("addon_group", "유틸", "Hybrid"), ("addon_name", "4번", "#4"),
                                 ("addon_name", "5번", "#5"), ("addon_name", "추가안함", "Do not add")]))
    out = _build(prepared, translated, placement)
    assert out["productOptions"] == [{"name": "Set", "values": [{"name": "12 Pcs + Caddie Bag"}]}]
    must = json.loads(_mf(out["metafields"], "custom", "required_selections")["value"])
    assert [v["label"] for v in must["groups"][0]["values"]] == ["#4", "#5"] and len(must["revision"]) == 64
    assert _mf(out["metafields"], "custom", "optional_addons") is None
    assert out["seo"]["title"] == out["title"][:70]


# ---- the owner's answers after the 100-product pilot (2026-11-09) ----------------------------------------------

def test_brand_spelled_as_the_vendor_whatever_the_case_in_the_title():
    prepared, translated, placement = _product()
    translated["en"][text_id("title", prepared["product"]["title_ko"])] = "CALLAWAY REVA Complete Set"
    assert _build(prepared, translated, placement)["title"] == "Callaway REVA Complete Set"
    translated["en"][text_id("brand", "캘러웨이")] = "callaway"
    out = _build(prepared, translated, placement, vendors={"callaway": "CALLAWAY"})
    assert out["vendor"] == "CALLAWAY" and out["title"] == "CALLAWAY REVA Complete Set"


def test_vendor_spellings_take_the_dictionarys_case(monkeypatch):
    import translation_dicts
    monkeypatch.setattr(translation_dicts.Dictionaries, "__init__", lambda self: setattr(
        self, "entries", {"brand": {"핑": "PING", "요넥스": "Yonex"}}))
    out = PB.vendor_spellings({"ping": "Ping", "yonex": "YONEX", "acme": "ACME"})
    assert out == {"ping": "PING", "yonex": "Yonex", "acme": "ACME"}


def test_price_and_platform_sentences_out_and_photo_only_rows_get_a_line():
    prepared, translated, placement = _product()
    reviews = prepared["product"]["reviews"]
    reviews[0]["text_ko"] = "가볍고 좋아요. 가성비 최고"
    reviews.append({"id": "79", "score": 4, "text_ko": "", "created_at": "2026-01-02T00:00:00Z", "writer": "y",
                    "avatar": None, "photos": ["collected/r/images/555/p1.webp"]})
    reviews.append({"id": "80", "score": 5, "text_ko": "11번가", "created_at": "2026-01-03T00:00:00Z", "writer": "z",
                    "avatar": None, "photos": []})
    translated["en"].update(_en([("review", "가볍고 좋아요. 가성비 최고", "It's light and good. Great value for the price!"),
                                 ("review", "11번가", "A bit cheaper on 11st.")]))
    urls = {f: f"https://cdn/{os.path.basename(f)}" for f in sp.review_files(prepared)}
    rows = sp.reviews(prepared, sp.English(translated), urls)
    assert [r["description"] for r in rows][:1] == ["It's light and good."]
    assert len(rows) == 2 and rows[1]["description"] in sp.PHOTO_ONLY_TEXTS            # 80: nothing left, no photo
    assert rows[1]["description"] == sp.photo_only_text("79")                           # stable per review


def test_review_photos_fill_a_thin_gallery_up_to_five():
    prepared, _, _ = _product()
    assert sp.review_gallery(prepared) == []                                            # 2 photos of its own
    p = prepared["product"]
    p["images"] = p["images"][:1]
    p["reviews"] = [{"id": str(i), "score": s, "photos": [f"r{i}a.webp", f"r{i}b.webp"], "text_quality": q,
                     "text_grade": "full"} for i, s, q in ((1, 5, 10), (2, 3, 90), (3, 4, 40), (4, 5, 40), (5, 5, 20))]
    assert sp.review_gallery(prepared) == ["r4a.webp", "r3a.webp", "r5a.webp", "r1a.webp"]   # 4+, best first, 5 in all
    assert sp.review_gallery(prepared, skip={"r3a.webp"}) == ["r4a.webp", "r3b.webp", "r5a.webp", "r1a.webp"]
    p["images"] = []                                     # none of its own: 5, a second round of photos after one each
    assert sp.review_gallery(prepared) == ["r4a.webp", "r3a.webp", "r5a.webp", "r1a.webp", "r4b.webp"]


def test_review_rank_prefers_several_photos_and_drops_purchase_snapshots():
    one = {"id": "1", "score": 5, "photos": ["a"], "text_quality": 60, "text_grade": "full"}
    many = {"id": "2", "score": 5, "photos": ["b", "c", "d"], "text_quality": 40, "text_grade": "full"}
    assert sp.review_rank(many) > sp.review_rank(one)                                   # the owner: several photos
    assert sp.review_rank({**one, "score": 3}) is None and sp.review_rank({**one, "score": True}) is None
    assert sp.review_rank({**one, "text_grade": "rating_only"}) is None                 # one photo, no words
    assert sp.review_rank({**one, "text_cut": ["packing"]}) is None                     # the box it came in
    assert sp.review_rank({**many, "text_cut": ["seller"]}) < sp.review_rank(many)
    assert sp.review_rank({**one, "text_grade": "short"}) < sp.review_rank({**one, "text_grade": "full"})


def test_review_gallery_skips_shown_small_and_strip_photos():
    prepared, _, _ = _product()
    p = prepared["product"]
    p["images"] = p["images"][:1]                                                       # sha "a" * 64
    p["reviews"] = [{"id": str(i), "score": 5, "photos": [f"p{i}"], "text_quality": 50 - i, "text_grade": "full"}
                    for i in range(6)]
    info = {"p0": {"sha256": "a" * 64, "width": 800, "height": 800},                    # the product's own photo
            "p1": {"sha256": "x", "width": 300, "height": 900},                         # too small
            "p2": {"sha256": "y", "width": 2400, "height": 600},                        # a strip
            "p3": {"sha256": "z", "width": 900, "height": 1200},
            "p4": {"sha256": "z", "width": 900, "height": 1200},                        # the same photo again
            "p5": {"sha256": "g", "width": 900, "height": 1200, "green": 0.4}}          # a course
    assert sp.review_gallery(prepared, info) == ["p3"]
    p["reviews"][1]["photos"] = ["p1", "p2", "p6"]                                      # its third photo is tried
    assert sp.review_gallery(prepared, info) == ["p6", "p3"]


def test_review_rank_counts_helpful_votes():
    r = {"id": "1", "score": 5, "photos": ["a"], "text_quality": 40, "text_grade": "full"}
    assert sp.review_rank({**r, "likes": 2}) > sp.review_rank(r)
    assert sp.review_rank({**r, "text_cut": ["price"]}) == sp.review_rank(r)          # a price remark is no box


def test_a_struck_out_gallery_photo_publishes_the_product_again(tmp_path):
    shop = _shop(tmp_path)
    prepared, translated, placement = shop.inputs()[0][KEY], shop.inputs()[1][KEY], shop.inputs()[2][KEY]
    a = PB.inputs_digest(prepared, translated, placement, "fairwardgolf", [{"file": "x", "sha256": "1"}])
    assert a != PB.inputs_digest(prepared, translated, placement, "fairwardgolf", [])

# ---- title length (Google Merchant Center: 150 characters; 2026-11-10) -------------------------------------------

def test_fit_title_cuts_whole_facts_then_whole_words():
    t = "PING GLE2 Yonex Elite Mixed Women's Complete Golf Set, 10 Pieces, Driver, Hybrid, 7 Irons, Putter"
    assert sp.TITLE_MAX == 150 and sp.SEO_TITLE_MAX == 70                    # Google Merchant Center; the page title
    assert sp.fit_title(t) == t and sp.fit_title("  A   B ") == "A B"
    assert sp.fit_title(t, 90) == "PING GLE2 Yonex Elite Mixed Women's Complete Golf Set, 10 Pieces, Driver, Hybrid, 7 Irons"
    assert sp.fit_title("A B Complete Golf Set, 10 Pieces, Caddie Bag", 40) == "A B Complete Golf Set, 10 Pieces"   # a fact whole
    assert sp.fit_title(t, 48) == "PING GLE2 Yonex Elite Mixed Women's Complete"                 # words, never "Go"
    assert sp.fit_title("Callaway REVA Women's Set with Bag and Putter", 30) == "Callaway REVA Women's Set"     # no "with"
    assert sp.fit_title("X" * 200, 150) == "X" * 150
    # a comma early in the title does not take the rest with it
    early = "PING G430 Max, Men's Complete Golf Set 12 Pieces with Caddie Bag and Mallet Putter"
    assert sp.fit_title(early, 70) == "PING G430 Max, Men's Complete Golf Set 12 Pieces with Caddie Bag"
    # no count without its unit, no joining word, no open bracket; a model's "Plus" stays
    assert sp.fit_title("Honma Mutsumi Special 3-Star Women's High-COR Complete Golf Set 13 Pieces", 70) \
        == "Honma Mutsumi Special 3-Star Women's High-COR Complete Golf Set"
    assert sp.fit_title("PRGR Sweep M15 Women's Complete Set 12 Pcs With Caddie Bag Made in Japan", 70) \
        == "PRGR Sweep M15 Women's Complete Set 12 Pcs With Caddie Bag"
    assert sp.fit_title("PING G440 Bridgestone V300 Mixed Men's Complete Golf Set 2025 11 Pieces", 70) \
        == "PING G440 Bridgestone V300 Mixed Men's Complete Golf Set 2025"                      # the year stays
    assert sp.fit_title("TaylorMade Stealth 2 Plus Men's Driver 10.5 Degrees Stiff", 27) == "TaylorMade Stealth 2 Plus"
    assert sp.fit_title("Callaway REVA Women's Set (Driver, Hybrid, 7 Irons, Putter)", 50) == "Callaway REVA Women's Set"
    for source in (t + " " + t, early + " and more words to cut here", t.replace(",", "")):
        for limit in range(20, 160):
            out = sp.fit_title(source, limit)
            assert 0 < len(out) <= limit and source.startswith(out) and out == out.strip(" ,")
            assert source[len(out):len(out) + 1] in ("", " ", ",")                               # a whole word


def test_a_long_title_is_published_within_googles_limit():
    prepared, translated, placement = _product()
    long = "REVA 2027 Women's Complete Golf Club Set 10 Pieces " + "Graphite Lightweight Steel Black Bag " * 4
    translated["en"][text_id("title", prepared["product"]["title_ko"])] = long
    out = _build(prepared, translated, placement)
    assert out["title"].startswith("Callaway REVA 2027") and len(out["title"]) <= 150            # the brand counted
    assert out["title"].endswith("Black Bag Graphite Lightweight Steel Black Bag Graphite")      # a whole word, 143
    assert out["seo"]["title"] == "Callaway REVA 2027 Women's Complete Golf Club Set 10 Pieces Graphite"   # 68, a word
    assert all(len(f["alt"]) <= sp.ALT_MAX for f in out["files"]) and len(out["handle"]) <= sp.HANDLE_MAX
    # the brand only in the part cut off: it goes in front after the cut
    filler = " ".join(f"Part{n:02d}" for n in range(25))
    translated["en"][text_id("title", prepared["product"]["title_ko"])] = f"Women's Complete Golf Set {filler} by Callaway"
    title = _build(prepared, translated, placement)["title"]
    assert title.startswith("Callaway Women's Complete Golf Set Part00") and len(title) <= 150


# ---- the real titles of the store (fixtures/titles/golf_50002788.jsonl: the 105 products published 2026-11-10;
#      title_ko / brand_ko, the translation `en` / `brand_en`, the published `title` / `vendor` / `seo`, and for two
#      products `en_long`: the 116- and 137-character titles the model wrote before the length rule) -----------------

def _real_titles():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "titles", "golf_50002788.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_real_titles_are_published_as_recorded():
    rows = _real_titles()
    vendors = {r["vendor"].lower(): r["vendor"] for r in rows}             # the brand dictionary's spellings
    assert len(rows) == 105
    for r in rows:
        ids = {text_id("title", r["title_ko"]): r["en"]}
        if r["brand_ko"]:
            ids[text_id("brand", r["brand_ko"])] = r["brand_en"]
        title, vendor = sp.title_vendor({"title_ko": r["title_ko"], "brand_ko": r["brand_ko"]}, sp.English({"en": ids}),
                                        vendors, "Fairward Golf")
        assert (title, vendor) == (r["title"], r["vendor"]), r["id"]
        assert len(title) <= sp.TITLE_MAX and sp.fit_title(title) == title, r["id"]      # none is cut for Google
        assert sp.fit_title(title, sp.SEO_TITLE_MAX) == r["seo"], r["id"]                # the page title, as recorded


def test_real_titles_cut_to_any_length_stay_whole():
    for r in _real_titles():
        for source in [r["title"]] + ([r["en_long"]] if r.get("en_long") else []):
            for limit in range(30, 151, 3):
                out = sp.fit_title(source, limit)
                assert 0 < len(out) <= limit and source.startswith(out), (r["id"], limit, out)
                assert source[len(out):len(out) + 1] in ("", " ", ","), (r["id"], limit, out)        # a whole word
                assert not re.search(r"(?:[,;:/&+-]|\b(?:with|and|for|in|of|the|to|or|made))$", out, re.I), (limit, out)
                assert out.count("(") == out.count(")"), (r["id"], limit, out)


def test_the_two_real_long_titles_within_googles_limit():
    long = {r["id"]: r["en_long"] for r in _real_titles() if r.get("en_long")}
    assert sorted(len(t) for t in long.values()) == [116, 137]
    assert sp.fit_title(long["8514409092"]) == long["8514409092"]                         # 137: Google takes it whole
    assert sp.fit_title(long["8514409092"], 100) == ("GV Tour 2026 New Great Victory Complete Golf Club Set for Beginner "
                                                     "to Intermediate Men's and Women's")
    assert sp.fit_title(long["8514409092"], 70) == "GV Tour 2026 New Great Victory Complete Golf Club Set for Beginner"
    assert sp.fit_title(long["6655509590"], 100) == ("Mutsumi Honma Premium Gold 2-Star High-Rebound Women's Mixed "
                                                     "Complete Set 10 Pcs Driver Wood 7-Piece")


def test_a_dry_run_spells_the_vendor_as_the_real_run(tmp_path):
    """2026-11-11: a dry run without the store wrote "maruman" and "Fairward Golf <title>"; it takes the brand
    dictionary's spellings and the tenant's name offline."""
    ids = PB.offline_ids("fairwardgolf")
    assert ids["tenant"] == "Fairward Golf" and ids["vendors"].get("maruman") == "Maruman"
