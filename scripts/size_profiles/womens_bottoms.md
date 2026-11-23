# Profile `womens_bottoms` (women's skirts and culottes)

Part of [SIZES.md](../SIZES.md). Data: `womens_bottoms.json`. Category: 50002802 Golf Skirts & Culottes
(`CategoryRules.sizes = "womens_bottoms"`, 2026-11-22, the agent on the owner's delegation). Labels `kr_bottoms`,
measures `bottoms` (waist, hip, length: `size_chart.MEASURE_SETS`), fit `waist`, key `waist`, pick `band`.

## The grid (the fallback, by the body waist)

| US | US numeric | Fits waist (in) | Band's lower edge (cm, the row's key) | Korean letter / women's size |
|---|---|---|---|---|
| XXS | 00 | 23-24 | 58.4 | XXS |
| XS | 0-2 | 24-26 | 61 | XS, 44 |
| S | 4-6 | 26-28 | 66 | S, 55 |
| M | 8-10 | 28-30 | 71.1 | M, 66 |
| L | 12-14 | 30-33 | 76.2 | L, 77 |
| XL | 16 | 33-35 | 83.8 | XL, 88 |
| XXL | 18 | 35-37 | 88.9 | XXL, 99 |
| XXXL | 20 | 37-39 | 94 | XXXL |

Why: Korean skirts sell by letter, by the women's size (55 / 66 / 77) or by the waist (inches 24-34, cm 61-82). A
letter and a women's size follow the women's tops (55 = S, 66 = M, 77 = L). A waist number is the body waist: the US
band whose lower edge is at or under it (`pick: band`, an edge takes the larger size: the owner 2026-11-21, never a
size too small), and its US number (`us_by_waist_in`: 26 in = US 4, 27 = US 6, 70 cm = 27.6 in = US 8), so 26 and 27
stay two sizes ("S (US 4)", "S (US 6)").

A waist is read only for this profile (`size_labels.waist_labels`): in a top's chart "73" is a length, never a size.
The chart: a waist or hip laid flat (단면) is doubled on the storefront; with no word, a waist under 53 cm or a hip
under 72 cm is taken as flat.

2026-11-22, the second review (47 drafts): a half size is sized up (`kr_women` 44.5 = S, 55.5 = M, 66.5 = L, 77.5 = XL:
"M(66반-77)" is L, "XL(66~66반)" M-L); a women's size the profile cannot map holds, never its bare letter; a number
80..95 beside a letter ("S(90)", Kappa) is the maker's hip or top numbering, never a waist, in the label and in the
chart; a waist the chart pairs with a letter ("S(25)") sizes that letter; 날씬 / 통통 (slim / chubby) before a women's
size are dropped.

2026-11-23, the pants pilot: a bare letter takes the body waist its seller writes beside it in the text ("S(24-26),
M(27-28)", "M사이즈 (27-28)", "25-26 : S": `waist_text_pairs`, basis `text_waist`), when every bare letter of the option
has one; it was sized by the letter alone, one or two sizes over (4 of 13 women's pants, 5 live skirts).
