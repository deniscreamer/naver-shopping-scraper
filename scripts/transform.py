"""Transform: one collected product (an example_99 line) -> a prepared product for one shop. Pure, offline,
deterministic: no AI, no network, no English. Korean stays Korean; `texts` lists every Korean text the
translation stage must translate. The collected line is never changed.

Why each rule (research 2026-11-05: 23 collected products, 13 of them compared one to one with what the
naver-harvester published, and its 60 published products):

  * prices: krw = the product's price + the variant's extra_price (the page's own answer); usd = KRW rounded up to
    the cent at the shop's rate; cost = price, no compare-at, not taxable. Our extra_price gave the harvester's
    published price for 191 of 191 variants of 6 products, so option names are never parsed for money.
  * options: the option groups but CUSTOM / SIMPLE (COMBINATION here), the observed rows only (a GVTOUR set: 69 rows, not 360), sold-out rows kept
    (available false). An axis with one value across the rows becomes a fact; one row -> no options (one default
    variant) and its values become facts. An axis about writing a review / a coupon is a Naver price trick, not a
    product option: dropped, the rows without that discount kept (the harvester published one as "Photo review
    discount").
  * SKU: the harvester's recipe (391 of 391): sha256 of {schemaVersion, sourceId, tenantOfferKey} as compact JSON
    with sorted keys; sourceId "observed:" + the Korean option tuple as compact JSON, or the product id.
  * spec rows shown: all but 상품번호, 제조일자, Naver promotions (이벤트, 사은품: points, coupons; 11 of the 60 shop
    products showed them) and pointers ("상세페이지 참조": no value; 7 of 60).
  * variants: the category's choice (transform_shops paid_variants; off by default), made from the page's options.
  * attributes (attributes.py): what the seller states that a shop may split a category by (gender: the variants,
    the 성별 row, the title), with its evidence -> product.attributes; the shop's sections are not decided here
    (placement.py, the last stage before Shopify; the owner 2026-11-08).
  * brand: the 브랜드 row / brandName, else the manufacturer (never Naver's M0000000 or a pointer); none ->
    run_transform's brand_fallback.
  * text fields (a name on a tag) -> personalization; add-ons on sale and in stock: free ones, paid ones too
    with the category's paid_addons (price in KRW and USD); a (필수) group is required.
  * held (not published, kept with codes): collect_incomplete, price_unknown, no_variants,
    options_unaligned, axes_over_3, specs_folded, no_images, images_over_50. More combinations than the shop's
    cap: the first ones are offered, every option value kept (note variants_capped).
  * notes (never block): shipping_paid, overseas_shipping (the price stays the cost; the operator decides),
    brand_fallback (no brand and no manufacturer stated: run_transform takes one from the
    title, the origin's importer, the images' text, or 노브랜드; brand_fallback.py),
    option_name_placeholder (선택 / 선택2 / 옵션: named from the values in translation),
    paid_addons_left_out, paid_variants_left_out, title_names_one_variant, purchase_agency, price_name_mismatch,
    photos_incomplete, reviews_none_chosen, measures_from_images / description_images_missing / _stale / _failed / _partial (the category's
    description_images switch: the images' size / weight guess, the larger value wins; description_measures.py).

    from transform import prepare
    from transform_shops import rules_for
    prepared = prepare(line, rules_for("fairwardgolf"), run="50002788-20261105T193000Z", line_no=1)
"""
import functools
import hashlib
import json
import os
import re
from collections import Counter
from typing import Any, TypedDict

import attributes
from description_clean import body_notes, clean, clean_images
from description_images import current, image_rows
from description_measures import container_in, package_for, profile_for, read_rows
from naver_variants import choose_variants
from package_measures import load_table
from spec_variants import check_specs, title_one_variant
from transform_shops import CategoryRules, ShopRules

FORMAT = "prepared/3"           # 2 (2026-11-07): package fields may carry how / quote / flags / compared;
                                 # product.description_images_text (run_transform); 3 (2026-11-08): no shop
                                 # leaves, product.attributes instead (the shop's sections: placement.py)
MAX_AXES = 3                       # Shopify options per product
MAX_IMAGES = 50
HIDDEN_ROWS = {"상품번호", "제조일자", "이벤트", "사은품", "인증정보"}     # 인증정보: purchase-agency / KC legal text
_AGENCY_RE = re.compile(r"\(?\s*(?:해외\s*)?구매\s*대행\s*\)?")             # 원산지 "일본산(구매대행)", "해외구매대행"
_DELIVERY_NOTE_RE = re.compile(r"배송\s*메[세시]지")                         # a row asking for a delivery note
_LABEL_DECOR_RE = re.compile(r"[★☆※]+|\(\s*필수\s*(?:선택)?\s*\)")             # "(필수)", "(필수선택)"
_REQUIRED_RE = re.compile(r"필수")
# "선택2", "옵션선택", "옵션+아이언커버.하프백" (2026-11-06): the name says nothing, the values do
_PLACEHOLDER_NAME_RE = re.compile(r"^(?:선택|옵션)(?:사항|선택)?\s*\d*(?:\s*[+/].*)?$")
_BRACKETS_RE = re.compile(r"\s*[(\[][^()\[\]]*[)\]]")          # innermost: 원산지 "중국산((주)위스트OEM)"
_AGENCY_WORD_RE = re.compile(r"구매\s*대행")
# a seller's numbering in front of a shown value / add-on: "선택1 9도SR", "선택3) ...", "1-1.남성 장갑", "6.쇼핑백"
_NUMBERING_RE = re.compile(r"^(?:(?:선택|옵션|택)\s*\d+\s*[).:\-]?|\d+(?:-\d+)?[.)](?!\d))\s*")   # 택1 (2026-11-07)
# a seller's tag in front of every value ("[당일출고] 스틸 샤프트 (S) SPEC", 8958060680) or of an option name
# ("(선택)샤프트/드라이버/아이언", 13553116678): not part of what is chosen (2026-11-06)
_LEAD_TAG_RE = re.compile(r"^\s*([\[(【][^\])】]{1,12}[\])】])\s*")
_CHOOSE_TAG_RE = re.compile(r"^\s*[\[(]\s*(?:선택|필수|옵션)\s*[\])]\s*")
_COUNT_ROW_RE = re.compile(r"^\s*(\d{1,2})\s*개")                    # 총클럽개수 "3개"
_POINTS_RE = re.compile(r"포인트|적립|쿠폰|할인|페이|마일리지|캐시")     # a promotion, not a thing in the box
_AREA_WORD_RE = re.compile(r"제주|도서|산간|지역|섬")
# a club count in the title / 모델명: "[3PCS]", "(3종)", "하프세트(5P)", "12pc"; not the "1pcs" of "10+1pcs"
_PIECES_RE = re.compile(r"(?<![\d.+])(\d{1,2})\s*(?:PCS|Pcs|pcs|PC|pc|피스|종|P)(?![A-Za-z0-9])")
_HALF_SET_RE = re.compile(r"하프\s*세트")
# 원산지 brackets naming the parts' own countries ("미국산(핑(미국) 미즈노(일본) 웨지퍼터(중국))", 2026-11-07)
_COUNTRY_RE = re.compile(r"미국|일본|중국|한국|국산|대만|베트남|태국|인도네시아|말레이시아|홍콩|필리핀|멕시코|USA|Japan|China",
                         re.I)
# add-on codes of a seller's catalogue: "[G192]01_미즈노 클럽 렌치" (13462927626)
_ADDON_CODE_RE = re.compile(r"^\s*\[[A-Za-z]{0,3}\d{2,6}\]\s*(?:\d{1,3}[_.)]\s*)?")
_COLOUR_AXIS_RE = re.compile(r"^(?:색상|컬러|칼라|color|colour)$", re.I)
_COLOUR_WORD_RE = re.compile(r"블랙|화이트|레드|블루|그레이|네이비|실버|골드|핑크|그린|옐로|오렌지|퍼플|브라운|베이지|민트|"
                             r"아이보리|카키|와인|black|white|red|blue|gray|grey|navy|silver|gold|pink|green", re.I)
_GIFT_RE = re.compile(r"사은품|증정")
# a value that only points to the description (server/naver_shopping/parsers.py _SEE_DESCRIPTION_RE, 2026-11-01)
_POINTER_RE = re.compile(
    r"^[\[(]?\s*(?:상품|제품)?\s*상세\s*(?:페이지|설명|정보|이미지)?\s*(?:에|란)?\s*(?:별도\s*)?"
    r"(?:참조|참고|표기|표시|확인)\s*[\])]?$|^\S+\s*항목\s*(?:참조|참고)$")
_PROMO_AXIS_RE = re.compile(r"리뷰|후기|쿠폰|적립")       # 리뷰 작성 O / X: -5,000 KRW for a promised review


class Prepared(TypedDict):
    format: str
    key: str
    shop: str
    status: str                    # ready | held
    held: list[dict[str, str]]
    notes: list[dict[str, str]]
    source: dict[str, Any]
    product: dict[str, Any]
    texts: list[dict[str, str]]


def text_id(kind: str, ko: str) -> str:
    """The same Korean text of the same kind has the same id in every product and every run."""
    return f"{kind}:{hashlib.sha256(ko.encode()).hexdigest()[:16]}"


def usd(krw: int, krw_per_usd: int) -> str:
    """KRW -> USD rounded up to the cent, as a string ("1970.00")."""
    cents = -(-krw * 100 // krw_per_usd)
    return f"{cents // 100}.{cents % 100:02d}"


def sku(prefix: str, key: str, source_id: str) -> str:
    canonical = json.dumps({"schemaVersion": "fairwardgolf-sku/v1", "sourceId": source_id, "tenantOfferKey": key},
                           ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return prefix + hashlib.sha256(canonical.encode()).hexdigest()[:24]


def _pointer(value: str | None) -> bool:
    parts = [p.strip() for p in (value or "").split("/")]
    return bool(parts) and all(_POINTER_RE.match(p) for p in parts)


def _drop_promo_axes(names: list[str], rows: list[dict[str, Any]]) -> tuple[list[int], list[dict[str, Any]]]:
    """Axis indexes to keep, and the rows left once a review / coupon axis is gone (per remaining tuple, the row
    with the highest price: the one without the discount)."""
    promo = [i for i, n in enumerate(names)
             if _PROMO_AXIS_RE.search(n) or all(_PROMO_AXIS_RE.search(r["options"][i]) for r in rows)]
    keep = [i for i in range(len(names)) if i not in promo]
    if not promo:
        return keep, rows
    best: dict[tuple[str, ...], dict[str, Any]] = {}
    for r in rows:
        k = tuple(r["options"][i] for i in keep)
        if k not in best or (r["price"] or 0) > (best[k]["price"] or 0):
            best[k] = r
    return keep, list(best.values())


def _tidy(text: str) -> str:
    """A seller's doubled spaces out of a shown name / value (the SKU keeps the raw tuple)."""
    return re.sub(r"\s+", " ", text or "").strip()


def _unnumbered(values: list[str]) -> list[str] | None:
    """The values without the seller's numbering, or without one tag every value starts with ("[당일출고]"), when
    every one carries it and none is left empty; None else."""
    if not values:
        return None
    tags = {m.group(1) if m else None for m in map(_LEAD_TAG_RE.match, values)}
    if len(tags) == 1 and None not in tags:
        out = [_LEAD_TAG_RE.sub("", v, count=1).strip() for v in values]
    elif all(_NUMBERING_RE.match(v) for v in values):
        out = [_NUMBERING_RE.sub("", v).strip() for v in values]
    else:
        return None
    return out if all(out) else None


def _axis_name(name: str) -> str:
    """"(선택)샤프트/드라이버/아이언" -> "샤프트/드라이버/아이언"."""
    return _CHOOSE_TAG_RE.sub("", _tidy(name)) or _tidy(name)


def _capped(rows: list[dict[str, Any]], axes: list[int], cap: int) -> list[dict[str, Any]]:
    """At most `cap` rows: in stock first, then the cheaper, then page order. First the rows that cover the most
    pairs of option values not offered yet (every value of one axis with every value of another), so no pair is
    left unbuyable while the cap allows (497 combinations of a TaylorMade set kept every value but sold each 5번
    wood with one driver only, 2026-11-07); with one axis, one row per value. Then the rest, in turn from each
    value of the first axis (128 -> 100 on a PING set gave the L driver 64 combinations and the A driver 36)."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i].get("is_available") is False, rows[i]["price"] or 0, i))
    if axes:                                       # in turn from each value of the first axis
        queues: dict[str, list[int]] = {}
        for i in order:
            queues.setdefault(_tidy(rows[i]["options"][axes[0]]), []).append(i)
        order = []
        while any(queues.values()):
            for q in queues.values():
                if q:
                    order.append(q.pop(0))

    def units(i: int) -> set[tuple[Any, ...]]:
        vals = [(a, _tidy(rows[i]["options"][a])) for a in axes]
        return {(*x, *y) for k, x in enumerate(vals) for y in vals[k + 1:]} if len(vals) > 1 else set(vals)
    first = (lambda i: _tidy(rows[i]["options"][axes[0]])) if axes else (lambda i: "")
    count: dict[str, int] = {}
    picked: list[int] = []
    seen: set[tuple[Any, ...]] = set()
    gain = {i: units(i) for i in order if rows[i].get("is_available") is not False}
    while len(picked) < cap:                       # most new pairs; of equals, the value offered least
        best = max(gain, key=lambda i: (len(gain[i] - seen), -count.get(first(i), 0)), default=None)
        if best is None or not gain[best] - seen:
            break
        picked.append(best)
        seen |= gain.pop(best)
        count[first(best)] = count.get(first(best), 0) + 1
    rest = [i for i in order if i not in picked]
    while rest and len(picked) < cap:              # the next row from the first-axis value offered least
        i = min(rest, key=lambda r: (count.get(first(r), 0), rest.index(r)))
        rest.remove(i)
        picked.append(i)
        count[first(i)] = count.get(first(i), 0) + 1
    return [rows[i] for i in sorted(picked)]


def simple_choices(specs: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    """SIMPLE option groups (a choice that is not a variant): one value -> a fact like a one-value axis
    ("선택: 드라이버+우드+하이브리드/SR", the set's only option, 9168175809, 2026-11-07); several -> their names, for a
    note (they are not sold as variants)."""
    groups: dict[str, list[str]] = {}
    for o in (specs.get("options") or {}).get("simple_options") or []:
        groups.setdefault(_tidy(o.get("group") or ""), []).append(_tidy(o.get("name") or ""))
    facts, left = [], []
    for name, values in groups.items():
        values = [v for v in dict.fromkeys(values) if v]
        if len(values) == 1:
            label = _axis_name(name)
            facts.append({"label_ko": "" if _PLACEHOLDER_NAME_RE.match(label) else label, "value_ko": values[0]})
        elif values:
            left.append(name)
    return facts, left


def options_and_variants(line: dict[str, Any], rules: ShopRules, key: str, cat: CategoryRules) -> dict[str, Any]:
    """-> {options, facts, variants, held, skipped_paid, duplicate_values, capped} in Korean. The variant choice is the category's
    (cat.paid_variants), made again from the page's options: the collected line's own choice may differ."""
    specs = line["specs"]
    base = line["details"]["pricing"]["discounted_price"]
    choice: dict[str, Any] = dict(choose_variants(specs["options"], base, paid=cat.paid_variants))
    groups = [g for g in (specs["options"] or {}).get("option_groups") or []     # the axes: what measures.bind
              if g.get("type") not in ("CUSTOM", "SIMPLE")]                     # and parse_page_options count
    names = [g.get("name") or "" for g in groups]
    rows = [r for r in choice.get("variants") or [] if r.get("options")]
    # a seller's "write a delivery message" row is not a version of the product (2026-11-05: 선택사항 = 인기조합 /
    # 배송메세지기입 on a TaylorMade set); a product of only such rows keeps them (nothing else to sell)
    real = [r for r in rows if not any(_DELIVERY_NOTE_RE.search(v) for v in r["options"])]
    rows = real or rows
    if rows and any(len(r["options"]) != len(names) for r in rows):           # rows that do not fit the groups:
        return {"options": [], "facts": [], "variants": [], "held": [{             # never publish one of them alone
            "code": "options_unaligned", "detail": f"{len(names)} option groups, rows of "
            f"{sorted({len(r['options']) for r in rows})} values"}], "skipped_paid": 0, "duplicate_values": [],
            "capped": None}
    package = {p.get("variant_id"): p.get("fields") for p in line.get("package") or []}
    product_id = line["details"]["id"]
    skipped = choice.get("skipped_paid") or 0
    facts: list[dict[str, str]] = []
    if not rows:                                   # no options: one default variant at the product's price
        return {"options": [], "facts": facts, "held": [] if not names else [{"code": "no_variants", "detail":
                f"{len(names)} option groups, no variant chosen (paid={choice.get('paid')})"}],
                "variants": [_variant(rules, key, product_id, [], base, None, True, package.get(None))],
                "skipped_paid": skipped, "duplicate_values": [], "capped": None}
    keep, rows = _drop_promo_axes(names, rows)
    capped = None
    page_order = {i: list(dict.fromkeys(_tidy(r["options"][i]) for r in rows)) for i in keep}
    if len(rows) > rules.variant_cap:              # more than the shop sells: the first ones, every value kept
        varying = [i for i in keep if len({_tidy(r["options"][i]) for r in rows}) > 1]
        capped = f"{len(rows)} -> {rules.variant_cap}"
        rows = _capped(rows, varying, rules.variant_cap)
    values = {i: [v for v in page_order[i] if any(_tidy(r["options"][i]) == v for r in rows)] for i in keep}
    axes = [i for i in keep if len(values[i]) > 1]
    shown = {i: {v: v for v in values[i]} for i in keep}
    duplicate = []
    for i in axes:                                 # "선택1 9도SR" -> "9도SR"; kept when two values would then be one
        plain = _unnumbered(values[i])
        if plain and len(set(plain)) == len(plain):
            shown[i] = dict(zip(values[i], plain))
            values[i] = plain
        elif plain:
            duplicate.append(_tidy(names[i]))
    for i in keep:
        if i not in axes and names[i] not in HIDDEN_ROWS:      # a one-value 상품번호 axis is a seller code
            label = _tidy(names[i])                            # "선택: 남성풀세트": the value says it all
            label = _axis_name(label)
            facts.append({"label_ko": "" if _PLACEHOLDER_NAME_RE.match(label) else label, "value_ko": values[i][0]})
    today = {v.get("id"): v.get("is_today_dispatch") for v in (specs["options"] or {}).get("variants") or []}
    variants = [_variant(rules, key, product_id, r["options"], r["price"], r.get("id"), r.get("is_available"),
                         package.get(r.get("id")), [shown[i][_tidy(r["options"][i])] for i in axes],
                         today.get(r.get("id"))) for r in rows]
    if not axes:
        variants = variants[:1]                    # one row (or only constant axes): the default variant
    held = []
    if len(axes) > MAX_AXES:
        held.append({"code": "axes_over_3", "detail": f"{len(axes)} option axes"})
    return {"options": [{"name_ko": _axis_name(names[i]), "values_ko": values[i]} for i in axes], "facts": facts,
            "variants": variants, "held": held, "skipped_paid": skipped, "duplicate_values": duplicate,
            "capped": capped}


def _variant(rules: ShopRules, key: str, product_id: str, tuple_ko: list[str], krw: int | None,
             naver_id: str | None, available: bool | None, package: Any, shown: list[str] | None = None,
             today: bool | None = None):
    source_id = "observed:" + json.dumps(tuple_ko, ensure_ascii=False, separators=(",", ":")) if tuple_ko \
        else str(product_id)
    return {"source_id": source_id, "naver_variant_id": naver_id, "options_ko": shown or [],
            "price_krw": krw, "price_usd": None if krw is None else usd(krw, rules.krw_per_usd),
            "sku": sku(rules.sku_prefix, key, source_id), "available": available is not False, "package": package,
            "today_dispatch": today}   # the seller sends this variant the same day (todayDispatch; one of two, 8958060680)


# ---- the rest of the product --------------------------------------------------------------

# Naver's "no value" codes: a 제조사 of "M0000000" is its placeholder for no manufacturer (seen 2026-11-08,
# 13464713764: the page row and naverShoppingSearchInfo.manufacturerName both say it); never a spec or a hint
_PLACEHOLDER_CODE = re.compile(r"^[A-Z]0{6,}$")


def spec_rows(specs: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for r in specs.get("specs") or []:
        label, value = r.get("label"), r.get("value") or ""
        if label == "원산지":                       # the reseller's purchase agency / importer is not an origin
            value = _AGENCY_RE.sub("", value)
            inner = value[value.find("("):] if "(" in value else ""
            if len(set(_COUNTRY_RE.findall(inner))) < 2:   # brackets naming 2+ countries are the parts' origins
                while _BRACKETS_RE.search(value):
                    value = _BRACKETS_RE.sub("", value)
            value = re.sub(r"\s+", " ", value).strip()
        if label not in HIDDEN_ROWS and value and not _pointer(value) and not _PLACEHOLDER_CODE.match(value.strip()):
            out.append({"label_ko": label, "value_ko": value})
    return out


def _relative(run: str, product_id: str, file: str | None) -> str | None:
    return f"collected/{run}/images/{product_id}/{os.path.basename(file)}" if file else None


def images(line: dict[str, Any], run: str) -> list[dict[str, Any]]:
    pid = line["details"]["id"]
    return [{"position": f["position"], "file": _relative(run, pid, f["file"]), "sha256": f["sha256"],
             "width": f["width"], "height": f["height"]} for f in (line.get("photos") or {}).get("files") or []]


def reviews(line: dict[str, Any], run: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    picked = line.get("reviews") or {}
    summary = picked.get("summary") or line["details"].get("reviews") or {}
    rating = ({"value": summary.get("average_score"), "count": summary.get("count")}
              if summary.get("count") else None)
    pid = line["details"]["id"]
    media: dict[str, dict[str, Any]] = {}
    for f in (line.get("review_media") or {}).get("files") or []:
        m = media.setdefault(f["review_id"], {"photos": [], "avatar": None})
        if f["kind"] == "review-image":
            m["photos"].append(_relative(run, pid, f["file"]))
        else:
            m["avatar"] = _relative(run, pid, f["file"])
    out = []
    for r in picked.get("results") or []:
        m = media.get(r["id"], {"photos": [], "avatar": None})
        out.append({"id": r["id"], "score": r["score"], "text_ko": r["text"], "created_at": r["created_at"],
                    "writer": (r.get("writer") or {}).get("masked_id"), "photos": m["photos"],
                    "avatar": m["avatar"], "tier": r.get("tier")})
    return rating, out


def personalization(specs: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"label_ko": re.sub(r"\s+", " ", _LABEL_DECOR_RE.sub("", t.get("label") or t.get("name") or "")).strip(),
             "required": bool(t.get("required")),
             "max_length": t.get("max_length"), "placeholder_ko": t.get("placeholder")}
            for t in (specs.get("options") or {}).get("text_options") or []]


def _plain(text: str) -> str:
    """"1-1.남성 장갑" -> "남성 장갑": an add-on's numbering is the seller's list order, not its name."""
    return _NUMBERING_RE.sub("", _ADDON_CODE_RE.sub("", _tidy(text))).strip() or _tidy(text)


def addons(specs: dict[str, Any], krw_per_usd: int, paid: bool = False) -> list[dict[str, Any]]:
    """Add-ons on sale and in stock: free ones only, paid ones too with the category's `paid_addons`. A group
    named (필수) / (필수선택) must be chosen: `required`, the decoration dropped."""
    out = []
    for s in (specs.get("options") or {}).get("supplements") or []:
        price = s.get("price") or 0
        if (price == 0 or paid) and s.get("status") in (None, "SALE") and (s.get("stock_quantity") or 0) > 0:
            group = s.get("group") or ""
            out.append({"group_ko": _plain(_LABEL_DECOR_RE.sub("", group)), "name_ko": _plain(s.get("name") or ""),
                        "required": bool(_REQUIRED_RE.search(group)), "price_krw": price,
                        "price_usd": usd(price, krw_per_usd)})
    return out


def _texts(product: dict[str, Any]) -> list[dict[str, str]]:
    found: list[tuple[str, str]] = [("title", product["title_ko"]), ("brand", product["brand_ko"])]
    for o in product["options"]:
        found += [("option_name", o["name_ko"])] + [("option_value", v) for v in o["values_ko"]]
    for kind, rows in (("fact", product["facts"]), ("spec", product["specs"])):
        for r in rows:
            found += [(f"{kind}_label", r["label_ko"]), (f"{kind}_value", r["value_ko"])]
    found += [("text_label", p["label_ko"]) for p in product["personalization"]]
    found += [("text_placeholder", p["placeholder_ko"]) for p in product["personalization"]]
    for a in product["addons"]:
        found += [("addon_group", a["group_ko"]), ("addon_name", a["name_ko"])]
    found += [("review", r["text_ko"]) for r in product["reviews"]]
    out, seen = [], set()
    for kind, ko in found:
        if ko and (kind, ko) not in seen:
            seen.add((kind, ko))
            out.append({"id": text_id(kind, ko), "kind": kind, "ko": ko})
    return out


def _images_unread(sidecar: dict[str, Any] | None) -> list[dict[str, str]]:
    """The stage could not read this product (description_images_failed: its error; --force reads it again), or
    some of its images (description_images_partial: n of m, by status: failed = 5xx / network, read again next
    run; gone = 4xx / not an image; refused = a seller's host blocks hotlinks)."""
    if not sidecar:
        return []
    if sidecar.get("error"):
        return [{"code": "description_images_failed", "detail": str(sidecar["error"])[:200]}]
    images = sidecar.get("images") or []
    unread = Counter(i["status"] for i in images if i.get("status") in ("failed", "gone", "refused"))
    if not unread:
        return []
    return [{"code": "description_images_partial", "detail": f"{sum(unread.values())} of {len(images)} images not "
             f"read ({', '.join(f'{k} {v}' for k, v in sorted(unread.items()))})"}]


@functools.lru_cache(maxsize=1)
def _measures_table() -> dict[str, Any]:
    return load_table()


def _image_measures(ov: dict[str, Any], sidecar: dict[str, Any] | None, title: str, model: str,
                    pieces: re.Match | None, spec_rows_raw: list[dict[str, Any]], category_id: str | None) -> list[dict[str, str]]:
    """Merge the description images' size / weight guess into each variant's package (description_measures):
    per field the larger of today's value and the guess. With the category's parts profile: the item count of a
    variant is its option values' ("12종"), else the title / 모델명's, else the profile's count row (총클럽개수),
    else the images'; the container: its option values, else the title and the product's one-value facts, else
    the images."""
    if sidecar is None:
        return [{"code": "description_images_missing", "detail": "no sidecar: run description_images.py"}]
    profile = profile_for(category_id)               # by the Naver leaf category id; None: the core only
    facts = read_rows(image_rows(sidecar, with_conf=True), profile)
    row: dict[str, Any] = next((r for r in _measures_table().get("rows", [])
                                if str(r["category_id"]) == str(category_id)), {})
    band = profile.count if profile else (0, 0)
    counted = [int(pieces.group(1))] if pieces else []
    if profile and profile.count_row:
        counted += [int(m.group(1)) for r in spec_rows_raw if r.get("label") == profile.count_row
                    for m in [_COUNT_ROW_RE.match(r.get("value") or "")] if m]
    product_count = next((c for c in counted if band[0] <= c <= band[1]), None)     # not a 2-club "set"
    product_text = " ".join([title, model] + [f["value_ko"] for f in ov["facts"]])
    taken: dict[str, int] = {}
    for v in ov["variants"]:
        if not v.get("package"):
            continue
        text = " ".join(v["options_ko"])
        own = [int(m.group(1)) for m in _PIECES_RE.finditer(text) if band[0] <= int(m.group(1)) <= band[1]]
        has = container_in(text, profile)
        v["package"], names = package_for(v["package"], facts, max(own) if own else product_count,
                                          has if has is not None else container_in(product_text, profile),
                                          row.get("plausible"), profile)
        for name in names:
            taken[name] = taken.get(name, 0) + 1
    if not taken:
        return []
    return [{"code": "measures_from_images", "detail": ", ".join(
        f"{n} {c}/{len(ov['variants'])}" for n, c in sorted(taken.items()))}]


def prepare(line: dict[str, Any], rules: ShopRules, run: str, line_no: int,
            images_text: dict[str, Any] | None = None) -> Prepared:
    key = line["key"]
    details, specs = line.get("details"), line.get("specs")
    held: list[dict[str, str]] = []
    notes: list[dict[str, str]] = []
    source = {"run": run, "line": line_no, "link": (details or {}).get("link"),
              "channel_no": key.split(":")[2], "product_id": key.split(":")[3],
              "category_id": ((specs or {}).get("category") or {}).get("id")}
    if not details or not specs or specs.get("options") is None:
        return {"format": FORMAT, "key": key, "shop": rules.shop.value, "status": "held",
                "held": [{"code": "collect_incomplete", "detail": "no details / specs / options answer"}],
                "notes": notes, "source": source, "product": {}, "texts": []}
    category = specs.get("category") or {}
    cat = rules.category(category.get("id"), category.get("name"))
    ov = options_and_variants(line, rules, key, cat)
    held += ov["held"]
    simple_facts, simple_left = simple_choices(specs)
    ov["facts"] = ov["facts"] + simple_facts
    if simple_left:                                 # chosen at the order, not a variant: the operator decides
        notes.append({"code": "simple_options_left_out", "detail": ", ".join(simple_left)})
    # neutral attributes (the seller's gender, ...) with their evidence; the shop's sections are decided at the
    # last stage before Shopify from them (placement.py, the owner 2026-11-08), never here
    stated = attributes.extract([(v["sku"], list(v.get("options_ko") or [])) for v in ov["variants"]],
                                specs.get("specs") or [], details.get("name"),
                                (line.get("listing") or {}).get("query"))
    if details["pricing"].get("discounted_price") is None:
        held.append({"code": "price_unknown", "detail": "no product price"})
    facts = specs.get("facts") or {}
    brand = facts.get("brand") or {}
    maker = facts.get("manufacturer") or {}
    if not brand.get("value") and maker.get("value") and not _PLACEHOLDER_CODE.match(str(maker["value"]).strip()) \
            and not _pointer(str(maker["value"])):
        # no brand: the manufacturer (the owner, 2026-11-08); still none: brand_fallback.py, run-level
        brand = {"value": maker["value"], "source": f"manufacturer:{maker.get('source')}"}
    imgs = images(line, run)
    if not imgs:
        held.append({"code": "no_images", "detail": "no gallery photo saved"})
    if len(imgs) > MAX_IMAGES:
        held.append({"code": "images_over_50", "detail": f"{len(imgs)} photos"})
    rating, picked = reviews(line, run)
    if rating and rating["count"] and not picked:
        notes.append({"code": "reviews_none_chosen", "detail": f"{rating['count']} reviews, none chosen"})
    if (line.get("variants") or {}).get("name_mismatches"):
        notes.append({"code": "price_name_mismatch", "detail": ",".join(line["variants"]["name_mismatches"])})
    if ov["skipped_paid"]:                          # a smaller set than the title may describe is sold
        notes.append({"code": "paid_variants_left_out", "detail": f"{ov['skipped_paid']} variants change the price"})
    one = title_one_variant(details["name"], ov["options"])
    if one:                                         # the translation keeps the title to what every variant is
        notes.append({"code": "title_names_one_variant", "detail": ", ".join(one)})
    desc = details.get("description") or {}
    checked = check_specs(spec_rows(specs), ov["options"], ov["variants"], desc.get("text"), details["name"])
    shown_specs = checked["specs"]                  # rows true of part of the variants: bound (for_ko) or dropped
    notes += checked["notes"]
    if ov["capped"]:                                # combinations past the shop's cap are not offered
        notes.append({"code": "variants_capped", "detail": ov["capped"]})
    if ov["duplicate_values"]:                      # "선택3 S" / "선택6 S": the numbering is the only difference
        notes.append({"code": "option_values_duplicate", "detail": ", ".join(ov["duplicate_values"])})
    model = next((r.get("value") or "" for r in specs.get("specs") or [] if r.get("label") == "모델명"), "")
    pieces = _PIECES_RE.search(f"{details['name']} {model}")
    count = next((_COUNT_ROW_RE.match(r.get("value") or "") for r in specs.get("specs") or []
                  if r.get("label") == "총클럽개수"), None)
    bigger = any(int(m.group(1)) > 5 for o in ov["options"] for v in o["values_ko"]
                 for m in _PIECES_RE.finditer(v))   # values of 4종 and 12종 sets: the title names one (6999516176)
    if pieces:                                      # the title / 모델명 count wins: "(3종)" few, "12pc" a full set
        if int(pieces.group(1)) <= 5 and not bigger:   # even when its 총클럽개수 row says 3개 (13780241403)
            notes.append({"code": "few_pieces", "detail": pieces.group(0)})
    elif _HALF_SET_RE.search(details["name"]):      # "하프세트": a half set (10954221464)
        notes.append({"code": "few_pieces", "detail": "하프세트"})
    elif count and 0 < int(count.group(1)) <= 5:    # 총클럽개수 3개: driver + wood + hybrid (13302492097)
        notes.append({"code": "few_pieces", "detail": f"총클럽개수 {count.group(1)}개"})
    if cat.description_images:                      # the images' guess: the larger of it and today's value
        if images_text is not None and not current(images_text, line):
            notes.append({"code": "description_images_stale", "detail": "sidecar read from other links: run "
                          "description_images.py again"})
        else:
            notes += _image_measures(ov, images_text, details["name"], model, pieces, specs.get("specs") or [],
                                     category.get("id"))
            notes += _images_unread(images_text)
    vague = [o["name_ko"] for o in ov["options"] if _PLACEHOLDER_NAME_RE.match(o["name_ko"])
             or _COLOUR_AXIS_RE.match(o["name_ko"]) and not any(_COLOUR_WORD_RE.search(v) for v in o["values_ko"])]
    if vague:                                       # the translation names such an axis from its values
        notes.append({"code": "option_name_placeholder", "detail": ", ".join(vague)})
    paid_addons = [s for s in (specs.get("options") or {}).get("supplements") or [] if (s.get("price") or 0) > 0]
    if paid_addons and not cat.paid_addons:
        notes.append({"code": "paid_addons_left_out", "detail": f"{len(paid_addons)} paid add-ons"})
    if not specs.get("is_complete", True):
        held.append({"code": "specs_folded", "detail": f"상품정보 left folded: {len(specs.get('specs') or [])} rows"})
    delivery = specs.get("delivery") or details.get("delivery") or {}
    if (delivery.get("base_fee") or 0) > 0:
        notes.append({"code": "shipping_paid", "detail": f"{delivery.get('fee_type')} {delivery.get('base_fee')} KRW"})
    if delivery.get("is_overseas"):
        notes.append({"code": "overseas_shipping", "detail": str(delivery.get("customs_tax_type") or "")})
    hidden_promo = [r for r in specs.get("specs") or [] if r.get("label") in ("이벤트", "사은품")]
    things = [r["value"] for r in hidden_promo if r.get("label") == "사은품" and r.get("value")
              and not _POINTS_RE.search(r["value"])]
    if things:                                      # "오리지널커버 증정": head covers in the box, not points; hidden
        notes.append({"code": "gift_hidden", "detail": "; ".join(things)})   # with the promotions: list or not?
    raw = desc.get("text") or ""
    if hidden_promo and _GIFT_RE.search(raw):       # the rows are hidden as Naver's promotions; the text still
        notes.append({"code": "description_mentions_gifts", "detail": ", ".join(        # promises them
            sorted({m.group(0) for m in _GIFT_RE.finditer(raw)}))})
    cleaned = clean(desc.get("text"), store_name=(details.get("store") or {}).get("name"),
                    promo_hidden=bool(hidden_promo), brand=details.get("brand"))
    notes += [{"code": n["code"], "detail": n["detail"]}
              for n in cleaned["notes"] + body_notes(desc.get("html"), desc.get("images"))]
    pictures = clean_images(desc.get("images"), desc.get("html"))
    extra_text = delivery.get("extra_fee_text")
    number = re.sub(r"[,\s원]", "", extra_text or "")
    returns = " ".join(f"{r.get('label')} {r.get('value')}" for r in (details.get("notice") or {}).get("terms") or []
                       if "반품" in f"{r.get('label')}")
    if number.isdigit() and not _AREA_WORD_RE.search(extra_text or "") \
            and re.search(rf"(?<!\d){number}\s*원", returns.replace(",", "")):
        extra_text = None                           # "18000" = the return fee stated in the notice, typed there
    agency = json.dumps([specs.get("specs"), details.get("notice"), delivery.get("policy_text")], ensure_ascii=False)
    if _AGENCY_WORD_RE.search(agency):              # bought abroad for the buyer: returns / customs differ
        notes.append({"code": "purchase_agency", "detail": "구매대행 in the specs / notice / delivery policy"})
    if not (line.get("photos") or {}).get("is_complete", True):
        notes.append({"code": "photos_incomplete", "detail": f"{len(imgs)} of {line['photos'].get('total')}"})
    product = {
        "title_ko": details["name"], "brand_ko": brand.get("value"), "brand_source": brand.get("source"),
        "attributes": stated, "options": ov["options"], "facts": ov["facts"], "variants": ov["variants"],
        "pricing": {"base_krw": details["pricing"].get("discounted_price"),
                    "original_krw": details["pricing"].get("sale_price"), "krw_per_usd": rules.krw_per_usd,
                    "rounding": "ceil-cent", "taxable": False, "compare_at": None},
        "specs": shown_specs, "personalization": personalization(specs),
        "addons": addons(specs, rules.krw_per_usd, cat.paid_addons),
        "rating": rating, "reviews": picked, "images": imgs,
        "delivery": {**{k: delivery.get(k) for k in ("scope", "fee_type", "base_fee", "is_overseas",
                                                     "customs_tax_type", "extra_fee_area2", "extra_fee_area3",
                                                     "policy_text", "lead_time")}, "extra_fee_text": extra_text},
        "description_ko": cleaned["text"],                                     # not in `texts` yet: a later
        "description_images": pictures["images"],                              # translation decision
        "description_dropped": [dict(d) for d in cleaned["dropped"]] + [            # the seller's boilerplate,
            {"rule": "banner_image", "text": d["link"]} for d in pictures["dropped"]],  # for audit
    }
    return {"format": FORMAT, "key": key, "shop": rules.shop.value, "status": "held" if held else "ready",
            "held": held, "notes": notes, "source": source, "product": product, "texts": _texts(product)}
