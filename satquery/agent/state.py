"""The document that flows through the nine agent nodes, and the trace
entries each node contributes to it.

There's no LangGraph dependency here (nothing in this prototype's verified
environment pulls it in, and a hand-rolled nine-node pipeline doesn't need
the extra machinery) - but the same discipline the plan calls for
(`trace: Annotated[list[TraceEntry], operator.add]`, "every node appends
without any node owning the document") is reproduced by hand: node functions
in `nodes.py` never see or mutate `state.trace` directly, they return
`(updated_state, TraceEntry)`, and `graph.py` alone is responsible for
appending that entry. No node can accidentally overwrite or drop the trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

Outcome = Literal["pending", "answered", "rejected", "clarify", "degraded"]


@dataclass(frozen=True)
class TraceEntry:
    node: str
    status: Literal["ok", "warn", "fatal", "skipped"]
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


@dataclass(frozen=True)
class SatQueryState:
    question: str
    image_paths: tuple[Path, ...]

    trace: tuple[TraceEntry, ...] = field(default_factory=tuple)
    outcome: Outcome = "pending"

    # -- populated progressively by nodes, in pipeline order --
    manifests: tuple[Any, ...] | None = None
    validation: Any | None = None  # ValidationReport (2 images) or tuple[CheckResult, ...] (1 image)
    task: str | None = None  # classified capability, e.g. "change_detection"
    task_certainty: float = 0.0
    image_modalities: tuple[str, ...] | None = None  # per-image, same order as image_paths
    modalities: tuple[str, ...] | None = None  # deduped, for the resolver query
    plan: Any | None = None  # registry.resolver.ResolutionResult
    display_arrays: tuple[Any, ...] | None = None  # preprocessed (3, H, W) uint8 arrays, not JSON-serialised
    execution: dict[str, Any] | None = None  # raw stub tool output
    fused: dict[str, Any] | None = None  # Python-derived facts from `execution`
    confidence: dict[str, Any] | None = None
    answer: str | None = None

    def with_updates(self, **kwargs: Any) -> "SatQueryState":
        return replace(self, **kwargs)
