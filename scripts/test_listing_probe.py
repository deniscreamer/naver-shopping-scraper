"""listing_probe.analyze on fixture rows (2026-11-22): where the rows are, the section's screen with its examples,
the alternative rules' difference, the flags for the agent. Offline."""
import listing_probe as P

FILTERS = {"categories": [{"id": "50002796", "name": "티셔츠", "path": ["스포츠/레저", "골프", "골프의류", "티셔츠"], "depth": 4},
                          {"id": "50002797", "name": "니트", "path": ["스포츠/레저", "골프", "골프의류", "니트"], "depth": 4}],
           "attributes": [{"id": "10012485|M10574795", "group": "10012485", "name": "긴팔"}], "price": [], "facets": []}


def row(name, cat="50002796", reviews=10):
    return {"name": name, "category_id": cat, "reviews": {"count": reviews}}


ROWS = [row("타이틀리스트 남성 골프 긴팔 티셔츠"), row("남성 골프 맨투맨 기모"), row("남성 골프 카라티 티셔츠"),
        row("남성 골프 카라 티셔츠", reviews=0), row("남성 여름 냉감 긴팔 이너"),
        row("남성 골프 니트 반집업", "50002797"), row("남성 골프 니트 스웨터", "50002797")]


def test_the_probe_counts_the_rows_the_screen_and_the_adjacent_category():
    got = P.analyze(ROWS, FILTERS, "50002796", "mens-fall-long-sleeve-tops")
    assert got["rows"] == 7 and got["in_category"] == 5
    assert got["screen"]["kept"] == 2 and got["screen"]["reasons"]["title:not_long_sleeve"] == 2
    assert got["screen"]["reasons"]["title:cooling"] == 1
    assert got["others_screen"]["50002797"] == {"rows": 2, "kept": 2, "examples": {"kept": [
        "남성 골프 니트 반집업", "남성 골프 니트 스웨터"]}}
    flags = {f["flag"] for f in got["attention"]}
    assert {"kept_low", "requires_drops", "adjacent_category", "attribute_filter"} <= flags
    assert got["adjacent"] == [{"id": "50002797", "path": "스포츠/레저 > 골프 > 골프의류 > 니트"}]


def test_the_alternative_rules_show_what_they_add():
    rules = P.LF.title_rules("50002796", leaf="mens-fall-long-sleeve-tops")
    wider = [dict(r, requires=[[*r["requires"][0], "카라"]]) if r["code"] == "not_long_sleeve" else r for r in rules]
    got = P.analyze(ROWS, FILTERS, "50002796", "mens-fall-long-sleeve-tops", alt_rules=wider)
    assert got["alt"]["kept"] == 4 and got["alt"]["added"] == ["남성 골프 카라 티셔츠", "남성 골프 카라티 티셔츠"]
    assert got["alt"]["dropped"] == []
    assert "## " not in P.report("50002796", None, {})                       # no query, no section
    assert "kept by the screen: 2 of 5" in P.report("50002796", "mens", {"q": got})
