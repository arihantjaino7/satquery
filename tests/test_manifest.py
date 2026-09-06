import hashlib

from satquery.io.manifest import read_manifest


def test_optical_a_manifest(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")

    assert entry.driver == "GTiff"
    assert entry.has_crs
    assert entry.crs == "EPSG:32643"
    assert entry.shape == (256, 256)
    assert entry.dtype == "uint16"
    assert entry.band_count == 12
    assert entry.nodata == 0.0
    assert entry.gsd == (10.0, 10.0)
    assert entry.acquisition_date == "2024-06-15"

    # planted nodata patch is an exact fraction: rows[0:12] x cols[0:30]
    expected_fraction = (12 * 30) / (256 * 256)
    assert entry.nodata_fraction == expected_fraction

    assert len(entry.footprint_corners) == 4
    tl = entry.footprint_corners[0]
    assert tl == (650000.0, 1980000.0)


def test_sha256_matches_raw_file_hash(fixtures_dir):
    path = fixtures_dir / "optical_a.tif"
    entry = read_manifest(path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry.sha256 == expected


def test_sar_a_manifest_no_nodata(fixtures_dir):
    entry = read_manifest(fixtures_dir / "sar_a.tif")

    assert entry.dtype == "float32"
    assert entry.band_count == 2
    assert entry.nodata is None
    assert entry.nodata_fraction == 0.0


def test_broken_no_crs_manifest(fixtures_dir):
    entry = read_manifest(fixtures_dir / "broken_no_crs.tif")
    assert entry.has_crs is False
    assert entry.crs is None
    # everything else about the file is still readable
    assert entry.shape == (256, 256)
    assert entry.band_count == 12


def test_broken_gsd_mismatch_manifest(fixtures_dir):
    entry = read_manifest(fixtures_dir / "broken_gsd_mismatch.tif")
    assert entry.gsd == (40.0, 40.0)
    assert entry.shape == (64, 64)
