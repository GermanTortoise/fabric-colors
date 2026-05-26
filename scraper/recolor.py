"""Re-extract colors from cached images and update the DB.

Use this after changing the extraction algorithm in scraper/color.py. It reads
the cached image bytes (populated by past scrape runs), re-runs extraction, and
overwrites hex/lab_* on each fabric row. No network calls.

Rows whose image isn't in the cache are skipped — those need a scrape run first.

Usage:
    python -m scraper.recolor [limit]
"""
import sys

from scraper import color, db
from scraper.base import image_cache_path


def main(limit: int | None = None) -> None:
    db.init()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, name, image_url FROM fabrics WHERE image_url IS NOT NULL"
        ).fetchall()

    updated = 0
    missing = 0
    failed = 0
    for r in rows:
        if limit and updated >= limit:
            break
        path = image_cache_path(r["image_url"])
        if not path.exists():
            missing += 1
            continue
        try:
            result = color.extract_dominant_color(path.read_bytes())
        except Exception as exc:
            failed += 1
            print(f"  extraction failed for id={r['id']} ({r['name']}): {exc}")
            continue
        with db.connect() as conn:
            conn.execute(
                "UPDATE fabrics SET hex=?, lab_l=?, lab_a=?, lab_b=? WHERE id=?",
                (result.hex, result.lab[0], result.lab[1], result.lab[2], r["id"]),
            )
        updated += 1
        if updated % 100 == 0:
            print(f"  processed {updated} (missing: {missing}, failed: {failed})")

    print(f"Done. Updated {updated}, missing from cache: {missing}, failed: {failed}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(lim)
