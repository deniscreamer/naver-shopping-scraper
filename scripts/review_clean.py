"""Review sanitizing before translation and publication (the owner, 2026-11-08): every buyer's review is kept with
its score; its text keeps what the buyer says about the product and loses what describes the Korean purchase, which
is not our shop (the Korean seller and their service, shipping and customs, prices in won, packing, the seller's
free gifts, other platforms) and the decoration (emoji, emoticons, ㅋㅋ). Pure, offline, deterministic, Korean in
and Korean out; the translation stage translates what is left.

The patterns come from 666 real reviews of golf sets (2026-11-08): six agents mined span patterns per topic and
tested them on the corpus, skeptics checked each one, and the general ones were kept (the corpus is
fixtures/reviews/golf_50002788.jsonl; test_review_clean.py checks the result on all of it).

How a span is cut. A topic clause is cut whole, from its keyword to the clause's end: a joint (-고, -서, -는데,
-지만, -며, -구요) or the sentence's end (-요, -다, -죠, -음, punctuation), so that what is left reads as Korean:
"배송도 빠르고 디자인도 맘에 듭니다" -> "디자인도 맘에 듭니다". The clause's body is short and never crosses a product
word (클럽, 헤드, 캐디백, 디자인, 무게 ...): a sentence that mixes the topic and the product keeps the product. Some
topics cut a phrase only ("저렴하게 잘샀어요" -> "잘샀어요", "가격대비 좋아요" -> "좋아요": the opinion stays).

Not cut, on purpose: "not used yet" (아직 사용전이나 좋아 보입니다: cutting it would overstate the review), short
praise (좋아요, 만족합니다: the buyer's rating in words), "잘 쓰고 있어요" (use, in the present).

Grades (every review is kept but a sponsored one):
  full         the text names the product (an aspect: 타구감, 비거리, 헤드, 캐디백, 무게, 디자인, 기스 ...)
  short        an opinion without an aspect (좋아요, 만족합니다, 마음에 들어요, a sentence about the buyer)
  rating_only  nothing left (빠른배송 감사합니다): the score (and photos) without text
  sponsored    체험단 / 협찬 / 제공받아: dropped (not a buyer's word)
and `quality` 0..100 for ordering (aspects, length, photos).

A new category: its aspects (ASPECTS) and product words (PRODUCT_WORDS) by Naver category id; the topics are the
same for any product bought in Korea.

    from review_clean import clean_reviews
    kept, stats = clean_reviews(reviews, category_id)
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

# ---- the product side (what is kept) ---------------------------------------------------------------------------

ASPECTS_ALL = (   # any category
    r"디자인|디지인|이쁘|이뻐|이쁜|예쁘|예뻐|예쁜|예쁩|고급(?:스|진)|색상|색깔|색감|칼라|컬러|(?<![검])[흰은금]색|검은색|검정"
    r"|화이트|블랙|민트|보라색|실물|사진(?:과|보다|하고|이랑)|모양|외관",
    r"퀄리티|품질|마감(?:처리|이)|튼튼|견고(?!한?\s?포장)|재질|짱짱|허접|성능|내구성",
    r"기스|흠집|(?<![가-힣])흠(?:이|은)|불량|(?<![가-힣])하자(?!마자)|(?<!더)부러(?:지|졌|짐)|깨짐|휘(?:어|지|었)|찍힘|스크래치"
    r"|누락|빠진\s?것|뜯어져",
    r"무게|가볍|가벼|무겁|무거|경량|사이즈|크기|길이",
)
ASPECTS: dict[str, tuple[str, ...]] = {
    "50002788": (
        r"타구감|타격감|타감|손맛|임팩트\s?느낌|채감|맞는\s?느낌|칠\s?맛",
        r"타구음|타격음|(?<![가-힣])소리(?:가|도|는|$|\s)",
        r"비거리|거리(?:가|도)?\s?(?:좀더\s?|잘\s?|정말\s?)?(?:나오|나와|늘)|(?:공이|잘)\s?뜨(?:는|고|네|게|요)",
        r"방향성|관용성|탄도|슬라이스|(?<![가-힣])(?:잘\s?|정타\s?)맞(?:고|아|네|는|습|음|추|으|을)|정타|잘\s?쳐(?:지|져)",
        r"골프채|(?<![가-힣])[새첫]?채(?:가|는|도|를|로|랑|$|\s|[.,!~])|여성채|여자채|왼손채|드라이버|드라이브(?!스루)|드라이베"
        r"|아이언|(?<![가-힣])우드|유틸|웨지|퍼터|클럽|풀\s?세트|하프\s?세트",
        r"헤드|샤프트|사프트|(?<![가-힣])강도(?:가|는|도|$|\s|이고)|플렉스|카본|스틸|로프트|그립|낭창|뻣뻣",
        r"캐디\s?[백벡]|개디\s?[백벡]|골프\s?[백벡]|골프\s?가방|하프백|(?<![가-힣])백(?=에|이|은|도|과|까지)|가방|커버|카바",
        r"구성(?!원)|알차|알찬|(?<![세])세트(?!장)",
        r"초보|입문(?!기념)|골린이|백돌이|중급자|여성용|남성용|힘\s?없|힘이\s?없|스윙|그립감|사용감|무게감|손에\s?(?:감|잘|착|딱)",
    ),
}
# 50002787 junior clubs (2026-11-11): the clubs' aspects of the full sets, and what a parent writes of the child
ASPECTS["50002787"] = ASPECTS["50002788"] + (r"아이(?:가|도|는|랑)|아들|딸|애가|애들|초등|어린이|키에\s?맞|잘\s?(?:치|쳐)",)
# product words a cut never crosses (the guard of a clause's body)
PRODUCT_WORDS_ALL = ("디자인", "색상", "무게", "품질", "실물", "예쁘", "이쁘", "예뻐", "이뻐", "제품", "상품",
                     # a defect report is about the product even inside a shipping clause ("박스 열어보니 스크래치")
                     "기스", "스크래치", "흠집", "깨짐", "깨져", "불량", "파손", "하자", "찍힘", "부러", "누락", "빠진")
PRODUCT_WORDS: dict[str, tuple[str, ...]] = {
    "50002788": ("클럽", "채(?![우워])", "드라이버", "아이언", "어이언", "우드", "유틸", "퍼터", "헤드", "샤프트", "그립", "캐디백",
                 "가방", "골프백", "커버", "타구", "타감", "비거리", "구성", "풀세트", "세트", "스틸", "카본"),
}
PRODUCT_WORDS["50002787"] = PRODUCT_WORDS["50002788"]         # junior clubs: the same clubs (2026-11-11)
OPINION_RE = re.compile(
    r"좋아|좋습|좋네|좋음|좋다|좋고|좋은|괜찮|만족|(?:마음|맘)에\s?(?:들|드|쏙)|최고|굿|짱|강추|추천|아쉽|아쉬|별로|실망|불편"
    r"|편해|편하|딱\s?(?:이|입|맞)|훌륭|멋지|멋져|대박|감동|기대")

# ---- the purchase side (what is cut) ---------------------------------------------------------------------------

_END_LOOK = r"(?=[\s.,!?~^;:)ㅎㅋㅠㅜ♡♥\U0001F000-\U0001FAFF☀-➿]|$)"
END = (r"(?:(?<=[았었])어요(?=[가-힣])|(?:고|구|서|며|는데|지만|구요|고요|요|(?<!보)다|죠|음|름|함|됨|임|듯|네|굳|굿|(?<=되)어|(?<=와)서)" + _END_LOOK + r")"
       r"[ \t.,!?~^;:)ㅎㅋ]*")
SENT_START = r"(?:(?<=^)|(?<=^ )|(?<=[.!?~^;\n])|(?<=[.!?~^;\n] )|(?<=요 )|(?<=다 )|(?<=네 )|(?<=ㅎ )|(?<=ㅋ ))"
LEAD = (r"(?:(?:정말|너무|엄청|완전|생각보다|생\S?각보다|오늘|아침에|빠르게|빨리|안전하게|안전히|신속하게|무사히|일단|그리고|또한?"
        r"|무엇보다|단|다만|암튼|무튼|그래도)\s*){0,2}")


# a line (or a sentence ending a line) that is only what the purchase cost besides the price: "세금 배송10",
# "관세랑 배송비 합쳐서 3만", "배송비 별도 5천원", "관세 10만 배송비 2만" (2026-11-08: a set's review on the site still
# said "Tax, shipping 10.")
_COST_WORD = r"(?:세관신고|세금|관세|관부가세|부가세|통관비?|배송비?|택배비?|운송비|운임)(?:는|은|도|이랑|랑|과|와|까지)?"
_COST_JOIN = r"(?:합쳐서|합해서|포함해서|포함|별도|각각|따로|총)"
_COST_AMOUNT = r"\d[\d,.]*[ \t]*(?:만[ \t]*원|만|원|천[ \t]*원)?[ \t]*(?:정도|가량|쯤)?"
_COST_PART = r"(?:" + _COST_WORD + r"[ \t]*[,+/·]?[ \t]*(?:" + _COST_JOIN + r"[ \t]*)?)+" + r"(?:" + _COST_AMOUNT + r")?"   # the amount may be cut already
_COST_LINE = (r"(?:(?<=^)|(?<=\n)|(?<=[.!?] ))[ \t]*" + _COST_PART + r"(?:[ \t]*[,+/·]?[ \t]*" + _COST_PART
              + r")*[ \t.!]*(?=\n|$)")


def _body(guard: str, n: int) -> str:
    return rf"(?:(?!{guard})[^.!?\n]){{0,{n}}}?"


def _spans(guard: str) -> list[tuple[str, str, str]]:
    """(topic, name, regex) in the order they are applied: specific first, the general clause after."""
    b30, b20, b15 = _body(guard, 30), _body(guard, 20), _body(guard, 15)
    return [
        # shipping and delivery
        ("shipping", "order_to_receive", r"(?:\d+월\s*)?(?:\d+일날?\s*)?(?:주문|결제)(?:\s*후|\s*하고|하자마자|해서)?\s*"
         r"[^.!?\n]{0,25}?(?:수령|받기|받았|받을|도착|발송)" + b15 + END),
        ("shipping", "overseas", r"(?:배송(?:은|도)\s*)?해외(?:\s*배송|\s*직구|에서\s*받아서)(?:이라|이지만|인데|치고는?|라서)?\s*"
         + b20 + END),
        ("shipping", "fast_np", LEAD + r"(?:빠르고\s*)?(?:빠른|신속한|정확한|안전한)\s*(?:배송|도착)(?:과|와|및|,|도|에도?)?[\s~]*"
         r"(?:(?:감사|고맙)[가-힣]*" + END + r"|(?=[가-힣]))"),
        ("shipping", "list_item", r"(?:(?<=\s)|(?<=^))(?:배송|포장|가성비|가격)(?:\s*및|\s*,|\s+)\s*(?=(?:디자인|색상|색감|구성|"
         r"무게감|성능|품질|퀄리티|타구감|모양|제품|상품|모두|다\s|배송|포장|가성비|가격))"),
        ("shipping", "split", r"(?:배송(?:은|이)?\s*[^.!?\n]{0,25}?따로\s*(?:옵니다|와요|왔어요|오네요|왔습니다|보내주셨어요)"
         r"|\d+\s*(?:개|박스)로\s*나(?:눠|뉘어)\s*(?:배송|와|왔|오)[가-힣]*)" + r"[\s.,!?~^;ㅎㅋ]*"),
        ("shipping", "fast_alone", r"(?:빠른|신속한)\s*배송[\s.!~]*$"),
        ("shipping", "clause", LEAD + r"(?:(?:해외|국내|당일|빠른|로켓)\s*)?(?:배송|배달|택배)(?:기간|상태|정보)?"
         r"(?:이|은|는|도|이랑|과|와|:|가|치고는?|받는데까지|받는데)?\s*" + b30 + END
         + r"(?:(?:매우|좀|많이|너무)\s*(?:황당|당황|답답)[가-힣]*" + END + r")?"),
        ("shipping", "received_day", r"(?:일주일|이틀|사흘|\d+\s*일)\s*(?:날\s*)?(?:안에\s*|만에\s*)?(?:에\s*)?(?:받았|도착|왔|받아)[가-힣]*,?\s*"
         r"(?:[^.!?\n]{0,20}?(?:빠른|늦은|빨리\s*온|늦게\s*온)\s*편[가-힣]*" + END + r")?"),
        ("shipping", "arrival", r"(?:(?:진짜|정말|너무|엄청|완전|생각보다|생\S?각보다|오늘|아침에)\s*){0,2}(?:택배가\s*)?(?:빨리|빠르게|다음날|담날|뒷날|이틀\s*만에|하루\s*만에|하루만에|금방|\d+시\s*전에)\s*"
         r"(?:바로\s*)?(?:도착|받았|받을|왔|와서|오고|받아|오네|오|와)[가-힣]{0,6}" + END),
        ("shipping", "received", SENT_START + r"(?:(?:상품|제품|물건|골프클럽)\s*(?:을|은|도)?\s*)?(?:(?:이상\s*없이|손상\s*없이|안전하게|"
         r"무사히|깔끔하게)\s*)?(?:잘\s*)?(?:받았|도착했|왔)(?:습니다|어요|구요|고요|네요|어여|어용)?(?:[\s.,!?~^;ㅎㅋ]+|$)"),
        # customs and money
        # a line that is only what the purchase cost besides the price: "세금 배송10", "관세, 배송비 3만" (2026-11-08,
        # a set's review on the site still said "Tax, shipping 10.")
        ("price", "customs", r"(?:(?:단|추가로?|해외)\s*,?\s*)?(?:위\s*)?(?:가격에서\s*|가격에\s*)?(?:관부가세|관부과세|관세|부가세|부과세|세관|통관|세금)[^.!?\n]{0,40}?"
         + END),
        ("price", "amount_clause", r"(?:(?:결제\s*후에?|추가로)\s*)?(?:약\s*|대략\s*|총\s*)?\d[\d,.]*\s*(?:만\s*원|만|원|천\s*원)"
         r"(?:\s*(?:정도|가량|쯤|대|후반대|초반대|이상|더))*(?:은|이|을)?\s*(?:[가-힣]+\s+)?(?:나왔|나오|들었|든|냈|내라|내야|지불|"
         r"더\s*주|더\s*줘|들어)[^.!?\n]{0,20}?" + END),
        ("price", "amount", r"(?:약\s*|대략\s*|총\s*)?\d[\d,.]*\s*(?:만\s*원|원|천\s*원)(?:\s*(?:정도|가량|쯤|대|이상))*(?:에|이|은|을|으로)?[ \t]*"),
        ("price", "cost_line", _COST_LINE),            # after the amounts: "세관신고 18만원 세금 배송10" is a cost line
        # the Korean shop's discount or points as the reason to buy: "가격할인에 포인트 적립도 커서" (2026-11-09)
        ("price", "discount_points", r"(?:가격\s*)?(?:할인|세일|포인트(?:\s*적립)?|적립금?|쿠폰)(?:에|도|이|가|과|와|하고|이랑|까지)?"
         r"(?:\s*(?:포인트(?:\s*적립)?|적립금?|쿠폰)(?:도|이|가|까지)?)?\s*(?:커서|많아서|쏠쏠해서|좋아서|크고|많고|받아서|받고(?![\s/]*싶))\s*"),
        ("price", "cheaper_elsewhere", r"(?:(?:가격이|가격은|가격도)\s*)?(?:알리|테무|쿠팡|매장|다른\s*곳|다른곳|타\s*사이트|"
         r"(?<!무엇)[가-힣]+보다)[^.!?\n]{0,20}?(?:싸|쌉|저렴)(?!\s?보|해\s?보|하게\s?보)[가-힣]*"
         + END),
        ("price", "lowest", r"(?:여기가\s*)?(?:최저가|가장\s*저렴|젤\s*저렴|제일\s*저렴|젤\s*싸|제일\s*싸)[가-힣]*\s*(?:" + END + r")?"
         r"(?:여기가\s*[,.]?\s*)?"),
        ("price", "adverbial", r"(?:(?:좋은|착한|합리적인|저렴한|적절한|적당한|싼)\s*가격(?:에|으로)|(?:금액대|가격대)에서|가격에\s*비해|"
         r"가격적으로도?|(?:가격도\s*)?(?:저렴하게|저렴히|싸게)|싼\s*값에|싼값에)\s*"),
        ("price", "np", r"(?:저렴한|좋은|착한|합리적인|적당한)\s*가격(?![에으이은도대])(?:\s*(?:과|및|,))?\s*"),
        ("price", "value_adnominal", r"(?:가성비|가격)(?:가|이|도)?\s*(?=(?:좋은|착한|최고인|짱인|갑인)\s*[가-힣])"),
        ("price", "cheap_bare", SENT_START + r"(?:일단\s*|우선\s*)?(?:저렴|싸)(?:합니다|해요|하네요|고|서|요)[\s.,!?~^;ㅎㅋ]*"),
        ("price", "value_only", r"(?:가성비|가격)만\s*보고\s*"),
        ("price", "ratio", r"(?:가격|금액|비용|가성비)\s*대비(?:해서는|해서|로는)?\s*"),
        ("price", "list_item", r"(?:가성비|가격)(?:\s*및|\s*,|\s+)\s*(?=(?:디자인|색상|색감|구성|무게감|성능|품질|퀄리티|타구감|모양|제품|"
         r"상품|모두|다\s))"),
        ("price", "this_price", r"이\s*가격(?:에|이면|이라면|으로)(?![^.!?\n]{0,15}(?:없|않|못|어렵))\s*"),
        ("price", "value", r"(?<![과와] )(?:(?:착한|저렴한|좋은|합리적인)\s*)?(?:가성비|가격|금액|가격대|값)(?:는|도|가|이|은|로는|만)?\s*"
         r"(?:(?:진짜|정말|너무|넘|완전|매우|아주|참|엄청|꽤|제일|젤|가장|대박|좀|조금|약간|딱)\s*)*"
         r"(?:말할\s*(?:것|거)\s*없|좋|조아|최고|최거|갑|굿|짱|끝내|끝판|끝장|괜찮|갠찮|괞찬|대박|만족|착하|착한|착해|합리적|적당|훌륭|저렴|싸|쌉|싼|깡패|미쳤|멋)"
         r"[가-힣]*"
         r"(?:\s*(?:거|것)?\s*같[가-힣]*|\s*듯[가-힣]*)?[\s.,!?~^;ㅎㅋ👍]*"),
        # the seller, the shop, its service
        ("seller", "sentence", SENT_START + r"(?:판매자|사장|셀러|담당자|상담원|구매처)(?:님|분)?(?:께서|이|가|도|은|는|의)?\s*"
         + _body(guard, 70) + r"(?:[.!?]+|\n|$)"),
        # a line about dealing with the seller ("판매자님과 십년넘게 거래하신다는분"), and the surprise that it came fast
        # ("주문 후 ... 이렇게 빨리 도착할꺼라곤 / 기대도 안했는데 깜짝 놀랐습니다") (2026-11-09, a Daiwa set's review)
        ("seller", "dealings", r"(?:(?<=^)|(?<=\n))[^\n]*(?:판매자|사장|셀러)(?:님|분)?(?:과|와|이랑|하고)\s*[^\n]{0,20}?(?:거래|단골)[^\n]*"),
        ("shipping", "surprise", r"(?:(?<=^)|(?<=\n))[^\n]{0,40}?(?:빨리|일찍|금방)\s*(?:도착|올|받을)[가-힣]*\s*(?:꺼|거|것)라(?:곤|고는?|고)?"
         r"[^\n]*(?:\n[^\n]{0,40}?(?:놀랐|몰랐)[^\n]*)?"),
        ("seller", "subject", r"(?:판매자|사장|셀러|담당자)(?:님|분)?(?:께서|이|가|도|은|는)?\s*" + b30 + END),
        ("seller", "thanks_service", r"(?:(?<=\s)|(?<=^))(?:및|,)?\s*(?:(?:친절한|빠른|신속한|자세한)\s*)?(?:답변|안내|응대|대응|설명|연락|"
         r"전화\s*연락|전화|상담)(?:과|와|및|,|에|에도)?\s*(?:(?:답변|안내|응대|대응|설명|연락)(?:과|와|및|,|에|에도)?\s*)?"
         r"(?:(?:너무|정말|진심으로)\s*)?(?:감사|고맙)[가-힣!]*" + r"(?:" + END + r")?"),
        ("seller", "kind_predicate", r"(?:(?:너무|정말|매우|아주|엄청)\s*)*친[절철]\s*(?:하세요|하시고|하셨어요|하고|하게)?\s*(?:하세요|하시고|하십니다|합니다|해요|하시네요|하셔서"
         r"|하시구요|하시구|하셨어요|하셨습니다)[\s.,!?~^;ㅎㅋ👍]*"),
        ("seller", "kind", r"(?:(?:너무|정말|매우|아주|엄청|자세히)\s*)*친[절철](?:한\s*(?:응대|상담|답변|안내|설명|대응)|히\s*\S*|"
         r"하게\s*(?:\S+\s*)?(?:응대|상담|답변|안내|설명|알려|전화|대응)\S*)" + b20 + END),
        ("seller", "kind_bare", r"(?<![가-힣])친절(?:하고|함|합니다|해요)?(?=[\s.!~]*(?:\n|$))[\s.!~]*"),
        ("seller", "service", r"(?:톡톡|상담|응대|대응|응답|일\s*처리|답변|문의|전화|연락|고객관리|안내|설명(?=도|을|해))(?:도|이|은|을|에|해\s*주|주시)?\s*"
         + b30 + END),
        ("seller", "after_sales", r"(?<![A-Za-z])(?:A/?S|as)(?![A-Za-z])(?:도|가|는|를)?\s*" + b20 + END),
        ("seller", "wishes", r"(?:많이\s*(?:파시고|판매하시고|파세요|판매하세요)\s*)?(?:(?:많이\s*)?(?:번창|흥)(?:하세요|하시길|하시기를|"
         r"하셨으면|하십시오)|대박\s*나(?:세요|시길|시기를|셨으면)|부자\s*되(?:세요|시길)|많이\s*(?:파세요|판매하세요)|수고\s*하세요|"
         r"(?:사업|장사)\s*잘\s*되(?:세요|시길))[가-힣]*(?:\s*(?:좋겠|바랍|기원)[가-힣]*)?[ \t.,!?~^;ㅎㅋ👍]*"),
        ("seller", "repurchase", r"(?:다음에도|다음에|담에도?|또|자주|앞으로도)\s*(?:여기서\s*)?(?:이용|구매|주문|구입|찾)[가-힣]*" + END),
        ("seller", "buy_here", r"(?:여기서|이곳에서|여기에서|이\s*곳에서)\s*" + b20 + r"(?:구매|구입|사|살)[가-힣]*" + END),
        ("seller", "vocative", SENT_START + r"(?:사장|판매자)(?:님|분)\s*[~.!,]*\s+(?=\S)"),
        ("seller", "orphan", r"(?m)^[ \t]*(?:친절한\s*)?(?:안내|답변|응대|대응|상담|설명|문의)(?:까지|도|와|과|및)?[ \t]*$"),
        ("seller", "regular_shop", r"[가-힣]*단골(?:가게|매장|집)[가-힣?]*\s*"),
        ("seller", "store_header", r"(?m)^\s*\[(?:스마트스토어|네이버)\][^\n]*\n?"),
        # packing, the seller's gifts, platforms, the review itself
        ("packing", "list", r"(?:(?:꼼꼼한|견고한|깔끔한|안전한)\s*)?포장(?:과|및|,)\s*"),
        ("packing", "clause", LEAD + r"(?:(?:꼼꼼한|견고한|깔끔한|안전한)\s*)?포장(?:상태)?(?:도|이|은)?\s*" + b20 + END),
        ("packing", "adverb", r"(?:꼼꼼하게|꼼꼼히|깔끔하게|안전하게|하나하나)\s*포장[가-힣]*\s*" + b15 + END),
        # the 100-product pilot, 2026-11-09 (112 rows in 36 products still told of the purchase): coming back to the
        # shop, the seller's service in a product story, what the seller sent, order dates, weather, packing
        ("seller", "comeback_sentence", r"(?:(?<=^)|(?<=\n)|(?<=[.!?] ))[^.!?\n]{0,45}?(?:또|다시)\s*(?:들릴|들르|찾아올|구매하러|"
         r"상담드리)[가-힣]*[.!?\s]*"),
        ("seller", "from_here", r"(?:(?<=^)|(?<=\n)|(?<=[.!?] ))[^.!?\n]{0,30}?(?:여기서|이\s*샾|이\s*샵)[^.!?\n]{0,25}?"
         r"(?:바꿔야|구매|주문|알아본)[가-힣]*[^.!?\n]{0,8}?(?:[.!?]+|(?=\n)|$)"),
        ("seller", "comeback", r"(?:다음에(?:도)?|담에|나중에|앞으로(?:도)?)?\s*(?:[^.!?\n]{0,25}?(?:필요한\s*(?:제품|것|거|용품)이?\s*"
         r"(?:더\s*)?생기면|바꿀\s*때|교체(?:할)?\s*때(?:\s*되면)?|상급자가?\s*되어서|구매때))\s*(?:또|다시)\s*(?:들릴|들르|찾아올|"
         r"찾아뵙|구매하러|상담드리|이용할|구매할|주문할)?[가-힣]*" + END),
        ("seller", "did", r"(?:정말\s*)?(?:친절하게|세심하게)\s*(?:대처|배려|상담|설명|응대|안내)[가-힣\s]{0,8}?"
         r"(?:주셨|주시고|주셔서|주시네요|주십니다)[가-힣]*" + END),
        ("seller", "answered", r"(?:늘\s*|항상\s*)?(?:빠르고\s*)?친절하게\s*(?:답변|응대|안내)해\s*주(?:시는|신|셔서)[가-힣]*\s*"),
        ("seller", "inquiry", r"(?:비대면\s*거래인데도\s*불구하고\s*)?문의\s*사항\s*(?:친절하게\s*응대해\s*주신\s*)?(?=\S)"),
        ("seller", "visit_again", r"(?:(?<=^)|(?<=\n)|(?<=[.!?] ))[^.!?\n]{0,40}?(?:살\s*때도|살때도|때도)\s*(?:들릴|들를|올)[가-힣]*[.!?\s]*"),
        ("gift", "service_given", r"(?:주문\s*후\s*)?(?:미안하시다며\s*)?[가-힣]*(?:를|을)\s*서비스로\s*주셨[가-힣]*[.!\s]*"),
        ("gift", "thanks", r"사은품도\s*[^.!?\n]{0,25}?챙겨\s*주셔서\s*(?:감사합니다|감사해요)?[.!\s]*"),
        ("shipping", "arrived_well", r"(?:생각보다\s*)?빠르게\s*(?:안전하게\s*)?잘\s*도착했[가-힣]*\s*"),
        ("seller", "advice", r"(?:직접\s*)?(?:상세히|자세히)\s*[^.!?\n]{0,20}?(?:알려|설명해)\s*주셔서\s*"),
        ("seller", "polite", r"(?:복\s*많이\s*받으세요|더\s*많은\s*응원\s*보내드릴[께게]요|응원\s*보내드릴[께게]요)[.!\s]*"),
        ("seller", "always", r"항상\s*주문하는\s*제품입니다\s*"),
        ("gift", "sent", r"(?:정성껏\s*)?(?:별도로\s*)?(?:보내\s*주신|선물로\s*주신|사은품으로\s*주는|서비스로\s*주는)\s*[가-힣]*"
         r"(?:도|은|이)?\s*[^.!?\n]{0,20}?" + END),
        ("gift", "sense", r"센스있게[^.!?\n]{0,30}?서비스[^.!?\n]{0,5}?" + END + "?"),
        ("gift", "covers_given", r"(?:골프채마다\s*)?헤드커버도\s*주시고\s*[^.!?\n]{0,20}?챙겨\s*주셔서\s*"),
        ("shipping", "dates", r"(?:\d+\s*월\s*)?\d+\s*일(?:날)?\s*(?:주문|결제)(?:했고|하고|후)?\s*(?:(?:\d+\s*월\s*)?\d+\s*일"
         r"(?:에|날)?\s*(?:바로\s*냈습니다|관세)?\s*)*"),
        ("shipping", "took", r"(?:주문\s*(?:후|하고)?\s*)?(?:수령|도착|받기)까지[^.!?]{0,30}?(?:걸렸|걸린|걸리)[가-힣]*" + END),
        ("shipping", "weather", r"(?:폭설\s*속에|폭설속에|태풍을\s*뚫고|추석임에도|연휴\s*전에|연휴전에|연휴전이라고|연휴가\s*포함됐음에도\s*"
         r"불구하고|퀵으로\s*보내주셔서)\s*"),
        ("shipping", "weeks", r"딱?\s*\d+\s*주\s*정도에\s*오는\s*것\s*같[가-힣]*" + END),
        ("packing", "careful", r"(?:새제품\s*)?포장\s*(?:진짜|정말|너무|엄청)?\s*꼼꼼하게\s*[가-힣]*" + END + "?"),
        ("packing", "thanks", r"(?:판매자님?\s*)?포장(?:을)?\s*꼼꼼하게\s*해\s*주신\s*덕분에\s*"),
        ("packing", "wrap", r"(?:골프채\s*)?(?:뽁뽁이|뽁뾱이|에어캡|완충재)[에로]?\s*(?:정말\s*)?(?:꼼꼼하게)?\s*"),
        ("packing", "came_careful", r"(?:엄청|정말|너무)\s*꼼꼼하게\s*왔고\s*"),
        ("packing", "tied", r"(?:골프채\s*)?움직이지\s*않게\s*타이로\s*묶었어요[.!\s]*"),
        ("packing", "box_torn", r"(?:그런지\s*)?(?:무게\s*때문에\s*)?박스가[^.!?\n]{0,25}?찢어져서\s*왔지만\s*"),
        ("gift", "freebie", r"(?:귀여운\s*)?(?:추가\s*)?(?:사은품|증정품|서비스템|서비스\s*상품)(?:도|은|을|이|으로|까지)?\s*" + b30 + END),
        ("gift", "given", r"(?:선물|서비스)(?:도|을|까지)\s*(?:많이|엄청|이것저것|푸짐하게|빵빵하게|잘)?\s*(?:주|챙겨)[가-힣]*" + END),
        ("platform", "review_promise", r"(?:(?:일단\s*)?(?:사용해|사용|써|쳐)\s*보고\s*)?(?:또|다시)?\s*(?:한\s*달\s*|일주일\s*)?"
         r"(?:리뷰|후기|품평)\s*(?:또|다시)?\s*(?:남길|올릴|작성할|남기|올리(?!니)|쓸|올리게)[가-힣]*"
         r"(?:\s*(?:수\s*)?(?:있음|있으면)\s*남길[가-힣]*)?" + r"(?:" + END + r")?"),
        ("platform", "review_read", r"(?:다른\s*)?(?:후기|리뷰)(?:가|를|들|도)?\s*(?:많이\s*)?(?:없어|보고|참고|읽고)[가-힣]*\s*" + b15 + END),
        ("platform", "other_site", r"(?:네이버|스마트스토어|쿠팡|알리|테무|타\s*사이트|다른\s*사이트|사이트)(?:에서|가|나|를|도)?\s*" + b20 + END),
        # filler
        ("filler", "thanks", SENT_START + r"(?:(?:정말|너무|항상|진심으로|대단히)\s*)?(?:감사(?:합니다|해요|드립니다|드려요|합니당|해여)?|"
         r"고맙습니다|고마워요|땡큐)[\s.,!?~^;ㅎㅋ👍]*"),
        ("filler", "will_use", SENT_START + r"(?:(?:앞으로|오래오래|오래)\s*)?잘\s*(?:쓰겠|쓸게|쓸께|쓸꼐|사용하겠|사용할게|사용할께|"
         r"사용\s*하겠|사용해\s*볼께|사용해\s*볼게|이용하겠)[가-힣]*[\s.,!?~^;ㅎㅋ]*"),
    ]


# text addressed to a model, not a review ("ignore all previous instructions ..."): the sentence goes
_INJECTION_RE = re.compile(r"[^.!?\n]*\b(?:ignore|disregard|forget)\b[^.!?\n]{0,40}\b(?:instructions?|prompts?|rules)\b[^.!?\n]*"
                           r"[.!?]?|[^.!?\n]*\b(?:system prompt|you are (?:an? )?(?:AI|assistant|model))\b[^.!?\n]*[.!?]?", re.I)
SPONSORED_RE = re.compile(r"체험단|협찬|원고료|무상\s?으로\s?제공|서포터즈|(?:제품|상품|업체)[을를로]?\s?(?:무상\s?)?제공\s?받아\s?"
                          r"(?:작성|쓴|솔직)|제공\s?받아\s?(?:작성|쓴|솔직)")

# ---- decoration ------------------------------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U00002190-\U000021FF\U00002300-\U000023FF"
    "\U00003200-\U000032FF\U0000FE00-\U0000FE0F\U0000200B-\U0000200F\U0000E000-\U0000F8FF"
    "♡♥❤❣★☆✩✪✰♪♫♬♩✔✓✨❀✿❁♣♠♦◆◇■□▲△▼▽●○◎•※〓]+")
_KAOMOJI_RE = re.compile(
    r"\^[0oO.ㅡ_\-]\^|\^[ \t^_\-ㅡ~;*ㅅㅇ]*\^?[;*]*|[-=][_.][-=];*|[Tㅠㅜ][_.\-][Tㅠㅜ]"   # "^0^" whole; never a
    r"|(?<![A-Za-z0-9])[:;]-?[)(DPp](?![A-Za-z0-9])|;{2,}|>_<")                    # digit after ^^ (0.5)
_JAMO_RE = re.compile(r"[ㄱ-ㆎᄀ-ᇿ]+")
_LINK_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\w+|\b0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}\b")
_LETTER_RUN_RE = re.compile(r"\b[a-z]*([a-z])\1{2,}[a-z]*\b")      # vvvwww; capitals (XXX, TT) are codes
_MASK_RE = re.compile(r"[*#=_+]{2,}")
_TILDE_RE = re.compile(r"(?<!\d)[~〜∼～]+|[~〜∼～]+(?!\s?\d)")     # 22~25 (a range) stays
_WORD_REPEAT_RE = re.compile(r"([가-힣]{1,4}?)\1{2,}")
_ENDED_RE = re.compile(r"(?:요|니다|[었았했였겠]다|한다|이다|죠|네|음|함|임|듯|굿|굳)$")


def strip_decoration(text: str) -> str:
    """Emoji, emoticons, jamo (ㅋㅋ ㅎㅎ ㅠㅠ, a stray ㅆ inside a word), tildes, links, masks, letter runs and word
    repeats out; a decoration that ended a sentence (after 요 / 다 ...) becomes a full stop."""
    text = unicodedata.normalize("NFC", text or "")
    text = _LINK_RE.sub(" ", text)
    text = re.sub(r"(?<=[가-힣])" + _JAMO_RE.pattern + r"(?=[가-힣])", "", text)
    for pattern in (_EMOJI_RE, _KAOMOJI_RE, _TILDE_RE, _JAMO_RE):
        text = pattern.sub("\x00", text)
    out: list[str] = []
    for i, part in enumerate(re.split(r"\x00+", text)):
        if i and out:
            prev = out[-1].rstrip(" ")
            out[-1] = prev + ("." if _ENDED_RE.search(prev) and part.strip() else "") + ("" if part[:1] == "\n" else " ")
        out.append(part)
    text = "".join(out)
    text = re.sub(r"\*\^+\*|(?<!\S)\*(?!\S)", " ", text)       # *^^* and a lone star (2026-11-09: "/ *" on the site)
    text = _MASK_RE.sub(" ", text)
    text = _LETTER_RUN_RE.sub(" ", text)
    return _WORD_REPEAT_RE.sub(r"\1\1", text)


# a line left with one dangling word of a cut sentence: an adverb or a modifier with nothing to modify ("꼼꼼하게",
# "챙겨주신"); a word that says something on its own ("좋아요", "만족") is not one
_FRAGMENT_RE = re.compile(r"(?:꼼꼼|친절|신속|빠르|안전|정성스럽|세심)(?:하게|히|하신|게)|(?:챙겨|보내|포장해|해|신경써)\s*주신|친절하신")


# a line that starts with the particle of a noun that was cut ("으로 왔어요"); only these, so "이 클럽세트" and "와" stay
_ORPHAN_RE = re.compile(r"^(?:으로|은|는|을|를)\s+")


def tidy(text: str) -> str:
    """Punctuation runs, spaces, a bracket whose other half was cut, empty lines, a stray joint at an edge."""
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r"\.{3,}|…+", "...", text)
    text = re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)
    text = re.sub(r"([,.!?])(?:[ \t]*[,.])+", r"\1", text)
    text = re.sub(r"[ \t]+([.,!?])", r"\1", text)
    text = re.sub(r"\.(?=[!?])", "", text)
    text = re.sub(r"(?<=[.!?])(?=[가-힣A-Za-z])", " ", text)
    if text.count("(") != text.count(")"):
        text = text.replace("(", " ").replace(")", " ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line.strip(" \t,;:/").lstrip(".!? ") for line in text.split("\n")]
    text = "\n".join("" if _FRAGMENT_RE.fullmatch(line) else line for line in lines)
    text = re.sub(r"\n(?:[ \t]*\n)+", "\n", text)            # a line whose words were all cut
    return text.strip(" \n,;:/")


@lru_cache(maxsize=16)
def _compiled(category_id: str | None) -> tuple[list[tuple[str, str, re.Pattern[str]]], re.Pattern[str]]:
    words = PRODUCT_WORDS_ALL + PRODUCT_WORDS.get(category_id or "", ())
    guard = "(?:" + "|".join(words) + ")"
    spans = [(topic, name, re.compile(rx)) for topic, name, rx in _spans(guard)]
    aspects = re.compile("|".join(f"(?:{a})" for a in ASPECTS_ALL + ASPECTS.get(category_id or "", ())))
    return spans, aspects


def cut_purchase(text: str, category_id: str | None = None) -> tuple[str, list[str]]:
    """Every span about the Korean purchase out -> (text, the topics cut)."""
    spans, _ = _compiled(str(category_id) if category_id else None)
    cut: list[str] = []
    for topic, _name, pattern in spans:
        text, n = pattern.subn(" ", text)
        if n:
            cut.append(topic)
    return text, sorted(set(cut))


# ---- the English side (after translation) ----------------------------------------------------------------------
# The owner, 2026-11-09, after the 100-product pilot: a review says nothing about the price or the value ("가성비",
# "이 가격에 얻을 수 없죠", "for the price") and names no other platform or buying agent ("11번가", "구매대행"). The
# Korean says it in too many ways to cut by clause; the English says it in a few words, so a sentence of the
# translated review that does goes whole (58 sentences of the pilot). "cheap-looking", "feels cheap" are about the
# product and stay, and so do "the real deal" and a seller story's "asked for extra money" (complaints stay).
_EN_PRICE_RE = re.compile(
    r"\b(?:price[ds]?|pricey|pricier|pricing|value|(?<!extra )(?<!more )money|bang for (?:the|your|my) buck|budget(?:-friendly)?|"
    r"afford(?:able|ably)?|bargain|steal|cost(?:s|ing|ly)?|cheap(?:er|est|ly)?|inexpensive|expensive|"
    r"(?:good|great|better|best|sweet|nice|fair|decent) deal|easy on the wallet|"
    r"\d[\d,.]*\s*(?:million\s*|thousand\s*)?(?:won|bucks|dollars|KRW)|(?:thousand|million)\s+(?:won|bucks|dollars)|"
    r"won(?=\s*[.,!?)]|$))\b", re.I)
_EN_QUALITY_CHEAP_RE = re.compile(
    r"\bcheap(?:-|\s+)(?:look|feel|made|plastic|material|finish|quality)\w*|\b(?:looks?|looking|looked|feels?|feeling|felt|"
    r"seems?|seemed)\s+(?:a\s+(?:bit|little)\s+|kind\s+of\s+|pretty\s+|really\s+|very\s+|too\s+|so\s+)?cheap\w*", re.I)
_EN_PLATFORM_RE = re.compile(
    r"\b(?:Naver|Smart\s?Store|Coupang|11st|11th\s+Street|G-?Market|SSG(?:\.com)?|Lotte\s?On|Musinsa|AliExpress|Temu|"
    r"Amazon|Golfzon\s+(?:Market|Mall)|(?:buying|purchasing|purchase)\s+agen(?:t|cy)|proxy\s+(?:buyer|service)|"
    r"overseas\s+(?:shopping|purchase|direct)|direct\s+(?:purchase|import)s?)\b", re.I)
_EN_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def english_cut(sentence: str) -> str | None:
    """The topic that sends this English sentence out ("price", "platform"), or None."""
    if _EN_PLATFORM_RE.search(sentence):
        return "platform"
    if _EN_PRICE_RE.search(_EN_QUALITY_CHEAP_RE.sub(" ", sentence)):
        return "price"
    return None


def cut_english(text: str) -> str:
    """The translated review without its sentences about the price or another platform (line breaks kept)."""
    lines = []
    for line in (text or "").split("\n"):
        kept = [s for s in _EN_SENTENCE_RE.split(line.strip()) if s and english_cut(s) is None]
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines)


# ---- the verdict -----------------------------------------------------------------------------------------------

@dataclass
class Verdict:
    keep: bool
    text: str                                # the cleaned text ("" for rating_only)
    grade: str                               # full | short | rating_only | sponsored
    quality: int                             # 0..100: aspects, length, photos
    cut: list[str] = field(default_factory=list)


def _syllables(text: str) -> int:
    return len(re.findall(r"[가-힣]", text))


def clean(text: str, has_photos: bool = False, category_id: str | None = None) -> Verdict:
    original = text or ""
    if SPONSORED_RE.search(original):
        return Verdict(False, "", "sponsored", 0)
    category = str(category_id) if category_id else None
    cut_text, cut = cut_purchase(original, category)
    cut_text, injected = _INJECTION_RE.subn(" ", cut_text)
    if injected:
        cut = sorted(set(cut) | {"injection"})
    out = tidy(strip_decoration(cut_text))
    if cut:                                     # a cut can leave a line on the particle of its noun ("으로 왔어요")
        out = tidy("\n".join(_ORPHAN_RE.sub("", line) for line in out.split("\n")))
    _, aspects_re = _compiled(category)
    aspects = len({m.group(0) for m in aspects_re.finditer(out)})
    syllables = _syllables(out) + 2 * len(re.findall(r"[A-Za-z]{2,}", out))   # an English review counts too
    if aspects:
        grade = "full"
    elif syllables >= 2 and (OPINION_RE.search(out) or syllables >= 4):
        grade = "short"
    else:
        grade, out = "rating_only", ""
    quality = min(60, 20 * aspects) + min(25, syllables // 4) + (15 if has_photos else 0)
    return Verdict(True, out, grade, min(100, quality), cut)


def clean_reviews(reviews: list[dict[str, Any]], category_id: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The prepared reviews ({id, text_ko, photos, ...}) -> all of them but sponsored ones, each with text_ko
    cleaned, text_grade, text_quality, text_original_ko (when the text changed) and text_cut (the topics cut); and
    the counts for the note."""
    kept: list[dict[str, Any]] = []
    grades: Counter[str] = Counter()
    trimmed = 0
    for r in reviews:
        v = clean(r.get("text_ko") or "", bool(r.get("photos")), category_id)
        grades[v.grade] += 1
        if not v.keep:
            continue
        out = dict(r, text_ko=v.text, text_grade=v.grade, text_quality=v.quality)
        if v.text != (r.get("text_ko") or ""):
            out["text_original_ko"] = r.get("text_ko")
        if v.cut:
            out["text_cut"] = v.cut
            trimmed += bool(v.text)
        kept.append(out)
    stats = {"in": len(reviews), "kept": len(kept), "grades": dict(grades), "trimmed": trimmed}
    return kept, stats
