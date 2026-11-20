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
    p = prep("8514409092", maker("혼마코리아"))
    assert p["product"]["brand_ko"] == "혼마코리아"
    assert p["product"]["brand_source"] == "manufacturer:search_info.manufacturerName"
    # a trading company is no maker (2026-11-11): PING's importer, a shop's name; brand_fallback goes on (the title)
    for none in ("M0000000", "상세정보참조", "(주)삼양인터내셔날", "세모물상점", "스퀘어홀딩"):
        p = prep("8514409092", maker(none))
        assert p["status"] == "ready" and p["product"]["brand_ko"] is None   # left to brand_fallback (run-level)


def test_brand_other_is_no_brand():
    """10697131625, 2026-11-11: a 브랜드 row of 기타 ("other") names no brand: the manufacturer next, then
    brand_fallback (the tenant's name at the end; the owner: Fairward Golf); a 제조사 of 기타 is none either."""
    def rows(brand, manufacturer):
        def change(line):
            line["specs"]["specs"] = [r for r in line["specs"]["specs"] if r["label"] not in ("브랜드", "제조사")] + [
                {"label": "브랜드", "value": brand}, {"label": "제조사", "value": manufacturer or "기타"}]
            line["specs"]["facts"].update(brand={"value": brand, "source": "specs:브랜드"},
                                          manufacturer=manufacturer and {"value": manufacturer,
                                                                         "source": "search_info.manufacturerName"})
        return change
    p = prep("8514409092", rows("기타", "테일러메이드코리아"))
    assert p["product"]["brand_ko"] == "테일러메이드코리아"
    assert p["product"]["brand_source"] == "manufacturer:search_info.manufacturerName"
    for maker in (None, "기타"):
        p = prep("8514409092", rows("기타", maker))
        assert p["status"] == "ready" and p["product"]["brand_ko"] is None   # left to brand_fallback (run-level)
    assert not [r for r in p["product"]["specs"] if r["label_ko"] in ("브랜드", "제조사")]      # "Brand: Other": none


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


def test_image_measures_compose_per_variant():
    """The owner, 2026-11-10: a field the seller does not state is composed from the set's parts, the flat default
    is the last resort. 7583123963 ("13 PCS ... (백세트포함)"): three club weights are not the set, so 13 x the
    baseline 340 g (the women's 12PCS variants: 12 x) + the bag set's stated 4.95 kg; the package is that + the
    2 kg carton; the 45.5 in driver + 100 mm; a set with a bag: 400 x 320. Each carries the default it replaced."""
    pid = "7583123963"
    line = copy.deepcopy(lines()[pid])
    p = prepare(line, RULES_ON, "r", 1, sidecar())
    for v in p["product"]["variants"]:
        pk = v["package"]
        clubs = 12 if "12PCS" in " ".join(v["options_ko"]) else 13          # the variant's own count
        assert [(f["value"]["max"], f["confidence"], f["source"]) for f in pk.values()] == [
            (x, level, "composed") for x, level in ((clubs * 340 + 4950, 2), (clubs * 340 + 6950, 2), (1256, 3),
                                                    (400, 2), (320, 2))]
        assert [f["compared"] for f in pk.values()] == [{"value": x, "source": "category_default", "confidence": 1}
                                                        for x in (5700, 7000, 1250, 280, 230)]
        assert [x["from"] for x in pk["product_weight_g"]["parts"]] == [f"{clubs} clubs x baseline club weight", "stated"]
    note = next(n for n in p["notes"] if n["code"] == "measures_from_images")
    assert all(name in note["detail"] for name in pk)
    assert lines()[pid]["package"] == line["package"]            # the collected line is never changed


def test_image_measures_nothing_read_composes_what_the_listing_says():
    """Nothing in the images and no club count anywhere: the two weights stay the flat default. The length is the
    baseline driver + the margin, the sides those of the listing's bag state (the variants' "블랙백")."""
    pid = next(iter(lines()))
    p = prepare(copy.deepcopy(lines()[pid]), RULES_ON, "r", 1, sidecar([["좋은 클럽입니다"]], pid))
    for v, before in zip(p["product"]["variants"], prep(pid)["product"]["variants"]):
        pk = v["package"]
        assert [pk[n] for n in list(pk)[:2]] == [before["package"][n] for n in list(pk)[:2]]
        assert pk["product_weight_g"]["source"] == "category_default" and pk["product_weight_g"]["confidence"] == 1
        assert (pk["package_length_mm"]["value"]["max"], pk["package_length_mm"]["confidence"]) == (1240, 2)
        assert pk["package_width_mm"]["how"].startswith("box side, ")


def test_image_measures_stale_sidecar_is_a_note_and_not_used():
    """A sidecar read from other links (an older collection of the product) is not used."""
    pid = "7583123963"
    p = prepare(copy.deepcopy(lines()[pid]), RULES_ON, "r", 1, {**sidecar(), "links_sha256": "old"})
    assert any(n["code"] == "description_images_stale" for n in p["notes"])
    assert [v["package"] for v in p["product"]["variants"]] == [v["package"] for v in prep(pid)["product"]["variants"]]


def test_image_measures_without_a_profile_use_the_core_only(monkeypatch):
    """A category with the switch on and no parts profile (none mapped to its Naver id): club tables and bags mean
    nothing, and nothing is composed from parts; a stated product weight still counts (any category), and the
    package is that weight + the row's carton. A product's size is not its box."""
    import description_measures
    monkeypatch.setattr(description_measures, "CATEGORY_PROFILES", {})
    core = RULES_ON
    pid = "7583123963"
    p = prepare(copy.deepcopy(lines()[pid]), core, "r", 1, sidecar())
    assert all(f["source"] == "category_default" for v in p["product"]["variants"] for f in v["package"].values())
    p = prepare(copy.deepcopy(lines()[pid]), core, "r", 1,
                sidecar([["제품 무게 / 12kg", "제품 사이즈 / 140 x 35 x 30cm"]]))
    pk = p["product"]["variants"][0]["package"]
    assert (pk["product_weight_g"]["value"]["max"], pk["product_weight_g"]["confidence"]) == (12000, 4)
    assert (pk["package_weight_g"]["value"]["max"], pk["package_weight_g"]["confidence"]) == (14000, 3)
    assert pk["package_length_mm"]["source"] == "category_default"


def _images(pid):
    with open(os.path.join(os.path.dirname(FX), "description_images", pid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def test_image_measures_read_the_typed_text():
    """8958060680: the bag's weight and the club table are typed, not in an image ("캐디백" / "무게 : 약 3.8kg",
    "클럽 무게(g) | R: 294 / S: 297 | R: 317 / S: 320 | R: 351 / S: 353 | 528"). Five weights of 11 clubs are not
    the set: 11 x the baseline club + the bag's own 3.8 kg."""
    pid = "8958060680"
    p = prepare(_fixture(pid), RULES_ON, "r", 1, _images(pid))
    for v in p["product"]["variants"]:
        w = v["package"]["product_weight_g"]
        assert (w["value"]["max"], w["how"], w["source"], w["confidence"]) == (11 * 340 + 3800, "clubs + bag", "composed", 2)
        assert w["parts"][1] == {"part": "bag", "value": 3800, "from": "stated", "quote": "무게 : 약 3.8kg",
                                 "said_by": "listing"}
        assert w["compared"] == {"value": 5700, "source": "category_default", "confidence": 1}
        assert v["package"]["package_length_mm"]["parts"][0]["value"] == 1149      # 45.25", not the bag's "47인치 대응"
    off = prepare(_fixture(pid), RULES_ON, "r", 1, {**_images(pid), "links_sha256": "old"})
    assert all(f["source"] == "category_default" for v in off["product"]["variants"] for f in v["package"].values())
    # read with the images or not at all: a stale sidecar is a note, the typed text waits for the next reading


def test_image_measures_the_spec_row_says_no_bag():
    """10337644911: 골프백포함여부 "미포함" (no bag word in the options, the title or the images): the clubs alone,
    in a box of a set without a bag."""
    pid = "10337644911"
    p = prepare(_fixture(pid), RULES_ON, "r", 1, _images(pid))
    for v in p["product"]["variants"]:
        w = v["package"]["product_weight_g"]
        assert w["how"] == "clubs, no bag" and w["parts"][0]["from"] == "11 clubs x median club weight"
        assert w["parts"][1] == {"part": "bag", "value": 0, "from": "not in the set", "said_by": "listing"}
        assert [v["package"][n]["value"]["max"] for n in ("package_width_mm", "package_height_mm")] == [200, 160]


def test_image_measures_compose_only_with_the_tables_block(monkeypatch):
    """10337644911 (11 clubs, 골프백포함여부 미포함): with the operator's `baselines` in the category's row, 11 x the
    median 326.5 g, that + the carton, the 45.25 in driver + the margin, the sides of a set without a bag. A row
    without the block composes nothing: the flat defaults, as before the block existed."""
    pid = "10337644911"
    p = prepare(_fixture(pid), RULES_ON, "r", 1, _images(pid))
    for v in p["product"]["variants"]:
        assert [(f["value"]["max"], f["how"], f["confidence"]) for f in v["package"].values()] == [
            (3592, "clubs, no bag", 2), (5592, "product weight + carton", 2), (1249, "longest club + margin", 3),
            (200, "box side, no bag", 2), (160, "box side, no bag", 2)]
        assert [f["compared"]["value"] for f in v["package"].values()] == [5700, 7000, 1250, 280, 230]
    assert {"code": "measures_from_images", "detail": "package_height_mm 4/4, package_length_mm 4/4, "
            "package_weight_g 4/4, package_width_mm 4/4, product_weight_g 4/4"} in p["notes"]
    table = copy.deepcopy(transform._measures_table())
    del table["rows"][0]["baselines"]
    monkeypatch.setattr(transform, "_measures_table", lambda: table)
    for v in prepare(_fixture(pid), RULES_ON, "r", 1, _images(pid))["product"]["variants"]:
        assert all(f["source"] == "category_default" and "compared" not in f for f in v["package"].values())


def test_image_measures_an_addon_boston_bag_is_not_the_package():
    """13734679551: "사이즈 / L48×W24×H30CM" is the Boston bag sold as an add-on ("RB LADY 보스턴 백" 46,000); it was
    the package's width and height (300 / 240). The set's own bag (title "캐디백 포함") states its weight, "약2.8Kg
    (본체)": the sides are the baseline's for a set with a bag."""
    pid = "13734679551"
    p = prepare(_fixture(pid), RULES_ON, "r", 1, _images(pid))
    for v in p["product"]["variants"]:
        pk = v["package"]
        assert [(pk[n]["value"]["max"], pk[n]["how"]) for n in ("package_width_mm", "package_height_mm")] == [
            (400, "box side, with bag"), (320, "box side, with bag")]
        assert pk["product_weight_g"]["value"]["max"] == 10 * 340 + 2800
        assert pk["product_weight_g"]["parts"][1]["quote"] == "중량 / 약2.8Kg (본체)"


def test_image_measures_a_collected_sellers_value_on_todays_scale():
    """6630856593 was collected with the 1-3 scale: its "중량: 약11.5kg / 4.7kg" (bound by club count) carries 2 in
    the line and 4 in the prepared record, with or without the description stage. The package, a default of
    7000 g below the 11.5 kg, is that weight + the carton: 3, the seller's own figure. Without the description
    stage no product weight stays above the package either (D2, 2026-11-17): the bare "중량" 11.5 kg over the
    default box is read as the box, the product weight is the default."""
    pid = "6630856593"
    assert {p["fields"]["product_weight_g"]["confidence"] for p in _fixture(pid)["package"]} == {2}
    p = prepare(_fixture(pid), RULES, "r", 1, _images(pid))
    for v in p["product"]["variants"]:
        weight, packed = v["package"]["product_weight_g"], v["package"]["package_weight_g"]
        if weight["source"] == "source_stated":
            assert (weight["value"]["max"], weight["confidence"], packed["source"]) == (4700, 4, "category_default")
        else:
            assert (weight["compared"]["value"], weight["compared"]["rejected"]) == (11500, "above_package")
            assert (packed["value"]["max"], packed["flags"]) == (11500, ["item_weight_as_packed"])
    p = prepare(_fixture(pid), RULES_ON, "r", 1, _images(pid))
    assert {v["package"]["product_weight_g"]["confidence"] for v in p["product"]["variants"]} == {4}
    for v in p["product"]["variants"]:
        weight, packed = v["package"]["product_weight_g"], v["package"]["package_weight_g"]
        assert weight["source"] == "source_stated" and weight["value"]["max"] in (4700, 11500)
        assert (packed["value"]["max"], packed["confidence"], packed["how"]) == \
            (weight["value"]["max"] + 2000, 3, "product weight + carton")


def test_image_measures_club_count_the_title_before_the_row():
    """The title's "N개" counts the clubs before the 총클럽개수 row and without one. 10481094198: the title's "10개
    풀세트" with a row of "3개" was a set of 3 clubs (846 g); shown on 13728190518 ("캘러웨이 워버드 골프채 세트 10개
    캐디백 포함", row "10개"), whose typed table gives the weights."""
    pid = "13728190518"
    for value in ("3개", None):
        line = _fixture(pid)
        rows = line["specs"]["specs"]
        assert [r["value"] for r in rows if r["label"] == "총클럽개수"] == ["10개"]
        line["specs"]["specs"] = [{**r, "value": value} if r["label"] == "총클럽개수" else r
                                  for r in rows if r["label"] != "총클럽개수" or value]
        p = prepare(line, RULES_ON, "r", 1, _images(pid))
        for v in p["product"]["variants"]:
            assert v["package"]["product_weight_g"]["parts"][0]["from"] == \
                "7 club weights + 3 x their median"                   # its table of seven (2026-11-11)


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


def test_paid_variants_without_paid_addons():
    from transform_shops import rules_for, without_paid_addons
    rule = without_paid_addons(rules_for("fairwardgolf")).category("50002788")
    assert rule.paid_variants and not rule.paid_addons and rule.description_images


def test_measures_counts_and_single_clubs_2026_11_11():
    """The 300 sets of the fairwardgolf job: a club count in an option value ("4개 스틸 건백", "12+볼백"), a typed
    numbered composition, one club filed as a set (13743963823: a driving iron), a women's set."""
    from transform import _LADIES_RE, _MENS_RE, _NUMBERED_RE, _OPTION_COUNT_RE, _SET_RE
    from description_measures import GOLF_SET
    assert [int(m.group(1)) for m in _OPTION_COUNT_RE.finditer("4개 스틸 건백 / 12+볼백 / 10클럽 / 3개월")] == [4, 12, 10]
    assert _NUMBERED_RE.match("1> 드라이버: PXG 0211") and not _NUMBERED_RE.match("10.5도")
    title = "벤세이어스 RED LINE 드라이빙 아이언"
    assert GOLF_SET.single_item.search(title) and not _SET_RE.search(title)
    assert _SET_RE.search("접이식 실내 골프채 풀세트")                       # a set word keeps it a set
    assert _LADIES_RE.search("젝시오 14 여성 풀세트") and _MENS_RE.search("남녀공용 골프채")


def test_measures_option_counts_skip_the_irons_count_2026_11_11():
    """An option value that names a club kind counts the irons of a set picked over several options, not the set
    (13313940582 "드라이버 10.5도(R)+아이언 9개(R)", 13741964465 "8개구성(6~S)", 12211893510 "IR 7개L"); the title's
    closed list of clubs means no bag (13068838282)."""
    from transform import _CLOSED_TITLE_RE, _KIND_RE
    for o in ("드라이버 10.5도(R)+아이언 9개(R)", "8개구성(6~S)", "IR 7개L", "8개아이언", "7개(6-9+P+A+S)-L"):
        assert _KIND_RE.search(o), o
    for o in ("4개 스틸 건백", "12개세트 카본 R", "MTG040 12 스틸 로드+볼백"):
        assert not _KIND_RE.search(o), o
    assert _CLOSED_TITLE_RE.search("핑 G440K 드라이버 남성 골프채 조합세트 [드라이버+우드+유틸리티]")
    assert _CLOSED_TITLE_RE.search("야마하 Cs 여성용 클럽세트 (드라이버+아이언세트) 8I")
    assert not _CLOSED_TITLE_RE.search("테일러메이드 풀세트 [11개]")
    from transform import _SET_OPTION_RE
    assert not _SET_OPTION_RE.search("8개구성 NS820 (R)") and _SET_OPTION_RE.search("9개 스틸 스탠드백")


def test_measures_a_list_of_the_clubs_means_no_bag_2026_11_11():
    """The clubs listed with no bag: down to the putter (8437045488, 10208717296), or with a count (12999322418, the
    typed line of 12931412033); a bag word in the list keeps it open; a kind alone says nothing."""
    from transform import _closed_list
    from description_measures import GOLF_SET as G
    for text in ("11.5L 5번유틸 7아이언 퍼터", "10.5R유틸4번R8아이언R퍼터", "드라이버 10.5도 R, 아이언 6개",
                 "드라이버+8개아이언 9개 구성"):
        assert _closed_list(text, G), text
    for text in ("드라이버+우드+아이언+퍼터+캐디백", "카본 아이언 구성 11개", "10.5도 R"):
        assert not _closed_list(text, G), text


def test_a_sellers_contact_note_is_no_option_and_no_addon():
    """The iron sets' review (2026-11-15): a phone number in an option name (9707668123), a "contact us" variant
    (12198910588) and add-on (12219474816) were published."""
    from transform import _axis_name, _contact_only
    assert _axis_name("샤프트 선택(문의010-7229-8779)") == "샤프트 선택"
    assert _contact_only("커스텀 오더는 톡톡 문의 부탁드립니다.") and _contact_only("특주주문시 연락주세요(02-2200-1633)")
    assert not _contact_only("A(주문전문의)") and not _contact_only("7아이언세트 L") and not _contact_only("오른손(기본)")

    def contact_row(line):
        line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "구성", "type": "COMBINATION"}]
        base = line["specs"]["options"]["variants"][0]
        line["specs"]["options"]["variants"] = [{**base, "id": "a", "options": ["7아이언세트 L"]},
                                                {**base, "id": "b", "options": ["커스텀 오더는 톡톡 문의 부탁드립니다."]}]
    assert len(prep("8514409092", contact_row)["product"]["variants"]) == 1


def test_the_maker_naming_a_longer_brand_the_title_names_wins():
    """7186088743 (2026-11-15): 혼마 in the brand row, 무쯔미혼마 the maker, "무쯔미 혼마 스페셜 2스타" the title: a Mutsumi
    Honma set, not Honma. A Korean distributor's name (지브이골프코리아) never wins."""
    def mutsumi(line):
        line["details"]["name"] = "무쯔미 혼마 스페셜 2스타 여성 경량 아이언세트 (8개)"
        line["specs"]["facts"]["brand"] = {"value": "혼마", "source": "specs:브랜드"}
        line["specs"]["facts"]["manufacturer"] = {"value": "무쯔미혼마", "source": "specs:제조사"}
    assert prep("8514409092", mutsumi)["product"]["brand_ko"] == "무쯔미혼마"
    assert prep("8514409092")["product"]["brand_ko"] == "지브이투어"


def test_a_sellers_note_leaves_an_option_value():
    """2026-11-15: "L/세금미포함" (tax not included) and "A(주문전문의)" (ask before ordering) were published as values."""
    from transform import _without_notes
    assert _without_notes(["L/세금미포함", "A/세금미포함"]) == ["L", "A"]
    assert _without_notes(["A(주문전문의)", "L(주문전문의)"]) == ["A", "L"]
    assert _without_notes(["L", "L 당일출고"]) is None                  # two values would be one: kept
    assert _without_notes(["7아이언세트 L", "8아이언세트 L"]) is None      # no note


def test_sets_only_leaves_a_single_clubs_variant_out_and_holds_a_product_of_them():
    """Wedges (sets_only, the owner 2026-11-15): of a set-or-single listing only the set variants are sold
    (12710842654 "50도+56도 세트" kept, "50도" out); a listing whose every variant is one wedge is held."""
    from transform import single_club
    for single in (["60 Degree-1PC", "1 TARNISH 60 Degree"], ["Black Left Handed", "LH Black 52 Degree"],
                   ["GRF539-52 degrees"], ["52도 웨지 블랙 1개"], ["56도"], ["48 (Y그라인드)", "DG S200"]):
        assert single_club(single), single
    for kept in (["50/54/58 Degree-3PCS"], ["RH Black 52 56 60 Set"], ["52+56+60"], ["black"], ["Left"],
                 ["스틸파이버 i60R"], ["NS PRO 950 R"], ["50도+56도 세트", "NS PRO 950 R"]):   # i60R is a shaft
        assert not single_club(kept), kept
    cat = dataclasses.replace(RULES.categories["50002788"], sets_only=True)
    rules = dataclasses.replace(RULES, categories={"50002788": cat})

    def wedges(values):
        def edit(line):
            line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "로프트", "type": "COMBINATION"}]
            base = line["specs"]["options"]["variants"][0]
            line["specs"]["options"]["variants"] = [{**base, "id": str(i), "options": [v], "extra_price": 0}
                                                    for i, v in enumerate(values)]
        return edit
    p = prep("12945108653", wedges(["50도+56도 세트", "50도", "56도"]), rules=rules)
    assert len(p["product"]["variants"]) == 1 and "세트" in p["product"]["variants"][0]["source_id"]
    held = prep("12945108653", wedges(["52도", "56도", "60도"]), rules=rules)
    assert held["status"] == "held" and "single_only" in {h["code"] for h in held["held"]}


def test_sets_only_holds_a_title_that_sells_one_piece():
    """2026-11-15, the wedge pilot: "골프 웨지 세트 52 56 60도 갭 샌드 로브 60도 웨지 실버 1개" sells one wedge."""
    from transform import _ONE_PIECE_RE
    for title in ("골프 웨지 세트 52 56 60도 갭 샌드 로브 60도 웨지 실버 1개", "BombTech 골프 웨지 세트 52 56 60도 실버 1개",
                  "남성용 단조 풀페이스 골프 웨지 세트 52 56 60도 CNC 밀링 블랙. 56° 1개"):
        assert _ONE_PIECE_RE.search(title), title
    for title in ("테일러메이드 MG5 웨지 SB 세트 3개", "웨지 3종 세트 11개", "골프 웨지 세트 1개 구성", "USC U-21 웨지 2개 세트"):
        assert not _ONE_PIECE_RE.search(title), title
    cat = dataclasses.replace(RULES.categories["50002788"], sets_only=True)
    rules = dataclasses.replace(RULES, categories={"50002788": cat})

    def one(line):
        line["details"]["name"] = "골프 웨지 세트 52 56 60도 갭 샌드 로브 60도 웨지 실버 1개"
        line["specs"]["options"]["option_groups"] = [{"id": "1", "name": "색상", "type": "COMBINATION"}]
        base = line["specs"]["options"]["variants"][0]
        line["specs"]["options"]["variants"] = [{**base, "id": "a", "options": ["실버"], "extra_price": 0}]
    held = prep("12945108653", one, rules=rules)
    assert held["status"] == "held" and "single_only" in {h["code"] for h in held["held"]}


def test_a_loft_restated_on_a_second_axis_is_one_club_but_two_club_slots_are_two_clubs():
    """2026-11-15, the lenses: two Yamato 'set or single' imports published as sets (12951827729, 12921931106), every
    variant one wedge written on two axes ("Size: 56 Degree" + "Style Name: Black 56 Degree"); the TaylorMade MG5
    sets (12701183962, 13646379989) pick one club per axis and may pick one loft twice: kept."""
    from transform import _club_slots, single_club
    yamato = ["Size", "Style Name"]
    for values in (["1 56 Degree", "1 Black 56 Degree"], ["56 Degree", "Black 56 Degree"], ["60 Degree", "60 Degree"]):
        assert single_club(values, yamato), values
    for names, values in ((["옵션 1", "옵션 2"], ["52.09 SB", "52.09 SB"]),
                          (["웨지 로프트 바운스 선택-1", "웨지 로프트 바운스 선택-2", "웨지 로프트 바운스 선택-3"],
                           ["48도 09 바운스", "48도 09 바운스", "48도 09 바운스"]),
                          (["SB웨지1", "SB웨지2"], ["크롬56도(12도)", "크롬56도(12도)"])):
        assert _club_slots(names) and not single_club(values, names), (names, values)
    assert not _club_slots(["Size", "Style Name"]) and not _club_slots(["로프트"])
    assert not single_club(["52 Degree", "56 Degree"], yamato)                          # two lofts: two clubs


def test_written_out_escapes_are_decoded_before_the_title_is_read():
    """2026-11-15: 15 products carried "u2013" / "u2019" as text (13016883852 "개별 u2013 단조", 13209544038 "세트 u2013
    소년 u2019 & 소녀"); it reached the titles, the handles and dedupe's numbers."""
    from description_clean import decode_escapes, decode_line
    assert decode_escapes("세트 u2013 소년 u2019 & 소녀") == "세트 – 소년 ' & 소녀"
    assert decode_escapes("PGM 남성 u2019s 컴플리트 U2013 티타늄") == "PGM 남성 's 컴플리트 – 티타늄"
    for kept in ("clubface scuffed", "U2000X", "A11N db4P LH01-52", "u20", "abcu2013", "", None):
        assert decode_escapes(kept) == kept
    line = {"key": "k", "details": {"name": "웨지 u2013 단조", "description": {"text": "a u2019 b", "html": "x u2013"}},
            "listing": {"name": "웨지 u2013 단조"}, "specs": {}}
    out = decode_line(line)
    assert out["details"]["name"] == out["listing"]["name"] == "웨지 – 단조"
    assert out["details"]["description"] == {"text": "a ' b", "html": "x u2013"}            # the html as it is
    assert line["details"]["name"] == "웨지 u2013 단조"                                       # the line not changed


def test_the_four_live_categories_are_reviewed_and_a_new_one_is_not():
    """2026-11-16, draft first: the categories live before it publish ACTIVE as before; a new category is DRAFT
    until the owner marks it reviewed. The free-only and no-add-on variants of the rules keep the mark."""
    from transform_shops import CategoryRules, reviewed, rules_for, without_paid, without_paid_addons
    live = ("50002788", "50002787", "50002670", "50002783")
    assert all(reviewed("fairwardgolf", c) for c in live) and CategoryRules().reviewed is False
    for variant in (without_paid, without_paid_addons):
        assert all(variant(rules_for("fairwardgolf")).category(c).reviewed for c in live)
    assert not reviewed("fairwardgolf", "999") and not reviewed("nosuchshop", "1") and not reviewed("fairwardgolf", None)
    # 50002784 chippers (the owner, 2026-11-18): paid variants yes, paid add-ons no; DRAFT first until the owner
    # activated the 90 drafts after the lens review and marked it reviewed (2026-11-19)
    chippers = rules_for("fairwardgolf").category("50002784")
    assert reviewed("fairwardgolf", "50002784") and chippers.paid_variants and not chippers.paid_addons
    assert chippers.description_images and not chippers.sets_only and not chippers.wedge_sets


def test_stated_weights_checked_without_the_description_images():
    """D2 (2026-11-17) for every product, not only one with a current sidecar: 6630856593's server "중량: 약11.5kg"
    of the 12-club sets over the 7000 g default box, with no sidecar and with a stale one, never goes out as a
    product weight above the package."""
    pid = "6630856593"
    stale = {**_images(pid), "links_sha256": "0" * 64}
    for images in (None, stale):
        p = prepare(_fixture(pid), RULES_ON, "r", 1, images)
        codes = {n["code"] for n in p["notes"]}
        assert codes & {"description_images_missing", "description_images_stale"}
        for v in p["product"]["variants"]:
            weight, packed = v["package"]["product_weight_g"], v["package"]["package_weight_g"]
            assert (weight.get("value") or {}).get("max", weight.get("central")) <= \
                (packed.get("value") or {}).get("max", packed.get("central"))


# ---- a free gift as an option axis (2026-11-18, the chipper review) ------------------------------------------------

def _chipper(pid):
    with open(os.path.join(os.path.dirname(FX), "collected", pid + ".json"), encoding="utf-8") as f:
        return json.load(f)


def test_a_free_gifts_sizes_are_not_versions_of_the_chipper():
    """Missile Black Eagle 10421264752 (2026-11-18): the club has no option; its 7 variants were the free FILA glove's
    sizes ("휠라 양피장갑 왼손 19호 ... 25호 1장", axis 사은품, extra_price 0). Chippers (gift_axis_out): one variant,
    the first row's SKU kept (in stock or not), a note; another category's rules keep the 7 (its sets' gifts are a bag set, a putter,
    a club the buyer picks: the owner's word)."""
    line = _chipper("10421264752")
    p = json.loads(json.dumps(prepare(copy.deepcopy(line), RULES_ON, "50002784-test", 1)))
    [v] = p["product"]["variants"]
    assert p["product"]["options"] == [] and v["options_ko"] == [] and v["price_krw"] == 89000
    assert v["source_id"] == 'observed:["35인치","휠라 양피장갑 왼손 19호 1장"]'
    assert {"code": "gift_axis_dropped", "detail": "사은품 (7 values): a free gift, not a version; 7 -> 1 rows"} \
        in p["notes"]
    assert not [t for t in p["texts"] if "양피장갑" in t["ko"]]           # nothing of the gift left to translate
    off = dataclasses.replace(RULES_ON, categories={**RULES_ON.categories, "50002784": dataclasses.replace(
        RULES_ON.categories["50002784"], gift_axis_out=False)})
    kept = prepare(copy.deepcopy(line), off, "50002784-test", 1)
    assert len(kept["product"]["variants"]) == 7 and kept["product"]["options"][0]["name_ko"] == "사은품"


@pytest.mark.parametrize("names, rows, kept", [
    # a gift priced apart is a choice: stays
    (["사은품"], [("장갑 S", 100), ("장갑 L", 120)], ([0], 2)),
    # the set itself with a gift ("옵션+사은품 하프백", 13457270622): a product choice, stays
    (["옵션+사은품 아이언커버"], [("레바26 민트", 100), ("레바26 블랙", 100)], ([0], 2)),
    # every value only adds a gift to a product choice ("3세대흑백95-115cm클럽커버증정", 13824501696): stays
    (["옵션"], [("흑백95-115cm클럽커버증정", 100), ("흑황95-115cm클럽커버증정", 100)], ([0], 2)),
    # every value is the gift ("[사은품] 장갑 22호"): goes
    (["선택"], [("[사은품] 장갑 22호", 100), ("[사은품] 장갑 23호", 100)], ([], 1)),
    # a gift beside the club's own axis: one row per loft, its first row (in stock when any row is)
    (["로프트", "증정 장갑"], [("35도", "S", 100, False), ("35도", "M", 100), ("45도", "S", 110), ("45도", "M", 110)],
     ([0], 2)),
])
def test_which_gift_axes_go(names, rows, kept):
    rows = [{"options": list(r[:len(names)]), "price": r[len(names)],
             "is_available": r[len(names) + 1] if len(r) > len(names) + 1 else True} for r in rows]
    keep, left, said = transform._drop_gift_axes(names, list(range(len(names))), rows)
    assert (keep, len(left)) == kept and (said is None) == (len(left) == len(rows))
    if names[0] == "로프트":
        assert [(r["options"], r["is_available"]) for r in left] == [(["35도", "S"], True), (["45도", "S"], True)]


def test_a_gift_size_sold_out_keeps_the_variant():
    """The review of 569b77f: the row kept for a dropped gift axis is the tuple's first, not its first in stock, so a
    glove size selling out moves no source_id / SKU / variant id of a published chipper (10421264752: 19호 first)."""
    line = _chipper("10421264752")
    before = prepare(copy.deepcopy(line), RULES_ON, "50002784-test", 1)["product"]["variants"]
    sold = copy.deepcopy(line)
    sold["specs"]["options"]["variants"][0].update(stock_quantity=0, is_available=False)    # the page's row: 19호 out
    after = prepare(sold, RULES_ON, "50002784-test", 1)["product"]["variants"]
    assert [(v["source_id"], v["sku"], v["naver_variant_id"]) for v in after] \
        == [(v["source_id"], v["sku"], v["naver_variant_id"]) for v in before]
    assert "19호" in after[0]["source_id"] and after[0]["available"] is True


def test_a_dropped_gifts_tuple_is_out_only_when_every_row_is():
    rows = [{"options": ["35도", g], "price": 100, "is_available": a} for g, a in (("S", False), ("M", False))]
    assert [r["is_available"] for r in transform._drop_gift_axes(["로프트", "사은품"], [0, 1], rows)[1]] == [False]
    rows[1]["is_available"] = None
    assert [r["is_available"] for r in transform._drop_gift_axes(["로프트", "사은품"], [0, 1], rows)[1]] == [None]


# ---- women's knit cardigans 50002797 (the owner, 2026-11-19) ------------------------------------------------------

def _knit(groups, variants, notice=(), specs=()):
    """The chipper fixture as a knit cardigan of 50002797: its options, notice and spec rows replaced."""
    line = copy.deepcopy(_chipper("10421264752"))
    line["specs"]["category"] = {"id": "50002797", "name": "니트",
                                 "path": ["스포츠/레저", "골프", "골프의류", "니트"]}
    line["details"]["name"] = "[현대백화점] 레노마골프 여성 조직감 방풍 집업 니트 가디건 RWSCN8208"
    line["specs"]["options"]["option_groups"] = [{"id": str(i), "name": n, "type": "COMBINATION"}
                                                 for i, n in enumerate(groups)]
    line["specs"]["options"]["variants"] = [
        {"id": str(900 + i), "name": " / ".join(v), "options": list(v), "extra_price": extra, "stock_quantity": 9,
         "is_available": True, "is_today_dispatch": None} for i, (v, extra) in enumerate(variants)]
    line["details"]["notice"] = {"type": "WEAR", "items": [
        {"label": label, "value": value, "is_see_description": see} for label, value, see in notice]}
    line["specs"]["specs"] = [{"label": label, "value": value} for label, value in specs]
    return line


def test_the_knit_rules_are_the_owners():
    knit = rules_for("fairwardgolf").category("50002797")
    assert knit.paid_variants and not knit.paid_addons and knit.description_images and knit.gift_axis_out
    assert knit.no_choice_out and knit.composition and not knit.reviewed
    assert not knit.sets_only and not knit.wedge_sets and not knit.agency_needs_brand
    assert not any(c.no_choice_out or c.composition for k, c in rules_for("fairwardgolf").categories.items()
                   if k != "50002797")                       # the clubs' products stay as published


def test_no_choice_values_are_not_versions_of_the_cardigan():
    """"선택안함" on the 사이즈 axis is a row of nothing: it goes; an axis of nothing but "없음" goes whole; a plus size
    at +5,000 KRW stays (paid variants)."""
    rows = [(("블랙", "55", "없음"), 0), (("블랙", "66", "없음"), 0), (("블랙", "선택안함", "없음"), 0),
            (("아이보리", "55", "없음"), 0), (("아이보리", "88", "없음"), 5000), (("아이보리", "선택 안함", "없음"), 0)]
    p = prepare(_knit(["색상", "사이즈", "추가"], rows), RULES_ON, "50002797-test", 1)
    assert [(o["name_ko"], o["values_ko"]) for o in p["product"]["options"]] == [
        ("색상", ["블랙", "아이보리"]), ("사이즈", ["55", "66", "88"])]
    assert sorted(v["price_krw"] for v in p["product"]["variants"]) == [89000, 89000, 89000, 94000]
    note = next(n for n in p["notes"] if n["code"] == "no_choice_dropped")
    assert note["detail"] == "사이즈: 선택 안함, 선택안함; 추가: no choice on every row, the axis; 6 -> 4 rows"


@pytest.mark.parametrize("names, rows, kept, said", [
    (["색상"], ["블랙", "선택안함"], ([0], 1), True),
    (["색상"], ["블랙", "그레이"], ([0], 2), False),
    (["색상", "옵션"], [("블랙", "필요없음"), ("그레이", "필요 없음")], ([0], 2), True),
    (["색상"], ["1. 선택없음", "블랙"], ([0], 1), True),
    (["색상"], ["없음 표시 블랙"], ([0], 1), False),                       # a word inside a value is no "no choice"
])
def test_which_no_choice_values_go(names, rows, kept, said):
    rows = [{"options": list(r) if isinstance(r, tuple) else [r], "price": 100, "is_available": True} for r in rows]
    keep, left, note = transform._drop_no_choice(names, list(range(len(names))), rows)
    assert (keep, len(left)) == kept and (note is not None) == said


def test_the_clubs_keep_a_no_choice_value():
    rows = [(("35인치", "선택안함"), 0), (("35인치", "헤드커버"), 0)]
    line = _knit(["길이", "추가"], rows)
    line["specs"]["category"] = {"id": "50002784", "name": "치퍼"}
    p = prepare(line, RULES_ON, "50002784-test", 1)
    assert p["product"]["options"][0]["values_ko"] == ["선택안함", "헤드커버"] and "composition_ko" not in p["product"]


def test_the_composition_rows_are_kept_for_the_duty_and_the_description():
    line = _knit(["색상"], [(("블랙",), 0), (("그레이",), 0)],
                 notice=[("제품소재", "상세페이지 참조", True), ("섬유의 조성 또는 혼용률", "아크릴 50%, 울 30%, 나일론 20%", False),
                         ("색상", "블랙, 그레이", False)],
                 specs=[("소재", "울혼방"), ("브랜드", "레노마골프")])
    p = prepare(line, RULES_ON, "50002797-test", 1)
    assert p["product"]["composition_ko"] == [
        {"label_ko": "소재", "value_ko": "울혼방", "source": "spec"},
        {"label_ko": "섬유의 조성 또는 혼용률", "value_ko": "아크릴 50%, 울 30%, 나일론 20%", "source": "notice"}]
    from shop_pricing import policy
    box = {f: {"central": n, "confidence": 1} for f, n in (("package_length_mm", 280), ("package_width_mm", 220),
                                                           ("package_height_mm", 40), ("package_weight_g", 400))}
    variant = {**p["product"]["variants"][0], "package": box}       # the fixture's package rows are the chipper's
    b = policy("fairwardgolf").quote(variant, p["product"], "50002797").breakdown
    assert b is not None and b["dutyRate"] == "0.125" and b["dutyBasis"]["byFibre"] == "0.32" and b["dutyBasis"]["fibre"] == "man-made" \
        and b["dutyBasis"]["source"] == "notice" and b["coefficient"] == "1.10"
