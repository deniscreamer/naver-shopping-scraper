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
    assert D.signals(new, old) == {"first_photo": False, "photos": 0.5, "variants": 0.0, "sold_equal": False,
                                   "confirmed": True}
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


def test_load_reads_the_ledger_and_keeps_what_was_replaced_leading_to_its_replacement(tmp_path):
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
                                                                 keys[2]: "replaced", keys[4]: "job"}
    assert index.replaced == {keys[2]: keys[0]} and index.live(keys[2]) == (keys[0], index.by_key[keys[0]])
    assert set(D.load(SHOP, str(tmp_path), withdrawn=False, records=recs).by_key) == {keys[0]}   # --report: the store


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


def test_pairs_lists_same_upc_hold_candidates_without_a_title_match():
    # 2026-11-17, the W7 review: a same-UPC hold candidate has no title match, yet the pilot's sheets must show it
    m = {"key": "k-t", "status": "published", "confirmed": False}
    events = [{"key": "k1", "event": "duplicate_seen", "decision": "same_upc:k-a", "same_upc": ["k-a", "k-b"],
               "upc": ["792713116504"], "matches": []},
              {"key": "k2", "event": "duplicate_seen", "decision": "same_upc:k-t", "same_upc": ["k-t"], "matches": [m]}]
    rows = D.pairs(events)
    assert [(r["n"], r["candidate"], r["key"], r["decision"], r["status"], r["confirmed"]) for r in rows] == [
        (1, "k1", "k-a", "same_upc:k-a", "", False), (2, "k1", "k-b", "same_upc:k-b", "", False),
        (3, "k2", "k-t", "same_upc:k-t", "published", False)]   # a title match sharing the UPC: one row


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
    assert shop.withdrawn() == {old} and index.by_key[old]["status"] == "replaced" and index.live(old)[0] == new
    assert D.ledger(SHOP, str(tmp_path / "shops"))[old]["reason"] == f"replaced_by:{new}"
    assert job.events()[-1]["event"] == "replaced"
    assert J.replace_step(job, {"publisher": (admin, None, {})}, shop, new) == "" and len(admin.calls) == 1


def test_a_later_copy_of_the_product_just_replaced_in_the_same_job_is_a_copy_of_its_replacement(tmp_path):
    """The reviewer's gap inside one job (2026-11-16): A (old title, old photos) replaced by B; a later seller C that
    matches A only (B has its own photos and another title) must not come out as new."""
    shop, old, new = _published_shop(tmp_path, 4, 4)
    later = record(3, 33, WILSON, photos=("a", "b", "c"))
    job = dedupe_job(tmp_path, "on", [record(2, 22, WILSON), later])
    job.log(new, "duplicate_better", replaces=old, matches=[])
    index = D.Index([E(1, 11, WILSON), E(2, 22, "윌슨 프로필 JGI 주니어 세트 다른 이름", photos=("n1", "n2"),
                                         values=[["x"]], grade="POWER")])
    assert J.replace_step(job, {"publisher": (Admin(), None, {}), "dedupe": index}, shop, new).startswith("; replaces")
    assert J.dedupe_step(job, {"dedupe": index}, later["key"], later) == f"not taken: duplicate_of:{new}"
    plain = D.Index([E(2, 22, "윌슨 프로필 JGI 주니어 세트 다른 이름", photos=("n1", "n2"), values=[["x"]])])
    assert plain.decide(D.entry(later))["decision"] is None                    # the gap with drop(old)


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


def test_a_draft_does_not_replace_a_live_product_and_activate_prints_its_withdraw_line(tmp_path, capsys):
    """Draft first, 2026-11-16: the old one stays live until the new one is activated, then the owner withdraws it."""
    import publish as PB
    shop, old, new = _published_shop(tmp_path, 4, 4)
    PB._append(shop.ledger_path, {"format": PB.FORMAT, "key": new, "status": "published", "product_id": "gid://new",
                                  "store_status": "DRAFT"})
    job = dedupe_job(tmp_path, "on", [record(2, 22, WILSON)])
    job.log(new, "duplicate_better", replaces=old, matches=[])
    admin = Admin()
    what = J.replace_step(job, {"publisher": (admin, None, {})}, shop, new)
    assert what == "; 11 kept: the new one is a draft" and admin.calls == []
    assert job.events()[-1]["why"] == J.DRAFT_WHY
    assert J.withdraw_lines(job) == [f".venv/bin/python scripts/publish.py {SHOP} --withdraw {old} "
                                     f"--reason replaced_by:{new}"]


def test_a_draft_replaces_a_draft(tmp_path):
    import publish as PB
    shop, old, new = _published_shop(tmp_path, 4, 4)
    for k, pid in ((old, "gid://old"), (new, "gid://new")):
        PB._append(shop.ledger_path, {"format": PB.FORMAT, "key": k, "status": "published", "product_id": pid,
                                      "store_status": "DRAFT"})
    job = dedupe_job(tmp_path, "on", [record(2, 22, WILSON)])
    job.log(new, "duplicate_better", replaces=old, matches=[])
    admin = Admin()
    assert J.replace_step(job, {"publisher": (admin, None, {})}, shop, new) == "; replaces 11 (withdrawn)"
    assert admin.calls == [("gid://old", "DRAFT")]


def test_a_draft_is_in_the_duplicates_index_as_published(tmp_path):
    import publish as PB
    shop, old, new = _published_shop(tmp_path, 4, 4)
    PB._append(shop.ledger_path, {"format": PB.FORMAT, "key": old, "status": "published", "product_id": "gid://old",
                                  "store_status": "DRAFT"})
    assert D.ledger_status(D.ledger(SHOP, str(tmp_path / "shops"))[old]) == "published"


# ---- a copy of a replaced product (2026-11-16, the owner's wedge review) ---------------------------------------

GOSPORTS = "GoSports 불법 맥스 스핀 골프 웨지 세트 - 남성용 오른손잡이 모래, 롭, 갭 웨지, 브러시드 스테인리스"
GOSPORTS_LIVE = "GoSports Illegal Max Spin 골프 웨지 세트 - 남성용 오른손잡이용 샌드, 롭, 갭 웨지, 브러시드 스테인리스"


def _gosports():
    """The real chain: 13619939279 replaced by 13379851400, replaced by 12918511112 (live); 12557420063 matches the
    first two (one title, one photo) and not the live one (its own photos, another translation)."""
    w = dict(photos=("2e53b0", "f09d35", "431100"), values=[], price=205470, category="50002783")
    first = E(102773407, 13619939279, GOSPORTS, status="replaced", **w)
    second = E(102683334, 13379851400, GOSPORTS, grade="SPROUT", status="replaced", **{**w, "price": 212040})
    live = E(102781427, 12918511112, GOSPORTS_LIVE, photos=("live1", "live2"), values=[], price=192870,
             category="50002783")
    copy = E(102770910, 12557420063, GOSPORTS, status="job", **{**w, "price": 199080})
    index = D.Index([live])
    index.replace(first["key"], second["key"], first)
    index.replace(second["key"], live["key"], second)
    return index, first, second, live, copy


def test_a_copy_of_a_replaced_product_is_a_copy_of_its_live_replacement():
    """Job fairwardgolf-50002783-20261116T083154Z published 12557420063 as new: its match 13619939279 (not taken
    against it the day before) had been withdrawn as replaced_by: and dropped out of the index."""
    index, first, second, live, copy = _gosports()
    assert D.Index([live]).decide(copy)["decision"] is None                     # the gap: the live one alone
    d = index.decide(copy)
    assert d["decision"] == "duplicate_of" and d["of"] == live["key"]
    assert {(m["key"], m["status"], m["live"]) for m in d["matches"] if m["confirmed"]} == {
        (first["key"], "replaced", live["key"]), (second["key"], "replaced", live["key"])}


def test_a_better_copy_of_a_replaced_product_replaces_the_live_one():
    index, first, second, live, copy = _gosports()
    d = index.decide({**copy, "grade": "POWER"})
    assert d["decision"] == "duplicate_better" and d["of"] == live["key"]     # job.py withdraws the live one


def test_a_copy_of_a_replaced_product_held_by_the_owner_is_never_taken():
    """A11N 13512885159 matched 13405976594, replaced by 13552318731; a chain ending at a hold: (or any owner's
    withdrawal) blocks its copies as the held product itself does."""
    same = dict(values=[["Black"], ["Bronze"]], price=199350, category="50002783")
    old = E(1100067303, 13405976594, "A11N SPORTS의 위조 골프 웨지 세트 Black", status="replaced",
            photos=("85a6d8", "de2b09", "b59c45"), **same)
    held = E(102683547, 13552318731, "A11N SPORTS의 위조 골프 웨지 세트 db4P Bronze", status="withdrawn",
             photos=("85a6d8", "de2b09", "b59c45"), **{**same, "price": 187830})
    copy = E(1100013105, 13512885159, "A11N SPORTS의 위조 골프 웨지 세트 Black", status="job",
             photos=("e0a554", "3d2479", "9679ef"), **{**same, "price": 211330})
    index = D.Index([held])
    index.replace(old["key"], held["key"], old)
    for c in (copy, {**copy, "grade": "PLATINUM", "reviews": 900}):
        d = index.decide(c)
        assert d["decision"] == "duplicate_of_withdrawn" and d["of"] == held["key"]


def test_a_chain_ending_outside_the_index_never_lets_a_copy_through():
    index, first, second, live, copy = _gosports()
    index.drop(live["key"])                                   # published with no collected record, or dropped
    d = index.decide({**copy, "grade": "PLATINUM"})
    assert d["decision"] == "duplicate_of" and d["of"] == live["key"]


def test_the_live_product_is_no_copy_of_its_own_replaced_copies_and_a_cycle_ends():
    index, first, second, live, copy = _gosports()
    same_as_first = {**live, "first": first["first"], "shas": first["shas"], "tkey": first["tkey"],
                     "words": first["words"], "numbers": first["numbers"]}
    assert index.decide(same_as_first)["decision"] is None                   # re-collected live one: itself
    loop = D.Index()
    loop.replace("a", "b")
    loop.replace("b", "a")
    assert loop.live("a") == ("b", None)


def test_a_replaced_product_that_only_shares_the_title_is_not_followed():
    """Not confirmed (an ordinary product, other photos and variants): listed, no decision."""
    index, first, second, live, copy = _gosports()
    other = {**copy, "agency": False, "first": "zz", "shas": {"zz"}, "key": f"{SHOP}:naver:7:7", "channel": "7"}
    d = index.decide(other)
    assert d["decision"] is None and d["matches"] and not any(m["confirmed"] for m in d["matches"])


def test_index_replace_after_a_job_replacement_keeps_the_old_one_leading_to_the_new():
    old, new = E(1, 1, WILSON), E(2, 2, WILSON, photos=("n1", "n2"), values=[["x"]], grade="POWER")
    index = D.Index([old, new])
    index.replace(old["key"], new["key"])
    assert index.by_key[old["key"]]["status"] == "replaced"
    d = index.decide(E(3, 3, WILSON, status="job"))                      # matches only old: a copy of new
    assert d["decision"] == "duplicate_of" and d["of"] == new["key"]


# ---- one listing copied by resellers (same_listing, 2026-11-16) --------------------------------------------------

LAZRUS_PHOTOS = ("ce3147", "f694c5", "72bc4c")
LAZRUS_SETS = [["Black Right Handed", "RH Black 50 54 58 Set"], ["Black Right Handed", "RH Black 52 56 60 Set"],
               ["Silver Right Handed", "RH Silver 52 56 60 Set"]]


def _lazrus(channel, pid, name, singles, **k):
    return E(channel, pid, name, photos=LAZRUS_PHOTOS, values=LAZRUS_SETS + singles, category="50002783", **k)


def lazrus():
    """The real three (2026-11-16): one photo set byte for byte, the same 3 sets sold, other single wedges listed."""
    return (
        _lazrus(102329146, 13016648376, "남성 또는 개인용 라즈러스 프리미엄 단조 골프 웨지 세트 - 50 52 54 56 58",
                [["Black Right Handed", "RH Black 52 Degree"], ["Silver Right Handed", "RH Silver 52 Degree"],
                 ["Silver Right Handed", "RH Silver 56 Degree"], ["Silver Right Handed", "RH Silver 60 Degree"]],
                price=312930),
        _lazrus(102651580, 12079160628, "남성용 LAZRUS 프리미엄 단조 골프 웨지 세트 - 52, 56, 60도 웨지 + 더 많은 스핀을 위한 "
                "밀링 페이스 - 훌륭한 골프 선물",
                [["Black Left Handed", "LH Black 52 Degree"], ["Black Right Handed", "RH Black 52 Degree"],
                 ["Silver Right Handed", "RH Silver 52 Degree"], ["Silver Right Handed", "RH Silver 56 Degree"]],
                price=299880),
        _lazrus(102770910, 12557380462, "남성 또는 개인용 라즈러스 프리미엄 단조 골프 웨지 세트 - 50 52 54 56 58 60 64 72도 + "
                "더 많은 스핀을 위한 밀드 페이스 훌륭한 선물",
                [["Black Left Handed", "LH Black 52 Degree"], ["Black Right Handed", "RH Black 52 Degree"],
                 ["Black Right Handed", "RH Black 56 Degree"], ["Black Right Handed", "RH Black 64 Degree"],
                 ["Black Right Handed", "RH Black 72 Degree"], ["Silver Right Handed", "RH Silver 52 Degree"],
                 ["Silver Right Handed", "RH Silver 56 Degree"], ["Silver Right Handed", "RH Silver 60 Degree"]],
                price=290070))


def test_resellers_of_one_listing_are_one_product_whatever_their_titles_list():
    a, b, c = lazrus()
    assert a["sold"] == b["sold"] == c["sold"] and len(a["sold"]) == 3        # the single wedges are not sold
    for x, y in ((a, b), (a, c), (b, c)):
        assert D.signals(x, y)["variants"] < D.VARIANTS_JACCARD and not D.alike(x, y)   # the gap before
        assert D.same_listing(x, y) and D.strong(x, y) and D.possible(x, y) and D.confirm(x, y)
    assert [len(g) for g in D.groups([a, b, c])] == [3]
    assert D.title_only(D.groups([a, b, c])[0]) == []


def test_the_sold_variants_keep_single_clubs_outside_a_sets_only_category():
    a = E(1, 1, "x", values=LAZRUS_SETS + [["Black Right Handed", "RH Black 52 Degree"]], category="50002787")
    assert len(a["sold"]) == 4
    other_shop = D.entry({**record(1, 1, "x", values=LAZRUS_SETS + [["Black", "52 Degree"]], category="50002783"),
                          "key": "othershop:naver:1:1"})
    assert len(other_shop["sold"]) == 4                                         # no rules for that shop: all sold


@pytest.mark.parametrize("change", ["order", "one_photo", "two_photos", "sold", "no_variants", "colour"])
def test_one_listing_needs_its_lead_photos_in_order_and_the_same_variants_sold(change):
    a, b, _ = lazrus()
    if change == "order":
        b = {**b, "lead": (LAZRUS_PHOTOS[1], LAZRUS_PHOTOS[0], LAZRUS_PHOTOS[2])}
    elif change == "one_photo":
        b = {**b, "lead": LAZRUS_PHOTOS[:2] + ("other",), "shas": set(LAZRUS_PHOTOS[:2]) | {"other"}}
    elif change == "two_photos":
        a, b = ({**e, "lead": LAZRUS_PHOTOS[:2], "shas": set(LAZRUS_PHOTOS[:2])} for e in (a, b))
    elif change == "sold":                                                     # Wilson JGI sizes: another size set
        b = {**b, "sold": b["sold"] - {sorted(b["sold"])[0]}}
    elif change == "no_variants":
        a, b = ({**e, "sold": frozenset()} for e in (a, b))
    else:                                                                       # a colour edition: its own variants
        b = {**b, "sold": frozenset({"blackedition/rhblack525660set"})}
    assert not D.same_listing(a, b) and not D.strong(a, b)


@pytest.mark.parametrize("x, y", [
    # one listing's photos and variants, and the titles still name another product: kind, hand, numbers the
    # variants do not spell out, a model word
    ("올리마르 ATS 주니어 라임 블루 시리즈 Right Hand Putter", "올리마르 ATS 주니어 라임 블루 시리즈 Right Hand Hybrid"),
    ("BombTech 골프 웨지 세트 52 56 60도 왼손잡이", "BombTech 골프 웨지 세트 52 56 60도 오른손잡이"),
    ("PGM 주니어 골프 클럽 완비 세트 Aged 3-5", "PGM 주니어 골프 클럽 완비 세트 Aged 9-12"),
    ("PGM 여성 골프채 풀세트 9종", "PGM 여성 골프채 풀세트 12종"),
    ("[던롭코리아정품] 스릭슨 27ZXI-RKT 남성 풀세트 GF", "[던롭코리아정품] 스릭슨 27ZXI-RKT MAX 남성 풀세트 GF"),
])
def test_one_listing_with_another_version_in_the_title_is_not_strong(x, y):
    same = dict(photos=("p1", "p2", "p3"), values=[["a"], ["b"]], price=300000, category="50002787")
    a, b = E(1, 1, x, **same), E(2, 2, y, **same)
    assert a["lead"] == b["lead"] and a["sold"] == b["sold"]
    assert not D.strong(a, b), (x, y)


def test_a_title_naming_the_listing_first_variant_is_the_same_listing():
    """PGM 13274024476 "Aged 9-12" and 13390550850 "Aged 3-5" (2026-11-16): the same 9 variants list every age, the
    same photos; the numbers are the variants'."""
    values = [[f"Aged {a}", c] for a in ("3-5", "6-8", "9-12") for c in ("Black", "Pink", "Yellow")]
    same = dict(photos=("p1", "p2", "p3"), values=values, category="50002787")
    a = E(102783573, 13274024476, "어린이용 PGM 주니어 골프 클럽 완비 세트, 스탠드 백이 있는 5개, 소년 및 소녀용 헤드 커버 "
          "2개, 오른손 Aged 9-12 Black", price=330210, **same)
    b = E(102682315, 13390550850, "eAj 용 PGM 주니어 골프 클럽 완비 세트, 스탠드 백이 있는 골프 클럽 5개, 소년 및 소녀용 "
          "헤드 커버 2개, 오른손 Aged 3-5 Black", price=318870, **same)
    assert D.same_listing(a, b) and D.strong(a, b)
    a0, b0 = ({**e, "vnums": set()} for e in (a, b))
    assert not D.same_listing(a0, b0)                       # numbers no variant spells out: Aged 9-12 / Aged 3-5


@pytest.mark.parametrize("x, y", [
    # the real pair (2026-11-16, 50002788): the variants "7irons(6-9.pw...)" spell 9 and 7, the titles count 10 and 9
    ("미즈노 JPX QII 풀세트 여성 조합 골프채 10개 드라이버 유틸리티 7아이언", "미즈노 여성 풀세트 JPX QII 카본 골프채 9개 세트 미즈노코리아"),
    ("PGM 여성 골프채 풀세트 9종", "PGM 여성 골프채 풀세트 12종"),
    ("PGM 여성 골프채 9pcs 세트", "PGM 여성 골프채 12 pcs 세트"),
])
def test_a_count_in_the_title_is_its_own_even_when_a_variant_writes_the_number(x, y):
    values = [["11.5도L", "4번22도L", "7irons(6-9.PW.PS.PS)카본L"], ["11.5도L", "5번25도L", "7irons(6-9.PW.PS.PS)카본L"],
              ["12종 풀세트"]]
    same = dict(photos=("p1", "p2", "p3"), values=values, price=1450000, category="50002788")
    a, b = E(500004615, 13826383159, x, **same), E(500020721, 13826377851, y, **same)
    assert a["lead"] == b["lead"] and a["sold"] == b["sold"]
    assert not D.same_listing(a, b) and not D.strong(a, b), (x, y)


def test_a_count_both_titles_share_does_not_part_one_listing():
    """PGM 13274024476 / 13390550850 both write "5개" and "2개": the same counts, one listing still."""
    values = [[f"Aged {a}", c] for a in ("3-5", "6-8", "9-12") for c in ("Black", "Pink")]
    same = dict(photos=("p1", "p2", "p3"), values=values, category="50002787", price=330210)
    a = E(1, 1, "PGM 주니어 골프 클럽 완비 세트, 골프 클럽 5개, 헤드 커버 2개, 오른손 Aged 9-12 Black", **same)
    b = E(2, 2, "PGM 주니어 골프 클럽 완비 세트, 골프 클럽 5개, 헤드 커버 2개, 오른손 Aged 3-5 Black", **same)
    assert a["counts"] == b["counts"] == {"5", "2"} and D.same_listing(a, b)


def test_a_copy_of_a_replaced_product_priced_apart_from_the_live_end_is_not_followed():
    """The price guard holds against the live end as at step 1: a copy priced like the replaced product but x2.5 the
    live one is not its copy; x1.5 is (13826709716 at 44,000 KRW and its live end 13623397378 at 26,160: x1.68)."""
    index, first, second, live, copy = _gosports()
    far = {**copy, "price": int(live["price"] * 2.5)}
    first_far = {**first, "price": far["price"]}
    index.add(first_far)                                       # the replaced one priced near the copy
    d = index.decide(far)
    assert d["decision"] is None
    assert any(m.get("live_price") is False for m in d["matches"] if m["key"] == first["key"])
    near = {**copy, "price": int(live["price"] * 1.5)}
    assert index.decide(near)["decision"] == "duplicate_of"


def test_club_slot_axes_count_each_loft_as_transform_does():
    """TaylorMade MG5 "52.09 SB" on 옵션 1 and 옵션 2 (club slots): the variant is two clubs, sold in a sets_only
    category; on other axes the same loft twice is one club (left out)."""
    line = record(1, 1, "테일러메이드 MG5 웨지 세트", values=[["52.09 SB", "56.12 SB"], ["52.09 SB", "52.09 SB"]],
                  category="50002783")
    slots = {**line, "specs": {"options": {"option_groups": [{"name": "옵션 1"}, {"name": "옵션 2"}]}}}
    other = {**line, "specs": {"options": {"option_groups": [{"name": "Size"}, {"name": "Style Name"}]}}}
    assert len(D.entry(slots)["sold"]) == 2 and len(D.entry(other)["sold"]) == 1


# ---- 2026-11-17, the wedge review (W7): the spaced key, sold sets of agency imports, UPC ------------------------

def _agency(rec, upc=None):
    """A purchase-agency import (구매대행) whose description copies the Amazon table's UPC row."""
    rec["specs"] = {"specs": [{"label": "원산지", "value": "미국(구매대행)"}]}
    if upc:
        rec["details"] = {"description": {"text": f"Brand Name | Majek\nUPC | {upc}\nGolf Club Type | Wedge"}}
    return rec


MIURA_VALUES = [["2개(52Y,56Y)"], ["3개(50Y,54Y,58C)"], ["3개(52Y,56Y,60C)"]]


def test_hangul_words_spaced_apart_and_an_importer_word_keep_no_copy_apart():
    """C43: Miura Forged Black QPQ 11585620683 / 11585678496 (variants 1.0, photos 0.75, both 1,360,000 KRW): the titles
    differ only by '샤프트 선택' / '샤프트선택' and '미우라코리아' (its brand 미우라 is in the title)."""
    a = E(101434385, 11585620683, "미우라 포지드 웨지 블랙 QPQ (2개세트) + 샤프트선택 미우라코리아", grade="PREMIUM",
          price=1360000, photos=("m1", "m2", "m3", "m4"), values=MIURA_VALUES, category="50002783")
    b = E(100246487, 11585678496, "미우라 포지드 웨지 블랙 QPQ 2개세트 샤프트 선택", grade="POWER", price=1360000,
          photos=("m1", "m2", "m3", "x4"), values=MIURA_VALUES, category="50002783", status="job")
    assert a["tkey"] != b["tkey"] and a["skey"] == b["skey"]
    assert D.possible(b, a) and D.confirm(b, a) and not D.strong(b, a)
    assert D.Index([a]).decide(b)["decision"] == "duplicate_of"
    assert [len(g) for g in D.groups([a, b])] == [2]


@pytest.mark.parametrize("x, y", [
    # joined across a digit '(3~5세)' would be '35세': Olimar ATS left-hand putters of two ages
    ("올리마르 ATS 주니어 남자 라임 / 블루 시리즈 개인 골프 클럽35세 Left Hand Putter",
     "올리마르 ATS 주니어 남자 라임 / 블루 시리즈 개인 골프 클럽(3~5세) Left Hand Putter"),
    # 던롭코리아 without 던롭 in the title stays a word (Cleveland 588 13622282055 / 13523037432)
    ("[던롭코리아] 클리브랜드 리미티드 에디션 588 투어 액션 웨지 세트", "클리브랜드 리미티드 에디션 588 투어 액션 웨지 세트"),
])
def test_the_spaced_key_never_joins_across_a_digit_nor_drops_an_importer_without_its_brand(x, y):
    assert D.spaced_key(x, "1") != D.spaced_key(y, "1")


def test_the_spaced_key_joins_hangul_neighbours_only():
    assert D.spaced_key("샤프트 선택 2개세트", "1") == D.spaced_key("샤프트선택 2개세트", "1") == "1|2개세트 샤프트선택"
    assert D.spaced_key("미우라 웨지 미우라코리아", "1") == "1|미우라웨지"
    assert D.spaced_key("!!!", "1") is None


PRON_TITLES = ("일본 프로니즈 웨지 세트 또는 싱글 남성 골프 클럽", "일본 프로니즈 웨지 세트 싱글 남성 골프 클럽")
PRON_A = [["50 54 58 Degree Legal", "2 Pearl 3 Club Pro Steel"], ["50 Degree Legal", "3 Sliver Traditional Stee"],
          ["52 56 60 Degree Legal", "2 Pearl 3 Club Pro Steel"], ["54 Degree Legal", "1 Black Professional Stee"],
          ["56 Degree Legal", "1 Black Professional Stee"], ["58 Degree Legal", "1 Black Professional Stee"]]
PRON_B = [["50 54 58 Degree Legal", "2 Pearl 3 Club Pro Steel"], ["52 56 60 Degree Legal", "2 Pearl 3 Club Pro Steel"],
          ["54 Degree Legal", "1 Professional Steel Shaf"], ["56 Degree Legal", "1 Professional Steel Shaf"],
          ["58 Degree Legal", "1 Professional Steel Shaf"]]


def _pron():
    a = _agency(record(1100067303, 13408226321, PRON_TITLES[0], price=298530, photos=("p1", "p2", "p3", "p4"),
                       values=PRON_A, category="50002783"))
    b = _agency(record(102786034, 13566632407, PRON_TITLES[1], price=336870, photos=("q1", "q2", "q3"),
                       values=PRON_B, category="50002783"))
    return a, b


def test_two_agency_imports_selling_the_same_sets_are_confirmed_in_a_job():
    """C41 part 1: pron 13408226321 / 13566632407, duplicate_seen not_confirmed before (variants 0.22 over the page
    list), the sets sold equal ('50 54 58 Degree Legal', '52 56 60 Degree Legal'): one product in the job as in --report."""
    a, b = (D.entry(r) for r in _pron())
    old = {**a, "status": "published"}
    s = D.signals(b, old)
    assert s["variants"] < D.VARIANTS_JACCARD and not s["first_photo"] and s["sold_equal"] and s["confirmed"]
    assert D.Index([old]).decide(b)["decision"] == "duplicate_of"
    korean = [D.entry(record(*r["key"].split(":")[2:], PRON_TITLES[i], values=PRON_A if i == 0 else PRON_B,
                             category="50002783")) for i, r in enumerate(_pron())]
    assert not D.signals(*korean)["sold_equal"]                        # Korean sellers: never by the sets sold
    other = D.entry({**_pron()[1], "key": "othershop:naver:102786034:13566632407"})
    assert not D.sold_equal(a, other)                                  # no sets_only rules for that shop


def test_the_sets_sold_set_aside_the_numbers_they_spell_in_alike():
    """C41 part 2: AM20XX 13016628843 / 13363498942, titles '50/52/54/56/58' / '50/52/54/56/58/60도', the same two sets
    sold ('50 54 58 Degree Set', '52 56 60 Degree Set'): alike once the numbers the sets spell out are set aside."""
    values = [["50 54 58 Degree Set"], ["50 Degree"], ["52 56 60 Degree Set"], ["52 Degree"], ["54 Degree"],
              ["56 Degree"], ["58 Degree"], ["60 Degree"]]
    a = D.entry(_agency(record(102329146, 13016628843, "더 많은 스핀을 위한 골프 샌드 웨지 프리미엄 세트 또는 개별 "
                               "50/52/54/56/58 50 54 58 Degree Set", photos=("a1", "a2", "a3"), values=values,
                               category="50002783", price=190350)))
    b = D.entry(_agency(record(102683334, 13363498942, "eAj 더 많은 스핀을 위한 골프 샌드 웨지 프리미엄 골프 웨지 세트 "
                               "또는 개별 50/52/54/56/58/60도 밀링 페이스 50 54 58 Degree Set",
                               photos=("b1", "b2", "b3"), values=values, category="50002783", price=233820)))
    assert a["numbers"] != b["numbers"] and a["sold"] == b["sold"]
    assert D.alike(a, b) and D.possible(a, b) and D.confirm(a, b)
    other = {**b, "sold": frozenset({"505458degreeset"})}             # another set sold: the numbers count again
    assert not D.alike(a, other)


def test_one_agency_family_selling_other_sets_stays_apart():
    """C41 part 2's limit: Pinkley 13566628089 '... 옵션 1' (Color: 옵션 1 / Bronze) and 13261529837 '... Black'
    (Black / Bronze): sold 0.33 alike, the numbers are not set aside."""
    a = D.entry(_agency(record(102786034, 13566628089, "핀클리 위조 골프 웨지 세트 3 52 56 60도 밀드 페이스로 스핀 "
                               "오른손 옵션 1", values=[["옵션 1"], ["Bronze"]], category="50002783")))
    b = D.entry(_agency(record(102748022, 13261529837, "핀클리 위조 골프 웨지 세트 3 – 52, 56, 60도, 밀드 페이스로 최대 "
                               "스핀, 오른손 Black", values=[["Black"], ["Bronze"]], category="50002783")))
    assert not D.alike(a, b) and not D.sold_equal(a, b) and not D.upc_suspect(a, b)


MAJEK_SENIOR = ("마젝 골프 시니어 남자 완비 웨지 세트 52 갭 웨지GW 56 샌드 웨지SW 60",
                "마젝 골프 샌드 52 GW LW 60 시니어 오른손잡이 세트 남자 웨지 SW 56 완비")


def _majek(upc_b="792713117044", photos_b=("j1", "j2", "j3"), values_b=(), title_b=MAJEK_SENIOR[1]):
    a = D.entry(_agency(record(102329146, 13018098465, MAJEK_SENIOR[0], price=194130, photos=("j1", "j2", "j3"),
                               values=[], category="50002783"), "792713117044"), "published")
    b = D.entry(_agency(record(1100071177, 13312218924, title_b, price=186660, photos=photos_b,
                               values=list(values_b), category="50002783"), upc_b), "job")
    return a, b


def test_no_variants_every_photo_and_one_upc_is_one_listing():
    """C40: Majek Senior 13018098465 / 13312218924, the title shuffled by seller 1100071177, no variants, the same 3
    photos, UPC 792713117044 in the description's Amazon table: strong (no variants, so neither the variants path nor
    same_listing could say it)."""
    a, b = _majek()
    assert a["upc"] == {"792713117044"} and a["tkey"] != b["tkey"] and not D.alike(a, b)
    assert D.same_upc_listing(a, b) and D.strong(a, b) and D.possible(b, a) and D.confirm(b, a)
    assert D.Index([a]).decide(b)["decision"] == "duplicate_of"


@pytest.mark.parametrize("change", ["other_upc", "kind", "variants", "two_photos", "photo"])
def test_no_variants_and_one_photo_set_without_one_upc_is_no_listing(change):
    """C40's limits: Majek women 792713116382 / senior 792713117044 share one photo set (the title's lofts 52/56/60 do
    not tell them apart); Olimar ATS Iron / Putter 810022120200 (the agency copied the parent's UPC); variants on one
    side; fewer than LEAD_PHOTOS photos; one photo not shared."""
    if change == "other_upc":
        a, b = _majek(upc_b="792713116382", title_b="여성용 골프 웨지 세트 52 56 60도 갭 샌드 롭 웨지 구성 오른손잡이용")
    elif change == "kind":                                             # the kinds are strong()'s own check
        a, b = _majek(title_b="마젝 골프 샌드 52 GW LW 60 시니어 오른손잡이 세트 남자 퍼터 SW 56 완비 Putter")
        a = {**a, "words": a["words"] | {"iron"}}
        assert D.same_upc_listing(a, b) and not D.strong(a, b)
        return
    elif change == "variants":
        a, b = _majek(values_b=[["52 56 60"]])
    elif change == "two_photos":
        a, b = _majek(photos_b=("j1", "j2"))
        a = {**a, "shas": {"j1", "j2"}}
    else:
        a, b = _majek(photos_b=("j1", "j2", "zz"))
    assert not D.same_upc_listing(a, b) and not D.strong(a, b)


def test_one_upc_under_titles_that_agree_is_a_hold_candidate_never_a_decision():
    """C39: one UPC, the photos not all shared (so not strong), no title match: decide() gives no decision and names
    the product for a hold (same_upc); the report lists it apart from the groups."""
    a, b = _majek(photos_b=("j1", "z2", "z3", "z4"))
    assert not D.possible(b, a) and D.upc_suspect(b, a)
    d = D.Index([a]).decide(b)
    assert d["decision"] is None and d["same_upc"] == [a["key"]] and d["upc"] == ["792713117044"]
    assert D.same_upc_groups([a, b], []) and not D.groups([a, b])
    first = _majek(photos_b=("j1", "z2", "z3", "z4"))[1]               # first photo shared: confirmed, not possible
    assert D.signals(first, a)["confirmed"] and D.Index([a]).decide(first)["decision"] is None
    assert D.Index([a]).decide({**b, "upc": set()}) == {"decision": None, "of": None, "matches": []}


@pytest.mark.parametrize("x, y, upc", [
    # Hireko / Professional Open 690: a 4-piece set and a 3-piece set share the parent's UPC
    ("Hireko 웨지 프로페셔널 오픈 690 골프 시리즈 세트 개별 5256606468 4-Piece Set 52/56/60/64",
     "프로페셔널 오픈 690 골프 웨지 세트 5256606468 3Piece Set 525660 Right", "810022123058"),
    # BombTech Silver / Black share 850064238204
    ("BombTech - 프리미엄 골프 웨지 세트 52 56 60도 스핀 증가를 위한 Max Silver",
     "골프 웨지 BombTech - 프리미엄 세트 52도 56도 60도 최대 그루브로 스핀 증가 블랙", "850064238204"),
    # Olimar ATS junior Iron / Putter share 810022120200; a title naming no club is no kind
    ("올리마르 주니어 옐로우 시리즈 개인 골프 클럽 세 이하 Iron", "올리마르 ATS 주니어 옐로우 시리즈 개인 골프 클럽(3세 이하) Putter",
     "810022120200"),
    ("올리마르 ATS 주니어 옐로우 시리즈 개인 골프 클럽 Putter", "올리마르 ATS 주니어 옐로우 시리즈 개인 골프 클럽",
     "810022120521"),
])
def test_one_upc_on_another_edition_is_no_hold_candidate(x, y, upc):
    a = D.entry(_agency(record(1, 11, x, values=[], category="50002783"), upc), "published")
    b = D.entry(_agency(record(2, 22, y, values=[], category="50002783"), upc), "job")
    assert a["upc"] & b["upc"] and not D.upc_suspect(a, b) and "same_upc" not in D.Index([a]).decide(b)


def test_upc_reads_every_code_of_the_row_and_a_gtin_as_its_upc():
    text = ("UPC | 815898026403 815898029947\nGlobal Trade Identification Number : 00792713117044\n"
            "UPC | ‎091966124145\nModel | 52 56 60")
    assert D.upcs(text) == {"815898026403", "815898029947", "792713117044", "91966124145"}
    assert D.upcs("UPC 코드 | 792713117044") == set() and D.upcs("") == set()


def test_same_brand_and_sets_sold_is_a_report_row_never_a_decision():
    """C41 part 3, report only: MAZEL 'DS-VH 4 Iron' 13603085795 / '7 Iron' 13312250515 sell the same iron numbers;
    equal sold sets coincide across products, so the pair is listed for the owner and never matched."""
    values = [[f"{n} Iron"] for n in range(1, 10)] + [["PW"], ["SW"]]
    a = D.entry(_agency(record(102617717, 13603085795, "MAZEL 남성 골프 아이언 세트9PCS 또는 위한 오른손잡이 골퍼를 "
                               "123456789 DS-VH 4 Iron", values=values, category="50002783", price=102400,
                               photos=("m1", "m2", "m3"))), "published")
    b = D.entry(_agency(record(1100071177, 13312250515, "MAZEL 남성 또는 스틸 아이언 위한 9PCS 샤프트가 세트 오른손잡이 "
                               "골퍼를 골프 7 Iron", values=values, category="50002783", price=85680,
                               photos=("m1", "m2", "x3"))), "job")
    brands = {a["key"]: "MAZEL", b["key"]: "mazel"}
    assert D.brand_sold_pairs([a, b], brands, []) == ([(a, b)] if a["key"] < b["key"] else [(b, a)])
    assert D.Index([a]).decide(b)["decision"] is None and not D.groups([a, b])
    assert D.brand_sold_pairs([a, b], {a["key"]: "MAZEL", b["key"]: "PGM"}, []) == []


def test_on_mode_holds_a_same_upc_copy_as_a_draft_and_log_mode_only_says_so(tmp_path, monkeypatch):
    """C39 in a job: decision same_upc:<key> (taken); under on it is published as a draft and withdrawn at once with a
    'hold: copy of live <key>' reason (OWNER_RULES rule 2); under log the event only."""
    import publish as PB
    shop, old, new = _published_shop(tmp_path, 0, 0)
    monkeypatch.setattr("placement.run", lambda *a, **k: None)
    monkeypatch.setattr(PB.Shop, "ready", lambda self: [new])
    drafts = []

    def publish_one(shop_, key, *a, draft=False, **k):
        drafts.append(draft)
        return {"key": key, "status": "published", "handle": "h"}
    monkeypatch.setattr(PB, "publish_one", publish_one)
    a, _ = _majek(photos_b=("j1", "z2", "z3", "z4"))
    a = {**a, "key": old}
    line = _agency(record(2, 22, MAJEK_SENIOR[1], values=[], photos=("j1", "z2", "z3", "z4"), category="50002783"),
                   "792713117044")
    for mode, calls in (("log", 0), ("on", 1)):
        job = dedupe_job(tmp_path / mode, mode, [line])
        job.meta["shops_root"] = str(tmp_path / "shops")
        job.shops_root = job.meta["shops_root"]
        assert J.dedupe_step(job, {"dedupe": D.Index([a])}, new, line) is None
        ev = job.events()[-1]
        assert ev["event"] == "duplicate_seen" and ev["decision"] == f"same_upc:{old}" and ev["upc"] == ["792713117044"]
        admin = Admin()
        what = J.publish_step(job, {"publisher": (admin, None, {})}, new)
        assert len(admin.calls) == calls and drafts[-1] is (mode == "on")
    assert what.endswith("; held (same UPC as 11)") and job.events()[-1]["event"] == "held_same_upc"
    assert D.ledger(SHOP, str(tmp_path / "shops"))[new]["reason"].startswith(f"hold: copy of live {old}, same UPC 7927")
    assert J.upc_hold_step(job, {"publisher": (Admin(), None, {})}, shop, new) == ""      # once
