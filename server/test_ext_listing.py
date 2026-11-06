"""Offline tests for the captcha wait of the adapter transport (ext_listing.check): a fake bridge shows a captcha,
then a new one (a wrong answer), then the page. Nothing is ever typed into the captcha: the human answers.

    python -m pytest server/test_ext_listing.py -q
"""
import ext_listing

CAPTCHA = ('<html><head><title>captcha</title></head><body><div id="wtm_captcha"><p>This receipt is made virtually.'
           '</p><p class="q">What is the first number of the store\'s phone number?</p>'
           '<input type="text" placeholder="Please enter the Answer."></div></body></html>')
CAPTCHA_2 = CAPTCHA.replace("first number of the store's phone number", "price of the second item")
PAGE = "<html><head><title>검색</title></head><body>상품</body></html>"


class Pages:
    """A bridge whose tab shows the given pages in turn (the last one stays)."""
    def __init__(self, *pages):
        self.pages, self.calls = list(pages), []

    def call(self, op, **args):
        self.calls.append((op, args.get("selector")))
        if op == "page":
            html = self.pages[0] if len(self.pages) == 1 else self.pages.pop(0)
            return {"url": "https://search.shopping.naver.com/ns/search", "title": "t", "html": html}
        if op == "query":
            return {"count": 1}
        if op == "click":
            return {"x": 1, "y": 1, "newTabId": None}
        if op == "screenshot":
            return "data:image/png;base64,iVBORw0KGgo="
        raise AssertionError(f"unexpected op {op}")


def test_question():
    assert ext_listing.captcha_question(CAPTCHA) == "What is the first number of the store's phone number?"
    assert ext_listing.captcha_question(PAGE) is None


def test_captcha_waits_reports_again_and_goes_on(tmp_path, monkeypatch):
    notices = []
    monkeypatch.setattr(ext_listing, "notify", lambda event, message, **d: notices.append((event, d.get("question"))))
    monkeypatch.setattr(ext_listing.time, "sleep", lambda s: None)
    monkeypatch.setattr(ext_listing, "pause", lambda a, b: None)
    bridge = Pages(CAPTCHA, CAPTCHA, CAPTCHA_2, CAPTCHA_2, PAGE)
    summary = {}
    assert ext_listing.check(bridge, 7, "search", str(tmp_path), summary) is True
    assert notices == [("captcha", "What is the first number of the store's phone number?"),
                       ("captcha", "What is the price of the second item?")]
    assert ("click", ext_listing.CAPTCHA_INPUT) in bridge.calls                # the cursor in the answer field
    assert not any(op == "type" for op, _ in bridge.calls)                      # never typed: the human answers
    assert summary["status"] == "running"
    state = ext_listing.captcha_state()
    assert (state["status"], state["step"], state["attempt"]) == ("solved", "search", 2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "search-captcha-2.html", "search-captcha-2.png", "search-captcha.html", "search-captcha.png"]


def test_captcha_not_answered_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(ext_listing, "notify", lambda *a, **d: None)
    monkeypatch.setattr(ext_listing.time, "sleep", lambda s: None)
    clock = iter(range(0, 100000, 100))
    monkeypatch.setattr(ext_listing.time, "monotonic", lambda: next(clock))
    assert ext_listing.check(Pages(CAPTCHA), 7, "search", str(tmp_path), {}) is False
    assert ext_listing.captcha_state()["status"] == "timed_out"


def test_captcha_state_while_waiting(tmp_path, monkeypatch):
    monkeypatch.setattr(ext_listing, "notify", lambda *a, **d: None)
    monkeypatch.setattr(ext_listing, "pause", lambda a, b: None)
    seen = []
    monkeypatch.setattr(ext_listing.time, "sleep", lambda s: seen.append(ext_listing.captcha_state()))
    assert ext_listing.check(Pages(CAPTCHA, PAGE), 7, "product", str(tmp_path), {}) is True
    waiting = seen[0]
    assert waiting["status"] == "waiting" and waiting["question"].startswith("What is the first number")
    assert waiting["screenshot"].endswith("product-captcha.png") and waiting["wait_s"] == ext_listing.HUMAN_WAIT_S
