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
  * price_krw ("정상가 865,000원", "정상가 대비 22% 할인": our prices are USD), cross_sell ("아래 링크에서 구매": the
    card is gone; its lead line goes too when the follow-up says "해당 상품은" and the lead is about another colour /
    model: "⛳화이트 컬러 모델은 기존 출시 상품입니다."), junk (no word of two letters left, 13741767690 "o": text None,
    note description_junk).
  * store_claim also covers the genuine-goods pitch ("정품만 판매", "유통 경로", "정품 여부", "OEM 표기"); the product's
    own "100% 정품", "정품 헤드커버", "정식통관" stay. label: "제품상세" alone on its line (it headed the images).

Images (clean_images): a description image whose file name says it is the seller's banner (배송, 통관, 공지, 이벤트,
하단배너, foot_info, as.jpg, ...) is dropped. Names are decoded first (twice URL-encoded names; proxy-smartstore
links carry the original link base64-encoded after /img/). Snap tiles (p-<id>-s-6-A-<n>.jpg: Naver's pictures of a
whole editor-NONE body) are never dropped: a banner inside them cannot be cut, body_notes flags it instead.
A Latin file name that is Hangul typed on the 2-set keyboard ("gkeksqpsj" = 하단베너) is matched as that Hangul.
With the description HTML, SmartEditor's data-linkdata of each image also drops an image that links to the
seller's channels (TalkTalk, Band, blog, Instagram, YouTube, Kakao channel) or store pages (link_banner) and thin
strips (originalHeight <= 40 or width / height > 25: spacer) and 1x1 tracking pixels (pixel).

    from description_clean import clean, clean_images, body_notes
    pictures = clean_images(details["description"]["images"], details["description"]["html"])
    out = clean(details["description"]["text"], store_name=details["store"]["name"], promo_hidden=bool(hidden),
                brand=details["brand"])
    out["text"], out["dropped"], out["notes"]
"""
import base64
import binascii
import html as html_lib
import json
import re
from collections.abc import Iterable, Iterator
from typing import TypedDict
from urllib.parse import unquote, urlparse

POLICY_MAX_LINES = 12          # a policy block with no component end: the longest seen ran 9 lines (11256507948)
STORE_SENTENCE_MAX = 80        # the store's name in a longer sentence is product prose more often than a claim
SPACER_MAX_HEIGHT = 40         # px (SmartEditor originalHeight); 13446843026 spacers 12 / 30, its buttons 160
SPACER_MIN_RATIO = 25          # width / height; 1080x30 is 36, the narrowest real picture seen 860x100 (8.6)


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

# a line ending on one of these goes on in the next line (11256507948 "...유선 전화로" / "안내해 드리겠습니다:)");
# seen 2026-11-06 (8958060680): "고가의 해외구매대행 상품인 만큼" / "궁금한 점이 있으시면" / "네이버 톡톡으로 문의해
# 주세요." is one sentence. "-면" only after a verb ending (시면, 으면, 하면, 다면): "고강도 타격면" is the club face.
# seen 2026-11-07 (13785630702): "클럽만 따로 판매하거나" / "...판매하는 경우" / "...명확한지" / "확인해 주세요." and
# "골프채 풀세트는 본래" go on; "-지" only after an adnominal ending (인지, 한지, 는지): "웨지", "미끄럼방지", "패키지" end
_CONTINUES_RE = re.compile(r"(?:으?로|와|과|고|며|서|의|은|는|을|를|에|및|,|이며|하며|에게|"
                           r"(?:[시으하다라려]|있|없)면|만큼|는데|지만|니까|거나|경우|[인한는은던]지|본래)$")
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
    # closings seen 2026-11-06 (8958060680): "궁금하신 내용을 편하게 여쭤봐주세요!", "...친절하게 답변드리겠습니다!"
    ("contact", re.compile(r"톡톡|talk\.naver\.com|유선\s*전화|고객\s*센터|카카오톡\s*(?:채널|플러스|상담|문의)|H/?P\s*:|"
                           r"여쭤\s*(?:봐|보)?\s*주|답변\s*(?:해\s*)?드리|문의\s*(?:해\s*)?주(?:세요|시면|십시오)|"
                           r"문의\s*(?:하시기|바랍니다)")),
    # a KRW price promotion (8958060680 "무려 190,300원 할인!", "정상가 865,000원", "정상가 대비 22% 할인 혜택"):
    # the shop's price is in USD and is not Naver's
    ("price_krw", re.compile(r"(?:정상가|할인가|판매가|소비자가|시중가|특가|할인)\D{0,10}\d[\d,]*\s*원|"
                             r"\d[\d,]*\s*원\s*(?:할인|인하|특가)|\d+(?:\.\d+)?\s*%\s*(?:할인|DC|OFF)", re.I)),
    # a line about a product card the parser left out (8958060680 "해당 상품은 아래 링크에서 구매하실 수 있습니다.")
    ("cross_sell", re.compile(r"(?:아래|하단)\s*(?:의\s*)?(?:링크|배너)|링크(?:에서|를\s*통해)\s*구매")),
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
    # the seller's genuine-goods pitch, about the store and other sellers (2026-11-07, 13785630702 / 8958060680:
    # "일본 현지 정식 유통 정품만 판매합니다", "OEM 표기 골프채는 ... 유통 경로가 다를 수 있습니다", "구매 전 정품 여부와 A/S
    # 가능 여부를 반드시 확인해 주세요"). The product's own "100% 정품", "정품 헤드커버 포함", "정품등록", "정식통관",
    # "정식 복각" stay
    ("store_claim", re.compile(r"(?:저희|당사)\s*\S+(?:는|은)|"
                               r"(?:공식|정식)\s*(?:온라인\s*)?(?:판매\s*)?(?:대리점|수입\s*업체|판매권|판매점)|"
                               r"정품만\s*(?:을\s*)?(?:판매|취급)|유통\s*경로|정품\s*여부|OEM\s*표기")),
]
# a section label alone on its line, heading the images that follow (2026-11-07: "제품상세" in 10076378929,
# 12391261816, 12391346892): nothing to read once the images are apart. "[제품 상세 사양]" (a table's heading),
# "Details" (heads text) stay
_LABEL_RE = re.compile(r"^(?:제품|상품)\s*상세(?:\s*(?:정보|설명|이미지|페이지))?$|^상세\s*(?:정보|설명|이미지)$")
# the lead line of a cross-sell pair: another colour / model, which the follow-up "해당 상품은 아래 링크에서 구매하실 수
# 있습니다." points at (2026-11-07: "⛳화이트 컬러 모델은 기존 출시 상품입니다." 13785630702, "⛳블랙 컬러 모델은 2026년 9월에
# 출시되었습니다." 8958060680)
_OTHER_MODEL_RE = re.compile(r"(?:컬러|색상|칼라|다른|기존|신형|구형|이전)\s*(?:\S*\s*)?(?:모델|버전|제품|상품)?\s*(?:은|는)\s")
_REFERS_BACK_RE = re.compile(r"^\W*(?:해당|이|그|위)\s*(?:상품|제품|모델)")
_NAME_EDGE_RE = re.compile(r"^[\W_]+|[\W_]+$")
# a store named for its trade: "일본 구매대행 해피마로" writes itself 해피마로 in the text (8958060680, 2026-11-06)
_STORE_PREFIX_RE = re.compile(r"^(?:(?:일본|미국|중국|독일|영국|유럽|해외|국내|글로벌)\s*)?"
                              r"(?:구매\s*대행|해외\s*직구|직구|병행\s*수입|직수입)\s+")
_WORD_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{2,}")


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
    name = _STORE_PREFIX_RE.sub("", name) or name
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
        last: list[str] = []            # the sentence just kept in this block, [] when the one before was dropped
        while i < len(lines):
            head = lines[i].strip()
            if _LABEL_RE.match(head):
                dropped.append({"rule": "label", "text": lines[i]})
                i, last = i + 1, []
                continue
            if _POLICY_HEAD_RE.match(head) or promo_hidden and _GIFT_HEAD_RE.match(head):
                end = len(lines) if bounded else min(len(lines), i + POLICY_MAX_LINES)
                if not bounded and end < len(lines):
                    notes.append({"code": "description_policy_block_unbounded", "detail": head})
                dropped.append({"rule": "policy" if _POLICY_HEAD_RE.match(head) else "gift",
                                "text": "\n".join(lines[i:end])})
                i, last = end, []
                continue
            sentence = next(sentences(lines[i:]))
            joined = " ".join(x.strip() for x in sentence)
            why = _rule(joined, store)
            if why == "cross_sell" and last and _REFERS_BACK_RE.match(joined) and \
                    _OTHER_MODEL_RE.search(" ".join(x.strip() for x in last)):
                del out[len(out) - len(last):]
                dropped.append({"rule": "cross_sell", "text": "\n".join(last)})
            if why:
                dropped.append({"rule": why, "text": "\n".join(sentence)})
                last = []
            else:
                out.extend(sentence)
                last = sentence
            i += len(sentence)
        if out:
            kept_blocks.append("\n".join(out))
    cleaned = "\n\n".join(kept_blocks) or None
    if cleaned and not _WORD_RE.search(cleaned):
        # 13741767690 (2026-11-06): the whole text is "o": no word of two letters, nothing to show or translate
        dropped.append({"rule": "junk", "text": cleaned})
        notes.append({"code": "description_junk", "detail": cleaned[:80]})
        return {"text": None, "dropped": dropped, "notes": notes}
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
    r"안내문|회사\s*_?이미지|택배|bottom_?img|^(?:brand|customer)\.(?:jpe?g|png|gif)$|"
    # seen 2026-11-06 on the pilot 20: "..._네이버톡톡_복사.jpg", "..._하단_상페_복사.jpg" (상세페이지 footer; "민트_드라이버
    # _상페.jpeg" is the product's own page and stays), "하단고정배너(860)문구O.jpg", 베너 (the common misspelling)
    r"톡톡|하단[\s_]*(?:고정)?[\s_]*(?:[배베]너|상페|안내)|(?:상단|고정)[\s_]*[배베]너|"
    # seen 2026-11-07: "오늘출발.gif" (10076378929, 12391261816, 12391346892: the store's same-day dispatch badge),
    # holiday notices "chuseok.jpg" (5558420432, 6153061020 tiles), 추석 / 설날 / 명절 / 당일발송
    r"오늘[\s_]*출발|당일[\s_]*(?:발송|출고|출발|배송)|추석|설날|명절|한가위|chuseok|seollal", re.I)
_SNAP_RE = re.compile(r"/p-\d+-s-\d+-[A-Z]-\d+\.\w+$")
# the HTML comments sellers mark their banners with in tiled bodies (12696567111 "최상단 사은품", "하단 안내 이미지";
# 10870655883 "휴무 공지사항", "카카오톡 플러스친구", "배송정보")
_BANNER_COMMENT_RE = re.compile(r"안내\s*이미지|플러스\s*친구|카카오톡")
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)
_SRC_RE = re.compile(r"""\b(data-src|src)\s*=\s*["']([^"']+)["']""", re.I)
_ANCHOR_RE = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']#([^"']+)["']""", re.I)
_TARGET_RE = re.compile(r"""\b(?:id|name)\s*=\s*["']([^"']+)["']""", re.I)


# SmartEditor image components: data-linkdata='{"src", "originalWidth", "originalHeight", "linkUse", "link"}'
_LINKDATA_RE = re.compile(r"""\bdata-linkdata\s*=\s*(["'])(.*?)\1""", re.S)
# an image that opens the seller's channels is a banner, not the product (2026-11-06: 13446843026 Band / blog /
# Instagram buttons, 8958060680 the TalkTalk banner)
_LINK_BANNER_HOSTS = ("talk.naver.com", "band.us", "blog.naver.com", "instagram.com", "youtube.com", "youtu.be",
                      "pf.kakao.com", "facebook.com")
_STORE_HOSTS = ("smartstore.naver.com", "brand.naver.com")

# 2-set (dubeolsik) keyboard: the key -> the jamo it types (shifted keys: the double consonants, ㅒ, ㅖ)
_KEY_JAMO = dict(zip("rRseEfaqQtTdwWczxvgkoiOjpuPhynbml", "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎㅏㅐㅑㅒㅓㅔㅕㅖㅗㅛㅜㅠㅡㅣ"))
_INITIALS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_FINALS = ["", *"ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"]
_VOWEL_PAIRS = {"ㅗㅏ": "ㅘ", "ㅗㅐ": "ㅙ", "ㅗㅣ": "ㅚ", "ㅜㅓ": "ㅝ", "ㅜㅔ": "ㅞ", "ㅜㅣ": "ㅟ", "ㅡㅣ": "ㅢ"}
_FINAL_PAIRS = {"ㄱㅅ": "ㄳ", "ㄴㅈ": "ㄵ", "ㄴㅎ": "ㄶ", "ㄹㄱ": "ㄺ", "ㄹㅁ": "ㄻ", "ㄹㅂ": "ㄼ", "ㄹㅅ": "ㄽ", "ㄹㅌ": "ㄾ",
                "ㄹㅍ": "ㄿ", "ㄹㅎ": "ㅀ", "ㅂㅅ": "ㅄ"}
_LATIN_RUN_RE = re.compile(r"[A-Za-z]{3,}")


def qwerty_hangul(word: str) -> str | None:
    """Latin letters typed with the keyboard left on Latin, as the Hangul they stand for on the 2-set layout
    ("gkeksqpsj" -> "하단베너", 6540695739, 2026-11-06), or None when they are not whole Hangul syllables (a real
    Latin word: "brand", "csgolf", "logo": a vowel with no consonant before it, or a consonant with no vowel)."""
    jamo = []
    for ch in word:
        j = _KEY_JAMO.get(ch) or _KEY_JAMO.get(ch.lower())
        if j is None:
            return None
        jamo.append(j)

    def consonant(k: int) -> bool:
        return k < len(jamo) and jamo[k] in _INITIALS

    def vowel(k: int) -> bool:
        return k < len(jamo) and jamo[k] not in _INITIALS

    out, i = [], 0
    while i < len(jamo):
        if not (consonant(i) and vowel(i + 1)):
            return None
        lead, v = jamo[i], jamo[i + 1]
        i += 2
        if vowel(i) and v + jamo[i] in _VOWEL_PAIRS:
            v, i = _VOWEL_PAIRS[v + jamo[i]], i + 1
        tail = ""
        if consonant(i) and not vowel(i + 1):
            pair = jamo[i] + jamo[i + 1] if consonant(i + 1) else ""
            if pair in _FINAL_PAIRS and not vowel(i + 2):
                tail, i = _FINAL_PAIRS[pair], i + 2
            elif jamo[i] in _FINALS:
                tail, i = jamo[i], i + 1
        out.append(chr(0xAC00 + (_INITIALS.index(lead) * 21 + _VOWELS.index(v)) * 28 + _FINALS.index(tail)))
    return "".join(out) if len(out) >= 2 else None


def _proxied(link: str) -> str | None:
    """The original link a proxy-smartstore link carries base64-encoded after /img/, or None."""
    path = urlparse(link).path
    if "proxy-smartstore" not in link or "/img/" not in path:
        return None
    token = path.split("/img/", 1)[1]
    try:
        return base64.b64decode(token + "=" * (-len(token) % 4), validate=False).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def image_name(link: str) -> str:
    """The file name a description image link stands for, decoded."""
    path = _proxied(link) or urlparse(link).path
    return unquote(unquote(path.rstrip("/").rsplit("/", 1)[-1]))


def _image_key(link: str) -> str:
    """One image whatever its scheme, size query or proxy: host + decoded path."""
    link = _proxied(link) or link
    u = urlparse(link if "//" in link else "//" + link)
    return u.netloc.lower() + unquote(unquote(u.path))


def _banner(link: str) -> str | None:
    if _SNAP_RE.search(urlparse(link).path):
        return None
    name = image_name(link)
    if _BANNER_NAME_RE.search(name):
        return name
    typed = [h for h in map(qwerty_hangul, _LATIN_RUN_RE.findall(name.rsplit(".", 1)[0])) if h]
    return name if typed and _BANNER_NAME_RE.search(" ".join(typed)) else None


def _linkdata(html: str | None) -> dict[str, dict]:
    """The description HTML's SmartEditor image components by image (_image_key)."""
    found: dict[str, dict] = {}
    for _, raw in _LINKDATA_RE.findall(html or ""):
        try:
            data = json.loads(html_lib.unescape(raw))
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("src"), str):
            found.setdefault(_image_key(data["src"]), data)
    return found


def _int(value: object) -> int:
    try:
        return int(str(value))
    except ValueError:
        return 0


def _link_banner(data: dict) -> bool:
    if str(data.get("linkUse")).lower() != "true" or not isinstance(data.get("link"), str):
        return False
    u = urlparse(data["link"])
    host = u.netloc.lower().split(":")[0]
    if any(host == h or host.endswith("." + h) for h in _LINK_BANNER_HOSTS):
        return True
    # the store's own pages (home, category, search: 6630856593 ".../viviga_world/search?q=PGM"); a link to a product
    # is another product's card, not a banner
    return any(host == h or host.endswith("." + h) for h in _STORE_HOSTS) and "/products/" not in u.path


def _pixel(data: dict) -> bool:
    """A 1x1 image: a tracking pixel (13728190518 p.tcdn.co.kr/.../6a86d63e42e7754b885ab8c4, originalWidth 1 /
    originalHeight 1, no file extension; seen 2026-11-07). 860x1 is an unmeasured picture (_spacer); 0x0 unknown."""
    return _int(data.get("originalWidth")) == 1 and _int(data.get("originalHeight")) == 1


def _spacer(data: dict) -> bool:
    """A strip between two pictures: originalHeight 1 is an outside image the editor did not measure (8396163567
    727_01.jpg, the product's photo), not a size."""
    w, h = _int(data.get("originalWidth")), _int(data.get("originalHeight"))
    return h > 1 and (h <= SPACER_MAX_HEIGHT or w / h > SPACER_MIN_RATIO)


def clean_images(urls: Iterable[str] | None, html: str | None = None) -> CleanedImages:
    """Description image links -> the product's own (order kept) and the seller banners dropped: by file name, and
    with the description HTML by what SmartEditor says of the image (a link to the seller's channels or store page:
    link_banner; a thin strip: spacer)."""
    images: list[str] = []
    dropped: list[DroppedImage] = []
    components = _linkdata(html)
    for link in urls or []:
        name = _banner(link)
        data = components.get(_image_key(link)) or {}
        rule = "boilerplate_name" if name else "link_banner" if _link_banner(data) else \
            "pixel" if _pixel(data) else "spacer" if _spacer(data) else None
        if rule is None:
            images.append(link)
        else:
            dropped.append({"rule": rule, "link": link, "name": name or image_name(link)})
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
