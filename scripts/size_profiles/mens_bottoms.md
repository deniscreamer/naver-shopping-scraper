# Profile `mens_bottoms` (men's and unisex golf pants)

Part of [SIZES.md](../SIZES.md). Data: `mens_bottoms.json`. Category: 50002801 Golf Pants, a product the seller states
men's, unisex or mixed (`CategoryRules.sizes_mens`, `sizes_unisex`, 2026-11-23, the agent on the owner's delegation).
Labels `kr_bottoms`, measures `trousers` (waist, hip, thigh, rise, leg opening, inseam, length), fit `waist`, key
`waist`, `waist_read: mens`, pick `band`. The storefront shows the US waist alone: "W32", a band "W32-33".

## The grid (by the body waist; each band holds one Korean letter)

| US | Fits waist (in) | Band's lower edge (cm, the row's key) | Korean letter |
|---|---|---|---|
| W26-27 | 26-27 | 66 | XS |
| W28-29 | 28-29 | 71.1 | S |
| W30-31 | 30-31 | 76.2 | M |
| W32-33 | 32-33 | 81.3 | L |
| W34-35 | 34-35 | 86.4 | XL, LL |
| W36-37 | 36-37 | 91.4 | XXL |
| W38-40 | 38-40 | 96.5 | XXXL, 3L |
| W41-44 | 41-44 | 104.1 | |

Why: US men's pants are sold by the waist in inches (W30, W32), not by a letter; Korean men's golf pants sell by the
waist in inches (28-40), by the waist in cm (76, 79, 82, 85, 88) or by a letter whose waists the Korean charts give
(S 28-29, M 30-31, L 32-33, XL 34-35, XXL 36-37). A waist label is its US waist: an inch as written, a cm as Korea
writes it (`cm_round` 0.3: 82 = W32, 85 = W33, 88 = W34, 91 = W36; Adidas' "88(34)"); "32(82)" is one waist, and "M(32)"
beside "M(82)" one size. A letter with 90..120 in fives ("M(95)") is a top's chest (a polo sold with the pants):
held, never a waist; "2XL(92)" is a waist. A letter's waist in the seller's text sizes it, as the women's. A letter is its band ("M" = W30-31), never a US letter:
a Korean M is a US S. Women's sizes (55, 66) mean nothing here: such a value holds the product. In this profile a
number 26..44 is a waist in inches and 66..112 a waist in cm before anything else ("88" is 88 cm, never a women's 88).

A unisex or mixed pair is sized as men's; a pair whose seller states no gender holds size_unmapped ("no gender
stated"): men's and women's waists cannot be told apart.

## Brand rows (`brands`)

None yet.
