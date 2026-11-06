"""Offline tests for shop_stores.py: the store registry.

    .venv/bin/python -m pytest scripts/test_shop_stores.py -q
"""
import pytest

from shop_stores import STORES, StoreId, get_store


def test_every_store_id_has_a_profile():
    assert set(STORES) == set(StoreId)
    for key, store in STORES.items():
        assert store.id is key and store.site.startswith("https://") and store.publisher
        assert store.file_prefix == key.value


def test_get_store_by_name_env_and_default(monkeypatch):
    monkeypatch.delenv("SHOP_STORE", raising=False)
    assert get_store().id is StoreId.FAIRWARDGOLF
    monkeypatch.setenv("SHOP_STORE", "skinsli")
    assert get_store().publisher == "SKINSLI"
    assert get_store(" KyoBooks ").site == "https://kyobooks.com"            # an argument wins over the env
    with pytest.raises(ValueError, match="unknown store 'nope'; known: fairwardgolf"):
        get_store("nope")


def test_shopify_values():
    shop = STORES[StoreId.FAIRWARDGOLF].shopify
    assert shop and shop.domain.endswith(".myshopify.com") and shop.shop_id.startswith("gid://shopify/Shop/")
    assert shop.credentials_env == "SHOPIFY_CREDENTIALS_FAIRWARDGOLF" and shop.namespace == "fairwardgolf"
    assert all(s.shopify is None for k, s in STORES.items() if k is not StoreId.FAIRWARDGOLF)   # not given yet
