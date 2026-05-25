"""Fabric Wholesale Direct (fabricwholesaledirect.com).

Shopify storefront. robots.txt explicitly allows public catalog crawling and
points agents at /agents.md and a UCP/MCP endpoint. We use /products.json
(paginated) instead of HTML scraping because Shopify returns full structured
data: variants, options, tags, images.

One FabricRecord is emitted per (product, unique color). Variants that share a
color but differ on size are deduped.
"""
import re
import time
from typing import Iterable

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
    base_url = "https://fabricwholesaledirect.com"
    crawl_delay = 2.5

    def iter_records(self) -> Iterable[FabricRecord]:
        page = 1
        while True:
            url = f"{self.base_url}/products.json?limit=250&page={page}"
            time.sleep(self.crawl_delay)
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            products = resp.json().get("products", [])
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
                store_product_id=f"{p['id']}-{_slugify(color)}",
                name=f"{title} – {color}",
                url=f"{product_url}?variant={v['id']}",
                image_url=image_url,
                raw_color_name=color,
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

    @staticmethod
    def _drape_image(p: dict, featured_url: str | None, code: str = "a1") -> str | None:
        if not featured_url:
            return None
        # featured_url looks like ".../SV582877..._Red_a2_<uuid>.jpg?v=..."
        # Strip query string and find the prefix before "_a<digit>_".
        path = featured_url.split("?", 1)[0]
        m = re.search(r"^(.+)_a\d+_", path)
        if not m:
            return None
        prefix = m.group(1)
        target = f"_{code}_"
        for img in p.get("images") or []:
            src = (img.get("src") or "").split("?", 1)[0]
            if src.startswith(prefix) and target in src.lower():
                return img.get("src")
        return None

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
