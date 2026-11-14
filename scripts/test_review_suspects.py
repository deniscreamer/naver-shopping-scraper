"""review_suspects.py: the doubtful published products of a lenient run, read offline (the owner, 2026-11-14)."""
import csv
import json
import os

import review_suspects as R

SHOP = "fairwardgolf"


def prepared(n, title, category="50002788", specs=(), options=(("",),)):
    return {"key": f"{SHOP}:naver:100:{n}", "status": "ready",
            "source": {"category_id": category, "product_id": str(n), "channel_no": "100"},
            "product": {"title_ko": title, "specs": [{"label_ko": a, "value_ko": b} for a, b in specs],
                        "pricing": {"base_krw": 1000000},
                        "variants": [{"options_ko": list(o), "price_krw": 1000000} for o in options]}}


def shop(tmp_path, products, published):
    root = tmp_path / "shops"
    for sub in ("prepared", "publish"):
        (root / SHOP / sub).mkdir(parents=True)
    (root / SHOP / "prepared" / "products.jsonl").write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in products), encoding="utf-8")
    (root / SHOP / "publish" / "published.jsonl").write_text("".join(json.dumps(
        {"key": f"{SHOP}:naver:100:{n}", "status": s, "product_id": f"gid://shopify/Product/9{n}",
         "handle": f"h-{n}", "admin_url": f"https://admin/{n}"}) + "\n" for n, s in published), encoding="utf-8")
    return root


PRODUCTS = [
    prepared(1, "테일러메이드 Qi4D 남성 풀세트 10개"),                                    # a set: not listed
    prepared(2, "PXG 풀세트 남성 3종세트 드라이버 우드 유틸리티"),                         # few_clubs
    prepared(3, "골프 드라이버 남성용 오른손 고반발 골프채"),                              # single_club (the title)
    prepared(4, "혼마 남성 골프채 풀세트", specs=[("아이언개수", "단품")]),                # single_club (a spec row)
    prepared(5, "[중고] 핑 G430 남성 풀세트 11개"),                                        # used
    prepared(6, "중고급자용 젝시오 남성 풀세트 10개"),                                    # 중고급: not used
    prepared(7, "여성 풀세트 캐디백 주니어 골프공 증정"),                             # junior, accessory
    prepared(8, "접이식 성인용 골프채 휴대용"),                                            # single_club (folding)
    prepared(9, "젝시오 남성 골프채 풀세트 9개", specs=[("총클럽개수", "3개")]),           # few_clubs (a spec row)
    prepared(10, "골프 드라이버 남성용 단품"),                                              # not published
    prepared(11, "골프 퍼터 남성용"),                                                       # withdrawn
    prepared(12, "주니어 골프 드라이버", category="50002787"),                             # another category
    prepared(13, "남성 골프채 13종 풀세트"),                                                # 13종 is no 3종
    prepared(14, "캘러웨이 XJ3 주니어 골프채 풀세트 7개 캐디백 포함"),                     # junior (no rule drops it)
    prepared(15, "성인 및 주니어용가능 입문 골프채 풀세트 10개"),                          # 주니어용가능: not junior
]
LIVE = [(n, "published") for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15)] + [(11, "published"), (11, "withdrawn")]


def test_the_doubtful_published_products_and_their_reasons(tmp_path):
    root = shop(tmp_path, PRODUCTS, LIVE)
    rows = R.suspects(str(root / SHOP), "50002788")
    got = {r["key"].rsplit(":", 1)[-1]: r["reasons"] for r in rows}
    assert got == {"2": "few_clubs", "3": "single_club", "4": "single_club", "5": "used",
                   "7": "junior;accessory", "8": "single_club", "9": "few_clubs", "14": "junior"}
    two = next(r for r in rows if r["key"].endswith(":2"))
    assert two["product_id"] == "92" and two["handle"] == "h-2" and two["admin_url"] == "https://admin/2"
    assert two["price"] == "1000000 KRW"                         # no package box: the rule cannot price it


def test_a_job_limits_the_review_to_its_keys_and_the_csv_goes_next_to_it(tmp_path, capsys):
    root = shop(tmp_path, PRODUCTS, LIVE)
    job = tmp_path / "jobs" / "j1"
    job.mkdir(parents=True)
    (job / "listing.jsonl").write_text("".join(json.dumps({"key": f"{SHOP}:naver:100:{n}"}) + "\n"
                                               for n in (1, 3, 5)), encoding="utf-8")
    before = (root / SHOP / "publish" / "published.jsonl").read_text(encoding="utf-8")
    assert R.main([SHOP, "--job", "j1", "--shops-root", str(root), "--jobs-root", str(tmp_path / "jobs")]) == 0
    assert "2 doubtful published products of 50002788 in job j1: single_club 1, used 1" in capsys.readouterr().out
    with open(job / "suspects.csv", encoding="utf-8-sig", newline="") as f:
        lines = list(csv.DictReader(f))
    assert [(x["key"].rsplit(":", 1)[-1], x["reasons"]) for x in lines] == [("3", "single_club"), ("5", "used")]
    assert lines[1]["title"] == "[중고] 핑 G430 남성 풀세트 11개"
    assert (root / SHOP / "publish" / "published.jsonl").read_text(encoding="utf-8") == before   # read only


def test_without_a_job_the_csv_goes_in_the_shop_folder(tmp_path):
    root = shop(tmp_path, PRODUCTS, LIVE)
    assert R.main([SHOP, "--shops-root", str(root)]) == 0
    assert os.path.exists(root / SHOP / "review_suspects-50002788.csv")
