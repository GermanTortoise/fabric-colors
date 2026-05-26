import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fabrics.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS fabrics (
    id INTEGER PRIMARY KEY,
    brand TEXT NOT NULL,
    collection TEXT NOT NULL,
    color_code TEXT NOT NULL,
    color_name TEXT NOT NULL,
    manufacturer_url TEXT NOT NULL UNIQUE,
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
    UNIQUE (brand, collection, color_code)
);

CREATE INDEX IF NOT EXISTS idx_fabrics_lab ON fabrics (lab_l, lab_a, lab_b);
CREATE INDEX IF NOT EXISTS idx_fabrics_material ON fabrics (material);
CREATE INDEX IF NOT EXISTS idx_fabrics_weave ON fabrics (weave);
CREATE INDEX IF NOT EXISTS idx_fabrics_brand ON fabrics (brand);
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
