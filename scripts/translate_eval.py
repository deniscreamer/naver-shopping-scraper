"""The translation quality check (the owner, 2026-11-08): a sample of a shop's prepared products is translated in a
scratch folder with empty dictionaries (so the model does the work the dictionaries will later remember), then a
second model judges every translated text against its Korean, and a side-by-side HTML page shows both with the
flags. Run it when a category or a shop (tenant) is added, or after a prompt change. It costs money: about
$0.01-0.02 a product to translate and $0.03 a product to judge (2026-11-08, golf sets); nothing is written to the
shop's own translation files or the live dictionaries.

    .venv/bin/python scripts/translate_eval.py fairwardgolf --products 12 [--shops-root DIR] [--out DIR]

The sample takes varied products first (many variants, a placeholder option name, add-ons with a text field, many
reviews, a title naming one variant, a brand fallback, purchase agency), one brand each while it can.

The judge (JUDGE_MODEL, effort medium) flags: fact_lost, fact_added, meaning_changed, negation_flipped,
strength_changed, number_or_code_wrong, unnatural_english, wrong_term, untranslated. A flag is a lead for a person,
not a verdict; on 2026-11-08 three rounds of fixes took the golf sets from 25 to 10 flags of 260 texts (3.8%).

Out (in --out, default a new folder in scripts/output/translate-eval/): the sample's shops folder, judge.json,
report.html; the counts and the cost printed.
"""
import argparse
import html
import json
import os
import sys
import tempfile
import time
from collections import Counter
from typing import Any, Callable

import translate as T
import translation_dicts as D
from keep_run import OUTPUT_ROOT, SHOPS_ROOT

JUDGE_MODEL = "claude-opus-5-5"
JUDGE_BATCH = 30
JUDGED_KINDS = ("title", "brand", "review", "option_name", "option_value", "spec_value", "fact_label", "fact_value",
                "addon_group", "addon_name", "text_label")
JUDGE_SYSTEM = """You are a strict bilingual reviewer (Korean / American English) of product translations for a US
online shop that sells products bought in Korea. For each item judge the English against the Korean source. A title
may drop shop tags, the Korean distributor and words only some variants have; reviews should read like an American
buyer (casual, slang ok) but keep every fact, the strength of the opinion and any criticism; option values and specs
must be exact and short; numbers and codes must survive (units: 도=°, 인치=in, 호=Size, 번=#). Flag only real problems.
Issue codes: fact_lost, fact_added, meaning_changed, negation_flipped, strength_changed, number_or_code_wrong,
unnatural_english, wrong_term, untranslated. Return JSON only."""
JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "ok", "issues", "note"],
                               "properties": {"id": {"type": "string"}, "ok": {"type": "boolean"},
                                              "issues": {"type": "array", "items": {"type": "string"}},
                                              "note": {"type": "string"}}}}}}
JUDGE_PRICE = {"input": 4.00, "output": 20.00}


def _notes(p: dict[str, Any]) -> set[str]:
    return {str(n.get("code")) for n in p.get("notes") or [] if isinstance(n, dict)}


def sample(prepared: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """n ready products, the varied ones first, one brand each while it can."""
    ready = [p for p in prepared if p.get("status") == "ready"]
    wants: list[Callable[[dict[str, Any]], bool]] = [
        lambda p: len(p["product"]["variants"]) >= 40,
        lambda p: "option_name_placeholder" in _notes(p),
        lambda p: bool(p["product"]["addons"]) and bool(p["product"]["personalization"]),
        lambda p: sum(1 for r in p["product"]["reviews"] if r.get("text_ko")) >= 12,
        lambda p: "title_names_one_variant" in _notes(p),
        lambda p: "brand_fallback" in _notes(p),
        lambda p: "purchase_agency" in _notes(p),
    ]
    chosen: list[dict[str, Any]] = []
    brands: set[str] = set()
    for want in wants + [lambda p: True] * n:
        if len(chosen) >= n:
            break
        for strict in (True, False):
            hit = next((p for p in ready if p not in chosen and want(p)
                        and (not strict or p["product"].get("brand_ko") not in brands)), None)
            if hit:
                chosen.append(hit)
                brands.add(hit["product"].get("brand_ko"))
                break
    return chosen


def pairs(prepared: list[dict[str, Any]], translated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The unique texts with their English, judged kinds only: a dictionary kind once per Korean, a product's own
    text (title, review) once per product (two products may translate the same Korean differently)."""
    by_key = {p["key"]: p for p in prepared}
    out, seen = [], set()
    for r in translated:
        for t in by_key[r["key"]]["texts"]:
            en = r["en"].get(t["id"])
            mark = _mark(r["key"], t["kind"], t["ko"])
            if en is None or t["kind"] not in JUDGED_KINDS or mark in seen:
                continue
            seen.add(mark)
            out.append({"key": r["key"], "kind": t["kind"], "ko": t["ko"], "en": en})
    return out


def _mark(key: str, kind: str, ko: str) -> tuple[str, str, str]:
    return (key if kind in T.PRODUCT_KINDS else "", kind, ko)


def judge(items: list[dict[str, Any]], client: Any) -> tuple[list[dict[str, Any]], Counter[str]]:
    usage: Counter[str] = Counter()
    out = []
    for start in range(0, len(items), JUDGE_BATCH):
        batch = items[start:start + JUDGE_BATCH]
        body = [{"id": str(n), "kind": x["kind"], "ko": x["ko"], "en": x["en"]} for n, x in enumerate(batch, 1)]
        try:
            r = client.messages.create(model=JUDGE_MODEL, max_tokens=16000, system=JUDGE_SYSTEM,
                                       output_config={"effort": "medium",
                                                      "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
                                       messages=[{"role": "user", "content": json.dumps({"items": body},
                                                                                        ensure_ascii=False)}])
            usage.update(input=r.usage.input_tokens, output=r.usage.output_tokens)
            got = {i["id"]: i for i in json.loads("".join(b.text for b in r.content if b.type == "text"))["items"]}
        except Exception as e:                   # one bad batch (an API error, a cut answer) costs only its rows
            print(f"judge: batch {start // JUDGE_BATCH + 1} failed: {type(e).__name__}", file=sys.stderr)
            got = {}
        for n, x in enumerate(batch, 1):
            v = got.get(str(n), {"ok": None, "issues": ["judge_missing"], "note": ""})
            out.append({**x, "ok": v["ok"], "issues": v["issues"], "note": v["note"]})
    return out, usage


def report(prepared: list[dict[str, Any]], translated: list[dict[str, Any]], judged: list[dict[str, Any]]) -> str:
    """The side-by-side page: Korean (a review's page text under it) -> English, flagged rows red."""
    flags = {_mark(x["key"], x["kind"], x["ko"]): x for x in judged}
    by_key = {p["key"]: p for p in prepared}
    rows = []
    for r in translated:
        p = by_key[r["key"]]
        rows.append(f"<h2>{html.escape(r['key'].split(':')[-1])} &middot; {html.escape(str(p['product'].get('brand_ko')))}"
                    f" &middot; {html.escape(r['status'])}</h2><table>")
        originals = {x["text_ko"]: x.get("text_original_ko") for x in p["product"].get("reviews") or []}
        for t in p["texts"]:
            j = flags.get(_mark(r["key"], t["kind"], t["ko"]))
            bad = j is not None and not j["ok"]
            flag = (f"<div class=flag>{html.escape(', '.join(j['issues']))}: {html.escape(j['note'])}</div>"
                    if bad and j else "")
            orig = originals.get(t["ko"]) if t["kind"] == "review" else None
            orig_html = f"<div class=orig>page: {html.escape(orig)}</div>" if orig else ""
            rows.append(f"<tr class={'bad' if bad else 'ok'}><td class=k>{t['kind']}</td><td>{html.escape(t['ko'])}"
                        f"{orig_html}</td><td>{html.escape(r['en'].get(t['id'], ''))}{flag}</td></tr>")
        rows.append("</table>")
    n_bad = sum(1 for x in judged if not x["ok"])
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Translation eval</title><style>
:root{{--bg:#fff;--fg:#1b1b1b;--mut:#666;--line:#e3e3e3;--bad:#fff1ef;--flag:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151515;--fg:#eee;--mut:#9a9a9a;--line:#333;--bad:#3a1d1a;--flag:#ff8a80}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:16px}}
table{{border-collapse:collapse;width:100%;table-layout:fixed}}
td{{border-top:1px solid var(--line);padding:6px;vertical-align:top;white-space:pre-wrap;word-break:break-word}}
td.k{{width:110px;color:var(--mut);font-size:12px}}tr.bad td{{background:var(--bad)}}
.flag{{color:var(--flag);font-size:12px;margin-top:4px}}.orig{{color:var(--mut);font-size:12px;margin-top:4px}}
h2{{font-size:16px;margin:24px 0 6px}}</style></head><body><h1>Translation eval</h1>
<p>{len(translated)} products. Korean as sent (reviews after sanitizing, the page's text under them) &rarr; English.
Red: flagged by the judge model, {n_bad} of {len(judged)} unique texts.</p>{''.join(rows)}</body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Translate a sample with empty dictionaries, judge it, write a report.")
    ap.add_argument("shop")
    ap.add_argument("--products", type=int, default=12)
    ap.add_argument("--shops-root", default=SHOPS_ROOT)
    ap.add_argument("--out", help="the output folder (default: a new one in scripts/output/translate-eval/)")
    args = ap.parse_args(argv)
    with open(os.path.join(args.shops_root, args.shop, "prepared", "products.jsonl"), encoding="utf-8") as f:
        chosen = sample([json.loads(x) for x in f if x.strip()], args.products)
    out = args.out or os.path.join(OUTPUT_ROOT, "translate-eval", time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    shop_dir = os.path.join(out, "shops", args.shop, "prepared")
    os.makedirs(shop_dir, exist_ok=True)
    with open(os.path.join(shop_dir, "products.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in chosen))
    try:
        keys = T.keys_from_env()
        if not keys.get(T.ANTHROPIC_KEY):
            raise T.TranslateError(f"the judge ({JUDGE_MODEL}) needs {T.ANTHROPIC_KEY} in the key file")
        chain = T.build_chain(keys)
        empty = D.Dictionaries(tempfile.mkdtemp(prefix="eval-live-"), tempfile.mkdtemp(prefix="eval-backup-"))
        run = T.run(args.shop, chain, os.path.join(out, "shops"), dicts=empty)
    except T.TranslateError as e:
        print(f"translate_eval: {e}", file=sys.stderr)
        return 2
    print("\n".join(run["report"][:2]))
    translated = run["records"]
    import anthropic
    client = anthropic.Anthropic(api_key=keys.get(T.ANTHROPIC_KEY), max_retries=4)
    judged, usage = judge(pairs(chosen, translated), client)
    with open(os.path.join(out, "judge.json"), "w", encoding="utf-8") as f:
        json.dump(judged, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "report.html"), "w", encoding="utf-8") as f:
        f.write(report(chosen, translated, judged))
    bad = [x for x in judged if not x["ok"]]
    judge_cost = sum(usage[k] * p for k, p in JUDGE_PRICE.items()) / 1_000_000
    print(f"judged {len(judged)} texts: {len(bad)} flagged ({100 * len(bad) / max(1, len(judged)):.1f}%) "
          f"{dict(Counter(i for x in bad for i in x['issues']))}; judge ${judge_cost:.3f}")
    print(f"report: {os.path.join(out, 'report.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
