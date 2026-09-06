"""Given a requested capability, modality set, and image count, decide which
registered tool answers the query - and record *why every other candidate
was, or wasn't, in the running*.

This mirrors `satquery.io.validate`'s check pattern on purpose: filter
checks run in a fixed order per candidate, the first failing check is the
recorded reason, and passing candidates are recorded too. A trace that only
shows the winner proves nothing about what was actually considered - which
is exactly the auditable-execution-trace requirement (capability #5) this
registry exists to serve.

Filtering is capability -> modality -> image_count, in that order, so a tool
that fails on more than one dimension still gets one clear, specific reason
rather than a vague "didn't qualify." Candidates are recorded in registry
load order (itself filename-sorted, so deterministic); the winner is whoever
scores highest among eligible candidates, tie-broken by tool id. Nothing here
is random and nothing depends on set/dict iteration order, so the same query
run twice produces byte-identical output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from satquery.registry.loader import get_registry
from satquery.registry.schema import ToolSpec


@dataclass(frozen=True)
class Candidate:
    tool_id: str
    version: str
    eligible: bool
    reason: str
    score: float | None  # the tool's eval_score for the requested capability, if eligible


@dataclass(frozen=True)
class ResolutionResult:
    capability: str
    modalities: tuple[str, ...]
    image_count: int
    candidates: tuple[Candidate, ...]  # every tool considered, in registry load order
    chosen: str | None  # tool_id of the winner, or None if nothing qualifies

    @property
    def eligible(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if c.eligible)

    @property
    def rejected(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if not c.eligible)


def _evaluate(spec: ToolSpec, capability: str, modalities: Sequence[str], image_count: int) -> Candidate:
    if capability not in {c.value for c in spec.capabilities}:
        supported = [c.value for c in spec.capabilities]
        return Candidate(spec.id, spec.version, False, f"does not support capability {capability!r} (supports {supported})", None)

    spec_modalities = {m.value for m in spec.modalities}
    missing_modalities = [m for m in modalities if m not in spec_modalities]
    if missing_modalities:
        return Candidate(
            spec.id, spec.version, False,
            f"missing modality support for {missing_modalities} (supports {sorted(spec_modalities)})",
            None,
        )

    if image_count > spec.image_count.max:
        return Candidate(spec.id, spec.version, False, f"image_count max {spec.image_count.max} < {image_count}", None)
    if image_count < spec.image_count.min:
        return Candidate(spec.id, spec.version, False, f"image_count min {spec.image_count.min} > {image_count}", None)

    score = spec.eval_scores[capability]
    return Candidate(spec.id, spec.version, True, f"eligible: capability, modality, and image_count all satisfied (eval_score={score:.2f})", score)


def resolve(
    capability: str,
    modalities: Sequence[str],
    image_count: int,
    registry: Sequence[ToolSpec] | None = None,
) -> ResolutionResult:
    """Filter `registry` (defaults to the cached `registry/entries/` load)
    down to tools that support `capability`, whose declared `modalities`
    cover every modality in the request, and whose `image_count` range
    accepts `image_count`. The eligible candidate with the highest declared
    eval score for `capability` wins ties broken by tool id, ascending, so
    ranking never depends on load order or float equality edge cases beyond
    a stable, named rule.
    """
    specs = registry if registry is not None else get_registry()
    candidates = tuple(_evaluate(spec, capability, modalities, image_count) for spec in specs)

    eligible = [c for c in candidates if c.eligible]
    chosen = None
    if eligible:
        chosen = min(eligible, key=lambda c: (-(c.score or 0.0), c.tool_id)).tool_id

    return ResolutionResult(
        capability=capability,
        modalities=tuple(modalities),
        image_count=image_count,
        candidates=candidates,
        chosen=chosen,
    )
