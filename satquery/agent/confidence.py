"""Confidence as four named, independently-inspectable components - never one
opaque number. A single "82% confident" is a claim nobody can check; showing
*which* of input quality, task certainty, model fitness, and output agreement
is dragging the score down (or holding it up) is something a judge, or a
future debugging session, can actually act on.
"""

from __future__ import annotations

from satquery.io.validate import Status
from satquery.agent.state import SatQueryState, TraceEntry


def _input_quality(state: SatQueryState) -> tuple[float, str]:
    if state.outcome == "rejected" or state.validation is None:
        return 0.0, "input failed validation (or was never readable) - no usable signal"

    if isinstance(state.validation, tuple):
        results = state.validation
    else:
        results = state.validation.results

    total = len(results)
    if total == 0:
        return 1.0, "no checks ran (nothing to penalise)"
    pass_n = sum(1 for r in results if r.status == Status.PASS)
    warn_n = sum(1 for r in results if r.status == Status.WARN)
    score = (pass_n + 0.5 * warn_n) / total
    return round(score, 3), f"{pass_n}/{total} checks PASS, {warn_n}/{total} WARN (half credit), 0 FATAL"


def _task_certainty(state: SatQueryState) -> tuple[float, str]:
    if state.outcome == "clarify":
        return 0.0, "classifier found no clear top capability (ambiguous question)"
    return round(state.task_certainty, 3), f"margin between top and second-best capability score, classified as {state.task!r}"


def _model_fitness(state: SatQueryState) -> tuple[float, str]:
    if state.plan is None or state.plan.chosen is None:
        return 0.0, "no eligible tool was found in the registry for this query"
    chosen = next(c for c in state.plan.candidates if c.tool_id == state.plan.chosen)
    return round(chosen.score or 0.0, 3), f"{state.plan.chosen}'s declared eval_score for capability={state.task!r} (placeholder, prototype-only)"


def _output_agreement(state: SatQueryState) -> tuple[float, str]:
    if state.execution is None:
        return 0.0, "no tool executed - nothing to cross-check"
    if state.execution["capability"] == "change_detection":
        return (
            1.0,
            "the answer is derived directly from the mask statistics in this prototype, so they are "
            "definitionally consistent; this component becomes meaningful once the verbalising VLM is "
            "no longer stubbed and can disagree with the specialist tool",
        )
    return (
        0.5,
        "single stubbed tool with no independent second signal to cross-check against - neutral, not "
        "evidence of agreement or disagreement",
    )


def compute_confidence(state: SatQueryState) -> dict:
    iq_score, iq_note = _input_quality(state)
    tc_score, tc_note = _task_certainty(state)
    mf_score, mf_note = _model_fitness(state)
    oa_score, oa_note = _output_agreement(state)

    components = {
        "input_quality": {"score": iq_score, "explanation": iq_note},
        "task_certainty": {"score": tc_score, "explanation": tc_note},
        "model_fitness": {"score": mf_score, "explanation": mf_note},
        "output_agreement": {"score": oa_score, "explanation": oa_note},
    }
    overall = round(sum(c["score"] for c in components.values()) / len(components), 3)
    return {"components": components, "overall": overall}


def node_confidence(state: SatQueryState) -> tuple[SatQueryState, TraceEntry]:
    confidence = compute_confidence(state)
    new_state = state.with_updates(confidence=confidence)
    entry = TraceEntry(
        "confidence", "ok",
        f"overall={confidence['overall']:.2f} "
        f"(input_quality={confidence['components']['input_quality']['score']:.2f}, "
        f"task_certainty={confidence['components']['task_certainty']['score']:.2f}, "
        f"model_fitness={confidence['components']['model_fitness']['score']:.2f}, "
        f"output_agreement={confidence['components']['output_agreement']['score']:.2f})",
        confidence,
    )
    return new_state, entry
