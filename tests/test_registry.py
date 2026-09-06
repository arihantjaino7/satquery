from pathlib import Path

import pytest
import yaml

from satquery.cli import cmd_resolve
from satquery.registry.loader import RegistryLoadError, get_registry, load_registry
from satquery.registry.resolver import resolve

VALID_ENTRY = {
    "id": "test-tool",
    "version": "0.1.0-stub",
    "capabilities": ["vqa"],
    "modalities": ["optical_rgb"],
    "image_count": {"min": 1, "max": 1},
    "input_spec": "single optical tile",
    "weights": "stub",
    "est_vram_mb": 1000,
    "license": "mit",
    "eval_scores": {"vqa": 0.5},
}


def _write(dir_: Path, name: str, data: dict) -> Path:
    path = dir_ / name
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# -- loader: schema validation -----------------------------------------------


def test_valid_entry_loads(tmp_path):
    _write(tmp_path, "a.yaml", VALID_ENTRY)
    specs = load_registry(tmp_path)
    assert len(specs) == 1
    assert specs[0].id == "test-tool"


def test_malformed_entry_bad_capability_fails_loudly(tmp_path):
    bad = {**VALID_ENTRY, "capabilities": ["not_a_real_capability"]}
    _write(tmp_path, "bad.yaml", bad)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "bad.yaml" in str(exc.value)
    assert "capabilities" in str(exc.value)


def test_malformed_entry_missing_field_fails_loudly(tmp_path):
    bad = {k: v for k, v in VALID_ENTRY.items() if k != "license"}
    _write(tmp_path, "bad.yaml", bad)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "bad.yaml" in str(exc.value)
    assert "license" in str(exc.value)


def test_malformed_entry_unknown_field_fails_loudly(tmp_path):
    bad = {**VALID_ENTRY, "totally_unknown_field": 123}
    _write(tmp_path, "bad.yaml", bad)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "bad.yaml" in str(exc.value)


def test_malformed_entry_image_count_min_gt_max_fails_loudly(tmp_path):
    bad = {**VALID_ENTRY, "image_count": {"min": 5, "max": 1}}
    _write(tmp_path, "bad.yaml", bad)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "bad.yaml" in str(exc.value)


def test_malformed_entry_missing_eval_score_for_declared_capability(tmp_path):
    bad = {**VALID_ENTRY, "capabilities": ["vqa", "captioning"], "eval_scores": {"vqa": 0.5}}
    _write(tmp_path, "bad.yaml", bad)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "eval_scores" in str(exc.value)


def test_invalid_yaml_syntax_fails_loudly(tmp_path):
    (tmp_path / "bad.yaml").write_text("id: [unterminated\n", encoding="utf-8")
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "bad.yaml" in str(exc.value)


def test_duplicate_id_fails_loudly(tmp_path):
    _write(tmp_path, "a.yaml", VALID_ENTRY)
    _write(tmp_path, "b.yaml", VALID_ENTRY)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "test-tool" in str(exc.value)


def test_dangling_fallback_fails_loudly(tmp_path):
    bad = {**VALID_ENTRY, "fallback": "does-not-exist"}
    _write(tmp_path, "a.yaml", bad)
    with pytest.raises(RegistryLoadError) as exc:
        load_registry(tmp_path)
    assert "does-not-exist" in str(exc.value)


def test_empty_directory_fails_loudly(tmp_path):
    with pytest.raises(RegistryLoadError):
        load_registry(tmp_path)


# -- loader: picks up every file ---------------------------------------------


def test_loader_picks_up_every_yaml_file(tmp_path):
    for i in range(4):
        _write(tmp_path, f"tool_{i}.yaml", {**VALID_ENTRY, "id": f"tool-{i}"})
    specs = load_registry(tmp_path)
    assert sorted(s.id for s in specs) == [f"tool-{i}" for i in range(4)]


def test_loader_ignores_non_yaml_files(tmp_path):
    _write(tmp_path, "a.yaml", VALID_ENTRY)
    (tmp_path / "README.md").write_text("not a registry entry", encoding="utf-8")
    specs = load_registry(tmp_path)
    assert len(specs) == 1


def test_loader_is_deterministic_across_calls(tmp_path):
    for i in range(5):
        _write(tmp_path, f"tool_{i}.yaml", {**VALID_ENTRY, "id": f"tool-{i}"})
    first = [s.id for s in load_registry(tmp_path)]
    second = [s.id for s in load_registry(tmp_path)]
    assert first == second


def test_default_registry_loads_and_validates():
    """The project's real registry/entries/*.yaml must itself be valid."""
    specs = get_registry()
    assert len(specs) >= 4
    ids = [s.id for s in specs]
    assert len(ids) == len(set(ids))


# -- resolver: filter + rank + reject ----------------------------------------


def test_resolve_change_detection_picks_higher_scoring_specialist():
    result = resolve("change_detection", ["optical_ms"], 2)
    assert result.chosen == "cdvqa-siamese"
    assert len(result.eligible) == 2
    rejected_ids = {c.tool_id for c in result.rejected}
    assert rejected_ids == {"geochat-7b", "rsvqa-baseline", "sar-captioner-lite", "skysense-fusion"}
    for c in result.rejected:
        assert "does not support capability" in c.reason


def test_resolve_records_image_count_rejection_with_named_reason():
    result = resolve("vqa", ["optical_rgb"], 2)
    geochat = next(c for c in result.candidates if c.tool_id == "geochat-7b")
    assert not geochat.eligible
    assert geochat.reason == "image_count max 1 < 2"


def test_resolve_vqa_single_image_picks_geochat_over_rsvqa():
    result = resolve("vqa", ["optical_rgb"], 1)
    assert result.chosen == "geochat-7b"
    rsvqa = next(c for c in result.candidates if c.tool_id == "rsvqa-baseline")
    assert rsvqa.eligible
    assert rsvqa.tool_id != result.chosen  # eligible, but outranked


def test_resolve_cross_modal_fusion_picks_the_only_fusion_tool():
    result = resolve("cross_modal_fusion", ["optical_ms", "sar"], 2)
    assert result.chosen == "skysense-fusion"
    for c in result.rejected:
        assert "does not support capability" in c.reason


def test_resolve_modality_check_is_subset_not_exact_match():
    # requested modalities must all be within what the tool supports, but
    # the tool need not support every modality it *could* handle to qualify
    result = resolve("cross_modal_fusion", ["optical_ms"], 2)
    skysense = next(c for c in result.candidates if c.tool_id == "skysense-fusion")
    assert skysense.eligible


def test_resolve_rejects_on_missing_modality_support():
    result = resolve("captioning", ["sar"], 1)
    assert result.chosen == "sar-captioner-lite"
    geochat = next(c for c in result.candidates if c.tool_id == "geochat-7b")
    assert not geochat.eligible
    assert "missing modality support" in geochat.reason


def test_resolve_nothing_qualifies_returns_empty_not_crash():
    result = resolve("vqa", ["sar"], 5)
    assert result.chosen is None
    assert result.eligible == ()
    assert len(result.rejected) == len(result.candidates) > 0
    for c in result.candidates:
        assert not c.eligible
        assert c.reason  # every rejection is named, never blank


def test_resolve_unknown_capability_rejects_everyone_by_name():
    result = resolve("segmentation", ["optical_rgb"], 1)
    assert result.chosen is None
    assert all("does not support capability 'segmentation'" in c.reason for c in result.candidates)


def test_resolve_is_reproducible_byte_identical_ordering_and_reasoning():
    first = resolve("change_detection", ["optical_ms"], 2)
    second = resolve("change_detection", ["optical_ms"], 2)
    assert first.candidates == second.candidates
    assert first.chosen == second.chosen
    assert [c.tool_id for c in first.candidates] == [c.tool_id for c in second.candidates]
    assert [c.reason for c in first.candidates] == [c.reason for c in second.candidates]


# -- CLI ----------------------------------------------------------------------


def test_cmd_resolve_prints_table_and_returns_result(capsys):
    result = cmd_resolve("change_detection", ["optical_ms"], 2)
    out = capsys.readouterr().out
    assert result.chosen == "cdvqa-siamese"
    assert "CHOSEN" in out
    assert "cdvqa-siamese" in out
    assert "rejected" in out


def test_cmd_resolve_nothing_qualifies_prints_none_not_crash(capsys):
    result = cmd_resolve("vqa", ["sar"], 5)
    out = capsys.readouterr().out
    assert result.chosen is None
    assert "Chosen: none" in out
