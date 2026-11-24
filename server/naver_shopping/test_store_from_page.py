"""The store record a product page leaves (2026-11-24: the curl store page login-gated), offline."""
import os

import pytest

import cache
from naver_shopping import api
from naver_shopping.fetch import NaverBlocked

PAGE = os.path.join(os.path.dirname(__file__), "fixtures", "product_page_channel.html")


@pytest.fixture(autouse=True)
def fresh_cache():
    cache._store.clear()
    yield
    cache._store.clear()


def gated(store):
    raise NaverBlocked("login gate on store mild9700")


def test_a_product_page_leaves_its_store_record():
    with open(PAGE, encoding="utf-8") as f:
        assert api.remember_store_from_page(f.read()) == "mild9700"
    seen = cache.peek("naver_shopping.store_seen", {"slug": "mild9700"})["store"]
    assert (seen["uid"], seen["merchant_id"], seen["slug"]) == ("2sWDvkfSuoCYc2dnM4UMc", "500124160", "mild9700")
    assert api.remember_store_from_page("<html>no state</html>") is None and api.remember_store_from_page(None) is None


def test_a_login_gated_store_falls_back_to_the_page_record_only(monkeypatch):
    monkeypatch.setattr(api, "_store", gated)
    with pytest.raises(NaverBlocked):                       # nothing seen yet: the gate stands
        api._product_store("mild9700")
    with open(PAGE, encoding="utf-8") as f:
        api.remember_store_from_page(f.read())
    assert api._product_store("mild9700")["uid"] == "2sWDvkfSuoCYc2dnM4UMc"
    with pytest.raises(NaverBlocked):                       # another store: no record of it
        api._product_store("other")

    def walled(store):
        raise NaverBlocked("HTTP 429 (captcha / rate wall) on store other")
    monkeypatch.setattr(api, "_store", walled)
    with pytest.raises(NaverBlocked):                       # a captcha / rate wall is never covered
        api._product_store("other")


def test_a_cached_store_page_wins_and_a_seen_store_sends_no_gated_request(monkeypatch):
    with open(PAGE, encoding="utf-8") as f:
        api.remember_store_from_page(f.read())
    monkeypatch.setattr(api, "_store", lambda store: pytest.fail("a seen store is not fetched"))
    assert api._product_store("mild9700")["uid"] == "2sWDvkfSuoCYc2dnM4UMc"
    cache.cached_call("naver_shopping.store", {"store": "https://smartstore.naver.com/mild9700"},
                      lambda store: {"store": {"uid": "from-best"}}, api.ttl.STORE_CACHE)
    assert api._product_store("mild9700")["uid"] == "from-best"


def test_a_brand_store_is_kept_under_its_url_and_its_brand_link():
    """2026-11-24 review: a brand store's channel url (ibs) is not its link's slug (drbrian)."""
    with open(os.path.join(os.path.dirname(__file__), "fixtures", "brand_product_drbrian.html"), encoding="utf-8") as f:
        assert api.remember_store_from_page(f.read()) == "ibs"
    assert cache.peek("naver_shopping.store_seen", {"slug": "drbrian"})["store"]["slug"] == "ibs"


def test_peek_never_runs_anything():
    assert cache.peek("naver_shopping.store_seen", {"slug": "nobody"}) is None
