---
name: sweep
description: What a rule, dictionary or prompt improvement changes for the products already in the store, read only (scripts/sweep.py): old model answers now judged wrong, what a resend would change (groups, worse), the owner's yes or no per group (--decline, --confirm) and the resend of a group he approved. Use for "что улучшится у старых товаров", "прогони sweep", "перезалей старые", "проверь регрессию по магазину", "after a rule change", after a scroll or job, before a release, or a new category's first run.
---

# Sweep: old products after an improvement

The doc: `scripts/SWEEP.md` (every result line, what it means, what to do). The owner's rules:
`scripts/OWNER_RULES.md` rule 1. Sweep, `--decline` and `--confirm` send nothing and cost nothing; `--confirm` is a
step of an approved resend, `--decline` only on his no.

| Task | `scripts/SWEEP.md` section |
|---|---|
| Run it, read a line of its output (a check, a group, `WORSE`, `since prev`, `declined`) | "How to use" (the table) |
| What a check catches; known false positives | "Checks"; "How to use", "Known false positives" |
| Why a product is in a group; `.force`; the fields | "The store lagging" |
| A guard tripped (worse, exit 1) | "Guards" |
| No baseline (`publish/sent/`) | "The store's before" |
| The owner's no; the resend of a group | "The owner's decisions" |
| The files (`latest/`, `prev/`, `selection/`, `decisions.jsonl`) | "Files" |

Procedure:
1. **Run**: `.venv/bin/python scripts/sweep.py <shop>` (about 20 s; refused while a job holds the shop: wait). After
   a rule change, `since prev` must show new findings only where the change meant them; any other new one, and
   any `WORSE` line, is a regression: fix it and run again before telling the owner.
2. **Read** each group and finding against its examples (`lens.py products <shop> --keys-file
   shops/<shop>/sweep/latest/groups/<id>.keys` for a visual group) and the known false positives.
3. **Report to the owner by group**, live and drafts apart: the group id, what changes, how many, the verdict, 3
   examples old -> new with handles, the cost (free: a resend; paid: N model calls, about $X, minutes). Recommend
   only `improvement` groups; `eyeball` ones are shown, not pushed.
4. **His word per group**: a yes covers that group as shown. A no: `.venv/bin/python scripts/sweep.py <shop>
   --decline --keys-file shops/<shop>/sweep/latest/groups/<id>.keys --reason "<his why> (owner <date>)"` (a
   check's finding: `--check <code>` with its `<code>.live.keys`).
5. **The resend** of a yes, in SWEEP.md's order ("The owner's decisions"): a paid re-ask as its own question first;
   the state backup as he decides (for a description- or title-only group propose skipping the 15 GB backup, he
   decides); `sweep.py <shop> --confirm <id>`; `store_diff.py <shop> --keys-file <id>.confirmed.keys` (always; a key
   it flags: out of both printed files, told); the printed `publish.py ... [--force]`; sweep again: the group gone,
   worse 0; `shop_view.py check` on the plan.
6. **Report**: keys, handles, admin links, what was dropped by `--confirm` and why; the declined keys a later send
   would still carry.

Never:
- send a group, or any key of it, without the owner's yes for that group; never widen a yes to another group;
- run a paid re-ask (`translate.py --reask`, `describe.py --force` on published products) without his yes and a
  stated cost;
- mix drafts into a live group's question (the owner, 2026-11-19: apart);
- run `description_images.py --prune-cache` (the OCR cache stays, the owner 2026-11-19), or a re-OCR or Naver
  re-collection from a sweep finding unasked;
- run `--decline` on the owner's behalf without his word in chat.

More: one product's fix: skill `fix-a-product`; the store actions: skill `store-actions`; a new check from a
defect found on old products: skill `seller-pattern-rule`.
