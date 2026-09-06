"""The shape of one entry in the model registry: what a tool can do, what it
needs as input, and how good it (supposedly) is at each capability it claims.

Pydantic does the schema validation here — unlike `satquery.io`, which reports
facts about files it can already open, a registry entry is hand-written YAML
that can simply be wrong (a typo'd capability, `min > max`, a missing eval
score). `extra="forbid"` catches a misspelled field name too, not just a
wrong type, so a broken entry fails at load time with a specific field and
message instead of silently being ignored or crashing mid-query later.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Capability(str, Enum):
    VQA = "vqa"
    CAPTIONING = "captioning"
    GROUNDING = "grounding"
    CHANGE_DETECTION = "change_detection"
    CROSS_MODAL_FUSION = "cross_modal_fusion"


class Modality(str, Enum):
    SAR = "sar"
    OPTICAL_RGB = "optical_rgb"
    OPTICAL_MS = "optical_ms"


class ImageCountRange(BaseModel):
    model_config = {"extra": "forbid"}

    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def _min_le_max(self) -> "ImageCountRange":
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must be <= max ({self.max})")
        return self


class ToolSpec(BaseModel):
    """One candidate tool the resolver can pick. `weights` is either a real
    path or the literal string `"stub"` — every entry in this prototype's
    registry is `"stub"` until Step 5+ wires in trained/loaded models.

    `eval_scores` maps a *capability name* (not an arbitrary metric name) to
    a score in [0, 1], one entry per capability this tool declares. These are
    placeholder numbers for prototype ranking only — not published benchmark
    results — so the resolver has something real to rank on before any model
    is actually trained or evaluated.
    """

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    capabilities: list[Capability] = Field(min_length=1)
    modalities: list[Modality] = Field(min_length=1)
    image_count: ImageCountRange
    input_spec: str = Field(min_length=1)
    weights: str = Field(min_length=1)
    est_vram_mb: int = Field(ge=0)
    license: str = Field(min_length=1)
    eval_scores: dict[str, float] = Field(default_factory=dict)
    fallback: str | None = None

    @model_validator(mode="after")
    def _eval_scores_cover_capabilities(self) -> "ToolSpec":
        missing = [c.value for c in self.capabilities if c.value not in self.eval_scores]
        if missing:
            raise ValueError(f"eval_scores is missing an entry for declared capability/ies: {missing}")
        out_of_range = {k: v for k, v in self.eval_scores.items() if not (0.0 <= v <= 1.0)}
        if out_of_range:
            raise ValueError(f"eval_scores must be in [0, 1]: {out_of_range}")
        return self

    @model_validator(mode="after")
    def _fallback_not_self(self) -> "ToolSpec":
        if self.fallback == self.id:
            raise ValueError(f"fallback cannot reference itself ({self.id!r})")
        return self
