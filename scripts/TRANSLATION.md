# Translation: Korean product texts to English

How the translation stage works, the owner's decisions behind it, how to add a shop (tenant) or a Naver category,
how to check the quality, and what is still open. The code: `translate.py` (the stage), `translation_dicts.py`
(dictionaries), `translation_rules.py` (unit templates), `review_clean.py` (reviews, in the transform),
`translate_keys.py` (the keys), `translate_eval.py` (the quality check), `prompts/` (system prompt and briefs). Its
place in the pipeline and the details of each part: "Translation" at the end of this doc and [TRANSFORM.md](TRANSFORM.md) "Transform".

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
| A title's length: the prompt asks for about 90 characters; over 100 the title goes back to the model with "too long" (it drops the least important facts from the end: materials, colours, the club list, "for beginners"), up to 2 times; a title that never gets under keeps its shortest answer that passed the other checks and does not hold the product (nor does a refusal, a cut answer or the provider going down in a round asked only to shorten); a title already in `translation/texts.jsonl` is not asked again (delete its row to translate it again), unless the product's brand changed since: a title row keeps the `brand_ko` it was asked with, and a title asked under another brand is asked again, its old English kept until the answer (2026-11-15: Generic, Edis, PRECISE stayed at the head of fixed titles; a hand correction row has no brand and is never asked again); the publication cuts to Google Merchant Center's 150 (`shopify_payload.fit_title`) | `translate.ASK_SHORTER`, `prompts/translate_fix.md` |
| Reviews as an American buyer would write them: the meaning and the strength kept, casual allowed, no machine phrasing; a sentence the cleaning cut on a joining word ends as a full sentence, a meaningless fragment is dropped | `prompts/translate_system.md` |
| Reviews kept with their score; their text loses the Korean purchase (seller, shipping, customs, won, packing, gifts) | `review_clean.py` |
| After translation, at publication: an English sentence about the price or value, or naming another platform or a buying agent, goes (the owner, 2026-11-09; complaints about the seller stay) | `review_clean.cut_english` |
| Bounded batches, a final check that every text came back, retries in the same conversation | `make_batches`, `_converse` |
| Few tokens: short ids, compact JSON, the category's terms in the cached system prompt, no thinking tokens | `request`, `system_prompt`, `ANTHROPIC_TRANSLATE_THINKING` |
| The job translates each product right after it is prepared | `job.py` (`translate_one`) |

## A new shop (tenant) or category

Nothing in the stage's code changes. Per case:

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

   The purchase topics (shipping, seller, price ...) are the same for every category.
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
files or the live dictionaries.

**Golf sets, 2026-11-08** (12 products, 260 texts): 25 flagged, then 17, then 10 (3.8%) after three rounds of
fixes:
- golf terms and model lines in the category brief;
- flex-letter runs split by a template;
- review fidelity rules (no "for the price", the subject kept, no upgrade of strength);
- title words that only some variants have, passed as context.

The 10 left were nuances in reviews (two broken in the source already), a brand spelling (since added) and one
label.

**Live checks the same day:**
- a rerun asks nothing;
- an interrupted run keeps every product it finished;
- every provider down leaves the products `pending`, and the next run translates them;
- a 24-value option takes two batches; a 1 700-character review is translated whole;
- a job of 3 new products went from the listing to translated and placed: about $0.01 and 5-9 s a product for
  translation, against 66-98 s of collection.

## Known limits

- **Reviews**:
  - A purchase remark in the middle of a Korean sentence that also names the product stays there: "제품구성이 좋고
    가격도 저렴해요". Cutting it would break the sentence. When it is about the price, the English sentence goes at
    publication (`cut_english`), the product words in it too.
  - A rare form the patterns do not know stays in the text, for example "여러가지로 친절하고 ... 처리해 주었으나". Add
    such forms to `review_clean.py` with a test when they show up.
- **Ambiguous Korean.** The model may give an opinion to the wrong person ("디자인도 맘에 듭니다" after "와이프 ...").
  The judge flags it; the prompt asks to keep the buyer as the subject.
- **Titles keep every code of the source**, so a model written twice stays ("BG-100L BG100L"). Titles translated
  before 2026-11-08 evening are the literal ones (in the texts store); they change only when translated again.
- **Category scope.** 50002788, 50002787 (junior clubs, 2026-11-11: its own brief; the sets' glued-flex rule, review
  aspects with a parent's words and glossary) and 50002670 (women's iron sets, 2026-11-14: its own brief; the sets'
  rule, aspects, product words and glossary) and 50002783 (wedge sets, 2026-11-15: its own brief, the sets' rule,
  aspects, product words and glossary) have a category brief, aspects and rules. Another category gets the
  base prompt and the general aspects until it has its own.

## Open (2026-11-08)

- **The OpenAI fallback** has never answered live: the account has no credits (429). Until it has, a down Anthropic
  leaves products `pending`.
- **The dictionaries** were backed up on 2026-11-08T14:06:19Z (372 entries; every backup file carries `backed_up`,
  and `translation_dicts.py status` prints the last one). A few model answers there are worth a second look, for
  example "9도 S4번유틸S ..." -> "9° S4 Hybrid ..." (a flex letter glued to the next club's number, with a space
  before it). New brands enter the brand dictionary without the owner's word.
- **Wrong entries deleted** (2026-11-11, the owner: "ошибочные удаляй"): all 1,676 entries were read by a model
  reviewer and each flag by three more; the 40 that at least two confirmed were deleted from both copies (기타 ->
  TaylorMade, 브리지스톤골프 -> Bridgestone Golf, Nikent for Nickent, flex letters glued to the next club ("S4
  Hybrid"), 백미포함 read as "with bag", an added "Driver", a dropped 여성, Glory for Gloire, ...). The next run
  asks the model for them again. The 23 published products that used them stay as they are in the store until
  they are published again; until a full `translate.py` run their record is `pending`.
- **Publication** (`publish.py`, 2026-11-08) reads `translation/translated.jsonl`; a text without English holds
  the product.

## Translation (`translate.py`)

Decisions, a new shop or category, the quality check (`translate_eval.py`), limits: [TRANSLATION.md](TRANSLATION.md).

The owner (2026-11-08): the prepared products' `texts` go to English through Claude Sonnet 5.5 (effort low, JSON
output) before placement and publication. Not translated: `description_ko` and the images' text (a later stage
writes the description from them; their `to_translate` flag is not this stage's).

```sh
.venv/bin/python scripts/translate.py fairwardgolf --offline   # no model: what the dictionaries and rules leave
.venv/bin/python scripts/translate.py fairwardgolf --limit 3   # the model for 3 products
.venv/bin/python scripts/translation_dicts.py status [--json]  # sync helper: dates, what the backup lacks, advice
.venv/bin/python scripts/translation_dicts.py backup           # by hand: live -> scripts/dictionaries/, then commit
```

Per text, the first that answers:

1. **The product's own store:** title, review, a placeholder option name (선택 / 옵션, named from its values), in
   `translation/texts.jsonl`.
2. **The dictionary of its kind:** brand, option name / value, spec and fact label / value, add-on group / name,
   text-field label / placeholder. One file per kind: the brand's for the whole shop, every other kind's per Naver
   category (`<category id>/<kind>.json`, 2026-11-11: a new category starts empty). The live copies in `scripts/output/dictionaries/` grow during
   runs and are out of git. Their backups in `scripts/dictionaries/` are in git and seed a missing live copy; they
   are updated by hand with `backup`, after `status`, since runs never commit; a backup stamps each file
   `backed_up`. The sync only adds: a run takes the entries only the backup has (pulled from git, seeded by hand),
   a backup writes the live entries over the backup's and keeps its others. A wrong entry is fixed in the live
   copy; deleting one for good means both copies. `status` shows when the live copies were last written and the
   last backup, the new and changed entries, the ones only in git, and the advice (`action` none / wait / backup /
   review in `--json`). A backup is due at 20 waiting entries, or 7 days after the last one with any waiting
   (`BACKUP_AT_CHANGES`, `BACKUP_AFTER_DAYS`); changed entries are read first, since the backup writes the live
   English over git's. When it is due, a `translate.py` run's report (not `--only`) and `job.py run` (done) /
   `job.py status` print one reminder line. The brand dictionary comes first: the
   model gets the shop's vendor spellings and reuses one for the same brand.
3. **The rules** (`translation_rules.py`):
   - 10.5도 -> 10.5°, 33인치 -> 33 in, 22호 -> Size 22, 3번 -> #3, 7개 -> 7 / 7 pcs, 12종 -> 12 pcs, 2026년형 -> 2026 model;
   - 노브랜드 alone becomes the tenant's name (`Store.publisher`), and inside a text it is removed;
   - a brand of 기타 ("other") alone becomes the tenant's name as well (2026-11-11);
   - a text with no Hangul left is done; the rest goes to the model already converted.
4. **The model:** one request per product, with the system prompt in `prompts/translate_system.md`. Each item is
   checked:
   - every id is returned once;
   - no Hangul is left;
   - the source's numbers and Latin codes are kept;
   - the text is within its length limit;
   - the option values stay distinct.

   What fails goes back in the same conversation (`prompts/translate_fix.md`), at most twice. What still fails
   leaves the product `untranslated`; what passed is kept.

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

**Checked 2026-11-08** on 12 varied trial products with a second model (Opus 5.5) as the judge: 25 of 260 texts
flagged, then 17, then 10 (3.8%) after three rounds of fixes.
- **The fixes:**
  - the golf terms and model lines in the category brief;
  - a glued spec run split after each flex letter (`CATEGORY_RULES`);
  - review fidelity in the system prompt: no "for the price", the subject kept, no upgrade of strength;
  - a title's words that only some variants have (the note `title_names_one_variant`) passed as context;
  - text addressed to a model cut from reviews.
- **Live checks also run:** rerun (0 calls), resume of an untranslated item, every provider down (`pending`, then
  resumed), a 24-value option and a 1 700-character review.
- **The report:** `translate_eval.py` writes `report.html` (see TRANSLATION.md).

**Tokens** (the owner, 2026-11-08: no overspend):
- **The request:**
  - compact JSON;
  - the batch's short ids (`1`, `2` ...) instead of the text ids, both ways;
  - the category's terms only in the system prompt, which is cached and read at a tenth of the input price;
  - the shop's vendor list only when a brand is asked.
- **No thinking:** `thinking: between_tools`, with effort low. On simple words it gave the same English at fewer
  output tokens and 20% less time. `ANTHROPIC_TRANSLATE_THINKING=adaptive` turns it back on.
- **Where the cost goes:** the output, that is the English itself.
- **Measured 2026-11-08** on 4 varied trial products (129 texts, empty dictionaries): 11 batches, 12 calls (one fix
  round), all translated, about $0.015 and 8 s a product, $0.0005 a text. With the dictionaries the shop's repeated
  texts cost nothing.

**The system prompt is assembled** (`system_prompt`):
- the translator's role and rules (`prompts/translate_system.md`);
- the shop's brief (`prompts/tenants/<shop>.md`: who sells to whom, spelling, tone);
- the category's brief (`prompts/categories/<Naver category id>.md`: what the products are, their terms, how buyers
  write about them).

**A new shop or category** (the whole checklist, every stage: [ONBOARDING.md](ONBOARDING.md)) needs a short brief file only here, no code. Write the file following the 50002788 one; the
category's review aspects go in `review_clean.ASPECTS` / `CONTEXT`. A missing brief is left out, and the base prompt
works alone, less precisely.

Out: `translation/translated.jsonl` (per product: status, English by text id, where each came from) and
`report.txt` (counts, tokens and cost, new dictionary entries).

The keys: `scripts/translate_keys.py install <file>` moves the operator's key file out of the repo, makes it 600,
and sets `TRANSLATE_KEY_FILE` in `.env` ([SETUP.md](../SETUP.md)). The models, their efforts and the chain's order
are `.env` settings, not code (`TRANSLATE_PROVIDERS`, `ANTHROPIC_TRANSLATE_MODEL` / `_EFFORT`,
`OPENAI_TRANSLATE_MODEL` / `_EFFORT`; `translate.settings()`). The server-side refusal fallback is sent only to the
Claude models that take it.

On the 143 trial sets (2026-11-08):
- without the model, the dictionaries and rules gave 3 606 of 4 877 texts;
- the model is left 1 271: titles 143, reviews 442, option values 292, spec values 505 (with repeats across
  products, each asked once per product);
- the reviews are sanitized but all kept, so 411 review texts are left (the cut text is gone from them).

A job made since 2026-11-08 runs this stage per product, right after prepare (`job.py`, translated; `new --no-translate`
leaves it out). See [JOB_AGENT.md](JOB_AGENT.md).

