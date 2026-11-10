"""Translation: each prepared product's Korean texts (`texts`) -> English, before placement and publication (the
owner, 2026-11-08: by a model API; the description and the images' text are not translated, a later stage writes
the description from them).

Per text, the first that answers:
  1. the product's own store    title, review, a placeholder option name (선택 / 옵션: named from its values):
                                translation/texts.jsonl, by (product key, text id)
  2. the dictionary of its kind every other kind (brand, option and spec rows, add-ons, text fields): one
                                translation per Korean text for every product (translation_dicts.py, live copies
                                out of git, backups in git)
  3. the rules                  units and sizes, 노브랜드 (translation_rules.py); a text with no Hangul left is done
  4. the model                  one request per product with all its pending texts, partly converted by the rules

The model: Claude Sonnet 5.5, effort low (the defaults; .env sets the models, efforts and order: settings()), the answer as JSON in a fixed schema; OpenAI as the fallback (the owner,
2026-11-08) when Anthropic is down (connection, 5xx / overload, rate limit after the SDK's retries, any other API
error but a refused key) or declines: that batch starts again on OpenAI, and Anthropic rests COOLDOWN_S before it
is tried again. A product goes in batches (make_batches: its short texts, then its reviews apart, each batch
bounded in items and characters); the system prompt is the base role + the shop's brief + the category's brief
(system_prompt: prompts/tenants/<shop>.md, prompts/categories/<Naver category id>.md). Every item is checked (all ids,
no Hangul, the source's numbers and Latin codes kept, length limits, option values distinct); the failed ones go
back in the same conversation (prompts/translate_fix.md) at most FIX_ROUNDS times. What still fails leaves the
product `untranslated`; what passed is kept (dictionaries, the product's store), so the next run asks only for the
rest.

    .venv/bin/python scripts/translate.py fairwardgolf [--offline] [--only KEY] [--limit N] [--shops-root DIR]

  --offline   no model: resolve from the stores, dictionaries and rules only; say what would be asked

The keys: `.env` names a key file (TRANSLATE_KEY_FILE), mode 0600 and ignored by git, holding ANTHROPIC_API_KEY=...
and OPENAI_API_KEY=... (either may be missing: no fallback, or OpenAI only). OPENAI_TRANSLATE_MODEL in `.env`
overrides the OpenAI model. The keys go to the clients only: never into os.environ, never printed. A refused key
stops the run.

Files, shops/<shop>/translation/:
    texts.jsonl        append-only {key, id, kind, ko, en, by, at}: the product-level translations
    translated.jsonl   rebuilt each run, sorted by key: {format, key, status: translated | untranslated | pending |
                       held, en: {text id: English}, by: {dictionary, rule, product, model: count}, provider
                       (the model that answered), problems}
    report.txt         counts, the untranslated products and why, the new dictionary entries, tokens and cost
"""
import argparse
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import shop_stores
from keep_run import SHOPS_ROOT
from shopify_catalog import _git_ignored
from translation_dicts import KINDS as DICT_KINDS
from translation_dicts import Dictionaries, reminder
from translation_rules import codes, has_hangul, numbers, sanitize

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "prompts")
FORMAT = "translated/1"
MODEL = "claude-sonnet-5-5"              # the defaults; .env changes them with no code change (settings())
OPENAI_MODEL = "gpt-6.1-terra"
EFFORT = "low"
PROVIDERS_ENV = "TRANSLATE_PROVIDERS"    # the order of the chain, e.g. "anthropic,openai" or "openai"
MODEL_ENV = {"anthropic": "ANTHROPIC_TRANSLATE_MODEL", "openai": "OPENAI_TRANSLATE_MODEL"}
EFFORT_ENV = {"anthropic": "ANTHROPIC_TRANSLATE_EFFORT", "openai": "OPENAI_TRANSLATE_EFFORT"}
THINKING_ENV = "ANTHROPIC_TRANSLATE_THINKING"   # off (default: no thinking tokens for a translation) | adaptive
OPENAI_MODEL_ENV = MODEL_ENV["openai"]
# Claude models that take the server-side refusal fallback (`fallbacks: "default"`); another model is asked without it
SERVER_FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
MAX_TOKENS = 16000
FIX_ROUNDS = 2
COOLDOWN_S = 600                         # a provider that failed is not tried again for this long
PRICE_PER_MTOK = {MODEL: {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50}}
KEY_FILE_ENV = "TRANSLATE_KEY_FILE"
ANTHROPIC_KEY = "ANTHROPIC_API_KEY"
OPENAI_KEY = "OPENAI_API_KEY"
PRODUCT_KINDS = ("title", "review")
# A request carries a bounded batch (the owner, 2026-11-08: a long request invites a model to skip or invent items):
# the product's short texts in batches of BATCH_ITEMS / BATCH_CHARS, its reviews apart in REVIEW_ITEMS / REVIEW_CHARS.
# Every batch is its own conversation (fix rounds included); at the end every pending id must have an answer.
BATCH_ITEMS, BATCH_CHARS = 40, 2500
REVIEW_ITEMS, REVIEW_CHARS = 8, 2500
TENANT_PROMPTS = os.path.join(PROMPTS, "tenants")
CATEGORY_PROMPTS = os.path.join(PROMPTS, "categories")
LIMITS = {"option_name": 32, "option_value": 64, "addon_name": 64, "fact_value": 64, "fact_label": 60,
          "spec_label": 60, "addon_group": 80, "text_label": 80, "text_placeholder": 80, "title": 255}
# A title over ASK_SHORTER is sent back to the model once or twice ("too long": the prompt's own target is about
# 90); the shortest answer that passed every other check is kept when it never gets under (a long title never
# holds a product: shopify_payload.fit_title cuts it to Google's 150 at publication). 2026-11-10: a GV Tour set
# came out at 137 characters; Google Merchant Center takes at most 150 and shows about the first 70.
ASK_SHORTER = {"title": 100}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"],
          "properties": {"items": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["id", "en"],
              "properties": {"id": {"type": "string"}, "en": {"type": "string"}}}}}}


class TranslateError(Exception):
    """The stage cannot run (no key, a bad key file, the API refusing the key): fix and run again."""


class ProviderDown(Exception):
    """A provider could not answer (network, 5xx, rate limit after retries, another API error): try the next one."""


def _prompt(name: str) -> str:
    with open(os.path.join(PROMPTS, name), encoding="utf-8") as f:
        return f.read().strip()


# ---- the key ---------------------------------------------------------------------------------------------------

def read_keys(path: str, ignored: Any = _git_ignored) -> dict[str, str]:
    """The API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY) from a KEY=value file that is 0600 and ignored by git (as the
    Shopify credentials). At least one."""
    path = os.path.realpath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise TranslateError(f"key file {path} does not exist")
    if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise TranslateError(f"key file {path} is readable by others: chmod 600 it")
    if not ignored(path):
        raise TranslateError(f"key file {path} is not ignored by git: move it out of the repo or ignore it")
    keys = {}
    with open(path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                name, value = line.split("=", 1)
                name, value = name.strip().removeprefix("export ").strip(), value.strip().strip("'\"")
                if name in (ANTHROPIC_KEY, OPENAI_KEY) and value:
                    keys[name] = value
    if not keys:
        raise TranslateError(f"key file {path} has no {ANTHROPIC_KEY}=... or {OPENAI_KEY}=...")
    return keys


def keys_from_env() -> dict[str, str]:
    path = os.environ.get(KEY_FILE_ENV, "").strip()
    if not path:
        raise TranslateError(f"{KEY_FILE_ENV} is not set: put the path of the key file in .env (SETUP.md), or run "
                             "with --offline")
    return read_keys(path)


# ---- the model -------------------------------------------------------------------------------------------------

@dataclass
class Reply:
    content: Any                         # the assistant turn as returned (thinking included), sent back unchanged
    text: str
    stop_reason: str | None
    usage: dict[str, int] = field(default_factory=dict)


class Model(Protocol):
    name: str

    def send(self, system: str, messages: list[dict[str, Any]],
             schema: dict[str, Any] | None = None) -> Reply: ...


class AnthropicModel:
    """Claude through the Messages API: structured JSON output, effort low, the server-side refusal fallback."""

    def __init__(self, api_key: str, model: str = MODEL, effort: str | None = EFFORT, client: Any = None,
                 thinking: str = "off"):
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, max_retries=4)
        self.client, self.name, self.effort, self.thinking = client, model, effort, thinking

    def send(self, system: str, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> Reply:
        """`schema`: the JSON the answer must be (default: the translation's items; describe.py sends its own)."""
        import anthropic
        try:
            output: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema or SCHEMA}}
            if self.effort:
                output["effort"] = self.effort
            extra: dict[str, Any] = {}
            if self.thinking == "off":
                # Claude Sonnet 5.5 turns thinking off with between_tools (disabled is a 400 there); thinking tokens
                # are output tokens, and a translation gains little from them (measured 2026-11-08, see README)
                extra["thinking"] = {"type": "between_tools"}
            if self.name in SERVER_FALLBACK_MODELS:
                extra.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            r = self.client.beta.messages.create(
                model=self.name, max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages, output_config=output, **extra)
        except anthropic.AuthenticationError as e:
            raise TranslateError(f"Anthropic refused the key: {type(e).__name__}") from None
        except anthropic.APIError as e:
            raise ProviderDown(f"{type(e).__name__}: {str(e)[:200]}") from None
        u = r.usage
        usage = {"input": u.input_tokens or 0, "output": u.output_tokens or 0,
                 "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
        text = "".join(b.text for b in r.content if getattr(b, "type", None) == "text")
        return Reply(r.content, text, r.stop_reason, usage)


class OpenAIModel:
    """The fallback: OpenAI Chat Completions with a strict JSON schema, reasoning effort low. The conversation is the
    same as Claude's (system prompt, the user JSON, the assistant's text, the fix turns)."""

    def __init__(self, api_key: str, model: str = OPENAI_MODEL, effort: str | None = EFFORT, client: Any = None):
        if client is None:
            import openai
            client = openai.OpenAI(api_key=api_key, max_retries=4)
        self.client, self.name, self.effort = client, model, effort

    def send(self, system: str, messages: list[dict[str, Any]], schema: dict[str, Any] | None = None) -> Reply:
        import openai
        try:
            extra = {"reasoning_effort": self.effort} if self.effort else {}
            r = self.client.chat.completions.create(
                model=self.name, max_completion_tokens=MAX_TOKENS,
                messages=[{"role": "system", "content": system}] + messages,
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "answer" if schema else "translations", "strict": True,
                                                 "schema": schema or SCHEMA}},
                **extra)
        except openai.AuthenticationError as e:
            raise TranslateError(f"OpenAI refused the key: {type(e).__name__}") from None
        except openai.OpenAIError as e:
            raise ProviderDown(f"{type(e).__name__}: {str(e)[:200]}") from None
        choice = r.choices[0]
        text = choice.message.content or ""
        stop = {"length": "max_tokens", "content_filter": "refusal"}.get(choice.finish_reason, choice.finish_reason)
        if getattr(choice.message, "refusal", None):
            stop = "refusal"
        u = r.usage
        details = getattr(u, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        usage = {"input": (u.prompt_tokens or 0) - cached, "output": u.completion_tokens or 0, "cache_read": cached}
        return Reply(text, text, stop, usage)


class Chain:
    """The providers in order (Anthropic, then OpenAI). One that failed rests `cooldown_s` before it is tried again,
    so a run does not wait for a dead provider on every product."""

    def __init__(self, models: list[Model], cooldown_s: float = COOLDOWN_S, clock: Any = time.monotonic):
        self.models, self.cooldown_s, self.clock = models, cooldown_s, clock
        self.down_until: dict[str, float] = {}
        self.events: list[str] = []

    def available(self) -> list[Model]:
        now = self.clock()
        return [m for m in self.models if self.down_until.get(m.name, 0.0) <= now]

    def mark_down(self, model: Model, why: str) -> None:
        self.down_until[model.name] = self.clock() + self.cooldown_s
        self.events.append(f"{model.name} down: {why}")


def settings(env: Any = os.environ) -> list[tuple[str, str, str | None]]:
    """[(provider, model, effort)] in the chain's order, from .env (the owner, 2026-11-08: a model is changed without
    a code change). Unset: the defaults. An effort "off" is not sent (a model that takes none)."""
    order = [p.strip().lower() for p in (env.get(PROVIDERS_ENV) or "anthropic,openai").split(",") if p.strip()]
    unknown = [p for p in order if p not in MODEL_ENV]
    if unknown or not order:
        raise TranslateError(f"{PROVIDERS_ENV}: {', '.join(unknown) or 'empty'}: use anthropic and / or openai")
    out = []
    for provider in dict.fromkeys(order):
        model = (env.get(MODEL_ENV[provider]) or "").strip() or (MODEL if provider == "anthropic" else OPENAI_MODEL)
        effort = (env.get(EFFORT_ENV[provider]) or "").strip() or EFFORT
        out.append((provider, model, None if effort.lower() == "off" else effort))
    return out


def build_chain(keys: dict[str, str], env: Any = os.environ) -> Chain:
    """The providers of settings() whose key is in the key file; none: the run cannot ask a model."""
    models: list[Model] = []
    for provider, model, effort in settings(env):
        if provider == "anthropic" and keys.get(ANTHROPIC_KEY):
            thinking = (env.get(THINKING_ENV) or "off").strip().lower()
            models.append(AnthropicModel(keys[ANTHROPIC_KEY], model, effort, thinking=thinking))
        elif provider == "openai" and keys.get(OPENAI_KEY):
            models.append(OpenAIModel(keys[OPENAI_KEY], model, effort))
    if not models:
        raise TranslateError(f"no key in the key file for the providers of {PROVIDERS_ENV}")
    return Chain(models)


# ---- one product -----------------------------------------------------------------------------------------------

def _placeholders(prepared: dict[str, Any]) -> set[str]:
    """The placeholder option names (선택 / 옵션 ...). The transform joins several axes' names with ", " in one note."""
    out: set[str] = set()
    for n in prepared.get("notes") or []:
        if isinstance(n, dict) and n.get("code") == "option_name_placeholder" and n.get("detail"):
            detail = str(n["detail"])
            out |= {detail, *(w.strip() for w in detail.split(", ") if w.strip())}
    return out


def plan(prepared: dict[str, Any], dicts: Dictionaries, store: dict[tuple[str, str], str],
         tenant: str) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    """-> (English by text id, where each came from, the items the model must translate)."""
    key = prepared["key"]
    product = prepared.get("product") or {}
    placeholders = _placeholders(prepared)
    category = (prepared.get("source") or {}).get("category_id")
    one_variant = [w.strip() for n in prepared.get("notes") or []                # the transform joins spans with ", "
                   if isinstance(n, dict) and n.get("code") == "title_names_one_variant" and n.get("detail")
                   for w in str(n["detail"]).split(", ") if w.strip()]
    options = product.get("options") or []
    option_of = {v: o["name_ko"] for o in options for v in o["values_ko"]}
    values_of = {o["name_ko"]: o["values_ko"] for o in options}
    en: dict[str, str] = {}
    by: dict[str, str] = {}
    pending: list[dict[str, Any]] = []
    for t in prepared.get("texts") or []:
        tid, kind, ko = t["id"], t["kind"], t["ko"]
        own = kind in PRODUCT_KINDS or (kind == "option_name" and ko in placeholders)
        hit = store.get((key, tid)) if own else dicts.get(kind, ko)
        if hit is None and kind in ("spec_value", "fact_value"):
            hit = dicts.get("brand", ko)                 # a 브랜드 / 제조사 row: the shop's vendor spelling
        if hit is not None:
            en[tid], by[tid] = hit, "product" if own else "dictionary"
            continue
        source = sanitize(kind, ko, tenant, category)
        if not has_hangul(source):
            en[tid], by[tid] = source, "rule"
            continue
        item: dict[str, Any] = {"id": tid, "kind": kind, "source": source}
        if kind == "title" and one_variant:
            # the transform's note title_names_one_variant: words only some variants are (the title keeps to what
            # every variant is); the check does not ask for their numbers / codes
            item["context"] = "drop from the title, only some variants have it: " + " | ".join(one_variant)
            item["drop"] = [sanitize("title", w, tenant, category) for w in one_variant]
        if kind == "option_name" and ko in placeholders:
            item["context"] = "values: " + " | ".join(values_of.get(ko, [])[:12])
            item["placeholder"] = True           # named from its values: its own digits (선택2) need not survive
        elif kind == "option_value" and ko in option_of and option_of[ko] not in placeholders:
            item["context"] = "option: " + option_of[ko]
        pending.append(item)
    # option values of one axis that the dictionaries / rules made the same English: asked again, told to differ
    by_text = {t["id"]: t for t in prepared.get("texts") or []}
    for same in collisions(prepared, en):
        english = {x: en[x] for x in same}
        for tid in same:
            if by.get(tid) in ("dictionary", "rule"):
                t = by_text[tid]
                pending.append({"id": tid, "kind": t["kind"], "source": sanitize(t["kind"], t["ko"], tenant, category),
                                "context": "must differ from: " + ", ".join(english[x] for x in same if x != tid)})
                en.pop(tid)
                by.pop(tid)
    return en, by, pending


def request(prepared: dict[str, Any], en: dict[str, str], pending: list[dict[str, Any]],
            dicts: Dictionaries) -> str:
    """The user message, compact (the owner, 2026-11-08: no token spent twice): the product's title and brand, the
    shop's vendor spellings only when a brand is asked, the items with the batch's short ids. The category's terms
    are in the system prompt (cached), not here."""
    product = prepared.get("product") or {}
    brand_id = next((t["id"] for t in prepared.get("texts") or [] if t["kind"] == "brand"), None)
    head: dict[str, Any] = {"title_ko": product.get("title_ko")}
    if brand_id and en.get(brand_id):
        head["brand_en"] = en[brand_id]
    body: dict[str, Any] = {"product": head}
    if any(i["kind"] == "brand" for i in pending):
        body["vendors"] = dicts.vendors()
    body["items"] = [{k: v for k, v in i.items() if k in ("id", "kind", "source", "context")} for i in pending]
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def make_batches(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """The pending items in request-sized batches: short texts first (in their order: title, brand, options ...),
    then the reviews; a batch closes at its item or character limit; an item longer than the limit goes alone."""
    out: list[list[dict[str, Any]]] = []
    for reviews in (False, True):
        limit_n, limit_c = (REVIEW_ITEMS, REVIEW_CHARS) if reviews else (BATCH_ITEMS, BATCH_CHARS)
        batch: list[dict[str, Any]] = []
        size = 0
        for item in items:
            if (item["kind"] == "review") != reviews:
                continue
            n = len(item["source"]) + len(item.get("context") or "")
            if batch and (len(batch) >= limit_n or size + n > limit_c):
                out.append(batch)
                batch, size = [], 0
            batch.append(item)
            size += n
        if batch:
            out.append(batch)
    return out


def _spec(folder: str, name: str | None) -> str | None:
    path = os.path.join(folder, f"{name}.md")
    if name and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return None


def system_prompt(shop: str | None, category_id: str | None) -> str:
    """The base prompt (the translator's role and rules) + the shop's brief (prompts/tenants/<shop>.md) + the
    category's brief (prompts/categories/<Naver category id>.md: what the products are, how buyers write, terms).
    A missing brief is left out (the base prompt works alone): add one to make a new shop or category precise."""
    parts = [_prompt("translate_system.md")]
    tenant = _spec(TENANT_PROMPTS, shop)
    if tenant:
        parts.append("## The shop\n\n" + tenant)
    category = _spec(CATEGORY_PROMPTS, str(category_id) if category_id else None)
    if category:
        parts.append("## The product category\n\n" + category)
    return "\n\n".join(parts)


_PROMO = r"당일|발송|출고|배송|무료|할인|특가|이벤트|사은품|증정|AS|A/S|정품|쿠폰|적립"
_BRACKETS_RE = re.compile(r"\[[^\]]*\]|[(（][^)）]*(?:" + _PROMO + r")[^)）]*[)）]|[가-힣]*(?:코리아|인터내셔날|인터내셔널)\s*"
                          r"(?:\d+\s*%)?|\d+\s*%\s*(?:정품|할인|적립)|(?<![A-Za-z])(?:무상\s*A/?S|A/S(?:\s*(?:가능|보장))?|AS\s*(?:가능|보장))(?![A-Za-z])")   # after-sales claims


def _checked_source(item: dict[str, Any]) -> str:
    """The part of the source whose numbers and codes must survive: a title's [bracketed] shop tags ([1년AS],
    [오늘출고]) and its Korean distributor ("던롭스포츠코리아100%", "삼양인터내셔날") may be dropped, as the system prompt
    asks."""
    if item.get("placeholder"):
        return ""                                # renamed from its values: nothing of "선택2" must survive
    if item["kind"] != "title":
        return item["source"]
    text = _BRACKETS_RE.sub(" ", item["source"])
    for word in item.get("drop") or []:
        text = text.replace(word, " ")
    return text


def verify(items: list[dict[str, Any]], text: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """The model's answer -> (accepted English by id, failed items with their problems). An item whose only problem
    is being over ASK_SHORTER carries `usable`: its English, good enough when no shorter one comes."""
    want = {i["id"]: i for i in items}
    try:
        got = json.loads(text)
        rows = got["items"]
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise TypeError("items")
    except (ValueError, KeyError, TypeError):
        return {}, [{"id": i["id"], "source": i["source"], "en": None, "problems": ["not json / wrong shape"]}
                    for i in items]
    accepted: dict[str, str] = {}
    failed: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for r in rows:
        rid, out = str(r.get("id")), r.get("en")
        if rid not in want:
            continue                                     # an id not asked for is ignored (the fix prompt says so)
        item = want[rid]
        problems = []
        if rid in seen:
            problems.append("duplicate id")
        seen.add(rid)
        out = out.strip() if isinstance(out, str) else ""
        if not out:
            problems.append("empty")
        if has_hangul(out):
            problems.append("korean left")
        checked = _checked_source(item)
        lost = [n for n in numbers(checked) if n not in out]
        if lost:
            problems.append("numbers changed: missing " + ", ".join(lost))
        lost_codes = sorted(c for c in codes(checked) if c not in out.upper())
        if lost_codes:
            problems.append("codes lost: missing " + ", ".join(lost_codes))
        limit = LIMITS.get(item["kind"])
        if limit and len(out) > limit:
            problems.append(f"too long: {len(out)} characters, at most {limit}")
        usable = None
        ask = ASK_SHORTER.get(item["kind"])
        if ask and not problems and len(out) > ask:
            problems.append(f"too long: {len(out)} characters, at most {ask}")
            usable = out
        if problems:
            failed[rid] = {"id": rid, "source": item["source"], "en": out or None, "problems": problems}
            if usable:
                failed[rid]["usable"] = usable
            accepted.pop(rid, None)
        else:
            accepted[rid] = out
    for rid, item in want.items():
        if rid not in seen:
            failed[rid] = {"id": rid, "source": item["source"], "en": None, "problems": ["missing"]}
    return accepted, list(failed.values())


def collisions(prepared: dict[str, Any], en: dict[str, str]) -> list[list[str]]:
    """Option values of one axis that became the same English: [[text id, ...], ...]."""
    from transform import text_id
    out = []
    for o in (prepared.get("product") or {}).get("options") or []:
        ids = [text_id("option_value", v) for v in dict.fromkeys(o["values_ko"])]
        by_en: dict[str, list[str]] = {}
        for i in ids:
            if i in en:
                by_en.setdefault(en[i].casefold(), []).append(i)
        out += [same for same in by_en.values() if len(same) > 1]
    return out


@dataclass
class Outcome:
    record: dict[str, Any]
    new_texts: list[dict[str, Any]]      # product-level translations to append to texts.jsonl
    usage: dict[str, dict[str, int]]     # by model name
    calls: int


def _converse(model: Model, prepared: dict[str, Any], pending: list[dict[str, Any]], en: dict[str, str],
              dicts: Dictionaries, usage: dict[str, int],
              system: str | None = None) -> tuple[dict[str, str], list[dict[str, Any]], int, str]:
    """One conversation with one model: the request, then the fix rounds. -> (accepted English by id, the problems
    left, calls, how it ended: done | refusal | max_tokens). ProviderDown passes up. The model sees the batch's short
    ids ("1", "2" ...: fewer tokens in and out than the text ids); they are mapped back here.
    A fix round asked only to shorten titles (every item still asked has a usable answer) never costs the batch:
    the provider going down, a refusal or a cut answer in it ends the conversation as done, with those answers."""
    real = {str(n): i["id"] for n, i in enumerate(pending, 1)}
    wire = {v: k for k, v in real.items()}
    items = {str(n): {**i, "id": str(n)} for n, i in enumerate(pending, 1)}
    messages: list[dict[str, Any]] = [{"role": "user", "content": request(prepared, en, list(items.values()), dicts)}]
    ask = list(items.values())
    model_en: dict[str, str] = {}
    usable: dict[str, str] = {}                       # over ASK_SHORTER only: the shortest answer so far
    problems: list[dict[str, Any]] = []
    system = system or _prompt("translate_system.md")
    calls = 0

    def settle() -> None:
        """A problem whose item has a usable answer is no problem: the shortest good one stands."""
        for p in [p for p in problems if p["id"] in usable and p["id"] not in model_en]:
            model_en[p["id"]] = usable[p["id"]]
            problems.remove(p)

    for round_no in range(FIX_ROUNDS + 1):
        only_length = bool(round_no) and all(i["id"] in usable for i in ask)
        try:
            reply = model.send(system, messages)
        except ProviderDown:
            if not only_length:
                raise
            break                                     # the answers so far stand (settle below)
        calls += 1
        for k, v in reply.usage.items():
            usage[k] = usage.get(k, 0) + v
        if reply.stop_reason in ("refusal", "max_tokens"):
            problems = [{"id": i["id"], "source": i["source"], "en": None, "problems": [str(reply.stop_reason)]}
                        for i in ask]
            settle()
            return _back(model_en, problems, real) + (calls, "done" if not problems else str(reply.stop_reason))
        accepted, problems = verify(ask, reply.text)
        model_en.update(accepted)
        for p in problems:
            text = p.pop("usable", None)
            if text and len(text) < len(usable.get(p["id"], text + " ")):
                usable[p["id"]] = text
        merged = {**en, **{real[k]: v for k, v in model_en.items()}}
        for same in collisions(prepared, merged):
            for i in [wire[i] for i in same if i in wire and wire[i] in model_en]:
                problems.append({"id": i, "source": items[i]["source"], "en": model_en.pop(i),
                                 "problems": ["values not distinct: " + ", ".join(
                                     items[wire[j]]["source"] if j in wire else merged.get(j, j) for j in same)]})
        if not problems or round_no == FIX_ROUNDS:
            break
        fix = _prompt("translate_fix.md") + "\n" + json.dumps({"failed": problems}, ensure_ascii=False,
                                                              separators=(",", ":"))
        messages += [{"role": "assistant", "content": reply.content}, {"role": "user", "content": fix}]
        ask = [items[p["id"]] for p in problems if p["id"] in items]
    settle()                                          # never under the asked length: the shortest good one stands
    return _back(model_en, problems, real) + (calls, "done")


def _back(model_en: dict[str, str], problems: list[dict[str, Any]],
          real: dict[str, str]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """The batch's short ids -> the text ids."""
    return ({real[k]: v for k, v in model_en.items()},
            [{**p, "id": real.get(p["id"], p["id"])} for p in problems])


def translate_product(prepared: dict[str, Any], dicts: Dictionaries, store: dict[tuple[str, str], str],
                      tenant: str, model: "Model | Chain | None", now: str) -> Outcome:
    key = prepared["key"]
    record: dict[str, Any] = {"format": FORMAT, "key": key, "en": {}, "by": {}, "problems": [], "provider": None}
    usage: dict[str, dict[str, int]] = {}
    if prepared.get("status") != "ready":
        return Outcome({**record, "status": "held"}, [], usage, 0)
    en, by, pending = plan(prepared, dicts, store, tenant)
    calls = 0
    problems: list[dict[str, Any]] = []
    model_of: dict[str, str] = {}                     # text id -> the model that translated it
    waiting = False                                   # a batch no provider could take: the product waits
    system = system_prompt(prepared.get("shop"), (prepared.get("source") or {}).get("category_id"))
    for batch in (make_batches(pending) if pending and model is not None else []):
        providers: list[Model] = model.available() if isinstance(model, Chain) else [model] if model else []
        answered = False
        for n, m in enumerate(providers):
            try:
                got, batch_problems, c, end = _converse(m, prepared, batch, en, dicts,
                                                        usage.setdefault(m.name, {}), system)
            except ProviderDown as e:
                if isinstance(model, Chain):
                    model.mark_down(m, str(e))
                continue
            calls += c
            if end != "done" and n + 1 < len(providers):
                continue                              # declined or cut: the next provider tries this batch
            for tid, text in got.items():
                en[tid], by[tid], model_of[tid] = text, "model", m.name
            problems += batch_problems
            answered = True
            break
        if not answered:
            waiting = True
            problems.append({"id": "-", "problems": ["every provider down for a batch of "
                                                     f"{len(batch)}: " + ", ".join(i["id"] for i in batch[:3])]})
    asked = bool(calls)
    new_texts = []
    placeholders = _placeholders(prepared)
    for t in prepared.get("texts") or []:
        if by.get(t["id"]) != "model":
            continue
        if t["kind"] in PRODUCT_KINDS or (t["kind"] == "option_name" and t["ko"] in placeholders):
            store[(key, t["id"])] = en[t["id"]]
            new_texts.append({"key": key, "id": t["id"], "kind": t["kind"], "ko": t["ko"], "en": en[t["id"]],
                              "by": model_of.get(t["id"]), "at": now})
        else:
            dicts.add(t["kind"], t["ko"], en[t["id"]])
    missing = [t["id"] for t in prepared.get("texts") or [] if t["id"] not in en]
    collide = collisions(prepared, en)
    if collide:
        problems += [{"id": i, "problems": ["values not distinct"]} for same in collide for i in same]
    status = ("translated" if not missing and not collide else
              "pending" if waiting or not asked else "untranslated")
    counts: dict[str, int] = {}
    for source in by.values():
        counts[source] = counts.get(source, 0) + 1
    record.update(status=status, en=en, by=counts, problems=problems if status != "translated" else [],
                  missing=missing, model_calls=calls,
                  provider=",".join(sorted(set(model_of.values()))) or None)
    return Outcome(record, new_texts, usage, calls)


# ---- the shop --------------------------------------------------------------------------------------------------

def _load_store(path: str) -> dict[tuple[str, str], str]:
    store: dict[tuple[str, str], str] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    store[(row["key"], row["id"])] = row["en"]
                except (ValueError, KeyError, TypeError):
                    continue                     # a torn last line (a run killed while writing): ignored
    return store


def cost(usage: dict[str, dict[str, int]]) -> tuple[float, list[str]]:
    """Dollars for the models with a known price; the models without one are listed (their tokens are reported)."""
    total, unknown = 0.0, []
    for name, u in usage.items():
        prices = PRICE_PER_MTOK.get(name)
        if prices is None:
            unknown.append(name)
            continue
        total += sum(u.get(k, 0) * p for k, p in prices.items()) / 1_000_000
    return total, unknown


def run(shop: str, model: "Model | Chain | None", shops_root: str = SHOPS_ROOT, dicts: Dictionaries | None = None,
        only: str | None = None, limit: int | None = None, clock: Any = time.gmtime) -> dict[str, Any]:
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    dicts = dicts or Dictionaries()
    with open(os.path.join(shops_root, shop, "prepared", "products.jsonl"), encoding="utf-8") as f:
        prepared = [json.loads(x) for x in f if x.strip()]
    out_dir = os.path.join(shops_root, shop, "translation")
    os.makedirs(out_dir, exist_ok=True)
    texts_path = os.path.join(out_dir, "texts.jsonl")
    store = _load_store(texts_path)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", clock())
    records: list[dict[str, Any]] = []
    usage: dict[str, dict[str, int]] = {}
    calls = asked = 0
    for p in sorted(prepared, key=lambda x: x["key"]):
        use = model
        if (only and p["key"] != only) or (limit is not None and asked >= limit):
            use = None                                   # resolved from what is kept, not sent
        outcome = translate_product(p, dicts, store, tenant, use, now)
        if outcome.calls:
            asked += 1
        records.append(outcome.record)
        calls += outcome.calls
        for name, u in outcome.usage.items():
            mine = usage.setdefault(name, {})
            for k, v in u.items():
                mine[k] = mine.get(k, 0) + v
        if outcome.new_texts:
            with open(texts_path, "a", encoding="utf-8") as f:
                f.write("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in outcome.new_texts))
        dicts.save()                                     # after each product: a stopped run keeps its answers
    with open(os.path.join(out_dir, "translated.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records))
    status: dict[str, int] = {}
    sources: dict[str, int] = {}
    for r in records:
        status[r["status"]] = status.get(r["status"], 0) + 1
        for k, v in r["by"].items():
            sources[k] = sources.get(k, 0) + v
    pending_kinds: dict[str, int] = {}
    kinds = {t["id"]: t["kind"] for p in prepared for t in p.get("texts") or []}
    for r in records:
        for tid in r.get("missing") or []:
            pending_kinds[kinds.get(tid, "?")] = pending_kinds.get(kinds.get(tid, "?"), 0) + 1
    usage = {name: u for name, u in usage.items() if any(u.values())}   # a provider that never answered: no line
    dollars, unpriced = cost(usage)
    providers: dict[str, int] = {}
    for r in records:
        if r.get("provider"):
            providers[r["provider"]] = providers.get(r["provider"], 0) + 1
    lines = [f"translate {shop}: {len(records)} products: {status}; texts by {sources}; model calls {calls}, "
             f"answered by {providers or 'none'}; tokens {usage or 0}, cost ${dollars:.4f}"
             + (f" (+ {', '.join(unpriced)}: no price set)" if unpriced else ""),
             f"  not translated yet, by kind: {pending_kinds or 'none'}",
             f"  new dictionary entries: " + (", ".join(f"{k} {len(v)}" for k, v in dicts.added.items() if v)
                                             or "none")]
    due = reminder(dicts.live_root, dicts.backup_root) if not only else None   # a job's product: the job says it
    if due:
        lines.append("  " + due)
    if isinstance(model, Chain):
        lines.insert(1, "  chain: " + " -> ".join(f"{m.name}" for m in model.models))
        lines += [f"  {e}" for e in model.events]
    for r in records:
        if r["status"] == "untranslated":
            lines.append(f"  untranslated {r['key']}: " + "; ".join(
                f"{p['id']}: {', '.join(p['problems'])}" for p in r["problems"][:6]))
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return {"records": records, "report": lines, "usage": usage, "calls": calls}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Translate a shop's prepared products (Korean -> English).")
    p.add_argument("shop")
    p.add_argument("--shops-root", default=SHOPS_ROOT)
    p.add_argument("--offline", action="store_true", help="no model: stores, dictionaries and rules only")
    p.add_argument("--only", help="send only this product key to the model")
    p.add_argument("--limit", type=int, help="send at most N products to the model")
    args = p.parse_args(argv)
    try:
        model = None if args.offline else build_chain(keys_from_env())
        print("\n".join(run(args.shop, model, args.shops_root, only=args.only, limit=args.limit)["report"]))
    except TranslateError as e:
        print(f"translate: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
