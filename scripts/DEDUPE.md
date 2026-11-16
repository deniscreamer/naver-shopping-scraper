# Duplicates (`dedupe.py`, `job.py --dedupe`)

One product is often sold by several stores (Wilson Profile JGI: 9 copies in the store). The shop keeps it once, at
the best seller (the owner approved the rule 2026-11-15). A job checks each product right after it is collected;
two read-only commands show the decisions and the groups already in the store. Code: the `dedupe.py` docstring;
the job's side: `job.py` (`dedupe_step`, `replace_step`). What waits for the owner: [OWNER_RULES.md](OWNER_RULES.md).

## How to use

| Task | Run | Then |
|---|---|---|
| A job (`new` or `scroll`) | nothing: `--dedupe on` is the default | read the events below in `status --json` / the log |
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

- `off`: nothing is looked up.
- `log`: one event `duplicate_seen` per product with a title match (the would-be decision `duplicate_of:<key>` /
  `duplicate_better:<key>` / `duplicate_of_withdrawn:<key>`, the matches and their signals); nothing else changes.
  The index grows as in `on` (a would-be `duplicate_of` does not join it), so later decisions are the same.
- `on` (the owner's decision 2026-11-15: replace automatically): see the events below.

### What a job's events mean, and what you do

| Event / status | Means | You |
|---|---|---|
| `duplicate_seen`, decision `not_confirmed` | a title match, not confirmed by photos or variants: an ordinary product, taken | nothing |
| `duplicate_seen`, a would-be decision (`log` only) | what `on` would have done | nothing; `--pairs` after the run |
| `not_taken: duplicate_of_withdrawn:<key>` | a confirmed match the owner withdrew: never taken | nothing |
| `not_taken: duplicate_of:<key>` | not strictly better than the best confirmed match: closed (no images, no translation) | nothing |
| `duplicate_better {replaces}` | strictly better: taken as usual | nothing |
| `replaced` | once the better one was published, the old one was withdrawn (`publish.withdraw`, DRAFT, reason `replaced_by:<new key>`): it was still published and the new one has no fewer variants | nothing; it shows in the report |
| `replace_skipped` with why | the old one stays: `not published`, `the old one is not published`, the new one is a draft, `fewer variants (N < M)`, or `withdraw failed: ...` | a draft: see below; a failed withdraw: tell the owner (withdrawn by hand on his word) |

A draft (draft first, 2026-11-16) never replaces a live product (`replace_skipped`: the new one is a draft):
`job.py activate --job <id>` prints the old one's `--withdraw` line, run on the owner's word once the new one is
live ([JOB_AGENT.md](JOB_AGENT.md#draft-first-a-category-not-yet-reviewed-the-owner-2026-11-16)). A product
withdrawn as `replaced_by:` is not compared again (its replacement is).

### `--pairs`: a job's decisions

`dedupe.py --pairs <shop> --job <id> [--out DIR]` reads the job's events (`duplicate_seen`, `duplicate_better`,
`not_taken`) and writes, in the job's `pairs/`: sheets `pairs1.jpg` ... of candidate | match photos, numbered,
`dup` on the confirmed ones, and `index.tsv` (decision, signals, both keys and titles), for the owner to check the
decisions.

### `--report`: groups in the store

`dedupe.py --report <shop> [--category <id>] [--list]` counts the duplicate groups already in the store, best first
(a tie: more variants), and marks `title only` the members joined by title words alone (`dedupe.title_only`: no
shared photo, no variants alike; a colour edition, a set with its bag). Look at their photos before a withdrawal:
`lens.py dupes <shop>` shows the groups as rows, those members red.

## The rule

Right after a product is collected, before its description images, `dedupe.py` looks it up in an index built when
the run starts:

- **The index:** the shop's published products (drafts awaiting review included, draft first 2026-11-16) and the
  ones the owner withdrew (not those withdrawn as `replaced_by:<key>`: their replacement is the live copy), plus the
  job's own collected products. Each product the job takes on joins it, so a later seller in the same job is
  compared too; one of them closed later in the run (not_taken / deferred / failed, or held by the transform or the
  translation: agency_no_brand, single_only, 2026-11-15) leaves it again.
- **A possible duplicate:** the same category and the same set of title words (case, signs and order ignored, what
  is in brackets kept: `27ZXI-RKT LS` is not `27ZXI-RKT`, `Qi4D MAX` is not `Qi4D`), another store, prices within x2
  (`PRICE_RATIO`).
- **Confirmed** when the first photo is the same file, or half the photos of the smaller gallery are
  (`PHOTOS_SHARED`), or the variants agree >= 80% (`VARIANTS_JACCARD`); not confirmed: an ordinary product (event
  `duplicate_seen`, decision `not_confirmed`).
- **Purchase-agency imports** (구매대행: a copy of one foreign listing, 2026-11-15): two of them are also one product
  with a title of 12+ words (`LONG_TITLE`) alike word for word (`long_title`), or with titles translated apart
  (`alike`: the same numbers, club kinds, hand, gender and bag words, 6+ words (`ALIKE_MIN_WORDS`), 70% of them
  alike (`WORDS_ALIKE`) after one spelling per word: 모래 / 샌드, 남성용 / 남성, eAj dropped). The first photo alone is
  never a match: an agency lists each version of one listing apart under its one photo.
- **`strong`** (2026-11-15): any two products are also one with every photo and variant alike: the same category,
  photos shared >= 80% (`STRONG_PHOTOS`), variants >= 80%, and the titles not clashing on club kind, hand, gender,
  bag (미포함 wins) or the numbers standing alone (Aged 3-5 / 9-12, 9종 / 12종), a subset passing, and agreeing on a
  model's version word (MAX, LS, TR, PRO, 맥스: 27ZXI-RKT and its LS share a dealer's photo and variants).
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
