"""The nine pipeline nodes: ingest, validate, classify, plan, preprocess,
execute, fuse, confidence (in `confidence.py`), respond.

Every node has the signature `(SatQueryState) -> (SatQueryState, TraceEntry)`
- it computes the next state and reports what happened, but never touches
`state.trace` or timing itself. `graph.py` owns both (see `state.py`'s
docstring for why), which keeps every node here a small, pure, independently
testable function of its input state.
"""

from __future__ import annotations

import rasterio

from satquery.io.manifest import read_manifest
from satquery.io.modality import SAR, infer_modality
from satquery.io.preprocess import optical_to_display, sar_to_display
from satquery.io.validate import Status, validate_image, validate_pair
from satquery.models import landcover
from satquery.models.stub import stub_change_detection, stub_cross_modal_fusion, stub_single_image
from satquery.registry.resolver import resolve
from satquery.agent.state import SatQueryState, TraceEntry
from satquery.serialize import to_jsonable

# -- classify: a deterministic keyword scorer standing in for the LLM task
# classifier the architecture calls for. Clearly a stub (see module docstring
# in models/stub.py for the philosophy) - a real LLM swaps in behind this
# same function signature with zero change to the rest of the pipeline.
CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "change_detection": ("change", "different", "compare", "before", "after", "difference", "changed"),
    "cross_modal_fusion": ("radar", "sar", "fuse", "fusion", "combined", "both sensors"),
    "grounding": ("where", "locate", "find", "point to", "bounding box"),
    "captioning": ("describe", "caption", "summarize", "summary"),
    "vqa": ("what", "how many", "is there", "does", "count", "which"),
}


def node_ingest(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    manifests = []
    errors = []
    for path in state.image_paths:
        try:
            manifests.append(read_manifest(path))
        except Exception as exc:  # noqa: BLE001 - any failure here means "unreadable", by design
            errors.append(f"{path.name}: {exc}")

    if errors:
        new_state = state.with_updates(manifests=tuple(manifests) or None, outcome="rejected")
        entry = TraceEntry("ingest", "fatal", f"{len(errors)}/{len(state.image_paths)} image(s) unreadable", {"errors": errors})
        return new_state, entry

    new_state = state.with_updates(manifests=tuple(manifests))
    entry = TraceEntry(
        "ingest", "ok", f"read {len(manifests)} image manifest(s)",
        {"images": [{"path": str(m.path), "sha256_short": m.sha256[:12], "shape": m.shape, "band_count": m.band_count} for m in manifests]},
    )
    return new_state, entry


def node_validate(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    n = len(state.image_paths)

    if n == 2:
        report = validate_pair(state.image_paths[0], state.image_paths[1])
        fatal_names = [r.name for r in report.results if r.status == Status.FATAL]
        ok = report.ok
        summary = {"pass": report.pass_count, "warn": report.warn_count, "fatal": report.fatal_count, "checks": to_jsonable(report.results)}
    elif n == 1:
        results = validate_image(state.image_paths[0])
        fatal_names = [r.name for r in results if r.status == Status.FATAL]
        ok = not fatal_names
        pass_n = sum(1 for r in results if r.status == Status.PASS)
        warn_n = sum(1 for r in results if r.status == Status.WARN)
        report = tuple(results)
        summary = {"pass": pass_n, "warn": warn_n, "fatal": len(fatal_names), "checks": to_jsonable(results)}
    else:
        new_state = state.with_updates(outcome="rejected")
        entry = TraceEntry("validate", "fatal", f"unsupported image_count={n} for this prototype (must be 1 or 2)", {})
        return new_state, entry

    if ok:
        new_state = state.with_updates(validation=report)
        entry = TraceEntry("validate", "ok", "all checks passed", summary)
    else:
        new_state = state.with_updates(validation=report, outcome="rejected")
        entry = TraceEntry("validate", "fatal", f"{len(fatal_names)} FATAL check(s): {', '.join(fatal_names)}", summary)
    return new_state, entry


def _classify_question(question: str, image_modalities: tuple[str, ...]) -> tuple[str | None, dict[str, float], bool]:
    q = question.lower()
    scores = {cap: 0.0 for cap in CAPABILITY_KEYWORDS}
    for cap, keywords in CAPABILITY_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                scores[cap] += 1.0
    if len(set(image_modalities)) > 1:
        scores["cross_modal_fusion"] += 1.0

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], list(CAPABILITY_KEYWORDS).index(kv[0])))
    top_cap, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    ambiguous = top_score == 0.0 or top_score == second_score
    return (None if ambiguous else top_cap), scores, ambiguous


def node_classify(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    image_modalities = tuple(infer_modality(p).inferred for p in state.image_paths)
    task, scores, ambiguous = _classify_question(state.question, image_modalities)

    seen: list[str] = []
    for m in image_modalities:
        if m not in seen:
            seen.append(m)
    modalities = tuple(seen)

    ranked_scores = sorted(scores.values(), reverse=True)
    top = ranked_scores[0] if ranked_scores else 0.0
    second = ranked_scores[1] if len(ranked_scores) > 1 else 0.0
    certainty = 0.0 if ambiguous or top == 0.0 else max(0.0, min(1.0, (top - second) / top))

    if ambiguous:
        new_state = state.with_updates(
            image_modalities=image_modalities, modalities=modalities, task_certainty=certainty, outcome="clarify",
        )
        entry = TraceEntry(
            "classify", "warn", "question is ambiguous across capabilities (stub keyword classifier)",
            {"scores": scores, "candidates": list(CAPABILITY_KEYWORDS)},
        )
        return new_state, entry

    new_state = state.with_updates(task=task, image_modalities=image_modalities, modalities=modalities, task_certainty=certainty)
    entry = TraceEntry(
        "classify", "ok", f"classified as {task!r} (stub keyword classifier, certainty={certainty:.2f})",
        {"scores": scores, "chosen": task},
    )
    return new_state, entry


def node_plan(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    result = resolve(capability=state.task, modalities=state.modalities, image_count=len(state.image_paths))
    candidates_json = to_jsonable(result.candidates)

    if result.chosen is None:
        new_state = state.with_updates(plan=result, outcome="degraded")
        entry = TraceEntry(
            "plan", "warn", f"no eligible tool for capability={state.task!r}; degrading to a generic response",
            {"candidates": candidates_json, "chosen": None},
        )
        return new_state, entry

    new_state = state.with_updates(plan=result)
    entry = TraceEntry("plan", "ok", f"chosen tool: {result.chosen}", {"candidates": candidates_json, "chosen": result.chosen})
    return new_state, entry


def node_preprocess(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    arrays = []
    summaries = []
    for path, modality in zip(state.image_paths, state.image_modalities):
        with rasterio.open(path) as ds:
            arr = ds.read()
        display = sar_to_display(arr) if modality == SAR else optical_to_display(arr)
        arrays.append(display)
        summaries.append({"path": str(path), "modality": modality, "display_shape": display.shape})

    new_state = state.with_updates(display_arrays=tuple(arrays))
    entry = TraceEntry("preprocess", "ok", f"rendered {len(arrays)} display array(s)", {"images": summaries})
    return new_state, entry


def node_execute(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    tool_id = state.plan.chosen
    task = state.task

    if task == "change_detection":
        output = stub_change_detection(state.display_arrays[0], state.display_arrays[1])
    elif task == "cross_modal_fusion":
        output = stub_cross_modal_fusion(state.question, state.manifests, state.modalities)
    elif task in ("vqa", "captioning"):
        # Real Step 7 encoder if trained weights matching this image exist,
        # else the honest stub - see satquery.models.landcover's docstring.
        output = landcover.predict(state.manifests[0].path, state.image_modalities[0]) or stub_single_image(
            task, state.question, state.manifests[0], state.image_modalities[0]
        )
    else:  # grounding - land-cover classification can't localise, so it never bypasses the stub
        output = stub_single_image(task, state.question, state.manifests[0], state.image_modalities[0])

    execution = {"tool_id": tool_id, "capability": task, **output}
    new_state = state.with_updates(execution=execution)
    entry = TraceEntry("execute", "ok", f"ran {tool_id} ({'STUB' if output.get('stub') else 'real'})", execution)
    return new_state, entry


def node_fuse(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    execution = state.execution
    if execution["capability"] == "change_detection":
        percent = execution["percent_changed"]
        facts = {
            "percent_changed": percent,
            "changed": percent >= 1.0,
            "changed_pixel_count": execution["changed_pixel_count"],
            "total_pixel_count": execution["total_pixel_count"],
        }
        message = f"derived: {percent:.2f}% of pixels changed (threshold={execution['threshold']})"
    else:
        facts = {"answer": execution["answer"]}
        message = "passed through single-tool answer (nothing further to derive)"

    new_state = state.with_updates(fused=facts)
    entry = TraceEntry("fuse", "ok", message, facts)
    return new_state, entry


def node_respond(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    if state.outcome == "rejected":
        fatal_names = []
        if isinstance(state.validation, tuple) and state.validation and hasattr(state.validation[0], "status"):
            fatal_names = [r.name for r in state.validation if r.status == Status.FATAL]
        elif state.validation is not None and hasattr(state.validation, "results"):
            fatal_names = [r.name for r in state.validation.results if r.status == Status.FATAL]
        reason = ", ".join(fatal_names) if fatal_names else "input could not be read"
        answer = f"I can't answer this: the input failed validation ({reason})."
        entry = TraceEntry("respond", "fatal", "produced a rejection message", {"answer": answer})
        return state.with_updates(answer=answer), entry

    if state.outcome == "clarify":
        answer = (
            "Your question doesn't map clearly to one supported capability "
            f"({', '.join(CAPABILITY_KEYWORDS)}). Could you clarify what you're asking - "
            "e.g. 'what changed between these two images?' or 'what is in this image?'"
        )
        entry = TraceEntry("respond", "warn", "produced a clarifying question", {"answer": answer})
        return state.with_updates(answer=answer), entry

    if state.outcome == "degraded":
        rejected = [f"{c.tool_id} ({c.reason})" for c in state.plan.rejected]
        answer = (
            f"I understood this as a {state.task!r} question, but no registered tool currently supports "
            f"capability={state.task!r} with modalities={list(state.modalities)} and image_count={len(state.image_paths)}. "
            f"Considered and rejected: {'; '.join(rejected) if rejected else 'no candidates in the registry'}."
        )
        entry = TraceEntry("respond", "warn", "produced a degraded (no-tool-available) response", {"answer": answer})
        return state.with_updates(answer=answer, outcome="degraded"), entry

    if state.execution["capability"] == "change_detection":
        answer = (
            f"[STUB PIPELINE] Between the two images, approximately {state.fused['percent_changed']:.2f}% of the scene "
            f"changed ({state.fused['changed_pixel_count']}/{state.fused['total_pixel_count']} pixels over an abs-diff "
            f"threshold of {state.execution['threshold']}). {state.execution['method']}."
        )
    else:
        answer = state.fused["answer"]

    entry = TraceEntry("respond", "ok", "produced a final answer", {"answer": answer})
    return state.with_updates(answer=answer, outcome="answered"), entry
