"""Cache TTL per /naver-shopping/* endpoint (cache.py, keyed on the
validated params). The product record (naver_shopping.product) is ONE
cached bundle of the store-backend answers that products/details and
products/reviews both read, so a client calling both pays one box round
trip for the record and one per review page.
"""
from datetime import timedelta

# Search results reorder with ads and promotions through the day; prices move.
SEARCH_CACHE = timedelta(hours=2)
# The total match count moves slowly.
SEARCH_COUNT_CACHE = timedelta(hours=6)
# Product record: price / stock / options move daily; the description and
# notice rarely.
PRODUCT_CACHE = timedelta(hours=6)
# Review pages: a page re-sorts as reviews arrive; busiest products get a
# few an hour.
REVIEWS_CACHE = timedelta(hours=6)
# Store record (grade, sale count, categories) moves weekly.
STORE_CACHE = timedelta(hours=24)
# Popular / best rails are recomputed by Naver daily.
STORE_PRODUCTS_CACHE = timedelta(hours=12)
# Catalog review samples move with new reviews.
CATALOG_REVIEWS_CACHE = timedelta(hours=12)
# DataLab publishes once a day (yesterday's data appears in the morning).
DATALAB_CACHE = timedelta(hours=24)
# The category tree changes a few times a year.
CATEGORIES_CACHE = timedelta(days=7)
