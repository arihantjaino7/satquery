"""Generate the Step 3 "quality cliff" demonstration: the same SAR band,
stretched the wrong way (naive min-max on linear power) and the right way
(dB -> percentile clip -> uint8), side by side in one PNG.

This is the image the plan calls "keep this, it is a PPT slide" — it proves
the domain-specific fix in one glance instead of a paragraph.

Run:  ./.venv/Scripts/python.exe scripts/demo_sar_stretch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # run directly without PYTHONPATH

import numpy as np
import rasterio

from satquery.io.preprocess import (
    naive_linear_stretch,
    sar_band_to_display,
    sar_to_display,
    side_by_side,
    write_png,
)

FIXTURES_DIR = Path("fixtures")
OUT_DIR = Path("docs/assets")


def _to_rgb(band_2d: np.ndarray) -> np.ndarray:
    return np.stack([band_2d, band_2d, band_2d])


def main() -> None:
    sar_path = FIXTURES_DIR / "sar_a.tif"
    with rasterio.open(sar_path) as ds:
        arr = ds.read()  # (2, H, W): VV, VH

    vv = arr[0]

    naive = _to_rgb(naive_linear_stretch(vv))
    correct = _to_rgb(sar_band_to_display(vv))

    naive_dark_frac = (naive[0] < 10).mean()
    correct_dark_frac = (correct[0] < 10).mean()
    print(f"naive stretch:   median={np.median(naive):.0f}  {naive_dark_frac:.1%} of pixels near-black")
    print(f"correct stretch: median={np.median(correct):.0f}  {correct_dark_frac:.1%} of pixels near-black")

    comparison = side_by_side(naive, correct)
    out_path = write_png(comparison, OUT_DIR / "sar_stretch_naive_vs_correct.png")
    print(f"wrote {out_path.resolve()}  ({comparison.shape[2]}x{comparison.shape[1]}, left=naive right=correct)")

    false_color = sar_to_display(arr)
    fc_path = write_png(false_color, OUT_DIR / "sar_false_color_vv_vh_ratio.png")
    print(f"wrote {fc_path.resolve()}  (dual-pol VV/VH/ratio false colour)")


if __name__ == "__main__":
    main()
