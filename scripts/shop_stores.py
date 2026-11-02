"""Our Shopify stores: who publishes the photos we prepare.

The photo pipeline (naver_images + image_prep) is the same for every store;
only these values differ. Each prepared WebP carries the store as its
publisher (XMP dc:publisher + dc:source) and file names start with its id.
The store is not the product's brand and never claims authorship or copyright.

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
class Store:
    id: StoreId
    publisher: str                       # XMP dc:publisher
    site: str                            # XMP dc:source, https://...

    @property
    def file_prefix(self) -> str:
        return self.id.value


STORES = {
    StoreId.FAIRWARDGOLF: Store(StoreId.FAIRWARDGOLF, "Fairward Golf", "https://fairwardgolf.com"),
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
