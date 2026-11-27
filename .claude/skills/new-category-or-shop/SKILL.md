---
name: new-category-or-shop
description: Add a new Naver leaf category to a shop, or a new shop (tenant), to the collect → transform → translate → describe → place → price → publish pipeline without silent gaps. Use when the owner asks to collect another category (golf bags, drivers, shoes, any Naver category id), to add another tenant or store, or asks what must be filled in for one (package defaults, delivery price, sections).
---

# A new category or a new shop

The task: a new Naver leaf category in a shop, or a new shop (tenant), through every stage without silent gaps.
The checklist and the reasons: `scripts/ONBOARDING.md`; this skill is the procedure.

| Task | `scripts/ONBOARDING.md` section |
|---|---|
| The commands of a first run, what each result means, what to read after it | "How to use" |
| The legend (stops / silent / weaker), one leaf id everywhere, the owner gives the values | "Rules for every row" |
| A category in an existing shop: what stops without it | "A. A new category in an existing shop", "Required" |
| What works without, but worse | "Quality: works without these, but worse" |
| A new shop (tenant) | "B. A new shop (tenant)" |
| Golf or `fairwardgolf` in shared code | "C. Golf or fairwardgolf in shared code" |
| What earlier categories did to the rest of the shop (L1-L10), when the file was written | "History", "Learned on the first new category" |
| The first run, in order | "D. The order of a first run" |
| The pilots of 5 and 30: review every phase, fix, rebuild, report, wait | "E. The pilot cycle: 5, then 30, then the owner" |
| Each stage's own part | skills `transform`, `translation`, `describe`, `placement`, `price`, `publish` |

Rules: `scripts/OWNER_RULES.md`; who gives which value, dated (ONBOARDING.md "Rules for every row"): the package
defaults are yours (2026-11-26), the rest the owner's yes on your numbers.

1. **Scope.** Say which case it is: a category in an existing shop (part A), a new shop (part B), or both. Find
   the Naver **leaf** id (`/categories/list`, or a product page's `specs.category.id`). Every file uses that one
   string.
2. **Analysis phase, before anything is added (the owner 2026-11-22).** Nothing goes into the rule files until it
   is done. Read the store's collections (ONBOARDING.md A6: the section may exist already), probe
   the listing the jobs read (ONBOARDING.md "B0. Probe the listing": `scripts/listing_probe.py` with the owner's
   query and two or three candidates: the rows by category, the adjacent leaves, the screen's reasons with
   examples, `--alt-rules`, the page's attributes), and price the candidate default boxes on a cheap and a dear
   product (A1). Decide from the probe's flags yourself; ask the owner only where the probe cannot settle a choice
   that changes what the shop sells. Look at every contact sheet of the probe and write `decision.md` in its folder
   (the queries the jobs take, the adjacent leaves: together / own section / leave, the rules: keep / widen /
   narrow). Probe again after every change of the title screen, and once more right before the pilot. Bring
   numbers to the questions.
3. **The package defaults are yours; the rest: propose, then the owner's yes.** Write the A1 row yourself
   (ONBOARDING.md E1: the probe's cards and pages, priced on a cheap and a dear product; a baseline for a set in a
   container stays the owner's). Then one round to the owner with your proposed numbers, each written down with its
   date:
   - A2: paid variants, paid add-ons, OCR of the images;
     `reviewed` is never asked: a new category stays False (its products go DRAFT first) until the owner's word
     after the pilot's review and activation;
   - A3: the shop's sections, the split attribute, and what to do with an unresolved value;
   - A5: the coefficients and the duty for this category;
   - for a shop: B1 the domain, shop id and namespace; B2 the credentials variable (never read the file);
     B6 the delivery rule.
4. **Plan in `research/<feature>/`** (outside git): a checklist from ONBOARDING.md rows A/B. Then decide on each
   row of part C with the owner. C1 (the hardcoded `fairwardgolf` metafield namespace) must be fixed before a
   second shop publishes anything.
5. **Implement** the required rows first, then the quality rows the category needs. Keep each value's owner and
   date in a comment or the row's `approved_*`. Rules: `AGENTS.md`; for `server/`, `server/docs/DEVELOPMENT_RULES.md`.
6. **Tests.**
   - Update the registry tests named in A1 (`version`) and B10.
   - Run `.venv/bin/python -m pytest scripts -q`, and `-m pytest -q` if `server/` changed.
   - After the first checked products, add fixtures: `scripts/make_measures_fixture.py` for the package, plus the
     collected and placement fixtures.
7. **The pilot cycle (ONBOARDING.md part E, the owner 2026-11-26), yours up to the report.** The pilot of 5,
   every product read by hand in every phase, the fixes (rules, readers, the package row), the rebuild and the
   resend of the pilot's own drafts; then the pilot of 30, its lens review (a workflow), the same fixes, every new
   rule run over the whole category; then a short report in the chat with the next step to choose (the next 100,
   or the fixes that need the owner's yes) and wait. Never leave every product on the default box: the pilot
   either reads the real weights and sizes or improves the reader. The commands of the first job:
   - The pilot of 5 (E2): `TRANSLATE_PROVIDERS=openai,anthropic SHOP_STORE=<shop> .venv/bin/python -u scripts/job.py
     scroll --query "..." --category <leaf id> <paid flags> --publish --describe --count 5` (skill `run-a-job`), its
     products DRAFT; then 30 the same way. The old mode (`job.py new ... --count 5 --publish --describe`, `run`) only
     on the owner's word or for 2+ queries.
   - `category_mismatch` in the screen counts means a wrong id; `stop: prepare: ShopRulesMissing` means A2;
     `placement.py <shop>` showing `no_profile` means A3.
   - Read every product of the pilot by hand (E3); `publish.py <shop> --dry-run` for the price breakdown.
   - The job's `--paid` / `--paid-variants` holds for its own products only (ONBOARDING.md L1).
   - With the fixes: `run_transform.py`, `translate.py` (offline first), `describe.py --only` where moved,
     `placement.py`, then `publish.py <shop> --job <id>`: the pilot's own drafts, no owner's word (E4).
   - Before the report (E6): what the category did to the rest of the shop, step 8.
   - Activation and `reviewed` only on the owner's word. Shopify writes go only through `publish.py` /
     `shopify_admin.py`.
8. **Read what the new category did to the rest of the shop** (ONBOARDING.md "Learned" under "History", part D step 6):
   `.venv/bin/python scripts/store_diff.py <shop>` (read only) lists the published products a publication would
   change, field by field, and those that cannot be built now; then `translation_dicts.py status`: read every new
   dictionary entry before the dictionaries' backup. Run it in E6, before the report; any live product it lists is
   the owner's to decide (`scripts/OWNER_RULES.md` rule 1).
9. **Finish.**
   - Update the docs of every rule you changed, in the same commit (AGENTS.md rule 6). CHANGELOG.md is frozen at
     0.18.0: no entry (the owner, 2026-11-14); releases: skill `release`.
   - Correct ONBOARDING.md if the code differed from it (it is the map: keep it true).
   - Delete the research folder. Commit only when asked.
