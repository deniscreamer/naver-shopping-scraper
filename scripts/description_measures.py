"""Package weight and size guessed from the OCR text of the description images (description_images.py), and
merged with today's fields (package_measures.py): per field the larger value wins. Pure, offline, deterministic.

The owner, 2026-11-07: RapidOCR only; match size and weight from OCR with simple rules, compare with the previous
way, take the larger size and weight; no 100 % accuracy chase; not tied to one category.

Two layers:

  core (every category)   what a seller writes of the product itself, in any category:
                            packed   박스 / 포장 / 택배 / 패키지 + a weight or an a x b x c size     -> package, conf 2
                                     (an image's reading is never a seller's typed value: 2 at most)
                            stated   세트 / 본품 / 제품 / 상품 무게 kg; a row labelled 무게 / 중량 / weight
                                     with a kg value; 제품 / 상품 크기 / 사이즈 / 규격 + a size triple  -> conf 2
                                     (the product's weight and size bound the package's from below)
  profile (per category)  the parts a category's images list when the product is a set of like items in a
                          container: each item's weight and length in spec tables, the container's weight and
                          size, how many items. A Profile is data (ranges, words), chosen by the Naver leaf
                          category id (CATEGORY_PROFILES, profile_for). GOLF_SET (50002788, OCR study on 50
                          sets, 2026-11-07): items = clubs ("클럽 중량(g) / 310 / 306", "45.5인치"), container =
                          the bag ("무게 약 4.1kg / 높이 약 89cm", "입구 9인치", "캐디백-91cm(세로)*31cm(폭)*40cm(가로)").
                          Without a profile only the core runs.

Guess (lower bounds per field; a field with nothing to go on is left out):

  product_weight_g    a stated set / product weight, else items x the median item weight (+ the container's stated
                      weight when the variant has it)
  package_weight_g    a stated packed weight, never below the product guess (a box weighs at least its contents)
  package_*_mm        a stated box size; else the longest of the product's size, the longest item, the container's
                      long side; the short sides from the product's size or the container's mouth / sides

Rows that are a shop rule (20kg 초과), customs (5kg 이하 통관), a person (체형 182cm 84kg), a price, a disclaimer, or
after a cross-sell heading (함께 구매, to the end of the image) are never read.

The merge (merge_fields): per field the value today's way uses (a seller's value max, or the category default's
central) is compared with the guess; the larger is kept, the other travels as `compared`. A guess outside the
category's plausible band (when the operator gave one) is not taken.

    from description_measures import profile_for, read_rows, package_for
    profile = profile_for("50002788")                    # by Naver category id; None: the core only
    facts = read_rows(images, profile)                   # images: [[row text, ...] per image], rows top to bottom
    fields, taken = package_for(variant_fields, facts, item_count=12, container=True, profile=profile)
"""
import re
import statistics
from dataclasses import dataclass
from typing import Any

FIELDS = ("product_weight_g", "package_weight_g", "package_length_mm", "package_width_mm", "package_height_mm")
SOURCE = "description_image"
INCH_MM = 25.4


@dataclass(frozen=True)
class Profile:
    """The parts of a category's sets: like items (N per set) and the container they come in."""
    item: str                            # the word in `how` ("clubs")
    item_weight_label: re.Pattern        # a row head naming one item's whole weight ("클럽 중량")
    part_label: re.Pattern               # a row head naming a part of an item, never the item ("샤프트 중량")
    item_g: tuple[float, float]          # one item's weight
    item_in: tuple[float, float]         # one item's length, inches
    item_cm: tuple[float, float]         # the same, cm
    count_re: re.Pattern                 # items in the set ("11PCS", "총 10개")
    count: tuple[int, int]               # a plausible item count
    container: str                       # the word in `how` ("bag")
    container_word: re.Pattern           # the container named ("캐디백")
    container_row: re.Pattern            # words of the container's own table ("입구", "높이")
    container_g: tuple[float, float]
    container_long_mm: tuple[float, float]
    container_mouth_in: tuple[float, float]
    container_no: re.Pattern             # the set has no container ("골프백 미포함", "캐디백 별도")
    container_yes: re.Pattern            # it has one ("캐디백 포함")
    window: int = 6                      # rows above a value searched for the container's name
    count_row: str | None = None         # a 상품정보 row that states the item count ("총클럽개수": "11개")
    plausible: tuple[tuple[str, float, float], ...] = ()   # (field, min, max): a guess outside is absurd


_BAG = r"(?:골프\s*백|캐디\s*백|스탠드\s*백|백)"
GOLF_SET = Profile(
    item="clubs",
    item_weight_label=re.compile(r"(?:클럽|총|전체)\s*(?:중량|무게)|club\s*weight|total\s*weight|"
                                 r"^\s*(?:#\d\s*)?(?:중량|무게)\s*\(g\)", re.I),
    part_label=re.compile(r"샤프트|헤드|그립|shaft|head|grip|바디|무게추|웨이트|스크류|screw", re.I),
    item_g=(180, 650),                   # driver ~300 g, irons ~400 g, putter ~550 g
    item_in=(32.0, 48.5),                # putter 33", driver 46"
    item_cm=(81.0, 124.0),
    count_re=re.compile(r"(?<![\d.+])(\d{1,2})\s*(?:PCS|Pcs|pcs|피스|P(?![A-Za-z0-9]))|(?:클럽|총)\s*(\d{1,2})\s*개|"
                        r"(\d{1,2})\s*개\s*(?:클럽|구성)"),
    count=(3, 16),
    container="bag",
    container_word=re.compile(r"캐디\s*백|골프\s*백|스탠드\s*백|휠\s*백|카트\s*백|보스[턴톤]\s*백|캐리\s*백|bag\b|백\s*세트", re.I),
    container_row=re.compile(r"입구|후드|커버|포켓|숄더|스트랩|모델|사이즈|무게|중량|높이|총\s*길이", re.I),
    container_g=(1500, 9000),            # a caddie / stand bag (with a boston bag 4.95 kg)
    container_long_mm=(700, 1500),       # its height / total length
    container_mouth_in=(7.0, 11.0),      # 8.5 / 9 / 9.5 inch
    container_no=re.compile(_BAG + r"\s*(?:은|는)?\s*(?:미\s*포함|불\s*포함|포함\s*(?:되지|안)|없음|없이|별도|제외|"
                            r"X\b|x\b|미\s*제공)"),
    container_yes=re.compile(_BAG + r"\s*(?:\+\s*[가-힣]+\s*)*(?:세트\s*)?(?:포함|증정|구성)(?!\s*(?:되지|안))"),
    count_row="총클럽개수",
    # a golf full set in its box (OCR study 2026-11-07 and the 55 harvester sets): wider than any set
    plausible=(("product_weight_g", 1500, 20000), ("package_weight_g", 2000, 25000),
               ("package_length_mm", 800, 1700), ("package_width_mm", 100, 700), ("package_height_mm", 80, 600)),
)
# Naver leaf category id -> its parts profile (the core runs for every category; a profile only where the images
# list parts of a set). Add a category here when its images need its own words / ranges (scripts/README.md).
CATEGORY_PROFILES: dict[str, Profile] = {
    "50002788": GOLF_SET,                # 스포츠/레저 > 골프 > 골프클럽 > 풀세트
}
# any category: a guess outside these is an OCR / reading error, never a product (a 1 g phone case is fine, a
# 200 kg parcel is freight, a 3 m side is not a parcel)
CORE_PLAUSIBLE: dict[str, tuple[float, float]] = {"product_weight_g": (10, 200000), "package_weight_g": (10, 200000), "package_length_mm": (10, 3000),
                  "package_width_mm": (5, 3000), "package_height_mm": (2, 3000)}
NUMBER_CONF = 0.9                        # RapidOCR row confidence (its lowest cell): the research finder's OCR-doubt line
                                         # (digit boxes under 0.95 were ~38 % wrong; a row is its weakest box)
MAX_RATIO = 3.0                          # a guess more than 3x today's value (the default's central, the seller's
                                         # value) is absurd: a misread ("45.5kg" for 4.55) or another product


def profile_for(category_id: str | None) -> Profile | None:
    """The parts profile of a Naver leaf category, None: the core only."""
    return CATEGORY_PROFILES.get(str(category_id or ""))

_NUM = r"(\d{1,4}(?:[.,]\d{1,2})?)"
_KG_RE = re.compile(_NUM + r"\s*(?:kg|㎏|킬로)", re.I)
_G_RE = re.compile(r"(?<![\d.])" + _NUM + r"\s*g(?![a-z])", re.I)
_BARE_RE = re.compile(r"(?<![\d.])(\d{3}(?:\.\d)?)(?!\d)(?:\s*g)?(?![\w.%])")     # "약318", "#3-약344"
_INCH_RE = re.compile(_NUM + r"\s*(?:인치|inch|in\b|\")", re.I)
_CM_RE = re.compile(_NUM + r"\s*\(?\s*(?:cm|센치|㎝)", re.I)                 # "총길이 130(cm)"
_AXIS = r"(?:(?<![A-Za-z])[WDHL](?![A-Za-z])|가로|세로|높이|폭|길이|깊이)?\s*:?\s*"       # "W53 x D38 x H62.5 cm"
_TRIPLE_RE = re.compile(_AXIS + _NUM + r"\s*(?:cm|mm)?\s*[x×X*]\s*" + _AXIS + _NUM + r"\s*(?:cm|mm)?\s*[x×X*]\s*"
                        + _AXIS + _NUM + r"\s*(cm|mm)?", re.I)
_SIDE_RE = re.compile(_NUM + r"\s*cm\s*\(?\s*(?:세로|가로|폭|높이|길이|깊이)", re.I)   # 91cm(세로)*31cm(폭)*40cm(가로)
_LENGTH_HEAD = re.compile(r"길이|length", re.I)
_PACKED_WORD = re.compile(r"박스|포장|택배\s*(?:무게|중량|사이즈|크기)|패키지|package|packing|gross", re.I)
_SET_WORD = re.compile(r"(?:풀\s*세트|세트|본품|제품|상품)\s*(?:총\s*)?(?:무게|중량)|(?:set|product|item|net)\s*weight",
                       re.I)
_WEIGHT_HEAD = re.compile(r"^\s*(?:총\s*)?(?:무게|중량|무|weight)\s*[:)(]?\s*(?:/|:|$|약|\d)", re.I)
# "무게 / 3.5kg"; "무 / 0.6kg": OCR split the label of a spec table into its letters (9809159942, 2026-11-07)
_SIZE_WORD = re.compile(r"(?:제품|본품|상품|완제품)?\s*(?:크기|사이즈|규격|치수)|size|dimension", re.I)
_SKIP_ROW = re.compile(
    r"초과|이하|미만|넘는|넘을|경우|화물|택배비|택배사|착불|운임|배송비|교환|반품|환불|관부가세|통관|면세|미화|"
    r"신장|체형|키\s*\d|몸무게|후기|리뷰|유저|\d\s*원(?![가-힣])|₩|할인|적립|차이가?\s*있을|다를\s*수|오차")
_CROSS_SELL = re.compile(r"함께\s*구매|추천\s*상품|같이\s*구매|관련\s*상품|다른\s*상품")
KEYS = ("packed_weights", "packed_boxes", "set_weights", "product_weights", "product_sizes",
        "item_weights", "item_lengths", "item_counts",
        "container_weights", "container_long", "container_sides", "container_no", "container_yes")


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _in(v: float, band: tuple[float, float]) -> bool:
    return band[0] <= v <= band[1]


def _sides(triple: re.Match) -> list[float]:
    scale = 1 if (triple.group(4) or "").lower() == "mm" else 10
    return sorted((_num(triple.group(k)) * scale for k in (1, 2, 3)), reverse=True)


def _readable(rows: list[str]) -> list[tuple[int, str]]:
    """(index, row) of the rows that may be read: before a cross-sell heading, not a shop rule / person / price."""
    out = []
    for i, row in enumerate(rows):
        if _CROSS_SELL.search(row):
            break                                   # a cross-sell block runs to the end of the image
        if not _SKIP_ROW.search(row):
            out.append((i, row))
    return out


def _row_sides(row: str, triple: re.Match | None) -> list[float]:
    if triple:
        return _sides(triple)
    found = _SIDE_RE.findall(row)
    return sorted((_num(x) * 10 for x in found), reverse=True)[:3] if len(found) >= 3 else []


def read_rows(images: list[list[Any]], profile: Profile | None = None) -> dict[str, Any]:
    """Facts from the OCR rows of each image (the core's, plus the profile's parts when one is given). A row is its
    text, or (text, OCR confidence): a row read below NUMBER_CONF gives no single value (a box, a set / product
    weight or size, the container's, an item's length), only its share of the items' median weight and its words.
    Every value carries its row as the quote."""
    facts: dict[str, Any] = {k: [] for k in KEYS}
    p = profile
    for n, raw in enumerate(images):
        rows = [r if isinstance(r, str) else r[0] for r in raw]
        confs = [1.0 if isinstance(r, str) else r[1] for r in raw]
        for i, row in _readable(rows):
            where = {"image": n, "row": i, "quote": row[:200]}
            sure = confs[i] >= NUMBER_CONF                 # larger wins: an upward misread is the one that gets in
            kgs = [_num(m.group(1)) * 1000 for m in _KG_RE.finditer(row)] if sure else []
            triple = _TRIPLE_RE.search(row) if sure else None
            head = row.split(" / ", 1)[0]
            near = p is not None and any(p.container_word.search(r) for r in rows[max(0, i - p.window):i + 1])
            if p:
                if p.container_no.search(row):
                    facts["container_no"].append(where)
                elif p.container_yes.search(row):
                    facts["container_yes"].append(where)
                for m in p.count_re.finditer(row):
                    count = int(next(g for g in m.groups() if g))
                    if _in(count, p.count):
                        facts["item_counts"].append({**where, "count": count})
            # core: packed, then stated set / product values
            if _PACKED_WORD.search(row):
                if kgs:
                    facts["packed_weights"].append({**where, "g": max(kgs)})
                if triple:
                    facts["packed_boxes"].append({**where, "mm": _sides(triple)})
                continue
            if kgs and _SET_WORD.search(row):              # "캐디백 포함 풀세트 무게 약 7.5kg": the set's
                facts["set_weights"].append({**where, "g": max(kgs)})
                continue
            if p and near:                                  # the container's own table
                facts["container_weights"] += [{**where, "g": g} for g in kgs if _in(g, p.container_g)]
                if sure and (p.container_row.search(row) or p.container_word.search(row)):
                    for m in _INCH_RE.finditer(row):
                        inch = _num(m.group(1))
                        if _in(inch, p.container_mouth_in):            # a round mouth: both short sides
                            facts["container_sides"].append({**where, "mm": [round(inch * INCH_MM)] * 2})
                    sides = _row_sides(row, triple)
                    if sides and _in(sides[0], p.container_long_mm):
                        facts["container_long"].append({**where, "mm": sides[0]})
                        facts["container_sides"].append({**where, "mm": sides[1:3]})
                    elif not sides:                                     # "높이 약89cm", "총길이 130(cm)"
                        facts["container_long"] += [{**where, "mm": _num(m.group(1)) * 10} for m in _CM_RE.finditer(row)
                                                    if _in(_num(m.group(1)) * 10, p.container_long_mm)]
                # no `continue`: a set's composition line ("골프백:1개") sits above its item table (6630856593)
            elif kgs and _WEIGHT_HEAD.search(row) and not (p and p.part_label.search(head)):
                facts["product_weights"].append({**where, "g": max(kgs)})          # "무게 / 4.2kg", "중량: 2.3kg"
            if not near and triple and (_SIZE_WORD.search(row) or triple.group(4)):
                facts["product_sizes"].append({**where, "mm": _sides(triple)})     # "사이즈 60 x 55 x 90cm",
                                                                                    # "W53 X D38 X H62.5 cm"
            if p is None:
                continue
            # profile: the items' own weights and lengths
            if p.item_weight_label.search(head) and not p.part_label.search(head.replace("총", "")):
                for cell in row.split(" / ")[1:] if " / " in row else [row]:
                    w = _G_RE.search(cell) or _BARE_RE.search(cell)
                    if w and _in(_num(w.group(1)), p.item_g):
                        facts["item_weights"].append({**where, "g": _num(w.group(1))})
            for m in _INCH_RE.finditer(row) if sure else ():
                inch = _num(m.group(1))
                if _in(inch, p.item_in):
                    facts["item_lengths"].append({**where, "mm": round(inch * INCH_MM)})
            if sure and _LENGTH_HEAD.search(head) and not p.part_label.search(head):
                inch_label = re.search(r"inch|인치", head, re.I)              # "클럽길이(inch) / 45.5"
                for cell in row.split(" / ")[1:]:
                    for x in re.findall(r"(?<![\d.])(\d{2,3}(?:\.\d{1,3})?)(?![\d])", cell):
                        v = float(x)
                        if _in(v, p.item_in) and (inch_label or "/" not in cell):
                            facts["item_lengths"].append({**where, "mm": round(v * INCH_MM)})
                        elif _in(v, p.item_cm):                                # "112.395/44.25", "약114cm"
                            facts["item_lengths"].append({**where, "mm": round(v * 10)})
    return facts


def _ev(value: float, confidence: int, how: str, quotes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"value": {"min": round(value), "max": round(value)}, "source": SOURCE, "confidence": confidence,
            "how": how, "quote": quotes[0]["quote"] if quotes else None}


def image_count(facts: dict[str, Any]) -> int | None:
    """The item count the images state most often ("11PCS", "총 10개"), the largest of equals."""
    counts = [f["count"] for f in facts["item_counts"]]
    return max(set(counts), key=lambda c: (counts.count(c), c)) if counts else None


def container_in(text: str, profile: Profile | None) -> bool | None:
    """A variant's or a title's words about the container: True (캐디백 포함, +캐디백), False (백 미포함, 별도), None."""
    if profile is None:
        return None
    text = text or ""
    if profile.container_no.search(text):
        return False
    if profile.container_word.search(text) or profile.container_yes.search(text):
        return True
    return None


def guess(facts: dict[str, Any], item_count: int | None = None, container: bool | None = None,
          profile: Profile | None = None) -> dict[str, dict[str, Any]]:
    """The five fields' lower bounds from the facts. item_count: items in the set (the title / a spec row / the
    images); container: the variant has the container (True / False / None unknown)."""
    out: dict[str, dict[str, Any]] = {}
    if container is None and (facts["container_no"] or facts["container_yes"]):
        container = not facts["container_no"]         # "본 풀세트는 골프백 미포함 제품입니다" wins over a yes
    with_container = profile is not None and container is not False
    if facts["packed_weights"]:
        best = max(facts["packed_weights"], key=lambda f: f["g"])
        out["package_weight_g"] = _ev(best["g"], 2, "stated packed weight", [best])     # read from an image: 2 at most
    if facts["packed_boxes"]:
        best = max(facts["packed_boxes"], key=lambda f: f["mm"][0])
        for name, side in zip(FIELDS[2:], best["mm"]):
            out[name] = _ev(side, 2, "stated box size", [best])
    weight = None
    if facts["set_weights"]:
        best = max(facts["set_weights"], key=lambda f: f["g"])
        weight = _ev(best["g"], 2, "stated set weight", [best])
    elif profile and facts["item_weights"] and (item_count := item_count or image_count(facts)):
        total = statistics.median(f["g"] for f in facts["item_weights"]) * item_count
        quotes, how = facts["item_weights"], f"{item_count} {profile.item} x median {profile.item[:-1]} weight"
        if with_container and facts["container_weights"]:
            box = max(facts["container_weights"], key=lambda f: f["g"])
            total += box["g"]
            quotes, how = [box] + quotes, how + f" + {profile.container}"
        weight = _ev(total, 2, how, quotes)
    elif facts["product_weights"]:
        best = max(facts["product_weights"], key=lambda f: f["g"])
        weight = _ev(best["g"], 2, "stated weight", [best])
    if weight:
        out["product_weight_g"] = weight
        packed = out.get("package_weight_g")
        if not packed or packed["value"]["max"] < weight["value"]["max"]:      # a box weighs at least its contents
            out["package_weight_g"] = {**weight, "how": weight["how"] + " (box >= contents)"}
    if "package_length_mm" not in out:
        _sizes(out, facts, profile, with_container)
    if profile is not None and container is None:      # with or without the bag is not said: the operator's
        for name, f in out.items():                    # default covers both, the guess is weaker (owner 2026-11-07)
            if f["how"] != "stated box size":
                out[name] = {**f, "confidence": 1, "flags": ["container_unknown"]}
    return out


def _sizes(out: dict[str, Any], facts: dict[str, Any], profile: Profile | None, with_container: bool) -> None:
    sized = [(f["mm"][0], f, "product size") for f in facts["product_sizes"]]
    if profile:
        sized += [(f["mm"], f, f"longest {profile.item[:-1]}") for f in facts["item_lengths"]]
        if with_container:
            sized += [(f["mm"], f, f"{profile.container} length") for f in facts["container_long"]]
    if sized:
        mm, f, how = max(sized, key=lambda s: s[0])
        out["package_length_mm"] = _ev(mm, 2, how, [f])
    short = [(f["mm"][1:3], f, "product size") for f in facts["product_sizes"]]
    if with_container and profile:
        short += [(f["mm"], f, f"{profile.container} mouth / sides") for f in facts["container_sides"]]
    for k, name in enumerate(FIELDS[3:]):
        if short:
            sides, f, how = max(short, key=lambda s: s[0][k])
            out[name] = _ev(sides[k], 2, how, [f])


def package_for(fields: dict[str, Any], facts: dict[str, Any], item_count: int | None, container: bool | None,
                plausible: dict[str, dict[str, float]] | None = None,
                profile: Profile | None = None) -> tuple[dict[str, Any], list[str]]:
    """One variant's five fields with the images' guess merged in -> (fields, names taken from the images)."""
    return merge_fields(fields, guess(facts, item_count, container, profile), plausible, profile)


def bands(plausible: dict[str, dict[str, float]] | None, profile: Profile | None) -> dict[str, tuple[float, float]]:
    """The band a guess must fall in, per field: the operator's (category_measures.json `plausible`), else the
    profile's, else the core's."""
    out: dict[str, tuple[float, float]] = dict(CORE_PLAUSIBLE)
    out.update({name: (lo, hi) for name, lo, hi in (profile.plausible if profile else ())})
    out.update({name: (b["min"], b["max"]) for name, b in (plausible or {}).items()})
    return out


def today_value(field: dict[str, Any]) -> float | None:
    """The number today's way uses: a seller's value (its max), a default's central; a contradiction alone: None."""
    if "value" in field:
        return field["value"]["max"]
    return field.get("central")


def _brief(field: dict[str, Any]) -> dict[str, Any]:
    """What `compared` keeps of the other value: its number, source, confidence and how (not the default's whole
    table row or the image's quote: the winner carries its own evidence)."""
    brief = {"value": today_value(field), "source": field.get("source"), "confidence": field.get("confidence"),
             "how": field.get("how"), "flags": field.get("flags")}
    return {k: v for k, v in brief.items() if v not in (None, [])}


def merge_fields(fields: dict[str, Any], guessed: dict[str, dict[str, Any]],
                 plausible: dict[str, dict[str, float]] | None = None,
                 profile: Profile | None = None) -> tuple[dict[str, Any], list[str]]:
    """-> (fields, names taken from the images). Per field the larger of today's value and the guess; the loser
    travels as `compared`. An absurd guess is never taken (`rejected`): outside the field's band (bands()), or
    more than MAX_RATIO x today's value."""
    out, taken = dict(fields), []
    limits = bands(plausible, profile)
    for name in FIELDS:
        g, now = guessed.get(name), fields.get(name)
        if not g or not now:
            continue
        v, base = g["value"]["max"], today_value(now)
        lo, hi = limits[name]
        if v > hi or v < lo and base is None:      # a low lower bound loses anyway (3 clubs of a set)
            out[name] = {**now, "compared": {**_brief(g), "rejected": "implausible_for_category"}}
            continue
        if base and v > base * MAX_RATIO:
            out[name] = {**now, "compared": {**_brief(g), "rejected": "far_above_today"}}
            continue
        if base is None or v > base:
            out[name] = {**g, "compared": _brief(now)}
            taken.append(name)
        else:
            out[name] = {**now, "compared": _brief(g)}
    return out, taken
