"""Flask app: browse fabrics, filter, color-match.

Run from the project root:
    python -m app.main
Then open http://localhost:5000
"""
import base64
import io
import math

import numpy as np
from flask import Flask, render_template, request
from PIL import Image, ImageDraw

from scraper.color import extract_with_debug, rgb_to_lab
from scraper.db import connect
from scraper.manufacturers.fabricwholesaledirect import FabricWholesaleDirectScraper

app = Flask(__name__)


def hex_to_lab(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"invalid hex: {hex_str}")
    rgb = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    lab = rgb_to_lab(rgb.reshape(1, 3)).reshape(3)
    return float(lab[0]), float(lab[1]), float(lab[2])


DEFAULT_TOLERANCE = 65.0


@app.route("/")
def index():
    material = request.args.get("material", "").strip()
    weave = request.args.get("weave", "").strip()
    target = request.args.get("color", "").strip()
    try:
        tolerance = float(request.args.get("tolerance", DEFAULT_TOLERANCE))
    except ValueError:
        tolerance = DEFAULT_TOLERANCE

    where = ["hex IS NOT NULL"]
    params: list = []
    if material:
        where.append("material = ?")
        params.append(material)
    if weave:
        where.append("weave = ?")
        params.append(weave)

    sql = f"""
        SELECT *
        FROM fabrics
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
            rows = [r for r in rows if r.get("delta_e") is not None and r["delta_e"] <= tolerance]
            rows.sort(key=lambda r: r["delta_e"])
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
        current_tolerance=tolerance,
    )


@app.route("/picker")
def picker():
    return render_template("picker.html")


def _png_data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@app.route("/debug/sample")
def debug_sample():
    listing_url = request.args.get("url", "").strip()
    ctx: dict = {"url": listing_url}
    if not listing_url:
        return render_template("debug_sample.html", **ctx)

    try:
        scraper = FabricWholesaleDirectScraper()
        image_url, info = scraper.resolve_listing_image(listing_url)
        img_bytes = scraper.fetch_image(image_url)
        debug = extract_with_debug(img_bytes)
    except Exception as exc:
        ctx["error"] = f"{exc.__class__.__name__}: {exc}"
        return render_template("debug_sample.html", **ctx)

    # Original with crop box outlined.
    annotated = debug.original.copy()
    draw = ImageDraw.Draw(annotated)
    # Use a stroke width that scales with image size so it stays visible.
    stroke = max(2, min(annotated.size) // 200)
    draw.rectangle(debug.crop_box, outline="#ff0000", width=stroke)

    # Cropped thumbnail with masked-out pixels tinted red, so you can see what
    # k-means ignored. When mask wasn't applied, show the unmodified thumbnail.
    sample = debug.cropped_thumbnail.convert("RGBA")
    if debug.mask_applied:
        overlay = np.zeros((*sample.size[::-1], 4), dtype=np.uint8)
        rejected = (~debug.mask).reshape(sample.size[::-1])
        overlay[rejected] = (255, 0, 0, 140)
        sample = Image.alpha_composite(sample, Image.fromarray(overlay, mode="RGBA"))

    pct_masked = round(100 * (1 - debug.mask.mean()), 1) if debug.mask_applied else 0.0

    ctx.update({
        "info": info,
        "result": debug.result,
        "mask_applied": debug.mask_applied,
        "pct_masked": pct_masked,
        "crop_box": debug.crop_box,
        "original_size": debug.original.size,
        "sample_size": debug.cropped_thumbnail.size,
        "original_b64": _png_data_uri(annotated),
        "sample_b64": _png_data_uri(sample),
    })
    return render_template("debug_sample.html", **ctx)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
