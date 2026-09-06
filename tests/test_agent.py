from satquery.agent.confidence import compute_confidence
from satquery.agent.graph import NODE_ORDER, run
from satquery.agent.nodes import _classify_question, node_ingest, node_validate
from satquery.agent.state import SatQueryState


def _run(fixtures_dir, question, *names):
    paths = [fixtures_dir / f"{n}.tif" for n in names]
    return run(question, paths)


# -- full pipeline: the four outcome paths -----------------------------------


def test_change_detection_answers_with_real_derived_stat(fixtures_dir):
    state = _run(fixtures_dir, "What changed between these two images?", "optical_t1", "optical_t2")

    assert state.outcome == "answered"
    assert state.task == "change_detection"
    assert state.plan.chosen == "cdvqa-siamese"
    assert state.execution["stub"] is True
    assert 0.0 < state.execution["percent_changed"] < 100.0  # real pixel diff, not a placeholder constant
    assert "percent_changed" in state.fused
    assert state.answer is not None and "changed" in state.answer
    assert len(state.trace) == len(NODE_ORDER) == 9
    assert [t.node for t in state.trace] == list(NODE_ORDER)
    assert all(t.status != "skipped" for t in state.trace)  # nothing skipped on the happy path


def test_single_image_vqa_answers(fixtures_dir):
    state = _run(fixtures_dir, "What is in this image?", "optical_a")

    assert state.outcome == "answered"
    assert state.task == "vqa"
    assert state.plan.chosen == "geochat-7b"
    assert state.execution["stub"] is True
    assert "stub" in state.answer.lower()


def test_cross_modal_fusion_answers(fixtures_dir):
    state = _run(fixtures_dir, "Can you fuse the radar and optical sensors here?", "optical_a", "sar_a")

    assert state.outcome == "answered"
    assert state.task == "cross_modal_fusion"
    assert state.plan.chosen == "skysense-fusion"
    assert set(state.modalities) == {"optical_ms", "sar"}


def test_rejected_path_halts_before_classify(fixtures_dir):
    state = _run(fixtures_dir, "What changed?", "optical_a", "broken_wrong_crs")

    assert state.outcome == "rejected"
    assert state.answer is not None and "failed validation" in state.answer
    by_node = {t.node: t.status for t in state.trace}
    assert by_node["ingest"] == "ok"
    assert by_node["validate"] == "fatal"
    assert by_node["classify"] == "skipped"
    assert by_node["plan"] == "skipped"
    assert by_node["preprocess"] == "skipped"
    assert by_node["execute"] == "skipped"
    assert by_node["fuse"] == "skipped"
    assert by_node["confidence"] == "ok"  # confidence and respond always run
    assert by_node["respond"] == "fatal"
    assert len(state.trace) == 9


def test_rejected_path_on_unreadable_image(tmp_path, fixtures_dir):
    fake = tmp_path / "not_a_raster.tif"
    fake.write_bytes(b"not a real tiff")
    state = _run_paths("bogus question", [fixtures_dir / "optical_a.tif", fake])

    assert state.outcome == "rejected"
    by_node = {t.node: t.status for t in state.trace}
    assert by_node["ingest"] == "fatal"
    assert by_node["validate"] == "skipped"
    assert by_node["classify"] == "skipped"


def _run_paths(question, paths):
    return run(question, paths)


def test_clarify_path_on_ambiguous_question(fixtures_dir):
    state = _run(fixtures_dir, "hello there", "optical_a")

    assert state.outcome == "clarify"
    assert state.task is None
    assert state.answer is not None and "clarify" in state.answer.lower()
    by_node = {t.node: t.status for t in state.trace}
    assert by_node["classify"] == "warn"
    assert by_node["plan"] == "skipped"
    assert by_node["preprocess"] == "skipped"
    assert by_node["confidence"] == "ok"
    assert by_node["respond"] == "warn"


def test_degraded_path_when_no_tool_matches(fixtures_dir):
    # vqa on a single SAR image: geochat-7b/rsvqa-baseline are optical-only,
    # skysense-fusion needs 2 images - nothing in the registry qualifies.
    state = _run(fixtures_dir, "What is in this image?", "sar_a")

    assert state.outcome == "degraded"
    assert state.task == "vqa"
    assert state.plan.chosen is None
    assert len(state.plan.rejected) == len(state.plan.candidates)
    assert "no registered tool" in state.answer
    for c in state.plan.rejected:
        assert c.tool_id in state.answer  # every rejected candidate is named in the response
    by_node = {t.node: t.status for t in state.trace}
    assert by_node["plan"] == "warn"
    assert by_node["preprocess"] == "ok"  # doesn't depend on which tool was chosen, still renders for display
    assert by_node["execute"] == "skipped"


# -- determinism ---------------------------------------------------------


def test_plan_section_is_byte_identical_across_runs(fixtures_dir):
    state_1 = _run(fixtures_dir, "What changed between these two images?", "optical_t1", "optical_t2")
    state_2 = _run(fixtures_dir, "What changed between these two images?", "optical_t1", "optical_t2")

    assert state_1.plan == state_2.plan
    assert state_1.execution == state_2.execution
    assert state_1.confidence == state_2.confidence
    assert state_1.answer == state_2.answer
    assert [t.node for t in state_1.trace] == [t.node for t in state_2.trace]
    assert [t.status for t in state_1.trace] == [t.status for t in state_2.trace]
    assert [t.message for t in state_1.trace] == [t.message for t in state_2.trace]
    assert [t.data for t in state_1.trace] == [t.data for t in state_2.trace]


# -- classify: the deterministic stub keyword classifier ----------------------


def test_classify_change_detection_keywords():
    task, scores, ambiguous = _classify_question("what changed here compared to before?", ("optical_ms",))
    assert task == "change_detection"
    assert not ambiguous


def test_classify_no_keywords_is_ambiguous():
    task, scores, ambiguous = _classify_question("hello there", ("optical_ms",))
    assert task is None
    assert ambiguous


def test_classify_tie_is_ambiguous():
    # "what" -> vqa; "where" -> grounding; equal top scores, genuinely ambiguous
    task, scores, ambiguous = _classify_question("what and where", ("optical_ms",))
    assert ambiguous
    assert task is None


def test_classify_cross_modal_bonus_from_distinct_modalities():
    task, scores, ambiguous = _classify_question("radar fusion combined", ("optical_ms", "sar"))
    assert task == "cross_modal_fusion"
    assert scores["cross_modal_fusion"] >= 2.0  # keyword hits + the distinct-modality bonus


# -- node_ingest / node_validate in isolation ---------------------------------


def test_node_ingest_rejects_unreadable_file(tmp_path):
    fake = tmp_path / "broken.tif"
    fake.write_bytes(b"garbage")
    state = SatQueryState(question="q", image_paths=(fake,))
    new_state, entry = node_ingest(state)
    assert new_state.outcome == "rejected"
    assert entry.status == "fatal"


def test_node_validate_rejects_zero_images():
    state = SatQueryState(question="q", image_paths=())
    new_state, entry = node_validate(state)
    assert new_state.outcome == "rejected"
    assert entry.status == "fatal"


def test_node_validate_rejects_more_than_two_images(fixtures_dir):
    state = SatQueryState(question="q", image_paths=tuple(fixtures_dir / n for n in ("optical_a.tif", "sar_a.tif", "rgb_a.tif")))
    new_state, entry = node_validate(state)
    assert new_state.outcome == "rejected"
    assert entry.status == "fatal"


# -- confidence: four named components, never a single opaque number ---------


def test_confidence_has_four_named_components(fixtures_dir):
    state = _run(fixtures_dir, "What changed between these two images?", "optical_t1", "optical_t2")
    components = state.confidence["components"]
    assert set(components) == {"input_quality", "task_certainty", "model_fitness", "output_agreement"}
    for c in components.values():
        assert 0.0 <= c["score"] <= 1.0
        assert c["explanation"]  # every component is explained, not just scored


def test_confidence_zero_model_fitness_when_no_tool_chosen(fixtures_dir):
    state = _run(fixtures_dir, "What is in this image?", "sar_a")
    assert state.outcome == "degraded"
    assert state.confidence["components"]["model_fitness"]["score"] == 0.0


def test_compute_confidence_is_a_pure_function_of_state(fixtures_dir):
    state = _run(fixtures_dir, "What changed between these two images?", "optical_t1", "optical_t2")
    assert compute_confidence(state) == compute_confidence(state)
