# Sweep: what an improvement changes for products already in the store

`sweep.py` answers, for the products already in the store, two questions in one run (2026-11-19):
- **old answers** (stage 1, `--answers` alone): whose cached model answers (the English title, option names, the
  description) a rule, dictionary or prompt improvement would now judge wrong. Re-preparing never reaches them:
  `translation/texts.jsonl` keeps a title until `translate.plan` asks it again, and `describe.py` keeps a description.
- **the store lagging** (stage 3, `--store` alone): what a resend would change, today's offline build
  (`publish.build`) against what the store last got (`publish/sent/<id>.json`, `publish.load_sent`), field by field;
  a verdict per changed product (worse, improvement, eyeball) and groups for the owner's decision.

Read only: local files, no network, no credentials, no model; it writes only `shops/<shop>/sweep/` (`latest/`, `prev/` the run
before, `selection/` a run narrowed by a selection), or with `--seed-sent` only `publish/sent/<id>.json` (and no report),
with `--decline` only `sweep/decisions.jsonl`, with `--confirm` only the group's `.confirmed.keys` and `.plan.tsv`.

## How to use

```sh
.venv/bin/python scripts/sweep.py <shop>                         # every published product: both parts, a table
.venv/bin/python scripts/sweep.py <shop> --answers | --store     # one part alone (its files only)
.venv/bin/python scripts/sweep.py <shop> --json                  # {"answers": ..., "store": ...}; one part: its file's shape
.venv/bin/python scripts/sweep.py <shop> --only <ref> [--only <ref>] [--keys-file F] [--job ID [--event E]]
.venv/bin/python scripts/sweep.py <shop> --seed-sent [--json] [a selection]   # the store's "before" (stage 2)
.venv/bin/python scripts/sweep.py <shop> --decline --keys-file F [--check <code>] --reason "<why> (owner <date>)"
.venv/bin/python scripts/sweep.py <shop> --confirm <group id> [--json]      # before a group's resend (stage 4)
```

The owner decides each group (and each paid re-ask) as the report shows it; his yes or no and the resend are
"The owner's decisions" below (skill `sweep`).

When: after a commit that changes what products are built from (a rule, a dictionary entry, a prompt), between jobs,
after `run_transform.py <shop> --diff`, `translate.py <shop> --offline` and `placement.py <shop>`; after a scroll or
job (it adds brands and terms); before a release. It takes about 17 seconds for the whole shop (2,265 published:
the checks about 2 s, the store part about 14 s, nearly all of it `publish.build`).

The first line is the scope: live (ACTIVE, or an old ledger row with no `store_status`) and drafts (`DRAFT`) are
counted apart; withdrawn products (holds among them) are left out; ready products never published are counted, not
checked. Then the input files' times, then a row a check (live, draft) with up to 3 examples (key, handle, the
offending text), and one line: the description images' OCR sidecars that carry an error (the whole shop's, whatever
the selection). Then the store part: one line of counts (with a baseline: same, changed by verdict, worse; no
baseline by reason), a row a group with up to 3 examples, then per part what is new and gone since the run before.
Worse products, when there are any, are printed first of all.

| Result | What it means | What to do |
|---|---|---|
| a check's count is 0 | nothing an improvement now judges wrong | nothing |
| `title.pending_reask` | `translate.plan` already wants these titles again (another brand than when it was asked) | paid: ask the owner ("ask again N titles, about $0.01-0.02 each?"), then `translate.py <shop> --keys-file shops/<shop>/sweep/latest/title.pending_reask.live.keys`; a republish is a second question (OWNER_RULES.md, rule 1); a Korean title that names both brands (a maker and its line, a mixed set) only gets them reordered (2026-11-19: 4 live titles, PRGR / Yonex, Koara / Mazel, ONOFF / Daiwa, Stardom / Katana): on the owner's word keep the old English as a hand row (`by: review-...`), never asked again |
| `title.other_brand` | the English title names another dictionary brand than the vendor, the Korean does not | read the examples (known false positives below); a real error: the owner decides `translate.py --reask` on the keys file, or a hand row (`by: review-...`) per product (skill `fix-a-product`) |
| `title.set_single` | the English title promises a set while one club or item is sold: describe.py's model said so in the description row's `conflicts` (2026-11-19: 92 live by a loose scan; the check: 26 live, 16 junior 50002787, 10 full sets 50002788); the extra lines: `by category` (the keys per store and Naver category in `title.set_single/<live\|draft>.<category>.keys`) and `hand titles that also match` (a hand title row, `by: review-...`, still promising a set: never a finding, no `--reask` reaches it; 27 live, most from the 2026-11-19 brand fixes; `title.set_single/hand.<store>.keys`) | read the examples, one category at a time, never the whole `title.set_single.live.keys` with one context. A product of another category (a single driving iron, chipper, putter or 7 iron among full sets 50002788, a single wedge in wedge sets) goes to the owner as a hold question (skill `store-actions`), not a re-ask: take its key out of the category's file. The rest: paid, ask the owner ("ask again N titles, about $0.01-0.02 each?"), then per category its own context, e.g. junior: `translate.py <shop> --reask --keys-file shops/<shop>/sweep/latest/title.set_single/live.50002787.keys --context "only one club is sold, the buyer picks its type: do not call it a set; name it as a single junior golf club"` (a wedge set's own wording, or none); read old -> new, sweep again; then the resend question per group (OWNER_RULES.md, rule 1). The hand titles: tell the owner, a new hand row each (skill `fix-a-product`). His no: `--decline --check title.set_single` |
| `text.hangul` | Korean left in an English text the store shows | fix at the source (a dictionary entry: skill `dictionaries`; a description: `describe.py --force --keys-file F` on the owner's word) |
| `description.old_brand` | the description names the product under another brand (an old vendor, a seller's shop) | the owner's word, then `describe.py <shop> --force --keys-file .../description.old_brand.live.keys`; then the republish question |
| `description.patterns` | a stored description trips a check `describe.py` has now (shop talk, talk about the listing, a link) | as `description.old_brand` |
| `description.stale` | the description was written from another packet than today's | nothing by default: one number, a keys file; the owner, 2026-11-19: only descriptions with an explicit error get rewritten |
| `OCR sidecars with an error (whole shop)` | `description_images.py` failed on these products | by hand only: `.venv/bin/python scripts/description_images.py <shop> --products <product id> --force` (the Naver product id, the key's last part; ~20 s a product, under the lock) |
| `seed-sent <shop>: N published (withdrawn left out): A written, B already there, C no_baseline` (`--seed-sent`) | `publish/sent/<id>.json` written for each published product whose offline build gives the ledger's `output` (B: the file holds it already, not rewritten); the C others have no baseline, a line a reason with up to 3 keys: `today's build differs from the ledger` (the store has something today's files no longer build: a vendor the store spells otherwise, a rule changed since), `the ledger row has no output` (a failed photo, a row from before `output` existed), `not buildable: <error>` (a missing file or record) | nothing: their "before" comes with their next real send (`publish.py` writes it); stage 3 shows them as no baseline |
| `store lagging <shop>: L live, D drafts; B with a baseline: S same, C changed (improvement I, eyeball E; needing --force F), W worse; no baseline N (...)` | the store part's counts: B products have a trusted "before" (`load_sent`); S of them build today exactly to what the store has (a resend would be skipped); the C others would change, F of them only with `--force` (`.force` groups, below); no baseline N, by reason (`no publish/sent file`: published before stage 2 and not seeded, or a failed photo; `the ledger row has no output`; `the publish/sent file is not the ledger's output`: a send cut off, a hand edit) | nothing for S; the groups for C; the no-baseline keys get their "before" with their next real send (or `--seed-sent`) |
| a group row: `<live\|draft>.<category>.<verdict>[.force].<fields>  N  <verdict>  [fields]  free: a resend only ...`, 3 examples `key handle old -> new` | N products of one Naver category, live or drafts, whose resend changes exactly these fields; one product is in exactly one group (the whole payload is sent, so a yes covers everything shown); `groups/<group id>.keys` holds its keys. `.force`: today's output differs but the inputs digest is the ledger's (a vendor the store spells otherwise, a `shopify_payload` change made without `sp.VERSION`, a review file's new URL), so `publish.py` skips these keys unforced: the cost line says `publish.py --keys-file F --force`, and a whole shop of them after a code change means `sp.VERSION` was forgotten (bump it, sweep again). Verdict `improvement`: a check (`title.other_brand`, `text.hangul`, `description.old_brand`, `description.patterns`) fires on the store's text and not on today's; `eyeball`: anything else (a weight, a section's tags, a price, a vendor). Flags after the changes, not verdicts: `price $a-b -> $c-d` (each SKU's `weight S: a -> b g` is a change line), `now trips <check>` (an eyeball group: today's text trips a check the store's does not), `review files not uploaded yet: N` | the owner decides each group as shown (live and drafts apart); his yes or no and the resend: "The owner's decisions" below |
| `WORSE N (a guard tripped: ...)` first, then `key  live\|draft  handle  <guard>: <why>` (exit 1) | today's build would send something worse than the store has (Guards below); these products are in no group | read each: a product no longer ready or buildable is left as the store has it by `publish.py` too; another guard is a regression of the rule just changed (fix it, sweep again) or a seller's change (skill `product-trace`); never resend one unasked |
| `since prev (checks\|groups): name: N now, A new, G gone` (`nothing new, nothing gone`, `no previous run`) | per check and per group (and `worse`), against the run before (`sweep/prev/`): a part run alone compares with that part's last run; a run with a selection prints `a selection, not compared` and writes `sweep/selection/` (latest/ and prev/ stay the whole shop's) | after a rule change, "new" should be exactly what the change meant to do; anything else new is a regression to read before telling the owner |
| `declined by the owner, hidden: N (...)` (the store part: `...; a later send of them carries the declined change anyway ...: <keys> (declined.keys)`; the checks: `(<check> n, ...)`) | N keys the owner said no to (`--decline`) still build to exactly what he declined: left out of every group (or that check's findings and keys file); one comes back by itself when its build moves | nothing; never resend them unasked. A later send of such a key (`publish.py` on it, `--force` for a `.force` one, `reprice.py --apply`) still carries the declined change: his no is not a block, say so when that send is asked for |
| `declined N (<group or check>) -> .../sweep/decisions.jsonl` (`--decline`) | one line a key appended: `{key, group, output, reason, at}` | the report's next run shows them hidden |
| exit 2, `sweep: nothing declined: <key>: in no group of the last whole run ...` / `its build moved since the run ...` / `not a <check> finding ...` / `does not build today` / `no sweep/latest/...: run ... first` / `the last run kept no outputs (before stage 4)` (`--decline`, `--confirm`) | the key (or group) is not what the last whole run showed; nothing written | run `sweep.py <shop>` (whole), read it, decline what it shows; a check's finding: `--check <code>` |
| `confirm <group id>: K of N kept; <why> n: <keys>` then the publish command (`--confirm`) | the group's keys re-built: dropped those `its build moved since the run`, `sent since the run`, `withdrawn since the run`, `declined`, `does not build today`; `groups/<id>.confirmed.keys` and `<id>.plan.tsv` written | send exactly the printed command on the owner's yes (the dropped keys were not what he saw: a new sweep shows them); `nothing left to send`: tell him |
| exit 1, `sweep: <path>:<n>: not a JSON line ...` | a shop file has a broken line (`sweep/decisions.jsonl` too: a cut-off last line is ignored with a warning, and `--decline` cuts it off before
appending) | skill `recover-state` |
| `sweep: stop: <shop> is busy: ...` (exit 2) | a job or a command holds the shop's lock and rewrites the files read here | wait for it (`job.py status`), run again |
| exit 2, `no product selected` / `none of the N named products is published here` / `unknown shop` | a selection that names no published product, or a shop `shop_stores.py` does not have | name published products (it never widens to every product), or a known shop |

Live and drafts are listed apart in every count and keys file (`<check>.live.keys`, `<check>.draft.keys`, the
groups' first word): the owner decides them apart (2026-11-19). Exit codes: 0 done; 1 a worse product (the store
part), or a shop file with a broken line; 2 usage or busy. A keys file feeds any command's `--keys-file`. Nothing is sent: what reaches
the store is a later, separate step on the owner's word.

Known false positives (read before asking the owner about a finding):
- 9647083907 (`title.other_brand` and `description.old_brand`): "Majesty Maruman Verity VGR ..." under Majesty; its
  Korean title spells the maker 마루만, the brand dictionary has only 마루망. The fix is a dictionary entry
  마루만 -> Maruman on the owner's word (skill `dictionaries`), not a reask.
- `description.old_brand`, what a set holds named in the lead: 9591107809 ("... mixing TaylorMade and Callaway",
  its Korean "캘러웨이/ 테일러메이드/ 풀세트" under the vendor Callaway TaylorMade: Cleveland in the lead),
  13364274307 ("... irons and an Odyssey putter", its Korean title cut at 오디). About 3 of the 104.

## Checks

Each a pure function over local files (sweep.py `CHECKS`; test_sweep.py compares this table with the code). A text
whose last row a review wrote is never flagged, only what the model or a rule wrote: a title or option text whose last
`texts.jsonl` row is `by: review-...` (translate's own `_load_fixed`); a description whose last `descriptions.jsonl`
row is `by: review-<date>-<why>` (DESCRIBE.md, "Hand rows"; none exists yet, 2026-11-19, so the description checks
have no exemption in practice).

| Code | What it catches | How |
|---|---|---|
| `title.pending_reask` | a title `translate.plan` already has among its pending items | `translate.plan` offline with the store, the brands asked with and the hand rows, as `translate.run` loads them |
| `title.other_brand` | a dictionary brand in the English title that is not the vendor | whole words, 3 letters or more, the shop's spellings (`vendor_name`); not the vendor (`translate._brand_en`) nor a line of it or it of the vendor; quiet when the Korean title or a spec value (not the 브랜드 / 제조사 / 원산지 / 수입원 rows) names it (a Korean key where a word starts, `brand_fallback.in_title`, or the Latin spelling), or the Korean title or a spec value says 조합 (a mixed set: "조합풀세트" in the 종류 row); not judged when the vendor is unknown |
| `title.set_single` | a conflict on the description row says the title promises a set while one club or item is sold | `set_single`: one of the row's `conflicts` (describe.py's model) whose clause before "but" / "while" / "whereas" names the title and a set, no single item ("set or a single wedge" is the title offering both) and no unclear count ("not clear", "not stated", "not given"); and whose clause after it names one club or item (single / one / only one + a club noun, a few words between: "a single RED LINE driving iron", "only one M5 Silver Chipper"; or a pick of one: picks / chooses / sells one loft, size, style, type) and no sets, pairs or N-piece / N-wedge choices ("single wedges, pairs and three-wedge sets"); never a lone "single" or "one of" ("single-length shafts", "only one loft is given", "one of the irons"); quiet the other way round (a spec row single, the title's set: the set may be what is sold) and with no title named; only while the English title still says set (a title asked again since is no finding); a hand title row never (counted apart) |
| `text.hangul` | Hangul in the English title, an option name or value, or the description | `translation_rules.HANGUL_RE` |
| `description.old_brand` | the description's first sentence names a brand that is not the vendor | the test of `title.other_brand` on the first sentence (where the description names the product) |
| `description.patterns` | a stored description `describe.py` would cut today | `describe.packet_free_problems` (the part of `problems()` that needs no packet: shop talk, the listing, kana / han, link, phone, price, markup) on each paragraph, heading and item; Hangul alone is `text.hangul`'s |
| `description.stale` | the packet changed since the description was written | `describe.source_sha256` against the row's `source_sha256`, as `describe.py --offline --published` counts stale (ready and translated products) |

The owner's declines of a check's finding (`--decline --check`) hide it from that check: "The owner's decisions"
below. The dictionaries are read as translate.py reads them, without their sync
writes (`Dictionaries(write=False)`; test_sweep.py compares the two).

## The store lagging (stage 3, 2026-11-19)

For each published, not withdrawn product (or a selection) with a baseline (`publish.load_sent`: the file's sha256
is the ledger's `output`), `publish.build` offline gives today's normalized `product_input`; equal to the ledger's
`output` it is `same` (`publish_one` would skip it), otherwise `changed`. A changed product whose inputs digest is
still the ledger's `digest` is `.force`: `publish_one` skips a key by its digest before it builds, so only
`publish.py --force` sends it (the review of stage 3, 2026-11-19); the others `publish_one` sends unforced.
test_sweep.py proves all three on a fake Admin with a real send's vendor spellings. The fields: `store_diff.compare` over the baseline in the store's read shape
(`as_live`: title, vendor, type, tags, body, SEO title, options, variants by SKU: price, option values, metafields;
the product's metafields, the reviews feed, the photos by hash), then what store_diff does not read (a variant's
`weight` and `cost`, other variant fields, `seo.description`, `photo alt` when the title did not change, any other
key); `other` when none of these names a difference the output hashes.

Vendor spellings as a real send has them (`send_ids`): the store's first, read from the baselines' vendors in the
ledger's order, then the brand dictionary's (read only). A brand the dictionary spells otherwise than the store
(10476142508 LAROUGE, stage 0) is no change. The store may hold spellings only withdrawn products carry, or
products with no baseline (10476142508 LAROUGE itself): those are not read, so a later product of such a brand alone
would show a vendor change a real send would not make (a known gap; it shows as an eyeball `vendor` group, read it
against `shopify_catalog.py vendors`).

## Guards

A changed product that trips one is worse: left out of every group, printed first, exit 1 (sweep.py `GUARDS`;
test_sweep.py compares this table with the code and trips each on a real fixture pair).

| Code | What it catches | How |
|---|---|---|
| `not_buildable` | today the product is not ready (prepared, translated, placed) or does not build | `Shop.ready()` / `not_ready()`, then `publish.build` raising (a missing file, Untranslated, PayloadError); `publish.py` leaves such a product as the store has it |
| `vendor_lost` | the vendor became empty or the shop's own name where the store has a brand | `brand_key` of the vendor against the tenant's |
| `fewer_variants` | fewer variants than the store has | the counts |
| `fewer_photos` | fewer photos than the store has | the counts of `files` |
| `description_lost` | a description the store has is gone, or today's is a fallback | the body empty now; or changed and today's `descriptions.jsonl` row is `status: fallback` (its intro only the title), unless the store's was a fallback too (`was_fallback`: its first text the store's title or today's fallback intro; a heuristic, nothing records the store's description status) |

A falling confidence and a price move are flags, not guards: a weight fixed moves a price lawfully.

## The store's "before" (`--seed-sent`, stage 2, 2026-11-19)

`publish.py` keeps, for each real send, the dict its `output` hashes in `publish/sent/<Naver product id>.json`
([PUBLISH.md](PUBLISH.md), "The store's before"), so a later stage diffs it against today's build field by field
without reading Shopify. `--seed-sent` gives the products published before that their file: for every published,
not withdrawn product (or a selection), `publish.build` offline (the brand dictionary's vendor spellings, read only,
as the dry run; no Shopify, no model) and, when its `output` equals the ledger's, today's build is what the store has
and is written (`write_atomic`; a file already holding it is left alone, so a second run writes nothing). The others
are counted `no_baseline` by reason and get no file. It runs no check and writes nothing but `publish/sent/` files (and the lock's holder line, `shops/.<shop>.lock`);
refused while the shop is busy, and unlike the checks it holds the shop's lock while it runs (about 14 s; a job or
`publish.py` started meanwhile is refused as busy): the ledger it read at the start stays the ledger it compares
with, so it never overwrites a newer send's file with an older build. A reader trusts only
`publish.load_sent` (the file's sha256 against the ledger's `output`).

The seed takes vendor spellings from the brand dictionary (as the dry run), so a product the store spells otherwise
gets no baseline (10476142508 LAROUGE); the store part builds with the store's spellings (`send_ids`, above).

## The owner's decisions (stage 4, 2026-11-19)

The owner decides per group (live and drafts apart), as the whole run showed it: a yes covers that group's keys and
everything shown for them, nothing else ([OWNER_RULES.md](OWNER_RULES.md), rule 1). Running sweep, `--decline` and
`--confirm` costs nothing and sends nothing; `--confirm` is a step of a resend he already approved (no question of
its own), `--decline` is run only on his no.

**His no** (`--decline`): `sweep.py <shop> --decline --keys-file shops/<shop>/sweep/latest/groups/<id>.keys --reason
"<his why> (owner <date>)"` appends one line a key to `shops/<shop>/sweep/decisions.jsonl`: `{key, group (the
group's id), output (the build output the run showed), reason, at}`. A declined key is left out of every group while
today's build gives that same output, counted on one `declined by the owner, hidden` line and listed in
`declined.keys`; a rule, dictionary or answer that moves its build brings it back to a group by itself (he declined
what he saw, not the key). Worse keys are never hidden. A check's finding (`--check <code>`, its keys file
`<code>.live.keys`): the line's group is the check code, the output today's build of the key; it is hidden from that
check's findings, count and keys file (never from a group, nor a group's decline from a check) while the key builds
the same. Every output declined for a key stays declined: a build that later returns to one of them is hidden
again. Each key must be what the last whole run showed (in a group, or that check's finding; a group's key must
still build to the output shown: a build moved since is refused, run sweep again and show him the new change), else
the whole command is refused, nothing written (exit 2). `--reason` ends in `(owner YYYY-MM-DD)` (else exit 2). A torn
last line of `decisions.jsonl` (a run killed while appending) is cut off before the append, named on stderr, so it
never becomes a broken middle line. It runs under the shop's lock (busy: exit 2) and writes only
`decisions.jsonl` (and the lock's holder line). The no is not a block: any later send of the key (`publish.py`
naming it, `--force` for a `.force` one, `reprice.py --apply`, a whole-shop run after a version bump) carries the
declined change with the rest of the payload; the report lists them for that question.

**His yes, the resend of one group** (the one procedure; skill `sweep`):
1. A paid group first gets its own question: "spend about $N on new answers?" (`translate.py <shop> --reask
   --keys-file F`, `describe.py <shop> --force --keys-file F`); only local files change. Read old -> new on a sample,
   sweep again, then ask about the send.
2. The state backup as the owner decides it: `state_backup.py` (about 15 GB with the photos); for a group that only
   changes descriptions or titles the agent may propose to skip it, the owner decides.
3. `sweep.py <shop> --confirm <id>`: re-builds the group's keys, drops those whose output moved since the run or that
   were sent, withdrawn or declined since; writes `groups/<id>.confirmed.keys` and `<id>.plan.tsv`; prints the send.
4. `store_diff.py <shop> --keys-file shops/<shop>/sweep/latest/groups/<id>.confirmed.keys`: always (the owner,
   2026-11-19); a product with a field the owner was not shown (a hand edit in the admin) is left out of the send:
   remove its line from both `<id>.confirmed.keys` and `<id>.plan.tsv` and tell him; do not run `--confirm` again
   afterwards (it would put the key back).
5. `publish.py <shop> --keys-file shops/<shop>/sweep/latest/groups/<id>.confirmed.keys` (`--force` for a `.force`
   group), exactly as printed. A send cut off is resumed by running it again (sent keys are skipped as same).
6. `sweep.py <shop>`: the group gone, worse 0 (the proof the send landed); `shop_view.py check <shop>
   shops/<shop>/sweep/latest/groups/<id>.plan.tsv` (every line ok) confirms the store states only (the keys were
   already active or draft). Report to the owner the keys, handles and admin links.

## Files

`shops/<shop>/sweep/latest/` (`shop_files.write_atomic`, rewritten each run; a part's previous files moved to
`sweep/prev/` first, only that part's, so `--answers` or `--store` alone keeps the other's). A run with a selection
(`--only`, `--keys-file`, `--job`) writes the same files to `sweep/selection/` instead (its own previous ones
removed, `since_prev` null) and leaves `latest/` and `prev/` alone: a part of the shop against the whole would call
every other group gone, then new.
- `answers.json` (the checks): shop, at, seconds, the input files' times, the selection, the scope, per check its
  live and draft counts and every finding `{key, store, handle, text}`, `declined` (`{check: keys hidden}`), the OCR
  error keys, `since_prev`.
- `<check>.live.keys`, `<check>.draft.keys`: one key a line (empty when none).
- `store.json` (the store part): shop, at, seconds, the selection, the scope (live, draft, baselines), `same` (keys),
  `worse` (`{key, store, handle, category, guards, changes}`), `changed` (a count a verdict), `needs_force` (a count), `no_baseline` (a reason:
  count, keys), `declined` (`{key, store, handle, group, force}`: hidden by the owner's no), `groups` (`{id, store,
  category, fields, verdict, force, cost, keys, count, examples, outputs, ledger}`: `outputs` each key's build output
  shown, `ledger` its ledger output then, what `--decline` records and `--confirm` checks), `since_prev` (`{group,
  worse or declined: {now, new, gone}}`, null on the first run).
- `groups/<group id>.keys`: one key a line, for a `--keys-file`; `declined.keys` the hidden ones.
- `groups/<group id>.confirmed.keys`, `<group id>.plan.tsv` (`key<TAB>active|draft`): written by `--confirm`.
- `shops/<shop>/sweep/decisions.jsonl` (append-only, never rotated; in the state backup's `01-state`): the owner's
  declines.

The shop's lock: refused while it is held (`shop_files.ensure_free`: a shared lock tried and dropped, the lock file
neither made nor written); not held while it reads, so a job may start meanwhile (a few seconds).

## History

- 2026-11-19: the two-brand scan (by hand) found 98 live titles holding two brands (titles the model wrote before
  2026-11-15 carry no `brand_ko`, so a brand change never asked them again: "Pongdang Swim Kids' ..." under Inparo,
  "PING Women's Junior ..." from 핑크) and the wholesaler 감씨 / the store 골드벙커 read as brands (Gamssi, Gold
  Bunker: 59 products whose images name Inparo). Fixed by hand rows and `translate._stale_lead`; `sweep.py` is
  the scan as a command.
- 2026-11-19, the first run on fairwardgolf (2,175 live, 90 drafts; 2.1 s): `title.pending_reask` 4 live,
  `title.other_brand` 1 (7 before the 조합 rule: 6 mixed sets whose Korean spells the other maker as the dictionary
  does not, 브릿지스톤, 테일러, 요넥), `text.hangul` 0, `description.old_brand` 105 (330 on the whole description:
  an Odyssey putter in 99 Callaway sets, True Temper shafts; the first sentence keeps the Gold Bunker 25 / Gamssi 13
  / PGM / Pongdang Swim / PING class), `description.patterns` 1 ("Unknown Manufacturer ..."), `description.stale`
  620 (619 live, 1 draft), OCR sidecars with an error 1.
- 2026-11-19, the review of the first run: a mixed set is also one whose spec value says 조합 (9275189943 only in
  its 종류 row "조합풀세트"): `description.old_brand` 105 -> 104; the other counts unchanged (2.1 s). Known false
  positives listed under How to use.
- 2026-11-19, stage 2, the first `--seed-sent` on fairwardgolf (13.3 s): 2,265 published, 2,263 written (84.7 MB),
  2 no_baseline, both `today's build differs from the ledger` as stage 0 measured: 10476142508 (LAROUGE, the
  dictionary's vendor spelling against the store's) and 12584340779 (the owner keeps it). A second run wrote nothing.
- 2026-11-19, stage 3, the store part (`store_run`, guards, groups, `latest/` -> `prev/`), the first full run on
  fairwardgolf: 17.5 s wall (checks 2.9 s, store part 13.9 s); 2,265 published (2,175 live, 90 drafts), 2,263 with
  a baseline, all 2,263 same, 0 changed, 0 worse, no groups; no baseline 2 (no publish/sent file: 10476142508
  LAROUGE, 12584340779). The checks against the run before: `title.pending_reask` 4 gone (the four titles settled).
- 2026-11-19, the review of stage 3: a changed key whose inputs digest is still the ledger's is `.force` (publish
  skips it unforced: a store spelling, a payload change without `sp.VERSION`), its own groups and cost; a run with
  a selection writes `sweep/selection/` and compares with nothing; `description_lost` quiet on a fallback the store
  had too; the weight is a change line, no longer a flag too. The live run: 17.3 s, all 2,263 same, 0 changed,
  0 needing --force, 0 worse, no groups; nothing new or gone since the run before.
- 2026-11-19, stage 4: the owner's decisions (`--decline`, `sweep/decisions.jsonl`: a key hidden while it builds to
  what he declined, a check's finding with `--check`) and `--confirm <group>` before a resend (a key moved, sent,
  withdrawn or declined since the run dropped; the printed `publish.py --keys-file [--force]`); the resend procedure
  above; skill `sweep`. The live run (read only, nothing declined): 17.2 s, all 2,263 same, 0 changed, 0 worse, no
  groups; nothing new or gone since the run before.
- 2026-11-19, `title.set_single`: describe.py's conflicts on 92 live products said the title promises a set while
  one club is sold (research's loose scan: title + set + single words); the check keeps it tight (the title and a set
  before "but" / "while", one club or item after it, the English title still a set). The paid fix is `translate.py
  --reask --context "..."` ([TRANSLATION.md](TRANSLATION.md)), one category's keys file at a time
  (`title.set_single/<store>.<category>.keys`); a wrong-category product is a hold question. Its review: a lone
  "single" / "only one" fired on gaps ("only one loft is given", "the number of wedges is not clear") and mixed
  option lists (pairs, three-wedge sets): the one thing is now a club or an item; the hand title rows that match are
  counted apart (`hand.<store>.keys`). The live run (read only): 26 live (16 junior; 10 full sets, each a single club
  in the full-set category: hold questions), 0 drafts; 27 live hand titles also match.
