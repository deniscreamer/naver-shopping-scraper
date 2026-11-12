"""review_pick (the owner, 2026-11-11): a product with many reviews keeps the best few, their photos capped."""
from review_pick import KEEP, PER_PRODUCT, PER_REVIEW, pick, score


def review(i, text, photos=0, likes=0, stars=5):
    return {"id": str(i), "text": text, "score": stars, "likes": likes,
            "attachments": [{"type": "photo", "url": f"u{i}-{n}"} for n in range(photos)]}


GOOD = "아이가 좋아해요. 클럽 무게가 가볍고 드라이버 타구감도 좋아서 연습장에서 잘 쳐요. 길이도 키에 딱 맞아요."
SHIPPING = "배송 빠르고 포장 꼼꼼해요 감사합니다"


def test_a_few_reviews_are_left_as_they_came():
    few = [review(i, SHIPPING, photos=6) for i in range(KEEP)]
    assert pick(few, "50002787") == (few, None)                                 # equal, copied


def test_the_best_are_kept_in_their_order_and_their_photos_capped():
    many = [review(i, f"{SHIPPING} {i}", photos=1) for i in range(12)] + [review(100 + i, f"{GOOD} {i}번째", photos=5)
                                                                  for i in range(6)]
    kept, summary = pick(many, "50002787")
    assert len(kept) == KEEP
    assert {str(100 + i) for i in range(6)} <= {r["id"] for r in kept}           # every product review is kept
    assert all(len(r["attachments"]) <= PER_REVIEW for r in kept)
    assert sum(len(r["attachments"]) for r in kept) <= PER_PRODUCT
    order = [int(r["id"]) for r in kept]
    assert order == sorted(order, key=lambda i: [r["id"] for r in many].index(str(i)))  # the server's order
    assert summary["from"] == 18 and summary["kept"] == KEEP and summary["photos_from"] == 42


def test_a_fair_low_score_stays_and_sponsored_go():
    many = [review(i, f"{SHIPPING} {i}") for i in range(10)] + [review(50, GOOD, stars=2), review(51, "체험단으로 " + GOOD)]
    kept, _ = pick(many, "50002787")
    assert "50" in {r["id"] for r in kept} and "51" not in {r["id"] for r in kept}
    assert score(review(51, "협찬 받아 " + GOOD), "50002787") is None


def test_one_buyers_text_again_is_not_taken_twice():
    many = [review(i, GOOD, photos=1) for i in range(5)] + [review(10 + i, f"{GOOD} 다른 {i}") for i in range(10)]
    kept, _ = pick(many, "50002787")
    assert sum(r["text"] == GOOD for r in kept) == 1
