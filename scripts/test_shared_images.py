"""Offline tests for shared_images.py (store-wide description banners found across one transform run).

The links are real: store 100568453 from the run of 2026-11-07, its 10 prepared fixtures in
fixtures/prepared/, and the must-not-match stores of the three checked runs.

    .venv/bin/python -m pytest scripts/test_shared_images.py -q
"""
import copy
import json
import os

from shared_images import MIN_PRODUCTS, MIN_SHARE, image_identity, drop_shared_images

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "prepared")
CDN = "https://shop-phinf.pstatic.net/"
# store 100568453's header and footer, uploaded again for each batch of listings (same file name, new folder)
HEAD = "30434463209514390_345786175.jpg"
FOOT1 = "60948062508870618_280838627.jpg"
FOOT2 = "22313003105171778_1094441035.jpg"


def product(pid, channel, images):
    return {"key": f"fairwardgolf:naver:{channel}:{pid}", "status": "ready", "held": [], "notes": [],
            "source": {"channel_no": channel, "product_id": pid},
            "product": {"description_images": list(images), "description_dropped": []}}


def store_fixtures():
    out = []
    for name in sorted(os.listdir(FX)):
        with open(os.path.join(FX, name), encoding="utf-8") as f:
            p = json.load(f)
        if p["source"]["channel_no"] == "100568453":
            out.append(p)
    return out


def names(links):
    return [x.split("?")[0].rsplit("/", 1)[-1] for x in links]


def test_store_banners_dropped_from_the_real_store():
    # seen 2026-11-07 (run40b): 18 listings of 100568453 open with HEAD and close with FOOT1 + FOOT2, numeric names,
    # 5-6 upload folders each; the 10 fixtures of the store keep the pattern
    given = store_fixtures()
    assert len(given) == 10
    before = copy.deepcopy(given)
    out = {p["key"].split(":")[3]: p for p in drop_shared_images(given)}
    assert given == before                                          # pure: the input is not changed
    p = out["13002235969"]
    kept, dropped = p["product"]["description_images"], p["product"]["description_dropped"]
    assert HEAD not in names(kept) and FOOT1 not in names(kept) and FOOT2 not in names(kept)
    assert len(kept) == 10                                          # 13 - 3
    assert [d["rule"] for d in dropped if d["rule"] == "shared_store_image"] == ["shared_store_image"] * 3
    assert names(d["text"] for d in dropped if d["rule"] == "shared_store_image") == [HEAD, FOOT1, FOOT2]
    [note] = [n for n in p["notes"] if n["code"] == "description_shared_images"]
    assert note["detail"] == (f"dropped: {HEAD} (5 of 6 listing groups), {FOOT1} (6 of 6 listing groups), "
                              f"{FOOT2} (5 of 6 listing groups)")
    # the two G440 MAX sets have their own header (43515115306493022_971115519.jpg, 2 of 10): kept
    p = out["13753294507"]
    assert names(p["product"]["description_images"])[0] == "43515115306493022_971115519.jpg"
    assert len(p["product"]["description_images"]) == 3
    # the old 2024 listing (run20) closes with FOOT1 and then a footer of its own (60948062316366678_1397231647.jpg,
    # 1 of 10): FOOT1 is no longer at the edge, so it stays and the note names it; the header goes
    p = out["10816781893"]
    assert names(p["product"]["description_images"])[-2:] == [FOOT1, "60948062316366678_1397231647.jpg"]
    assert HEAD not in names(p["product"]["description_images"])
    [note] = [n for n in p["notes"] if n["code"] == "description_shared_images"]
    assert note["detail"] == f"dropped: {HEAD} (5 of 6 listing groups); kept in the middle: {FOOT1} (6 of 6 listing groups)"
    assert sum(len(p["product"]["description_images"]) for p in given) - \
        sum(len(p["product"]["description_images"]) for p in out.values()) == 26   # 8 HEAD + 9 FOOT1 + 9 FOOT2


def test_identity_merges_a_reupload_by_a_distinctive_name_only():
    a = CDN + f"20260113_42/1768273789031HaRbt_JPEG/{HEAD}?type=w860"
    b = CDN + f"20250405_172/1743831662836dw1fg_JPEG/{HEAD}?type=w860"
    assert image_identity(a) == image_identity(b)
    assert image_identity(a) == image_identity(a.replace("?type=w860", "?type=w640"))
    # generic names stay one image per link: 102412170 (run40-replay) has 34 different image.png in 3 listings
    c = CDN + "20240710_104/1720617096050WTqQJ_PNG/image.png?type=w860"
    d = CDN + "20240710_53/1720617532356McyvH_PNG/image.png?type=w860"
    assert image_identity(c) != image_identity(d)
    for generic in ("최종.jpg", "상세_기본.jpg", "000000000000000.jpg", "1.jpg"):
        assert image_identity(CDN + f"x/1A_JPEG/{generic}") != image_identity(CDN + f"y/2B_JPEG/{generic}")
    # a phone photo name is one source file: merged (KakaoTalk_20251223_151514485.jpg, 100568453)
    k = "KakaoTalk_20251223_151514485.jpg"
    assert image_identity(CDN + f"x/1A_JPEG/{k}") == image_identity(CDN + f"y/2B_JPEG/{k}")


def test_generic_names_repeated_in_every_listing_are_not_a_banner():
    # 102412170 (run40-replay): every listing has its own image.png set, the name repeats, the links do not
    ps = [product(pid, "102412170", [CDN + f"20240710_{i}/17206{pid[-4:]}{i:03d}x_PNG/image.png?type=w860"
                                     for i in range(5)])
          for pid in ("10569099959", "10563381788", "10569037690")]
    assert drop_shared_images(ps) == ps


def test_the_same_set_listed_twice_keeps_its_photos():
    # 101773735 (run40b): 10076378929 and 12391261816 are one set listed twice, all 12 photos shared
    photos = [CDN + "20240315_1/1710439340543GDQ91_JPEG/1번우드.jpg?type=w860",
              CDN + "20240315_2/1710439446914Kk9tC_JPEG/详情图14.jpg?type=w860",
              CDN + "20240315_3/1710442530943u0N6D_JPEG/bag.jpg?type=w860"]
    pair = [product("10076378929", "101773735", photos), product("12391261816", "101773735", photos)]
    assert drop_shared_images(pair) == pair                          # fewer than MIN_PRODUCTS listings
    # three copies of one description count as one listing: still nothing shared by MIN_PRODUCTS listings
    three = pair + [product("12391261817", "101773735", photos),
                    product("12391261818", "101773735", [CDN + "z/9Z_JPEG/other.jpg"])]
    assert drop_shared_images(three) == three


def test_one_set_listed_three_times_keeps_its_photos():
    # seen 2026-11-07 (run40b + run40-replay), 101773735: PGM steel 9 (10076378929), steel 12 (12391261816) and
    # carbon 12 (12391346892) open with their own club photos and share the last 12 photos (12/22 = 0.55): one set
    tail = [CDN + f"20240315_{i}/17104{i:08d}x_JPEG/{n}?type=w860" for i, n in enumerate(
        ("1번우드.jpg", "详情图14.jpg", "详情图7_(2).jpg", "详情图19.jpg", "详情图20.jpg", "详情图12_(2).jpg", "详情图6.jpg",
         "详情图22.jpg", "퍼터.jpg", "샤프트.jpg", "bag.jpg", "003.png"))]
    ps = [product(pid, "101773735", [CDN + f"own/{pid}{i}_PNG/{i:03d}.png" for i in range(10)] + tail)
          for pid in ("10076378929", "12391261816", "12391346892")]
    assert drop_shared_images(ps) == ps
    # with banners of their own the three still count once: the store has one listing group, below MIN_PRODUCTS
    other = [product(str(i), "101773735", [CDN + f"o/{i}A_JPEG/own{i}.jpg"]) for i in range(2)]
    assert drop_shared_images(ps + other) == ps + other


def test_a_store_with_fewer_listings_than_the_minimum_is_untouched():
    # run20: two listings of 100568453 share the header 1725079598721CRAyj_JPEG/HEAD
    head = CDN + f"20240831_1/1725079598721CRAyj_JPEG/{HEAD}?type=w860"
    ps = [product("10816781893", "100568453", [head, CDN + "a/1A_JPEG/a.jpg"]),
          product("10816904599", "100568453", [head, CDN + "b/2B_JPEG/b.jpg"])]
    assert MIN_PRODUCTS == 3
    assert drop_shared_images(ps) == ps


def test_below_the_share_is_kept():
    # 100568453 (run40b): the G440 MAX photos 상세_기본.jpg / 샤프트.jpg are in 4 of 18 listings (one model line)
    shared = CDN + "20251005_9/1759631986376gVWHF_JPEG/상세_기본.jpg?type=w860"
    ps = [product(str(i), "100568453", ([shared] if i < 4 else []) + [CDN + f"o/{i}A_JPEG/own{i}.jpg"])
          for i in range(9)]
    assert 4 / 9 < MIN_SHARE
    assert drop_shared_images(ps) == ps


def test_other_stores_do_not_vote():
    head = CDN + f"20260113_42/1768273789031HaRbt_JPEG/{HEAD}?type=w860"
    ps = [product(str(i), ch, [head, CDN + f"o/{i}A_JPEG/own{i}.jpg"])
          for i, ch in enumerate(("100568453", "100568453", "500028318", "100416178"))]
    assert drop_shared_images(ps) == ps


def test_a_shared_image_in_the_middle_stays():
    # banners open or close a description; one inside the product's own photos is kept (and named in the note)
    head = CDN + f"20260113_42/1768273789031HaRbt_JPEG/{HEAD}?type=w860"
    foot = CDN + f"20260114_1/1768385533267PIVPV_JPEG/{FOOT1}?type=w860"
    ps = [product(str(i), "100568453", [head, CDN + f"o/{i}A_JPEG/own{i}.jpg", foot, CDN + f"p/{i}B_JPEG/end{i}.jpg"])
          for i in range(3)]
    out = drop_shared_images(ps)
    for p in out:
        assert names(p["product"]["description_images"]) == [f"own{p['key'][-1]}.jpg",
                                                              FOOT1, f"end{p['key'][-1]}.jpg"]
        [note] = p["notes"]
        assert note["code"] == "description_shared_images" and f"kept in the middle: {FOOT1}" in note["detail"]


def test_deterministic_and_order_kept():
    given = store_fixtures()
    a = drop_shared_images(given)
    b = drop_shared_images(list(reversed(given)))
    assert [p["key"] for p in a] == [p["key"] for p in given]
    assert {p["key"]: p for p in a} == {p["key"]: p for p in b}
