"""Publication: a shop's prepared + translated + placed products -> its Shopify store (the owner, 2026-11-08, MVP).

    .venv/bin/python scripts/publish.py fairwardgolf                     # every product ready and not published
    .venv/bin/python scripts/publish.py fairwardgolf --only <key> [--only <key>] [--force] [--dry-run]
    .venv/bin/python scripts/publish.py fairwardgolf --shops-root scripts/output/trial-20261108/shops

A product is published when it is `ready` (transform), `translated` (translate.py) and `placed` (placement.py). Per
product, in this order (shopify_payload.py builds, shopify_admin.py sends):
  1. the reviews' photos and avatars -> Shopify Files (the files app), once per file (named by its hash);
  2. the review rows -> a JSON feed file on Shopify's CDN, its link in custom.reviews_feed_url;
  3. the gallery photos -> staged uploads, attached to the product in productSet (alt "<brand> <title> - photo N");
     a product with fewer than 2 photos of its own gets buyers' photos after them, 5 in all at most
     (shopify_payload.review_gallery, ranked by review_rank);
  4. productSet: create, or update the product that has its source key (fairwardgolf.source_offer_id); ACTIVE;
     the body (descriptionHtml) is the product's description when describe.py wrote one, empty otherwise;
  5. published to every sales channel of the store (the owner, 2026-11-09); one line in
     shops/<shop>/publish/published.jsonl.

A product whose inputs did not change since its last publication is skipped (`--force` sends it again), and so is
one whose productSet would send what it sent last time (`output` in the ledger, output_digest; 2026-11-11). On an update
photos already on the product are kept by their hash (no new upload). `--withdraw <key> --reason "..."` takes a
published product off the store (DRAFT, nothing deleted) and keeps it from being sent again. --dry-run builds and writes the payload to
shops/<shop>/publish/payloads/<id>.json and sends nothing (no upload, no write).
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import describe
import shopify_payload as sp
from shop_pricing import policy
from shop_stores import get_store
from shopify_catalog import CatalogError

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SHOPS_ROOT = os.path.join(SCRIPTS, "output", "shops")
FORMAT = "published/1"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _last(path: str) -> dict[str, dict[str, Any]]:
    """The last line per key of a JSON-lines file ({} when it does not exist)."""
    out: dict[str, dict[str, Any]] = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    out[row["key"]] = row
    return out


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


def _append(path: str, row: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


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

    def ledger(self) -> dict[str, dict[str, Any]]:
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


def publish_one(shop: Shop, key: str, products: Any, files: Any, ids: dict[str, Any], force: bool = False,
                dry_run: bool = False, rehandle: bool = False) -> dict[str, Any]:
    """One product to Shopify -> its ledger row (status published / skipped / dry-run)."""
    prepared_all, translated_all, placed_all = shop.inputs()
    prepared, translated, placement = prepared_all[key], translated_all.get(key) or {}, placed_all.get(key) or {}
    extra = gallery(shop, prepared)
    description = (describe.load_store(shop.dir).get(key) or {}).get("html") or ""
    digest = inputs_digest(prepared, translated, placement, shop.shop, extra, description)
    before = shop.ledger().get(key)
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
    images = list(prepared["product"].get("images") or []) + extra
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
    row = {"format": FORMAT, "key": key, "status": "published", "at": _now(),
           "digest": None if failed else digest,                  # a failed photo: the next run sends it again
           "output": None if failed else output,
           "product_id": product["id"], "handle": product["handle"], "created": not product_id,
           "photos": [{"sha256": img["sha256"], "media_id": m["id"]} for img, m in zip(images, media)
                      if m["status"] != "FAILED"],
           "photos_failed": failed, "reviews": len(rows), "feed_url": feed_url,
           "pricing": pricing.describe()["version"], "prices_usd": prices_of(payload),
           "admin_url": f"https://admin.shopify.com/store/{products.shop.domain.split('.')[0]}/products/"
                        f"{product['id'].rsplit('/', 1)[-1]}",
           "preview_url": product.get("onlineStorePreviewUrl")}
    _append(shop.ledger_path, row)
    if ids.get("vendors") is not None and payload.get("vendor"):    # the next products of this run spell it so
        ids["vendors"].setdefault(sp.brand_key(payload["vendor"]), payload["vendor"])
    return row


def prices_of(payload: dict[str, Any]) -> list[int]:
    """The lowest and the highest variant price a payload sends, whole dollars (the ledger keeps them, so a new
    price rule can show what it changes: reprice.py)."""
    prices = [int(float(v["price"])) for v in payload["variants"]]
    return [min(prices), max(prices)]


def vendor_spellings(store: dict[str, str]) -> dict[str, str]:
    """{lower case: spelling}: the brand dictionary's spelling first, whatever the case of the shop's or the model's
    (the owner, 2026-11-09: PING stays PING, Yonex stays Yonex), then the shop's for a brand the dictionary does not
    have (2026-11-09: the run's map was read once from an empty shop)."""
    from translation_dicts import Dictionaries
    out: dict[str, str] = {}
    try:
        brands = list(Dictionaries().entries.get("brand", {}).values())
    except Exception:                                       # no dictionary: the shop's spellings only
        brands = []
    for v in brands:
        out.setdefault(sp.brand_key(sp.vendor_name(v)), sp.vendor_name(v))
    for v in store.values():                         # the store's first spelling of a brand (shopify_admin's order)
        out.setdefault(sp.brand_key(v), v)
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
    ap.add_argument("--only", action="append", default=[], help="a product key (repeat for several)")
    ap.add_argument("--shops-root", default=SHOPS_ROOT, help="the folder holding <shop>/")
    ap.add_argument("--force", action="store_true", help="send even when nothing changed")
    ap.add_argument("--dry-run", action="store_true", help="build and save the payload; send nothing")
    ap.add_argument("--withdraw", action="append", default=[], help="a published product's key: set it DRAFT and "
                    "never send it again (with --reason)")
    ap.add_argument("--reason", help="why a product is withdrawn (kept in the ledger)")
    ap.add_argument("--rehandle", action="store_true", help="give a product already in the shop the handle its "
                    "title makes now (the old one redirects)")
    args = ap.parse_args(argv)
    shop = Shop(args.shop, args.shops_root)
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
