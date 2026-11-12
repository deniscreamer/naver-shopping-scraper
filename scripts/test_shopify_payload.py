"""shopify_payload's brand and title rules (2026-11-12, the junior clubs' first 30)."""


def test_one_brand_whatever_its_dots_and_spaces():
    """12552413383 / 12813088660 (2026-11-11): "US Kids Golf U.S.KIDSGOLF UL7-51" and "U.S. Kids Golf US Kids Golf
    UL7 45": the brand once, as the vendor spells it."""
    import shopify_payload as sp
    assert sp.brand_key("U.S.KIDSGOLF") == sp.brand_key("U.S. Kids Golf") == sp.brand_key("US Kids Golf")
    assert sp.vendor_name("U.S.KIDSGOLF", {"uskidsgolf": "U.S. Kids Golf"}) == "U.S. Kids Golf"
    assert sp._brand_in("US Kids Golf U.S.KIDSGOLF UL7-51 Junior Set", "U.S. Kids Golf") == "U.S. Kids Golf UL7-51 Junior Set"
    assert sp._brand_in("US Kids Golf UL7 45 Junior Set", "U.S. Kids Golf") == "U.S. Kids Golf UL7 45 Junior Set"
    assert sp._brand_in("Yonex Ezone Set with Yonex bag", "YONEX") == "YONEX Ezone Set with YONEX bag"


def test_a_brand_with_its_letters_swapped_is_the_brand():
    """7151166811 (2026-11-11): the images say PGM, the seller's title PMG: not "PGM PMG Kids' ..."."""
    import shopify_payload as sp
    product = {"title_ko": "t", "brand_ko": "b"}
    en = sp.English({"en": {sp.text_id("title", "t"): "PMG Kids' Junior Golf Club Set",
                            sp.text_id("brand", "b"): "PGM"}})
    assert sp.title_vendor(product, en)[0] == "PGM Kids' Junior Golf Club Set"
