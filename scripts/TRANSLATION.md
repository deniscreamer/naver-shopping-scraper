# Translation: Korean product texts to English

How the translation stage works, the owner's decisions behind it, how to add a shop (tenant) or a Naver category,
how to check the quality, and what is still open. The code: `translate.py` (the stage), `translation_dicts.py`
(dictionaries), `translation_rules.py` (unit templates), `review_clean.py` (reviews, in the transform),
`translate_keys.py` (the keys), `translate_eval.py` (the quality check), `prompts/` (system prompt and briefs). Its
place in the pipeline and the details of each part: [README.md](README.md) "Translation" and "Transform".

## Decisions (the owner, 2026-11-08)

| Decision | Where it lives |
|---|---|
| A model API translates. Not the session's agent. | `translate.py` |
| Claude Sonnet 5.5 at effort low; OpenAI as the fallback; models changed in `.env`, not in code | `settings()`, `.env.example` |
| The description and the images' text are not translated: `describe.py` reads them in Korean and writes the English description (the owner, 2026-11-10; README "The product's description") | `transform._texts` (not in `texts`), `describe.packet` |
| One dictionary per kind of text, in JSON, growing during runs out of git; backups in git, updated by hand; `status` says when a backup is due | `translation_dicts.py`, `scripts/dictionaries/` |
| Brands are the shop's (`dictionaries/brand.json`); every other kind is a Naver category's own (`dictionaries/<category id>/<kind>.json`): a new category starts empty and its entries never reach another (2026-11-11: 50002787's entries had changed four products of 50002788) | `translation_dicts.SHARED`, `Dictionaries.scope` |
| The brand is looked up first; one spelling per brand in the whole shop | brand dictionary, `vendors` in the request |
| No brand (노브랜드): the tenant's name; inside a text the word is removed. A brand of 기타 ("other", the owner 2026-11-11): the tenant's name too (transform already leaves it out: the fallback decides) | `translation_rules.sanitize`, `transform.NOT_A_BRAND` |
| Units and sizes by templates (10.5도, 33인치, 22호, 3번, 7개, 2026년형); the model only for the rest | `translation_rules.py` |
| Titles are the store's names (the owner, 2026-11-08, as the harvester's): brand first, then model, year, who it is for, the kind of set, pieces, what is included; no shop, dispatch, distributor or after-sales ("AS가능") words, no loft / flex / shaft codes or club list, no usage or gift words (the 100-product pilot, 2026-11-09). The model, not templates: nobody can foresee every title | `prompts/translate_system.md` |
| A title's length: the prompt asks for about 90 characters; over 100 the title goes back to the model with "too long" (it drops the least important facts from the end: materials, colours, the club list, "for beginners"), up to 2 times; a title that never gets under keeps its shortest answer that passed the other checks and does not hold the product (nor does a refusal, a cut answer or the provider going down in a round asked only to shorten); a title already in `translation/texts.jsonl` is not asked again (delete its row to translate it again); the publication cuts to Google Merchant Center's 150 (`shopify_payload.fit_title`) | `translate.ASK_SHORTER`, `prompts/translate_fix.md` |
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
- **Category scope.** 50002788 and 50002787 (junior clubs, 2026-11-11: its own brief; the sets' glued-flex rule, review
  aspects with a parent's words and glossary) have a category brief, aspects and rules. Another category gets the
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
