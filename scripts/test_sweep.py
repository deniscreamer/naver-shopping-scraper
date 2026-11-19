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
import shopify_payload as sp
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


# ---- 2b. title.set_single -------------------------------------------------------------------------------------

# describe.py's conflicts on live products (2026-11-19), the title promising a set while one club is sold
SET_PICKS_ONE = ("The Title describes a set with driver, irons and putter, but the buyer picks one club type: iron, "
                 "putter or driver")                                                   # 13693475187
SET_SINGLE_IRON = "The title calls it a set, but the seller's texts describe a single #7 iron"   # 13848307900


def test_set_single_on_real_conflicts():
    assert S.set_single(SET_PICKS_ONE) and S.set_single(SET_SINGLE_IRON)
    assert S.set_single("The Korean title says complete set, while the product sold is a single 52° gap wedge.")
    # near misses: no single item sold; no title named (the set composition row); the title offering both; the other
    # way round (a spec row single, the title's set may be what is sold)
    assert not S.set_single("The iron count is given as 7 pieces, but the listed irons (5, 6, 7, 8, 9, PW, SW) add "
                            "up to 7")
    assert not S.set_single("The set composition row lists 3 fairway woods, but the buyer picks a single fairway wood")
    assert not S.set_single("The Korean title offers a set or a single wedge, but the buyer's choices are only two "
                            "3-wedge sets.")
    assert not S.set_single("Specifications list a single loft of 60 degrees, while the title gives a set of 52°, "
                            "56° and 60°.")
    assert not S.set_single("The title says set or single, but only 3-piece sets are offered as choices.")
    # the review of the check (2026-11-19): the one thing must be a club or an item, not a gap or a mixed option list
    assert S.set_single("The Title calls the product a golf club set, but the seller's texts describe a single RED "
                        "LINE driving iron (hybrid) and give no club count or set contents.")         # 13793333309
    assert S.set_single("The title describes a complete golf club set, but only one M5 Silver Chipper with head "
                        "cover is sold.")                                                            # 13376918792
    assert S.set_single("Title says a 3-piece set of 52/56/60°, but the buyer picks one size: 56, 52 or 60.")
    assert not S.set_single("Title and description give a six-wedge set (50/52/54/56/58/60), but the size options "
                            "are single wedges, pairs and three-wedge sets.")                         # 13754846756
    assert not S.set_single("The title calls it a wedge set, but only one loft (52°) is given and the number of "
                            "wedges is not stated.")                                                 # 13312227353
    assert not S.set_single("Number of wedges in the set is not clear: the title says set but names a single 52° AW "
                            "wedge, and the Korean title ends with an unexplained 5.")                # 13389324355
    for probe in ("the specs give single-length shafts", "the specs give single length shafts",
                  "one of the irons has no loft given", "the buyer picks a single shaft flex"):
        assert not S.set_single(f"The title calls it a set, but {probe}."), probe
    row = {"conflicts": ["The origin is unclear.", SET_SINGLE_IRON]}
    assert S.set_single_conflict(row, "Kids' Junior Golf Club Set") == SET_SINGLE_IRON
    assert S.set_single_conflict(row, "Kids' Junior #7 Iron") is None              # asked again since: no finding
    assert S.set_single_conflict({"conflicts": "x"}, "Set") is None and S.set_single_conflict(None, "Set") is None


def test_set_single_in_the_shop_a_review_title_never(fx, capsys):
    """13552318731's description row (live, "A11N SPORTS Forged Golf Wedge Set db4P") with the conflict: flagged live with the conflict as its text; the owner's no
    (--decline --check) hides it; a hand title row (by review-...) is never flagged."""
    seeded(fx)
    shop = os.path.join(fx.shops, SHOP)
    key = fx.key(A11N)
    row = describe.load_store(shop)[key]
    append(os.path.join(shop, "translation", "descriptions.jsonl"), {**row, "conflicts": [SET_PICKS_ONE]})
    P._MEMO.clear()
    first = whole(fx, capsys)["answers"]
    f = next(f for f in first["checks"]["title.set_single"]["findings"] if f["key"] == key)
    assert f["store"] == "live" and f["text"] == S._clip(SET_PICKS_ONE)
    assert found(first, "title.set_single") == {key}
    keys = open(os.path.join(shop, "sweep", "latest", "title.set_single.live.keys"), encoding="utf-8").read()
    assert keys == key + "\n"
    category = P.Shop(SHOP, fx.shops).inputs()[0][key]["source"]["category_id"]
    assert f["category"] == str(category)
    split = os.path.join(shop, "sweep", "latest", S.SET_SINGLE_DIR)
    assert os.listdir(split) == [f"live.{category}.keys"]
    assert open(os.path.join(split, f"live.{category}.keys"), encoding="utf-8").read() == key + "\n"
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--check", "title.set_single", "--only", A11N,
                   "--reason", "the owner holds it for its category (owner 2026-11-19)"]) == 0
    capsys.readouterr()
    second = whole(fx, capsys)["answers"]
    assert key not in found(second, "title.set_single") and second["declined"] == {"title.set_single": [key]}
    p = P.Shop(SHOP, fx.shops).inputs()[0][key]
    append(os.path.join(shop, "translation", "texts.jsonl"),
           {"key": key, "id": title_of(p), "kind": "title", "ko": "x", "en": "A11N SPORTS Forged Golf Wedge Set db4P",
            "by": "review-2026-11-19-set"})
    open(S.decisions_path(fx.shops, SHOP), "w").close()                            # no decline: the hand row alone
    third = whole(fx, capsys)
    assert key not in found(third["answers"], "title.set_single")
    hand = third["answers"]["set_single_hand"]                                    # counted apart, never a finding
    assert [(h["key"], h["store"], h["text"]) for h in hand] == [(key, "live", S._clip(SET_PICKS_ONE))]
    assert open(os.path.join(split, "hand.live.keys"), encoding="utf-8").read() == key + "\n"
    assert os.listdir(split) == ["hand.live.keys"]
    assert any("hand titles that also match" in x and "1 live" in x for x in S.table(third["answers"], "out"))


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
    assert sorted(os.listdir(out)) == sorted(["answers.json", "store.json", "groups", "declined.keys",
                                              S.SET_SINGLE_DIR]
                                             + [f"{c}.{s}.keys" for c in S.CODES for s in ("live", "draft")])
    assert os.listdir(os.path.join(out, "groups")) == []                           # no baseline in the fixture
    assert os.listdir(os.path.join(out, S.SET_SINGLE_DIR)) == []                   # no set_single in the fixture
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
    both = json.loads(capsys.readouterr().out)
    a = both["answers"]
    assert (both["store"]["scope"]["live"], both["store"]["scope"]["draft"]) == (6, 1)
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
    assert S.main([SHOP, "--shops-root", fx.shops, "--only", "12178430576", "--json", "--answers"]) == 0
    a = json.loads(capsys.readouterr().out)                                       # --answers: answers.json's shape
    assert a["scope"]["live"] == 1 and a["selection"] == [fx.key("12178430576")]


def test_ocr_sidecars_with_an_error_one_line(fx):
    assert answers(fx)["ocr_errors"] == []                                          # the fixture's two: read fine
    folder = os.path.join(fx.shops, SHOP, "description_images")
    key = "fairwardgolf:naver:1100031592:12814122019"                              # live, 2026-11-19
    with open(os.path.join(folder, "12814122019.json"), "w", encoding="utf-8") as f:
        json.dump({"format": "description_images/1", "key": key, "product_id": "12814122019", "engine": "dict",
                   "images": [], "skipped": [], "error": "worker died (exit -11)", "seconds": 4.2}, f)
    assert answers(fx)["ocr_errors"] == [key]


# ---- --seed-sent: the store's "before" (stage 2) ----------------------------------------------------------------

UNBUILDABLE = "5917858699"                       # a photo the fixture lacks (stage 0: 6 of its 7 build, equal)


def test_seed_sent_writes_where_the_offline_build_is_the_ledgers_and_nothing_else(fx, tmp_path, capsys):
    shop = P.Shop(SHOP, fx.shops)
    ledger = shop.ledger()
    before = _tree(fx.root)
    assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent", "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    after = _tree(fx.root)
    new = {k for k in after if k not in before or after[k] != before[k]}
    sent = os.path.join("shops", SHOP, "publish", "sent")
    lock = os.path.join("shops", f".{SHOP}.lock")                                 # the holder's line (shop_lock)
    assert set(before) <= set(after) and all(k.startswith(sent + os.sep) or k == lock for k in new)
    assert not os.path.exists(tmp_path / "live")                                   # no dictionary written
    assert (r["published"], r["seeded"], r["kept"]) == (7, 6, 0) and len(new - {lock}) == 6 == r["sent_files"]
    assert r["no_baseline"] == {"not buildable: FileNotFoundError": {"count": 1, "keys": [fx.key(UNBUILDABLE)]}}
    for key in ledger:
        if not key.endswith(UNBUILDABLE):
            assert P.load_sent(shop, key) is not None and sp.digest(P.load_sent(shop, key)) == ledger[key]["output"]
    for key in shop.withdrawn():                                                   # never a withdrawn product
        assert not os.path.exists(P.sent_path(shop, key))
    assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent", "--json"]) == 0  # again: nothing written
    r = json.loads(capsys.readouterr().out)
    again = {k: v for k, v in _tree(fx.root).items() if k != lock}                # the lock line names its time
    assert (r["seeded"], r["kept"]) == (0, 6) and again == {k: v for k, v in after.items() if k != lock}


def test_seed_sent_counts_a_differing_build_and_a_row_without_output(fx, capsys):
    ledger = os.path.join(fx.shops, SHOP, "publish", "published.jsonl")
    rows = {}
    for line in open(ledger, encoding="utf-8"):
        rows[json.loads(line)["key"]] = json.loads(line)
    a, b = fx.key("13552318731"), fx.key("13370257430")
    append(ledger, {**rows[a], "output": "0" * 64}, {**rows[b], "output": None})
    assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"seed-sent {SHOP}: 7 published (withdrawn left out): 4 written, 0 already there, "
                          "3 no_baseline")
    assert f"today's build differs from the ledger: 1 ({a})" in out
    assert f"the ledger row has no output: 1 ({b})" in out
    shop = P.Shop(SHOP, fx.shops)
    assert not os.path.exists(P.sent_path(shop, a)) and not os.path.exists(P.sent_path(shop, b))
    assert not os.path.exists(os.path.join(fx.shops, SHOP, "sweep"))              # no checks run, no report


def test_seed_sent_refused_while_the_shop_is_busy_and_a_selection(fx, capsys):
    with shop_files.shop_lock(fx.shops, SHOP, "job.py run j1"):
        assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent"]) == 2
    assert capsys.readouterr().out.startswith(f"sweep: stop: {SHOP} is busy: job.py run j1")
    assert not os.path.exists(os.path.join(fx.shops, SHOP, "publish", "sent"))
    assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent", "--only", fx.key("12080067974")]) == 2  # withdrawn
    assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent", "--only", "12178430576", "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert (r["published"], r["seeded"], r["sent_files"]) == (1, 1, 1)


def test_seed_sent_holds_the_shops_lock_while_it_writes(fx, monkeypatch, capsys):
    """2026-11-19: the ledger is read once; a send started meanwhile could write a newer file seed then overwrites
    with the older build, so no job or send may start while it writes."""
    tried = []
    write = P.write_sent

    def write_while_a_job_tries(*a):
        try:
            with shop_files.shop_lock(fx.shops, SHOP, "job.py run j2"):
                tried.append("got the lock")
        except shop_files.ShopBusy:
            tried.append("busy")
        return write(*a)
    monkeypatch.setattr(P, "write_sent", write_while_a_job_tries)
    assert S.main([SHOP, "--shops-root", fx.shops, "--seed-sent", "--only", "12178430576"]) == 0
    assert tried == ["busy"]
    with shop_files.shop_lock(fx.shops, SHOP, "job.py run j3"):                  # released after
        pass



# ---- the store lagging (stage 3): today's build against publish/sent/ --------------------------------------------

A11N, YAMATO_LEFT, YAMATO_FULL = "13552318731", "13830312765", "13016112970"     # live; live; live (activated)
MILE_HIGH, OWN, RESTORED = "13830324906", "13370257430", "12178430576"            # live; the shop's brand; restored


def seeded(fx):
    """The fixture with its baselines (sweep.py --seed-sent: 6 of its 7 published build to the ledger's output)."""
    assert S.seed_sent(SHOP, fx.shops, None, S.read_dictionaries(S.DICTS_LIVE))["seeded"] == 6
    return P.Shop(SHOP, fx.shops)


def rewrite(fx, rel, key, change):
    """The last row of `key` in the shop file `rel` changed in place (change(row)), the file rewritten whole."""
    path = os.path.join(fx.shops, SHOP, rel)
    rows = [json.loads(x) for x in open(path, encoding="utf-8")]
    change(next(r for r in reversed(rows) if r["key"] == key))
    shop_files.write_atomic(path, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    P._MEMO.clear()


def retitle(fx, pid, change):
    """Today's English title of the product (translated.jsonl), change(old) -> new."""
    key = fx.key(pid)
    p = P.Shop(SHOP, fx.shops).inputs()[0][key]

    def edit(r):
        r["en"][title_of(p)] = change(r["en"][title_of(p)])
    rewrite(fx, os.path.join("translation", "translated.jsonl"), key, edit)


def rebase(fx, pid, change):
    """The store's "before" edited (change(baseline)): the file and the ledger's output follow, as a real send of it
    would have left them (load_sent trusts it)."""
    shop = P.Shop(SHOP, fx.shops)
    key = fx.key(pid)
    base = P.load_sent(shop, key)
    change(base)
    P.write_sent(shop, key, base)
    append(shop.ledger_path, {**shop.ledger()[key], "output": sp.digest(base)})
    P._MEMO.clear()


def describe_row(fx, pid, **row):
    append(os.path.join(fx.shops, SHOP, "translation", "descriptions.jsonl"),
           {"key": fx.key(pid), "generated": "model", "by": "claude-sonnet-5-5", "status": "ok", **row})
    P._MEMO.clear()


def lag(fx, keys=None, dicts=None):
    return S.store_run(SHOP, fx.shops, keys, dicts or S.read_dictionaries(S.DICTS_LIVE))


def grouped(r):
    """{key: its group} over every group (a key in two groups fails here)."""
    out = {}
    for g in r["groups"]:
        for k in g["keys"]:
            assert k not in out, f"{k} in {out.get(k)} and {g['id']}"
            out[k] = g
    return out


def test_store_all_same_after_the_seed_and_no_baseline_one_line(fx, capsys):
    r = lag(fx)
    assert r["same"] == [] and r["groups"] == [] and r["worse"] == []              # no publish/sent/ yet
    assert r["no_baseline"] == {S.NO_FILE: {"count": 7, "keys": sorted(P.Shop(SHOP, fx.shops).ledger())}}
    seeded(fx)
    r = lag(fx)
    assert len(r["same"]) == 6 and r["groups"] == [] and r["worse"] == []
    assert r["no_baseline"] == {S.NO_FILE: {"count": 1, "keys": [fx.key(UNBUILDABLE)]}}
    assert S.main([SHOP, "--shops-root", fx.shops, "--store"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"store lagging {SHOP}: 7 live, 0 drafts; 6 with a baseline: 6 same, 0 changed "
                          f"(improvement 0, eyeball 0; needing --force 0), 0 worse; no baseline 1 ({S.NO_FILE}: 1, "
                          f"{fx.key(UNBUILDABLE)})")


def real_send_ids(shop):
    """publish.clients' ids on a fake store holding the baselines: shopify_admin.vendor_spellings ({lower case:
    the first spelling}, products oldest first: the ledger's order), then publish.vendor_spellings, not sweep's."""
    first = {}
    for key in shop.ledger():
        b = P.load_sent(shop, key)
        if b and b.get("vendor"):
            first.setdefault(b["vendor"], len(first))
    store = {}
    for name in sorted(first, key=first.__getitem__):
        store.setdefault(name.lower(), name)
    return {"publications": ["gid://shopify/Publication/9"], "location": "gid://shopify/Location/1",
            "vendors": P.vendor_spellings(store), "tenant": TENANT}


def send_all(shop, keys, force=False):
    """publish_one on a fake Admin for each key, the real send's ids -> ({key: status}, products)."""
    from test_publish import FakeFiles, FakeProducts
    ids, products = real_send_ids(shop), FakeProducts()
    return {k: P.publish_one(shop, k, products, FakeFiles(), {**ids, "vendors": dict(ids["vendors"])},
                             force=force)["status"] for k in keys}, products


def test_changed_is_what_publish_one_sends_and_same_is_skipped(fx):
    """Equivalence with the real path: each key sweep calls changed (not .force), publish_one on a fake Admin sends;
    each same one it skips; a .force one (the output moved, the inputs digest did not: a vendor the store spells
    otherwise) it skips unforced and sends forced."""
    shop = seeded(fx)
    retitle(fx, A11N, lambda t: t.replace("Wedge Set", "Wedge Pair"))
    old = describe.load_store(shop.dir)[fx.key(MILE_HIGH)]["html"]
    describe_row(fx, MILE_HIGH, html=old.replace("</p>", " It suits a beginner.</p>", 1))
    rebase(fx, YAMATO_FULL, lambda b: b.update(vendor="YAMATO"))     # the store's other spelling; YAMATO_LEFT, older,
    r = lag(fx)                                                      # has "Yamato": the send spells it so
    g = grouped(r)
    changed = set(g) | {w["key"] for w in r["worse"]}
    assert changed == {fx.key(A11N), fx.key(MILE_HIGH), fx.key(YAMATO_FULL)} and not r["worse"]
    forced = {k for k, x in g.items() if x["force"]}
    assert forced == {fx.key(YAMATO_FULL)} and r["needs_force"] == 1
    assert g[fx.key(YAMATO_FULL)]["cost"] == S.COST_FORCE and ".force." in g[fx.key(YAMATO_FULL)]["id"]
    assert {g[fx.key(p)]["cost"] for p in (A11N, MILE_HIGH)} == {S.COST_FREE}
    assert set(r["same"]) == set(shop.ledger()) - changed - {fx.key(UNBUILDABLE)}
    status, products = send_all(shop, [*r["same"], *changed])
    assert {k for k, v in status.items() if v == "published"} == changed - forced
    assert {k for k, v in status.items() if v == "skipped"} == set(r["same"]) | forced
    assert len(products.sent) == 2
    r = lag(fx)
    assert set(grouped(r)) == forced and len(r["same"]) == 5                        # sent: the same now
    status, products = send_all(shop, sorted(forced), force=True)
    assert set(status.values()) == {"published"} and products.sent[0][0]["vendor"] == "Yamato"
    assert lag(fx)["groups"] == [] and len(lag(fx)["same"]) == 6


def test_a_payload_change_without_a_version_needs_force(fx, monkeypatch):
    """A shopify_payload change made without sp.VERSION moves every output and no inputs digest: every key is
    .force, none in a plain resend group (publish_one would skip each)."""
    shop = seeded(fx)
    real = sp.fit_title
    monkeypatch.setattr(sp, "fit_title", lambda *a, **k: real(*a, **k) + " X")
    r = lag(fx)
    assert len(grouped(r)) == 6 and r["needs_force"] == 6
    assert all(g["force"] and g["cost"] == S.COST_FORCE for g in r["groups"])
    big = r["groups"][0]
    assert (big["count"], len(big["examples"])) == (5, S.EXAMPLES)                # 5 keys, 3 examples
    status, _ = send_all(shop, sorted(grouped(r)))
    assert set(status.values()) == {"skipped"}


def test_a_vendor_the_store_spells_otherwise_is_no_change(fx):
    """10476142508 LAROUGE (stage 0): the dictionary spells a brand otherwise than the store; the build takes the
    store's spelling from the baselines as a real send takes it from the store."""
    shop = seeded(fx)
    dicts = S.read_dictionaries(S.DICTS_LIVE)
    for ko, en in list(dicts.entries["brand"].items()):
        if en == "Yamato":
            dicts.entries["brand"][ko] = "YAMATO"                                    # a later entry in capitals
    r = lag(fx, dicts=dicts)
    assert {fx.key(YAMATO_LEFT), fx.key(YAMATO_FULL)} <= set(r["same"]) and r["groups"] == []
    alone = {"vendors": P.vendor_spellings({}, list(dicts.entries["brand"].values())), "tenant": TENANT}
    built = P.build(shop, fx.key(YAMATO_LEFT), alone)                             # the dictionary alone: a false
    assert built["output"] != shop.ledger()[fx.key(YAMATO_LEFT)]["output"]         # vendor change
    assert built["product_input"]["vendor"] == "YAMATO"


def test_the_guards_on_real_pairs(fx, capsys):
    seeded(fx)
    rebase(fx, RESTORED, lambda b: b.update(vendor="PGM"))     # it was PGM's; restored under the shop's name
    rebase(fx, MILE_HIGH, lambda b: b["variants"].append({**b["variants"][0], "sku": "FW-gone"}))
    rebase(fx, YAMATO_LEFT, lambda b: b["files"].append({"id": "0" * 64, "alt": "photo"}))
    describe_row(fx, A11N, html="")                                                # the description gone
    describe_row(fx, OWN, html="<p>Fairward Golf Unisex Wedge Set 5460.</p>", status="fallback")
    rewrite(fx, os.path.join("placement", "placements.jsonl"), fx.key(YAMATO_FULL),
            lambda r: r.update(status="unresolved", reason="no_profile"))
    r = lag(fx)
    worse = {w["key"]: w["guards"] for w in r["worse"]}
    assert {k: [g.split(":")[0] for g in v] for k, v in worse.items()} == {
        fx.key(RESTORED): ["vendor_lost"], fx.key(MILE_HIGH): ["fewer_variants"],
        fx.key(YAMATO_LEFT): ["fewer_photos"], fx.key(A11N): ["description_lost"],
        fx.key(OWN): ["description_lost"], fx.key(YAMATO_FULL): ["not_buildable"]}
    assert worse[fx.key(RESTORED)] == ["vendor_lost: 'PGM' -> 'Fairward Golf'"]
    assert worse[fx.key(OWN)] == ["description_lost: a fallback now (its intro only the title)"]
    assert worse[fx.key(YAMATO_FULL)] == ["not_buildable: placement unresolved: no_profile"]
    assert r["groups"] == [] and r["same"] == []                                    # in no group
    assert S.main([SHOP, "--shops-root", fx.shops]) == 1
    out = capsys.readouterr().out
    assert out.startswith("WORSE 6 (a guard tripped")
    written = json.load(open(os.path.join(fx.shops, SHOP, "sweep", "latest", "store.json"), encoding="utf-8"))
    assert len(written["worse"]) == 6 and written["groups"] == []


def test_a_good_change_trips_no_guard(fx):
    """The guards' good cases: a variant, a photo and a description kept, the shop's own brand kept as it was."""
    seeded(fx)
    rebase(fx, MILE_HIGH, lambda b: b["variants"].pop())                           # today has more: not worse
    rebase(fx, YAMATO_LEFT, lambda b: b["files"].pop())
    rebase(fx, OWN, lambda b: b.update(descriptionHtml=""))                        # a description added
    r = lag(fx)
    assert r["worse"] == [] and set(grouped(r)) == {fx.key(MILE_HIGH), fx.key(YAMATO_LEFT), fx.key(OWN)}
    assert S.guards({"vendor": TENANT}, {"vendor": TENANT}, None, TENANT) == []    # the shop's brand all along


def test_an_improvement_on_a_real_pair(fx):
    """The store's title carries Pongdang Swim (the two-brand scan's class), today's does not: title.other_brand
    fires on the store's and not on today's."""
    seeded(fx)
    rebase(fx, A11N, lambda b: b.update(title=b["title"].replace("A11N SPORTS", "Pongdang Swim")))
    retitle(fx, MILE_HIGH, lambda t: t + " Kit")                                  # a change no check judges
    r = lag(fx)
    g = grouped(r)
    a = g[fx.key(A11N)]
    assert (a["verdict"], a["fields"]) == ("improvement", ["title"])
    assert a["examples"][0]["improved"] == ["title.other_brand"]
    assert a["examples"][0]["changes"][0].startswith("title: 'Pongdang Swim Forged")
    assert g[fx.key(MILE_HIGH)]["verdict"] == "eyeball"
    assert r["changed"] == {"improvement": 1, "eyeball": 1}


def test_each_text_check_an_improvement_and_one_now_tripped(fx):
    """The other three TEXT_CHECKS on real pairs (the store's text bad, today's not), and a key whose build clears
    one check but trips another: eyeball, flagged."""
    seeded(fx)

    def korean_option(b):
        name = b["productOptions"][0]["name"]
        b["productOptions"][0]["name"] = name + " 색상"
        for v in b["variants"]:
            for o in v["optionValues"]:
                if o.get("optionName") == name:
                    o["optionName"] = name + " 색상"
    rebase(fx, MILE_HIGH, korean_option)                                            # an option name's Hangul
    lead_other = "<p>Pongdang Swim Kids' Junior Golf Club is a junior club.</p>"   # another brand in the lead
    rebase(fx, OWN, lambda b: b.update(descriptionHtml=lead_other + b["descriptionHtml"]))
    link = "<p>Visit www.golf.co.kr for more.</p>"                                  # a link: description.patterns
    rebase(fx, YAMATO_FULL, lambda b: b.update(descriptionHtml=b["descriptionHtml"] + link))
    rebase(fx, A11N, lambda b: b.update(descriptionHtml=b["descriptionHtml"] + link))
    retitle(fx, A11N, lambda t: "Pongdang Swim " + t)                              # today's title: another brand
    r = lag(fx)
    assert not r["worse"]
    rows = {e["key"]: (g["verdict"], e) for g in r["groups"] for e in g["examples"]}
    assert {k: (v, e["improved"]) for k, (v, e) in rows.items()} == {
        fx.key(MILE_HIGH): ("improvement", ["text.hangul"]),
        fx.key(OWN): ("improvement", ["description.old_brand"]),
        fx.key(YAMATO_FULL): ("improvement", ["description.patterns"]),
        fx.key(A11N): ("eyeball", ["description.patterns"])}
    assert "now trips title.other_brand" in rows[fx.key(A11N)][1]["flags"]


def test_not_buildable_when_the_build_raises_and_a_broken_file_is_exit_1(fx, monkeypatch):
    seeded(fx)
    real = P.build

    def build(shop, key, ids):
        if key == fx.key(MILE_HIGH):
            raise sp.PayloadError("no price for SKU FW-1")
        return real(shop, key, ids)
    monkeypatch.setattr(P, "build", build)
    r = lag(fx)
    assert [(w["key"], w["guards"]) for w in r["worse"]] == [
        (fx.key(MILE_HIGH), ["not_buildable: PayloadError: no price for SKU FW-1"])]
    assert fx.key(MILE_HIGH) not in r["same"] + list(grouped(r)) and len(r["same"]) == 5

    def broken(shop, key, ids):
        raise S.LedgerError("translated.jsonl:3: not a JSON line")
    monkeypatch.setattr(P, "build", broken)
    with pytest.raises(S.LedgerError):                                             # never a product's verdict
        lag(fx)


def test_the_guards_edges():
    """vendor_lost when the vendor becomes empty; a fallback that was a fallback in the store too is not lost."""
    assert S.guards({"vendor": "PGM"}, {"vendor": ""}, None, TENANT) == ["vendor_lost: 'PGM' -> ''"]
    assert S.guards({"vendor": ""}, {"vendor": TENANT}, None, TENANT) == []
    old = {"title": "PGM Junior Putter", "descriptionHtml": "<p>PGM Junior Putter.</p><ul><li>34 in</li></ul>"}
    new = {"title": "PGM Junior Putter", "descriptionHtml": "<p>PGM Junior Putter.</p><ul><li>35 in</li></ul>"}
    fallback = {"status": "fallback"}
    assert S.guards(old, new, fallback, TENANT) == []                              # fallback -> fallback
    ok = {**old, "descriptionHtml": "<p>A junior putter with a soft grip.</p>"}
    assert S.guards(ok, new, fallback, TENANT) == ["description_lost: a fallback now (its intro only the title)"]
    assert S.guards(ok, ok, fallback, TENANT) == []                                # the body as the store has it


def test_withdrawn_and_no_baseline_keys_in_no_group(fx):
    shop = seeded(fx)
    for pid in (A11N, MILE_HIGH, YAMATO_LEFT, OWN):
        retitle(fx, pid, lambda t: t + " Kit")
    ledger = shop.ledger()
    append(shop.ledger_path, {**{k: ledger[fx.key(A11N)][k] for k in ("format", "key", "product_id", "handle")},
                              "status": "withdrawn", "reason": "hold: test", "at": "2026-11-19T00:00:00Z"})
    os.remove(P.sent_path(shop, fx.key(MILE_HIGH)))                                # no file
    tampered = P.load_sent(shop, fx.key(YAMATO_LEFT))
    tampered["title"] += " (edited)"
    with open(P.sent_path(shop, fx.key(YAMATO_LEFT)), "w", encoding="utf-8") as f:
        json.dump(tampered, f)                                                     # not the ledger's output
    append(shop.ledger_path, {**ledger[fx.key(YAMATO_FULL)], "output": None})       # a failed photo's row
    P._MEMO.clear()
    r = lag(fx)
    assert set(grouped(r)) == {fx.key(OWN)}
    assert r["no_baseline"] == {S.NO_FILE: {"count": 2, "keys": sorted([fx.key(MILE_HIGH), fx.key(UNBUILDABLE)])},
                                S.NOT_LEDGER: {"count": 1, "keys": [fx.key(YAMATO_LEFT)]},
                                S.NO_OUTPUT: {"count": 1, "keys": [fx.key(YAMATO_FULL)]}}
    assert fx.key(A11N) not in r["same"] + [w["key"] for w in r["worse"]] and r["scope"]["live"] == 6


def test_one_key_one_group_and_drafts_apart(fx):
    shop = seeded(fx)
    last = shop.ledger()[fx.key(YAMATO_LEFT)]
    append(shop.ledger_path, {**last, "store_status": "DRAFT"})                    # the same output: still same
    for pid in (YAMATO_LEFT, YAMATO_FULL, MILE_HIGH, RESTORED):
        retitle(fx, pid, lambda t: t + " Kit")
    r = lag(fx)
    g = grouped(r)
    assert set(g) == {fx.key(YAMATO_LEFT), fx.key(YAMATO_FULL), fx.key(MILE_HIGH), fx.key(RESTORED)}
    # the Naver category apart: the same change, the same verdict, two categories, two groups
    a, b = g[fx.key(MILE_HIGH)], g[fx.key(RESTORED)]
    assert (a["category"], b["category"]) == ("50002783", "50002787") and a["fields"] == b["fields"]
    assert a["id"] != b["id"] and ".50002783." in a["id"] and ".50002787." in b["id"]
    assert g[fx.key(YAMATO_FULL)] is a
    draft = g[fx.key(YAMATO_LEFT)]
    assert draft["store"] == "draft" and draft["keys"] == [fx.key(YAMATO_LEFT)]
    assert {g[fx.key(p)]["store"] for p in (YAMATO_FULL, MILE_HIGH)} == {"live"}
    assert [x["store"] for x in r["groups"]][-1] == "draft"                        # live first
    assert sum(x["count"] for x in r["groups"]) == sum(r["changed"].values()) == 4
    append(shop.ledger_path, {**last, "store_status": "ACTIVE"})                   # live again: its fields, its
    live = grouped(lag(fx))[fx.key(YAMATO_LEFT)]                                   # category, its verdict alike
    assert live["id"] == "live" + draft["id"][len("draft"):] and live["store"] == "live"


def test_latest_to_prev_and_new_gone(fx, capsys):
    seeded(fx)
    sweep_dir = os.path.join(fx.shops, SHOP, "sweep")

    def go(*flags):
        assert S.main([SHOP, "--shops-root", fx.shops, "--json", *flags]) == 0
        return json.loads(capsys.readouterr().out)
    first = go()
    assert first["store"]["since_prev"] is None and first["answers"]["since_prev"] is None
    retitle(fx, A11N, lambda t: t + " Kit")
    both = go()
    second = both["store"]
    prev_answers = json.load(open(os.path.join(sweep_dir, "prev", "answers.json"), encoding="utf-8"))
    assert prev_answers == first["answers"]                                       # the answers rotated too
    assert both["answers"]["since_prev"]["description.stale"]["new"] == 1          # the retitled one's packet
    gid = second["groups"][0]["id"]
    assert second["since_prev"][gid] == {"now": 1, "new": 1, "gone": 0}
    assert json.load(open(os.path.join(sweep_dir, "prev", "store.json"), encoding="utf-8"))["groups"] == []
    retitle(fx, MILE_HIGH, lambda t: t + " Kit")
    third = go("--store")                                                          # the store part alone
    other = next(x["id"] for x in third["groups"] if fx.key(MILE_HIGH) in x["keys"])
    assert third["since_prev"][gid] == {"now": 1, "new": 0, "gone": 0}
    assert third["since_prev"][other] == {"now": 1, "new": 1, "gone": 0} and other != gid
    keys = open(os.path.join(sweep_dir, "latest", "groups", f"{other}.keys"), encoding="utf-8").read()
    assert keys == fx.key(MILE_HIGH) + "\n"
    assert os.listdir(os.path.join(sweep_dir, "prev", "groups")) == [f"{gid}.keys"]
    retitle(fx, A11N, lambda t: t.removesuffix(" Kit"))                            # back as the store has it
    fourth = go()
    assert fourth["store"]["since_prev"][gid] == {"now": 0, "new": 0, "gone": 1}
    assert not os.path.exists(os.path.join(sweep_dir, "latest", "groups", f"{gid}.keys"))
    checks = fourth["answers"]["since_prev"]          # against the last checks run (the second: --store kept it)
    assert set(checks) == set(S.CODES) and checks["description.stale"]["gone"] == 1    # A11N's title back: its
    assert all(d["new"] == 0 for d in checks.values())                                 # packet is today's again
    assert all(d["gone"] == 0 for c, d in checks.items() if c != "description.stale")
    rebase(fx, YAMATO_LEFT, lambda b: b["files"].append({"id": "0" * 64, "alt": "photo"}))     # a guard trips
    assert S.main([SHOP, "--shops-root", fx.shops, "--json", "--store"]) == 1
    assert json.loads(capsys.readouterr().out)["since_prev"]["worse"] == {"now": 1, "new": 1, "gone": 0}


def test_a_selection_writes_apart_and_compares_with_nothing(fx, capsys):
    """--only (or --keys-file, --job) narrows the store part to its keys and writes sweep/selection/: latest/ and
    prev/ stay the whole shop's, so the next whole run finds nothing new or gone."""
    seeded(fx)
    sweep_dir = os.path.join(fx.shops, SHOP, "sweep")
    for pid in (A11N, MILE_HIGH):
        retitle(fx, pid, lambda t: t + " Kit")
    assert S.main([SHOP, "--shops-root", fx.shops, "--json"]) == 0
    whole = json.loads(capsys.readouterr().out)["store"]
    assert set(grouped(whole)) == {fx.key(A11N), fx.key(MILE_HIGH)}
    kept = {k: v for k, v in _tree(sweep_dir).items() if not k.startswith("selection")}
    assert S.main([SHOP, "--shops-root", fx.shops, "--store", "--json", "--only", MILE_HIGH]) == 0
    sel = json.loads(capsys.readouterr().out)
    assert sel["scope"]["live"] == 1 and sel["selection"] == [fx.key(MILE_HIGH)] and sel["since_prev"] is None
    assert set(grouped(sel)) == {fx.key(MILE_HIGH)}
    files = os.listdir(os.path.join(sweep_dir, "selection", "groups"))
    assert [open(os.path.join(sweep_dir, "selection", "groups", f), encoding="utf-8").read() for f in files] == [
        fx.key(MILE_HIGH) + "\n"]
    assert {k: v for k, v in _tree(sweep_dir).items() if not k.startswith("selection")} == kept
    assert S.main([SHOP, "--shops-root", fx.shops, "--only", A11N]) == 0           # both parts, the text
    out = capsys.readouterr().out
    assert "since prev (checks): a selection, not compared" in out and "since prev (groups): a selection" in out
    assert sorted(os.listdir(os.path.join(sweep_dir, "selection", "groups"))) != files    # its own, the last one's gone
    assert os.path.exists(os.path.join(sweep_dir, "selection", "answers.json"))
    assert {k: v for k, v in _tree(sweep_dir).items() if not k.startswith("selection")} == kept
    assert S.main([SHOP, "--shops-root", fx.shops, "--json"]) == 0
    again = json.loads(capsys.readouterr().out)
    for part in ("answers", "store"):
        assert all(d["new"] == 0 and d["gone"] == 0 for d in again[part]["since_prev"].values())


def test_each_part_alone_writes_its_own_files(fx, capsys):
    seeded(fx)
    latest = os.path.join(fx.shops, SHOP, "sweep", "latest")
    assert S.main([SHOP, "--shops-root", fx.shops, "--store"]) == 0
    assert sorted(os.listdir(latest)) == ["declined.keys", "groups", "store.json"]
    assert S.main([SHOP, "--shops-root", fx.shops, "--answers"]) == 0
    assert "store.json" in os.listdir(latest) and "answers.json" in os.listdir(latest)
    assert not os.path.exists(os.path.join(fx.shops, SHOP, "sweep", "prev", "store.json"))   # store's kept
    capsys.readouterr()


def test_the_store_part_writes_only_under_sweep_and_exit_codes(fx, capsys):
    seeded(fx)
    rebase(fx, YAMATO_LEFT, lambda b: b["files"].append({"id": "0" * 64, "alt": "photo"}))
    retitle(fx, A11N, lambda t: t + " Kit")
    before = _tree(fx.root)
    assert S.main([SHOP, "--shops-root", fx.shops, "--store"]) == 1                 # worse: 1
    after = _tree(fx.root)
    new = {k for k in after if k not in before or after[k] != before[k]}
    assert new and all(k.startswith(os.path.join("shops", SHOP, "sweep", "latest") + os.sep) for k in new)
    with shop_files.shop_lock(fx.shops, SHOP, "job.py run j1"):
        assert S.main([SHOP, "--shops-root", fx.shops, "--store"]) == 2             # busy: 2
    rebase(fx, YAMATO_LEFT, lambda b: b["files"].pop())
    assert S.main([SHOP, "--shops-root", fx.shops, "--store"]) == 0                 # changed, none worse: 0
    with pytest.raises(SystemExit) as e:
        S.main([SHOP, "--shops-root", fx.shops, "--seed-sent", "--store"])          # usage: 2
    assert e.value.code == 2
    capsys.readouterr()


def test_changes_names_what_store_diff_does_not_read():
    """The weight, the cost, the SEO description and any other key: a change the output hashes is never "same"."""
    base = {"title": "T", "vendor": "V", "productType": "P", "status": "ACTIVE", "tags": ["a"], "descriptionHtml": "",
            "seo": {"title": "T", "description": ""}, "productOptions": [], "files": [{"id": "1" * 64, "alt": "T"}],
            "metafields": [], "variants": [{"sku": "S", "price": "10.00", "optionValues": [], "metafields": [],
                                            "inventoryItem": {"cost": "5.00", "measurement": {"weight": {
                                                "value": 1000, "unit": "GRAMS"}}}}]}
    assert S.changes(base, copy.deepcopy(base)) == []
    heavier = copy.deepcopy(base)
    heavier["variants"][0]["inventoryItem"]["measurement"]["weight"]["value"] = 1200
    heavier["variants"][0]["price"] = "12.00"
    assert S.changes(base, heavier) == ["price S: 10.00 -> 12.00", "weight S: 1000 -> 1200 g"]
    assert sorted({S.field_of(c) for c in S.changes(base, heavier)}) == ["price", "weight"]
    assert S.flags(base, heavier) == ["price $10-10 -> $12-12"]                    # the weight: changes()' line
    other = copy.deepcopy(base)
    other["seo"]["description"], other["giftCard"] = "x", True
    assert S.changes(base, other) == ["seo.description", "giftCard"]
    alt = copy.deepcopy(base)
    alt["files"][0]["alt"] = "T - photo 1"
    assert S.changes(base, alt) == ["photo alt"]
    alt["title"] = "T2"                                         # the alt follows the title: the title's line only
    assert [S.field_of(c) for c in S.changes(base, alt)] == ["title"]
    inv = copy.deepcopy(base)
    v = inv["variants"][0]
    v["inventoryItem"].update(cost="6.00", tracked=True)
    v["taxable"] = False
    assert S.changes(base, inv) == ["cost S: 5.00 -> 6.00", "variant inventoryItem.tracked", "variant taxable"]
    assert [S.field_of(c) for c in S.changes(base, inv)] == ["cost", "variant inventoryItem.tracked",
                                                             "variant taxable"]
    feed = copy.deepcopy(base)
    feed["metafields"] = [{"namespace": "custom", "key": "reviews_feed_url", "type": "url", "value": "sha:abc"}]
    assert S.changes(feed, copy.deepcopy(feed)) == []
    feed2 = copy.deepcopy(feed)
    feed2["metafields"][0]["value"] = "sha:def"
    assert S.changes(feed, feed2) == ["reviews feed"]
    assert S.changes(feed, dict(feed, title="T2")) == ["title: 'T' -> 'T2'"]       # the same feed: not named
    gone = [S.field_of(c) for c in S.changes(feed, base)]
    assert gone and "other" not in gone
    body = dict(base, descriptionHtml="<p>One.</p><p>Two.</p>")
    assert S.changes(body, dict(base, descriptionHtml="<p>One.</p><p>Three.</p>")) == [
        "descriptionHtml: 'Two.' -> 'Three.'"]
    typed = copy.deepcopy(base)
    typed["files"][0]["contentType"] = "IMAGE"
    assert S.changes(base, typed) == ["other"]                                     # nothing names it: "other"
    long = S.group_id("live", "50002783", [f"variant inventoryItem.field{i}" for i in range(9)], "eyeball")
    assert len(long) == S.GROUP_ID_MAX and long.startswith("live.50002783.eyeball.variant_inventoryItem.field0")
    assert long != S.group_id("live", "50002783", [f"variant inventoryItem.field{i}" for i in range(10)], "eyeball")

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


def test_sweep_md_guards_table_is_the_code():
    with open(os.path.join(SCRIPTS, "SWEEP.md"), encoding="utf-8") as f:
        text = f.read()
    start = text.index("\n## Guards\n")
    end = text.find("\n## ", start + 1)
    rows = re.findall(r"^\|\s*`([a-z_]+)`\s*\|", text[start:end if end != -1 else None], re.M)
    assert rows == list(S.GUARD_CODES), f"SWEEP.md 'Guards' rows {rows} != sweep.GUARD_CODES {list(S.GUARD_CODES)}"


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


# ---- the owner's declines and --confirm (stage 4) ----------------------------------------------------------------

def whole(fx, capsys, *flags, code=0):
    """A whole run (--json) -> its output; the exit code checked."""
    assert S.main([SHOP, "--shops-root", fx.shops, "--json", *flags]) == code
    return json.loads(capsys.readouterr().out)


def keys_file(tmp_path, *keys, name="keys.txt"):
    path = tmp_path / name
    path.write_text("".join(k + "\n" for k in keys))
    return str(path)


def group_of(result, key):
    return next(g for g in result["groups"] if key in g["keys"])


REASON = "the old title reads fine (owner 2026-11-19)"


def test_decline_hides_a_key_and_it_returns_when_its_output_moves(fx, tmp_path, capsys):
    seeded(fx)
    for pid in (A11N, MILE_HIGH):
        retitle(fx, pid, lambda t: t + " Kit")
    first = whole(fx, capsys)["store"]
    gid = group_of(first, fx.key(A11N))["id"]
    shown = group_of(first, fx.key(A11N))["outputs"][fx.key(A11N)]
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--keys-file", keys_file(tmp_path, A11N),
                   "--reason", REASON]) == 0
    assert capsys.readouterr().out.startswith(f"declined 1 ({gid}) -> ")
    rows = shop_files.read_jsonl(S.decisions_path(fx.shops, SHOP))
    assert [{k: r[k] for k in ("key", "group", "output", "reason")} for r in rows] == [
        {"key": fx.key(A11N), "group": gid, "output": shown, "reason": REASON}] and rows[0]["at"]
    second = whole(fx, capsys)["store"]
    assert fx.key(A11N) not in grouped(second) and fx.key(MILE_HIGH) in grouped(second)
    handle = P.Shop(SHOP, fx.shops).ledger()[fx.key(A11N)]["handle"]
    assert second["declined"] == [{"key": fx.key(A11N), "store": "live", "handle": handle, "group": gid,
                                   "force": False}]
    assert sum(second["changed"].values()) == 1 and second["since_prev"]["declined"] == {"now": 1, "new": 1, "gone": 0}
    latest = os.path.join(fx.shops, SHOP, "sweep", "latest")
    assert open(os.path.join(latest, "declined.keys"), encoding="utf-8").read() == fx.key(A11N) + "\n"
    assert gid != group_of(second, fx.key(MILE_HIGH))["id"]                     # two categories: its own group
    assert not os.path.exists(os.path.join(latest, "groups", f"{gid}.keys"))
    assert S.main([SHOP, "--shops-root", fx.shops, "--store"]) == 0
    out = capsys.readouterr().out
    assert re.search(r"^declined by the owner, hidden: 1 \(back when a key's build moves: sweep/decisions\.jsonl\); "
                     r"a later send of them carries the declined change anyway.*reprice\.py --apply\): "
                     + re.escape(fx.key(A11N)), out, re.M)
    retitle(fx, A11N, lambda t: t + " Pro")                                        # another build: back
    third = whole(fx, capsys)["store"]
    assert fx.key(A11N) in grouped(third) and third["declined"] == []


def test_decline_writes_only_decisions_and_the_lock_file_and_refuses(fx, tmp_path, capsys):
    seeded(fx)
    retitle(fx, A11N, lambda t: t + " Kit")
    whole(fx, capsys)
    before = _tree(fx.root)
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", MILE_HIGH, "--reason", REASON]) == 2
    assert "in no group of the last whole run" in capsys.readouterr().err         # same: nothing to decline
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", MILE_HIGH, "--only", A11N,
                   "--reason", REASON]) == 2                                       # one bad key: nothing written
    capsys.readouterr()
    lock = os.path.join("shops", f".{SHOP}.lock")
    assert {k for k, v in _tree(fx.root).items() if before.get(k) != v} <= {lock}
    assert not os.path.exists(S.decisions_path(fx.shops, SHOP))
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 0
    after = _tree(fx.root)
    assert {k for k in after if before.get(k) != after[k]} == {
        lock, os.path.join("shops", SHOP, "sweep", S.DECISIONS)}
    with shop_files.shop_lock(fx.shops, SHOP, "job.py run j1"):
        assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 2
    assert capsys.readouterr().out.splitlines()[-1].startswith(f"sweep: stop: {SHOP} is busy: job.py run j1")
    for flags in (["--decline", "--only", A11N], ["--decline", "--only", A11N, "--reason", " "],
                  ["--decline", "--only", A11N, "--reason", "x"], ["--decline", "--only", A11N, "--reason", "(owner)"],
                  ["--decline", "--reason", REASON], ["--reason", REASON], ["--decline", "--confirm", "x"],
                  ["--confirm", "x", "--only", A11N], ["--decline", "--store", "--only", A11N, "--reason", REASON]):
        with pytest.raises(SystemExit) as e:
            S.main([SHOP, "--shops-root", fx.shops, *flags])
        assert e.value.code == 2, flags
    capsys.readouterr()
    assert len(shop_files.read_jsonl(S.decisions_path(fx.shops, SHOP))) == 1


def test_decline_with_no_run_before_is_refused(fx, capsys):
    seeded(fx)
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 2
    assert "no sweep/latest/store.json: run `sweep.py fairwardgolf` first" in capsys.readouterr().err


def test_decline_a_checks_finding(fx, tmp_path, capsys):
    """description.old_brand on 13830324906 ("Black Tee Mile High Life Wedge Set ...": the fixture's live
    description) declined: hidden from that check only while the product builds the same; a new description back."""
    shop = seeded(fx)
    first = whole(fx, capsys)["answers"]
    assert fx.key(MILE_HIGH) in found(first, "description.old_brand")
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--check", "description.old_brand", "--only",
                   MILE_HIGH, "--reason", "Black Tee is the maker's line (owner 2026-11-19)"]) == 0
    capsys.readouterr()
    row = shop_files.read_jsonl(S.decisions_path(fx.shops, SHOP))[-1]
    assert row["group"] == "description.old_brand" and row["output"] == shop.ledger()[fx.key(MILE_HIGH)]["output"]
    second = whole(fx, capsys)
    a = second["answers"]
    assert fx.key(MILE_HIGH) not in found(a, "description.old_brand")
    assert a["declined"] == {"description.old_brand": [fx.key(MILE_HIGH)]}
    assert a["checks"]["description.old_brand"]["live"] == first["checks"]["description.old_brand"]["live"] - 1
    assert fx.key(MILE_HIGH) not in open(os.path.join(fx.shops, SHOP, "sweep", "latest",
                                                      "description.old_brand.live.keys"), encoding="utf-8").read()
    assert second["store"]["declined"] == []                                       # a check's no is not a group's
    assert S.main([SHOP, "--shops-root", fx.shops, "--answers"]) == 0
    assert "declined by the owner, hidden: 1 (description.old_brand 1;" in capsys.readouterr().out
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--check", "title.other_brand", "--only", MILE_HIGH,
                   "--reason", REASON]) == 2                                       # not that check's finding
    assert "not a title.other_brand finding" in capsys.readouterr().err
    old = describe.load_store(shop.dir)[fx.key(MILE_HIGH)]["html"]
    describe_row(fx, MILE_HIGH, html=old.replace("</p>", " It suits a beginner.</p>", 1))
    third = whole(fx, capsys)["answers"]
    assert fx.key(MILE_HIGH) in found(third, "description.old_brand") and third["declined"] == {}


def test_decisions_a_torn_last_line_tolerated_a_broken_middle_one_exit_1(fx, tmp_path, capsys):
    seeded(fx)
    retitle(fx, A11N, lambda t: t + " Kit")
    whole(fx, capsys)
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 0
    capsys.readouterr()
    path = S.decisions_path(fx.shops, SHOP)
    good = open(path, encoding="utf-8").read()
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"key": "fairwardgolf:naver:1:2", "gro')                         # a run killed while appending
    r = whole(fx, capsys)["store"]
    assert [h["key"] for h in r["declined"]] == [fx.key(A11N)] and fx.key(A11N) not in grouped(r)
    retitle(fx, MILE_HIGH, lambda t: t + " Kit")                                   # the owner's next no, torn tail
    whole(fx, capsys)
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", MILE_HIGH, "--reason", REASON]) == 0
    assert "a cut-off last line dropped before the append" in capsys.readouterr().err
    assert [x["key"] for x in shop_files.read_jsonl(path)] == [fx.key(A11N), fx.key(MILE_HIGH)]
    r = whole(fx, capsys)["store"]                                                 # exit 0: both still honoured
    assert {h["key"] for h in r["declined"]} == {fx.key(A11N), fx.key(MILE_HIGH)}
    good = open(path, encoding="utf-8").read()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"key": "torn\n' + good)                                          # a broken line, then a whole one
    assert S.main([SHOP, "--shops-root", fx.shops]) == 1
    assert re.search(r"^sweep: .*decisions\.jsonl:1: not a JSON line", capsys.readouterr().err, re.M)


def test_decline_of_a_build_moved_since_the_run_is_refused(fx, capsys):
    """He said no to what the run showed: a build moved since is not that, so nothing is written (run sweep again)."""
    seeded(fx)
    retitle(fx, A11N, lambda t: t + " Kit")
    whole(fx, capsys)
    retitle(fx, A11N, lambda t: t + " Pro")
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 2
    assert "its build moved since the run: run `sweep.py fairwardgolf` again" in capsys.readouterr().err
    assert not os.path.exists(S.decisions_path(fx.shops, SHOP))


def test_a_declined_key_that_trips_a_guard_is_worse_not_hidden(fx, monkeypatch, capsys):
    seeded(fx)
    retitle(fx, A11N, lambda t: t + " Kit")
    whole(fx, capsys)
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 0
    capsys.readouterr()
    real = S.guards
    monkeypatch.setattr(S, "guards", lambda old, new, *a: real(old, new, *a)
                        + (["vendor_lost: test"] if str(new.get("title", "")).endswith("Kit") else []))
    r = whole(fx, capsys, code=1)["store"]                                        # same output, now worse: shown
    assert fx.key(A11N) in [w["key"] for w in r["worse"]] and r["declined"] == []


def test_confirm_and_decline_refuse_a_run_from_before_stage_4(fx, capsys):
    seeded(fx)
    retitle(fx, A11N, lambda t: t + " Kit")
    gid = group_of(whole(fx, capsys)["store"], fx.key(A11N))["id"]
    path = os.path.join(fx.shops, SHOP, "sweep", "latest", "store.json")
    data = json.load(open(path, encoding="utf-8"))
    for g in data["groups"]:
        del g["outputs"]
    open(path, "w", encoding="utf-8").write(json.dumps(data))
    assert S.main([SHOP, "--shops-root", fx.shops, "--confirm", gid]) == 2
    assert "kept no outputs" in capsys.readouterr().err
    assert S.main([SHOP, "--shops-root", fx.shops, "--decline", "--only", A11N, "--reason", REASON]) == 2
    assert "kept no outputs" in capsys.readouterr().err
    assert not os.path.exists(S.decisions_path(fx.shops, SHOP))


def test_confirm_drops_what_moved_was_sent_withdrawn_or_declined_and_prints_force(fx, monkeypatch, capsys):
    """A .force group of 5 (a payload change without its version): one key's build moves after the run, one is
    sent (its ledger output and sent file follow), one withdrawn, one declined: one is kept, the command --force."""
    shop = seeded(fx)
    real = sp.fit_title
    monkeypatch.setattr(sp, "fit_title", lambda *a, **k: real(*a, **k) + " X")
    first = whole(fx, capsys)["store"]
    big = first["groups"][0]
    assert big["force"] and big["count"] == 5
    moved, sent, gone, said, kept = big["keys"]
    retitle(fx, moved.rsplit(":", 1)[1], lambda t: t + " Kit")
    rebase(fx, sent.rsplit(":", 1)[1], lambda b: b.update(title=b["title"] + " (sent)"))
    row = shop.ledger()[gone]
    append(shop.ledger_path, {**{k: row[k] for k in ("format", "key", "product_id", "handle")},
                              "status": "withdrawn", "reason": "hold: test", "at": "2026-11-19T00:00:00Z"})
    P._MEMO.clear()
    S.decline(SHOP, fx.shops, [said], REASON)
    before = _tree(fx.root)
    assert S.main([SHOP, "--shops-root", fx.shops, "--confirm", big["id"]]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == (f"confirm {big['id']}: 1 of 5 kept; its build moved since the run 1: {moved}; sent since the "
                      f"run 1: {sent}; withdrawn since the run 1: {gone}; declined 1: {said}")
    folder = os.path.join(fx.shops, SHOP, "sweep", "latest", "groups")
    assert open(os.path.join(folder, f"{big['id']}.confirmed.keys"), encoding="utf-8").read() == kept + "\n"
    assert open(os.path.join(folder, f"{big['id']}.plan.tsv"), encoding="utf-8").read() == kept + "\tactive\n"
    assert any(x.strip().startswith(".venv/bin/python scripts/publish.py fairwardgolf --keys-file ")
               and x.endswith(f"{big['id']}.confirmed.keys --force") for x in out)
    after = _tree(fx.root)
    assert {k for k in after if before.get(k) != after[k]} == {
        os.path.join("shops", SHOP, "sweep", "latest", "groups", f"{big['id']}.{x}")
        for x in ("confirmed.keys", "plan.tsv")}


def test_confirm_a_plain_group_then_the_send_empties_it(fx, capsys):
    shop = seeded(fx)
    for pid in (YAMATO_FULL, MILE_HIGH):
        retitle(fx, pid, lambda t: t + " Kit")
    g = group_of(whole(fx, capsys)["store"], fx.key(MILE_HIGH))
    assert set(g["keys"]) == {fx.key(YAMATO_FULL), fx.key(MILE_HIGH)} and not g["force"]
    assert S.main([SHOP, "--shops-root", fx.shops, "--confirm", g["id"]]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"confirm {g['id']}: 2 of 2 kept\n")
    line = next(x for x in out.splitlines() if "scripts/publish.py" in x)
    assert line.endswith(f"{g['id']}.confirmed.keys") and "--force" not in line
    assert "shop_view.py check fairwardgolf " in out and "(the proof: the group gone, worse 0)" in out
    confirmed = open(os.path.join(fx.shops, SHOP, "sweep", "latest", "groups", f"{g['id']}.confirmed.keys"),
                     encoding="utf-8").read().split()
    status, _ = send_all(shop, confirmed)
    assert set(status.values()) == {"published"}
    after = whole(fx, capsys)["store"]
    assert after["groups"] == [] and after["worse"] == [] and after["since_prev"][g["id"]]["gone"] == 2
    assert S.main([SHOP, "--shops-root", fx.shops, "--confirm", g["id"]]) == 2     # gone from the last run
    assert f"no group {g['id']!r} in the last whole run" in capsys.readouterr().err
    with shop_files.shop_lock(fx.shops, SHOP, "job.py run j1"):
        assert S.main([SHOP, "--shops-root", fx.shops, "--confirm", g["id"]]) == 2
    assert capsys.readouterr().out.startswith(f"sweep: stop: {SHOP} is busy: job.py run j1")


def test_confirm_a_draft_group_plans_draft(fx, capsys):
    shop = seeded(fx)
    last = shop.ledger()[fx.key(YAMATO_LEFT)]
    append(shop.ledger_path, {**last, "store_status": "DRAFT"})
    retitle(fx, YAMATO_LEFT, lambda t: t + " Kit")
    g = group_of(whole(fx, capsys)["store"], fx.key(YAMATO_LEFT))
    assert g["store"] == "draft"
    assert S.main([SHOP, "--shops-root", fx.shops, "--confirm", g["id"]]) == 0
    capsys.readouterr()
    plan = os.path.join(fx.shops, SHOP, "sweep", "latest", "groups", f"{g['id']}.plan.tsv")
    assert open(plan, encoding="utf-8").read() == fx.key(YAMATO_LEFT) + "\tdraft\n"


def test_sweep_md_names_every_flag_and_the_skill_points_there():
    """Each of sweep.py's own flags is in SWEEP.md's How to use; the skill names SWEEP.md sections that exist."""
    with open(os.path.join(SCRIPTS, "sweep.py"), encoding="utf-8") as f:
        flags = set(re.findall(r'ap\.add_argument\("(--[a-z-]+)"', f.read())) - {"--shops-root"}
    with open(os.path.join(SCRIPTS, "SWEEP.md"), encoding="utf-8") as f:
        text = f.read()
    use = text[text.index("\n## How to use\n"):text.index("\n## Checks\n")]
    assert {"--decline", "--confirm", "--check", "--reason"} <= flags
    assert not {x for x in flags if x not in use}, "flags missing from SWEEP.md How to use"
    skill = os.path.join(os.path.dirname(SCRIPTS), ".claude", "skills", "sweep", "SKILL.md")
    with open(skill, encoding="utf-8") as f:
        body = f.read()
    assert 30 <= body.count("\n") <= 60
    sections = {m.split(" (")[0].replace('"', "").strip() for m in re.findall(r"^## (.+)$", text, re.M)}
    named = re.findall(r'^\| [^|]+ \| "([^"]+)"', body, re.M)
    assert len(named) >= 6 and not [n for n in named if n not in sections], (named, sections)
