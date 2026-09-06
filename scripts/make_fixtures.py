"""Generate synthetic GeoTIFF fixtures for SatQuery AI development.

Nothing downstream should ever be blocked on a real download: this produces a
co-registered optical (12-band uint16) + SAR (2-band float32) pair, an RGB
derivative, a bi-temporal pair with a planted change region, and four
"broken" variants that each isolate exactly one real-world ingestion fault
(wrong CRS, partial footprint overlap, GSD mismatch, missing CRS).

All content is deterministic (fixed RNG seeds) so re-running this script
reproduces byte-identical files.

Run:  ./.venv/Scripts/python.exe scripts/make_fixtures.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

# ---------------------------------------------------------------------------
# Shared grid: everything below is expressed relative to this so that
# co-registration ("same CRS, same transform, same shape") is trivially true
# unless a fixture is deliberately built to break it.
# ---------------------------------------------------------------------------

CRS_EPSG = 32643  # WGS 84 / UTM zone 43N — plausible for an ISRO scene over India
WRONG_CRS_EPSG = 32644  # adjacent UTM zone: a classic "picked the wrong zone" bug
GSD = 10.0  # metres/pixel, Sentinel-2-like
HEIGHT = WIDTH = 256
ORIGIN_X = 650000.0
ORIGIN_Y = 1980000.0
BASE_TRANSFORM = Affine(GSD, 0.0, ORIGIN_X, 0.0, -GSD, ORIGIN_Y)

# BigEarthNet-style 12-band Sentinel-2 order (B10 cirrus dropped, as BEN does)
S2_BAND_NAMES = [
    "B01", "B02", "B03", "B04", "B05", "B06",
    "B07", "B08", "B8A", "B09", "B11", "B12",
]

# Fractional (row0, row1, col0, col1) land-cover regions, shape-independent.
# class 0 is implicit background (bare soil) everywhere else.
REGIONS = {
    1: (0.08, 0.27, 0.08, 0.35),   # water
    2: (0.55, 0.90, 0.10, 0.47),   # vegetation
    3: (0.15, 0.43, 0.62, 0.90),   # urban / built-up
}

# Sub-box inside the vegetation region that gets bulldozed into "urban"
# between t1 and t2 — the planted change region.
CHANGE_REGION_FRAC = (0.65, 0.80, 0.20, 0.35)

# Small sensor-gap patch used to exercise nodata_fraction.
NODATA_REGION_FRAC = (0.0, 0.05, 0.0, 0.12)

# Roughly plausible Sentinel-2 surface-reflectance-ish DN values (0-10000
# scale) per class, in S2_BAND_NAMES order. Not radiometrically exact —
# just physically ordered (water dark and darkest in NIR/SWIR, vegetation
# has the classic red-edge jump, urban is bright and comparatively flat).
CLASS_REFLECTANCE = {
    0: [1200, 1300, 1500, 1800, 2000, 2200, 2300, 2400, 2450, 2100, 3000, 2600],  # bare soil
    1: [600, 500, 400, 250, 150, 100, 90, 80, 75, 70, 50, 40],                    # water
    2: [800, 700, 900, 600, 1500, 3200, 3600, 3800, 3900, 3700, 1400, 900],       # vegetation
    3: [1600, 1700, 1900, 2100, 2200, 2300, 2350, 2500, 2550, 2300, 2800, 2600],  # urban
}

# (VV, VH) linear backscatter power per class — water near-specular (very
# low return), vegetation moderate with more volume (VH) scattering, urban
# bright from double-bounce.
SAR_BASE = {
    0: (0.02, 0.01),
    1: (0.002, 0.001),
    2: (0.05, 0.03),
    3: (0.35, 0.08),
}


def _region_slice(shape: tuple[int, int], frac: tuple[float, float, float, float]) -> tuple[slice, slice]:
    h, w = shape
    r0, r1, c0, c1 = frac
    return slice(int(r0 * h), int(r1 * h)), slice(int(c0 * w), int(c1 * w))


def _landcover_mask(shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    for cls, frac in REGIONS.items():
        rs, cs = _region_slice(shape, frac)
        mask[rs, cs] = cls
    return mask


def _synth_optical_scene(mask: np.ndarray, seed: int) -> np.ndarray:
    """(bands, H, W) uint16, reflectance-like, per-class spectral curve + noise."""
    rng = np.random.default_rng(seed)
    n_bands = len(S2_BAND_NAMES)
    arr = np.zeros((n_bands, *mask.shape), dtype=np.float64)
    for b in range(n_bands):
        base = np.zeros(mask.shape, dtype=np.float64)
        for cls, values in CLASS_REFLECTANCE.items():
            base[mask == cls] = values[b]
        noise = rng.normal(loc=1.0, scale=0.04, size=mask.shape)
        arr[b] = base * noise
    arr = np.clip(arr, 0, 10000)
    return arr.astype(np.uint16)


def _synth_sar_scene(mask: np.ndarray, seed: int) -> np.ndarray:
    """(2, H, W) float32 VV/VH linear power: exponential speckle + bright outliers.

    Single-look intensity speckle is exponentially distributed around the
    class mean backscatter; a handful of urban pixels get boosted further to
    mimic corner-reflector returns. This is exactly the heavy right tail that
    makes a naive min-max stretch on SAR produce a near-black image (Step 3).
    """
    rng = np.random.default_rng(seed)
    arr = np.zeros((2, *mask.shape), dtype=np.float64)
    for pol in range(2):
        base = np.zeros(mask.shape, dtype=np.float64)
        for cls, values in SAR_BASE.items():
            base[mask == cls] = values[pol]
        speckle = rng.exponential(scale=1.0, size=mask.shape)
        arr[pol] = base * speckle

    urban_pixels = np.argwhere(mask == 3)
    if len(urban_pixels) > 0:
        n_outliers = max(1, int(0.003 * len(urban_pixels)))
        idx = rng.choice(len(urban_pixels), size=n_outliers, replace=False)
        for i in idx:
            r, c = urban_pixels[i]
            arr[:, r, c] *= rng.uniform(6.0, 15.0)

    return arr.astype(np.float32)


def _write_geotiff(
    path: Path,
    array: np.ndarray,
    transform: Affine,
    crs: CRS | None,
    nodata: float | None = None,
    band_names: list[str] | None = None,
    tags: dict[str, str] | None = None,
) -> Path:
    count, height, width = array.shape
    profile = dict(
        driver="GTiff",
        height=height,
        width=width,
        count=count,
        dtype=array.dtype,
        crs=crs,
        transform=transform,
    )
    if nodata is not None:
        profile["nodata"] = nodata
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array)
        if band_names:
            for i, name in enumerate(band_names, start=1):
                dst.set_band_description(i, name)
        if tags:
            dst.update_tags(**tags)
    return path


def build_all(out_dir: Path, seed: int = 42) -> dict[str, Path]:
    out_dir = Path(out_dir)
    crs = CRS.from_epsg(CRS_EPSG)
    paths: dict[str, Path] = {}

    # -- co-registered optical + SAR pair -----------------------------------
    mask = _landcover_mask((HEIGHT, WIDTH))

    optical_arr = _synth_optical_scene(mask, seed=seed)
    nodata_rs, nodata_cs = _region_slice((HEIGHT, WIDTH), NODATA_REGION_FRAC)
    optical_arr[:, nodata_rs, nodata_cs] = 0

    paths["optical_a"] = _write_geotiff(
        out_dir / "optical_a.tif", optical_arr, BASE_TRANSFORM, crs,
        nodata=0, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    sar_arr = _synth_sar_scene(mask, seed=seed + 1)
    paths["sar_a"] = _write_geotiff(
        out_dir / "sar_a.tif", sar_arr, BASE_TRANSFORM, crs,
        nodata=None, band_names=["VV", "VH"],
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    # -- RGB derivative (true colour: B04/B03/B02 -> uint8) ------------------
    rgb_u16 = optical_arr[[3, 2, 1], :, :].astype(np.float64)
    rgb_arr = np.clip(rgb_u16 / 12.0, 0, 255).astype(np.uint8)
    paths["rgb_a"] = _write_geotiff(
        out_dir / "rgb_a.tif", rgb_arr, BASE_TRANSFORM, crs,
        nodata=0, band_names=["R", "G", "B"],
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    # -- bi-temporal pair with a planted change region ------------------------
    mask_t1 = mask.copy()
    change_rs, change_cs = _region_slice((HEIGHT, WIDTH), CHANGE_REGION_FRAC)
    mask_t2 = mask_t1.copy()
    mask_t2[change_rs, change_cs] = 3  # vegetation -> urban

    optical_t1 = _synth_optical_scene(mask_t1, seed=seed + 10)
    optical_t2 = _synth_optical_scene(mask_t2, seed=seed + 11)

    paths["optical_t1"] = _write_geotiff(
        out_dir / "optical_t1.tif", optical_t1, BASE_TRANSFORM, crs,
        nodata=None, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2023-01-10"},
    )
    paths["optical_t2"] = _write_geotiff(
        out_dir / "optical_t2.tif", optical_t2, BASE_TRANSFORM, crs,
        nodata=None, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2024-03-22"},
    )

    change_mask = (mask_t1 != mask_t2).astype(np.uint8)[np.newaxis, :, :]
    paths["change_mask"] = _write_geotiff(
        out_dir / "change_mask.tif", change_mask, BASE_TRANSFORM, crs,
        nodata=None, band_names=["change"],
        tags={"DESCRIPTION": "ground-truth planted change mask (1 = changed)"},
    )

    # -- broken variants, each isolating exactly one fault --------------------

    # wrong CRS: correct-looking transform, adjacent UTM zone -> silently
    # mislocated by ~100 km even though every number "looks" plausible.
    paths["broken_wrong_crs"] = _write_geotiff(
        out_dir / "broken_wrong_crs.tif", optical_arr, BASE_TRANSFORM,
        CRS.from_epsg(WRONG_CRS_EPSG), nodata=0, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    # 60% footprint overlap: correct CRS/GSD/shape, origin shifted east by
    # 0.4 * width so only 60% of the frame overlaps optical_a.
    shifted_transform = Affine(GSD, 0.0, ORIGIN_X + 0.4 * WIDTH * GSD, 0.0, -GSD, ORIGIN_Y)
    overlap_mask = _landcover_mask((HEIGHT, WIDTH))
    overlap_arr = _synth_optical_scene(overlap_mask, seed=seed + 20)
    paths["broken_partial_overlap"] = _write_geotiff(
        out_dir / "broken_partial_overlap.tif", overlap_arr, shifted_transform, crs,
        nodata=0, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    # 4x GSD mismatch: same CRS + origin + footprint, 40 m pixels -> 64x64.
    coarse_transform = Affine(GSD * 4, 0.0, ORIGIN_X, 0.0, -GSD * 4, ORIGIN_Y)
    coarse_shape = (HEIGHT // 4, WIDTH // 4)
    coarse_mask = _landcover_mask(coarse_shape)
    coarse_arr = _synth_optical_scene(coarse_mask, seed=seed + 21)
    paths["broken_gsd_mismatch"] = _write_geotiff(
        out_dir / "broken_gsd_mismatch.tif", coarse_arr, coarse_transform, crs,
        nodata=0, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    # missing CRS: identical grid and content to optical_a, CRS tag stripped.
    paths["broken_no_crs"] = _write_geotiff(
        out_dir / "broken_no_crs.tif", optical_arr, BASE_TRANSFORM, None,
        nodata=0, band_names=S2_BAND_NAMES,
        tags={"ACQUISITION_DATE": "2024-06-15"},
    )

    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("fixtures"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    paths = build_all(args.out_dir, seed=args.seed)
    print(f"Wrote {len(paths)} fixtures to {args.out_dir.resolve()}:")
    for name, path in paths.items():
        size_kb = path.stat().st_size / 1024
        print(f"  {name:<24} {path.name:<28} {size_kb:8.1f} KB")


if __name__ == "__main__":
    main()
