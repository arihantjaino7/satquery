"""Turn a raster array into something a human or a VLM can actually look at.

The quality cliff this module exists to cross: SAR backscatter is stored as
linear power, and a handful of pixels (corner reflectors, urban double-bounce)
can be 100-1000x brighter than the terrain around them. Stretch that range
naively (plain min-max to 0-255) and those outliers eat the whole range —
everything else, which is what's actually being asked about, collapses to
near-black. `naive_linear_stretch` reproduces that failure on purpose so it
can be shown, not just claimed; `sar_to_display` is the fix: convert to
decibels first (which compresses the outliers logarithmically), clip to the
2nd/98th percentile (which discards what's left of the extremes), then
rescale to 8-bit.

Optical doesn't have the same power-law problem, so it only needs correct
band selection (pick the true-colour bands by name, not by guessing position)
and the same percentile stretch. `tile_image` exists for scenes too large to
hand a model in one piece; on a scene already within `tile_size` it's a no-op
that returns one tile covering the whole image.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning

_DB_EPSILON = 1e-10  # floor before log10 so a zero/negative pixel yields a
                      # very negative dB value instead of -inf/NaN

_S2_TRUE_COLOR_BANDS = ("B04", "B03", "B02")  # red, green, blue


# ---------------------------------------------------------------------------
# Building blocks — each is a small, pure, independently testable step.
# ---------------------------------------------------------------------------


def linear_to_db(x: np.ndarray) -> np.ndarray:
    """Linear power/amplitude -> decibels: 10*log10(x), zero-guarded."""
    return 10.0 * np.log10(np.clip(x, _DB_EPSILON, None))


def _band_percentile_clip(band: np.ndarray, low: float, high: float) -> np.ndarray:
    lo, hi = np.percentile(band, [low, high])
    if hi <= lo:  # a flat band: nothing to stretch, avoid a zero-width range
        return np.full_like(band, lo, dtype=np.float64)
    return np.clip(band, lo, hi)


def percentile_clip(arr: np.ndarray, low: float = 2.0, high: float = 98.0) -> np.ndarray:
    """Clip each band independently to its own [low, high] percentile range.

    Per-band, not global: SAR polarisations (and optical bands) sit on
    different scales, so a shared range would let one band dominate the
    others exactly the way the naive stretch lets outliers dominate.
    """
    if arr.ndim == 2:
        return _band_percentile_clip(arr.astype(np.float64), low, high)
    return np.stack([_band_percentile_clip(arr[i].astype(np.float64), low, high) for i in range(arr.shape[0])])


def _band_to_uint8(band: np.ndarray) -> np.ndarray:
    lo, hi = float(band.min()), float(band.max())
    if hi <= lo:
        return np.zeros(band.shape, dtype=np.uint8)
    scaled = (band - lo) / (hi - lo) * 255.0
    return np.clip(scaled, 0, 255).astype(np.uint8)


def rescale_to_uint8(arr: np.ndarray) -> np.ndarray:
    """Linearly rescale each band's own min-max to 0-255."""
    if arr.ndim == 2:
        return _band_to_uint8(arr)
    return np.stack([_band_to_uint8(arr[i]) for i in range(arr.shape[0])])


def naive_linear_stretch(arr: np.ndarray) -> np.ndarray:
    """The wrong way to display SAR: a plain min-max stretch directly on
    linear power, no dB conversion, no outlier clipping. Exists to
    demonstrate the failure mode `sar_to_display` fixes — see
    `scripts/demo_sar_stretch.py`.
    """
    return rescale_to_uint8(arr.astype(np.float64))


# ---------------------------------------------------------------------------
# SAR display path.
# ---------------------------------------------------------------------------


def sar_band_to_display(band: np.ndarray, low: float = 2.0, high: float = 98.0) -> np.ndarray:
    """Correct single-band SAR path: linear -> dB -> percentile clip -> uint8."""
    return rescale_to_uint8(percentile_clip(linear_to_db(band), low, high))


def sar_to_display(arr: np.ndarray, low: float = 2.0, high: float = 98.0) -> np.ndarray:
    """SAR array (bands, H, W) of linear power -> a 3-channel uint8 image.

    Dual-pol uses the conventional VV / VH / ratio false-colour scheme. The
    ratio channel is built as `dB(VV) - dB(VH)` rather than a separate
    VV/VH division: subtracting two already-guarded dB bands *is* the ratio
    in dB, with no extra epsilon-guarding needed. Single-pol repeats the one
    band across all three channels (a correctly stretched grayscale image).
    """
    if arr.shape[0] >= 2:
        db_vv = linear_to_db(arr[0])
        db_vh = linear_to_db(arr[1])
        ratio_db = db_vv - db_vh
        stack = np.stack([db_vv, db_vh, ratio_db])
    else:
        db = linear_to_db(arr[0])
        stack = np.stack([db, db, db])

    return rescale_to_uint8(percentile_clip(stack, low, high))


# ---------------------------------------------------------------------------
# Optical display path.
# ---------------------------------------------------------------------------


def select_optical_bands(
    arr: np.ndarray,
    band_names: list[str] | None,
    target: tuple[str, str, str] = _S2_TRUE_COLOR_BANDS,
) -> np.ndarray:
    """Pick the three bands to show as RGB. Uses band *names* when available,
    so the result is correct regardless of how the bands happen to be
    ordered in the file; falls back to position only when no names exist.
    """
    count = arr.shape[0]
    if count == 3:
        return arr
    if band_names and all(name in band_names for name in target):
        idx = [band_names.index(name) for name in target]
        return arr[idx]
    if count == 1:
        return np.concatenate([arr, arr, arr], axis=0)
    return arr[:3]  # no names to trust and more than 3 bands: best-effort


def optical_to_display(
    arr: np.ndarray,
    band_names: list[str] | None = None,
    low: float = 2.0,
    high: float = 98.0,
) -> np.ndarray:
    """Optical array (bands, H, W), any dtype -> 3-channel uint8."""
    rgb = select_optical_bands(arr, band_names)
    return rescale_to_uint8(percentile_clip(rgb, low, high))


# ---------------------------------------------------------------------------
# Tiling for oversized scenes.
# ---------------------------------------------------------------------------


@dataclass
class Tile:
    array: np.ndarray
    row_off: int
    col_off: int
    height: int
    width: int


def tile_image(arr: np.ndarray, tile_size: int = 512) -> list[Tile]:
    """Split a (bands, H, W) array into tile_size x tile_size tiles. Edge
    tiles are smaller, never padded. A scene already within tile_size on
    both axes comes back as a single tile covering the whole image, so
    callers can always tile-then-process without a size special case.
    """
    _, h, w = arr.shape
    tiles: list[Tile] = []
    for row_off in range(0, h, tile_size):
        th = min(tile_size, h - row_off)
        for col_off in range(0, w, tile_size):
            tw = min(tile_size, w - col_off)
            tiles.append(Tile(arr[:, row_off:row_off + th, col_off:col_off + tw], row_off, col_off, th, tw))
    return tiles


# ---------------------------------------------------------------------------
# Output.
# ---------------------------------------------------------------------------


def write_png(arr_uint8: np.ndarray, path: str | Path) -> Path:
    """Write a (3, H, W) uint8 array as a plain PNG — for viewing, not
    further geospatial processing, so no georeferencing is attached.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="PNG", height=arr_uint8.shape[1], width=arr_uint8.shape[2], count=3, dtype="uint8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(arr_uint8)
    return path


def side_by_side(left: np.ndarray, right: np.ndarray, gap: int = 12) -> np.ndarray:
    """Concatenate two (3, H, W) uint8 images horizontally with a white gap
    column, for a single before/after comparison image.
    """
    h = max(left.shape[1], right.shape[1])

    def _pad(img: np.ndarray) -> np.ndarray:
        pad_h = h - img.shape[1]
        if pad_h == 0:
            return img
        return np.pad(img, ((0, 0), (0, pad_h), (0, 0)), constant_values=255)

    left, right = _pad(left), _pad(right)
    gap_col = np.full((3, h, gap), 255, dtype=np.uint8)
    return np.concatenate([left, gap_col, right], axis=2)
