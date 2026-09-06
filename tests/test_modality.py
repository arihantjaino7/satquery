import shutil

from satquery.io.modality import (
    OPTICAL_MS,
    OPTICAL_RGB,
    SAR,
    infer_modality,
    parse_filename_hint,
)


def test_infers_optical_a_as_multispectral(fixtures_dir):
    result = infer_modality(fixtures_dir / "optical_a.tif")
    assert result.inferred == OPTICAL_MS
    assert result.filename_hint == OPTICAL_MS
    assert result.agrees_with_hint is True
    assert result.evidence  # non-empty, explainable


def test_infers_sar_a_as_sar(fixtures_dir):
    result = infer_modality(fixtures_dir / "sar_a.tif")
    assert result.inferred == SAR
    assert result.filename_hint == SAR
    assert result.agrees_with_hint is True


def test_infers_rgb_a_as_rgb(fixtures_dir):
    result = infer_modality(fixtures_dir / "rgb_a.tif")
    assert result.inferred == OPTICAL_RGB
    assert result.filename_hint == OPTICAL_RGB
    assert result.agrees_with_hint is True


def test_inference_ignores_misleading_filename(fixtures_dir, tmp_path):
    # Same bytes as sar_a.tif, but a filename that gives no hint at all.
    decoy = tmp_path / "image_alpha.tif"
    shutil.copyfile(fixtures_dir / "sar_a.tif", decoy)

    result = infer_modality(decoy)
    assert result.inferred == SAR  # decided from pixel stats, unaffected by filename
    assert result.filename_hint is None
    assert result.agrees_with_hint is None


def test_inference_flags_disagreement_with_wrong_filename(fixtures_dir, tmp_path):
    # optical_a's bytes, but named as though it were SAR.
    decoy = tmp_path / "definitely_sar.tif"
    shutil.copyfile(fixtures_dir / "optical_a.tif", decoy)

    result = infer_modality(decoy)
    assert result.inferred == OPTICAL_MS  # stats still say optical, filename is wrong
    assert result.filename_hint == SAR
    assert result.agrees_with_hint is False


def test_parse_filename_hint():
    assert parse_filename_hint("fixtures/sar_a.tif") == SAR
    assert parse_filename_hint("fixtures/rgb_a.tif") == OPTICAL_RGB
    assert parse_filename_hint("fixtures/optical_a.tif") == OPTICAL_MS
    assert parse_filename_hint("fixtures/scene007.tif") is None
