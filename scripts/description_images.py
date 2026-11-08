"""Optional stage between keep_run and run_transform: read the text of a product's description images (RapidOCR)
into a sidecar file, for the categories whose transform rules switch it on (CategoryRules.description_images: off
by default, on for 50002788 golf full sets). The transform reads the sidecar offline (description_measures.py: size /
weight, the larger of that and today's value wins; description_image_text.py: clean Korean text for translation).

Per product (the newest kept line of each key, as run_transform takes it), one at a time:

  links     details.description.images, in order -> clean_images (seller banners by name / link / spacer / pixel
            out) -> the first SmartEditor image when lower than FIRST_HEADER_MAX (the store's header strip) -> GIFs
            out -> any public HTTPS host (the owner, 2026-11-07, AGENTS.md rule 3; never http, an IP, localhost, a
            name resolving to a private address) -> a SmartEditor link without its `?type=w848` (the original:
            w1280 / w2000 answer 404, research 2026-11-07) -> a link repeated in one body once
  sources   Naver first (the owner, 2026-11-07): a body Naver cut into snap tiles is read from the tiles, stitched;
            only when a tile does not read, from the seller's own images in its HTML (tile_sources: 7583123963 113
            tiles, 45 sources) when every source reads. A seller's host can be 5x slower (13369469193: 266 s vs 54
            s) and its proxy-smartstore links expire; the tiles carry the store's banners (cut from the text)
  reuse     an image another product of the store already read (same link, same engine) is copied from that
            sidecar, not fetched or read again (`reused`); a slice equal to one already read in the product (dHash)
            takes its rows
  download  naver_images.fetch (HTTPS, no redirects, MAX_BYTES, pace, retries); Naver's CDN answering 403 / 429
            stops the whole stage (CdnRefused, like a collection); a seller's host doing so fails that image only
            (`refused`); 5xx / network: `failed` (read again next run); 4xx / not an image: `gone` (an expired
            proxy-smartstore token: for good); smaller than MIN_SIDE: skipped `tiny`. Bytes cached per product
            under description_images/cache/<product id>/ (--prune-cache deletes them, the sidecars stay)
  OCR       description_ocr: slices (snap tiles stitched), RapidOCR, rows; in a fresh worker process per product
            (read_isolated: no memory build-up; a crash, a kill or PRODUCT_TIMEOUT is that product's error, one
            more try, then an error sidecar; Ctrl+C stops cleanly); one run per shop at a time (a lock)
  sidecar   scripts/output/shops/<shop>/description_images/<product id>.json
            {format, product_id, key, links_sha256, engine {name, version, onnxruntime, params}, images [{link,
            host, status, error?, reused?, width, height, bytes, slices [{y0, y1, rows [{text, conf, y}]}]}],
            skipped [{link, rule}], error?, seconds}
            A sidecar with the same links and engine is kept (resumable); --force rereads (also an error sidecar).

Cost (live 2026-11-07, 20 sets): ~20 s a product (13-100 s), the worker up to ~2.1 GB, the run ~50 MB.

    .venv/bin/python scripts/description_images.py fairwardgolf                 # every kept run
    .venv/bin/python scripts/description_images.py fairwardgolf --products 7583123963 13446843026
    .venv/bin/python scripts/description_images.py fairwardgolf --prune-cache [--products ...]   # free the disk
"""
import argparse
import fcntl
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import sys
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import description_ocr as ocr
from description_clean import _IMG_RE, _img_link, _image_key, _linkdata, clean_images
from keep_run import SHOPS_ROOT
from naver_images import RENDITION_HOSTS, CdnRefused, ImageError, allowed, fetch, new_session
from transform_shops import ShopRulesMissing, rules_for

FORMAT = "description_images/1"
PRODUCT_TIMEOUT = 900            # s for one product in its worker (the heaviest live product, 113 images: 167 s)
_RETRIABLE = re.compile(r"HTTP 5\d\d|Error|[Tt]imeout|timed out|reset|refused")


class StageBusy(Exception):
    """Another description_images run holds this shop's lock."""
FOLDER = "description_images"
FIRST_HEADER_MAX = 400          # px: a first SmartEditor image lower than this is the store's header strip
MIN_SIDE = 60                    # px: smaller is a counter, an icon or a spacer, never text worth reading


def sidecar_dir(shop: str, shops_root: str = SHOPS_ROOT) -> str:
    return os.path.join(shops_root, shop, FOLDER)


def load_sidecar(shop: str, product_id: str, shops_root: str = SHOPS_ROOT) -> dict[str, Any] | None:
    path = os.path.join(sidecar_dir(shop, shops_root), f"{product_id}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def current(sidecar: dict[str, Any] | None, line: dict[str, Any]) -> bool:
    """The sidecar was read from this line's description links (not from an older collection of the product)."""
    links, _ = pick_links(((line.get("details") or {}).get("description")) or {})
    return sidecar is not None and sidecar.get("links_sha256") == links_sha(links)


def image_rows(sidecar: dict[str, Any] | None, with_conf: bool = False) -> list[list[Any]]:
    """The OCR rows of each read image, in description order, normalised (the input of
    description_measures.read_rows); with_conf: (text, OCR confidence) pairs."""
    return [[(ocr.norm(r["text"]), r["conf"]) if with_conf else ocr.norm(r["text"])
             for s in img.get("slices") or [] for r in s["rows"]]
            for img in (sidecar or {}).get("images") or [] if img.get("status") == "read"]


def pick_links(description: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    """-> (links to fetch, [{link, rule}] skipped)."""
    cleaned = clean_images(description.get("images"), description.get("html"))
    skipped = [{"link": d["link"], "rule": d["rule"]} for d in cleaned["dropped"]]
    links: list[str] = []
    first = cleaned["images"][0] if cleaned["images"] else None
    data = _linkdata(description.get("html")).get(_image_key(first)) if first else None
    if data and 1 < int(data.get("originalHeight") or 0) < FIRST_HEADER_MAX:   # a SmartEditor body's opening
        skipped.append({"link": str(first), "rule": "first_header"})               # strip: the store's header
        cleaned = {**cleaned, "images": cleaned["images"][1:]}                 # (never useful, research)
    for link in dict.fromkeys(cleaned["images"]):         # a link repeated in one body is read once
        parts = urlsplit(link)
        if parts.path.lower().endswith(".gif"):
            skipped.append({"link": link, "rule": "gif"})
        elif not allowed(link, any_host=True):              # any public HTTPS host (the owner, 2026-11-07)
            skipped.append({"link": link, "rule": "not_https_public"})
        else:
            plain = link.split("?")[0] if parts.hostname in RENDITION_HOSTS and parts.query.startswith("type=") else link
            if plain not in links:
                links.append(plain)
    return links, skipped


def _cached_fetch(link: str, cache: str, session: Any, sleep: Callable[[float], None]) -> bytes:
    path = os.path.join(cache, hashlib.sha256(link.encode()).hexdigest()[:24] + ".bin")
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    _, _, data, _ = fetch(link, session, sleep, any_host=True)
    os.makedirs(cache, exist_ok=True)
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    return data


def tile_sources(description: dict[str, Any]) -> list[str]:
    """A tiled body's own pictures: Naver cuts an editor-less body into 945 x 1134 snap tiles, but the body's HTML
    keeps the seller's <img> links (7583123963: 113 tiles, 45 sources; on the 50 fixture sets 459 tiles, 92
    sources). The same filters as pick_links (banners, GIFs, hosts)."""
    srcs = [_img_link(tag) for tag in _IMG_RE.findall(description.get("html") or "")]
    links, _ = pick_links({"images": [u for u in srcs if u and not ocr.SNAP_RE.search(u)],
                           "html": description.get("html")})
    return links


def _fetch_all(links: list[str], fetcher: Callable[..., bytes], cache: str, session: Any,
               sleep: Callable[[float], None], known: dict[str, dict[str, Any]]) -> tuple[list, list, list]:
    """-> (image entries, [(link, bytes)] to OCR, skipped). An image another product of the store already read
    (same link, same engine: `known`) is taken from there, not fetched or read again (a store's banners and spec
    sheets repeat across its listings)."""
    images: list[dict[str, Any]] = []
    got: list[tuple[str, bytes]] = []
    skipped: list[dict[str, str]] = []
    for link in links:
        host = "naver" if (urlsplit(link).hostname or "").endswith(".pstatic.net") else "seller"
        if link in known:
            images.append({**known[link], "reused": True})
            continue
        try:
            data = fetcher(link, cache, session, sleep)
        except ImageError as e:
            # 5xx / network: "failed", read again next run; 4xx / not an image (an expired proxy-smartstore token,
            # a deleted file): "gone", for good (re-reading would fail the same way every run)
            status = "failed" if _RETRIABLE.search(str(e)) else "gone"
            images.append({"link": link, "host": host, "status": status, "error": str(e)[:300]})
            continue
        except CdnRefused as e:
            if host == "naver":
                raise                                # Naver's CDN refused us: stop the stage
            # a seller's host refusing a hotlink (shopping.c.yimg.jp 403, 2026-11-07): that image only, for good
            images.append({"link": link, "host": host, "status": "refused", "error": str(e)[:300]})
            continue
        try:
            im = ocr.open_rgb(data)
        except Exception as e:                       # noqa: BLE001  (a broken file fails that image only)
            images.append({"link": link, "host": host, "status": "gone", "error": f"not readable: {type(e).__name__}"})
            continue
        if im.width < MIN_SIDE or im.height < MIN_SIDE:   # a counter / icon / spacer a seller's host serves
            skipped.append({"link": link, "rule": "tiny"})
            continue
        images.append({"link": link, "host": host, "status": "read", "width": im.width, "height": im.height,
                       "bytes": len(data), "slices": []})
        got.append((link, data))
    return images, got, skipped


def read_product(line: dict[str, Any], engine: Any, cache: str, session: Any = None,
                 sleep: Callable[[float], None] = time.sleep,
                 fetcher: Callable[..., bytes] | None = None,
                 known: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """One collected line -> its sidecar. A tiled body is read from its tiles (Naver first), from the seller's
    sources only when a tile fails and every source reads. Raises CdnRefused (stop the stage)."""
    started = time.monotonic()
    key = line["key"]
    description = (line.get("details") or {}).get("description") or {}
    links, skipped = pick_links(description)
    fetcher = fetcher or _cached_fetch
    known = known or {}
    images, got, extra = _fetch_all(links, fetcher, cache, session, sleep, known)
    skipped += extra
    tiled = bool(links) and all(ocr.SNAP_RE.search(x) for x in links)
    if tiled and any(i["status"] != "read" for i in images):
        # Naver first (the owner, 2026-11-07: its CDN is fast and steady; a seller's host can be 5x slower, its
        # proxy-smartstore links expire); a tile Naver did not serve: the seller's own pictures, when all read
        sources = tile_sources(description)
        alt, alt_got, alt_extra = _fetch_all(sources, fetcher, cache, session, sleep, known) if sources else ([], [], [])
        if alt and all(i["status"] == "read" for i in alt):
            skipped += alt_extra + [{"link": f"{len(links)} snap tiles", "rule": "tiles_replaced_by_sources"}]
            images, got = alt, alt_got
    by_link = {img["link"]: img for img in images}
    for s in ocr.read_slices(engine, ocr.slices_of(got)):
        by_link[s["link"]]["slices"].append({k: s[k] for k in ("y0", "y1", "rows")})
    for img in images:                               # a stitched strip's slices sit on its first tile
        if img["status"] == "read" and not img["slices"] and ocr.SNAP_RE.search(img["link"]):
            img["status"] = "stitched"
    return {"format": FORMAT, "product_id": key.split(":")[3], "key": key, "links_sha256": links_sha(links),
            "engine": engine.info(), "images": images, "skipped": skipped,
            "seconds": round(time.monotonic() - started, 1)}


def known_images(out_dir: str, engine: dict[str, Any], links: list[str], skip: str) -> dict[str, dict[str, Any]]:
    """The read image entries other sidecars of the shop hold for these links (same engine), by link."""
    wanted, found = set(links), {}  # type: set[str], dict[str, dict[str, Any]]
    for name in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
        if not name.endswith(".json") or name == f"{skip}.json":
            continue
        try:
            with open(os.path.join(out_dir, name), encoding="utf-8") as f:
                sc = json.load(f)
        except (OSError, ValueError):
            continue
        if sc.get("engine") != engine:
            continue
        for img in sc.get("images") or []:
            if img.get("link") in wanted and img.get("status") == "read" and img.get("slices") \
                    and not ocr.SNAP_RE.search(img["link"]) and not img.get("reused"):
                found.setdefault(img["link"], {k: v for k, v in img.items() if k != "reused"})
    return found


def links_sha(links: list[str]) -> str:
    return hashlib.sha256("\n".join(links).encode()).hexdigest()


def _write(path: str, data: dict[str, Any]) -> None:
    part = f"{path}.{os.getpid()}.part"
    with open(part, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(part, path)


def _read_in_child(line: dict[str, Any], cache: str, known: dict[str, Any] | None = None) -> dict[str, Any]:
    """One product in a worker process of its own: the engine and the image bytes die with it."""
    return read_product(line, ocr.Engine(), cache, new_session(), known=known)


def _child(reader: Callable[..., dict[str, Any]], args: tuple, conn: Any) -> None:
    try:
        conn.send(("ok", reader(*args)))
    except CdnRefused as e:
        conn.send(("refused", str(e)))
    except BaseException as e:                       # noqa: BLE001  (reported to the parent, which decides)
        conn.send(("error", f"{type(e).__name__}: {e}"[:500]))
    finally:
        conn.close()


def read_isolated(reader: Callable[..., dict[str, Any]], line: dict[str, Any], cache: str,
                  timeout: float = PRODUCT_TIMEOUT, known: dict[str, Any] | None = None) -> tuple[str, Any]:
    """Run reader(line, cache) in a fresh spawned process and wait for it, synchronously -> ("ok", sidecar) |
    ("refused", message) | ("error", message). A worker that dies (killed for memory, a crash) or outlives
    `timeout` is an error, never a hang; Ctrl+C (KeyboardInterrupt here) kills the worker and goes on up."""
    ctx = multiprocessing.get_context("spawn")
    recv, send = ctx.Pipe(duplex=False)
    args = (line, cache) if known is None else (line, cache, known)
    worker = ctx.Process(target=_child, args=(reader, args, send), daemon=True)
    worker.start()
    send.close()
    deadline = time.monotonic() + timeout
    try:
        while True:
            if recv.poll(1):
                try:
                    return recv.recv()
                except EOFError:
                    return "error", f"worker died (exit {worker.exitcode})"
            if not worker.is_alive() and not recv.poll(0):
                return "error", f"worker died (exit {worker.exitcode})"
            if time.monotonic() > deadline:
                return "error", f"timeout after {timeout:.0f} s"
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(5)
        if worker.is_alive():
            worker.kill()
            worker.join()
        recv.close()


def _lock(out_dir: str) -> Any:
    f = open(os.path.join(out_dir, ".lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise StageBusy(f"{out_dir}: another description_images run is working on this shop") from None
    return f


def run(shop: str, runs: list[str] | None = None, products: list[str] | None = None, force: bool = False,
        shops_root: str = SHOPS_ROOT, engine: Any = None, fetcher: Callable[..., bytes] | None = None,
        log: Callable[[str], None] = print, reader: Callable[..., dict[str, Any]] | None = None,
        timeout: float = PRODUCT_TIMEOUT) -> dict[str, Any]:
    """Every kept product of the shop whose category has the switch on, one at a time. Each product is read in a
    fresh worker process (read_isolated: the run never accumulates the engine's memory, a crash or a hang of one
    product is that product's error); an error gets one more try, then an error sidecar is written (the product
    is not read again until --force). Tests pass an engine (and a fetcher): read in this process.
    A script that calls run() must keep its work under `if __name__ == "__main__":` (a spawned worker imports the
    calling script again; without the guard it would run the script's work a second time: example_15, 2026-11-07)."""
    from run_transform import latest_lines
    rules = rules_for(shop)
    out_dir = sidecar_dir(shop, shops_root)
    cache = os.path.join(out_dir, "cache")
    os.makedirs(out_dir, exist_ok=True)
    counts = {"read": 0, "kept": 0, "off": 0, "no_rules": 0, "errors": 0}
    lock = _lock(out_dir)
    try:
        for _, _, line in latest_lines(shop, runs, shops_root).values():
            product_id = line["key"].split(":")[3]
            if products and product_id not in products:
                continue
            category = ((line.get("specs") or {}).get("category") or {})
            try:
                if not rules.category(category.get("id"), category.get("name")).description_images:
                    counts["off"] += 1
                    continue
            except ShopRulesMissing:
                counts["no_rules"] += 1
                continue
            path = os.path.join(out_dir, f"{product_id}.json")
            links, skipped = pick_links(((line.get("details") or {}).get("description")) or {})
            old = load_sidecar(shop, product_id, shops_root)
            retry = any(i.get("status") == "failed" for i in (old or {}).get("images") or [])   # a 5xx / network
            if old and not force and not retry and old.get("links_sha256") == links_sha(links) and \
                    old.get("engine") == (engine.info() if engine else ocr.engine_info()):
                counts["kept"] += 1
                continue
            product_cache = os.path.join(cache, product_id)      # one folder per product: easy to delete later
            started = time.monotonic()
            known = known_images(out_dir, engine.info() if engine else ocr.engine_info(),
                                 links + tile_sources(((line.get("details") or {}).get("description")) or {}),
                                 product_id)
            if engine is not None:
                sidecar = read_product(line, engine, product_cache, None, fetcher=fetcher, known=known)
            else:
                for attempt in (1, 2):
                    kind, value = read_isolated(reader or _read_in_child, line, product_cache, timeout,
                                                known if reader is None else None)
                    if kind == "refused":
                        raise CdnRefused(value)
                    if kind == "ok":
                        sidecar = value
                        break
                    log(f"description_images: {product_id}: attempt {attempt}: {value}")
                else:                                    # recorded: the transform notes it, --force reads again
                    sidecar = {"format": FORMAT, "product_id": product_id, "key": line["key"],
                               "links_sha256": links_sha(links), "engine": ocr.engine_info(), "images": [],
                               "skipped": skipped, "error": value,
                               "seconds": round(time.monotonic() - started, 1)}
                    counts["errors"] += 1
            _write(path, sidecar)
            counts["read"] += 1
            n_rows = sum(len(s["rows"]) for i in sidecar["images"] for s in i.get("slices") or [])
            failed = sum(i["status"] in ("failed", "gone", "refused") for i in sidecar["images"])
            log(f"description_images: {product_id}: {len(sidecar['images'])} images ({failed} not read), "
                f"{len(sidecar['skipped'])} skipped, {n_rows} rows, {sidecar['seconds']} s"
                + (f", ERROR {sidecar['error']}" if sidecar.get("error") else ""))
    finally:
        lock.close()
    return {"counts": counts, "out_dir": out_dir}


def prune_cache(shop: str, products: list[str] | None = None, shops_root: str = SHOPS_ROOT) -> tuple[int, int]:
    """Delete the downloaded images of these products (default: every product) -> (folders, bytes). The
    sidecars stay (the transform needs only them); a later --force run downloads again."""
    cache = os.path.join(sidecar_dir(shop, shops_root), "cache")
    folders = n_bytes = 0
    for name in sorted(os.listdir(cache)) if os.path.isdir(cache) else []:
        path = os.path.join(cache, name)
        if not os.path.isdir(path) or products and name not in products:
            continue
        n_bytes += sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path))
        shutil.rmtree(path)
        folders += 1
    return folders, n_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR a shop's description images into sidecar files.")
    parser.add_argument("shop", help="shop id, e.g. fairwardgolf")
    parser.add_argument("runs", nargs="*", help="kept run ids (default: every kept run)")
    parser.add_argument("--products", nargs="*", help="only these product ids")
    parser.add_argument("--force", action="store_true", help="read again even when the sidecar is current")
    parser.add_argument("--prune-cache", action="store_true",
                        help="only delete the downloaded images (all, or --products); the sidecars stay")
    args = parser.parse_args(argv)
    if args.prune_cache:
        folders, n_bytes = prune_cache(args.shop, args.products)
        print(f"description_images: deleted the image cache of {folders} products ({n_bytes / 1e6:.0f} MB)")
        return 0
    try:
        result = run(args.shop, args.runs or None, args.products, args.force)
    except ShopRulesMissing as e:
        print(f"description_images: stop: {e}")
        return 2
    except CdnRefused as e:
        print(f"description_images: stop: image CDN refused ({e}); the sidecars written so far are kept")
        return 3
    except StageBusy as e:
        print(f"description_images: stop: {e}")
        return 4
    except KeyboardInterrupt:
        print("description_images: stopped by the operator; the sidecars written so far are kept (run again to go on)")
        return 130
    print(f"description_images: {result['counts']} -> {result['out_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
