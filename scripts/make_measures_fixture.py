"""A measures regression fixture from a real product (2026-11-11): the product's latest collected line and its
description_images sidecar cut to what the transform's hook reads (title, 상품정보 rows, one-value facts, the
first three variants, add-ons, typed lines, the images' rows that hold a digit or a measure word; the others kept
as a count, a row naming the seller (an address, a phone, a web or mail address) as "x"), written to fixtures/measures/<product id>.json with an empty `expected`.
Then pin it and read the diff against the product's own lines (R-TEST-5):

    .venv/bin/python -I scripts/make_measures_fixture.py <product id> "<covers>" "<checked; checked; ...>" ["<note>"]
    .venv/bin/python -I scripts/make_measures_fixture.py <product id> --recut      # again, keeping the texts and the pins
    UPDATE_GOLDEN=1 .venv/bin/python -m pytest scripts/test_measures_fixtures.py

Reads scripts/output/shops/fairwardgolf (collected/, description_images/): offline."""
import json, os, re, sys  # noqa: E401
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import run_transform, transform
from description_images import load_sidecar
from transform_shops import rules_for, without_paid_addons

pid = sys.argv[1]
if sys.argv[2] == "--recut":
    old = json.load(open(f"fixtures/measures/{pid}.json"))
    covers, checked, note, kept = old["covers"], old["checked"], old.get("note", ""), old["expected"]
else:
    covers, checked = sys.argv[2], [c.strip() for c in sys.argv[3].split(";") if c.strip()]
    note, kept = sys.argv[4] if len(sys.argv) > 4 else "", []
lines = run_transform.latest_lines("fairwardgolf")
key = next(k for k in lines if k.endswith(":" + pid))
run_id, n, line = lines[key]
got: dict = {}
real = transform._image_measures


def spy(ov, sidecar, title, model, pieces, spec_rows, cat_id, typed=None, supplements=None):
    got.update(ov=json.loads(json.dumps(ov)), title=title, spec_rows=spec_rows, typed=typed or "",
               supplements=supplements or [])
    return real(ov, sidecar, title, model, pieces, spec_rows, cat_id, typed, supplements)


transform._image_measures = spy
transform.prepare(line, without_paid_addons(rules_for("fairwardgolf")), run_id, n, load_sidecar("fairwardgolf", pid))
PHONE = re.compile(r"\d{2,4}\s*-\s*\d{3,4}\s*-\s*\d{4}")
# a row naming the seller: an address, a phone, a web or mail address, the business numbers: the whole row is "x"
PRIVATE = re.compile(r"@[A-Za-z0-9.-]+\.[a-z]|www\.|https?://|0\d{1,2}[- .]?\d{3,4}[- .]?\d{4}|\b1[5-8]\d\d[- ]?\d{4}\b|"
                     r"[가-힣]+(?:시|군|구)\s*[가-힣]+(?:로|길|동)\s?\d+|[가-힣]+(?:로|길)\s?\d+(?:-\d+)?|사업자|통신판매|"
                     r"대표자|주소|kakao|카카오|등록번호|\d{3}\.\d{3,4}\.\d{4}", re.I)


def private(text: str) -> str:
    return "x" if PRIVATE.search(text) else PHONE.sub("x", text)
UNIT = re.compile(r"\d|(?:cm|mm|㎝|kg|㎏|g\b|인치|인츠|inch|\"|형)|무게|중량|길이|사이즈|크기|가방|백|개|PCS|pcs|구성|포함|별매|"
                  r"드라이버|아이언|퍼터|우드|유틸|head|shaft|grip|CPM|\d\s*/\s*\d", re.I)
images = []
for img in (load_sidecar("fairwardgolf", pid) or {}).get("images") or []:
    rows: list = []
    blank = 0
    for sl in img.get("slices") or []:
        for r in sl.get("rows") or []:
            t = private(r.get("text") or "")
            if UNIT.search(t):
                if blank:
                    rows.append(blank); blank = 0
                rows.append([t, r.get("conf", 1.0)])
            else:
                blank += 1
    if blank:
        rows.append(blank)
    if img.get("status") == "read":
        images.append(rows)
specs = line["specs"]
spec_rows = [r for r in got["spec_rows"] if r.get("label") not in ("A/S 안내", "A/S 전화번호")]
variants = [{"id": str(v.get("id")), "options_ko": list(v.get("options_ko") or [])}
            for v in (specs.get("options") or {}).get("variants") or []]
fixture = {"product_id": pid, "covers": covers, "checked": checked, **({"note": note} if note else {}),
           "input": {"title": got["title"], "category": {"id": specs["category"]["id"], "name": specs["category"].get("name")},
                     "spec_rows": spec_rows, "facts": got["ov"]["facts"],
                     "variants": [{"id": str(v["naver_variant_id"]) if v.get("naver_variant_id") else None, "options_ko": v["options_ko"]}
                                  for v in got["ov"]["variants"]][:3],
                     "supplements": got["supplements"], "typed": [private(t) for t in got["typed"].split("\n") if t.strip()],
                     "images": images, "measures": specs.get("measures") or {}},
           "expected": kept}
out = f"fixtures/measures/{pid}.json"
json.dump(fixture, open(out, "w"), ensure_ascii=False, indent=1)
print("wrote", out, "variants", len(fixture["input"]["variants"]), "images", len(images))
