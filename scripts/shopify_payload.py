"""A prepared, translated and placed product -> the Shopify data that publishes it (the owner, 2026-11-08, MVP).
Pure and offline: no network, no clock; publish.py uploads the files and sends what this builds.

One product is built in two steps, because the reviews' files must be on Shopify's CDN first:
  1. `review_files(prepared)`: the local review photos and avatars to upload (publish.py gets their CDN links);
  2. `reviews(prepared, en, urls)`: the review rows with those links (the JSON feed file and `custom.reviews_seo`);
  3. `product_input(prepared, en, placement, ...)`: the `productSet` input (title, vendor, handle, type, tags,
     options, variants, photos, metafields), status ACTIVE.

The owner's rules:
- English everywhere from the translation (by text id); a text without English stops the product (`Untranslated`).
- Price: KRW kept in metafields; cost = KRW at 1 000 = 1 USD rounded up to a dollar; price = cost through the shop's
  margin hook (shop_pricing.py, none yet). No compare-at price.
- Buyable: every variant is untracked and sold without limit (CONTINUE), one sold out on Naver too (the owner,
  2026-11-09: the site opens buying later); `available` in the variant's fairwardgolf.source says which it is.
- A seller's "1+1" listing repeats one option (two sets, one flex each): an option with the same English name and
  the same values as an earlier one, which no price depends on, is one option (the owner, 2026-11-09).
- No description (descriptionHtml empty), no HS / origin codes, no delivery data, no facts, no gender metafield
  (the gender places the product: tags and type come from placement.py).
- Photos: the product's gallery, alt "<brand> <title> - photo N" (the brand once when the title starts with it); a
  product with fewer than GALLERY_MIN photos gets buyers' photos after its own, up to GALLERY_MAX in all
  (review_gallery(), ranked by review_rank()).
- A product without options gets one option with a universal name and value (FALLBACK_OPTION).

Metafields: the storefront's (custom.*, read by the site, the formats it renders) and our own (fairwardgolf.*, not
on the storefront, one JSON per concern with a schemaVersion: add a field there, or a row to PRODUCT_FIELDS).
"""
import hashlib
import json
import re
import unicodedata
from typing import Any

from review_clean import cut_english
from shop_pricing import Policy, money
from transform import text_id

VERSION = "payload/10"                         # bump on a change of what this module builds: every product is sent again
FALLBACK_OPTION = ("Option", "Standard")      # a product with no option of its own (Shopify's "Title / Default")
OPTION_VALUE_MAX = 255
ALT_MAX = 512
HANDLE_MAX = 200
TITLE_MAX = 150                               # Google Merchant Center's limit for a product title (title [title])
SEO_TITLE_MAX = 70                            # the page <title>; about what a search result shows
REVIEW_ROWS = 20                              # rows in custom.reviews_seo (the site's SEO block); the feed has all
GALLERY_MIN = 2                               # fewer product photos: buyers' photos fill the gallery (the owner,
GALLERY_MAX = 5                               # 2026-11-09: a fuller gallery for Google Merchant) up to this many photos
GALLERY_PER_REVIEW = 2                        # photos of one review at most
GALLERY_MIN_SIDE = 400                        # px: a smaller photo is not shown
GALLERY_MAX_RATIO = 2.2                       # long side / short side: a strip or a panorama is not shown
GALLERY_MAX_GREEN = 0.15                      # share of grass-green pixels: over it, a course or a range (_shown)
PURCHASE_TOPICS = {"seller", "packing", "shipping", "gift"}   # review_clean's cut topics that tell of the delivery
# the text of a review that is photos only (or whose every sentence was cut): one of these, picked by the review's id
# (the owner, 2026-11-09: the photo is worth showing, a row needs words); none says more than that there are photos
PHOTO_ONLY_TEXTS = ("Sharing a few photos.", "Here are my photos.", "Photos attached.", "Here's how it looks in person.",
                    "A few photos for anyone deciding.", "Adding some real-life photos.", "Here's a look at mine.",
                    "Posting a couple of photos.")


class Untranslated(Exception):
    """A text the product needs has no English yet: the product waits for translate.py."""


class PayloadError(Exception):
    """The product cannot be built (no variant, a broken placement ...)."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class English:
    """The product's English by (kind, Korean): the translated line's `en` by text id."""

    def __init__(self, translated: dict[str, Any]):
        self.en = translated.get("en") or {}
        self.missing: list[str] = []

    def __call__(self, kind: str, ko: str | None) -> str:
        if not ko:
            return ""
        tid = text_id(kind, ko)
        value = self.en.get(tid)
        if value is None:
            self.missing.append(tid)
            return ""
        return value

    def check(self) -> None:
        if self.missing:
            raise Untranslated(", ".join(sorted(set(self.missing))[:10]))


# ---- names -------------------------------------------------------------------------------------------------------

def handle(title: str, brand: str = "") -> str:
    """"Callaway REVA Women's 10-Piece Set" -> "callaway-reva-womens-10-piece-set" (the harvester's rule: ASCII only,
    the brand in front unless the title starts with it)."""
    text = title if not brand or title.lower().startswith(brand.lower()) else f"{brand} {title}"
    text = re.sub(r"[™®©'’`]", "", text)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        raise PayloadError(f"no handle from the title {title!r}")
    return slug[:HANDLE_MAX].rstrip("-")


def alt(brand: str, title: str, n: int) -> str:
    name = title if not brand or title.lower().startswith(brand.lower()) else f"{brand} {title}"
    return f"{name} - photo {n}"[:ALT_MAX]


_OPTION_NAME_RE = re.compile(r"\s+/\s+")      # Shopify refuses " / " in an option name (it joins variant titles)
_SELECT_RE = re.compile(r"^(?:Select|Choose|Choice of|Pick)\s+(?=\S)", re.I)    # "Select Driver (REAX MR 50)"
_LEGAL_RE = re.compile(r"(?:[\s,]*(?:Co\.?,?\s*Ltd\.?|Ltd\.?|Inc\.?|Corp\.?|Corporation|Co\.|Company|\(주\)|주식회사))+$",
                       re.I)


def title_vendor(product: dict[str, Any], en: "English", vendors: dict[str, str] | None = None,
                 tenant: str | None = None) -> tuple[str, str]:
    """(title, vendor): the vendor as the shop spells it, and the title starting with it when the model left the
    brand out (a maker's name; not the tenant's own name for 노브랜드)."""
    title = clean_title(en("title", product["title_ko"]))
    brand = vendor_name(en("brand", product.get("brand_ko")).strip(), vendors)
    if brand and brand != tenant and brand.lower() not in title.lower():
        title = f"{brand} {title}"
    elif brand:                                 # the title spells the brand as the vendor does ("Yonex" -> "YONEX"
        title = re.sub(rf"(?<![\w-]){re.escape(brand)}(?![\w-])", lambda _: brand, title, flags=re.I)   # if so)
    fitted = fit_title(title)
    if brand and brand != tenant and brand.lower() not in fitted.lower():      # the brand stood in the part cut off
        fitted = fit_title(f"{brand} {fitted}")
    return fitted, brand


_IMPORT_RE = re.compile(r"\s*\(?\b(?:Parallel[- ]Import(?:ed)?|Korea(?:n)? (?:Genuine|Official)(?: Product)?)\b\)?", re.I)


# what a cut must not end on: punctuation, a joining word ("Set with", "Bag Made in"; "Plus" is a model's name and
# a capital "A" a flex, so they stay), and a count whose unit was cut off ("Set 13" of "13 Pieces", "Hybrid 8" of
# "8 Irons")
_DANGLING_RE = re.compile(r"(?:[\s,;:/&+–-]+|\s+(?:(?i:with|and|for|in|of|the|an|to|by|or|made|from|on|at|including"
                          r"|w/?)|a)(?=\s*$|[\s,;:/&+–-]))+$")
_COUNTED_RE = re.compile(r"(?:pieces?|pcs?|irons?|woods?|hybrids?|wedges?|clubs?|putters?|balls?|dozen|packs?|sets?|"
                         r"degrees?|inch(?:es)?|in|cm|mm|g|kg|oz|lbs?)\b", re.I)
FIT_KEEP = 0.6                                # a cut at a comma must keep this share of the limit, else words are cut


def fit_title(title: str, limit: int = TITLE_MAX) -> str:
    """The title within `limit` characters, whole words only. The translation asks the model for a short title
    (translate.ASK_SHORTER); this is the last guard, for the title that stayed long and for the brand put in front
    of it. Too long: the facts after a comma go first, from the end (a store title ends on its least important
    facts: "..., Driver, Hybrid, 7 Irons, Putter"), when that keeps FIT_KEEP of the limit; else whole words from
    the end. Nothing is left dangling: a joining word, a comma, a count without its unit, an open bracket."""
    title = re.sub(r"\s+", " ", title or "").strip()
    if len(title) <= limit:
        return title
    out = title
    while len(out) > limit and ", " in out:
        out = out.rsplit(", ", 1)[0]
    if len(out) > limit or len(out) < FIT_KEEP * limit:
        cut = title[:limit + 1]
        out = cut[:cut.rfind(" ")] if " " in cut else title[:limit]
        rest = title[len(out):].lstrip()
        if _COUNTED_RE.match(rest):                       # "... Set 13" | "Pieces ..."
            out = re.sub(r"\s+#?\d+(?:\.\d+)?$", "", out)
    if out.count("(") > out.count(")"):
        out = out[:out.rfind("(")]
    while True:
        shorter = _DANGLING_RE.sub("", out).strip()
        if shorter == out:
            return out
        out = shorter


def clean_title(title: str) -> str:
    """The translated title without what the prompt sometimes lets through (2026-11-09 pilot): "(Parallel Import)",
    a word written twice in a row ("Tour Edge Edge"), a code written twice ("BG-100 BG100", "D1 ... D1")."""
    title = _IMPORT_RE.sub("", title or "")
    out: list[str] = []
    seen: set[str] = set()
    for word in title.split():
        key = re.sub(r"[^a-z0-9]", "", word.lower())
        coded = bool(re.search(r"\d", key)) and len(key) >= 2
        if out and key and key == re.sub(r"[^a-z0-9]", "", out[-1].lower()):
            continue                                       # the same word twice in a row
        if coded and key in seen:
            continue                                       # a model code met before
        if coded:
            seen.add(key)
        out.append(word)
    return re.sub(r"\s+([,)])", r"\1", " ".join(out)).strip(" ,-")


def vendor_name(brand: str, spellings: dict[str, str] | None = None) -> str:
    """The shop's vendor from the translated brand: a maker's company form cut ("Prokenex / SJG Co., Ltd." ->
    "Prokenex"), and the one spelling of it, compared without case ({lower case: spelling}: the brand dictionary's,
    else the shop's; the owner, 2026-11-09: a brand the dictionary writes in capitals is in capitals, and the other
    way round, whatever the case it came in)."""
    name = re.split(r"\s*/\s*|\s*,\s*", brand or "")[0]      # "Mizuno, Hillcreek" -> "Mizuno" (2026-11-09)
    name = _LEGAL_RE.sub("", name).strip(" ,./")
    return (spellings or {}).get(name.lower(), name)


def _unique(values: list[str]) -> list[str]:
    """Option values as Shopify takes them: unique in their option (two Korean values one English: "X", "X (2)")."""
    out: list[str] = []
    for v in values:
        v = (v or "").strip()[:OPTION_VALUE_MAX] or FALLBACK_OPTION[1]
        name, n = v, 2
        while name in out:
            suffix = f" ({n})"
            name, n = v[:OPTION_VALUE_MAX - len(suffix)] + suffix, n + 1
        out.append(name)
    return out


# ---- reviews -----------------------------------------------------------------------------------------------------

def review_files(prepared: dict[str, Any]) -> list[str]:
    """The review photos and avatars (paths relative to the shop folder) that must be on Shopify's CDN."""
    out: list[str] = []
    for r in prepared["product"].get("reviews") or []:
        for f in ([r["avatar"]] if r.get("avatar") else []) + list(r.get("photos") or []):
            if f not in out:
                out.append(f)
    return out


def review_id(naver_id: str) -> int:
    """The row's number (the harvester's, kept so the site's ids stay stable)."""
    return int(hashlib.sha256(f"naver:{naver_id}".encode()).hexdigest()[:12], 16) + 1


def reviews(prepared: dict[str, Any], en: English, urls: dict[str, str]) -> list[dict[str, Any]]:
    """Every selected review as the site's row (customer, rating, text, CDN photos, date); `date` as in the feed."""
    rows = []
    for r in prepared["product"].get("reviews") or []:
        rid = str(r.get("id") or "").strip()
        score, date = r.get("score"), r.get("created_at")
        if not rid or not isinstance(score, (int, float)) or isinstance(score, bool) or not isinstance(date, str):
            continue                            # the site drops the whole feed for one row it cannot read
        images = [urls[f] for f in r.get("photos") or [] if urls.get(f)]
        text = close_review(cut_english(en("review", r.get("text_ko"))))
        if not text and not images:
            continue                            # rating only, nothing to show (the score is in the product's rating)
        r = {**r, "id": rid}
        customer: dict[str, Any] = {"name": r.get("writer") or "Naver buyer"}
        if r.get("avatar") and urls.get(r["avatar"]):
            customer["avatarUrl"] = urls[r["avatar"]]
        rows.append({"id": review_id(r["id"]), "customer": customer, "rating": r["score"], "title": "",
                     "description": text or photo_only_text(rid), "date": r.get("created_at"),
                     "images": images, "verified": False,
                     "source": {"platform": "naver", "language": "ko", "translated": True, "reviewId": r["id"]}})
    return rows


def photo_only_text(review: str) -> str:
    return PHOTO_ONLY_TEXTS[int(hashlib.sha256(f"photo:{review}".encode()).hexdigest()[:8], 16) % len(PHOTO_ONLY_TEXTS)]


def review_rank(review: dict[str, Any]) -> float | None:
    """How well a review's photos may show the product, higher first; None: its photos are not for the gallery.
    Measured on the pilot (2026-11-09: 94 picks judged by eye, then 80 by four judging agents; 43 fit): the text
    tells little of what the photo shows, so the order follows the owner (useful reviews, several photos first)
    and the few signals that held: Naver's "helpful" votes, a full text, and no story of the purchase (a review
    that told of the seller, packing or shipping showed the box or the shop; one photo and no product words
    rarely showed the product)."""
    photos, score = review.get("photos") or [], review.get("score")
    if not photos or not isinstance(score, (int, float)) or isinstance(score, bool) or score < 4:
        return None                             # a low score's photo may show a defect
    grade = review.get("text_grade")
    purchase = bool(set(review.get("text_cut") or []) & PURCHASE_TOPICS)
    if len(photos) == 1 and (grade == "rating_only" or purchase):
        return None                             # one photo and nothing about the product: the box, the delivery
    raw = review.get("likes")
    likes: int = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
    rank = float(review.get("text_quality") or 0)            # aspects named, length (0..100)
    rank += 10 * min(max(likes, 0), 3)                        # buyers found it helpful
    rank += 30 if len(photos) >= 2 else 0                     # the owner: a buyer who shows several photos first
    rank += 5 * min(len(photos) - 1, 3)
    rank += {"full": 15, "short": 0}.get(grade or "", -15)
    rank -= 10 if len(photos) == 1 and grade != "full" else 0
    rank -= 25 if purchase else 0
    rank += 3 if score >= 5 else 0
    return rank


def _shown(meta: dict[str, Any]) -> bool:
    """A photo the gallery may show by its file: not small, not a strip, not mostly grass (a course, a range, a
    screen-golf room: 7 of 7 such picks of the pilot showed a person or a place, none of 65 product photos was over
    0.03). No meta: not judged."""
    w, h = meta.get("width") or 0, meta.get("height") or 0
    if w and h and (min(w, h) < GALLERY_MIN_SIDE or max(w, h) / min(w, h) > GALLERY_MAX_RATIO):
        return False
    return (meta.get("green") or 0) <= GALLERY_MAX_GREEN


def review_gallery(prepared: dict[str, Any], info: dict[str, dict[str, Any]] | None = None,
                   skip: Any = frozenset()) -> list[str]:
    """The buyers' photos (paths relative to the shop folder) that follow the product's own in its gallery: a
    product with fewer than GALLERY_MIN photos gets them until the gallery holds GALLERY_MAX (the owner, 2026-11-09).
    Reviews in review_rank() order; one photo per review a round (its first photo the gallery may show), up to
    GALLERY_PER_REVIEW rounds, so the gallery shows several buyers. `info` {path: {sha256, width, height, green}}
    (publish.py reads the files): a photo shown already (same hash: the product's own, or one buyer's photo in two
    reviews) or not _shown() is passed over. `skip`: photos a person struck out (the shop's gallery_skip list)."""
    product = prepared["product"]
    own = product.get("images") or []
    room = GALLERY_MAX - len(own)
    if len(own) >= GALLERY_MIN or room <= 0:
        return []
    info = info or {}
    seen = {img.get("sha256") for img in own if img.get("sha256")}
    scored = [(review_rank(r), str(r.get("id")), r["photos"]) for r in product.get("reviews") or []]
    ranked = [photos for rank, _, photos in sorted((t for t in scored if t[0] is not None),
                                                   key=lambda t: (-(t[0] or 0), t[1]))]
    out: list[str] = []
    next_photo = [0] * len(ranked)
    for _ in range(GALLERY_PER_REVIEW):
        for n, photos in enumerate(ranked):
            while next_photo[n] < len(photos) and len(out) < room:
                rel = photos[next_photo[n]]
                next_photo[n] += 1
                meta = info.get(rel) or {}
                if rel in out or rel in skip or (meta.get("sha256") and meta["sha256"] in seen) or not _shown(meta):
                    continue
                out.append(rel)
                if meta.get("sha256"):
                    seen.add(meta["sha256"])
                break
    return out


_TRAILING_RE = re.compile(r"[\s,;:–-]*\b(?:and|but|so|or|plus|because|since|though|while|which)\s*$", re.I)


def close_review(text: str) -> str:
    """A review the cleaning cut mid-sentence ends on "and" in English ("Lightweight and"): the dangling word goes and
    the sentence closes (2026-11-09 pilot: 19 rows). A review that ends on its own (".", "!", "?", "...", ")") stays."""
    text = (text or "").rstrip()
    stripped = _TRAILING_RE.sub("", text).rstrip(" ,;:–-")
    if stripped != text and stripped and stripped[-1] not in ".!?)…":
        return stripped + "."
    return text


def reviews_seo(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """custom.reviews_seo: the first rows, the date named `createdAt` (the site's two formats differ in that only)."""
    out = []
    for row in rows[:REVIEW_ROWS]:
        row = dict(row)
        row["createdAt"] = row.pop("date")
        out.append(row)
    return out


# ---- the product -------------------------------------------------------------------------------------------------

_GIFT_RE = re.compile(r"증정|사은품|서비스|이벤트")
_NUMBERED_RE = re.compile(r"^\s*(?:\d{1,2}[.)](?!\d)\s*|SPEC\s+)", re.I)   # "01. 12 pcs ...", "SPEC 10.5 R"; not
                                                                             # a decimal ("10.5°": 2026-11-09, "5°")


def _value(text: str) -> str:
    return _NUMBERED_RE.sub("", text or "").strip()


def _single(product: dict[str, Any], en: English) -> tuple[str, str]:
    """The name and value of a product's one variant: what the seller's one remaining choice says (a constant
    option axis, kept by the transform as a fact: "세트: 12P + 캐디백", when the others were sold out or cost
    extra), else the universal FALLBACK_OPTION. A gift line is not a choice."""
    facts = [f for f in product.get("facts") or [] if f.get("value_ko") and not _GIFT_RE.search(
        (f.get("label_ko") or "") + f["value_ko"])]
    if len(facts) == 1:
        value = _value(en("fact_value", facts[0]["value_ko"]))
        name = en("fact_label", facts[0]["label_ko"]).strip() if facts[0].get("label_ko") else ""
        name = _SELECT_RE.sub("", _OPTION_NAME_RE.sub("/", name)).strip()
        if value:
            return (name or FALLBACK_OPTION[0])[:OPTION_VALUE_MAX], value[:OPTION_VALUE_MAX]
    return FALLBACK_OPTION


def _twins(product: dict[str, Any], en: English) -> dict[str, Any]:
    """The product with a repeated option made one: same English name, same values, and no price depends on the
    repeat (5684497984, "1+1": two "Driver / Wood / Hybrid Flex" options, 4 variants at one price -> 2). Per choice
    of the other options the variant kept is the one whose repeat equals the option it repeats; buyable if any is."""
    options = product.get("options") or []
    for j in range(1, len(options)):
        for i in range(j):
            if options[i]["values_ko"] != options[j]["values_ko"] or \
                    en("option_name", options[i]["name_ko"]) != en("option_name", options[j]["name_ko"]):
                continue
            groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
            for v in product["variants"]:
                picked = list(v.get("options_ko") or [])
                if len(picked) != len(options):
                    return product
                groups.setdefault(tuple(picked[:j] + picked[j + 1:]), []).append(v)
            if any(len({int(v["price_krw"]) for v in g}) > 1 for g in groups.values()):
                continue                        # the repeat changes the price: a choice of its own
            variants = []
            for rest, g in groups.items():
                same = [v for v in g if v["options_ko"][j] == v["options_ko"][i]]
                variants.append({**(same or g)[0], "options_ko": list(rest),
                                 "available": any(v.get("available") for v in g)})
            return _twins({**product, "options": options[:j] + options[j + 1:], "variants": variants}, en)
    return product


def _options(product: dict[str, Any], en: English) -> tuple[list[dict[str, Any]], list[list[str]]]:
    """[{name, values:[{name}]}] and, per Korean option, the English of each Korean value (same order)."""
    options = product.get("options") or []
    if not options:
        name, value = _single(product, en)
        return [{"name": name, "values": [{"name": value}]}], []
    out: list[dict[str, Any]] = []
    values_en: list[list[str]] = []
    for o in options:
        name = _OPTION_NAME_RE.sub("/", en("option_name", o["name_ko"])).strip()
        name = _SELECT_RE.sub("", name).strip() or FALLBACK_OPTION[0]
        names = _unique([_value(en("option_value", v)) for v in o["values_ko"]])
        out.append({"name": name[:OPTION_VALUE_MAX], "values": [{"name": v} for v in names]})
        values_en.append(names)
    seen: set[str] = set()                             # two options with one English name: Shopify refuses it
    for i, o in enumerate(out):
        while o["name"] in seen:
            o["name"] = f"{o['name'][:OPTION_VALUE_MAX - 4]} {i + 1}"
        seen.add(o["name"])
    return out, values_en


def _package(variant: dict[str, Any]) -> dict[str, Any] | None:
    package = variant.get("package") or {}
    return {"schemaVersion": "fairwardgolf-package/1", "fields": package} if package else None


def _weight_g(variant: dict[str, Any]) -> int | None:
    """The shipping weight: the package's central value (the seller's, else the category's average)."""
    field = (variant.get("package") or {}).get("package_weight_g") or {}
    value = field.get("central")
    if value is None:                           # read from the description images: {"value": {"min", "max"}} or a
        raw = field.get("value")                # number; the heavier end ships (2026-11-09: 9 GV Tour variants)
        value = max(raw.get("min") or 0, raw.get("max") or 0) if isinstance(raw, dict) else raw
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _variants(prepared: dict[str, Any], options: list[dict[str, Any]], values_en: list[list[str]],
              pricing: Policy, location_id: str) -> list[dict[str, Any]]:
    product = prepared["product"]
    taxable = bool((product.get("pricing") or {}).get("taxable"))
    out, seen = [], set()
    for v in product["variants"]:
        if values_en:
            picked = []
            for i, ko in enumerate(v.get("options_ko") or []):
                values_ko = product["options"][i]["values_ko"]
                if ko not in values_ko:
                    raise PayloadError(f"variant {v.get('sku')}: option value {ko!r} is not among the option's values")
                picked.append({"optionName": options[i]["name"], "name": values_en[i][values_ko.index(ko)]})
        else:
            picked = [{"optionName": options[0]["name"], "name": options[0]["values"][0]["name"]}]
        combo = tuple(p["name"] for p in picked)
        if combo in seen:
            raise PayloadError(f"two variants with the same options {combo}")
        seen.add(combo)
        krw = int(v["price_krw"])
        cost = pricing.cost_usd(krw)
        price = pricing.price_usd(cost, {"variant": v, "product": product})
        available = bool(v.get("available"))
        item: dict[str, Any] = {"tracked": False, "cost": money(cost), "requiresShipping": True}
        weight = _weight_g(v)
        if weight:
            item["measurement"] = {"weight": {"value": weight, "unit": "GRAMS"}}
        variant: dict[str, Any] = {
            "optionValues": picked, "sku": v["sku"], "price": money(price), "taxable": taxable,
            "inventoryPolicy": "CONTINUE", "inventoryItem": item,
            "metafields": [{"namespace": "fairwardgolf", "key": "source", "type": "json", "value": _json({
                "schemaVersion": "fairwardgolf-variant-source/1", "naverVariantId": v.get("naver_variant_id"),
                "sourceId": v.get("source_id"), "optionsKo": v.get("options_ko") or [], "priceKrw": krw,
                "costUsd": cost, "priceUsd": price, "available": available})}],
        }
        package = _package(v)
        if package:
            variant["metafields"].append({"namespace": "fairwardgolf", "key": "package", "type": "json",
                                          "value": _json(package)})
        out.append(variant)
    if not out:
        raise PayloadError("no variant")
    return out


def _key(seed: str, prefix: str, taken: set[str] | None = None) -> str:
    """A stable key from the seed; with `taken`, a seed met twice gets "#2", "#3" (keys must be unique)."""
    key, n = f"{prefix}_{hashlib.sha256(seed.encode()).hexdigest()[:24]}", 2
    while taken is not None and key in taken:
        key, n = f"{prefix}_{hashlib.sha256(f'{seed}#{n}'.encode()).hexdigest()[:24]}", n + 1
    if taken is not None:
        taken.add(key)
    return key


# The site's reader contract (naver-harvester shared/product-configuration, read 2026-11-08): strict objects, no key
# beyond these; add-ons only complimentary (priceKrw 0); labels trimmed, non-empty, bounded in code points.
PERSONALIZATION_MAX_FIELDS = 20
ADDON_MAX_GROUPS, ADDON_MAX_CHOICES = 10, 100
ADDON_GROUP_LABEL, ADDON_CHOICE_LABEL = 60, 120
REQUIRED_MAX_GROUPS, REQUIRED_MAX_VALUES, REQUIRED_VALUE_LABEL = 5, 100, 120
# a gift's wording in an extra's English label ("Free Maruman 2W Putter 1 Pc", "... Gift Default Selection"): the
# block is already "Complimentary extras" (2026-11-09 pilot)
_GIFT_EN_RE = re.compile(r"\b(?:Free|Gift(?:ed)?|Complimentary|Bonus|Default Selection|Included)\b", re.I)
_NO_ADD_RE = re.compile(r"추가\s*안\s*함|선택\s*안\s*함|미선택|없음|추가안함")


_SPACE_RE = re.compile(r"[\s\ufeff\u200b]+")      # what JavaScript's trim() removes, and the zero-width space


def _label(text: str | None, limit: int | None = None) -> str:
    text = _SPACE_RE.sub(" ", text or "").strip()
    return text if limit is None else _SPACE_RE.sub(" ", "".join(list(text)[:limit])).strip()


def _text_label(text: str) -> str:
    """One wording for the same field (2026-11-09: "ex." / "e.g." / "Put on" for 클럽에 부착하실 이름(ex 홍길동))."""
    text = _label(text)
    text = re.sub(r"\(\s*(?:ex|e\.g|eg|example)\.?,?\s*", "(e.g., ", text, flags=re.I)
    text = re.sub(r"\bName Sticker Name\b", "Name for the Name Sticker", text, flags=re.I)
    return text


def personalization(prepared: dict[str, Any], en: English) -> dict[str, Any] | None:
    """custom.personalization_fields as the site reads it: a field without an English label is left out, and a
    length limit only when the seller set one."""
    fields: list[dict[str, Any]] = []
    taken: set[str] = set()
    for t in prepared["product"].get("personalization") or []:
        label = _text_label(en("text_label", t.get("label_ko")))
        if not label or len(fields) >= PERSONALIZATION_MAX_FIELDS:
            continue
        limit = t.get("max_length")
        fields.append({"key": _key(prepared["key"] + "|" + (t.get("label_ko") or ""), "field", taken), "type": "text",
                       "label": label, "required": bool(t.get("required")),
                       "placeholder": _label(en("text_placeholder", t.get("placeholder_ko"))) or None, "hint": None,
                       "constraints": {"maxLength": limit} if isinstance(limit, int) and not isinstance(limit, bool)
                       and limit >= 0 else {}})
    return {"schemaVersion": "product-personalization/v1", "fields": fields} if fields else None


def addons(prepared: dict[str, Any], en: English, pricing: Policy) -> tuple[dict[str, Any] | None,
                                                                             dict[str, Any] | None,
                                                                             dict[str, Any] | None]:
    """(custom.optional_addons, fairwardgolf.addons). The site shows complimentary choices only, in its exact
    format; every add-on, paid ones with their USD price, goes to our own field, ready for the day the site sells
    them (as products of their own, or variants)."""
    every: dict[str, dict[str, Any]] = {}
    taken: set[str] = set()
    for a in prepared["product"].get("addons") or []:
        g = every.get(a["group_ko"])
        if g is None:
            g = every[a["group_ko"]] = {"key": _key(prepared["key"] + "|" + a["group_ko"], "addon", taken),
                                        "label": _label(en("addon_group", a["group_ko"])), "groupKo": a["group_ko"],
                                        "required": bool(a.get("required")), "choices": []}
        krw = int(a.get("price_krw") or 0)
        cost = pricing.cost_usd(krw)
        g["choices"].append({"key": _key(prepared["key"] + "|" + a["group_ko"] + "|" + a["name_ko"], "choice", taken),
                             "label": _label(en("addon_name", a["name_ko"])), "nameKo": a["name_ko"],
                             "priceKrw": krw, "costUsd": cost,
                             "priceUsd": pricing.price_usd(cost, {"addon": a}), "free": krw == 0})
    site: list[dict[str, Any]] = []
    required: list[dict[str, Any]] = []
    one_variant = len(prepared["product"].get("variants") or []) == 1
    for g in every.values():
        label = _label(_GIFT_EN_RE.sub(" ", g["label"]), ADDON_GROUP_LABEL)
        free = [c for c in g["choices"] if c["free"] and _label(c["label"], ADDON_CHOICE_LABEL)]
        if g["required"] and one_variant:
            # a choice the buyer must make (기본 구성품 유틸 선택, required) is not an extra (2026-11-09: shown under
            # "Complimentary extras · Optional"): custom.required_selections, the site's field for it, which the
            # contract allows on a one-variant product only; "do not add" is no value there
            values = [c for c in free if not _NO_ADD_RE.search(c["nameKo"])]
            labels = list(dict.fromkeys(_label(_GIFT_EN_RE.sub(" ", c["label"]), REQUIRED_VALUE_LABEL) for c in values))
            if label and len(labels) >= 2 and len(required) < REQUIRED_MAX_GROUPS:
                required.append({"key": _key(prepared["key"] + "|select|" + g["groupKo"], "select", taken),
                                 "label": label, "hint": None, "values": [
                                     {"key": _key(prepared["key"] + "|value|" + g["groupKo"] + "|" + v, "value", taken),
                                      "label": v} for v in labels[:REQUIRED_MAX_VALUES] if v]})
                continue
        choices = [{"key": c["key"], "label": _label(_GIFT_EN_RE.sub(" ", c["label"]), ADDON_CHOICE_LABEL) or
                    _label(c["label"], ADDON_CHOICE_LABEL), "priceKrw": 0} for c in free]
        if label and choices and len(site) < ADDON_MAX_GROUPS:
            site.append({"key": g["key"], "label": label, "choices": choices[:ADDON_MAX_CHOICES]})
    public = {"schemaVersion": "product-optional-addons/v1", "groups": site} if site else None
    private = ({"schemaVersion": "fairwardgolf-addons/1", "groups": list(every.values())} if every else None)
    must = None
    if required:
        must = {"schemaVersion": "product-required-selections/v1", "revision": "", "combinations": "all",
                "priceEffect": "none", "groups": required}
        must["revision"] = hashlib.sha256(_json(required).encode()).hexdigest()
    return public, private, must


def _placement(placement: dict[str, Any]) -> tuple[str, list[str]]:
    if (placement or {}).get("status") != "placed" or not placement.get("leaves"):
        raise PayloadError(f"not placed: {(placement or {}).get('status')} {(placement or {}).get('reason')}")
    leaves = placement["leaves"]
    primary = max(leaves, key=lambda leaf: len(leaf.get("skus") or []))
    tags: list[str] = []
    for leaf in leaves:
        tags += [t for t in leaf.get("tags") or [] if t not in tags]
    return primary["product_type"], tags


def product_input(prepared: dict[str, Any], translated: dict[str, Any], placement: dict[str, Any],
                  pricing: Policy, location_id: str, photos: list[dict[str, Any]], feed_url: str | None = None,
                  rows: list[dict[str, Any]] | None = None, handle_override: str | None = None,
                  vendors: dict[str, str] | None = None, tenant: str | None = None) -> dict[str, Any]:
    """The productSet input. `photos`: one {"originalSource"} (a new upload) or {"id"} (a photo already on the
    product) per gallery photo, in order; alt is set here. `rows`: the review rows (reviews())."""
    en = English(translated)
    prepared = {**prepared, "product": _twins(prepared["product"], en)}
    product, source = prepared["product"], prepared["source"]
    title, brand = title_vendor(product, en, vendors, tenant)
    options, values_en = _options(product, en)
    variants = _variants(prepared, options, values_en, pricing, location_id)
    personal, (extra, extra_all, must) = personalization(prepared, en), addons(prepared, en, pricing)
    for r in product.get("reviews") or []:
        en("review", r.get("text_ko"))
    en.check()
    product_type, tags = _placement(placement)
    files = []
    for n, photo in enumerate(photos, 1):
        f = dict(photo)
        if "originalSource" in f:
            f["contentType"] = "IMAGE"
        f["alt"] = alt(brand, title, n)
        files.append(f)
    base = product.get("pricing") or {}
    metafields = [
        {"namespace": "fairwardgolf", "key": "source_offer_id", "type": "single_line_text_field",
         "value": prepared["key"]},
        {"namespace": "fairwardgolf", "key": "source_url", "type": "url", "value": source["link"].split("?")[0]},
        {"namespace": "fairwardgolf", "key": "source", "type": "json", "value": _json({
            "schemaVersion": "fairwardgolf-source/1", "platform": "naver", "key": prepared["key"],
            "url": source["link"].split("?")[0], "channelNo": source.get("channel_no"),
            "productId": source.get("product_id"), "categoryId": source.get("category_id"),
            "run": source.get("run"), "titleKo": product["title_ko"], "brandKo": product.get("brand_ko"),
            "priceKrw": base.get("base_krw"), "originalPriceKrw": base.get("original_krw")})},
        {"namespace": "fairwardgolf", "key": "pricing", "type": "json", "value": _json({
            "schemaVersion": "fairwardgolf-pricing/1", **pricing.describe()})},
    ]
    rating = product.get("rating") or {}
    if rating.get("count"):
        metafields += [
            {"namespace": "custom", "key": "review", "type": "rating",
             "value": _json({"scale_min": "1.0", "scale_max": "5.0", "value": f"{float(rating['value']):.1f}"})},
            {"namespace": "custom", "key": "rating_count", "type": "number_integer", "value": str(rating["count"])}]
    if rows:
        metafields.append({"namespace": "custom", "key": "reviews_seo", "type": "json",
                           "value": _json(reviews_seo(rows))})
    if feed_url:
        metafields.append({"namespace": "custom", "key": "reviews_feed_url", "type": "url", "value": feed_url})
    if personal:
        metafields.append({"namespace": "custom", "key": "personalization_fields", "type": "json",
                           "value": _json(personal)})
    if extra:
        metafields.append({"namespace": "custom", "key": "optional_addons", "type": "json", "value": _json(extra)})
    if must:
        metafields.append({"namespace": "custom", "key": "required_selections", "type": "json", "value": _json(must)})
    if extra_all:
        metafields.append({"namespace": "fairwardgolf", "key": "addons", "type": "json", "value": _json(extra_all)})
    return {
        "title": title, "handle": handle_override or handle(title, brand), "vendor": brand,
        "productType": product_type, "tags": tags, "status": "ACTIVE", "descriptionHtml": "",
        "seo": {"title": fit_title(title, SEO_TITLE_MAX), "description": ""},            # the site's <title> (2026-11-09: "Fairward Golf |
                                                                     # Fairward Golf" on every product page)
        "productOptions": options, "variants": variants, "files": files, "metafields": metafields,
    }


# The metafields this module writes when the product has them; on an update one the product no longer has is
# deleted (productSet adds and updates metafields, it never removes one).
MANAGED = (("custom", "review"), ("custom", "rating_count"), ("custom", "reviews_seo"), ("custom", "reviews_feed_url"),
           ("custom", "personalization_fields"), ("custom", "optional_addons"), ("custom", "required_selections"),
           ("fairwardgolf", "addons"))


def stale(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """The managed metafields this payload does not set (to delete on an update)."""
    have = {(m["namespace"], m["key"]) for m in payload["metafields"]}
    return [k for k in MANAGED if k not in have]


def digest(value: Any) -> str:
    """The sha256 of a payload, to skip a product whose Shopify data did not change."""
    return hashlib.sha256(_json(value).encode()).hexdigest()
