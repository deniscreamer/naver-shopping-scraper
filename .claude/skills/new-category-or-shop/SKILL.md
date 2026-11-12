---
name: new-category-or-shop
description: Add a new Naver leaf category to a shop, or a new shop (tenant), to the collect → transform → translate → describe → place → price → publish pipeline without silent gaps. Use when the owner asks to collect another category (golf bags, drivers, shoes, any Naver category id), to add another tenant or store, or asks what must be filled in for one (package defaults, delivery price, sections).
---

# A new category or a new shop

The checklist and the reasons are in `scripts/ONBOARDING.md`. Read it first; this skill is only the procedure.

1. **Scope.** Say which case it is: a category in an existing shop (part A), a new shop (part B), or both. Find
   the Naver **leaf** id (`/categories/list`, or a product page's `specs.category.id`). Every file uses that one
   string.
2. **Ask the owner, never invent.** Use one AskUserQuestion round for the owner's values, each written down with
   its date:
   - A1: the package averages, and baselines only for a set in a container;
   - A2: paid variants, paid add-ons, OCR of the images;
   - A3: the shop's sections, the split attribute, and what to do with an unresolved value;
   - A5: the coefficients and the duty for this category;
   - for a shop: B1 the domain, shop id and namespace; B2 the credentials variable (never read the file);
     B6 the delivery rule.
3. **Plan in `research/<feature>/`** (outside git): a checklist from ONBOARDING.md rows A/B. Then decide on each
   row of part C with the owner. C1 (the hardcoded `fairwardgolf` metafield namespace) must be fixed before a
   second shop publishes anything.
4. **Implement** the required rows first, then the quality rows the category needs. Keep each value's owner and
   date in a comment or the row's `approved_*`. Rules: `AGENTS.md`; for `server/`, `server/docs/DEVELOPMENT_RULES.md`.
5. **Tests.**
   - Update the registry tests named in A1 (`version`) and B10.
   - Run `.venv/bin/python -m pytest scripts -q`, and `-m pytest -q` if `server/` changed.
   - After the first checked products, add fixtures: `scripts/make_measures_fixture.py` for the package, plus the
     collected and placement fixtures.
6. **First run, small.**
   - `SHOP_STORE=<shop> .venv/bin/python scripts/job.py new --query "..." --category <leaf id> --count 5`.
   - `new` only reads and screens the listing. `category_mismatch` means a wrong id.
   - `job.py run` collects and prepares. `stop: prepare: ShopRulesMissing` means A2.
   - Run `placement.py <shop>`; `no_profile` means A3.
   - Check 2-3 products by hand, then run `publish.py <shop> --dry-run` (ONBOARDING.md part D).
   - Publish for real only after the owner says yes. Shopify writes go only through `publish.py` /
     `shopify_admin.py`.
7. **Finish.**
   - Update the docs of every rule you changed and `CHANGELOG.md`.
   - Correct ONBOARDING.md if the code differed from it (it is the map: keep it true).
   - Delete the research folder. Commit only when asked.
