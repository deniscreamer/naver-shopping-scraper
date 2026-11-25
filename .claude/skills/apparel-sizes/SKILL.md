---
name: apparel-sizes
description: Apparel sizes in the fairwardgolf store: Korean size labels (90, M(90), S(55), L(55-66), 0(85), FREE) turned into US sizes per product (size_labels.py, size_chart.py, apparel_sizes.py, size_profiles/), the seller's size chart read from the description and the OCR (SIZE_CHARTS.md), the US size chart in the description, and the link to the Naver size the owner orders (variant fairwardgolf.source sizeKo, product fairwardgolf.sizes). Use for "размеры", "US размер", "таблица размеров", "какой размер заказывать на Naver", a product held size_unmapped, a size one up or down, a brand that sizes its own way, a size chart not read or read wrong, or a new apparel category or profile (men's tops, trousers, shoes).
---

# Apparel sizes

The docs: [scripts/SIZES.md](../../../scripts/SIZES.md) (the mechanism, opens with "How to use"),
[scripts/SIZE_CHARTS.md](../../../scripts/SIZE_CHARTS.md) (reading a seller's chart), `scripts/size_profiles/<profile>.md`
(one garment profile: its grid, brand rows, sellers' habits). Rules: the storefront shows US
sizes only, the Korean originals stay in our files and the admin-only metafields (the owner, 2026-11-19); the
product's own label and chart first, the default grid only as the fallback; never a guessed size.

| Task | SIZES.md section |
|---|---|
| A held `size_unmapped`, a merged note, the owner's "which Naver size" | "How to use" |
| A Japanese letter (O, XO, SS), a "ㅡ" dash, a gender + colour + size value, one chest for every size (2026-11-25) | "How to use": the rows of 2026-11-25 |
| The owner answered how one held product is sized (gender, read as, the size sold, two spellings one size) | "How to use": the `sizes` block of `variants_by_owner.json` (2026-11-25) |
| What a product gives the converter | "The inputs" |
| Why a value got its US size (`basis`) | "The order"; the grid: `size_profiles/<profile>.md` |
| What Shopify gets (option, metafields, chart block) | "What the store gets" |
| A chart not read, a half or double chest, a number that is no measurement | SIZE_CHARTS.md "How to use", "When a chart is not read" |
| A brand row, a rule change | "Changing it" |
| Another garment (trousers, shoes, men's tops) | "Adding a profile" |

1. **Look**: `.venv/bin/python scripts/shop_view.py show <shop> <ref> --raw prepared --path product.sizes` (the
   values, `basis`, the chart in cm); the page's chart: `--raw prepared --path product.description_ko` and the OCR
   sidecar (`description_images/<pid>.json`).
2. **Prove** a wrong size from the seller's chart or label, never from a photo alone.
3. **Fix** at the source: a brand row in the profile's `size_profiles/<profile>.json` (with its evidence and date, and
   a line in its `.md`), or the rule in `size_labels.py` / `size_chart.py` / `apparel_sizes.py` with a test in `test_apparel_sizes.py`; a chart the rule misread goes into
   `fixtures/sizes/` (skill `seller-pattern-rule`).
4. **Check**: `.venv/bin/python -m pytest scripts/test_apparel_sizes.py -q`; after a deliberate change
   `UPDATE_GOLDEN=1` and read the diff; then `run_transform.py <shop> --diff` (only the apparel moves) and
   `store_diff.py <shop>`.
5. **Products in the store**: a resend is the owner's word (scripts/OWNER_RULES.md rule 1; skill `store-actions`).
