"""Example 1: is the API up, and is the browser extension connected?

    .venv/bin/python server/run.py            # in another terminal
    .venv/bin/python scripts/example_01_health.py
"""
from naver_api_client import NaverApiClient

api = NaverApiClient()                        # NAVER_API_URL or http://localhost:8000
health = api.health()

print("status:   ", health["status"])
print("extension:", health["extension"])     # connected = /listings can run
print("endpoints:", ", ".join(health["endpoints"]))
