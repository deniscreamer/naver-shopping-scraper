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

    .venv/bin/python scripts/translate.py fairwardgolf [--offline] [--only REF] [--keys-file F] [--job ID [--event E]]
                                                      [--limit N] [--reask [--context TEXT]] [--shops-root DIR]

  --offline   no model: resolve from the stores, dictionaries and rules only; say what would be asked
  --only      the one product the model may be asked for: a key, Naver product id, handle or link (shop_view.resolve)
  --keys-file, --job [--event]   more products the model may be asked for (shop_view.selected_keys); a ref that
              names no product or several stops the command (exit 2) before anything is asked
  --reask     with named products only: their own titles and placeholder option names asked again with today's
              notes, the old English kept until a checked answer; a hand correction (by review-...) never
  --context   with --reask only: a text added to each re-asked title's context (joined with any note's), e.g. "only
              one club is sold, the buyer picks its type: do not call it a set" (sweep's title.set_single, 2026-11-19)

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
from typing import Any, Collection, Protocol

import shop_stores
from keep_run import SHOPS_ROOT
from shop_files import append_line, locked, write_atomic
from shop_view import add_ref_flags, keys_from_args, selection_asked
from shopify_catalog import _git_ignored
from translation_dicts import KINDS as DICT_KINDS
from translation_dicts import Dictionaries, reminder
from translation_rules import NO_BRAND, codes, has_hangul, numbers, sanitize

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS = os.path.join(HERE, "prompts")
FORMAT = "translated/1"
MODEL = "claude-sonnet-5-5"              # the defaults; .env changes them with no code change (settings())
OPENAI_MODEL = "gpt-6.1-terra"
EFFORT = "low"
PROVIDERS_ENV = "TRANSLATE_PROVIDERS"    # the order of the chain, e.g. "anthropic,openai" or "openai"
DEFAULT_ORDER = "openai,anthropic"       # the owner, 2026-11-18: gpt-6.1-terra first, Claude the fallback (was
                                         # "anthropic,openai" while OpenAI had no credits)
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
# a garment title's size run ("55 66 77", "90 95 100"): the category brief keeps sizes out of the English title, so
# its numbers need not survive (knit cardigans 50002797, the owner 2026-11-19); a fibre's share ("100%") is no size
TITLE_SIZES = {"50002797": re.compile(r"(?<![\d.A-Za-z])(?:44|55|66|77|88|99|85|90|95|100|105|110)(?![\d.%])")}
TITLE_SIZES["50002798"] = TITLE_SIZES["50002797"]           # women's windbreakers: the same garment sizes (2026-11-20)
TITLE_SIZES["50002796"] = TITLE_SIZES["50002797"]           # women's long-sleeve tops: the same sizes (2026-11-21)
TITLE_SIZES["50002799"] = TITLE_SIZES["50002797"]           # 재킷, the same section (2026-11-21)
TITLE_SIZES["50002816"] = TITLE_SIZES["50002797"]           # rainwear: the garment sizes (2026-11-24)
# skirts: the women's sizes and the waists in inches and cm a title may list ("25 26 27 28", "64 67 70"; 2026-11-22)
TITLE_SIZES["50002802"] = re.compile(r"(?<![\d.A-Za-z])(?:44|55|66|77|88|99|2[3-9]|3[0-4]|6[1-9]|7[0-9])(?![\d.%])")
# golf pants: the women's sizes, the waists in inches (23-48) and in cm (61-112) a title may list ("28 30 32", "76 79
# 82"; 2026-11-23); a big-size run reaches 46 (2026-11-24, 5093872434: "30-46size" failed "missing 46")
TITLE_SIZES["50002801"] = re.compile(
    r"(?<![\d.A-Za-z])(?:44|55|66|77|88|99|2[3-9]|3[0-9]|4[0-8]|6[1-9]|[7-9][0-9]|10[0-9]|11[0-2])(?![\d.%])")
# a pants title's size run as one word, "30-46size", "34사이즈", "42까지" (2026-11-24, 5093872434: "codes lost: missing
# 46SIZE"): left out whole, its numbers and the glued SIZE
TITLE_SIZE_RUN = {"50002801": re.compile(
    r"(?<![\d.A-Za-z])\d{2,3}(?:\s*[-~]\s*\d{2,3})?\s*(?:size|사이즈|까지)(?![A-Za-z])", re.I)}
# a garment title's season code ("26FW", "2025 SS", "23F/W"): the briefs leave the season out of the English title, so
# its digits need not survive either (2026-11-20, the windbreaker pilot: "TaylorMade 26FW Women's ..." kept it only
# because a lost number fails the check); the same apparel categories as TITLE_SIZES
# ... and "N pcs 택1": the unit rule (sanitize) writes 종 as pcs before this reads the title (2026-11-22, the men's tops
# pilot: "[울시] ... 2종 택1" reached the model as "2 pcs 택1", its digits not freed: "2 pcs, Choose 1")
# ... and "2스타일" (2026-11-24, 12534121142: "[김영주골프] ... 2스타일 ... KPFMSL17" went out as "... KPFMSL17 2 Styles")
TITLE_PICK = re.compile(r"(?<!\d)\d\s*\+\s*\d(?!\d)|\d{1,2}\s*(?:종|컬러|가지|스타일|color|colors|styles?)(?:\s*(?:중\s*)?택\s*\d)?"
                        r"|\d{1,2}\s*pcs\s*(?:중\s*)?택\s*\d", re.I)
TITLE_SIZE_LETTERS = re.compile(r"(?<![A-Za-z\d])(XXS|2XS|XS|XL|XXL|2XL|XXXL|3XL|4XL|FREE)(?![A-Za-z\d])", re.I)
# ... and "2026년 SS시즌" (2026-11-24, 10160025240: went out as "Volvik Golfwear 2026 SS Men's ...")
TITLE_SEASON = re.compile(r"(?<![A-Za-z\d])(\d{2}|\d{4})\s?(?:년\s?)?(?:FW|SS|F/W|S/S|AW)(?:\s?시즌)?(?![A-Za-z])", re.I)
# ... and a garment's model year ("2024년 모델", "2025년형", "2024 모델": 2026-11-24, the rainwear pilot, Titleist
# 10311872120 "... 상하세트 2024년 모델" failed "numbers changed: missing 2024" while the brief leaves the year out)
# ... and a bare season word with no year ("아디다스 FW 겨울 ...", "아디다스 SS 여름 ...": 2026-11-25, six adidas titles
# failed "codes lost: missing FW" while the brief leaves the season out)
TITLE_SEASON_WORD = re.compile(r"(?<![A-Za-z\d/])(FW|SS|F/W|S/S)(?![A-Za-z\d/])", re.I)
TITLE_MODEL_YEAR = re.compile(r"(?<![A-Za-z\d])20\d{2}\s?(?:년\s?(?:형|모델|식)?|모델)(?![A-Za-z\d])")
# a seller's promotion word in a garment title (2026-11-24, 5489884876: "마스터베어 인기 BEST 골프팬츠" went out as
# "MASTER BEAR BEST Golf Pants"): left out, and its English taken out of the answer
TITLE_PROMO = re.compile(r"(?<![A-Za-z가-힣])(?:인기|BEST|베스트)(?![A-Za-z가-힣])", re.I)
TITLE_PROMO_EN = r"Best[- ]?Sellers?|Best|Popular"
# The English words a garment title's answer loses whatever the model wrote (strip, verify): the briefs leave them
# out and the model kept them (the golf pants pilot review, 2026-11-24). A Korean word -> its English.
# - a word of one variant (pants, 50002801): 9부 where 롱 is sold too (6384912528: "9-Length Cropped" over 8 cuts),
#   숏 (5746242591: "VT Short Inseam" over 숏 and 롱), an optional fleece or cargo (10997837767 기모 추가: 기모없음 /
#   기모추가; 5990911618 원단: 기본 / 기모 / 카고 went out as "Fleece-Lined Cargo"): an option axis with a value that
#   has it and one that has not ("기모없음" has not)
# - a fit word on a listing of styles none of which says it (5979440160: "레귤러핏" over 26 S/S 골프바지 / 기모골프바지,
#   the fleece style slim): an option axis whose every value names a garment (바지, 팬츠)
PANTS_VARIANT_WORDS = (
    ("기모", r"Fleece[- ]Lined|Brushed[- ]Fleece|Brushed|Fleece"),
    ("카고", r"Cargo"),
    ("9부", r"9[- ]?(?:/\s?10[- ]?)?Length|9/10|Ankle[- ]Length|Cropped"),
    ("7부", r"7[- ]?(?:/\s?10[- ]?)?Length|7/10|Capri|Cropped"),
    ("롱", r"Long(?:[- ](?:Inseam|Length))?|Full[- ]Length"),
    ("숏", r"Short(?:[- ](?:Inseam|Length))?"),
    ("레귤러핏", r"Regular[- ]Fit"),
    ("슬림핏", r"Slim[- ]Fit|Slim"),
    ("일자", r"Straight[- ](?:Leg|Fit)|Straight"),
    ("부츠컷", r"Boot[- ]?Cut"),
)
PANTS_FIT_WORDS = ("레귤러핏", "슬림핏", "일자", "부츠컷")
_GARMENT = re.compile(r"바지|팬츠|슬랙스|조거")
_NO_WORD = r"\s*(?:없음|없는|X(?![A-Za-z])|미포함|안함|제외)"
# 와이드 밴딩 is a wide waistband, a wide leg only beside the garment or a fit (2026-11-24, 6689446962: "와이드 밴딩 ...
# 일자" went out as "Wide-Leg", the 하의핏 row 슬림핏)
_WIDE_BAND = re.compile(r"와이드\s*밴딩")
_WIDE_LEG = re.compile(r"와이드\s*(?:팬츠|바지|슬랙스|핏|레그|부츠컷)|세미\s*와이드")
# cotton in a title the material row does not list (2026-11-24, 8269563762: "나이키 골프 바지 면 배기", 소재 폴리에스테르,
# 나일론, 기타, went out as "Nike Men's Cotton ...")
_COTTON = re.compile(r"(?<![가-힣])(?:면|코튼)(?=\s|$|바지|팬츠|소재|\d)")
_COTTON_ROW = re.compile(r"면|코튼|cotton", re.I)
# a model code like the ones the options carry, which no option value carries (2026-11-24, 8772595840: "HG1712 HG1713
# HG1715" in the title, the colours HG1713 / HG1715 only)
_MODEL_CODE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,4})\d{3,}[A-Za-z0-9]*(?![A-Za-z0-9])")
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
                # are output tokens, and a translation gains little from them (measured 2026-11-08, see TRANSLATION.md)
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
    order = [p.strip().lower() for p in (env.get(PROVIDERS_ENV) or DEFAULT_ORDER).split(",") if p.strip()]
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


def _brand_en(prepared: dict[str, Any], dicts: Dictionaries, tenant: str) -> str:
    """The English the store shows as this product's vendor: its brand text's dictionary spelling (a Latin name as it
    is), the shop's own name when it has none."""
    for t in prepared.get("texts") or []:
        if t["kind"] == "brand":
            source = sanitize("brand", t["ko"], tenant)
            return dicts.get("brand", t["ko"]) or ("" if has_hangul(source) else dicts.brand_spelling(source))
    return tenant


def _stale_lead(english: str, vendor: str, dicts: Dictionaries) -> str | None:
    """The dictionary brand an English title starts with when it is not the product's vendor (`vendor`): the title
    was written under another brand. 2026-11-19, the two-brand scan: titles the model wrote before 2026-11-15 carry no
    brand_ko, so a brand change never asked them again: "Pongdang Swim Kids' …" under Inparo (the vendor in front:
    "Inparo Pongdang Swim …"), "PING Women's Junior …" (핑크, pink) under no brand; 98 live titles held two brands.
    None when the title starts with the vendor, the vendor is a longer name of it or it of the vendor (Maruman
    Majesty; Majesty Maruman), or the vendor is unknown."""
    if not vendor or not english:
        return None
    low, own = english.lower(), vendor.lower()
    if low.startswith(own):
        return None
    for b in sorted((v for v in dicts.vendors() if len(v) >= 3), key=len, reverse=True):
        bl = b.lower()
        if low.startswith(bl) and (len(low) == len(bl) or not low[len(bl)].isalnum()):
            return None if same_brand_line(b, vendor) else b
    return None


def same_brand_line(brand: str, vendor: str) -> bool:
    """`brand` is the vendor, a longer name of it or it of the vendor (Maruman Majesty; Majesty Maruman), compared
    without case: not another brand (_stale_lead; sweep.py's brand checks, 2026-11-19)."""
    b, v = brand.lower(), vendor.lower()
    return bool(b) and bool(v) and (v.startswith(b) or b.startswith(v))


def _say(item: dict[str, Any], text: str) -> None:
    item["context"] = "; ".join([*([item["context"]] if item.get("context") else []), text])


def _has_word(value: str, word: str) -> bool:
    """`value` says `word`, not its absence ("기모없음", "기모 X", "노기모")."""
    w = re.escape(word)
    return word in value and not re.search(w + _NO_WORD, value) and not re.search(r"(?:노|무)" + w, value)


def one_variant_word(word: str, options: list[dict[str, Any]], fit: bool = False) -> bool:
    """`word` of a pants title is one variant's: an option axis has a value that says it and one that does not; a fit
    word (`fit`) also when an axis lists styles (every value a garment: "26 S/S 골프바지 / 기모골프바지") not all of
    which say it."""
    for o in options:
        values = o.get("values_ko") or []
        said = [_has_word(v, word) for v in values]
        if any(said) and not all(said):
            return True
        if fit and len(values) >= 2 and all(_GARMENT.search(v) for v in values) and not all(said):
            return True
    return False


def garment_title(item: dict[str, Any], category: str, product: dict[str, Any], seasons: list[str]) -> None:
    """A garment title's words the English must not keep (the golf pants pilot review, 2026-11-24): each is told to
    the model (context), freed from the number / code check (drop) and taken out of the answer (strip, verify), as
    the model kept them though the briefs leave them out. Every TITLE_SIZES category: the season code's letters
    ("... Golf Pants FW", 7221598523), a promotion word (인기 / BEST), a choice count's English ("2 Styles"), a model
    code no option value carries where the values carry its siblings. Pants (50002801): a word of one variant
    (PANTS_VARIANT_WORDS), 와이드 밴딩 as a wide leg, cotton the material row does not list."""
    source = item["source"]
    options = product.get("options") or []
    strip: list[str] = []
    drop: list[str] = []
    letters = {re.sub(r"[^A-Z]", "", s.upper()) for s in seasons}            # "2026년 SS시즌" -> SS, "23F/W" -> FW
    kinds = [p for k, p in (("FW", "F/?W"), ("SS", "S/?S"), ("AW", "A/?W")) if k in letters]
    if kinds:                                       # "... Golf Pants FW", "2026 SS Men's ...": the code, its year
        strip.append(r"(?:(?:\d{2}|\d{4})\s?)?(?:" + "|".join(kinds) + r")(?:\s?Season)?")
    promo = TITLE_PROMO.findall(source)
    if promo:
        drop += promo
        strip.append(TITLE_PROMO_EN)
        _say(item, " / ".join(promo) + " is the seller's promotion: leave it out of the title")
    if item.get("pick"):
        strip.append(r"\d{1,2}[- ]?(?:Styles?|Types?|Colou?rs?|Kinds?)")
    value_codes = codes(" ".join(v for o in options for v in o.get("values_ko") or []))
    found = [(m.group(0), m.group(1).upper()) for m in _MODEL_CODE.finditer(source)]
    carried = {p for c, p in found if c.upper() in value_codes}
    gone = [c for c, p in found if p in carried and c.upper() not in value_codes]
    if gone:
        drop += gone
        strip += [re.escape(c) for c in gone]
        _say(item, "model codes no option sells: " + ", ".join(gone) + ": leave them out of the title")
    if category == "50002801":
        words = [(ko, en) for ko, en in PANTS_VARIANT_WORDS
                 if ko in source and one_variant_word(ko, options, ko in PANTS_FIT_WORDS)]
        if words:
            strip += [en for _, en in words]
            drop += [ko for ko, _ in words if re.search(r"\d", ko)]
            _say(item, "only some variants are " + ", ".join(ko for ko, _ in words) + " (the options sell the others): "
                 "leave them out of the title")
        if _WIDE_BAND.search(source) and not _WIDE_LEG.search(source):
            strip.append(r"Wide[- ]Leg(?:ged)?")
            _say(item, "와이드 밴딩 is a wide waistband, not a wide leg")
        rows = product.get("composition_ko") or []
        if _COTTON.search(source) and rows and not any(_COTTON_ROW.search(str(r.get("value_ko") or "")) for r in rows):
            strip.append(r"Cotton")
            _say(item, "the material row lists no cotton (면): leave cotton out of the title")
    if drop:
        item["drop"] = [*(item.get("drop") or []), *drop]
    if strip:
        item["strip"] = [*(item.get("strip") or []), *strip]


def strip_words(text: str, patterns: list[str]) -> str:
    """`text` without the whole words `patterns` match (case aside), its spaces and commas tidied; a joining word
    beside one goes with it ("Straight-Leg and Bootcut", both one variant's, 5367746327: not "Elastic-Waist and Golf
    Pants"), one of two kept ("A and B and C" -> "A and C")."""
    join = r"(?:and|or|&|/)"
    for p in patterns:
        text = re.sub(r"(?P<pre>\s+" + join + r")?(?:^|\s+)(?<![\w/'-])(?:" + p + r")(?![\w/-])(?P<post>\s+" + join
                      + r"(?=\s))?", lambda m: (m.group("pre") or "") + " " if m.group("pre") and m.group("post")
                      else " ", " " + text, flags=re.I)
    text = re.sub(r",\s*,", ",", re.sub(r"\s+", " ", text))
    return re.sub(r"\s+([,)])", r"\1", text).replace("()", "").strip(" ,-/")


def plan(prepared: dict[str, Any], dicts: Dictionaries, store: dict[tuple[str, str], str],
         tenant: str, brands: dict[tuple[str, str], str] | None = None, reask: bool = False,
         fixed: Collection[tuple[str, str]] = (), context: str | None = None
         ) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    """-> (English by text id, where each came from, the items the model must translate). A title the model
    translated under another brand than the product's now (`brands`: the brand_ko a title row was asked with) is
    asked again, its old English kept until an answer comes (2026-11-15: Generic -> Bermuda, Edis -> Majek, PRECISE ->
    XINGGM kept the old brand at the head of the title; a row without a brand, a hand correction, is never asked
    again). `reask` (translate.py --reask, 2026-11-17, the wedge-set review W10: 75 live titles kept the English
    asked before the notes title_lofts_not_sold / title_cut / title_word_unproven existed): the product's own title
    and placeholder option names are asked again with today's notes, the old English kept until a checked answer
    comes; a hand correction (`fixed`: its last row written by a review) is never asked again. `context`
    (translate.py --reask --context, 2026-11-19, sweep's title.set_single: 92 live titles promising a set where one
    club is sold): with `reask`, added to each re-asked title item's context, after any note's."""
    key = prepared["key"]
    product = prepared.get("product") or {}
    placeholders = _placeholders(prepared)
    category = (prepared.get("source") or {}).get("category_id")
    one_variant = [w.strip() for n in prepared.get("notes") or []                # the transform joins spans with ", "
                   if isinstance(n, dict) and n.get("code") == "title_names_one_variant" and n.get("detail")
                   for w in str(n["detail"]).split(", ") if w.strip()]
    lofts_not_sold = next((str(n["detail"]) for n in prepared.get("notes") or []
                           if isinstance(n, dict) and n.get("code") == "title_lofts_not_sold" and n.get("detail")), None)
    cut = next((str(n["detail"]).split(" cut,")[0] for n in prepared.get("notes") or []
                if isinstance(n, dict) and n.get("code") == "title_cut" and n.get("detail")), None)
    unproven = [w.strip() for n in prepared.get("notes") or []
                if isinstance(n, dict) and n.get("code") == "title_word_unproven" and n.get("detail")
                for w in str(n["detail"]).split(", ") if w.strip()]
    options = product.get("options") or []
    option_of = {v: o["name_ko"] for o in options for v in o["values_ko"]}
    values_of = {o["name_ko"]: o["values_ko"] for o in options}
    en: dict[str, str] = {}
    by: dict[str, str] = {}
    pending: list[dict[str, Any]] = []
    # a title is asked again for its new brand only once the brand has its English (13625754692: 디맥스프로 not
    # translated yet; the title would be asked with no brand_en, 2026-11-17)
    brand_known = all(dicts.get("brand", t["ko"]) is not None or not has_hangul(sanitize("brand", t["ko"], tenant))
                      for t in prepared.get("texts") or [] if t["kind"] == "brand")
    for t in prepared.get("texts") or []:
        tid, kind, ko = t["id"], t["kind"], t["ko"]
        own = kind in PRODUCT_KINDS or (kind == "option_name" and ko in placeholders)
        # a value this product had to tell apart from another (a collision's answer, below) is the product's own
        local = None if own else store.get((key, tid))
        own = own or local is not None
        hit = store.get((key, tid)) if own else dicts.get(kind, ko, category)
        if hit is None and kind in ("spec_value", "fact_value"):
            hit = dicts.get("brand", ko)                 # a 브랜드 / 제조사 row: the shop's vendor spelling
        again = reask and own and kind in ("title", "option_name") and (key, tid) not in fixed
        if hit is not None:
            en[tid], by[tid] = hit, "product" if own else "dictionary"
        if hit is not None and not again:
            asked_with = (brands or {}).get((key, tid))
            if kind == "title" and asked_with is not None and asked_with != (product.get("brand_ko") or "") \
                    and brand_known:
                pending.append({"id": tid, "kind": kind, "source": sanitize(kind, ko, tenant, category),
                                "context": f"the brand is now {product.get('brand_ko')}, not {asked_with}"})
            elif kind == "title" and asked_with is None and (key, tid) not in fixed and brand_known:
                stale = _stale_lead(hit, _brand_en(prepared, dicts, tenant), dicts)
                if stale:
                    pending.append({"id": tid, "kind": kind, "source": sanitize(kind, ko, tenant, category),
                                    "context": f"the brand is now {product.get('brand_ko') or 'none'}; the title "
                                               f"was written as {stale}'s: name {stale} only if this Korean title "
                                               "names it"})
            continue
        source = sanitize(kind, ko, tenant, category)
        if not has_hangul(source):
            if hit is None:                                # a re-asked name keeps its English until an answer
                # a Latin brand takes the brand dictionary's spelling, compared without case or spaces (2026-11-24,
                # 5489884876: specs:브랜드 "MASTER BEAR" for 마스터베어 -> Master Bear, as _brand_en spells it)
                en[tid], by[tid] = (dicts.brand_spelling(source) if kind == "brand" else source), "rule"
            if kind == "option_name" and ko in placeholders:
                # a Latin placeholder name ("Color" over "52 56 Degree Tarnish", Amazon imports; 2026-11-17, the
                # wedge-set review C50: 21 axes, 18 of them not colours): the model names it from its values, the
                # rule's English kept until it answers. Never named by a rule: "Lofts" would rename heights (50002787)
                pending.append({"id": tid, "kind": kind, "source": source, "placeholder": True,
                                "context": "values: " + " | ".join(values_of.get(ko, [])[:12])})
            continue
        item: dict[str, Any] = {"id": tid, "kind": kind, "source": source}
        if kind == "title" and one_variant:
            # the transform's note title_names_one_variant: words only some variants are (the title keeps to what
            # every variant is); the check does not ask for their numbers / codes
            item["context"] = "drop from the title, only some variants have it: " + " | ".join(one_variant)
            item["drop"] = [sanitize("title", w, tenant, category) for w in one_variant]
        if kind == "title" and (lofts_not_sold or cut):
            # the transform's notes title_lofts_not_sold (C46) and title_cut (C48), 2026-11-17: the wedge title's
            # lofts no set sold has, a list Naver cut at 50 characters; their numbers / the cut word need not survive
            said = [item["context"]] if item.get("context") else []
            if lofts_not_sold:
                said.append(f"lofts the title lists that are not one set sold: {lofts_not_sold}; write only the "
                            "lofts of a set sold (several sets joined by 'or'), never the list as one set")
                item["free_numbers"] = re.findall(r"\d+", lofts_not_sold.split(" (sold:")[0])
            if cut:
                said.append("Naver cut this title at 50 characters: its loft list may be incomplete; write no "
                            "piece count it does not state" + (f"; {cut} at its end is a cut word: leave it out"
                                                               if cut != "''" else ""))
                if cut != "''":
                    item["cut"] = sanitize("title", cut.strip("'"), tenant, category)
            item["context"] = "; ".join(said)
        if kind == "title" and unproven:
            # the transform's note title_word_unproven (C67, 2026-11-17): 단조 the seller writes on every title, its
            # page never saying the club is forged; the model sees the title only, so the note tells it
            said = [item["context"]] if item.get("context") else []
            said.append(" / ".join(unproven) + " (forged): the seller writes it on its titles and nothing on "
                        "this product's page says forged: leave it out of the title")
            item["context"] = "; ".join(said)
            item["drop"] = (item.get("drop") or []) + [sanitize("title", w, tenant, category) for w in unproven]
        if kind == "title" and str(category) in TITLE_SIZES:
            sizes = TITLE_SIZES[str(category)].findall(item["source"])
            if sizes:
                item["free_numbers"] = [*(item.get("free_numbers") or []), *sizes]
            # a size letter standing alone ("스판 주름 XL 골프치마", 5527933102, 2026-11-22: "codes lost: missing XL"): the
            # briefs leave every size out of a title, so it need not survive either
            letters = TITLE_SIZE_LETTERS.findall(item["source"])
            if letters:
                item["free_codes"] = [*(item.get("free_codes") or []), *(x.upper() for x in letters)]
                # ... and the count of "3XL" / "2XS" (2026-11-24, 9232590815: "... 연습복 3XL" failed "numbers changed:
                # missing 3" while the English rightly left the size out)
                counts = [x[0] for x in letters if x[0].isdigit()]
                if counts:
                    item["free_numbers"] = [*(item.get("free_numbers") or []), *counts]
            # a season code may go whole, its letters too: "22ss", "23FW" failed "codes lost" (the second
            # windbreaker pilot 2026-11-21, 7114115147, 11092759396) while only its digits were freed
            season_codes = [m.group(0) for m in TITLE_SEASON.finditer(item["source"])]
            seasons = list(season_codes) + [m.group(0) for m in TITLE_MODEL_YEAR.finditer(item["source"])]
            bare = [m.group(1).upper() for m in TITLE_SEASON_WORD.finditer(item["source"])]
            if bare:
                item["free_codes"] = [*(item.get("free_codes") or []), *bare, *(b.replace("/", "") for b in bare)]
            # "1+1" (a 2-Pack) and a choice count ("3종 택1", "6컬러"): the brief says them otherwise or leaves them out
            # (2026-11-21, the tops pilot: "... 1+1", "Choose 1 of 3 pcs" kept to keep their digits)
            seasons += [m.group(0) for m in TITLE_PICK.finditer(item["source"])]
            run = TITLE_SIZE_RUN.get(str(category))
            seasons += run.findall(item["source"]) if run else []
            if any(not re.search(r"\+", m.group(0)) for m in TITLE_PICK.finditer(item["source"])):
                item["pick"] = True                 # a choice of styles: never "pcs" in English (verify)
            if seasons:
                item["drop"] = [*(item.get("drop") or []), *seasons]
            garment_title(item, str(category), product, season_codes)
        if kind == "title" and again and context:
            item["context"] = "; ".join([*([item["context"]] if item.get("context") else []), context])
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
                                "context": "must differ from: " + ", ".join(english[x] for x in same if x != tid),
                                "differ": True})
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


_PICK_EN = re.compile(r"(?i)\b\d+\s*(?:pcs?|pieces?)\b|\bpcs\b|\bchoose\s+(?:1|one)\b")


def _checked_source(item: dict[str, Any]) -> str:
    """The part of the source whose numbers and codes must survive: a title's [bracketed] shop tags ([1년AS],
    [오늘출고]) and its Korean distributor ("던롭스포츠코리아100%", "삼양인터내셔날") may be dropped, as the system prompt
    asks."""
    if item.get("placeholder"):
        return ""                                # renamed from its values: nothing of "선택2" must survive
    if item["kind"] != "title":
        return item["source"]
    text = _BRACKETS_RE.sub(" ", item["source"])
    if item.get("cut"):                             # Naver's cut word, at the end only (C48)
        text = re.sub(r"\s*" + re.escape(item["cut"]) + r"\s*$", " ", text)
    # spacing aside: the note joins "13 PCS" as "13PCS" (C47); the longest first, so a word inside another does not
    # break it (2026-11-24, 7221598523: the note's "25" went before "25 FW" and left "codes lost: missing FW";
    # 5093872434: "30" before "30-46size" left 46SIZE)
    for word in sorted(item.get("drop") or [], key=lambda w: -len("".join(w.split()))):
        bare = "".join(word.split())
        if bare:
            text = re.sub(r"\s*".join(map(re.escape, bare)), " ", text)
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
        if out and item.get("strip"):                   # a garment title's words the briefs leave out (garment_title)
            out = strip_words(out, item["strip"])
        if not out:
            problems.append("empty")
        if has_hangul(out):
            problems.append("korean left")
        checked = _checked_source(item)
        lost = [n for n in numbers(checked) if n not in out and n not in (item.get("free_numbers") or ())]
        if lost:
            problems.append("numbers changed: missing " + ", ".join(lost))
        if item.get("pick") and _PICK_EN.search(out):
            # 2026-11-22, the men's tops pilot: "[울시] ... 2종 택1" (one knit, a choice of 2) went out as "... 2 pcs,
            # Choose 1" and "Choose 1 of 4 pcs" though the brief says leave the choice out: it reads as a bundle
            problems.append("a choice of styles (N종 택1) is no pack: leave it out of the title, no pcs / Choose")
        lost_codes = sorted(c for c in codes(checked) if c not in out.upper() and c not in (item.get("free_codes") or ()))
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
                      tenant: str, model: "Model | Chain | None", now: str,
                      brands: dict[tuple[str, str], str] | None = None, reask: bool = False,
                      fixed: Collection[tuple[str, str]] = (), context: str | None = None) -> Outcome:
    key = prepared["key"]
    record: dict[str, Any] = {"format": FORMAT, "key": key, "en": {}, "by": {}, "problems": [], "provider": None}
    usage: dict[str, dict[str, int]] = {}
    if prepared.get("status") != "ready":
        return Outcome({**record, "status": "held"}, [], usage, 0)
    en, by, pending = plan(prepared, dicts, store, tenant, brands, reask and model is not None, fixed, context)
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
    # a collision's answer stays with the product (2026-11-24: 엔조이핏 10107163054 sells 차콜 and 먹색, both
    # "Charcoal"; the re-ask's "Charcoal Gray" went into the category dictionary and renamed 차콜 in 6+ live products)
    differ = {i["id"] for i in pending if i.get("differ")}
    for t in prepared.get("texts") or []:
        if by.get(t["id"]) != "model":
            continue
        if t["kind"] in PRODUCT_KINDS or (t["kind"] == "option_name" and t["ko"] in placeholders) \
                or t["id"] in differ:
            store[(key, t["id"])] = en[t["id"]]
            row = {"key": key, "id": t["id"], "kind": t["kind"], "ko": t["ko"], "en": en[t["id"]],
                   "by": model_of.get(t["id"]), "at": now}
            if t["kind"] == "title":                  # the brand the title was translated under (plan, brands)
                row["brand_ko"] = (prepared.get("product") or {}).get("brand_ko") or ""
                if brands is not None:
                    brands[(key, t["id"])] = row["brand_ko"]
            new_texts.append(row)
        else:
            dicts.add(t["kind"], t["ko"], en[t["id"]], (prepared.get("source") or {}).get("category_id"))
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

def _load_brands(path: str, tenant: str | None = None) -> dict[tuple[str, str], str]:
    """(key, title id) -> the brand_ko its last row was translated under; a row without one (older, or a hand
    correction) drops it: never asked again for its brand. An older row the model wrote (no "review" writer) that
    starts with the shop's own name (`tenant`) was translated as 노브랜드 (2026-11-17, the wedge-set review C06:
    "Fairward Golf …" kept at the head of 25 titles whose products have a brand now: PGM, 69 Golf, Vice Golf …)."""
    brands: dict[tuple[str, str], str] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("kind") == "title":
                        if "brand_ko" in row:
                            brands[(row["key"], row["id"])] = row["brand_ko"]
                        elif tenant and not str(row.get("by") or "").startswith("review") \
                                and str(row.get("en") or "").startswith(tenant):
                            brands[(row["key"], row["id"])] = NO_BRAND
                        else:
                            brands.pop((row["key"], row["id"]), None)
                except (ValueError, KeyError, TypeError):
                    continue
    return brands


def _load_fixed(path: str) -> set[tuple[str, str]]:
    """(key, text id) whose last row a review wrote (a hand correction, by "review-..."): never asked again."""
    fixed: set[tuple[str, str]] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    (fixed.add if str(row.get("by") or "").startswith("review") else fixed.discard)(
                        (row["key"], row["id"]))
                except (ValueError, KeyError, TypeError):
                    continue
    return fixed


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
        only: str | Collection[str] | None = None, limit: int | None = None,
        clock: Any = time.gmtime, reask: bool = False, context: str | None = None) -> dict[str, Any]:
    """`only`: the key (or keys) the model may be asked for; the other products are resolved from what is kept.
    `reask`: their own titles and placeholder names asked again (plan); only with `only`. `context`: added to each
    re-asked title's context (plan); only with `reask`."""
    if context is not None and (not reask or not context.strip()):
        raise TranslateError("--context goes with --reask (and the products named), and says something")
    context = context.strip() if context is not None else None
    if reask and not only:
        raise TranslateError("--reask needs the products named (--only, --keys-file, --job)")
    wanted = {only} if isinstance(only, str) else set(only or ())
    tenant = shop_stores.STORES[shop_stores.StoreId(shop)].publisher
    dicts = dicts or Dictionaries()
    with open(os.path.join(shops_root, shop, "prepared", "products.jsonl"), encoding="utf-8") as f:
        prepared = [json.loads(x) for x in f if x.strip()]
    out_dir = os.path.join(shops_root, shop, "translation")
    os.makedirs(out_dir, exist_ok=True)
    texts_path = os.path.join(out_dir, "texts.jsonl")
    store = _load_store(texts_path)
    brands = _load_brands(texts_path, tenant)
    fixed = _load_fixed(texts_path)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", clock())
    records: list[dict[str, Any]] = []
    usage: dict[str, dict[str, int]] = {}
    calls = asked = 0
    for p in sorted(prepared, key=lambda x: x["key"]):
        use = model
        if (wanted and p["key"] not in wanted) or (limit is not None and asked >= limit):
            use = None                                   # resolved from what is kept, not sent
        outcome = translate_product(p, dicts, store, tenant, use, now, brands, reask and use is not None, fixed,
                                    context)
        if outcome.calls:
            asked += 1
        records.append(outcome.record)
        calls += outcome.calls
        for name, u in outcome.usage.items():
            mine = usage.setdefault(name, {})
            for k, v in u.items():
                mine[k] = mine.get(k, 0) + v
        if outcome.new_texts:
            append_line(texts_path, *(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in outcome.new_texts))
        dicts.save()                                     # after each product: a stopped run keeps its answers
    write_atomic(os.path.join(out_dir, "translated.jsonl"),        # a reader never sees half (shop_files)
                 "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records))
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
             f"  new dictionary entries: " + (", ".join(f"{k} {len(v)}" for k, v in dicts.all_added().items())
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
    p.add_argument("--only", help="send only this product to the model (its key, Naver product id, handle or link)")
    p.add_argument("--limit", type=int, help="send at most N products to the model")
    p.add_argument("--reask", action="store_true",
                   help="ask the named products' own titles and placeholder option names again with today's notes "
                        "(the old English kept until a checked answer; hand corrections never)")
    p.add_argument("--context", help="with --reask: a text added to each re-asked title's context (joined with any "
                                     "note's), e.g. \"only one club is sold, the buyer picks its type: do not call it "
                                     "a set\"")
    add_ref_flags(p)
    args = p.parse_args(argv)
    if args.context is not None and (not args.reask or not args.context.strip()):
        p.error("--context goes with --reask (and the products named), and says something")
    only: list[str] | None = None
    if args.only or selection_asked(args):            # refs -> keys (a full key as it is, as before)
        only = keys_from_args(p, args, args.shop, [args.only] if args.only else [], args.shops_root)

    def body() -> int:
        try:
            model = None if args.offline else build_chain(keys_from_env())
            print("\n".join(run(args.shop, model, args.shops_root, only=only, limit=args.limit,
                                      reask=args.reask, context=args.context)["report"]))
        except TranslateError as e:
            print(f"translate: {e}", file=sys.stderr)
            return 2
        return 0
    # --offline too: it rewrites translated.jsonl and saves the dictionaries (a job's fresh product dropped otherwise)
    return locked(args.shops_root, args.shop, "translate.py", body, "translate")


if __name__ == "__main__":
    sys.exit(main())
