"""Publication: a shop's prepared + translated + placed products -> its Shopify store (the owner, 2026-11-08, MVP).

    .venv/bin/python scripts/publish.py fairwardgolf                     # every product ready and not published
    .venv/bin/python scripts/publish.py fairwardgolf --only <key> [--only <key>] [--force] [--dry-run]
    .venv/bin/python scripts/publish.py fairwardgolf --shops-root scripts/output/trial-20261108/shops
    .venv/bin/python scripts/publish.py fairwardgolf --withdraw <ref> --reason "..." --dry-run   # names the key only

A product is named by its key, Naver product id, handle or link (shop_view.resolve; a full key as it is), in
--only / --withdraw / --restore / --activate; --keys-file F and --job ID [--event E] add more, to the action given
(a bare --withdraw / --restore / --activate takes only those). A ref that names several products, or none in a
store action, stops the command before anything is sent (exit 2, the candidates listed); an --only ref that names
none is "not ready" and skipped, as before. An empty ref (`--only "$KEY"` with KEY unset), keys file path, --job or
--event is a usage error (exit 2), never "every product". With --dry-run a withdraw, restore or activate prints per
key what it would do from the ledger ("would withdraw", or "not published here" / "not withdrawn here" / "not a
draft here"; exit 1 when a withdraw or restore would refuse one) and sends nothing (2026-11-16; before, --dry-run
did not stop them).

A product is published when it is `ready` (transform), `translated` (translate.py) and `placed` (placement.py). Per
product, in this order (shopify_payload.py builds, shopify_admin.py sends):
  1. the reviews' photos and avatars -> Shopify Files (the files app), once per file (named by its hash);
  2. the review rows -> a JSON feed file on Shopify's CDN, its link in custom.reviews_feed_url;
  3. the gallery photos -> staged uploads, attached to the product in productSet (alt "<brand> <title> - photo N");
     a product with fewer than 2 photos of its own gets buyers' photos after them, 5 in all at most
     (shopify_payload.review_gallery, ranked by review_rank);
  4. productSet: create, or update the product that has its source key (fairwardgolf.source_offer_id); a create is
     ACTIVE, or DRAFT when its Naver category is not marked reviewed (transform_shops.reviewed; draft first,
     2026-11-16); an update of a draft sends no status (the store keeps its own);
     the body (descriptionHtml) is the product's description when describe.py wrote one, empty otherwise;
  5. published to every sales channel of the store (the owner, 2026-11-09); one line in
     shops/<shop>/publish/published.jsonl (a draft: `published` with store_status DRAFT).

A product whose inputs did not change since its last publication is skipped (`--force` sends it again), and so is
one whose productSet would send what it sent last time (`output` in the ledger, output_digest; 2026-11-11). On an update
photos already on the product are kept by their hash (no new upload). `--withdraw <key> --reason "..."` takes a
published product off the store (DRAFT, nothing deleted) and keeps it from being sent again; `--restore` puts it back
as it was (ACTIVE, or DRAFT for a draft). `--activate <key>` puts a draft live (ACTIVE) on the owner's word after the
lens review (job.py activate --job does a job's drafts). --dry-run builds and writes the payload to
shops/<shop>/publish/payloads/<id>.json and sends nothing (no upload, no write).
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

import describe
import shopify_payload as sp
import transform_shops
from shop_files import append_line, locked, read_jsonl
from shop_pricing import policy
from shop_stores import get_store
from shop_types import LedgerPhoto, LedgerRow
from shop_view import add_ref_flags, keys_from_args, selection_asked
from shopify_catalog import CatalogError

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
FORMAT = "published/1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# A file read once per process while it does not change (its mtime and size): publish_one read the shop's prepared,
# translated, placement and description files for every product, 0.6 s each (2026-11-16: store_diff of 2,015
# products took over 20 minutes, 1.7 million JSON lines parsed per 100 products). An appended ledger is read again.
_MEMO: dict[str, tuple[tuple[int, int], Any]] = {}


def _memo(path: str, load: Any) -> Any:
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return load(path)
    stamp = (st.st_mtime_ns, st.st_size)
    hit = _MEMO.get(path)
    if hit is None or hit[0] != stamp:
        hit = _MEMO[path] = (stamp, load(path))
    return hit[1]


APPENDED = ("published.jsonl", "files.jsonl")      # only an appended file may end in a cut-off line (shop_files)


def _read_last(path: str) -> dict[str, dict[str, Any]]:
    """A bad line is a LedgerError naming <path>:<n> (2026-11-16: the ledger, prepared, translated and placements
    are read strictly; the ledger and files.jsonl forgive a cut-off last line, a run killed while appending)."""
    out: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path, tail_ok=os.path.basename(path) in APPENDED):
        out[row["key"]] = row
    return out


def _last(path: str) -> dict[str, Any]:
    """The last line per key of a JSON-lines file ({} when it does not exist); shared, read only for the callers.
    The ledger's rows are shop_types.LedgerRow."""
    return _memo(path, _read_last)


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _photo(path: str) -> dict[str, Any]:
    """{sha256, width, height, green} of a local photo: green is the share of grass-green pixels (a course, a range
    mat, a screen-golf floor; shopify_payload.GALLERY_MAX_GREEN). Unreadable: 0 x 0, the payload does not judge it."""
    out: dict[str, Any] = {"sha256": _sha(path), "width": 0, "height": 0}
    try:
        from PIL import Image
        with Image.open(path) as im:
            out["width"], out["height"] = im.size
            px = im.convert("HSV").resize((64, 64)).tobytes()
        hsv = [px[i:i + 3] for i in range(0, len(px), 3)]
        out["green"] = round(sum(1 for h, s, v in hsv if 51 < h < 115 and s > 64 and v > 51) / len(hsv), 3)
    except Exception:
        pass
    return out


def _append(path: str, row: Mapping[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    append_line(path, json.dumps(row, ensure_ascii=False))           # one write, after a line end (shop_files)


class Shop:
    """A shop's folders: what is ready to publish and what was published."""

    def __init__(self, shop: str, root: str = SHOPS_ROOT):
        self.shop, self.dir = shop, os.path.join(root, shop)
        self.ledger_path = os.path.join(self.dir, "publish", "published.jsonl")
        self.files_path = os.path.join(self.dir, "publish", "files.jsonl")
        self.skip_path = os.path.join(self.dir, "publish", "gallery_skip.txt")

    def gallery_skip(self) -> set[str]:
        """The sha256 of buyers' photos not to put in a gallery (one per line, "# why" after it; a box, a shop, a
        landscape: photos only a person can judge, checked on a contact sheet)."""
        if not os.path.exists(self.skip_path):
            return set()
        with open(self.skip_path, encoding="utf-8") as f:
            return {line.split("#")[0].strip() for line in f if line.split("#")[0].strip()}

    def inputs(self) -> tuple[dict, dict, dict]:
        return (_last(os.path.join(self.dir, "prepared", "products.jsonl")),
                _last(os.path.join(self.dir, "translation", "translated.jsonl")),
                _last(os.path.join(self.dir, "placement", "placements.jsonl")))

    def withdrawn(self) -> set[str]:
        """The products taken off the store by hand (`--withdraw`): never sent again until a later row says so."""
        return {k for k, r in _last(self.ledger_path).items() if r.get("status") == "withdrawn"}

    def ready(self) -> list[str]:
        prepared, translated, placed = self.inputs()
        gone = self.withdrawn()
        return [k for k, p in prepared.items() if p.get("status") == "ready" and k not in gone
                and (translated.get(k) or {}).get("status") == "translated"
                and (placed.get(k) or {}).get("status") == "placed"]

    def not_ready(self, key: str) -> str | None:
        """The gate of `ready` that `key` fails, in its order (withdrawn, prepared, translation, placement), None for
        a ready product (2026-11-18, the chipper scroll: a job's "placement placed: None" said nothing of the real
        gate, a product replaced and withdrawn)."""
        prepared, translated, placed = self.inputs()
        if key in self.withdrawn():
            return f"withdrawn ({_last(self.ledger_path)[key].get('reason') or 'no reason'})"
        p = prepared.get(key) or {}
        if p.get("status") != "ready":
            held = [h.get("code") for h in p.get("held") or []]
            return f"prepared {p.get('status')}" + (f" {held}" if held else "")
        t = translated.get(key) or {}
        if t.get("status") != "translated":
            return f"translation {t.get('status')}"
        pl = placed.get(key) or {}
        if pl.get("status") != "placed":
            return f"placement {pl.get('status')}: {pl.get('reason')}"
        return None

    def ledger(self) -> dict[str, LedgerRow]:
        return {k: r for k, r in _last(self.ledger_path).items() if r.get("status") == "published"}

    def file_urls(self) -> dict[str, str]:
        return {r["sha256"]: r["url"] for r in _last(self.files_path).values()}

    def path(self, rel: str) -> str:
        return os.path.join(self.dir, rel)


def inputs_digest(prepared: dict, translated: dict, placement: dict, shop: str, gallery: list | None = None,
                  description: str | None = None) -> str:
    """`gallery`: the buyers' photos chosen for the gallery (a photo struck out in gallery_skip.txt changes it).
    `description`: the product's description HTML (describe.py). It enters the digest only when the product has
    one, so a product without a description keeps the digest it was published with (2026-11-10: adding the key
    for every product would send the whole shop again)."""
    inputs = {"prepared": prepared, "en": translated.get("en"), "placement": placement,
              "pricing": policy(shop).describe(), "format": FORMAT, "payload": sp.VERSION, "gallery": gallery or []}
    if description:
        inputs["description"] = description
    return sp.digest(inputs)


def restore(shop: Shop, key: str, products: Any, reason: str) -> dict[str, Any]:
    """Undo a withdrawal (the owner, 2026-11-15: the no-brand agency imports withdrawn on 2026-11-12/14 go back under
    the shop's name): the product is ACTIVE again and the ledger takes its last published row once more, with no
    digest, so the next publication sends it with today's data (the same product, its photos kept). A draft that was
    withdrawn is restored a draft (2026-11-16: restore never puts a product not yet reviewed live)."""
    before = _last(shop.ledger_path).get(key)
    if not before or before.get("status") != "withdrawn":
        raise SystemExit(f"{key}: not withdrawn here")
    published = None
    for row in read_jsonl(shop.ledger_path, tail_ok=True):
        if row.get("key") == key and row.get("status") == "published":
            published = row
    if published is None:
        raise SystemExit(f"{key}: no published row to restore")
    status = products.set_status(before["product_id"],
                                 "DRAFT" if published.get("store_status") == "DRAFT" else "ACTIVE")
    row = {**published, "digest": "", "at": _now(), "restored": reason, "store_status": status}
    _append(shop.ledger_path, row)
    return row


def activate(shop: Shop, key: str, products: Any) -> LedgerRow | None:
    """A draft (store_status DRAFT, draft first) live: ACTIVE, on the owner's word after the lens review (2026-11-16).
    The ledger takes its row again with store_status ACTIVE and `activated`; digest, output and photos stay, so
    nothing is sent again. -> the row, or None for a key that is not a published draft here (no call, no line)."""
    before = shop.ledger().get(key)
    if not before or before.get("store_status") != "DRAFT":
        return None
    status = products.set_status(before["product_id"], "ACTIVE")
    row: LedgerRow = {**before, "store_status": status, "activated": _now()}
    _append(shop.ledger_path, row)
    return row


def withdraw(shop: Shop, key: str, products: Any, reason: str) -> dict[str, Any]:
    """Take a published product off the store: DRAFT (off every sales channel, nothing deleted; the owner,
    2026-11-11: a bag alone and a toy in the junior clubs). The ledger row `withdrawn` keeps publish.py from sending
    it again; the store keeps it, so the listing's screen still finds it as already published."""
    before = _last(shop.ledger_path).get(key)
    if not before or before.get("status") not in ("published", "withdrawn"):
        raise SystemExit(f"{key}: not published here")
    status = products.set_status(before["product_id"], "DRAFT")
    row: dict[str, Any] = {**{k: before[k] for k in ("format", "key", "product_id", "handle", "admin_url")
                              if k in before},
           "status": "withdrawn", "store_status": status, "reason": reason, "at": _now()}
    _append(shop.ledger_path, row)
    return row


def output_digest(payload: dict[str, Any]) -> str:
    """The sha256 of what a product's productSet sends, built with each photo as its file's hash and the reviews'
    feed as its content's hash (no upload, no link, no handle: an update keeps the handle it has). Two runs that
    would send the same agree on it, whatever else changed in the inputs (2026-11-11: inputs_digest moved on 18 of
    20 products whose Shopify data stood still, and hid the two that did change)."""
    return sp.digest({k: v for k, v in payload.items() if k != "handle"})


def gallery(shop: "Shop", prepared: dict[str, Any]) -> list[dict[str, Any]]:
    """The buyers' photos that follow the product's own ([{file, sha256}], shopify_payload.review_gallery), with
    each candidate photo read here (hash, size, the share of green) and the shop's struck-out list applied."""
    if len(prepared["product"].get("images") or []) >= sp.GALLERY_MIN:
        return []
    info = {rel: _photo(shop.path(rel)) for r in prepared["product"].get("reviews") or []
            for rel in r.get("photos") or [] if sp.review_rank(r) is not None}
    skip_sha = shop.gallery_skip()
    skip = {rel for rel, meta in info.items() if meta["sha256"] in skip_sha}
    return [{"file": rel, "sha256": info[rel]["sha256"]} for rel in sp.review_gallery(prepared, info, skip)]


# A photo's file name carries its content's hash ("fairwardgolf-12211893510-007-73e48f31ce6df744.webp"); Shopify
# adds "_<uuid>" to a name it already holds.
_MEDIA_SHA = re.compile(r"-([0-9a-f]{16})(?:_[0-9a-f-]+)?\.[a-z]+(?:\?|$)")


def _unique(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each photo once (12211893510, 2026-11-12: the seller's gallery held its first photo twice; Shopify kept it
    once, the ledger paired the photos with the media by position, and the next update sent every media id one
    place off: the store lost the first photo and showed the putter twice)."""
    seen: set[str] = set()
    out = []
    for img in images:
        if img["sha256"] not in seen:
            seen.add(img["sha256"])
            out.append(img)
    return out


def _sha16(media: dict[str, Any]) -> str | None:
    found = _MEDIA_SHA.search(((media.get("image") or {}).get("url") or "").split("/")[-1])
    return found.group(1) if found else None


def _on_store(product: dict[str, Any], images: list[dict[str, Any]]) -> dict[str, str]:
    """{photo sha256: the store's media id} for the photos the store holds, read from its media's file names; a
    media whose name carries no hash, or a second media of one photo, is left out (productSet then drops it)."""
    by16 = {img["sha256"][:16]: img["sha256"] for img in images}
    out: dict[str, str] = {}
    for m in product.get("media", {}).get("nodes") or []:
        sha = by16.get(_sha16(m) or "")
        if sha and sha not in out and m.get("status") != "FAILED":
            out[sha] = m["id"]
    return out


def _ledger_photos(images: list[dict[str, Any]], media: list[dict[str, Any]]) -> list[LedgerPhoto]:
    """The ledger's photos: each media paired with its photo by the hash in its file name, by position when a name
    carries none."""
    out: list[LedgerPhoto] = []
    by16 = {img["sha256"][:16]: img["sha256"] for img in images}
    for i, m in enumerate(media):
        if m["status"] == "FAILED":
            continue
        sha = by16.get(_sha16(m) or "") or (images[i]["sha256"] if i < len(images) else None)
        if sha and all(p["sha256"] != sha for p in out):
            out.append({"sha256": sha, "media_id": m["id"]})
    return out


def publish_one(shop: Shop, key: str, products: Any, files: Any, ids: dict[str, Any], force: bool = False,
                dry_run: bool = False, rehandle: bool = False, draft: bool = False) -> Mapping[str, Any]:
    """One product to Shopify -> its ledger row (status published, a LedgerRow), the last one (status skipped), or
    what a dry run built (status dry-run: payload, handle, output, product_id, feed_sha, images)."""
    prepared_all, translated_all, placed_all = shop.inputs()
    prepared, translated, placement = prepared_all[key], translated_all.get(key) or {}, placed_all.get(key) or {}
    extra = gallery(shop, prepared)
    store = _memo(os.path.join(shop.dir, "translation", describe.STORE), lambda _: describe.load_store(shop.dir))
    description = (store.get(key) or {}).get("html") or ""
    digest = inputs_digest(prepared, translated, placement, shop.shop, extra, description)
    before: Mapping[str, Any] | None = shop.ledger().get(key)
    if before and before.get("digest") == digest and not force and not dry_run and not rehandle:
        return {**before, "status": "skipped"}
    pricing, pid = policy(shop.shop), prepared["source"]["product_id"]
    sp.product_input(prepared, translated, placement, pricing, "check", [], None, None, "check")   # nothing sent
                                                    # before the product builds (Untranslated / PayloadError)

    # 1-2. the reviews' files and feed (the files app)
    known = shop.file_urls()
    shas = {rel: _sha(shop.path(rel)) for rel in sp.review_files(prepared)}
    new = {rel: sha for rel, sha in shas.items() if sha not in known}
    if new and not dry_run:                         # all at once: staged in parallel, created and polled together
        by_name = {os.path.basename(rel): rel for rel in new}
        created = files.create_many([(shop.path(rel), name, True) for name, rel in by_name.items()])
        for name, rel in by_name.items():
            known[new[rel]] = created[name]
            _append(shop.files_path, {"key": new[rel], "sha256": new[rel], "file": rel, "url": created[name],
                                      "at": _now()})
    urls = {rel: known.get(sha, f"dry-run:{rel}") for rel, sha in shas.items()}
    en = sp.English(translated)
    rows = sp.reviews(prepared, en, urls)
    body = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
    feed_sha = hashlib.sha256(body).hexdigest()[:24] if rows else None
    images = _unique(list(prepared["product"].get("images") or []) + extra)
    output = output_digest(sp.product_input(
        prepared, translated, placement, pricing, "check", [{"id": img["sha256"]} for img in images],
        f"sha:{feed_sha}" if feed_sha else None, rows, handle_override="check", vendors=ids.get("vendors"),
        tenant=ids.get("tenant"), description_html=description))
    if before and before.get("output") == output and not new and not force and not dry_run and not rehandle:
        return {**before, "status": "skipped"}             # what Shopify would get is what it has
    feed_url = None
    if rows:
        name = f"{shop.shop}-reviews-{pid}-{feed_sha}.json"
        local = shop.path(os.path.join("publish", "payloads" if dry_run else "feeds", name))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        with open(local, "wb") as f:
            f.write(body)
        feed_url = f"dry-run:{name}" if dry_run else files.create(local, name, image=False)

    # 3. the product to update (the ledger, the shop's source keys, or the product that already has its handle and
    #    key: a create that failed after productSet), its handle (a new one avoids another product's), the photos
    product_id = (before or {}).get("product_id") or (None if dry_run else products.keys().get(key))
    title, vendor = sp.title_vendor(prepared["product"], en, ids.get("vendors"), ids.get("tenant"))
    handle = (None if rehandle else (before or {}).get("handle")) or sp.handle(title, vendor)
    if (not product_id or rehandle) and not dry_run:
        n, base = 2, handle
        while (owner := products.handle_owner(handle)) is not None:
            if owner[1] == key:
                product_id = product_id or owner[0]
                break
            handle, n = f"{base}-{n}", n + 1
    on_product = {p["sha256"]: p["media_id"] for p in (before or {}).get("photos") or []} if product_id else {}
    if product_id and not dry_run:                  # the store's own media, by the hash in their file names: the
        on_product = _on_store(products.media_ready(product_id), images) or on_product   # ledger can be wrong
    upload = [img for img in images if img["sha256"] not in on_product]
    staged = dict(zip((img["file"] for img in upload), [f"dry-run:{img['file']}" for img in upload] if dry_run else
                      products.stage_many([(shop.path(img["file"]), "IMAGE", None) for img in upload])))
    photos = [{"id": on_product[img["sha256"]]} if img["sha256"] in on_product else
              {"originalSource": staged[img["file"]]} for img in images]

    # 4. the product (an update keeps the handle it has in the shop)
    payload = sp.product_input(prepared, translated, placement, pricing, ids.get("location", "dry-run:location"),
                               photos, feed_url, rows, handle_override=handle, vendors=ids.get("vendors"),
                               tenant=ids.get("tenant"), description_html=description)
    if product_id and not rehandle:
        del payload["handle"]
    elif product_id:
        payload["redirectNewHandle"] = True             # the old address keeps working
    # draft first (2026-11-16): a product of a category not marked reviewed is created DRAFT, for the lens review and
    # the owner's activation; an update of a draft sends no status, so one activated in the admin stays live. After
    # output (built with ACTIVE): the status never moves a digest, nothing is sent again for it
    if (before or {}).get("store_status") == "DRAFT":
        del payload["status"]
    # draft: a job's own products created DRAFT in any category (job.py --draft, the owner 2026-11-16: a pilot in a
    # reviewed category the owner activates after the lens review)
    elif not before and (draft or not transform_shops.reviewed(shop.shop, prepared["source"].get("category_id"))):
        payload["status"] = "DRAFT"
    if dry_run:
        out = shop.path(os.path.join("publish", "payloads", f"{pid}.json"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        return {"key": key, "status": "dry-run", "payload": out, "handle": handle, "output": output,
                "product_id": product_id, "feed_sha": feed_sha, "images": [img["sha256"] for img in images]}
    product = products.product_set(payload, product_id)
    if product_id:                                  # productSet never removes a metafield: drop what is gone
        products.delete_metafields(product["id"], sp.stale(payload))
    product = {**product, **products.media_ready(product["id"])}
    products.publish(product["id"], ids["publications"])
    media = product["media"]["nodes"]
    failed = [m["id"] for m in media if m["status"] == "FAILED"]
    row: LedgerRow = {"format": FORMAT, "key": key, "status": "published", "at": _now(),
           "digest": None if failed else digest,                  # a failed photo: the next run sends it again
           "output": None if failed else output,
           "product_id": product["id"], "handle": product["handle"], "created": not product_id,
           "photos": _ledger_photos(images, media),
           "photos_failed": failed, "reviews": len(rows), "feed_url": feed_url,
           "pricing": pricing.describe()["version"], "prices_usd": prices_of(payload),
           "admin_url": f"https://admin.shopify.com/store/{products.shop.domain.split('.')[0]}/products/"
                        f"{product['id'].rsplit('/', 1)[-1]}",
           "preview_url": product.get("onlineStorePreviewUrl")}
    status = product.get("status") or payload.get("status") or (before or {}).get("store_status")
    if status and status != "ACTIVE":                    # the ledger's shape as before for a live product
        row["store_status"] = status
    _append(shop.ledger_path, row)
    if ids.get("vendors") is not None and payload.get("vendor"):    # the next products of this run spell it so
        ids["vendors"].setdefault(sp.brand_key(payload["vendor"]), payload["vendor"])
    return row


def prices_of(payload: dict[str, Any]) -> list[int]:
    """The lowest and the highest variant price a payload sends, whole dollars (the ledger keeps them, so a new
    price rule can show what it changes: reprice.py)."""
    prices = [int(float(v["price"])) for v in payload["variants"]]
    return [min(prices), max(prices)]


def vendor_spellings(store: dict[str, str], brands: list[str] | None = None) -> dict[str, str]:
    """{brand_key: spelling}: the first spelling a brand was known by stays, compared without case, dots or spaces
    (the owner, 2026-11-17: "whichever came first stays, upper or lower case"): the store's oldest spelling
    (shopify_admin's order), then the brand dictionary's for a brand the store does not have yet (its first value:
    translation_dicts.brand_spelling), then the model's (a run remembers each new vendor for its next products).
    Before 2026-11-17 the dictionary came first and a dictionary entry written later in another case changed a live
    vendor (9951345559 KIRKLAND -> Kirkland). `brands`: the brand dictionary's values when the caller has them
    loaded (sweep.py's read-only copy; Dictionaries() may write the live file)."""
    from translation_dicts import Dictionaries
    out: dict[str, str] = {}
    for v in store.values():                         # the store's first spelling of a brand (oldest product first)
        out.setdefault(sp.brand_key(v), v)
    if brands is None:
        try:
            brands = list(Dictionaries().entries.get("brand", {}).values())
        except Exception:                                   # no dictionary: the shop's spellings only
            brands = []
    for v in brands:
        out.setdefault(sp.brand_key(sp.vendor_name(v)), sp.vendor_name(v))
    return out


def offline_ids(shop: str) -> dict[str, Any]:
    """What a dry run knows without the store: the brand dictionary's vendor spellings and the tenant's name, so its
    payload spells the vendor and the title as the real run does (2026-11-11: without them a dry run wrote "maruman"
    for Maruman and put "Fairward Golf" before a title of the shop's own brand, and read as a regression). The
    shop's own spellings of brands the dictionary lacks come only with the store."""
    return {"vendors": vendor_spellings({}), "tenant": get_store(shop).publisher}


def clients(shop: str) -> tuple[Any, Any, dict[str, Any]]:
    from shopify_admin import FilesAdmin, ProductsAdmin
    store = get_store(shop)
    products, files = ProductsAdmin(store), FilesAdmin(store)
    products.check_shop()
    files.check_shop()
    ids = {"publications": products.publication_ids(), "location": products.location_id(),
           "vendors": vendor_spellings(products.vendor_spellings()), "tenant": store.publisher}
    return products, files, ids


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("shop")
    ap.add_argument("--only", action="append", default=[], help="a product: its key, Naver product id, handle or "
                    "link (repeat for several)")
    ap.add_argument("--shops-root", default=SHOPS_ROOT, help="the folder holding <shop>/")
    ap.add_argument("--force", action="store_true", help="send even when nothing changed")
    ap.add_argument("--dry-run", action="store_true", help="build and save the payload; send nothing")
    ap.add_argument("--withdraw", action="append", default=[], nargs="?", const="",
                    help="a published product's key: set it DRAFT and never send it again (with --reason)")
    ap.add_argument("--restore", action="append", default=[], nargs="?", const="",
                    help="a withdrawn product's key: ACTIVE again (a draft: DRAFT), sent with today's data by the "
                    "next run (with --reason)")
    ap.add_argument("--activate", action="append", default=[], nargs="?", const="",
                    help="a draft's key (a category not marked reviewed): ACTIVE, on the owner's word after the lens "
                    "review (repeat for several)")
    ap.add_argument("--reason", help="why a product is withdrawn or restored (kept in the ledger)")
    ap.add_argument("--rehandle", action="store_true", help="give a product already in the shop the handle its "
                    "title makes now (the old one redirects)")
    add_ref_flags(ap)
    args = ap.parse_args(argv)
    shop = Shop(args.shop, args.shops_root)
    action = next((a for a in ("activate", "restore", "withdraw") if getattr(args, a)), "only")
    given = getattr(args, action)
    named = [r for r in given if r.strip()]
    if action == "only" and len(named) < len(given):        # `--only "$KEY"` with KEY unset: never "every product"
        ap.error("--only: an empty ref")
    if action != "only" and named and len(named) < len(given):
        ap.error(f"--{action}: an empty ref among the products")   # a bare --{action} goes with --keys-file / --job
    if action != "only" and not (named or selection_asked(args)):
        ap.error(f"--{action}: a product (a ref, --keys-file or --job)")
    if action == "only" and not (named or selection_asked(args)):
        args.only = []
    else:            # refs -> keys; a full key as it is (known or not, as before); --only: a ref matching nothing is
        setattr(args, action, keys_from_args(ap, args, args.shop, named, args.shops_root,   # kept, "not ready"
                                             unknown_ok=action == "only"))
    if action in ("withdraw", "restore") and not args.reason:
        ap.error(f"--{action} needs --reason")
    if args.dry_run and action != "only":         # a store action sends at once: --dry-run says what it would do
        return _dry_store_action(shop, action, getattr(args, action))
    if args.activate:
        from shopify_admin import ProductsAdmin
        admin = ProductsAdmin(get_store(args.shop))
        admin.check_shop()
        failed = 0
        for key in args.activate:                  # one refused key does not stop the others (as job.py activate)
            try:
                got = activate(shop, key, admin)
            except CatalogError as e:
                failed += 1
                print(f"{key}: failed: {e}"[:300])
                continue
            print(f"{key}: activated ({got['store_status']}) {got.get('admin_url', '')}" if got else
                  f"{key}: not a draft here")
        return 1 if failed else 0
    if args.restore:
        if not args.reason:
            ap.error("--restore needs --reason")
        from shopify_admin import ProductsAdmin
        admin = ProductsAdmin(get_store(args.shop))
        admin.check_shop()
        for key in args.restore:
            row = restore(shop, key, admin, args.reason)
            print(f"{key}: restored ({row['store_status']}) {row.get('admin_url', '')}")
        return 0
    if args.withdraw:
        if not args.reason:
            ap.error("--withdraw needs --reason")
        from shopify_admin import ProductsAdmin
        admin = ProductsAdmin(get_store(args.shop))
        admin.check_shop()
        for key in args.withdraw:
            row = withdraw(shop, key, admin, args.reason)
            print(f"{key}: withdrawn ({row['store_status']}) {row.get('admin_url', '')}")
        return 0
    if args.dry_run:                                # sends nothing: no lock (a job may run meanwhile)
        return _publish(args, shop)
    # sending: refused while a job of the shop runs (two processes could create one product twice)
    return locked(args.shops_root, args.shop, "publish.py", lambda: _publish(args, shop), "publish")


def _dry_store_action(shop: Shop, action: str, keys: list[str]) -> int:
    """--dry-run with --withdraw / --restore / --activate: per key what the real call would do, from the ledger (the
    same tests as withdraw / restore / activate), nothing sent. Exit 1 when a withdraw or restore would refuse a key
    (the real call stops there), else 0 (activate passes over a key that is not a draft, as the real call does)."""
    last = _last(shop.ledger_path)
    drafts = {k for k, r in shop.ledger().items() if r.get("store_status") == "DRAFT"}
    refused = 0
    for key in keys:
        before: dict[str, Any] = last.get(key) or {}
        if action == "withdraw":
            ok, no = before.get("status") in ("published", "withdrawn"), "not published here"
        elif action == "restore":
            ok, no = before.get("status") == "withdrawn", "not withdrawn here"
        else:                                       # a published draft (a withdrawn row is DRAFT too: not one)
            ok, no = key in drafts, "not a draft here"
        refused += not ok and action != "activate"
        print(f"{key}: would {action} (dry run: nothing sent)" if ok else f"{key}: {no} (dry run)")
    return 1 if refused else 0


def _publish(args: argparse.Namespace, shop: Shop) -> int:
    ready = shop.ready()
    keys = [k for k in args.only if k in ready] if args.only else ready
    for k in set(args.only) - set(ready):
        print(f"{k}: not ready (needs prepared ready, translated, placed)", file=sys.stderr)
    products = files = None
    ids: dict[str, Any] = offline_ids(args.shop)
    if not args.dry_run and keys:
        products, files, ids = clients(args.shop)
    counts: dict[str, int] = {}
    for key in keys:
        try:
            row = publish_one(shop, key, products, files, ids, force=args.force, dry_run=args.dry_run,
                              rehandle=args.rehandle)
        except (sp.Untranslated, sp.PayloadError) as e:
            row = {"key": key, "status": "held", "reason": f"{type(e).__name__}: {e}"}
        except CatalogError as e:                       # Shopify refused (userErrors, a file not ready ...)
            row = {"key": key, "status": "failed", "reason": str(e)[:500]}
        counts[row["status"]] = counts.get(row["status"], 0) + 1
        print(f"{key}: {row['status']} {row.get('handle') or ''} {row.get('admin_url') or row.get('payload') or ''}"
              f"{' ' + row['reason'] if row.get('reason') else ''}")
    print(f"publish {args.shop}: {len(keys)} products: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
