"""sweep.py (the retro-sweep plan, stage 1, 2026-11-19): old model answers a rule now judges wrong, read only. Each
check on one real bad case and one real good case: the shop fixture (fixtures/shop), the prepared fixtures of the
two-brand scan (13510579139 "Pongdang Swim Kids' ...", 13848307900 "PING Women's ..." from 핑크, 13826709716 "Gold
Bunker Inparo JR. ..."), live answers quoted with their product ids. Offline (conftest forbids sockets).

    .venv/bin/python -m pytest scripts/test_sweep.py -q
"""
import copy
import hashlib
import json
import os
import re

import pytest

import describe
import publish as P
import shop_files
import sweep as S
import translation_dicts as D

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
TENANT = "Fairward Golf"
SHOP = "fairwardgolf"
PONGDANG = "Pongdang Swim Kids' Junior Golf Club Putter and Iron"                     # 13510579139, 2026-11-14
PING_PINK = "PING Women's Junior Golf Club Set, #7 Iron, Graphite Shaft"              # 13848307900, 2026-11-13
GOLD_BUNKER = "Gold Bunker Inparo JR. Junior Golf Clubs for Ages 9-12 - Iron, Putter, Driver"   # 13826709716
# 10467808983 (live, 2026-11-15): a vendor's line in its title, the Korean title naming both
MARUMAN = {"key": "fairwardgolf:naver:100117142:10467808983", "status": "ready", "notes": [], "held": [],
           "source": {"category_id": "50002670", "product_id": "10467808983"},
           "product": {"title_ko": "마루망 마제스티 프레스티지오12 여성용 8아이언세트 TL-750 (병행)", "brand_ko": "마루망",
                       "specs": [{"label_ko": "제조사", "value_ko": "마루망"}, {"label_ko": "브랜드", "value_ko": "마루망"},
                                 {"label_ko": "원산지", "value_ko": "일본산"}], "options": []},
           "texts": [{"id": "title:b68cc069e0628c0a", "kind": "title",
                      "ko": "마루망 마제스티 프레스티지오12 여성용 8아이언세트 TL-750 (병행)"},
                     {"id": "brand:c4841c27d555b0dc", "kind": "brand", "ko": "마루망"}]}
MARUMAN_EN = "Maruman Majesty Prestigio 12 Women's 8-Piece Iron Set TL-750"
MARUMAN_HTML = ("<p>Maruman Majesty Prestigio 12 Women's Iron Set TL-750 is a women's iron set with a built-in "
                "tungsten structure for a low center of gravity and a high ball flight.</p>")
# real model sentences settle() cut (descriptions.jsonl `dropped`), as a stored description would show them
TEENS = "It is made for amateur teens, the seller's 10대 age group."                  # 13085001745
OFFICIAL = "Official Korean Callaway distributor product (정품)."                      # 6415415160


def fixture(pid):
    with open(os.path.join(SCRIPTS, "fixtures", "prepared", f"{pid}.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def dicts(tmp_path):
    """The dictionaries of git (the backups), read only: no live copy is made."""
    return S.read_dictionaries(str(tmp_path / "live"), D.BACKUP_ROOT)


@pytest.fixture
def brands(dicts):
    return S.Brands(dicts, TENANT)


@pytest.fixture
def fx(shop_fixture, tmp_path, monkeypatch):
    """The shop fixture with sweep's and describe's dictionaries pointed at git's (nothing live read or written)."""
    monkeypatch.setattr(S, "DICTS_LIVE", str(tmp_path / "live"))
    real = P.vendor_spellings
    backup = list(S.read_dictionaries(str(tmp_path / "live")).entries["brand"].values())
    monkeypatch.setattr(P, "vendor_spellings", lambda store, brands=None: real(store, backup if brands is None
                                                                               else brands))
    return shop_fixture


def lead(body):
    return S.first_sentence(S.text_of(body))


def pats(body):
    return S.description_patterns(S.text_of(body))


def title_of(p):
    return next(t["id"] for t in p["texts"] if t["kind"] == "title")


def answers(fx, keys=None):
    return S.run(SHOP, fx.shops, keys, S.read_dictionaries(S.DICTS_LIVE))


def found(a, code):
    return {f["key"] for f in a["checks"][code]["findings"]}


def append(path, *rows):
    shop_files.append_line(path, *(json.dumps(r, ensure_ascii=False) for r in rows))


# ---- 1. title.pending_reask ------------------------------------------------------------------------------------

def test_pending_reask_the_old_title_plan_asks_again(dicts):
    p = fixture("13510579139")
    store = {(p["key"], title_of(p)): PONGDANG}
    said = S.pending_reask(p, dicts, store, TENANT, {}, set())
    assert said and said.startswith(PONGDANG) and "Pongdang Swim" in said.split("<-")[1]
    assert S.pending_reask(p, dicts, store, TENANT, {}, {(p["key"], title_of(p))}) is None   # a hand row: never


def test_pending_reask_a_title_led_by_its_vendor_is_not(dicts, fx):
    store = {(MARUMAN["key"], title_of(MARUMAN)): MARUMAN_EN}
    assert S.pending_reask(MARUMAN, dicts, store, TENANT, {}, set()) is None
    assert not found(answers(fx), "title.pending_reask")                         # the fixture's 7 live products


# ---- 2. title.other_brand --------------------------------------------------------------------------------------

def test_other_brand_names_the_old_brand_the_korean_does_not(brands):
    assert S.other_brand(PONGDANG, TENANT, fixture("13510579139"), brands) == ["Pongdang Swim"]   # its 브랜드 row:
    assert S.other_brand(PING_PINK, TENANT, fixture("13848307900"), brands) == ["PING"]   # the seller's shop; 핑크
    assert S.other_brand(GOLD_BUNKER, TENANT, fixture("13826709716"), brands) == ["Gold Bunker"]  # Inparo is named


def test_other_brand_quiet_on_a_brand_line_and_a_brand_the_korean_names(brands):
    assert S.other_brand(MARUMAN_EN, "Maruman", MARUMAN, brands) == []           # 마제스티 in the Korean title
    inparo = "Inparo JR. Junior Golf Clubs for Ages 9-12 - Iron, Putter, Driver"
    assert S.other_brand(inparo, TENANT, fixture("13826709716"), brands) == []    # "Inparo JR." in the Korean
    # a mixed set: 12079565200's Korean names Bridgestone as 브릿지스톤, a spelling the dictionary lacks
    mixed = copy.deepcopy(MARUMAN)
    mixed["product"]["title_ko"] = "최강조합 핑 G440 브릿지스톤 V300 9세대 남성 조합 스틸 풀세트 퍼터포함 11피스"
    assert S.other_brand("PING G440 Bridgestone V300 9th Gen Men's Mixed Steel Complete Set", "PING", mixed,
                         brands) == []
    assert brands.named("PINGPONG Set") == []                                    # whole words


def test_other_brand_a_line_of_the_vendor_and_a_short_brand(dicts):
    brands = S.Brands(dicts, TENANT)
    # 9275189943 (live): the vendor PXG TaylorMade (its brand PXG테일러메이드); "PXG" is a line of it, not another brand
    assert brands.other("PXG 0211 Women's Left-Handed Driver", "PXG TaylorMade", "여성 왼손 골프채 풀세트") == []
    assert brands.other("PXG 0211 Women's Left-Handed Driver", "Callaway", "여성 왼손 골프채 풀세트") == ["PXG"]
    # no brand of the dictionary has fewer than 3 letters (2026-11-19); one added would never be looked for
    dicts.entries["brand"]["지비"] = "GB"
    assert S.Brands(dicts, TENANT).named("GB golf bag") == []
    # an unknown vendor (a Hangul brand with no entry: _brand_en gives ""): not judged, as translate._stale_lead
    assert brands.other(PONGDANG, "", "") == []


def test_a_mixed_set_named_in_the_type_row(brands):
    # 9275189943 (live): "조합" only in its 종류 row; the description's lead names Callaway's wood among the makers
    p = copy.deepcopy(MARUMAN)
    p["product"]["title_ko"] = "여성/ 왼손/ PXG/ 테일러메이드/ 골프채 풀세트 좌타 여자 AS가능 피엑스지 왼손잡이"
    p["product"]["specs"] = [{"label_ko": l, "value_ko": v} for l, v in (
        ("제조사", "PXG테일러메이드"), ("브랜드", "PXG테일러메이드"), ("모델명", "PXG테일러메이드"), ("원산지", "미국산"),
        ("종류", "조합풀세트"), ("성별", "여성용"), ("사용방향", "왼손용"), ("퍼터형태", "말렛(반달형)"))]
    text = "a left-handed women's set mixing clubs from PXG, Callaway and TaylorMade"
    assert S.other_brand(text, "PXG TaylorMade", p, brands) == []
    p["product"]["specs"][4]["value_ko"] = "풀세트"                                # not a mixed set: Callaway is other
    assert S.other_brand(text, "PXG TaylorMade", p, brands) == ["Callaway"]


def test_read_dictionaries_are_what_dictionaries_load(tmp_path):
    """write=False gives the entries the default load gives, and writes nothing (a live copy lacking backup entries,
    one kind missing, a category's scope)."""
    with open(os.path.join(D.BACKUP_ROOT, "brand.json"), encoding="utf-8") as f:
        backup = json.load(f)["entries"]
    some = dict(list(backup.items())[:20])
    some["새브랜드"] = "New Brand"                                                # an entry only the live copy has
    for name in ("ro", "rw"):
        os.makedirs(tmp_path / name)
        D._write(str(tmp_path / name / "brand.json"), "brand", some)
    before = _tree(str(tmp_path / "ro"))
    ro = S.read_dictionaries(str(tmp_path / "ro"))
    rw = D.Dictionaries(str(tmp_path / "rw"))
    assert ro.entries == rw.entries and ro.entries["brand"]["새브랜드"] == "New Brand"
    category = sorted(n for n in os.listdir(D.BACKUP_ROOT) if os.path.isdir(os.path.join(D.BACKUP_ROOT, n)))[0]
    assert ro.scope(category).entries == rw.scope(category).entries
    assert _tree(str(tmp_path / "ro")) == before and _tree(str(tmp_path / "rw")) != before
    with pytest.raises(RuntimeError):
        ro.save()


def test_a_review_row_is_never_flagged(fx):
    shop = os.path.join(fx.shops, SHOP)
    key = fx.key("13552318731")
    p = next(json.loads(x) for x in open(os.path.join(shop, "prepared", "products.jsonl"), encoding="utf-8")
             if json.loads(x)["key"] == key)
    tid = title_of(p)
    translated_path = os.path.join(shop, "translation", "translated.jsonl")
    rows = [json.loads(x) for x in open(translated_path, encoding="utf-8")]
    for r in rows:
        if r["key"] == key:
            r["en"][tid] = f"Pongdang Swim {r['en'][tid]}"                         # another brand at its head
    shop_files.write_atomic(translated_path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    texts = os.path.join(shop, "translation", "texts.jsonl")
    model = {"key": key, "id": tid, "kind": "title", "ko": "x", "en": "Pongdang Swim x", "by": "claude-sonnet-5-5"}
    append(texts, model)
    a = answers(fx)
    assert key in found(a, "title.other_brand")
    # run() reports what translate.plan pends: the old title led by another brand, asked with no brand_ko
    pend = next(f for f in a["checks"]["title.pending_reask"]["findings"] if f["key"] == key)
    assert pend["text"].startswith("Pongdang Swim x <- ") and "Pongdang Swim's" in pend["text"]
    append(texts, {**model, "by": "review-2026-11-19-two-brand"})                  # the owner's hand row: kept
    a = answers(fx)
    assert key not in found(a, "title.other_brand") and key not in found(a, "title.pending_reask")
    descriptions = os.path.join(shop, "translation", "descriptions.jsonl")
    bad = f"<p>{TEENS}</p><ul><li>{OFFICIAL}</li></ul>"
    append(descriptions, {"key": key, "html": bad, "generated": "model", "by": "claude-sonnet-5-5"})
    a = answers(fx)
    assert key in found(a, "text.hangul") and key in found(a, "description.patterns")
    # a hand-written description (DESCRIBE.md "Hand rows": by review-<date>-<why>)
    append(descriptions, {"key": key, "html": bad, "generated": "model", "by": "review-2026-11-19-teens"})
    a = answers(fx)
    assert not any(key in found(a, c) for c in ("text.hangul", "description.patterns", "description.stale",
                                                  "description.old_brand"))


def test_option_texts_hangul_and_their_review_row(fx):
    # 5917858699 (Yamaha, live): its option value as the model would have left it untranslated
    shop = os.path.join(fx.shops, SHOP)
    key = fx.key("5917858699")
    vid = "option_value:a839786802f114aa"
    translated_path = os.path.join(shop, "translation", "translated.jsonl")
    rows = [json.loads(x) for x in open(translated_path, encoding="utf-8")]
    for r in rows:
        if r["key"] == key:
            r["en"][vid] = "11.5L4번7번우드5번유틸7아이언퍼터+백포함"
    shop_files.write_atomic(translated_path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    f = next(f for f in answers(fx)["checks"]["text.hangul"]["findings"] if f["key"] == key)
    assert f["text"].startswith("option_value 11.5L4번7번우드")
    append(os.path.join(shop, "translation", "texts.jsonl"),
           {"key": key, "id": vid, "kind": "option_value", "ko": "x", "en": "x", "by": "review-2026-11-19-option"})
    assert key not in found(answers(fx), "text.hangul")


# ---- 3. text.hangul --------------------------------------------------------------------------------------------

def test_hangul_left_in_an_english_text():
    assert S.hangul({"description": TEENS}) == [f"description: {TEENS}"]
    assert S.hangul({"title": MARUMAN_EN, "option_value 9-12세 퍼터": "Ages 9-12 Putter"}) == []


def test_hangul_none_in_the_fixture_shop(fx):
    a = answers(fx)
    assert a["scope"]["live"] == 7 and not found(a, "text.hangul")


# ---- 4. description.old_brand ----------------------------------------------------------------------------------

def test_old_brand_in_the_first_sentence(brands, fx):
    # the live descriptions written under the old vendor (2026-11-19)
    pongdang = "<p>Pongdang Swim Kids' Junior Golf Club is a single junior club, not a set. The buyer picks.</p>"
    ping = "<p>PING junior #7 iron with a carbon (graphite) shaft, made for golf practice.</p>"
    assert S.other_brand(lead(pongdang), TENANT, fixture("13510579139"), brands) == ["Pongdang Swim"]
    assert S.other_brand(lead(ping), TENANT, fixture("13848307900"), brands) == ["PING"]
    # the fixture: 12178430576 (restored under the shop's name) still reads "The PGM Junior Putter ..."
    assert fx.key("12178430576") in found(answers(fx), "description.old_brand")


def test_old_brand_quiet_on_the_vendors_line_and_what_the_set_holds(brands, fx):
    assert S.other_brand(lead(MARUMAN_HTML), "Maruman", MARUMAN, brands) == []
    # 13427122484 (live): a Callaway set's putter is an Odyssey, in a list item, not the product's name
    callaway = copy.deepcopy(MARUMAN)
    callaway["product"]["title_ko"] = "캘러웨이 REVA 여성 풀세트 10피스"
    body = "<p>Callaway REVA Women's Complete Golf Set is a 10-club set.</p><ul><li>Putter: Odyssey White Hot OG #7</li></ul>"
    assert S.other_brand(lead(body), "Callaway", callaway, brands) == []
    assert fx.key("13552318731") not in found(answers(fx), "description.old_brand")    # "A11N SPORTS Forged ..."


# ---- 5. description.patterns -----------------------------------------------------------------------------------

def test_patterns_shop_talk_and_listing_talk():
    assert pats(f"<p>A wedge set.</p><ul><li>{OFFICIAL}</li></ul>") == [
        f"shop talk: Official: {OFFICIAL}"]
    said = pats(f"<p>{TEENS}</p>")
    assert said == [f"about the listing: seller: {TEENS}"]                        # its Hangul: text.hangul's
    assert pats("<p>A putter made in 日本.</p>") == ["not English: A putter made in 日本."]
    # 13754321428 (live): "Unknown Manufacturer" as the product's name
    assert pats("<p>Unknown Manufacturer Men's Left-Handed Complete Golf Club Set.</p>")
    assert pats("<p>Visit www.golf.co.kr for &lt;b&gt;more&lt;/b&gt;</p>")[0].startswith("link")


def test_patterns_none_in_the_fixture_descriptions(fx):
    assert pats(MARUMAN_HTML) == []
    assert not found(answers(fx), "description.patterns")


# ---- 6. description.stale --------------------------------------------------------------------------------------

def test_stale_is_what_describe_offline_published_counts(fx):
    a = answers(fx)
    stale = found(a, "description.stale")
    run = describe.run(SHOP, None, fx.shops, published=True)                       # model None: nothing asked
    in_shop = set(P.Shop(SHOP, fx.shops).ledger())
    assert stale == set(run["stale"]) & in_shop
    assert fx.key("12178430576") in stale and fx.key("13552318731") not in stale   # real both ways


# ---- the run: scope, files, lock, selection --------------------------------------------------------------------

def _tree(root):
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            path = os.path.join(d, n)
            out[os.path.relpath(path, root)] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return out


def test_the_run_writes_only_under_sweep(fx, tmp_path, capsys):
    before = _tree(fx.root)
    assert S.main([SHOP, "--shops-root", fx.shops]) == 0
    after = _tree(fx.root)
    new = {k for k in after if k not in before or after[k] != before[k]}
    assert new and all(k.startswith(os.path.join("shops", SHOP, "sweep", "latest") + os.sep) for k in new)
    assert set(before) <= set(after) and not os.path.exists(tmp_path / "live")     # no dictionary written either
    out = os.path.join(fx.shops, SHOP, "sweep", "latest")
    assert sorted(os.listdir(out)) == sorted(["answers.json"] + [f"{c}.{s}.keys" for c in S.CODES
                                                                 for s in ("live", "draft")])
    keys = open(os.path.join(out, "description.stale.live.keys"), encoding="utf-8").read().split()
    assert fx.key("12178430576") in keys
    printed = capsys.readouterr().out
    assert printed.startswith(f"sweep {SHOP}: 7 live, 0 drafts checked; 5 withdrawn left out")
    assert re.search(r"^description\.stale\s+\d+\s+0$", printed, re.M)


def test_drafts_apart_and_withdrawn_left_out(fx, capsys):
    ledger = os.path.join(fx.shops, SHOP, "publish", "published.jsonl")
    key = fx.key("12178430576")
    last = [json.loads(x) for x in open(ledger, encoding="utf-8") if json.loads(x)["key"] == key][-1]
    append(ledger, {**last, "store_status": "DRAFT"})
    assert S.main([SHOP, "--shops-root", fx.shops, "--json"]) == 0
    a = json.loads(capsys.readouterr().out)
    assert a["scope"]["live"] == 6 and a["scope"]["draft"] == 1
    assert [f["key"] for f in a["checks"]["description.stale"]["findings"] if f["store"] == "draft"] == [key]
    out = os.path.join(fx.shops, SHOP, "sweep", "latest")
    assert open(os.path.join(out, "description.stale.draft.keys"), encoding="utf-8").read() == key + "\n"
    withdrawn = P.Shop(SHOP, fx.shops).withdrawn()
    assert withdrawn and not withdrawn & {f["key"] for c in a["checks"].values() for f in c["findings"]}


def test_refused_while_the_shop_is_busy(fx, capsys):
    lock = os.path.join(fx.shops, f".{SHOP}.lock")
    shop_files.ensure_free(fx.shops, SHOP)                                         # free: no lock file made
    assert not os.path.exists(lock)
    with shop_files.shop_lock(fx.shops, SHOP, "job.py run j1"):
        assert S.main([SHOP, "--shops-root", fx.shops]) == 2
        held = open(lock, encoding="utf-8").read()
    out = capsys.readouterr().out
    assert out.startswith(f"sweep: stop: {SHOP} is busy: job.py run j1 (pid {os.getpid()}, since ")
    assert not os.path.exists(os.path.join(fx.shops, SHOP, "sweep"))
    assert open(lock, encoding="utf-8").read() == held                              # the holder's line kept
    shop_files.ensure_free(fx.shops, SHOP)                                         # released: free again


def test_a_selection_naming_nothing_is_exit_2_never_all(fx, tmp_path, capsys):
    empty = tmp_path / "keys.txt"
    empty.write_text("# nothing\n")
    with pytest.raises(SystemExit) as e:
        S.main([SHOP, "--shops-root", fx.shops, "--keys-file", str(empty)])
    assert e.value.code == 2
    assert S.main([SHOP, "--shops-root", fx.shops, "--only", fx.key("12080067974")]) == 2    # withdrawn: none
    assert not os.path.exists(os.path.join(fx.shops, SHOP, "sweep"))
    assert S.main([SHOP, "--shops-root", fx.shops, "--only", "12178430576", "--json"]) == 0
    a = json.loads(capsys.readouterr().out)
    assert a["scope"]["live"] == 1 and a["selection"] == [fx.key("12178430576")]


def test_ocr_sidecars_with_an_error_one_line(fx):
    assert answers(fx)["ocr_errors"] == []                                          # the fixture's two: read fine
    folder = os.path.join(fx.shops, SHOP, "description_images")
    key = "fairwardgolf:naver:1100031592:12814122019"                              # live, 2026-11-19
    with open(os.path.join(folder, "12814122019.json"), "w", encoding="utf-8") as f:
        json.dump({"format": "description_images/1", "key": key, "product_id": "12814122019", "engine": "dict",
                   "images": [], "skipped": [], "error": "worker died (exit -11)", "seconds": 4.2}, f)
    assert answers(fx)["ocr_errors"] == [key]


# ---- the doc ---------------------------------------------------------------------------------------------------

def test_sweep_md_checks_table_is_the_code():
    with open(os.path.join(SCRIPTS, "SWEEP.md"), encoding="utf-8") as f:
        text = f.read()
    start = text.index("\n## Checks\n")
    end = text.find("\n## ", start + 1)
    rows = re.findall(r"^\|\s*`([a-z_.]+)`\s*\|", text[start:end if end != -1 else None], re.M)
    assert rows == list(S.CODES), f"SWEEP.md 'Checks' rows {rows} != sweep.CODES {list(S.CODES)}"
    # the How to use table (what the owner and the agents act on): a row a code, no code it does not have
    use = text[text.index("\n## How to use\n"):start]
    said = re.findall(r"^\|\s*`([a-z_]+\.[a-z_]+)`\s*\|", use, re.M)
    assert sorted(said) == sorted(S.CODES), f"SWEEP.md 'How to use' codes {said} != sweep.CODES {list(S.CODES)}"


def test_an_unknown_shop_is_usage_and_a_broken_line_exit_1(fx, capsys):
    with pytest.raises(SystemExit) as e:
        S.main(["nosuchshop", "--shops-root", fx.shops])
    assert e.value.code == 2 and "unknown shop 'nosuchshop'" in capsys.readouterr().err
    ledger = os.path.join(fx.shops, SHOP, "publish", "published.jsonl")
    last = open(ledger, encoding="utf-8").read().splitlines()[-1]
    with open(ledger, "a", encoding="utf-8") as f:
        f.write('{"key": "torn\n' + last + "\n")                                    # a torn line, then a whole one
    assert S.main([SHOP, "--shops-root", fx.shops]) == 1
    assert re.search(r"^sweep: .*published\.jsonl:\d+: not a JSON line", capsys.readouterr().err, re.M)
    assert not os.path.exists(os.path.join(fx.shops, SHOP, "sweep"))
