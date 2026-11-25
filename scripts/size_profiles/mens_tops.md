# Profile `mens_tops` (men's tops)

Part of [SIZES.md](../SIZES.md). Data: `mens_tops.json`. Categories: 50002796 golf T-shirts, the men's section
mens-fall-long-sleeve-tops (`CategoryRules.sizes_mens`: a product the seller states men's, 2026-11-21). Labels `kr_tops`,
measures `tops`, fit `chest`. The storefront shows the US letter alone ("M"), no US number.

## The grid (2026-11-21; the review 2026-11-22: each band holds its own chest, the letters the Korean convention)

| KR chest | US | fits chest (in) |
|---|---|---|
| 85 | XXS | 32-34 |
| 90 | XS | 34-36 |
| 95 | S | 36-38 |
| 100 | M | 38-40 |
| 105 | L | 40-42 |
| 110 | XL | 42-44 |
| 115 | XXL | 44-46 |
| 120 | XXXL | 46-48 |

Why: a Korean men's label is the body chest in cm (KS K 0050); 100 cm = 39.4 in, the US M band of men's charts. A
bare Korean letter follows the Korean convention (XS 85, S 90, M 95, L 100, XL / LL 105, XXL / 2XL / 3L 110, XXXL / 3XL
115; 4XL 120 since 2026-11-25, a rain suit's M..4XL 11859489664, read only in this profile, `parse_label` leaves "4XL"
unread): a Korean M is a US S, as "M(95)" is. Japanese makers' O = LL (105) and XO = 3L (110) beside S / M / L, SS =
XS (85) below S in a ladder to LL / 3L (2026-11-25, `size_labels.japanese_ladder`: TaylorMade TL439 11859686166 and
11534592689 M..XO = US S, M, L, XL; Callaway C25989100 11616404746 SS..3L = XXS..XL). Women's sizes (55, 66) mean
nothing here: such a value holds the product.
A unisex top is not in the men's section (`stated_only`): it keeps the women's profile in the women's section.

## Brand rows (`brands`)

- **adidas** (`asian_letters`, the owner 2026-11-25): its Asian letters AS = 95, AM = 100, AL = 105, AXL = 110, A2XL =
  115 (US S / M / L / XL / XXL), the letter winning over the number a listing writes in brackets, which differs by
  model in majorgolf's charts (5176506757: IM7295 S(95) .. 2XL(115), IT7211..IT7213 and IX4323 S(100) .. XL(115);
  13740514016 "주문사이즈 / AS .. A2XL" over "(95) .. (110) / (110)", staff fitting "AM100"; 9998916822 S(100) ..
  XL(115)). Only the A-letters ("AS", "AM (105)") take it, bare after a colour too ("KG2154 화이트 AS", split by this
  row only); two models' "AM (100)" / "AM (105)" are one M, each its own Naver value, no chart; a bare S / M / L of
  adidas keeps the Korean letters above; the row is named in `brand_row` only where it sized a value.
