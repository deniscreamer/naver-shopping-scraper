"""Offline tests for shopnship_rates.py: a fake calculator and a saved capture, no network.

    .venv/bin/python -m pytest scripts/test_shopnship_rates.py -q
"""
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import requests

import delivery_tariff as DT
import shopnship_rates as SR

HERE = os.path.dirname(os.path.abspath(__file__))


class Calculator:
    """Answers in order (a text, a status code or an exception); records each call's form."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, url, files, timeout):
        self.calls.append({k: v[1] for k, v in files.items()})
        assert url == SR.URL and timeout == SR.TIMEOUT and all(v[0] is None for v in files.values())
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        code, text = (answer, "") if isinstance(answer, int) else (200, answer)
        return type("R", (), {"status_code": code, "text": text})()


def test_the_form_is_the_pages_form():
    assert SR.fields(20, 15, 10, 0.5) == {"country": "US", "danwe": "1", "length": "20", "width": "15",
                                          "height": "10", "weight": "0.5"}
    assert SR.fields("124.5", 20, 16, Decimal("1E+1"))["weight"] == "10"                  # never an exponent


@pytest.mark.parametrize("box", [(0, 15, 10, 1), (20, -1, 10, 1), (20, 15, "x", 1), (20, 15, 10, "nan"),
                                 (20, 15, 10, "inf"), (20, 15, 10, None)])
def test_a_box_needs_positive_numbers(box):
    with pytest.raises(ValueError):
        SR.fields(*box)


def test_the_country_is_a_two_letter_code():
    for bad in ("", "us", "USA", None, 5, ["US"]):
        with pytest.raises(ValueError, match="country"):
            SR.fields(20, 15, 10, 1, bad)


def test_the_answer_is_five_prices_in_the_pages_order():
    assert SR.parse("0.00/48.51/0.00/0.00/27.46") == {
        "dhl": None, "fedex": Decimal("48.51"), "ems": None, "ems_premium": None,
        "shopnship_standard": Decimal("27.46")}
    assert SR.parse(" 1,234.50/0/0/0/0 \n")["dhl"] == Decimal("1234.50")
    assert SR.parse("0/0/0/0/0") == dict.fromkeys(SR.CARRIERS)


@pytest.mark.parametrize("text", ["", "error", "0.00/48.51/0.00/0.00", "0.00/48.51/0.00/0.00/27.46/1.00",
                                  "0.00/abc/0.00/0.00/27.46", "<html>0/0/0/0/0</html>", "0.00/-1/0.00/0.00/27.46",
                                  "0.00/48.512/0.00/0.00/27.46", None, 5, "0.00/48,51/0.00/0.00/27,46",
                                  "0,00/1,23/0/0/0", "1,2,3.4/0/0/0/0", "0/٤٨.٥١/0/0/0", "0/20000.00/0/0/0",
                                  "\ufeff0.00/48.51/0.00/0.00/27.46"])
def test_anything_else_is_an_error_not_a_price(text):
    with pytest.raises(SR.CalculatorError, match="unexpected"):
        SR.parse(text)


def test_a_price_not_offered_and_a_failure_stay_apart():
    assert SR.quote(20, 15, 10, 0.5, post=Calculator("0.00/48.51/0.00/0.00/27.46"))["fedex"] == Decimal("48.51")
    assert SR.quote(20, 15, 10, 60, post=Calculator("0.00/0.00/0.00/0.00/0.00"))["fedex"] is None
    with pytest.raises(SR.CalculatorError):
        SR.ask(SR.fields(20, 15, 10, 1), Calculator(404), sleep=lambda s: None)


def test_a_network_error_or_a_5xx_is_tried_again_and_a_4xx_is_not():
    waits = []
    calc = Calculator(requests.ConnectionError("down"), 503, "0.00/48.51/0.00/0.00/27.46")
    assert SR.ask(SR.fields(20, 15, 10, 1), calc, waits.append) == "0.00/48.51/0.00/0.00/27.46"
    assert len(calc.calls) == 3 and len(waits) == 2
    calc = Calculator(503)
    with pytest.raises(SR.CalculatorError, match="HTTP 503"):
        SR.ask(SR.fields(20, 15, 10, 1), calc, lambda s: None)
    assert len(calc.calls) == SR.RETRIES
    calc = Calculator(403)
    with pytest.raises(SR.CalculatorError, match="HTTP 403"):
        SR.ask(SR.fields(20, 15, 10, 1), calc, lambda s: None)
    assert len(calc.calls) == 1


def test_the_grid_asks_each_thing_once():
    rows = SR.grid()
    assert len(rows) == 198 and len({json.dumps(r, sort_keys=True) for r in rows}) == 198
    assert {r["group"] for r in rows} == {"table", "above", "rounding", "volume", "sides", "long", "examples"}
    tariff = DT.load().for_shop("fairwardgolf")
    with open(os.path.join(HERE, tariff.row["source"]), encoding="utf-8") as f:           # the saved capture asked
        asked = [{k: r[k] for k in ("group", "length", "width", "height", "weight")} for r in json.load(f)["requests"]]
    assert asked == rows                                                                  # exactly this grid
    assert [r["weight"] for r in rows if r["group"] == "table"][::13] == ["0.5", "7.0", "13.5", "20.0"]


def test_a_capture_keeps_every_raw_answer_and_goes_on_after_a_failure():
    rows = [{"group": "table", "length": "10", "width": "10", "height": "10", "weight": w} for w in ("1", "2", "3")]
    calc, waits = Calculator("0.00/48.51/0.00/0.00/27.46", 403, "0.00/75.79/0.00/0.00/0.00"), []
    at = datetime(2026, 11, 11, 7, 0, 0, tzinfo=timezone.utc)
    data = SR.capture("US", rows, calc, waits.append, now=lambda: at)
    assert (data["format"], data["country"], data["started_at"]) == (SR.FORMAT, "US", "2026-11-11T07:00:00Z")
    assert data["carriers"] == list(SR.CARRIERS) and [c["weight"] for c in calc.calls] == ["1", "2", "3"]
    first, second, third = data["requests"]
    assert first["raw"] == "0.00/48.51/0.00/0.00/27.46" and first["usd"]["fedex"] == "48.51" and first["usd"]["dhl"] is None
    assert "HTTP 403" in second["error"] and "raw" not in second
    assert third["usd"] == {"dhl": None, "fedex": "75.79", "ems": None, "ems_premium": None, "shopnship_standard": None}
    assert waits == [SR.PAUSE, SR.PAUSE] and "stopped" not in data          # a pause between requests, none after


def test_a_capture_stops_when_the_site_does_not_answer():
    rows = [{"group": "table", "length": "10", "width": "10", "height": "10", "weight": str(w)} for w in range(1, 9)]
    calc = Calculator("0.00/48.51/0.00/0.00/27.46", 429)                   # one answer, then refusals
    data = SR.capture("US", rows, calc, lambda s: None)
    assert len(calc.calls) == 1 + SR.GIVE_UP and len(data["requests"]) == 1 + SR.GIVE_UP
    assert data["stopped"] == "3 rows in a row without an answer; 4 rows not asked"
    calc = Calculator("<html>maintenance</html>")
    assert len(SR.capture("US", rows, calc, lambda s: None)["requests"]) == SR.GIVE_UP
    calc = Calculator()
    with pytest.raises(ValueError, match="weight"):                        # a bad row stops before any request
        SR.capture("US", rows + [{**rows[0], "weight": "0"}], calc, lambda s: None)
    assert calc.calls == []


def test_a_capture_is_compared_with_the_recorded_table(tmp_path, capsys):
    tariff = DT.load().for_shop("fairwardgolf")
    source = os.path.join(HERE, tariff.row["source"])
    with open(source, encoding="utf-8") as f:
        captured = json.load(f)
    assert SR.differences(captured, tariff.row["table"]) == []
    assert SR.main(["compare", source]) == 0 and "the same 71 steps" in capsys.readouterr().out
    for r in captured["requests"]:
        if r["group"] == "table" and r["weight"] == "8.0":
            r["usd"]["fedex"] = "140.00"
    captured["requests"] = [r for r in captured["requests"] if r["weight"] not in ("49.5", "50.0", "50.004")]
    changed = tmp_path / "new.json"
    changed.write_text(json.dumps(captured), encoding="utf-8")
    assert SR.differences(captured, tariff.row["table"]) == [
        "8 kg: recorded 136.12, captured 140.00", "50 kg: recorded 809.67, captured no step"]
    assert SR.main(["compare", str(changed)]) == 1 and "8 kg: recorded 136.12" in capsys.readouterr().out


def test_the_recorded_tariff_is_the_saved_captures_table():
    tariff = DT.load().for_shop("fairwardgolf")
    with open(os.path.join(HERE, tariff.row["source"]), encoding="utf-8") as f:
        captured = json.load(f)
    assert captured["format"] == SR.FORMAT and not [r for r in captured["requests"] if "error" in r]
    assert SR.table(captured) == tariff.row["table"]
    assert captured["started_at"][:10] == tariff.row["checked_at"]


def test_one_step_per_price_named_by_its_heaviest_weight():
    rows = [{"group": "above", "weight": w, "usd": {"fedex": usd}} for w, usd in
            (("20.5", "301.36"), ("21.0", "327.00"), ("21.5", "343.42"), ("22.0", "343.42"), ("51", None))]
    assert SR.table({"requests": rows + [{"group": "long", "weight": "6", "usd": {"fedex": "1.00"}},
                                         {"group": "above", "weight": "23", "error": "x"}]}) == {
        "20.5": "301.36", "21": "327.00", "22": "343.42"}


def test_the_command_line(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(SR.requests, "post", Calculator("0.00/48.51/0.00/0.00/27.46"))
    assert SR.main(["quote", "20", "15", "10", "0.5"]) == 0
    out = capsys.readouterr().out
    assert "fedex" in out and "48.51" in out and "not offered" in out
    assert SR.main(["quote", "20", "15", "10", "0"]) == 1 and "positive" in capsys.readouterr().err
    assert SR.main(["capture", "--out", str(tmp_path / "no"), "--country", "usa"]) == 1
    assert "country" in capsys.readouterr().err and not (tmp_path / "no").exists()
    monkeypatch.setattr(SR, "grid", lambda: [{"group": "table", "length": "10", "width": "10", "height": "10",
                                              "weight": "1"}])
    monkeypatch.setattr(SR.time, "sleep", lambda s: None)
    assert SR.main(["capture", "--out", str(tmp_path)]) == 0
    (name,) = os.listdir(tmp_path)
    assert name.startswith("shopnship-us-") and json.load(open(tmp_path / name))["requests"][0]["usd"]["fedex"] == "48.51"


def test_the_network_is_closed_for_every_test():
    import socket
    for attempt in (lambda: socket.create_connection(("127.0.0.1", 9)), lambda: socket.getaddrinfo("example.com", 80),
                    lambda: socket.socket().connect_ex(("127.0.0.1", 9)), lambda: requests.get("http://127.0.0.1:9")):
        with pytest.raises(AssertionError, match="network"):
            attempt()
