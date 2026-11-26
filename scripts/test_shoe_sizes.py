"""shoe_sizes: Korean mm -> US sizes (the owner's chart, 2026-11-25) and the section of a pair by its gender and sizes."""
import shoe_sizes as S
from transform_shops import rules_for


def test_the_owners_chart():
    assert [S.us_mens(m) for m in (250, 255, 260, 270, 280, 290, 300)] == [7, 7.5, 8, 9, 10, 11, 12]
    assert [S.us_womens(m) for m in (220, 225, 230, 240, 250, 260)] == [5, 5.5, 6, 7, 8, 9]


def test_mm_read_from_the_sellers_values():
    assert [S.mm_of(v) for v in ("250", "255mm", "265(US 8.5)", "270 와이드", "235㎜", "US 7 (250)")] == \
        [250, 255, 265, 270, 235, 250]
    assert [S.mm_of(v) for v in ("화이트", "8.5", "GY8525", "250/260", "2025", "")] == [None] * 6
    assert S.wide("270 와이드") and S.wide("265 3E") and not S.wide("화이트(W)") and not S.wide("270")


def test_labels_by_the_stated_gender():
    assert S.us_label(270, "mens") == "US 9 (270 mm)"
    assert S.us_label(250, "womens") == "US 8 (250 mm)"
    assert S.us_label(250, "unisex") == "US M 7 / W 8 (250 mm)"
    assert S.us_label(270, "mens", "Wide") == "US 9 Wide (270 mm)"
    assert [S.width(v) for v in ("XW 240", "W 220", "M 250", "270 와이드", "화이트(W)", "250")] == \
        ["Extra Wide", "Wide", "", "Wide", "", ""]


def test_footjoys_width_letters():
    """FootJoy PRO SL 10239862675 (2026-11-25): XW the men's extra wide, W the women's wide, 240 in both."""
    out = S.resolve([{"name_ko": "선택", "values_ko": ["남성용", "여성용"]},
                     {"name_ko": "사이즈", "values_ko": ["XW 240", "XW 250", "W 220", "W 240"]}], "mixed")
    assert out["held"] is None and [v["us"] for v in out["values"]] == [
        "US M 4 / W 5 Wide (220 mm)", "US M 6 / W 7 Wide (240 mm)",
        "US M 6 / W 7 Extra Wide (240 mm)", "US M 7 / W 8 Extra Wide (250 mm)"]
    # every size value sold by one gender's variants only: that gender's label
    out = S.resolve([{"name_ko": "사이즈", "values_ko": ["XW 240", "W 240"]}], "mixed",
                    {"XW 240": {"mens"}, "W 240": {"womens"}})
    assert [v["us"] for v in out["values"]] == ["US 7 Wide (240 mm)", "US 6 Extra Wide (240 mm)"]
    # one value both sell (adidas S2G 13171935653): every value both labels, never "US 7.5" twice
    out = S.resolve([{"name_ko": "사이즈", "values_ko": ["245", "250", "255"]}], "mixed",
                    {"245": {"womens"}, "250": {"mens", "womens"}, "255": {"mens"}})
    assert [v["us"] for v in out["values"]] == ["US M 6.5 / W 7.5 (245 mm)", "US M 7 / W 8 (250 mm)",
                                                "US M 7.5 / W 8.5 (255 mm)"]


def test_resolve_finds_the_size_option_by_its_values():
    """낫소 4822059321 (2026-11-25): a model option, a colour option, the sizes 230-285 out of order."""
    options = [{"name_ko": "낫소 보아 골프화", "values_ko": ["스윙스타", "OK", "알바트로스"]},
               {"name_ko": "색상", "values_ko": ["화이트", "블랙", "화이트(여성)", "화이트(남성)"]},
               {"name_ko": "사이즈", "values_ko": ["250", "255", "260", "230", "235"]}]
    out = S.resolve(options, "mixed")
    assert out["option"] == 2 and out["held"] is None and out["profile"] == "shoes_unisex"
    assert [v["ko"] for v in out["values"]] == ["230", "235", "250", "255", "260"]
    assert out["values"][0]["us"] == "US M 5 / W 6 (230 mm)"
    assert S.resolve(options, "mens")["values"][-1]["us"] == "US 8 (260 mm)"


def test_resolve_holds_what_it_cannot_read():
    assert S.resolve([{"name_ko": "색상", "values_ko": ["화이트", "블랙"]}], "mens")["held"].startswith("no size option")
    held = S.resolve([{"name_ko": "사이즈", "values_ko": ["250", "260", "free"]}], "mens")["held"]
    assert held == "'free': not read as a size in mm"
    held = S.resolve([{"name_ko": "사이즈", "values_ko": ["250", "250mm", "260"]}], "mens")["held"]
    assert held.startswith("two Korean sizes on one US size")
    held = S.resolve([{"name_ko": "사이즈", "values_ko": ["7", "8", "9"]}], "mens")["held"]
    assert "not read as sizes in mm" in held


def test_section_by_gender_and_sizes():
    """The owner 2026-11-25: one section a pair; unstated by its largest size, unisex and undecided men's."""
    assert S.section_gender("mens", [250, 290])[0] == "mens"
    assert S.section_gender("womens", [220, 250])[0] == "womens"
    assert S.section_gender("mens", [220, 245])[0] == "conflict"
    assert S.section_gender("womens", [260, 290])[0] == "conflict"
    assert S.section_gender(None, [250, 290])[0] == "mens"
    assert S.section_gender(None, [220, 250])[0] == "womens"
    assert S.section_gender(None, [230, 260])[0] == "unknown"
    assert S.section_gender("unisex", [230, 260])[0] == "mens"
    assert S.section_gender("mixed", [220, 250])[0] == "womens"
    assert S.section_gender(None, [])[0] == "unknown"


def test_the_chart_block():
    out = S.resolve([{"name_ko": "사이즈", "values_ko": ["250", "270"]}], "mens")
    html = S.chart_html(out)
    assert html.startswith("<h3>Size chart (US)</h3>") and "<td>US 9</td>" in html and "<td>10.6 in</td>" in html


def test_the_category_uses_them():
    shoes = rules_for("fairwardgolf").categories["50001740"]
    assert shoes.shoe_sizes and not shoes.sizes and not shoes.reviewed and shoes.paid_variants and not shoes.paid_addons
