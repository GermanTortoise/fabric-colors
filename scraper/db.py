import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fabrics.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fabrics (
    id INTEGER PRIMARY KEY,
    store_id INTEGER NOT NULL REFERENCES stores(id),
    store_product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
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
    raw_color_name TEXT,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reviewed INTEGER DEFAULT 0,
    UNIQUE (store_id, store_product_id)
);

CREATE INDEX IF NOT EXISTS idx_fabrics_lab ON fabrics (lab_l, lab_a, lab_b);
CREATE INDEX IF NOT EXISTS idx_fabrics_material ON fabrics (material);
CREATE INDEX IF NOT EXISTS idx_fabrics_weave ON fabrics (weave);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
