"""The lenses on real records (fixtures/lens/cases.json, made by make_lens_fixture.py from the wedge pilot, the junior
runs and the store's duplicate cleanup, 2026-11-15), and on the unexpected: torn files, missing photos, products a
file never heard of, one price for all, an id that is two keys (neither shown), a job with no events.

    .venv/bin/python -m pytest scripts/test_lens_fixture.py -q

The shop is rebuilt in a tmp folder; its photos are drawn there (a colour per product), no seller photo is in git.
"""
import hashlib
import json
import os

import pytest
from PIL import Image

import dedupe
import lens as L
import sheet as S
from shop_view import ShopView, collected_photos, job_keys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = json.load(open(os.path.join(HERE, "fixtures", "lens", "cases.json"), encoding="utf-8"))
SHOP = FIX["shop"]
WEDGE_JOB, JUNIOR_JOB = "fairwardgolf-50002783-20261115T150124Z", "fairwardgolf-50002787-20261112T155753Z"


def key(pid):
    return next(k for k in FIX["cases"] if k.endswith(":" + pid))


def write_jsonl(path, rows, torn=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        if torn:
            f.write('{"key": "fairwardgolf:naver:1:2", "stat')            # a write cut short
    return path


def colour(text):
    h = hashlib.sha256(text.encode()).digest()
    return (h[0], h[1], h[2])


@pytest.fixture
def real(tmp_path):
    """The fixture's records as a shop and two jobs; every prepared image drawn except the BG-100 Black Edition's
    second one (a photo gone from disk)."""
    root, jobs = tmp_path / "shops", tmp_path / "jobs"
    d = root / SHOP
    write_jsonl(str(d / "prepared" / "products.jsonl"), FIX["prepared"], torn=True)
    write_jsonl(str(d / "translation" / "translated.jsonl"), FIX["translated"])
    write_jsonl(str(d / "placement" / "placements.jsonl"), FIX["placements"])
    write_jsonl(str(d / "publish" / "published.jsonl"), FIX["ledger"], torn=True)
    run = d / "collected" / "lens-20261115T000000Z"
    write_jsonl(str(run / "products.jsonl"), FIX["collected"])
    (run / "manifest.json").write_text("{}")
    for p in FIX["prepared"]:
        for i, img in enumerate(p["product"]["images"]):
            if p["key"] == key("13785630702") and i == 1:
                continue
            path = d / img["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (48, 36), colour(img["file"])).save(path)
    for job, events in FIX["events"].items():
        write_jsonl(str(jobs / job / "events.jsonl"), events)
    return str(root), str(jobs)


# ---- the real cases ------------------------------------------------------------------------------------------

def test_the_view_reads_every_real_case(real):
    root, _ = real
    v = ShopView(SHOP, root)
    for k in FIX["cases"]:
        p = v.get(k)
        assert p.key == k and p.title_ko, k
    bermuda = v.get(key("13127601930"))
    assert bermuda.brand_source == "title_word" and bermuda.title_en and bermuda.leaves == ["wedge-sets"]
    assert bermuda.store == "withdrawn" and bermuda.reason.startswith("replaced_by:")      # the cleanup's last word
    assert bermuda.handle                                                               # from its published row
    junior = v.get(key("4385835200"))
    assert junior.variants == 6 and junior.options[0].startswith("선택해 주세요: 6~8세")
    restored = v.get(key("13475342948"))                    # withdrawn, then published again: the last row wins
    assert restored.store == "published" and restored.brand_source == "title_word"


def test_price_flags_the_cheapest_wedge_sets_at_the_foot(real):
    root, _ = real
    plan = L.price(ShopView(SHOP, root), "50002783", store="any")
    order = [c.key for c in plan.cards]
    assert order[0] == key("12731471202")                                  # ₩89,000 Yamaha RMX, two wedges
    assert plan.cards[0].mark in ("flag", "info") and plan.cards[0].data["z"] < 0
    assert all(order.index(key("5305572105")) < order.index(key(p)) for p in ("13127601930", "13016152694"))


def test_section_shows_the_bar_clamp_among_junior_sets(real):
    root, _ = real
    plan = L.section(ShopView(SHOP, root), category="50002787")
    clamp = next(c for c in plan.cards if c.key == key("13770121877"))
    assert "클램프" in clamp.data["title_ko"] and clamp.photos                 # the photo is what shows it


def test_brand_puts_the_shops_own_name_and_the_title_words_first(real):
    root, _ = real
    plan = L.brand(ShopView(SHOP, root), "50002787")
    sources = [c.data["brand_source"] or "none" for c in plan.cards]
    weak = [s.split(":")[0] in L.WEAK_BRAND for s in sources]
    assert weak == sorted(weak, reverse=True)                                   # every weak one before any strong
    assert {key("13770121877"), key("13475342948"), key("13324729995")} <= {c.key for c in plan.cards if c.mark == "flag"}


def test_held_on_the_real_wedge_job(real):
    root, jobs = real
    plan = L.held(ShopView(SHOP, root), WEDGE_JOB, jobs)
    by = {c.key: c for c in plan.cards}
    # one cause, one banner: held by the transform (prepared) or by the placement (not taken)
    assert by[key("12178049211")].group == "held: single_only" == by[key("11097352600")].group
    assert by[key("11097352600")].data["options"]                              # from its collected line
    dup = by[key("13292782760")]
    assert dup.group == "duplicate_of" and dup.data["match"] == key("13619604371")
    assert len(dup.photos) == 4 and all(dup.photos)                            # its 2 photos, then its match's 2
    # published in the job, then "not taken" on a resume: it reached the store, it is no hold
    assert key("13127601930") not in by and key("13016152694") not in by


def test_held_on_the_real_junior_job_names_every_screen_code(real):
    root, jobs = real
    plan = L.held(ShopView(SHOP, root), JUNIOR_JOB, jobs)
    groups = {c.group for c in plan.cards}
    assert {"card_not_found", "title: not_golf", "category_mismatch"} <= groups
    nowhere = next(c for c in plan.cards if c.group == "card_not_found")
    assert nowhere.photos == [None] and nowhere.lines[0]                         # a key the shop's files never saw


def test_dupes_on_the_real_bg100_and_reva_groups(real):
    root, _ = real
    plan = L.dupes(ShopView(SHOP, root))
    rows = [(c.key, c.data["role"], c.data["title_only"]) for c in plan.cards]
    groups = {c.data["dup_group"] for c in plan.cards}
    assert (key("13809756465"), "keep", True) in rows or (key("13827555559"), "keep", True) in rows
    reva = [c for c in plan.cards if c.key in (key("13325799991"), key("11989518458"))]
    assert len(reva) == 2 and all(c.data["title_only"] for c in reva)          # with or without bags: by title only
    assert key("12215613033") not in {c.key for c in plan.cards}               # withdrawn copies are not grouped
    assert len(groups) == 3                                                     # BG-100, REVA, A11N


def test_products_puts_the_real_versions_side_by_side(real, tmp_path):
    root, _ = real
    ids = ["13785630702", "13809756465", "13827555559", "11989518458", "13325799991"]
    plan = L.products(ShopView(SHOP, root), ids)
    assert [c.key.split(":")[3] for c in plan.cards] == ids and plan.photos == 6
    black = plan.cards[0]
    gone = [i["file"] for i in next(p for p in FIX["prepared"] if p["key"] == black.key)["product"]["images"]][1]
    assert all(os.path.exists(x) for x in black.photos) and not any(x.endswith(gone) for x in black.photos)
    done = L.render(plan, str(tmp_path / "out"))
    assert len(done["sheets"]) == 1 and os.path.getsize(done["sheets"][0]) > 0


def test_every_lens_renders_the_real_shop_from_the_command_line(real, tmp_path):
    root, jobs = real
    runs = [["section", "--category", "50002787"], ["price", "--category", "50002783", "--store", "any"],
            ["brand"], ["dupes"], ["held", "--job", WEDGE_JOB], ["products", "13770121877", "8958060680"]]
    for args in runs:
        out = tmp_path / args[0]
        cmd = [args[0], SHOP, *args[1:], "--shops-root", root, "--jobs-root", jobs, "--out", str(out)]
        assert L.main(cmd) == 0, args
        summary = json.load(open(out / "summary.json", encoding="utf-8"))
        assert summary["meta"]["lens"] == args[0] and summary["cards"], args
        index = (out / "index.tsv").read_text(encoding="utf-8").splitlines()
        assert len(index) == len(summary["cards"]) + 1 and all("\n" not in x for x in index)


# ---- the unexpected ------------------------------------------------------------------------------------------

def test_torn_last_lines_are_skipped(real):
    root, _ = real
    v = ShopView(SHOP, root)
    assert "fairwardgolf:naver:1:2" not in v.keys() and len(v.prepared) == len(FIX["prepared"])


def test_one_price_for_all_has_no_outlier(tmp_path):
    median, score = L.outliers([300000] * 8)
    assert median == pytest.approx(300000) and score(300000) == 0


def test_too_few_prices_flag_nothing():
    assert L.outliers([1000, 900000])[0] is None


def test_a_product_with_no_variants_no_images_no_title(tmp_path):
    root = tmp_path / "shops"
    k = f"{SHOP}:naver:9:99"
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"),
                [{"key": k, "status": "ready", "source": {"category_id": "50002783"}, "product": {}}])
    write_jsonl(str(root / SHOP / "publish" / "published.jsonl"), [{"key": k, "status": "published"}])
    v = ShopView(SHOP, str(root))
    p = v.get(k)
    assert (p.title_ko, p.price_krw, p.variants, p.photos) == ("", None, 0, [])
    plan = L.price(v, "50002783")
    assert plan.cards[0].mark == "flag" and plan.cards[0].lines[0].startswith("₩?")
    assert L.render(plan, str(tmp_path / "o"))["sheets"]


def test_a_shop_with_no_files_draws_nothing(tmp_path):
    v = ShopView(SHOP, str(tmp_path / "none"))
    assert v.keys() == [] and L.section(v, category="1").cards == []
    assert L.render(L.section(v, category="1"), str(tmp_path / "o"))["sheets"] == []


def test_a_job_with_no_events(tmp_path, real):
    root, _ = real
    assert L.held(ShopView(SHOP, root), "no-such-job", str(tmp_path)).cards == []
    assert job_keys("no-such-job", str(tmp_path)) == []


def test_a_product_id_of_two_keys_shows_neither_and_lists_both(tmp_path, capsys):
    root = tmp_path / "shops"
    rows = [{"key": f"{SHOP}:naver:{ch}:777", "status": "ready", "product": {}} for ch in (1, 2)]
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"), rows)
    plan = L.products(ShopView(SHOP, str(root)), ["777", "nope", f"{SHOP}:naver:2:777"])
    assert [c.key for c in plan.cards] == [f"{SHOP}:naver:2:777"]             # the key chooses (2026-11-16)
    out = capsys.readouterr().out
    assert "nope" in out and f"{SHOP}:naver:1:777" in out and f"{SHOP}:naver:2:777" in out   # the miss, both keys


def test_newest_collect_run_gives_the_photos(tmp_path):
    shop_dir = tmp_path / SHOP
    for run, n in (("z-20261101T000000Z", 3), ("a-20261115T000000Z", 2)):       # newest by timestamp, not by name
        for i in range(1, n + 1):
            p = shop_dir / "collected" / run / "images" / "5" / f"{SHOP}-5-{i:03d}-h{i}.webp"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
    got = collected_photos(str(shop_dir), "5")
    assert len(got) == 2 and all("a-20261115" in g for g in got)
    twice = shop_dir / "collected" / "a-20261115T000000Z" / "images" / "5" / f"{SHOP}-5-003-h1.webp"
    twice.write_bytes(b"x")                                                    # one image at two positions: once
    assert len(collected_photos(str(shop_dir), "5")) == 2


def test_a_broken_image_file_is_drawn_as_no_photo(tmp_path):
    bad = tmp_path / "bad.webp"
    bad.write_bytes(b"not an image")
    cards = [S.Card(n=1, key="k", photos=[str(bad)], lines=["한글 라벨 " * 20])]   # a label far too long
    assert S.grid(cards, str(tmp_path / "g")) and S.rows(cards, str(tmp_path / "r"))


def test_a_group_longer_than_a_sheet_goes_on_over_sheets(tmp_path):
    cards = [S.Card(n=i, key=f"k{i}", group="one") for i in range(1, 8)]
    assert len(S.rows(cards, str(tmp_path), per_sheet=3, photos=1, thumb=30)) == 3


def test_tabs_and_newlines_in_a_title_stay_one_index_line(tmp_path):
    cards = [S.Card(n=1, key="k", data={"title_ko": "웨지\t세트\n2개"})]
    tsv, _ = S.write_index(cards, str(tmp_path), ["title_ko"])
    lines = open(tsv, encoding="utf-8").read().splitlines()
    assert len(lines) == 2 and lines[1].split("\t")[-1] == "웨지 세트 2개"


def test_dupes_with_an_empty_store(tmp_path):
    v = ShopView(SHOP, str(tmp_path))
    assert L.dupes(v, shops_root=str(tmp_path)).cards == []


def test_held_reason_groups_of_every_real_shape():
    cases = {
        "not ready to publish (placement held: single_only)": "held: single_only",
        "failed images: description_images error sidecar": "failed images",
        "deferred: api_500": "deferred: api_500",
        "not ready to publish (placement unresolved: gender unknown)": "placement unresolved: gender unknown",
        "not ready to publish (placement placed: None)": "placement placed: None",
        "duplicate_of:fairwardgolf:naver:1100142898:13619604371": "duplicate_of",
        "duplicate_of_withdrawn:fairwardgolf:naver:1:2": "duplicate_of_withdrawn",
        "title:not_golf (a cable-pulling grip; the rule added after the snapshot)": "title: not_golf",
        "card_not_found": "card_not_found",
        "category_mismatch": "category_mismatch",
        "held: single_only, agency_no_brand": "held: single_only, agency_no_brand",
        "": "?",
    }
    for reason, group in cases.items():
        assert L._reason_group(reason) == group, reason
    assert L._match_key("duplicate_of:fairwardgolf:naver:1100142898:13619604371") == \
        "fairwardgolf:naver:1100142898:13619604371"
    assert L._match_key("card_not_found") is None


def test_the_dedupe_report_reads_the_fixtures_collected_lines(real):
    root, _ = real
    rep = dedupe.report(SHOP, root)
    assert rep["groups"] == 3 and rep["title_only"] == 4                    # A11N: by photos and variants


# ---- the review's fixes (2026-11-15: five reviewers on real data, each finding checked by a sceptic) ------------

def test_held_shows_failed_and_deferred_products_of_real_jobs(real):
    root, jobs = real
    junior = L.held(ShopView(SHOP, root), JUNIOR_JOB, jobs)
    sets = L.held(ShopView(SHOP, root), "fairwardgolf-50002788-20261113T043522Z", jobs)
    failed = [c for c in sets.cards if c.data["event"] == "failed"]
    assert failed and failed[0].group == "failed translate" and "too long" in failed[0].data["reason"]
    recovered = [e["key"] for e in FIX["events"][JUNIOR_JOB] if e["event"] == "failed"
                 and any(x["key"] == e["key"] and x["event"] == "published" for x in FIX["events"][JUNIOR_JOB])]
    assert recovered and not set(recovered) & {c.key for c in junior.cards}     # failed, then published: no hold
    irons = L.held(ShopView(SHOP, root), "fairwardgolf-50002670-20261115T045151Z", jobs)
    assert any(c.data["event"] == "deferred" and c.group == "deferred: api_500" for c in irons.cards)


def test_held_marks_red_a_duplicate_of_a_withdrawn_match_and_names_the_live_copy(real):
    root, jobs = real
    plan = L.held(ShopView(SHOP, root), WEDGE_JOB, jobs)
    gosports = next(c for c in plan.cards if c.key == key("13261457036"))
    assert gosports.mark == "flag" and gosports.data["match_store"] == "withdrawn"
    # its match was replaced_by 13379851400, a key this fixture has no ledger row of: not live, so not named live
    # (2026-11-16: the chain is followed to a published key; the real chain: test_lens_live_copy.py)
    assert gosports.data["match_live"] is None and "-> no live copy (ends at 13379851400)" in gosports.lines
    assert "duplicate_of:13619939279" in " ".join(gosports.lines)              # the key cut to its product id
    assert gosports.data["signals"] is not None and set(gosports.data["signals"]) == {"first_photo", "photos", "variants"}
    bombtech = next(c for c in plan.cards if c.key == key("13292782760"))
    assert bombtech.mark == "info" and bombtech.data["match_store"] == "published"


def test_section_marks_the_real_set_or_single_listing(real):
    root, _ = real
    plan = L.section(ShopView(SHOP, root), leaf="wedge-sets", store="any")
    yamato = next(c for c in plan.cards if c.key == key("12951827729"))       # 세트 또는 개별
    assert yamato.mark == "info" and yamato.data["single_looking"]
    bermuda = next(c for c in plan.cards if c.key == key("13127601930"))
    assert not bermuda.data["single_looking"]


def test_all_prepared_photos_gone_falls_back_to_the_collected_ones(tmp_path):
    root = tmp_path / "shops"
    k = f"{SHOP}:naver:9:42"
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"),
                [{"key": k, "status": "ready", "product": {"images": [{"file": "collected/OLD/images/42/s-42-001-bb.jpg"}]}}])
    p = root / SHOP / "collected" / "1-20261101T000000Z" / "images" / "42" / "s-42-001-aa.jpg"
    p.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(p)
    assert ShopView(SHOP, str(root)).get(k).photos == [str(p)]


def test_most_prices_equal_does_not_make_a_small_step_an_outlier():
    _, score = L.outliers([100] * 5 + [101])
    assert abs(score(101)) < 1
    assert score(1000) > L.HIGH_Z                                               # x10 still is


def test_price_flags_far_ends_of_a_two_humped_category_and_marks_the_top(tmp_path):
    root = tmp_path / "shops"
    prices = [10500] + [30000 + 2000 * i for i in range(30)] + [300000 + 20000 * i for i in range(30)] + [12000000]
    rows = [{"key": f"{SHOP}:naver:1:{i}", "status": "ready", "source": {"category_id": "c"},
             "product": {"variants": [{"price_krw": v}]}} for i, v in enumerate(prices)]
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"), rows)
    plan = L.price(ShopView(SHOP, str(root)), "c", store="any")
    assert plan.cards[-1].mark == "flag" and plan.cards[-1].data["of_median"].startswith("x")   # x25+ of the median
    assert plan.meta["dearest_marked"] >= 1 and plan.cards[-2].mark == "info"


def test_under_five_prices_the_lens_says_it_marks_nothing(tmp_path):
    root = tmp_path / "shops"
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"),
                [{"key": f"{SHOP}:naver:1:{i}", "source": {"category_id": "c"},
                  "product": {"variants": [{"price_krw": 1000 * (i + 1)}]}} for i in range(3)])
    plan = L.price(ShopView(SHOP, str(root)), "c", store="any")
    assert plan.meta["note"] and not any(c.mark for c in plan.cards)


def test_brand_marks_one_vendor_written_several_ways(tmp_path):
    root = tmp_path / "shops"
    names = [("yamato", "specs:브랜드"), ("yamato golf", "specs:제조사"), ("Yamato", "specs:브랜드"), ("Lazrus", "specs:브랜드")]
    write_jsonl(str(root / SHOP / "prepared" / "products.jsonl"),
                [{"key": f"{SHOP}:naver:1:{i}", "product": {"brand_ko": b, "brand_source": src}}
                 for i, (b, src) in enumerate(names)])
    plan = L.brand(ShopView(SHOP, str(root)), store="any")
    marks = {c.data["brand"]: c.mark for c in plan.cards}
    assert marks == {"yamato": "info", "yamato golf": "info", "Yamato": "info", "Lazrus": None}
    assert plan.meta["spellings"] == {"yamato": ["Yamato", "yamato", "yamato golf"]}


def test_dupes_shows_a_group_the_owner_judged_versions_grey_and_says_so(real):
    root, _ = real
    v = ShopView(SHOP, root)
    L.mark_versions(v, [key("13325799991"), key("11989518458")], "owner 2026-11-15: REVA with bags is another product")
    plan = L.dupes(ShopView(SHOP, root))
    reva = [c for c in plan.cards if c.key in (key("13325799991"), key("11989518458"))]
    assert all(c.mark is None and c.data["reviewed"] for c in reva) and "reviewed" in reva[0].group
    bg = [c for c in plan.cards if c.key in (key("13809756465"), key("13827555559"))]
    assert all(c.mark == "flag" for c in bg)                                     # title words only: red wins
    assert plan.meta["published"] and len(plan.meta["reviewed_groups"]) == 1
    assert all("options" in c.data for c in plan.cards)


def test_dupes_versions_needs_two_keys_and_a_note(real):
    root, _ = real
    with pytest.raises(SystemExit):
        L.main(["dupes", SHOP, "--versions", key("13325799991"), "--shops-root", root])
    with pytest.raises(SystemExit):
        L.main(["dupes", SHOP, "--versions", f"{key('13325799991')},{key('11989518458')}", "--shops-root", root])


def test_two_looks_at_one_scope_write_two_folders(tmp_path):
    a = L.out_dir("r", SHOP, "brand", "50002783")
    b = L.out_dir("r", SHOP, "brand", "50002783", source="none,title_word")
    c = L.out_dir("r", SHOP, "section", "wedge-sets", store="withdrawn")
    assert len({a, b, c}) == 3 and b.endswith("brand-50002783-src-none+title_word") and c.endswith("-withdrawn")


def test_a_short_group_after_a_long_one_does_not_leave_a_sheet_almost_empty(tmp_path):
    cards = [S.Card(n=1, key="a", group="one")] + [S.Card(n=i, key=f"k{i}", group="two") for i in range(2, 22)]
    assert len(S.rows(cards, str(tmp_path), per_sheet=12, photos=1, thumb=30)) == 2   # 12 + 9, not 1 + 12 + 8


def test_a_long_title_wraps_so_its_tail_shows(tmp_path):
    from PIL import ImageDraw
    pen = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines = S._wrap(pen, S._font(12), ["₩96,210 x0.33", "Yamato Full-Face Forged Milled Golf Wedge Set or Single"],
                    144, 3)
    assert len(lines) == 3 and "Single" in " ".join(lines) or lines[-1].endswith("…")
