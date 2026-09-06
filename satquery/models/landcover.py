"""Swappable land-cover classifier: real inference once Step 7's Kaggle-trained
weights exist (see `notebooks/01_bigearthnet_encoder.ipynb`), `None` otherwise
so the caller falls back to `models.stub.stub_single_image`. This is the
"local" backend behind the `stub | local | mlx` interface the architecture
calls for (see `docs/` / the build plan) - `node_execute` doesn't know or
care which backend actually answered a vqa/captioning question; it only
sees the returned dict, so dropping trained weights into `models_weights/`
upgrades the pipeline with zero changes anywhere else.

`torch`/`torchvision` are imported lazily, only once a matching weight file
is found on disk - importing this module, or running the full agent
pipeline before training finishes, never requires either to be installed.

Real inference here is intentionally best-effort at demo time: the trained
model expects fixed-size BigEarthNet-style patches on a fixed band count
per variant (10 Sentinel-2 bands, 2 Sentinel-1 bands, or the 12-band fusion
of both) and an uploaded image may match neither the shape nor the exact
band layout. Rather than hand-rolling channel remapping for every possible
input, a mismatch is treated the same as "no model available" (`predict`
returns `None`, `_load_model`/`predict` never raise past this module) -
correct-looking-but-wrong predictions are worse than an honest stub.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

# Standard BigEarthNet-19 (Sumbul et al., 2020) CORINE-derived multi-label
# nomenclature - the *default* class list, used only if a checkpoint has no
# accompanying `<variant>_classes.json`. The notebook always writes one
# alongside its weights (the exact label vocabulary it actually trained on,
# in trained order), so a real checkpoint's classes come from that file, not
# this constant - two independently-hardcoded lists that could silently
# drift apart is worse than a single source of truth on disk.
CORINE_19_CLASSES: tuple[str, ...] = (
    "Urban fabric",
    "Industrial or commercial units",
    "Arable land",
    "Permanent crops",
    "Pastures",
    "Complex cultivation patterns",
    "Land principally occupied by agriculture, with significant areas of natural vegetation",
    "Agro-forestry areas",
    "Broad-leaved forest",
    "Coniferous forest",
    "Mixed forest",
    "Natural grassland and sparsely vegetated areas",
    "Moors, heathland and sclerophyllous vegetation",
    "Transitional woodland/shrub",
    "Beaches, dunes, sands",
    "Inland wetlands",
    "Coastal wetlands",
    "Inland waters",
    "Marine waters",
)

PATCH_SIZE = 120  # BigEarthNet's native patch size - trained models expect this
PREDICTION_THRESHOLD = 0.5
_IN_CHANNELS = {"fused": 12, "s2": 10, "s1": 2}

WEIGHTS_DIR = Path(__file__).resolve().parent.parent.parent / "models_weights"
_VARIANT_FILES = {
    "fused": WEIGHTS_DIR / "landcover_fused.pt",
    "s2": WEIGHTS_DIR / "landcover_s2.pt",
    "s1": WEIGHTS_DIR / "landcover_s1.pt",
}
_CLASSES_FILES = {
    "fused": WEIGHTS_DIR / "landcover_fused_classes.json",
    "s2": WEIGHTS_DIR / "landcover_s2_classes.json",
    "s1": WEIGHTS_DIR / "landcover_s1_classes.json",
}


@lru_cache(maxsize=3)
def _load_classes(variant: str) -> tuple[str, ...]:
    path = _CLASSES_FILES.get(variant)
    if path is not None and path.exists():
        try:
            classes = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(classes, list) and all(isinstance(c, str) for c in classes) and classes:
                return tuple(classes)
        except (json.JSONDecodeError, OSError):
            pass
    return CORINE_19_CLASSES


def _select_variant(modality: str) -> str | None:
    """Which trained variant, if any, this image's modality could use.
    Fused isn't reachable here - it needs a co-registered S1+S2 pair, which
    `node_execute` only has for `cross_modal_fusion`, not single-image
    vqa/captioning - so single-image inference only ever picks s1 or s2.
    """
    if modality == "sar":
        return "s1" if _VARIANT_FILES["s1"].exists() else None
    return "s2" if _VARIANT_FILES["s2"].exists() else None


@lru_cache(maxsize=3)
def _load_model(variant: str):
    """Lazily import torch and load one variant's weights, cached so a demo
    session pays this cost once. Returns `None` (never raises) if torch
    isn't installed, the weight file is missing, or it fails to load -
    every one of those is "no real model yet", handled identically by the
    caller.
    """
    path = _VARIANT_FILES.get(variant)
    if path is None or not path.exists():
        return None
    try:
        import torch
        from torchvision.models import resnet50
    except ImportError:
        return None

    model = resnet50(weights=None)
    model.conv1 = torch.nn.Conv2d(_IN_CHANNELS[variant], 64, kernel_size=7, stride=2, padding=3, bias=False)
    model.fc = torch.nn.Linear(model.fc.in_features, len(_load_classes(variant)))
    try:
        state_dict = torch.load(path, map_location="cpu")
        model.load_state_dict(state_dict)
    except Exception:  # noqa: BLE001 - a corrupt/mismatched checkpoint degrades to "no model", not a crash
        return None
    model.eval()
    return model


def _prepare_tensor(arr: np.ndarray):
    import torch
    import torch.nn.functional as tf

    x = torch.from_numpy(arr.astype(np.float32))
    lo = x.amin(dim=(1, 2), keepdim=True)
    hi = x.amax(dim=(1, 2), keepdim=True)
    x = (x - lo) / (hi - lo).clamp_min(1e-6)  # per-band min-max to [0, 1], matching the notebook's normalisation
    x = x.unsqueeze(0)  # (1, C, H, W)
    if x.shape[-2:] != (PATCH_SIZE, PATCH_SIZE):
        x = tf.interpolate(x, size=(PATCH_SIZE, PATCH_SIZE), mode="bilinear", align_corners=False)
    return x


def predict(manifest_path: Path, modality: str) -> dict[str, Any] | None:
    """Real land-cover inference if a matching trained variant is on disk
    and its input channel count matches this image's band count, else
    `None` so `node_execute` falls back to the honest stub. Never raises.
    """
    variant = _select_variant(modality)
    if variant is None:
        return None
    model = _load_model(variant)
    if model is None:
        return None

    try:
        import torch

        with rasterio.open(manifest_path) as ds:
            arr = ds.read()
        if arr.shape[0] != _IN_CHANNELS[variant]:
            return None  # band count doesn't match this variant's trained input - degrade, don't guess

        x = _prepare_tensor(arr)
        with torch.no_grad():
            probs = torch.sigmoid(model(x))[0]
        scores = probs.tolist()
    except Exception:  # noqa: BLE001 - any inference failure degrades to the stub, not a pipeline crash
        return None

    classes = _load_classes(variant)
    ranked = sorted(zip(classes, scores), key=lambda kv: -kv[1])
    predicted = [{"label": label, "score": round(score, 3)} for label, score in ranked if score >= PREDICTION_THRESHOLD]
    top5 = [{"label": label, "score": round(score, 3)} for label, score in ranked[:5]]
    labels_text = ", ".join(p["label"] for p in predicted) or "no class above threshold"

    answer = (
        f"[{variant}-encoder] predicted land cover: {labels_text} "
        f"(Step 7 {len(classes)}-class classifier trained on BigEarthNet, threshold={PREDICTION_THRESHOLD})."
    )
    return {
        "stub": False,
        "method": f"BigEarthNet-trained ResNet-50 ({variant} variant, {len(classes)}-class multi-label)",
        "variant": variant,
        "predicted_classes": predicted,
        "top5": top5,
        "answer": answer,
    }
