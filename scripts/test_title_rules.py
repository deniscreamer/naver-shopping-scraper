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


def test_every_shop_selling_a_category_with_title_rules_sells_it_as_sets_only():
    """TITLE_RULES["50002783"] drops "or single" because the shop keeps no one-club variant (sets_only); a shop that
    takes 50002783 without sets_only would sell the single its title no longer names (2026-11-16)."""
    from transform_shops import RULES
    from translation_rules import TITLE_RULES
    sellers = [(shop, rules.categories[cat]) for shop, rules in RULES.items() for cat in TITLE_RULES
               if cat in rules.categories]
    assert sellers and all(cat.sets_only for _, cat in sellers), [s for s, c in sellers if not c.sets_only]
