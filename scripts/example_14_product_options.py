"""Example 14: a product's options and which variants we collect, on real golf full sets.

Step 1 - api.product_specs(link, query)["options"]: what can be bought, read from the product page's own answer
in your Chrome (the adapter; ~30-60 s a product). Every declared variant with its extra price and stock; sold-out
ones are kept with is_available False (the page shows them as (품절)); text options (a text the buyer types, with
its label, required and length limit from the page's field),
simple options, add-ons. `/products/details` has no options since 2026-11-02 (ENDPOINTS.md).
Step 2 - naver_variants.choose_variants(): by default only the variants that keep the product's price; with
`paid` (the operator's choice) also the ones that cost more or less, each with its price.

The cases (the 남성 / 여성 골프채 풀세트 searches, 2026-11-02), one per kind:

  * no options at all (PING G440K set): has_options False, no variants;
  * combinations, all free (GV Tour set: 9 variants);
  * a text option + combinations with a sold-out row (Majesty Royal: 네임택용 성함, 24 variants, 1 sold out);
  * a paid, sold-out variant and a "+" that is not money (Honma D1: S set "D1 500 S+950 S" free, R set +60,000
    sold out);
  * cheaper variants (Callaway REVA: without the bag -100,000, those sold out);
  * only a text the buyer types, no variants (PRGR Sweep: 네임스티커 성함);
  * many combinations whose names join clubs with "+" (TaylorMade Glory: 48 variants, all free);
  * a SIMPLE choice, no combinations (XXIO13 iron set MP1300: 강도 L; from the 골프 아이언 세트 search).

Needs Chrome open with the adapter. A captcha on the way: solve it in that Chrome within 60 s.

    .venv/bin/python scripts/example_14_product_options.py [paid]
"""
import sys

from naver_api_client import ApiError, NaverApiClient
from naver_variants import choose_variants

PAID = len(sys.argv) > 1 and sys.argv[1] == "paid"
MEN, WOMEN, IRONS = "남성 골프채 풀세트", "여성 골프채 풀세트", "골프 아이언 세트"   # searches listing the cards
CASES = [
    ("no options", "https://smartstore.naver.com/scarabee/products/13021362937", MEN),
    ("free combinations", "https://smartstore.naver.com/majorgolf/products/7583123963", MEN),
    ("text option + sold-out row", "https://smartstore.naver.com/samsung-golf/products/12434254421", MEN),
    ("paid + sold-out row, '+' in a name", "https://smartstore.naver.com/thegolf/products/5543745139", MEN),
    ("cheaper rows, sold out", "https://smartstore.naver.com/thegolf/products/13413924099", WOMEN),
    ("a text only, no variants", "https://smartstore.naver.com/adpargolf/products/13751285162", WOMEN),
    ("48 free rows, '+' joins clubs", "https://smartstore.naver.com/thegolf9015/products/10816508198", WOMEN),
    ("a simple choice, no variants", "https://smartstore.naver.com/gatagolf/products/13553833826", IRONS),
]

api = NaverApiClient()
print(f"variants: {'free and paid' if PAID else 'free only (pass paid to take paid ones too)'}\n")
for label, link, query in CASES:
    try:
        details = api.product_details(link)                 # the price; its own options are null since 2026-11-02
        specs = api.product_specs(link, query=query)          # -> naver_types.ProductSpecs, options from the page
    except ApiError as e:
        print(f"[{label}] {link}: {e.status} {e.error}\n")
        continue
    options = specs["options"]
    print(f"[{label}] {(specs['name'] or '')[:60]}")
    if options is None:
        print("  the page gave no product answer: options unknown (not the same as no options)\n")
        continue
    groups = ", ".join(f"{g['name']} ({g['type']})" for g in options["option_groups"]) or "none"
    print(f"  groups: {groups}; product stock {options['stock_quantity']}, sold out: {options['is_sold_out']}")
    choice = choose_variants(options, details["pricing"]["discounted_price"], paid=PAID)
    print(f"  variants: {len(options['variants'])} declared -> {len(choice['variants'])} taken "
          f"({choice['available']} in stock, {choice['sold_out']} sold out), {choice['skipped_paid']} left out as paid"
          + (f", name / price disagree: {choice['name_mismatches']}" if choice["name_mismatches"] else ""))
    for v in choice["variants"][:6]:
        state = "in stock" if v["is_available"] else "SOLD OUT" if v["is_available"] is False else "stock unknown"
        extra = f" ({v['extra_price']:+,})" if v["extra_price"] else ""
        print(f"    - {v['name']}: {v['price']:,} KRW{extra}, {state}" if v["price"] is not None
              else f"    - {v['name']}: price unknown{extra}, {state}")
    for o in choice["simple_options"]:
        print(f"  simple choice: {o['group']} = {o['name']}")
    for t in choice["text_options"]:
        need = "required" if t["required"] else "optional" if t["required"] is False else "required unknown"
        limit = f", at most {t['max_length']} characters" if t["max_length"] else ""
        print(f"  text the buyer types: {t['label'] or t['name']} ({need}{limit})")
    if choice["supplements"]:
        print(f"  add-ons (not variants): {len(choice['supplements'])}")
    print()
