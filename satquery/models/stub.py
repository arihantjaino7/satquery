"""Deterministic placeholder tools, standing in for the trained/loaded models
Steps 7-8 will build. Every function here is labelled `"stub": True` in its
own output so a stub result is never mistaken for a real model's, in the
trace or anywhere downstream.

Where a real, cheap computation is possible (change detection: a threshold on
the actual pixel difference between two preprocessed images), it's used
instead of a fake number - the "stub" part is that it's not a trained
siamese network, not that the numbers are made up. Where no real computation
is possible without a trained model (VQA, captioning, grounding), the output
is an honest templated placeholder built from real manifest facts, not
invented prose pretending to be a model's opinion.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from satquery.io.manifest import ManifestEntry

CHANGE_DIFF_THRESHOLD = 30.0  # mean abs difference (0-255 display scale) above which a pixel counts as "changed"


def stub_change_detection(display_a: np.ndarray, display_b: np.ndarray, threshold: float = CHANGE_DIFF_THRESHOLD) -> dict[str, Any]:
    """Placeholder for the Step 8 siamese change detector (ResNet-18 on
    SECOND): a deterministic per-pixel absolute-difference threshold on the
    two *display-stretched* (3, H, W) uint8 arrays already produced by the
    `preprocess` node. Real arithmetic on real pixels, just not a trained
    model - the trained detector in Step 8 replaces this function's body,
    not the shape of what it returns.
    """
    diff = np.abs(display_a.astype(np.int16) - display_b.astype(np.int16)).mean(axis=0)
    changed_mask = diff > threshold
    percent_changed = float(changed_mask.mean() * 100.0)
    return {
        "stub": True,
        "method": "abs-diff-threshold placeholder for the Step 8 siamese change detector",
        "threshold": threshold,
        "percent_changed": round(percent_changed, 2),
        "changed_pixel_count": int(changed_mask.sum()),
        "total_pixel_count": int(changed_mask.size),
    }


def stub_single_image(capability: str, question: str, manifest: ManifestEntry, modality: str) -> dict[str, Any]:
    """Placeholder for a single-image VLM head (vqa / captioning / grounding).
    No trained encoder exists yet (Step 7 trains the real one), so this
    returns a templated sentence built from real manifest facts - honestly
    labelled as a stub, not a guessed answer dressed up as a real one.
    """
    h, w = manifest.shape
    answer = (
        f"[stub {capability}] question={question!r} over a {modality} image "
        f"({h}x{w} px, {manifest.band_count} band(s), acquired {manifest.acquisition_date or 'unknown date'}). "
        "No trained vision-language head is wired in yet (see Step 7) - this is a placeholder response, "
        "not a real model's answer."
    )
    return {"stub": True, "method": f"templated placeholder for a {capability} VLM head (Step 7)", "answer": answer}


def stub_cross_modal_fusion(question: str, manifests: tuple[ManifestEntry, ...], modalities: tuple[str, ...]) -> dict[str, Any]:
    """Placeholder for an optical+SAR fusion tool. Reports real per-image
    facts (so the "fusion" is at least real data juxtaposition) without
    claiming a trained fusion model produced any interpretation.
    """
    per_image = [f"{mod}: {m.shape[0]}x{m.shape[1]} px, {m.band_count} band(s)" for m, mod in zip(manifests, modalities)]
    answer = (
        f"[stub cross_modal_fusion] question={question!r} over {len(manifests)} co-registered image(s): "
        f"{'; '.join(per_image)}. No trained fusion encoder is wired in yet (see Step 7) - this is a "
        "placeholder response, not a real model's answer."
    )
    return {"stub": True, "method": "templated placeholder for a cross-modal fusion model (Step 7)", "answer": answer}
