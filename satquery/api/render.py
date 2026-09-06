"""Turn in-memory display arrays into base64 PNG data URIs for the browser.

Kept separate from `satquery.io.preprocess.write_png`, which writes to disk
for the CLI/PPT path — the API only ever needs bytes in a response, so this
goes through Pillow and `BytesIO` instead of round-tripping the filesystem
per request.
"""

from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
from PIL import Image


def array_to_png_data_uri(arr_uint8: np.ndarray) -> str:
    """(3, H, W) uint8 -> a `data:image/png;base64,...` string."""
    hwc = np.moveaxis(arr_uint8, 0, -1)
    buf = BytesIO()
    Image.fromarray(hwc, mode="RGB").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def change_mask_overlay_png(
    display_a: np.ndarray,
    display_b: np.ndarray,
    threshold: float,
    color: tuple[int, int, int] = (255, 64, 64),
    alpha: int = 150,
) -> str:
    """RGBA overlay, transparent except `color`@`alpha` where the abs-diff
    between the two display-stretched images exceeds `threshold`.

    `stub_change_detection` only returns aggregate stats (percent changed,
    pixel counts), not the pixel mask itself — this recomputes the same
    abs-diff-threshold arithmetic (same threshold value) purely so the
    canvas has pixels to draw; it is not a second, independent detector.
    """
    diff = np.abs(display_a.astype(np.int16) - display_b.astype(np.int16)).mean(axis=0)
    mask = diff > threshold
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask, 0] = color[0]
    rgba[mask, 1] = color[1]
    rgba[mask, 2] = color[2]
    rgba[mask, 3] = alpha
    buf = BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
