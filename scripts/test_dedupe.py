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
    srixon = [E(4, 4, "스릭슨 27ZXI-RKT 풀세트"), E(5, 5, "스릭슨 27ZXI-RKT LS 풀세트")]
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
    ctx = _ctx(job, E(9, 99, "다른 상품", status="published"))
    collect_to_images["line"] = first
    with pytest.raises(ImagesReached):
        J.one(job, ctx, first["key"], None)                                  # joins the index as "job"
    job.log(first["key"], "not_taken", reason="not ready to publish")        # closed after the dedupe step
    collect_to_images["line"] = later
    with pytest.raises(ImagesReached):                                       # goes on: nothing left to copy
        J.one(job, ctx, later["key"], None)
    assert first["key"] not in ctx["dedupe"].by_key and f"{SHOP}:naver:9:99" in ctx["dedupe"].by_key


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
