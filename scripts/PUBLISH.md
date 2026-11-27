# Publication to Shopify

How prepared, translated and placed products reach the Shopify store (`publish.py`), the store actions (withdraw,
hold, restore, activate), the payload and its metafields, and the history (the Shopify roadmap, the harvester's
products); split from scripts/README.md on 2026-11-16 (history: `git log --follow scripts/README.md`).

## How to use

What waits for the owner (re-sending a published product, a whole-shop run, every store action) and what does not
(a job's own `--publish` of its new products, every read-only command): [OWNER_RULES.md](OWNER_RULES.md) rule 1; the
procedure for store actions: skill `store-actions`. Commands from the repo root:

```sh
.venv/bin/python scripts/publish.py fairwardgolf [--only <key>] [--force] [--dry-run] [--rehandle] [--draft] [--shops-root DIR]
.venv/bin/python scripts/publish.py fairwardgolf --withdraw <key> | --restore <key> --reason "..."   # also --activate <key>
.venv/bin/python scripts/store_diff.py fairwardgolf [--only <key>] [--category <id>]                 # read only
.venv/bin/python scripts/publish.py fairwardgolf --withdraw <ref> --reason "..." --dry-run          # the key, nothing sent
.venv/bin/python scripts/publish.py fairwardgolf --channels [--dry-run]                             # live products onto the channels they miss
```

Wherever a `<key>` is asked, a product id, a handle or a link works too, and `--keys-file F` / `--job ID [--event E]`
add more (2026-11-16): [OPERATIONS.md](OPERATIONS.md#naming-a-product-shop_viewresolve-2026-11-16) "Naming a product".

| Task | Run | Section |
|---|---|---|
| See what a product would become, send nothing | `publish.py <shop> --dry-run [--only <key>]` (payloads in `publish/payloads/`) | [Publication](#publication-publishpy-mvp-the-owner-2026-11-08), [The payload](#the-payload-shopify_payloadpy) |
| Publish what is ready (a job with `--publish` does it per product) | `publish.py <shop> [--only <key>]` | [Publication](#publication-publishpy-mvp-the-owner-2026-11-08) |
| The store and our files disagree | `store_diff.py <shop> [--only <key>]`; skill `product-trace` | [Store actions](#withdraw-hold-restore-activate-store-actions) |
| What the store holds now (one product, counts, a collection, a dump) | `shopify_catalog.py <shop> show <ref>`, `counts`, `collection <handle>` (read only) | [After an action](#after-an-action-check-it) |
| Withdraw, hold, restore, activate, rehandle, force | the flags above, on the owner's word | [Store actions](#withdraw-hold-restore-activate-store-actions) |
| A sales channel was added (Shop, Google & YouTube): the live products onto it | `publish.py <shop> --channels --dry-run` (counts per channel id), then without it | [Publication](#publication-publishpy-mvp-the-owner-2026-11-08) |
| A published product looks wrong (title, vendor, price, options, reviews, photos) | `--dry-run --only <key>`, read the payload | [The payload](#the-payload-shopify_payloadpy), [Metafields](#metafields) |
| Credentials, tokens, uploads | never read the credential files | [Access and uploads](#access-and-uploads) |

What a publication run prints, one line per product (`<key>: <status> ...`), then the counts:

| Status | Means | You |
|---|---|---|
| `published` | sent; its row is in `publish/published.jsonl` | nothing |
| `skipped` | its inputs (or what Shopify would get) did not change | nothing; `--force --only <key>` on a live product only on the owner's word |
| `dry-run` | the payload is in `publish/payloads/`, nothing sent | read it |
| `held` | no English for a text (`Untranslated`) or a payload that cannot be built (`PayloadError`: a variant with no price) | fix the cause (translation, package, price), run `--only <key>` again (a product already in the store: rule 1) |
| `failed` | Shopify refused (userErrors, a file not ready ...) | read the reason; fix it, then `--only <key>` again (a product already in the store: rule 1) |
| `<key>: not ready (...)` (stderr) | an `--only` key not prepared `ready`, `translated` and `placed`, or withdrawn | finish its stages first; a withdrawn one: `--restore` on the owner's word |
| `publish: stop: <shop> is busy: ...` (exit 2) | a job of the shop runs: sending takes the shop's lock (a dry run, withdraw, restore and activate do not) | wait for the job, or `--dry-run` |

## Publication (`publish.py`, MVP, the owner 2026-11-08)

A product goes to the store when it is `ready` (transform), `translated` and `placed`; a job made with
`job.py new --publish` does it for each product right after translation (placement of the whole shop, offline,
then this one product; with `--describe` its description is written in between, see [DESCRIBE.md](DESCRIBE.md)). Per product: the reviews' photos and avatars to Shopify Files (the files app, once per
file, named by its hash, `publish/files.jsonl`), the review rows as a JSON feed file there, the gallery photos as
staged uploads attached in `productSet` (create, or update the product with its source key; a send cut off after
`productSet` but before its ledger row finds that product again by its source key or handle, so no second copy), ACTIVE, published
to every sales channel of the store (the owner, 2026-11-09; the list is read at each run, so a channel added later
reaches new sends; 2026-11-24: an activation publishes the product on every channel of that day too, and
`--channels` puts the live products already in the store onto a channel they miss, data and ledger untouched). Draft first (2026-11-16): a create in a Naver category
not marked reviewed (`transform_shops.reviewed`) is DRAFT, still published to the channels, so it shows once
activated; the ledger row stays `published` with `store_status: DRAFT` (only when not ACTIVE), so dedupe, the lenses,
store_diff and the job's stages see it as published; an update of a draft sends no `status` (one activated in the
admin stays live); the status is outside `output` and the digest, so nothing is sent again for it; one line in `shops/<shop>/publish/published.jsonl` (product id, handle,
photos by hash, admin link, `pricing`: the rule's version, `prices_usd`: the lowest and the highest variant price; rows
from before 2026-11-11 have neither). Unchanged inputs: skipped; on an update photos already there are kept by hash, and a
managed metafield the product no longer has is deleted (`shopify_payload.MANAGED`; productSet never removes one).
`--dry-run` writes the payload to `publish/payloads/` and sends nothing. `shopify_payload.VERSION` is in the
digest: a change of what the builder makes sends every product again. So is the shop's price rule
(`shop_pricing.Policy.describe()`: every number and the tariff's version): a new rule or tariff sends every
product again too, so `reprice.py` shows the change first (see PRICE.md, The price).

### The store's "before": `publish/sent/` and the build (2026-11-19, the retro-sweep plan, stage 2)

What a product's `productSet` sends is hashed as `output` in its ledger row; the dict hashed is kept beside it, so a
later step can show the owner field by field old -> new without reading Shopify:

- `publish.build(shop, key, ids)` builds what `publish_one` would send and writes nothing (no payload, no feed file,
  no `files.jsonl`, no ledger row): `{key, output, product_input, feed_sha, images, handle, digest}`.
  `product_input` is the dict `output_digest` hashes (each photo as its file's sha256, the reviews' feed as
  `sha:<its hash>`, no handle; `publish.normalized`), so `sha256` of its canonical JSON (`shopify_payload.digest`)
  is `output`. The dry run, the real run and `build` compute `output` in one place (`publish._built`).
  `build`'s `output` is the real run's only when every review file is in `files.jsonl` already (one not uploaded
  yet is hashed as `dry-run:<file>`); `new_files` counts those.
- A real send (not a dry run, not skipped, not failed) whose row has an `output` writes
  `publish/sent/<Naver product id>.json` (`shop_files.write_atomic`, that dict as canonical JSON: one line) after
  its ledger row. A failed photo (`failed`, so `output` None), a refused send (CatalogError, no row), a skip
  and a dry run write none. A disk error on the file is a warning line, not a stop: the send and its row stand,
  the product has no baseline until its next send (2026-11-19).
- `publish.load_sent(shop, key)` -> the dict, or None when the file is missing or not JSON, or its sha256 is not the
  ledger's `output` (a send cut off between its row and its file, a file from an older send, a hand edit, a
  withdrawn key): no baseline. The file proves itself; never trust one `load_sent` refuses.
- Products published before stage 2 get theirs from `sweep.py <shop> --seed-sent` (today's offline build where it
  equals the ledger's `output`; [SWEEP.md](SWEEP.md)). About 37 KB a product (fairwardgolf, 2026-11-19: 2,263 files,
  84.7 MB); in the state backup
  ([OPERATIONS.md](OPERATIONS.md), Backup).

## Withdraw, hold, restore, activate (store actions)

Each one waits for the owner's word ([OWNER_RULES.md](OWNER_RULES.md)); the procedure: skill `store-actions`. A
product's key is `fairwardgolf:naver:<channel>:<product id>`: a lens's `index.tsv` gives it by sheet number (column
`key`), the ledger by product id; each flag also takes the product id, a handle or a link and resolves it (two
products for one ref: exit 2, both keys listed), and `--dry-run` with a store action prints `<key>: would <action>`
and sends nothing: run it first to see the key the action takes. A key the real call would refuse says so from the
ledger: `not published here` (withdraw), `not withdrawn here` (restore; exit 1 for these two), `not a draft here`
(activate). Two changes of 2026-11-16, both toward sending less: `--dry-run` used to let a store action through
(now it only says what it would do), and an empty ref (`--only "$KEY"` with KEY unset, `--keys-file ""`, `--job ""`,
`--event` without `--job`) stops with exit 2 instead of meaning every product; `--only <ref>` that names no product is
still `not ready` and skipped (exit 0), as before.

- `publish.py <shop> --withdraw <key> --reason "..."`: the product goes DRAFT in the store (nothing deleted), the
  ledger row says `withdrawn` with the reason, and it is never sent again; dedupe closes a new copy of it as
  `duplicate_of_withdrawn` (unless the reason is `replaced_by:<key>`: then its replacement is compared). Allowed
  while a job runs (no shop lock).
- **Hold** (the owner, 2026-11-16): a doubtful copy a lens review found is withdrawn with a reason starting `hold:`
  (the exact reason is in OWNER_RULES rule 2), not as `replaced_by:`, until the owner decides: [OWNER_RULES.md](OWNER_RULES.md) rule 2.
- `--restore <key> --reason "..."`: undoes a withdrawal: ACTIVE again (a product created as a draft comes back a
  draft), its last published row back in the ledger with no digest, so the next `--only <key>` sends today's data.
- `--activate <key>` (repeatable): a draft live, nothing sent again; `not a draft here` for a key that is not a
  published draft (a withdrawn or held one included). `job.py activate --job <id> [--dry-run]`: every remaining
  draft of a job, withdrawn ones skipped; it prints the `--withdraw` lines of the old copies a draft did not replace.
- `--draft`: the products created by this run go DRAFT in any category (as `job.py --draft`; 2026-11-25: products a rule change freed go to the lens review first, then `--activate`).
- `--rehandle --only <key>`: the handle its title makes now (the old one redirects); `--force --only <key>`: send
  even when nothing changed. Both re-send a published product: rule 1 of OWNER_RULES.md.
- `store_diff.py <shop> [--only <key>] [--category <id>]`: read only, what a publication would change, field by
  field (it rewrites `publish/store_diff.json`: after `--only` that file holds one key, 2026-11-17; run it in full
  before building batches from it); `--adopt` (takes the shop's lock) records `output` for products the store already has.

### After an action: check it

Read only, after the owner's word was carried out (2026-11-16, the owner's five tools):

```sh
.venv/bin/python scripts/shop_view.py history <shop> <ref>             # the ledger rows the action wrote
.venv/bin/python scripts/shop_view.py check <shop> plan.tsv            # every planned key<TAB>state<TAB>reason: ok
.venv/bin/python scripts/shopify_catalog.py <shop> show <ref>          # the store's status, handle, vendor, collections
.venv/bin/python scripts/shopify_catalog.py <shop> counts              # active / draft / archived / all
```

`shopify_catalog.py show` finds the product by the ledger's `product_id` (a ref as everywhere; a handle or a number
our files never had is asked of the store), `--variants`, `--metafields [NS[.KEY]]` and `--media` add their lines,
`--json` the store's answer. `counts`' active and draft should equal `shop_view.py query <shop> --count-by state`'s
active and withdrawn + draft (2026-11-16: 2017 and 346, the same on both sides). The whole tool:
[OPERATIONS.md](OPERATIONS.md#reading-the-shop-by-hand-2026-11-16) "Reading the shop by hand".

## The payload (`shopify_payload.py`)

What a product becomes in the store; read it when a published product looks wrong.

The owner's rules (`shopify_payload.py`):
- **Title, vendor**: the translation's (the title prompt makes the store name: brand first, no shop, distributor or
  after-sales words, no loft / flex / shaft codes, no club list, no usage or gift words). The vendor loses a
  maker's company form and a second brand ("Prokenex / SJG Co., Ltd." -> "Prokenex", "Mizuno, Hillcreek" ->
  "Mizuno") and keeps the first spelling the brand was known by, compared without case, dots or spaces (the owner,
  2026-11-17: "whichever came first stays"): the store's oldest product's spelling, else the brand dictionary's
  (the dictionary keeps a brand's first spelling too: `translation_dicts.brand_spelling`; PING stays PING, Yonex
  stays Yonex, 2026-11-09), else the model's (a run remembers each new vendor for its next products); the
  title spells the brand as the vendor; a title without its brand gets it in front (not the tenant's name). Handle from the title (ASCII, the brand in front; a taken handle
  gets `-2`, `-3`; an update keeps the shop's handle, `--rehandle` sets the new one with a redirect).
- **Price**: per variant from `shop_pricing.Policy.quote` (see PRICE.md, The price). In a shop with the delivery
  rule (fairwardgolf, the owner 2026-11-11) the price holds the purchase, the duty, the delivery and the margin,
  and Shopify's cost per item is the purchase with ShopNShip's commission (the duty is not in it); elsewhere cost = price =
  the Naver KRW at 1 000 KRW = 1 USD rounded UP to a whole dollar. A variant that cannot be priced (no box, a box
  over the tariff's 50 kg) holds the product (`PayloadError`). No compare-at price. Add-ons: the KRW at the same
  rate only, no delivery, duty or margin.
- **Buyable**: every variant is untracked and sold without limit (CONTINUE), one sold out on Naver too (the owner,
  2026-11-09: buying opens on the site later); the variant's `fairwardgolf.source.available` keeps Naver's state.
  Weight: the package's central weight in grams.
- **"1+1" options**: an option with the same English name and values as an earlier one, which no price depends on,
  is dropped (one variant per choice of the others, the one whose repeat equals the option); a repeat that changes
  the price stays an option of its own ("Flex", "Flex 2").
- **Options**: the translation's, without a leading "Select" and with " / " made "/" (Shopify refuses it in a name),
  values without a seller's numbering ("01.", "SPEC"); two values with one English get "(2)". A product with one
  variant is named by the seller's one remaining choice (a constant option axis the transform keeps as a fact:
  "Set: 12 Pcs + Caddie Bag"), else `Option: Standard` (`FALLBACK_OPTION`); a gift line is not a choice.
- **Apparel sizes** (a category with `CategoryRules.sizes`, knit cardigans 50002797; the owner 2026-11-19): the size
  option is named `Size` and holds the US sizes only ("S (US 4-6)", "One Size"), never the Korean; the Korean value of
  each is kept for the owner's orders on Naver in the variant's `fairwardgolf.source` (`optionsKo` as always, plus
  `sizeKo` / `sizeUs`; `sizeKo` the seller's own Naver value, `naver_size_ko` when a value was split, 2026-11-25) and the product's `fairwardgolf.sizes` (`fairwardgolf-sizes/1`: the map US -> Korean with the
  chest in cm and how it was read, the merged spellings, the seller's chart in cm). The description ends with the
  size chart block (`apparel_sizes.chart_html`, inches), built here, not by the model. [SIZES.md](SIZES.md).
  Its other options lose a seller's colour code ("C5: Gray" -> Gray) and a photo note ("(Worn by Model)"), and an
  option named for its colour is "Color" ("Windproof Cardigan Color"; 2026-11-20); the clubs' options are untouched.
- **Title clean-up** (`clean_title`): "(Parallel Import)", a word written twice in a row, a model code written
  twice. SEO title = the title (the site's page `<title>`), cut at a whole word within 70 characters.
- **Title length** (`fit_title`): at most 150 characters, Google Merchant Center's limit for `title` (a longer one
  is an item issue there; Shopify itself takes 255). The translation already asks the model again for a title over
  100 (TRANSLATION.md); this is the last guard, with the brand put in front counted: the facts after a comma go
  first, from the end, when that keeps 60% of the limit, else whole words from the end; nothing is left dangling (a
  joining word, a comma, a count without its unit: "Set 13" of "13 Pieces", an open bracket), and a brand that
  stood only in the part cut off goes in front. Google truncates a longer title itself and warns ("Text too
  long"); it shows about the first 70 characters, which is why the title's order is brand, model, who, what.
- **Add-ons**: gift words out of the English labels ("Free", "Gift", "Default Selection"); a required free group
  of a one-variant product goes to `custom.required_selections` (product-required-selections/v1, the site's field
  for a choice the buyer must make; "do not add" is no value there). A required choice of a product with several
  variants stays in `custom.optional_addons`: the site's contract allows `required_selections` on one-variant
  products only, so showing it as required is the site's change (the owner, 2026-11-09).
- **Reviews**: a review the cleaning cut mid-sentence and the English ends on "and" is closed ("Lightweight.").
  Text-field labels take one wording ("(e.g., John Doe)").
- **Reviews**: a sentence of the English about the price or the value, or naming another platform or a buying
  agent, goes (`review_clean.cut_english`, the owner 2026-11-09); a review with no text left and no photo is not a
  row (its score is in the rating); one with photos only gets a short neutral line (`PHOTO_ONLY_TEXTS`, picked by
  the review's id); a row Naver gave without an id, score or date is left out (one bad row empties the site's
  whole feed).
- **Photos**: alt "<brand> <title> - photo N" (the brand once when the title starts with it). A product with fewer
  than 2 photos of its own gets buyers' photos after them, 5 photos in all at most (the owner 2026-11-09, a fuller
  gallery for Google Merchant; never from the description images). `review_rank` orders the reviews rated 4-5 (a review telling of a defect, `DEFECT_RE`: 불량, 파손, 찢어, "상태가 안좋", 실밥 ..., gives no photo whatever its score, 2026-11-26, a split zipper of PXG 10556770499; `told_defect`, 2026-11-27: not the
  ground's state, "잔디의 상태가 안좋은 계절에", nor a defect said absent, "아무 하자 없이"):
  the review's usefulness (`text_quality`, Naver's "helpful" votes `likes`, a full text over a short one), several
  photos first (the owner), lower for a review that told of the purchase (seller, packing, shipping: its photo is
  often the box); a review with one photo and no product words, or about the purchase only, is passed over.
  `review_gallery` takes one photo per review a round (the review's first photo the gallery may show), two rounds;
  never a photo shown already (same hash), one under 400 px, a strip (over 2.2:1) or one mostly grass-green (over
  15%: a course, a range, a screen-golf room). Measured on the pilot (judging agents on 80 picks): the text tells
  little of what a photo shows, so `publish/gallery_skip.txt` (sha256 per line, "# why") strikes out a photo a
  person saw was wrong (boxes, a shop, people); a photo check by a vision model was offered and declined (the owner,
  2026-11-09).
- **Not sent**: descriptionHtml for a product without a description (`describe.py`, [DESCRIBE.md](DESCRIBE.md)), HS /
  origin codes, Naver's delivery data as such (the seller's fee in Korea and the box are inside the price; the
  box's fields are in `fairwardgolf.package`), facts, spec rows (`product.specs`: the description's input only,
  `describe.py`; the owner's corrections in `<shop>/specs_by_owner.json`, 2026-11-18), gender (placement uses it
  for the sections), compare-at.

### Metafields

Storefront (`custom.*`, the site reads them, the harvester's formats kept): `review` (rating),
`rating_count`, `reviews_seo` (up to 20 rows: id, customer {name, avatarUrl}, rating, title "", description,
images, verified false, source, createdAt), `reviews_feed_url` (the JSON feed, every row, `date` instead of
`createdAt`), `personalization_fields` (product-personalization/v1; a field without an English label is left out,
`maxLength` only when the seller set one), `optional_addons` (product-optional-addons/v1: complimentary choices
only, `{key, label, priceKrw: 0}` and nothing more). The site reads these through strict schemas (naver-harvester
`store-scripts/shared/src/product-*.ts`, `shared/product-configuration/limits.ts`, `shared/reviews/`): an extra key
or a paid choice hides the whole block (seen on the site 2026-11-08). Ours (`fairwardgolf.*`, not on the storefront, one JSON per
concern with a `schemaVersion`; a new value is a new field there, a new concern a new key):

| Owner | Key | What |
|---|---|---|
| product | `source_offer_id` | The source key (the shop check and the update find the product by it) |
| product | `source_url` | The Naver page, without its query |
| product | `source` (json) | platform, key, url, channel / product / category ids, run, Korean title and brand, `priceKrw`, `originalPriceKrw` |
| product | `pricing` (json) | How the prices were made. A shop without the rule: `fairwardgolf-pricing/1`, version `krw-cost/1`, `krwPerUsd`, rounding, margin null. With it: `fairwardgolf-pricing/2`, version `landed/2` and every number of the rule (`krwPerUsd`, `serviceUsd`, `dutyRate`, `koreaPaid`, `coefficients`, `margin` (`fixedUsd`, `rate`, `minUsd`), `paymentRate`, rounding), the tariff (`id`, `checkedAt`, `version`, `sha256`), the dates of the owner's decisions (`decided`) |
| product | `addons` (json) | Every add-on, paid ones too: group (`required`), choices with `priceKrw`, `costUsd`, `priceUsd` (the rate only: no delivery, duty or margin), `free`; ready for the day the site sells paid add-ons |
| variant | `source` (json) | Naver variant id, source id, Korean options, `priceKrw`, `costUsd` (Shopify's cost per item: with the rule the purchase + commission, no duty), `priceUsd`, `available` |
| variant | `price` (json) | With the rule only: `fairwardgolf-variant-price/1`, how the price was made: `naverKrw`, `koreaDeliveryKrw` and `koreaFeeType`, `purchaseUsd`, `serviceUsd`, `dutyRate` / `dutyUsd`, `costUsd`, `box` (cm, gross, billable, step kg), `rule`, `krwPerUsd`, `level`, `coefficient`, `tariff` (id, checkedAt, version, sha256), `gridUsd`, `insideUsd`, `deliveryUsd`, `fees` (id, usd, because), `feeUsd`, `baseUsd`, `marginUsd`, `keepUsd`, `paymentRate`, `neededUsd`, `priceUsd`, `paymentUsd`, `surplusUsd` |
| variant | `package` (json) | The five shipping fields as the transform made them (value range, `confidence`, source, reliability) |

The harvester's other keys (`custom.measurements`, `*_confidence_level`, `fairwardgolf.source_variants`,
`source_pricing`, `catalog_*`, `enrichment_state` ...) are not written; their definitions stay for its 60 products.

### Access and uploads

Credentials: a store app's client id + secret file per store, its path in env as `shop_stores.py` names it
(`SHOPIFY_CREDENTIALS_FAIRWARDGOLF`), next to the store's domain, shop id, API version and namespace there; tokens are
minted per run (`shopify_catalog.Credentials`; the writing apps: Publication, Access). They are never committed. A
product's key, which every `--only`, `--withdraw` and `--activate` takes, is its source key
(`<namespace>.source_offer_id` = `<namespace>:naver:<channel_no>:<product_id>`, e.g.
`fairwardgolf:naver:500048270:12154351233`); a lens's `index.tsv` and the ledger give it by number or product id.

Access: `ProductsAdmin` (PRODUCTS_API_*, write_products) and `FilesAdmin` (ADMIN_API_*, write_files), both keys in
the store's credentials file, tokens minted per run as in the shop check. `ShopCatalog` stays read-only.

Uploads in batches (2026-11-09): a product's new review photos and avatars, and its new gallery photos, go at once:
names searched 10 a query, one `stagedUploadsCreate` and one `fileCreate` per 50 files, the files sent to the
staging bucket 6 at a time (each retried on 429 / 5xx), one `nodes()` poll for the whole batch. The GraphQL calls
stay one at a time: Shopify limits by query cost per app and store (this store: a 2 000-point bucket, 100 points a
second back; a search of 10 names costs ~5, a mutation ~10), and a THROTTLED answer, a 429 or a 5xx waits what
Shopify says and repeats (`shopify_catalog._send`). The measurement: History, below.

## History

The design note that came before the publication, the harvester's products it learnt from, and the measurements.

**Uploads, measured live**: 30 photos in 8.3 s (0.28 s a file, 7 GraphQL calls) against 4.0 s a file
one by one (5 calls a file).

### Shopify roadmap

This is a design note, older than the publication above. The code so far: the read-only check of what a store already has (`shopify_catalog.py`),
the transform to prepared products (see TRANSFORM.md, Transform) and the placement into the shop's sections (`placement.py`, see
PLACEMENT.md) and the translation (`translate.py`, see TRANSLATION.md, Translation: `translation/translated.jsonl`, English by text
id); publication joins them (`publish.py`, see Publication).

The pipeline: collection (example_99) -> kept runs (`keep_run.py`) -> prepared products (`run_transform.py`:
prices in USD, options, SKUs, attributes, spec rows, text fields, free add-ons, reviews, photo files) ->
translations by text id -> placement (`placement.py`: the shop's sections, tags, product type) -> publication. Settled in the transform: the currency rule, the variant cap (over it: the
first combinations, every pair of values, `variants_capped`), the photos (re-uploaded WebP files, not Naver's CDN).
Settled since: publication through the Admin GraphQL `productSet` (see Publication); delivery, duty and margin
inside the price of a shop with free delivery (see PRICE.md, The price, the owner 2026-11-11).

Publication is `publish.py` (above; its credentials and the product's key: "Access and uploads"); the start variant per collection is not sent (ONBOARDING.md C11).

### What the naver-harvester published (reference for publication)

Read from 60 of its products in the shop (391 variants, all metafields; 2026-11-05). Repeat what works, not its
mistakes. A local snapshot of those 60 (not in git): `scripts/output/harvester-shopify-products-2026-11-05.json`.
- Body: `descriptionHtml` empty on 60 of 60; the text is in `custom.description_html`: optional prose `<p>` blocks,
  then one `<p>` of `<strong>Label:</strong> value<br>` rows (at most 60000 characters; 37 of 60 had spec rows
  only). Hidden labels: product number and date of manufacture (the label NFKC-lowercased, `\s:._-` stripped:
  productnumber, productno, 상품번호, manufacturedate, manufacturingdate, dateofmanufacture, 제조일자, 제조년월, 제조연월).
- Reviews: `custom.review` `{"scale_min":"1.0","scale_max":"5.0","value":"4.9"}` and `custom.rating_count` from
  Naver's summary, only with a count above 0; `custom.reviews_seo` holds the rows, and the same rows go to a Shopify
  File linked from `custom.reviews_feed_url`. A row: `id = int(sha256("naver:" + reviewId)[:12], 16) + 1`,
  `customer.name` the masked id, `title ""`, `verified false`, `source {platform: naver, language: ko, translated:
  true, reviewId}`, `createdAt`, images as Shopify Files links.
- Text fields: `custom.personalization_fields` (product-personalization/v1: key, label, required, placeholder, hint,
  maxLength; the seller's maxLength less the operator's suffix). Add-ons: `custom.optional_addons`
  (product-optional-addons/v1: groups `{key addon_<24hex>, label, choices [{key choice_<24hex>, label, priceKrw}]}`).
  `custom.required_selections` (a fold), `custom.category_start_variants`.
- Private `fairwardgolf.*` metafields (no storefront access): `source_offer_id`, `source_url` (no query or
  fragment), `naver_offer_key` (legacy), `catalog_fingerprint`, `catalog_stage` `showcase-cost-priced/v1`,
  `source_variants` v2 `{offerKey, translationHash, variants [{sourceId, variantId, optionValues, sku}]}`,
  `source_pricing` `{source {url, observedAt, basePriceKrw, originalPriceKrw}, policy, excluded, variants}`.
- Tags: leaf, parent and showcase tags plus `fairwardgolf:naver` (dropped once the public handle is set). Products are
  created DRAFT, then activated; `inventoryQuantity` 0 on all 391 variants.
- Handle: strip ™®© and apostrophes, NFKD without combining marks, refuse any non-ASCII left, lower case, join
  `[^a-z0-9]+` with "-"; refuse an empty one, over 255 characters, the word "naver" or a source id; the brand in front
  unless the name starts with it; a collision holds the product until a person writes a seoName.
- Brand: a Latin brand is its own English name, else a 23-entry dictionary (`mappings/brands.en.json`), then a
  reviewed spelling; distributors dropped (테일러메이드코리아 -> TaylorMade, 던롭코리아 -> XXIO).
- Images: `<handle>-NNN-<hash16>.webp`, alt = the title (at most 125 characters).
- Its mistakes: vendor drift (HONMA / Honma / Mutsumi Honma, PING / PING Golf) and doubled-brand handles, "korea" in
  6 handles, 45 distinct option names (one of 35 characters, "Color: L"), spec-label drift ("Total club count" /
  "Total number of clubs"), Event rows on 11 of 60 and pointer rows on 7 of 60, 62 of 250 alts duplicated or stale,
  2 products with no review rows though the counts said 3 and 21.
