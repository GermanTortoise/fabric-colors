"""SY Fabrics (syfabrics.com).

SY Fabrics is a reseller that hides the maker, so vendor = "SY Fabrics" is the
link-out target and manufacturer/manufacturer_sku are left null. collection =
the fabric type parsed from the product title (e.g. "Plush Triple Velvet"),
color_code = the Shopify product id (one color per product, so the id is unique).

Shopify storefront — same /products.json approach as fabricwholesaledirect.
~3,700 products, paginated 250 at a time via ?page=N.

The catalog is mostly one-product-per-color listings (option name "Title",
single "Default Title" variant) with the color baked into the title. A handful
of products instead expose every color as a variant ("Color"/"Color/Swatch"
option) — those are full-bolt duplicates of colors that already exist as their
own products, so we skip them to avoid duplicate colors.

Titles are noisy: the color trails the fabric type and is itself followed by SKU
codes ("VL-18", "436"), size notes ("60 YARD ROLL", '120" Wide'), and quoted
asides. Roughly half the catalog is novelty prints (sports/character/animal
fleece, florals, embroidery) which we must exclude. Our filter requires the
title to contain a recognized color word: that yields the color label, lets us
strip it off to recover the fabric type, and excludes most prints (no color
word) and "Assorted ... Remnants" lots in one stroke. The accurate swatch hex
comes from the product image, not this label.
"""
import re
from typing import Iterable

from scraper.base import BaseScraper, FabricRecord

# Print / novelty / texture markers that disqualify a product as a solid. Run
# whole-word against the title. Extends BaseScraper._PATTERN_RE with the themes
# SY Fabrics' fleece/specialty lines actually use.
_PATTERN_RE = re.compile(
    r"\b("
    r"print|prints|floral|stripe|striped|plaid|check|checkered|pattern|polka|"
    r"dot|geometric|paisley|tartan|houndstooth|camo|camouflage|aztec|"
    r"animal|cheetah|leopard|jaguar|zebra|tiger|giraffe|snake|skins?|"
    r"dogs?|cats?|puppy|puppies|kitten|bear|bunny|butterfly|unicorn|dinosaur|"
    r"elephant|monkey|dragon|phoenix|confetti|flames?|snowflakes?|patchwork|"
    r"hearts?|stars?|owls?|hibiscus|sequins?|embroider|embroidered|pintuck|"
    r"glitz|brocade|jacquard|damask|quilt|"
    r"assorted|remnants?|sample|swatch|multi"
    r")\b",
    re.IGNORECASE,
)

# Color vocabulary, longest phrases first so "royal blue" wins over "blue".
# Used to (a) find the color word, (b) split it off to recover the fabric type.
# Note "fuschia" — SY Fabrics' own common misspelling of fuchsia.
_COLOR_WORDS = (
    "royal blue", "navy blue", "sky blue", "baby blue", "powder blue",
    "light blue", "dark blue", "hunter green", "olive green", "forest green",
    "kelly green", "lime green", "mint green", "dark green", "light green",
    "seafoam green", "candy pink", "dark gold",
    "hot pink", "baby pink", "light pink", "dusty rose", "off white",
    "silver gray", "silver grey", "charcoal gray", "charcoal grey",
    "light gray", "light grey", "dark gray", "dark grey",
    "royal", "navy", "olive", "kelly", "burgundy", "maroon", "wine",
    "fuchsia", "fuschia", "magenta", "champagne", "ivory", "beige", "taupe",
    "khaki", "chocolate", "coffee", "mustard", "lavender", "lilac", "plum",
    "violet", "eggplant", "mauve", "turquoise", "teal", "aqua", "cyan",
    "emerald", "jade", "coral", "peach", "salmon", "rust", "copper", "bronze",
    "charcoal", "silver", "gold", "brown", "orange", "yellow", "purple",
    "pink", "rose", "red", "green", "blue", "black", "white", "gray", "grey",
    "cream", "tan", "nude", "mint", "seafoam", "brick",
)
_COLOR_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _COLOR_WORDS) + r")\b",
    re.IGNORECASE,
)


class SyFabricsScraper(BaseScraper):
    slug = "syfabrics"
    name = "SY Fabrics"
    vendor = "SY Fabrics"
    # Reseller that hides the maker — manufacturer/manufacturer_sku stay null.
    base_url = "https://syfabrics.com"
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
                rec = self._record_for_product(product)
                if rec is not None:
                    yield rec
            page += 1

    def _record_for_product(self, p: dict) -> FabricRecord | None:
        title = (p.get("title") or "").strip()
        if not title:
            return None

        # Skip multi-color "bolt" products (color exposed as a variant option) —
        # they duplicate colors that exist as their own single-color products.
        for o in p.get("options") or []:
            if "color" in (o.get("name") or "").lower() and len(o.get("values") or []) > 1:
                return None

        # Reject prints / novelty / non-solid textures.
        if _PATTERN_RE.search(title):
            return None

        color = self._color_from_title(title)
        if color is None:
            return None  # no recognizable color → can't label it; likely a print

        image_url = self._image_for(p)
        if not image_url:
            return None

        return FabricRecord(
            vendor=self.vendor,
            collection=self._collection_from_title(title) or title,
            color_code=str(p["id"]),
            color_name=color,
            vendor_url=f"{self.base_url}/products/{p['handle']}",
            image_url=image_url,
        )

    @staticmethod
    def _color_from_title(title: str) -> str | None:
        """Return the (title-cased) color word in the title, preferring the last
        match since the color trails the fabric type."""
        matches = list(_COLOR_RE.finditer(title))
        if not matches:
            return None
        return matches[-1].group(0).title()

    @staticmethod
    def _collection_from_title(title: str) -> str | None:
        """Fabric type = the title up to where the color starts, trimmed."""
        matches = list(_COLOR_RE.finditer(title))
        if not matches:
            return None
        prefix = title[: matches[-1].start()].strip()
        # Drop a dangling slash/dash left by splitting (e.g. "Satin/Lamour ").
        prefix = prefix.rstrip(" -/").strip()
        return prefix or None

    @staticmethod
    def _image_for(p: dict) -> str | None:
        for v in p.get("variants") or []:
            src = (v.get("featured_image") or {}).get("src")
            if src:
                return src
        images = p.get("images") or []
        if images:
            return images[0].get("src")
        return None
