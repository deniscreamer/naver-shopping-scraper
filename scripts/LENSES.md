# Visual lenses: looking at products by eye

A lens draws a shop's products as numbered contact sheets for one question ("is every product in this section a
wedge set?", "which of these are one product?"). An AI agent reads the sheets as images, names the numbers it doubts,
then proves each doubt from the text (`index.tsv`, `summary.json`, the variants, the description). Counts and rules
find what the data says; the photo finds what the data hides: a single wedge sold as a "set", a black edition under
a colourless title, a bag missing from a "with bag" listing, a brand printed on the head and absent from the specs.
Code: the `lens.py` docstring. What waits for the owner: [OWNER_RULES.md](OWNER_RULES.md). How it began: [History](#history).

## How to use

Run from the repo root: `.venv/bin/python scripts/lens.py <lens> <shop> [scope]`. Read only and offline.

| Question | Run | Then |
|---|---|---|
| A job printed `review due` (drafts of a category not marked reviewed) | exactly its commands: `job.py status --job <id> --json`, key `review.commands` | read the sheets, report; activation waits for the owner ([rule 5](#the-rule-of-use)) |
| Is every product the section's (after a pilot, a job, a placement rule change)? | `lens.py section <shop> --leaf <leaf>` (or `--category <id>`, `--job <id>`) | [`section`](#section-is-every-product-the-sections) |
| Odd items among sets, a price far from the category's | `lens.py price <shop> --category <id>` (or `--leaf <leaf>`) | [`price`](#price-what-sits-far-from-the-categorys-price) |
| Is the vendor right (after a brand rule or dictionary change)? | `lens.py brand <shop> --category <id> --source none,title_word,description_row` | [`brand`](#brand-is-the-vendor-right) |
| The store's duplicate groups: one product or versions? | `lens.py dupes <shop> [--category <id>]` | [`dupes`](#dupes-one-product-or-versions); the rule: [DEDUPE.md](DEDUPE.md) |
| Many prepared but not published: was the hold right? | `lens.py held <shop> --job <id>` | [`held`](#held-was-the-hold-right) |
| One doubt, two listings to compare, a finding to show | `lens.py products <shop> <id, key, handle or link> ...` | [`products`](#products-these-side-by-side) |

What it prints: `<lens>: N cards, F flagged (red) <numbers>; M marked to look at (blue) <numbers>` (the first 30 of
each; all in `summary.json` `meta.flagged` / `meta.marked`), then the meta lines it has (`note`, `published`,
`same_title_groups`, `reviewed_groups`, `spellings`), the sheets' paths, `index.tsv` and `summary.json`
([The tools](#the-tools)).

What to do on each result:
- **Red or blue numbers:** look at every sheet, then prove each number from its `index.tsv` line
  ([Reading a sheet](#reading-a-sheet-for-an-agent)); a photo alone is never the reason.
- **Nothing red or blue:** still read every sheet: a mark is only the lens's rule, the eye finds the rest.
- **`note: fewer than 5 prices: no median, nothing marked`** (`price`): read the ladder by eye.
- **A usage error** (exit 2, nothing drawn): `section` needs `--category`, `--leaf` or `--job`; `price` needs
  `--category` or `--leaf`; `held` needs `--job`; `products` needs one or more keys or ids; `dupes --versions` needs
  two or more keys and `--note` (whose word, why).
- **`<ref>: not in the shop's files, left out`** / **`<ref>: N products match, name one by its key: ...; left out`**
  (`products`): the ref is unknown, or names several products (an id under two stores' keys): none of them is shown
  (2026-11-16, `shop_view.resolve`); give the key you mean.
- **A finding:** report it to the owner (numbers, keys, titles, reason, what was not looked at, the sheets' folder).
  A withdrawal, a hold, a republish or a rule change waits for the owner's word (skill `store-actions`); a copy of a
  live product the rules missed is held as a draft and asked about ([`dupes`](#dupes-one-product-or-versions)).

## The rule of use

1. **Read only.** A lens reads local files (`scripts/output/shops/<shop>/`, a job's `events.jsonl`) and writes
   sheets; it sends nothing to Naver, Shopify or a model and changes no pipeline file.
2. **The picture finds, the text proves.** Never act on a photo alone: open the number's line in `index.tsv` /
   `summary.json`, its variants and title, or `lens.py products <id> ...` for all its photos side by side.
3. **The owner decides.** A finding goes to the owner as numbers, keys and the reason; a withdrawal, a republish or a
   rule change waits for the owner's word ([OWNER_RULES.md](OWNER_RULES.md)).
4. **Say what was not looked at.** A sheet shows one photo per product in a grid; a doubt the first photo cannot
   settle needs the `products` lens.
5. **Drafts (draft first, 2026-11-16).** A product of a category not marked reviewed is published DRAFT; the ledger
   says `published`, so it is in every lens under `--store published`. The scripts only print when the review is due
   (`job.py` at 20 drafts, at done and in `status`: `review due` with the exact lens commands); the agent runs them,
   reports, and activation waits for the owner's word (JOB_AGENT.md, Draft first).

## The tools

| File | What it is |
|---|---|
| `scripts/lens.py` | The lenses and the command line: `lens.py <lens> <shop> [scope] [--out DIR]` |
| `scripts/sheet.py` | The drawing: `Card` (number, key, photos, label lines, mark, group), `grid`, `rows`, `write_index` |
| `scripts/shop_view.py` | One read-only view of a shop's files joined by key (`ShopView`, `Product`), a job's events |
| `scripts/review_grid.py` | The first contact sheet (after a job, first photos only); draws through `sheet.py` |
| `scripts/dedupe.py --pairs` | A job's duplicate decisions, candidate beside match (its own drawing) |

Output: `scripts/output/shops/<shop>/lens/<lens>[-<scope>][-<store>][-src-<sources>]/` (no scope: `lens/<lens>/`;
`--out DIR` elsewhere). It holds:
- `sheet1.jpg ...`;
- `index.tsv`, one line per card: n, key, group, mark, the lens's columns, product id, category, store, price,
  variants, brand and its source, section, options, English and Korean title, handle, admin and Naver links;
- `summary.json`, the same with the lens's `meta`.

A new run in the same folder replaces the old sheets. The command prints the red and the blue numbers (the first 30;
all of them are in `summary.json` `meta.flagged` / `meta.marked`) and the paths.

Numbers:
- **red**: flagged by the lens's rule;
- **blue**: worth a look;
- **green**: the kept copy (dupes);
- grey: plain.

A card has one colour, and red wins. The lens writes no pipeline file. Its one file besides its output is
`lens/reviewed.jsonl`, which `dupes --versions` writes on the owner's word.

## The lenses and when to use them

### `section`: is every product the section's?
Command: `lens.py section <shop> --leaf wedge-sets` (or `--category <id>`, `--job <id>`; `--store withdrawn` / `any`).

Each card in the grid shows the price, the variant count and up to 3 wrapped lines of the English title.
- **Red:** no photo on disk. A recorded photo that is gone from disk is left out, and with none left the newest
  collect run's photos are shown.
- **Blue:** the product may sell one club. Its title says "or single" (또는 개별, 및 개별, 단품), or every variant
  is one club by `transform.single_club` (one loft, 1pc, no set word).

When:
- After a pilot or a job, before telling the owner it is done (with `review_grid.py` for the job's own products).
- After a placement rule change: the leaf's sheet shows what moved in.

Catches: heads without shafts, single clubs, training aids, bags, used sets, toys, another category's product (a
woodwork clamp among the junior sets, 2026-11-15).

### `price`: what sits far from the category's price?
Command: `lens.py price <shop> --category <id>` (or `--leaf`; `--low 2 --high 3`).

The grid runs cheapest first, and each card shows `₩price xRatio-of-median`.

The price is **Naver's** (KRW, the lowest variant): the source, not the store's USD price. This lens therefore shows
the products, not the price rule. A `shop_pricing.py` change is checked by its own tests and the repricing dry run.
- **Red:**
  - a robust z of the log price below -2 or above 3 (median, MAD, at least 0.05);
  - under x0.1 or beyond x25 of the median (junior PING Prodi G sets sit at x16, a ₩5M placeholder at x41);
  - no price.
- **Blue:** the cheapest 5% and the dearest 2% not already red. A wide, two-humped category (junior sets
  ₩10k-₩5M) has no outlier by z, yet toys, singles and placeholder prices sit at its ends.
- **Under 5 prices:** no median, nothing is marked, and the command says so. Read the ladder by eye.

When: after a new category's pilot (the cheap end of the wedge sets were single wedges, 2026-11-15), and when the
section lens looks clean but the category is large.

Catches: singles sold as sets, accessories and toys, "from" prices of a cheap option, deposit or placeholder prices.

### `brand`: is the vendor right?
Command: `lens.py brand <shop> [--category <id>] [--source none,title_word,description_row]`. Without `--source`,
every product of the scope is shown.

The grid puts weak sources first, then sorts by brand. Each card shows `brand [source]`.
- **Red:** a weak source (none, title_word, description_row, origin, images_text, images_text_latin).
- **Blue:** one brand written several ways among the products shown (yamato, yamato golf, 야마토, 'Yamato'). That is
  one vendor in the store under several names. `meta.spellings` lists them.

When:
- After a brand rule or dictionary change (`brand_fallback.py`, the dictionaries), before the backup.
- `--source none` for the products under the shop's own name, where a logo on the head or the bag names the brand.

Catches: a model word taken for a brand ("Generic" in the specs row), a description word taken for a brand
(images_text "PRECISE"), a model line written as a brand (핀클리 for A11N SPORTS Pinkly), a brand the photo shows.

### `dupes`: one product or versions?
Command: `lens.py dupes <shop> [--category <id>]`. The duplicate rule, `--report`, `--pairs` and the job's
`--dedupe`: [DEDUPE.md](DEDUPE.md).

The rows put each group under a banner, the kept copy first. Every member shows 4 photos, grade, reviews, price,
variants and its first options.
- **Green:** the kept copy.
- **Red:** joined by title words alone (`dedupe.title_only`, [DEDUPE.md](DEDUPE.md#--report-groups-in-the-store)). Red wins, so a title-only kept copy is red too; its line
  says `keep`.
- **Grey, "reviewed: versions":** a group the owner judged versions.

To record such a judgement: `lens.py dupes <shop> --versions <key>,<key>[,...] --note "<whose word, why>"`. It
appends to `lens/reviewed.jsonl`, so the next run shows only new groups.

The meta carries the store's published count and the titles repeated across stores that were not joined.

When:
- Before withdrawing the store's duplicate groups (`dedupe.py --report`), red members first.
- After a change to `dedupe.py` (words, kinds, thresholds): the new groups, before a job runs with it.

Catches: colour editions (black bag, white bag), a set with or without its bag, sizes or years under one title.

A copy of a live product the rules missed (found here, in `section` or in `products`) is not withdrawn as
`replaced_by:` unasked: list each copy with both keys, titles and prices, ask, and meanwhile hold it as a draft
(`--withdraw <key> --reason "hold: copy of live <key>, ..."`): [OWNER_RULES.md](OWNER_RULES.md) rule 2.

### `held`: was the hold right?
Command: `lens.py held <shop> --job <id>`.

This lens covers every product of the job that did not reach the store: the last word on it is a not_taken, failed
or deferred event, or a held prepared / translated one. A product published later is left out.

The rows go under one banner per cause:
- `held: single_only`, whether the transform held it or the placement did;
- `duplicate_of`;
- `placement unresolved: gender unknown`;
- `failed translate`;
- `deferred: api_500`;
- `title: not_golf`, `card_not_found`, and so on.

Each card shows the product's photos and options (a held product's from its collected line), and the event and
reason.

A duplicate also shows its match's 2 photos on the right, the match's options, and the pair's dedupe signals in the
index:
- **Blue:** the match is live.
- **Red:** the match is no longer in the store. The card names the live copy when the withdrawal says
  `replaced_by:`, else it says "no live copy".

When: after a job whose prepared-but-not-published count is high (the wedge pilot: "why so many prepared but not
added?"), and before changing a rule to let more in.

Catches: a real set held as single, a wrong duplicate match, a duplicate of a withdrawn copy, products lost to a
failure.

### `products`: these side by side
Command: `lens.py products <shop> <ref> ...`: a key, a product id, a handle or a link
([OPERATIONS.md](OPERATIONS.md#naming-a-product-shop_viewresolve-2026-11-16) "Naming a product"). A ref of several
products (an id under two stores' keys) shows none and prints their keys: name one.

The rows show up to 6 photos each (one image once), both titles, price, variants, store status, brand and source,
section, and the first 3 options. Labels wrap into the room the photos leave.

When: to settle one doubt from another lens, to compare two listings the owner names, or to show the owner a
finding.

## Reading a sheet (for an agent)

- Read every sheet of the run (the Read tool shows a JPG); a sheet holds 60 grid cards or about 12 rows.
- Write down the numbers that look wrong and why in a few words, before opening any index line.
- For each number: its line in `index.tsv` (title, price, variants, options, link); a `products` lens of the doubtful
  ones when one photo is not enough.
- Report: the lens and scope, how many cards, the numbers found with key, title and reason, and what was not looked
  at. Keep the sheets' path in the report for the owner.

## Tests and the fixture

- `scripts/test_lens.py`: each lens on a small made-up shop (choice, order, marks, the command line).
- `scripts/test_lens_fixture.py`: the lenses on **real records**, `scripts/fixtures/lens/cases.json`. These are 22
  products of the wedge pilot, the junior runs and the duplicate cleanup, each with why it is there:
  - the ₩89,000 wedge "set";
  - the bar clamp among junior sets;
  - BG-100 Black Edition and white;
  - REVA with and without bags;
  - a hold, a duplicate and its match;
  - a product published and then "not taken" on a resume;
  - a product withdrawn and published again;
  - the real screen codes (`card_not_found`, `title:not_golf`, `category_mismatch`).

  The file also tests the unexpected cases:
  - a torn last line;
  - a photo gone from disk;
  - a broken image;
  - a product with no title, price or variants;
  - one price for all;
  - one id in two stores' keys;
  - a job with no events;
  - an empty shop;
  - a group longer than a sheet;
  - a tab in a title.

  The shop is rebuilt in a tmp folder, and its photos are drawn there. No seller photo is kept in git.
- `scripts/make_lens_fixture.py` cuts the fixture from `scripts/output` (offline). Run it again after a deliberate
  change, then read the diff. A new case is a line in its `CASES`, with why the case is there.

## Adding a lens

A lens is a function `(view: ShopView, ...) -> Plan(lens, cards, layout, columns, meta)` in `lens.py`, a choice in
`main`, a test in `scripts/test_lens.py` (a tmp shop, no network) and one on the real fixture in
`scripts/test_lens_fixture.py` and a section here with its question, command,
when, and what it catches. Cards take their data from `Product.row()` plus the lens's own fields; a mark means
"flag" only when the lens has a rule for it.

## History

- **Born 2026-11-15** from the store's duplicate cleanup: 54 products joined by title words alone were looked at on
  sheets, 3 of them were not one product (BG-100 Black Edition, REVA with and without its bags), 188 copies went to
  DRAFT with no false withdrawal. Owner: "check it is no error, then DRAFT".
