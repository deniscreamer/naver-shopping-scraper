# Reading a seller's size chart (`size_chart.py`)

Part of [SIZES.md](SIZES.md). The input is the description's text lines and the OCR rows of its images. An OCR row is
the cells of one visual line joined left to right with " / " (`description_ocr.rows`); no x positions are kept.
They are not needed: on 2026-11-19 all 36 tables of the knit pilot (30 products) were studied, and every one
splits right on " / " or "|". Every failure was in the text (units, header shapes, words), none in the geometry.
If geometry is ever wanted, the cells' x exists only inside `description_ocr.rows()`; keeping it means a new
sidecar format and reading the cached images again.

## How to use

| Symptom | Look at | Fix |
|---|---|---|
| a product's chart is missing or a field is empty | its lines: `shop_view.py show <shop> <ref> --raw prepared --path product.description_ko` and the sidecar `description_images/<pid>.json` (rows by image, `y`) | find its layout below; a new layout or word: a rule in `size_chart.py` with a test and a golden diff |
| a garment chest shows half or double | `product.sizes.chart.kinds.chest` | the kind words below; a note line ("단면 기준") is a hint |
| a number that is no measurement in the chart (a model's height, a price) | the line | a word in `NOT_CHART_RE`, or the field's plausible range |
| a row whose measures are not read but whose label pairs a letter with a women's size ("L(55-66) / 48 / 20 / 58", 12220300865) | the row stays out of the chart | nothing: its pairing still sizes the bare letter ([SIZES.md](SIZES.md) "The order" 3, 2026-11-20) |

## The layouts (the 2026-11-19 study: 28 of 30 products carry a chart, 36 tables)

| | Layout | Example | Products |
|---|---|---|---|
| P1 | by row, a header of measure names, the size first | `사이즈 \| 어깨너비 \| 가슴둘레 \| 총길이` / `85 (S) \| 39 \| 95 \| 54` | 7 (9 tables) |
| P2 | by row, a header without the size cell; cm and inches in a cell; the header in Korean then English | `총장 / 어깨너비 / 가슴둘레 / 소매기장` / `Total Length / ...` / `90 (S) / 55cm (21.7in) / ...` | 13722416544 |
| P3 | by column, the sizes across (with `사이즈` or without; a `Korea Size` or `US` row) | `사이즈 / M(90) / L(95)` / `가슴너비 / 46 / 48.5` | 7 |
| P3a | by column, one size | `호칭 / FREE(66-88)` / `가슴둘레 / 126` | 13823433220 |
| P4 | a label, then name+number pairs | `L 총장 61 어깨 35 가슴 44`, `S(90)-총장56/어깨37/가슴48` | 5 |
| P5 | one-size lines, no label (`/`, spaces, `- `, `cm/`, `(cm):`) | `총장59/어깨54/가슴56`, `어깨(cm): 40`, `가슴 / 46` | 7 (8 tables) |

Rules that hold the layouts apart:
- A cell's value: a number, cm optional, an inch value in brackets ignored ("55cm (21.7in)" is 55). Inches alone
  are never read as cm.
- A dropped cell never shifts a row: a row is read only when its cells count as the header's (or the columns').
- Two header lines straight after each other with as many cells are one header (Korean then English). A header of a
  different length replaces the last one.
- The corner cell of a header: 사이즈, size, 치수, 호칭, 구분, 단위(cm), the unit alone (CM, cm, (cm): "CM / 90 / 95 /
  100 / 105", 13021502381, 2026-11-20).
- One cell written twice with no space ("53/53": "85 (S) | 36 | 92 | 58 | 53/53", 11377634969) is one value when both
  halves are equal (2026-11-20); two different numbers stay two cells, and the row is skipped.
- A value that breaks its table's run (2026-11-20, an OCR misread: "어깨너비 / 35.5 / 57 / 38.5 / 40.5",
  13338110183) leaves that row, never shown: in a run of one measure over a table's sizes whose other values all rise
  (or all fall), a middle value of a run of 4 or more outside its two neighbours by more than their span (3 cm at
  least). An end value is never dropped (a bigger last step is real grading as often). Two such places: none. On
  2026-11-20 it dropped one value of the 328 runs in the shop and the pilot (`size_chart._breaks`).
- A line whose corner is a size word ("사이즈 / 90 / 95 / 100 / 105") is a column header, never a row under a header of
  measure names of as many cells (a diagram's labels "총길이 / 소매길이 / 총길이 / 총길이" right before it swallowed PING
  12361710158's chart, 2026-11-20).
- A one-size column header needs that corner, then one label with no comma ("사이즈 / 90, 95, 100" is a list, not a
  chart); its rows are measure rows or a pairs line ("사이즈 | FREE" then "총장59/어깨54/..."); it ends at the first
  two-cell row that is not its measure.
- A header of measure names nothing was read under (a diagram's labels: "어깨너비 / 가슴둘레") does not stop the
  one-size lines after it.
- One-size blocks of a product sold in types (an option that is no size and no colour, its values 2+ characters
  and no size labels): a heading starts its block (`ONE#<value>`). A heading: no digit, exactly one type's value,
  nothing else but brackets, 형 / 타입 and the garment's noun ("(앞면 로고형)", "니트집업가디건 (뒷면로고형)"; never
  "앞면로고 타입은 ... 보다", prose). The block before any heading keeps its place: named by the one type left, else
  unnamed. 10885610305 shows a block per type; without a type option the second block is a conflict, the first
  kept (`chart_conflicts`).
- A figure letter before a row ("b / 가슴둘레 / 86") is dropped.

## The measures (`MEASURE_SETS`, a profile's `measures`)

`tops`: chest (가슴, 가습 (OCR), 품 as a word, bust, chest), sleeve (소매, 소매 길이 / 기장, 팔길이, sleeve length),
length (총장, 총기장, 총길이, 기장, 상의길이, length), shoulder (어깨, shoulder). The first that matches a cell names it:
sleeve before length ("Sleeve Length"). Each has a plausible range in cm, flat and round; a row with a value out of
range is not read ("가슴 / 2").

Kinds: flat (단면, 너비, 넓이, 폭, width: a chest doubled on the storefront), round (둘레, 들레 (OCR), circ). The word
of the value kept is the kind: a second table that repeats a size never relabels the first's values (its values are
not kept either); two values of one field with different words make it `mixed`, each value then judged by its size.
A note ("상세치수는 단면기준", "둘레는 ... ×2") or a diagram label ("가슴단면") fills a kind the table left empty, only
when every value fits that kind's range (a "flat" note over a 92 cm chest is no flat chest); with none, a chest
under 75 cm is taken as flat. ("가슴/2" is not read: "/" splits the cells.)

Words with a space are one word in name+number lines ("소매 기장 58" is the sleeve, "총 기장 60" the length).

`bottoms` (2026-11-22, the skirts): waist (허리, not 허리밴딩; waist), hip (엉덩이, 힙, hip), length (총장, 기장, 치마 /
스커트 길이, length); waist and hip flat (단면) or round (둘레) as the chest; a flat / round note sets every field that has
both kinds.

Never a field (the tops): 소매통, 소매부리, 소매단너비, 화장 (centre back to cuff), A.H / 암홀, 목넓이, 목깊이,
밑단둘레 / 밑단단면, 커프스, 팔둘레 (and a bare "Sleeve": it is 팔둘레 at 11160224814).

## Never read

`NOT_CHART_RE`: the model and the buyer (모델, 착용, 키 165, 신장, 체중, 몸무게, 체형, 신체, kg, model, wear), the shop
(배송, 반품, 교환, 7만원, 상품번호). Not charts either, and not read by the layouts: size lists ("사이즈 / 90, 95, 100,
105"), recommendation tables ("평소 55사이즈 착용 시-XS 추천", 7562982095), the care label ("구 / 90 cm", 12558165017),
measuring-method text ("가슴둘레 : 겨드랑이 1cm 밑"), tolerance notes ("1~3cm 오차"), RFID tag samples ("호칭:100").
A model block (2026-11-20, 10940191023): a "Bust : 83cm" line with another Height / Waist / Hip line within 4 lines is
the model's bust. A number written against 사이즈 / size (no space) is a women's size, never a measure ("어깨가넓은 마른66사이즈" made a
conflict "shoulder 66", 11573884405).

## When a chart is not read

1. Copy the product's lines into a test (`test_apparel_sizes.py`, the study's section) with what a person reads.
2. Name the pattern: a new value shape, header shape, word, or layout. Add it narrowly; check the never-read list.
3. `UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_apparel_sizes.py`; read the fixture's diff: only the
   product meant may move. Then `run_transform.py <shop> --diff`.
4. A new layout or a new risk goes into the tables above, dated.
