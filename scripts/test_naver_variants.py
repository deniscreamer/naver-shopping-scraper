"""Offline tests for the variant choice (naver_variants.py).

The rows are real: the options of brand.naver.com/idmakers/products/11696178500 as the page's own answer gave
them on 2026-11-02 (server fixture page_product_idmakers.json, parsed): free and paid rows, a sold-out row, a
"+" that joins a pair, a CUSTOM text option, an add-on.

    .venv/bin/python -m pytest scripts/test_naver_variants.py -q
"""
import naver_types as T
from naver_variants import choose_variants, price_in_name


def variant(id, name, extra, stock):
    return {"id": id, "name": name, "options": name.split(" / "), "extra_price": extra, "stock_quantity": stock,
            "is_available": stock > 0, "is_today_dispatch": True, "registered_at": "2026-02-12"}


def options(*variants, simple=()):
    opts: T.PageOptions = {
        "has_options": True, "status": "SALE", "is_sold_out": False, "stock_quantity": 268312,
        "option_groups": [{"id": "10251381858", "name": "구성", "type": "COMBINATION"}],
        "variants": list(variants), "simple_options": list(simple),
        "text_options": [{"id": "11800253335", "name": "필수작성(미각인or각인:내용)후 옵션선택", "label": None,
                          "required": None, "placeholder": None, "hint": None, "min_length": None,
                          "max_length": None, "pattern": None}],
        "supplements": [{"id": "3678604239", "group": "선물포장", "name": "쇼핑백", "price": 1500,
                         "stock_quantity": 5000, "status": "SALE"}],
    }
    return opts


IDMAKERS = options(
    variant("56035243441", "선물세트(1p) / 실버블루 / 각인없음", 0, 4835),
    variant("56035243443", "선물세트(1p) / 실버핑크 / 각인없음", 0, 4963),
    variant("48835584250", "선물세트(1p) / 황동(골드) / 각인없음", 1000, 4818),
    variant("56035243450", "선물세트(2P) / 1.실버블루 + 실버블루 / 각인없음", 17000, 4996),
    variant("48835584252", "선물세트(1p) / 로즈골드 / 각인없음", 1000, 0),
    variant("56035243499", "선물세트(1p) / 티탄 / 각인없음", 0, 0),
)


def test_default_takes_only_the_unchanged_price():
    c = choose_variants(IDMAKERS, 17800)
    assert c["paid"] is False and [v["id"] for v in c["variants"]] == ["56035243441", "56035243443", "56035243499"]
    assert c["skipped_paid"] == 3 and c["available"] == 2 and c["sold_out"] == 1
    assert all(v["price"] == 17800 for v in c["variants"])
    sold = c["variants"][-1]
    assert sold["is_available"] is False and sold["stock_quantity"] == 0           # kept, marked
    assert c["text_options"][0]["id"] == "11800253335" and c["supplements"][0]["price"] == 1500


def test_paid_takes_every_variant_with_its_price():
    c = choose_variants(IDMAKERS, 17800, paid=True)
    assert len(c["variants"]) == 6 and c["skipped_paid"] == 0
    assert {v["id"]: v["price"] for v in c["variants"]}["56035243450"] == 34800
    assert c["sold_out"] == 2 and c["available"] == 4
    assert choose_variants(IDMAKERS, None, paid=True)["variants"][0]["price"] is None


def test_price_in_name_strict_form_only():
    assert price_in_name("화이트 (+5,000원)") == 5000
    assert price_in_name("캐디백 제외 (-300,000원)") == -300000
    assert price_in_name("1.실버블루 + 실버블루") is None                 # a "+" joining a pair
    assert price_in_name("드라이버+우드 12,000원 추가") is None             # not the strict form
    assert price_in_name("A (+1,000원) / B (+2,000원)") is None            # two amounts: unknown
    assert price_in_name(None) is None
    assert price_in_name("(+,원)") is None and price_in_name("( - , 원)") is None   # no digit: no amount


def test_name_and_data_disagree():
    opts = options(variant("1", "블랙 (+5,000원)", 0, 3), variant("2", "화이트 (+5,000원)", 5000, 3),
                   variant("3", "레드", 0, 3))
    c = choose_variants(opts, 100000)
    assert [v["id"] for v in c["variants"]] == ["3"]                       # the label says it costs more
    assert c["name_mismatches"] == ["1"] and c["skipped_paid"] == 2
    paid = choose_variants(opts, 100000, paid=True)
    assert [v["price_in_name"] for v in paid["variants"]] == [5000, 5000, None]


def test_simple_options_follow_the_price_rule():
    simple: list[T.SimpleOption] = [{"id": "1", "group": "그립", "name": "기본", "extra_price": 0},
                                    {"id": "2", "group": "그립", "name": "골프프라이드", "extra_price": 20000}]
    assert [o["id"] for o in choose_variants(options(simple=simple), 0)["simple_options"]] == ["1"]
    assert len(choose_variants(options(simple=simple), 0, paid=True)["simple_options"]) == 2


def test_honma_golf_set():
    """smartstore.naver.com/thegolf/products/5543745139 (Honma D1 set), 2026-11-02: an S set free and in stock
    (its name has a "+" between two clubs), an R set +60,000 and sold out."""
    opts = options(variant("44685560815", "S 세트 (D1 500 S+950 S)", 0, 94),
                   variant("44685560816", "R 세트 (D1 500 R)", 60000, 0))
    c = choose_variants(opts, 990000)
    assert [v["id"] for v in c["variants"]] == ["44685560815"] and c["skipped_paid"] == 1
    assert c["variants"][0]["price_in_name"] is None and c["name_mismatches"] == []
    paid = choose_variants(opts, 990000, paid=True)
    assert paid["variants"][1]["price"] == 1050000 and paid["sold_out"] == 1 and paid["available"] == 1


def test_two_amounts_in_one_name():
    """A combination's name joins its parts, each may carry its own amount; store extra price 0."""
    opts = options(variant("1", "드라이버 (+50,000원) / 우드 (+30,000원)", 0, 3),
                   variant("2", "드라이버 (+50,000원) / 우드 (+30,000원)", 80000, 3),
                   variant("3", "드라이버 (+0원) / 우드 (+0원)", 0, 3))
    c = choose_variants(opts, 500000)
    assert [v["id"] for v in c["variants"]] == ["3"] and c["skipped_paid"] == 2
    assert c["name_mismatches"] == ["1"]                     # labels say 80,000 more, the store says 0
    assert choose_variants(opts, 500000, paid=True)["variants"][0]["price_in_name"] is None


def test_reva_cheaper_without_the_bag():
    """smartstore.naver.com/thegolf/products/13413924099 (Callaway REVA set), 2026-11-02: each colour with the bag
    at the product's price and without it 100,000 cheaper, those sold out. A price change both ways counts."""
    opts = options(variant("1", "피치/서프 클럽 10PCS (캐디백포함)", 0, 50),
                   variant("2", "피치/서프 클럽 10PCS (캐디백 미포함)", -100000, 0),
                   variant("3", "블랙 클럽 10PCS (캐디백포함)", 0, 43),
                   variant("4", "블랙 클럽 10PCS (캐디백 미포함)", -100000, 0))
    c = choose_variants(opts, 1590000)
    assert [v["id"] for v in c["variants"]] == ["1", "3"] and c["skipped_paid"] == 2 and c["sold_out"] == 0
    paid = choose_variants(opts, 1590000, paid=True)
    assert [v["price"] for v in paid["variants"]] == [1590000, 1490000, 1590000, 1490000] and paid["sold_out"] == 2
