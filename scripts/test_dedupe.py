"""Offline tests for dedupe.py (the rule, the index, --report, --pairs) and job.py --dedupe (the decision after
collect, log mode, the replacement after publication). The records are built from real patterns of the fairwardgolf
shop (2026-11-15): Wilson Profile JGI sold by several stores, an Orlimar club and its Putter sharing a photo, Srixon
27ZXI-RKT and its LS / MAX, TaylorMade Qi4D and Qi4D MAX.

    .venv/bin/python -m pytest scripts/test_dedupe.py -q
"""
import json

import pytest

import dedupe as D
import job as J
from collect_guard import Outcome

SHOP = "fairwardgolf"
WILSON = "윌슨 주니어 프로필 JGI 골프 클럽 패키지 세트 - 스탠드 Blue Junior - Small Left"
WILSON_VALUES = [["Red", "Junior-Small", "Left"], ["Red", "Junior-Small", "Right"], ["Yellow", "Junior-Medium", "Left"],
                 ["Yellow", "Junior-Medium", "Right"]]


def record(channel, pid, name, grade="SEED", reviews=0, price=288540, photos=("a", "b", "c"), values=WILSON_VALUES,
           category="50002787"):
    """A collected record with what dedupe reads (listing, photos, variants)."""
    key = f"{SHOP}:naver:{channel}:{pid}"
    return {"key": key,
            "listing": {"product_id": str(pid), "name": name, "category_id": category, "key": key,
                        "store": {"channel_no": str(channel), "grade": grade}, "reviews": {"count": reviews},
                        "pricing": {"sale_price": price, "discounted_price": price}},
            "photos": {"files": [{"position": i, "source_sha256": s} for i, s in enumerate(photos)]},
            "variants": {"variants": [{"options": v} for v in values]}}


def E(*a, status="published", **k):
    return D.entry(record(*a, **k), status)


# ---- the rule ------------------------------------------------------------------------------------------------

def test_title_key_ignores_order_case_and_signs_and_keeps_brackets():
    a = D.title_key("[던롭코리아정품] 26년 스릭슨 27ZXI-RKT 남성 풀세트 (D+W+I) GF", "50002788")
    b = D.title_key("gf 남성 풀세트 26년 27zxi rkt 스릭슨 던롭코리아정품 d w i", "50002788")
    assert a == b and "던롭코리아정품" in a and a.startswith("50002788|")
    assert D.title_key("ＡＢＣ 클럽", "1") == D.title_key("abc 클럽", "1")          # NFKC: full-width letters
    assert D.title_key("!!!", "1") is None and D.title_key(None, "1") is None
    assert D.title_key(WILSON, "50002787") != D.title_key(WILSON, "50002788")     # the category is part of it


def test_grade_rank_and_better_is_strict():
    assert D.grade_rank("PLATINUM") > D.grade_rank("PREMIUM") > D.grade_rank("BIG_POWER") > D.grade_rank("POWER") \
        > D.grade_rank("SPROUT") > D.grade_rank("SEED") > D.grade_rank(None)
    seed, power = E(1, 1, WILSON), E(2, 2, WILSON, grade="POWER")
    assert D.better(power, seed) and not D.better(seed, power)
    more = E(3, 3, WILSON, reviews=5)
    assert D.better(more, seed) and not D.better(seed, E(4, 4, WILSON))      # equal: not better
    assert D.better(E(5, 5, WILSON, grade="PREMIUM"), E(6, 6, WILSON, grade="POWER", reviews=900))


def test_wilson_profile_jgi_from_other_stores_is_a_duplicate():
    old = E(1100105662, 13261541641, WILSON, photos=("02ce", "x1", "x2"))
    new = E(102688312, 13253313396, WILSON, photos=("5f23", "y1", "y2", "y3"), price=390510, status="job")
    s = D.signals(new, old)
    assert not s["first_photo"] and s["photos"] == 0 and s["variants"] == 1.0 and s["confirmed"]
    d = D.Index([old]).decide(new)
    assert d["decision"] == "duplicate_of" and d["of"] == old["key"] and d["matches"][0]["confirmed"]


def test_a_subset_of_the_variants_is_confirmed_by_the_first_photo_only():
    old = E(1, 1, WILSON, photos=("441884fd", "p"))
    fewer = E(2, 2, WILSON, photos=("441884fd", "q", "r"), values=WILSON_VALUES[:3], status="job")
    assert D.signals(fewer, old)["variants"] == 0.75 and D.signals(fewer, old)["first_photo"]
    assert D.confirm(fewer, old)
    no_photo = E(3, 3, WILSON, photos=("z",), values=WILSON_VALUES[:3], status="job")
    assert not D.confirm(no_photo, old)                                        # 0.75 < 0.8, no shared photo


def test_half_the_photos_shared_confirm():
    old = E(1, 1, WILSON, photos=("f1", "s1", "s2", "o1"), values=[])
    new = E(2, 2, WILSON, photos=("f2", "s1", "s2", "n1"), values=[], status="job")
    assert D.signals(new, old) == {"first_photo": False, "photos": 0.5, "variants": 0.0, "confirmed": True}
    assert D.signals(E(3, 3, WILSON, values=[]), E(4, 4, WILSON, photos=("q",), values=[]))["variants"] == 0.0


def test_orlimar_club_and_its_putter_share_a_photo_but_not_the_title():
    club = E(102748022, 13261491771, "올리마르 ATS 주니어 남자 라임 / 블루 시리즈 개인 골프 클럽(3~5세) Right Hand Hybrid",
             photos=("18f3920a", "a"), values=[["LeftHand", "Driver"], ["LeftHand", "Putter"]])
    putter = E(102794121, 12819122113, "올리마르 ATS 주니어 남자 라임 / 블루 시리즈 개인 골프 클럽(3~5세) Right Hand Putter",
               photos=("18f3920a", "b"), values=[["LeftHand", "Driver"], ["LeftHand", "Putter"]], status="job")
    assert D.signals(putter, club)["confirmed"]                               # the photo alone would join them
    d = D.Index([club]).decide(putter)
    assert d == {"decision": None, "of": None, "matches": []}


@pytest.mark.parametrize("old, new", [
    ("[던롭코리아정품] 26년 스릭슨 27ZXI-RKT 남성 풀세트 (D+W+U+I) GF",
     "[던롭코리아정품] 26년 스릭슨 27ZXI-RKT LS 남성 풀세트 (D+W+U+I) GF"),
    ("[던롭코리아정품] 26년 스릭슨 27ZXI-RKT 남성 풀세트 (D+U+I) GF",
     "[던롭코리아정품] 26년 스릭슨 27ZXI-RKT MAX 남성 풀세트 (D+U+I) GF"),
    ("[던롭코리아정품] 26년 스릭슨 27ZXI-RKT 남성 풀세트 (D+U+I) GF",
     "[던롭코리아정품] 26년 스릭슨 27ZXI-RKT TR 남성 풀세트 (D+U+I) GF"),
    ("테일러메이드 QI4D 남성 골프풀세트 아이언 11개", "테일러메이드 QI4D 맥스 남성 골프풀세트 아이언 11개"),
    ("[테일러메이드정품] QI4D 남성용 조합 풀세트 (D+U+IR) GF", "[테일러메이드정품] QI4D MAX 남성용 조합 풀세트 (D+U+IR) GF"),
])
def test_another_model_word_is_another_product(old, new):
    same = dict(photos=("same",), values=[["10.5도", "5S"]], price=2670000, category="50002788")
    a, b = E(100879099, 1, old, **same), E(102256718, 2, new, status="job", **same)
    assert D.confirm(a, b)                                                    # photos and variants say "the same"
    assert D.Index([a]).decide(b)["matches"] == []                            # the title does not


def test_the_same_store_and_a_price_beyond_x2_are_not_duplicates():
    old = E(1, 1, WILSON, price=100000)
    assert D.Index([old]).decide(E(1, 2, WILSON, status="job"))["matches"] == []        # the seller's own variant
    assert D.Index([old]).decide(E(2, 2, WILSON, price=250000, status="job"))["matches"] == []
    assert D.Index([old]).decide(E(2, 3, WILSON, price=200000, status="job"))["decision"] == "duplicate_of"
    assert D.price_ok({"price": None}, {"price": 5})


def test_a_withdrawn_match_is_never_taken_even_by_a_better_seller():
    gone = E(1, 1, WILSON, status="withdrawn")
    better = E(2, 2, WILSON, grade="PLATINUM", reviews=500, status="job")
    d = D.Index([gone, E(3, 3, WILSON)]).decide(better)
    assert d["decision"] == "duplicate_of_withdrawn" and d["of"] == gone["key"] and len(d["matches"]) == 2


@pytest.mark.parametrize("grade, reviews, decision", [
    ("PREMIUM", 0, "duplicate_better"), ("POWER", 11, "duplicate_better"), ("POWER", 10, "duplicate_of"),
    ("SEED", 999, "duplicate_of")])
def test_better_worse_and_equal_against_the_best_match(grade, reviews, decision):
    index = D.Index([E(1, 1, WILSON, grade="POWER", reviews=10), E(3, 3, WILSON, grade="SEED", reviews=50)])
    d = index.decide(E(2, 2, WILSON, grade=grade, reviews=reviews, status="job"))
    assert d["decision"] == decision and d["of"] == D.entry(record(1, 1, WILSON))["key"]


def test_load_reads_the_ledger_and_leaves_out_what_was_replaced(tmp_path):
    recs = {r["key"]: r for r in (record(1, 1, WILSON), record(2, 2, WILSON), record(3, 3, WILSON),
                                  record(4, 4, WILSON), record(5, 5, WILSON))}
    keys = list(recs)
    (tmp_path / SHOP / "publish").mkdir(parents=True)
    (tmp_path / SHOP / "publish" / "published.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"key": keys[0], "status": "published"},
        {"key": keys[1], "status": "published"}, {"key": keys[1], "status": "withdrawn", "reason": "a toy"},
        {"key": keys[2], "status": "withdrawn", "reason": f"replaced_by:{keys[0]}"},
        {"key": f"{SHOP}:naver:9:9", "status": "published"}]))                  # no collected record: left out
    index = D.load(SHOP, str(tmp_path), job_keys=[keys[4]], records=recs)
    assert {k: e["status"] for k, e in index.by_key.items()} == {keys[0]: "published", keys[1]: "withdrawn",
                                                                 keys[4]: "job"}
    assert set(D.load(SHOP, str(tmp_path), withdrawn=False, records=recs).by_key) == {keys[0]}


def test_report_groups_confirmed_copies_best_first():
    wilson = [E(1, 1, WILSON), E(2, 2, WILSON, grade="POWER"), E(3, 3, WILSON, photos=("n",), values=[["x"]])]
    srixon = [E(4, 4, "스릭슨 27ZXI-RKT 풀세트", photos=("s",)), E(5, 5, "스릭슨 27ZXI-RKT LS 풀세트", photos=("s",))]
    found = D.groups(wilson + srixon)
    assert [[e["key"].split(":")[3] for e in g] for g in found] == [["2", "1"]]   # 3: not confirmed; Srixon: two titles


def test_pairs_lists_every_match_a_job_looked_at():
    m = {"key": "k-old", "status": "published", "confirmed": True, "first_photo": True, "photos": 1.0, "variants_j": 1.0}
    events = [{"key": "k1", "event": "duplicate_seen", "decision": "duplicate_of:k-old", "matches": [m]},
              {"key": "k2", "event": "not_taken", "reason": "duplicate_of:k-old", "matches": [m]},
              {"key": "k3", "event": "duplicate_better", "replaces": "k-old", "matches": [m, {**m, "key": "k-o2"}]},
              {"key": "k4", "event": "not_taken", "reason": "already_published"}]
    rows = D.pairs(events)
    assert [(r["n"], r["candidate"], r["key"], r["decision"]) for r in rows] == [
        (1, "k1", "k-old", "duplicate_of:k-old"), (2, "k2", "k-old", "duplicate_of:k-old"),
        (3, "k3", "k-old", "duplicate_better:k-old"), (4, "k3", "k-o2", "duplicate_better:k-old")]


def test_draw_pairs_writes_a_sheet_and_the_index(tmp_path):
    pytest.importorskip("PIL")
    rows = [{"n": 1, "decision": "duplicate_of:a", "candidate": f"{SHOP}:naver:1:11", "key": f"{SHOP}:naver:2:22",
             "status": "published", "confirmed": True}]
    sheets = D.draw_pairs(rows, str(tmp_path / SHOP), str(tmp_path / "out"), names={f"{SHOP}:naver:1:11": "윌슨"})
    lines = (tmp_path / "out" / "index.tsv").read_text(encoding="utf-8").splitlines()
    assert len(sheets) == 1 and lines[1].startswith("1\tduplicate_of:a\tTrue") and "윌슨" in lines[1]


# ---- job.py --dedupe -----------------------------------------------------------------------------------------

def dedupe_job(tmp_path, mode, rows):
    folder = tmp_path / "jobs" / "j1"
    folder.mkdir(parents=True)
    meta = {"shop": SHOP, "category": "50002787", "paid": False, "reviews": 20, "shops_root": str(tmp_path / "shops")}
    if mode != "off":
        meta["dedupe"] = mode
    (folder / "job.json").write_text(json.dumps(meta))
    (folder / "listing.jsonl").write_text("".join(json.dumps({"key": r["key"], "product_id": r["key"].split(":")[3],
                                                              "query": "q", "link": "l"}) + "\n" for r in rows))
    return J.Job(str(folder))


class Catalog:
    def keys(self):
        return set()


class ImagesReached(Exception):
    pass


@pytest.fixture
def collect_to_images(monkeypatch):
    """one() with collect faked (the record given) and the description images step raising ImagesReached."""
    import description_images
    got = {}
    monkeypatch.setattr(J, "collect_with_waits", lambda job, api, store, table, guard, row, tmp, specs=None:
                        Outcome("complete", data={k: v for k, v in got["line"].items() if k != "key"}))
    monkeypatch.setattr(J, "keep_line", lambda job, line, tmp: "/x/run-1")

    def images(*a, **k):
        raise ImagesReached
    monkeypatch.setattr(description_images, "run", images)
    return got


def _ctx(job, *entries):
    ctx = {"catalog": Catalog(), "api": None, "store": None, "table": None, "guard": None}
    if job.meta.get("dedupe"):
        ctx["dedupe"] = D.Index(entries)
    return ctx


def test_on_mode_closes_a_duplicate_before_its_images(tmp_path, collect_to_images):
    new = record(2, 22, WILSON)
    job = dedupe_job(tmp_path, "on", [new])
    collect_to_images["line"] = new
    what = J.one(job, _ctx(job, E(1, 11, WILSON)), new["key"], None)
    assert what == f"not taken: duplicate_of:{SHOP}:naver:1:11"
    ev = job.events()[-1]
    assert ev["event"] == "not_taken" and ev["matches"][0]["key"] == f"{SHOP}:naver:1:11"
    assert J.closed(job)[new["key"]] == f"not_taken: duplicate_of:{SHOP}:naver:1:11"


def test_on_mode_a_withdrawn_match_closes_it(tmp_path, collect_to_images):
    new = record(2, 22, WILSON, grade="PLATINUM")
    job = dedupe_job(tmp_path, "on", [new])
    collect_to_images["line"] = new
    assert J.one(job, _ctx(job, E(1, 11, WILSON, status="withdrawn")), new["key"], None).startswith(
        "not taken: duplicate_of_withdrawn:")


def test_on_mode_a_better_seller_goes_on_and_a_later_worse_one_in_the_same_job_is_compared_with_it(
        tmp_path, collect_to_images):
    better, later = record(2, 22, WILSON, grade="PREMIUM"), record(3, 33, WILSON, grade="POWER")
    job = dedupe_job(tmp_path, "on", [better, later])
    ctx = _ctx(job, E(1, 11, WILSON))
    collect_to_images["line"] = better
    with pytest.raises(ImagesReached):
        J.one(job, ctx, better["key"], None)
    assert job.events()[-1]["event"] == "duplicate_better" and job.events()[-1]["replaces"] == f"{SHOP}:naver:1:11"
    collect_to_images["line"] = later
    assert J.one(job, ctx, later["key"], None) == f"not taken: duplicate_of:{better['key']}"   # added to the index


def test_a_job_product_closed_later_in_the_run_no_longer_blocks_a_copy(tmp_path, collect_to_images):
    first, later = record(2, 22, WILSON), record(3, 33, WILSON)
    job = dedupe_job(tmp_path, "on", [first, later])
    ctx = _ctx(job, E(9, 99, "다른 상품", status="published", photos=("z",), values=[["z"]]))
    collect_to_images["line"] = first
    with pytest.raises(ImagesReached):
        J.one(job, ctx, first["key"], None)                                  # joins the index as "job"
    job.log(first["key"], "not_taken", reason="not ready to publish")        # closed after the dedupe step
    collect_to_images["line"] = later
    with pytest.raises(ImagesReached):                                       # goes on: nothing left to copy
        J.one(job, ctx, later["key"], None)
    assert first["key"] not in ctx["dedupe"].by_key and f"{SHOP}:naver:9:99" in ctx["dedupe"].by_key


def test_a_job_product_held_by_the_transform_no_longer_blocks_a_copy(tmp_path, collect_to_images):
    """2026-11-15, the wedge pilot: a seller held as agency_no_brand kept 10 sellers of its models out of the store."""
    first, later = record(2, 22, WILSON), record(3, 33, WILSON)
    job = dedupe_job(tmp_path, "on", [first, later])
    ctx = _ctx(job, E(9, 99, "다른 상품", status="published", photos=("z",), values=[["z"]]))
    collect_to_images["line"] = first
    with pytest.raises(ImagesReached):
        J.one(job, ctx, first["key"], None)
    job.log(first["key"], "prepared", status="held", held=["agency_no_brand"])
    job.log(first["key"], "translated", status="held")
    assert J.held_keys(job) == {first["key"]}
    collect_to_images["line"] = later
    with pytest.raises(ImagesReached):
        J.one(job, ctx, later["key"], None)
    assert first["key"] not in ctx["dedupe"].by_key


def test_a_product_resumed_past_collect_is_still_looked_up(tmp_path, monkeypatch):
    """2026-11-15, the wedge pilot: products held by a rule at their collection came back ready and went from
    "translated" to the store; the dedupe step now runs at any stage the job takes a product on."""
    new = record(2, 22, WILSON)
    job = dedupe_job(tmp_path, "on", [new])
    ctx = _ctx(job, E(1, 11, WILSON))
    ctx["dedupe_records"] = {new["key"]: new}
    monkeypatch.setattr(J, "publish_step", lambda *a, **k: pytest.fail("published without the dedupe step"))
    assert J.one(job, ctx, new["key"], "translated") == f"not taken: duplicate_of:{SHOP}:naver:1:11"


def test_a_closed_published_product_stays_in_the_index(tmp_path):
    new, old = record(2, 22, WILSON), E(1, 11, WILSON)
    job = dedupe_job(tmp_path, "on", [new])
    job.log(old["key"], "not_taken", reason="already_published")
    index = D.Index([old])
    assert J.dedupe_step(job, {"dedupe": index}, new["key"], new) == f"not taken: duplicate_of:{old['key']}"


def test_log_mode_keeps_out_of_the_index_what_on_mode_would_close(tmp_path):
    a, b = record(2, 22, WILSON), record(3, 33, WILSON)
    job = dedupe_job(tmp_path, "log", [a, b])
    index = D.Index([E(1, 11, WILSON)])
    J.dedupe_step(job, {"dedupe": index}, a["key"], a)
    assert a["key"] not in index.by_key


def test_a_resumed_product_is_read_from_the_records_of_the_run_start(tmp_path, monkeypatch):
    import run_transform
    new = record(2, 22, WILSON)
    job = dedupe_job(tmp_path, "on", [new])
    monkeypatch.setattr(run_transform, "latest_lines", lambda *a, **k: pytest.fail("collected tree read again"))
    ctx = {"dedupe": D.Index([E(1, 11, WILSON)]), "dedupe_records": {new["key"]: new}}
    assert J.dedupe_step(job, ctx, new["key"], None).startswith("not taken: duplicate_of:")


def test_log_mode_changes_nothing_but_the_event(tmp_path, collect_to_images):
    new = record(2, 22, WILSON)
    job = dedupe_job(tmp_path, "log", [new])
    collect_to_images["line"] = new
    with pytest.raises(ImagesReached):                                       # it goes on to its images
        J.one(job, _ctx(job, E(1, 11, WILSON)), new["key"], None)
    ev = job.events()[-1]
    assert ev["event"] == "duplicate_seen" and ev["decision"] == f"duplicate_of:{SHOP}:naver:1:11"
    assert ev["matches"][0]["confirmed"] and J.closed(job) == {}
    assert [e["event"] for e in job.events()] == ["collected", "duplicate_seen"]


def test_off_mode_does_not_look(tmp_path, collect_to_images, monkeypatch):
    new = record(2, 22, WILSON)
    job = dedupe_job(tmp_path, "off", [new])
    collect_to_images["line"] = new
    monkeypatch.setattr(J, "dedupe_step", lambda *a: pytest.fail("looked up with --dedupe off"))
    ctx = _ctx(job, E(1, 11, WILSON))
    assert "dedupe" not in ctx and "dedupe" not in job.meta
    with pytest.raises(ImagesReached):
        J.one(job, ctx, new["key"], None)
    assert [e["event"] for e in job.events()] == ["collected"]


def test_a_decided_product_is_not_looked_up_again_on_resume(tmp_path):
    new = record(2, 22, WILSON)
    job = dedupe_job(tmp_path, "log", [new])
    job.log(new["key"], "duplicate_seen", decision="duplicate_of:x", matches=[])
    assert J.dedupe_step(job, {"dedupe": D.Index([E(1, 11, WILSON)])}, new["key"], new) is None
    assert len(job.events()) == 1


def test_the_new_and_scroll_flag_is_kept_in_job_json_only_when_not_off(tmp_path):
    import argparse
    base = {"query": "q", "category": "50002787", "count": 0, "paid": False, "paid_variants": False, "reviews": 20,
            "exclude_known": False, "no_translate": True, "publish": False, "describe": False}
    off = J.new_scroll_job(argparse.Namespace(**base, dedupe="off"), SHOP, str(tmp_path / "s"), str(tmp_path / "j1"))
    on = J.new_scroll_job(argparse.Namespace(**base, dedupe="log"), SHOP, str(tmp_path / "s"), str(tmp_path / "j2"))
    assert "dedupe" not in off.meta and J.Job(on.folder).meta["dedupe"] == "log"


# ---- the replacement after publication -----------------------------------------------------------------------

class Admin:
    def __init__(self):
        self.calls = []

    def set_status(self, pid, status):
        self.calls.append((pid, status))
        return status


def _published_shop(tmp_path, old_variants, new_variants):
    import publish as PB
    old, new = f"{SHOP}:naver:1:11", f"{SHOP}:naver:2:22"
    shop_dir = tmp_path / "shops" / SHOP
    (shop_dir / "prepared").mkdir(parents=True)
    (shop_dir / "prepared" / "products.jsonl").write_text("".join(
        json.dumps({"key": k, "product": {"variants": [{}] * n}}) + "\n" for k, n in ((old, old_variants),
                                                                                    (new, new_variants))))
    shop = PB.Shop(SHOP, str(tmp_path / "shops"))
    for k, pid in ((old, "gid://old"), (new, "gid://new")):
        PB._append(shop.ledger_path, {"format": PB.FORMAT, "key": k, "status": "published", "product_id": pid})
    return shop, old, new


def test_the_old_product_is_withdrawn_once_the_better_one_is_published(tmp_path):
    shop, old, new = _published_shop(tmp_path, 4, 4)
    job = dedupe_job(tmp_path, "on", [record(2, 22, WILSON)])
    job.log(new, "duplicate_better", replaces=old, matches=[])
    admin = Admin()
    index = D.Index([E(1, 11, WILSON)])
    what = J.replace_step(job, {"publisher": (admin, None, {}), "dedupe": index}, shop, new)
    assert what == "; replaces 11 (withdrawn)" and admin.calls == [("gid://old", "DRAFT")]
    assert shop.withdrawn() == {old} and old not in index.by_key
    assert D.ledger(SHOP, str(tmp_path / "shops"))[old]["reason"] == f"replaced_by:{new}"
    assert job.events()[-1]["event"] == "replaced"
    assert J.replace_step(job, {"publisher": (admin, None, {})}, shop, new) == "" and len(admin.calls) == 1


def test_fewer_variants_keep_the_old_product(tmp_path):
    shop, old, new = _published_shop(tmp_path, 15, 1)                         # Prodi G: 1 against 15
    job = dedupe_job(tmp_path, "on", [record(2, 22, WILSON)])
    job.log(new, "duplicate_better", replaces=old, matches=[])
    admin = Admin()
    what = J.replace_step(job, {"publisher": (admin, None, {})}, shop, new)
    assert "kept: fewer variants (1 < 15)" in what and admin.calls == [] and shop.withdrawn() == set()
    assert job.events()[-1]["event"] == "replace_skipped"


def test_an_old_product_no_longer_published_is_not_touched(tmp_path):
    import publish as PB
    shop, old, new = _published_shop(tmp_path, 4, 4)
    PB._append(shop.ledger_path, {"key": old, "status": "withdrawn", "reason": "by hand"})
    job = dedupe_job(tmp_path, "on", [record(2, 22, WILSON)])
    job.log(new, "duplicate_better", replaces=old, matches=[])
    admin = Admin()
    assert "the old one is not published" in J.replace_step(job, {"publisher": (admin, None, {})}, shop, new)
    assert admin.calls == []


def test_publish_step_replaces_only_in_on_mode(tmp_path, monkeypatch):
    import publish as PB
    shop, old, new = _published_shop(tmp_path, 4, 4)
    monkeypatch.setattr("placement.run", lambda *a, **k: None)
    monkeypatch.setattr(PB.Shop, "ready", lambda self: [new])
    monkeypatch.setattr(PB, "publish_one", lambda shop, key, *a, **k: {"key": key, "status": "published",
                                                                       "handle": "h"})
    for mode, calls in (("log", 0), ("on", 1)):
        job = dedupe_job(tmp_path / mode, mode, [record(2, 22, WILSON)])
        job.meta["shops_root"] = str(tmp_path / "shops")
        job.shops_root = job.meta["shops_root"]
        job.log(new, "duplicate_better", replaces=old, matches=[])
        admin = Admin()
        J.publish_step(job, {"publisher": (admin, None, {})}, new)
        assert len(admin.calls) == calls


def test_two_agency_imports_with_one_long_title_are_one_product():
    """2026-11-15, the wedge pilot: sellers of one Lazrus set (19 title words alike, photos re-encoded, variants 0.64
    alike). Only two purchase agencies' imports; Korean sellers' titles alike stay unconfirmed (Wilson JGI sizes)."""
    title = "남성 또는 개인용 라즈러스 프리미엄 단조 골프 웨지 세트 - 50 52 54 56 58 60 64 72도 더 많은 스핀을 위한 밀드 페이스"

    def agency(rec):
        rec["specs"] = {"specs": [{"label": "원산지", "value": "미국(구매대행)"}]}
        return rec
    a = agency(record(1, 11, title, photos=("x",), values=[["52"], ["56"], ["60"]], category="50002783"))
    b = agency(record(2, 22, title, photos=("y",), values=[["50"], ["52"], ["54"]], category="50002783"))
    assert D.entry(a)["agency"] and D.confirm(D.entry(a), D.entry(b))
    plain_a = record(1, 11, title, photos=("x",), values=[["52"]], category="50002783")
    plain_b = record(2, 22, title, photos=("y",), values=[["50"]], category="50002783")
    assert not D.confirm(D.entry(plain_a), D.entry(plain_b))
    short = "라즈러스 웨지 세트"
    assert not D.confirm(D.entry(agency(record(1, 11, short, photos=("x",), values=[["52"]]))),
                         D.entry(agency(record(2, 22, short, photos=("y",), values=[["50"]]))))


def test_two_agency_imports_translated_apart_are_one_product():
    """2026-11-15, the wedge pilot: GoSports in five stores, the English title translated apart ("모래" / "샌드",
    "남성용" / "남성", "eAj" before it). The numbers, club kinds, hand, gender and bag keep versions apart."""
    def agency(name, channel):
        rec = record(channel, channel * 11, name, photos=(str(channel),), values=[[str(channel)]], category="50002783")
        rec["specs"] = {"specs": [{"label": "원산지", "value": "미국(구매대행)"}]}
        return D.entry(rec)
    a = agency("GoSports 불법 맥스 스핀 골프 웨지 세트 - 남성용 오른손잡이 모래, 롭, 갭 웨지", 1)
    b = agency("eAj GoSports 고스포츠 불법 맥스 스핀 골프 웨지 세트 - 남성 오른손 샌드 롭 갭", 2)
    assert D.possible(a, b) and D.confirm(a, b)
    for x, y in (("올리마르 ATS 주니어 남자 라임 블루 시리즈 개인 골프 클럽(3~5세) Right Hand Putter",
                  "올리마르 ATS 주니어 남자 라임 블루 시리즈 개인 골프 클럽(3~5세) Right Hand Hybrid"),
                 ("올리마르 ATS 주니어 남자 라임 블루 시리즈 개인 골프 클럽(3~5세) Right Hand Putter",
                  "올리마르 ATS 주니어 남자 라임 블루 시리즈 개인 골프 클럽(5~8세) Right Hand Putter"),
                 ("GoSports 불법 맥스 스핀 골프 웨지 세트 - 남성용 오른손잡이 모래, 롭, 갭 웨지",
                  "GoSports 불법 맥스 스핀 골프 웨지 세트 - 남성용 왼손잡이 모래, 롭, 갭 웨지"),
                 ("캘러웨이 워버드 남성용 골프채 풀세트 10개 캐디백 포함 일본 직구",
                  "캘러웨이 워버드 남성용 골프채 풀세트 10개 일본 직구 입문")):
        assert not D.alike(agency(x, 1), agency(y, 2)), (x, y)
    korean = record(2, 22, "eAj GoSports 고스포츠 불법 맥스 스핀 골프 웨지 세트 - 남성 오른손 샌드 롭 갭",
                    photos=("z",), values=[["z"]], category="50002783")
    assert not D.alike(a, D.entry(korean))                           # a Korean seller's title: never by words


def test_report_marks_the_members_joined_by_title_words_only_and_a_tie_keeps_more_variants():
    """2026-11-15, the store's old groups: BG-100 Black Edition joined the white sets by title words alone (no photo,
    no variant shared); the report marks such members to be looked at on their photos. A tie of grade and reviews
    keeps the copy with more variants (TaylorMade QI4D: 15 or 84 variants of one dealer's set)."""
    def agency(channel, name, photos, values):
        rec = record(channel, channel * 11, name, photos=photos, values=values, category="50002788")
        rec["specs"] = {"specs": [{"label": "원산지", "value": "일본(구매대행)"}]}
        return D.entry(rec, "published")
    white = agency(1, "브리지스톤 BG-100 남성용 골프채 풀세트 11개 캐디백", ("w",), [["S"], ["R"]])
    copy = agency(2, "브리지스톤 BG-100 남성용 골프채 풀세트 11개 캐디백", ("w",), [["S"], ["R"]])
    black = agency(3, "브리지스톤 남성용 BG-100 골프채 풀세트 11개 캐디백", ("k",), [["블랙S"], ["블랙R"]])
    [group] = D.groups([white, copy, black])
    assert len(group) == 3 and D.title_only(group) == [black["key"]]
    few = E(4, 44, "테일러메이드 QI4D 남성용 풀세트 (D+W+I) GF", values=[["a"]], photos=("q",))
    many = E(5, 55, "테일러메이드 QI4D 남성용 풀세트 (D+W+I) GF", values=[["a"], ["b"]], photos=("q",))
    assert [e["key"] for e in D.groups([few, many])[0]] == [many["key"], few["key"]]


def test_a_written_out_escape_is_no_number_of_the_title():
    """2026-11-15: Yamato LH01 13016883852 ("개별 u2013 단조") had the numbers 01 2013 52 56 60 and its copy
    13370261145 01 52 56 60: alike() never compared them."""
    a = E(1, 13016883852, "야마토 왼손잡이 골프 웨지 세트 52 56 60 및 개별 u2013 단조 CNC 밀드 LH01-52 56 60 Degree")
    assert a["numbers"] == "01 52 56 60" and "u2013" not in a["tkey"]


def test_every_photo_and_variant_alike_is_one_product_whatever_the_titles():
    """2026-11-15, the lenses: three published A11N SPORTS wedge sets, one under its model line 핀클리 (13405976594,
    13552318731, 13207840596): photos 1.0, variants black / bronze 1.0, titles too far apart for alike()."""
    same = dict(photos=("p1", "p2", "p3"), values=[["Black"], ["Bronze"]], price=205000, category="50002783")
    a = E(1100067303, 13405976594, "A11N SPORTS의 위조 골프 웨지 세트 Black", **same)
    b = E(102683547, 13552318731, "A11N SPORTS의 위조 골프 웨지 세트 db4P Bronze", **same)
    c = E(102783573, 13207840596, "핀클리 위조 골프 웨지 세트 3 u2013 52, 56, 60도, 밀드 페이스로 최대 스핀, 오른손", **same)
    assert D.strong(a, b) and D.strong(a, c) and D.possible(b, c) and D.confirm(b, c)
    assert [len(g) for g in D.groups([a, b, c])] == [3]


@pytest.mark.parametrize("x, y", [
    # versions of one photo and one variant list the titles keep apart: club kind, hand, gender, bag, numbers, model
    ("올리마르 ATS 주니어 라임 블루 시리즈 Right Hand Putter", "올리마르 ATS 주니어 라임 블루 시리즈 Right Hand Hybrid"),
    ("BombTech 골프 웨지 세트 52 56 60도 왼손잡이", "BombTech 골프 웨지 세트 52 56 60도 오른손잡이"),
    ("PGM 주니어 골프 클럽 완비 세트 Aged 3-5", "PGM 주니어 골프 클럽 완비 세트 Aged 9-12"),
    ("PGM 여성 골프채 풀세트 9종", "PGM 여성 골프채 풀세트 12종"),
    ("브리지스톤 BG-100 풀세트 캐디백 포함", "브리지스톤 BG-100 풀세트 캐디백 미포함"),
    ("[던롭코리아정품] 스릭슨 27ZXI-RKT 남성 풀세트 GF", "[던롭코리아정품] 스릭슨 27ZXI-RKT MAX 남성 풀세트 GF"),
    ("핑 G440 남성 풀세트", "핑 G440 여성 풀세트"),
])
def test_one_photo_and_variant_list_with_another_version_in_the_title_is_not_strong(x, y):
    same = dict(photos=("p",), values=[["a"], ["b"]], price=300000, category="50002787")
    assert not D.strong(E(1, 1, x, **same), E(2, 2, y, **same)), (x, y)


def test_strong_needs_the_category_most_photos_and_the_variants():
    a = E(1, 1, "주니어 골프채 6-8세", photos=("p", "q"), values=[["6-8세 퍼터"], ["6-8세 아이언"]])
    assert D.strong(a, E(2, 2, "어린이 골프 클럽 초등 6-8세", photos=("p", "q"), values=[["6-8세 퍼터"], ["6-8세 아이언"]]))
    assert D.strong(a, E(2, 2, "어린이 골프 클럽 초등", photos=("p", "q"), values=[["6-8세 퍼터"], ["6-8세 아이언"]]))
    assert not D.strong(a, E(2, 2, "어린이 골프 클럽", photos=("p", "z", "y"), values=[["6-8세 퍼터"], ["6-8세 아이언"]]))
    assert not D.strong(a, E(2, 2, "어린이 골프 클럽", photos=("p", "q"), values=[["9-12세 퍼터"], ["9-12세 아이언"]]))
    assert not D.strong(a, E(2, 2, "어린이 골프 클럽", photos=("p", "q"), values=[["6-8세 퍼터"], ["6-8세 아이언"]],
                             category="50002788"))
