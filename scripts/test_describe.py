"""Offline tests for describe.py: the packet built before the request, the checks and the HTML after the answer,
the store, and the description's way into publication. A fake model, no network.

The inputs are six real products of the first 105 (fixtures/describe/<Naver product id>.json: the prepared record
cut to what the packet reads, the English the shop shows, the cleaned OCR blocks):
  13627933340  PRGR Sweep M17: image text only, a non-conforming driver, one origin
  8974646004   Callaway X HOT: a long typed text, the buyer picks the shaft
  12434254421  Majesty Royal: almost nothing but the title and the spec rows
  7595182520   PING + TaylorMade mixed set: the origin row and the image text disagree
  12606747315  Majesty Sterna: a paid extra putter described in an image block
  11061911792  Callaway Warbird: an image of buyers' reviews of other products, a hedged origin

    .venv/bin/python -m pytest scripts/test_describe.py -q
"""
import json
import os

import pytest

import describe as D
import publish as PB
import shopify_payload as sp
import translate
from shop_pricing import policy
from test_publish import FakeFiles, FakeProducts, IDS

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "describe")
GOLF = D.PROFILES["golf_set"]


def load(pid):
    with open(os.path.join(FIXTURES, f"{pid}.json"), encoding="utf-8") as f:
        return json.load(f)


def packet(pid):
    fx = load(pid)
    return D.packet(fx["prepared"], fx["translated"], fx["blocks"], None, "Fairward Golf")


class Fake:
    """A model that answers from a list: a dict (the JSON), a translate.Reply, or an exception to raise."""

    def __init__(self, answers, name="fake"):
        self.answers, self.name, self.calls = list(answers), name, []

    def send(self, system, messages, schema=None):
        self.calls.append({"system": system, "messages": messages, "schema": schema})
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        if isinstance(a, translate.Reply):
            return a
        return translate.Reply(None, json.dumps(a), "end_turn", {"input": 100, "output": 50})


GOOD = {"intro": "The PRGR Sweep M17 is an 11-club women's set for right-handed golfers. It comes with a caddie bag "
                 "and a Boston bag.",
        "included": ["Driver, 11.5°", "2 fairway woods", "Hybrid", "Irons: #7, #8, #9, PW, AW, SW", "Mallet putter",
                     "Caddie bag and Boston bag"],
        "highlights": ["The driver does not conform to USGA and R&A rules; for recreational play only.",
                       "Graphite iron shafts.", "Made in Japan."],
        "conflicts": []}


# ---- before the request -------------------------------------------------------------------------------------------

def test_packet_names_the_product_as_the_shop_does_and_puts_what_is_sold_first():
    m = packet("8974646004")["message"]
    assert m.startswith("# Product\nTitle: Callaway X HOT Men's Complete Golf Club Set, 11 Pieces with Caddie Bag\n"
                        "Brand: Callaway\n")
    assert "The buyer picks: X HOT Set with Caddie Bag: Steel Shaft (S) SPEC | Graphite Shaft (R) SPEC" in m
    assert "Driver Loft: 10.5°" in m and "Total Clubs: 11" in m          # the English rows the shop shows
    order = [m.index(h) for h in ("# Product", "# What is sold", "# Specifications", "# Seller's text")]
    assert order == sorted(order)
    assert "# Text read from the seller's images" not in m               # its only block is a table
    assert m.index("# Tables read from the seller's images") > m.index("# Seller's text")


def test_packet_says_one_configuration_when_there_is_nothing_to_pick():
    assert "One configuration, as the title says." in packet("13627933340")["message"]


def test_a_fact_without_a_label_and_the_listings_hints():
    m = packet("7595182520")["message"]
    assert "Fixed: Option 1 - Driver, Hybrid, 7 Irons, Putter" in m
    assert "only the one under \"What is sold\" is ours" in m           # paid_variants_left_out
    assert "paid extras: they are not part of this product" in packet("12606747315")["message"]


def test_tables_read_by_ocr_are_sent_apart_from_the_text():
    m = packet("13627933340")["message"]
    text, tables = m.split("# Tables read from the seller's images")
    assert "드라이버(#1 11.5°)" in text and "로프트각" not in text.split("# Text read from")[1]
    assert "로프트각() | 11.5 | 18 | 24 | 29" in tables and "2003년부터 | 쌓아온" not in tables   # words in columns: text
    assert packet("13627933340")["dropped"] == {}


@pytest.mark.parametrize("text, table", [
    ("NEW 2019 | 여성|카본10pcs | 클럽만", False),                      # 5479607864: "clubs only" must reach the model
    ("우드:1 | 아이언:7 | S | 퍼터:PT", False),
    ("제품구성 | 10PCS +골프백 | 제조자 | 캘러웨이", False),
    ("10.5 | 58.5 | H1 | 460 | 45.25 | Do | 298", True),
    ("중량(g) | 67 | 68 | 69\n토크() | 3.6 | 3.5 | 3.5", True),
    ("길이 | 43inch | 42inch", True),
    ("헤드 | 1W | 4W\n로프트각 | 11.5 | 18\n라이각 | 59.5 | 60", True),      # three rows: a table whatever the words
])
def test_words_in_columns_are_text_and_figures_are_a_table(text, table):
    block = {"id": "b1", "kind": "table", "image": 1, "text": text}
    assert D._is_table(block) is table
    sent, tables, dropped = D.image_text([block])
    assert (sent, tables) == (("", text) if table else (text, "")) and dropped == {}
    assert D._is_table({**block, "kind": "text"}) is False


def test_a_block_headed_by_a_paid_extra_is_not_sent():
    p = packet("12606747315")
    assert p["dropped"]["extra"] == 1 and "추가구매" not in p["message"] and "오디세이" not in p["message"]


def test_a_line_naming_an_extra_further_down_stays_with_its_label():
    blocks = [{"id": "b1", "kind": "text", "image": 1,
               "text": "제품 구성\n핑 G440 MAX 10.5도SR 드라이버\n테일러메이드 M4 경량스틸R 7아이언\n추가 주문 상품:5번 SR 페어웨이 우드"}]
    text, _, dropped = D.image_text(blocks)                               # 11635694901: the composition block
    assert dropped == {} and "드라이버" in text and "추가 주문 상품:5번" in text
    typed = D._lines_kept("5> 퍼터: MO-32 퍼터\n<골프백 별매 추가선택가능>\n테일러메이드 캐디백\n제조국 : 중국")
    assert "골프백 별매" in typed and "캐디백" in typed and "제조국" not in typed     # 9266336330: the label stays


def test_a_gift_fact_is_not_what_is_sold():
    from transform import text_id
    fx = load("13627933340")
    fx["prepared"]["product"]["facts"] = [{"label_ko": "사은품", "value_ko": "퍼터"},
                                          {"label_ko": "색상", "value_ko": "레드"}]
    fx["translated"]["en"].update({text_id("fact_label", "사은품"): "Free Gift", text_id("fact_value", "퍼터"): "Putter",
                                   text_id("fact_label", "색상"): "Color", text_id("fact_value", "레드"): "Red"})
    m = D.packet(fx["prepared"], fx["translated"], fx["blocks"], None, "Fairward Golf")["message"]
    assert "Fixed: Color: Red" in m and "Fixed: Free Gift" not in m
    assert "write that the product has no such item\nFree Gift: Putter" in m
    assert m.index("# Gifts of the seller") > m.index("Origin: ")


def test_an_image_of_buyers_reviews_is_not_sent():
    p = packet("11061911792")
    assert p["dropped"]["review"] == 19
    assert "kdse***" not in p["message"] and "입을수 있어서" not in p["message"]      # ids and the reviews by them


def test_long_image_text_is_cut_at_a_block():
    blocks = [{"id": f"b{i}", "kind": "text", "image": i, "text": "가" * 5000} for i in range(4)]
    text, tables, dropped = D.image_text(blocks)
    assert len(text) <= D.OCR_MAX + 10 and tables == "" and dropped == {"over": 2}
    rows = [{"id": f"t{i}", "kind": "table", "image": i, "text": "1 | 2 | 3\n" * 500} for i in range(3)]
    assert D.image_text(rows)[2] == {"over": 2}


@pytest.mark.parametrize("row, texts, country, why", [
    ("일본산", [], "Japan", None),
    ("중국산", ["제조국 : 중국 (일본 정식 유통제품)"], "China", None),          # the first country, not the bracket
    (None, ["※원산국- Made in JAPAN"], "Japan", None),
    (None, ["좋은 클럽입니다"], None, None),                                    # nobody names one
    ("미국산", ["제조국 / 베트남(변동될수 있음)"], None, "sources disagree"),
    ("일본산", ["제조국은 일본이 아닌 다른 국가일 수 있습니다"], None, "hedged"),
    ("일본 외 제3국", [], None, "hedged"),
    ("중국산(중국, 홍콩) 등", [], None, "sources disagree"),
    ("일본산", ["헤드커버 ( Made in CHINA ) 포함"], None, "sources disagree"),  # a part's origin: silence is safe
    ("미국산", ["*테일러메이드공장일정에따라베트남, 타이완, 중국에서생산됩니다."], None, "sources disagree"),   # 11635694901
    ("일본산", ["제조국: 생산 시기에 따라 변동될 수 있음"], None, "hedged"),       # a hedge that names no country
    (None, ["원산지는 상이할 수 있습니다"], None, "hedged"),
    ("캄보디아산", ["헤드 커버(Made in CHINA ) 포함"], None, "hedged"),          # a country the table does not know
])
def test_origin_is_stated_only_when_the_sources_name_one_country(row, texts, country, why):
    got, note = D.origin(row, texts)
    assert got == country
    assert (why in note) if why else note is None


def test_the_origin_line_is_the_only_word_on_origin_in_the_packet():
    p = packet("13627933340")
    assert p["origin"] == "Japan" and "Origin: made in Japan" in p["message"]
    assert "Made in JAPAN" not in p["message"] and "Country of Origin" not in p["message"]
    p = packet("7595182520")
    assert p["origin"] is None and "sources disagree: row: USA; text: China, Taiwan, Vietnam" in p["origin_note"]
    assert "Origin: do not state" in p["message"] and "제조국" not in p["message"]
    assert "Country of Origin" not in p["message"] and "에서생산" not in p["message"]
    p = packet("8974646004")
    assert p["origin"] == "China" and "제조국" not in p["message"]


def test_the_answer_schema_follows_the_profile():
    s = D.schema(GOLF)
    assert s["required"] == ["conflicts", "intro", "included", "highlights"] and s["additionalProperties"] is False
    assert D.schema(D.PROFILES["default"])["required"] == ["conflicts", "intro", "highlights"]
    assert D.profile_of("50002788")[0] == "golf_set" and D.profile_of("50000167")[0] == "default"
    assert "golf club sets" in D.system_prompt("golf_set") and "`included`" not in D.system_prompt("default")


# ---- after the answer ---------------------------------------------------------------------------------------------

NUMBERS = D.allowed_numbers("Driver Loft: 10.5°\nTotal Clubs: 11\n#6, #7, #8, #9\n마제스티 23년 로얄\n9인치")


@pytest.mark.parametrize("text", [
    "Driver, 10.5°, with an adjustable hosel", "Irons: #6–#9, PW, AW, SW", "An 11-club men's set.",
    "The 2023 Royal line.",                                             # 23년 in the Korean
    "9-inch caddie bag and head covers", "Made in Japan.", "Japan-market model, made in Japan.",
    "Putter with two white alignment lines and a red dot.", "Two parallel alignment lines on the putter.",
    "7 irons: #6-#9, P/A/S", "Important for a slower swing.",
])
def test_a_plain_fact_passes(text):
    assert D.problems(text, NUMBERS, "Japan") == []


@pytest.mark.parametrize("text, why", [
    ("캘러웨이 드라이버", "not English"),
    ("ドライバー 10.5°", "not English"),
    ("See www.samsunggolf.co.kr for more.", "link"),
    ("Call 051-324-6360.", "phone"),
    ("Only $499 this week.", "price"),
    ("Costs 880,000 won.", "price"),
    ("<b>Forged</b> irons.", "markup"),
    ("A set for right-hand... women golfers.", "markup"),
    ("Free shipping on this set.", "shop talk: shipping"),
    ("3-year warranty included.", "shop talk: warranty"),
    ("100% genuine product.", "shop talk: 100% genuine"),
    ("Comes with a free gift.", "shop talk: gift"),
    ("A 1+1 offer.", "shop talk: 1+1"),
    ("Buyers' reviews praise the feel.", "shop talk: reviews"),
    ("Driver, 9.5°", "numbers not in the source: 9.5"),
    ("A 12-club set.", "numbers not in the source: 12"),
    ("Made in China.", "origin: China"),
    ("Forged in Korea.", "origin: Korea"),
    ("A product of China.", "origin: China"),
    ("Chinese-made heads with graphite shafts.", "origin: China"),
    ("Handmade in Vietnam.", "origin: Vietnam"),
    ("A genuine Callaway product.", "shop talk: genuine"),
    ("Officially imported by Callaway Golf.", "shop talk: Officially"),
    ("Not a grey-market import.", "shop talk: grey-market"),
    ("Free A/S for 3 years.", "shop talk: A/S"),
    ("Driver (10.5° loft per the specifications)", "about the listing: per the"),
    ("Hybrid, depending on the option chosen", "about the listing: depending on the option"),
    ("It is aimed at men who want a full set of 10 clubs.", "about the listing: who want"),
    ("The set is a parallel import.", "shop talk: parallel import"),
    ("Specs may differ slightly from the actual product.", "about the listing: may differ"),
    ("No putter is mentioned.", "about the listing: is mentioned"),
])
def test_what_cannot_be_shown(text, why):
    assert why in D.problems(text, NUMBERS, "Japan")


def test_a_number_glued_by_ocr_is_still_the_models_to_use():
    numbers = D.allowed_numbers("페어웨이우드(#418°,#724°)\n유틸리티 (#629)")           # 13627933340, block b08
    assert D.problems("2 fairway woods (#4 at 18°, #7 at 24°)", numbers | {"2", "4", "7"}, None) == []
    assert D.problems("Fairway wood, 19°", numbers, None) == ["numbers not in the source: 19"]
    assert D.problems("8 irons", numbers, None) == ["numbers not in the source: 8"]    # one digit: as given only


def test_the_clubs_inside_a_range_are_the_models_to_name():
    numbers = D.allowed_numbers("12.5도 | 18도 | 5번,6번 | (7-9,P,S)\n아이언 #5~9")        # 13719960843
    assert D.problems("Irons and wedges: 7, 8, 9, P, S", numbers, None) == []
    assert D.problems("Irons: #5, #6, #7, #8, #9", numbers, None) == []
    assert D.problems("Irons: #4-#9", numbers, None) == ["numbers not in the source: 4"]
    assert "13" not in D.allowed_numbers("6-4 Ti, 2020-2026")                          # not a range of clubs


def test_the_stage_asks_at_its_own_effort_with_thinking_on():
    chain = D.build_chain({translate.ANTHROPIC_KEY: "k", translate.OPENAI_KEY: "o"}, {})
    assert [(m.name, m.effort) for m in chain.models] == [(translate.MODEL, "medium"),
                                                         (translate.OPENAI_MODEL, "medium")]
    assert chain.models[0].thinking == "adaptive"
    one = D.build_chain({translate.ANTHROPIC_KEY: "k"}, {"DESCRIBE_EFFORT": "high", "TRANSLATE_PROVIDERS": "anthropic"})
    assert [(m.name, m.effort) for m in one.models] == [(translate.MODEL, "high")]
    with pytest.raises(translate.TranslateError):
        D.build_chain({}, {})


def test_no_origin_decided_means_no_origin_in_the_text():
    assert D.problems("Made in Japan.", NUMBERS, None) == ["origin: Japan"]
    assert D.problems("Japanese-made irons.", NUMBERS, None) == ["origin: Japan"]
    assert D.problems("Made in the USA.", NUMBERS, "USA") == []
    assert D.problems("Made in U.S.A. Steel shafts.", NUMBERS, "USA") == []


def test_a_market_version_is_not_an_origin():
    assert D.problems("Japan-market model, made in China.", NUMBERS, "China") == []
    assert D.problems("Japan-market model.", NUMBERS, None) == []
    assert D.problems("Japan spec shafts.", NUMBERS, "China") == []
    assert D.problems("Japan-market model, made in Japan.", NUMBERS, "China") == ["origin: Japan"]


def test_a_good_answer_is_rendered_as_it_is():
    done = D.settle(GOOD, GOLF, packet("13627933340"))
    assert done["status"] == "ok" and done["dropped"] == []
    assert done["html"] == (
        "<p>The PRGR Sweep M17 is an 11-club women's set for right-handed golfers. It comes with a caddie bag and a "
        "Boston bag.</p>\n"
        "<h3>What's included</h3>\n"
        "<ul>\n<li>Driver, 11.5°</li>\n<li>2 fairway woods</li>\n<li>Hybrid</li>\n"
        "<li>Irons: #7, #8, #9, PW, AW, SW</li>\n<li>Mallet putter</li>\n<li>Caddie bag and Boston bag</li>\n</ul>\n"
        "<h3>Highlights</h3>\n"
        "<ul>\n<li>The driver does not conform to USGA and R&amp;A rules; for recreational play only.</li>\n"
        "<li>Graphite iron shafts.</li>\n<li>Made in Japan.</li>\n</ul>")


def test_a_bad_highlight_goes_alone():
    answer = {**GOOD, "highlights": GOOD["highlights"] + ["Free shipping and a 3-year warranty."]}
    done = D.settle(answer, GOLF, packet("13627933340"))
    assert done["status"] == "trimmed" and done["fields"]["highlights"] == GOOD["highlights"]
    assert done["dropped"][0]["where"] == "highlights" and "shop talk: shipping" in done["dropped"][0]["why"]


def test_a_bad_item_takes_the_whole_included_list():
    answer = {**GOOD, "included": GOOD["included"] + ["5 wood, 19°"]}        # another listing's club
    done = D.settle(answer, GOLF, packet("13627933340"))
    assert done["fields"]["included"] == [] and "What's included" not in done["html"]
    assert done["fields"]["highlights"] == GOOD["highlights"] and done["status"] == "trimmed"


def test_a_bad_intro_sentence_goes_alone():
    answer = {**GOOD, "intro": GOOD["intro"] + " It ships with a 3-year warranty."}
    done = D.settle(answer, GOLF, packet("13627933340"))
    assert done["fields"]["intro"] == GOOD["intro"] and done["status"] == "trimmed"


@pytest.mark.parametrize("answer", [None, "sorry", [], {}, {"intro": "", "included": "x", "highlights": None},
                                    {"intro": "무료배송 이벤트!", "included": [], "highlights": [], "conflicts": []}])
def test_no_usable_intro_is_the_title_as_one_sentence(answer):
    done = D.settle(answer, GOLF, packet("12434254421"))
    assert done["status"] == "fallback"
    assert done["html"] == "<p>Majesty 2023 Royal Men's Complete Set.</p>"


def test_the_wrong_country_never_reaches_the_page():
    answer = {**GOOD, "intro": "A men's set. Made in the USA.", "highlights": ["Made in USA."], "included": []}
    done = D.settle(answer, GOLF, packet("7595182520"))                   # origin: do not state
    assert done["fields"] == {"intro": "A men's set.", "included": [], "highlights": []}


def test_lists_and_length_are_capped():
    answer = {"intro": "A set. " + "It is light. " * 60, "included": [f"Item {c}" for c in "abcdefghij"],
              "highlights": ["Light.", "x" * 230, "Stable.", "Soft.", "Easy.", "Plain."], "conflicts": []}
    done = D.settle(answer, GOLF, packet("13627933340"))
    f = done["fields"]
    assert len(f["intro"]) <= D.INTRO_MAX and f["intro"].startswith("A set. It is light.")
    assert len(f["included"]) == 10 and f["highlights"] == ["Light.", "Stable.", "Soft.", "Easy."]
    why = [w for d in done["dropped"] for w in d["why"]]
    assert "too long" in why and "too many" in why and "intro too long" in why and done["status"] == "trimmed"


def test_a_list_of_the_box_over_its_cap_is_not_shown_in_part():
    answer = {**GOOD, "included": [f"Club {c}" for c in "abcdefghijklmn"]}     # 14 items: the last would be the bag
    done = D.settle(answer, GOLF, packet("13627933340"))
    assert done["fields"]["included"] == [] and done["status"] == "trimmed"


def test_an_intro_sentence_that_does_not_fit_is_reported():
    long = "It has a driver, woods, a hybrid, irons and a putter, " + "and more clubs, " * 14 + "all with covers."
    answer = {**GOOD, "intro": f"A women's set. {long} {long} No putter is included."}
    done = D.settle(answer, GOLF, packet("13627933340"))
    assert done["status"] == "trimmed" and len(done["fields"]["intro"]) <= D.INTRO_MAX
    assert any(d["why"] == ["intro too long"] for d in done["dropped"])


def test_the_whole_text_stays_under_the_cap():
    answer = {"intro": "A set.", "included": ["i" * 150] * 8, "highlights": ["h" * 150] * 4, "conflicts": []}
    f = D.settle(answer, GOLF, packet("13627933340"))["fields"]
    assert D._size(f, ["included", "highlights"]) <= D.TOTAL_MAX            # the last highlights go first
    assert len(f["highlights"]) == 1 and len(f["included"]) == 8


def test_text_is_escaped_and_a_profile_without_a_list_does_not_render_it():
    fields = {"intro": "Fit for <everyone> & more.", "highlights": ["USGA & R&A"], "included": ["Driver"]}
    assert D.render(fields, D.PROFILES["default"]) == (
        "<p>Fit for &lt;everyone&gt; &amp; more.</p>\n<h3>Highlights</h3>\n<ul>\n<li>USGA &amp; R&amp;A</li>\n</ul>")


def test_conflicts_go_to_the_row_not_to_the_page():
    done = D.settle({**GOOD, "conflicts": ["Title says 11 clubs, the row says 10."]}, GOLF, packet("13627933340"))
    assert done["conflicts"] == ["Title says 11 clubs, the row says 10."] and "row says" not in done["html"]


# ---- the request --------------------------------------------------------------------------------------------------

def test_one_request_with_the_profiles_schema():
    model, usage = Fake([GOOD]), {}
    answer, by = D.ask(model, "SYS", "MSG", D.schema(GOLF), usage)
    assert answer == GOOD and by == "fake" and usage == {"fake": {"input": 100, "output": 50}}
    assert model.calls == [{"system": "SYS", "messages": [{"role": "user", "content": "MSG"}],
                            "schema": D.schema(GOLF)}]


def test_a_provider_that_is_down_is_skipped_and_rested():
    a, b = Fake([translate.ProviderDown("529")], "a"), Fake([GOOD], "b")
    chain = translate.Chain([a, b], clock=lambda: 0.0)
    assert D.ask(chain, "S", "M", {}, {}) == (GOOD, "b")
    assert [m.name for m in chain.available()] == ["b"]


def test_nobody_answering_is_no_provider():
    chain = translate.Chain([Fake([translate.ProviderDown("x")], "a"), Fake([translate.ProviderDown("y")], "b")])
    with pytest.raises(D.NoProvider):
        D.ask(chain, "S", "M", {}, {})


@pytest.mark.parametrize("reply", [translate.Reply(None, "", "refusal", {}), translate.Reply(None, "{", "max_tokens", {}),
                                   translate.Reply(None, "not json", "end_turn", {})])
def test_a_refusal_a_cut_answer_or_broken_json_is_no_answer_and_no_second_request(reply):
    model = Fake([reply])
    assert D.ask(model, "S", "M", {}, {}) == (None, "fake")
    assert len(model.calls) == 1


# ---- the shop -----------------------------------------------------------------------------------------------------

PIDS = ("13627933340", "12434254421")


@pytest.fixture
def shop(tmp_path, monkeypatch):
    monkeypatch.setattr(PB, "vendor_spellings", lambda store: {})
    d = tmp_path / "fairwardgolf"
    (d / "prepared").mkdir(parents=True)
    (d / "translation").mkdir()
    prepared, translated = [], []
    for pid in PIDS:
        fx = load(pid)
        rel = f"translation/{pid}/description_images.ko.json"
        fx["prepared"]["product"]["description_images_text"] = {"state": "to_translate", "ko": rel}
        (d / rel).parent.mkdir(parents=True)
        (d / rel).write_text(json.dumps({"blocks": fx["blocks"]}, ensure_ascii=False))
        prepared.append(fx["prepared"])
        translated.append(fx["translated"])
    (d / "prepared/products.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in prepared))
    (d / "translation/translated.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n"
                                                              for t in translated))
    return str(tmp_path), [p["key"] for p in prepared]


THIN = {"intro": "A men's right-handed set from the Majesty Royal line with 11 clubs. No bag is included.",
        "included": [], "highlights": ["Made in Japan."], "conflicts": []}


def test_each_product_is_asked_once_and_kept(shop):
    root, keys = shop
    model = Fake([THIN, GOOD])                                           # sorted by key: 12434254421 first
    r = D.run("fairwardgolf", model, root)
    assert [x["status"] for x in r["rows"]] == ["ok", "ok"] and len(model.calls) == 2
    row = D.load_store(os.path.join(root, "fairwardgolf"))[keys[0]]
    assert row["html"].startswith("<p>The PRGR Sweep M17") and row["by"] == "fake" and row["origin"] == "Japan"
    assert row["generated"] == "model" and row["profile"] == "golf_set" and row["left_out"] == {}
    assert "golf club sets" in model.calls[0]["system"] and model.calls[0]["schema"] == D.schema(GOLF)
    again = D.run("fairwardgolf", Fake([]), root)                        # a model that would fail if asked
    assert again["rows"] == [] and again["stale"] == [] and "0 described" in again["report"][0]


def test_only_one_product_and_a_limit(shop):
    root, keys = shop
    model = Fake([GOOD])
    assert [x["key"] for x in D.run("fairwardgolf", model, root, only=keys[0])["rows"]] == [keys[0]]
    r = D.run("fairwardgolf", Fake([]), root, limit=0)
    assert r["rows"] == [] and r["waiting"] == [keys[1]]


def test_without_a_model_nothing_is_asked_or_written(shop):
    root, keys = shop
    r = D.run("fairwardgolf", None, root)
    assert sorted(r["waiting"]) == sorted(keys) and D.load_store(os.path.join(root, "fairwardgolf")) == {}


def test_a_changed_source_is_reported_stale_and_kept_until_forced(shop):
    root, keys = shop
    D.run("fairwardgolf", Fake([THIN, GOOD]), root)
    path = os.path.join(root, "fairwardgolf", "prepared", "products.jsonl")
    rows = [json.loads(x) for x in open(path, encoding="utf-8")]
    for p in rows:
        if p["key"] == keys[0]:
            p["product"]["description_ko"] = "새로운 설명입니다"
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in rows))
    r = D.run("fairwardgolf", Fake([]), root)
    assert r["stale"] == [keys[0]] and r["rows"] == []
    forced = D.run("fairwardgolf", Fake([GOOD]), root, only=keys[0], force=True)
    assert forced["rows"][0]["key"] == keys[0] and D.run("fairwardgolf", Fake([]), root)["stale"] == []


def test_products_already_in_the_shop_are_left_alone_unless_asked(shop):
    root, keys = shop
    ledger = os.path.join(root, "fairwardgolf", "publish", "published.jsonl")
    os.makedirs(os.path.dirname(ledger))
    with open(ledger, "w", encoding="utf-8") as f:
        f.write(json.dumps({"key": keys[0], "status": "published", "digest": "x"}) + "\n")
    model = Fake([THIN, GOOD])
    assert [x["key"] for x in D.run("fairwardgolf", model, root)["rows"]] == [keys[1]]
    assert [x["key"] for x in D.run("fairwardgolf", model, root, published=True)["rows"]] == [keys[0]]


def test_no_provider_stops_the_run_and_writes_nothing(shop):
    root, _ = shop
    with pytest.raises(D.NoProvider):
        D.run("fairwardgolf", translate.Chain([Fake([translate.ProviderDown("x")])]), root)
    assert D.load_store(os.path.join(root, "fairwardgolf")) == {}


def test_an_unusable_answer_still_gives_a_description(shop):
    root, keys = shop
    r = D.run("fairwardgolf", Fake([translate.Reply(None, "", "refusal", {})]), root, only=keys[1])
    row = r["rows"][0]
    assert row["status"] == "fallback" and row["html"] == "<p>Majesty 2023 Royal Men's Complete Set.</p>"
    assert "fallback" in r["report"][1] and "no usable answer" in r["report"][1]


def test_a_job_s_one_product_run_leaves_the_shops_report_alone(shop):
    root, keys = shop
    D.run("fairwardgolf", Fake([THIN]), root, limit=1)
    report = os.path.join(root, "fairwardgolf", "translation", D.REPORT)
    before = open(report, encoding="utf-8").read()
    D.run("fairwardgolf", Fake([GOOD]), root, only=keys[0])
    assert open(report, encoding="utf-8").read() == before


def test_the_cli_refuses_a_key_the_shop_does_not_have(shop, capsys):
    root, _ = shop
    with pytest.raises(SystemExit) as e:
        D.main(["fairwardgolf", "--shops-root", root, "--only", "13627933340", "--offline"])
    assert e.value.code == 2 and "no such product key" in capsys.readouterr().err


def test_a_torn_last_line_of_the_store_is_ignored(shop):
    root, keys = shop
    D.run("fairwardgolf", Fake([GOOD]), root, only=keys[0])
    with open(os.path.join(root, "fairwardgolf", "translation", D.STORE), "a", encoding="utf-8") as f:
        f.write('{"key": "x", "html": ')
    assert list(D.load_store(os.path.join(root, "fairwardgolf"))) == [keys[0]]


# ---- the way into publication -------------------------------------------------------------------------------------

def test_the_digest_changes_only_for_a_product_that_has_a_description():
    from test_publish import _product
    prepared, translated, placement = _product()
    plain = PB.inputs_digest(prepared, translated, placement, "fairwardgolf", [])
    assert plain == sp.digest({"prepared": prepared, "en": translated.get("en"), "placement": placement,
                               "pricing": policy("fairwardgolf").describe(), "format": PB.FORMAT,
                               "payload": sp.VERSION, "gallery": []})       # as before describe.py: no new key
    assert PB.inputs_digest(prepared, translated, placement, "fairwardgolf", [], "") == plain
    assert PB.inputs_digest(prepared, translated, placement, "fairwardgolf", [], None) == plain
    assert PB.inputs_digest(prepared, translated, placement, "fairwardgolf", [], "<p>A set.</p>") != plain


def test_the_payload_body_is_the_description():
    from test_publish import _product
    prepared, translated, placement = _product()
    args = (prepared, translated, placement, policy("fairwardgolf"), "gid://shopify/Location/1", [])
    assert sp.product_input(*args)["descriptionHtml"] == ""
    assert sp.product_input(*args, description_html="<p>A set.</p>")["descriptionHtml"] == "<p>A set.</p>"


def test_publish_sends_the_stored_description_and_a_new_one_sends_the_product_again(tmp_path):
    from test_publish import KEY, _shop
    shop = _shop(tmp_path)
    products, files = FakeProducts(), FakeFiles()
    PB.publish_one(shop, KEY, products, files, IDS)
    assert products.sent[0][0]["descriptionHtml"] == ""
    assert PB.publish_one(shop, KEY, products, files, IDS)["status"] == "skipped"
    with open(os.path.join(shop.dir, "translation", D.STORE), "w", encoding="utf-8") as f:
        f.write(json.dumps({"key": KEY, "html": "<p>A set.</p>"}) + "\n")
    assert PB.publish_one(shop, KEY, products, files, IDS)["status"] == "published"
    assert products.sent[1][0]["descriptionHtml"] == "<p>A set.</p>"
    assert PB.publish_one(shop, KEY, products, files, IDS)["status"] == "skipped"
