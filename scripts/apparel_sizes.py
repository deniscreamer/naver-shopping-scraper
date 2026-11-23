"""Korean apparel sizes -> US sizes, per product (the owner, 2026-11-19; the doc: scripts/SIZES.md).

Pure and offline. `resolve()` takes what one prepared product says about its sizes and returns the size option's US
values, the Korean value each came from, and the seller's garment measurements; transform.prepare stores it as
product.sizes (CategoryRules.sizes names the profile), shopify_payload shows it (the option values, the size chart
block, the variants' and the product's fairwardgolf metafields). The Korean values never reach the storefront.

Inputs (each optional except the options):
  options        the prepared options [{name_ko, values_ko}]: the size option is found by its values, not its name
                 (13665521998 "PIL[핑크]" holds XS-L);
  texts          the description's text lines and the OCR rows of its images: the seller's own size chart;
  brand, title   for a brand row (the profile's "brands");
  profile        the garment kind (size_profiles/<name>.json: its fallback grid, its brands, its measures).

One value's Korean chest (cm of body chest, the number Korean labels carry) is taken, in order, from:
  1. the seller's chart, a "US" row (an explicit US size per column): the US letter as written; then a brand row
     with system "us" (PXG): its letter is the US letter;
  2. the value itself: "90", "M(90)", "0(85)", "S(55)" (women's 55 -> 90 by the profile's kr_women), "L(55-66)";
  3. the seller's chart pairing a letter with a number ("85 (S)", "Size / XS / S" over "Korea Size / 85 / 90");
  4. the brand row's letters (WAAC S = 90); a letter range "S/M" takes both letters' chests;
  5. the profile's letters (S = 90): the fallback, said in `basis`.
FREE / F / 프리 is One Size. A value none of these reads, or two Korean sizes landing on one US size, holds the product
(size_unmapped): an invented size is worse than none.
"""
import json
import re
from pathlib import Path
from typing import Any, Callable

from size_chart import NOT_CHART_RE, ONE, Chart, measure_names, read_chart  # noqa: F401  (re-exported: the callers' one module)
from size_labels import Label, is_size_name, parse_label, waist_labels  # noqa: F401

_COLOUR_NAME_RE = re.compile(r"색상|컬러|칼라|색깔|color|colour", re.I)    # not a type's section (size_chart sections)
# a colour value under any option name ("선택: 블랙 / 네이비"): never a type's section
_COLOUR_VALUE_RE = re.compile(r"블랙|화이트|아이보리|네이비|그레이|회색|베이지|브라운|카키|그린|민트|블루|스카이|레드|와인|버건디|핑크|"
                              r"퍼플|옐로우|오렌지|차콜|크림|카멜|실버|골드|색$|black|white|navy|gr[ae]y|beige|pink|blue|red",
                              re.I)
PROFILES_DIR = Path(__file__).with_name("size_profiles")    # one <name>.json a garment profile, its <name>.md
VERSION = "sizes/2"                          # bump on a change of what resolve() returns
# a letter paired with a Korean women's size in the seller's text or OCR, outside any chart row: "L[55~66]/XL[77]",
# "M(55), L(66), XL(77)", an OCR row "L(55-66) / 48 / 20 / 58" whose measures are not read (2026-11-20 review:
# 10036686854, 11016233632, 12220300865); the label's own parse decides what the token is
_LETTER_ALT = r"XXXL|3XL|XXL|2XL|XXS|2XS|XS|XL|LL|S|M|L"      # deliberately narrow: these sellers' letters
_WOMEN_TOKEN = r"\d{2}(?:\.5|반)?(?:\s*[-~]\s*\d{2}(?:\.5|반)?)?"
# the closing bracket ends a pair: a letter right after it is the next pair ("M(55)L(66)", the OCR glued them:
# Toosom 12566658191 sold M as US M, one size too big, 2026-11-21); a digit after it is no pair
_TEXT_PAIR_RE = re.compile(rf"(?<![A-Za-z0-9])(?:(?:{_LETTER_ALT})\s*[(\[]\s*{_WOMEN_TOKEN}\s*[)\]]|"
                           rf"{_WOMEN_TOKEN}\s*[(\[]\s*(?:{_LETTER_ALT})\s*[)\]])(?!\d)", re.I)
# the same letters, for a value whose colour and size are joined ("Ivory/085", "블랙 100 L": 12487887784, 10940191023)
_JOIN_SPLIT_RE = re.compile(r"[\s/_]+")             # "_" too: "티셔츠 55_아이보리" (6354978708, 2026-11-21)

# --- resolving -----------------------------------------------------------------------------------------------------

def grids(folder: Path = PROFILES_DIR) -> dict[str, Any]:
    """{"profiles": {name: profile}}: every size_profiles/<name>.json (format size-profile/1)."""
    out: dict[str, Any] = {}
    for f in sorted(folder.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("format") != "size-profile/1" or data.get("name") != f.stem:
            raise ValueError(f"{f}: not a size profile named {f.stem}")
        out[f.stem] = data
    return {"profiles": out}


def _norm(text: str | None) -> str:
    return re.sub(r"[\s\[\]()]+", "", str(text or "")).upper()


def brand_row(profile: dict[str, Any], brand: str | None, title: str | None) -> tuple[str, dict[str, Any]] | None:
    """The brand's row: brand_ko equal to an alias; else (no brand_ko row matched) the title starting with an alias
    as a word of its own ("[왁] 여성 ...", "PXG 여성 ..."; never "왁스 코팅 ...")."""
    rows = [(name, row) for name, row in profile.get("brands", {}).items() if not name.startswith("_")]
    b = _norm(brand)
    for name, row in rows:
        if b and any(_norm(a) == b for a in row.get("aliases", [])):
            return name, row
    lead = re.sub(r"^[\s\[(]+", "", str(title or "")).upper()
    for name, row in rows:
        for alias in row.get("aliases", []):
            a = alias.upper()
            if len(a) >= 1 and lead.startswith(a) and (len(lead) == len(a) or not re.match(r"[가-힣A-Z0-9]", lead[len(a)])):
                return name, row
    return None


def size_option(options: list[dict[str, Any]]) -> int | None:
    """The option whose every value is a size label (the last such, a colour comes first); else one named a size
    (사이즈 / size) or with most of its values sizes: resolve() holds it on the value it cannot read, rather than send
    "L(77~)" as it is (2026-11-19 review)."""
    whole = [i for i, o in enumerate(options) if o.get("values_ko") and all(parse_label(v) for v in o["values_ko"])]
    if whole:
        return whole[-1]
    for i in range(len(options) - 1, -1, -1):
        values = options[i].get("values_ko") or []
        read = sum(1 for v in values if parse_label(v))
        # an option named a size is chosen even when none of its values reads (2026-11-21, the second windbreaker
        # pilot: "WS / WM / WL" 13483086996, "A.0 / B.1 / C.2" 11966824855, "0호 / 1호 / 2호" 12300620164, "S(상세사이즈
        # 확인했습니다)" 11734583917 went out raw with no US size and no hold): resolve() holds it on the first value
        if values and (is_size_name(options[i].get("name_ko")) or (read and read * 2 > len(values))):
            return i
    return None


def _same(a: Label, b: Label) -> bool:
    """Two labels of one size: the same chest or women's numbers; else, the same letter where one has no number."""
    if a.free and b.free:
        return True
    if a.chest and b.chest:
        return a.chest == b.chest
    if a.women and b.women:
        return a.women == b.women
    if a.jp is not None and b.jp is not None:
        return a.jp == b.jp
    return bool(a.letter) and a.letter == b.letter


def _grid_row(profile: dict[str, Any], chest: float) -> dict[str, Any] | None:
    if profile.get("pick") == "band":            # each row's number is its band's lower edge (the skirts' waist): the
        rows = sorted(profile["grid"], key=lambda r: r["chest_cm"])          # last row at or under the value, so an
        under = [r for r in rows if r["chest_cm"] <= chest + 0.05]          # edge goes to the larger size
        return under[-1] if under and chest - rows[-1]["chest_cm"] <= 6 else (rows[0] if rows[0]["chest_cm"] - chest <= 3
                                                                              else None)
    best = min(profile["grid"], key=lambda r: abs(r["chest_cm"] - chest))
    return best if abs(best["chest_cm"] - chest) <= 2.5 else None


def _us_range(text: str) -> tuple[float, float]:
    ends = [float(x) for x in str(text).split("-")]
    return (-1.0, -1.0) if text == "00" else (ends[0], ends[-1])


def _brand_us(hit: tuple[str, dict[str, Any]] | None, rows: list[dict[str, Any]],
              profile: dict[str, Any]) -> tuple[str, str] | None:
    """The maker's own US number for one Korean chest (a brand row's `us_by_chest`, its printed table: 2026-11-21,
    Superior 085..105 = US 2..10, one to two sizes under the grid's) -> ("S (US 6)", "S"): the grid's letter whose US
    numbers hold it; None without such a row or that chest (the grid's then)."""
    if not hit or len(rows) != 1:
        return None
    num = (hit[1].get("us_by_chest") or {}).get(str(int(rows[0]["chest_cm"])))
    if num is None:
        return None
    n = float(num)
    row = next((r for r in profile["grid"] if r.get("us_num")
                and _us_range(r["us_num"])[0] <= n <= _us_range(r["us_num"])[1]), None)
    return (f"{row['us']} (US {num})", row["us"]) if row else None


def _us_text(rows: list[dict[str, Any]]) -> str:
    if not all(r.get("us_num") for r in rows):     # men's tops: the US letter alone (2026-11-21)
        return rows[0]["us"] if len(rows) == 1 else f"{rows[0]['us']}-{rows[-1]['us']}"
    if len(rows) == 1:
        return f"{rows[0]['us']} (US {rows[0]['us_num']})"
    lo, hi = rows[0], rows[-1]
    return f"{lo['us']}-{hi['us']} (US {lo['us_num'].split('-')[0]}-{hi['us_num'].split('-')[-1]})"


def _chest_of(label: Label, profile: dict[str, Any]) -> list[float]:
    """The Korean chest of the label's numbers; [] when a women's size is not in kr_women (a half size, "66반", sits
    between two US sizes: held unless the profile names it). A profile keyed by the waist ("key": "waist", the
    skirts, 2026-11-22) reads the label's waist (cm, inches made cm) and a number 80..95 as a waist in cm; a profile of
    tops never reads a waist."""
    if profile.get("key") == "waist":
        # a number 80..95 beside a letter is the maker's hip or top numbering, never the waist ("S(90)", Kappa
        # 11871883753, 2026-11-22: S went out as XXL); alone it is a waist in cm
        chest = [] if label.letter else [c for c in label.chest if c <= 95]
        if label.waist or chest:
            return list(label.waist) + chest
        if label.chest and label.letter:
            return []
    elif label.chest:
        return list(label.chest)
    out = []
    for w in label.women:
        key = f"{w:g}"
        if key not in profile["kr_women"]:
            return []
        out.append(profile["kr_women"][key])
    return out


def _typed_rows(chart: Chart, sections: list[str]) -> list[dict[str, Any]]:
    """The one-size rows per type when the chart tied blocks to types; the block read before any type's heading
    keeps its place: named by the one type left untied, else unnamed (never dropped)."""
    tied = [n for n in chart.rows if n in chart.sections]
    if not tied:
        return []
    out = []
    if ONE in chart.rows:
        left = [v for v in dict.fromkeys(sections) if v not in chart.sections.values()]
        row: dict[str, Any] = {"us": "One Size", "cm": dict(chart.rows[ONE])}
        if len(left) == 1:
            row["section_ko"] = left[0]
        out.append(row)
    out += [{"us": "One Size", "section_ko": chart.sections[n], "cm": dict(chart.rows[n])} for n in tied]
    return out


def _letter_chest(letter: str, pairs: dict[str, float], hit: tuple[str, dict[str, Any]] | None,
                  profile: dict[str, Any]) -> float | None:
    if letter in pairs:
        return pairs[letter]
    if hit and letter in (hit[1].get("letters") or {}):
        return float(hit[1]["letters"][letter])
    return float(profile["letters"][letter]) if letter in profile["letters"] else None


def text_pairs(texts: list[str]) -> dict[str, Label]:
    """The letters the seller's text pairs with one Korean women's size ("L[55~66]", "M(55)", "77(XL)"); a letter
    written with two different numbers is left out (never a guess: today's reading stays). Model and shop lines
    (size_chart.NOT_CHART_RE) are skipped."""
    seen: dict[str, set[str]] = {}
    got: dict[str, Label] = {}
    for line in texts:
        if NOT_CHART_RE.search(line):
            continue
        for token in _TEXT_PAIR_RE.findall(line):
            label = parse_label(token)
            if label is None or not label.letter or not label.women or label.chest or label.upto:
                continue
            seen.setdefault(label.letter, set()).add(label.key)
            got[label.letter] = label
    return {k: v for k, v in got.items() if len(seen[k]) == 1}


def _joined_size(value: str, free: bool = False) -> Label | None:
    """The size of one value that joins a colour and a size, or None: a size tail after a head that is no size
    ("Black/090", "아이보리 M"), or a size head before a tail that is no size ("FREE/그레이", "XL/크림": 2026-11-21,
    Mineflow 9969597394); a letter, a chest or a women's size, FREE only when `free`."""
    words = [w for w in _JOIN_SPLIT_RE.split(str(value or "").strip()) if w]
    if len(words) < 2:
        return None
    with waist_labels():                                 # one size with its note ("XS (25인치 전후)"): no colour,
        if parse_label(str(value)):                      # whatever the profile
            return None
    middle = [(words[i], words[:i] + words[i + 1:]) for i in range(1, len(words) - 1)]   # "티셔츠 55_아이보리"
    for size, rest in ((words[-1], words[:-1]), (words[0], words[1:]), *middle):
        label = parse_label(size)
        if label and (label.letter or label.chest or label.women or label.waist or (free and label.free)) \
                and (free or not label.free) and not parse_label(" ".join(rest)):
            return label
    return None


def split_joined(options: list[dict[str, Any]]) -> tuple[int, list[tuple[str, str]]] | None:
    """The option that joins a colour and a size in every value, as _joined reads it, and each value's (rest, size
    word): ("Ivory/085" -> ("Ivory", "085"), "남성 골프 이너웨어__블랙 95" -> ("남성 골프 이너웨어 블랙", "95"),
    "티셔츠 55_아이보리" -> ("티셔츠 아이보리", "55")); None when no option does (2026-11-22, the men's tops pilot: 20
    apparel products held for it, transform._sizes splits it in two options)."""
    if _joined(options) is None:
        return None
    for i, o in enumerate(options):
        values = [str(v) for v in o.get("values_ko") or []]
        out: list[tuple[str, str]] = []
        for v in values:
            words = [w for w in _JOIN_SPLIT_RE.split(v.strip()) if w]
            label = _joined_size(v, free=True)
            if label is None:
                break
            for k in (len(words) - 1, 0, *range(1, len(words) - 1)):
                rest = words[:k] + words[k + 1:]          # a second size word in the rest ("오프화이트 85 XS"): no split
                if parse_label(words[k]) == label and not parse_label(" ".join(rest)) \
                        and not any(parse_label(w) or (len(w) > 1 and w[0] in "AaWw" and parse_label(w[1:]))
                                    for w in rest):    # adidas' Asian letters "AXL (110)", a women's "WS": no colour
                    out.append((" ".join(rest), words[k]))
                    break
            else:
                break
        if len(out) == len(values) and len({sz for _, sz in out}) >= 2:
            return i, out
    return None


def joined_value(value: str | None) -> bool:
    """One value that joins a colour and a size ("Black/090", "아이보리 M", "XL/크림"): never FREE alone."""
    return _joined_size(str(value or "")) is not None


def _joined(options: list[dict[str, Any]]) -> str | None:
    """An option whose values join a colour and a size ("Ivory/085", "오프화이트 85 XS"): every value ends in a size
    (a letter, a chest or a women's size, never FREE or a bare 0..4) after a head that is no size, two sizes or more."""
    for o in options:
        values = [str(v) for v in o.get("values_ko") or []]
        tails: list[str] = []
        for v in values:
            label = _joined_size(v, free=True)
            if not label:
                tails = []
                break
            tails.append(label.key)
        # two sizes or more, FREE counted only beside another ("FREE/그레이", "XL/크림", 2026-11-21)
        if len(set(tails)) >= 2:
            return f"{o.get('name_ko')!r}: colour and size in one option ({values[0]!r} ...)"
    return None


def _by_position(resolved: list[dict[str, Any]], chart: Chart, profile: dict[str, Any]) -> None:
    """Bare letters only on the profile's fallback, over a chart whose rows are numbers alone, as many: the seller's
    sizes in order ("S / M / L" sold, "호칭 / 95 / 100 / 105" charted: S is 95). 2026-11-20, the windbreaker pilot
    (Kim Young Joo DOFLJP01 11074837484: the fallback made S = 90, one size too small, and the chart was dropped).
    Rewritten in place, basis `chart_position`; anything else (a count that differs, a lettered row) is left alone."""
    if not resolved or any(r.get("basis") != "fallback_letters" for r in resolved):
        return
    numbered = sorted(((lab.chest[0], n) for n, lab in chart.labels.items()
                       if n in chart.rows and lab and len(lab.chest) == 1 and not lab.letter and not lab.women),
                      key=lambda x: x[0])
    if len(numbered) != len(resolved) or len({c for c, _ in numbered}) != len(numbered):
        return
    ordered = sorted(resolved, key=lambda r: r["chest_cm"] or 0)
    rows = [_grid_row(profile, c) for c, _ in numbered]
    if not all(rows):
        return
    for item, (chest, name), row in zip(ordered, numbered, rows):
        assert row is not None
        item.update(us=_us_text([row]), letter=row["us"], chest_cm=row["chest_cm"], basis="chart_position",
                    chart_label=name)


def resolve(options: list[dict[str, Any]], texts: list[str], brand: str | None, title: str | None,
            profile_name: str, table: dict[str, Any] | None = None, has_fact: bool = False) -> dict[str, Any]:
    """The sizes of a product (_resolve), waists read when the profile is keyed by the waist (size_labels)."""
    table = table or grids()
    with waist_labels(table["profiles"][profile_name].get("key") == "waist"):
        return _resolve(options, texts, brand, title, profile_name, table, has_fact)


def _resolve(options: list[dict[str, Any]], texts: list[str], brand: str | None, title: str | None,
             profile_name: str, table: dict[str, Any] | None = None, has_fact: bool = False) -> dict[str, Any]:
    """-> {"version", "profile", "option": index or None, "values": [{ko, us, letter, chest_cm, basis}] in size
    order, "merged": {ko: ko kept}, "chart": {kinds, rows: [{us, cm: {...}}]} or None, "held": detail or None}.
    `has_fact`: the product states its one size as a fact (transform._sizes resolves it): no size option is then
    no unknown size."""
    table = table or grids()
    profile = table["profiles"][profile_name]
    index = size_option(options)
    sections = [v for i, o in enumerate(options) if i != index and not _COLOUR_NAME_RE.search(str(o.get("name_ko") or ""))
                and not any(_COLOUR_VALUE_RE.search(str(x)) for x in o.get("values_ko") or [])
                and not all(parse_label(x) for x in o.get("values_ko") or [])
                for v in o.get("values_ko") or []]
    chart = read_chart(texts, profile.get("measures", "tops"), sections)
    hit = brand_row(profile, brand, title)
    out: dict[str, Any] = {"version": VERSION, "profile": profile_name, "option": None, "values": [], "merged": {},
                           "brand_row": hit[0] if hit else None, "chart": None, "held": None}
    rows_by_label = [(n, chart.labels.get(n) or parse_label(n), m) for n, m in chart.rows.items()]
    if chart.conflicts:
        out["chart_conflicts"] = list(chart.conflicts)
    typed = _typed_rows(chart, sections)
    if index is None:                                # no size option: one size, its measurements if the chart has
        joined = _joined(options)
        if joined:                                   # "Ivory/085": the Korean size would reach the store (2026-11-20)
            out["held"] = joined
            return out
        listed = list(dict.fromkeys(lab.key for _, lab, _ in rows_by_label
                                    if lab and not lab.free and (lab.chest or lab.women or lab.waist or lab.letter)))
        # ... and the chart's size labels without measures (2026-11-21, the second tops pilot: Nike 13660201494
        # sells only S, written in its title, while its chart names S, M, XL, 2XL: no size reached the store)
        labelled = [n for n, lab in chart.labels.items()
                    if lab and not lab.free and (lab.chest or lab.women or lab.waist or lab.letter)]
        if len(listed) < 2 and len({chart.labels[n].key for n in labelled}) >= 2:
            listed = list(dict.fromkeys(chart.labels[n].key for n in labelled))
            rows_by_label = [(n, chart.labels[n], chart.rows.get(n) or {}) for n in labelled]
        if not has_fact and len(listed) >= 2:       # the chart has rows of several sizes, the product sells one
            names = [n for n, lab, _ in rows_by_label if lab and not lab.free]     # (13004790971: 95..110, 2026-11-20)
            out["held"] = f"no size option, the chart lists {', '.join(names[:6])}: which size is sold is unknown"
            return out
        if typed:                                    # one block per type ("앞면로고" / "뒷면로고": 10885610305)
            out["chart"] = {"kinds": dict(chart.kinds), "rows": typed}
            return out
        one = [r for r in rows_by_label if r[1] and r[1].free] or (rows_by_label if len(rows_by_label) == 1 else [])
        if one:
            out["chart"] = {"kinds": dict(chart.kinds), "rows": [{"us": "One Size", "cm": dict(one[0][2])}]}
        return out
    out["option"] = index
    pairs: dict[str, float] = {}                     # the chart's letter -> chest pairings (85 (S), Korea Size row)
    for n, lab in chart.labels.items():
        chest = chart.korea.get(n) or (lab.chest[0] if lab and lab.chest else None)
        if lab and lab.letter and chest and profile.get("key") != "waist":   # "S(90)" over a skirt: no waist
            pairs[lab.letter] = chest
    written = text_pairs(texts)                      # "L[55~66]/XL[77]": the seller's text pairs a letter
    # a letter's women's size from the seller ("55~66(L)", "L[55~66]") counts only when every bare letter of the option
    # has one: M/L/XL over "L[55~66]/XL[77]" would mix two systems (L=S-M before M=M); today's letters then stay
    # (2026-11-20 review)
    for use_women in (True, False):
        out["merged"] = {}
        paired = unpaired = 0
        seen: dict[str, str] = {}                        # the label's key -> the first Korean value with it
        resolved = []
        for ko in options[index]["values_ko"]:
            label = parse_label(ko)
            if label is None:
                out["held"] = f"{ko!r}: not read as a size"
                return out
            if label.key in seen:                        # "M (66)" and "M(66)": one size written twice
                out["merged"][ko] = seen[label.key]
                continue
            seen[label.key] = ko
            matches = [n for n, lab in chart.labels.items() if lab and _same(lab, label)]
            # the chart's label with measurements, then the one written as the value is, then one with its letter: a
            # bare header label ("SIZE / S / M") or a model line never takes the size's row (2026-11-19 review)
            matches.sort(key=lambda n: (n not in chart.rows, chart.labels[n].key != label.key,
                                        chart.labels[n].letter != label.letter))
            own = matches[0] if matches else None
            item: dict[str, Any] = {"ko": ko}
            # FREE with its range beside another size ("Free(55-66)" and "L", 5875520955, 2026-11-22) is that range,
            # never "One Size" (a US buyer reads it as fitting all); alone it stays One Size
            ranged = label.free and (label.women or label.chest or label.waist) and len(options[index]["values_ko"]) > 1
            if label.free and not ranged:
                item.update(us="One Size", letter=None, chest_cm=None, basis="free")
            elif own and own in chart.us:
                letter = chart.us[own]
                row = next((r for r in profile["grid"] if r["us"] == letter), None)
                item.update(us=_us_text([row]) if row else letter, letter=letter,
                            chest_cm=row["chest_cm"] if row else None, basis="chart_us")
            elif hit and hit[1].get("system") == "us" and label.letter:
                row = next((r for r in profile["grid"] if r["us"] == label.letter), None)
                item.update(us=_us_text([row]) if row else label.letter, letter=label.letter,
                            chest_cm=None, basis=f"brand_us:{hit[0]}")
            else:
                chests, basis, women = _chest_of(label, profile), "label", False
                if not chests and label.jp is not None and own and chart.korea.get(own):
                    chests, basis = [chart.korea[own]], "chart_korea"
                if not chests and label.upto and label.letter:     # "S/M": both letters' chests, a range
                    ends = [_letter_chest(x, pairs, hit, profile) for x in (label.letter, label.upto)]
                    if all(ends):
                        chests, basis = [e for e in ends if e], "letter_range"
                mate = chart.labels.get(own) if own else None
                if not chests and mate and mate.chest and profile.get("key") != "waist":
                    chests, basis = list(mate.chest), "chart_pair"
                if not chests and mate and profile.get("key") == "waist" and _chest_of(mate, profile):
                    chests, basis = _chest_of(mate, profile), "chart_pair"     # a waist the chart pairs ("S(25)")
                if use_women and not chests and mate and mate.women and mate.letter == label.letter:
                    chests, basis, women = _chest_of(mate, profile), "chart_pair", True   # "55~66(L)" (9353856438)
                if not chests and label.letter and label.letter in pairs:
                    chests, basis = [pairs[label.letter]], "chart_pair"
                if use_women and not chests and label.letter and not label.upto and label.letter in written:
                    chests, basis, women = _chest_of(written[label.letter], profile), "text_pair", True
                if not chests and label.letter and hit and label.letter in (hit[1].get("letters") or {}):
                    chests, basis = [hit[1]["letters"][label.letter]], f"brand:{hit[0]}"
                if not chests and label.letter and label.letter in profile["letters"] and not label.women:
                    # a women's size the profile cannot map ("XL(66~66반)" in the tops) holds, never its bare
                    # letter (2026-11-22, the skirts review: XL(66~66반) went out XL, two sizes over the 66)
                    chests, basis = [profile["letters"][label.letter]], "fallback_letters"
                grid_rows = [r for c in sorted(set(chests)) if (r := _grid_row(profile, c))]
                if not chests or len(grid_rows) != len(set(chests)):
                    out["held"] = f"{ko!r}: no US size ({'chest ' + str(chests) if chests else 'not read'})"
                    return out
                grid_rows = sorted({r["chest_cm"]: r for r in grid_rows}.values(), key=lambda r: r["chest_cm"])
                item.update(us=_us_text(grid_rows), letter=grid_rows[0]["us"] if len(grid_rows) == 1 else None,
                            chest_cm=grid_rows[0]["chest_cm"], basis=basis)
                own_us = _brand_us(hit, grid_rows, profile)
                if own_us and hit:                           # the maker's own US number for its Korean size
                    item.update(us=own_us[0], letter=own_us[1], basis=f"brand_us_num:{hit[0]}")
                elif basis == "label" and len(label.waist) == 1 and len(grid_rows) == 1 and not label.women:
                    # a waist size ("26", "27", "67"): the US number of that waist, so 26 and 27 stay two sizes
                    # (S (US 4), S (US 6)); the skirts, 2026-11-22
                    num = (profile.get("us_by_waist_in") or {}).get(str(int(label.waist[0] / 2.54 + 0.5)))
                    row = next((r for r in profile["grid"] if num and r.get("us_num")
                                and _us_range(r["us_num"])[0] <= _us_range(num)[0] <= _us_range(r["us_num"])[1]), None)
                    if num and row:                          # the letter whose US numbers hold it (70 cm: US 8, M)
                        item.update(us=f"{row['us']} (US {num})", letter=row["us"], chest_cm=row["chest_cm"],
                                    basis="waist")
                if women:
                    paired += 1
                elif label.letter and not (label.upto or label.chest or label.women or label.waist) \
                        and (basis == "fallback_letters" or basis.startswith("brand:")):
                    unpaired += 1                    # a bare letter the seller left without a women's size
            item["chart_label"] = own
            resolved.append(item)
        if not (paired and unpaired):
            break
    _by_position(resolved, chart, profile)
    us = [r["us"] for r in resolved]
    if len(set(us)) != len(us):
        dup = sorted({u for u in us if us.count(u) > 1})
        out["held"] = f"two Korean sizes on one US size: {', '.join(dup)}"
        return out
    order = {r["us"]: i for i, r in enumerate(profile["grid"])}
    resolved.sort(key=lambda r: (r["chest_cm"] is None, r["chest_cm"] or 0, order.get(r["letter"] or "", 99)))
    out["values"] = resolved
    if typed and all(r["us"] == "One Size" for r in resolved):      # FREE sold in types: a row per type
        out["chart"] = {"kinds": dict(chart.kinds), "rows": typed}
        return out
    rows = [{"us": r["us"], "cm": dict(chart.rows[r["chart_label"]])} for r in resolved
            if r["chart_label"] and chart.rows.get(r["chart_label"])]
    if rows:
        out["chart"] = {"kinds": dict(chart.kinds), "rows": rows}
    return out


# --- the storefront's size chart -----------------------------------------------------------------------------------

def inches(cm: float) -> float:
    return round(cm / 2.54 * 2) / 2


def _in(x: float) -> str:
    return f"{x:g}"


CHART_MARK = "<h3>Size chart (US)</h3>"       # the block's start: sweep reads the description without it


def chart_html(sizes: dict[str, Any], table: dict[str, Any] | None = None,
               section_en: Callable[[str], str] | None = None) -> str:
    """The size chart block at the end of the description (US sizes, inches); "" when there is nothing to show.
    Garment chest laid flat (단면) is doubled; the body bust is the profile's band for the size. `section_en`: the
    English of a type's Korean value, for a one-size chart per type ("One Size (Front Logo)")."""
    table = table or grids()
    profile = table["profiles"][sizes["profile"]]
    bands = {r["us"]: r["bust_in"] for r in profile["grid"]}
    values = sizes.get("values") or []
    chart = sizes.get("chart") or {}
    measured = {r["us"]: r["cm"] for r in chart.get("rows") or []}
    kinds = chart.get("kinds") or {}
    rows_in = chart.get("rows") or []
    fields = [f for f in measure_names(profile.get("measures", "tops")) if any(f in r["cm"] for r in rows_in)]
    names = {"chest": "Garment chest", "length": "Length", "shoulder": "Shoulder", "sleeve": "Sleeve",
             "waist": "Garment waist", "hip": "Hip"}
    flat_under = {"chest": 75, "waist": 53, "hip": 72}     # a value laid flat (단면) is doubled; with no word, under this

    def garment(field_: str, cm: float) -> float:
        if field_ not in flat_under:
            return inches(cm)
        flat = kinds.get(field_) == "flat" or (kinds.get(field_) in (None, "mixed") and cm < flat_under[field_])
        return inches(cm * 2 if flat else cm)

    rows = []
    if values:
        fits = f"Fits {profile.get('fit', 'bust')}"          # "Fits chest" for men's tops (2026-11-21)
        head = ["Size", fits] + [names.get(f, f.title()) for f in fields]
        for v in values:
            band = bands.get(v["letter"] or "") if v.get("letter") else None
            if v["us"] != "One Size" and band is None and v.get("chest_cm"):
                lo = _grid_row(profile, v["chest_cm"])
                band = lo["bust_in"] if lo else None
            cells = [v["us"], f"{_in(band[0])}–{_in(band[1])} in" if band else "—"]
            m = measured.get(v["us"]) or {}
            cells += [f"{_in(garment(f, m[f]))} in" if f in m else "—" for f in fields]
            rows.append(cells)
    elif rows_in:
        head = ["Size"] + [names.get(f, f.title()) for f in fields]
        for row in rows_in:
            us, m = row["us"], row["cm"]
            if row.get("section_ko"):
                us = f"{us} ({section_en(row['section_ko']) if section_en else row['section_ko']})"
            rows.append([us] + [f"{_in(garment(f, m[f]))} in" if f in m else "—" for f in fields])
    else:
        return ""
    fit_note = (f"Fits {profile.get('fit', 'bust')} is the body measurement each size is made for; " if values
                else "")
    round_ = " and ".join(f for f in ("chest", "waist", "hip") if f in fields) or "chest"
    note = (f"{fit_note}the garment measurements are the maker's, the {round_} all the way round, to within about 1 in."
            if fields else f"{fit_note}the maker gave no garment measurements.")
    note = note[0].upper() + note[1:]
    block = _el("table", [_el("thead", [_el("tr", [_el("th", h) for h in head])]),
                          _el("tbody", [_el("tr", [_el("td", c) for c in r]) for r in rows])], ' class="size-chart"')
    return f"{CHART_MARK}{block}<p>{note}</p>"


def _el(tag: str, inner: str | list[str], attrs: str = "") -> str:
    """An element as Shopify stores it (2026-11-19: it rewrote the table with line breaks, so every draft read as
    changed): text inline; one child inline ("<thead><tr>"); several children each on a line of its own."""
    if isinstance(inner, str):
        return f"<{tag}{attrs}>{inner}</{tag}>"
    if len(inner) == 1:
        return f"<{tag}{attrs}>{inner[0]}</{tag}>"
    return f"<{tag}{attrs}>\n" + "\n".join(inner) + f"\n</{tag}>"
