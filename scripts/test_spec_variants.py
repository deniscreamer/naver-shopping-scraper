"""spec_variants: spec rows vs the sold variants, and the title check. Offline; every case is a real quote from the
40 collected golf sets (category 50002788, research 2026-11-06) or from saved pages beside them (11164222651,
10649210920). Must-not-match cases are tests too: a wrong binding publishes a false fact for some variants."""
import pytest

from spec_variants import (check_specs, description_materials, family_floor, material, part_count, row_year,
                           stated_total, title_one_variant, years)


def _opt(name, *values):
    return {"name_ko": name, "values_ko": list(values)}


def _rows(**rows):
    return [{"label_ko": k.replace("_", " "), "value_ko": v} for k, v in rows.items()]


def _spec(label, value):
    return {"label_ko": label, "value_ko": value}


def _by_label(result):
    return {r["label_ko"]: r for r in result["specs"]}


def _codes(result):
    return {n["code"]: n["detail"] for n in result["notes"]}


# ---- R-MAT material class --------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("그라파이트/카본", "CARBON"), ("경량스틸", "STEEL"), ("남성용 SR스틸", "STEEL"), ("NS PRO 950GH", "STEEL"),
    ("경량그라파이트", "CARBON"), ("여성용", None),
    ("스틸 or 카본", None),                       # names both (12391346892 description)
])
def test_material(text, expected):
    assert material(text) == expected


def test_material_binds_carbon_row_to_the_silent_value_9868413561():
    got = check_specs([_spec("아이언샤프트소재", "그라파이트/카본")], [_opt("옵션", "여성용", "남성용 SR스틸")],
                      [{"options_ko": ["여성용"]}, {"options_ko": ["남성용 SR스틸"]}], None)
    assert got["specs"] == [{"label_ko": "아이언샤프트소재", "value_ko": "그라파이트/카본", "for_ko": ["여성용"]}]
    assert _codes(got) == {"specs_bound_to_variants": "아이언샤프트소재 그라파이트/카본 -> 여성용"}


def test_material_stated_by_every_value_drops_the_row_10563381788():
    got = check_specs([_spec("아이언샤프트소재", "그라파이트/카본")], [_opt("타입", "왼손 4스틸+골프백", "왼손 4카본+골프백")],
                      [], None)
    assert got["specs"] == []
    assert list(_codes(got)) == ["specs_stated_by_variants"]


def test_material_fits_no_variant_drops_the_row_10649210920():
    got = check_specs([_spec("아이언샤프트소재", "그라파이트/카본")],
                      [_opt("선택", "9.5도 R + 9아이언세트 스틸 R", "10.5도 R + 9아이언세트 스틸 R")], [], None)
    assert got["specs"] == []
    assert list(_codes(got)) == ["specs_fit_no_variant"]


@pytest.mark.parametrize("specs, options", [
    ([], [_opt("경도/아이언 샤프트", "R 카본", "S 스틸")]),                                   # no row: 13777887875
    ([_spec("아이언샤프트소재", "경량그라파이트")],                                           # 13099257309
     [_opt("드라이버+8개 아이언", "10.5도 R+아이언 R", "10.5도 SR+아이언 SR", "9.5도 R+아이언 R")]),
    ([_spec("아이언샤프트소재", "스틸")],                                                     # 10208717296
     [_opt("선택", "10.5R유틸4번R8아이언R퍼터", "10.5SR유틸4번SR8아이언R퍼터", "9도SR유틸4번SR8아이언R퍼터")]),
    ([_spec("아이언샤프트소재", "그라파이트/카본")],                                          # 12434254421
     [_opt("드라이버", "9.5도 R", "10.5도 R"), _opt("아이언", "8아이언세트 카본 R", "8아이언세트 카본 SR")]),
])
def test_material_must_not_match(specs, options):
    got = check_specs(specs, options, [], None)
    assert got == {"specs": specs, "notes": []}


# ---- R-DESC material bound to a whole option value -------------------------------------------

def test_description_materials_6774818843():
    assert description_materials("워버드 클럽 세트 (10 개 세트) 스틸(S) / 카본(R)", ["R", "S"]) == \
        {"S": "STEEL", "R": "CARBON"}


@pytest.mark.parametrize("text, values", [
    ("4종 스틸 샤프트 / 4종 카본(R) 샤프트", ["4종-스틸 샤프트", "4종-카본(R) 샤프트"]),   # R is not a whole value
    ("그 외: 카본샤프트(강도: R)", ["R", "S"]),                                            # more than the value
    ("아이언 : WARBIRD (R), 오리지널 스틸 (UNI : SR 상당)", ["R", "S"]),
    ("스틸(S) / 스틸(R) / 카본(S)", ["R", "S"]) ,                                           # S bound to both: only R
])
def test_description_materials_must_not_match(text, values):
    got = description_materials(text, values)
    assert "S" not in got and "4종-카본(R) 샤프트" not in got


def test_description_binds_the_steel_row_to_s_6774818843():
    desc = "캐디 백입니다.\n워버드 클럽 세트 (10 개 세트) 스틸(S) / 카본(R)\n캘러웨이 골프"
    got = check_specs([_spec("아이언샤프트소재", "스틸")], [_opt("선택", "R", "S")],
                      [{"options_ko": ["R"]}, {"options_ko": ["S"]}], desc)
    assert got["specs"] == [{"label_ko": "아이언샤프트소재", "value_ko": "스틸", "for_ko": ["S"]}]
    assert _codes(got) == {"specs_bound_to_variants": "아이언샤프트소재 스틸 -> S"}
    assert check_specs([_spec("아이언샤프트소재", "스틸")], [_opt("선택", "R", "S")], [], None)["notes"] == []


# ---- R-COUNT stated totals -------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("12종 카본+골프백", 12), ("스틸9P+캐디백", 9), ("4스틸 + 골프백", 4), ("BM 풀세트 여성 실버 12PCS", 12),
    ("10개세트 클럽만", 10), ("카본그라파이트11종+캐디백", 11), ("12카본 + 골프백 (신축성)", 12),
    ("8개 아이언", None), ("7번 아이언", None), ("10.5도 R", None), ("XR 24 백세트포함", None),
    ("D1 500 S+950 S", None), ("4번유틸", None),
    ("피치 11PC+(사은품 7종 세트 포함)", None),         # two totals: the gift 7종
    ("7개구성 REAX 40 카본(L)", None),                  # 7개구성 = the irons of an iron axis
    ("드라이버+8개 아이언", None),
])
def test_stated_total(text, expected):
    assert stated_total(text) == expected


def test_count_binds_total_but_values_state_it_12274419597():
    values = ["스틸9P+캐디백", "카본9P+캐디백", "스틸12P+캐디백", "카본12P+캐디백"]
    specs = _rows(아이언_구성="#6, #7, #8, #9, 피칭웨지(PW), 샌드웨지(SW)", 총클럽개수="9개",
                  풀세트구성="드라이버, 3유틸리티, 퍼터, 6아이언세트", 아이언샤프트소재="스틸", 아이언개수="6개")
    got = check_specs(specs, [_opt("세트 구성", *values)], [], None)
    rows = _by_label(got)
    assert "총클럽개수" not in rows and "아이언샤프트소재" not in rows           # every value states both
    for label in ("아이언 구성", "풀세트구성", "아이언개수"):
        assert rows[label]["for_ko"] == ["스틸9P+캐디백", "카본9P+캐디백"]
    assert [r["label_ko"] for r in got["specs"]] == ["아이언 구성", "풀세트구성", "아이언개수"]   # order kept
    notes = _codes(got)
    assert set(notes) == {"specs_stated_by_variants", "specs_bound_to_variants"}
    assert "총클럽개수 9개" in notes["specs_stated_by_variants"]
    assert "아이언샤프트소재 스틸" in notes["specs_stated_by_variants"]


def test_count_fits_no_variant_9343324012():
    values = ["10.5R 4번유틸R 8아이언R 퍼터", "10.5도 4번유틸SR8아이언R 퍼터", "9도 SR4번유틸SR 8아이언R 퍼터",
              "9도 S4번유틸S 8아이언S 퍼터"]
    specs = _rows(아이언_구성="#5, #6, #7, #8, #9, 피칭웨지(PW), 어프로치웨지(AW), 샌드웨지(SW)", 총클럽개수="12개",
                  풀세트구성="드라이버, 유틸리티, 퍼터, 8아이언세트", 아이언샤프트소재="스틸", 아이언개수="8개")
    got = check_specs(specs, [_opt("선택", *values)], [], None)
    assert [r["label_ko"] for r in got["specs"]] == ["아이언 구성", "풀세트구성", "아이언샤프트소재", "아이언개수"]
    assert all("for_ko" not in r for r in got["specs"])          # one group (11): the family stays product-wide
    assert _codes(got) == {"specs_fit_no_variant": "총클럽개수 12개: the variants are 11"}


# ---- R-PARTS club count of a full part list --------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("드라이버 우드 유틸 7아이언 퍼터", 11), ("드라이버 유틸 7아이언 퍼터", 10), ("9도SR유틸4번SR8아이언R퍼터", 11),
    ("9R 4번유틸 8아이언퍼터", 11), ("10.5도 R 4번유틸 7아이언 퍼터", 10), ("10.5 도 R4번유틸 8아이언R퍼터", 11),
    ("드라이버+8개 아이언", None),             # no putter: one axis of three
    ("7번 아이언 퍼터", None),                 # one #7 iron
    ("11.5도 L+아이언 L+퍼터", None),          # no iron count
    ("8아이언세트 카본 R", None),
])
def test_part_count(text, expected):
    assert part_count(text) == expected


def test_part_lists_bind_total_and_family_5182294301():
    specs = _rows(아이언_구성="#6, #7, #8, #9, 피칭웨지(PW), 어프로치웨지(AW), 샌드웨지(SW)", 총클럽개수="10개",
                  풀세트구성="드라이버, 7아이언세트, 유틸리티, 퍼터", 아이언샤프트소재="스틸", 아이언개수="7개")
    got = check_specs(specs, [_opt("선택", "드라이버 유틸 7아이언 퍼터", "드라이버 우드 유틸 7아이언 퍼터")], [], None)
    rows = _by_label(got)
    for label in ("총클럽개수", "아이언 구성", "풀세트구성", "아이언개수"):     # a count from a part list is not stated
        assert rows[label]["for_ko"] == ["드라이버 유틸 7아이언 퍼터"]
    assert "for_ko" not in rows["아이언샤프트소재"]
    assert list(_codes(got)) == ["specs_bound_to_variants"]
    assert "총클럽개수 10개 -> 드라이버 유틸 7아이언 퍼터" in _codes(got)["specs_bound_to_variants"]


@pytest.mark.parametrize("total, values", [
    ("11개", ["9도SR 유틸 8아이언 퍼터", "9도S 유틸 8아이언 퍼터", "10.5도R 유틸 8아이언 퍼터"]),   # 10337644911
    ("11개", ["9R 4번유틸 8아이언퍼터", "10.5R 4번유틸 8아이언퍼터", "9S 4번유틸 8아이언퍼터"]),    # 8490916979
    ("10개", ["10.5도 R 4번유틸 7아이언 퍼터", "9도 S 4번유틸 7아이언 퍼터"]),                      # 7632306067
    ("11개", ["10.5R유틸4번R8아이언R퍼터", "9도S유틸4번S8아이언S퍼터"]),                            # 10208717296
])
def test_count_must_not_match_when_every_part_list_counts_to_the_row(total, values):
    specs = _rows(총클럽개수=total, 풀세트구성="드라이버, 유틸리티, 8아이언세트, 퍼터")
    assert check_specs(specs, [_opt("선택", *values)], [], None) == {"specs": specs, "notes": []}


# ---- R-FAMILY composition rows ----------------------------------------------------------------

@pytest.mark.parametrize("rows, expected", [
    ({"아이언개수": "6개", "아이언 구성": "#6, #7, #8, #9, 피칭웨지(PW), 샌드웨지(SW)",
      "풀세트구성": "드라이버, 3유틸리티, 퍼터, 6아이언세트"}, 9),                                      # 12274419597
    ({"아이언 구성": "#7, 샌드웨지(SW)", "풀세트구성": "드라이버, 퍼터, 웨지"}, 4),                     # 6999516176
    ({"아이언개수": "7개", "아이언 구성": "#5, #6, #7, #8, #9, 샌드웨지(SW), 피칭웨지(PW)",
      "풀세트구성": "드라이버, 7아이언세트, 퍼터, 페어웨이"}, 10),                                       # 6630856593
    ({"아이언개수": "6개", "아이언 구성": "#7, #8, #9, PW, AW, SW",                                     # 11164222651:
      "풀세트구성": "드라이버, 7아이언세트, 페어웨이, 유틸리티, 3유틸리티, 퍼터, 6아이언세트"}, 6),     # a checklist
    ({"풀세트구성": "드라이버, 5아이언세트, 3페어웨이, 퍼터, 웨지"}, 9),                                 # 웨지: no list
    ({"골프백포함여부": "캐디백"}, None),
])
def test_family_floor(rows, expected):
    assert family_floor(rows) == expected


def test_family_binds_to_the_4_set_6999516176():
    values = ["4종-스틸 샤프트", "4종-카본(S) 샤프트", "4종-카본(R) 샤프트", "12종-스틸 샤프트", "12종-카본(S) 샤프트",
              "12종-카본(R) 샤프트"]
    specs = _rows(아이언_구성="#7, 샌드웨지(SW)", 풀세트구성="드라이버, 퍼터, 웨지", 아이언샤프트소재="스틸")
    got = check_specs(specs, [_opt("타입", *values)], [], None)
    rows = _by_label(got)
    assert rows["아이언 구성"]["for_ko"] == rows["풀세트구성"]["for_ko"] == values[:3]
    assert "아이언샤프트소재" not in rows                                        # every value states it


def test_family_follows_the_total_6630856593():
    values = ["4스틸 + 골프백", "4카본 + 골프백", "12스틸 + 골프백", "12카본 + 골프백", "12스틸 + 골프백 (신축성)",
              "12카본 + 골프백 (신축성)"]
    specs = _rows(아이언_구성="#5, #6, #7, #8, #9, 샌드웨지(SW), 피칭웨지(PW)", 총클럽개수="12개",
                  풀세트구성="드라이버, 7아이언세트, 퍼터, 페어웨이", 아이언샤프트소재="그라파이트/카본", 아이언개수="7개")
    got = check_specs(specs, [_opt("타입", *values)], [], None)
    rows = _by_label(got)
    assert set(rows) == {"아이언 구성", "풀세트구성", "아이언개수"}
    assert all(r["for_ko"] == values[2:] for r in rows.values())


def test_family_on_two_axes_names_the_deciding_axis_12391346892():
    specs = _rows(아이언_구성="#5, #6, #7, #8, #9, 피칭웨지(PW), 샌드웨지(SW)", 총클럽개수="12개",
                  풀세트구성="드라이버, 3페어웨이, 퍼터, 7아이언세트", 아이언샤프트소재="그라파이트/카본", 아이언개수="7개")
    options = [_opt("소재", "카본", "스틸"), _opt("세트", "12종", "9종")]
    variants = [{"options_ko": [m, s]} for m in ("카본", "스틸") for s in ("12종", "9종")]
    got = check_specs(specs, options, variants, None)
    rows = _by_label(got)
    assert set(rows) == {"아이언 구성", "풀세트구성", "아이언개수"}
    assert all(r["for_ko"] == ["12종"] for r in rows.values())
    assert "아이언 구성 #5, #6, #7, #8, #9, 피칭웨지(PW), 샌드웨지(SW) -> 12종" in \
        _codes(got)["specs_bound_to_variants"]


@pytest.mark.parametrize("composition", ["드라이버, 5아이언세트, 3페어웨이, 퍼터, 웨지",       # 10569037690
                                         "5아이언세트, 3페어웨이, 드라이버, 퍼터, 웨지"])      # 10569099959
def test_family_binds_to_12_10569037690_10569099959(composition):
    values = ["9종 스틸+골프백", "9종 카본+골프백", "12종 스틸+골프백", "12종 카본+골프백"]
    specs = _rows(아이언_구성="#5, #6, #7, #8, #9, 피칭웨지(PW), 샌드웨지(SW)", 총클럽개수="12개",
                  풀세트구성=composition, 아이언샤프트소재="그라파이트/카본", 아이언개수="4개")
    rows = _by_label(check_specs(specs, [_opt("옵션", *values)], [], None))
    assert set(rows) == {"아이언 구성", "풀세트구성", "아이언개수"}
    assert all(r["for_ko"] == values[2:] for r in rows.values())


def test_family_checklist_stays_product_wide_11164222651():
    specs = _rows(아이언개수="6개", 아이언_구성="#7, #8, #9, PW, AW, SW", 총클럽개수="10개",
                  풀세트구성="드라이버, 7아이언세트, 페어웨이, 유틸리티, 3유틸리티, 퍼터, 6아이언세트")
    got = check_specs(specs, [_opt("구성", "10개세트 클럽만", "11개세트 클럽만")], [], None)
    rows = _by_label(got)
    assert rows["아이언개수"]["for_ko"] == rows["아이언 구성"]["for_ko"] == ["10개세트 클럽만"]
    assert "for_ko" not in rows["풀세트구성"]
    assert "총클럽개수" not in rows                                              # stated by every value


def test_family_undecided_drops_the_rows():
    specs = _rows(아이언개수="7개", 풀세트구성="드라이버, 퍼터, 7아이언세트")       # floor 9, sets of 10 and 12
    got = check_specs(specs, [_opt("구성", "10종 세트", "12종 세트")], [], None)
    assert got["specs"] == []
    assert list(_codes(got)) == ["specs_composition_undecided"]


@pytest.mark.parametrize("specs, options", [
    (_rows(아이언개수="8개", 풀세트구성="8아이언세트, 드라이버, 유틸리티, 페어웨이"),            # 12434254421
     [_opt("드라이버", "9.5도 R", "10.5도 R"), _opt("아이언", "8아이언세트 카본 R", "8아이언세트 카본 SR")]),
    (_rows(아이언개수="8개", 아이언_구성="#5, #6, #7, #8, #9, 피칭웨지(PW), 어프로치웨지(AW), 샌드웨지(SW)"),
     [_opt("드라이버+8개 아이언", "10.5도 R+아이언 R", "9.5도 R+아이언 R"), _opt("우드 선택", "5번 R", "3번 R")]),
    (_rows(아이언_구성="#7, 샌드웨지(SW)", 풀세트구성="드라이버, 퍼터"),                          # 10563381788
     [_opt("타입", "왼손 4스틸+골프백", "왼손 4카본+골프백")]),
    (_rows(아이언개수="7개"), [_opt("아이언", "7개구성 REAX 40 카본(L)", "7개구성 REAX 40 카본(R)")]),  # 13741767690
])
def test_family_must_not_match_one_group(specs, options):
    got = check_specs(specs, options, [], None)
    assert all("for_ko" not in r for r in got["specs"] if r["label_ko"] != "아이언샤프트소재")
    assert not any(n["code"] in ("specs_bound_to_variants", "specs_composition_undecided") for n in got["notes"])


def test_no_options_never_touched():
    specs = _rows(총클럽개수="12개", 아이언개수="7개")
    assert check_specs(specs, [], [], None) == {"specs": specs, "notes": []}
    assert check_specs(specs, [_opt("선택", "12종")], [], None) == {"specs": specs, "notes": []}


# ---- R-YEAR model year vs 출시 ----------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("XR26 남성 풀세트 백포함", {26}), ("(추가할인) XR 24 백세트포함", {24}), ("X HOT 21 캐디백포함", {21}),
    ("23년 로얄", {23}), ("2024 모델", {24}),
    ("G430", set()), ("젝시오14 남성", set()), ("ST-MAX 230", set()), ("BM 13PCS", set()),
    ("Qi4D MAX LITE 10pcs", set()), ("9.5도 R", set()), ("Qi10 V300", {10}),
])
def test_years(text, expected):
    assert years(text) == expected


def test_row_year():
    assert row_year("2026년형") == 26 and row_year("상세설명 참조") is None


XR = ["XR26 남성 풀세트 백포함", "(추가할인) XR 24 백세트포함", "(추가할인) X HOT 23 백세트포함", "(추가할인) X HOT 21 캐디백포함"]


def test_year_binds_to_xr26_12696567111():
    specs = [_spec("모델명", "26캘러웨이 풀세트 XR26 FULL SET 12PC"), _spec("성별", "남성용"), _spec("출시", "2026년형")]
    got = check_specs(specs, [_opt("옵션+아이언커버.하프백", *XR)], [], None)
    rows = _by_label(got)
    assert rows["출시"]["for_ko"] == ["XR26 남성 풀세트 백포함"]
    assert "for_ko" not in rows["모델명"]
    notes = _codes(got)
    assert notes["specs_bound_to_variants"] == "출시 2026년형 -> XR26 남성 풀세트 백포함"
    assert notes["specs_name_one_variant"] == "모델명 26캘러웨이 풀세트 XR26 FULL SET 12PC: XR26"   # the row's span


def test_year_must_not_match_without_the_row_year():
    specs = [_spec("출시", "2024년형")]
    assert check_specs(specs, [_opt("모델", "Qi10 V300", "Qi10 MAX")], [], None)["notes"] == []
    assert check_specs(specs, [_opt("모델", "G430", "G425")], [], None)["notes"] == []


# ---- the word match left for other rows -------------------------------------------------------

def test_model_row_word_match_10569037690():
    specs = [_spec("모델명", "PGM 골프채 풀세트 남성 입문용 골프채세트 9종")]
    got = check_specs(specs, [_opt("옵션", "9종 스틸+골프백", "9종 카본+골프백", "12종 스틸+골프백")], [], None)
    assert got["specs"] == specs
    assert _codes(got) == {"specs_name_one_variant": "모델명 PGM 골프채 풀세트 남성 입문용 골프채세트 9종: 9종"}


# ---- R-TITLE --------------------------------------------------------------------------------

def test_title_xr26_not_gender_nor_bag_12696567111():
    assert title_one_variant("(당일퀵) 캘러웨이 XR26 남성 풀세트 백포함 캘러웨이코리아 2026",
                             [_opt("옵션+아이언커버.하프백", *XR)]) == ["XR26"]


def test_title_span_9도sr_10337644911():
    assert title_one_variant("테일러메이드 Qi10 V300 남성골프풀세트클럽11개선택1 9도SR 유틸 8아이언 퍼터",
                             [_opt("선택", "9도SR 유틸 8아이언 퍼터", "9도S 유틸 8아이언 퍼터", "10.5도R 유틸 8아이언 퍼터",
                                   "10.5도SR 유틸 8아이언 퍼터")]) == ["9도SR"]


def test_title_gender_with_a_rival_7674852369():
    assert title_one_variant("투어엣지 바주카 370 엣지 골프 풀세트 남성용 골프채세트",
                             [_opt("선택", "투어엣지 바주카 370 남성용 풀세트", "투어엣지 레이디 여성용 풀세트 민트",
                                   "투어엣지 레이디 여성용 풀세트 블랙")]) == ["바주카", "370", "남성용"]


def test_title_count_from_part_lists_5182294301():
    assert title_one_variant("핑 G425,다이와 조합 남성골프채풀세트(클럽10개) 선택1 드라이버 유틸 7아이언 퍼터",
                             [_opt("선택", "드라이버 유틸 7아이언 퍼터", "드라이버 우드 유틸 7아이언 퍼터")]) == ["10개"]


@pytest.mark.parametrize("title, options, expected", [
    ("신품 혼마 D1 남성용 골프채 풀세트 2021년 S세트 D1 500 S+950 S (병행)",                       # 5543745139
     [_opt("세트선택", "S 세트 (D1 500 S+950 S)", "R 세트 (D1 500 R)")], ["S", "950"]),
    ("일본 Wistella 위스텔라 여성용 남성용 골프채풀세트", [_opt("옵션", "여성용", "남성용 SR스틸")], []),  # both
    ("지브이투어 벨로시티 BM 13 PCS 남성 여성 풀세트 (백세트포함)",                                  # 7583123963
     [_opt("골프클럽구분", "BM 풀세트 스틸 블랙 13PCS", "BM 풀세트 여성 실버 12PCS", "BM 풀세트 카본 골드 13PCS")],
     ["13PCS"]),
    ("24년 핑 G430 10K V300 남성골프채풀세트 11개조합 선택1 10.5R유틸4번R8아이언R퍼터",               # 10208717296
     [_opt("선택", "10.5R유틸4번R8아이언R퍼터", "10.5SR유틸4번SR8아이언R퍼터", "9도SR유틸4번SR8아이언R퍼터",
           "9도S유틸4번S8아이언S퍼터")], ["10.5R", "R"]),
    ("PGM 초보자 남성 카본 입문용골프채 12종 풀세트",                                               # 12391346892
     [_opt("소재", "카본", "스틸"), _opt("세트", "12종", "9종")], ["카본", "12종"]),
    ("왼손/ 테일러메이드/ 풀세트 골프채  남자 좌타 남성 레프티 왼손잡이 골프 R강도 S강도",            # names both
     [_opt("샤프트강도", "R강도", "S강도")], []),
    ("테일러메이드코리아 스텔스2 남성골프채 풀세트 11개조합 드라이버 선택4) 9R 4번유틸 8아이언퍼터",    # all 11
     [_opt("선택", "9R 4번유틸 8아이언퍼터", "10.5R 4번유틸 8아이언퍼터", "9S 4번유틸 8아이언퍼터")], ["9R"]),
])
def test_title_unchanged_cases(title, options, expected):
    assert title_one_variant(title, options) == expected


def test_title_gender_without_a_rival_is_noise():
    assert title_one_variant("브랜드 남성 풀세트", [_opt("선택", "남성 풀세트 블랙", "화이트")]) == []
    assert title_one_variant("브랜드 남성 풀세트", [_opt("선택", "남성 풀세트 블랙", "여성 화이트")]) == ["남성"]


# ---- pilot 2026-11-06 (19 more golf sets): numbers with units, the driver loft, the bag ------------------

GLORY = [_opt("드라이버+아이언", "11.5도 L+아이언 L", "11.5도 A+아이언 A", "10.5도 A+아이언A"),
         _opt("유틸리티 선택", "4번 L", "4번 A", "5번 L", "5번 A")]


def test_title_loft_and_club_number_10816781893():
    # "11.5" names the value "11.5도", "유틸4" the 4번 of the 유틸리티 axis; the L of "아이언L" is inside no span
    # of its own once 11.5L / 유틸4L carry it (the touching rule)
    assert title_one_variant("2025 테일러메이드 올 뉴 글로리 여성용 풀세트 드라이버11.5L+아이언L+유틸4L", GLORY) == \
        ["11.5L", "유틸4L"]


def test_title_club_numbers_with_latin_parts_13553116678():
    options = [_opt("페어웨이우드", "5W", "3W", "7W"), _opt("유틸리티", "4U", "3U", "5U", "6U")]
    assert title_one_variant("혼마 베레스 아이주 2스타 여성 10개 풀세트 11.5+5W+4U+7i (병행)", options) == ["5W", "4U"]


def test_model_row_names_loft_wood_and_util_10816904599():
    options = [_opt("드라이버+아이언+퍼터(32인치)+골프백 선택", "11.5도 L+아이언 L+퍼터+골프백", "11.5도 A+아이언 A+퍼터+골프백",
                    "10.5도 A+아이언A+퍼터+골프백"),
               _opt("우드 선택", "5번 L", "5번 A", "3번 L", "3번 A"), _opt("유틸리티 선택", "4번 L", "4번 A", "5번 L", "5번 A")]
    row = "2025 테일러메이드 올 뉴 글로리 여성용 풀세트 [드라이버11.5L+아이언L+퍼터+골프백+우드5L+유틸4L]"
    got = check_specs([_spec("모델명", row)], options, [], None)
    assert _codes(got) == {"specs_name_one_variant": f"모델명 {row}: 11.5L, 우드5L, 유틸4L"}


@pytest.mark.parametrize("title, options", [
    ("핑 G430 10K 남성 클럽 10개 풀세트", [_opt("드라이버", "10도 R", "9도 R")]),      # 10K / 10개 are not a loft
    ("Qi10 남성 풀세트 9아이언", [_opt("드라이버", "10도 R", "9도 R")]),               # Qi10, 9아이언
    ("테일러메이드 Qi10 V300 남성골프풀세트클럽11개선택1 9도SR 유틸 8아이언 퍼터",        # 유틸 8아이언: no 유틸8
     [_opt("선택", "9도SR 유틸 8아이언 퍼터", "9도SR 유틸 7아이언 퍼터")]),
    ("젝시오 풀세트 3유틸리티 구성", [_opt("유틸리티", "3번", "4번")]),                 # 3유틸리티: a count, not #3
    ("혼마 풀세트 5W 4U", [_opt("유틸리티", "4번 R", "5번 R")]),                        # 4U is a util: no other axis
])
def test_title_numbers_must_not_match(title, options):
    got = title_one_variant(title, options)
    assert not any(w in got for w in ("10", "9", "10K", "8", "3유틸리티", "5W")), got


def test_title_util_number_is_the_axis_part_not_a_wood():
    assert title_one_variant("풀세트 우드4", [_opt("유틸리티 선택", "4번 L", "5번 L")]) == []


# ---- R-LOFT driver loft ----------------------------------------------------------------------

def test_loft_stated_by_every_value_drops_the_row_11635855564():
    options = [_opt("드라이버", "10.5도 SR", "10.5도 R", "9도 SR", "9도 R", "9도 S"),
               _opt("유틸리티", "3번 R", "3번 SR", "3번 S", "4번 R", "4번 SR", "4번 S", "5번 R", "5번 SR", "5번 S")]
    specs = _rows(드라이버_로프트각="10.5도", 아이언샤프트소재="경량스틸")
    got = check_specs(specs, options, [], None)
    assert [r["label_ko"] for r in got["specs"]] == ["아이언샤프트소재"]
    assert _codes(got) == {"specs_stated_by_variants": "드라이버 로프트각 10.5도: every variant states it"}


def test_loft_without_degree_sign_13369469193():
    options = [_opt("선택", "NEW 2.0 트리슐라 클럽세트 10.5 R", "NEW 2.0 트리슐라 클럽세트 10.5 SR",
                    "NEW 2.0 트리슐라 클럽세트 9.5 SR")]
    got = check_specs(_rows(드라이버_로프트각="10.5도"), options, [], None)
    assert got["specs"] == []
    assert list(_codes(got)) == ["specs_stated_by_variants"]


def test_loft_binds_to_the_values_it_fits_when_some_are_silent():
    options = [_opt("드라이버", "10.5도 R", "9도 R", "R"), _opt("아이언", "8아이언 R")]
    got = check_specs(_rows(드라이버_로프트각="10.5도"), options, [], None)
    assert got["specs"] == [{"label_ko": "드라이버 로프트각", "value_ko": "10.5도", "for_ko": ["10.5도 R", "R"]}]


def test_loft_fits_no_variant():
    got = check_specs(_rows(드라이버_로프트각="11.5도"), [_opt("드라이버", "10.5도 R", "9도 R")], [], None)
    assert got["specs"] == []
    assert _codes(got) == {"specs_fit_no_variant": "드라이버 로프트각 11.5도: the variants are 10.5도, 9도"}


@pytest.mark.parametrize("specs, options", [
    (_rows(드라이버_로프트각="11.5도, 10.5도"), GLORY),                                   # 10816781893: lists all sold
    (_rows(드라이버_로프트각="9.5도, 10.5도"),                                              # 8958060680: values silent
     [_opt("브리지스톤 BG100 화이트 풀세트 캐디백포함", "스틸 샤프트 (S) SPEC", "카본 샤프트 (R) SPEC")]),
    (_rows(드라이버_로프트각="11.5도"),                                                     # wood / util lofts
     [_opt("우드", "우드7번(21도)-L", "우드9번(33도)-A"), _opt("유틸", "유틸8번(36도)-A", "유틸6번(28도)-L")]),
    (_rows(드라이버_로프트각="10.5도"), [_opt("유틸리티", "4번 R", "5번 S")]),              # 4번 R is no loft
])
def test_loft_must_not_match(specs, options):
    assert check_specs(specs, options, [], None) == {"specs": specs, "notes": []}


# ---- R-DESC material bound by a sentence ------------------------------------------------------

WARBIRD = "※플렉스 R 모델의 아이언에는 카본 샤프트,\n플렉스 S 모델의 아이언에는 스틸 샤프트 장착"


def test_description_materials_sentence_7166885441():
    assert description_materials(WARBIRD, ["R", "S"]) == {"R": "CARBON", "S": "STEEL"}


def test_description_sentence_binds_the_carbon_row_7166885441():
    got = check_specs([_spec("아이언샤프트소재", "그라파이트/카본")], [_opt("플렉스", "R", "S")], [], WARBIRD)
    assert got["specs"] == [{"label_ko": "아이언샤프트소재", "value_ko": "그라파이트/카본", "for_ko": ["R"]}]


@pytest.mark.parametrize("text", [
    "R 모델의 드라이버에는 카본 샤프트, S 모델의 드라이버에는 카본 샤프트",          # the driver, not the irons
    "R 모델 출시 기념, 스틸 커버 증정\n",                                             # far apart and no shaft
    "플렉스 R 모델: 경량 설계. 카본 헤드커버",                                         # another sentence
])
def test_description_sentence_must_not_match(text):
    assert description_materials(text, ["R", "S"]) == {}


# ---- R-BAG the bag in the title vs values without it -------------------------------------------

REVA = [_opt("구성", "피치/서프 클럽 10PCS (캐디백포함)", "피치/서프 클럽 10PCS (캐디백 미포함)", "블랙 클럽 10PCS (캐디백포함)",
             "블랙 클럽 10PCS (캐디백 미포함)")]


def test_title_bag_with_values_without_it_13413924099():
    assert title_one_variant("캘러웨이 2026 REVA 레바 여성 풀세트 피치/서프 10PCS+골프백 [캘러웨이코리아]", REVA) == \
        ["피치", "서프", "골프백"]


def test_title_bag_must_not_match_13734679551():
    options = [_opt("구성", "풀세트+캐디백(화이트)", "풀세트+캐디백(화이트/그레이)")]       # every value has the bag
    assert title_one_variant("미즈노 RB LADY 여성 풀세트 캐디백", options) == []
    # a title without the bag names the 미포함 values (one span), not the bag
    assert title_one_variant("레바 여성 풀세트 캐디백 미포함", REVA) == ["캐디백 미포함"]


def test_title_loft_written_two_ways_9343324012():
    # "10.5R" and "10.5도" are one loft: the title "10.5R" still names the 10.5R value, not both 10.5 values
    values = ["10.5R 4번유틸R 8아이언R 퍼터", "10.5도 4번유틸SR8아이언R 퍼터", "9도 SR4번유틸SR 8아이언R 퍼터",
              "9도 S4번유틸S 8아이언S 퍼터"]
    assert title_one_variant("삼양인터내셔날 핑 G430 브리지스톤 v300 조합 남성골프채풀세트 11개 드라이버10.5R 4번유틸R "
                             "8아이언R 퍼터", [_opt("선택", *values)]) == ["10.5R", "R"]
