"""store_diff.compare and publish.output_digest (2026-11-11): what a publication would change in the store."""
import copy

import publish as P
from store_diff import compare

PAYLOAD = {"title": "Junior Putter", "vendor": "Skulldog", "productType": "Junior Golf Clubs & Sets", "status": "ACTIVE",
           "tags": ["a", "b"], "descriptionHtml": "<p>x</p>", "seo": {"title": "Junior Putter"},
           "productOptions": [{"name": "Age", "values": [{"name": "Ages 5-8"}, {"name": "Ages 9-12"}]}],
           "variants": [{"sku": "FW-1", "price": "259.00", "optionValues": [{"optionName": "Age", "name": "Ages 5-8"}],
                         "metafields": [{"namespace": "fairwardgolf", "key": "price", "value": '{"a": 1}'}]},
                        {"sku": "FW-2", "price": "279.00", "optionValues": [{"optionName": "Age", "name": "Ages 9-12"}],
                         "metafields": []}],
           "metafields": [{"namespace": "fairwardgolf", "key": "source", "value": '{"k": 1}'},
                          {"namespace": "custom", "key": "reviews_feed_url", "value": "dry-run:x"}],
           "handle": "junior-putter"}
FEED = "0123456789abcdef01234567"


def live(**change):
    out = {"title": "Junior Putter", "vendor": "Skulldog", "productType": "Junior Golf Clubs & Sets",
           "status": "ACTIVE", "tags": ["b", "a"], "descriptionHtml": "<p>x</p>", "seo": {"title": "Junior Putter"},
           "options": [{"name": "Age", "values": ["Ages 9-12", "Ages 5-8"]}],      # Shopify's own order
           "variants": {"nodes": [
               {"sku": "FW-1", "price": "259.0", "selectedOptions": [{"name": "Age", "value": "Ages 5-8"}],
                "metafields": {"nodes": [{"namespace": "fairwardgolf", "key": "price", "value": '{"a":1}'}]}},
               {"sku": "FW-2", "price": "279.0", "selectedOptions": [{"name": "Age", "value": "Ages 9-12"}],
                "metafields": {"nodes": []}}]},
           "metafields": {"nodes": [
               {"namespace": "fairwardgolf", "key": "source", "value": '{"k":1}'},
               {"namespace": "custom", "key": "reviews_feed_url",
                "value": f"https://cdn.shopify.com/s/files/1/x/fairwardgolf-reviews-1-{FEED}.json?v=1"}]}}
    out.update(change)
    return out


def test_the_same_product_has_nothing_to_change():
    assert compare(PAYLOAD, live(), FEED, ["s1"], ["s1"]) == []


def test_each_kind_of_change_is_named():
    assert compare(PAYLOAD, live(vendor="PING"), FEED, ["s1"], ["s1"]) == ["vendor: 'PING' -> 'Skulldog'"]
    assert compare(PAYLOAD, live(), "f" * 24, ["s1"], ["s1"]) == ["reviews feed"]
    assert compare(PAYLOAD, live(), FEED, ["s1", "s2"], ["s1"]) == ["photos: 1 -> 2"]
    cheaper = copy.deepcopy(live())
    cheaper["variants"]["nodes"][0]["price"] = "239.00"
    assert compare(PAYLOAD, cheaper, FEED, ["s1"], ["s1"]) == ["price FW-1: 239.00 -> 259.00"]
    extra = copy.deepcopy(live())
    extra["metafields"]["nodes"].append({"namespace": "custom", "key": "optional_addons", "value": "[]"})
    assert compare(PAYLOAD, extra, FEED, ["s1"], ["s1"]) == ["custom.optional_addons (deleted)"]


def test_the_output_digest_leaves_the_handle_out():
    assert P.output_digest(PAYLOAD) == P.output_digest({**PAYLOAD, "handle": "another"})
    assert P.output_digest(PAYLOAD) != P.output_digest({**PAYLOAD, "title": "Junior Putter 2"})
