"""Fabric Depot (fabricdepot.com).

Fabric Depot is a multi-brand retailer that does not disclose the maker — the
Shopify `vendor` field is literally "Fabrics" and titles read "Famous Maker" or
name a designer with no structured maker code. So vendor = "Fabric Depot" is the
link-out target and manufacturer/manufacturer_sku are left null (same reseller
shape as SY Fabrics; see project memory `project_identity_dedup_model`).

Shopify storefront. One product per color (single variant, option "Title" =
"Default Title"); the variant SKU (e.g. "APS14027") is stable and unique, so
color_code = sku.

robots.txt and /agents.md permit public catalog browsing (/products.json,
/collections/<handle>/products.json) with no declared crawl-delay; we keep the
courteous BaseScraper default anyway. Transactional flows are gated behind a
UCP/MCP endpoint requiring human approval — we never touch those, only read.

Solid identification — the important part:
- Solid vs print is NOT reliably in the product tags or title. The store-wide
  /products.json carries a literal "Solid" tag on only ~0.6% of products, and a
  third of real solids don't even have "solid" in their name. The site instead
  classifies via a metafield-driven filter and curates the result into a
  `solid-fabrics` collection. So we scrape that collection directly — it IS the
  site's solid set (print-free; its `fabricdesign_*` tags are Texture/Slub/
  Iridescent — i.e. solid-COLORED textures, which we keep).

Parsing quirks:
- Remnant cut-pieces ("4 YD PC-…", tagged "Remnant") are transient single cuts
  and excluded; obvious multi-color listings are skipped too (no single dominant
  color to match on).
- Titles LEAD with the color ("Royal Blue Cotton Solid Double Gauze…"), the
  inverse of SY where the color trails — so we match a leading color run.
- The variant `featured_image` is null; images[0] is the bare "<SKU>.jpg" main
  swatch, which is what we extract color from.
- Physical specs live in body_html as "-Width: 53", "-Fiber Content: 100% Cotton"
  lines. Weight is only qualitative ("Light"), so weight_gsm stays null.
"""
import re
from typing import Iterable

from scraper.base import BaseScraper, FabricRecord

# Weave vocabulary, mirroring fabricwholesaledirect.py (kept module-local so each
# source stays self-contained, like SY copying its own _PATTERN_RE).
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
_WEAVE_RE = re.compile(r"\b(" + "|".join(WEAVE_TERMS) + r")\b", re.IGNORECASE)

# Color vocabulary, longest phrases first so "royal blue" wins over "blue".
# Adapted from syfabrics.py with a few leading-modifier words this catalog uses
# (pastel, bright, deep, heather, neon…). Used to peel the color off the FRONT
# of the title.
_COLOR_WORDS = (
    "royal blue", "navy blue", "sky blue", "baby blue", "powder blue",
    "light blue", "dark blue", "hunter green", "olive green", "forest green",
    "kelly green", "lime green", "mint green", "dark green", "light green",
    "seafoam green", "candy pink", "dark gold", "off white", "off-white",
    "hot pink", "baby pink", "light pink", "dusty rose",
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
# Leading modifiers that qualify a base color (e.g. "Pastel Blue").
_MODIFIERS = (
    "pastel", "bright", "deep", "dusty", "dark", "light", "medium",
    "heather", "heathered", "neon", "soft", "pale", "rich", "vintage",
)
# Set of every base color token, for validating that a leading run is really a
# color (and not a lone modifier).
_BASE_COLOR_TOKENS = {w for phrase in _COLOR_WORDS for w in phrase.split()}

_COLOR_ALT = "|".join(re.escape(c) for c in (*_COLOR_WORDS, *_MODIFIERS))
# Match a run of color/modifier words anchored at the start of the title,
# separated by spaces/hyphens/slashes ("Royal Blue", "Pastel Blue-White").
_LEADING_COLOR_RE = re.compile(
    rf"^(?:\b(?:{_COLOR_ALT})\b)(?:[\s/-]+\b(?:{_COLOR_ALT})\b)*",
    re.IGNORECASE,
)


class FabricDepotScraper(BaseScraper):
    slug = "fabricdepot"
    name = "Fabric Depot"
    vendor = "Fabric Depot"
    # Reseller that hides the maker — manufacturer/manufacturer_sku stay null.
    base_url = "https://fabricdepot.com"
    # The site's curated solid-color set. Scraping this collection is how we
    # identify solids (tags/titles are unreliable — see module docstring).
    collection_handle = "solid-fabrics"
    crawl_delay = 2.5

    def iter_records(self) -> Iterable[FabricRecord]:
        page = 1
        while True:
            url = (f"{self.base_url}/collections/{self.collection_handle}"
                   f"/products.json?limit=250&page={page}")
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

        raw_tags = p.get("tags") or []
        tags = {t.lower() for t in raw_tags}

        # The collection is already curated to solids, but guard the edges:
        # drop the rare leaked print, transient remnant cut-pieces ("4 YD PC-…"),
        # and obvious multi-color listings (no single dominant color to match).
        if "print" in tags:
            return None
        if "remnant" in tags or "category_remnant fabric" in tags:
            return None
        if re.search(r"\bPC-", title) or re.search(r"\bYD\s+PC\b", title, re.IGNORECASE):
            return None
        if re.search(r"\bmulti(?:color|colour|-?color)?\b", title, re.IGNORECASE):
            return None

        variants = p.get("variants") or []
        sku = (variants[0].get("sku") if variants else None) or str(p.get("id"))

        images = p.get("images") or []
        if not images:
            return None
        image_url = images[0].get("src")
        if not image_url:
            return None

        color_name, collection = self._color_and_collection(title, raw_tags)

        body = p.get("body_html") or ""
        record = FabricRecord(
            vendor=self.vendor,
            collection=collection,
            color_code=sku,
            color_name=color_name,
            vendor_url=f"{self.base_url}/products/{p['handle']}",
            image_url=image_url,
            material=self._content_tag(raw_tags),
            content=self._fiber_content(body) or self._content_tag(raw_tags),
            weave=self._weave(raw_tags, title),
            width_inches=self._width(body),
        )
        # Backstop pattern check on the assembled name, like the other scrapers.
        if not self.is_solid(record):
            return None
        return record

    @staticmethod
    def _color_and_collection(title: str, raw_tags: list[str]) -> tuple[str, str]:
        """Peel the leading color run off the title. Returns (color_name,
        collection). Falls back to the single `maincolor_` tag for the color and
        the full title for the collection when no leading color parses."""
        m = _LEADING_COLOR_RE.match(title)
        # Tokenize on non-letters so hyphenated runs ("Yellow-Beige") validate.
        if m and any(t in _BASE_COLOR_TOKENS for t in re.findall(r"[a-z]+", m.group(0).lower())):
            color = m.group(0).strip()
            collection = title[m.end():].lstrip(" -/").strip()
            return color.title(), (collection or title)

        for t in raw_tags:
            if t.lower().startswith("maincolor_"):
                return t.split("_", 1)[1].replace("-", " ").title(), title
        return title, title

    @staticmethod
    def _content_tag(raw_tags: list[str]) -> str | None:
        for t in raw_tags:
            if t.lower().startswith("content_"):
                return t.split("_", 1)[1].strip() or None
        return None

    @staticmethod
    def _fiber_content(body_html: str) -> str | None:
        m = re.search(r"Fiber Content:\s*([^<\n]+)", body_html, re.IGNORECASE)
        return m.group(1).strip() if m else None

    @staticmethod
    def _width(body_html: str) -> float | None:
        m = re.search(r"Width:\s*(\d+(?:\.\d+)?)", body_html, re.IGNORECASE)
        return float(m.group(1)) if m else None

    @staticmethod
    def _weave(raw_tags: list[str], title: str) -> str | None:
        # Prefer the store's `category_<X> Fabric` tags (e.g. "Gauze Fabric",
        # "Jersey Knit Fabric"); skip the generic "Woven Fabric"/"Knit Fabric".
        for t in raw_tags:
            if not t.lower().startswith("category_"):
                continue
            value = t.split("_", 1)[1]
            m = _WEAVE_RE.search(value)
            if m:
                return m.group(0).title()
        # Fall back to scanning the title.
        m = _WEAVE_RE.search(title)
        return m.group(0).title() if m else None
