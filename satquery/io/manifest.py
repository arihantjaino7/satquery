"""Read the structural facts out of a raster file: hash, geometry, shape,
dtype, nodata coverage, and whatever acquisition date is embedded in tags.

This is deliberately dumb and literal — it reports what the file says about
itself. Deciding whether that's *correct* (CRS agrees with a partner image,
footprints overlap enough, ...) is `satquery.io.validate`'s job, not this
module's.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import Polygon, box


@dataclass
class ManifestEntry:
    path: Path
    sha256: str
    driver: str
    has_crs: bool
    crs: str | None            # "EPSG:xxxx" if resolvable, else raw WKT, else None
    transform: tuple[float, float, float, float, float, float]
    shape: tuple[int, int]     # (height, width)
    dtype: str
    band_count: int
    nodata: float | None
    nodata_fraction: float
    gsd: tuple[float, float]   # (x, y) pixel size in CRS units
    footprint_wkt: str
    footprint_corners: list[tuple[float, float]]  # TL, TR, BR, BL
    acquisition_date: str | None


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _nodata_fraction(arr: np.ndarray, nodata: float | None) -> float:
    """Fraction of pixel *locations* where every band is nodata.

    A pixel with some bands nodata and others valid isn't a data gap, it's
    partial information, so this only counts locations with no observation
    at all.
    """
    if nodata is None:
        return 0.0
    if np.isnan(nodata):
        per_band_nodata = np.isnan(arr)
    else:
        per_band_nodata = arr == nodata
    all_bands_nodata = per_band_nodata.all(axis=0)
    return float(all_bands_nodata.mean())


def _parse_acquisition_date(tags: dict[str, str]) -> str | None:
    for key in ("ACQUISITION_DATE", "acquisition_date"):
        if key in tags:
            raw = tags[key]
            try:
                return date.fromisoformat(raw).isoformat()
            except ValueError:
                return raw
    for key in ("TIFFTAG_DATETIME",):
        if key in tags:
            raw = tags[key]
            try:
                return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").date().isoformat()
            except ValueError:
                return raw
    return None


def _footprint(bounds, transform) -> tuple[Polygon, list[tuple[float, float]]]:
    left, bottom, right, top = bounds
    polygon = box(left, bottom, right, top)
    corners = [(left, top), (right, top), (right, bottom), (left, bottom)]  # TL, TR, BR, BL
    return polygon, corners


def read_manifest(path: str | Path) -> ManifestEntry:
    path = Path(path)
    sha256 = _sha256_of_file(path)

    with rasterio.open(path) as ds:
        driver = ds.driver
        has_crs = ds.crs is not None
        if not has_crs:
            crs_str = None
        else:
            epsg = ds.crs.to_epsg()
            crs_str = f"EPSG:{epsg}" if epsg is not None else ds.crs.to_wkt()

        transform = tuple(ds.transform)[:6]
        shape = (ds.height, ds.width)
        dtypes = set(ds.dtypes)
        if len(dtypes) > 1:
            raise ValueError(f"{path}: mixed band dtypes {ds.dtypes} not supported")
        dtype = ds.dtypes[0]
        band_count = ds.count
        nodata = ds.nodata
        gsd = (abs(ds.transform.a), abs(ds.transform.e))

        arr = ds.read()
        nodata_fraction = _nodata_fraction(arr, nodata)

        footprint, corners = _footprint(ds.bounds, ds.transform)
        acquisition_date = _parse_acquisition_date(ds.tags())

    return ManifestEntry(
        path=path,
        sha256=sha256,
        driver=driver,
        has_crs=has_crs,
        crs=crs_str,
        transform=transform,
        shape=shape,
        dtype=str(dtype),
        band_count=band_count,
        nodata=nodata,
        nodata_fraction=nodata_fraction,
        gsd=gsd,
        footprint_wkt=footprint.wkt,
        footprint_corners=corners,
        acquisition_date=acquisition_date,
    )
