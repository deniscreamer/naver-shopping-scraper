"""Offline check that server/ is a working import root: every top-level
module resolves by its bare name and the route table is complete.

    python -m pytest server/test_import_smoke.py -q

The browser and transport modules import their heavy pieces lazily, so the
parser tests never touch them; this is what catches a module left behind by
a move. No Chrome is launched and nothing goes to the network.
"""
import importlib

import pytest

MODULES = ["browser_client", "cache", "config", "egress", "hostenv", "patchright_driver", "routes",
           "schema_fields", "scraper_errors", "url_blocking",
           "naver_shopping.api", "naver_shopping.cache_config", "naver_shopping.fetch",
           "naver_shopping.parsers", "naver_shopping.refs", "naver_shopping.schemas",
           "naver_shopping.composite", "ext_bridge", "notify"]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)


def test_routes_mounted():
    import bottle
    import routes

    rules = {r.rule for r in bottle.default_app().routes}
    for path, *_ in routes.ENDPOINTS:
        assert path in rules and "/" + routes.SITE + path in rules
    assert {"/", "/health"} <= rules
    # 11 endpoints at both prefixes, plus / and /health
    assert len(rules) == 2 * len(routes.ENDPOINTS) + 2 == 24
