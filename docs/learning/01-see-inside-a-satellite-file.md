# 01 — See inside a satellite file

> **Status:** done. `python -m satquery inspect fixtures/optical_a.tif` prints a full manifest and a modality decision.

## What we built

Three files that let you point at any GeoTIFF and get the truth about it: `scripts/make_fixtures.py` generates fake-but-realistic satellite images so we're never blocked on a real download, `satquery/io/manifest.py` reads the structural facts out of a file (CRS, shape, dtype, nodata, footprint...), and `satquery/io/modality.py` figures out whether a file is SAR, RGB, or multispectral optical — without looking at the filename.

## The one big idea: deciding from evidence, not from the label

The tempting way to write `infer_modality()` is: check if the filename contains "sar", return `"sar"`. That's cheating — a real pipeline gets files named `scene_042.tif` with no hint at all, or worse, a file mislabeled by whoever exported it.

Instead, the function looks at what the pixels themselves are like, using signals that are actually true of the data:

- **dtype** — SAR sensors record backscatter power as `float32`; optical sensors record integer brightness values.
- **band count** — SAR files usually have 1-2 bands (one per radar polarization); optical multispectral files have many more.
- **skewness** — a measure of how lopsided the value distribution is. SAR images have a few extremely bright pixels (metal structures bounce radar straight back) sitting on top of mostly dark terrain, which makes the distribution heavily lopsided. Optical reflectance values are much more evenly spread.
- **dynamic range** — the ratio of the brightest pixel to the typical pixel. Same story: SAR's stray bright pixels blow this ratio way up.

Each signal adds a small score to one or more candidate labels (`sar`, `optical_rgb`, `optical_ms`), and whichever label ends up with the highest score wins. It's the same idea as a doctor weighing several symptoms instead of diagnosing from one — no single signal is proof by itself, but together they're a confident answer, and you can always ask "why did you decide that?" and get real numbers back.

Here's the same scoring idea in miniature, nothing to do with satellites:

```python
def guess_fruit(weight_g, is_round):
    scores = {"grape": 0, "watermelon": 0}
    if weight_g < 10:
        scores["grape"] += 1
    else:
        scores["watermelon"] += 1
    if is_round:
        scores["grape"] += 1
        scores["watermelon"] += 1  # both are round, so this doesn't discriminate
    return max(scores, key=scores.get)
```

Small, cheap checks, added up, picked by the highest total. That's the whole pattern.

## The actual code

```python
# satquery/io/modality.py
scores = {SAR: 0.0, OPTICAL_RGB: 0.0, OPTICAL_MS: 0.0, OPTICAL_PAN: 0.0}

if is_float:
    scores[SAR] += 0.4          # SAR backscatter is stored as float
else:
    for k in (OPTICAL_RGB, OPTICAL_MS, OPTICAL_PAN):
        scores[k] += 0.2        # integer DN/reflectance is optical-typical

if band_count <= 2:
    scores[SAR] += 0.3
elif band_count == 3:
    scores[OPTICAL_RGB] += 0.3
else:
    scores[OPTICAL_MS] += 0.3

if mean_skew > 1.2:
    scores[SAR] += 0.15         # heavy right tail = bright scatterers + speckle

if mean_dyn_range > 20:
    scores[SAR] += 0.15         # a few pixels dominate the range

inferred = max(scores, key=scores.get)
```

Every one of those `+=` lines also gets written to an `evidence` list as a plain sentence, so `python -m satquery inspect` can print *why*, not just the final label. `parse_filename_hint()` is a completely separate function — it reads the filename purely so we can report "filename says X, pixels say Y, they (dis)agree", never to decide anything.

## Try it

```bash
./.venv/Scripts/python.exe -m satquery inspect fixtures/optical_a.tif
./.venv/Scripts/python.exe -m satquery inspect fixtures/sar_a.tif
```

- Compare the `evidence` lines between the two — same code path, completely different reasoning trail.
- Look at `tests/test_modality.py::test_inference_ignores_misleading_filename` — it copies `sar_a.tif`'s actual bytes into a file named `image_alpha.tif` and confirms the answer is still `sar`. That test is the proof that the filename genuinely isn't load-bearing.
- Run `pytest tests/ -v` — 21 tests, covering the fixtures, the manifest reader, and the modality scorer.

## Words worth knowing

- **Skewness** — a number describing how lopsided a distribution is. Near 0 means roughly symmetric; a big positive number means a long tail of unusually high values.
- **Dynamic range** — here, the ratio of the brightest pixel to a typical (median) pixel. High = a few outliers dominate.
- **Speckle** — the grainy, salt-and-pepper noise pattern that's inherent to radar imagery, caused by how radar waves interfere with each other when they bounce back.
- **Nodata fraction** — the share of pixels that carry no real measurement (e.g. a sensor gap at the edge of a scene), computed only where *every* band agrees a pixel is empty.

---

**Next:** Step 2 — `satquery/io/validate.py`, the checker that compares a *pair* of images (do their CRS match? does their footprint actually overlap enough? are they on the same pixel grid?) and reports PASS/WARN/FATAL for each check.
