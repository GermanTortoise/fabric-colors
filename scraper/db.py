import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fabrics.db"

# Identity model (see project memory `project_identity_dedup_model`): a row is a
# buyable listing. `vendor` + `vendor_url` are the source we link out to and are
# always known. `manufacturer` + `manufacturer_sku` are the attributed maker and
# its code, populated only when a source discloses them (null otherwise, as for
# resellers like SY Fabrics that hide the maker). Cross-vendor de-duplication on
# the disclosed manufacturer key is deferred until a source actually overlaps an
# existing manufacturer, so (manufacturer, manufacturer_sku) is indexed but not
# unique. Per-listing idempotency is UNIQUE (vendor, collection, color_code).
SCHEMA = """
CREATE TABLE IF NOT EXISTS fabrics (
    id INTEGER PRIMARY KEY,
    vendor TEXT NOT NULL,
    collection TEXT NOT NULL,
    color_code TEXT NOT NULL,
    color_name TEXT NOT NULL,
    vendor_url TEXT NOT NULL UNIQUE,
    manufacturer TEXT,
    manufacturer_sku TEXT,
    image_url TEXT,
    hex TEXT,
    lab_l REAL,
    lab_a REAL,
    lab_b REAL,
    material TEXT,
    weave TEXT,
    weight_gsm REAL,
    width_inches REAL,
    content TEXT,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reviewed INTEGER DEFAULT 0,
    UNIQUE (vendor, collection, color_code)
);

CREATE INDEX IF NOT EXISTS idx_fabrics_lab ON fabrics (lab_l, lab_a, lab_b);
CREATE INDEX IF NOT EXISTS idx_fabrics_material ON fabrics (material);
CREATE INDEX IF NOT EXISTS idx_fabrics_weave ON fabrics (weave);
CREATE INDEX IF NOT EXISTS idx_fabrics_vendor ON fabrics (vendor);
CREATE INDEX IF NOT EXISTS idx_fabrics_manufacturer ON fabrics (manufacturer, manufacturer_sku);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring a pre-split DB up to the current shape, in place.

    Old shape had `brand`/`manufacturer_url`. We rename them to `vendor`/
    `vendor_url`, add the attribution columns, and backfill `manufacturer`
    (+ `manufacturer_sku`) for the single-source brands scraped before the
    split. No-op on a fresh DB (table absent) or one already migrated.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fabrics)").fetchall()}
    if not cols or "vendor" in cols:
        return
    conn.execute("ALTER TABLE fabrics RENAME COLUMN brand TO vendor")
    conn.execute("ALTER TABLE fabrics RENAME COLUMN manufacturer_url TO vendor_url")
    conn.execute("ALTER TABLE fabrics ADD COLUMN manufacturer TEXT")
    conn.execute("ALTER TABLE fabrics ADD COLUMN manufacturer_sku TEXT")
    conn.execute("DROP INDEX IF EXISTS idx_fabrics_brand")
    # FWD and Robert Kaufman are makers of what they sell; Kaufman also publishes
    # a real SKU (the existing color_code). SY Fabrics' maker is unknown -> null.
    conn.execute(
        "UPDATE fabrics SET manufacturer = vendor"
        " WHERE vendor IN ('Fabric Wholesale Direct', 'Robert Kaufman')"
    )
    conn.execute(
        "UPDATE fabrics SET manufacturer_sku = color_code WHERE vendor = 'Robert Kaufman'"
    )


def init() -> None:
    with connect() as conn:
        _migrate(conn)
        conn.executescript(SCHEMA)
