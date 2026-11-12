# Seller data: what product pages say, and how collection and the transform read it

Patterns seen on 139 golf sets of category 50002788 checked against their product pages (2026-11-05..07: 40 + 19 +
40 new products, the first 40 checked twice). Each line: what the page or the seller writes, an example product id,
where it is handled. Rules: [server/docs/ENDPOINTS.md](../server/docs/ENDPOINTS.md) (collection),
[README.md](README.md) "Transform" (the transform). Regression fixtures of these products:
`server/naver_shopping/fixtures/pages/` and `fixtures/collected|prepared/` (server DEVELOPMENT_RULES R-TEST-5).

## Collection (server)

Finding the page
- The product page is opened only from a search page (name -> card photo). A long name can miss its own card on the
  first page; its first 5 words find it (13425122164) -> `ext_product.search_queries`.
- A click on the card's photo opens nothing about 1 time in 20; the read tries again.
- Ad cards (`is_ad`) are products like the others and are kept by the listing screen (the owner, 2026-11-06);
  rental, another category, already in the shop and deferred stay screened -> `listing_filter.Screen`.
- Naver sometimes answers a page with its own `maintenance/internal-error.html` (about 1 read in 25, for minutes,
  on any product); it passes within ~2-15 min. Two reads of one product right after each other made it likelier.
  A run waits 2 min and tries again, then skips the product for later (research runners).

Gallery -> `/products/details` `images`
- One photo is common (21 of 40 sets in the 2026-11-07 run): the page itself has one (its productImages /
  galleryImages; no 360 view, no option images). The seller puts a collage there (clubs, bag, gifts) and the rest in
  the description images. The other shop-phinf images in the page are "similar products" (`similar.pd`), never the
  gallery -> `parsers.parse_simple_product` comment.

The purchase box (delivery promise) -> `pdp.delivery_promise`, `parsers.parse_page_delivery`
- Three wordings: "오늘출발 16:00 마감" (old), "오늘출발" + "14:00 까지 결제 시 오늘 바로 발송" + "11.11.(수) 도착 확률
  98%", and 네이버 배송 "11.11.(수) 도착" (no probability).
- "오늘출발 휴무" on a weekend / after KST midnight: no dispatch today, the answer's thisDayDispatchBasisTime is not a
  cutoff then (`today_off`).
- The same-day dispatch is per variant (todayDispatch): one of two may ship today (8958060680).
- "평균 N일 이내 도착 확률 P%" is the answer's sellerDeliveryLeadTimes (cumulative %), not productAverageDeliveryLeadTime:
  N is the first day whose cumulative share reaches about 72-80 % (80 or 89 on day 1 gives N=1, 53-71 gives N=2;
  matched on ~130 reads); the line can be missing from one read and present a minute later.
- The regional fee text (differentialFeeByArea) sometimes holds the return fee typed there ("18000" = 반품 편도
  18000원, 6153061020) -> dropped in the transform only when it equals the notice's return fee.

Description -> `parsers.parse_contents`, `pdp.description_text`
- Naver's own text leaves out SmartEditor cards: se-oglink (other products, TalkTalk), se-placesMap (store map and
  address), se-material (shopping cards); we skip them in text and images too.
- Tables (se-table) are per-club specs of 4-11 columns: one line per row, cells joined by " | " (spanned cells once).
- An editor-NONE body comes as Naver's snapshot tiles (p-<id>-s-N-A-<n>.jpg): banners are baked in, not cut.
- YouTube oembeds in the body are not collected yet.

Weight and size -> `measures.py`, `package_measures.py`
- Most sets give weight / size only in images (no OCR): the category default (confidence 1).
- Notice 중량 may list one weight per club count ("약11.5kg / 4.7kg", 6630856593) -> bound by club count.
- Club spec tables (td-only, column headers) and "총중량" under a club heading are one club's, never the set's.
- "7번 기준 36인치, 332g" is one reference club; "6아이언" is a set of six irons.
- A plain 중량 row of a set is the set as sold, but with or without the box is not said: confidence 4 (2 on the
  1-3 scale used until 2026-11-10).

## Transform (scripts)

Options and variants -> `transform.options_and_variants`
- Sellers number values ("선택1 9도SR", "선택3)", "택1 ..."), tag them ("[당일출고] ..."), decorate axis names
  ("(선택)샤프트/드라이버/아이언"): shown without, the SKU keeps the raw tuple; values equal once unnumbered stay
  numbered (option_values_duplicate, 9496523995).
- Axes named 선택 / 옵션 / 색상 whose values are not colours ("세트 R / 세트 S", 13462927626): option_name_placeholder.
- A SIMPLE option of one value can be the set's only option ("드라이버+우드+하이브리드/SR", 9168175809): a fact.
- Configurators of 128-497 combinations at one price (an XXIO 14 set: 6 x 9 x 9): offered up to the shop's cap,
  covering every pair of values first, shared over the first axis (variants_capped).
- A "write a delivery message" row and a review-discount axis are not versions of the product.

Spec rows vs variants -> `spec_variants.check_specs`
- 상품정보 rows are product-wide but often describe one version: shaft material (스틸 / 카본), club count (12종 /
  9P / "4스틸"), the composition rows (아이언개수, 아이언 구성, 풀세트구성), model year (출시 2026년형 vs XR26), driver
  loft (row 10.5도 while 9도 heads are sold).
- A count after a part word is that part's ("아이언 선택 (8개)" = 8 irons, not an 8-club set; 12999501692).
- Sellers contradict themselves: 총클럽개수 3개 on a 12pc set (13780241403), 아이언개수 11개 = 총클럽개수 (13026991307),
  아이언 구성 missing #6 while 아이언개수 says 7 -> specs_contradict when the title decides, else kept.
- A loft half a degree off the sold heads (row 9.5도, values 9도): kept, specs_loft_near_miss.
- Titles write a whole value with other spacing ("NS PRO950GH NEO R" = "NS PRO950GH NEO(R)").

Small sets -> few_pieces
- "[3PCS]", "(3종)", "(2종)", "하프세트(5P)", or 총클럽개수 of 5 or fewer; the title's count wins over a wrong row
  ("12pc" with 총클럽개수 3개); not "10+1pcs"; not when a variant is a full set (4종 / 12종 values).

Gender -> `attributes.py` (read by `placement.py`; 2026-11-08 on the 143 trial sets)
- No 성별 row on some sets (19 of 143): the title says it ("젝시오13 여성 풀세트").
- The variants say it per variant ("여성용-그라파이트"); a set listing both genders is `mixed` (13425122164: a men's
  listing with a women's variant).
- A seller marks only the women's variants "(여성용)" beside the plain model, with 성별 남녀공용: the unmarked ones
  are men's (8514409092 GVTOUR: 46 men's, 23 women's).
- A row and a title naming opposite genders: `conflict`; nothing says it: `unknown`; both held, never guessed from a
  flex, a colour or a model.

Brand -> `transform.prepare`, `brand_fallback.py` (2026-11-08)
- A seller who links no Naver brand leaves no 브랜드 row and no brandName anywhere Naver serves (6 of 143 sets): the
  manufacturer, else a brand of the shop in the title (4 of 6), 원산지's importer, the images' text (BEN SAYERS
  repeated, 13425122164), else 노브랜드 (13464713764).
- 제조사 "M0000000" is Naver's code for no manufacturer: not a spec row, not a brand (13464713764).
- 브랜드 "기타" ("other") names no brand (10697131625, 2026-11-11): neither the brand nor the manufacturer; the
  fallback goes on, the tenant's name at the end (the owner: Fairward Golf). The model once translated it as
  TaylorMade, and the dictionary then gave that brand to three no-name sets.
- The images' text holds words that contain a short brand (쇼핑 "shopping" and 치핑 "chipping" hold 핑, Ping) and the
  retailer's web address (www.houma.co.kr): a Korean brand counts only where a word starts, an address not at all
  (13445783517, 13625754692, 2026-11-11).

Origin, gifts, add-ons
- 원산지 brackets name an importer ("일본(IRUGI SHOJI)", "중국산((주)위스트OEM)") -> cut; or the parts' countries
  ("미국산(핑(미국) 미즈노(일본) 웨지퍼터(중국))") -> kept.
- A hidden 사은품 row can name a thing in the box ("오리지널커버 증정") -> gift_hidden.
- Add-on names carry the seller's codes and numbering ("[G192]01_미즈노 클럽 렌치", "1-1.남성 장갑") -> left out.

Description cleanup -> `description_clean.py`, `shared_images.py`
- A SmartEditor line is not a sentence: sellers wrap after connectives (-로, -만큼, -시면, -거나, -는 경우);
  rules match the joined sentence.
- Boilerplate: greetings, signatures, phones, TalkTalk / Kakao, Naver Pay pickup, return / delivery / customs blocks,
  KRW price promos (our prices are USD), cross-sell pairs ("화이트 컬러 모델은 ..." + "아래 링크에서 구매"), the
  store's claims and anti-OEM pitch; product claims that look alike stay ("정품 헤드커버 포함", "정식통관 ... 품질AS
  보증라벨").
- Banner images: by name (배송, 공지, 하단배너, 톡톡, 오늘출발, 추석, Hangul typed on a QWERTY layout "gkeksqpsj"),
  by link (TalkTalk, Band, blog, Instagram), by size (spacers, 1x1 tracking pixels), and run-level by repetition
  across one store's listings (numeric names, re-uploaded per batch of listings).
- A description that is only "o" is junk (13741767690).

## Description images (OCR, research 2026-11-07 on the 50 fixture products)

- The images are the description: their text is ~12x the page's text, and 31 of 50 sets have no page text at all.
- No image states a box size, a package weight or the whole set's weight. 74 % of the number + unit tokens sit in
  per-club spec tables: 클럽 중량(g) / 총중량(g) (a whole club: ~250-450 g), 헤드 / 샤프트 / 그립 중량 (parts),
  길이 in inches or cm (33-46"). `총중량` there is one club's, never the set's. A plain "중량(g)" may be the heads':
  7583123963's summary tables give "중량(g) / 198 / 202 / 207 / 233" (woods) and "중량(g) / 257 / ... / 297" (irons)
  beside per-club 총중량 rows of 280-515 g (2026-11-10: a row of only under-club weights marks the label).
- Kilograms are a bag's own weight (stand bag 4.1 kg, caddie bags 3.5 / 4.5 kg, "총무게:(캐디백+보스턴백) 약4.95kg"),
  a shop rule ("20kg 초과 화물"), customs ("5kg 이하 통관") or a buyer's body weight in a review screenshot.
- Size triples are bags ("캐디백-91cm(세로)*31cm(폭)*40cm(가로)", a boston bag L48xW24xH30) or a shop's cross-sell
  cards below "함께 구매" (a half bag 10x7x126 cm of another product). A bag's mouth is written in inches (8.5 / 9인치).
- "본 풀세트는 골프백 미포함 제품입니다" (5 sets) and "12종+캐디백" / "GOLF BAG" (2) say what the name does not.
- So description_measures.py composes the fields from the parts (the clubs' weights + the bag; the driver + a
  margin), each part from the page when it is there and from the operator's baseline when it is not (2026-11-10;
  until then: a guess from the parts, the larger of it and today's value).
- What the baselines rest on, the 120 sets (2026-11-10): the median club of the sellers' tables is 332 g; 11 sets
  state their bag's weight, 2.6-4.8 kg; 4 state a caddie bag's sides, 39-40 x 31 cm; one set (a Callaway Edge, on 3
  listings) states its box, 121 x 20 x 16 cm, around a 111 cm driver.
- On the 120 collected sets (2026-11-10): the 상품정보 row 골프백포함여부 is on 81 (미포함 47, 캐디백 24, 캐디백 +
  보스턴백 6, 스탠드백 4) and agrees with every other explicit word but one listing whose free variants are the
  no-bag ones (8514409092: the variant's words go first). A bag sold as a paid add-on means the set has none (6
  sets); an add-on Boston bag, shoe bag or pouch says nothing, and its table ("여성용 경량 보스턴" ... "사이즈 /
  L48×W24×H30CM") looks like the caddie bag's. 38 sets have typed text: the box and its weight ("패키지 크기 : L 20
  x W 16 x H 121 cm", "패키지 무게 : 10.8kg", one Callaway set on 3 listings), club tables with cells joined by
  " | ", the bag's lines ("캐디백" / "무게 : 약 3.8kg"; "47인치 대응" is the club length a bag takes). A bag's kg also
  comes as "약4.1 (kg)"; "약1.5kg경량화되어" is a comparison. "함께 구매" / "다른 상품" in a sentence is no cross-sell
  heading (20 sets have such a row, 5 are headings).
- The clubs on the same 120 (2026-11-10). 118 state the driver's length, 43.5-46.0 in (1105-1168 mm; ladies'
  43.5-45.25, men's 44.5-46.0); no other club is that long (a men's 3-wood 43-43.5 in, a ladies' 41-42.5). Tables
  come as a labelled row ("클럽길이(inch) / 45.5 / 43 / ...", 91 sets) or as a header with one club per row ("1W /
  10.5 / 58 / 45.25 inch / D0 / R / 197g / 320g", 19 sets, 21 for weights); cm and inches side by side
  ("112.395/44.25", "114.3cm(45인치)"); the driver's row is often the one OCR reads worst. A shaft maker's table
  (TIP / Butt 외경) gives the uncut shaft, 46 in. Per-club totals are on 95 sets, 252-549 g; one page may hold
  several sets' tables (R and S, last year's model) and, on a combination set, each maker's table with its
  choices (a driver by nine shafts). The club count: the title's "N개" / "NPCS" is right more often than the
  총클럽개수 row (5 disagree, the title right on 4); 총클럽개수 may count the bag and covers (8053135821: 12개, 9
  clubs), and so may the title ("11피스": ten clubs and the bag, 13657325637); "4피스 티타늄 페이스" / "4PCS단조" in
  an image is the head's make. A whole set's table runs from the driver to the putter: the putters stated are
  485-549 g, the heaviest wedge 462 g; a table that stops at the SW leaves the putter out (X HOT: ten weights
  of "총 11개 클럽", 8974646004). A club is often weighed by flex, the two values within 2 % ("약252 / 약255" L /
  A, 10816781893); the step between two irons is about as small (343 / 348 / 354).

## Not handled yet (known)
- Banners inside snapshot tiles (OCR reads them; their address, hours, services and stations / shops of the map
  are cut from the text since 2026-11-08, a map's restaurant names are not); per-buyer purchase limits; YouTube in descriptions;
  the notice's 제품구성 not carried; the return fee near the item price; spanned table cells (colspan) lose their column.
- S/R club weights and lofts given per flex in a description table, not bound to the S/R variants (6774818843,
  8958060680).
- An option value that is a service, not a product ("피팅상담요청", 10954221464) is a sellable variant.
- Left-handed (좌타 / 왼손) only in the title, no fact or tag (10954221464); a 모델명 naming another product type.
- 원산지 with an importer after a slash ("기타국가 / 테일러메이드코리아", 12973604141); 병행수입 (grey import) gets no note.
- A putter counted in the set also offered as an add-on (13741767690).
- Composition rows that fit no variant on a product with one variant group (7632306067); "+우드" sets losing their
  아이언 구성 binding (9902027106); a title year (2026) not flagged (12696567111).
- A chosen photo review whose photo failed to decode is published without it, no note (13413924099; iPhone HDR
  photos, an MPO with a gain map, decode since 2026-11-08); notes
  `reviews_incomplete` (a count but no rows) and `photo_small` were planned, not built.
- Banners not caught: a lister's shared `/profile/` header and footer (13728190518), names like 수서권_2026.png,
  golf_top.jpg.
- Store banners re-uploaded per product (another URL, the same bytes: 14 of 43 identical-file groups on the 50) are
  read again: reuse is by link and dHash runs within one product. A store-wide slice dHash (218 pairs across
  products, all within one store, 0 false) would skip them (2026-11-07).
- Images that contradict the spec rows or the name on the set's contents (13026991307: images 6 irons + 2 wedges,
  rows 8 irons; 13741767690: name 10 counting a separately sold wood, images 9; 13099257309: the name's 8 counts
  irons only, images 11): no note flags it (2026-11-07).
- Reviews: the summary's photo_count can be lower than the files a selection downloads, and selected_reviews took 6
  of 35 and 2 of 36 reviews on two ktksports sets (7202588289, 7632306067) under a cap of 20: not looked into
  (2026-11-07).

## Open questions (defaults taken, not yet confirmed by the owner)
- Settled 2026-11-11: delivery, duty and margin are inside the price of a shop with the rule (scripts/README.md,
  "The price").
- Shared store images: half of a store's listing groups, at the start or end of a description only; does a banner
  linking to the store's own page (PGM-배너.jpg) count as a link banner (today: yes)?
- A loft half a degree off: kept with a note (today) or bound to the matching variants? Keep dropped spec rows for
  audit (`specs_dropped`)? Shorten `for_ko`? A carbon row bound by elimination (9868413561)?
- A stated set weight above the category's high (11.5 kg): the product's weight (today) or with the box? Multiplied
  totals ("500g x 2개") taken as stated? 1 kg as the boundary between a part and a set? A club length a component?
- A description that is all boilerplate becomes null (8978750961): accept (today) or hold?
- Should the translator get a bare flex letter (R / S) as an option value?
