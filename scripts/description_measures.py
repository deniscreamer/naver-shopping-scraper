"""Package weight and size from the description: the OCR text of its images (description_images.py) and the lines
of its typed text (one more block of rows, no OCR doubt), merged with today's fields (package_measures.py). Pure,
offline, deterministic.

The owner, 2026-11-07: RapidOCR only; match size and weight from OCR with simple rules; no 100 % accuracy chase;
not tied to one category. 2026-11-10 (in place of "the larger value wins"): the flat category default is the
last resort. A field takes the first of

  1  the seller's own statement of that field: the server path's value (source_stated; nothing here replaces
     it), else a packed weight, a box, a set / product weight read in the description (guess)
  2  an estimate composed from the set's parts (compose): each part from the product's own data when it is
     there, from the operator's baseline when it is not (the `baselines` block of the category's row in
     category_measures.json: never made up here; no block, no composition)
  3  the category default, only when the composition is unknown (the number of items or the container's state
     cannot be told); a known composition is never dropped for being small (three clubs are three clubs)

Two layers of reading (read_rows):

  core (every category)   what a seller writes of the product itself, in any category:
                            packed   박스 / 포장 / 택배 / 패키지 + a weight or an a x b x c size     -> the package's
                            stated   세트 / 본품 / 제품 / 상품 무게 kg; a row labelled 무게 / 중량 / weight
                                     with a kg value                                            -> the product's
                            (a product's size, 제품 / 상품 크기 / 사이즈 / 규격 + a triple, is read as a fact and
                            is no field's: a product is not its box)
  profile (per category)  the parts a category's images list when the product is a set of like items in a
                          container: each item's weight and length in spec tables, the container's weight and
                          size, how many items. A Profile is data (ranges, words), chosen by the Naver leaf
                          category id (CATEGORY_PROFILES, profile_for). GOLF_SET (50002788, OCR study on 50
                          sets, 2026-11-07): items = clubs ("클럽 중량(g) / 310 / 306", "45.5인치"), container =
                          the bag ("무게 약 4.1kg / 높이 약 89cm", "입구 9인치", "캐디백-91cm(세로)*31cm(폭)*40cm(가로)").
                          A row is the container's when the nearest row naming one, on it or up to `window`
                          rows above, names the container; when that row names an accessory (a Boston bag, a
                          shoe bag, a pouch: the profile's word list) its size and weight are nobody's.
                          Without a profile only the core runs.
                          The items' tables come two ways (120 sets, 2026-11-10): a labelled row, the values
                          after the label ("클럽길이(inch) / 45.5 / 43", "총중량(g) / 308 / 326 / ..."), or a
                          header naming the columns with one item per row below ("클럽넘 / 로프트 / 전체길이 /
                          총중량", "1W / 10.5 / 45.25 inch / 320g"). A length needs no unit mark (inches and cm
                          are apart) and is read at any OCR confidence; a weight is an item's only in its band,
                          and a label whose row holds only weights under it names a part in that image.
                          (The container's length, mouth and sides are read as facts; since 2026-11-10 the
                          box's sides are the baseline's, so no field takes them.)

The composition (compose, _items_total, _boxed; a set of a profile's items in its container):

  product_weight_g    items + container. Items: the sum of one table that gives one weight per item of the set;
                      else the count x the median item weight, when the weights read cover at least half of the
                      items (weights within 2 % are one item's: a club by two flexes); else the count x the
                      baseline item weight. Container: nothing when the set has none, its stated weight, else
                      the baseline's
  package_weight_g    the product's weight as the field ends up + the baseline carton
  package_length_mm   the longest item read, else the baseline's, + the baseline margin
  package_width_mm,   a stated box, whole or not at all; else the baseline sides of a set without the
  package_height_mm   container / with it

The longest item is the largest length stated, taken only inside the profile's band of the longest (the driver:
42.5-48.5 in); below it the driver's row was not read and the baseline stands in, never a putter or an iron.

The seller's own table before the listing's count (_items_total; 120 sets, 2026-11-10). A listing counts pieces
("총클럽개수 12개": nine clubs, the bag, two head covers, 8053135821; "11피스" with the bag, 13657325637) or
states no count at all (5543663553, 7674852369). A full table is the set then: its sum the items' weight, its
length the count. Full: one row or the rows under one header, at least 9 weights, the heaviest 475 g and up
(the ladder runs to the putter: the putters stated are 485-549 g, the heaviest wedge 462 g; without it the
table is short of the set, as X HOT's ten of eleven, 8974646004); the listing's count may be up to 3 over its
length (the two listings of the 120 seen to count pieces are 1 and 3 over), never under. Rows gathered under
one label are not such a table (the two rows of 13446843026 hold 11 of its 12 clubs). The numbers are the
profile's (full_items, full_last_g, pieces_over). A count the table gives is weaker than the listing's:
confidence 2, `count_from: "table"` (and `count_listed`, what the listing said).

Confidence, 1-5 on every field (the owner, 2026-11-10; 1-3 before: package_measures.py has the scale):
  5  the seller states the field in typed text with its kind (a typed box, a typed packed weight)
  4  stated, a weaker reading: read from an image, or the kind left open
  3  composed wholly from the seller's own figures for this product, plus the operator's carton / margin: the
     items' exact sum with the container absent or its weight stated (the count the listing's, the container's
     state from the listing or the typed text); the length from the longest item read
  2  composed with a baseline or a weak part: the count x the median, a baseline item / container / longest
     item, the baseline box sides, the container's state from an image's sentence, the count from the images
     or from the items' table alone
  1  the flat category default
A composed field says how it was built: `how`, `parts` ([{part, value, from, quote}]: from "stated", the items'
total as it was made, "baseline", or the field it is), `baseline` (who approved the operator's amounts in it)
and, as `compared`, the default it replaced.

More rules (2026-11-11, the 300 sets of the fairwardgolf job; scripts/README.md "More of the page"): core skips
(shipping rules, a buyer, a shoe box), "세트 패키지" not a package, "크기,중량" a weight; the profile's bag words
(machine translation, a composition item, gift bags, container_hint), a closed composition (container_closed:
no bag, weak), the bag assumed when the count is known and nothing says (container_assumed: the baseline bag,
flagged, 2), composition_count, the label spellings, ref_weight (the #7 iron for the clubs no row weighs),
part_columns (head + shaft + grip), a weight in its label's cell / one row up / after an option index, a part
table + the baseline for the rest, per-row tables that are the set, short_set / short_spread, length_noise,
shaft_table, long_sure_mm, ladies (the women's driver of an L / A variant).

Known limits (2026-11-11, left as they are): the #7's weight stands for every club its image does not weigh,
the putter too (a few hundred grams under on a set of 9-12); a composition OCR splits over rows gives no count
(13409110111); several weights in one cell ("306/310", "C1320") give the first only (no set of the 300 changed
by it); an option's "N개" beside other options is never the set's, even where it is.

Known limits (2026-11-10, left as they are): a "1+1" listing ships two sets and is weighed as one (5684497984);
a table is not bound to a variant: of several whole tables the lightest stands for every variant (the S set of
11659201020 and 5543663553 gets the R row; the women's variants of 7674852369 the men's twelve clubs); on a
page of several models the bag's weight may be another model's bag (12696567111) and the longest driver stands
for every variant.

Rows that are a shop rule (20kg 초과), customs (5kg 이하 통관), a person (체형 182cm 84kg), a price, a disclaimer, or
after a cross-sell heading (함께 구매하면 좋은 상품 / 추천 상품, to the end of the image) are never read.

Whether a variant has the container (container_in, container_listed, compose), in the order of trust: the
variant's own option words; the title, 모델명 and one-value facts; the profile's 상품정보 row (골프백포함여부: 미포함 /
캐디백); a container sold as a paid add-on (the set then has none); the sentences of the typed text; those of the
images (a weak part: confidence 2 at most). Nothing says it: the weight and the two sides stay the default's.

    from description_measures import profile_for, read_rows, package_for
    profile = profile_for("50002788")                    # by Naver category id; None: the core only
    facts = read_rows(images, profile, typed)            # images: [[row text, ...] per image], rows top to bottom;
                                                         # typed: the typed description's lines
    fields, taken = package_for(variant_fields, facts, item_count=12, container=True, profile=profile)
                                                         # plausible=, baselines=: the category row's blocks
"""
import re
import statistics
from dataclasses import dataclass
from typing import Any

FIELDS = ("product_weight_g", "package_weight_g", "package_length_mm", "package_width_mm", "package_height_mm")
SIDES = FIELDS[2:]
SOURCE = "description_image"
TYPED = "description_text"               # `from` of a value read in the seller's typed text, not in an image
COMPOSED = "composed"                    # `source` of a field worked out from the set's parts (compose)
BASELINE = "baseline"                    # `from` of a part the operator's table gave, not the product
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
    longest_mm: tuple[float, float]      # the longest item of a set (the driver): no other item is in this band
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
    accessory: re.Pattern                # a thing sold or given with the set, neither the product nor its
                                         # container ("보스턴백", "파우치"): its size and weight are never read
    window: int = 10                     # rows above a value searched for the container's / an accessory's name
    column_rows: int = 18                # rows read under a table's header (a 14-club table, its flex rows)
    set_spread: float = 1.0              # a set's heaviest item is at least this much its lightest
    part_table: re.Pattern | None = None     # a header of a part maker's own table: its lengths are the part's
    container_trim: re.Pattern | None = None   # a thing for the container, never one ("캐디백 항공커버")
    count_row: str | None = None         # a 상품정보 row that states the item count ("총클럽개수": "11개")
    count_title: re.Pattern | None = None   # the item count as a title writes it ("클럽 10개", "풀세트 9개")
    container_spec: str | None = None    # a 상품정보 row that says which container comes with it ("골프백포함여부")
    container_spec_no: tuple[str, ...] = ()                # its values that say none ("미포함")
    same_item: float = 1.02              # two weights within this of each other are one item's (its flexes)
    full_items: int = 0                  # a table of at least so many items whose heaviest is full_last_g and up
    full_last_g: float = 0.0             # (the ladder's last item) is the whole set, whatever the listing counts;
    pieces_over: int = 0                 # the listing's count may be so many over it (pieces, a gift). 0: no rule
    plausible: tuple[tuple[str, float, float], ...] = ()   # (field, min, max): a guess outside is absurd
    # 2026-11-11, the 300 sets of the fairwardgolf job (research of the owner's "собрать больше данных"):
    container_hint: re.Pattern | None = None      # a row of the container's own table that names no container
                                                  # ("크기 / 9형", "구경 / 8.5인치"): its block is the container's
    kind_word: re.Pattern | None = None           # an item kind ("드라이버", "아이언"): composition lines and counts
    composition_row: str | None = None            # a 상품정보 row that lists the kinds ("풀세트구성")
    single_item: re.Pattern | None = None         # a listing of one item filed as a set ("치퍼", "드라이빙 아이언")
    single_option: re.Pattern | None = None       # an option value of one item's own choices ("24도 스틸")
    ref_weight: re.Pattern | None = None          # one item's weight marked as its group's ("410(#7)")
    part_columns: tuple[re.Pattern, ...] = ()     # the part columns whose sum is an item's weight (head, shaft, grip)
    shaft_table: re.Pattern | None = None         # a shaft maker's table header: no item length under it
    length_noise: re.Pattern | None = None        # a row whose length is another thing's ("47인치 지원": a bag's)
    long_sure_mm: float = 0.0                     # a longest item above it needs two rows that state it
    ladies: re.Pattern | None = None              # a row of the women's / soft-flex item ("L", "여성용")
    short_set: int = 0                            # a set of at most so many items needs only short_spread
    short_spread: float = 1.0
    container_assumed: bool = False               # items known, the container's state not: composed with the
                                                  # baseline container (the heavy side), flagged (the owner)


_BAG = r"(?:골프\s*가방|백)"               # any bag word ends in 백: "캐디백", "스탠드백", "백세트"
GOLF_SET = Profile(
    item="clubs",
    # OCR's 클럽 and 총: "클럼무게(g) / 307 / 313 / ..." (13495098284), "충중량(g)" (6655509590)
    # 2026-11-11 (300 sets): "총 종량" (5059255237), "클럽 증량(g)" (11227278650), "무계(g)" (9343324012), "Club중량"
    # (5917553052), "클립 무게(g)" (8064868493), "T/W(g)" (11658240481); never "N g 증량", a weight gain
    item_weight_label=re.compile(r"(?:클[럽럼립업]|[총충]|전체|club)\s*(?:[중종충]\s*[량림당]|무\s*[게계])|"
                                 r"(?:클[럽럼립업]|[총충])\s*증\s*량|club\s*weight|total\s*weight|\bT\s*/\s*W\s*\(|"
                                 r"^\s*(?:#\d\s*)?(?:중량|무[게계])\s*\(g\)", re.I),
    # parts as OCR spells them too (사프트중량, 해드무게, 허드중량, 손잡이무게); 스윙웨이트 is the balance beside a
    # total, not a part: "총중량(g)/스윙웨이트 / 약316g/D1 ..." (6392093003)
    part_label=re.compile(r"샤프[트드]|사프[트드]|[헤해허]드|그립|손[잡집]이|shaft|head|grip|바디|무게추|"
                          r"(?<!스윙)(?<!스윙 )웨이트|스크류|screw", re.I),
    item_g=(240, 650),                   # driver ~300 g, irons ~400 g, putter ~550 g; the lightest club stated on
                                         # 120 sets is 252 g, a wood's head 197-235 g ("중량(g) / 198 / 202 / 207",
                                         # 7583123963: such a row makes its label a part's, read_rows)
    item_in=(32.0, 48.5),                # putter 33", driver 46"
    item_cm=(81.0, 124.0),
    longest_mm=(1080, 1232),             # 42.5-48.5 in: the 118 stated drivers are 43.5-46.0 in (1105-1168 mm), a
                                         # ladies' 3-wood 41-42.5 in, a putter 33-34 in (120 sets, 2026-11-10)
    # not a head's make: "저중심 4피스 티타늄 페이스 설계" (12945108653), "4PCS단조" (6540695739)
    count_re=re.compile(r"(?<![\d.+])(\d{1,2})\s*(?:PCS|Pcs|pcs|PC(?![A-Za-z])|ps(?![A-Za-z])|피스|P(?![A-Za-z0-9]))"
                        r"(?!\s*(?:단조|티타늄))|"
                        r"(?:클럽|총)\s*(\d{1,2})\s*개|(\d{1,2})\s*개\s*(?:클럽|구성)"),
    count=(3, 16),
    container="bag",
    # machine translation of 球包 / 枪包: "볼 가방용 12 장", "12+볼백", "공 봉투 크기", "9개 스틸 건백" (13024139837,
    # 12548802833, 13842637863; 2026-11-11)
    container_word=re.compile(r"캐디\s*백|골프\s*백|스탠드\s*백|휠\s*백|카트\s*백|캐리\s*백|bag\b|백\s*세트|"
                              r"볼\s*백|볼\s*가방|공\s*봉투|건\s*백", re.I),
    container_row=re.compile(r"입구|후드|커버|포켓|숄더|스트랩|모델|사이즈|무게|중량|높이|총\s*길이", re.I),
    container_g=(1500, 9000),            # a caddie / stand bag (with a boston bag 4.95 kg)
    container_long_mm=(700, 1500),       # its height / total length
    container_mouth_in=(7.0, 11.0),      # 8.5 / 9 / 9.5 inch
    # "백세트제외" (13446875008), "골프 가방 불포함 상품 입니다." (13389271367), "캐디백은 포함되어 있지 않습니다."
    # (13325799991), "골프백 별매 추가선택가능" (9266336330), "10개세트 클럽만" (11164222651; not "클럽만 따로 판매",
    # 8958060680, nor the clubs' own: "클럽만의 기술력", "이 클럽만으로")
    container_no=re.compile(_BAG + r"\s*(?:세트\s*)?(?:은|는)?\s*(?:미\s*포함|불\s*포함|포함\s*(?:되지|되어\s*있지|안)|"
                            r"없음|없이|별도|별매|제외|X\b|x\b|미\s*제공)|"
                            r"클럽\s*만(?![의으을이])(?!\s*(?:필요|원하|구매|주문|구입|따로))"),
    # also "세트 내용 | 8개+캐디백", "조합되는 캐디 백" (2026-11-11); a bag in a composition line: read_rows
    container_yes=re.compile(_BAG + r"\s*(?:\+\s*[가-힣]+\s*)*(?:세트\s*)?(?:까지\s*)?(?:포함|증정|구성)"
                             r"(?!\s*(?:되지|되어\s*있지|안))|"
                             r"\d\s*개\s*\+\s*(?:캐디|골프|스탠드|카트|볼)\s*백|조합\s*되는\s*캐디\s*백"),
    # a Boston bag ("여성용 경량 보스턴", 13513786835), a shoe bag, a pouch, a half bag: extras, never the set's bag
    # and a gift's bag: "젝시오 크루 고급 레디백" (12979780461), "6핑BS버킷백", "텀블러백" (12133282383)
    accessory=re.compile(r"보스[턴톤]|boston|슈즈\s*백|신발\s*(?:가방|주머니)|파우치|pouch|하프\s*백|레디\s*백|"
                         r"버킷\s*백|텀블러\s*백", re.I),
    # driver ~300 g, wedge ~450 g, putter ~520 g; the irons alone are not a set ("클럽중량(g) / L / 317 / 322 / ...
    # / 347 / 347": eight irons on the page of a driver and seven, 12965394174), nor a driver by nine shafts
    # (8029218821)
    set_spread=1.25,
    part_table=re.compile(r"tip|butt|외경", re.I),         # a shaft maker's table: its 46 in is the uncut shaft
    container_trim=re.compile(r"커버|cover|네임\s*택|name\s*tag|이름표|후드", re.I),   # a bag's cover, its name tag
    count_row="총클럽개수",
    # "클럽10개", "10개 풀세트", "골프채 9개", "풀세트 [11개]", "(13개)", "11개조합"; never "웨지2개" (below the
    # band), "3개월"
    count_title=re.compile(r"클럽\s*(\d{1,2})\s*개|(?<![\d.+])(\d{1,2})\s*개\s*(?:클럽|조합|세트|구성|풀\s*세트)|"
                           r"(?:풀\s*세트|골프채|세트)\s*[\[(]?\s*(\d{1,2})\s*개(?![월입])|"
                           r"[\[(]\s*(?:클럽\s*)?(\d{1,2})\s*개\s*[\])]"),
    container_spec="골프백포함여부",        # "미포함" | "캐디백" | "스탠드백" | "캐디백, 보스턴백" (on 81 of 120 sets)
    container_spec_no=("미포함",),
    # the driver "약252 / 약255" by flex (L / A), the utility "약292 / 약296", the #7 iron "약320g / 약321g": three
    # clubs of nine, not six (10816781893; its pairs are 0.3-1.9 % apart)
    same_item=1.02,
    # the whole set in one table, driver to putter (120 sets, 2026-11-10): the shortest set tabled is 9 clubs
    # (8053135821, 13462928946), the longest part of one that holds a putter 7 (13627933340: the irons and the
    # putter of 11); the putters stated are 485-549 g, the heaviest wedge 462 g. Without the putter a table is
    # short of the set: X HOT's ten values end at the SW, 452 g, and its "11개" is right (8974646004)
    full_items=9,
    full_last_g=475,
    # "총클럽개수 12개" over a table of 9: the bag and two head covers are pieces (8053135821); "11피스" over ten
    # clubs: the bag (13657325637): the two listings of the 120 seen to count pieces. A typed "총 14piece" over
    # eleven clubs tabled (10639350746, fixtures/collected) is 3 over as well
    pieces_over=3,
    # a golf full set in its box (OCR study 2026-11-07 and the 55 harvester sets): wider than any set
    plausible=(("product_weight_g", 1500, 20000), ("package_weight_g", 2000, 25000),
               ("package_length_mm", 800, 1700), ("package_width_mm", 100, 700), ("package_height_mm", 80, 600)),
    # a bag's table with no bag word in reach: "크기 / 9형" over "중량(g) / 약4kg" (9626476348)
    container_hint=re.compile(r"(?<![\d.])\d{1,2}(?:\.\d)?\s*형(?![가-힣])|입\s*틀"),     # not 구경: a grip's core
    kind_word=re.compile(r"드라이[버브]|우드|페어웨이|유틸|하이브리드|아이언|웨지|퍼터|치퍼|\bDR\b|\bFW\b|\bUT\b|\bPT\b"),
    composition_row="풀세트구성",
    # one club filed under full sets: 13743963823 (a driving iron), 13464713764 (접이식 실내 골프채, a putter)
    single_item=re.compile(r"드라이빙\s*아이언|치퍼|접이식|실내\s*(?:연습용\s*)?골프채|단품|낱개"),
    # 13743963823 ("초보 남성 골프채 풀세트", a Ben Sayers driving iron): its options are one club's lofts x shafts
    # 13787625100: "2번(17도) L" (one hybrid by its number)
    single_option=re.compile(r"^\s*(?:\d\s*번\s*)?\(?\s*\d{1,2}(?:\.\d)?\s*도\s*\)?\s*(?:스틸|그라파이트|카본|SR|[RSLAX])?\s*$"),
    # "410(#7)" (12049132531), "337(#7번 아이언기준)" (10567215349), "#7 약320g" (10816332813), "364(R:#7)"
    # (the #7 iron is the reference; "#4-324g" is the #4's own weight: 8029218821)
    ref_weight=re.compile(r"[(（]\s*(?:[A-Z]{1,2}\s*:\s*)?I?\s*[#＃]?\s*7\s*(?:번)?(?![\d.])|[#＃]\s*7\s*[-–]?\s*약?\s*\d{3}|"
                          r"[(（]\s*[#＃]?\s*7\s*번?\s*(?:아이언)?\s*[A-Z]{0,2}\s*기준"),   # not "(#5 기준)": a wood's
                                                                              # own weight (12089326778)
    # PGM / SMACK: "TYPE / No. / LIE / LOFT / Head(g) / Shaft(g) / Grip(g) / Len" (12391346892), "헤드무게 / 바디무게
    # (the shaft) / 그립무게" (10562364435)
    part_columns=(re.compile(r"head\s*\(g\)|[헤해]드\s*(?:무게|중량)", re.I),
                  re.compile(r"shaft\s*\(g\)|샤프트\s*(?:무게|중량)|바디\s*무게", re.I),
                  re.compile(r"grip\s*\(g\)|[그고]립\s*(?:무게|중량)|손잡이\s*\(g\)", re.I)),
    shaft_table=re.compile(r"(?=.*\bCPM\b)(?=.*(?:torque|토크|kick|킥))", re.I),    # 10954221464: "46inch" uncut
    length_noise=re.compile(r"대응|지원|수납"),       # "대응 클럽 길이: 45인치", "47 Inch 지원" (8958623680)
    long_sure_mm=1181,                               # 46.5 in: the drivers stated are 43.5-46.0 in
    ladies=re.compile(r"여성|레이디|ladies|(?<![A-Za-z])[LA](?![A-Za-z])", re.I),
    short_set=4,                                     # a driver, a wood and a hybrid: 252-296 g (11415466474)
    short_spread=1.1,
    container_assumed=True,
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
_KG_RE = re.compile(_NUM + r"\s*\(?\s*(?:kg|㎏|킬로)(?!\s*(?:경량화|가벼))", re.I)
# "중량-약4.1 (kg)" (12089326778); not "약1.5kg경량화되어": 1.5 kg lighter than the old bag (5543663553)
_G_RE = re.compile(r"(?<![\d.])" + _NUM + r"\s*g(?![a-z])", re.I)
_BARE_RE = re.compile(r"(?<![\d.])(?<![A-Za-z]{2}\s)(\d{3}(?:\.\d)?)(?!\d)(?:\s*g)?(?![\w.%])")
# "약318", "#3-약344", "343/D1"; not a shaft's model after its name: "약256g / C1(ULT 250 J-L)" gave a 250 g club on
# three of seven rows (9321714669), "DG 300"
_INCH_RE = re.compile(r"(?<!\d)" + _NUM + r"\s*(?:인치|인츠|인체|인처|inch|in\b|\")(?!\s*(?:대응|지원))", re.I)   # not "9형 / 47인치 대응": the clubs a
                                                                            # bag takes (8958060680)
_CM_RE = re.compile(_NUM + r"\s*\(?\s*(?:cm|센치|㎝)", re.I)                 # "총길이 130(cm)"
_AXIS = r"(?:(?<![A-Za-z])[WDHL](?![A-Za-z])|가로|세로|높이|폭|길이|깊이)?\s*:?\s*"       # "W53 x D38 x H62.5 cm"
_TRIPLE_RE = re.compile(_AXIS + _NUM + r"\s*(?:cm|mm)?\s*[x×X*]\s*" + _AXIS + _NUM + r"\s*(?:cm|mm)?\s*[x×X*]\s*"
                        + _AXIS + _NUM + r"\s*(cm|mm|inch|인치)?", re.I)
# no unit: cm; "Item Package Dimensions L x W x H | 48.2 x 12.7 x 8.5 inches" (typed, 10639350746)
_SIDE_RE = re.compile(_NUM + r"\s*cm\s*\(?\s*(?:세로|가로|폭|높이|길이|깊이)", re.I)   # 91cm(세로)*31cm(폭)*40cm(가로)
_LENGTH_CELL = re.compile(r"길\s*[이o치]|length|[같집]\s*[이에]\s*\(?\s*(?:i?nch|인치)", re.I)   # "립같이(inch)",
                                                                                         # "집이(nch)" (2026-11-11)   # OCR's 길이: "길o(inch)", "길치(인치)" (13462928946)
_LENGTH_NUM = re.compile(r"(?<![\d.,])(\d{2,3}(?:[.,]\d{1,4})?)(?!\d)")        # "45.25", "45,25", "97.4725"
_LENGTH_CM = re.compile(_LENGTH_NUM.pattern + r"\s*\(?\s*(?:cm|센치|㎝)", re.I)   # three decimals: "(114.935cm)"
_GLUED_RE = re.compile(r"(\.\d{2,3}?)(?=1?\d{2}\.\d)")   # two cells read as one: "116.84107.32" (5543663553)
_LABEL_CELL = re.compile(r"[가-힣]{2}|[A-Za-z]{3}")        # a cell of words, not of values: "토크(°)", "라이각"
# not "풀세트 패키지" / "세트 패키지": the set itself (2026-11-11); "Gross Weight 465g" of one club is under any band
_PACKED_WORD = re.compile(r"박스|포장|택배\s*(?:무게|중량|사이즈|크기)|(?<!세트)(?<!세트\s)패키지|package|packing|gross", re.I)
# and the notice's "크기,중량 1230mm/10kg" (상품정보고시: the product's; 2026-11-11)
_SET_WORD = re.compile(r"(?:풀\s*세트|세트|본품|제품|상품)\s*(?:총\s*)?(?:무게|중량)|(?:set|product|item|net)\s*weight|"
                       r"크기\s*[,·/]\s*중량", re.I)
_WEIGHT_HEAD = re.compile(r"^\s*(?:총\s*)?(?:무게|중량|무|weight)\s*[:)(]?\s*(?:/|\||:|$|약|\d)", re.I)
# "무게 / 3.5kg"; "무 / 0.6kg": OCR split the label of a spec table into its letters (9809159942, 2026-11-07)
_SIZE_WORD = re.compile(r"(?:제품|본품|상품|완제품)?\s*(?:크기|사이즈|규격|치수)|size|dimension", re.I)
_SKIP_ROW = re.compile(
    r"초과|이하|미만|넘는|넘을|경우|화물|택배비|택배사|착불|운임|배송비|교환|반품|환불|관부가세|통관|면세|미화|"
    r"신장|체형|키\s*\d|몸무게|후기|리뷰|유저|\d\s*원(?![가-힣])|₩|할인|적립|차이가?\s*있을|다를\s*수|오차|"
    # 2026-11-11 (300 sets): a shipping rule ("5kg내외:4만원", "2kg까지는", "세변합이160cm이상", "무게가10kg 이상"), a
    # buyer ("175cm, 77~79kg", "182cm- 84kg"), the returns' shoe box ("골프화박스 규격 395 x 250 x 155")
    r"내외|까지는|\d\s*(?:kg|cm)\s*이상|1[4-9]\d\s*cm\s*[,\-/~]?\s*[4-9]\d(?:\s*~\s*\d{2})?\s*kg|"
    r"(?:골프화|골프회|신발|슈즈)\s*박스")
# a heading of the shop's other products ("함께 구매하면 좋은 상품", 13369469193; "... 베스트 추천 상품입니다.",
# 12965275150). Not the returns text "다른 상품으로 교환하는 경우" nor "원하시는퍼터를함께구매하시어" (row 19 of
# 311 on 12606747315): on a description that is one tall image those cut the whole spec away (2026-11-10)
_CROSS_SELL = re.compile(r"(?:함께|같이)\s*구매\s*하면|추천\s*상품|관련\s*상품")
KEYS = ("packed_weights", "packed_boxes", "set_weights", "product_weights", "product_sizes",
        "item_weights", "item_lengths", "item_counts",
        "container_weights", "container_long", "container_sides", "container_no", "container_yes", "container_closed")
_BARE_G = re.compile(r"(?<![\d.])(\d{2,3}(?:\.\d)?)\s*g?(?![\d.])")   # a part's grams in its column ("65", "198g")
_LOST_DOT = re.compile(r"(?<![\d.,])([34]\d{3})(?![\d.,])")   # "4375": 43.75 in with its dot lost (8437045488)
_GLUED_INDEX = re.compile(r"^\s*[12](\d{3})\s*[(（]")           # "1378(S:#7)": option 1, 378 g (6728937165)


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _in(v: float, band: tuple[float, float]) -> bool:
    return band[0] <= v <= band[1]


def _sides(triple: re.Match) -> list[float]:
    scale = {"mm": 1, "inch": INCH_MM, "인치": INCH_MM}.get((triple.group(4) or "").lower(), 10)
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


def _about(rows: list[str], i: int, p: Profile) -> str | None:
    """What row i speaks of, by the nearest row at or above it (p.window rows) that names one: "container", or
    "accessory" (13513786835: "여성용 경량 보스턴" 8 rows above "사이즈 / L48×W24×H30CM"). A row naming both is
    the container's ("총무게:(캐디백+보스턴백) 약4.95kg", 7583123963)."""
    for row in reversed(rows[max(0, i - p.window):i + 1]):
        if p.accessory.search(row):             # "젝시오 크루 고급 레디백": the gift's, though it says 백
            return "accessory" if not p.container_word.search(p.accessory.sub("", row)) else "container"
        if p.container_word.search(row) or p.container_hint and p.container_hint.search(row):
            return "container"
    return None


def _grams(cell: str, p: Profile) -> float | None:
    """One item's weight in a cell of its table: "320g", "약318", "#3-약344"; a part's or a set's is out of band."""
    w = _G_RE.search(cell) or _BARE_RE.search(cell)
    if w and _in(_num(w.group(1)), p.item_g):
        return _num(w.group(1))
    glued = _GLUED_INDEX.match(cell)
    return _num(glued.group(1)) if glued and _in(_num(glued.group(1)), p.item_g) else None


def _ref_grams(cell: str, p: Profile) -> float | None:
    """The reference iron's weight in a cell that names it: "#5 365g #7 376g" 376, "304(#5) 315(#7)" 315."""
    m = re.search(r"[#＃]\s*7\s*[-–]?\s*약?\s*(\d{3})", cell) or re.search(r"(\d{3})\s*g?\s*[(（][^)）]*7", cell)
    return _num(m.group(1)) if m and _in(_num(m.group(1)), p.item_g) else None


def _lengths(cell: str, p: Profile) -> list[int]:
    """The item lengths a cell states, mm. The unit is the band's (inches 32-48.5, cm 81-124: they never meet), so
    it needs no mark: "45.25 inch", "110.49/43.5" (13413924099), "약114cm", "45,25", "44°" (OCR's inch mark)."""
    values = [_num(x) for x in _LENGTH_NUM.findall(_GLUED_RE.sub(r"\1 ", cell))] + \
        [v for x in _LOST_DOT.findall(cell) if _in(v := int(x) / 100, p.item_in)]
    return [round(v * INCH_MM) if _in(v, p.item_in) else round(v * 10) for v in values
            if _in(v, p.item_in) or _in(v, p.item_cm)]


def _column_lengths(cells: list[str], j: int, n: int, p: Profile) -> list[int]:
    """One item's row under a header whose cell j of n is the length: that cell. A row OCR dropped cells from
    ("드라이버 / 10.5 / 44.5 / 60 / 339" under six heads, 7674852369): cell j from the left or from the right,
    when only one of the two is a length (an iron's loft, 44-48, is inside the driver's band: never a guess)."""
    if len(cells) == n:
        return _lengths(cells[j], p)
    if not n - j <= len(cells) < n:
        return []
    left, right = _lengths(cells[j], p) if j < len(cells) else [], _lengths(cells[j - n], p)
    return left or right if not (left and right) else []


def read_rows(images: list[list[Any]], profile: Profile | None = None,
              typed: list[str] | None = None) -> dict[str, Any]:
    """Facts from the OCR rows of each image (the core's, plus the profile's parts when one is given). A row is its
    text, or (text, OCR confidence): a row read below NUMBER_CONF gives no single value (a box, a set / product
    weight or size, the container's), only its words and the items' weights and lengths (an item's value is held
    by its band, and a set's by the band of its longest item).
    typed: the lines of the seller's typed description, read as one more block of rows (no OCR doubt; its table
    cells are joined by " | ", an image's by " / "). Every value carries its row as the quote, and `image` (its
    number) or `from` TYPED."""
    facts: dict[str, Any] = {k: [] for k in KEYS}
    p = profile
    blocks: list[tuple[int | None, str, list[Any]]] = [(n, " / ", raw) for n, raw in enumerate(images)]
    for n, sep, raw in blocks + ([(None, " | ", typed)] if typed else []):
        rows = [r if isinstance(r, str) else r[0] for r in raw]
        confs = [1.0 if isinstance(r, str) else r[1] for r in raw]
        col: tuple[int, int, int | None, int | None] | None = None    # the last table header: its row, its number
        first: str | None = None                           # of cells, the length's cell, the item weight's cell
                                                           # counted from the end; `first`: the last row's head
        parts: set[str] = set()                            # weight labels that name a part in this block
        above: list[str] | None = None                     # the cells of the row read before
        shaft_until = -1                                   # rows of a shaft maker's table: no item length
        pcol: tuple[int, int, list[int]] | None = None   # a part-columns header: its row, cells, columns
        for i, row in _readable(rows):
            where = {"from": TYPED, "row": i, "quote": row[:200]} if n is None else \
                {"image": n, "row": i, "quote": row[:200]}
            sure = confs[i] >= NUMBER_CONF                 # a statement stands in for a default: a misread would too
            kgs = [_num(m.group(1)) * 1000 for m in _KG_RE.finditer(row)] if sure else []
            triple = _TRIPLE_RE.search(row) if sure else None
            head = row.split(sep, 1)[0]
            about = _about(rows, i, p) if p else None
            if p:
                kinds = len({w for w in p.kind_word.findall(row)}) if p.kind_word else 0
                # a whole composition on one row: from the driver (or a wood) to the putter ("드라이버 1개/페어웨이우드2개"
                # alone is a part of one split over rows: 13409110111)
                closed = bool(re.search(r"드라이[버브]|\bDR\b|우드", row) and re.search(r"퍼터|\bPT\b", row))
                if p.container_no.search(row):
                    facts["container_no"].append(where)
                elif p.container_yes.search(row):
                    facts["container_yes"].append(where)
                elif kinds >= 3 and p.container_word.search(p.accessory.sub("", row)):
                    facts["container_yes"].append(where)       # "아이언세트(6~S) / 퍼터(33\") / 골프백" (8822855547)
                elif kinds >= 3 and closed:
                    # a closed composition, no bag in it: "1드라이버+1우드+2유틸리티+7아이언+1퍼터(12pcs)"; weak,
                    # only when nothing else speaks of the bag (compose)
                    facts["container_closed"].append(where)
                if closed and (n_kinds := composition_count(row, p)):
                    facts["item_counts"].append({**where, "count": n_kinds, "composition": True})
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
            if p and about == "container":                  # the container's own table
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
            elif not about and kgs and _WEIGHT_HEAD.search(row) and not (p and p.part_label.search(head)):
                facts["product_weights"].append({**where, "g": max(kgs)})          # "무게 / 4.2kg", "중량: 2.3kg"
            if not about and triple and (_SIZE_WORD.search(row) or triple.group(4)):   # not an accessory's
                facts["product_sizes"].append({**where, "mm": _sides(triple)})     # "사이즈 60 x 55 x 90cm",
                                                                                    # "W53 X D38 X H62.5 cm"
            if p is None:
                continue
            # profile: the items' own weights and lengths
            cells = row.split(sep)
            weighs = [j for j, c in enumerate(cells)
                      if p.item_weight_label.search(c) and not p.part_label.search(c.replace("총", ""))]
            at = weighs[0] if weighs else len(cells)       # "클럽 중량(g) / 310 / 306": the cells after the label
            valued = [(g, c) for c in cells[at + 1:] or cells[at:] if (g := _grams(c, p))]
            if weighs and not valued:                      # "...L기준)총 중량 약 305g / 킥포인트": in its own cell
                label_at = p.item_weight_label.search(cells[at])
                if label_at and (g := _grams(cells[at][label_at.end():], p)):
                    valued = [(g, cells[at])]
            if weighs and not valued and above and len(above) >= 3 and abs(len(above) - len(cells)) <= 1:
                valued = [(g, c) for c in above if (g := _grams(c, p))]   # OCR put the values one row up
                valued = valued if len(valued) >= 3 else []               # (13581639583)
            valued = [(_ref_grams(c, p) or g, c) if p.ref_weight and p.ref_weight.search(c) else (g, c)
                      for g, c in valued]          # "#5 365g #7 376g": the #7's (9343324012)
            grams = [g for g, _ in valued]
            table = re.sub(r"\s", "", cells[at]) if weighs else ""
            facts["item_weights"] += [{**where, "g": g, "table": table,
                                       **({"ref": True} if p.ref_weight and p.ref_weight.search(c) else {})}
                                      for g, c in valued]
            # a row of the label with only weights under an item's: the label names a part here, on its other
            # rows too. "중량(g) / 198 / 202 / 207 / 233" (the woods' heads) over "중량(g) / 257 / 263 / ... / 297"
            # (the irons'): 22 head weights made the median club of a 13-club set 296 g (7583123963)
            if weighs and not grams and any(_num(m.group(1)) < p.item_g[0]
                                            for c in cells[at + 1:] for m in _BARE_RE.finditer(c)):
                parts.add(table)
            # lengths at any OCR confidence: a row's is its weakest cell ("DO", "|"), and the driver's short
            # row at the top of a table is the one that fell under the line, so an iron's clean row won (25 of
            # 120 sets); read at any confidence no set got a value above its driver (2026-11-10)
            noise = bool(p.length_noise and p.length_noise.search(row)) or i <= shaft_until
            found = [round(_num(m.group(1)) * INCH_MM) for m in _INCH_RE.finditer(row)
                     if _in(_num(m.group(1)), p.item_in)] if not noise else []   # "45.5인치", "44\"" on any row
            if not about and not noise and not _TRIPLE_RE.search(row):         # "(114.935cm)" under "R / 45.25"
                found += [round(_num(m.group(1)) * 10) for m in _LENGTH_CM.finditer(row)  # (12965275150)
                          if _in(_num(m.group(1)), p.item_cm)]
            label = next((j for j, c in enumerate(cells)
                          if (_LENGTH_CELL.search(c) or c.strip() == "이" and j and cells[j - 1].strip() == "길")
                          and not p.part_label.search(c)), None)       # "길 / 이 / 45.5": OCR split the label
            stated = []
            for cell in cells[label + 1:] if label is not None else ():        # "클럽길이(inch) / 45.5 / 43"
                mm = _lengths(cell, p)
                if not mm and _LABEL_CELL.search(cell):                        # the next label: "길이(inch) / 45 /
                    break                                                      # 토크(°) / 7.8" (13302492097)
                stated += mm
            found += stated
            heads = (label if label is not None and not stated else None,
                     weighs[-1] if weighs and not grams else None)       # cell 0 too: "길이(inch) / 로프트 / 라이각"
            if p.shaft_table and p.shaft_table.search(row):     # a shaft maker's table: "Flex / Weight / CPM /
                shaft_until = i + p.column_rows                  # Torque / Kick Point / inch" (10954221464)
            # "Head(g) / Shaft(g) / Grip(g)": a club is their sum (12391346892)
            at_parts = [next((j for j, c in enumerate(cells) if pat.search(c)), None) for pat in p.part_columns] \
                if p.part_columns and len(cells) >= 5 and not weighs else [None]
            if None not in at_parts:
                pcol = (i, len(cells), [j for j in at_parts if j is not None])
            elif pcol and i - pcol[0] <= p.column_rows and pcol[1] <= len(cells) <= pcol[1] + 1:   # (+ a balance)
                nums = [_BARE_G.search(cells[j]) for j in pcol[2]]
                if all(nums) and _in(total := sum(_num(m.group(1)) for m in nums if m), p.item_g):
                    facts["item_weights"].append({**where, "g": total, "table": pcol[0], "parts": True})
            if len(cells) >= 3 and heads != (None, None):       # a table's header, one club per row below:
                # "클럽넘 / 로프트 / 라이각 / 전체길이 / 스윙웨이트 / 플렉스 / 헤드중량 / 총중량" (5684497984). The
                # weight's cell is counted from the end: OCR drops cells in the middle, the total stays last
                col = None if p.part_table and p.part_table.search(row) else \
                    (i, len(cells), heads[0], heads[1] - len(cells) if heads[1] is not None else None)
                first = None
            elif col and i - col[0] <= p.column_rows and len(cells) >= 3 and label is None and not weighs:
                if col[2] is not None:
                    found += _column_lengths(cells, col[2], col[1], p)
                # "1W / 10.5 / 58 / 45.25 inch / D0 / R / 197g / 320g"; its SR and S rows are the same club
                if col[3] and len(cells) >= -col[3] and cells[0] != first and (g := _grams(cells[col[3]], p)):
                    facts["item_weights"].append({**where, "g": g, "table": col[0]})
                first = cells[0]
            lady = {"ladies": True} if p.ladies and p.ladies.search(row) else {}
            facts["item_lengths"] += [{**where, "mm": mm, **lady} for mm in dict.fromkeys(found)]
            above = cells
        facts["item_weights"] = [f for f in facts["item_weights"]
                                 if not (f.get("image") == n and f["table"] in parts)]
    return facts


def _ev(value: float, confidence: int, how: str, quotes: list[dict[str, Any]]) -> dict[str, Any]:
    typed = {"from": TYPED} if quotes and quotes[0].get("from") else {}      # the quote is typed text, not OCR
    return {"value": {"min": round(value), "max": round(value)}, "source": SOURCE, "confidence": confidence,
            "how": how, "quote": quotes[0]["quote"] if quotes else None, **typed}


def longest_item(facts: dict[str, Any], profile: Profile, ladies: bool = False) -> dict[str, Any] | None:
    """The longest item of the set: the largest length stated, when it is in the band of the longest (the
    driver's). Below it the driver's row was not read: nothing, never a shorter club (a 34 in putter stood as the
    longest club of 12863003091). Above long_sure_mm a length needs two rows that state it (one noisy OCR row
    said 47 in for 41, 2026-11-11). `ladies`: a women's set takes the longest of the women's / L / A rows when
    the page has one in the band (XXIO 14: R 45.5 in, L 44.5 in)."""
    lengths = [f for f in facts["item_lengths"] if _in(f["mm"], profile.longest_mm)]
    if profile.long_sure_mm:
        sure = [f for f in lengths if f["mm"] <= profile.long_sure_mm
                or sum(abs(g["mm"] - f["mm"]) <= 3 for g in lengths) >= 2]
        if len(sure) < len(lengths) and max((f["mm"] for f in sure), default=0) < profile.long_sure_mm - 50:
            return None                             # the long row dropped, what is left is a shorter club
        lengths = sure                              # (11578482349: "48.25 / 43.78", the 3-wood): the baseline
    longest = max(lengths, key=lambda f: f["mm"], default=None)
    lady = max((f for f in lengths if f.get("ladies")), key=lambda f: f["mm"], default=None)
    if ladies and longest and lady and longest["mm"] - lady["mm"] <= 30:
        return lady                                 # the same driver by flex; not a wood's L row (13022225490)
    return longest


def composition_count(text: str, profile: Profile) -> int | None:
    """The items a composition line lists, kind by kind (2026-11-11): "드라이버 1개/페어웨이우드2개/유틸리티 1개/
    아이언8개/퍼터 1개" 13, "드라이버, 7아이언세트, 유틸리티, 퍼터" 10, "1> 드라이버 ... 4> 아이언 6,7,8,9,P,S 5> 퍼터"
    10, "1드라이버+1우드+2유틸리티+7아이언+1퍼터(12pcs)" 12; a stated total ("총 11개") is the count. A kind counts
    its number ("N개", "N아이언", "2유틸리티", "우드2"), a list of club numbers (6,7,8,9,P,S), else one; covers are
    no clubs. None: fewer than two kinds, no number at all, a kind named twice with two numbers ("7아이언/8아이언":
    the variants' choices), or a total outside the profile's count band."""
    if not profile.kind_word:
        return None
    total = re.search(r"총\s*(\d{1,2})\s*(?:개|pcs|PCS|피스)", text)
    if total and _in(int(total.group(1)), profile.count):
        return int(total.group(1))
    kinds: dict[str, int] = {}
    said = False
    for part in re.split(r"[,+/·&|]|\s\d\s*>|^\d\s*>|및", text):
        word = profile.kind_word.search(part)
        if not word or re.search(r"커버|cover", part, re.I):
            continue
        kind = {"페어웨이": "우드", "하이브리드": "유틸"}.get(word.group(), word.group())
        listed = re.search(r"(?<![\w.])(?:\d{1,2}|[PAGSW])(?:\s*[,.]\s*(?:\d{1,2}|[PAGSW]|PW|AW|SW)){3,}", text) \
            if kind == "아이언" else None
        n = re.search(r"(?<![A-Za-z0-9.])(\d{1,2})\s*개|(?<![\w.#\-])(\d{1,2})(?=" + word.group() + r")|"
                      + word.group() + r"\s*[x*×]?\s*(\d)(?![\d번도°.])|아이언\s*(\d{1,2})\s*(?:개|종|pcs)", part, re.I)
        if n and kind == "우드" and n.group(2) and int(n.group(2)) > 2:
            count, said = 1, True                   # "3페어웨이", "5우드": the #3 / #5 wood (11691723070)
        elif n:
            count, said = int(next(g for g in n.groups() if g)), True
        elif listed:
            count, said = len(re.split(r"\s*[,.]\s*", listed.group())), True
        else:
            count = 1
        if kind in kinds and kinds[kind] != count:
            return None                             # "8아이언세트, ... 7아이언세트": the variants' choices, no count
        kinds[kind] = count                         # (8514409092's 풀세트구성)
    count = sum(kinds.values())
    return count if len(kinds) >= 2 and said and _in(count, profile.count) else None


def image_count(facts: dict[str, Any]) -> int | None:
    """The item count the images state most often ("11PCS", "총 10개"), the largest of equals."""
    counts = [f["count"] for f in facts["item_counts"]]
    return max(set(counts), key=lambda c: (counts.count(c), c)) if counts else None


def container_in(text: str, profile: Profile | None) -> bool | None:
    """A variant's or a title's words about the container: True (캐디백 포함, +캐디백), False (백 미포함, 별도,
    백세트제외), None."""
    if profile is None:
        return None
    text = text or ""
    if profile.container_no.search(text):
        return False
    if profile.container_word.search(text) or profile.container_yes.search(text):
        return True
    return None


def container_listed(spec_rows: list[dict[str, Any]], supplements: list[dict[str, Any]],
                     profile: Profile | None) -> bool | None:
    """The listing's own answer when its words give none: the profile's 상품정보 row ("골프백포함여부": "미포함"
    False, "캐디백" True), else a container sold as a paid add-on: the set then has none ("젝시오 골프백 추가 구매 /
    바퀴형 - 핑크" 350,000, 12965275150; not an accessory: "RB LADY 여성용 보스턴백", "4. 골프백 / 럭셔리 신발가방",
    nor a thing for the container, the profile's container_trim: "캐디백 항공커버", "캐디백 네임택")."""
    if profile is None:
        return None
    for r in spec_rows:
        if profile.container_spec and r.get("label") == profile.container_spec and (r.get("value") or "").strip():
            return r["value"].strip() not in profile.container_spec_no
    for s in supplements:
        text = f"{s.get('group')} {s.get('name')}"
        if (s.get("price") or 0) > 0 and profile.container_word.search(text) and not profile.accessory.search(text) \
                and not (profile.container_trim and profile.container_trim.search(text)):
            return False
    return None


def guess(facts: dict[str, Any], profile: Profile | None = None) -> dict[str, dict[str, Any]]:
    """What the seller states of the five fields themselves (a field nothing states is left out): a packed
    weight, a box (its three sides are one statement), a set's or a product's weight. Confidence 5: typed, with
    its kind ("패키지 무게 : 10.8kg", 13389271367); 4: read from an image ("-패키지무게:10.8kg", 13495098284), or
    the kind left open (a set's weight: with the box or not). Read both ways, the typed line is the one kept.
    In a set of parts (a profile) a plain 무게 row may be one part's: not the product's."""
    out: dict[str, dict[str, Any]] = {}
    # the same line read in an image and in the typed text ("패키지 무게 : 10.8kg": 13495098284's image row,
    # 13389271367's typed line): the typed one, 5; max() by the value alone kept the image's, read first
    if facts["packed_weights"]:
        best = max(facts["packed_weights"], key=lambda f: (f["g"], "from" in f))
        out["package_weight_g"] = _ev(best["g"], 5 if "from" in best else 4, "stated packed weight", [best])
    if facts["packed_boxes"]:
        best = max(facts["packed_boxes"], key=lambda f: (f["mm"][0], "from" in f))
        for name, side in zip(SIDES, best["mm"]):
            out[name] = _ev(side, 5 if "from" in best else 4, "stated box size", [best])
    weights, how = (facts["set_weights"], "stated set weight") if facts["set_weights"] else \
        ([] if profile else facts["product_weights"], "stated weight")           # "무게 / 4.2kg": the core only
    if weights:
        best = max(weights, key=lambda f: (f["g"], "from" in f))
        out["product_weight_g"] = _ev(best["g"], 4, how, [best])
    return out


def _part(name: str, value: float, source: str, fact: dict[str, Any] | None = None, **more: Any) -> dict[str, Any]:
    """One part of a composed field: its value, where it came from (`from`: "stated", how the items were
    totalled, BASELINE, the field it is) and the row it was read in."""
    return {"part": name, "value": round(value), "from": source, **({"quote": fact["quote"]} if fact else {}), **more}


def _composed(how: str, confidence: int, baselines: dict[str, Any], parts: list[dict[str, Any]]) -> dict[str, Any]:
    """A composed field: the sum of its parts. `baseline`: who approved the operator's amounts in it, and when."""
    total = sum(x["value"] for x in parts)
    by = {"baseline": {k: baselines[k] for k in ("approved_by", "approved_at")}} \
        if any(BASELINE in x["from"] for x in parts) else {}
    return {"value": {"min": total, "max": total}, "source": COMPOSED, "confidence": confidence, "how": how,
            "parts": parts, **by}


def compose(facts: dict[str, Any], item_count: int | None, container: bool | None, profile: Profile,
            baselines: dict[str, Any], ladies: bool = False) -> dict[str, dict[str, Any]]:
    """The fields of a set composed from its parts, for where the seller states none (the owner, 2026-11-10: the
    flat category default is the last resort). A part comes from the product's own data when it is there, from
    the operator's `baselines` (the block of the category's row in category_measures.json) when it is not:

      product_weight_g    the items (_items_total) + the container: nothing when the set has none, its stated
                          weight, else the baseline's
      package_length_mm   the longest item read (longest_item), else the baseline's, + the baseline margin
      package_width_mm,   the baseline box sides of a set without the container / with it
      package_height_mm
      (package_weight_g   the product's weight as the field ends up + the baseline carton: merge_fields, _boxed)

    Unknown, so left to the default: the weight when the item count or the container's state cannot be told,
    the two sides when the container's state cannot. item_count and container are the listing's (the title, an
    option value, a 상품정보 row, a paid add-on); None: the images' count; the typed text's sentences on the
    container, then the images' (a no wins over a yes). The count is the items' own table's when one table is
    the whole set and the listing counts more (pieces) or nothing (_items_total; `count_from`: "table", and
    `count_listed`: what the listing said). Confidence 3: worked out wholly from the seller's own figures, only
    the margin the operator's (the items' exact sum, the container absent or its weight stated, the count the
    listing's and the container's state not from the images; the length from the longest item read). 2: a
    baseline or a weak part is in it (the count x the median, the images' count or sentence, a count only the
    table gives)."""
    p, b, one = profile, baselines, profile.item[:-1]
    out: dict[str, dict[str, Any]] = {}
    said = "listing"
    if container is None:
        for typed in (True, False):                   # the typed text's sentences, then the images'
            no, yes = ([f for f in facts[k] if ("from" in f) == typed] for k in ("container_no", "container_yes"))
            if no or yes:
                container, said = not no, TYPED if typed else SOURCE     # "본 풀세트는 골프백 미포함 제품입니다"
                break                                                    # wins over a yes
    flags: list[str] = []
    if container is None and facts.get("container_closed"):   # a closed composition with no bag in it (weak)
        container, said = False, TYPED if any("from" in f for f in facts["container_closed"]) else SOURCE
    if container is None and p.container_assumed and (item_count or image_count(facts)
                                                      or _items_total(facts["item_weights"], None, p, b["item_g"])):
        container, said, flags = True, BASELINE, ["container_assumed"]    # the clubs known, the bag not: the heavy
                                                                          # side, flagged (the owner, 2026-11-11)
    longest = longest_item(facts, p, ladies)
    out["package_length_mm"] = _composed(f"longest {one} + margin", 3 if longest else 2, b, [
        _part(f"longest {one}", longest["mm"], "stated", longest) if longest else
        _part(f"longest {one}", b["longest_item_mm"], BASELINE), _part("margin", b["length_margin_mm"], BASELINE)])
    if container is None:
        return out
    sides, state = (b["sides_with_container_mm"], f"with {p.container}") if container else \
        (b["sides_mm"], f"no {p.container}")
    for name, side in zip(SIDES[1:], sides):
        out[name] = _composed(f"box side, {state}", 2, b, [_part("box side", side, BASELINE, said_by=said)])
        if flags:
            out[name]["flags"] = flags
    count = item_count or image_count(facts)
    total = _items_total(facts["item_weights"], count, p, b["item_g"])
    if total:
        items, how, rows, n = total                   # n: the count used, the table's own when it is the whole set
        box = max(facts["container_weights"], key=lambda f: f["g"], default=None) if container else None
        counted = {"count_from": "table", **({"count_listed": item_count} if item_count else {})} if n != count else \
            {"count_from": "listing" if item_count else SOURCE}
        parts = [_part(p.item, items, how, rows[0] if rows else None, **counted),
                 _part(p.container, box["g"] if box else b["container_g"] if container else 0,
                       "stated" if box else BASELINE if container else "not in the set", box, said_by=said)]
        sure = how.startswith("sum of") and (box or not container) and item_count == n and said != SOURCE
        out["product_weight_g"] = _composed(f"{p.item} + {p.container}" if container else f"{p.item}, {state}",
                                            3 if sure and not flags else 2, b, parts)
        if flags:
            out["product_weight_g"]["flags"] = flags
    return out


def _items_total(weights: list[dict[str, Any]], count: int | None, profile: Profile,
                 baseline_g: float) -> tuple[float, str, list[dict[str, Any]], int] | None:
    """The items' total weight -> (g, how, its rows, the count used); None: no count, the listing's or a table's.
    `count`: the listing's, else the images'. The first of

      1  one table that gives exactly one weight per item of the set, as many values as the count: their sum
         ("총중량(g) / 308 / 326 / 360 / 376 / 382 / 388 / 394 / 401 / 412 / 545" of a 10-club set: 3892 g, where
         10 x the median of the page's 20 values gave 3975; 11659201020). A table is one row, the rows of one
         image (or of the typed text) under one label ("클럽무게(g) / 290", "... / 315", "... / 330 / 341", ...:
         13719960843; not a driver's, an iron set's and a putter's tables of a combination set, each under its
         maker's label: 13229172406), or the rows under one header
      2  the seller's own table before the listing's "pieces": a full table, when the count is up to pieces_over
         (3) more than its length, or when nothing states a count: its sum, and its length is the count
         ("총클럽개수 12개" counts the bag and two head covers: the nine rows "Driver / ... / 336" to "Putter / ... /
         532" are the clubs, 3955 g where 12 x the median gave 5340, 8053135821; "11피스" with the bag, the ten
         typed weights 3634 g, 13657325637; no count stated and twelve clubs under one header, 7674852369).
         Full: one row or the rows under one header (not rows gathered under a label: the two rows of
         13446843026 hold 11 of its 12 clubs), at least full_items (9) weights, the heaviest full_last_g
         (475 g) and up: the ladder ends at its last item, the putter. With no count, full tables of two
         lengths are two sets: no count
      3  the count x the median item weight, only when the weights read cover at least half of the items: as
         many items as half the count (weights within same_item, 2 %, of each other are one item's: a club by
         two flexes is not two clubs, 10816781893), the heaviest set_spread x the lightest (a driver by nine
         shafts, two woods and a utility, 292-340 g, said 3090 g for a 10-club set of about 3.8 kg: 8029218821;
         4 weights of 9 clubs, the driver's and the wood's: 13728931694)
      4  the count x the operator's baseline item weight

    Of several tables in 1 or 2 (the R and the S set) the lightest."""
    tables: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for f in weights:
        block = f.get("image", TYPED)
        for key in ((block, "row", f["row"]), (block, f["table"])):
            tables.setdefault(key, []).append(f)
    one = profile.item[:-1]
    spread = profile.short_spread if count and count <= profile.short_set else profile.set_spread
    sets = {key: t for key, t in tables.items()
            if max(f["g"] for f in t) >= spread * min(f["g"] for f in t)}
    sums = [t for t in sets.values() if len(t) == count]
    if not sums and profile.full_items:
        sums = [t for key, t in sets.items() if (len(key) == 3 or isinstance(key[1], int))
                and profile.full_items <= len(t) <= profile.count[1] and max(f["g"] for f in t) >= profile.full_last_g
                and (count is None or len(t) < count <= len(t) + profile.pieces_over)]
        if count is None and len({len(t) for t in sums}) > 1:
            sums = []
    if sums:
        rows = min(sums, key=lambda t: sum(f["g"] for f in t))
        return sum(f["g"] for f in rows), f"sum of {len(rows)} {one} weights", rows, len(rows)
    if count is None:
        return None

    def distinct(t: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for f in sorted(t, key=lambda f: f["g"]):  # "약252 / 약255": one club by two flexes
            if not out or f["g"] > out[-1]["g"] * profile.same_item:
                out.append(f)
        return out

    # 2026-11-11 (300 sets), each a table of the page that is not the whole set:
    # a reference item's weight for the items not stated: "무게(g) | 297 | 320 | 353 | 410(#7) | 528" of 11 clubs:
    # 297 + 320 + 353 + 528 + 7 x 410 (12049132531)
    # the other clubs are the page's other weights, one per club (10816332813: the driver 252 and the utility 292
    # in their own images, "#7약320g" for the seven irons)
    ref = next((f for f in weights if f.get("ref")), None)
    if ref:                                         # the others of its own image (or of the typed text): a page's
        block = ref.get("image", TYPED)             # other images show the brand's other lineups (9343324012)
        others = distinct([f for f in weights if not f.get("ref") and f.get("image", TYPED) == block
                           and not ref["g"] / profile.same_item <= f["g"] <= ref["g"] * profile.same_item])
        if len(others) < count:
            n = count - len(others)
            return (sum(f["g"] for f in others) + ref["g"] * n,
                    f"{len(others)} {one} weights + reference {one} weight x {n}", others + [ref], count)
    # per-row tables that together are the set: the driver's card, the woods', the irons' (one row each)
    by_row = [distinct(t) for key, t in tables.items() if len(key) == 3]
    if len(by_row) >= 2 and sum(len(t) for t in by_row) == count:
        rows = [f for t in by_row for f in t]
        if max(f["g"] for f in rows) >= spread * min(f["g"] for f in rows):
            return sum(f["g"] for f in rows), f"sum of {count} {one} weights", rows, count
    # one table of half the set or more: its items + its own median for the rest (count x the page's median mixed
    # the other lineups in; the baseline club is lighter than the irons and the putter missing: 12733446652)
    # (its values as read: a ladder's steps are 2 %, so no value is merged here)
    part = max((t for t in tables.values() if len(t) < count), key=len, default=[])
    if count / 2 <= len(part) < count and max(f["g"] for f in part) >= spread * min(f["g"] for f in part):
        rest = statistics.median(f["g"] for f in part)
        return (sum(f["g"] for f in part) + (count - len(part)) * rest,
                f"{len(part)} {one} weights + {count - len(part)} x their median", part, count)
    grams, items, last = [f["g"] for f in weights], 0, 0.0
    for g in sorted(grams):                         # "약252 / 약255": one club by two flexes
        if g > last * profile.same_item:
            items, last = items + 1, g
    if items * 2 >= count and max(grams) >= spread * min(grams):
        return statistics.median(grams) * count, f"{count} {profile.item} x median {one} weight", weights, count
    return count * baseline_g, f"{count} {profile.item} x {BASELINE} {one} weight", [], count


def package_for(fields: dict[str, Any], facts: dict[str, Any], item_count: int | None, container: bool | None,
                plausible: dict[str, dict[str, float]] | None = None, profile: Profile | None = None,
                baselines: dict[str, Any] | None = None, ladies: bool = False) -> tuple[dict[str, Any], list[str]]:
    """One variant's five fields with the description's statements and the composition merged in -> (fields,
    names no longer today's). plausible, baselines: the blocks of the category's row in the operator's table,
    when it has them; no composition without the block or without a profile."""
    made = compose(facts, item_count, container, profile, baselines, ladies) if profile and baselines else {}
    return merge_fields(fields, guess(facts, profile), plausible, profile, made, baselines)


def bands(plausible: dict[str, dict[str, float]] | None, profile: Profile | None) -> dict[str, tuple[float, float]]:
    """The band a value must fall in, per field: the operator's (category_measures.json `plausible`), else the
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
    table row, a quote or the parts: the winner carries its own evidence)."""
    brief = {"value": today_value(field), "source": field.get("source"), "confidence": field.get("confidence"),
             "how": field.get("how"), "flags": field.get("flags"), "from": field.get("from")}
    return {k: v for k, v in brief.items() if v not in (None, [])}


def _boxed(product: dict[str, Any], baselines: dict[str, Any]) -> dict[str, Any]:
    """The package's weight: the product's weight as its field holds it (the seller's, a statement of the
    description, the composition) + the baseline carton. 3 when that weight is the seller's own figure (3 and
    up), else 2. 6630856593: "중량: 약11.5kg" with a default package of 7000 g, below its contents."""
    return _composed("product weight + carton", 3 if product.get("confidence", 0) >= 3 else 2, baselines,
                     [_part("product", product["value"]["max"], FIELDS[0]),
                      _part("carton", baselines["carton_g"], BASELINE)])


def merge_fields(fields: dict[str, Any], stated: dict[str, dict[str, Any]],
                 plausible: dict[str, dict[str, float]] | None = None, profile: Profile | None = None,
                 composed: dict[str, dict[str, Any]] | None = None,
                 baselines: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    """-> (fields, names no longer today's). Per field, the first of (the owner, 2026-11-10):

      the seller's value of the server path (source_stated)   kept, whatever the description says
      a statement of the field in the description (guess)      in place of the category default, whatever its size
      the composition (compose; the package's weight: _boxed)  in place of the default
      the flat category default                                the last resort

    The value not kept travels as `compared` (under a statement or a composition: the default it replaced).
    A box is one statement, its three sides taken whole or not at all (`box_not_whole`: of a gift's "패키지
    사이즈 30 x 20 x 10cm" the 300 mm length is refused, and 200 x 100 must not stay as the sides of a 1250 mm
    package). Never taken (`rejected`; `refused` under the composition that stood in): a statement outside the
    field's band (bands()), any value above the band or more than MAX_RATIO x today's. A composition is never
    refused for being under the band: a driver, a wood and a hybrid are 3 x 340 g, under any set's weight, and
    the count and the bag's state are known (13302492097 stayed at the flat 5700 / 7000 g). A stated packed
    weight stands also under the product's weight: over a composition it is the seller's word against an
    estimate; under the seller's own product weight (4-5) it is taken with `flags: ["below_contents"]` (a box
    weighs at least what is in it: the operator decides)."""
    out, taken = dict(fields), []
    limits = bands(plausible, profile)

    def absurd(name: str, g: dict[str, Any], stated: bool = True) -> str | None:
        v, base = g["value"]["max"], today_value(fields[name])
        if v > limits[name][1] or stated and v < limits[name][0]:
            return "implausible_for_category"
        return "far_above_today" if base and v > base * MAX_RATIO else None

    no = {name: absurd(name, g) for name, g in stated.items() if name in fields}
    if any(no.get(name) or "value" in fields[name] for name in SIDES if name in no):
        no.update({name: no.get(name) or "box_not_whole" for name in SIDES})
    for name in FIELDS:
        now, said, made = fields.get(name), stated.get(name), (composed or {}).get(name)
        if not now:
            continue
        product = out.get(FIELDS[0], {})                # as merged: the seller's, a statement, the composition
        if name == FIELDS[1] and "value" in product:
            made = _boxed(product, baselines) if baselines else made
            if said and said["value"]["max"] < product["value"]["max"] and product.get("confidence", 0) >= 4:
                said = {**said, "flags": ["below_contents"]}      # two statements of the seller: both kept
        if "value" in now:                              # the seller's own: nothing replaces it
            if other := said or made:
                out[name] = {**now, "compared": _brief(other)}
            continue
        refused = {**_brief(said), "rejected": no[name]} if said and no.get(name) else None
        why = absurd(name, made, False) if made else None
        if said and not refused:
            out[name] = {**said, "compared": _brief(now)}
        elif made and not why:
            out[name] = {**made, "compared": _brief(now), **({"refused": refused} if refused else {})}
        else:
            lost = refused or made and {**_brief(made), "rejected": why}
            if lost:
                out[name] = {**now, "compared": lost}
            continue
        taken.append(name)
    return out, taken
