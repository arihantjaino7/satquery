import hashlib

import pytest
import rasterio
from shapely.geometry import box

from scripts.make_fixtures import (
    CRS_EPSG,
    GSD,
    HEIGHT,
    WIDTH,
    WRONG_CRS_EPSG,
    build_all,
)

EXPECTED_FILES = {
    "optical_a", "sar_a", "rgb_a", "optical_t1", "optical_t2", "change_mask",
    "broken_wrong_crs", "broken_partial_overlap", "broken_gsd_mismatch", "broken_no_crs",
}


def test_writes_expected_files(fixtures_dir):
    names = {p.stem for p in fixtures_dir.glob("*.tif")}
    assert names == EXPECTED_FILES


def test_optical_sar_are_coregistered(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_a.tif") as opt, \
         rasterio.open(fixtures_dir / "sar_a.tif") as sar:
        assert opt.crs == sar.crs
        assert opt.transform == sar.transform
        assert opt.shape == sar.shape


def test_optical_a_shape_and_dtype(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_a.tif") as ds:
        assert ds.count == 12
        assert ds.dtypes[0] == "uint16"
        assert ds.crs.to_epsg() == CRS_EPSG
        assert ds.shape == (HEIGHT, WIDTH)


def test_sar_a_shape_and_dtype(fixtures_dir):
    with rasterio.open(fixtures_dir / "sar_a.tif") as ds:
        assert ds.count == 2
        assert ds.dtypes[0] == "float32"


def test_broken_wrong_crs_differs_only_in_crs(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_a.tif") as good, \
         rasterio.open(fixtures_dir / "broken_wrong_crs.tif") as bad:
        assert bad.crs.to_epsg() == WRONG_CRS_EPSG
        assert bad.crs != good.crs
        assert bad.transform == good.transform
        assert bad.shape == good.shape


def test_broken_partial_overlap_is_about_60_percent(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_a.tif") as good, \
         rasterio.open(fixtures_dir / "broken_partial_overlap.tif") as bad:
        assert bad.crs == good.crs
        assert bad.transform.a == good.transform.a  # same GSD

        good_box = box(*good.bounds)
        bad_box = box(*bad.bounds)
        overlap_fraction = good_box.intersection(bad_box).area / good_box.area
        assert 0.55 <= overlap_fraction <= 0.65


def test_broken_gsd_mismatch_is_4x(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_a.tif") as good, \
         rasterio.open(fixtures_dir / "broken_gsd_mismatch.tif") as bad:
        assert bad.transform.a == pytest.approx(good.transform.a * 4)
        assert bad.shape == (good.shape[0] // 4, good.shape[1] // 4)
        # same footprint despite coarser pixels
        assert box(*bad.bounds).equals(box(*good.bounds))


def test_broken_no_crs_has_no_crs(fixtures_dir):
    with rasterio.open(fixtures_dir / "broken_no_crs.tif") as ds:
        assert ds.crs is None


def test_change_mask_matches_planted_region(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_t1.tif") as t1, \
         rasterio.open(fixtures_dir / "optical_t2.tif") as t2, \
         rasterio.open(fixtures_dir / "change_mask.tif") as mask_ds:
        mask = mask_ds.read(1)
        changed_fraction = mask.mean()
        assert 0.01 < changed_fraction < 0.10  # a real but small planted region
        assert t1.transform == t2.transform == mask_ds.transform


def test_generation_is_deterministic(tmp_path_factory):
    out_a = tmp_path_factory.mktemp("run_a")
    out_b = tmp_path_factory.mktemp("run_b")
    build_all(out_a, seed=42)
    build_all(out_b, seed=42)

    def sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    for name in EXPECTED_FILES:
        assert sha256(out_a / f"{name}.tif") == sha256(out_b / f"{name}.tif")
