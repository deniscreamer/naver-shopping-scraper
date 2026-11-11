"""A wide look at ShopNShip's calculator for conditions the tariff model may miss (the owner, 2026-11-11).

Not part of the price path: a research tool. It asks boxes chosen to cross every line we know of (length, second
side, length and girth, volume, the weight steps, the table's end), in both orders of magnitude, and compares each
FedEx answer with what delivery_tariff.py predicts from the recorded table. A row where they differ is a condition
the model does not have. Other carriers' answers are kept raw for later reading.

    .venv/bin/python scripts/shopnship_explore.py run --out scripts/output/shopnship     # one request a second
    .venv/bin/python scripts/shopnship_explore.py run --out scripts/output/shopnship \
        --rows scripts/fixtures/shopnship/explore-round2-rows.json                       # the second round's rows
    .venv/bin/python scripts/shopnship_explore.py report scripts/output/shopnship/shopnship-explore-us-<time>.json

The two explorations of 2026-11-11 (427 requests, every modelled answer equal to the model but one weight of 17
digits the server reads as a binary number) are in
scripts/fixtures/shopnship/; test_delivery_tariff.py replays them while the tariff is of that day.

Each row: {group, form (the fields as sent), note}; the answer adds raw, usd, predicted (our base in USD or None),
match. Special rows send forms the client's `fields` would refuse (no sides, pounds and inches): how the
calculator treats them is part of the question.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import delivery_tariff as DT
import shopnship_rates as SR

FORMAT = "shopnship-explore/1"
LB, INCH = Decimal("0.45359237"), Decimal("2.54")


def _form(length: Any, width: Any, height: Any, weight: Any) -> dict[str, str]:
    return SR.fields(length, width, height, weight)


def rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(group: str, form: dict[str, str], note: str = "") -> None:
        out.append({"group": group, "form": form, "note": note})

    # A. one long side grows; the cross-section and the gross weight stay
    for length in list(range(50, 301, 10)) + [118, 119, 121, 122, 123, 125, 149, 151, 152, 153, 243, 244, 273, 274, 275]:
        add("length", _form(length, 20, 16, 6))
    for length in (100, 150, 200, 250, 274, 275, 300, 330, 400):
        add("length_thin", _form(length, 10, 10, 1), "a thin box: little volume, a long side")
    # B. the second side
    for width in (40, 50, 60, 70, 75, 76, 77, 78, 80, 90, 100):
        add("second_side", _form(100, width, 10, 2))
    # C. length and girth, volume: a square cross-section grows
    for side in (25, 30, 35, 38, 40, 41, 41.2, 41.3, 41.5, 42, 43, 45, 48, 50):
        add("girth", _form(100, side, side, 3), "100 + 4 x side; volume 100 x side^2")
    big: list[tuple[Any, Any, Any]] = [
        (200, 30, 30), (200, 33, 33), (200, 35, 35), (250, 20, 20), (260, 20, 20), (150, 40, 40), (160, 39, 39),
        (120, 45, 45), (60, 60, 47), (88, 44, 44), (88, 44, 43.5), (70, 60, 55), (55, 55, 55), (56, 56, 56)]
    for a, b, c in big:
        add("big", _form(a, b, c, 5))
    # D. the same box, the sides named in another order
    for box in ((124, 20, 16), (20, 124, 16), (16, 20, 124), (20, 16, 124), (123, 40, 32), (32, 123, 40), (40, 32, 123)):
        add("order", _form(*box, 6))
    # E. gross against volume: which one pays, on both sides of 20, 25 and 32 kg
    volumes = {"5": (50, 25, 20), "12": (60, 40, 25), "19.5": (65, 50, 30), "20.2": (101, 50, 20),
               "25.5": (85, 50, 30), "33": (110, 50, 30), "48": (120, 50, 40)}
    for name, box in volumes.items():
        for gross in ("1", "10", "20", "26", "30", "45"):
            add("gross_or_volume", _form(*box, gross), f"volumetric {name} kg")
    # F. the weight in small steps across step borders and the table's uneven places
    def sweep(first: str, last: str, step: str) -> list[Decimal]:
        values, at = [], Decimal(first)
        while at <= Decimal(last):
            values.append(at)
            at += Decimal(step)
        return values
    for weight in sweep("5", "6", "0.05") + sweep("16", "17", "0.1") + sweep("20", "22", "0.1") + \
            sweep("24.5", "26.5", "0.1") + sweep("32", "34", "0.25") + sweep("49", "51", "0.25"):
        add("weight_sweep", _form(10, 10, 10, weight))
    for edge in ("0.01", "0.05", "0.2", "60", "68", "69", "100"):
        add("weight_edge", _form(10, 10, 10, edge))
    # G. a long box that is also heavy: does a heavy long box cost more than its weight step
    for gross in ("8", "10.8", "12", "18", "18.1", "25", "25.1", "26", "30", "45"):
        add("long_heavy", _form(124, 20, 16, gross))
    for gross in ("31", "32", "33", "40", "50"):
        add("long_heavy", _form(123, 40, 32, gross))
    # H. forms the client would not send
    for kilos in ("1", "6", "30"):
        add("no_sides", {"country": "US", "danwe": "1", "weight": kilos}, "weight only: the page asks for no sides")
        add("no_sides", {"country": "US", "danwe": "1", "length": "", "width": "", "height": "", "weight": kilos},
            "empty sides")
    add("no_sides", {"country": "US", "danwe": "1", "length": "0", "width": "0", "height": "0", "weight": "6"}, "zero sides")
    add("no_sides", {"country": "US", "danwe": "1", "length": "124", "width": "", "height": "", "weight": "6"},
        "one side only")
    for cm, kg in (((124, 20, 16), "6"), ((123, 40, 32), "10"), ((10, 10, 10), "2.005"), ((60, 40, 25), "1")):
        inches = [format((Decimal(str(v)) / INCH).quantize(Decimal("0.0001")), "f") for v in cm]
        pounds = format((Decimal(kg) / LB).quantize(Decimal("0.0001")), "f")
        add("pounds_inches", {"country": "US", "danwe": "2", "length": inches[0], "width": inches[1],
                              "height": inches[2], "weight": pounds}, f"the box {cm} cm, {kg} kg in lb and in")
    return out


def predicted(form: dict[str, str]) -> str | None:
    """Our base for a row's form by the recorded table; None = no price (over the table) or a form we do not model."""
    if form.get("danwe") != "1" or form.get("country", "US") != "US":
        return None
    try:
        box = DT.Box(form.get("length"), form.get("width"), form.get("height"), form.get("weight"))
        tariff = DT.load().tariffs["shopnship-fedex-ip-kr-us"]
        step = DT.step_kg(tariff, DT.billable_kg(tariff, box))
    except ValueError:
        return None
    return None if step is None else format(tariff.table[step], "f")


def run(country: str = "US", say: Any = print, todo: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    started, out, failed = datetime.now(timezone.utc), [], 0
    todo = rows() if todo is None else todo
    for i, row in enumerate(todo):
        entry: dict[str, Any] = {**row, "form": {"country": country, **row["form"]},
                                 "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        entry["predicted"] = predicted(entry["form"])
        try:
            entry["raw"] = SR.ask(entry["form"])
            entry["usd"] = {k: (None if v is None else str(v)) for k, v in SR.parse(entry["raw"]).items()}
            entry["match"] = entry["usd"]["fedex"] == entry["predicted"]
            failed = 0
        except SR.CalculatorError as e:
            entry["error"], failed = str(e), failed + 1
        out.append(entry)
        f = entry["form"]
        say(f"{i + 1}/{len(todo)} {row['group']} {f.get('length')}x{f.get('width')}x{f.get('height')} {f['weight']} -> "
            f"{entry.get('raw', entry.get('error'))} (ours {entry['predicted']})")
        if failed >= SR.GIVE_UP:
            say("stopped: the calculator does not answer")
            break
        if i + 1 < len(todo):
            time.sleep(SR.PAUSE)
    return {"format": FORMAT, "source": SR.URL, "country": country, "carriers": list(SR.CARRIERS),
            "started_at": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "finished_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "requests": out}


def report(data: dict[str, Any]) -> str:
    lines: list[str] = []
    asked: dict[str, int] = {}
    errors: dict[str, int] = {}
    differ: dict[str, list[dict[str, Any]]] = {}
    for r in data["requests"]:
        name = r["group"]
        asked[name] = asked.get(name, 0) + 1
        errors.setdefault(name, 0)
        differ.setdefault(name, [])
        if "error" in r:
            errors[name] += 1
        elif not r["match"]:
            differ[name].append(r)
    for name in asked:
        lines.append(f"{name}: {asked[name]} asked, {errors[name]} errors, {len(differ[name])} differ from the model")
        for r in differ[name]:
            f = r["form"]
            lines.append(f"   {f.get('length')}x{f.get('width')}x{f.get('height')} {f['weight']} (units {f['danwe']}): "
                         f"calculator {r['usd']['fedex']}, ours {r['predicted']}   raw {r['raw']}   {r.get('note', '')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--rows", help="a JSON file of rows [{group, form, note}] instead of the built-in list")
    p = sub.add_parser("report")
    p.add_argument("file")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        with open(a.file, encoding="utf-8") as f:
            print(report(json.load(f)))
        return 0
    os.makedirs(a.out, exist_ok=True)
    todo = None
    if a.rows:
        with open(a.rows, encoding="utf-8") as f:
            todo = json.load(f)
    data = run(todo=todo)
    path = os.path.join(a.out, f"shopnship-explore-us-{data['started_at'].replace('-', '').replace(':', '')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{path}: {len(data['requests'])} requests")
    print(report(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
