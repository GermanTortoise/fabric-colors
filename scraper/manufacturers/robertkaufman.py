"""Robert Kaufman (robertkaufman.com).

Pilot manufacturer scraper. Robert Kaufman publishes their entire Kona Cotton
Solids catalog inline on the category landing page as HTML-entity-encoded JSON
(generated server-side by their PHP catalog). One HTTP request yields all
~370 colors with code, name, fiber, width, and weight. Swatch images live at
/assets/fabric/detail/K001-<code>.jpg.

robots.txt is permissive (User-agent: * / Disallow: <empty>). No declared
crawl-delay; we still hold the BaseScraper default between the category page
fetch and image fetches as a courtesy.
"""
import html as html_module
import re
from typing import Iterable

from scraper.base import BaseScraper, FabricRecord


class RobertKaufmanScraper(BaseScraper):
    slug = "robertkaufman"
    name = "Robert Kaufman"
    brand = "Robert Kaufman"
    base_url = "https://www.robertkaufman.com"
    crawl_delay = 2.0
    image_delay = 0.2

    # Each Kona color is rendered into a per-product JS data object in the
    # category page. We pull the params block, which carries the user-visible
    # color name and physical specs. Field order in the embedded data is
    # stable across colors but we use a tolerant pattern (any non-brace chars
    # between fields) so a future Robert Kaufman key reordering still parses.
    _ENTRY_RE = re.compile(
        r'"sku":"(K001-[A-Z0-9_-]+)"'
        r'[^{}]*?"color":"([^"]*)"'
        r'[^{}]*?"contents":"([^"]*)"'
        r'[^{}]*?"width":"([^"]*)"'
        r'[^{}]*?"weight":"([^"]*)"',
        re.DOTALL,
    )

    def iter_records(self) -> Iterable[FabricRecord]:
        yield from self._iter_collection(
            collection="Kona Cotton",
            landing_path="/fabrics/kona_cotton/",
        )

    def _iter_collection(self, collection: str, landing_path: str) -> Iterable[FabricRecord]:
        raw = self.fetch(self.base_url + landing_path)
        text = html_module.unescape(raw)
        seen: set[str] = set()
        for m in self._ENTRY_RE.finditer(text):
            code, color, contents, width, weight = m.groups()
            if code in seen:
                continue
            seen.add(code)
            record = FabricRecord(
                brand=self.brand,
                collection=collection,
                color_code=code,
                color_name=color.title(),
                manufacturer_url=f"{self.base_url}{landing_path}{code}/",
                image_url=f"{self.base_url}/assets/fabric/detail/{code}.jpg",
                material=contents or None,
                content=contents or None,
                width_inches=_parse_float(width),
                weight_gsm=_oz_per_sqyd_to_gsm(_parse_float(weight)),
            )
            if self.is_solid(record):
                yield record


def _parse_float(s: str) -> float | None:
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# Robert Kaufman publishes fabric weight in ounces per square yard. Convert to
# g/m² so the column is comparable across manufacturers (1 oz/yd² ≈ 33.906 g/m²).
def _oz_per_sqyd_to_gsm(oz: float | None) -> float | None:
    if oz is None:
        return None
    return round(oz * 33.906, 1)
