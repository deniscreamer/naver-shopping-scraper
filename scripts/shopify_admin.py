"""Writes to our own Shopify store (the owner allowed it 2026-11-08: publication). Two apps of the store, both in
the store's credentials file (shop_stores.Shopify.credentials_env), each with its own minted token:

  ProductsAdmin  PRODUCTS_API_CLIENT_ID / _SECRET   write_products: staged uploads, productSet, publishing
  FilesAdmin     ADMIN_API_CLIENT_ID / _SECRET      write_files: the reviews' photos, avatars and JSON feed

Both reuse shopify_catalog's transport (the shop checked before work, token checks, throttling, no secret in an
error or print). shopify_catalog.ShopCatalog itself stays read-only.
"""
import mimetypes
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import requests

from shopify_catalog import RETRIES, RETRY_WAIT, TIMEOUT, CatalogError, ShopCatalog

POLL_S = 2.0
POLL_TRIES = 30                                  # ~60 s for a file to be READY
# Many files at once (2026-11-09: review photos uploaded one by one with a READY poll each made publication ~35 s a
# product). Shopify's Admin GraphQL limits by query cost, a leaky bucket per app and store (Standard plan: 100
# points a second; a mutation costs ~10; an input array holds at most 250 items; fileCreate takes at most 250 files;
# shopify.dev/docs/apps/build/apis/graphql-admin/rate-limits, read 2026-11-09). So the GraphQL calls stay one at a
# time and few: one stagedUploadsCreate and one fileCreate per batch, one nodes() poll for the whole batch; a
# THROTTLED answer, a 429 or a 5xx waits and repeats (shopify_catalog._send). Only the uploads of the files
# themselves to the staging bucket (a storage host, not the Admin API) run in parallel, each retried on 429 / 5xx.
BATCH = 50                                       # files per staged-upload / fileCreate call (Shopify allows 250)
UPLOAD_WORKERS = 6                               # parallel uploads to the staging bucket
FIND_BATCH = 10                                  # file names per files(query:) search


class AdminError(CatalogError):
    """Shopify refused a write (userErrors) or a file did not become ready."""


def _errors(result: dict[str, Any], what: str) -> None:
    errors = result.get("userErrors") or []
    if errors:
        text = "; ".join(f"{'.'.join(map(str, e.get('field') or []))}: {e.get('message')}" for e in errors)
        raise AdminError(f"{what}: {text[:600]}")


class _Writer(ShopCatalog):
    WRITES = True
    PROBE = False

    def __init__(self, store: Any, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep, **kw: Any):
        super().__init__(store, session=session, sleep=sleep, **kw)
        self._upload = session or requests.Session()
        self._upload.trust_env = False

    def stage(self, path: str, resource: str = "IMAGE", mime: str | None = None) -> str:
        """Upload a local file to Shopify's staging bucket -> its resourceUrl (for productSet / fileCreate)."""
        return self.stage_many([(path, resource, mime)])[0]

    def stage_many(self, items: list[tuple[str, str, str | None]]) -> list[str]:
        """[(path, resource IMAGE / FILE, mime or None)] -> their resourceUrls, in order: one stagedUploadsCreate per
        BATCH, the uploads in parallel."""
        out: list[str] = []
        for start in range(0, len(items), BATCH):
            chunk = [(path, resource, mime or mimetypes.guess_type(path)[0] or "application/octet-stream")
                     for path, resource, mime in items[start:start + BATCH]]
            data = self._post("""mutation($input: [StagedUploadInput!]!) { stagedUploadsCreate(input: $input) {
                stagedTargets { url resourceUrl parameters { name value } } userErrors { field message } } }""",
                              {"input": [{"resource": resource, "filename": os.path.basename(path), "mimeType": mime,
                                          "httpMethod": "POST", "fileSize": str(os.path.getsize(path))}
                                         for path, resource, mime in chunk]})
            result = data["stagedUploadsCreate"]
            _errors(result, f"staged upload of {len(chunk)} files")
            targets = result["stagedTargets"]
            if len(targets) != len(chunk):
                raise AdminError(f"staged upload: {len(targets)} targets for {len(chunk)} files")
            jobs = [(path, mime, target) for (path, _, mime), target in zip(chunk, targets)]
            if len(jobs) == 1:
                self._send_file(*jobs[0])
            else:
                with ThreadPoolExecutor(max_workers=min(UPLOAD_WORKERS, len(jobs))) as pool:
                    list(pool.map(lambda job: self._send_file(*job), jobs))       # the first error is raised
            out += [t["resourceUrl"] for t in targets]
        return out

    def _send_file(self, path: str, mime: str, target: dict[str, Any]) -> None:
        """One file to its staging target; a 429 / 5xx / connection error waits and repeats (RETRIES times)."""
        name = os.path.basename(path)
        session = self._thread_session()
        for attempt in range(1, RETRIES + 1):
            try:
                with open(path, "rb") as f:
                    r = session.post(target["url"], data={p["name"]: p["value"] for p in target["parameters"]},
                                     files={"file": (name, f, mime)}, timeout=TIMEOUT * 4, allow_redirects=False)
                status = r.status_code
            except requests.RequestException:
                status = 0
            if status in (200, 201, 204):
                return
            if status and status != 429 and status < 500:
                raise AdminError(f"staged upload {name}: HTTP {status}")
            if attempt < RETRIES:
                self._sleep(RETRY_WAIT * attempt)
        raise AdminError(f"staged upload {name}: failed {RETRIES} times (HTTP {status or 'no answer'})")

    def _thread_session(self) -> Any:
        """One upload session per thread (a requests.Session is not shared between threads); a session given that is
        not a requests.Session (a test's fake bucket) is used as it is."""
        if threading.current_thread() is threading.main_thread() or not isinstance(self._upload, requests.Session):
            return self._upload
        local = self.__dict__.setdefault("_local", threading.local())
        if not hasattr(local, "session"):
            local.session = requests.Session()
            local.session.trust_env = False
        return local.session


class ProductsAdmin(_Writer):
    SCOPE = "write_products"

    def publication_ids(self) -> list[str]:
        """Every sales channel of the store (the owner, 2026-11-09: a product is on all of them)."""
        nodes = self._post("query { publications(first: 50) { nodes { id name } } }")["publications"]["nodes"]
        if not nodes:
            raise AdminError("the store has no publication (sales channel)")
        return [n["id"] for n in nodes]

    def location_id(self, name: str | None = None) -> str:
        nodes = self._post("query { locations(first: 20) { nodes { id name isActive } } }")["locations"]["nodes"]
        active = [n for n in nodes if n["isActive"] and (name is None or n["name"] == name)]
        if not active:
            raise AdminError(f"no active location {name!r}")
        return active[0]["id"]

    def vendor_spellings(self) -> dict[str, str]:
        """{lower case: the shop's spelling}: one not in capitals when the shop has one ("CALLAWAY", "Callaway" ->
        "Callaway"; PING stays PING), else the most used (vendor search ignores case, so every product is read)."""
        from collections import Counter
        counts: Counter = Counter()
        cursor = None
        while True:
            page = self._post("""query($c: String) { products(first: 250, after: $c) { pageInfo { hasNextPage endCursor }
                nodes { vendor } } }""", {"c": cursor})["products"]
            counts.update(n["vendor"] for n in page["nodes"] if n["vendor"])
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        out: dict[str, str] = {}
        for name in sorted(counts, key=lambda n: (n.isupper(), -counts[n], n)):
            out.setdefault(name.lower(), name)
        return out

    def handle_owner(self, handle: str) -> tuple[str, str | None] | None:
        """(product id, its source key) of the product with this handle, or None."""
        node = self._post(f"""query($h: String!) {{ productByHandle(handle: $h) {{ id
            key: metafield(namespace: "{self.shop.namespace}", key: "source_offer_id") {{ value }} }} }}""",
                          {"h": handle}).get("productByHandle")
        return (node["id"], (node.get("key") or {}).get("value")) if node else None

    def product_set(self, payload: dict[str, Any], product_id: str | None = None) -> dict[str, Any]:
        data = self._post("""mutation($identifier: ProductSetIdentifiers, $input: ProductSetInput!) {
            productSet(identifier: $identifier, input: $input, synchronous: true) {
              product { id handle status onlineStorePreviewUrl
                media(first: 250) { nodes { id status ... on MediaImage { image { url } } } } }
              userErrors { field message code } } }""",
                          {"identifier": {"id": product_id} if product_id else None, "input": payload})
        result = data["productSet"]
        _errors(result, "productSet")
        return result["product"]

    def delete_metafields(self, product_id: str, keys: list[tuple[str, str]]) -> None:
        """Remove these metafields from the product (a key it does not have is no error)."""
        if not keys:
            return
        data = self._post("""mutation($m: [MetafieldIdentifierInput!]!) { metafieldsDelete(metafields: $m) {
            userErrors { field message } } }""",
                          {"m": [{"ownerId": product_id, "namespace": ns, "key": key} for ns, key in keys]})
        _errors(data["metafieldsDelete"], "metafieldsDelete")

    def publish(self, product_id: str, publication_ids: list[str]) -> None:
        data = self._post("""mutation($id: ID!, $input: [PublicationInput!]!) { publishablePublish(id: $id,
            input: $input) { userErrors { field message } } }""",
                          {"id": product_id, "input": [{"publicationId": p} for p in publication_ids]})
        _errors(data["publishablePublish"], "publish")

    def media_ready(self, product_id: str) -> dict[str, Any]:
        """The product's media after Shopify processed them (waits while one is UPLOADED / PROCESSING)."""
        for _ in range(POLL_TRIES):
            product = self._post("""query($id: ID!) { product(id: $id) { media(first: 250) { nodes { id status
                ... on MediaImage { image { url } } } } } }""", {"id": product_id})["product"]
            nodes = product["media"]["nodes"]
            if all(n["status"] in ("READY", "FAILED") for n in nodes):
                return product
            self._sleep(POLL_S)
        raise AdminError(f"{product_id}: media not ready after {POLL_TRIES * POLL_S:.0f} s")


class FilesAdmin(_Writer):
    NAMES = ("ADMIN_API_CLIENT_ID", "ADMIN_API_CLIENT_SECRET")
    SCOPE = "write_files"

    def find(self, filename: str) -> str | None:
        """The CDN link of a file already uploaded under this name (names carry the content's hash)."""
        return self.find_many([filename]).get(filename)

    def find_many(self, filenames: list[str]) -> dict[str, str]:
        """{name: CDN link} of the files already uploaded under these names, FIND_BATCH names a search."""
        out: dict[str, str] = {}
        for start in range(0, len(filenames), FIND_BATCH):
            stems = {name.rsplit(".", 1)[0]: name for name in filenames[start:start + FIND_BATCH]}
            query = " OR ".join(f"filename:{stem}*" for stem in stems)
            nodes = self._post("""query($q: String!, $n: Int!) { files(first: $n, query: $q) { nodes { fileStatus
                ... on MediaImage { image { url } } ... on GenericFile { url } } } }""",
                               {"q": query, "n": min(250, 5 * len(stems))})["files"]["nodes"]
            for n in nodes:
                url = ((n.get("image") or {}).get("url") or n.get("url") or "").split("?")[0]
                if n.get("fileStatus") != "READY" or not url:
                    continue
                base = os.path.basename(url)
                for stem, name in stems.items():
                    if base.startswith(stem) and name not in out:
                        out[name] = url
        return out

    def create(self, path: str, filename: str, image: bool = True) -> str:
        """Upload one file to Shopify Files (once: the same name is found again) -> its CDN link."""
        return self.create_many([(path, filename, image)])[filename]

    def create_many(self, items: list[tuple[str, str, bool]]) -> dict[str, str]:
        """[(path, file name, image?)] -> {file name: CDN link}: the ones already in Files found by name, the others
        staged in parallel, created BATCH at a time and polled together until READY."""
        out = self.find_many([name for _, name, _ in items])
        todo = [(path, name, image) for path, name, image in items if name not in out]
        for start in range(0, len(todo), BATCH):
            chunk = todo[start:start + BATCH]
            sources = self.stage_many([(path, "IMAGE" if image else "FILE", "image/webp" if image else
                                        "application/json") for path, _, image in chunk])
            data = self._post("""mutation($files: [FileCreateInput!]!) { fileCreate(files: $files) {
                files { id } userErrors { field message } } }""",
                              {"files": [{"originalSource": source, "filename": name,
                                          "contentType": "IMAGE" if image else "FILE",
                                          "duplicateResolutionMode": "RAISE_ERROR"}
                                         for source, (_, name, image) in zip(sources, chunk)]})
            result = data["fileCreate"]
            _errors(result, f"fileCreate of {len(chunk)} files")
            ids = {f["id"]: name for f, (_, name, _) in zip(result["files"], chunk)}
            out.update(self._ready(ids))
        return out

    def _ready(self, ids: dict[str, str]) -> dict[str, str]:
        """{file id: name} -> {name: CDN link} once every file is READY (one nodes() query a poll)."""
        out: dict[str, str] = {}
        waiting = dict(ids)
        for _ in range(POLL_TRIES):
            nodes = self._post("""query($ids: [ID!]!) { nodes(ids: $ids) { id ... on MediaImage { fileStatus
                image { url } } ... on GenericFile { fileStatus url } } }""", {"ids": list(waiting)})["nodes"]
            for node in nodes:
                node = node or {}
                url = (node.get("image") or {}).get("url") or node.get("url")
                if node.get("fileStatus") == "READY" and url and node.get("id") in waiting:
                    out[waiting.pop(node["id"])] = url.split("?")[0]
                elif node.get("fileStatus") == "FAILED":
                    raise AdminError(f"fileCreate {waiting.get(str(node.get('id')))}: FAILED")
            if not waiting:
                return out
            self._sleep(POLL_S)
        raise AdminError(f"fileCreate: {len(waiting)} files not ready after {POLL_TRIES * POLL_S:.0f} s")
