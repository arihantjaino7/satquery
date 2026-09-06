from dataclasses import replace

from satquery.cli import cmd_validate
from satquery.io.manifest import read_manifest
from satquery.io.validate import (
    Status,
    _check_band_count,
    _check_dimensions,
    _check_format_allowed,
    _check_has_crs,
    _check_has_transform,
    _check_nodata_fraction,
    validate_image,
    validate_pair,
)


def _status(results, name):
    for r in results:
        if r.name == name:
            return r.status
    raise AssertionError(f"no check named {name!r}; have {[r.name for r in results]}")


# -- integration: full pairs against the real fixtures -----------------------


def test_good_pair_is_all_pass(fixtures_dir):
    report = validate_pair(fixtures_dir / "optical_a.tif", fixtures_dir / "sar_a.tif")

    assert report.ok
    assert report.fatal_count == 0
    assert report.warn_count == 0
    assert len(report.results) == 20  # 7 per image + 6 pair checks
    assert all(r.status == Status.PASS for r in report.results)


def test_broken_wrong_crs_fails_on_crs_footprint_and_grid(fixtures_dir):
    report = validate_pair(fixtures_dir / "optical_a.tif", fixtures_dir / "broken_wrong_crs.tif")

    assert not report.ok
    assert _status(report.results, "has_crs[b]") == Status.PASS  # it *has* a CRS, just the wrong one
    assert _status(report.results, "crs_match") == Status.FATAL
    assert _status(report.results, "footprint_overlap") == Status.FATAL
    # grid_alignment measures *fractional* pixel offset (distance to the nearest
    # integer pixel, bounded to [0, 0.5]) rather than raw distance — after
    # reprojecting through the wrong CRS the true offset is ~637km, which wraps
    # to a fraction near the 0.5 worst case, so this still correctly lands FATAL.
    assert _status(report.results, "grid_alignment") == Status.FATAL
    assert _status(report.results, "gsd_ratio") == Status.PASS  # same pixel size either way


def test_broken_partial_overlap_warns_without_halting(fixtures_dir):
    report = validate_pair(fixtures_dir / "optical_a.tif", fixtures_dir / "broken_partial_overlap.tif")

    assert report.fatal_count == 0
    assert report.ok
    assert _status(report.results, "crs_match") == Status.PASS
    assert _status(report.results, "gsd_ratio") == Status.PASS
    assert _status(report.results, "footprint_overlap") == Status.WARN
    assert _status(report.results, "grid_alignment") == Status.WARN


def test_broken_gsd_mismatch_fails_only_gsd_ratio(fixtures_dir):
    report = validate_pair(fixtures_dir / "optical_a.tif", fixtures_dir / "broken_gsd_mismatch.tif")

    assert not report.ok
    assert _status(report.results, "gsd_ratio") == Status.FATAL
    assert _status(report.results, "crs_match") == Status.PASS
    assert _status(report.results, "footprint_overlap") == Status.PASS  # same real-world extent
    assert _status(report.results, "grid_alignment") == Status.PASS  # same origin, no offset
    assert _status(report.results, "dimensions[b]") == Status.PASS  # 64x64 is still usable


def test_broken_no_crs_fails_on_has_crs_and_every_dependent_check(fixtures_dir):
    report = validate_pair(fixtures_dir / "optical_a.tif", fixtures_dir / "broken_no_crs.tif")

    assert not report.ok
    assert _status(report.results, "has_crs[b]") == Status.FATAL
    assert _status(report.results, "crs_match") == Status.FATAL
    assert _status(report.results, "footprint_overlap") == Status.FATAL
    assert _status(report.results, "grid_alignment") == Status.FATAL
    # facts that don't actually depend on CRS are still evaluated, not skipped
    assert _status(report.results, "gsd_ratio") == Status.PASS
    assert _status(report.results, "modality_distinct") == Status.PASS
    assert _status(report.results, "temporal_order") == Status.PASS


def test_validate_image_unreadable_path_gives_single_fatal(tmp_path):
    results = validate_image(tmp_path / "does_not_exist.tif", role="a")

    assert len(results) == 1
    assert results[0].name == "readable[a]"
    assert results[0].status == Status.FATAL


def test_validate_pair_one_side_unreadable_reports_every_pair_check(fixtures_dir, tmp_path):
    report = validate_pair(fixtures_dir / "optical_a.tif", tmp_path / "does_not_exist.tif")

    assert not report.ok
    for name in ("crs_match", "footprint_overlap", "gsd_ratio", "grid_alignment", "modality_distinct", "temporal_order"):
        assert _status(report.results, name) == Status.FATAL


# -- unit: individual check bands, via dataclasses.replace on a real entry --


def test_format_allowed_warns_on_unlisted_driver(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")
    assert _check_format_allowed(entry).status == Status.PASS
    assert _check_format_allowed(replace(entry, driver="PNG")).status == Status.WARN


def test_has_crs_fatal_when_missing(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")
    assert _check_has_crs(entry).status == Status.PASS
    assert _check_has_crs(replace(entry, has_crs=False, crs=None)).status == Status.FATAL


def test_has_transform_fatal_on_identity(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")
    assert _check_has_transform(entry).status == Status.PASS
    identity = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    assert _check_has_transform(replace(entry, transform=identity)).status == Status.FATAL


def test_band_count_fatal_on_zero(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")
    assert _check_band_count(entry).status == Status.PASS
    assert _check_band_count(replace(entry, band_count=0)).status == Status.FATAL


def test_nodata_fraction_bands(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")
    assert _check_nodata_fraction(entry).status == Status.PASS  # real value is ~0.55%
    assert _check_nodata_fraction(replace(entry, nodata_fraction=0.25)).status == Status.WARN
    assert _check_nodata_fraction(replace(entry, nodata_fraction=0.75)).status == Status.FATAL


def test_dimensions_bands(fixtures_dir):
    entry = read_manifest(fixtures_dir / "optical_a.tif")
    assert _check_dimensions(entry).status == Status.PASS  # 256x256
    assert _check_dimensions(replace(entry, shape=(32, 256))).status == Status.WARN
    assert _check_dimensions(replace(entry, shape=(0, 256))).status == Status.FATAL


# -- CLI: prints a readable table, not a crash, for good and broken pairs ---


def test_cmd_validate_good_pair_prints_table(fixtures_dir, capsys):
    report = cmd_validate(str(fixtures_dir / "optical_a.tif"), str(fixtures_dir / "sar_a.tif"))
    out = capsys.readouterr().out

    assert report.ok
    assert "crs_match" in out
    assert "grid_alignment" in out
    assert "Result:" in out


def test_cmd_validate_broken_pair_shows_fatal(fixtures_dir, capsys):
    report = cmd_validate(str(fixtures_dir / "optical_a.tif"), str(fixtures_dir / "broken_wrong_crs.tif"))
    out = capsys.readouterr().out

    assert not report.ok
    assert "FATAL" in out
    assert "HALT" in out
