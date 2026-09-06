"""Decide whether a raster is SAR, RGB, or multispectral optical.

The inference is driven by pixel statistics and structural properties of
the file itself (dtype, band count, skewness, dynamic range) — never by the
filename. `parse_filename_hint` reads the filename separately, purely so the
caller can report whether the two agree; it never feeds the decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio

# Canonical modality labels.
SAR = "sar"
OPTICAL_RGB = "optical_rgb"
OPTICAL_MS = "optical_ms"
OPTICAL_PAN = "optical_pan"
UNKNOWN = "unknown"

_SKEW_HIGH_THRESHOLD = 1.2
_DYNAMIC_RANGE_HIGH_THRESHOLD = 20.0


@dataclass
class ModalityInference:
    path: Path
    inferred: str
    filename_hint: str | None
    agrees_with_hint: bool | None
    evidence: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)


def parse_filename_hint(path: str | Path) -> str | None:
    """What the filename *claims* the modality is. Never used to classify."""
    stem = Path(path).stem.lower()
    tokens = re.split(r"[_\-.]+", stem)
    if "sar" in tokens:
        return SAR
    if "rgb" in tokens:
        return OPTICAL_RGB
    if "pan" in tokens or "panchromatic" in tokens:
        return OPTICAL_PAN
    if "ms" in tokens or "multispectral" in tokens or "optical" in tokens:
        return OPTICAL_MS
    return None


def _band_stats(band: np.ndarray, nodata: float | None) -> dict[str, float]:
    if nodata is not None:
        valid = band[np.isnan(band)] if np.isnan(nodata) else band[band != nodata]
    else:
        valid = band.ravel()
    valid = valid.astype(np.float64)

    if valid.size == 0:
        return {"skew": 0.0, "dyn_range": 0.0}

    mean = valid.mean()
    std = valid.std()
    skew = 0.0 if std == 0 else float(np.mean(((valid - mean) / std) ** 3))

    median = float(np.median(valid))
    vmax = float(valid.max())
    dyn_range = (vmax / median) if median > 0 else vmax

    return {"skew": skew, "dyn_range": dyn_range}


def infer_modality(path: str | Path) -> ModalityInference:
    path = Path(path)

    with rasterio.open(path) as ds:
        band_count = ds.count
        dtype = ds.dtypes[0]
        nodata = ds.nodata
        arr = ds.read()

    is_float = np.dtype(dtype).kind == "f"
    per_band = [_band_stats(arr[i], nodata) for i in range(band_count)]
    mean_skew = float(np.mean([s["skew"] for s in per_band]))
    mean_dyn_range = float(np.mean([s["dyn_range"] for s in per_band]))

    scores = {SAR: 0.0, OPTICAL_RGB: 0.0, OPTICAL_MS: 0.0, OPTICAL_PAN: 0.0}
    evidence: list[str] = []

    # -- dtype: SAR is conventionally stored as float32 linear power/amplitude
    if is_float:
        scores[SAR] += 0.4
        evidence.append(f"dtype={dtype} is floating point -> typical of SAR backscatter power/amplitude")
    else:
        for k in (OPTICAL_RGB, OPTICAL_MS, OPTICAL_PAN):
            scores[k] += 0.2
        evidence.append(f"dtype={dtype} is integer -> typical of quantised optical reflectance/DN")

    # -- band count
    if band_count <= 2:
        scores[SAR] += 0.3
        evidence.append(f"band_count={band_count} (<=2) -> matches single/dual-pol SAR (e.g. VV, VV+VH)")
    elif band_count == 3:
        scores[OPTICAL_RGB] += 0.3
        evidence.append(f"band_count={band_count} (==3) -> matches true-colour RGB")
    else:
        scores[OPTICAL_MS] += 0.3
        evidence.append(f"band_count={band_count} (>3) -> matches multispectral optical (more bands than visible)")
    if band_count == 1:
        scores[OPTICAL_PAN] += 0.2
        evidence.append("band_count=1 -> consistent with panchromatic")

    # -- skewness: SAR speckle + discrete bright scatterers give a heavy right tail
    if mean_skew > _SKEW_HIGH_THRESHOLD:
        scores[SAR] += 0.15
        evidence.append(
            f"mean skewness={mean_skew:.2f} (high, right-tailed) -> consistent with speckle + "
            "bright discrete scatterers typical of SAR"
        )
    else:
        scores[OPTICAL_RGB] += 0.05
        scores[OPTICAL_MS] += 0.05
        evidence.append(f"mean skewness={mean_skew:.2f} (low/moderate) -> consistent with smoother reflectance distributions")

    # -- dynamic range: a handful of pixels dominating the range is a SAR tell
    if mean_dyn_range > _DYNAMIC_RANGE_HIGH_THRESHOLD:
        scores[SAR] += 0.15
        evidence.append(
            f"mean dynamic range (max/median)={mean_dyn_range:.1f} (high) -> a few very bright pixels "
            "dominate, typical of SAR corner reflectors"
        )
    else:
        scores[OPTICAL_RGB] += 0.05
        scores[OPTICAL_MS] += 0.05
        evidence.append(f"mean dynamic range (max/median)={mean_dyn_range:.1f} (low/moderate) -> bounded range typical of optical")

    inferred = max(scores, key=scores.get)

    hint = parse_filename_hint(path)
    agrees = None if hint is None else (hint == inferred)

    return ModalityInference(
        path=path,
        inferred=inferred,
        filename_hint=hint,
        agrees_with_hint=agrees,
        evidence=evidence,
        scores=scores,
    )
