"""The title rules of the owner's wedge-set review (2026-11-16): "or single" dropped, glued lofts split, the seller's
"db" marker removed (translation_rules.sanitize, before the model), and an import title's appended option named for
the model to drop (spec_variants.title_variant_tail -> note title_names_one_variant). Real titles and option rows of
fairwardgolf; offline."""
import json
import os

import pytest

import translate as T
from spec_variants import title_variant_tail
from translation_rules import numbers, sanitize

TENANT = "Fairward Golf"
WEDGES = "50002783"


@pytest.mark.parametrize("ko, out", [
    # (a) "or single": the shop sells sets only
    ("남성용 단조 골프 웨지 세트 또는 개인용 48/50/52/54/56/58/60도 간격",                         # 13016551520
     "남성용 단조 골프 웨지 세트 48/50/52/54/56/58/60° 간격"),
    ("야마토 풀페이스 골프 웨지 세트 또는 개별 50/52/54/56/58/60 단조 갭 샌드",                    # 13016112970
     "야마토 풀페이스 골프 웨지 세트 50/52/54/56/58/60 단조 갭 샌드"),
    ("야마토 골프 웨지 세트 또는 개인 50/52/54/56/58/60 갭 샌드 남녀 밀링",                       # 13363853270
     "야마토 골프 웨지 세트 50/52/54/56/58/60 갭 샌드 남녀 밀링"),
    ("남성 또는 개인용 라즈러스 프리미엄 단조 골프 웨지 세트 - 50 52 54 56 58",                    # 13016648376
     "남성 라즈러스 프리미엄 단조 골프 웨지 세트 - 50 52 54 56 58"),
    ("야마토 왼손잡이 골프 웨지 세트 52 56 60 및 개별 – 단조 CNC 밀드 LH01-52 56 60 Degree",      # 13016883852
     "야마토 왼손잡이 골프 웨지 세트 52 56 60 – 단조 CNC 밀드 LH01-52 56 60 Degree"),
    ("Golf Wedge Set or Single Wedge 52 56 60", "Golf Wedge Set 52 56 60"),
    # (b) a glued run of lofts
    ("XINGGM 남성용 단조 골프 웨지 세트 개인용 48505254565860도 간격 남성 Silver",                  # 13372276089
     "XINGGM 남성용 단조 골프 웨지 세트 48°/50°/52°/54°/56°/58°/60° 간격 남성 Silver"),
    ("Alvo Golf 프리미엄 풀페이스 골프 웨지 세트 3 525660도 로브 갭 샌드 남성",                     # 13389307551
     "Alvo Golf 프리미엄 풀페이스 골프 웨지 세트 3 52°/56°/60° 로브 갭 샌드 남성"),
    ("T WINSOLOGY 골프 샌드 웨지 세트 남녀용 505458도 클럽 오른손용 피치 선물",                    # 13372006463
     "T WINSOLOGY 골프 샌드 웨지 세트 남녀용 50°/54°/58° 클럽 오른손용 피치 선물"),
    ("69 도 골프 남녀 웨지 세트5460 세트브 샌드 피칭",                                            # 13370257430
     "69° 골프 남녀 웨지 세트 54°/60° 세트브 샌드 피칭"),
    ("프로페셔널 오픈 690 골프 웨지 세트 5256606468 3Piece Set 525660 Right",                    # 13566630297
     "프로페셔널 오픈 690 골프 웨지 세트 52°/56°/60°/64°/68° 3Piece Set 52°/56°/60° Right"),
    ("골프 웨지 세트/개별 52 56 60도", "골프 웨지 세트 52 56 60°"),             # "/" right after 세트
    ("골프 웨지 세트 4856도 샌드", "골프 웨지 세트 48°/56° 샌드"),                  # two lofts and 도
    # nine and ten lofts (C24, 2026-11-17): the limit was eight
    ("XINGGM 웨지 남성용 개별용 위조 골프 세트 48505254565860687072° Black/Right Handed",          # 13377515123
     "XINGGM 웨지 남성용 개별용 위조 골프 세트 48°/50°/52°/54°/56°/58°/60°/68°/70°/72° Black/Right Handed"),
    ("XINGGM 남성용 개인용 위조 골프 웨지 세트 485052545860687072° RH Black/Right Handed",         # 13364055281
     "XINGGM 남성용 개인용 위조 골프 웨지 세트 48°/50°/52°/54°/58°/60°/68°/70°/72° RH Black/Right Handed"),
    ("골프 웨지 세트 or single wedge 52", "골프 웨지 세트 52"),
    # (c) the seller's marker
    ("A11N SPORTS의 위조 골프 웨지 세트 db4P Bronze", "A11N SPORTS의 위조 골프 웨지 세트 Bronze"),     # 13552318731
    ("프리미엄 풀페이스 골프 웨지 세트 52/56/60도 샌드 – 단조 오른손 웨지, dbQF Black 52",          # 13552339143
     "프리미엄 풀페이스 골프 웨지 세트 52/56/60° 샌드 – 단조 오른손 웨지, Black 52"),
])
def test_wedge_title_rules(ko, out):
    assert sanitize("title", ko, TENANT, WEDGES) == out


@pytest.mark.parametrize("ko", [
    "골프 웨지 세트 개별포장 52 56 60도",          # 개별포장 (packed one by one) is not "single"
    "웨지 세트 605652",                          # lofts not going up: not a list
    "웨지 GRF539-5256 세트",                      # a code: "-" before
    "웨지 세트 52566",                            # an odd run
    "웨지 세트 i60R 샤프트",                       # a shaft code
    "PGM 웨지 세트 2024 신형",                     # a year is no loft
    "XINGGM 단조 골프 웨지 세트 48-72도",           # a range, the general rule only
    "프로페셔널 오픈 690 골프 웨지 세트",            # three digits
    "남자 개인 주니어 8세 라임 올리마르 ATS D6U 시리즈 골프 블루 클럽 DB6",   # Orlimar's DB6 (12592888269) stays
    "웨지 세트 dbx4 52",                          # not the marker's shape
    # the review of these rules (2026-11-16): "or" inside a Latin word, "/싱글" not after 세트 / 웨지, two lofts with
    # no 도 / ° / 세트 next to them, a 도 that starts a Korean word
    "Razor 단품 웨지 세트",
    "Color 싱글 웨지 세트",
    "RTX For 개인 웨지 세트",
    "웨지 세트 스틸/싱글 벤드",
    "모델 4856 웨지 세트",
    "6072 스핀 웨지 세트",
    "웨지 세트 5256 도매",
    "웨지 세트 525660도클럽",
])
def test_wedge_title_rules_leave(ko):
    general = sanitize("title", ko, TENANT, "50002788")          # what the general rules alone make of it
    assert sanitize("title", ko, TENANT, WEDGES) == general


def test_title_rules_only_titles_and_wedges():
    """The rules are the wedge category's titles': an option value, another category's title, a review stay."""
    ko = "골프 웨지 세트 또는 개별 525660도"
    assert sanitize("option_value", ko, TENANT, WEDGES) == "골프 웨지 세트 또는 개별 525660°"
    assert sanitize("title", ko, TENANT, "50002788") == "골프 웨지 세트 또는 개별 525660°"
    assert sanitize("review", "세트 db4P", TENANT, WEDGES) == "세트 db4P"
    # the marker goes from every category's title (13555308677, junior sets)
    junior = "PGM 주니어 컴플리트 오른손잡이 9피스"
    assert sanitize("title", junior + " db9N", TENANT, "50002787") == sanitize("title", junior, TENANT, "50002787")


@pytest.mark.parametrize("ko, category, out", [
    # C07 (2026-11-17): the seller's product code at the end of a title goes, in every category
    ("(병행) 미스테리 R라인 웨지 세트 52도/57도 WA3817570", WEDGES,                                 # 12789874438
     "(병행) 미스테리 R라인 웨지 세트 52°/57°"),
    ("그라인드 웍스 52도 56도 웨지 세트 다골 S200 품번 1116", WEDGES,                             # 12748952803
     "그라인드 웍스 52° 56° 웨지 세트 다골 S200"),
    ("(캘러웨이코리아정품) 26년 캘러웨이 레바 여성골프채 풀세트 SA3882511", "50002788",             # 13719765598
     "(캘러웨이코리아정품) 26년 캘러웨이 레바 여성골프채 풀세트"),
    ("투어엣지 바주카 370 남성용 스틸 골프채 풀세트 P SA3547472", "50002788",                      # 12429105179
     "투어엣지 바주카 370 남성용 스틸 골프채 풀세트 P"),
])
def test_a_seller_code_at_the_end_of_a_title_goes(ko, category, out):
    assert sanitize("title", ko, TENANT, category) == out
    assert not {"3817570", "1116", "3882511", "3547472"} & set(numbers(sanitize("title", ko, TENANT, category)))


@pytest.mark.parametrize("ko, code", [
    ("웨지 세트 WA3817568 52도 56도", "WA3817568"),       # not at the end: kept
    ("웨지 세트 NWA3817568", "NWA3817568"),               # glued to a letter: a model code
    ("웨지 세트 WA381756", "WA381756"),                   # six digits
    ("웨지 세트 WA38175681", "WA38175681"),               # eight digits
    ("웨지 세트 상품품번 1116", "1116"),                   # 품번 inside a word
    ("웨지 세트 품번 12", "12"),                          # too short for a code
])
def test_a_code_like_word_that_is_not_the_sellers_code_stays(ko, code):
    assert code in sanitize("title", ko, TENANT, WEDGES)
    assert sanitize("option_value", "52도 WA3817568", TENANT, WEDGES).endswith("WA3817568")   # titles only


def test_split_lofts_survive_the_number_check():
    """The model may write the split list: "525660" was a number the check asked for whole."""
    item = {"id": "t", "kind": "title", "source": sanitize("title", "골프 웨지 세트 3 525660도", TENANT, WEDGES)}
    assert numbers(item["source"]) == ["3", "52", "56", "60"]
    ok, failed = T.verify([item], json.dumps({"items": [{"id": "t", "en": "3-Piece Wedge Set 52°/56°/60°"}]}))
    assert ok == {"t": "3-Piece Wedge Set 52°/56°/60°"} and not failed


# the page's option rows as collected (id, options), the first is the page's default
XINGGM = [{"id": "58033737065", "options": ["58 Degree", "Silver RH"]},
          {"id": "58033737066", "options": ["58 Degree", "Black RH"]},
          {"id": "58033737080", "options": ["52 60 Degree Set", "Black RH"]},
          {"id": "58033737081", "options": ["56 60 Degree Set", "Black RH"]}]
HIREKO = [{"id": "1", "options": ["3Piece Set 525660", "Right"]},
          {"id": "2", "options": ["4Piece Set 52566064", "Right"]},
          {"id": "3", "options": ["52 Degree", "Right"]}]


def test_variant_tail_named():
    title = "XINGGM 단조 골프 웨지 세트 48-72도 오른손용 샌드 갭 롭 스핀 강화 벙커 탈출 용이 골프 클럽 58 Degree Silver RH"
    assert title_variant_tail(title, XINGGM, {"58033737080", "58033737081"}) == "58 Degree Silver RH"   # 13468791008
    title = "프로페셔널 오픈 690 골프 웨지 세트 5256606468 3Piece Set 525660 Right"
    assert title_variant_tail(title, HIREKO, {"1", "2"}) == "3Piece Set 525660 Right"      # one of two sold
    assert title_variant_tail("A11N SPORTS의 위조 골프 웨지 세트 db4P Bronze",                  # 13552318731
                              [{"id": "a", "options": ["Bronze"]}, {"id": "b", "options": ["Black"]}],
                              {"a", "b"}) == "Bronze"


def test_a_placeholder_tail_is_named():
    """C53 (2026-11-17): the page's placeholder value appended to the title ("… 오른손 옵션 1"), even as the one
    variant sold (13566628089) and with Hangul; a title that only is the placeholder, or a Latin title, is not."""
    rows = [{"id": "1", "options": ["옵션 1"]}, {"id": "2", "options": ["Bronze"]}]
    title = "핀클리 위조 골프 웨지 세트 3 52 56 60도 밀드 페이스로 스핀 오른손 옵션 1"
    assert title_variant_tail(title, rows, {"1"}) == "옵션 1"
    assert title_variant_tail("WENGH 골프 웨지 52 56 60 세트 - 레인보우로 Option 2",                # 13566627679's kind
                              [{"id": "1", "options": ["Option 2"]}], {"1"}) == "Option 2"
    assert title_variant_tail("옵션 1", rows, {"1"}) is None
    assert title_variant_tail("Golf Wedge Set 옵션 1", rows, {"1"}) is None
    assert title_variant_tail("골프 웨지 세트 옵션 12개", [{"id": "1", "options": ["옵션 1"]}], {"1"}) is None


def test_variant_tail_not_named():
    title = "프로페셔널 오픈 690 골프 웨지 세트 3Piece Set 525660 Right"
    assert title_variant_tail(title, HIREKO, {"1"}) is None                        # the only variant sold
    assert title_variant_tail("3Piece Set 525660 Right", HIREKO, {"2"}) is None   # the whole title
    assert title_variant_tail("Hireko Open 690 Wedge Set 3Piece Set 525660 Right", HIREKO, {"2"}) is None  # no Hangul
    assert title_variant_tail("골프 웨지 세트 3Piece Set 525660 Right 블랙", HIREKO, {"2"}) is None   # not the end
    assert title_variant_tail("골프 웨지 세트 xRight", [{"id": "1", "options": ["Right"]}], {"2"}) is None  # a word's part
    assert title_variant_tail("골프 웨지 세트 블랙", [{"id": "1", "options": ["블랙"]}], {"2"}) is None   # a Korean value
    # the review of this rule (2026-11-16): a ", " inside the value, a bare number
    assert title_variant_tail("골프 웨지 세트 Black, Right", [{"id": "1", "options": ["Black, Right"]}], {"2"}) is None
    assert title_variant_tail("골프 웨지 세트 52/56/60도 세트 52", [{"id": "1", "options": ["52"]}], {"2"}) is None
    assert title_variant_tail("골프 웨지 세트 52 60", [{"id": "1", "options": ["52", "60"]}], {"2"}) is None


def test_tail_reaches_the_model_as_a_drop(tmp_path):
    """XINGGM 13468791008 (fixtures/collected, prepared golden): the transform names the appended option, the stage
    asks the model to drop it and its 58 need not survive; the title is otherwise the rules' source."""
    import translation_dicts as D
    path = os.path.join(os.path.dirname(__file__), "fixtures", "prepared", "13468791008.json")
    with open(path, encoding="utf-8") as f:
        prepared = json.load(f)
    dicts = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    assert title["drop"] == ["58 Degree Silver RH"]
    assert "58" not in numbers(T._checked_source(title)) and "72" in numbers(T._checked_source(title))


def _sets(*values):
    return [{"options_ko": [v]} for v in values]


def test_title_lofts_not_sold():
    """C46 (2026-11-17): the title lists lofts no set sold has, or the union of several sets as one list."""
    from spec_variants import title_lofts_not_sold as lns
    sold = _sets("50 54 58 Degree Set", "52 56 60 Degree Set")
    assert lns("야마토 골프 웨지 세트 또는 개인 50/52/54/56/58/60 갭 샌드", sold, []) == \
        "50/52/54/56/58/60 (sold: 50/54/58 | 52/56/60)"                                   # 13363853270: the union
    assert lns("야마토 골프 웨지 세트 505254565860 갭", sold, []) == "50/52/54/56/58/60 (sold: 50/54/58 | 52/56/60)"
    assert lns("ALVO 웨지 세트 52/56/60/70도", _sets("52 56 60도 세트"), []) == "52/56/60/70 (sold: 52/56/60)"
    assert lns("Mile High Life 웨지 세트 갭 50 Degrees", _sets("52/58 세트"), []) == "50 (sold: 52/58)"   # 13377524996
    # the facts' one set when no variant is kept
    assert lns("웨지 세트 52 56 60 64도", [], [{"value_ko": "52 56 60도 세트"}]) == "52/56/60/64 (sold: 52/56/60)"
    # fine: a run that is one set sold; two sets each closed by 도 (10361963641); lofts unknown
    assert lns("야마토 웨지 세트 52 56 60도", sold, []) is None
    assert lns("[52/56도 50/56도 세트] ZESTAIM 웨지세트", _sets("52/56도 세트", "50/56도 세트"), []) is None
    assert lns("웨지 세트 50/52/54/56/58/60", _sets("Black", "Silver"), []) is None              # no lofts sold
    assert lns("웨지 세트 50/52/54/56/58/60", _sets("52 56 60 Degree Set", "Black"), []) is None  # one names none
    assert lns("웨지 세트 50/52/54", [], [{"value_ko": "52 56도"}, {"value_ko": "50 54도"}]) is None  # two facts
    # a number with a unit is no loft (the review, 2026-11-17): a length, an age, a weight; "세트" is a set word
    one = _sets("52 56 60도 세트")
    assert lns("드라이버 45인치 웨지 52 56 60도 세트", one, []) is None
    assert lns("골프키 58인치+ 웨지 52 56 60 세트", one, []) is None                     # Mazek's kind, 13389972303
    assert lns("웨지 세트 50대 남성 52 56 60도", one, []) is None
    assert lns("웨지 52 56 60 58인치 60 kg", one, []) is None                          # a unit after a run's last
    assert lns("웨지 52 56 60 64 세트", one, []) == "52/56/60/64 (sold: 52/56/60)"     # 64 세트: a loft
    assert lns("BYBOMYA 단조 골프 웨지 50 52 54 56 58 60 개별 또는 세트", sold, []) == \
        "50/52/54/56/58/60 (sold: 50/54/58 | 52/56/60)"                                # 13603807427: 개별, a word
    assert lns("웨지 52 56 60 세트 48-72도", one, []) == "48/72 (sold: 52/56/60)"      # a range's ends still count


def test_title_cut():
    """C48 (2026-11-17): an agency wedge title Naver cut inside its loft list at 46-50 characters."""
    from spec_variants import title_cut
    t = "마제크 그래파이트 마젝 골프 남자 완비 웨지 세트 52° 갭 웨지GW 56° 샌드 웨지S"                     # 13370558777
    assert title_cut(t) == {"partial": "S", "lofts": 2, "count": False}
    assert title_cut("Ram 단조 골프채 골프 웨지 램골프프로 스핀3 웨지세트 - 52° 간격 56° 모래 6") == \
        {"partial": "6", "lofts": 2, "count": False}                                           # 13386317152
    assert title_cut("POSSOT 3 PCS 웨지 세트 또는 개별 골프 남녀 오른손용 52 갭 56 샌드") == \
        {"partial": "", "lofts": 2, "count": True}                                             # 13016426814
    assert title_cut(t[:45]) is None                                                           # too short
    assert title_cut("골프 웨지 세트 52 56 60도 남성용 오른손잡이 그라파이트 시니어 빅앤톨 플러스 52") is None   # lofts before
    assert title_cut("골프 웨지 세트 남성용 오른손잡이 프리미엄 단조 밀링 페이스 블랙 52 56 60도") is None   # three, uncut


def test_the_wedge_notes_reach_the_model(tmp_path):
    """C46 / C48: the notes become the title's context; the lofts not sold and the cut word need not survive."""
    import translation_dicts as D
    path = os.path.join(os.path.dirname(__file__), "fixtures", "prepared", "13468791008.json")
    with open(path, encoding="utf-8") as f:
        prepared = json.load(f)
    prepared["product"]["title_ko"] = title_ko = "골프 웨지 세트 남성용 오른손잡이 그라파이트 시니어 50/52/54/56 S"
    prepared["texts"] = [{**t, "ko": title_ko} if t["kind"] == "title" else t for t in prepared["texts"]]
    prepared["notes"] = [n for n in prepared["notes"] if n["code"] not in ("title_names_one_variant", "title_lofts_not_sold")] + [
        {"code": "title_lofts_not_sold", "detail": "50/52/54/56 (sold: 52/56 | 50/54)"},
        {"code": "title_cut", "detail": "'S' cut, 4 lofts written"}]
    dicts = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    assert "not one set sold: 50/52/54/56 (sold: 52/56 | 50/54)" in title["context"]
    assert "'S' at its end is a cut word" in title["context"]
    ok, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en":
                                                          "Men's Senior Graphite Wedge Set, 52°/56° or 50°/54°"}]}))
    assert ok and not failed
    ok, failed = T.verify([{**title, "free_numbers": []}], json.dumps({"items": [{"id": title["id"], "en":
                                                                                  "Men's Wedge Set 52°/56°"}]}))
    assert not ok and "numbers changed" in failed[0]["problems"][0]
    assert T._checked_source({"kind": "title", "source": "웨지 S 세트 52 S", "cut": "S"}).split() == ["웨지", "S", "세트", "52"]


def test_a_sellers_forged_on_every_title_with_a_silent_page():
    """C67 (2026-11-17): the agency 102454334 writes 단조 into its titles; with nothing outside the title saying
    forged, the word is the seller's habit. A line copying the title is no source; other sellers are left alone."""
    from spec_variants import title_word_unproven
    junior = "올리마르 우타 웨지 단조 골프채 ATS 주니어 보이즈 블루라임 시리즈 개별 골프클럽 5세 Right Hand"   # 13383523012
    typed = "올리마르 우타 웨지 단조 골프채 ATS 주니어 보이즈 블루라임 시리즈 개별 골프클럽 5세\n- Ages 5 and up"
    assert title_word_unproven(junior, "102454334", [typed, "Alloy Steel\nGraphite", ""]) == ["단조"]
    lazrus = "LAZRUS GOLF 라즈루스 프리미엄 단조 골프 웨지 남성용 세트 - 5256 60도 Silver Right Handed"  # 13389498451
    bullets = ("LAZRUS GOLF 라즈루스 프리미엄 단조 골프 웨지 남성용 세트 - 5256 60도\n"
               "- ENHANCED SPIN AND CONTROL: The micro milled face of Lazarus Premium Quality Forged Golf Wedge Set")
    assert title_word_unproven(lazrus, "102454334", [bullets]) == []
    assert title_word_unproven(junior, "102454334", ["", "", "B620 CS FORGED"]) == []     # the images' text
    assert title_word_unproven(junior, "102454334", ["", "연철 단조 헤드", ""]) == []       # a spec value
    assert title_word_unproven("야마토 포지드 웨지 세트 52 56 60", "102454334", []) == ["포지드"]
    assert title_word_unproven(junior, "1100167681", []) == []                         # another seller's 단조
    assert title_word_unproven("마제크 웨지 세트 52 56", "102454334", []) == []
    assert title_word_unproven(junior, "102454334", ["Forgiving sole for beginners"]) == ["단조"]   # not "forged"
    majek = "마제크 우타 단조 웨지 골프용 마젝골프 시니어 남자 컴플리트 세트 52° 갭 웨지GW 5"            # 13383752241
    ocr = "마제크 우타 단조 웨지 골프용 마적골프 시니어 남자 컴플리트 세\n트 52'캡웨지GW 5\nMore Forgiving"
    assert title_word_unproven(majek, "102454334", ["", "", ocr]) == ["단조"]   # the title as OCR misread it
    assert title_word_unproven(majek, "102454334", ["", "", "마제크 웨지 헤드는 연철 단조 공법으로 만든 제품"]) == []


def test_the_unproven_word_reaches_the_model(tmp_path):
    """C67: the note title_word_unproven becomes the title's context, joined to the other notes' context."""
    import translation_dicts as D
    path = os.path.join(os.path.dirname(__file__), "fixtures", "prepared", "13468791008.json")
    with open(path, encoding="utf-8") as f:
        prepared = json.load(f)
    prepared["product"]["title_ko"] = title_ko = "마제크 단조 웨지 우타 골프채 골프 남자 컴플리트 세트 52° 갭 웨지GW 56° 샌드"
    prepared["texts"] = [{**t, "ko": title_ko} if t["kind"] == "title" else t for t in prepared["texts"]]
    prepared["notes"] = [n for n in prepared["notes"] if n["code"] not in ("title_names_one_variant", "title_lofts_not_sold")] + [
        {"code": "title_cut", "detail": "'샌' cut, 2 lofts written"},
        {"code": "title_word_unproven", "detail": "단조"}]
    dicts = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    assert "Naver cut this title" in title["context"]
    assert "단조 (forged): the seller writes it on its titles" in title["context"]
    assert title["drop"] == ["단조"]
    ok, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en":
                                                          "Majek Men's Wedge Set, 52° Gap Wedge GW and 56° Sand"}]}))
    assert ok and not failed
    prepared["notes"] = [n for n in prepared["notes"] if n["code"] != "title_word_unproven"]
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    assert "forged" not in next(i for i in pending if i["kind"] == "title")["context"]


def test_every_shop_selling_a_category_with_title_rules_sells_it_as_sets_only():
    """TITLE_RULES["50002783"] drops "or single" because the shop keeps no one-club variant (sets_only); a shop that
    takes 50002783 without sets_only would sell the single its title no longer names (2026-11-16)."""
    from transform_shops import RULES
    from translation_rules import TITLE_RULES
    sellers = [(shop, rules.categories[cat]) for shop, rules in RULES.items() for cat in TITLE_RULES
               if cat in rules.categories]
    assert sellers and all(cat.sets_only for _, cat in sellers), [s for s, c in sellers if not c.sets_only]


def test_a_knit_titles_size_run_may_be_left_out(tmp_path):
    """50002797 (the owner, 2026-11-19): the brief keeps sizes out of a knit cardigan's English title; the size run's
    numbers need not survive, the model code's still must."""
    import translation_dicts as D
    path = os.path.join(os.path.dirname(__file__), "fixtures", "prepared", "13468791008.json")
    with open(path, encoding="utf-8") as f:
        prepared = json.load(f)
    title_ko = "[현대백화점] PXG 여성 바시티 브이넥 가디건 PHFPW520 55 66 77 울 100%"
    prepared["source"]["category_id"] = "50002797"
    prepared["notes"] = []
    prepared["product"]["title_ko"] = title_ko
    prepared["texts"] = [{**t, "ko": title_ko} if t["kind"] == "title" else t for t in prepared["texts"]]
    dicts = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    assert title["free_numbers"] == ["55", "66", "77"]
    ok, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en":
                                                          "PXG Women's Varsity V-Neck Cardigan PHFPW520, 100% Wool"}]}))
    assert ok and not failed
    _, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en": "PXG Women's Varsity Cardigan"}]}))
    assert failed and failed[0]["problems"] == ["numbers changed: missing 100, 520", "codes lost: missing PHFPW520"]
    prepared["source"]["category_id"] = "50002784"                       # a club title keeps its numbers
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    assert "free_numbers" not in next(i for i in pending if i["kind"] == "title")


def test_a_windbreaker_titles_season_code_may_be_left_out(tmp_path):
    """50002798 (the second windbreaker pilot, 2026-11-21): "22ss" / "23FW" left out of the English title failed
    "codes lost" while only the digits were freed; the whole season code is dropped from the check, the model code
    still must survive."""
    import translation_dicts as D
    path = os.path.join(os.path.dirname(__file__), "fixtures", "prepared", "13468791008.json")
    with open(path, encoding="utf-8") as f:
        prepared = json.load(f)
    title_ko = "제이린드버그 22ss 여성골프웨어 바람막이 자켓 텐리 Tenley 23FW GWJT07"
    prepared["source"]["category_id"] = "50002798"
    prepared["notes"] = []
    prepared["product"]["title_ko"] = title_ko
    prepared["texts"] = [{**t, "ko": title_ko} if t["kind"] == "title" else t for t in prepared["texts"]]
    dicts = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    _, _, pending = T.plan(prepared, dicts, {}, TENANT)
    title = next(i for i in pending if i["kind"] == "title")
    assert title["drop"] == ["22ss", "23FW"]
    ok, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en":
                                                          "J.Lindeberg Women's Tenley Golf Windbreaker GWJT07"}]}))
    assert ok and not failed
    _, failed = T.verify([title], json.dumps({"items": [{"id": title["id"], "en": "J.Lindeberg Women's Windbreaker"}]}))
    assert failed and failed[0]["problems"] == ["numbers changed: missing 07", "codes lost: missing GWJT07"]


def test_a_model_codes_tail_is_no_size():
    """A code ending in a size number (K90, C100) keeps its number: only free-standing sizes are freed (review
    2026-11-19)."""
    sizes = T.TITLE_SIZES["50002797"]
    assert T.TITLE_SIZES["50002798"] is sizes                             # windbreakers: the same sizes (2026-11-20)
    assert T.TITLE_SIZES["50002799"] is sizes                             # 재킷, the same section (2026-11-21)
    assert T.TITLE_SIZES["50002796"] is sizes                             # long-sleeve tops (2026-11-21)
    # a season code's digits are freed too (2026-11-20, the windbreaker pilot: "26FW" kept in a TaylorMade title)
    assert T.TITLE_SEASON.findall("테일러메이드 26FW 여성 바람막이 TJ6-72HG01-199 2025 SS 23F/W") == ["26", "2025", "23"]
    assert T.TITLE_SEASON.findall("BGBWSJ704 K90 FW 3레이어") == []
    # a garment's model year (2026-11-24, the rainwear pilot: Titleist "... 상하세트 2024년 모델"); a model code's digits never
    assert [m.group(0) for m in T.TITLE_MODEL_YEAR.finditer("레인웨어 상하세트 2024년 모델 / 2025년형 / 2023 모델")] == [
        "2024년 모델", "2025년형", "2023 모델"]
    assert not list(T.TITLE_MODEL_YEAR.finditer("TSMR2024 레인슈트 C25989100 2024"))
    assert sizes.findall("WWW24K90 여성 가디건 C100 55 66 77 90 울 100%") == ["55", "66", "77", "90"]


def test_a_pack_and_a_choice_count_may_be_left_out():
    """The tops pilot (2026-11-21): "1+1" is a 2-Pack, "3종 택1" / "6컬러" a choice of colours: their digits are free."""
    assert [m.group(0) for m in T.TITLE_PICK.finditer("JN 여성 기모 이너 1+1 / 울시 셔츠 3종 택1 6컬러 PKWCW4218-51")] == [
        "1+1", "3종 택1", "6컬러"]
    assert not list(T.TITLE_PICK.finditer("PKWCW4218-51 2025 7LOTS907"))
    # 2026-11-22: the unit rule writes 종 as pcs first ("2종 택1" reaches the check as "2 pcs 택1"); a bare "13 pcs" is no pick
    assert [m.group(0) for m in T.TITLE_PICK.finditer("[울시] 남성 풀오버 니트 2 pcs 택1")] == ["2 pcs 택1"]
    assert not list(T.TITLE_PICK.finditer("13 pcs 풀세트"))


def test_a_choice_of_styles_is_never_a_pack_in_english():
    """The men's tops pilot (2026-11-22): "[울시] 남성 소프트터치 카라 풀오버 니트 2종 택1" went out as "... 2 pcs, Choose 1"
    and "4종 택1" as "Choose 1 of 4 pcs": a choice reads as a bundle; the check sends such a title back."""
    item = {"id": "t", "kind": "title", "source": "[울시] 남성 소프트터치 카라 풀오버 니트 2종 택1", "drop": ["2종 택1"],
            "pick": True}
    for bad in ("Wolsey Men's Soft-Touch Collared Knit Pullover 2 pcs, Choose 1",
                "Wolsey Men's Classic Fleece-Lined Top, Choose 1 of 4 pcs"):
        assert "a choice of styles" in T.verify([item], json.dumps({"items": [{"id": "t", "en": bad}]}))[1][0]["problems"][0]
    good = "Wolsey Men's Soft-Touch Collared Knit Pullover"
    assert T.verify([item], json.dumps({"items": [{"id": "t", "en": good}]}))[0] == {"t": good}
    pack = {**item, "source": "JN 남성 기모 이너 1+1", "drop": ["1+1"], "pick": False}
    assert T.verify([pack], json.dumps({"items": [{"id": "t", "en": "JN Men's Fleece Base Layer 2-Pack"}]}))[1] == []


def test_a_size_letter_in_a_garment_title_may_be_left_out():
    """5527933102 (the skirts pilot, 2026-11-22): "여성골프웨어 백 플리츠 골프스커트 스판 주름 XL 골프치마 빅사이즈" failed
    "codes lost: missing XL"; a size letter standing alone is free, one inside a code (AXL22) is not."""
    assert T.TITLE_SIZE_LETTERS.findall("스판 주름 XL 골프치마 FREE") == ["XL", "FREE"]
    assert not T.TITLE_SIZE_LETTERS.findall("AXL22 XL2")
    item = {"id": "t", "kind": "title", "source": "여성골프웨어 백 플리츠 골프스커트 스판 주름 XL 골프치마", "free_codes": ["XL"]}
    assert T.verify([item], json.dumps({"items": [{"id": "t", "en": "Women's Back-Pleated Stretch Golf Skirt"}]}))[1] == []


# ---- golf pants titles (50002801, the pilot review 2026-11-24): real titles and option rows of fairwardgolf --------

PANTS = "50002801"


def _pants_title(tmp_path, title_ko, options=(), notes=(), composition=()):
    """The title item plan() asks the model for: a pants product with these title, options, notes and fibre rows."""
    import translation_dicts as D
    prepared = {"key": "fairwardgolf:naver:1:1", "source": {"category_id": PANTS},
                "notes": [{"code": c, "detail": d} for c, d in notes],
                "product": {"title_ko": title_ko, "options": [{"name_ko": n, "values_ko": list(v)} for n, v in options],
                            "composition_ko": [{"label_ko": "소재", "value_ko": v} for v in composition]},
                "texts": [{"id": "title:t", "kind": "title", "ko": title_ko}]}
    dicts = D.Dictionaries(str(tmp_path / "live"), str(tmp_path / "none"))
    return next(i for i in T.plan(prepared, dicts, {}, TENANT)[2] if i["kind"] == "title")


def _answer(item, en):
    ok, failed = T.verify([item], json.dumps({"items": [{"id": item["id"], "en": en}]}))
    return ok.get(item["id"]), [p for f in failed for p in f["problems"]]


def test_a_pants_titles_size_count_and_size_run_may_be_left_out(tmp_path):
    """9232590815: "... 연습복 3XL" failed "numbers changed: missing 3" (the letters were free, not their count);
    5093872434: "... 빅사이즈 30-46size" failed "missing 46, codes lost: missing 46SIZE" (46 over the waists, the
    run glued to SIZE; the note's "30" went before the run and broke it)."""
    item = _pants_title(tmp_path, "여성골프바지 골프 조거팬츠 카고바지 빅사이즈 연습복 3XL",
                        [("사이즈", ["S", "XL", "2XL", "3XL"])], [("title_names_one_variant", "XL")])
    assert _answer(item, "Hallo Golf Women's Cargo Jogger Golf Pants") == ("Hallo Golf Women's Cargo Jogger Golf Pants", [])
    item = _pants_title(tmp_path, "쟌피엘 가을 남자 스판 골프바지 골프웨어 허리밴딩 빅사이즈 30-46size",
                        [("사이즈", ["30", "32", "34", "36", "38", "40"])], [("title_names_one_variant", "30")])
    assert _answer(item, "Jean Pierre Men's Stretch Elastic-Waist Golf Pants")[1] == []
    assert T.TITLE_SIZE_RUN[PANTS].findall("허리 42까지 34사이즈 30~46 size BG1234") == ["42까지", "34사이즈", "30~46 size"]
    assert T.TITLE_SIZES[PANTS].findall("46 48 49") == ["46", "48"]


def test_a_pants_titles_season_promotion_and_style_count_are_taken_out(tmp_path):
    """7221598523 "25 FW 볼빅 ..." went out as "... Golf Pants FW"; 10160025240 "2026년 SS시즌 볼빅 ..." as "Volvik Golfwear
    2026 SS Men's ..."; 5489884876 "마스터베어 인기 BEST 골프팬츠" as "MASTER BEAR BEST Golf Pants"; 12534121142 "...
    2스타일 ... KPFMSL17" as "... KPFMSL17 2 Styles"."""
    item = _pants_title(tmp_path, "25 FW 볼빅 남성 기모 골프 바지 남자 베이직 팬츠 데일리 가을 겨울",
                        [("옵션", ["25FW", "26FW"])], [("title_names_one_variant", "25")])
    assert _answer(item, "VOLVIK Men's Fleece-Lined Golf Pants FW") == ("VOLVIK Men's Fleece-Lined Golf Pants", [])
    item = _pants_title(tmp_path, "2026년 SS시즌 볼빅 골프 남성 스트레치 여름 바지 배색 쿨 팬츠")
    assert _answer(item, "Volvik Golfwear 2026 SS Men's Stretch Color-Block Golf Pants") == (
        "Volvik Golfwear Men's Stretch Color-Block Golf Pants", [])
    item = _pants_title(tmp_path, "제로다몰 봄여름가을겨울 마스터베어 인기 BEST 골프팬츠")
    assert _answer(item, "MASTER BEAR BEST Golf Pants") == ("MASTER BEAR Golf Pants", [])
    assert "promotion" in item["context"]
    item = _pants_title(tmp_path, "[김영주골프] 봄가을 겨울기모 2스타일 프리미엄 스판 반밴딩 필드룩 남성 골프바지 KPFMSL17",
                        [("색상", ["봄가을-블랙", "겨울기모-블랙"])])
    assert _answer(item, "Kim Young Joo Golf Men's Stretch Elastic-Waist Golf Pants KPFMSL17 2 Styles") == (
        "Kim Young Joo Golf Men's Stretch Elastic-Waist Golf Pants KPFMSL17", [])
    # no season code in the title: a code with the season's letters in it stays
    assert _answer(_pants_title(tmp_path, "볼빅 남성 골프 바지 VBSS123"), "Volvik Men's Golf Pants VBSS123")[0] == (
        "Volvik Men's Golf Pants VBSS123")


def test_a_word_of_one_pants_variant_is_taken_out(tmp_path):
    """6384912528: "... 9부 일자핏 블랙 S" over 9부 and 롱, 일자핏 and 부츠컷 went out as "9-Length Cropped"; 5746242591
    "VT까슬이 숏" over 숏(9부) and 롱(10부) as "VT Short Inseam"; 10997837767 기모 a +2,000 KRW option (기모없음 /
    기모추가) as "Fleece-Lined"; 5990911618 원단 기본 / 기모 / 카고 as "Fleece-Lined Cargo"; 5979440160 레귤러핏 over two
    styles (the fleece one slim) as "Regular-Fit"."""
    cuts = ["(간절기)9부 일자핏", "(기모)9부일자핏", "(간절기)롱일자핏", "(기모)롱부츠컷"]
    item = _pants_title(tmp_path, "여성골프바지 빅사이즈 여자골프웨어 골프복 간절기 골프연습복 9부 일자핏 블랙 S",
                        [("계절", cuts), ("컬러", ["블랙", "네이비"])])
    assert _answer(item, "L.TO.L Golf Women's 9-Length Cropped Golf Pants") == ("L.TO.L Golf Women's Golf Pants", [])
    assert "9부, 일자" in item["context"]
    item = _pants_title(tmp_path, "여성 가을 겨울 골프바지 골프복 연습장복장 빅사이즈 골프웨어 VT까슬이 숏",
                        [("팬츠 종류", ["VT까슬이 숏(9부)", "VT까슬이 롱(10부)", "VT기모 숏(9부)"])])
    assert _answer(item, "Women's Golf Pants VT Short Inseam")[0] == "Women's Golf Pants VT"
    item = _pants_title(tmp_path, "여자 골프 와이드 팬츠 바지 기모 빅사이즈 여자골프웨어", [("기모 추가", ["기모없음", "기모추가"])])
    assert _answer(item, "JN Women's Fleece-Lined Wide-Leg Golf Pants")[0] == "JN Women's Wide-Leg Golf Pants"
    item = _pants_title(tmp_path, "여성골프바지 골프조거팬츠 골프웨어 기본 카고 기모 민그린", [("원단", ["기본", "기모", "카고"])])
    assert _answer(item, "Min Green Women's Fleece-Lined Cargo Jogger Golf Pants")[0] == "Min Green Women's Jogger Golf Pants"
    item = _pants_title(tmp_path, "26 S/S 아디다스 골프 바지 봄 가을 남자 골프웨어 레귤러핏 신축성 좋은",
                        [("상품", ["26 S/S 아디다스 골프바지", "아디다스 기모골프바지 (가을/겨울)"])])
    assert _answer(item, "Adidas Men's Regular-Fit Stretch Golf Pants")[0] == "Adidas Men's Stretch Golf Pants"
    # 5367746327: "... 일자 부츠컷 ..." over 매끈일자 / 매끈부츠컷 went out as "... Straight-Leg and Bootcut Golf Pants"
    item = _pants_title(tmp_path, "여성 골프바지 밴딩 뱃살보정 매끈 일자 부츠컷 빅사이즈 여성골프웨어",
                        [("디자인", ["매끈일자 봄가을", "매끈일자 기모", "매끈부츠컷 봄가을"])])
    assert _answer(item, "Baily White Women's Elastic-Waist Straight-Leg and Bootcut Golf Pants")[0] == (
        "Baily White Women's Elastic-Waist Golf Pants")
    assert T.strip_words("Cargo or Fleece-Lined and Stretch Golf Pants", ["Fleece[- ]Lined"]) == (
        "Cargo or Stretch Golf Pants")
    # every variant fleece-lined (7221598523: the season is the option), a fit word over colours: they stay
    item = _pants_title(tmp_path, "25 FW 볼빅 남성 기모 골프 바지", [("옵션", ["25FW", "26FW"])])
    assert _answer(item, "Volvik Men's Fleece-Lined Golf Pants")[0] == "Volvik Men's Fleece-Lined Golf Pants"
    assert "strip" not in _pants_title(tmp_path, "남성 레귤러핏 9부 골프바지", [("컬러", ["블랙", "네이비"])])
    assert not T.one_variant_word("기모", [{"values_ko": ["무기모", "노기모"]}, {"values_ko": ["기모추가", "기모 추가"]}])
    assert T.one_variant_word("기모", [{"values_ko": ["기모 X", "기모 O"]}])


def test_a_pants_title_wide_band_cotton_and_unsold_codes(tmp_path):
    """6689446962 "와이드 밴딩 ... 일자" (a wide waistband, a slim straight leg) went out as "Wide-Leg"; 8269563762
    "나이키 골프 바지 면 배기" (소재 폴리에스테르, 나일론, 기타) as "Cotton"; 8772595840 "HG1712 HG1713 HG1715" with the
    colours HG1713 / HG1715 only kept HG1712."""
    item = _pants_title(tmp_path, "여성 골프바지 ﻿와이드 밴딩 뱃살보정 ﻿일자 벨트 빅사이즈 ﻿여성골프웨어")
    assert _answer(item, "Baily White Women's Wide-Leg Elastic-Waist Golf Pants")[0] == (
        "Baily White Women's Elastic-Waist Golf Pants")
    assert "strip" not in _pants_title(tmp_path, "여자 골프 와이드 팬츠 와이드밴딩")          # a wide leg said too
    item = _pants_title(tmp_path, "나이키 골프 바지 면 배기 남성 팬츠 발목 기장 봄 옷 웨어 남자 드라이핏 밴딩 골프복",
                        composition=["폴리에스테르, 나일론, 기타"])
    assert _answer(item, "Nike Men's Cotton Elastic-Waist Cropped Golf Pants")[0] == (
        "Nike Men's Elastic-Waist Cropped Golf Pants")
    assert "strip" not in _pants_title(tmp_path, "남성 골프 면바지", composition=["면 97%, 스판 3%"])
    assert "strip" not in _pants_title(tmp_path, "남성 골프 면바지")                       # no material row: kept
    item = _pants_title(tmp_path, "아디다스 윈드레디 4웨이 스트레치 여성 골프바지 HG1712 HG1713 HG1715",
                        [("색상", ["HG1713 그레이3", "HG1715 블랙"]), ("사이즈", ["XS", "S"])])
    assert _answer(item, "Adidas Women's Wind.RDY 4-Way Stretch Golf Pants HG1712 HG1713 HG1715") == (
        "Adidas Women's Wind.RDY 4-Way Stretch Golf Pants HG1713 HG1715", [])
    # the values carry no code of the title's (colours only): every code stays and must survive
    item = _pants_title(tmp_path, "아디다스 여성 골프바지 HG1712 HG1713", [("색상", ["그레이", "블랙"])])
    assert _answer(item, "Adidas Women's Golf Pants HG1713")[1] == ["numbers changed: missing 1712",
                                                                     "codes lost: missing HG1712"]
