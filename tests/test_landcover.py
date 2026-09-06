"""Contract tests for the swappable land-cover backend: when no trained
weights are available for a given variant, `predict()` must degrade to
`None` cleanly (never raise) so `node_execute` falls back to the stub
exactly as it did before this module existed. Weights now exist in this
checkout (Step 7 trained on Colab - see the step7_bigearthnet_training
memory), so these tests monkeypatch the variant-file paths to nonexistent
locations rather than relying on the ambient absence of models_weights/ -
the "no weights yet" contract has to hold on a fresh clone too, not just
in an environment that happens to have none.
"""

from __future__ import annotations

import importlib.util

import pytest

from satquery.models import landcover

_TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None
_HAS_S1_WEIGHTS = landcover._VARIANT_FILES["s1"].exists()


def test_predict_returns_none_when_no_weights_exist(fixtures_dir, tmp_path, monkeypatch):
    missing = {variant: tmp_path / f"missing_{variant}.pt" for variant in landcover._VARIANT_FILES}
    monkeypatch.setattr(landcover, "_VARIANT_FILES", missing)
    landcover._load_model.cache_clear()

    assert landcover._select_variant("sar") is None
    assert landcover._select_variant("optical_ms") is None
    assert landcover.predict(fixtures_dir / "optical_a.tif", "optical_ms") is None
    assert landcover.predict(fixtures_dir / "sar_a.tif", "sar") is None


def test_corine_19_classes_is_fixed_length():
    # The trained model's output layer size is len(CORINE_19_CLASSES) -
    # changing this without retraining silently breaks weight loading.
    assert len(landcover.CORINE_19_CLASSES) == 19
    assert len(set(landcover.CORINE_19_CLASSES)) == 19


def test_load_model_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setitem(landcover._VARIANT_FILES, "s2", tmp_path / "does-not-exist.pt")
    landcover._load_model.cache_clear()
    assert landcover._load_model("s2") is None


@pytest.mark.skipif(
    not (_TORCH_AVAILABLE and _HAS_S1_WEIGHTS),
    reason="requires torch installed and a trained s1 checkpoint in models_weights/",
)
def test_predict_real_inference_on_matching_sar_fixture(fixtures_dir):
    # fixtures/sar_a.tif is a 2-band SAR fixture - matches the s1 variant's
    # expected channel count exactly, so this exercises real inference, not
    # the stub fallback (the model has no idea it's a synthetic fixture and
    # not a real Sentinel-1 patch, so the *labels* are meaningless - this
    # only asserts the plumbing works end to end).
    landcover._load_model.cache_clear()
    result = landcover.predict(fixtures_dir / "sar_a.tif", "sar")

    assert result is not None
    assert result["stub"] is False
    assert result["variant"] == "s1"
    assert len(result["top5"]) == 5
    assert all(0.0 <= c["score"] <= 1.0 for c in result["top5"])
    assert isinstance(result["answer"], str) and "s1-encoder" in result["answer"]
