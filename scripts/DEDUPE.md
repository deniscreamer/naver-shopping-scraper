# Duplicates (`dedupe.py`, `job.py --dedupe`)

One product is often sold by several stores (Wilson Profile JGI: 9 copies in the store). The shop keeps it once, at
the best seller (the owner approved the rule 2026-11-15). A job checks each product right after it is collected;
two read-only commands show the decisions and the groups already in the store. Code: the `dedupe.py` docstring;
the job's side: `job.py` (`dedupe_step`, `replace_step`). What waits for the owner: [OWNER_RULES.md](OWNER_RULES.md).

## How to use

| Task | Run | Then |
|---|---|---|
| A job (`new` or `scroll`) | nothing: `--dedupe on` is the default (the owner's yes after the W7 pilot, 2026-11-17) | read the events below in `status --json` / the log |
| A check run that changes nothing | `--dedupe log` on `new` / `scroll`, only when the owner wants it | `--pairs`, show the owner |
| Were a job's decisions right? | `.venv/bin/python scripts/dedupe.py --pairs <shop> --job <id>` | look at the sheets, list wrong pairs for the owner |
| Change the rule (developer): a missed copy or a false merge | the test first (`test_dedupe.py`), measure before and after on the store's groups | skill `dedupe-rule` (the tests, fixture and docs that move with it; the owner's word) |
| Copies already in the store | `.venv/bin/python scripts/dedupe.py --report <shop> [--category <id>] [--list]` | `lens.py dupes <shop>`, red members first ([LENSES.md](LENSES.md#dupes-one-product-or-versions)) |
| A copy the rules missed (found in a lens) | nothing automatic | hold it and ask: [OWNER_RULES.md](OWNER_RULES.md) rule 2 |
| Two given products: copies or versions? | `.venv/bin/python scripts/lens.py products <shop> <id1> <id2>`; `.venv/bin/python scripts/job.py where <id>` for their `duplicate_seen` / `duplicate_of` events (the full signals: `grep '<id>' scripts/output/jobs/*/events.jsonl`); `dedupe.py --report <shop> --list` for their group | compare with [The rule](#the-rule) (possible duplicate, confirmed); copies the rule missed: [OWNER_RULES.md](OWNER_RULES.md) rule 2 (list both, ask, hold) |

No command judges one given pair: `dedupe.py` has only `--report` and `--pairs`. Both commands are read only and offline. Withdrawing a group's copies, or marking a group versions
(`lens.py dupes --versions`), is the owner's word.

### `--dedupe off|log|on` (the owner, 2026-11-15)

`new` and `scroll` take it, `on` by default (the owner, 2026-11-15, after the log pilot). It is kept in job.json and
read again by `run` / `scroll --job`. A job made before has no key and runs as `off`; `off` writes no key.
The W7 pilot (2026-11-17, job fairwardgolf-50002783-20261118T061139Z, `--dedupe log --draft`, 20 published drafts):
all 20 were copies of live products, each with a closing decision (`duplicate_of` 6, `duplicate_of_withdrawn` 14:
a confirmed withdrawn match is looked at first, by design); the owner said yes: `on` is the default again, with the
wedge-set review's confirmations (C40, C41-1, C43) and the `held_same_upc` hold.

- `off`: nothing is looked up.
- `log`: one event `duplicate_seen` per product with a title match (the would-be decision `duplicate_of:<key>` /
  `duplicate_better:<key>` / `duplicate_of_withdrawn:<key>`, the matches and their signals); nothing else changes.
  The index grows as in `on` (a would-be `duplicate_of` does not join it), so later decisions are the same.
- `on` (the owner's decision 2026-11-15: replace automatically): see the events below.

### What a job's events mean, and what you do

| Event / status | Means | You |
|---|---|---|
| `duplicate_seen`, decision `not_confirmed` | a title match, not confirmed by photos or variants: an ordinary product, taken | nothing |
| `duplicate_seen`, decision `same_upc:<key>` (2026-11-17) | no confirmed match, but the UPC of `<key>` under `upc_suspect` (`same_upc`: every such key, `upc`: the codes): taken | `log`: nothing; `on`: see `held_same_upc` |
| `duplicate_seen`, decision `same_item:<key>` (2026-11-20) | no confirmed match, but the same Naver catalog or style code as `<key>` (`same_item`: every such key, `why`: `catalog <id>` / `code <code>`): taken | a flag only, in every mode (the owner: not certain enough to act on): the product goes on as usual, a draft in an unreviewed category and LIVE in a reviewed one. `job.py status`, the done line and the progress line print the open pairs (`same-item candidates: N ...`, both products still published, the pair not judged versions) with `lens.py products` per pair and `--pairs` for the job; `job.py activate` leaves such drafts. The agent checks each pair from the data (skill visual-review) and brings the owner copy / versions / doubtful; his word: a copy is withdrawn or held (`publish.py --withdraw`), versions are recorded (`lens.py dupes --versions <keys> --note ...`: the pair never comes back) |
| `held_same_upc` (`on`) | that product was published as a draft and withdrawn at once, reason `hold: copy of live <key>, same UPC ...` (`same UPC as <key>` when `<key>` is not live) | list it for the owner: copy or version ([OWNER_RULES.md](OWNER_RULES.md) rule 2); a failed withdraw (`why`): hold it by hand on his word |
| `duplicate_seen`, a would-be decision (`log` only) | what `on` would have done | nothing; `--pairs` after the run |
| `not_taken: duplicate_of_withdrawn:<key>` | a confirmed match the owner withdrew: never taken | nothing |
| `not_taken: duplicate_of:<key>` | not strictly better than the best confirmed match: closed (no images, no translation) | nothing |
| `duplicate_better {replaces}` | strictly better: taken as usual | nothing |
| `replaced` | once the better one was published, the old one was withdrawn (`publish.withdraw`, DRAFT, reason `replaced_by:<new key>`): it was still published and the new one has no fewer variants | nothing; it shows in the report |
| `replace_skipped` with why | the old one stays: `not published`, `the old one is not published`, the new one is a draft, `fewer variants (N < M)`, or `withdraw failed: ...` | a draft: see below; a failed withdraw: tell the owner (withdrawn by hand on his word) |

A draft (draft first, 2026-11-16) never replaces a live product (`replace_skipped`: the new one is a draft):
`job.py activate --job <id>` prints the old one's `--withdraw` line, run on the owner's word once the new one is
live ([JOB_AGENT.md](JOB_AGENT.md#draft-first-a-category-not-yet-reviewed-the-owner-2026-11-16)). A product
withdrawn as `replaced_by:` stays in the index (status `replaced`, 2026-11-16) and leads a copy that matches only it to
the live end of its chain (`replace` keeps it after a replacement inside the job as well).

### `--pairs`: a job's decisions

`dedupe.py --pairs <shop> --job <id> [--out DIR]` reads the job's events (`duplicate_seen`, `duplicate_better`,
`not_taken`) and writes, in the job's `pairs/`: sheets `pairs1.jpg` ... of candidate | match photos, numbered,
`dup` on the confirmed ones, and `index.tsv` (decision, signals, both keys and titles), for the owner to check the
decisions.
Same-UPC hold candidates (`duplicate_seen` with `same_upc:<key>`, 2026-11-17) appear there as well, usually with no
title match: one row per product sharing the UPC (a title match sharing it keeps its one row), decision
`same_upc:<that key>`, never `dup`; the pilot shows them to the owner before `on`.

### `--report`: groups in the store

`dedupe.py --report <shop> [--category <id>] [--list]` counts the duplicate groups already in the store, best first
(a tie: more variants), and marks `title only` the members joined by title words alone (`dedupe.title_only`: no
shared photo, no variants alike; a colour edition, a set with its bag). Look at their photos before a withdrawal:
`lens.py dupes <shop>` shows the groups as rows, those members red.

Two lists of hold candidates follow the groups (2026-11-17), never groups themselves and never withdrawn by a
script: `same UPC <code>` (published products joined by `upc_suspect`, no group holding them together already),
and `same brand and sets sold`; after them, apart, the same-item candidates (`same item (catalog <id> | style
code)`, joined by `same_item`, 2026-11-20: a flag for the agent's review, a group only of members that each pair with
every other, never chained through a third, a pair judged versions left out) and
(`same brand and sets sold`: pairs of agency imports in a `sets_only` category with the same prepared `brand_ko` and
the same sold sets of 2+ values with a digit, no kind / hand / gender / bag clash: equal sets can coincide, MAZEL
'4 Iron' / '7 Iron'). The summary line counts them; each is the owner's word ([OWNER_RULES.md](OWNER_RULES.md) rule 2).

## The rule

Right after a product is collected, before its description images, `dedupe.py` looks it up in an index built when
the run starts:

- **The index:** the shop's published products (drafts awaiting review included, draft first 2026-11-16), the
  ones the owner withdrew, and those withdrawn as `replaced_by:<key>` (status `replaced`, 2026-11-16), plus the
  job's own collected products. Each product the job takes on joins it, so a later seller in the same job is
  compared too; one of them closed later in the run (not_taken / deferred / failed, or held by the transform or the
  translation: agency_no_brand, single_only, 2026-11-15) leaves it again.
- **A possible duplicate:** the same category and the same set of title words (case, signs and order ignored, what
  is in brackets kept: `27ZXI-RKT LS` is not `27ZXI-RKT`, `Qi4D MAX` is not `Qi4D`), another store, prices within x2
  (`PRICE_RATIO`). The same **spaced key** counts too (2026-11-17, C43: `spaced_key`, Miura Forged Black QPQ
  11585620683 / 11585678496): adjacent Hangul words joined ('샤프트 선택' = '샤프트선택'), never across a digit or a
  Latin word ('(3~5세)' is not '35세'), and a brand+코리아 word dropped when the brand itself is a title word
  (미우라코리아 with 미우라; 던롭코리아정품 stays).
  The same **tail key** counts too (2026-11-18, the chipper scroll: `tail_key`, the double-sided TTY / PGM chipper
  11360733287 / 6414820248, titles apart only by the store's name in front, 홈스월드 / 지아이엘): the title key without
  the title's first word, when that word is no version word (no digit, no club kind, hand, gender, bag or model word:
  퍼터 / 웨지, 왼손 / 오른손, MAX / LS, 2025 / 2024 stay apart) and 6+ words (`ALIKE_MIN_WORDS`) are left (DR / YR
  여자골프채 여성골프채풀세트 stay apart). It is a match only: a confirmation is still needed.
- **Confirmed** when the first photo is the same file, or half the photos of the smaller gallery are
  (`PHOTOS_SHARED`), or the variants agree >= 80% (`VARIANTS_JACCARD`); not confirmed: an ordinary product (event
  `duplicate_seen`, decision `not_confirmed`).
- **Purchase-agency imports** (구매대행: a copy of one foreign listing, 2026-11-15): two of them are also one product
  with a title of 12+ words (`LONG_TITLE`) alike word for word (`long_title`), or with titles translated apart
  (`alike`: the same numbers, club kinds, hand, gender and bag words, 6+ words (`ALIKE_MIN_WORDS`), 70% of them
  alike (`WORDS_ALIKE`) after one spelling per word: 모래 / 샌드, 남성용 / 남성, eAj dropped). The first photo alone is
  never a match: an agency lists each version of one listing apart under its one photo. With the same non-empty
  sets sold, the numbers those sets spell out (counts kept) are set aside before the numbers are compared (2026-11-17,
  C41: AM20XX 13016628843 / 13363498942 '50/52/54/56/58' / '.../60도'); sets sold apart keep every number (one agency
  family's Pinkley '옵션 1' / Black).
- **`sold_equal`** (2026-11-17, C41): in a `sets_only` category two agency imports with the same title key or
  `alike` that sell the same non-empty sets are confirmed, in the job as in `--report` (pron 13408226321 /
  13566632407: variants 0.22 over the page list, `not_confirmed` before; MAZEL 13391641875 / 13204525652, Yamato LH01).
- **`strong`** (2026-11-15): any two products are also one with every photo and variant alike: the same category,
  photos shared >= 80% (`STRONG_PHOTOS`), variants >= 80%, and the titles not clashing on club kind, hand, gender,
  bag (미포함 wins) or the numbers standing alone (Aged 3-5 / 9-12, 9종 / 12종), a subset passing, and agreeing on a
  model's version word (MAX, LS, TR, PRO, 맥스: 27ZXI-RKT and its LS share a dealer's photo and variants).
- **`same_listing`** (part of `strong`, 2026-11-16, the owner's wedge review: Lazrus 13016648376 / 12079160628 /
  12557380462, one photo set byte for byte, the same 3 sets sold, variants 0.64-0.75 alike because each lists other
  single wedges): the first `LEAD_PHOTOS` (3) photos the same files in the same order, photos shared >= 80%, the same
  non-empty set of variants sold (in a `sets_only` category without the single clubs transform leaves out, club-slot
  axes counted as transform counts them), the kinds and model words as `strong`, and the titles' numbers not
  clashing once those a variant spells out are set aside (lofts, ages: "Aged 9-12" / "Aged 3-5" of one PGM listing).
  A count stays the title's own even when a variant writes the number ("10개" / "9개": Mizuno JPX QII 13826383159 /
  13826377851, variants "7irons(6-9...)"). Measured on the store: 4 new pairs of published products, the 3 Lazrus and
  PGM 13274024476 / 13390550850 (50002787).
- **`strong` by UPC** (`same_upc_listing`, 2026-11-17, C40): two listings with no variants, the same first photo,
  every photo shared (`LEAD_PHOTOS`+), no clash of the free numbers and a UPC in common (the description's Amazon
  table: `upcs`, [SELLER_DATA.md](SELLER_DATA.md)), the kinds and model words as `strong`. Titles shuffled apart by
  agencies (Majek per UPC, GoSports, STIX, Pinemeadow, Bermuda, Pro Open 690 LH): 25 pairs of the shop's records, all
  copies. Not the title's lofts (52/56/60 is in nearly every title; one Majek photo set serves its women's, senior
  and men's sets) and not under 3 photos (one generic photo is common).
- **Same UPC, no confirmed match** (2026-11-17, C39): a hold candidate only, never a match or a decision
  (`upc_suspect`, `Index.same_upc`): the same category, another store, the price guard, the same club kinds named in
  both titles (never read from the description: its Style Name row lists every edition), the same piece count, the
  same colour when both titles name one, no hand / gender / bag clash, the same model words, the lofts and ages (free
  numbers of 1-2 digits) not clashing unless the same sets are sold, one sold set inside the other. In `possible()`
  it would withdraw versions automatically (Olimar ATS junior clubs share their parent's UPC).
- **The same Naver catalog or style code, no confirmed match** (2026-11-20, the owner: strong flags, no complicated
  rule; the next word the same day: a flag for review, never a hold): `same_item`, `Index.same_items`. The catalog: the page answer's
  `epInfo.matchingModelId` (`/products/specs` `catalog.id`; products collected before it from `<shop>/catalog_ids.json`,
  the backfill below), a catalog holding more than `CATALOG_LOOSE` (15) published products ignored (one held 37 junior sets
  of every age; 15, not 6: flagged copies stay published, Yamaha Femina is at 6). The style code (`style_codes`): the model name's first part and the title's tokens of 6+ characters
  with 3+ digits and a letter (521F4SD304, MR322LSJ92), the same brand when both name one, never across a combo set
  (조합, +), never a shaft's model (KBS MAX105, MODUS115), a brand that is the seller's store name counting as none
  (SNGR15702 under 대량가성비추천할인몰). Both: the same category, another store, the price guard, no clash of club
  kind, bag, hand, gender or length read inside the words ("남성골프채풀세트"), of junior ages ("3세 이하" / "3-5세") or
  of piece counts. The loose catalogs are counted once over the published products (`loose_catalogs`), never over a
  job's growing index; a replaced match's live end must pass the price and store guards itself. Measured on the store the same day:
  the catalog joined 30 groups across stores; without the loose ones about 23 of the 31 live pairs were one item the
  title rule had missed (Yamaha Femina 6 times live, Mutsumi Honma 3, Yamaha CS 3, TaylorMade Glory, Honma Kiwami5,
  Kolon VWX), the rest versions Naver files together, most of them stopped by the clashes; the code: 4 club groups,
  all one item. Rejected the same day: `details.catalog_id` (the listing's own nvMid, never shared), a perceptual
  photo hash (Pearly Gates "matched" Wolsey; a real pair re-shot matched nothing), the catalog's seller list (a
  catalog page: R-NAVER-1, and our own products are all we compare).
- **The catalog backfill** (`<shop>/catalog_ids.json`, `{"ids": {product id: catalog id | null}}`, 2026-11-20): the
  catalog of the products collected before `/products/specs` gave it, read once from the page answers the server had
  saved (`server/output/ext-product/*/product.json`, `parsers.parse_page_catalog`, the latest per product); 3622
  products, 310 matched. A product collected since carries its own; the file is not grown.
- **A replaced match** (2026-11-16, the owner's wedge review: GoSports 12557420063 was not taken as a copy of
  13619939279 on 2026-11-15, then published as new once 13619939279 was replaced by 13379851400 and that by
  12918511112; A11N 13512885159 through 13405976594 -> 13552318731, a hold): a confirmed match withdrawn as
  `replaced_by:` counts as the live end of its chain (`Index.live`, `live` in the match row): a withdrawn end
  (`hold:` or any owner's withdrawal) gives `duplicate_of_withdrawn`, a published or job end the usual better / not
  better (`duplicate_better` names the live end: that is what `replace_step` withdraws), an end not in the index
  `duplicate_of` (never let through). The price guard holds against the live end (`live_price` false: not followed).
  Measured on the store: 6 published junior sets (50002787) now read as copies of a live product through a replaced
  one: 13064095798, 13826709716, 13790999652, 13253313396, 13261691142, 13401593453 (for the owner: hold or keep).
- A title's written-out escapes ("u2013") are decoded before its words and numbers are read.
- A product is looked up at whatever stage the job takes it on (a resumed one too: 2026-11-15, 13 copies went from
  "prepared" to the store).
- **Better** = a higher store grade (PLATINUM > PREMIUM > BIG_POWER > POWER > SPROUT > SEED), then more reviews;
  price never decides.
- Colours are not kind words: as kinds they split 4 real copies of the store's groups (2026-11-15). The title alone
  cannot tell a colour edition or a set with its bag from a plain one: that is what `title only` and the lens are for.

## History

- **Log pilot** (2026-11-15, junior clubs, `log`, 103 published): 7 duplicates, all the same product on the owner's
  look at the pairs sheet (6 by photo and variants, 1 by variants only: a reshuffled title, another colour on the
  main photo), no false merge, no better seller (equal grades); 5 of 7 matched products of the same job. Then `on`
  became the default.
- **Agency imports** (2026-11-15, the wedge pilot): `long_title` and `alike` were added (four sellers of one Lazrus
  set, 19 words alike, photos re-encoded, variants 0.64 alike; GoSports in 5 stores under titles translated apart).
- **`strong`** (2026-11-15, the lenses): three A11N SPORTS sets, one under the model line 핀클리; six sellers of one
  challenger junior set.
- **The store's cleanup** (2026-11-15, the owner: "check it is no error, then DRAFT"): 106 groups, 191 extra copies,
  all looked at; 54 joined by title words only, 3 of them not one product (BG-100 Black Edition and white, REVA
  2025 with or without its bags: the title does not say, colours as kind words split 4 real copies instead); 188
  withdrawn `replaced_by:<kept key>`. The lens `dupes` was born from it ([LENSES.md](LENSES.md)).
- **Copies the rules missed** (the owner, 2026-11-16): held as drafts with a `hold:` reason, the owner decides each
  ([OWNER_RULES.md](OWNER_RULES.md) rule 2).
- **The wedge-set review** (2026-11-17, W7: C39, C40, C41, C43 in their narrow forms; commit 0bc3834): measured on the
  store's old groups (the ledger's published and withdrawn products), 8 groups new or larger, all copies: Miura QPQ (spaced key), Majek x5 / STIX / Pinemeadow / Bermuda / Pro
  Open 690 (UPC, no variants), AM20XX and PGM junior (sets sold), none lost; the owner's reviewed versions unchanged.
  `--report` of the published: 5 -> 8 groups, plus 7 same-UPC groups (8 extra copies) and 6 same-brand-and-sets
  pairs to hold on the owner's word. Rejected: the UPC in `possible()`, the title's lofts in `strong`, `same_listing`
  under 3 photos, the subset-of-options path (about 2045 pairs), copies matched within one shop (C42: it merged 7 of
  24 different editions, steel / carbon, R / SR, XJ / XJ 2). Piloted 2026-11-17 (`--dedupe log`, 20 of 20 drafts
  copies of live products, every one closed under `on`); the owner's yes the same day: `on` the default. Open: 5 pairs
  inside `--report` groups carry different UPCs, possible false merges for the owner's look at the photos; the one
  named, pron 13408226321 / 13566632407 (754003448245 / 754003447477), was withdrawn `replaced_by:` 13207564502 on
  2026-11-17, the other 4 were never listed.
- **The chipper scroll** (2026-11-18, fairwardgolf-50002784-20261118T130246Z, `--dedupe on`): the dupes lens found 7
  copy groups among its drafts that the rule let through. Why each was missed: Odyssey 2025 women's chipper x6, PING
  Chip W, PRGR R35, World Eagle CH809 LH and Cleveland 10077017895: titles worded apart, every photo the seller's own
  (shared 0), the variants written apart (the known gap: other variant text, other photos); Cleveland 10103838449 /
  10068993288 one title, but men's and women's against women's only (variants 0); GV Tour ES 9968111930 / 2552593690
  one store (never compared: C42), 11847041779 apart; TTY 7518807949 titles apart. The tail key catches TTY / PGM
  11360733287 / 6414820248 (variants 1.0, the store's name in front). Measured on the store's old groups: 2 groups
  new, both copies on their photos (TTY, 50002784; Gold Bunker junior set 13193526523 / 13293885011 아동 / 유아,
  50002787), none lost or larger, the owner's reviewed versions unchanged; `--report` of the published 3 -> 5 groups.
  Rejected: a fuzzy title or variant text match for the rest (no photo or variant signal tells their versions apart:
  33.5 / 34.5 in, men's / women's, steel / carbon).
