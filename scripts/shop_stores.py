"""Our Shopify stores: who publishes the photos we prepare, and where the
store's catalog is read.

The photo pipeline (naver_images + image_prep) is the same for every store;
only these values differ. Each prepared WebP carries the store as its
publisher (XMP dc:publisher + dc:source) and file names start with its id.
The store is not the product's brand and never claims authorship or copyright.

`shopify` is where shopify_catalog reads the store (the "already in the shop"
check): the *.myshopify.com domain, the shop id the API must answer with, the
Admin API version, the env variable (in the repo-root .env) that holds the PATH
of the store app's credentials file (client id + secret, mode 0600, ignored by
git; a 24 h token is minted from them each run, never stored) and the
metafield namespace of the source key. None for a store whose values the
operator has not given yet: the check stops there and asks for them.

Add a store: one StoreId member and its STORES entry (test_shop_stores.py
checks that every member has one). Pick the store per run with SHOP_STORE in
the repo-root .env (loaded here too), or pass it to get_store().

    from shop_stores import get_store
    store = get_store()                  # SHOP_STORE, else fairwardgolf
"""
import os
from dataclasses import dataclass
from enum import StrEnum

from naver_api_client import load_env_file

load_env_file()                          # SHOP_STORE from the repo-root .env, the shell wins


class StoreId(StrEnum):
    FAIRWARDGOLF = "fairwardgolf"
    SKINSLI = "skinsli"
    KYOBOOKS = "kyobooks"
    BANAFISH = "banafish"


@dataclass(frozen=True)
class Shopify:
    domain: str                          # <name>.myshopify.com
    shop_id: str                         # gid://shopify/Shop/<n>, checked before every read
    api_version: str                     # Admin API version, e.g. 2026-07
    credentials_env: str                 # env variable with the path of the app's client id / secret file
    namespace: str                       # metafield namespace of the source key (<namespace>.source_offer_id)


@dataclass(frozen=True)
class Store:
    id: StoreId
    publisher: str                       # XMP dc:publisher
    site: str                            # XMP dc:source, https://...
    shopify: Shopify | None = None       # None: the operator has not given this store's values yet

    @property
    def file_prefix(self) -> str:
        return self.id.value


STORES = {
    StoreId.FAIRWARDGOLF: Store(StoreId.FAIRWARDGOLF, "Fairward Golf", "https://fairwardgolf.com",
                                Shopify("93r1y5-tt.myshopify.com", "gid://shopify/Shop/70701744195", "2026-07",
                                        "SHOPIFY_CREDENTIALS_FAIRWARDGOLF", "fairwardgolf")),
    StoreId.SKINSLI: Store(StoreId.SKINSLI, "SKINSLI", "https://skinsli.com"),
    StoreId.KYOBOOKS: Store(StoreId.KYOBOOKS, "KyoBooks", "https://kyobooks.com"),
    StoreId.BANAFISH: Store(StoreId.BANAFISH, "BanaFish", "https://banafish.store"),
}
DEFAULT = StoreId.FAIRWARDGOLF
ENV = "SHOP_STORE"


def get_store(value: "str | StoreId | None" = None) -> Store:
    """The store `value` names, else SHOP_STORE from the environment, else DEFAULT."""
    key = value or os.environ.get(ENV) or DEFAULT
    try:
        return STORES[StoreId(str(key).strip().lower())]
    except ValueError:
        raise ValueError(f"unknown store {key!r}; known: {', '.join(s.value for s in StoreId)}") from None
