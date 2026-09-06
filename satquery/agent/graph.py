"""Wires the nine nodes into one run, in order, and owns the two things no
individual node should: trace assembly (every node's `TraceEntry` gets
appended here, never by the node itself) and the conditional edges for
reject / clarify / degrade.

A node is *skipped*, not silently omitted, once the pipeline has decided it
can't or shouldn't run further work - `outcome` is the single piece of state
that drives this, set by `ingest`/`validate` (-> "rejected"), `classify`
(-> "clarify"), or `plan` (-> "degraded"). Every run still produces exactly
nine trace entries in the same fixed order, whether a given node actually ran
or was skipped with a named reason - so "nine nodes" is true of every run,
not just the happy path, and a skipped step is visible instead of missing.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterator, Sequence

from satquery.agent.confidence import node_confidence
from satquery.agent.nodes import (
    node_classify,
    node_execute,
    node_fuse,
    node_ingest,
    node_plan,
    node_preprocess,
    node_respond,
    node_validate,
)
from satquery.agent.state import SatQueryState, TraceEntry

NODE_ORDER: tuple[str, ...] = ("ingest", "validate", "classify", "plan", "preprocess", "execute", "fuse", "confidence", "respond")

_NODE_FUNCS: dict[str, Callable[[SatQueryState], tuple[SatQueryState, TraceEntry]]] = {
    "ingest": node_ingest,
    "validate": node_validate,
    "classify": node_classify,
    "plan": node_plan,
    "preprocess": node_preprocess,
    "execute": node_execute,
    "fuse": node_fuse,
    "confidence": node_confidence,
    "respond": node_respond,
}


def _skip_reason(node_name: str, state: SatQueryState) -> str | None:
    if node_name in ("validate", "classify") and state.outcome == "rejected":
        return f"skipped: pipeline outcome is {state.outcome!r} (halted before reaching this node)"
    if node_name in ("plan", "preprocess") and state.outcome in ("rejected", "clarify"):
        return f"skipped: pipeline outcome is {state.outcome!r}"
    if node_name in ("execute", "fuse") and state.outcome in ("rejected", "clarify", "degraded"):
        return f"skipped: pipeline outcome is {state.outcome!r}"
    return None


def run_streaming(question: str, image_paths: Sequence[str | Path]) -> Iterator[tuple[SatQueryState, TraceEntry]]:
    """Same nine-node pipeline as `run`, but yields `(state, entry)` after
    each node completes instead of returning only the final state. `run`
    is defined in terms of this generator so there is exactly one place
    the node loop and trace assembly live - a caller that streams (the SSE
    endpoint) and a caller that doesn't (the CLI) can't drift apart.
    """
    state = SatQueryState(question=question, image_paths=tuple(Path(p) for p in image_paths))

    for node_name in NODE_ORDER:
        reason = _skip_reason(node_name, state)
        start = time.perf_counter()
        if reason is not None:
            entry = TraceEntry(node_name, "skipped", reason, {})
        else:
            state, entry = _NODE_FUNCS[node_name](state)
        duration_ms = (time.perf_counter() - start) * 1000.0
        entry = TraceEntry(entry.node, entry.status, entry.message, entry.data, round(duration_ms, 3))
        state = state.with_updates(trace=state.trace + (entry,))
        yield state, entry


def run(question: str, image_paths: Sequence[str | Path]) -> SatQueryState:
    """Run the full nine-node pipeline once. Deterministic given the same
    question, image files, and registry: every node is a pure function of
    state, and the only per-run variation is wall-clock `duration_ms`.
    """
    state: SatQueryState | None = None
    for state, _ in run_streaming(question, image_paths):
        pass
    assert state is not None
    return state
