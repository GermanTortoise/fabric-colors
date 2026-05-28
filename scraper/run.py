"""Scrape runner.

Usage:
    python -m scraper.run <manufacturer_slug> [limit]

Example:
    python -m scraper.run robertkaufman 20
"""
import importlib
import sys

from scraper import color, db
from scraper.base import BaseScraper, FabricRecord


def get_scraper(slug: str) -> BaseScraper:
    module = importlib.import_module(f"scraper.manufacturers.{slug}")
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, type) and issubclass(obj, BaseScraper) and obj is not BaseScraper:
            return obj()
    raise ValueError(f"No BaseScraper subclass found in scraper.manufacturers.{slug}")


def save_fabric(record: FabricRecord, result: color.ColorResult | None) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO fabrics (
                vendor, collection, color_code, color_name, vendor_url,
                manufacturer, manufacturer_sku,
                image_url, hex, lab_l, lab_a, lab_b,
                material, weave, weight_gsm, width_inches, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vendor, collection, color_code) DO UPDATE SET
                color_name=excluded.color_name,
                vendor_url=excluded.vendor_url,
                manufacturer=excluded.manufacturer,
                manufacturer_sku=excluded.manufacturer_sku,
                image_url=excluded.image_url,
                hex=excluded.hex,
                lab_l=excluded.lab_l, lab_a=excluded.lab_a, lab_b=excluded.lab_b,
                material=excluded.material,
                weave=excluded.weave,
                weight_gsm=excluded.weight_gsm,
                width_inches=excluded.width_inches,
                content=excluded.content
            """,
            (
                record.vendor,
                record.collection,
                record.color_code,
                record.color_name,
                record.vendor_url,
                record.manufacturer,
                record.manufacturer_sku,
                record.image_url,
                result.hex if result else None,
                result.lab[0] if result else None,
                result.lab[1] if result else None,
                result.lab[2] if result else None,
                record.material,
                record.weave,
                record.weight_gsm,
                record.width_inches,
                record.content,
            ),
        )


def run(slug: str, limit: int | None = None) -> None:
    db.init()
    scraper = get_scraper(slug)
    print(f"Scraping {scraper.name} ({scraper.base_url})")

    saved = 0
    for record in scraper.iter_records():
        if limit and saved >= limit:
            break
        try:
            result = None
            if record.image_url:
                try:
                    img_bytes = scraper.fetch_image(record.image_url)
                    result = color.extract_dominant_color(img_bytes)
                except Exception as exc:
                    print(f"  color extraction failed for {record.vendor_url}: {exc}")

            save_fabric(record, result)
            saved += 1
            hex_str = result.hex if result else "no-color"
            print(f"  [{saved}] {record.name} -> {hex_str}")
        except Exception as exc:
            print(f"  save error for {record.vendor_url}: {exc}")

    print(f"Done. Saved/updated {saved} fabrics.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scraper.run <manufacturer_slug> [limit]")
        sys.exit(1)
    slug = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run(slug, limit)
