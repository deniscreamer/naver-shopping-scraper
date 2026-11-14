"""Offline tests for scripts/: the HTTP client's retry / pagination rules
against a fake session, and the harvest classifier against the server's
committed search fixture. No network, no server.

    .venv/bin/python -m pytest scripts -q

Not in the default run (pyproject testpaths = server)."""
import json
import os

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

import example_search_harvest as H
from naver_api_client import ApiError, NaverApiClient

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                       "server", "naver_shopping", "fixtures", "search_slots.json")


# ---- fake transport ----------------------------------------------------------------

class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    """Answers each get() with the next scripted item (a response or an
    exception to raise) and records the calls."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        return self.request("GET", url, params=params, timeout=timeout)

    def request(self, method, url, params=None, timeout=None):
        self.calls.append({"method": method, "url": url, "params": dict(params or {}), "timeout": timeout})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def client(*answers):
    sleeps = []
    api = NaverApiClient(base_url="http://api.test", session=FakeSession(*answers), sleep=sleeps.append)
    return api, sleeps


def ok(body=None):
    return FakeResponse(200, body if body is not None else {})


# ---- get ----------------------------------------------------------------------------

def test_get_drops_none_params_and_uses_timeouts():
    api, _ = client(ok({"results": []}))
    assert api.get("/products/search", query="pi", max_price=None, category="50000003") == {"results": []}
    call = api.session.calls[0]
    assert call["url"] == "http://api.test/products/search"
    assert call["params"] == {"query": "pi", "category": "50000003"}
    assert call["timeout"] == (5.0, 900.0)


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("NAVER_API_URL", "http://other:9000/")
    monkeypatch.setenv("NAVER_API_READ_TIMEOUT", "60")
    api = NaverApiClient(session=FakeSession())
    assert api.base_url == "http://other:9000"
    assert api.timeout == (5.0, 60.0)


def test_502_retries_then_succeeds():
    api, sleeps = client(FakeResponse(502, {"error": "blocked"}), ok({"id": "1"}))
    assert api.get("/products/details", product="1") == {"id": "1"}
    assert len(api.session.calls) == 2
    assert sleeps == [10]


def test_502_gives_up_after_two_retries():
    api, sleeps = client(*[FakeResponse(502, {"error": "blocked"})] * 3)
    with pytest.raises(ApiError) as e:
        api.get("/products/details", product="1")
    assert e.value.status == 502
    assert sleeps == [10, 30]
    assert len(api.session.calls) == 3


def refused():
    reason = NewConnectionError(None, "Connection refused")
    return requests.exceptions.ConnectionError(MaxRetryError(None, "/health", reason))


@pytest.mark.parametrize("error", [refused(), requests.exceptions.ConnectTimeout("connect")])
def test_connect_failure_retries(error):
    api, sleeps = client(error, ok({"status": "ok"}))
    assert api.health() == {"status": "ok"}
    assert sleeps == [10]


@pytest.mark.parametrize("error", [
    requests.exceptions.ConnectionError(ProtocolError("Connection aborted.", "RemoteDisconnected")),
    requests.exceptions.ConnectionError("read timed out mid-body"),
])
def test_connection_error_after_send_is_not_retried(error):
    api, sleeps = client(error, ok())
    with pytest.raises(requests.exceptions.ConnectionError):
        api.get("/products/details", product="1")
    assert sleeps == [] and len(api.session.calls) == 1


@pytest.mark.parametrize("status", [400, 404, 500])
def test_client_and_server_errors_raise_without_retry(status):
    api, sleeps = client(FakeResponse(status, {"error": "nope", "errors": {"product": ["bad"]}}))
    with pytest.raises(ApiError) as e:
        api.get("/products/details", product="x")
    assert (e.value.status, e.value.error) == (status, "nope")
    assert e.value.errors == {"product": ["bad"]}
    assert sleeps == [] and len(api.session.calls) == 1


def test_read_timeout_is_not_retried():
    api, sleeps = client(requests.exceptions.ReadTimeout("slow"), ok())
    with pytest.raises(requests.exceptions.ReadTimeout):
        api.get("/products/details", product="1")
    assert sleeps == [] and len(api.session.calls) == 1


# ---- pages --------------------------------------------------------------------------

def page_body(n, has_next):
    return {"current_page": n, "next": f"http://elsewhere/products/reviews?page={n + 1}" if has_next else None,
            "results": [n]}


def test_pages_stop_on_null_next_and_never_follow_next_url():
    api, _ = client(ok(page_body(1, True)), ok(page_body(2, True)), ok(page_body(3, False)))
    got = [p["current_page"] for p in api.pages("/products/reviews", product="1")]
    assert got == [1, 2, 3]
    assert all(c["url"] == "http://api.test/products/reviews" for c in api.session.calls)
    assert [c["params"]["page"] for c in api.session.calls] == [1, 2, 3]


def test_pages_stop_at_schema_cap():
    api, _ = client(*[ok(page_body(n, True)) for n in range(1, 30)])
    assert len(list(api.pages("/keywords/rank", category="50000002"))) == 25


def test_pages_stop_at_reviews_cap():
    api, _ = client(*[ok(page_body(n, True)) for n in range(1, 502)])
    assert len(list(api.pages("/products/reviews", product="1"))) == 500
    assert api.session.calls[-1]["params"]["page"] == 500


def test_pages_cap_applies_to_prefixed_path():
    api, _ = client(*[ok(page_body(n, True)) for n in range(1, 30)])
    assert len(list(api.pages("/naver-shopping/keywords/rank", category="50000002"))) == 25
    assert api.session.calls[0]["url"] == "http://api.test/naver-shopping/keywords/rank"


def test_page_caps_match_server_schemas():
    schemas = pytest.importorskip("naver_shopping.schemas")
    from naver_api_client import PAGE_CAPS
    assert PAGE_CAPS == {"/products/reviews": schemas.MAX_REVIEW_PAGE, "/keywords/rank": schemas.MAX_RANK_PAGE}


def test_pages_stop_on_empty_results():
    api, _ = client(ok(page_body(1, True)), ok({"current_page": 2, "next": "http://x/?page=3", "results": []}), ok())
    assert [p["current_page"] for p in api.pages("/products/reviews", product="1")] == [1, 2]
    assert len(api.session.calls) == 2


def test_pages_stop_at_max_page():
    api, _ = client(*[ok(page_body(n, True)) for n in range(1, 10)])
    assert len(list(api.pages("/products/reviews", max_page=3, product="1"))) == 3


def test_pages_treat_page_400_after_a_yield_as_end():
    api, _ = client(ok(page_body(1, True)),
                    FakeResponse(400, {"error": "Invalid parameters: page", "errors": {"page": ["too big"]}}))
    assert [p["current_page"] for p in api.pages("/products/reviews", product="1")] == [1]


def test_pages_other_400_after_a_yield_raises():
    api, _ = client(ok(page_body(1, True)), FakeResponse(400, {"error": "naver-shopping rejected the request"}))
    with pytest.raises(ApiError):
        list(api.pages("/products/reviews", product="1"))


def test_pages_400_on_first_requested_page_raises_even_past_one():
    api, _ = client(FakeResponse(400, {"error": "Invalid parameters: product", "errors": {"product": ["bad"]}}))
    with pytest.raises(ApiError):
        list(api.pages("/products/reviews", page=3, product="bad"))


def test_pages_400_on_first_page_raises():
    api, _ = client(FakeResponse(400, {"error": "Invalid parameters: product"}))
    with pytest.raises(ApiError):
        list(api.pages("/products/reviews", product="bad"))


# ---- harvest classifier ----------------------------------------------------------------

def test_classify_store_product_uses_store_link():
    card = {"type": "product", "product_id": "8087042745",
            "link": "https://smartstore.naver.com/main/products/8087042745",
            "store": {"link": "https://smartstore.naver.com/dailyromantic"}}
    assert H.classify_card(card) == (
        "product", "https://smartstore.naver.com/dailyromantic/products/8087042745", None)


def test_classify_catalog_and_external():
    assert H.classify_card({"type": "catalog", "catalog_id": "61626354397",
                            "link": "https://search.shopping.naver.com/catalog/61626354397"})[:2] \
        == ("catalog", "61626354397")
    kind, target, reason = H.classify_card({"type": "product", "product_id": "1",
                                            "link": "https://link.coupang.com/re/X",
                                            "store": {"link": "https://link.coupang.com/re/Y"}})
    assert (kind, target) == ("skip", None) and "link.coupang.com" in reason


@pytest.mark.parametrize("store_link, product_id", [
    ("https://smartstore.naver.com/main", "8087042745"),          # reserved slug, from an unwrapped /main/ mallUrl
    ("https://smartstore.naver.com", "8087042745"),               # no slug at all
    ("https://smartstore.naver.com/dailyromantic", "12345"),      # under refs' 6 digits
])
def test_classify_skips_inputs_refs_would_reject(store_link, product_id):
    card = {"type": "product", "product_id": product_id,
            "link": f"https://smartstore.naver.com/main/products/{product_id}", "store": {"link": store_link}}
    assert H.classify_card(card)[:2] == ("skip", None)


def test_classifier_on_server_search_fixture():
    """Contract check: the classifier against the cards the server really
    emits for the committed fixture. This TEST (not the scripts) borrows the
    server parser, found through pyproject's pythonpath = server."""
    parsers = pytest.importorskip("naver_shopping.parsers")
    with open(FIXTURE, encoding="utf-8") as f:
        cards = parsers.parse_search_slots(json.load(f))
    kinds = [H.classify_card(c) for c in cards]
    assert len(cards) == 96
    assert sum(k == "product" for k, _, _ in kinds) == 55
    assert sum(k == "catalog" for k, _, _ in kinds) == 40
    skipped = [r for k, _, r in kinds if k == "skip"]
    assert len(skipped) == 1 and "link.coupang.com" in skipped[0]
    products = [t for k, t, _ in kinds if k == "product"]
    assert all("/main/products/" not in t for t in products)
    assert all(t.startswith("https://smartstore.naver.com/") for t in products)


def test_harvest_resumes(tmp_path):
    card = {"id": "n1", "type": "product", "product_id": "8087042745",
            "link": "https://smartstore.naver.com/main/products/8087042745",
            "store": {"link": "https://smartstore.naver.com/dailyromantic"}}
    search = ok({"results": [card, {"id": "c1", "type": "catalog", "catalog_id": "61626354397"}]})
    api, _ = client(search, ok({"id": "8087042745"}))
    assert H.harvest(api, "q", 0, str(tmp_path)) == 1
    api2, _ = client(search)
    assert H.harvest(api2, "q", 0, str(tmp_path)) == 0      # already written: no details call
    rows = [json.loads(line) for line in open(tmp_path / "products.jsonl", encoding="utf-8")]
    assert len(rows) == 1
    assert rows[0]["endpoint"] == "/products/details"
    assert rows[0]["params"] == {"product": "https://smartstore.naver.com/dailyromantic/products/8087042745"}
    assert set(rows[0]) == {"fetched_at", "endpoint", "params", "data"}


def test_harvest_logs_a_400_and_continues(tmp_path):
    cards = [{"id": f"n{i}", "type": "product", "product_id": pid,
              "link": f"https://smartstore.naver.com/main/products/{pid}",
              "store": {"link": "https://smartstore.naver.com/dailyromantic"}}
             for i, pid in enumerate(["8087042745", "8087042746"])]
    api, _ = client(ok({"results": cards}), FakeResponse(400, {"error": "bad product"}), ok({"id": "8087042746"}))
    assert H.harvest(api, "q", 0, str(tmp_path)) == 1
    assert len(api.session.calls) == 3



def test_listing_starts_polls_and_reads_every_row():
    job = {"id": "20261101-120000-abcd", "status": "running", "kept": 0}
    api, sleeps = client(
        FakeResponse(202, job),
        ok({**job, "status": "captcha"}),
        ok({**job, "status": "done", "kept": 3, "stop": "hasMore=false"}),
        ok({"results": [{"product_id": "1"}, {"product_id": "2"}], "next": "http://x/next"}),
        ok({"results": [{"product_id": "3"}], "next": None}),
    )
    out = api.listing("남성 골프채 풀세트")
    assert out["job"]["status"] == "done" and [r["product_id"] for r in out["results"]] == ["1", "2", "3"]
    calls = api.session.calls
    assert calls[0]["method"] == "POST" and calls[0]["params"] == {"query": "남성 골프채 풀세트"}
    assert calls[1]["url"].endswith("/listings/20261101-120000-abcd") and len(sleeps) == 2
    assert calls[3]["url"].endswith("/listings/20261101-120000-abcd/products")


def test_listing_busy_raises():
    api, _ = client(FakeResponse(409, {"error": "a listing job is running: x", "job_id": "x"}))
    with pytest.raises(ApiError) as e:
        api.listing("q")
    assert e.value.status == 409


def test_listing_tab_methods_call_their_routes():
    tab = {"id": "20261114-070000-aaaa", "query": "q", "batch": 1, "has_more": True, "total": 53, "results": []}
    api, _ = client(ok(tab), ok({**tab, "batch": 2}), ok({"id": "1"}), ok({"id": tab["id"], "closed": True}))
    assert api.listing_tab_open("q")["batch"] == 1
    assert api.listing_tab_next(tab["id"])["batch"] == 2
    link = "https://smartstore.naver.com/s/products/1"
    api.listing_tab_specs(tab["id"], link)
    assert api.listing_tab_close(tab["id"])["closed"] is True
    calls = [(c["method"], c["url"].removeprefix("http://api.test"), c["params"]) for c in api.session.calls]
    assert calls == [("POST", "/listing-tabs", {"query": "q"}),
                     ("POST", f"/listing-tabs/{tab['id']}/next", {}),
                     ("GET", f"/listing-tabs/{tab['id']}/specs", {"product": link}),
                     ("DELETE", f"/listing-tabs/{tab['id']}", {})]


@pytest.mark.parametrize("status", [404, 409, 410, 503])
def test_listing_tab_errors_are_not_retried(status):
    api, sleeps = client(FakeResponse(status, {"error": "listing tab x is gone"}))
    with pytest.raises(ApiError) as e:
        api.listing_tab_next("20261114-070000-aaaa")
    assert e.value.status == status and sleeps == [] and len(api.session.calls) == 1


def test_examples_compile():
    import glob
    import py_compile
    here = os.path.dirname(os.path.abspath(__file__))
    examples = sorted(glob.glob(os.path.join(here, "example_[0-9][0-9]_*.py")))
    assert len(examples) == 16                      # 01-14, 15 (description images), 99
    for path in examples:
        py_compile.compile(path, doraise=True)


def test_check_setup_local_runs(capsys):
    import check_setup
    code = check_setup.main(["--no-server"])
    out = capsys.readouterr().out
    assert code in (0, 1) and "python >= 3.11" in out and ("READY" in out)


def test_env_file_loader(tmp_path, monkeypatch):
    from naver_api_client import load_env_file
    env = tmp_path / ".env"
    env.write_text("# comment\nNS_TEST_A=1\nexport NS_TEST_B='two'\nNS_TEST_C=\nNS_TEST_D=keep\n", encoding="utf-8")
    monkeypatch.setenv("NS_TEST_D", "shell")
    for k in ("NS_TEST_A", "NS_TEST_B", "NS_TEST_C"):
        monkeypatch.delenv(k, raising=False)
    load_env_file(str(env))
    assert os.environ["NS_TEST_A"] == "1" and os.environ["NS_TEST_B"] == "two"
    assert "NS_TEST_C" not in os.environ and os.environ["NS_TEST_D"] == "shell"
