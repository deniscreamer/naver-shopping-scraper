"""Transform: one collected product (an example_99 line) -> a prepared product for one shop. Pure, offline,
deterministic: no AI, no network, no English. Korean stays Korean; `texts` lists every Korean text the
translation stage must translate. The collected line is never changed.

Why each rule (research 2026-11-05: 23 collected products, 13 of them compared one to one with what the
naver-harvester published, and its 60 published products):

  * prices: krw = the product's price + the variant's extra_price (the page's own answer); usd = KRW rounded up to
    the cent at the shop's rate (kept in the record; Shopify's cost and price are made at publication by
    shop_pricing); no compare-at, not taxable. Our extra_price gave the harvester's
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
  * brand: the 브랜드 row / brandName (never 기타, "other"), else the manufacturer (never Naver's M0000000 or a
    pointer); none ->
    run_transform's brand_fallback.
  * text fields (a name on a tag) -> personalization; add-ons on sale and in stock: free ones, paid ones too
    with the category's paid_addons (price in KRW and USD); a (필수) group is required.
  * held (not published, kept with codes): collect_incomplete, price_unknown, no_variants,
    options_unaligned, axes_over_3, specs_folded, no_images, images_over_50, single_only, not_wedge_set;
    run_transform adds agency_no_brand (all of them: scripts/TRANSFORM.md "Held codes"). More combinations than the shop's
    cap: the first ones are offered, every option value kept (note variants_capped).
  * notes (never block): shipping_paid, overseas_shipping (a shop with the price rule puts a PAID / UNIT_QUANTITY_PAID
    fee into the purchase: shop_pricing),
    brand_fallback (no brand and no manufacturer stated: run_transform takes one from the
    title, the origin's importer, the images' text, or 노브랜드; brand_fallback.py),
    option_name_placeholder (선택 / 선택2 / 옵션: named from the values in translation),
    paid_addons_left_out, paid_variants_left_out, title_names_one_variant, purchase_agency, price_name_mismatch,
    photos_incomplete, reviews_none_chosen, reviews_cleaned (review_clean.py: kept, by grade, trimmed), measures_from_images / description_images_missing / _stale / _failed / _partial (the category's
    description_images switch: the package fields the description states or its parts compose, in place of the
    category default; description_measures.py).

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
from typing import Any, Mapping, TypedDict

import attributes
import brand_fallback
from description_clean import body_notes, clean, clean_images, decode_line
from description_images import current, image_rows
from description_measures import composition_count, container_in, container_listed, package_for, profile_for, read_rows
from naver_variants import choose_variants
from package_measures import current_defaults, load_table, on_scale
from spec_variants import check_specs, title_one_variant, title_variant_tail
from review_clean import clean_reviews
from shop_types import (CollectedLine, PreparedAddon, PreparedImage, PreparedPersonalization, PreparedProduct,
                        PreparedRating, PreparedSource, PreparedVariant)
from transform_shops import CategoryRules, ShopRules

FORMAT = "prepared/5"           # 2 (2026-11-07): package fields may carry how / quote / flags / compared;
                                 # product.description_images_text (run_transform); 3 (2026-11-08): no shop
                                 # leaves, product.attributes instead (the shop's sections: placement.py);
                                 # 4 (2026-11-08): reviews sanitized (review_clean.py): text_ko cleaned,
                                 # text_original_ko, text_cut, text_grade, text_quality; every review kept
                                 # (its score) but sponsored ones; 5 (2026-11-10): package confidence 1-5 (1-3
                                 # before), a field may be `source: composed` with parts / baseline / refused
MAX_AXES = 3                       # Shopify options per product
MAX_IMAGES = 50
HIDDEN_ROWS = {"상품번호", "제조일자", "이벤트", "사은품", "인증정보"}     # 인증정보: purchase-agency / KC legal text
_AGENCY_RE = re.compile(r"\(?\s*(?:해외\s*)?구매\s*대행\s*\)?")             # 원산지 "일본산(구매대행)", "해외구매대행"
_DELIVERY_NOTE_RE = re.compile(r"배송\s*메[세시]지")                         # a row asking for a delivery note
# a seller's contact note, never a product (2026-11-15, the iron sets' review): a phone number or "(문의 ...)" in an
# option name ("샤프트 선택(문의010-7229-8779)"); an option value or add-on choice that only asks the buyer to call or
# write ("커스텀 오더는 톡톡 문의 부탁드립니다.", "특주주문시 연락주세요(02-2200-1633)"), its brackets aside
_PHONE_RE = re.compile(r"\(?\s*(?:문의|tel|☎)?\s*0\d{1,2}[-\s.]?\d{3,4}[-\s.]?\d{4}\s*\)?", re.I)
_CONTACT_PAREN_RE = re.compile(r"\([^()]*(?:문의|연락|톡톡)[^()]*\)")
_CONTACT_RE = re.compile(r"문의|연락\s*(?:주|바|부탁)|톡톡")


def _contact_only(text: str) -> bool:
    """An option value or add-on choice that is only a request to contact the seller."""
    core = _PHONE_RE.sub("", _CONTACT_PAREN_RE.sub("", text or "")).strip()
    if _CONTACT_RE.search(core):                   # ... and names nothing of the product (a club, a shaft, a count)
        return not re.search(r"아이언|샤프트|강도|플렉스|우드|드라이버|퍼터|웨지|\d", core)
    return bool(text and not core and _PHONE_RE.search(text))
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
# 2026-11-11 (300 sets): a club count in an option value ("4개 스틸 건백", "12개세트 카본 R", "10클럽", "12+볼백"), a
# typed numbered composition ("1> 드라이버"), set words that keep a listing a set, a women's set (its driver row)
_OPTION_COUNT_RE = re.compile(r"(?<![\d.+~])(\d{1,2})\s*(?:개(?![월입])|클럽|\+\s*(?:볼|캐디|골프|스탠드)\s*백)")
_NUMBERED_RE = re.compile(r"^\s*\d\s*[>)]\s*\S")
_KIND_RE = re.compile(r"드라이[버브]|우드|유틸|하이브리드|아이언|웨지|퍼터|\bIR\b|\bI\b|\d\s*[~\-]\s*(?:\d|[PAGS]W?\b)")
_SOFT_FLEX_RE = re.compile(r"(?<![A-Za-z])[LA](?![A-Za-z])|레이디")
_HARD_FLEX_RE = re.compile(r"(?<![A-Za-z])(?:R|S|SR|X)(?![A-Za-z])|남성")


def _closed_list(text: str, profile: Any) -> bool:
    """The clubs listed with no bag: three kinds or more down to the putter ("11.5L 5번유틸 7아이언 퍼터": 8437045488;
    "10.5R유틸4번R8아이언R퍼터": 10208717296), or two kinds or more with a count ("드라이버 10.5도 R, 아이언 6개":
    12999322418; the typed "드라이버+8개아이언 9개 구성": 12931412033; 2026-11-11)."""
    if not text or profile.container_word.search(text) or not profile.kind_word:
        return False
    kinds = {w for w in profile.kind_word.findall(text)}
    return len(kinds) >= 3 and "퍼터" in kinds \
        or len(kinds) >= 2 and composition_count(text, profile) is not None   # (the driver often a loft: "10.5R")


_SET_OPTION_RE = re.compile(r"세트|풀\s*세트|볼\s*백|캐디\s*백|골프\s*백|건\s*백|스탠드\s*백")
_CLOSED_TITLE_RE = re.compile(r"[\[(]\s*(?:드라이버|우드|유틸|아이언)[^\])]*\+[^\])]*[\])]")
_IRONS_RE = re.compile(r"^\s*(?:\d{1,2}|[PAGSW])(?:\s*,\s*(?:\d{1,2}|[PAGSW]|PW|AW|SW)){3,}\s*$")
_SET_RE = re.compile(r"세트|풀\s*세트|\d\s*(?:PCS|pcs|피스|개)")
_LADIES_RE = re.compile(r"여성|레이디|ladies|우먼|women", re.I)
_MENS_RE = re.compile(r"남성|남자|men'?s(?!.*women)|남녀", re.I)
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
    source: PreparedSource
    product: PreparedProduct          # shop_types.py
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


# a seller's note inside an option value, not a version (2026-11-15, the iron sets' review: "L/세금미포함" -> "L /
# Tax Not Included", "A(주문전문의)" -> "A (Custom Order)" were published): tax, "ask before ordering", dispatch today
_VALUE_NOTE_RE = re.compile(r"\s*[/,\-]?\s*[(\[]?\s*(?:세금\s*미\s*포함|부가세\s*(?:별도|미포함)|주문\s*전\s*문의|"
                            r"(?:오늘|당일|즉시)\s*(?:출발|출고|발송))\s*[)\]]?\s*")


def _without_notes(values: list[str]) -> list[str] | None:
    """The values without a seller's note, when one carries it, none is left empty and they stay different."""
    out = [_VALUE_NOTE_RE.sub(" ", v).strip(" /-") for v in values]
    if out == values or not all(out) or len(set(out)) != len(out):
        return None
    return out


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
    name = _tidy(_PHONE_RE.sub("", _CONTACT_PAREN_RE.sub("", name or ""))) or _tidy(name)   # a phone note goes
    return _CHOOSE_TAG_RE.sub("", name) or name


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


# a variant that sells one club of a set-or-single listing (sets_only, wedges 2026-11-15, the pilot's variants: "60
# Degree-1PC", "RH Black 52 Degree", "GRF539-52 degrees", "52 Degree Wedge / Silver"): a single word, or exactly one
# loft (44-72, a number of its own: "i60R" is a shaft) with no set word or count of two or more
_SINGLE_WORD_RE = re.compile(r"(?i)(?<![0-9])1\s*(?:pcs?|개|ea)(?![a-z])|단품|개별|싱글|single|낱개")
_SET_WORD_RE = re.compile(r"(?i)set|세트|셋트|(?<![0-9])[2-9]\s*(?:pcs?|개|종|피스|p)(?![a-z])")
_ONE_PIECE_RE = re.compile(r"(?i)(?<![0-9])1\s*(?:개|pcs?|ea)(?![a-z0-9])\s*[)\]]?\s*$")   # the title's end: one piece
_LOFT_RE = re.compile(r"(?<![0-9A-Za-z])(?:4[4-9]|5[0-9]|6[0-9]|7[0-2])(?![0-9A-Za-z])")   # "i60R" is a shaft


def _club_slots(names: list[str]) -> bool:
    """Option axes that each pick one club of the set: names equal but for a number ("옵션 1" / "옵션 2", "웨지 로프트
    바운스 선택-1" / "-2" / "-3", "SB웨지1" / "SB웨지2"): the same loft on two of them is two clubs."""
    return len(names) > 1 and len({re.sub(r"[\d\s\-_/.#]+$", "", re.sub(r"\d+", "#", n)).strip() for n in names}) == 1


def single_club(values: list[str], names: list[str] | tuple[str, ...] = ()) -> bool:
    """The variant's own words say it sells one club (sets_only). A loft repeated on axes that describe one club
    ("Size: 56 Degree" + "Style Name: Black 56 Degree", Yamato 12951827729 / 12921931106, 2026-11-15: published as
    sets, every variant one wedge) counts once; on axes that are club slots (_club_slots: TaylorMade MG5 "52.09 SB" on
    옵션 1 and 옵션 2) each counts."""
    text = " ".join(values)
    if _SET_WORD_RE.search(text):
        return False
    lofts = _LOFT_RE.findall(text)
    if not _club_slots(list(names)):
        lofts = list(set(lofts))
    return bool(_SINGLE_WORD_RE.search(text)) or len(lofts) == 1


# a listing filed under wedge sets that sells an iron set or a full set (wedge_sets: 50002783, 2026-11-16, the
# overnight wedge scroll published 9 iron sets into the wedge-sets section: 13370424163 Cleveland ZipCore XL
# "Regular+4-PW", 13383002675 Callaway Apex "Regular+3 Iron- PW", 13385696985 TaylorMade Stealth "Stiff+5-P/A",
# 13370491895 Acer XV "( 5-9/ PW/ GW)" and "7피스 8피스", 13383404156 MAZEL "3456789피칭", 13603085795 MAZEL
# "123456789", 13377696273 Yamato "5 6 7 8 9 피윙", 13601554331 PGM "아이언 세트 59 PW SW"). Measured on the shop's 502
# listings of 50002783: no wedge set writes an iron run, a count of 6 to 16 clubs, or "아이언 세트" without "웨지 세트".
# An iron run: a start iron 3-7 ("#5", "5번", "4i", "4 Iron") to 9 / P / PW / AW / GW / SW, or a run of single
# digits ending at 9 written together ("3456789", "123456789") or apart ("5 6 7 8 9"). Not one (review 2026-11-16,
# wedge titles that could come): a day or age span ("7-9일", "3~9 days", "7-9 years"), a numbered option or a model
# number before a wedge and its loft ("1-AW 52도", "타입 2 - SW 56도", "RTX 6 - SW 56도": no start iron 1-2, no loft
# after the end), a spaced dash to a wedge with no iron word ("CBX 4 - AW/SW"); two-digit lofts ("52-56-60",
# "48-60도", "505254565860") never.
_IRON_RANGE_RE = re.compile(r"(?i)(?<![\d.a-z#])#?[3-7](?:\s*(?P<iron>번|iron|i|아이언))?(?P<sp1>\s*)[-~–](?P<sp2>\s*)"
                            r"(?:9(?![\d.])(?!\s*(?:years?|yrs?|세|살|일|days?|주|weeks?|개월|months?|시))"
                            r"|(?:pw?|피칭)(?![a-z])(?!\s*\d{2})|(?P<wedge>[ags]w)(?![a-z])(?!\s*\d{2}))")
_DIGIT_RUN_RE = re.compile(r"(?<![\d.])\d{4,9}(?![\d.])")
_SPACED_RUN_RE = re.compile(r"(?<![\d.])[1-7](?:\s*[ ,/]\s*\d(?![\d.])){3,}")
# a count of 6 to 16 clubs (a wedge set's is 2-4 in the 502 listings): "7피스", "9PCS", "11 PIECE", "12pcs" as they
# stand; "N개 / N본 / N자루" only before a set word ("10개 세트", "14본 구성"): "골프공 12개 증정", "헤드커버 10개",
# "10본 한정", "52개 샌드 56개" (a loft read as a count) and "6개월" are not one (review 2026-11-16). A count right after
# 웨지 counts wedges ("웨지 6개 세트 48 50 52 54 56 58", "웨지 6피스 세트"): a wedge set, not held.
_CLUB_COUNT_RE = re.compile(r"(?i)(?<![\d.])(\d{1,2})\s*(?:(?:피스|pcs?|pieces?)(?![a-z])"
                            r"|(?:개|본|자루)(?=\s*(?:풀\s*)?(?:세트|구성|set(?![a-z]))))")
_WEDGE_BEFORE_RE = re.compile(r"(?i)(?:웨지|wedges?)\s*$")
# also with a count between: "프로기어 04 아이언 5개 세트" (#7 #8 #9 PW AW, 10774881312, the overnight scroll 2026-11-16)
_IRON_SET_RE = re.compile(r"(?i)아이언\s*(?:\d{1,2}\s*(?:개|종|피스|pcs?|본)\s*)?세트|iron\s*set")
# "웨지 (아이언) 세트" (iron-type wedges), also with lofts, wedge letters or a count between: "웨지 AW SW 2개 세트",
# "웨지 50 56 2종 세트" (a wedge pair sold to match an iron set, review 2026-11-16)
_WEDGE_SET_RE = re.compile(r"(?i)웨지(?:\s*(?:\d{2}\s*(?:도|°)?|[agpsl]w(?![a-z])))*\s*(?:아이언\s*)?"
                           r"(?:\d{1,2}\s*(?:개|종|피스|pcs?)\s*)?세트|wedge\s*set")
# a value that is one club: KVV 13163034573 "골프 웨지 KVV 아이언 세트", variants 6 Iron / 8 Iron / Sand Wedge, one
# club a variant: not an iron set (left as it is, 2026-11-16); a single loft ("56 Degree", "56도") is one club too
_ONE_CLUB_RE = re.compile(r"(?i)\s*(?:\d{1,2}\s*(?:번\s*)?(?:iron|아이언)|(?:sand|pitching|gap|lob|approach)\s*wedge|"
                          r"(?:샌드|피칭|갭|로브|롭|어프로치)\s*웨지|[psagl]w|\d{2}\s*(?:도|°|degrees?))\s*")


# a full set, a wood set or a junior set filed under wedge sets with no iron run and under 6 clubs counted (2026-11-16,
# published the same night: 13469122120 "우드 골프 클럽 세트 3팩 드라이버 페어웨이", 13369466277 AGXGOLF "w드라이버
# 페어웨이", 12178193064 "골프클럽세트 우드 아이언 퍼터 웨지", 13312275044 PGM "III 18피스 클럽 드라이 460CC",
# 13312309860 "퍼터 ... 아이언 웨지 드라이버 ... 스탠드", 13383629001 Pro X "컴플리트 골프 세트", 13370403487 TaylorMade
# junior "4-6 years: 4 Piece Set", 13163081877 US Kids "Ages 6 to 8"). A club no wedge set holds (a driver, 460cc, a
# fairway wood, a wood, a hybrid, a utility) or a complete / full set is one in a title or a variant; not a cover or a
# grip for one ("우드 헤드커버", "드라이버 커버"), a utility wedge ("유틸리티 웨지", Olimar 4피스 웨지 세트), a "컴플리트
# 웨지 세트" (Mazek's wedge sets) or a "웨지 풀세트". A putter or a bag counts only with another club family or "클럽
# 세트" (a bag sold with a full set: World Eagle "클럽 세트 ... 11개 경량 캐디백"), never as a gift ("퍼터 증정"). A
# junior word or an age span with a set word holds unless a wedge set is written ("핑 프로디 G 주니어 골프 웨지 2종
# 세트"). Measured on the shop's 604 listings of 50002783, then 616 after the review (2026-11-16): 16 published held.
# Not a cover or a grip, also after a list of clubs ("드라이버 우드 커버 증정"); not a wedge or a sole of that kind
# ("하이브리드 웨지 세트", "유틸리티 샌드 웨지", "웨지 세트 하이브리드 솔": hybrid wedges exist); not a wood tee ("우드티
# 증정") nor a name ending in 우드 ("할리우드", "언더우드"). Review 2026-11-16, probe titles: none of them in the shop yet.
_CLUB_WORDS = r"드라이버|우드|유틸(?:리티)?|하이브리드|페어웨이|퍼터|driver|woods?|fairway|hybrid|utility|putter"
_GEAR_AFTER = (r"(?!(?:\s*(?:" + _CLUB_WORDS + r"|용|/|,|&|\+))*\s*(?:헤드\s*)?(?:커버|그립|cover|grip|headcover))")
_WEDGE_AFTER = (r"(?!\s*(?:(?:샌드|갭|롭|로브|피칭|어프로치|sand|gap|lob|pitching|approach)\s*)?"
                r"(?:웨지|wedges?|솔|soles?)(?![a-z]))")
_WOOD_RE = re.compile(r"(?i)(?:driver(?![a-z])|드라이버|460\s*cc|(?P<fairway>fairway|페어웨이)(?!\s*(?:우드|woods?))"
                      r"|fairway|페어웨이|(?<![a-z])woods?(?![a-z])(?!\s*tees?)|(?<!할리)(?<!언더)(?<!하드)(?<!로즈)우드"
                      r"(?!\s*티)|(?:hybrid|하이브리드|유틸리티|유틸(?!리티)|utility)" + _WEDGE_AFTER + r")" + _GEAR_AFTER)
# a complete / full set: not right after 웨지 ("웨지 3종 풀세트"), nor where a wedge set is written (_wedge_set_written);
# "완비" (PRECISE M3 "여성용 완비 ... 골프 클럽 세트" 13603361909), "이그제큐티브" / "골프 클럽 셋트" (AGXGOLF XLT
# Executive 13384214680), both published as wedge sets by the overnight scroll 2026-11-16
_COMPLETE_RE = re.compile(r"(?i)complete(?!\s*wedge)|컴플리트(?!\s*웨지)|풀\s*[세셋]트|풀셋|full\s*set|완비|이그제큐티브|"
                          r"executive|(?:클럽|골프채)\s*[세셋]트|club\s*set")
# a practice toy or one adjustable club, not a set of wedges ("골프 웨지 조절식 피칭 ... 퍼팅 연습 세트 연습용 폼 볼"
# 13163054038, "스포츠완구 골프 연습 세트" 13863445070, 2026-11-16)
_PRACTICE_RE = re.compile(r"(?i)조절식|조절\s*가능|adjustable|연습\s*(?:용\s*)?(?:세트|폼|볼)|practice\s*set")
_WEDGE_RIGHT_BEFORE_RE = re.compile(r"(?i)(?:웨지|wedges?)\s*(?:\d{1,2}\s*(?:개|종|피스|pcs?)\s*)?$")
_WEDGE_LETTER_RE = re.compile(r"(?i)(?<![a-z])([agsl]w)(?![a-z])")
_LOFT_DEGREE_RE = re.compile(r"(\d{2})\s*(?:도|°)")
# a count of wedges written: "웨지 3종", "3 Wedges", "3-Piece Wedges" (Mazek "여성 컴플리트 세트 웨지 3종", probe)
_WEDGE_COUNT_RE = re.compile(r"(?i)웨지\s*\d{1,2}\s*(?:개|종|피스|pcs?|본)|(?<![\d.])\d{1,2}\s*(?:-?\s*(?:pcs?|pieces?)\s*)?"
                             r"wedges?(?![a-z])")
# a putter or a bag ("골프백", not "골프 백스핀": Roiko "맥스 백스핀용"), and the gift or the gear around one ("퍼터 증정",
# "무료 캐디백", "퍼터 헤드커버 포함", "캐디백 수납"): not a club of a set
_BAG = r"(?:캐디|스탠드|카트|골프)\s*백(?!\s*스핀)"    # glued words are a seller's: "경량 캐디백블랙" (13165737174)
_PUTTER_BAG_RE = re.compile(r"(?i)퍼터|putter|" + _BAG + r"|(?:caddie|caddy|stand|cart|golf)\s*bag(?![a-z])")
_GIFT_AFTER_RE = re.compile(r"(?i)^\s*(?:용\s*)?(?:증정|사은품|서비스|gift|free|케이스|case|(?:헤드\s*)?커버|cover|headcover|"
                            r"그립|grip|포함|수납|무료)")
_GIFT_BEFORE_RE = re.compile(r"(?i)(?:증정|사은품|무료|free|bonus|보너스)\s*$")
_WITH_CLUBS_RE = re.compile(r"(?i)아이언(?!\s*(?:형|타입)?\s*웨지)|iron(?![a-z])(?!\s*-?\s*type)|퍼터|putter|"
                            r"(?P<set>클럽\s*세트|골프채\s*세트|club\s*set)")
# a junior word, or an age span of a child ("4-6 years", "3-5세", "Ages 6"): not a loft span before 세트 ("웨지 52-56
# 세트", "50-54-58 세트") nor a grown-up's ("시니어 50~60세", review 2026-11-16)
_JUNIOR_RE = re.compile(r"(?i)주니어|junior|키즈|(?<![a-z])kids?(?![a-z])|아동|어린이|유소년|(?<![a-z])ages?\s*\d"
                        r"|(?<![\d.\-~–])(?:1[0-2]|[1-9])\s*(?:-|~|–|to)\s*(?:1[0-5]|[1-9])(?![\d.])\s*"
                        r"(?:years?|yrs?|세(?!트)|살)")
_SET_IN_RE = re.compile(r"(?i)세트|셋트|set(?![a-z])")


def _wedge_set_written(texts: list[str], joined: str) -> bool:
    """A wedge set written: "웨지 (lofts) 세트" / "wedge set", a wedge count ("웨지 3종", "3 Wedges"), or two distinct
    lofts or wedge letters (a loft with ° counted once: "56°" is one)."""
    if any(_WEDGE_SET_RE.search(t) for t in texts) or _WEDGE_COUNT_RE.search(joined):
        return True
    lofts = set(_LOFT_RE.findall(joined)) | set(_LOFT_DEGREE_RE.findall(joined))
    letters = {m.lower() for m in _WEDGE_LETTER_RE.findall(joined)}
    return len(lofts) + len(letters) >= 2


def _gift(joined: str, m: re.Match[str]) -> bool:
    """A gift, a case or the gear of the putter or bag at m ("퍼터 증정", "무료 캐디백", "퍼터 헤드커버"): not a club."""
    return bool(_GIFT_AFTER_RE.search(joined[m.end():]) or _GIFT_BEFORE_RE.search(joined[:m.start()]))


def _full_set(texts: list[str]) -> str | None:
    """The word that makes a listing of wedge sets a full set, a wood set or a junior set (_WOOD_RE, _COMPLETE_RE,
    _PUTTER_BAG_RE, _JUNIOR_RE)."""
    joined = " | ".join(texts)
    written = _wedge_set_written(texts, joined)
    for m in _WOOD_RE.finditer(joined):
        if not (m.group("fairway") and written):     # "페어웨이 벙커 러프 웨지 3종 세트": where a wedge is used
            return m.group(0)
    if not written:
        for text in texts:
            for m in _COMPLETE_RE.finditer(text):
                if not _WEDGE_RIGHT_BEFORE_RE.search(text[:m.start()]):
                    return m.group(0)
    for m in _PUTTER_BAG_RE.finditer(joined):
        if _gift(joined, m):
            continue
        others = [w for w in _WITH_CLUBS_RE.finditer(joined)
                  if w.span() != m.span() and not (w.group("set") and written)
                  and not (_PUTTER_BAG_RE.fullmatch(w.group(0)) and _gift(joined, w))]
        if others:
            return m.group(0)
    if not written:     # a bag with no wedge set written: "윌슨 여성 프로필 카트백 골프 세트" (13370640792, 2026-11-16)
        for m in _PUTTER_BAG_RE.finditer(joined):
            if not re.fullmatch(r"(?i)퍼터|putter", m.group(0)) and not _gift(joined, m):
                return m.group(0)
    if (junior := _JUNIOR_RE.search(joined)) and _SET_IN_RE.search(joined) \
            and not any(_WEDGE_SET_RE.search(t) for t in texts):
        return junior.group(0)
    return None


# a variant that is one numbered iron ("우측 22년형 스틸 실버 8번 아이언", "7 Iron"); a variant of one club otherwise:
# a named wedge ("피칭 웨지", "Sand Wedge") or "아이언 2종 (세트)" (MAZEL WM-X 13762637990, 2026-11-16)
_NUMBERED_IRON_RE = re.compile(r"(?i)(?<![\d.])(\d)\s*(?:번\s*)?(?:iron|아이언)(?![a-z])")
_ONE_WEDGE_RE = re.compile(r"(?i)(?:sand|pitching|gap|lob|approach|샌드|피칭|갭|로브|롭|어프로치)\s*(?:wedge|웨지)"
                           r"|(?<![a-z])[psagl]w(?![a-z])|아이언\s*\d\s*종")


def _numbered_irons(rows: list[list[str]]) -> list[int]:
    """The irons of a listing whose every variant is one club and three or more numbered irons are among them (one iron
    a variant, MAZEL WM-X "8번 아이언"); [] otherwise (KVV: 6 Iron / 8 Iron / Sand Wedge, two irons, stays)."""
    irons: set[int] = set()
    for r in rows:
        text = " ".join(r)
        found = {int(n) for n in _NUMBERED_IRON_RE.findall(text)}
        if len(found) > 1 or (not found and not _ONE_WEDGE_RE.search(text)) or (found and _LOFT_RE.search(text)):
            return []
        irons |= found
    return sorted(irons) if len(irons) >= 3 else []


def _iron_run(text: str) -> str | None:
    for m in _IRON_RANGE_RE.finditer(text):
        if m.group("wedge") and m.group("sp1") and m.group("sp2") and not m.group("iron"):
            continue                                    # "CBX 4 - AW/SW": a model number before the wedges
        return m.group(0)
    for m in _DIGIT_RUN_RE.finditer(text):
        d = m.group(0)
        if d.endswith("9") and all(int(b) - int(a) == 1 for a, b in zip(d, d[1:])):
            return d
    for m in _SPACED_RUN_RE.finditer(text):
        n = [int(x) for x in re.findall(r"\d", m.group(0))]
        if all(b - a == 1 for a, b in zip(n, n[1:])):
            return m.group(0)
    return None


def not_wedge_set(title: str, rows: list[list[str]]) -> str | None:
    """Why a listing of a wedge-sets category (wedge_sets) sells no wedge set: an iron run in the title or a variant's
    value, a count of 6 to 16 clubs ("7피스", "12 Piece"), a full set, a wood set or a junior set (_full_set: a driver,
    a wood, a hybrid, a complete set, a putter or a bag with other clubs, an age span), a practice set or an adjustable
    club (_PRACTICE_RE), every variant one club with three
    numbered irons or more (_numbered_irons), or "아이언 세트" in the title with no "웨지 세트" (unless each variant is
    one club: KVV). None: a wedge set as far as the words go."""
    for text in [title] + [v for r in rows for v in r]:
        if run := _iron_run(text):
            return f"an iron run ({run!r})"
        counts = [int(m.group(1)) for m in _CLUB_COUNT_RE.finditer(text)
                  if not _WEDGE_BEFORE_RE.search(text[:m.start()])]
        if many := [n for n in counts if 6 <= n <= 16]:
            return f"{max(many)} clubs ({text[:40]!r})"
    if word := _full_set([title] + [v for r in rows for v in r]):
        return f"a full set, a wood set or a junior set ({word!r})"
    if m := _PRACTICE_RE.search(" | ".join([title] + [v for r in rows for v in r])):
        return f"a practice set or an adjustable club ({m.group(0)!r})"
    if irons := _numbered_irons(rows):
        return f"one numbered iron a variant ({', '.join(map(str, irons))})"
    if _IRON_SET_RE.search(title) and not _WEDGE_SET_RE.search(title) \
            and not (rows and all(any(_ONE_CLUB_RE.fullmatch(v) for v in r) for r in rows)):
        return "an iron set in the title, no wedge set"
    return None


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
    real = [r for r in rows if not any(_DELIVERY_NOTE_RE.search(v) or _contact_only(v) for v in r["options"])]
    rows = real or rows
    # an iron set or a full set filed under wedge sets (2026-11-16, the overnight wedge scroll), read on every row;
    # held after single_only, which stays the code of a listing of single wedges (12911658622 "아이언세트", by loft)
    why = not_wedge_set(re.sub(r"\s+", " ", line["details"].get("name") or ""), [r["options"] for r in rows]) \
        if cat.wedge_sets else None
    if cat.sets_only and _ONE_PIECE_RE.search(re.sub(r"\s+", " ", line["details"].get("name") or "")) \
            and not any(_SET_WORD_RE.search(" ".join(r["options"])) for r in rows):
        # "웨지 세트 52 56 60도 ... 실버 1개": the title sells one piece of the set (2026-11-15, the wedge pilot)
        return {"options": [], "facts": [], "variants": [], "held": [{"code": "single_only", "detail":
                "the title sells one piece (1개, 1pc)"}], "skipped_paid": 0, "duplicate_values": [], "capped": None}
    if cat.sets_only and rows:                     # a single club's variant is not sold; only such: held
        sets = [r for r in rows if not single_club(r["options"], names)]
        if not sets:
            return {"options": [], "facts": [], "variants": [], "held": [{"code": "single_only", "detail":
                    f"{len(rows)} variants, each one club"}], "skipped_paid": 0, "duplicate_values": [], "capped": None}
        rows = sets
    if why:
        return {"options": [], "facts": [], "variants": [], "held": [{"code": "not_wedge_set", "detail": why}],
                "skipped_paid": 0, "duplicate_values": [], "capped": None}
    if rows and any(len(r["options"]) != len(names) for r in rows):           # rows that do not fit the groups:
        return {"options": [], "facts": [], "variants": [], "held": [{             # never publish one of them alone
            "code": "options_unaligned", "detail": f"{len(names)} option groups, rows of "
            f"{sorted({len(r['options']) for r in rows})} values"}], "skipped_paid": 0, "duplicate_values": [],
            "capped": None}
    package = {p.get("variant_id"): p.get("fields") and current_defaults(on_scale(p["fields"]), line.get("specs") or {},
                                                                         p.get("variant_id"), _measures_table())
               for p in line.get("package") or []}
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
        bare = _without_notes(values[i])          # "L/세금미포함" -> "L" (a note, not a version)
        if bare:
            shown[i] = {raw: dict(zip(values[i], bare))[v] for raw, v in shown[i].items()}
            values[i] = bare
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
             today: bool | None = None) -> PreparedVariant:
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
# a 브랜드 row of "기타" ("other") names no brand (10697131625, 2026-11-11: a TaylorMade set; the model translated
# 기타 as TaylorMade once and the dictionary gave three no-name sets that brand): no brand, so the manufacturer and
# brand_fallback come next, and with nothing found the tenant's name (the owner, 2026-11-11: Fairward Golf)
NOT_A_BRAND = frozenset({"기타"})


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
        if label in ("브랜드", "제조사") and value.strip() in NOT_A_BRAND or label == "브랜드" \
                and brand_fallback.clean(value) is None \
                or label == "제조사" and brand_fallback.clean(value) is None and not brand_fallback.trade_name(value):
            # a shop's name in the brand row (세모물상점), an age (6~8세 퍼터); a 제조사 row naming an importer stays a
            # fact, one naming no firm goes ("협력업체", "중국": 13853234379, 2026-11-13)
            continue                                # "Brand: Other" says nothing (10697131625, 2026-11-11)
        if label == "브랜드":
            value = brand_fallback.clean(value) or value          # 코알라(200874), 던롭 던롭 (2026-11-12)
        if label not in HIDDEN_ROWS and value and not _pointer(value) and not _PLACEHOLDER_CODE.match(value.strip()):
            out.append({"label_ko": label, "value_ko": value})
    return out


def _relative(run: str, product_id: str, file: str | None) -> str | None:
    return f"collected/{run}/images/{product_id}/{os.path.basename(file)}" if file else None


def images(line: dict[str, Any], run: str) -> list[PreparedImage]:
    pid = line["details"]["id"]
    return [{"position": f["position"], "file": _relative(run, pid, f["file"]), "sha256": f["sha256"],
             "width": f["width"], "height": f["height"]} for f in (line.get("photos") or {}).get("files") or []]


def reviews(line: dict[str, Any], run: str) -> tuple[PreparedRating | None, list[dict[str, Any]]]:
    picked = line.get("reviews") or {}
    summary = picked.get("summary") or line["details"].get("reviews") or {}
    rating: PreparedRating | None = ({"value": summary.get("average_score"), "count": summary.get("count")}
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
                    "avatar": m["avatar"], "tier": r.get("tier"),
                    "likes": r.get("likes") if isinstance(r.get("likes"), int) else 0})   # Naver's "helpful" votes:
                                                                                          # the gallery's ranking
    return rating, out


def personalization(specs: dict[str, Any]) -> list[PreparedPersonalization]:
    return [{"label_ko": re.sub(r"\s+", " ", _LABEL_DECOR_RE.sub("", t.get("label") or t.get("name") or "")).strip(),
             "required": bool(t.get("required")),
             "max_length": t.get("max_length"), "placeholder_ko": t.get("placeholder")}
            for t in (specs.get("options") or {}).get("text_options") or []]


def _plain(text: str) -> str:
    """"1-1.남성 장갑" -> "남성 장갑": an add-on's numbering is the seller's list order, not its name."""
    return _NUMBERING_RE.sub("", _ADDON_CODE_RE.sub("", _tidy(text))).strip() or _tidy(text)


def addons(specs: dict[str, Any], krw_per_usd: int, paid: bool = False) -> list[PreparedAddon]:
    """Add-ons on sale and in stock: free ones only, paid ones too with the category's `paid_addons`. A group
    named (필수) / (필수선택) must be chosen: `required`, the decoration dropped."""
    out: list[PreparedAddon] = []
    for s in (specs.get("options") or {}).get("supplements") or []:
        price = s.get("price") or 0
        if _contact_only(s.get("name") or ""):     # "특주주문시 연락주세요(02-...)": a note, not an add-on
            continue
        if (price == 0 or paid) and s.get("status") in (None, "SALE") and (s.get("stock_quantity") or 0) > 0:
            group = s.get("group") or ""
            out.append({"group_ko": _plain(_LABEL_DECOR_RE.sub("", group)), "name_ko": _plain(s.get("name") or ""),
                        "required": bool(_REQUIRED_RE.search(group)), "price_krw": price,
                        "price_usd": usd(price, krw_per_usd)})
    return out


def _texts(product: Mapping[str, Any]) -> list[dict[str, str]]:
    found: list[tuple[str, str | None]] = [("title", product["title_ko"]), ("brand", product["brand_ko"])]
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


def _model_pieces(title: str, spec_rows_raw: list[dict[str, Any]]) -> tuple[str, re.Match | None]:
    """The 모델명 row and the piece count the title or it states ("12pc"), as prepare and the measures' fixtures
    (test_measures_fixtures.py) hand them to _image_measures."""
    model = next((r.get("value") or "" for r in spec_rows_raw if r.get("label") == "모델명"), "")
    return model, _PIECES_RE.search(f"{title} {model}")


def _image_measures(ov: dict[str, Any], sidecar: dict[str, Any] | None, title: str, model: str,
                    pieces: re.Match | None, spec_rows_raw: list[dict[str, Any]], category_id: str | None,
                    typed: str | None = None, supplements: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Merge the description's size and weight into each variant's package (description_measures): the rows of
    its images and the lines of its typed text (`typed`). A seller's value stays; in place of a category default
    goes the description's own statement of the field, else the composition from the set's parts when the
    category's row of the operator's table carries the `baselines` block.
    With the category's parts profile: the item count of a variant is its option values' ("스틸12P+캐디백": the
    variants of a listing are different sets), else the title / 모델명's ("12pc", then the profile's "클럽 10개"),
    else the profile's count row (총클럽개수: it disagrees with the title on 5 of 120 sets and the title is right on
    4), else the images' (the weakest: a page shows other sets); a full table of the items' weights goes before
    a count of pieces and gives the count nothing states (description_measures._items_total); the container, in
    the order of trust: its option values, else the title and the product's one-value facts, else the profile's
    상품정보 row (골프백포함여부), else a container sold as a paid add-on (the set has none), else the typed text's
    sentences, else the images'."""
    if sidecar is None:
        return [{"code": "description_images_missing", "detail": "no sidecar: run description_images.py"}]
    profile = profile_for(category_id)               # by the Naver leaf category id; None: the core only
    facts = read_rows(image_rows(sidecar, with_conf=True), profile,
                      [t.strip() for t in (typed or "").split("\n") if t.strip()])
    row: dict[str, Any] = next((r for r in _measures_table().get("rows", [])
                                if str(r["category_id"]) == str(category_id)), {})
    band = profile.count if profile else (0, 0)
    counted = [int(pieces.group(1))] if pieces else []
    if profile and profile.count_title:              # "야마하 cs HM+ 씨즈 10개 풀세트" with a 총클럽개수 row of
        counted += [int(g) for m in profile.count_title.finditer(f"{title} {model}")     # "3개" (10481094198)
                    for g in m.groups() if g]
    if profile and profile.count_row:
        counted += [int(m.group(1)) for r in spec_rows_raw if r.get("label") == profile.count_row
                    for m in [_COUNT_ROW_RE.match(r.get("value") or "")] if m]
    # 2026-11-11: the kinds the listing lists, after its own numbers: the 풀세트구성 row ("드라이버, 7아이언세트,
    # 유틸리티, 퍼터": 10), the typed numbered list ("1> 드라이버 ... 4> 아이언 6,7,8,9,P,S 5> 퍼터": 10, 9277462047)
    if profile and profile.composition_row:
        counted += [c for r in spec_rows_raw if r.get("label") == profile.composition_row
                    if (c := composition_count(r.get("value") or "", profile))]
    lines, numbered_lines = (typed or "").split("\n"), []  # type: list[str], list[str]
    for n, t in enumerate(lines):                    # "4> 아이언: ...", then its own line "6,7,8,9,P,S"
        if _NUMBERED_RE.match(t) or numbered_lines and n and _NUMBERED_RE.match(lines[n - 1]) and _IRONS_RE.match(t):
            numbered_lines.append(t)
    numbered = " ".join(numbered_lines)
    if profile and numbered and (c := composition_count(numbered, profile)):
        counted.append(c)
    product_count = next((c for c in counted if band[0] <= c <= band[1]), None)     # not a 2-club "set"
    product_text = " ".join([title, model] + [f["value_ko"] for f in ov["facts"]])
    options = [" ".join(v["options_ko"]) for v in ov["variants"] if v.get("options_ko")]
    single = bool(profile and (profile.single_item and profile.single_item.search(f"{title} {model}")
                               and not _SET_RE.search(f"{title} {model}")
                               or profile.single_option and product_count is None and options
                               and all(profile.single_option.match(o) for o in options)))   # one club: no bag
    listed = False if single else container_in(product_text, profile)
    if listed is True and profile and not profile.container_yes.search(product_text) and \
            any("from" in f for f in facts["container_no"]):
        listed = None          # a bare bag word in the title against the typed "<캐디백 별매>" (9266324198, 2026-11-11)
    if listed is None:
        listed = container_listed(spec_rows_raw, supplements or [], profile)
    first = " ".join((ov["variants"][0].get("options_ko") or []) if ov["variants"] else [])
    told = [t for t in (typed or "").split("\n") if "구성" in t]
    if listed is None and profile and (_CLOSED_TITLE_RE.search(title) or _closed_list(title, profile)
                                       or _closed_list(first, profile) or _closed_list(numbered, profile)
                                       or any(_closed_list(t, profile) for t in told)):
        listed = False       # "[드라이버+우드+유틸리티]", "(드라이버+아이언세트)": the title lists the clubs, no bag
                             # (13068838282, 6767889105; 2026-11-11)
    taken: dict[str, int] = {}
    for v in ov["variants"]:
        if not v.get("package"):
            continue
        text = " ".join(v["options_ko"])
        own = [int(m.group(1)) for m in _PIECES_RE.finditer(text) if band[0] <= int(m.group(1)) <= band[1]]
        # "4개 스틸 건백", "12+볼백" (2026-11-11): an option value that names no club kind; "아이언 9개", "8개구성
        # (6~S)", "IR 7개L" count the irons of a set picked over several options (13313940582, 13741964465)
        # (a variant picked over several options counts the set only where the value names the set or its bag:
        # "8개구성 NS820 (R)" beside the driver's and the wood's options is the irons, 13741704872)
        own += [int(m.group(1)) for o in v["options_ko"] if not _KIND_RE.search(o)
                and (len(v["options_ko"]) == 1 or _SET_OPTION_RE.search(o))
                for m in _OPTION_COUNT_RE.finditer(o) if band[0] <= int(m.group(1)) <= band[1]]
        has = container_in(text, profile)
        # the variant's own flex: an L / A (or 여성) variant takes its row; an R one keeps the longest (12965307704)
        ladies = bool(_SOFT_FLEX_RE.search(text) or _LADIES_RE.search(text)) and not _HARD_FLEX_RE.search(text)
        v["package"], names = package_for(v["package"], facts, 1 if single else max(own) if own else product_count,
                                          has if has is not None else listed,
                                          row.get("plausible"), profile, row.get("baselines"), ladies)
        for name in names:
            taken[name] = taken.get(name, 0) + 1
    if not taken:
        return []
    return [{"code": "measures_from_images", "detail": ", ".join(
        f"{n} {c}/{len(ov['variants'])}" for n, c in sorted(taken.items()))}]


def prepare(collected: CollectedLine, rules: ShopRules, run: str, line_no: int,
            images_text: dict[str, Any] | None = None) -> Prepared:
    key = collected["key"]
    line = decode_line(collected)                  # "u2013" written out by the seller: the character (2026-11-15)
    details, specs = line.get("details"), line.get("specs")
    held: list[dict[str, str]] = []
    notes: list[dict[str, str]] = []
    source: PreparedSource = {"run": run, "line": line_no, "link": (details or {}).get("link"),
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
    raw_maker = str((facts.get("manufacturer") or {}).get("value") or "")
    shop = details.get("store")
    if str(brand.get("value") or "").strip() in NOT_A_BRAND \
            or brand_fallback.resellers_own(str(brand.get("value") or ""), raw_maker, shop):
        brand = {}                                  # 기타; the reselling seller's own shop (재팬도코도코, 2026-11-12)
    elif brand.get("value"):                        # a shop's name (세모물상점, 2026-11-11), an age and a club,
        brand_value = brand_fallback.clean(str(brand["value"]))   # a code, a title (2026-11-12): brand_fallback.clean
        brand = {**brand, "value": brand_value} if brand_value else {}
    maker = dict(facts.get("manufacturer") or {})
    if maker.get("value"):                          # "X 협력사 / 협력 업체" (X's contract maker) names X (2026-11-11)
        maker["value"] = brand_fallback.clean(str(maker["value"])) or maker["value"]
    if brand_fallback.resellers_own(str(maker.get("value") or ""), raw_maker, shop):
        maker = {}                                  # "홈앤컴협력사" by the shop 홈앤컴: no maker named (2026-11-12)
    b_norm, m_norm = (re.sub(r"\s+", "", str(x.get("value") or "")).casefold() for x in (brand, maker))
    if b_norm and m_norm != b_norm and b_norm in m_norm and m_norm in re.sub(r"\s+", "", details["name"]).casefold() \
            and brand_fallback.clean(str(maker["value"])) and not brand_fallback.trade_name(str(maker["value"])) \
            and not re.search(r"코리아|한국|지점", str(maker["value"])):
        # the maker names a longer brand the title names too: 혼마 in the brand row, 무쯔미혼마 the maker, "무쯔미 혼마
        # 스페셜 2스타" the title (7186088743, 2026-11-15: a Mutsumi Honma set published as Honma)
        brand = {"value": maker["value"], "source": f"manufacturer:{maker.get('source')}"}
    if not brand.get("value") and maker.get("value") and brand_fallback.clean(str(maker["value"])) \
            and not _PLACEHOLDER_CODE.match(str(maker["value"]).strip()) \
            and not _pointer(str(maker["value"])) and str(maker["value"]).strip() not in NOT_A_BRAND \
            and not brand_fallback.trade_name(str(maker["value"])):
        # no brand: the manufacturer (the owner, 2026-11-08); still none: brand_fallback.py, run-level
        brand = {"value": maker["value"], "source": f"manufacturer:{maker.get('source')}"}
    imgs = images(line, run)
    if not imgs:
        held.append({"code": "no_images", "detail": "no gallery photo saved"})
    if len(imgs) > MAX_IMAGES:
        held.append({"code": "images_over_50", "detail": f"{len(imgs)} photos"})
    rating, chosen = reviews(line, run)
    if rating and rating["count"] and not chosen:
        notes.append({"code": "reviews_none_chosen", "detail": f"{rating['count']} reviews, none chosen"})
    picked, review_stats = clean_reviews(chosen, source["category_id"])
    if review_stats["in"]:
        grades = ", ".join(f"{k} {v}" for k, v in sorted(review_stats["grades"].items()))
        notes.append({"code": "reviews_cleaned", "detail": f"{review_stats['kept']} of {review_stats['in']} kept "
                      f"({grades}); {review_stats['trimmed']} trimmed"})
    if (line.get("variants") or {}).get("name_mismatches"):
        notes.append({"code": "price_name_mismatch", "detail": ",".join(line["variants"]["name_mismatches"])})
    if ov["skipped_paid"]:                          # a smaller set than the title may describe is sold
        notes.append({"code": "paid_variants_left_out", "detail": f"{ov['skipped_paid']} variants change the price"})
    one = title_one_variant(details["name"], ov["options"])
    tail = title_variant_tail(details["name"], (specs.get("options") or {}).get("variants") or [],
                              {str(v["naver_variant_id"]) for v in ov["variants"] if v.get("naver_variant_id")})
    if tail:                                        # an import title's appended option: one span, the words in it
        bare = tail.replace(" ", "")                # are not repeated ("12Black" in "Aged 9-12 Black"; 2026-11-16)
        one = [w for w in one if w.replace(" ", "") not in bare] + [tail]
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
    model, pieces = _model_pieces(details["name"], specs.get("specs") or [])
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
    if cat.description_images:                      # the description's statements, the set's composition
        if images_text is not None and not current(images_text, line):
            notes.append({"code": "description_images_stale", "detail": "sidecar read from other links: run "
                          "description_images.py again"})
        else:
            notes += _image_measures(ov, images_text, details["name"], model, pieces, specs.get("specs") or [],
                                     category.get("id"), desc.get("text"),
                                     (specs.get("options") or {}).get("supplements"))
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
    product: PreparedProduct = {
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
