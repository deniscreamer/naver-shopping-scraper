"""ShopNShip's public shipping calculator: one quote, and a dated capture of the rate grid (the owner, 2026-11-11).

ShopNShip is the shop's forwarding partner in Korea. Its calculator page
(https://shopnship.co.kr/en/help/shipping_calculator.php) posts the form to /form/calculator.php and gets one line
of text back: five prices in USD separated by "/", in the order of the page's script (read 2026-11-11):
DHL / FedEx / EMS / EMS Premium (K-Packet) / ShopNShip Standard. "0.00" = the calculator gave no price of that
carrier for this box (FedEx to the US: every box over 50 kg; EMS: all but one of the boxes asked).
No login, no cookie, no key. The form sends the country, the unit system (danwe 1 = kg and cm), the box's outer
sides and its gross weight; the calculator takes the volumetric weight into account itself.

    .venv/bin/python scripts/shopnship_rates.py quote 124 20 16 6                  # one box: every carrier's price
    .venv/bin/python scripts/shopnship_rates.py capture --out scripts/output/shopnship  # the grid, kept as a file
    .venv/bin/python scripts/shopnship_rates.py compare scripts/output/shopnship/shopnship-us-<time>.json

A capture adopted as the tariff is copied to scripts/fixtures/shopnship/ (tracked: the backup a later capture is
compared with), delivery_tariffs.json gets the new table, source, checked_at, version and a history line. The
review is by hand (the owner, 2026-11-11).

A capture keeps every request with the answer's raw text, so a tariff table can always be traced to what the
calculator said on that day. Requests go one at a time with a pause, and a capture stops after three rows in a
row without an answer: it is a partner's public page.
Tests never call it (test_shopnship_rates.py uses a fake calculator and a saved capture; conftest.py closes the
network for the whole folder).
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import requests

URL = "https://shopnship.co.kr/form/calculator.php"
PAGE = "https://shopnship.co.kr/en/help/shipping_calculator.php"
CARRIERS = ("dhl", "fedex", "ems", "ems_premium", "shopnship_standard")     # the answer's five fields, in order
UNITS_KG_CM = "1"                                                          # the form's danwe: 1 = kg / cm, 2 = lb / in
TIMEOUT, PAUSE, RETRIES = 15, 1.0, 3
GIVE_UP = 3                 # a capture stops after this many rows in a row without an answer
PRICE_MAX = Decimal(10000)  # a price over this is a misread answer, not a price
FORMAT = "shopnship-capture/1"
_PRICE_RE = re.compile(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?")      # 48.51, 1,234.50; never 48,51


class CalculatorError(Exception):
    """The calculator did not answer, or answered something that is not five prices."""


def _number(name: str, value: Any) -> str:
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        raise ValueError(f"{name} must be a number, got {value!r}") from None
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value!r}")
    return format(number, "f")                      # a plain decimal with a point, never an exponent


def fields(length_cm: Any, width_cm: Any, height_cm: Any, weight_kg: Any, country: str = "US") -> dict[str, str]:
    """The form's fields for one packed box: outer sides in cm, gross weight in kg."""
    if not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError(f"country must be a two-letter code, got {country!r}")
    return {"country": country, "danwe": UNITS_KG_CM, "length": _number("length", length_cm),
            "width": _number("width", width_cm), "height": _number("height", height_cm),
            "weight": _number("weight", weight_kg)}


def parse(text: str) -> dict[str, Decimal | None]:
    """The answer's five prices by carrier; None = no price of that carrier for this box (0.00). A comma is read
    only as a thousands separator ("1,234.50"): "48,51" is not a price."""
    parts = [p.strip() for p in (text if isinstance(text, str) else "").split("/")]
    if len(parts) != len(CARRIERS) or any(not _PRICE_RE.fullmatch(p) for p in parts):
        raise CalculatorError(f"unexpected calculator answer: {str(text)[:120]!r}")
    prices = [Decimal(p.replace(",", "")) for p in parts]
    if any(p > PRICE_MAX for p in prices):
        raise CalculatorError(f"unexpected calculator answer (a price over {PRICE_MAX}): {text[:120]!r}")
    return {name: (p if p > 0 else None) for name, p in zip(CARRIERS, prices)}


def ask(form: dict[str, str], post: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] | None = None) -> str:
    """The answer's raw text for one form. A network error or a 5xx is tried again; anything else stops."""
    post, sleep, last = post or requests.post, sleep or time.sleep, ""
    for attempt in range(RETRIES):
        try:
            response = post(URL, files={k: (None, v) for k, v in form.items()}, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = f"{type(e).__name__}: {e}"
        else:
            if response.status_code == 200:
                return response.text
            last = f"HTTP {response.status_code}"
            if response.status_code < 500:
                break
        if attempt + 1 < RETRIES:
            sleep(PAUSE * (attempt + 2))
    raise CalculatorError(f"no answer from the calculator: {last}")


def quote(length_cm: Any, width_cm: Any, height_cm: Any, weight_kg: Any, country: str = "US",
          post: Callable[..., Any] | None = None) -> dict[str, Decimal | None]:
    """Every carrier's price in USD for one box (None = not offered). Raises CalculatorError when there is no
    answer, so the three outcomes stay apart: a price, not offered, failed."""
    return parse(ask(fields(length_cm, width_cm, height_cm, weight_kg, country), post))


# --- the capture ------------------------------------------------------------------------------------------------

SMALL = (10, 10, 10)        # 0.2 kg volumetric: the gross weight alone sets the step


def _steps(first: str, last: str, step: str) -> list[Decimal]:
    out, at = [], Decimal(first)
    while at <= Decimal(last):
        out.append(at)
        at += Decimal(step)
    return out


def grid() -> list[dict[str, Any]]:
    """What a capture asks, each row {group, length, width, height, weight}:
    table      the weight steps by gross weight in a small box (0.5 kg steps to 20 kg);
    above      the same above 20 kg, where the owner's table stops (0.5 kg steps to 50 kg, 1 kg steps to 70 kg);
    rounding   weights just under, on and over a step, up to the table's end: how the billable weight is rounded;
    volume     boxes whose volumetric weight sets the step, against the same step by gross weight, to the end;
    sides      a fraction of a centimetre in each side: is a side rounded up before the volume;
    long       boxes around the fee's lines (121 cm, a second side of 76 cm): is the fee inside the price;
    examples   the owner's eleven packing examples."""
    rows: list[dict[str, Any]] = []

    def add(group: str, box: tuple[Any, ...], weight: Any) -> None:
        length, width, height = box
        rows.append({"group": group, "length": str(length), "width": str(width), "height": str(height),
                     "weight": str(weight)})

    for step in _steps("0.5", "20", "0.5"):
        add("table", SMALL, step)
    for step in _steps("20.5", "50", "0.5") + _steps("51", "70", "1"):
        add("above", SMALL, step)
    for weight in ("0.1", "0.49", "0.51", "1.004", "1.005", "1.006", "2.001", "2.004", "2.005", "2.006", "2.01",
                   "2.49", "2.499", "2.5", "2.501", "19.99", "20.001", "20.004", "20.005", "20.006", "20.01",
                   "20.49", "20.51", "21.004", "21.005", "21.006", "21.01", "30.01", "30.49", "50.004", "50.006",
                   "50.01", "50.5"):
        add("rounding", SMALL, weight)
    by_volume: list[tuple[Any, ...]] = [
        (41.7, 30, 20), (41.75, 30, 20), (41.8, 30, 20), (50, 25, 20), (50.1, 25, 20),     # 5.004 5.01 5.016 5.0 5.01
        (60, 40, 25), (124, 20, 16), (110, 25, 22), (100, 50, 40), (100, 50, 40.1), (123, 40, 32),
        (125, 35, 35), (126, 44, 36), (127, 45, 37), (135, 40, 35),
        (55, 35, 13),                                                                      # 5.005 exactly
        (100, 50, 50), (100, 50, 50.1), (100, 60, 50)]                                     # 50.0 50.1 60.0: the end
    for box in by_volume:
        add("volume", box, "1")
    by_side: list[tuple[Any, ...]] = [
        (100, 20, 12.4), (100, 20, 12.5), (100, 20, 12.6), (100, 20, 13), (100.4, 20, 12),
        (100, 12.4, 20), (100, 12.6, 20), (104.1, 20, 12)]              # the width and the length with a fraction
    for box in by_side:
        add("sides", box, "1")
    for length in (120, 121, 122, 124, 127):
        add("long", (length, 20, 16), "6")
    add("long", (80, 77, 6), "1")                                       # second side over 76 cm: 7.39 kg
    add("long", (80, 75, 6.16), "1")                                    # the same volume under every line
    examples: list[tuple[tuple[Any, ...], str]] = [
        ((16, 12, 8), "0.35"), ((22, 16, 12), "0.9"), ((28, 22, 17), "1.5"), ((25, 16, 13), "1.25"),
        ((30, 22, 16), "2.45"), ((28, 22, 8), "0.5"), ((35, 27, 12), "1.1"), ((115, 12, 12), "1.5"),
        ((110, 25, 22), "5"), ((125, 35, 35), "12"), ((135, 40, 35), "15")]
    for box, weight in examples:
        add("examples", box, weight)
    return rows


def capture(country: str = "US", rows: list[dict[str, Any]] | None = None, post: Callable[..., Any] | None = None,
            sleep: Callable[[float], None] | None = None, now: Callable[[], datetime] | None = None,
            say: Callable[[str], None] = lambda s: None) -> dict[str, Any]:
    """Every row of the grid asked once, in order, with the raw answer kept. A row that fails keeps its error and
    the capture goes on: the file says what was not learned. After GIVE_UP failed rows in a row the capture stops
    (`stopped`): the site is down or refusing, and asking the rest would only press on it."""
    clock, sleep = now or (lambda: datetime.now(timezone.utc)), sleep or time.sleep
    started, out, failed, stopped = clock(), [], 0, None
    rows = grid() if rows is None else rows
    forms = [fields(r["length"], r["width"], r["height"], r["weight"], country) for r in rows]    # all checked first
    for i, (row, form) in enumerate(zip(rows, forms)):
        entry: dict[str, Any] = {**row, "at": clock().strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            entry["raw"] = ask(form, post, sleep)
            entry["usd"] = {k: (None if v is None else str(v)) for k, v in parse(entry["raw"]).items()}
            failed = 0
        except CalculatorError as e:
            entry["error"], failed = str(e), failed + 1
        out.append(entry)
        say(f"{i + 1}/{len(rows)} {row['group']} {row['length']}x{row['width']}x{row['height']} {row['weight']} kg -> "
            f"{entry.get('raw', entry.get('error'))}")
        if failed >= GIVE_UP:
            stopped = f"{failed} rows in a row without an answer; {len(rows) - len(out)} rows not asked"
            say(f"stopped: {stopped}")
            break
        if i + 1 < len(rows):
            sleep(PAUSE)
    data = {"format": FORMAT, "source": URL, "page": PAGE, "country": country, "units": "kg, cm",
            "carriers": list(CARRIERS), "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_at": clock().strftime("%Y-%m-%dT%H:%M:%SZ"), "requests": out}
    if stopped:
        data["stopped"] = stopped
    return data


def table(captured: dict[str, Any], carrier: str = "fedex") -> dict[str, str]:
    """{weight step: USD} for one carrier, from a capture's small-box rows (the gross weight alone sets the
    price there). Weights asked in a row at one price are one step, named by the heaviest of them (21.5 and 22 kg
    cost the same: the step is 22 kg). A weight the carrier does not offer, or a failed row, is left out.
    Proven for FedEx only (every other row of the capture is explained by this table); another carrier may count
    the volume in another way."""
    rows = sorted(((Decimal(r["weight"]), r["usd"][carrier]) for r in captured["requests"]
                   if r["group"] in ("table", "above") and r.get("usd") and r["usd"].get(carrier)),
                  key=lambda x: x[0])
    out: dict[str, str] = {}
    for i, (weight, usd) in enumerate(rows):
        if i + 1 == len(rows) or rows[i + 1][1] != usd:
            out[str(weight.normalize() if weight != weight.to_integral() else weight.quantize(Decimal(1)))] = usd
    return out


def differences(captured: dict[str, Any], recorded: dict[str, str], carrier: str = "fedex") -> list[str]:
    """Where a capture's steps differ from a recorded table ({step: USD}): a new price, a new step, a lost step."""
    new, out = table(captured, carrier), []
    for step in sorted(set(new) | set(recorded), key=Decimal):
        if new.get(step) != recorded.get(step):
            out.append(f"{step} kg: recorded {recorded.get(step, 'no step')}, captured {new.get(step, 'no step')}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("quote", help="one box: every carrier's price")
    for name in ("length", "width", "height", "weight"):
        q.add_argument(name)
    q.add_argument("--country", default="US")
    c = sub.add_parser("capture", help="ask the whole grid and keep the answers in a dated file")
    c.add_argument("--out", required=True, help="the folder for shopnship-<country>-<UTC time>.json")
    c.add_argument("--country", default="US")
    m = sub.add_parser("compare", help="a capture file against the recorded tariff's table (exit 1 on a difference)")
    m.add_argument("capture")
    m.add_argument("--tariff", default="shopnship-fedex-ip-kr-us")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        import delivery_tariff                      # the recorded table lives with the calculator
        with open(a.capture, encoding="utf-8") as f:
            captured = json.load(f)
        diff = differences(captured, delivery_tariff.load().tariffs[a.tariff].row["table"])
        print("\n".join(diff) if diff else f"{a.capture}: the same {len(table(captured))} steps as {a.tariff}")
        return 1 if diff else 0
    if a.cmd == "quote":
        try:
            prices = quote(a.length, a.width, a.height, a.weight, a.country)
        except (CalculatorError, ValueError) as e:
            print(f"failed: {e}", file=sys.stderr)
            return 1
        for name, usd in prices.items():
            print(f"{name:20} {'not offered' if usd is None else usd}")
        return 0
    try:
        fields(1, 1, 1, 1, a.country)               # a bad country stops here, before the folder and the network
    except ValueError as e:
        print(f"failed: {e}", file=sys.stderr)
        return 1
    os.makedirs(a.out, exist_ok=True)
    data = capture(a.country, say=print)
    stamp = data["started_at"].replace("-", "").replace(":", "")
    path = os.path.join(a.out, f"shopnship-{a.country.lower()}-{stamp}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    failed = sum(1 for r in data["requests"] if "error" in r)
    print(f"{path}: {len(data['requests'])} requests, {failed} failed" + (f"; {data['stopped']}" if "stopped" in data else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
