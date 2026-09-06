import numpy as np
import rasterio

from satquery.io.preprocess import (
    Tile,
    linear_to_db,
    naive_linear_stretch,
    optical_to_display,
    percentile_clip,
    rescale_to_uint8,
    sar_band_to_display,
    sar_to_display,
    select_optical_bands,
    side_by_side,
    tile_image,
    write_png,
)

S2_BAND_NAMES = [
    "B01", "B02", "B03", "B04", "B05", "B06",
    "B07", "B08", "B8A", "B09", "B11", "B12",
]


def _read_sar_a(fixtures_dir):
    with rasterio.open(fixtures_dir / "sar_a.tif") as ds:
        return ds.read()


def _read_optical_a(fixtures_dir):
    with rasterio.open(fixtures_dir / "optical_a.tif") as ds:
        return ds.read()


# -- building blocks ----------------------------------------------------


def test_linear_to_db_is_zero_guarded():
    x = np.array([0.0, 1e-15, 1.0, 100.0])
    db = linear_to_db(x)
    assert np.all(np.isfinite(db))
    assert db[2] == 0.0  # 10*log10(1) == 0
    assert db[3] == 20.0  # 10*log10(100) == 20


def test_percentile_clip_clamps_outliers_per_band():
    # a single (H, W) band: 98 pixels at 1.0, two outliers at 1000/2000
    band = np.concatenate([np.full(98, 1.0), np.array([1000.0, 2000.0])]).reshape(10, 10)
    clipped = percentile_clip(band, low=2, high=98)
    assert clipped.max() < 1000.0
    assert clipped.min() >= 1.0


def test_percentile_clip_handles_flat_band_without_crashing():
    flat = np.full((4, 4), 5.0)
    clipped = percentile_clip(flat)
    assert np.all(clipped == 5.0)


def test_rescale_to_uint8_maps_min_max_to_0_255():
    band = np.array([[0.0, 5.0], [10.0, 2.5]])
    out = rescale_to_uint8(band)
    assert out.dtype == np.uint8
    assert out.min() == 0
    assert out.max() == 255


def test_rescale_to_uint8_flat_band_is_zeros_not_a_crash():
    flat = np.full((3, 3), 7.0)
    out = rescale_to_uint8(flat)
    assert out.dtype == np.uint8
    assert np.all(out == 0)


# -- the quality cliff, quantified, on real fixture data -----------------


def test_naive_stretch_is_near_black_on_real_sar(fixtures_dir):
    arr = _read_sar_a(fixtures_dir)
    naive = naive_linear_stretch(arr[0])
    # a few bright scatterers dominate a plain min-max range on linear power
    assert (naive < 10).mean() > 0.9


def test_correct_stretch_recovers_a_usable_image_on_the_same_data(fixtures_dir):
    arr = _read_sar_a(fixtures_dir)
    correct = sar_band_to_display(arr[0])
    # same underlying pixels as the naive-stretch test above, very different result
    assert (correct < 10).mean() < 0.1
    assert 50 < np.median(correct) < 220


# -- SAR display path ------------------------------------------------------


def test_sar_to_display_dual_pol_shape_and_dtype(fixtures_dir):
    arr = _read_sar_a(fixtures_dir)
    display = sar_to_display(arr)
    assert display.shape == (3, arr.shape[1], arr.shape[2])
    assert display.dtype == np.uint8


def test_sar_to_display_single_pol_replicates_across_channels(fixtures_dir):
    arr = _read_sar_a(fixtures_dir)
    display = sar_to_display(arr[:1])  # only VV
    assert display.shape == (3, arr.shape[1], arr.shape[2])
    assert np.array_equal(display[0], display[1])
    assert np.array_equal(display[1], display[2])


# -- optical display path ---------------------------------------------------


def test_select_optical_bands_uses_names_not_position():
    arr = np.arange(12 * 4 * 4).reshape(12, 4, 4).astype(np.float64)
    rgb = select_optical_bands(arr, S2_BAND_NAMES)
    # B04, B03, B02 -> indices 3, 2, 1
    assert np.array_equal(rgb[0], arr[3])
    assert np.array_equal(rgb[1], arr[2])
    assert np.array_equal(rgb[2], arr[1])


def test_select_optical_bands_falls_back_to_first_three_without_names():
    arr = np.arange(12 * 4 * 4).reshape(12, 4, 4).astype(np.float64)
    rgb = select_optical_bands(arr, band_names=None)
    assert np.array_equal(rgb, arr[:3])


def test_select_optical_bands_passthrough_when_already_three():
    arr = np.arange(3 * 4 * 4).reshape(3, 4, 4).astype(np.float64)
    rgb = select_optical_bands(arr, band_names=["R", "G", "B"])
    assert rgb is arr


def test_optical_to_display_shape_and_dtype_on_real_fixture(fixtures_dir):
    arr = _read_optical_a(fixtures_dir)
    display = optical_to_display(arr, band_names=S2_BAND_NAMES)
    assert display.shape == (3, arr.shape[1], arr.shape[2])
    assert display.dtype == np.uint8


# -- tiling -------------------------------------------------------------


def test_tile_image_returns_single_tile_when_within_tile_size():
    arr = np.zeros((3, 256, 256))
    tiles = tile_image(arr, tile_size=512)
    assert len(tiles) == 1
    assert tiles[0].height == 256 and tiles[0].width == 256


def test_tile_image_splits_oversized_scene_without_gaps_or_overlap():
    arr = np.arange(3 * 256 * 256).reshape(3, 256, 256)
    tiles = tile_image(arr, tile_size=100)
    # 256 / 100 -> offsets 0, 100, 200 on each axis -> 3x3 = 9 tiles
    assert len(tiles) == 9
    total_pixels = sum(t.height * t.width for t in tiles)
    assert total_pixels == 256 * 256
    # reassembling the tiles must reproduce the original array exactly
    rebuilt = np.zeros_like(arr)
    for t in tiles:
        rebuilt[:, t.row_off:t.row_off + t.height, t.col_off:t.col_off + t.width] = t.array
    assert np.array_equal(rebuilt, arr)


def test_tile_edge_tiles_are_smaller_not_padded():
    arr = np.zeros((1, 130, 130))
    tiles = tile_image(arr, tile_size=100)
    edge_tile = [t for t in tiles if t.row_off == 100 and t.col_off == 100][0]
    assert edge_tile.height == 30 and edge_tile.width == 30
    assert edge_tile.array.shape == (1, 30, 30)


# -- output ---------------------------------------------------------------


def test_write_png_roundtrips(tmp_path):
    arr = np.zeros((3, 5, 7), dtype=np.uint8)
    arr[0] = 255
    out_path = write_png(arr, tmp_path / "out.png")
    assert out_path.exists()
    with rasterio.open(out_path) as ds:
        read_back = ds.read()
    assert np.array_equal(read_back, arr)


def test_side_by_side_concatenates_with_gap():
    left = np.zeros((3, 4, 5), dtype=np.uint8)
    right = np.ones((3, 4, 6), dtype=np.uint8)
    combined = side_by_side(left, right, gap=3)
    assert combined.shape == (3, 4, 5 + 3 + 6)
    gap_slice = combined[:, :, 5:8]
    assert np.all(gap_slice == 255)


def test_side_by_side_pads_shorter_image_to_match_height():
    left = np.zeros((3, 4, 5), dtype=np.uint8)
    right = np.ones((3, 10, 5), dtype=np.uint8)
    combined = side_by_side(left, right, gap=2)
    assert combined.shape[1] == 10


# -- CLI --------------------------------------------------------------------


def test_cmd_preprocess_sar_writes_png(fixtures_dir, tmp_path, capsys):
    from satquery.cli import cmd_preprocess

    out_path = tmp_path / "sar_preview.png"
    result = cmd_preprocess(str(fixtures_dir / "sar_a.tif"), str(out_path))
    out = capsys.readouterr().out

    assert result == out_path
    assert out_path.exists()
    assert "sar" in out.lower()

    with rasterio.open(out_path) as ds:
        assert ds.count == 3
        assert ds.dtypes[0] == "uint8"


def test_cmd_preprocess_optical_writes_png(fixtures_dir, tmp_path):
    from satquery.cli import cmd_preprocess

    out_path = tmp_path / "optical_preview.png"
    cmd_preprocess(str(fixtures_dir / "optical_a.tif"), str(out_path))

    with rasterio.open(out_path) as ds:
        assert ds.count == 3
        assert ds.dtypes[0] == "uint8"


def test_cmd_preprocess_default_output_path(fixtures_dir):
    from satquery.cli import cmd_preprocess

    result = cmd_preprocess(str(fixtures_dir / "sar_a.tif"))
    try:
        assert result.name == "sar_a.preview.png"
        assert result.exists()
    finally:
        result.unlink(missing_ok=True)
