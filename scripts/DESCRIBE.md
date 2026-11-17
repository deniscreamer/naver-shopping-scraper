# The product's description

How `describe.py` writes the English product description and which model writes it; split from scripts/README.md on 2026-11-16 (history: `git log --follow scripts/README.md`).

## How to use

| Task | Run | Then |
|---|---|---|
| What the model is given for one product | `.venv/bin/python scripts/describe.py <shop> --only <key> --packet` | compare with the rules below ("Before") |
| Describe new products (paid calls) | `describe.py <shop> [--limit N]`, or a job with `--publish --describe` | the summary line `N described: {ok, trimmed, fallback}`; each non-`ok` row names what was cut and why |
| One description reads wrong | read its row in `shops/<shop>/translation/descriptions.jsonl` (`dropped`, `conflicts`, origin) | a rule or prompt: skill `prompt-change`; one product: skill `fix-a-product` |
| A product already in the store | `--published` or `--only`: the next `publish.py` sends it | the owner's go-ahead first ([OWNER_RULES.md](OWNER_RULES.md) section 1) |
| A prompt or model change: measure it | a few products not in the store, `--only <key> --force`; read the sample | a dated line under "Which model writes the descriptions" (a model) or in the profile's paragraph (a prompt) |

`ok`: as answered; `trimmed`: something cut by the checks; `fallback`: no intro left, the title as one sentence.

## The product's description (`describe.py`, the owner 2026-11-10)

```sh
.venv/bin/python scripts/describe.py fairwardgolf [--only <key>] [--limit N] [--offline] [--packet]
.venv/bin/python scripts/job.py new ... --publish --describe      # each product described right before it is sent
```

A minimalist English description in HTML for Shopify's own body (`descriptionHtml`; no metafield, no SEO
description). One model request and one answer per product, through translate.py's client (the same key, models
and fallback order) at this stage's own effort: `high` with thinking on (`DESCRIBE_EFFORT` in .env changes it);
no fix rounds. Why not the translation's `low` without thinking: checked 2026-11-10 on 35 descriptions against
their sources, 15 had a wrong club list or count, a fact of one choice told of all, or a lost "no bag" sentence;
the answer needs the sources compared and the clubs added up ("Which model" below). The script works before and after the request:

- **Before** (`packet`): what is sold goes first (the facts and the options of the variants we publish, the free
  required choices), then the English the shop already shows (title, brand, spec rows, option values: the
  description names the product as its title does), then the seller's typed text and the OCR blocks of the
  description images in Korean, and, in a section of their own, the tables read from those images (digits are
  lost in them, so a figure only a table gives is not stated; but the seller lists the set's clubs there, and the
  Naver spec rows are often wrong about them; one or two rows of mostly Korean words are text in columns, e.g.
  "여성 | 카본10pcs | 클럽만"). Left out:, a block headed by an offer of a paid extra or a gift (a line naming an extra
  inside another block stays with its label: the label is what tells the model to leave the item out), an image of
  buyers' reviews (masked ids), every line on the country of manufacture. A gift among the facts or the free
  choices is listed under "Gifts of the seller: never mention", not as what is sold. Notes the transform already made about the listing (other
  configurations sold, paid extras, gifts, several products in one description) are passed as one line each.
- **Origin** (the owner: keep the country): decided by the script, not the model. The 원산지 row and every
  "제조국 / made in" line of the texts name one country: `Origin: made in <country>`. They disagree or hedge
  ("may differ", "not Japan", "and others"), or the row names a country the table does not know: `Origin: do not
  state`, the reason in the report. Of the first 105: stated for 66, silent for 28, no source for 11. After the
  answer any other country in the text, in any wording ("Japanese-made", "a product of China"), cuts that
  sentence; "Japan-market model" is not an origin.
- **The answer**: JSON fields, not HTML: `conflicts` (points the sources disagree on: asked first, kept out of the
  text, shown in the report), `intro`, and the lists of the product's profile.
- **After** (`settle`): each intro sentence and each list item is checked alone (a sentence does not end after
  "Co." / "Inc." / "Ltd." / "Jr." nor between "No." and its number: "Detroit Golf Co. Premium …", 2026-11-17 C65): English only, no link, phone,
  price or markup, no shop talk (warranty, shipping, gifts, reviews, authenticity, parallel import), no talk about
  the listing ("per the specifications", "depending on the option", a seller's disclaimer "specs may differ"), every number is one the model was given or a club inside
  a range it was given (a tripwire, not a proof: a wrong number that stands elsewhere in the packet passes); in
  `wedge_set` (2026-11-17, C65) also the set's count, but only inside a count phrase ("set of 3", "3-piece",
  "3 wedges"): "a set of 3 wedges" was cut on about 25 wedge sets; a count added to the given numbers let a made-up
  "steps of 2 to 3 cm" through (11228451487). The count (`set_counts`, 2 to 6, never the buyer's picks): the
  distinct lofts (44-64) of the fixed facts when two or more ("Fixed: Size: 50 54 58 Degree Set" is 3); else none
  when a title offers a set or a single club ("Set or Single", 세트 또는 개별 / 개인, 싱글 또는), a loft range
  ("50-70도", not the list "52-56-60도") or names 5 lofts or more: that is the picker's menu, not the set (it let
  "a set of 6 wedges" through on 13488668518 and 13016433540; a wrong count of 4 to 6 on 29 of the shop's 906
  wedge-set packets), or a title names a loft above 64 ("69°", "72도": not counted, so the count came out low on 15
  packets, "set of 2" for 69 Golf 54°/60°/69°); else the distinct lofts of the title and the fixed facts when two or more ("52°/56°/60° GW SW"
  is 3, 13312222110), else the wedge names (PW AW GW SW LW UW). No country but the decided
  one. A failing highlight or intro sentence is dropped; a failing item of another list drops that list (half a
  list of the box's contents misleads; so does a clean list over its cap of 12). No intro left: the title as one
  sentence (`fallback`). Caps: intro 400 characters, an item 220, the whole text 1 500. The HTML is built by the script (`p`, `h3`, `ul`, `li`, text
  escaped, a line break between blocks).
- **What nothing checks**: a claim without a number that the seller did not make (the model explaining a term).
  The prompt forbids it; read a sample of `translation/descriptions.jsonl` when a category or the prompt changes.

A kind of product has a profile (`describe.PROFILES`: its Naver leaf categories, its lists with headings and
caps) and a brief (`prompts/describe/<profile>.md`: what each list holds, what a buyer of this kind of product
must be told). `golf_set` (50002788): "What's included" and "Highlights"; no bag or no putter is said plainly; a
non-conforming driver gets one fixed sentence; a version for the Asian or Japanese market is one highlight, joined
with the origin. `junior_clubs` (50002787, 2026-11-11): the same two lists, a single club or a set said in the
intro with the age or height range the seller gives. `iron_set` (50002670, 2026-11-14): the set's irons in one
item, the choice of iron count, shaft or flex in a highlight, 정품 / 병행 one highlight. `wedge_set` (50002783,
2026-11-15): the wedges by loft in one item, the choice of lofts, grind or shaft in a highlight, non-conforming
grooves (비공인) said as a limitation. A category without a profile gets `default`: the intro and highlights only. The common prompt
(`prompts/describe_system.md`) holds no golf rule or term (one quoted example of filler aside).

The answers are kept in `shops/<shop>/translation/descriptions.jsonl` (append-only; fields, HTML, what was cut
and why, conflicts, the origin decision, the model, the time; `generated: model` for a later Merchant feed, where
Google asks for AI-written text to be declared). A product with a row is not asked again; a row whose source
changed is reported `stale` and kept (`--force` asks again). `publish.py` puts the row's HTML into the payload and
into the publish digest only when the product has a row, so a product without one keeps its digest. Products
already in the shop are skipped unless `--published` or `--only` names them: a new description changes the digest,
and the next `publish.py` run sends the product (the owner's go-ahead first, JOB_AGENT.md).

### Which model writes the descriptions (compared 2026-11-10)

The default is **claude-sonnet-5-5 at effort `high`** (the owner, 2026-11-10: fewer errors; `medium` was the
default for a day, see the note after test 2). Two tests stand behind the choice of the model; repeat them when a
new model comes out, and add its row here.

**Test 1, breadth: one product, every model.** The same packet (Bridgestone BG-100, 8958060680: a clean listing
with two traps, a spec row that drops the #6 iron and a driver loft tied to the shaft set; 2 requests a setting)
and a stress packet (Mutsumi Honma + TaylorMade mixed set, 6707956586: the sources disagree on the loft, the
irons and the shaft material; 1 request). Three blind judges a product scored each answer against a fact list,
0-10. Accuracy and coverage are "clean packet / stress packet"; the price is the list price of the tokens used
(input + output, thinking included), no cache discount.

| Model | Effort | Accuracy | Coverage | Errors that block publishing | $ per 1 000 products | Time |
|---|---|---|---|---|---|---|
| claude-haiku-5-5 | medium | 9.8 / 5.5 | 7.4 / 5.7 | yes (stress) | 1.5 | 10 s |
| claude-haiku-5-5 | high | 10 / 10 | 5.0 / 6.0 | no | 3 | 21 s |
| claude-sonnet-5-5 | low, thinking off | 8.4 / 6.5 | 6.0 / 6.7 | yes (both) | 16 | 4 s |
| claude-sonnet-5-5 | medium | 10 / 9.7 | 8.9 / 9.0 | no | 24 | 11 s |
| claude-sonnet-5-5 | high | 10 / 10 | 7.7 / 9.0 | no | 29 | 13 s |
| claude-opus-5-5 | low | 10 / 10 | 6.8 / 9.7 | no | 36 | 8 s |
| claude-opus-5-5 | medium | 9.6 / 10 | 5.3 / 7.7 | no | 49 | 14 s |
| claude-opus-5-5 | high | 10 / 10 | 8.5 / 8.5 | no | 62 | 19 s |
| claude-fable-5-2 | low | 10 / 10 | 8.5 / 10 | no | 67 | 9 s |
| claude-fable-5-2 | medium | 9.2 / 10 | 8.2 / 9.2 | no | 109 | 23 s |
| claude-fable-5-2 | high | 9.0 / 10 | 8.3 / 7.7 | no | 208 | 56 s |
| claude-fable-5-1 (legacy) | medium | 8.5 / 10 | 4.3 / 10 | no | 146 | 23 s |

Prices per million tokens then (input / output): Haiku 5.5 $0.10 / $0.50, Sonnet 5.5 $2 / $10, Opus 5.5 $4 / $20,
Fable 5.2 $8 / $40. The answer itself is about 400 tokens; the rest of the output is thinking, which is what a
higher effort or a bigger model costs. From Sonnet `medium` up every setting was accurate; the dearer ones bought
nothing on this task.

**Test 2, depth: 35 products, the three candidates.** The 35 products first described (golf sets, 50002788), each
written by the three settings from the same prompt; one blind checker a product compared the three descriptions
(letters shuffled per product) with the packet: `good` (every claim supported), `minor` (slips of wording),
`wrong` (a false, unsupported or missing fact that misleads), and a usefulness mark 0-10.

| | claude-haiku-5-5 high | claude-sonnet-5-5 medium | claude-sonnet-5-5 high |
|---|---|---|---|
| good / minor / wrong | 11 / 22 / 2 | 18 / 17 / 0 | 20 / 13 / 2 |
| Usefulness, 0-10 | 6.7 | 7.3 | 7.6 |
| Picked as the best of the three | 9 | 14 | 12 |
| Empty "What's included" | 12 | 10 | 7 |
| $ per 1 000 products | 3.6 | 18 | 27 |
| Time a product (mean) | 27 s | 5 s | 12 s |

Sonnet `medium` and `high` cannot be told apart at this size (0 against 2 wrong of 35 is noise); `medium` costs a
third less and answers twice as fast. Haiku `high` is five times cheaper and makes no gross error, but writes
poorer descriptions (more slips, more empty lists, one description that fell back to the title) and is the
slowest, because it thinks the longest: the candidate for very large volumes, after the prompt is tuned for it.

**In use, the other 75 products of the store (harder listings: several configurations in one listing, sets
mixed from several makers).** Written at `medium` and checked the same way: 23 good, 36 minor, 16 wrong (a choice
described where one fixed combination is sold, another edition's features, a wrong count). The 16 asked again at
`high`, with one prompt line added: 14 passed, the other 2 had one highlight cut by hand. `medium` saves about $9
per 1 000 products against `high`; on hard listings that is not worth the errors, hence the default.

How the tests were run (scratch scripts, not in the repo): the packet, `describe.ask` and `describe.settle` called
directly for each model (`translate.AnthropicModel(key, model, effort, thinking="adaptive")`), nothing stored in
the shop and nothing published; the judging by agents that see the answers under neutral labels with the packet.
Limits: one or two requests a setting in test 1, one checker a product in test 2; only large differences are
reliable.

