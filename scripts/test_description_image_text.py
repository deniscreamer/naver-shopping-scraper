"""Offline tests for the description images' text for translation (description_image_text.py) and the files and
the flag run_transform writes (image_texts). Rows are OCR rows of live golf sets (2026-11-07), quoted as read.

    .venv/bin/python -m pytest scripts/test_description_image_text.py -q
"""
import json
import os

import description_image_text as T
import keep_run
import run_transform

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def sidecar(*images, conf=0.95):
    return {"images": [{"link": f"https://shop-phinf.pstatic.net/{n}.jpg", "status": "read",
                        "slices": [{"y0": 0, "y1": 100, "rows": [r if isinstance(r, dict) else
                                                                   {"text": r, "conf": conf, "y": 0} for r in rows]}]}
                       for n, rows in enumerate(images)]}


def kinds(b):
    return [(x["kind"], x["text"]) for x in b["blocks"]]


def test_tables_and_text_blocks_with_degrees_fixed():
    """12975257923: the QTS table reads "+1.0°" as "+1.00"; 9775704002: a spec table; prose between."""
    b = T.blocks(sidecar(["포지션 / 로프트각 / 페이스각 / 라이각", "L1 / +0.5 / +1.00 / -2.5°",
                          "조절식 슬리브를 통해 골퍼가 원하는 로프트를 조절", "헤드체적(cm) / 460"]))
    assert kinds(b) == [("text", "포지션 / 로프트각 / 페이스각 / 라이각"), ("table", "L1 | +0.5 | +1.0° | -2.5°"),
                        ("text", "조절식 슬리브를 통해 골퍼가 원하는 로프트를 조절"), ("table", "헤드체적(cm) | 460")]
    assert [x["id"] for x in b["blocks"]] == ["b01", "b02", "b03", "b04"]


def test_noise_rows_are_dropped_with_their_rule():
    prose = [f"{n}번째 기술 설명 문장입니다" for n in range(1, 8)]          # the image is mostly the product's
    b = T.blocks(sidecar(prose + [
        "세계 최초 신소재 VR-티타늄으로 도달한 비거리의 새로운 영역",
        "세계 최초 신소재 VR-티타늄으로 도달한 비거리의 새로운 영역",          # repeat (a slice overlap)
        {"text": "흐릿한 글자 줄입니다", "conf": 0.4, "y": 0},                   # low_confidence
        "B4", "85",                                                             # fragment
        "POWER TRAJECTORY",                                                     # photo_label
        "가격 / ¥69,300(세금 포함)",                                             # price
        "(02-6674-7500)[우편번호:08503]",                                         # contact
        "평일 오후 3시 이전 결제 시 당일 출고가 가능합니다.",                         # shop_policy
        "일산스타필드점 / 시타 / 강동점 / 시타",                                   # store_info
        "Copyright ©더골프샵 All rights reserved.",                              # legal
        "구매 고객 전원 클럽 네임택 증정",                                          # promo
    ]))
    assert kinds(b) == [("text", "\n".join(prose + ["세계 최초 신소재 VR-티타늄으로 도달한 비거리의 새로운 영역"]))]
    assert b["dropped"] == {"contact": 1, "fragment": 2, "legal": 1, "low_confidence": 1, "photo_label": 1,
                            "price": 1, "promo": 1, "repeat": 1, "shop_policy": 1, "store_info": 1}


def test_product_words_that_look_like_policy_stay():
    """"손목 부담", "오염에 강한", "탄도로 15% 향상": the product's copy, not the shop's terms or an address."""
    rows = ["손목에 부담을 줄여주는 경량 샤프트", "오염에 강한 소재", "높은 탄도로 15% 향상된 비거리"]
    assert [t for _, t in kinds(T.blocks(sidecar(rows)))] == ["\n".join(rows)]


def test_cross_sell_to_the_end_of_the_image_and_a_notice_image_whole():
    b = T.blocks(sidecar(["단조 아이언의 부드러운 타구감", "함께 구매하면 좋은 상품", "미즈노 하프백 경량 소재"],
                         ["교환 및 반품이 가능한 경우", "단순변심의 경우 수령 후 7일 이내 접수 시 가능",
                          "반품 배송비는 고객 부담입니다", "골프클럽 비닐 제거 시 처리불가", "AK골프 배송안내"]))
    assert kinds(b) == [("text", "단조 아이언의 부드러운 타구감")]
    assert b["dropped"]["cross_sell"] == 2 and b["dropped"]["shop_notice_image"] >= 1


def test_page_text_rules_also_apply():
    """description_clean.clean on a text block: a greeting line is the seller's, not the product's."""
    b = T.blocks(sidecar(["안녕하세요 골프몰입니다.", "부드러운 타구감의 단조 아이언"]))
    assert kinds(b) == [("text", "부드러운 타구감의 단조 아이언")] and b["dropped"]["greeting"] == 1


def test_shared_store_blocks_stay_and_are_marked():
    """Review 2026-11-07: a store's spec sheet of one model sits in several listings; it is the product's (it was
    dropped as a store banner). It stays, with `shared` = how many of the store's products carry it, and a
    product's sha256 never changes because another product changed."""
    a = T.blocks(sidecar(["헤드체적(cm) / 460", "드라이버 비거리 향상 기술 설명"]))
    b = T.blocks(sidecar(["헤드체적(cm) / 460", "아이언 관용성 향상 기술 설명"]))
    out = T.mark_shared({"k1": ("100", a), "k2": ("100", b), "k3": ("200", a)})
    assert [(x["text"], x["shared"]) for x in out["k1"]["blocks"]] == [("헤드체적(cm) | 460", 2),
                                                                       ("드라이버 비거리 향상 기술 설명", 1)]
    assert out["k3"]["blocks"][0]["shared"] == 1                # another store
    assert T.sha(out["k1"]["blocks"]) == T.sha(a["blocks"]) and len(a["blocks"][0]["key"]) == 16


def test_as_text_header_and_ids():
    bl = [{"id": "b01", "kind": "table", "image": 2, "text": "길이(인치) | 45.5"}]
    t = T.as_text("123", bl, T.sha(bl), T.glossary_for("50002788"))
    assert t.splitlines()[1] == f"# format {T.FORMAT}; sha256 {T.sha(bl)}; 1 blocks"
    assert "do not invent facts" in t and "로프트각 = loft" in t and T.glossary_for("1") == {}
    assert "[b01 table image 2]\n길이(인치) | 45.5" in t


def test_fixture_sidecars_leave_no_phones_prices_or_policy():
    """All 50 fixture products' real OCR: no phone number, KRW / yen price or delivery line in the kept text."""
    folder = os.path.join(FX, "description_images")
    kept = []
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            kept += [x["text"] for x in T.blocks(json.load(f))["blocks"]]
    text = "\n".join(kept)
    assert len(kept) > 300
    for row in text.splitlines():
        assert not T._PRICE.search(row) and not T._POLICY.search(row) and not T._CONTACT.search(row), row


# ---- run_transform: files and the flag -------------------------------------------------------------------------

def test_files_and_one_flag(tmp_path):
    """The translation step reads product.description_images_text.state, never the folder."""
    with open(os.path.join(FX, "collected", "10337644911.json"), encoding="utf-8") as f:
        line = json.load(f)
    src = tmp_path / "full"
    src.mkdir()
    (src / "products.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    shops = str(tmp_path / "shops")
    keep_run.keep(str(src), shops)

    def flag():
        return run_transform.run("fairwardgolf", None, shops)["prepared"][0]["product"]["description_images_text"]
    assert flag()["state"] == "not_read"
    side = os.path.join(shops, "fairwardgolf", "description_images")
    os.makedirs(side)
    with open(os.path.join(FX, "description_images", "10337644911.json"), encoding="utf-8") as f:
        sc = json.load(f)
    with open(os.path.join(side, "10337644911.json"), "w", encoding="utf-8") as f:
        json.dump(sc, f, ensure_ascii=False)
    got = flag()
    where = os.path.join(shops, "fairwardgolf", "translation", "10337644911")
    assert got["state"] == "to_translate" and got["ko"] == "translation/10337644911/description_images.ko.json"
    with open(os.path.join(where, "description_images.ko.json"), encoding="utf-8") as f:
        ko = json.load(f)
    assert ko["sha256"] == got["sha256"] and len(ko["blocks"]) == got["blocks"] > 0
    assert open(os.path.join(where, "description_images.ko.txt"), encoding="utf-8").read().startswith("# description")
    with open(os.path.join(where, "description_images.en.json"), "w", encoding="utf-8") as f:
        json.dump({"format": T.TRANSLATION_FORMAT, "source_sha256": got["sha256"], "blocks": []}, f)
    assert flag()["state"] == "translated"
    with open(os.path.join(where, "description_images.en.json"), "w", encoding="utf-8") as f:
        json.dump({"format": T.TRANSLATION_FORMAT, "source_sha256": "older text", "blocks": []}, f)
    assert flag()["state"] == "to_translate"                  # the Korean changed since that translation
    sc["images"] = []
    with open(os.path.join(side, "10337644911.json"), "w", encoding="utf-8") as f:
        json.dump(sc, f, ensure_ascii=False)
    got = flag()
    assert got["state"] == "empty" and not os.path.exists(os.path.join(where, "description_images.ko.json"))
    assert os.path.exists(os.path.join(where, "description_images.en.json"))    # the translator's file stays


def test_a_sentence_split_by_ocr_boxes_stays_text():
    """7583123963: "여성용은 / 12PCS/남성용은13PCS로" then "구성되어 있으니 ..." is one sentence, not a table row."""
    b = T.blocks(sidecar(["여성용은 / 12PCS/남성용은13PCS로", "구성되어 있으니 구매 시 참고 부탁드립니다."]))
    assert [k for k, _ in kinds(b)] == ["text"]
