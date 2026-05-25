"""Flask app: browse fabrics, filter, color-match.

Run from the project root:
    python -m app.main
Then open http://localhost:5000
"""
import math

import numpy as np
from flask import Flask, render_template, request

from scraper.color import rgb_to_lab
from scraper.db import connect

app = Flask(__name__)


def hex_to_lab(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"invalid hex: {hex_str}")
    rgb = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    lab = rgb_to_lab(rgb.reshape(1, 3)).reshape(3)
    return float(lab[0]), float(lab[1]), float(lab[2])


@app.route("/")
def index():
    material = request.args.get("material", "").strip()
    weave = request.args.get("weave", "").strip()
    target = request.args.get("color", "").strip()

    where = ["hex IS NOT NULL"]
    params: list = []
    if material:
        where.append("material = ?")
        params.append(material)
    if weave:
        where.append("weave = ?")
        params.append(weave)

    sql = f"""
        SELECT f.*, s.name AS store_name
        FROM fabrics f
        JOIN stores s ON s.id = f.store_id
        WHERE {' AND '.join(where)}
        LIMIT 500
    """

    with connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        materials = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT material FROM fabrics WHERE material IS NOT NULL ORDER BY material"
            ).fetchall()
        ]
        weaves = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT weave FROM fabrics WHERE weave IS NOT NULL ORDER BY weave"
            ).fetchall()
        ]

    if target:
        try:
            tl, ta, tb = hex_to_lab(target)
            for r in rows:
                if r["lab_l"] is None:
                    r["delta_e"] = None
                    continue
                r["delta_e"] = math.sqrt(
                    (r["lab_l"] - tl) ** 2
                    + (r["lab_a"] - ta) ** 2
                    + (r["lab_b"] - tb) ** 2
                )
            rows.sort(key=lambda r: (r["delta_e"] is None, r["delta_e"]))
        except ValueError:
            pass

    return render_template(
        "index.html",
        fabrics=rows,
        materials=materials,
        weaves=weaves,
        current_material=material,
        current_weave=weave,
        current_color=target or "#888888",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
