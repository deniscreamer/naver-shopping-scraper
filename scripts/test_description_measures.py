"""Offline tests for the size / weight guess from description image text (description_measures.py).

Two parts: the core (any category: stated packed / set / product values, no profile) and the golf_set profile
(clubs + the bag). The golf rows are RapidOCR rows of real fixture products (fixtures/description_images/,
OCR study 2026-11-07), quoted as read; the core's rows are how sellers of other categories write it.

    .venv/bin/python -m pytest scripts/test_description_measures.py -q
"""
import description_measures as D

GOLF = D.GOLF_SET
DEFAULT = {"low": 4500, "central": 7000, "high": 11000, "source": "category_default", "confidence": 1}


def fields(**over):
    base = {"product_weight_g": {**DEFAULT, "central": 5700}, "package_weight_g": dict(DEFAULT),
            "package_length_mm": {**DEFAULT, "central": 1250}, "package_width_mm": {**DEFAULT, "central": 280},
            "package_height_mm": {**DEFAULT, "central": 230}}
    return {**base, **over}


def values(g):
    return {k: v["value"]["max"] for k, v in g.items()}


# ---- the core: any category, no profile ---------------------------------------------------------------------

def test_core_chair_stated_weight_and_size():
    """A camping chair: "제품 무게 / 2.3kg", "사이즈 / 60 x 55 x 90cm"."""
    f = D.read_rows([["모델명 / CX-200", "제품 무게 / 2.3kg", "사이즈 / 60 x 55 x 90cm", "소재 / 알루미늄"]])
    assert values(D.guess(f)) == {"product_weight_g": 2300, "package_weight_g": 2300, "package_length_mm": 900,
                                  "package_width_mm": 600, "package_height_mm": 550}


def test_core_plain_weight_row_and_product_size_label():
    f = D.read_rows([["무게 / 약 12.5kg", "제품 크기(가로x세로x높이) / 450 x 380 x 620 mm"]])
    g = D.guess(f)
    assert g["product_weight_g"]["how"] == "stated weight" and values(g)["package_length_mm"] == 620


def test_core_packed_box_conf_2():
    """An image's reading is never a seller's typed value: a stated box from OCR is 2 at most (research cap)."""
    f = D.read_rows([["박스 사이즈 130 x 32 x 30 cm / 포장 무게 9.2kg", "풀세트 총 무게 약 7.8kg"]])
    g = D.guess(f)
    assert g["package_weight_g"]["confidence"] == 2 and values(g)["package_weight_g"] == 9200
    assert g["product_weight_g"]["confidence"] == 2 and values(g)["product_weight_g"] == 7800
    assert [values(g)[n] for n in D.FIELDS[2:]] == [1300, 320, 300]


def test_core_package_never_below_contents():
    f = D.read_rows([["제품 중량 / 5kg"], ["포장 무게 3kg"]])
    assert values(D.guess(f))["package_weight_g"] == 5000


def test_core_never_reads_rules_people_prices_cross_sell():
    f = D.read_rows([["©상품의 무게가20kg가 초과하거나.택배 부피가 큰 경우 화물택배로인계될 수 있습니다",
                      "분유, 꿀: 5kg 이하 통관 가능", "체형 남성 · 182cm · 84kg", "무게 3.5kg 가격 150,000원"],
                     ["함께 구매하면 좋은 상품", "사이즈 10 x 7 x 126cm", "무게 2.5kg"]])
    assert D.guess(f) == {}


def test_core_has_no_parts_without_a_profile():
    """Club tables mean nothing to the core: no item sums, no container."""
    f = D.read_rows([["클럽 중량(g) / 310 / 306 / 304", "캐디백 무게 / 4.1kg", "45.5인치"]])
    assert not f["item_weights"] and not f["container_weights"] and not f["item_lengths"]
    assert D.guess(f, 12, True) == {}           # "캐디백 무게" is no product weight label


# ---- golf_set profile -----------------------------------------------------------------------------------------

def test_club_weights_from_labelled_rows_only():
    """10337644911: the club row counts, the shaft row (a part) does not."""
    f = D.read_rows([["클럽 중량(g) / 310 / 306 / 304 / 약318 / 316 / 313 / #3-약344 / 338 / 335",
                      "샤프트중량(g) / 58 / 56 / 54 / 58 / 56 / 54 / 68 / 64 / 60",
                      "헤드중량(g) / 252 / 259 / 266"]], GOLF)
    assert [x["g"] for x in f["item_weights"]] == [310, 306, 304, 318, 316, 313, 344, 338, 335]


def test_club_weight_glued_and_with_flex():
    f = D.read_rows([["클럽중량(g) / 약304g / 약301g / 약298g", "총 중량(g) / 밸런스 / 약 300g / D3 (ALTA J CB BLUE.SR.46인치)"]],
                    GOLF)
    assert [x["g"] for x in f["item_weights"]] == [304, 301, 298, 300]
    assert [x["mm"] for x in f["item_lengths"]] == [1168]           # 46" in the same row


def test_bag_triple_sets_three_sides():
    """13446843026: the PRGR caddie bag, sides after their units."""
    f = D.read_rows([["캐디백 PRGR", "사이즈:캐디백-91cm(세로)*31cm(폭)*40cm(가로),"]], GOLF)
    assert [x["mm"] for x in f["container_long"]] == [910]
    assert [x["mm"] for x in f["container_sides"]] == [[400, 310]]


def test_bag_weight_and_mouth_in_a_bag_table():
    """12696567111: the stand bag's own table."""
    f = D.read_rows([["XR 24 스탠드백", "사이즈 / 남성용9인치|무게 약 4.1kg |높이 약89cm"]], GOLF)
    assert [x["g"] for x in f["container_weights"]] == [4100] and not f["product_weights"]
    assert [x["mm"] for x in f["container_sides"]] == [[229, 229]]
    assert [x["mm"] for x in f["container_long"]] == [890]


def test_cross_sell_block_runs_to_the_end_of_the_image():
    """13369469193: the shop's cross-sell cards (half bag 10x7x126 cm) below 함께 구매."""
    f = D.read_rows([["함께 구매하면 좋은 상품", "미즈노 하프백", "-길이: 약10X7X126(CM)", "무게 2.5kg"],
                     ["캐디백 무게 / 3.5kg"]], GOLF)
    assert not f["container_long"] and [x["g"] for x in f["container_weights"]] == [3500]


def test_bag_words():
    f = D.read_rows([["※ 본 풀세트는 골프백 미포함 제품입니다"], ["12종+캐디백 포함"]], GOLF)
    assert len(f["container_no"]) == 1 and len(f["container_yes"]) == 1
    assert D.container_in("남성 풀세트 + 캐디백", GOLF) is True and D.container_in("골프백 미포함", GOLF) is False
    assert D.container_in("10PCS", GOLF) is None and D.container_in("캐디백 포함", None) is None


def test_bag_in_other_no_words():
    assert D.container_in("캐디백 별도구매", GOLF) is False and D.container_in("캐디백 없음", GOLF) is False
    assert D.container_in("XR26 풀세트 백포함", GOLF) is True


def test_image_count_most_frequent():
    f = D.read_rows([["11PCS 풀세트", "구성 11PCS", "드라이버 3PCS"]], GOLF)
    assert D.image_count(f) == 11


def test_guess_clubs_and_bag():
    """7583123963: 13 clubs and the bag set's own weight (캐디백+보스턴백 4.95 kg)."""
    f = D.read_rows([["헤드체적(cc) / 460cc"],
                     ["클럽중량(g) / 300g / 310g / 320g", "BM 캐디백 세트", "소재:PVC 코팅면/총무게:(캐디백+보스턴백)약4.95kg"]],
                    GOLF)
    g = D.guess(f, 13, None, GOLF)
    assert values(g)["product_weight_g"] == 13 * 310 + 4950
    assert g["product_weight_g"]["how"] == "13 clubs x median club weight + bag"
    assert g["package_weight_g"]["value"] == g["product_weight_g"]["value"]
    assert values(D.guess(f, 13, False, GOLF))["product_weight_g"] == 13 * 310      # no bag in this variant


def test_guess_needs_a_count_for_items():
    f = D.read_rows([["클럽중량(g) / 300g / 310g"]], GOLF)
    assert "product_weight_g" not in D.guess(f, None, None, GOLF)


def test_no_bag_drops_bag_sides():
    f = D.read_rows([["캐디백", "사이즈:캐디백-91cm(세로)*31cm(폭)*40cm(가로),"], ["골프백 미포함"],
                     ["길이 / 45.5\""]], GOLF)
    g = D.guess(f, 10, None, GOLF)
    assert values(g)["package_length_mm"] == 1156 and "package_width_mm" not in g


def test_set_weight_near_a_bag_is_the_sets_not_the_bags():
    """Review 2026-11-07: "캐디백 포함 풀세트 무게 약 7.5kg" was taken as the bag and added to the clubs (11.2 kg)."""
    f = D.read_rows([["클럽 중량(g) / 300 / 310 / 320", "캐디백 사이즈 9인치", "캐디백 포함 풀세트 무게 약 7.5kg"]], GOLF)
    assert [x["g"] for x in f["set_weights"]] == [7500] and not f["container_weights"]
    assert values(D.guess(f, 12, True, GOLF))["product_weight_g"] == 7500


def test_composition_line_does_not_hide_the_club_table():
    """6630856593: "우드(1/3/5 하이브리드):4개 / 골프백:1개" above the woods' rows (45" driver)."""
    f = D.read_rows([["_12개 클럽+1개 골프가방", "우드(1/3/5 하이브리드):4개 / 골프백:1개",
                      "WOOD / #1 / 60 / 10.5 / 197 / 50 / 62 / 45\" / D1", "클럽 중량(g) / 300 / 310 / 320"]], GOLF)
    assert [x["mm"] for x in f["item_lengths"]] == [1143] and len(f["item_weights"]) == 3


def test_package_never_below_its_contents():
    f = D.read_rows([["클럽 중량(g) / 400 / 410 / 420"], ["포장 무게 3kg"]], GOLF)
    g = D.guess(f, 12, False, GOLF)
    assert values(g)["package_weight_g"] == values(g)["product_weight_g"] == 4920


def test_bare_lengths_under_a_unit_label():
    """13780241403 "클럽길이(inch) / 45.5", 13553116678 "길이(cm/inch) / 112.395/44.25"."""
    f = D.read_rows([["클럽길이(inch) / 45.5", "길이(cm/inch) / 112.395/44.25", "샤프트 길이 / 46"]], GOLF)
    assert sorted({x["mm"] for x in f["item_lengths"]}) == [1124, 1156]


# ---- the merge ------------------------------------------------------------------------------------------------

def test_merge_larger_wins_and_compared_travels():
    g = {"package_width_mm": D._ev(400, 2, "bag mouth / sides", [{"quote": "q"}]),
         "package_length_mm": D._ev(910, 2, "bag length", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), g)
    assert taken == ["package_width_mm"]
    assert out["package_width_mm"]["source"] == "description_image" and out["package_width_mm"]["compared"]["value"] == 280
    assert out["package_length_mm"]["source"] == "category_default" and out["package_length_mm"]["compared"] == {"value": 910, "source": "description_image", "confidence": 2,
                                                                                                                 "how": "bag length"}


def test_merge_seller_value_compared_by_its_max():
    stated = {"value": {"min": 9000, "max": 9500}, "source": "source_stated", "confidence": 3}
    g = {"package_weight_g": D._ev(9200, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(package_weight_g=stated), g)
    assert not taken and out["package_weight_g"]["source"] == "source_stated"


def test_merge_respects_the_plausible_band():
    g = {"package_weight_g": D._ev(40000, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), g, {"package_weight_g": {"min": 3000, "max": 20000}})
    assert not taken and out["package_weight_g"]["compared"]["rejected"] == "implausible_for_category"


def test_merge_contradiction_without_value_takes_the_guess():
    g = {"product_weight_g": D._ev(3000, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(product_weight_g={"contradiction": []}), g)
    assert taken == ["product_weight_g"]


def test_core_axis_letter_sizes_and_a_split_label():
    """Live 2026-11-07, other categories: a camping chair (11236665331) "W53 X D38 X H62.5 cm"; a kettle (9809159942)
    "사이즈 / W100 × D170 × H170 mm" and "무 / 0.6kg" (OCR split 무게 into its letters)."""
    g = D.guess(D.read_rows([["W53 X D38 X H62.5 cm"]]))
    assert [values(g)[n] for n in D.FIELDS[2:]] == [625, 530, 380]
    g = D.guess(D.read_rows([["모 / 델명 / AL-606G", "사이즈 / W100 × D170 × H170 mm", "무 / 0.6kg"]]))
    assert values(g) == {"product_weight_g": 600, "package_weight_g": 600, "package_length_mm": 170,
                         "package_width_mm": 170, "package_height_mm": 100}


# ---- profiles by category, absurd values, an unknown container ----------------------------------------------

def test_profile_by_naver_category_id():
    assert D.profile_for("50002788") is GOLF and D.profile_for(50002788) is GOLF
    assert D.profile_for("50000830") is None and D.profile_for(None) is None


def test_absurd_guesses_are_never_taken():
    """A misread "45.5kg" (4.55 kg) or a 12 m side: outside the core / profile band, or 3x today's value."""
    g = {"product_weight_g": D._ev(45500, 2, "x", [{"quote": "q"}]),
         "package_length_mm": D._ev(12000, 2, "x", [{"quote": "q"}]),
         "package_width_mm": D._ev(900, 2, "x", [{"quote": "q"}])}
    out, taken = D.merge_fields(fields(), g)                         # no profile: the core band, then the ratio
    assert not taken
    assert out["product_weight_g"]["compared"]["rejected"] == "far_above_today"           # 45.5 > 3 x 5.7 kg
    assert out["package_length_mm"]["compared"]["rejected"] == "implausible_for_category"  # over 3 m
    assert out["package_width_mm"]["compared"]["rejected"] == "far_above_today"
    out, taken = D.merge_fields(fields(), {"package_width_mm": D._ev(750, 2, "x", [{"quote": "q"}])}, None, GOLF)
    assert out["package_width_mm"]["compared"]["rejected"] == "implausible_for_category"   # golf box: <= 700 mm


def test_unknown_container_lowers_confidence():
    """The owner, 2026-11-07: one default covers sets with and without the bag; when the variant does not say,
    the images' guess is weaker (1)."""
    f = D.read_rows([["클럽중량(g) / 300g / 310g / 320g", "캐디백 무게 / 4kg"]], GOLF)
    unknown, known = D.guess(f, 12, None, GOLF), D.guess(f, 12, True, GOLF)
    assert unknown["product_weight_g"]["confidence"] == 1 and unknown["product_weight_g"]["flags"] == ["container_unknown"]
    assert known["product_weight_g"]["confidence"] == 2 and "flags" not in known["product_weight_g"]
    assert D.guess(D.read_rows([["박스 사이즈 130 x 32 x 30 cm"]], GOLF), 12, None, GOLF)["package_length_mm"]["confidence"] == 2



def test_low_confidence_rows_give_no_single_value():
    """Review 2026-11-07: the larger value wins, so an upward misread ("4.5kg" read "45kg") is the one that gets
    in; a row read below 0.9 gives no box, weight or length, only its share of the items' median."""
    rows = [("포장 무게 45kg", 0.80), ("제품 사이즈 / 140 x 35 x 30cm", 0.85), ("클럽 중량(g) / 300 / 310", 0.80),
            ("길이 / 48.5\"", 0.70)]
    f = D.read_rows([rows], GOLF)
    assert not f["packed_weights"] and not f["product_sizes"] and not f["item_lengths"]
    assert [x["g"] for x in f["item_weights"]] == [300, 310]
    f = D.read_rows([[("포장 무게 4.5kg", 0.99)]])
    assert [x["g"] for x in f["packed_weights"]] == [4500]
