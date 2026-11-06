"""The seller's boilerplate in a product description: what is not about the product, out of the text and the images.
Pure, offline, deterministic; no network, no server import (the text and the links come from the API's
details.description).

The parser already leaves out what SmartEditor marks as not the product's own text (link cards, shopping cards, the
store map, in-page jump links, hashtag lines; server/naver_shopping/pdp.py) and puts an empty line between two
SmartEditor components. What is left here is the seller's own text inside the same text and quotation components as
the product text, so it is cut by line and sentence rules, each from a real case (research 2026-11-06 on the 40
collected golf sets of category 50002788, false positives checked on 46 more saved products):

  * sentences: a SmartEditor <p> is a visual line, not a sentence. A line that ends on a connective ("...유선 전화로",
    "...최저가와", "...PGM의", ",") goes on in the next line; the rules match the joined sentence and drop all its lines.
  * policy: a heading about returns / exchange / delivery / customs ("●반품 및 교환 관련 안내", "◆ 해당 상품 관부가세
    및 배송 공지◆") drops its block up to the next empty line, the end of its component. A text with no empty line
    (editor NONE) has no component end: the block stops after POLICY_MAX_LINES lines, note
    description_policy_block_unbounded.
  * phone (a Korean number with separators: "010 4667 2057", "051 324 6360"; a UPC "190228623812" is not one),
    contact (톡톡, talk.naver.com, 유선 전화, 고객센터, 카카오톡 채널 / 상담, "H/P :"), naverpay (네이버페이 자동수거).
  * greeting ("안녕하세요. 제이디스포츠:)입니다." alone on its line), thanks ("감사합니다."), signature ("-제이디스포츠-",
    "듀벨로 올림"; "- 세트 설명 -", "- 추가선택 -" are headings and stay).
  * duties ("관세&부가세 ... 모두 포함"), lead_time ("배송은 9~14일가량"), promo (최저가, 득템, 안심하고 구매),
    store_claim ("저희 비비가월드는", "공식 온라인 대리점", "정식 수입업체"; "정식통관" stays), store_name (the store's
    name in a short sentence; off when the store is the brand's own), monitor ("모니터 사양에 따라 ... 차이").
  * gift: a block that starts with 사은품 ("사은품 최다 증정(소진시 대체품)"), only when Naver's promotion rows are hidden
    (the transform's hidden_promo): we would not hand those gifts out. "☆ 캐디백 증정 ☆" is part of the set and stays.
  * jump: "▲ 이동(상단)", "▲TOP", "맨 위로": a fallback for the parser's jump-link skip.

Images (clean_images): a description image whose file name says it is the seller's banner (배송, 통관, 공지, 이벤트,
하단배너, foot_info, as.jpg, ...) is dropped. Names are decoded first (twice URL-encoded names; proxy-smartstore
links carry the original link base64-encoded after /img/). Snap tiles (p-<id>-s-6-A-<n>.jpg: Naver's pictures of a
whole editor-NONE body) are never dropped: a banner inside them cannot be cut, body_notes flags it instead.

    from description_clean import clean, clean_images, body_notes
    out = clean(details["description"]["text"], store_name=details["store"]["name"], promo_hidden=bool(hidden),
                brand=details["brand"])
    out["text"], out["dropped"], out["notes"]
"""
import base64
import binascii
import re
from collections.abc import Iterable, Iterator
from typing import TypedDict
from urllib.parse import unquote, urlparse

POLICY_MAX_LINES = 12          # a policy block with no component end: the longest seen ran 9 lines (11256507948)
STORE_SENTENCE_MAX = 80        # the store's name in a longer sentence is product prose more often than a claim


class Dropped(TypedDict):
    rule: str
    text: str


class Note(TypedDict):
    code: str
    detail: str


class Cleaned(TypedDict):
    text: str | None
    dropped: list[Dropped]
    notes: list[Note]


class DroppedImage(TypedDict):
    rule: str
    link: str
    name: str


class CleanedImages(TypedDict):
    images: list[str]
    dropped: list[DroppedImage]


# ---- text rules ----------------------------------------------------------------------------------------------------

# a line ending on one of these goes on in the next line (11256507948 "...유선 전화로" / "안내해 드리겠습니다:)")
_CONTINUES_RE = re.compile(r"(?:으?로|와|과|고|며|서|의|은|는|을|를|에|및|,|이며|하며|에게)$")
_POLICY_HEAD_RE = re.compile(
    r"^[●○■□◆◇▶▷※*☞\-\s\[<]*(?:해당\s*상품\s*)?(?:\S*\s*)?(?:반품|교환|환불|취소|배송|통관|관부가세)\S*"
    r"(?:\s+(?:및|/)?\s*\S+){0,3}\s*(?:안내|주의\s*사항|공지|규정|정책|유의\s*사항)\s*[●◆\]>]*$")
_GIFT_HEAD_RE = re.compile(r"^[\[【(☆★◆●\s]*사은품")
# a separator is required: "010 4667 2057", "051 324 6360", "1588-1234"; a UPC / GTIN digit run is not a number
_PHONE_RE = re.compile(r"(?<![\d-])(?:0(?:1[016789]|2|[3-6][1-5]|70)|1[56]\d\d)[-. )]\s?\d{3,4}(?:[-. ]\d{4})?(?![\d-])")
_JUMP_RE = re.compile(r"^\s*[▲△↑]?\s*(?:이동\s*\(?\s*상단\s*\)?|맨\s*위\s*로(?:\s*가기)?|위\s*로\s*가기|top|"
                      r"상단\s*으로(?:\s*이동)?|처음\s*으로)\s*[▲△↑]?\s*$", re.I)
_RULES = [
    ("jump", _JUMP_RE),
    ("phone", _PHONE_RE),
    ("contact", re.compile(r"톡톡|talk\.naver\.com|유선\s*전화|고객\s*센터|카카오톡\s*(?:채널|플러스|상담|문의)|H/?P\s*:")),
    ("naverpay", re.compile(r"네이버\s*페이\s*(?:자동\s*)?(?:수거|반품|회수)")),
    ("monitor", re.compile(r"모니터.{0,30}(?:차이|다를|상이)")),
    ("greeting", re.compile(r"^안녕하세요[.!~,]?\s*\S{0,20}(?:입니다|이에요|예요)[.!~:)^]*$")),
    ("thanks", re.compile(r"^(?:항상\s*)?감사합니다[.!~^]*$")),
    # one dashed token, or a word + 올림 / 드림; "- 추가선택 -" (13498941795) and "- 세트 설명 -" are headings
    ("signature", re.compile(r"^(?:-\s*(?!\S*(?:선택|설명|안내|구성|옵션))[^\s\-]{2,20}\s*-|\S{2,15}\s*(?:올림|드림))$")),
    ("duties", re.compile(r"(?:관부가세|관세|부가세).{0,40}(?:포함|별도|미포함|납부|지불)|"
                          r"(?:포함|별도|미포함|납부|지불).{0,40}(?:관부가세|관세&?부가세)")),
    ("lead_time", re.compile(r"배송(?:은|기간|소요일?)?.{0,15}\d+\s*~\s*\d+\s*(?:일|영업일)")),
    ("promo", re.compile(r"최저가|득템|안심하고\s*구매")),
    ("store_claim", re.compile(r"(?:저희|당사)\s*\S+(?:는|은)|"
                               r"(?:공식|정식)\s*(?:온라인\s*)?(?:판매\s*)?(?:대리점|수입\s*업체|판매권|판매점)")),
]
_NAME_EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")


def sentences(lines: Iterable[str]) -> Iterator[list[str]]:
    """Visual lines -> sentences (lists of lines): a line ending on a connective goes on in the next one."""
    buf: list[str] = []
    for line in lines:
        buf.append(line)
        if not _CONTINUES_RE.search(line.strip()):
            yield buf
            buf = []
    if buf:
        yield buf


def _store_word(store_name: str | None, brand: str | None) -> str | None:
    """The store's name as it is written in a text ("따봉몰." -> "따봉몰"), or None when it says nothing (one letter)
    or is the brand's own store (its name is in every product line)."""
    name = _NAME_EDGE_RE.sub("", store_name or "")
    if len(name) < 2:
        return None
    b = _NAME_EDGE_RE.sub("", brand or "")
    if b and (b in name or name in b):
        return None
    return name


def _rule(sentence: str, store: str | None) -> str | None:
    for name, rx in _RULES:
        if rx.search(sentence):
            return name
    if store and store in sentence and len(sentence) < STORE_SENTENCE_MAX:
        return "store_name"
    return None


def clean(text: str | None, store_name: str | None = None, promo_hidden: bool = False,
          brand: str | None = None) -> Cleaned:
    """A description text (one line per block, an empty line between components) -> the text without the seller's
    boilerplate (None when nothing is left), what was dropped and why, and notes for a human."""
    dropped: list[Dropped] = []
    notes: list[Note] = []
    if not text or not text.strip():
        return {"text": None, "dropped": dropped, "notes": notes}
    store = _store_word(store_name, brand)
    bounded = "\n\n" in text.strip()
    kept_blocks = []
    for block in re.split(r"\n\s*\n", text.strip()):
        out: list[str] = []
        lines = [x for x in block.split("\n") if x.strip()]
        i = 0
        while i < len(lines):
            head = lines[i].strip()
            if _POLICY_HEAD_RE.match(head) or promo_hidden and _GIFT_HEAD_RE.match(head):
                end = len(lines) if bounded else min(len(lines), i + POLICY_MAX_LINES)
                if not bounded and end < len(lines):
                    notes.append({"code": "description_policy_block_unbounded", "detail": head})
                dropped.append({"rule": "policy" if _POLICY_HEAD_RE.match(head) else "gift",
                                "text": "\n".join(lines[i:end])})
                i = end
                continue
            sentence = next(sentences(lines[i:]))
            why = _rule(" ".join(x.strip() for x in sentence), store)
            if why:
                dropped.append({"rule": why, "text": "\n".join(sentence)})
            else:
                out.extend(sentence)
            i += len(sentence)
        if out:
            kept_blocks.append("\n".join(out))
    cleaned = "\n\n".join(kept_blocks) or None
    if cleaned is None:
        notes.append({"code": "description_all_boilerplate", "detail": f"{len(dropped)} dropped"})
    return {"text": cleaned, "dropped": dropped, "notes": notes}


# ---- images --------------------------------------------------------------------------------------------------------

# seller banners by file name (2026-11-06: 리뷰이벤트.png, 따봉몰_하단배너.jpg, 통관번호_안내.jpg, 해구대안내.jpg,
# 해외배송.jpg, foot_info.jpg, as.jpg, 본_제품은_..._익일발송이며_1년_무상_AS_가능합니다..png; in tiled bodies
# holiday_delivery.jpg, kakao_banner_op.jpg, notice01.jpg, CSinfo_Majorgolf.jpg, maincopyright.jpg, map.jpg,
# buysell_warranty_n.jpg). "KakaoTalk_2026..." is a phone photo, "PGM-배너.jpg" the brand's banner: both stay.
_BANNER_NAME_RE = re.compile(
    r"배송|통관|관부가세|교환|반품|환불|공지|휴무|이벤트|하단\s*_?배너|상단\s*_?배너|해구대|구매대행|사은품|익일발송|"
    r"무상_?A/?S|notice|holiday|deliver|copyright|foot_?info|footer|cs_?info|kakao_?(?:banner|plus|notice)|"
    r"plusfriend|(?<![a-z])event|warranty|^(?:as|map|gift)\.(?:jpe?g|png|gif)$|"
    # seen 2026-11-06 on the 40 re-checked: "ktksports 안내문11.jpg" (4 sets), 디씨골프 "회사이미지.jpg" (3),
    # "택배_Nope_AS.jpg", golfbank "brand.jpg" / "customer.jpg", akgolf "bottom_img_all.jpg"
    r"안내문|회사\s*_?이미지|택배|bottom_?img|^(?:brand|customer)\.(?:jpe?g|png|gif)$", re.I)
_SNAP_RE = re.compile(r"/p-\d+-s-\d+-[A-Z]-\d+\.\w+$")
# the HTML comments sellers mark their banners with in tiled bodies (12696567111 "최상단 사은품", "하단 안내 이미지";
# 10870655883 "휴무 공지사항", "카카오톡 플러스친구", "배송정보")
_BANNER_COMMENT_RE = re.compile(r"안내\s*이미지|플러스\s*친구|카카오톡")
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_SRC_RE = re.compile(r"""\b(data-src|src)\s*=\s*["']([^"']+)["']""", re.I)
_ANCHOR_RE = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']#([^"']+)["']""", re.I)
_TARGET_RE = re.compile(r"""\b(?:id|name)\s*=\s*["']([^"']+)["']""", re.I)


def image_name(link: str) -> str:
    """The file name a description image link stands for, decoded."""
    path = urlparse(link).path
    if "proxy-smartstore" in link and "/img/" in path:
        token = path.split("/img/", 1)[1]
        try:
            path = base64.b64decode(token + "=" * (-len(token) % 4), validate=False).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            pass
    return unquote(unquote(path.rstrip("/").rsplit("/", 1)[-1]))


def _banner(link: str) -> str | None:
    if _SNAP_RE.search(urlparse(link).path):
        return None
    name = image_name(link)
    return name if _BANNER_NAME_RE.search(name) else None


def clean_images(urls: Iterable[str] | None) -> CleanedImages:
    """Description image links -> the product's own (order kept) and the seller banners dropped by name."""
    images: list[str] = []
    dropped: list[DroppedImage] = []
    for link in urls or []:
        name = _banner(link)
        if name is None:
            images.append(link)
        else:
            dropped.append({"rule": "boilerplate_name", "link": link, "name": name})
    return {"images": images, "dropped": dropped}


def _img_link(tag: str) -> str:
    links = {k.lower(): v for k, v in _SRC_RE.findall(tag)}
    return links.get("data-src") or links.get("src") or ""


def body_notes(html: str | None, images: Iterable[str] | None = None) -> list[Note]:
    """Notes from the description HTML for what cannot be cut:

      * description_covers_several_products: 2+ in-page sections (<a href="#product1"> with a matching id in the
        body; "#top" is not a section). 12696567111, a 모음전 page of four models, is the one case in 40.
      * description_tiles_include_banners: the images are snap tiles and the body's own <img> names or HTML
        comments name seller banners (they are inside the tiles)."""
    notes: list[Note] = []
    if not html:
        return notes
    targets = set(_TARGET_RE.findall(html))
    sections = {a for a in _ANCHOR_RE.findall(html) if a.lower() != "top" and a in targets}
    if len(sections) >= 2:
        notes.append({"code": "description_covers_several_products", "detail": f"{len(sections)} in-page sections"})
    links = list(images or [])
    if links and all(_SNAP_RE.search(urlparse(x).path) for x in links):
        found = [n for n in (_banner(_img_link(tag)) for tag in _IMG_RE.findall(html)) if n]
        found += [c.strip() for c in _COMMENT_RE.findall(html)
                  if _BANNER_COMMENT_RE.search(c) or _BANNER_NAME_RE.search(c.strip())]
        if found:
            notes.append({"code": "description_tiles_include_banners", "detail": ", ".join(dict.fromkeys(found))})
    return notes
