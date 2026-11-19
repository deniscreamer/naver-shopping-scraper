# Sweep: old model answers a new rule judges wrong

`sweep.py` finds products already in the store whose cached model answers (the English title, option names, the
description) a rule, dictionary or prompt improvement would now judge wrong. Re-preparing never reaches them:
`translation/texts.jsonl` keeps a title until `translate.plan` asks it again, and `describe.py` keeps a description.
Read only: local files, no network, no credentials; it writes only `shops/<shop>/sweep/latest/`.

## How to use

```sh
.venv/bin/python scripts/sweep.py <shop>                         # every published product, a table
.venv/bin/python scripts/sweep.py <shop> --json                  # the same as JSON (answers.json's shape)
.venv/bin/python scripts/sweep.py <shop> --only <ref> [--only <ref>] [--keys-file F] [--job ID [--event E]]
```

When: after a commit that changes what products are built from (a rule, a dictionary entry, a prompt), between jobs,
after `run_transform.py <shop> --diff`, `translate.py <shop> --offline` and `placement.py <shop>`; after a scroll or
job (it adds brands and terms); before a release. It takes about 2 seconds for the whole shop (2,265 published).

The first line is the scope: live (ACTIVE, or an old ledger row with no `store_status`) and drafts (`DRAFT`) are
counted apart; withdrawn products (holds among them) are left out; ready products never published are counted, not
checked. Then the input files' times, then a row a check (live, draft) with up to 3 examples (key, handle, the
offending text), and one line: the description images' OCR sidecars that carry an error (the whole shop's, whatever
the selection).

| Result | What it means | What to do |
|---|---|---|
| a check's count is 0 | nothing an improvement now judges wrong | nothing |
| `title.pending_reask` | `translate.plan` already wants these titles again (another brand than when it was asked) | paid: ask the owner ("ask again N titles, about $0.01-0.02 each?"), then `translate.py <shop> --keys-file shops/<shop>/sweep/latest/title.pending_reask.live.keys`; a republish is a second question (OWNER_RULES.md, rule 1) |
| `title.other_brand` | the English title names another dictionary brand than the vendor, the Korean does not | read the examples (known false positives below); a real error: the owner decides `translate.py --reask` on the keys file, or a hand row (`by: review-...`) per product (skill `fix-a-product`) |
| `text.hangul` | Korean left in an English text the store shows | fix at the source (a dictionary entry: skill `dictionaries`; a description: `describe.py --force --keys-file F` on the owner's word) |
| `description.old_brand` | the description names the product under another brand (an old vendor, a seller's shop) | the owner's word, then `describe.py <shop> --force --keys-file .../description.old_brand.live.keys`; then the republish question |
| `description.patterns` | a stored description trips a check `describe.py` has now (shop talk, talk about the listing, a link) | as `description.old_brand` |
| `description.stale` | the description was written from another packet than today's | nothing by default: one number, a keys file; the owner, 2026-11-19: only descriptions with an explicit error get rewritten |
| `OCR sidecars with an error (whole shop)` | `description_images.py` failed on these products | by hand only: `.venv/bin/python scripts/description_images.py <shop> --products <product id> --force` (the Naver product id, the key's last part; ~20 s a product, under the lock) |
| exit 1, `sweep: <path>:<n>: not a JSON line ...` | a shop file has a broken line | skill `recover-state` |
| `sweep: stop: <shop> is busy: ...` (exit 2) | a job or a command holds the shop's lock and rewrites the files read here | wait for it (`job.py status`), run again |
| exit 2, `no product selected` / `none of the N named products is published here` / `unknown shop` | a selection that names no published product, or a shop `shop_stores.py` does not have | name published products (it never widens to every product), or a known shop |

Live and drafts are listed apart in every count and keys file (`<check>.live.keys`, `<check>.draft.keys`): the
owner decides them apart (2026-11-19). A keys file feeds any command's `--keys-file`. Nothing is sent: what reaches
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
| `text.hangul` | Hangul in the English title, an option name or value, or the description | `translation_rules.HANGUL_RE` |
| `description.old_brand` | the description's first sentence names a brand that is not the vendor | the test of `title.other_brand` on the first sentence (where the description names the product) |
| `description.patterns` | a stored description `describe.py` would cut today | `describe.packet_free_problems` (the part of `problems()` that needs no packet: shop talk, the listing, kana / han, link, phone, price, markup) on each paragraph, heading and item; Hangul alone is `text.hangul`'s |
| `description.stale` | the packet changed since the description was written | `describe.source_sha256` against the row's `source_sha256`, as `describe.py --offline --published` counts stale (ready and translated products) |

Not checks yet (the plan's later stages): what the store would get from today's build (`store_diff.py`), guards
(worse), groups and the owner's declines. The dictionaries are read as translate.py reads them, without their sync
writes (`Dictionaries(write=False)`; test_sweep.py compares the two).

## Files

`shops/<shop>/sweep/latest/` (`shop_files.write_atomic`, rewritten each run):
- `answers.json`: shop, at, seconds, the input files' times, the selection, the scope, per check its live and
  draft counts and every finding `{key, store, handle, text}`, the OCR error keys.
- `<check>.live.keys`, `<check>.draft.keys`: one key a line (empty when none).

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
