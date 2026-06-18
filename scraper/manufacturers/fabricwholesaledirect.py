"""Fabric Wholesale Direct (fabricwholesaledirect.com).

FWD is its own house brand — the store IS the manufacturer, so vendor and
manufacturer are both "Fabric Wholesale Direct" and the product page is the
link-out target. collection = product title (e.g. "Stretch Velvet"); color_code
= synthetic "{product_id}-{color_slug}" since FWD doesn't publish stable codes
(so manufacturer_sku is left null).

Shopify storefront. robots.txt explicitly allows public catalog crawling and
points agents at /agents.md and a UCP/MCP endpoint. We use /products.json
(paginated) instead of HTML scraping because Shopify returns full structured
data: variants, options, tags, images.

One FabricRecord is emitted per (product, unique color). Variants that share a
color but differ on size are deduped.
"""
import re
from typing import Iterable
from urllib.parse import parse_qs, urlparse

from scraper.base import BaseScraper, FabricRecord

WEAVE_TERMS = (
    "velveteen", "velvet", "poplin", "twill", "satin", "sateen", "chiffon",
    "crepe", "voile", "organza", "tulle", "corduroy", "denim", "canvas",
    "duck", "flannel", "fleece", "felt", "jersey", "knit", "lace",
    "jacquard", "damask", "brocade", "taffeta", "muslin", "gingham",
    "broadcloth", "oxford", "georgette", "habotai", "shantung", "dupioni",
    "ottoman", "tweed", "boucle", "minky", "mesh", "pongee", "charmeuse",
    "seersucker", "chambray", "gabardine", "gauze", "cheesecloth", "madras",
    "dobby", "faille", "ripstop", "tricot", "drill", "interlock", "habutai",
)

# fabrictype: tag values that aren't actually weaves (categories, properties,
# or finishes). When the first tag is one of these, fall back to the next.
FABRICTYPE_GENERIC = {
    "woven", "printed", "novelty", "on sale", "sheer", "lining",
    "moisture wicking", "uv protected fabric", "sustainable", "bonded",
    "brushed", "sequin", "burnout", "beaded", "embroidery", "rosette",
    "crinkle", "stretch", "blackout", "blackout lining", "fusible",
    "fusible interfacing", "interfacing", "interlining", "flame retardant",
    "solution dyed", "nonwoven", "quilt backing", "headliner",
}


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class FabricWholesaleDirectScraper(BaseScraper):
    slug = "fabricwholesaledirect"
    name = "Fabric Wholesale Direct"
    vendor = "Fabric Wholesale Direct"
    # House brand — the store is the maker. No published per-color SKU (codes are
    # synthetic), so manufacturer_sku stays null.
    manufacturer = "Fabric Wholesale Direct"
    base_url = "https://fabricwholesaledirect.com"
    crawl_delay = 2.5

    def iter_records(self) -> Iterable[FabricRecord]:
        page = 1
        while True:
            url = f"{self.base_url}/products.json?limit=250&page={page}"
            data = self.fetch_json(url)
            products = data.get("products", [])
            if not products:
                break
            print(f"  page {page}: {len(products)} products")
            for product in products:
                yield from self._records_for_product(product)
            page += 1

    def _records_for_product(self, p: dict) -> Iterable[FabricRecord]:
        tags = {t.lower() for t in (p.get("tags") or [])}
        if "pattern:solid" not in tags:
            return
        # Raw fabric has no `shop:` tag; finished goods (table covers, curtains,
        # sewing notions, accessories) do. Skip the finished goods.
        if any(t.startswith("shop:") for t in tags):
            return

        color_pos = self._color_option_position(p.get("options") or [])
        if color_pos is None:
            return

        raw_tags = p.get("tags") or []
        material = self._material_from_tags(raw_tags)
        width = self._width_from_tags(raw_tags)
        title = p.get("title") or ""
        weave = self._weave_from_product(p)
        product_url = f"{self.base_url}/products/{p['handle']}"

        seen: set[str] = set()
        for v in p.get("variants") or []:
            color = v.get(f"option{color_pos}")
            if not color or color in seen:
                continue
            # featured_image is the A2 swirl/swatch shot. Prefer A1 (the big
            # drape shot that fills the frame) — much better for color
            # extraction. Found by URL pattern since the listing endpoint
            # strips image alts.
            featured = (v.get("featured_image") or {}).get("src")
            image_url = self._drape_image(p, featured) or featured
            if not image_url:
                continue
            seen.add(color)

            yield FabricRecord(
                vendor=self.vendor,
                collection=title,
                color_code=f"{p['id']}-{_slugify(color)}",
                color_name=color,
                vendor_url=f"{product_url}?variant={v['id']}",
                manufacturer=self.manufacturer,
                image_url=image_url,
                material=material,
                content=material,
                weave=weave,
                width_inches=width,
            )

    @staticmethod
    def _color_option_position(options: list[dict]) -> int | None:
        for o in options:
            if (o.get("name") or "").strip().lower() == "color":
                return o.get("position")
        return None

    @staticmethod
    def _material_from_tags(tags: list[str]) -> str | None:
        for t in tags:
            if t.lower().startswith("content:") and "%" in t:
                return t.split(":", 1)[1].strip()
        return None

    @staticmethod
    def _width_from_tags(tags: list[str]) -> float | None:
        for t in tags:
            if t.lower().startswith("width:"):
                m = re.search(r"(\d+(?:\.\d+)?)", t)
                if m:
                    return float(m.group(1))
        return None

    # The "a<digit>" view code (a1 = full drape shot, a2 = swatch/swirl,
    # a3 = detail) identifies which shot a filename is. It sits in the MIDDLE of
    # the name, followed by an optional "_<NNN>x" size token and "_<uuid>" hash:
    #   "..._Hunter_Green_a2_3000x_<uuid>.jpg"  (underscores around the code)
    #   "...RayonChallis-Silvera1_3000x_<uuid>.jpg"  (code smushed against color)
    #   "...-OffWhitea2.jpg"  (older: no size/uuid trailing the code)
    # Capture the code's digit; the optional size/hash trail is what an
    # end-anchored "(_<uuid>)?\." pattern used to miss (the "x" in "3000x" and
    # the size token between code and hash both broke the old regex).
    _IMG_CODE_RE = re.compile(
        r"a(\d+)(?:_\d+x)?(?:_[a-f0-9-]+)?\.(?:jpe?g|png|webp)$",
        re.IGNORECASE,
    )

    @staticmethod
    def _drape_image(p: dict, featured_url: str | None, code: str = "a1") -> str | None:
        if not featured_url:
            return None
        fname = featured_url.split("?", 1)[0].rsplit("/", 1)[-1]
        fm = FabricWholesaleDirectScraper._IMG_CODE_RE.search(fname)
        if not fm:
            return None
        # Stem = the per-variant color/style prefix every shot of this variant
        # shares (everything before its "a<digit>" code). Find the sibling image
        # with the same stem but the requested code. Lowercased because FWD mixes
        # the "..._a1_" and attached "...Silvera1" spellings across colors.
        stem = fname[: fm.start()].lower()
        want = code.lower().lstrip("a")
        for img in p.get("images") or []:
            src = (img.get("src") or "").split("?", 1)[0]
            name = src.rsplit("/", 1)[-1]
            m = FabricWholesaleDirectScraper._IMG_CODE_RE.search(name)
            if m and m.group(1) == want and name[: m.start()].lower() == stem:
                return img.get("src")
        return None

    def resolve_listing_image(self, listing_url: str) -> tuple[str, dict]:
        """Given a public listing URL, return (A1 drape image URL, info dict).

        Info dict carries the product title, picked variant color, and the URL
        we fetched — useful for the debug viz to label what was sampled.
        Raises ValueError on URLs that aren't a FWD product page.
        """
        parsed = urlparse(listing_url)
        if "fabricwholesaledirect.com" not in (parsed.netloc or ""):
            raise ValueError("not a fabricwholesaledirect.com URL")
        m = re.match(r"^/products/([^/]+)/?$", parsed.path)
        if not m:
            raise ValueError("URL is not a /products/<handle> path")
        handle = m.group(1)
        variant_q = parse_qs(parsed.query).get("variant", [None])[0]
        variant_id = int(variant_q) if variant_q and variant_q.isdigit() else None

        data = self.fetch_json(f"{self.base_url}/products/{handle}.json")
        product = data.get("product") or {}
        variants = product.get("variants") or []
        if not variants:
            raise ValueError("product has no variants")

        variant = None
        if variant_id is not None:
            variant = next((v for v in variants if v.get("id") == variant_id), None)
        if variant is None:
            variant = variants[0]

        color_pos = self._color_option_position(product.get("options") or [])
        color = variant.get(f"option{color_pos}") if color_pos else None
        # The single-product .json endpoint omits `featured_image` (the catalog
        # /products.json denormalizes it in); reconstruct it from image_id.
        image_id = variant.get("image_id")
        featured = None
        for img in product.get("images") or []:
            if img.get("id") == image_id:
                featured = img.get("src")
                break
        image_url = self._drape_image(product, featured) or featured
        if not image_url:
            raise ValueError("no image found for variant")
        return image_url, {
            "title": product.get("title"),
            "color": color,
            "variant_id": variant.get("id"),
            "featured_image": featured,
            "drape_image": image_url,
        }

    @staticmethod
    def _weave_from_product(p: dict) -> str | None:
        # Prefer the store's own `fabrictype:` tag — most reliable signal.
        for t in (p.get("tags") or []):
            if not t.lower().startswith("fabrictype:"):
                continue
            value = t.split(":", 1)[1].strip()
            if value.lower() not in FABRICTYPE_GENERIC:
                return value
        # Fall back to scanning title + product_type for known weave terms.
        text = f"{p.get('title') or ''} {p.get('product_type') or ''}".lower()
        for term in WEAVE_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", text):
                return term.title()
        return None
