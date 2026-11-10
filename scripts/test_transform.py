"""Offline tests for the transform (transform.py, transform_shops.py, keep_run.py, run_transform.py).

fixtures/collected_fairwardgolf.jsonl: real collected lines, trimmed. 7583123963 is example_99's own output
(2026-11-05, photos and all); the other four were built offline from our API's real answers of 2026-11-05
(details, specs, selected reviews; variants with paid=True like the harvester, package from the category table;
gallery files stand-ins) for products the naver-harvester published, whose published values are asserted here.

    .venv/bin/python -m pytest scripts/test_transform.py -q
"""
import copy
import dataclasses
import json
import os
import stat

import pytest

import description_images
import keep_run
import run_transform
import spec_variants
import transform
from transform import prepare, sku, text_id, usd
from transform_shops import ShopRulesMissing, rules_for

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "collected_fairwardgolf.jsonl")
RULES_ON = rules_for("fairwardgolf")
# the description images' guess is tested on its own (test_image_measures_*): off here, as for a category without it
RULES = dataclasses.replace(RULES_ON, categories={k: dataclasses.replace(v, description_images=False)
                                                  for k, v in RULES_ON.categories.items()})


def lines():
    with open(FX, encoding="utf-8") as f:
        return {json.loads(x)["key"].split(":")[3]: json.loads(x) for x in f}


def prep(pid, change=None, rules=RULES):
    line = copy.deepcopy(lines()[pid])
    if change:
        change(line)
    return prepare(line, rules, "50002788-20261105T000000Z", 1)


def test_sku_and_price_as_published():
    assert sku("FW-", "fairwardgolf:naver:500186740:12945108653", 'observed:["풀세트"]') == "FW-9402af11868726eba5902af5"
    assert (usd(1970000, 1000), usd(12341, 1000), usd(12340, 1000), usd(1, 1000)) == ("1970.00", "12.35", "12.34", "0.01")


def test_one_variant_is_the_default_and_its_value_a_fact():
    p = prep("12945108653")                            # XXIO 13: published as 1 variant at $1,970.00
    [v] = p["product"]["variants"]
    assert p["status"] == "ready" and p["product"]["options"] == []
    assert (v["sku"], v["price_krw"], v["price_usd"]) == ("FW-9402af11868726eba5902af5", 1970000, "1970.00")
    assert p["product"]["facts"] == [{"label_ko": "", "value_ko": "풀세트"}]          # 선택사항 says nothing
    assert [n for n in p["notes"] if n["code"] != "reviews_cleaned"] == []   # the reviews' counts: review_clean
    gender = p["product"]["attributes"]["gender"]                          # no 성별 row: "여성" in the name
    assert gender["value"] == "womens" and [e["source"] for e in gender["evidence"]] == ["title"]


def test_observed_rows_three_axes_two_leaves():
    p = prep("8514409092")                             # GVTOUR: 69 rows of 3 axes, 남녀공용
    pr = p["product"]
    assert p["status"] == "ready" and len(pr["variants"]) == 69 and len(pr["options"]) == 3
    gender = pr["attributes"]["gender"]                    # the 성별 row 남녀공용, "(여성용)" on a third of the values
    assert gender["value"] == "mixed" and sorted(set(gender["variants"].values())) == ["mens", "womens"]
    base = pr["pricing"]["base_krw"]
    assert all(v["price_krw"] >= base and v["sku"].startswith("FW-") for v in pr["variants"])
    assert len({v["sku"] for v in pr["variants"]}) == 69
    assert all(len(v["options_ko"]) == 3 for v in pr["variants"])


def test_personalization_and_paid_addons():
    p = prep("12973087370")                            # XXIO 14: a name on the clubs, paid utility add-ons
    [field] = p["product"]["personalization"]
    assert field["required"] and field["max_length"] == 20 and "이름" in field["label_ko"]
    paid = p["product"]["addons"]                       # 50002788: paid_addons=True, offered with their price
    assert paid and all(a["price_krw"] > 0 and a["price_usd"] == usd(a["price_krw"], 1000) for a in paid)
    assert "paid_addons_left_out" not in {n["code"] for n in p["notes"]}
    off = dataclasses.replace(RULES.categories["50002788"], paid_addons=False)
    p = prep("12973087370", rules=dataclasses.replace(RULES, categories={"50002788": off}))
    assert p["product"]["addons"] == [] and "paid_addons_left_out" in {n["code"] for n in p["notes"]}


def test_free_addons_only():
    def gift(line):
        line["specs"]["options"]["supplements"] = [
            {"id": "1", "group": "사은품", "name": "장갑", "price": 0, "stock_quantity": 5, "status": "SALE"},
            {"id": "2", "group": "사은품", "name": "품절 장갑", "price": 0, "stock_quantity": 0, "status": "SALE"},
            {"id": "3", "group": "추가", "name": "우드", "price": 490000, "stock_quantity": 5, "status": "SALE"}]
    off = dataclasses.replace(RULES.categories["50002788"], paid_addons=False)
    assert prep("12973087370", gift, dataclasses.replace(RULES, categories={"50002788": off}))["product"]["addons"] == [
        {"group_ko": "사은품", "name_ko": "장갑", "required": False, "price_krw": 0, "price_usd": "0.00"}]
    assert [a["name_ko"] for a in prep("12973087370", gift)["product"]["addons"]] == ["장갑", "우드"]


def test_spec_rows_shown():
    rows = prep("12945108653")["product"]["specs"]
    labels = [r["label_ko"] for r in rows]
    assert "상품번호" not in labels and "제조일자" not in labels and "브랜드" in labels

    def promo(line):
        line["specs"]["specs"] += [{"label": "이벤트", "value": "포토리뷰 적립"}, {"label": "사은품", "value": "볼"},
                                   {"label": "색상", "value": "상세페이지 참조"}, {"label": "색상2", "value": "화이트"}]
    labels = [r["label_ko"] for r in prep("12945108653", promo)["product"]["specs"]]
    assert "이벤트" not in labels and "사은품" not in labels and "색상" not in labels and "색상2" in labels


def test_a_review_discount_axis_is_dropped():
    def review_axis(line):                             # the shape the harvester published as "Photo review discount"
        rows = []
        for r in line["specs"]["options"]["variants"]:
            for value, delta in (("리뷰 작성 O", -5000), ("리뷰 작성 X", 0)):
                rows.append({**r, "options": r["options"] + [value], "extra_price": r["extra_price"] + delta,
                             "id": f"{r['id']}{value[-1]}"})
        line["specs"]["options"]["variants"] = rows
        line["specs"]["options"]["option_groups"].append({"id": "9", "name": "포토리뷰 할인", "type": "COMBINATION"})
    p = prep("8357720534", review_axis)
    base = prep("8357720534")
    assert len(p["product"]["options"]) == len(base["product"]["options"])
    assert sorted(v["price_krw"] for v in p["product"]["variants"]) == \
        sorted(v["price_krw"] for v in base["product"]["variants"])          # the rows without the discount


@pytest.mark.parametrize("change, code", [
    (lambda l: l.update(specs=None), "collect_incomplete"),
    (lambda l: l["specs"].update(options=None), "collect_incomplete"),
    (lambda l: l["details"]["pricing"].update(discounted_price=None), "price_unknown"),
    (lambda l: l["photos"].update(files=[]), "no_images"),
    (lambda l: l["photos"].update(files=l["photos"]["files"] * 51), "images_over_50"),
    (lambda l: l["specs"]["options"].update(variants=[]), "no_variants"),
])
def test_held(change, code):
    p = prep("8514409092", change)
    assert p["status"] == "held" and code in [h["code"] for h in p["held"]]


def test_no_brand_takes_the_manufacturer():
    """The owner, 2026-11-08: no brand stated, at least the manufacturer; Naver's M0000000 and a pointer are none."""
    def maker(value):
        def change(line):
            line["specs"]["facts"].update(brand=None, manufacturer={"value": value,
                                                                    "source": "search_info.manufacturerName"})
        return change
    p = prep("8514409092", maker("(주)삼양인터내셔날"))
    assert p["product"]["brand_ko"] == "(주)삼양인터내셔날"
    assert p["product"]["brand_source"] == "manufacturer:search_info.manufacturerName"
    for none in ("M0000000", "상세정보참조"):
        p = prep("8514409092", maker(none))
        assert p["status"] == "ready" and p["product"]["brand_ko"] is None   # left to brand_fallback (run-level)


def test_caps():
    small = dataclasses.replace(RULES, variant_cap=10)
    full, p = prep("8514409092"), prep("8514409092", rules=small)
    assert p["status"] == "ready" and len(p["product"]["variants"]) == 10       # capped, not held
    assert {n["code"]: n["detail"] for n in p["notes"]}["variants_capped"] == "69 -> 10"
    assert {v["sku"] for v in p["product"]["variants"]} <= {v["sku"] for v in full["product"]["variants"]}
    for o in full["product"]["options"]:           # values kept in page order; with room, every one on sale
        kept = next(k for k in p["product"]["options"] if k["name_ko"] == o["name_ko"])
        assert kept["values_ko"] == [v for v in o["values_ko"] if v in kept["values_ko"]]
    roomy = prep("8514409092", rules=dataclasses.replace(RULES, variant_cap=sum(
        len(o["values_ko"]) for o in full["product"]["options"])))
    assert roomy["product"]["options"] == full["product"]["options"]

    def four_axes(line):
        line["specs"]["options"]["option_groups"].append({"id": "9", "name": "색상", "type": "COMBINATION"})
        for i, r in enumerate(line["specs"]["options"]["variants"]):
            r["options"] = r["options"] + [f"색{i % 2}"]
    assert "axes_over_3" in [h["code"] for h in prep("8514409092", four_axes)["held"]]


def test_texts_are_the_translation_worklist():
    a, b = prep("12973087370"), prep("8514409092")
    for p in (a, b):
        assert all(t["id"] == text_id(t["kind"], t["ko"]) for t in p["texts"])
        assert len({t["id"] for t in p["texts"]}) == len(p["texts"])
        kinds = {t["kind"] for t in p["texts"]}
        assert {"title", "brand", "option_name", "option_value", "spec_label", "spec_value"} <= kinds
    shared = {t["id"] for t in a["texts"]} & {t["id"] for t in b["texts"]}
    assert text_id("spec_label", "성별") in shared                         # the same Korean, the same id


def test_unknown_shop_or_category():
    with pytest.raises(ShopRulesMissing, match="skinsli: no transform rules"):
        rules_for("skinsli")
    with pytest.raises(ShopRulesMissing, match="Naver category 1 "):
        prep("8514409092", lambda l: l["specs"].update(category={"id": "1", "name": "x"}))


def test_keep_run_and_run_transform(tmp_path):
    src = tmp_path / "full-50002788"
    src.mkdir()
    (src / "products.jsonl").write_bytes(open(FX, "rb").read())
    for pid in ("7583123963", "999"):                                     # 999: an older run's product
        (src / "images" / pid).mkdir(parents=True)
        (src / "images" / pid / "a.webp").write_bytes(b"x")
    shops = tmp_path / "shops"
    target = keep_run.keep(str(src), str(shops))
    kept = os.path.join(target, "products.jsonl")
    assert open(kept, "rb").read() == open(FX, "rb").read() and not os.stat(kept).st_mode & stat.S_IWUSR
    assert sorted(os.listdir(os.path.join(target, "images"))) == ["7583123963"]
    with pytest.raises(keep_run.KeepError, match="already kept"):
        keep_run.keep(str(src), str(shops))
    first = run_transform.run("fairwardgolf", None, str(shops))
    out = os.path.join(first["out_dir"], "products.jsonl")
    once = open(out, "rb").read()
    run_transform.run("fairwardgolf", None, str(shops))
    assert open(out, "rb").read() == once                                  # the same input, the same bytes
    assert [p["status"] for p in first["prepared"]].count("ready") == 5
    assert first["report"][0].startswith("transform fairwardgolf: 5 products from 1 run(s): 5 ready, 0 held {}, notes")


def test_keep_run_refuses_mixed_shops(tmp_path):
    src = tmp_path / "run"
    src.mkdir()
    ls = list(lines().values())[:2]
    ls[1] = {**ls[1], "key": ls[1]["key"].replace("fairwardgolf", "skinsli")}
    (src / "products.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ls))
    with pytest.raises(keep_run.KeepError, match="one shop and one category"):
        keep_run.keep(str(src), str(tmp_path / "shops"))


def test_rows_that_do_not_fit_the_groups_are_held():
    def standard(line):                            # groups of another type: still the axes (not CUSTOM / SIMPLE)
        for g in line["specs"]["options"]["option_groups"]:
            g["type"] = "STANDARD"
    p = prep("8514409092", standard)
    assert p["status"] == "ready" and len(p["product"]["variants"]) == 69

    def unaligned(line):
        line["specs"]["options"]["option_groups"] = []
    p = prep("8514409092", unaligned)
    assert [h["code"] for h in p["held"]] == ["options_unaligned"] and p["product"]["variants"] == []


def test_runs_newest_wins_and_unfinished_copies_are_skipped(tmp_path):
    shops = tmp_path / "shops"
    first = dict(lines()["12945108653"])
    second = {**first, "details": {**first["details"], "name": first["details"]["name"] + " 신상"}}
    for i, line in enumerate((first, second)):
        src = tmp_path / f"run{i}"
        src.mkdir()
        (src / "products.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
        os.utime(src / "products.jsonl", (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
        keep_run.keep(str(src), str(shops))
    collected = shops / "fairwardgolf" / "collected"
    (collected / "50002788-29991231T000000Z.partial").mkdir()       # a stopped copy
    (collected / "stray.txt").write_text("x")
    assert len(run_transform.kept_runs("fairwardgolf", str(shops))) == 2
    [p] = run_transform.run("fairwardgolf", None, str(shops))["prepared"]
    assert p["product"]["title_ko"].endswith(" 신상") and p["source"]["line"] == 1      # the newer run's line


def test_run40_fixes():
    def delivery_note(line):                       # TaylorMade 10870655883: 선택사항 = 인기조합 / 배송메세지기입
        line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "선택사항", "type": "COMBINATION"}]
        base = line["specs"]["options"]["variants"][0]
        line["specs"]["options"]["variants"] = [{**base, "id": "a", "options": ["인기조합"]},
                                                {**base, "id": "b", "options": ["배송메세지기입"]}]
    p = prep("8514409092", delivery_note)
    assert len(p["product"]["variants"]) == 1 and p["product"]["facts"] == [{"label_ko": "", "value_ko": "인기조합"}]

    def legal_rows(line):
        line["specs"]["specs"] += [{"label": "인증정보", "value": "구매대행 상품으로 전기용품 안전관리법..."},
                                   {"label": "원산지", "value": "일본산(구매대행)"}]
    rows = {r["label_ko"]: r["value_ko"] for r in prep("12945108653", legal_rows)["product"]["specs"]}
    assert "인증정보" not in rows and rows["원산지"] == "일본산"

    def code_axis(line):                           # Callaway 13777887875: a one-value axis 상품번호 = '2109 cmix'
        line["specs"]["options"]["option_groups"][0]["name"] = "상품번호"
    assert prep("12945108653", code_axis)["product"]["facts"] == []

    label = prep("12973087370")["product"]["personalization"][0]["label_ko"]
    assert "★" not in label and "(필수)" not in label and "이름" in label

    def folded(line):
        line["specs"]["is_complete"] = False
    assert "specs_folded" in [h["code"] for h in prep("8514409092", folded)["held"]]

    def overseas(line):
        line["specs"]["delivery"] = {"fee_type": "UNIT_QUANTITY_PAID", "base_fee": 99000, "is_overseas": True,
                                     "customs_tax_type": None}
    p = prep("8514409092", overseas)
    assert {"shipping_paid", "overseas_shipping"} <= {n["code"] for n in p["notes"]} and p["status"] == "ready"
    assert p["product"]["delivery"]["base_fee"] == 99000
    assert {"description_ko", "description_images"} <= set(p["product"])


def test_notes_for_vague_axis_names_and_paid_addons():
    def vague(line):
        line["specs"]["options"]["option_groups"][1]["name"] = "선택2"
    p = prep("8514409092", vague)
    assert {"code": "option_name_placeholder", "detail": "선택2"} in p["notes"]
    off = dataclasses.replace(RULES.categories["50002788"], paid_addons=False)
    p = prep("12973087370", rules=dataclasses.replace(RULES, categories={"50002788": off}))
    assert {"code": "paid_addons_left_out", "detail": "4 paid add-ons"} in p["notes"]   # XXIO 14: 4 paid utilities


def test_paid_variants_follow_the_category():
    pid = "8357720534"
    paid = {v["source_id"] for v in prep(pid)["product"]["variants"]}          # 50002788: paid_variants=True
    cat = dataclasses.replace(RULES.categories["50002788"], paid_variants=False)
    free = prep(pid, rules=dataclasses.replace(RULES, categories={"50002788": cat}))
    line = lines()[pid]
    priced = sum(1 for v in line["specs"]["options"]["variants"] if v["extra_price"])
    assert priced and len(paid) == len(line["specs"]["options"]["variants"])
    assert len(free["product"]["variants"]) == len(paid) - priced
    assert {"code": "paid_variants_left_out", "detail": f"{priced} variants change the price"} in free["notes"]
    assert "paid_variants_left_out" not in {n["code"] for n in prep(pid)["notes"]}


def test_pages40_fixes():
    def sets(line):                                # T2 / T8: 12종 in the title, 9종 sold too; doubled spaces
        line["details"]["name"] = "젝시오 12종 풀세트"
        line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "옵션+아이언커버.하프백", "type": "COMBINATION"}]
        base = line["specs"]["options"]["variants"][0]
        line["specs"]["options"]["variants"] = [{**base, "id": "a", "options": ["선택1  12종  카본"], "extra_price": 0},
                                                {**base, "id": "b", "options": ["선택2 9종 스틸"], "extra_price": 0}]
    p = prep("12945108653", sets)
    assert p["product"]["options"] == [{"name_ko": "옵션+아이언커버.하프백", "values_ko": ["12종 카본", "9종 스틸"]}]
    assert p["product"]["variants"][0]["options_ko"] == ["12종 카본"]
    assert p["product"]["variants"][0]["source_id"] == 'observed:["선택1  12종  카본"]'      # the SKU keeps the raw
    codes = {n["code"]: n["detail"] for n in p["notes"]}
    assert codes["title_names_one_variant"] == "12종" and codes["option_name_placeholder"] == "옵션+아이언커버.하프백"

    def mixed(line):                               # T4: no 성별 row, 남성 in the name, 여성 sets among the values
        line["specs"]["specs"] = [r for r in line["specs"]["specs"] if r["label"] != "성별"]
        line["details"]["name"] = "남성 풀세트"
        line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "구성", "type": "COMBINATION"}]
        base = line["specs"]["options"]["variants"][0]
        line["specs"]["options"]["variants"] = [{**base, "id": "a", "options": ["남성 R"], "extra_price": 0},
                                                {**base, "id": "b", "options": ["여성 L"], "extra_price": 0}]
    p = prep("8514409092", mixed)
    gender = p["product"]["attributes"]["gender"]
    assert gender["value"] == "mixed" and sorted(gender["variants"].values()) == ["mens", "womens"]

    def required_group(line):                      # T5: a free add-on group the buyer must choose from
        line["specs"]["options"]["supplements"] = [
            {"id": "1", "group": "유틸리티(필수선택)", "name": "유틸 4번", "price": 0, "stock_quantity": 3, "status": "SALE"}]
    assert prep("12973087370", required_group)["product"]["addons"] == [
        {"group_ko": "유틸리티", "name_ko": "유틸 4번", "required": True, "price_krw": 0, "price_usd": "0.00"}]

    def agency(line):                              # T6 / T7: the importer in brackets; a purchase-agency item
        line["specs"]["specs"] += [{"label": "원산지", "value": "일본(IRUGI SHOJI)"}]
        line["specs"]["delivery"] = {**(line["specs"].get("delivery") or {}), "policy_text": "해외 구매대행 상품",
                                     "extra_fee_text": "제주 도서산간 10,000"}
    p = prep("12945108653", agency)
    assert {r["label_ko"]: r["value_ko"] for r in p["product"]["specs"]}["원산지"] == "일본"
    assert "purchase_agency" in {n["code"] for n in p["notes"]}
    assert p["product"]["delivery"]["extra_fee_text"] == "제주 도서산간 10,000"


def test_reverify40_fixes():
    T = transform
    # title / spec rows true of part of the values (2026-11-06 re-run)
    opts = [{"name_ko": "구성", "values_ko": ["BM 풀세트 스틸 블랙 13PCS", "BM 풀세트 여성 실버 12PCS",
                                              "BM 풀세트 카본 골드 13PCS"]}]
    assert spec_variants.title_one_variant("지브이투어 BM 13 PCS 남성 여성 풀세트", opts) == ["13PCS"]
    flex = [{"name_ko": "선택", "values_ko": ["10.5도R 4번유틸", "10.5도SR 4번유틸", "9도S 4번유틸"]}]
    assert spec_variants.title_one_variant("스텔스2 드라이버10.5도R 4번유틸", flex) == ["10.5도R"]          # the title's own span
    pair = [{"name_ko": "세트", "values_ko": ["12종 스틸", "12종 카본", "9종 스틸", "9종 카본"]}]
    assert spec_variants.title_one_variant("PGM 풀세트 12종", pair) == ["12종"]
    assert spec_variants.title_one_variant("PGM 풀세트 스틸 카본 선택", pair) == []          # names the choice
    assert spec_variants.title_one_variant("PGM 풀세트", pair) == []
    # spec rows vs the variants: test_spec_variants.py
    # 원산지 with brackets inside brackets; numbering on add-ons; jump links
    assert T.spec_rows({"specs": [{"label": "원산지", "value": "중국산((주)위스트OEM)"}]}) == [
        {"label_ko": "원산지", "value_ko": "중국산"}]
    assert T._plain("1-1.남성 합피 장갑") == "남성 합피 장갑" and T._plain("6.쇼핑백") == "쇼핑백"
    assert T._plain("9.5도 드라이버") == "9.5도 드라이버"

    def numbered(line):                            # two values the same once 선택N is gone: kept, noted
        line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "선택", "type": "COMBINATION"}]
        base = line["specs"]["options"]["variants"][0]
        line["specs"]["options"]["variants"] = [{**base, "id": "a", "options": ["선택3 10.5 S"], "extra_price": 0},
                                                {**base, "id": "b", "options": ["선택6 10.5 S"], "extra_price": 0}]
        line["details"]["name"] = "남성 풀세트 [3PCS]"
        line["specs"]["delivery"] = {**(line["specs"].get("delivery") or {}), "extra_fee_area2": 3000,
                                     "extra_fee_text": "18000"}
        line["details"]["notice"] = {**(line["details"].get("notice") or {}), "terms": [
            {"label": "소비자가 부담하는 반품비용 등에 관한 정보", "value": "편도 18000원"}]}
    p = prep("12945108653", numbered)
    assert p["product"]["options"][0]["values_ko"] == ["선택3 10.5 S", "선택6 10.5 S"]
    codes = {n["code"]: n["detail"] for n in p["notes"]}
    assert codes["option_values_duplicate"] == "선택" and codes["few_pieces"] == "3PCS"
    assert p["product"]["delivery"]["extra_fee_text"] is None          # the return fee typed in the area field

    def other_number(line):                        # "7000" beside a 4,000 area fee: not the return fee, kept
        numbered(line)
        line["specs"]["delivery"]["extra_fee_text"] = "7000"
    assert prep("12945108653", other_number)["product"]["delivery"]["extra_fee_text"] == "7000"


def _fixture(pid):
    with open(os.path.join(os.path.dirname(FX), "collected", pid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def test_pilot20_transform():
    # 2026-11-06 pilot on 20 more sets
    p = prepare(_fixture("8958060680"), RULES, "r", 1)               # "[당일출고]" on both values; only S ships today
    assert p["product"]["options"][0]["values_ko"] == ["스틸 샤프트 (S) SPEC", "카본 샤프트 (R) SPEC"]
    assert [v["today_dispatch"] for v in p["product"]["variants"]] == [True, False]
    assert p["product"]["variants"][0]["source_id"].startswith('observed:["[당일출고]')    # the SKU keeps the raw
    p = prepare(_fixture("13553116678"), RULES, "r", 1)              # "(선택)샤프트/드라이버/아이언"
    assert all(not o["name_ko"].startswith("(선택)") for o in p["product"]["options"])
    p = prepare(_fixture("13302492097"), RULES, "r", 1)              # 128 -> 100, 총클럽개수 3개
    codes = {n["code"]: n["detail"] for n in p["notes"]}
    assert codes["variants_capped"] == "128 -> 100" and codes["few_pieces"] == "3종"           # the title says it
    first = {}
    for v in p["product"]["variants"]:
        first[v["options_ko"][0]] = first.get(v["options_ko"][0], 0) + 1
    assert max(first.values()) - min(first.values()) <= 4             # shared out between the two drivers (was 64 / 36)
    p = prepare(_fixture("10816781893"), RULES, "r", 1)              # 사은품 오리지널커버 증정: a thing, hidden
    assert {n["code"]: n["detail"] for n in p["notes"]}["gift_hidden"] == "오리지널커버 증정"


def test_run40b_transform():
    # 2026-11-07, 40 more sets
    full = _fixture("12950788305")                                   # 497 combinations of 3 axes, cap 100
    p = prepare(full, RULES, "r", 1)
    assert len(p["product"]["variants"]) == 100
    sold = {tuple(v["options_ko"]) for v in p["product"]["variants"]}
    n = len(p["product"]["options"])
    pairs = lambda combos: {(a, x[a], b, x[b]) for x in combos for a in range(n) for b in range(a + 1, n)}
    every = {tuple(_tidy_all(r["options"])) for r in full["specs"]["options"]["variants"] if r.get("is_available")}
    assert pairs(every) <= pairs(sold)                                # every pair of values still buyable
    def few(pid):
        return {x["code"]: x["detail"] for x in prepare(_fixture(pid), RULES, "r", 1)["notes"]}.get("few_pieces")
    assert few("13058280430") == "3종" and few("10954221464") in ("5P", "하프세트") and few("13058200331") == "2종"
    assert few("11042680586") is None and few("13780241403") is None        # "10+1pcs"; a 12pc set (row 3개)
    origin = {r["label_ko"]: r["value_ko"] for r in prepare(_fixture("13026991307"), RULES, "r", 1)["product"]["specs"]}
    assert origin["원산지"] == "미국산(핑(미국) 미즈노(일본) 웨지퍼터(중국))"       # the parts' own countries
    p = prepare(_fixture("9168175809"), RULES, "r", 1)              # the only option is SIMPLE
    assert {"label_ko": "", "value_ko": "드라이버+우드+하이브리드/SR"} in p["product"]["facts"]
    p = prepare(_fixture("13462927626"), RULES, "r", 1)             # "[G192]01_미즈노 클럽 렌치"; 색상 = 세트 R / S
    assert p["product"]["addons"][0]["name_ko"] == "미즈노 클럽 렌치" and p["product"]["addons"][0]["group_ko"] == "렌치"
    assert "색상" in {x["code"]: x["detail"] for x in p["notes"]}["option_name_placeholder"]


def _tidy_all(values):
    return [transform._tidy(v) for v in values]


def test_few_pieces_not_when_a_variant_is_a_full_set():
    p = prepare(_fixture("6999516176"), RULES, "r", 1)              # title "4종 스틸", values 4종 / 12종 sets
    assert "few_pieces" not in {x["code"] for x in p["notes"]}


SIDECAR_ROWS = [["BM 캐디백 세트", "소재:PVC 코팅면/총무게:(캐디백+보스턴백)약4.95kg",
                 "사이즈:캐디백-91cm(세로)*31cm(폭)*40cm(가로),"],
                ["클럽중량(g) / 300g / 310g / 320g", "길이 / 45.5\""]]


def sidecar(rows=SIDECAR_ROWS, pid="7583123963"):
    links, _ = description_images.pick_links(lines()[pid]["details"].get("description") or {})
    return {"format": "description_images/1", "links_sha256": description_images.links_sha(links), "images": [
        {"link": f"https://shop-phinf.pstatic.net/{n}.jpg", "status": "read",
         "slices": [{"y0": 0, "y1": 100, "rows": [{"text": t, "conf": 0.99, "y": 0} for t in r]}]}
        for n, r in enumerate(rows)]}


def test_image_measures_switch_on_without_sidecar_is_a_note():
    pid = next(iter(lines()))
    p = prepare(copy.deepcopy(lines()[pid]), RULES_ON, "r", 1)
    assert {"code": "description_images_missing", "detail": "no sidecar: run description_images.py"} in p["notes"]
    assert p["status"] == prep(pid)["status"]                    # never holds


def test_image_measures_larger_wins_per_variant():
    """The owner, 2026-11-07: the larger of today's value and the images' guess. A 13-club set with the bag set
    (4.95 kg): 13 x 310 g + 4950 g = 8980 g (the women's 12PCS variants: 8670 g) beats the category's 7000 g; the bag's 40 x 31 cm beats 280 / 230 mm;
    the longest side (1156 mm club, 910 mm bag) stays under the category's 1250 mm. 7583123963: "13 PCS ...
    (백세트포함)"."""
    pid = "7583123963"
    line = copy.deepcopy(lines()[pid])
    p = prepare(line, RULES_ON, "r", 1, sidecar())
    off = prep(pid)
    for v, before in zip(p["product"]["variants"], off["product"]["variants"]):
        pk = v["package"]
        assert pk["package_weight_g"]["source"] == "description_image"
        clubs = 12 if "12PCS" in " ".join(v["options_ko"]) else 13          # the variant's own count
        assert pk["package_weight_g"]["value"]["max"] == clubs * 310 + 4950 == pk["product_weight_g"]["value"]["max"]
        assert pk["package_weight_g"]["compared"] == {"value": 7000, "source": "category_default",
                                                     **({"confidence": 1} if "confidence" in before["package"][
                                                         "package_weight_g"] else {})}
        assert pk["package_width_mm"]["value"]["max"] == 400 and pk["package_height_mm"]["value"]["max"] == 310
        assert pk["package_length_mm"] == {**before["package"]["package_length_mm"],
                                           "compared": pk["package_length_mm"]["compared"]}
    note = next(n for n in p["notes"] if n["code"] == "measures_from_images")
    assert "package_weight_g" in note["detail"] and "package_length_mm" not in note["detail"]
    assert lines()[pid]["package"] == line["package"]            # the collected line is never changed


def test_image_measures_nothing_to_go_on_changes_nothing():
    pid = next(iter(lines()))
    p = prepare(copy.deepcopy(lines()[pid]), RULES_ON, "r", 1, sidecar([["좋은 클럽입니다"]], pid))
    assert [v["package"] for v in p["product"]["variants"]] == [v["package"] for v in prep(pid)["product"]["variants"]]
    assert not any(n["code"].startswith(("measures_from", "description_images")) for n in p["notes"])


def test_image_measures_stale_sidecar_is_a_note_and_not_used():
    """A sidecar read from other links (an older collection of the product) is not used."""
    pid = "7583123963"
    p = prepare(copy.deepcopy(lines()[pid]), RULES_ON, "r", 1, {**sidecar(), "links_sha256": "old"})
    assert any(n["code"] == "description_images_stale" for n in p["notes"])
    assert [v["package"] for v in p["product"]["variants"]] == [v["package"] for v in prep(pid)["product"]["variants"]]


def test_image_measures_without_a_profile_use_the_core_only(monkeypatch):
    """A category with the switch on and no parts profile (none mapped to its Naver id): club tables and bags mean
    nothing; a stated product weight and size still count (any category)."""
    import description_measures
    monkeypatch.setattr(description_measures, "CATEGORY_PROFILES", {})
    core = RULES_ON
    pid = "7583123963"
    p = prepare(copy.deepcopy(lines()[pid]), core, "r", 1, sidecar())
    assert all(f["source"] != "description_image" for v in p["product"]["variants"] for f in v["package"].values())
    p = prepare(copy.deepcopy(lines()[pid]), core, "r", 1,
                sidecar([["제품 무게 / 12kg", "제품 사이즈 / 140 x 35 x 30cm"]]))
    pk = p["product"]["variants"][0]["package"]
    assert pk["product_weight_g"]["value"]["max"] == 12000 and pk["package_length_mm"]["value"]["max"] == 1400


def test_naver_placeholder_manufacturer_is_not_a_spec():
    """13464713764, 2026-11-08: 제조사 "M0000000" is Naver's code for no manufacturer."""
    from transform import spec_rows
    rows = spec_rows({"specs": [{"label": "제조사", "value": "M0000000"}, {"label": "원산지", "value": "국내산"}]})
    assert rows == [{"label_ko": "원산지", "value_ko": "국내산"}]


def test_free_only_rules_turn_paid_off_for_every_category():
    from transform_shops import rules_for, without_paid
    free = without_paid(rules_for("fairwardgolf")).category("50002788")
    assert not free.paid_variants and not free.paid_addons and free.description_images
    assert rules_for("fairwardgolf").category("50002788").paid_addons          # the shop's own rule unchanged
