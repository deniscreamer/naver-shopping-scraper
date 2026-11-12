"""The description images' OCR text (a description_images.py sidecar) -> clean Korean blocks for the translation
step. Pure, offline, deterministic. run_transform writes them per product and sets one flag on the prepared
product (description_images_text.state); the translation itself is a later step (not here).

Checked 2026-11-07 on 20 live golf sets (4369 OCR rows): prose and spec tables read well (prose near-exact, tables
~95 %), but the rows as read are not a text: 12 % of the characters are the shop's own blocks (delivery, returns,
the warehouse address, phones), 15 % of the rows repeat (slice overlaps, the same block twice), 9 % are 1-3
character fragments of photos ("B4", "ecco"), 11 % have a low OCR confidence, ~1 % are prices (a Japanese import's
"¥69,300(세금 포함)"), and a degree sign is read as a 0 ("+1.0°" -> "+1.00"). RapidOCR also leaves the spaces out of
11.8 % of prose lines (Apple Vision 0.1 %, not used: description_ocr), hence the INSTRUCTIONS line on lost spaces.
So, per read image in description order:

  rows      the sidecar's rows as read, normalised (description_ocr.norm)
  dropped   repeat (a sentence seen earlier in the product; a short or table row only within REPEAT_WINDOW
            rows: a slice overlap), cross_sell (from a 함께 구매 / 추천 상품 heading, a short row or the heading
            phrases, never a sentence or a policy line, to the end of the image), low_confidence (< MIN_CONF),
            fragment (no word of two letters and not a table row; "R / D1/296" is a table row), price (a money amount,
            가격), contact (a phone, an address with a street or a lot number, a URL, 우편번호), shop_policy
            (delivery, returns, orders, A/S, a notice card's lines: the shop's terms, not the product); an image whose
            rows are mostly shop_policy / contact is the shop's notice image: dropped whole (shop_notice_image);
            store_info (branches, hours, its channels and events, a branch list, a floor, its trade-in and fitting
            services, parking, its map's stations and shops); legal (copyright notices); promo (gifts, memberships,
            dealer claims); photo_label (a Latin-only label of a photo, no digit: "POWER TRAJECTORY")
  blocks    consecutive rows of one kind: `table` (3+ cells with a number, or a Korean label and its number:
            cells joined " | ", as the description text writes table rows) or `text` (rows as lines; " / " parts
            of one line that OCR read as separate boxes, e.g. two columns side by side); a text block also goes through
            description_clean.clean (the page text's sentence rules: store claims, promos, greetings, contacts)
  fixed     in a table row about angles (각 / ° in the row), a "1.00"-style number is the degree sign misread:
            "+1.00" -> "+1.0°"
  shared    (run level, mark_shared) every block has a `key` (its text's sha256, 16 hex); `shared` says how many
            products of one store carry it: a store's spec sheet is the product's and stays, translated once

    from description_image_text import blocks
    out = blocks(sidecar, store_name="AK골프", brand="미즈노")   # {"blocks": [{id, kind, image, text}], "dropped": {...}}
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any

import description_ocr as ocr
from description_clean import clean

FORMAT = "description_image_text/1"
TRANSLATION_FORMAT = "description_image_translation/1"
MIN_CONF = 0.6                   # RapidOCR row confidence: below it the row is mostly misread (OCR study 2026-11-07)
NOTICE_SHARE = 0.4               # an image with this share of shop rows is the shop's notice image
_CROSS_SELL = re.compile(r"함께\s*구매|추천\s*상품|같이\s*구매|관련\s*상품|다른\s*상품|BEST\s*ITEM", re.I)
# A cross-sell cut starts only at a heading: a short row, or the heading phrases. Seen 2026-11-08: a sentence did it
# (thegolf "원하시는퍼터를함께구매하시어본인만의풀세트를완성하세요!", the putter add-on, near the top of 29 stitched
# tiles: the cut to the end of the image took 292-330 rows of the set's own spec sheet on 3 Sterna listings), and so
# did shop-policy sentences ("다른 상품으로 교환하는 경우"), which the policy rule drops row by row anyway.
_CROSS_SELL_HEAD = re.compile(r"함께\s*구매하면\s*좋은|추천\s*상품|BEST\s*ITEM|관련\s*상품|같이\s*구매하면", re.I)
CROSS_SELL_HEADING = 20          # characters (no spaces): a cross-sell row this short is a heading
REPEAT_WINDOW = 12               # rows: a short or table row is a repeat only this close (a slice overlap read twice)
_WORD = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}")
_PRICE = re.compile(r"\d[\d,.]*\s*(?:원|만원)(?![가-힣])|[¥￥$€]\s*\d|\d\s*(?:엔|달러|USD|JPY)\b|가격|판매가|정상가|할인|쿠폰|적립",
                    re.I)
_CONTACT = re.compile(r"(?<![\d-])(?:0\d{1,2}|1[56]\d\d)[-. )]\s?\d{3,4}(?:[-. ]\d{4})?(?![\d-])|우편\s*번호|주소|"
                      r"https?://|www\.|\.co(?:m|\.kr)\b|[가-힣]+[시구군]\s+[가-힣\d]+(?:로|길)\s*\d+|"
                      r"[가-힣]+[시군구]\s*[가-힣\d]+[동읍면리]\s*\d+(?:-\d+)?|"     # a lot address: "부천시 중동1160-3"
                      r"카카오\s*톡|톡톡|고객\s*센터|상담\s*(?:원|시간|문의)|문의\s*(?:하|주|사항|전화)")
# the shop's terms; not words a product's copy uses ("손목 부담", "오염에 강한" stay)
_POLICY = re.compile(r"배송|택배|출고|발송|교환|반품|환불|결제|주문\s*(?:취소|건|시)|도서\s*산간|영업\s*시간|공휴일|"
                     r"A\s*/\s*S|무상\s*수리|보증\s*기간|처리\s*불가|양해|"
                     # a notice card's own lines (13464713764, 2026-11-08; "공지사함" / "제크자" as OCR reads them)
                     r"공지\s*사[항함]|간주\s*됩니다|동의\s*한|부담\s*하셔야|제\s*[3크키]\s*자|개인\s*정보")
# the store, not the product: branches, opening hours, pick-up, its channels and events (10870655883 AK골프's
# store list and "초특가 상품 알림 서비스", 2026-11-07)
_STORE = re.compile(r"매장|영업점|직영|지점|본점|방문\s*수령|연중\s*무휴|\d{1,2}:\d{2}\s*[~-]|오픈\s*채팅|채널|기획전|"
                    r"알림\s*서비스|이벤트|회원\s*가입|리뷰\s*작성|창립|유통사|"
                    # a store banner baked into snap tiles: hours, its services, its map (7429347947, 10050313095,
                    # 10341805328, 5479607864, 8822855547, 2026-11-08)
                    r"(?:평일|주말|토요일|일요일)\s*:?\s*(?:오전|오후)|(?:오전|오후)\s*\d{1,2}\s*시|중고\s*채|보상\s*판매|"
                    r"위탁|주차|피팅\s*스튜디오|(?:시청|구청|대입구|입구)역|\d+\s*번\s*출구|GS25|세븐\s*일레븐|스타벅스|"
                    r"농협|은행")
# the shop's legal notice, promotions and dealer claims (12975257923 "무단도용금지 ... 저작권법 제 98조", "구매 고객 전원
#클럽 네임택 증정", "XXIO CREW ... 웰컴키트", "공식 온라인 인증 대리점", 2026-11-07)
_LEGAL = re.compile(r"저작권|무단\s*(?:도용|사용|복제|배포)|copyright|all\s*rights\s*reserved|민\s*,?\s*형사|손해\s*배상", re.I)
_PROMO = re.compile(r"증정|사은품|멤버십|웰컴\s*키트|프로모션|구독료|혜택|대리점|판매처|인증\s*점")
_BRANCHES = re.compile(r"[가-힣A-Za-z]{1,10}점(?![가-힣])")          # "일산스타필드점 / 강동점": a store's branch list
_HANGUL = re.compile(r"[가-힣]")
_ANGLE_ROW = re.compile(r"각|°")
_DEGREE_0 = re.compile(r"(?<![\d.])([+\-±]?\d{1,2}\.\d)0(?=\s*(?:\||$))")


def _table_row(text: str) -> bool:
    """3+ cells with a number, or a label and its numbers ("헤드체적(cm) / 460", "로프트각(°) / 21.5 25 28.5")."""
    cells = text.split(" / ")
    numbers = sum(bool(re.search(r"\d", c)) for c in cells)
    # 2 cells: a label and its numbers; the label Korean, or a short code (a flex "R / D1/296", "SR / D2/299", a
    # garbled "4( / 9.5/10.5": 10341805328, 2026-11-08, dropped as fragments before)
    return len(cells) >= 3 and numbers >= 1 or len(cells) == 2 and bool(re.search(r"\d", cells[1])) \
        and not _HANGUL.search(cells[1]) \
        and (bool(_HANGUL.search(cells[0])) or 0 < len(cells[0].strip()) <= 4)   # "여성용은 / 12PCS/..." is a sentence


def _repeat(text: str, at: int, seen: dict[str, int]) -> bool:
    """A sentence seen anywhere before in the product; a short or table row only within REPEAT_WINDOW rows (a slice
    overlap): a table's own heading or row repeated in another table is kept (8822855547, 2026-11-08: 드라이버 / 퍼터
    headings and the iron 모델 #6..S row were dropped, the putter's rows left under the irons)."""
    if text not in seen:
        return False
    return not (len(text.replace(" ", "")) <= 12 or _table_row(text)) or at - seen[text] <= REPEAT_WINDOW


def _why(text: str, conf: float, seen: dict[str, int], at: int = 0) -> str | None:
    if _repeat(text, at, seen):
        return "repeat"
    if conf < MIN_CONF:
        return "low_confidence"
    if not _WORD.search(text) and not _table_row(text):
        return "fragment"
    if not _HANGUL.search(text) and not re.search(r"\d", text) and len(text.split()) <= 3:
        return "photo_label"                           # "POWER TRAJECTORY", "7IRON" is kept (a digit)
    if _PRICE.search(text):
        return "price"
    if _CONTACT.search(text):
        return "contact"
    if _POLICY.search(text):
        return "shop_policy"
    if _STORE.search(text) or len(_BRANCHES.findall(text)) >= 2 or re.search(r"\d+\s*층", text):
        return "store_info"
    if _LEGAL.search(text):
        return "legal"
    if _PROMO.search(text):
        return "promo"
    return None


def _cross_sell_heading(text: str) -> bool:
    if _POLICY.search(text):
        return False
    return bool(_CROSS_SELL_HEAD.search(text)) or bool(_CROSS_SELL.search(text)) and \
        len(text.replace(" ", "")) <= CROSS_SELL_HEADING


def _degrees(row: str) -> str:
    return _DEGREE_0.sub(r"\1°", row) if _ANGLE_ROW.search(row) else row


def blocks(sidecar: dict[str, Any] | None, store_name: str | None = None,
           brand: str | None = None) -> dict[str, Any]:
    """-> {"blocks": [{id, kind, image, text}], "dropped": {rule: rows}} for one product's sidecar."""
    dropped: Counter = Counter()
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    at = 0
    images = [img for img in (sidecar or {}).get("images") or [] if img.get("status") == "read"]
    for n, img in enumerate(images):
        rows = [(ocr.norm(r["text"]), r["conf"]) for s in img.get("slices") or [] for r in s["rows"]]
        kept: list[str] = []
        why_all: list[str | None] = []
        for i, (text, conf) in enumerate(rows):
            if _cross_sell_heading(text):
                dropped["cross_sell"] += len(rows) - i
                break
            at += 1
            why = _why(text, conf, seen, at)
            why_all.append(why)
            seen[text] = at
            if why:
                dropped[why] += 1
            else:
                kept.append(text)
        shop = sum(w in ("shop_policy", "contact", "price", "store_info", "legal", "promo") for w in why_all)
        if why_all and shop / len(why_all) >= NOTICE_SHARE and kept:   # the shop's delivery / returns / store image
            dropped["shop_notice_image"] += len(kept)
            continue
        groups: list[tuple[str, list[str]]] = []
        for text in kept:
            kind = "table" if _table_row(text) else "text"
            if groups and groups[-1][0] == kind:
                groups[-1][1].append(text)
            else:
                groups.append((kind, [text]))
        for kind, lines in groups:
            if kind == "table":
                body = "\n".join(_degrees(x.replace(" / ", " | ")) for x in lines)
            else:
                cleaned = clean("\n".join(lines), store_name=store_name, brand=brand)
                for d in cleaned["dropped"]:
                    dropped[d["rule"]] += d["text"].count("\n") + 1
                body = cleaned["text"] or ""
            if body.strip():
                out.append({"id": f"b{len(out) + 1:02d}", "kind": kind, "image": n + 1, "text": body.strip(),
                            "key": hashlib.sha256(body.strip().encode()).hexdigest()[:16]})
    return {"blocks": out, "dropped": dict(sorted(dropped.items()))}


def mark_shared(by_product: dict[str, tuple[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """{key: (store channel, blocks())} -> the same with `shared`: how many products of that store carry the block
    (its `key`). A store's spec sheet of one model sits in several listings (thegolf9015 상세_스펙.jpg, OCR study
    2026-11-07): it is the product's, so it stays; the translation step translates one `key` once. `shared`
    is not part of the product's sha256 (another product's change never resets a translation)."""
    stores: dict[str, Counter] = defaultdict(Counter)
    for channel, b in by_product.values():
        for k in {x["key"] for x in b["blocks"]}:
            stores[channel][k] += 1
    return {key: {**b, "blocks": [{**x, "shared": stores[channel][x["key"]]} for x in b["blocks"]]}
            for key, (channel, b) in by_product.items()}


def sha(block_list: list[dict[str, Any]]) -> str:
    """The product's text identity: ids, kinds, images and texts (not `shared`, which other products change)."""
    own = [{k: v for k, v in b.items() if k != "shared"} for b in block_list]
    return hashlib.sha256(json.dumps(own, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


# for whoever translates (a person or a model): what this text is and how to treat it (OCR study 2026-11-07, 50 fixture sets)
INSTRUCTIONS = (
    "This is text read by OCR from the product's description images, cleaned of the shop's own blocks. Translate "
    "each block under its [id]; one block may continue the one before it.",
    "OCR faults to expect: spaces lost between words, a few misread letters (닫힌 -> 달힌, 페이스 -> 레이스), a digit "
    "lost in a table. Translate what is meant; do not invent facts, numbers or claims that are not there.",
    "Keep numbers, units, model names, shaft / club codes and table cells exactly as written; a table row is cells "
    "\"a | b | c\": keep the cells and their order; ' / ' joins parts read side by side on one line.",
    "Leave out a line that is plainly not about the product (a store slogan, a region list, a stray label).",
    "Some sellers put screenshots of buyers' reviews in the description images (a 'Real Review' / 후기 / 리뷰 banner, "
    "masked ids like 'ridb*', dates, a buyer's height and weight, often about other products): this is kept as read "
    "for context; never use it as the product's description or its facts.",
    "A block's `key` (in the .ko.json) is the same in every listing that carries the same text: translate it once.",
)
# per Naver leaf category, the terms to translate one way (the shop's own words; add a category's when it starts)
GLOSSARIES: dict[str, dict[str, str]] = {
    "50002788": {"로프트각": "loft", "라이각": "lie angle", "헤드체적": "head volume", "샤프트": "shaft",
                 "강도": "flex", "플렉스": "flex", "토크": "torque", "킥포인트": "kick point", "밸런스": "swing weight",
                 "스윙웨이트": "swing weight", "총중량": "total weight", "클럽 중량": "club weight", "그립": "grip",
                 "드라이버": "driver", "페어웨이우드": "fairway wood", "유틸리티": "hybrid", "아이언": "iron",
                 "웨지": "wedge", "퍼터": "putter", "캐디백": "caddie bag", "스탠드백": "stand bag",
                 "보스턴백": "boston bag", "헤드커버": "head cover", "풀세트": "complete set", "관용성": "forgiveness",
                 "비거리": "distance", "타구감": "feel", "스윗스팟": "sweet spot", "단조": "forged", "주조": "cast",
                 "말렛형": "mallet", "일자형": "blade"},
}

GLOSSARIES["50002787"] = GLOSSARIES["50002788"]               # junior clubs: the same terms (2026-11-11)


def glossary_for(category_id: str | None) -> dict[str, str]:
    return GLOSSARIES.get(str(category_id or ""), {})


def as_text(product_id: str, block_list: list[dict[str, Any]], digest: str,
            glossary: dict[str, str] | None = None) -> str:
    """The Korean blocks as one file a translator reads: a header (format, sha256, instructions, the category's
    glossary), then each block under its id, kind and image number. The header is not part of the sha256: better
    instructions never reset a translation."""
    head = [f"# description images of product {product_id}: Korean text read by OCR, cleaned, to translate",
            f"# format {FORMAT}; sha256 {digest}; {len(block_list)} blocks"]
    head += [f"# {line}" for line in INSTRUCTIONS]
    if glossary:
        head.append("# glossary: " + "; ".join(f"{k} = {v}" for k, v in glossary.items()))
    body = [f"[{b['id']} {b['kind']} image {b['image']}]\n{b['text']}\n" for b in block_list]
    return "\n".join(head + [""] + body)
