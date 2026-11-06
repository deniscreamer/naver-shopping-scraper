"""Offline tests for shopify_catalog.py: a fake Shopify (auth + Admin GraphQL), no network, made-up credentials.

    .venv/bin/python -m pytest scripts/test_shopify_catalog.py -q
"""
import os

import pytest

import shopify_catalog as SC
from shop_stores import STORES, StoreId
from shopify_catalog import MAX_AGE, CatalogError, ShopCatalog, ShopNotConfigured, read_credentials

STORE = STORES[StoreId.FAIRWARDGOLF]
CLIENT_ID, SECRET = "test-client-id", "test-secret-not-real"
TOKENS = ["test-token-1", "test-token-2", "test-token-3"]
AUTH_URL = "https://93r1y5-tt.myshopify.com/admin/oauth/access_token"
SHOP = {"id": "gid://shopify/Shop/70701744195", "myshopifyDomain": "93r1y5-tt.myshopify.com"}
VERIFIED = {"data": {"shop": SHOP, "currentAppInstallation": {"accessScopes": [{"handle": "read_products"},
                                                                                 {"handle": "write_products"}]}}}
PROBE = {"data": {"products": {"nodes": [{"id": "gid://shopify/Product/1"}]}}}
SHOP_ONLY = {"data": {"shop": SHOP}}


def node(n, source=None, legacy=None, status="ACTIVE"):
    return {"id": f"gid://shopify/Product/{n}", "status": status,
            "source_offer_id": {"value": source} if source else None,
            "naver_offer_key": {"value": legacy} if legacy else None}


def page(nodes, cursor=None):
    return {"data": {"products": {"nodes": nodes, "pageInfo": {"hasNextPage": bool(cursor), "endCursor": cursor}}}}


class Answer:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status_code, self.headers = body, status, headers or {}

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def token(n=0, expires=86399):
    return Answer({"access_token": TOKENS[n], "scope": "read_products,write_products", "expires_in": expires})


class FakeShopify:
    """Answers in order; records every call (url, form or query, the token header)."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def post(self, url, timeout, allow_redirects, data=None, json=None, headers=None):
        assert allow_redirects is False and timeout
        self.calls.append({"url": url, "form": data, "query": (json or {}).get("query"),
                           "variables": (json or {}).get("variables"),
                           "token": (headers or {}).get("X-Shopify-Access-Token")})
        a = self.answers.pop(0)
        return a if isinstance(a, Answer) else Answer(a)


@pytest.fixture
def creds(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("PORT=8000\n")
    os.chmod(env, 0o600)
    path = tmp_path / ".env.fairwardgolf"
    path.write_text(f"PRODUCTS_API_CLIENT_ID={CLIENT_ID}\nPRODUCTS_API_CLIENT_SECRET='{SECRET}'\n"
                    "ADMIN_API_CLIENT_ID=not-this-one\n")
    os.chmod(path, 0o600)
    monkeypatch.setenv("SHOPIFY_CREDENTIALS_FAIRWARDGOLF", str(path))
    return {"env": str(env), "path": str(path)}


def catalog(creds, answers, clock=lambda: 0.0, wall=lambda: 1_000_000.0, sleeps=None):
    shopify = FakeShopify(answers)
    c = ShopCatalog(STORE, session=shopify, clock=clock, sleep=(sleeps.append if sleeps is not None else lambda s: None),
                    env_file=creds["env"], wall_clock=wall, ignored=lambda p: True)
    return c, shopify


START = [token(), VERIFIED, PROBE, SHOP_ONLY]               # mint, verify, probe, the read's shop check


def test_mints_verifies_then_reads_every_page(creds):
    c, shopify = catalog(creds, START + [page([node(1, "fairwardgolf:naver:100:11"), node(2, status="DRAFT")], "c1"),
                                         page([node(3, legacy="fairwardgolf:naver:100:33", status="ARCHIVED")])])
    assert c.keys() == {"fairwardgolf:naver:100:11": "gid://shopify/Product/1",
                        "fairwardgolf:naver:100:33": "gid://shopify/Product/3"}
    auth, verify, probe, shop, first, second = shopify.calls
    assert auth["url"] == AUTH_URL and auth["form"] == {"grant_type": "client_credentials", "client_id": CLIENT_ID,
                                                        "client_secret": SECRET}
    assert "accessScopes" in verify["query"] and "products(first: 1)" in probe["query"]
    assert all(x["token"] == TOKENS[0] for x in shopify.calls[1:])
    assert first["variables"] == {"cursor": None} and second["variables"] == {"cursor": "c1"}
    assert 'namespace: "fairwardgolf", key: "naver_offer_key"' in first["query"]
    assert first["url"] == "https://93r1y5-tt.myshopify.com/admin/api/2026-07/graphql.json"
    assert SECRET not in repr(c) and TOKENS[0] not in repr(c) and SECRET not in repr(c.credentials)
    assert "PRODUCTS_API_CLIENT_SECRET" not in os.environ          # the file's values never reach the environment


def test_a_401_mid_run_mints_once_and_repeats_once(creds):
    c, shopify = catalog(creds, START + [Answer({}, 401), token(1), VERIFIED, PROBE, page([])])
    assert c.keys() == {} and c.credentials.minted == 2
    assert shopify.calls[-1]["token"] == TOKENS[1] and shopify.calls[-1]["query"].lstrip().startswith("query Products")


def test_a_second_401_stops(creds):
    c, _ = catalog(creds, START + [Answer({}, 401), token(1), VERIFIED, PROBE, Answer({}, 401)])
    with pytest.raises(CatalogError, match="401 again with a new token"):
        c.keys()


def test_the_token_is_replaced_before_it_ends(creds):
    now, wall = [0.0], [1_000_000.0]
    c, shopify = catalog(creds, START + [page([]), token(1, expires=3600), VERIFIED, PROBE, SHOP_ONLY, page([])],
                         clock=lambda: now[0], wall=lambda: wall[0])
    c.keys()
    now[0], wall[0] = MAX_AGE + 1, wall[0] + 86399 - SC.REFRESH_MARGIN + 1     # the snapshot is old, the token ends
    c.keys()
    assert c.credentials.minted == 2 and shopify.calls[-1]["token"] == TOKENS[1]


def test_snapshot_kept_five_minutes(creds):
    now = [0.0]
    c, shopify = catalog(creds, START + [page([]), SHOP_ONLY, page([node(1, "fairwardgolf:naver:1:2")])],
                         clock=lambda: now[0])
    assert c.keys() == {} and c.keys() == {} and len(shopify.calls) == 5
    now[0] = MAX_AGE + 1
    assert c.keys() == {"fairwardgolf:naver:1:2": "gid://shopify/Product/1"} and c.credentials.minted == 1


@pytest.mark.parametrize("answers, message", [
    ([Answer({"error": f"bad {SECRET}"}, 401)], r"authentication refused \(HTTP 401\)"),
    ([Answer(ValueError("html"))], "not a token"),
    ([Answer({"access_token": ""})], "not a token"),
    ([token(), {"data": {"shop": {**SHOP, "myshopifyDomain": "other.myshopify.com"},
                         "currentAppInstallation": {"accessScopes": [{"handle": "read_products"}]}}}], "not 93r1y5"),
    ([token(), {"data": {"shop": SHOP, "currentAppInstallation": {"accessScopes": [{"handle": "write_orders"}]}}}],
     "lacks read_products"),
    ([token(), Answer({}, 401)], "the new token is refused"),
    ([token(), VERIFIED, {"data": {}}], "no products field"),
    (START + [page([node(1, "fairwardgolf:naver:x:2")])], "is not fairwardgolf:naver"),
    (START + [page([node(1, "skinsli:naver:1:2")])], "is not"),                      # another shop's namespace
    (START + [page([node(1, "fairwardgolf:naver:1:2"), node(2, "fairwardgolf:naver:1:2")])], "on two products"),
    (START + [Answer({}, 403)], "token is refused"),
    (START + [{"errors": [{"message": "Access denied for products field"}]}], "Access denied"),
    (START + [Answer({}, 503)] * SC.RETRIES, f"throttled {SC.RETRIES} times"),
    ([token(), VERIFIED, Answer({}, 401)], "the new token is refused"),                # a 401 on the probe
    ([token(expires=SC.REFRESH_MARGIN)], "the token lives only"),
])
def test_untrusted_catalog_stops_the_check(creds, answers, message):
    c, _ = catalog(creds, answers)
    with pytest.raises(CatalogError, match=message) as e:
        c.keys()
    assert SECRET not in str(e.value) and TOKENS[0] not in str(e.value) and CLIENT_ID not in str(e.value)


def test_throttled_then_ok(creds):
    c, shopify = catalog(creds, START + [{"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}]},
                                         page([])])
    assert c.keys() == {} and len(shopify.calls) == 6


def test_queries_only(creds):
    c, shopify = catalog(creds, [])
    for q in ("mutation { productDelete(input: {id: 1}) { deletedProductId } }",
              "query { x } mutation Del($id: ID!) { productDelete(input: {id: $id}) { deletedProductId } }"):
        with pytest.raises(CatalogError, match="reads only"):
            c._post(q)
    assert shopify.calls == []


def test_credentials_file_rules(creds, tmp_path):
    assert read_credentials(creds["path"], ignored=lambda p: True) == (CLIENT_ID, SECRET)
    with pytest.raises(ShopNotConfigured, match="not ignored by git"):
        read_credentials(creds["path"], ignored=lambda p: False)
    os.chmod(creds["path"], 0o644)
    with pytest.raises(ShopNotConfigured, match="readable by others"):
        read_credentials(creds["path"], ignored=lambda p: True)
    other = tmp_path / "admin-only.env"
    other.write_text("ADMIN_API_CLIENT_ID=a\nADMIN_API_CLIENT_SECRET=b\n")
    os.chmod(other, 0o600)
    with pytest.raises(ShopNotConfigured, match="lacks PRODUCTS_API_CLIENT_ID"):
        read_credentials(str(other), ignored=lambda p: True)
    with pytest.raises(ShopNotConfigured, match="does not exist"):
        read_credentials(str(tmp_path / "none"), ignored=lambda p: True)


def test_git_ignored(tmp_path):
    import subprocess
    assert SC._git_ignored(str(tmp_path / "x.env"))                   # not in a git work tree: cannot be committed
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".env.*\n")
    assert SC._git_ignored(str(tmp_path / ".env.fairwardgolf"))
    assert not SC._git_ignored(str(tmp_path / "creds.txt"))


def test_not_configured(creds, monkeypatch):
    with pytest.raises(ShopNotConfigured, match="skinsli: no Shopify values yet"):
        ShopCatalog(STORES[StoreId.SKINSLI], env_file=creds["env"])
    monkeypatch.delenv("SHOPIFY_CREDENTIALS_FAIRWARDGOLF")
    with pytest.raises(ShopNotConfigured, match="SHOPIFY_CREDENTIALS_FAIRWARDGOLF is not set"):
        ShopCatalog(STORE, env_file=creds["env"])
    monkeypatch.setenv("SHOPIFY_CREDENTIALS_FAIRWARDGOLF", creds["path"])
    os.chmod(creds["env"], 0o644)
    with pytest.raises(ShopNotConfigured, match="chmod 600"):
        ShopCatalog(STORE, env_file=creds["env"], ignored=lambda p: True)


def test_a_token_that_fails_verify_is_not_kept(creds):
    no_scope = {"data": {"shop": SHOP, "currentAppInstallation": {"accessScopes": [{"handle": "write_orders"}]}}}
    c, shopify = catalog(creds, [token(0), no_scope, token(1), VERIFIED, PROBE, SHOP_ONLY, page([])])
    with pytest.raises(CatalogError, match="lacks read_products"):
        c.keys()
    assert c.keys() == {} and c.credentials.minted == 2               # minted and verified again
    assert all(x["token"] == TOKENS[1] for x in shopify.calls[3:])


def test_a_mid_run_401_whose_new_token_is_for_another_shop_stops(creds):
    other = {"data": {"shop": {**SHOP, "myshopifyDomain": "other.myshopify.com"},
                      "currentAppInstallation": {"accessScopes": [{"handle": "read_products"}]}}}
    c, shopify = catalog(creds, START + [Answer({}, 401), token(1), other])
    with pytest.raises(CatalogError, match="not 93r1y5"):
        c.keys()
    assert c.credentials.minted == 2 and not shopify.answers


def test_throttled_waits_what_shopify_says(creds):
    cost = {"requestedQueryCost": 302, "throttleStatus": {"currentlyAvailable": 2, "restoreRate": 50}}
    sleeps = []
    c, _ = catalog(creds, START + [{"errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}],
                                    "extensions": {"cost": cost}},
                                   Answer({}, 429, {"Retry-After": "2.0"}), page([])], sleeps=sleeps)
    assert c.keys() == {} and sleeps == [7.0, 2.0]                     # (302 - 2) / 50 + 1, then Retry-After


def test_snapshot_age_counts_from_the_start_of_the_read(creds):
    now = [0.0]
    c, shopify = catalog(creds, START + [page([], "c1"), page([]), SHOP_ONLY, page([])], clock=lambda: now[0])
    post = shopify.post

    def slow(*a, **kw):                                                  # every call takes 100 s
        now[0] += 100
        return post(*a, **kw)
    shopify.post = slow
    c.keys()                                                             # 6 calls: started at 0, ended at 600
    c.keys()                                                             # its first page is 600 s old: read again
    assert len(shopify.calls) == 8


def test_credentials_symlink_is_checked_as_its_target(creds, tmp_path):
    link = tmp_path / "link.env"
    link.symlink_to(creds["path"])
    seen = []
    assert read_credentials(str(link), ignored=lambda p: seen.append(p) or True) == (CLIENT_ID, SECRET)
    assert seen == [os.path.realpath(creds["path"])]
    os.chmod(creds["path"], 0o644)
    with pytest.raises(ShopNotConfigured, match="readable by others"):
        read_credentials(str(link), ignored=lambda p: True)


def test_unreadable_credentials_file(creds):
    with open(creds["path"], "wb") as f:
        f.write(b"PRODUCTS_API_CLIENT_ID=\xff\xfe\n")
    with pytest.raises(ShopNotConfigured, match="cannot be read: UnicodeDecodeError"):
        read_credentials(creds["path"], ignored=lambda p: True)
