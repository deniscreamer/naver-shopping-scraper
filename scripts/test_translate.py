"""Offline tests of the translation stage: the rules (units, 노브랜드), the dictionaries (live / backup), the resolution
on real fixture products, the model's answer checked and fixed in the same conversation (a fake model: no key, no
network), the files, the key file and the Anthropic request.

    .venv/bin/python -m pytest scripts/test_translate.py -q
"""
import json
from datetime import datetime, timezone
import os
import re
from types import SimpleNamespace

import pytest

import translate as T
import translation_dicts as D
from translation_rules import codes, has_hangul, numbers, sanitize
from transform import prepare, text_id
from transform_shops import rules_for

HERE = os.path.dirname(os.path.abspath(__file__))
FX = os.path.join(HERE, "fixtures")
TENANT = "Fairward Golf"


# ---- rules ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("kind, ko, out", [
    ("spec_value", "10.5도", "10.5°"),
    ("spec_value", "9도, 10.5도", "9°, 10.5°"),
    ("option_value", "9도SR 스틸R", "9° SR 스틸R"),              # partly converted: the model does the rest
    ("addon_name", "83.82cm (33인치)", "83.82 cm (33 in)"),
    ("option_value", "22호", "Size 22"),
    ("text_label", "장갑사이즈(22~25호)", "장갑사이즈(Size 22–25)"),
    ("addon_name", "3번SR", "#3 SR"),
    ("option_value", "3번(15.5도)-L", "#3 (15.5°)-L"),
    ("spec_value", "7개", "7"),                                    # the whole text: the count
    ("fact_value", "11.5도 A 2개", "11.5° A 2 pcs"),
    ("option_value", "12종", "12 pcs"),
    ("spec_value", "2026년형", "2026"),                                 # the whole value: the year
    ("title", "캘러웨이 2026년형 풀세트", "캘러웨이 2026 model 풀세트"),
    ("brand", "노브랜드", TENANT),                                 # the whole text: the tenant's name
    ("spec_value", "노브랜드", TENANT),
    ("title", "노브랜드 실내 골프채", "실내 골프채"),               # inside a text: removed
    ("option_name", "샤프트강도", "샤프트강도"),                    # 강도 is not a degree: no number before it
    ("text_label", "제주도 배송", "제주도 배송"),
    ("title", "골프샵 1호점 특가", "골프샵 1호점 특가"),           # 호 before another syllable: not a size
    ("option_value", "4번유틸", "4번유틸"),
    ("review", "3번 썼는데 10도 좋아요", "3번 썼는데 10도 좋아요"),  # reviews are left as written
])
def test_rules(kind, ko, out):
    assert sanitize(kind, ko, TENANT) == out


@pytest.mark.parametrize("ko, out", [
    ("10.5R유틸4번R8아이언R퍼터", "10.5R, 유틸#4 R, 8아이언R, 퍼터"),       # each flex letter stays with its club
    ("11.5L유틸4번L7아이언L퍼터", "11.5L, 유틸#4 L, 7아이언L, 퍼터"),
    ("9도SR유틸4번SR8아이언R퍼터", "9° SR, 유틸#4 SR, 8아이언R, 퍼터"),
    ("S200+33인치", "S200+33 in"),                                       # not a flex before a club
])
def test_golf_spec_runs_are_split(ko, out):
    assert sanitize("option_value", ko, TENANT, "50002788") == out


def test_rule_helpers():
    assert has_hangul("9° 스틸") and not has_hangul("9° Steel")
    assert numbers("레드 (L) 11.5 / 7i") == ["11.5", "7"]
    assert codes("피칭웨지(PW) G440 7i R pgm") == {"PW", "G440", "7I"}       # one letter and lower case words: not codes
    assert codes("XXIO 12") == {"XXIO"}


# ---- dictionaries ----------------------------------------------------------------------------------------------

def test_live_dictionaries_seed_from_the_backup_and_back_up(tmp_path):
    backup, live = str(tmp_path / "backup"), str(tmp_path / "live")
    D._write(os.path.join(backup, "brand.json"), "brand", {"캘러웨이": "Callaway"})
    d = D.Dictionaries(live, backup)
    assert d.get("brand", "캘러웨이") == "Callaway" and os.path.exists(os.path.join(live, "brand.json"))
    d.add("brand", "핑", "PING")
    d.add("spec_label", "브랜드", "Brand")
    d.save()
    again = D.Dictionaries(live, backup)                           # the live copy, not the backup, is read
    assert again.get("brand", "핑") == "PING" and again.vendors() == ["Callaway", "PING"]
    rows = {r["kind"]: r for r in D.status(live, backup)}
    assert rows["brand"]["new"] == {"핑": "PING"} and rows["spec_label"]["new"] == {"브랜드": "Brand"}
    assert set(D.backup(live, backup)) == {"brand", "spec_label"}
    assert all(not r["new"] and not r["changed"] for r in D.status(live, backup))
    with open(os.path.join(backup, "brand.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert data.pop("backed_up").endswith("Z")
    assert data == {"format": "dictionary/1", "kind": "brand", "entries": {"캘러웨이": "Callaway", "핑": "PING"}}


def test_a_broken_dictionary_stops(tmp_path):
    (tmp_path / "brand.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(D.DictionaryError):
        D.Dictionaries(str(tmp_path), str(tmp_path / "none"))


def test_the_backups_in_git_are_valid():
    for kind in D.KINDS:
        entries = D._read(os.path.join(D.BACKUP_ROOT, f"{kind}.json"), kind)
        assert all(not has_hangul(en) for en in entries.values()), kind


# ---- a fake model --------------------------------------------------------------------------------------------

def _fake_en(source: str) -> str:
    """An "English" that passes the checks: each Hangul syllable becomes a letter (distinct values stay distinct)."""
    return re.sub(r"[가-힣]", lambda m: "abcdefghijklmnopqrstuvwxyz"[ord(m.group()) % 26], source)


def answer(items, change=None):
    """The fake model's answer; `change` gets rows that also carry the item's kind ("_kind", not sent)."""
    rows = [{"id": i["id"], "en": _fake_en(i["source"]), "_kind": i["kind"]} for i in items]
    if change:
        rows = change(rows)
    return json.dumps({"items": [{k: v for k, v in r.items() if k != "_kind"} for r in rows]}, ensure_ascii=False)


class FakeModel:
    """Answers from a script: each step is a function of the items asked (from the last user message)."""

    def __init__(self, *steps, stop_reason="end_turn", name="fake"):
        self.name = name
        self.steps = list(steps) or [None]
        self.calls = []
        self.stop_reason = stop_reason

    def send(self, system, messages):
        self.calls.append([dict(m) for m in messages])
        last = messages[-1]["content"]
        if len(messages) == 1:
            asked = json.loads(last)["items"]
        else:
            failed = json.loads(last[last.rindex('{"failed"'):])["failed"]
            first = json.loads(messages[0]["content"])["items"]
            asked = [i for i in first if i["id"] in {f["id"] for f in failed}]
        step = self.steps[min(len(self.calls) - 1, len(self.steps) - 1)]
        text = step(asked) if callable(step) else answer(asked)
        return T.Reply([{"type": "text", "text": text}], text, self.stop_reason, {"input": 100, "output": 50})


def dicts(tmp_path, **entries):
    backup = tmp_path / "backup"
    for kind, e in entries.items():
        D._write(str(backup / f"{kind}.json"), kind, e)
    return D.Dictionaries(str(tmp_path / "live"), str(backup))


def small(options=None, title="캘러웨이 레바 여성 풀세트 10개 세트 2027", brand="캘러웨이", notes=()):
    product = {"title_ko": title, "brand_ko": brand, "options": options or [], "facts": [], "specs": [],
               "personalization": [], "addons": [], "reviews": []}
    texts = [("title", title), ("brand", brand)]
    for o in product["options"]:
        texts += [("option_name", o["name_ko"])] + [("option_value", v) for v in o["values_ko"]]
    return {"key": "fairwardgolf:naver:1:1", "status": "ready", "notes": [dict(n) for n in notes],
            "source": {"category_id": "50002788"}, "product": product,
            "texts": [{"id": text_id(k, v), "kind": k, "ko": v} for k, v in texts]}


# ---- resolution on real products -----------------------------------------------------------------------------

def fixture(name):
    with open(os.path.join(FX, "collected", name + ".json"), encoding="utf-8") as f:
        line = json.load(f)
    sidecar = os.path.join(FX, "description_images", name + ".json")
    images = json.load(open(sidecar, encoding="utf-8")) if os.path.isfile(sidecar) else None
    return prepare(line, rules_for("fairwardgolf"), "50002788-fixtures", 1, images)


FIXTURES = sorted(n[:-5] for n in os.listdir(os.path.join(FX, "collected")) if n.endswith(".json"))


@pytest.mark.parametrize("name", FIXTURES[:12])
def test_every_text_is_resolved_or_asked(name, tmp_path):
    p = fixture(name)
    d = D.Dictionaries(str(tmp_path / "live"))                      # seeded from the backups in git
    en, by, pending = T.plan(p, d, {}, TENANT)
    asked = {i["id"] for i in pending}
    assert {t["id"] for t in p["texts"]} == set(en) | asked and not set(en) & asked
    assert all(not has_hangul(v) for v in en.values())
    assert all(has_hangul(i["source"]) for i in pending)            # the model gets only what the rules could not do
    assert all(not has_hangul(en[t["id"]]) for t in p["texts"] if t["kind"] == "spec_label")   # the 19 labels


def test_fixtures_translate_with_the_fake_model(tmp_path):
    d = D.Dictionaries(str(tmp_path / "live"))
    for name in FIXTURES[:8]:
        p = fixture(name)
        batches = T.make_batches(T.plan(p, d, {}, TENANT)[2])
        out = T.translate_product(p, d, {}, TENANT, FakeModel(), "2026-11-08T00:00:00Z")
        assert out.record["status"] == "translated", (name, out.record["problems"])
        assert out.calls == len(batches)                                     # one answer per batch, no fixes


def test_brand_from_the_dictionary_is_the_titles_spelling(tmp_path):
    p = small()
    d = dicts(tmp_path, brand={"캘러웨이": "Callaway"})
    en, by, pending = T.plan(p, d, {}, TENANT)
    assert en[text_id("brand", "캘러웨이")] == "Callaway" and by[text_id("brand", "캘러웨이")] == "dictionary"
    body = json.loads(T.request(p, en, pending, d))
    assert body == {"product": {"title_ko": p["product"]["title_ko"], "brand_en": "Callaway"},
                    "items": [{"id": pending[0]["id"], "kind": "title", "source": pending[0]["source"]}]}
    assert "10 pcs" in body["items"][0]["source"]                     # no glossary, no vendors: no brand asked


def test_a_placeholder_option_name_is_the_products_own_with_its_values(tmp_path):
    p = small(options=[{"name_ko": "선택", "values_ko": ["9도R 스틸", "10.5도R 스틸"]}],
              notes=[{"code": "option_name_placeholder", "detail": "선택"}])
    d = dicts(tmp_path, option_name={"선택": "Select"})               # a dictionary entry must not be used for it
    en, by, pending = T.plan(p, d, {}, TENANT)
    name = next(i for i in pending if i["kind"] == "option_name")
    assert name["context"] == "values: 9도R 스틸 | 10.5도R 스틸"
    out = T.translate_product(p, d, {}, TENANT, FakeModel(), "t")
    assert out.record["status"] == "translated"
    assert "선택" not in d.added["option_name"]                       # kept per product, not in the dictionary
    assert {r["kind"] for r in out.new_texts} == {"title", "option_name"}


# ---- the model: checks and fixes in the same conversation ----------------------------------------------------

def test_failed_items_are_asked_again_in_the_same_conversation(tmp_path):
    p = small(options=[{"name_ko": "색상", "values_ko": ["레드 스틸", "그린 스틸"]}])
    d = dicts(tmp_path)

    def broken(rows):
        rows = [dict(r) for r in rows[:-1]]                            # drop the last id ...
        rows[0]["en"] = "레드"                                          # ... and leave Korean in another
        return rows
    model = FakeModel(lambda items: answer(items, broken), None)
    out = T.translate_product(p, d, {}, TENANT, model, "t")
    assert out.record["status"] == "translated" and out.calls == 2
    history = model.calls[1]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert history[1]["content"][0]["type"] == "text"                  # the assistant turn sent back unchanged
    fix = history[2]["content"]
    assert fix.startswith(T._prompt("translate_fix.md")) and "korean left" in fix and '"missing"' in fix
    assert d.added["option_value"] and out.usage == {"fake": {"input": 200, "output": 100}}


def test_numbers_and_codes_must_survive(tmp_path):
    p = small(options=[{"name_ko": "로프트", "values_ko": ["레드 (L) 11.5 / 7i"]}])

    def lossy(rows):
        return [{**r, "en": "Red L"} if "11.5" in r["en"] else r for r in rows]
    model = FakeModel(lambda items: answer(items, lossy), None)
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, model, "t")
    fix = model.calls[1][2]["content"]
    assert "numbers changed: missing 11.5, 7" in fix and "codes lost: missing 7I" in fix
    assert out.record["status"] == "translated"


def test_a_titles_bracketed_shop_tags_may_go():
    item = {"id": "x", "kind": "title", "source": "[1년AS] 핑 G430 10 pcs"}
    accepted, failed = T.verify([item], json.dumps({"items": [{"id": "x", "en": "PING G430 10 pcs"}]}))
    assert accepted == {"x": "PING G430 10 pcs"} and not failed


def test_not_json_and_wrong_ids():
    item = {"id": "x", "kind": "option_value", "source": "레드"}
    assert T.verify([item], "Sure! Here it is")[1][0]["problems"] == ["not json / wrong shape"]
    accepted, failed = T.verify([item], json.dumps({"items": [{"id": "y", "en": "Red"}, {"id": "x", "en": ""}]}))
    assert not accepted and failed[0]["problems"] == ["empty"]
    accepted, failed = T.verify([item], json.dumps({"items": [{"id": "x", "en": "Red"}, {"id": "x", "en": "Red"}]}))
    assert not accepted and failed[0]["problems"] == ["duplicate id"]
    long = {"id": "n", "kind": "option_name", "source": "옵션"}
    assert "too long" in T.verify([long], json.dumps({"items": [{"id": "n", "en": "A" * 40}]}))[1][0]["problems"][0]


def test_values_that_collide_are_asked_again(tmp_path):
    p = small(options=[{"name_ko": "색상", "values_ko": ["레드", "빨강"]}])

    def same(rows):
        return [{**r, "en": "Red"} if r["_kind"] == "option_value" else r for r in rows]

    def fixed(items):
        return answer(items, lambda rows: [{**r, "en": "Red " + str(n)} for n, r in enumerate(rows)])
    model = FakeModel(lambda items: answer(items, same), fixed)
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, model, "t")
    assert "values not distinct" in model.calls[1][2]["content"]
    assert out.record["status"] == "translated"


def test_still_failing_after_the_fix_rounds_leaves_the_product_untranslated(tmp_path):
    p = small(options=[{"name_ko": "색상", "values_ko": ["레드"]}])
    d = dicts(tmp_path)

    def korean(rows):
        return [{**r, "en": "레드"} if r["_kind"] == "option_value" else r for r in rows]
    model = FakeModel(lambda items: answer(items, korean))
    out = T.translate_product(p, d, {}, TENANT, model, "t")
    assert out.calls == T.FIX_ROUNDS + 1 and out.record["status"] == "untranslated"
    assert out.record["missing"] == [text_id("option_value", "레드")]
    assert d.added["option_name"] == {"색상": _fake_en("색상")}          # what passed is kept
    assert [r["kind"] for r in out.new_texts] == ["title"]


def test_a_refusal_fails_the_product_only(tmp_path):
    out = T.translate_product(small(), dicts(tmp_path), {}, TENANT, FakeModel(stop_reason="refusal"), "t")
    assert out.record["status"] == "untranslated" and out.calls == 1
    assert out.record["problems"][0]["problems"] == ["refusal"]


def test_held_and_offline_products(tmp_path):
    assert T.translate_product({**small(), "status": "held"}, dicts(tmp_path), {}, TENANT, None, "t") \
        .record["status"] == "held"
    out = T.translate_product(small(), dicts(tmp_path), {}, TENANT, None, "t")
    assert out.record["status"] == "pending" and out.calls == 0


# ---- the shop ------------------------------------------------------------------------------------------------

def test_run_writes_the_files_and_a_second_run_asks_nothing(tmp_path):
    shop = tmp_path / "shops" / "fairwardgolf"
    (shop / "prepared").mkdir(parents=True)
    products = [fixture(n) for n in FIXTURES[:3]]
    (shop / "prepared" / "products.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in products), encoding="utf-8")
    d = D.Dictionaries(str(tmp_path / "live"))
    first = T.run("fairwardgolf", FakeModel(), str(tmp_path / "shops"), dicts=d,
                  clock=lambda: (2026, 11, 8, 0, 0, 0, 0, 312, 0))
    assert {r["status"] for r in first["records"]} == {"translated"} and first["calls"] >= 3
    out = shop / "translation"
    rows = [json.loads(x) for x in (out / "translated.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["key"] for r in rows] == sorted(p["key"] for p in products)
    assert all(set(r["en"]) == {t["id"] for t in p["texts"]} for r, p in
               zip(rows, sorted(products, key=lambda x: x["key"])))
    texts = [json.loads(x) for x in (out / "texts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {t["kind"] for t in texts} <= {"title", "review", "option_name"} and texts[0]["at"] == "2026-11-08T00:00:00Z"
    assert f"model calls {first['calls']}" in (out / "report.txt").read_text(encoding="utf-8")
    again = T.run("fairwardgolf", FakeModel(), str(tmp_path / "shops"), dicts=D.Dictionaries(str(tmp_path / "live")))
    assert again["calls"] == 0 and {r["status"] for r in again["records"]} == {"translated"}


def test_limit_and_offline(tmp_path):
    shop = tmp_path / "shops" / "fairwardgolf"
    (shop / "prepared").mkdir(parents=True)
    (shop / "prepared" / "products.jsonl").write_text(
        "".join(json.dumps(fixture(n), ensure_ascii=False) + "\n" for n in FIXTURES[:3]), encoding="utf-8")
    got = T.run("fairwardgolf", FakeModel(), str(tmp_path / "shops"), dicts=D.Dictionaries(str(tmp_path / "l")),
                limit=1)
    assert sorted(r["status"] for r in got["records"]) == ["pending", "pending", "translated"]
    assert sum(1 for r in got["records"] if r["model_calls"]) == 1                # one product sent


# ---- the key and the request ---------------------------------------------------------------------------------

def test_the_key_file(tmp_path):
    path = tmp_path / "translate.keys"
    path.write_text("# keys\nANTHROPIC_API_KEY='sk-ant-test'\nexport OPENAI_API_KEY=sk-oa-test\nOTHER=1\n",
                    encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(T.TranslateError, match="readable by others"):
        T.read_keys(str(path), ignored=lambda p: True)
    path.chmod(0o600)
    with pytest.raises(T.TranslateError, match="not ignored by git"):
        T.read_keys(str(path), ignored=lambda p: False)
    assert T.read_keys(str(path), ignored=lambda p: True) == {"ANTHROPIC_API_KEY": "sk-ant-test",
                                                              "OPENAI_API_KEY": "sk-oa-test"}
    path.write_text("OTHER=1\n", encoding="utf-8")
    with pytest.raises(T.TranslateError, match="has no ANTHROPIC_API_KEY"):
        T.read_keys(str(path), ignored=lambda p: True)
    with pytest.raises(T.TranslateError, match="does not exist"):
        T.read_keys(str(tmp_path / "none"))


def test_the_key_file_variable(monkeypatch):
    monkeypatch.delenv(T.KEY_FILE_ENV, raising=False)
    with pytest.raises(T.TranslateError, match="--offline"):
        T.keys_from_env()


def test_the_chain_from_the_keys():
    env = {"OPENAI_TRANSLATE_MODEL": "gpt-test"}
    chain = T.build_chain({"ANTHROPIC_API_KEY": "a", "OPENAI_API_KEY": "o"}, env)
    assert [m.name for m in chain.models] == ["claude-sonnet-5-5", "gpt-test"]
    assert [m.name for m in T.build_chain({"OPENAI_API_KEY": "o"}, env).models] == ["gpt-test"]
    with pytest.raises(T.TranslateError, match="no key"):
        T.build_chain({"OPENAI_API_KEY": "o"}, {"TRANSLATE_PROVIDERS": "anthropic"})


def test_models_efforts_and_order_come_from_the_env():
    """The owner, 2026-11-08: a model is changed in .env, not in the code."""
    assert T.settings({}) == [("anthropic", "claude-sonnet-5-5", "low"), ("openai", "gpt-6.1-terra", "low")]
    env = {"TRANSLATE_PROVIDERS": "openai, anthropic", "ANTHROPIC_TRANSLATE_MODEL": "claude-haiku-5-5",
           "ANTHROPIC_TRANSLATE_EFFORT": "medium", "OPENAI_TRANSLATE_MODEL": "gpt-5.4-mini",
           "OPENAI_TRANSLATE_EFFORT": "off"}
    assert T.settings(env) == [("openai", "gpt-5.4-mini", None), ("anthropic", "claude-haiku-5-5", "medium")]
    with pytest.raises(T.TranslateError, match="gemini"):
        T.settings({"TRANSLATE_PROVIDERS": "gemini"})


def test_a_model_without_server_fallback_or_effort_is_asked_without_them():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    T.AnthropicModel("k", "claude-haiku-5-5", None, client=client).send("S", [])
    assert "fallbacks" not in sent and "betas" not in sent and "effort" not in sent["output_config"]

    def create_oa(**kwargs):
        sent.clear()
        sent.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}", refusal=None),
                                                        finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, prompt_tokens_details=None))
    oa = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create_oa)))
    T.OpenAIModel("k", "gpt-4.1", None, client=oa).send("S", [])
    assert "reasoning_effort" not in sent


# ---- the fallback --------------------------------------------------------------------------------------------

class DownModel:
    name = "claude-sonnet-5-5"

    def __init__(self):
        self.calls = 0

    def send(self, system, messages):
        self.calls += 1
        raise T.ProviderDown("InternalServerError: overloaded")


def test_anthropic_down_the_product_goes_to_openai_and_anthropic_rests(tmp_path):
    now = [0.0]
    down, backup = DownModel(), FakeModel(name="gpt-test")
    chain = T.Chain([down, backup], cooldown_s=600, clock=lambda: now[0])
    d = dicts(tmp_path)
    first = T.translate_product(small(), d, {}, TENANT, chain, "t")
    assert first.record["status"] == "translated" and first.record["provider"] == "gpt-test"
    assert first.new_texts[0]["by"] == "gpt-test" and chain.events == ["claude-sonnet-5-5 down: InternalServerError: "
                                                                        "overloaded"]
    T.translate_product(small(title="핑 G430 풀세트"), d, {}, TENANT, chain, "t")
    assert down.calls == 1                                             # resting: not tried for the second product
    now[0] = 601
    T.translate_product(small(title="핑 G440 풀세트"), d, {}, TENANT, chain, "t")
    assert down.calls == 2                                             # tried again after the rest


def test_a_refusal_goes_to_the_next_provider(tmp_path):
    chain = T.Chain([FakeModel(stop_reason="refusal", name="claude-sonnet-5-5"), FakeModel(name="gpt-test")])
    out = T.translate_product(small(), dicts(tmp_path), {}, TENANT, chain, "t")
    assert out.record["status"] == "translated" and out.record["provider"] == "gpt-test" and out.calls == 2
    assert set(out.usage) == {"claude-sonnet-5-5", "gpt-test"}


def test_every_provider_down_leaves_the_product_pending(tmp_path):
    chain = T.Chain([DownModel()])
    out = T.translate_product(small(), dicts(tmp_path), {}, TENANT, chain, "t")
    assert out.record["status"] == "pending" and "down" in out.record["problems"][0]["problems"][0]
    assert T.translate_product(small(), dicts(tmp_path), {}, TENANT, chain, "t").record["status"] == "pending"


def test_a_refused_key_stops_the_run(tmp_path):
    class Refused:
        name = "claude-sonnet-5-5"

        def send(self, system, messages):
            raise T.TranslateError("Anthropic refused the key: AuthenticationError")
    with pytest.raises(T.TranslateError):
        T.translate_product(small(), dicts(tmp_path), {}, TENANT, T.Chain([Refused(), FakeModel()]), "t")


def test_the_openai_request():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        message = SimpleNamespace(content='{"items": []}', refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5,
                                                     prompt_tokens_details=SimpleNamespace(cached_tokens=4)))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    model = T.OpenAIModel("unused", "gpt-test", client=client)
    reply = model.send("SYSTEM", [{"role": "user", "content": "{}"}, {"role": "assistant", "content": "x"}])
    assert sent["model"] == "gpt-test" and sent["reasoning_effort"] == "low"
    assert sent["messages"][0] == {"role": "system", "content": "SYSTEM"} and len(sent["messages"]) == 3
    assert sent["response_format"]["json_schema"] == {"name": "translations", "strict": True, "schema": T.SCHEMA}
    assert reply.text == '{"items": []}' and reply.content == reply.text and reply.stop_reason == "stop"
    assert reply.usage == {"input": 6, "output": 5, "cache_read": 4}


@pytest.mark.parametrize("finish, refusal, stop", [("length", None, "max_tokens"), ("content_filter", None, "refusal"),
                                                    ("stop", "I can't", "refusal")])
def test_openai_stops(finish, refusal, stop):
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="", refusal=refusal),
                                                        finish_reason=finish)],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, prompt_tokens_details=None))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert T.OpenAIModel("k", client=client).send("S", []).stop_reason == stop


def test_api_errors_become_provider_down():
    import anthropic
    import httpx2 as httpx
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    def overloaded(**kwargs):
        raise anthropic.InternalServerError("overloaded", response=httpx.Response(529, request=req), body=None)

    def refused(**kwargs):
        raise anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None)

    def client(fn):
        return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=fn)))
    with pytest.raises(T.ProviderDown):
        T.AnthropicModel("k", client=client(overloaded)).send("S", [])
    with pytest.raises(T.TranslateError):
        T.AnthropicModel("k", client=client(refused)).send("S", [])


def test_the_anthropic_request():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text='{"items": []}')],
                               stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=3,
                                                     cache_creation_input_tokens=0))
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    reply = T.AnthropicModel("unused", client=client).send("SYSTEM", [{"role": "user", "content": "{}"}])
    assert sent["model"] == "claude-sonnet-5-5" and sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": T.SCHEMA}
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"} and sent["fallbacks"] == "default"
    assert sent["thinking"] == {"type": "between_tools"} and "temperature" not in sent
    assert reply.text == '{"items": []}' and len(reply.content) == 2
    assert reply.usage == {"input": 10, "output": 5, "cache_read": 3, "cache_write": 0}


def test_cost():
    dollars, unpriced = T.cost({"claude-sonnet-5-5": {"input": 1_000_000, "output": 100_000}, "gpt-test": {"input": 9}})
    assert dollars == pytest.approx(3.0) and unpriced == ["gpt-test"]


# ---- installing the keys (translate_keys.py) -----------------------------------------------------------------

def test_install_moves_the_file_and_sets_the_env(tmp_path):
    import translate_keys as K
    source = tmp_path / "Desktop" / "translate.keys"
    source.parent.mkdir()
    source.write_text("ANTHROPIC_API_KEY=sk-ant-x\nOPENAI_API_KEY=sk-proj-y\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("PORT=8000\nTRANSLATE_KEY_FILE=/old\n", encoding="utf-8")
    target = tmp_path / "config" / "translate.keys"
    assert K.install(str(source), str(target), str(env)) == ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
    assert not source.exists() and oct(target.stat().st_mode & 0o777) == "0o600"
    assert env.read_text(encoding="utf-8") == f"PORT=8000\nTRANSLATE_KEY_FILE={target}\n"
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_install_refuses_a_key_on_the_wrong_line(tmp_path):
    import translate_keys as K
    source = tmp_path / "translate.keys"
    source.write_text("OPENAI_API_KEY=sk-ant-x\n", encoding="utf-8")
    with pytest.raises(T.TranslateError, match="OPENAI_API_KEY"):
        K.install(str(source), str(tmp_path / "t.keys"), str(tmp_path / ".env"))
    assert source.exists() and not (tmp_path / ".env").exists()                  # nothing moved, nothing written


# ---- batches and the system prompt ---------------------------------------------------------------------------

def _items(kind, n, size=10):
    return [{"id": f"{kind}:{i}", "kind": kind, "source": "가" * size} for i in range(n)]


def test_batches_split_by_count_and_size_reviews_apart():
    items = _items("option_value", 45) + _items("review", 20, 400) + [{"id": "big", "kind": "review",
                                                                        "source": "가" * 5000}]
    batches = T.make_batches(items)
    kinds = [{i["kind"] for i in b} for b in batches]
    assert kinds[:2] == [{"option_value"}, {"option_value"}] and all(k == {"review"} for k in kinds[2:])
    assert [len(b) for b in batches[:2]] == [40, 5]                               # BATCH_ITEMS
    assert all(len(b) <= T.REVIEW_ITEMS for b in batches[2:])
    assert all(sum(len(i["source"]) for i in b) <= T.REVIEW_CHARS for b in batches[2:] if len(b) > 1)
    assert [i["id"] for i in batches[-1]] == ["big"]                              # too long: alone
    assert sorted(i["id"] for b in batches for i in b) == sorted(i["id"] for i in items)   # nothing lost


def test_a_product_with_many_reviews_is_asked_in_batches_and_all_come_back(tmp_path):
    reviews = [f"타구감이 좋고 헤드가 커서 편해요 {n}번째" for n in range(30)]
    p = small()
    p["texts"] += [{"id": text_id("review", r), "kind": "review", "ko": r} for r in reviews]
    model = FakeModel()
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, model, "t")
    assert out.record["status"] == "translated" and out.calls == 1 + 4          # title batch + 30 reviews / 8
    assert all(len(json.loads(c[0]["content"])["items"]) <= T.REVIEW_ITEMS for c in model.calls[1:])


def test_one_batch_down_leaves_the_product_pending_with_the_rest_kept(tmp_path):
    class Flaky(FakeModel):
        def send(self, system, messages):
            if len(self.calls) == 1:
                self.calls.append(messages)
                raise T.ProviderDown("overloaded")
            return super().send(system, messages)
    p = small()
    p["texts"] += [{"id": text_id("review", r), "kind": "review", "ko": r} for r in ("헤드가 커요", "그립이 얇아요")]
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, T.Chain([Flaky()]), "t")
    assert out.record["status"] == "pending" and out.record["en"][text_id("title", p["product"]["title_ko"])]


def test_the_system_prompt_has_the_shop_and_the_category():
    full = T.system_prompt("fairwardgolf", "50002788")
    assert full.startswith(T._prompt("translate_system.md"))
    assert "## The shop" in full and "Fairward Golf" in full
    assert "## The product category" in full and "골린이 beginner golfer" in full
    assert T.system_prompt("nosuchshop", "1") == T._prompt("translate_system.md")   # no brief: the base alone


def test_the_request_uses_the_category_system_prompt(tmp_path):
    seen = []

    class Spy(FakeModel):
        def send(self, system, messages):
            seen.append(system)
            return super().send(system, messages)
    T.translate_product({**small(), "shop": "fairwardgolf"}, dicts(tmp_path), {}, TENANT, Spy(), "t")
    assert seen and "## The product category" in seen[0]


# ---- batches on the wire (offline: what the model is sent and how its answers come back) ---------------------

def _product_with(options=(), reviews=(), brand="캘러웨이"):
    p = small(options=[{"name_ko": n, "values_ko": list(v)} for n, v in options], brand=brand)
    p["texts"] += [{"id": text_id("review", r), "kind": "review", "ko": r} for r in reviews]
    return p


def test_each_batch_gets_short_ids_and_answers_map_back_to_text_ids(tmp_path):
    p = _product_with(reviews=[f"헤드가 커서 편해요 {n}" for n in range(10)])
    model = FakeModel()
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, model, "t")
    sent = [json.loads(c[0]["content"])["items"] for c in model.calls]
    assert [[i["id"] for i in b] for b in sent] == [["1", "2"], [str(n) for n in range(1, 9)], ["1", "2"]]
    assert set(out.record["en"]) == {t["id"] for t in p["texts"]}            # every text id answered
    assert all(":" not in i["id"] for b in sent for i in b)                  # text ids never leave the process


def test_the_request_is_compact():
    p = _product_with()
    d = D.Dictionaries("/nonexistent-live", "/nonexistent-backup")
    body = T.request(p, {}, [{"id": "1", "kind": "title", "source": "가"}, {"id": "2", "kind": "brand", "source": "핑"}], d)
    assert ", " not in body and ": " not in body                            # no spaces
    assert json.loads(body)["vendors"] == []                                  # sent: a brand is asked
    assert "vendors" not in json.loads(T.request(p, {}, [{"id": "1", "kind": "review", "source": "가"}], d))


def test_a_fix_round_resends_only_the_failed_short_ids(tmp_path):
    p = _product_with(reviews=["헤드가 커요", "그립이 얇아요", "소리가 좋아요"])

    def drop_second(items):
        return answer(items, lambda rows: [r for r in rows if r["id"] != "2"])
    model = FakeModel(lambda items: answer(items), drop_second, None)       # batch 1 fine; batch 2 loses "2"
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, model, "t")
    fix = model.calls[2][-1]["content"]
    failed = json.loads(fix[fix.rindex('{"failed"'):])["failed"]
    assert [f["id"] for f in failed] == ["2"] and failed[0]["problems"] == ["missing"]
    assert out.record["status"] == "translated" and out.calls == 3


def test_an_answer_for_another_batch_is_ignored(tmp_path):
    p = _product_with(reviews=["헤드가 커요"])

    def extra(items):
        return answer(items, lambda rows: rows + [{"id": "99", "en": "made up", "_kind": "review"}])
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, FakeModel(extra), "t")
    assert "made up" not in out.record["en"].values() and out.record["status"] == "translated"


def test_option_values_in_two_batches_are_still_checked_together(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "BATCH_ITEMS", 2)                                 # title+brand / name+value / value
    p = _product_with(options=[("색상", ("레드", "빨강"))])

    def red(items):
        return answer(items, lambda rows: [{**r, "en": "Red"} if r["_kind"] == "option_value" else r for r in rows])

    def fixed(items):
        return answer(items, lambda rows: [{**r, "en": "Red 2"} for r in rows])
    model = FakeModel(red, red, red, fixed)
    out = T.translate_product(p, dicts(tmp_path), {}, TENANT, model, "t")
    assert any("values not distinct" in c[-1]["content"] for c in model.calls if len(c) > 1)
    assert out.record["status"] == "translated"


def test_thinking_is_off_unless_asked():
    sent = {}

    def create(**kwargs):
        sent.clear()
        sent.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    T.AnthropicModel("k", client=client).send("S", [])
    assert sent["thinking"] == {"type": "between_tools"}
    T.AnthropicModel("k", client=client, thinking="adaptive").send("S", [])
    assert "thinking" not in sent
    chain = T.build_chain({"ANTHROPIC_API_KEY": "a"}, {"ANTHROPIC_TRANSLATE_THINKING": "adaptive"})
    assert chain.models[0].thinking == "adaptive"


def test_a_spec_value_that_is_a_brand_takes_the_vendor_spelling(tmp_path):
    p = small()
    p["texts"].append({"id": text_id("spec_value", "핑"), "kind": "spec_value", "ko": "핑"})
    en, by, _ = T.plan(p, dicts(tmp_path, brand={"핑": "PING", "캘러웨이": "Callaway"}), {}, TENANT)
    assert en[text_id("spec_value", "핑")] == "PING" and by[text_id("spec_value", "핑")] == "dictionary"


def test_a_titles_distributor_and_counts_may_change_form():
    item = {"id": "1", "kind": "title", "source": "젝시오14 남성 풀세트 11pc 던롭스포츠코리아100%"}
    accepted, failed = T.verify([item], json.dumps({"items": [{"id": "1", "en": "XXIO 14 Men's Complete Set 11 pcs"}]}))
    assert accepted and not failed


def test_a_title_word_only_one_variant_has_goes_to_the_model_as_context(tmp_path):
    p = small(title="젝시오14 남성 풀세트 10.5도 R 9개", brand="젝시오",
              notes=[{"code": "title_names_one_variant", "detail": "10.5도 R"}])
    en, by, pending = T.plan(p, dicts(tmp_path, brand={"젝시오": "XXIO"}), {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    assert title["context"] == "drop from the title, only some variants have it: 10.5도 R" and title["drop"] == ["10.5° R"]
    assert "drop" not in json.loads(T.request(p, en, [title], dicts(tmp_path)))["items"][0]   # not sent
    accepted, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en": "XXIO 14 Men's Complete Set 9 pcs"}]}))
    assert accepted and not failed                                    # 10.5 may go: only one variant has it


def test_an_interrupted_run_keeps_what_was_done_and_resumes(tmp_path):
    shop = tmp_path / "shops" / "fairwardgolf"
    (shop / "prepared").mkdir(parents=True)
    products = [fixture(n) for n in FIXTURES[:3]]
    (shop / "prepared" / "products.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in products), encoding="utf-8")

    class Stops(FakeModel):
        def send(self, system, messages):
            if len(self.calls) >= 2:                      # Ctrl-C while the second product is asked
                raise KeyboardInterrupt
            return super().send(system, messages)
    with pytest.raises(KeyboardInterrupt):
        T.run("fairwardgolf", Stops(), str(tmp_path / "shops"), dicts=D.Dictionaries(str(tmp_path / "live")))
    saved = (shop / "translation" / "texts.jsonl").read_text(encoding="utf-8").splitlines()
    assert {json.loads(x)["key"] for x in saved} == {sorted(p["key"] for p in products)[0]}   # the first product kept
    again = FakeModel()
    T.run("fairwardgolf", again, str(tmp_path / "shops"), dicts=D.Dictionaries(str(tmp_path / "live")))
    asked = {i["source"] for c in again.calls for i in json.loads(c[0]["content"])["items"]}
    first = sorted(products, key=lambda p: p["key"])[0]
    assert not asked & {t["ko"] for t in first["texts"] if t["kind"] in ("title", "review")}   # not asked again


# ---- from the review of 2026-11-08 -----------------------------------------------------------------------------

def test_notes_with_several_spans_are_split(tmp_path):
    """The transform joins spans with ", ": "10.5도, R, 카본" and "선택1, 선택2"."""
    p = small(title="젝시오14 풀세트 드라이버 10.5도 R 카본 아이언 MP1400K", brand="젝시오",
              options=[{"name_ko": "선택1", "values_ko": ["9도R 스틸"]}, {"name_ko": "선택2", "values_ko": ["레드 스틸"]}],
              notes=[{"code": "title_names_one_variant", "detail": "10.5도, R, 카본, MP1400K"},
                     {"code": "option_name_placeholder", "detail": "선택1, 선택2"}])
    d = dicts(tmp_path, brand={"젝시오": "XXIO"})
    _, _, pending = T.plan(p, d, {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    accepted, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en": "XXIO 14 Complete Set"}]}))
    assert accepted and not failed                                  # 10.5 / MP1400K may go: one variant's
    names = [i for i in pending if i["kind"] == "option_name"]
    assert len(names) == 2 and all(i.get("placeholder") and i["context"].startswith("values:") for i in names)
    accepted, failed = T.verify(names[1:], json.dumps({"items": [{"id": names[1]["id"], "en": "Color"}]}))
    assert accepted and not failed                                  # "선택2" -> "Color": the 2 need not survive
    out = T.translate_product(p, d, {}, TENANT, FakeModel(), "t")
    assert "선택1" not in d.added["option_name"] and {"option_name"} <= {r["kind"] for r in out.new_texts}


def test_a_promo_tag_in_round_brackets_may_go():
    item = {"id": "1", "kind": "title", "source": "(당일발송) 핑 G440 드라이버 (1년AS)"}
    accepted, failed = T.verify([item], json.dumps({"items": [{"id": "1", "en": "PING G440 Driver"}]}))
    assert accepted and not failed


def test_dictionary_values_that_collide_are_asked_again(tmp_path):
    p = small(options=[{"name_ko": "색상", "values_ko": ["블랙", "검정"]}])
    d = dicts(tmp_path, option_value={"블랙": "Black", "검정": "Black"}, option_name={"색상": "Color"})
    en, by, pending = T.plan(p, d, {}, TENANT)
    asked = [i for i in pending if i["kind"] == "option_value"]
    assert len(asked) == 2 and all(i["context"] == "must differ from: Black" for i in asked)
    out = T.translate_product(p, d, {}, TENANT, FakeModel(), "t")
    assert out.record["status"] == "translated"


def test_a_torn_store_line_is_skipped(tmp_path):
    path = tmp_path / "texts.jsonl"
    path.write_text('{"key": "k", "id": "a", "en": "A"}\n{"key": "k", "id": "b", "e', encoding="utf-8")
    assert T._load_store(str(path)) == {("k", "a"): "A"}


def test_two_runs_saving_the_same_dictionary_keep_both(tmp_path):
    a = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "b"))
    b = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "b"))
    a.add("option_value", "화이트", "White")
    a.save()
    b.add("option_value", "레드", "Red")
    b.save()
    assert D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "b")).entries["option_value"] == {
        "화이트": "White", "레드": "Red"}


def test_a_backup_is_stamped_with_its_time(tmp_path):
    live, backup = str(tmp_path / "live"), str(tmp_path / "backup")
    assert D.backed_up(backup) is None
    d = D.Dictionaries(live, backup)
    d.add("brand", "핑", "PING")
    d.save()
    D.backup(live, backup, at="2026-11-08T13:00:00Z")
    with open(os.path.join(backup, "brand.json"), encoding="utf-8") as f:
        assert json.load(f)["backed_up"] == "2026-11-08T13:00:00Z"
    assert D.backed_up(backup) == "2026-11-08T13:00:00Z"
    assert D.Dictionaries(str(tmp_path / "live2"), backup).get("brand", "핑") == "PING"   # a stamped backup seeds


def _synced(tmp_path, live_entries, backup_entries, at="2026-11-08T13:00:00Z"):
    live, backup = str(tmp_path / "live"), str(tmp_path / "backup")
    D._write(os.path.join(backup, "option_value.json"), "option_value", backup_entries, backed_up=at)
    D._write(os.path.join(live, "option_value.json"), "option_value", live_entries)
    return live, backup


NOW = datetime(2026, 11, 9, 13, 0, 0, tzinfo=timezone.utc)                 # a day after the backup


def test_sync_in_sync_and_waiting(tmp_path):
    live, backup = _synced(tmp_path, {"레드": "Red"}, {"레드": "Red"})
    s = D.sync(live, backup, now=NOW)
    assert (s["action"], s["waiting"], s["days_since_backup"]) == ("none", 0, 1.0) and s["last_backup"]
    assert s["live_updated"].endswith("Z") and s["entries"] == {}
    live, backup = _synced(tmp_path, {"레드": "Red", "화이트": "White"}, {"레드": "Red"})
    s = D.sync(live, backup, now=NOW)
    assert (s["action"], s["new"]) == ("wait", 1) and "1 of 20 entries, 1.0 of 7 days" in s["advice"]
    assert s["entries"] == {"option_value": {"new": {"화이트": "White"}, "changed": {}, "git_only": {}}}
    assert D.reminder(live, backup, now=NOW) is None


def test_sync_due_by_count_by_days_and_before_any_backup(tmp_path):
    many = {f"색{i}": f"Color {i}" for i in range(D.BACKUP_AT_CHANGES)}
    live, backup = _synced(tmp_path, many, {})
    s = D.sync(live, backup, now=NOW)
    assert s["action"] == "backup" and "20 entries waiting" in s["reason"]
    live, backup = _synced(tmp_path, {"레드": "Red", "화이트": "White"}, {"레드": "Red"})
    s = D.sync(live, backup, now=datetime(2026, 11, 15, 13, 0, 0, tzinfo=timezone.utc))
    assert s["action"] == "backup" and s["reason"].startswith("7.0 days")
    live, backup = str(tmp_path / "l2"), str(tmp_path / "b2")
    D._write(os.path.join(live, "brand.json"), "brand", {"핑": "PING"})
    s = D.sync(live, backup, now=NOW)
    assert (s["action"], s["reason"], s["last_backup"]) == ("backup", "never backed up", None)
    assert "a backup is due (never backed up)" in D.reminder(live, backup, now=NOW)


def test_sync_changed_entries_are_read_first(tmp_path):
    many = {f"색{i}": f"Color {i}" for i in range(D.BACKUP_AT_CHANGES)}
    live, backup = _synced(tmp_path, {**many, "레드": "Crimson"}, {"레드": "Red"})
    s = D.sync(live, backup, now=NOW)
    assert (s["action"], s["changed"]) == ("review", 1)
    assert s["entries"]["option_value"]["changed"] == {"레드": ["Red", "Crimson"]}
    assert "the changed ones first" in D.reminder(live, backup, now=NOW)


def test_entries_only_in_git_are_never_dropped(tmp_path):
    """A backup newer than the live copy (pulled from git, seeded by hand): the entries wait for no backup, a
    backup keeps them, and the next run takes them into the live copy (the review of 2026-11-08)."""
    many = {f"색{i}": f"Color {i}" for i in range(25)}
    live, backup = _synced(tmp_path, {"레드": "Red"}, {"레드": "Red", **many})
    s = D.sync(live, backup, now=NOW)
    assert (s["action"], s["waiting"], s["git_only"]) == ("none", 0, 25) and "25 entries only in git" in s["advice"]
    D.backup(live, backup, at="2026-11-09T00:00:00Z")
    assert len(D._read(os.path.join(backup, "option_value.json"), "option_value")) == 26
    d = D.Dictionaries(live, backup)
    assert d.get("option_value", "색3") == "Color 3"
    assert len(D._read(os.path.join(live, "option_value.json"), "option_value")) == 26
    assert D.sync(live, backup, now=NOW)["git_only"] == 0


def test_a_live_fix_reaches_git_and_a_live_entry_is_not_overwritten_by_git(tmp_path):
    live, backup = _synced(tmp_path, {"레드": "Red"}, {"레드": "Rouge"})
    assert D.Dictionaries(live, backup).get("option_value", "레드") == "Red"     # the live copy wins in a run
    D.backup(live, backup, at="2026-11-09T00:00:00Z")
    assert D._read(os.path.join(backup, "option_value.json"), "option_value") == {"레드": "Red"}


def test_a_live_copy_not_written_yet_differs_in_nothing(tmp_path):
    backup = str(tmp_path / "backup")
    D._write(os.path.join(backup, "brand.json"), "brand", {"핑": "PING"}, backed_up="2026-11-08T13:00:00Z")
    s = D.sync(str(tmp_path / "no-live"), backup, now=NOW)
    assert (s["action"], s["git_only"], s["live_updated"]) == ("none", 0, None)


def test_the_reminder_never_stops_a_run(tmp_path):
    live, backup = _synced(tmp_path, {"레드": "Red", "화이트": "White"}, {"레드": "Red"}, at="2026-11-08")
    assert D.reminder(live, backup, now=NOW) is None                  # a hand-edited stamp: `status` shows it


def test_status_cli_prints_the_advice_and_json(tmp_path, capsys):
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")      # the CLI reads the clock: a fresh backup
    live, backup = _synced(tmp_path, {"레드": "Red", "화이트": "White"}, {"레드": "Red", "블루": "Blue"}, at=at)
    assert D.main(["status", "--live-root", live, "--backup-root", backup]) == 0
    out = capsys.readouterr().out
    assert f"last backup: {at} (" in out and "+ 화이트 -> White" in out and "< 블루 -> Blue (only in git)" in out
    assert "advice: not yet" in out
    assert D.main(["status", "--json", "--live-root", live, "--backup-root", backup]) == 0
    assert json.loads(capsys.readouterr().out)["action"] == "wait"


def test_a_run_reminds_when_the_backup_is_due(tmp_path):
    shop = tmp_path / "shops" / "fairwardgolf"
    (shop / "prepared").mkdir(parents=True)
    (shop / "prepared" / "products.jsonl").write_text(
        json.dumps(fixture(FIXTURES[0]), ensure_ascii=False) + "\n", encoding="utf-8")
    d = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "no-backup"))
    report = T.run("fairwardgolf", FakeModel(), str(tmp_path / "shops"), dicts=d)["report"]
    assert any("dictionaries: a backup is due (never backed up)" in line for line in report)


def test_a_titles_after_sales_claim_may_be_dropped_but_flex_letters_stay():
    item = {"id": "1", "kind": "title", "source": "S강도/ 왼손/ PXG/ 테일러메이드/ 골프채 풀세트 좌타 남성 AS가능 왼손잡이"}
    assert "AS" not in T._checked_source(item) and "PXG" in T._checked_source(item)
    flex = {"id": "2", "kind": "title", "source": "드라이버 A S 강도 선택 MASTER"}
    assert T._checked_source(flex) == flex["source"]


def test_a_brand_keeps_the_dictionarys_case(tmp_path):
    d = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "backup"))
    d.add("brand", "핑", "PING")
    d.add("brand", "핑골프", "Ping")                 # the model wrote it in another case: one spelling
    d.add("brand", "요넥스", "Yonex")
    assert d.get("brand", "핑골프") == "PING" and d.brand_spelling("YONEX") == "Yonex" and d.brand_spelling("Acme") == "Acme"
