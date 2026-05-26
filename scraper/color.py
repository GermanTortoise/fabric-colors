"""Color extraction from fabric product images.

The center-crop + k-means approach handles the common case: a flat photo of
fabric on a light background. Crops drop the background; k-means (vs. mean)
resists glare and shadow pixels. Output is converted to LAB so the web UI can
compute perceptual distance (Delta E) between a target color and stored fabrics.
"""
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image
from sklearn.cluster import KMeans


@dataclass
class ColorResult:
    hex: str
    lab: tuple[float, float, float]
    rgb: tuple[int, int, int]


@dataclass
class SampleDebug:
    """Intermediate state from the extraction pipeline, for visualization."""
    original: Image.Image
    crop_box: tuple[int, int, int, int]  # (left, top, right, bottom) in original coords
    cropped_thumbnail: Image.Image  # the pixels k-means actually saw
    mask: np.ndarray  # bool, len == cropped_thumbnail width*height
    mask_applied: bool
    result: ColorResult


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(float) / 255.0
    mask = rgb > 0.04045
    linear = np.where(mask, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)

    transform = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = linear @ transform.T

    white = np.array([0.95047, 1.00000, 1.08883])
    xyz_n = xyz / white

    delta = 6 / 29
    f = np.where(
        xyz_n > delta ** 3,
        np.cbrt(np.clip(xyz_n, 0, None)),
        xyz_n / (3 * delta ** 2) + 4 / 29,
    )

    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def _center_crop_box(size: tuple[int, int], ratio: float) -> tuple[int, int, int, int]:
    w, h = size
    cw, ch = int(w * ratio), int(h * ratio)
    left = (w - cw) // 2
    top = (h - ch) // 2
    return (left, top, left + cw, top + ch)


def extract_with_debug(
    image_bytes: bytes,
    center_crop_ratio: float = 0.5,
    n_clusters: int = 3,
) -> SampleDebug:
    original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    crop_box = _center_crop_box(original.size, center_crop_ratio)
    cropped = original.crop(crop_box)
    cropped.thumbnail((200, 200))

    pixels = np.array(cropped).reshape(-1, 3)

    # Only drop very-bright/very-dark pixels if doing so keeps the *majority*
    # of pixels. Pale fabrics (white, ivory) are themselves near-white, so an
    # unconditional brightness filter would discard the fabric and sample
    # only shadow regions, yielding a too-dark hex.
    brightness = pixels.mean(axis=1)
    mask = (brightness > 20) & (brightness < 240)
    mask_applied = bool(mask.sum() > 0.5 * len(pixels))
    used = pixels[mask] if mask_applied else pixels

    n = min(n_clusters, len(used))
    kmeans = KMeans(n_clusters=n, n_init=4, random_state=0).fit(used)
    counts = np.bincount(kmeans.labels_)
    dominant = kmeans.cluster_centers_[counts.argmax()].astype(int)

    r, g, b = (int(c) for c in dominant)
    hex_str = f"#{r:02x}{g:02x}{b:02x}"
    lab = rgb_to_lab(dominant.reshape(1, 3)).reshape(3)
    result = ColorResult(
        hex=hex_str,
        lab=(float(lab[0]), float(lab[1]), float(lab[2])),
        rgb=(r, g, b),
    )
    return SampleDebug(
        original=original,
        crop_box=crop_box,
        cropped_thumbnail=cropped,
        mask=mask,
        mask_applied=mask_applied,
        result=result,
    )


def extract_dominant_color(
    image_bytes: bytes,
    center_crop_ratio: float = 0.5,
    n_clusters: int = 3,
) -> ColorResult:
    return extract_with_debug(image_bytes, center_crop_ratio, n_clusters).result
