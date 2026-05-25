"""Template for an HTML/sitemap-based store scraper.

Copy this file to `<slug>_store.py` and replace the TODOs. For Shopify stores,
copy `fabricwholesaledirect_store.py` instead — Shopify exposes /products.json
which is far easier than HTML scraping.

Workflow:
  1. Read the store's robots.txt and Terms of Service.
  2. Find the sitemap (often linked from robots.txt).
  3. View source on one product page. If you see <script type="application/ld+json">
     with @type=Product, the JSON-LD path below works as-is.
  4. Otherwise add HTML selector logic in _parse_product.
"""
import json
from typing import Iterable
from xml.etree import ElementTree as ET

from scraper.base import BaseScraper, FabricRecord


class TemplateStoreScraper(BaseScraper):
    slug = "template"
    name = "Template Store"
    base_url = "https://example.com"
    crawl_delay = 10.0

    sitemap_url = "https://example.com/sitemap.xml"
    product_url_marker = "/products/"

    def iter_records(self) -> Iterable[FabricRecord]:
        for url in self._discover_urls():
            try:
                html = self.fetch(url)
            except Exception as exc:
                print(f"  fetch failed for {url}: {exc}")
                continue
            record = self._parse_product(html, url)
            if record and self.is_solid(record):
                yield record

    def _discover_urls(self) -> Iterable[str]:
        xml = self.fetch(self.sitemap_url)
        root = ET.fromstring(xml)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.findall(".//s:loc", ns):
            url = (loc.text or "").strip()
            if self.product_url_marker in url:
                yield url

    def _parse_product(self, html: str, url: str) -> FabricRecord | None:
        soup = self.soup(html)
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            product = self._find_product(data)
            if not product:
                continue

            image = product.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            elif isinstance(image, dict):
                image = image.get("url")

            return FabricRecord(
                store_product_id=str(
                    product.get("sku") or product.get("productID") or url
                ),
                name=product.get("name", ""),
                url=url,
                image_url=image,
            )
        return None

    @staticmethod
    def _find_product(data):
        if isinstance(data, dict):
            if data.get("@type") == "Product":
                return data
            for item in data.get("@graph") or []:
                if isinstance(item, dict) and item.get("@type") == "Product":
                    return item
        if isinstance(data, list):
            for item in data:
                found = TemplateStoreScraper._find_product(item)
                if found:
                    return found
        return None
