# Translation: Korean product texts to English

How the translation stage works, the owner's decisions behind it, its dictionaries, rules and prompts, the review
cleaning, how to add a shop (tenant) or a Naver category, how to check the quality, and what is still open; the
history (with the measurements) is at the end. The code: `translate.py` (the stage), `translation_dicts.py`
(dictionaries), `translation_rules.py` (unit templates), `review_clean.py` (reviews, in the transform),
`translate_keys.py` (the keys), `translate_eval.py` (the quality check), `prompts/` (system prompt and briefs). The
transform that writes the texts: [TRANSFORM.md](TRANSFORM.md) "Transform".

## How to use

Commands from the repo root (the model calls cost money: small runs first):

```sh
.venv/bin/python scripts/translate.py fairwardgolf --offline   # no model: what the dictionaries and rules leave
.venv/bin/python scripts/translate.py fairwardgolf --limit 3   # the model for 3 products
.venv/bin/python scripts/translate.py fairwardgolf --only <key>  # only this product to the model
.venv/bin/python scripts/translate.py fairwardgolf --reask --keys-file F  # their titles asked again (notes)
.venv/bin/python scripts/translate.py fairwardgolf --reask --keys-file F --context "TEXT"  # + a context for each title
.venv/bin/python scripts/translation_dicts.py status [--json]  # sync helper: dates, what the backup lacks, advice
.venv/bin/python scripts/translation_dicts.py backup           # by hand: live -> scripts/dictionaries/, then commit
.venv/bin/python scripts/translate_eval.py fairwardgolf --products 12   # the quality check (a second model judges)
```

A job made since 2026-11-08 runs this stage per product, right after prepare (`job.py`, `translate_one`, translated;
`new --no-translate` leaves it out). See [JOB_AGENT.md](JOB_AGENT.md).

Out, in `shops/<shop>/translation/`: `translated.jsonl` (per product: status, English by text id, where each came
from) and `report.txt` (counts, tokens and cost, new dictionary entries). What to do per status:

- `translated`: placement and publication can use it. Publication (`publish.py`, 2026-11-08) reads
  `translation/translated.jsonl`; a text without English holds the product.
- `untranslated`: a text failed the checks twice (its `problems` in the record, the reasons in `report.txt`). Fix
  the brief, the rules or the dictionary entry, then run again (`--only <key>`).
- `pending`: no provider answered, or the product was not asked (`--offline`, `--limit`). The next run translates it.
- `held`: the transform held the product; nothing to do here.

When a dictionary backup is due, a `translate.py` run's report (not `--only`) and `job.py run` (done) /
`job.py status` print one reminder line: run `translation_dicts.py status`, read the changed entries, then `backup`.

| Task | Section |
|---|---|
| What the stage translates and in which order (own store, dictionary, rules, model) | [Translation](#translation-translatepy) |
| Why the stage works as it does (model, fallback, tokens, what is not translated) | [Decisions](#decisions-the-owner-2026-11-08) |
| A product's own title or review | [1. The product's own store](#1-the-products-own-store) |
| A term wrong for every product; live and backup dictionaries | [2. Dictionaries](#2-dictionaries) |
| Units, sizes, 노브랜드, 기타 | [3. The rules](#3-the-rules-translation_rulespy) |
| Prompts, briefs, checks, fix rounds, fallback, batches, tokens, keys (a change: skill `prompt-change`) | [4. The model and its prompts](#4-the-model-and-its-prompts) |
| Reviews cleaned wrong | [Review cleaning](#review-cleaning-review_cleanpy) |
| A new shop (tenant) or Naver category | [A new shop (tenant) or category](#a-new-shop-tenant-or-category) |
| Is the translation good? | [Quality check](#quality-check) |
| A known wrong case, what is still open | [Known limits](#known-limits), [Open](#open-2026-11-08) |

## Translation (`translate.py`)

The owner (2026-11-08): the prepared products' `texts` go to English through Claude Sonnet 5.5 (effort low, JSON
output) before placement and publication. Not translated: `description_ko` and the images' text (a later stage
writes the description from them; their `to_translate` flag is not this stage's).

Per text, the first that answers: (1) the product's own store, (2) the dictionary of its kind, (3) the rules,
(4) the model. Each is below. The commands, the outputs and what to do per status: [How to use](#how-to-use).

## Decisions (the owner, 2026-11-08)

| Decision | Where it lives |
|---|---|
| A model API translates. Not the session's agent. | `translate.py` |
| Claude Sonnet 5.5 at effort low; OpenAI as the fallback; models changed in `.env`, not in code | `settings()`, `.env.example` |
| The description and the images' text are not translated: `describe.py` reads them in Korean and writes the English description (the owner, 2026-11-10; [DESCRIBE.md](DESCRIBE.md) "The product's description") | `transform._texts` (not in `texts`), `describe.packet` |
| One dictionary per kind of text, in JSON, growing during runs out of git; backups in git, updated by hand; `status` says when a backup is due | `translation_dicts.py`, `scripts/dictionaries/` |
| Brands are the shop's (`dictionaries/brand.json`); every other kind is a Naver category's own (`dictionaries/<category id>/<kind>.json`): a new category starts empty and its entries never reach another (2026-11-11: 50002787's entries had changed four products of 50002788) | `translation_dicts.SHARED`, `Dictionaries.scope` |
| The brand is looked up first; one spelling per brand in the whole shop | brand dictionary, `vendors` in the request |
| No brand (노브랜드): the tenant's name; inside a text the word is removed. A brand of 기타 ("other", the owner 2026-11-11): the tenant's name too (transform already leaves it out: the fallback decides) | `translation_rules.sanitize`, `transform.NOT_A_BRAND` |
| Units and sizes by templates (10.5도, 33인치, 22호, 3번, 7개, 2026년형); the model only for the rest | `translation_rules.py` |
| Titles are the store's names (the owner, 2026-11-08, as the harvester's): brand first, then model, year, who it is for, the kind of set, pieces, what is included; no shop, dispatch, distributor or after-sales ("AS가능") words, no loft / flex / shaft codes or club list, no usage or gift words (the 100-product pilot, 2026-11-09). The model, not templates: nobody can foresee every title | `prompts/translate_system.md` |
| A title's length: the prompt asks for about 90 characters; over 100 the title goes back to the model with "too long" (it drops the least important facts from the end: materials, colours, the club list, "for beginners"), up to 2 times; a title that never gets under keeps its shortest answer that passed the other checks and does not hold the product (nor does a refusal, a cut answer or the provider going down in a round asked only to shorten); a title already in `translation/texts.jsonl` is not asked again (delete its row to translate it again), unless the product's brand changed since: a title row keeps the `brand_ko` it was asked with, and a title asked under another brand is asked again, its old English kept until the answer (2026-11-15: Generic, Edis, PRECISE stayed at the head of fixed titles; a hand correction row has no brand and is never asked again; 2026-11-17, C06: an older model row with no brand that starts with the shop's name, "Fairward Golf …", counts as asked under 노브랜드, so 24 titles whose products have a brand now are asked again; a title waits until its new brand has its English, 13625754692; 2026-11-19, the two-brand scan: an older model row with no brand that starts with a dictionary brand other than the product's vendor, not the vendor nor a longer name of it, is asked again with that brand named, the model to keep it only if the Korean title names it: "Pongdang Swim Kids' …" under Inparo, "PING Women's Junior …" from 핑크, 45 titles, `translate._stale_lead`); `--reask` with named products (`--only`, `--keys-file`, `--job`; refused without) asks their own titles and placeholder option names again with today's notes (lofts not sold, cut, unproven words, one variant's words), the old English kept until a checked answer, a hand correction (its last row by `review-…`) never (2026-11-17, W10: 152 live wedge-set titles asked before the notes existed); `--reask --context "TEXT"` adds the text to each re-asked title item's context, after any note's (refused without `--reask`, exit 2; a hand row is still never asked; 2026-11-19, sweep's `title.set_single`: titles promising a set where one club is sold, e.g. "only one club is sold, the buyer picks its type: do not call it a set; name it as a single junior golf club"; one context fits one Naver category: run it on one category's keys file, sweep's `title.set_single/<store>.<category>.keys`, never the whole check's file); read the changes before a resend; the publication cuts to Google Merchant Center's 150 (`shopify_payload.fit_title`) | `translate.ASK_SHORTER`, `prompts/translate_fix.md` |
| Reviews as an American buyer would write them: the meaning and the strength kept, casual allowed, no machine phrasing; a sentence the cleaning cut on a joining word ends as a full sentence, a meaningless fragment is dropped | `prompts/translate_system.md` |
| Reviews kept with their score; their text loses the Korean purchase (seller, shipping, customs, won, packing, gifts) | `review_clean.py` |
| After translation, at publication: an English sentence about the price or value, or naming another platform or a buying agent, goes (the owner, 2026-11-09; complaints about the seller stay) | `review_clean.cut_english` |
| Bounded batches, a final check that every text came back, retries in the same conversation | `make_batches`, `_converse` |
| Few tokens: short ids, compact JSON, the category's terms in the cached system prompt, no thinking tokens | `request`, `system_prompt`, `ANTHROPIC_TRANSLATE_THINKING` |
| The job translates each product right after it is prepared | `job.py` (`translate_one`) |

## 1. The product's own store

Title, review, a placeholder option name (선택 / 옵션, named from its values), in `translation/texts.jsonl`. A
placeholder name with no Hangul ("Color" over "52 56 Degree Tarnish", Amazon imports; 2026-11-17, the wedge-set review
C50) is asked of the model too; until it answers the rule's English ("Color") stands. A rule never names it ("Lofts"
would rename the heights of 50002787). The same for an Amazon label of another kind than its values ("Shaft Material"
over "... LENGTH", 13390487313, 2026-11-18): the answer is that product's own row. A dictionary entry is never the
lever: the text id is shared, and "Shaft Material" -> "Length" would rename 12079165169 and 9703030793, whose values
are materials.

## 2. Dictionaries

Brand, option name / value, spec and fact label / value, add-on group / name, text-field label / placeholder. One
file per kind: the brand's for the whole shop, every other kind's per Naver category (`<category id>/<kind>.json`,
2026-11-11: a new category starts empty). The brand dictionary comes first: the model gets the shop's vendor
spellings and reuses one for the same brand. New brands enter the brand dictionary without the owner's word.

The live copies in `scripts/output/dictionaries/` grow during runs and are out of git. Their backups in
`scripts/dictionaries/` are in git and seed a missing live copy; they are updated by hand with `backup`, after
`status`, since runs never commit; a backup stamps each file `backed_up`. The sync only adds: a run takes the
entries only the backup has (pulled from git, seeded by hand), a backup writes the live entries over the backup's
and keeps its others. A wrong entry is fixed in the live copy; deleting one for good means both copies.
No lock guards the files: edit one by hand when no run is writing (`job.py status`). A fixed entry reaches products
only when they are built again: `translate.py <shop> --offline` rewrites `translated.jsonl` (a brand entry:
`run_transform.py <shop>` first, its brand fallback reads the brand dictionary); then `store_diff.py <shop>` lists
the published products it changes, and sending them is the owner's word ([OWNER_RULES.md](OWNER_RULES.md) rule 1).
A title is the product's own text, not rebuilt: a brand fix of case or punctuation follows into it, one of letters
leaves the old spelling with the new brand in front (`shopify_payload.title_vendor`; skill `dictionaries` step 5).
The live copies are in the state backup (`state_backup.py`, OPERATIONS.md "Backup"); `scripts/dictionaries/` is git's.

**Brand spellings chosen in the wedge-set review** (2026-11-17, commit 6897a05): the maker's own spelling in its
description text over the case of Amazon's Brand Name field (stix -> Stix, pron -> Pron, KIRKLAND -> Kirkland,
Bombtech Golf -> BombTech), never a spelling whose `brand_key` the titles lack (`title_vendor` would put it in front:
"Mystery Golf Mystery R-Line", "Kirkland Signature Kirkland"); Detroit Golf Co without the dot (`_LEGAL_RE` cuts "Co."
to "Detroit Golf"); Professional Open Series -> Hireko (a Hireko line, not a maker); none for YAMAHA / BridgeStone /
BALDO (`vendor_spellings` ignores case). Since f44ae7d the store's first spelling beats the dictionary for a brand it
has (PUBLISH.md "The payload"): Kirkland 9951345559 went out as "Kirkland", the spelling of the older "Kirkland
Signature 2nd Generation". Not added on purpose: 핀클리 stays A11N SPORTS (9 products read it; Finchley is the brief's);
no 토호 골프 nor a bare TEAM (C05); no 프로니즈 (the 50002783 brief's "프로니즈 = Pron" only, C29); 피네모 / 파인메도우 /
피네메도우 -> Pinemeadow Golf put off (C33), then added with 피네모도 in the chipper review (2026-11-18: the chippers
write 피네모도 / 파인메도우; 5 wedge sets read before by their Brand row change `brand_ko` only, the vendor stays
Pinemeadow Golf, 2 active ones' titles reach the store on the owner's word); no "Mystery Golf", no general "drop Golf" rule
(C28); T WINSOLOGY not made TWINSOLOGY. Disagreeing across dictionaries, open: brand.json 다우리 -> Dauri against
50002787/spec_value Dawoori, 로마로 -> Romaro against 50002670/spec_value and its brief's RomaRo (C34).

**The chipper review** (2026-11-18): 넥스젠 NEXGEN, 마이쿠자 MYKUJA (the store's first spelling), 머니 클럽 / 머니클럽 Money
Club, 치퍼랩 CHIPPER Lab, 무츠미혼마 Mutsumi Honma (beside 무쯔미혼마) added; 캘러웨이 오디세이 -> Odyssey (the brief:
Odyssey is the maker of the Odyssey chippers, Callaway's putter line); 브랜드. -> Brand. and the shop 수수's partner
phrases 수수협력사 co. / 수수랜드협력사.co. deleted (no brand: `brand_fallback.clean` / `resellers_own`).

`status` shows when the live copies were last written and the last backup (every backup file carries
`backed_up`), the new and changed entries since, the ones only in git, and the advice (`action` none / wait /
backup / review in `--json`). A backup is due at 20 waiting entries, or 7 days after the last one with any waiting
(`BACKUP_AT_CHANGES`, `BACKUP_AFTER_DAYS`); changed entries are read first, since the backup writes the live
English over git's.

## 3. The rules (`translation_rules.py`)

- 10.5도 -> 10.5°, 33인치 -> 33 in, 22호 -> Size 22, 3번 -> #3, 7개 -> 7 / 7 pcs, 12종 -> 12 pcs, 2026년형 -> 2026 model;
- 노브랜드 alone becomes the tenant's name (`Store.publisher`), and inside a text it is removed;
- a brand of 기타 ("other") alone becomes the tenant's name as well (2026-11-11);
- a category's own templates, if its specs glue together like golf's flex runs: `CATEGORY_RULES` (a glued spec run
  is split after each flex letter);
- a category's title rules, titles only: `TITLE_RULES`. Wedge sets (50002783, the owner's review 2026-11-16): the
  shop sells sets only (`sets_only`), so "세트 또는 개별 / 또는 개인(용) / 및 개별 / 세트 개인용 / or single" is dropped,
  and a glued run of lofts ("525660도", "5460") becomes "52°/56°/60°" (two digits a loft, 46-72, going up; "or" only as
  a word, "/" only right after 세트 / 웨지; two lofts only next to 도 / ° or after 세트, a run before a 도 that starts a
  Korean word stays: "모델 4856", "5256 도매"); every
  category's titles lose an import tool's marker "db" + two capitals or digits ("db4P", "dbT1"). 2026-11-17 (the
  wedge-set review): a glued run of up to ten lofts ("48505254565860687072°", C24), and every category's titles lose
  a seller's product code at their end ("WA3817568", "SA3882511", "품번 1116": the description's 상품코드, C07; inside
  the title a code stays). A title already
  translated keeps its English: delete its row in `translation/texts.jsonl`, or write a correction (skill
  `fix-a-product`), to change it;
- a category's option-value rules, option values only, after the general ones: `OPTION_VALUE_RULES`. Wedge sets
  (50002783, the wedge-set review C54, 2026-11-17): raw lofts become the list the titles use: a whole value of two or
  three glued even lofts going up ("5056" -> "50°/56°"), a whole "loft.bounce" ("56.12 SB" -> "56° (Bounce 12°) SB"),
  lofts glued by their degree signs ("50°56°" -> "50°/56°"), a run going up before Degree / ° ("52 56 60 Degree Set" ->
  "52°/56°/60° Set"), an import's " 1 pcs" tail right after a set's "(2 pcs )" or "Set" (also from the Korean "… (2개) 1개":
  the value is trimmed before these rules; any other value keeps its count, "블랙 1개" -> "블랙 1 pcs"); a dictionary hit is taken as it is;
- "Sliver" / "sliver" as a word of its own -> "Silver" / "silver" (a seller's typo, every category; C55);
- a text with no Hangul left is done; the rest goes to the model already converted.

## 4. The model and its prompts

One request per product, with the system prompt in `prompts/translate_system.md`. Each item is checked:
- every id is returned once;
- no Hangul is left;
- the source's numbers and Latin codes are kept;
- the text is within its length limit;
- the option values stay distinct.

What fails goes back in the same conversation (`prompts/translate_fix.md`), at most twice. What still fails
leaves the product `untranslated`; what passed is kept.

**A title's context from the transform's notes** (`plan`): `title_names_one_variant` (words only some variants have:
drop them; their numbers and codes need not survive, matched spacing aside, "13 PCS" = "13PCS", 2026-11-17 C47);
wedge sets, 2026-11-17: `title_lofts_not_sold` (C46: the title's lofts that are not one set sold, with the sets sold:
write only a set sold; those lofts need not survive the number check, or the corrected title would be refused) and
`title_cut` (C48: Naver cut the title at 50 characters; its loft list may be incomplete, no piece count it does not
state; the cut word at its very end, "S" / "샌", is left out and is not checked, only at the end);
`title_word_unproven` (C67, 2026-11-17, any category: 단조 the agency 102454334 writes on its titles, its page never
saying forged: leave it out; a title already translated keeps its "Forged" until it is asked again).

**The system prompt is assembled** (`system_prompt`):
- the translator's role and rules (`prompts/translate_system.md`);
- the shop's brief (`prompts/tenants/<shop>.md`: who sells to whom, spelling, tone);
- the category's brief (`prompts/categories/<Naver category id>.md`: what the products are, their terms, how buyers
  write about them).

A missing brief is left out, and the base prompt works alone, less precisely.

**Fallback:** OpenAI (the owner, 2026-11-08), through Chat Completions with a strict JSON schema, the same
prompts and reasoning effort low. Its model is `OPENAI_MODEL` in `translate.py`; `OPENAI_TRANSLATE_MODEL` in
`.env` overrides it.
- **When Anthropic is down** (network, 5xx or overload, a rate limit after the SDK's retries, another API error):
  that batch starts again on OpenAI, and Anthropic rests 10 minutes. A declined or cut batch also goes to OpenAI,
  without the rest.
- **A refused key** stops the run.
- **Every provider down:** the product stays `pending` for the next run.
- The report says which model answered each product.

**Batches.** A product is never sent whole when it is long. Its short texts go in batches of at most 40 items /
2 500 characters, its reviews apart in batches of at most 8 / 2 500 (`make_batches`). Each batch is its own
conversation with its own fix rounds and provider fallback. At the end every pending text must have an answer, or
the product is `untranslated` (a batch no provider could take: `pending`).

**Tokens** (the owner, 2026-11-08: no overspend):
- **The request:**
  - compact JSON;
  - the batch's short ids (`1`, `2` ...) instead of the text ids, both ways;
  - the category's terms only in the system prompt, which is cached and read at a tenth of the input price;
  - the shop's vendor list only when a brand is asked.
- **No thinking:** `thinking: between_tools`, with effort low. On simple words it gave the same English at fewer
  output tokens and 20% less time. `ANTHROPIC_TRANSLATE_THINKING=adaptive` turns it back on.
- **Where the cost goes:** the output, that is the English itself.

**The keys and the models.** `scripts/translate_keys.py install <file>` moves the operator's key file out of the
repo, makes it 600, and sets `TRANSLATE_KEY_FILE` in `.env` ([SETUP.md](../SETUP.md)). The models, their efforts
and the chain's order are `.env` settings, not code (`TRANSLATE_PROVIDERS`, `ANTHROPIC_TRANSLATE_MODEL` / `_EFFORT`,
`OPENAI_TRANSLATE_MODEL` / `_EFFORT`; `translate.settings()`); unset, the order is `openai,anthropic` (the owner,
2026-11-18: gpt-6.1-terra first, `translate.DEFAULT_ORDER`). The server-side refusal fallback is sent only to the
Claude models that take it.

## Review cleaning (`review_clean.py`)

Runs in the transform, before translation: every review is kept with its score, and its text loses the Korean
purchase (seller, shipping, customs, won, packing, gifts). The purchase topics (shipping, seller, price ...) are
the same for every category; what protects a clause is the category's own: the product words (`ASPECTS` and
`PRODUCT_WORDS`, keyed by the Naver category id) and where the product is used, counted only when it is not a
purchase reason (`CONTEXT`). After translation, at publication, `cut_english` drops an English sentence about the
price or value, or naming another platform or a buying agent (Decisions, above).

Its limits:
- A purchase remark in the middle of a Korean sentence that also names the product stays there: "제품구성이 좋고
  가격도 저렴해요". Cutting it would break the sentence. When it is about the price, the English sentence goes at
  publication (`cut_english`), the product words in it too.
- A rare form the patterns do not know stays in the text, for example "여러가지로 친절하고 ... 처리해 주었으나". Add
  such forms to `review_clean.py` with a test when they show up.

## A new shop (tenant) or category

Nothing in the stage's code changes; it needs short brief files only (the whole checklist, every stage:
[ONBOARDING.md](ONBOARDING.md)). Per case:

1. **The shop.** Add `prompts/tenants/<shop>.md`: who sells what to whom, the spelling (American or British) and
   the tone, in three lines. 노브랜드 becomes the shop's `Store.publisher` (`shop_stores.py`).
2. **The category.** Add `prompts/categories/<Naver category id>.md`, following 50002788:
   - what the products are;
   - the terms (Korean -> the shop's English);
   - the model lines and brand names the model may not know;
   - how buyers write about the products (slang).
3. **Reviews of that category** (`review_clean.py`):
   - the product words that protect a clause: `ASPECTS` and `PRODUCT_WORDS` keyed by the category id;
   - where the product is used, counted only when it is not a purchase reason: `CONTEXT`.
4. **Templates of that category**, if its specs glue together like golf's flex runs: `CATEGORY_RULES` in
   `translation_rules.py`, with a test.
5. **Dictionaries.** The category gets its own folder `scripts/dictionaries/<category id>/` with its first entries;
   optionally seed it with the category's spec labels and common values. Read every new entry before the first
   backup (8 of the junior clubs' first 108 were wrong).
   Otherwise the first runs fill the live copies, and `status` then `backup` keeps them.
6. **Check:**
   - `translate_eval.py <shop> --products 12`;
   - read `report.html`;
   - fix the brief or the rules;
   - run it again until few rows are flagged.

## Quality check

`translate_eval.py` takes a varied sample of ready products and translates it in its own folder with empty
dictionaries. A second model (Opus 5.5) then judges every translated text, and the script writes a side-by-side
`report.html` with the flagged rows marked. It costs about $0.05 a product and never touches the shop's translation
files or the live dictionaries. The rounds run so far: History, below.

## Known limits

- **Reviews**: see "Review cleaning" above.
- **Ambiguous Korean.** The model may give an opinion to the wrong person ("디자인도 맘에 듭니다" after "와이프 ...").
  The judge flags it; the prompt asks to keep the buyer as the subject.
- **Titles keep every code of the source**, so a model written twice stays ("BG-100L BG100L"). Titles translated
  before 2026-11-08 evening are the literal ones (in the texts store); they change only when translated again.
- **Category scope.** 50002788, 50002787 (junior clubs, 2026-11-11: its own brief; the sets' glued-flex rule, review
  aspects with a parent's words and glossary) and 50002670 (women's iron sets, 2026-11-14: its own brief; the sets'
  rule, aspects, product words and glossary) and 50002783 (wedge sets, 2026-11-15: its own brief, the sets' rule,
  aspects, product words and glossary) and 50002784 (chippers, 2026-11-18: its own brief with the listing's makers
  and lines, the clubs' rule and glossary, the clubs' aspects plus the short game's, product words plus 치퍼 / 칩퍼;
  its brief keeps a title's loft in degrees, 2026-11-18: History) and 50002797 (women's knit cardigans, 2026-11-19:
  its own brief with knit, fibre and fit terms, department-store prefixes dropped, a title of brand + Women's +
  garment + key feature with no size run, sizes never converted; `translate.TITLE_SIZES` lets a title's size run
  (55 66 77, 90 95 100) be left out without "numbers changed" (a free-standing number only: a code's tail, K90,
  must survive); aspects and product words of fit, length, thickness,
  pilling and washing)
  have a category brief, aspects and rules. Another category gets the
  base prompt and the general aspects until it has its own.

## Open (2026-11-08)

- **The OpenAI fallback** has never answered live: the account has no credits (429). Until it has, a down Anthropic
  leaves products `pending`.
- **The dictionaries**: a few model answers there are worth a second look, for example "9도 S4번유틸S ..." -> "9° S4
  Hybrid ..." (a flex letter glued to the next club's number, with a space before it).

## History

**Checked 2026-11-08, golf sets** (`translate_eval.py`, 12 varied trial products, 260 texts, a second model
(Opus 5.5) as the judge): 25 flagged, then 17, then 10 (3.8%) after three rounds of fixes:
- the golf terms and model lines in the category brief;
- a glued spec run split after each flex letter (`CATEGORY_RULES`);
- review fidelity in the system prompt: no "for the price", the subject kept, no upgrade of strength;
- a title's words that only some variants have (the note `title_names_one_variant`) passed as context;
- text addressed to a model cut from reviews.

The 10 left were nuances in reviews (two broken in the source already), a brand spelling (since added) and one
label.

**Live checks the same day:**
- a rerun asks nothing (0 calls);
- an interrupted run keeps every product it finished; an untranslated item resumes;
- every provider down leaves the products `pending`, and the next run translates them;
- a 24-value option takes two batches; a 1 700-character review is translated whole;
- a job of 3 new products went from the listing to translated and placed: about $0.01 and 5-9 s a product for
  translation, against 66-98 s of collection.

**Tokens, measured 2026-11-08** on 4 varied trial products (129 texts, empty dictionaries): 11 batches, 12 calls
(one fix round), all translated, about $0.015 and 8 s a product, $0.0005 a text. With the dictionaries the shop's
repeated texts cost nothing.

**On the 143 trial sets** (2026-11-08):
- without the model, the dictionaries and rules gave 3 606 of 4 877 texts;
- the model is left 1 271: titles 143, reviews 442, option values 292, spec values 505 (with repeats across
  products, each asked once per product);
- the reviews are sanitized but all kept, so 411 review texts are left (the cut text is gone from them).

**Wrong entries deleted** (2026-11-11, the owner: "ошибочные удаляй"): all 1,676 entries were read by a model
reviewer and each flag by three more; the 40 that at least two confirmed were deleted from both copies (기타 ->
TaylorMade, 브리지스톤골프 -> Bridgestone Golf, Nikent for Nickent, flex letters glued to the next club ("S4
Hybrid"), 백미포함 read as "with bag", an added "Driver", a dropped 여성, Glory for Gloire, ...). The next run
asks the model for them again. The 23 published products that used them stay as they are in the store until
they are published again; until a full `translate.py` run their record is `pending`.

**Checked 2026-11-17, wedge-set prompt lines** (`translate_eval.py --shops-root <sample>`, 15 products of the
wedge-set review, reviews left out, empty dictionaries; $0.07 translation + $0.15 judge): the base prompt's gender line
(C66: men's / women's / unisex only from 남성 / 남자 / 남, 여성 / 여자 / 여, 남녀; a hand is not a gender) and the
50002783 brief's 핀클리 / 핀칠리 Finchley, 리믹스 RMX, 제로 투어 Zero Tour (C68), 프로니즈 Pron (C29). "Men's" left the 8
titles that had it with no source (12079168386, 13017295953, 13372272290, 13382512411, 13384608635, 13406052242,
13312109978, 13830312687); 남 kept "Men's" (5414445973), 남녀 gave "Unisex" (13492459923, was "Men's Women's");
Pinkley / Pinchilly -> Finchley, Remix -> RMX, 0 Tour -> Zero Tour, Pro-Knees gone. One "Men's" came from the
spec row 성별 남성용 (12425620541). 9 of 104 texts flagged by the judge (a dropped flex "S", a spin claim, a leftover
"Legal", 노브랜드 as the shop's name: none from these lines).

**2026-11-18, the chipper brief's loft line** (not measured with a model: the owner delegated the decision, no paid call
was made). Two chippers stayed `untranslated` on "numbers changed": gpt-6.1-terra wrote "PGM Chipper" for "pgm 37° 칩퍼
치퍼" (12181419107) in all three calls of both job attempts, and left out "52도 56도 60도", the loft option's values, of
"CHIPPER Lab 골프 치퍼 52도 56도 60도 ..." (11664750138), while the same model kept the loft on about ten other chipper
titles ("PGM TUG019 35° Chipper-Putter" 6934029230, "Giga Golf RIC Chipper 35°" 4906542106, "... 35° 45°" 9993149923).
The likely trigger is the base prompt's title rule "No loft, flex or shaft codes (... the options say them)", meant for
joined codes ("11.5L", "#4 L") but read as covering a bare "37°"; the check is right (no note frees those numbers).
The base prompt is unchanged (its loft-code rule is right for the sets); `prompts/categories/50002784.md` says a
title's loft in degrees is a fact of the chipper and stays, a listed loft option's values too, with the two products
as the examples ("PGM 37° Chipper", "Chipper 52° / 56° / 60° Wide Sole"). Offline: `test_a_chippers_loft_stays_in_its_title`
(the brief reaches the prompt; the check accepts those answers and refuses "PGM Chipper"). It reaches the two products
when they are translated again (`translate.py fairwardgolf --only <id>`, the owner's word); a published title is not
asked again. A listed loft that is sold out (56° / 60° on 11664750138) stays in the title, as on the store's other
chipper drafts (9993149923's 45°): not handled.
