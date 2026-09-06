# 03 — See SAR become viewable

> **Status:** done. `scripts/demo_sar_stretch.py` writes [`docs/assets/sar_stretch_naive_vs_correct.png`](../assets/sar_stretch_naive_vs_correct.png) — keep this one, it's the PPT slide.

## What we built

One file, `satquery/io/preprocess.py`: it turns a raw raster array into an 8-bit image a human — or a VLM — can actually look at. `sar_to_display()` for radar, `optical_to_display()` for multispectral, `tile_image()` for scenes too big to hand a model whole. Plus `python -m satquery preprocess <path>` to run it from the command line, and `scripts/demo_sar_stretch.py` to generate the specific before/after comparison.

## The one big idea: the "obvious" way to display an image is wrong for SAR

For optical imagery, min-max stretch (find the darkest and brightest pixel, spread everything between them across 0–255) works fine. Do the exact same thing to SAR and you get a near-black image — not because the data is bad, but because SAR backscatter has a handful of pixels that are 100–1000x brighter than everything else (corner reflectors, metal roofs, anything that bounces radar straight back). The min-max range gets set by those few pixels, and the terrain you actually care about — which is almost all comparatively dim — gets compressed into the bottom few percent of the range and rounds to black.

Numbers from the actual fixture, not a hypothetical:

```
naive stretch:   median=0    98.5% of pixels near-black (< 10/255)
correct stretch: median=136   2.7% of pixels near-black
```

Same underlying pixels. The only thing that changed is *how* the same range got mapped to 0–255.

## The fix, and why each step earns its place

```python
# satquery/io/preprocess.py
def sar_band_to_display(band, low=2.0, high=98.0):
    return rescale_to_uint8(percentile_clip(linear_to_db(band), low, high))
```

1. **`linear_to_db`** — `10*log10(x)`. Backscatter power follows a power-law-ish distribution; log-compression is the standard fix for exactly this shape (it's the same reason audio and photography both work in log/gamma space, not linear). This alone turns "a few pixels are 1000x brighter" into "a few pixels are 30 dB brighter" — still the extreme, but no longer able to eat the whole dynamic range by itself.
2. **zero-guarded** — `log10(0)` is `-inf`, which would poison the min/max/percentile of everything downstream. `np.clip(x, 1e-10, None)` floors it to a very negative but finite dB value before the log, so one dead pixel can't break the whole image.
3. **`percentile_clip` to 2nd/98th** — dB compresses the outliers, it doesn't remove them. Clipping to the 2nd/98th percentile throws away what's left of the extreme tails *per band* (SAR VV and VH sit on different scales, so each gets its own range — a shared range would let one polarisation dominate the other the same way outliers dominated the naive stretch).
4. **rescale to 8-bit** — now that the range reflects the terrain instead of a handful of freak pixels, a plain min-max stretch is the right tool.

## Dual-pol false colour: reusing work instead of redoing it

```python
db_vv = linear_to_db(arr[0])
db_vh = linear_to_db(arr[1])
ratio_db = db_vv - db_vh  # subtracting two dB values IS the ratio, in dB
stack = np.stack([db_vv, db_vh, ratio_db])
```

The conventional SAR false-colour scheme is R=VV, G=VH, B=VV/VH ratio. The ratio channel could be computed as a fresh division (`vv / (vh + epsilon)`) and then need its *own* zero-guarding and its own dB conversion — or it can reuse the two dB bands already computed, since `dB(a) - dB(b) = dB(a/b)` is a basic log identity. Subtraction is cheaper, already zero-guarded (both inputs went through `linear_to_db`), and needs no new epsilon. Small thing, but it's the kind of detail worth having an answer for if asked "why not just divide the two bands?"

## Optical: a different problem, a simpler fix

Optical doesn't have SAR's power-law outlier problem, so there's no dB step — just correct band selection and the same percentile stretch:

```python
def select_optical_bands(arr, band_names, target=("B04", "B03", "B02")):
    if band_names and all(name in band_names for name in target):
        idx = [band_names.index(name) for name in target]
        return arr[idx]
    ...
```

The 12-band fixture stores bands in Sentinel-2 order (`B01, B02, ... B12`), not RGB order — true colour is `B04, B03, B02` (red, green, blue), which sit at *indices 3, 2, 1*, not 0, 1, 2. Selecting by **name** rather than position means this is correct regardless of how a given file happens to order its bands; position is only a fallback for files with no band descriptions at all.

## Tiling: a no-op until it isn't

```python
def tile_image(arr, tile_size=512):
    ...
    # a scene already <= tile_size on both axes returns a single tile
```

All the current fixtures are 256x256, so tiling never actually fires for them (one tile covering the whole image) — the test that proves it works uses a synthetic 256x256 array with `tile_size=100` to force a 3x3 grid, and checks the tiles exactly reassemble the original array with no gaps or overlap. This matters later: Step 6's browser preview and any real Cartosat/EOS-04 scene (which won't be a friendly 256x256) will need this path to actually trigger.

## Try it

```bash
./.venv/Scripts/python.exe scripts/demo_sar_stretch.py
./.venv/Scripts/python.exe -m satquery preprocess fixtures/sar_a.tif --out sar_preview.png
./.venv/Scripts/python.exe -m satquery preprocess fixtures/optical_a.tif --out optical_preview.png
```

- `preprocess` auto-detects modality (reusing Step 1's `infer_modality`, not the filename) and dispatches to the SAR or optical path accordingly.
- `pytest tests/ -v` — 58 tests total (36 from before + 22 new), covering every building block individually (via small synthetic arrays) and the full path against the real fixtures.
- Open `docs/assets/sar_stretch_naive_vs_correct.png` — left half is the naive stretch (black, one sparse cluster of specks over the urban block), right half is the correct one (all four land-cover regions visible: dark water, bright urban, mid-tone vegetation, textured bare-soil background).

## Words worth knowing

- **Backscatter** — the fraction of a radar pulse's energy that reflects back to the sensor. What SAR actually measures; stored as linear power, not a photograph.
- **Decibel (dB)** — a logarithmic ratio, `10*log10(x)`. Compresses large multiplicative differences into smaller additive ones — a 1000x brighter pixel becomes "30 dB brighter" instead of "999 units further up a linear scale."
- **Dynamic range** — the ratio between the brightest and typical values in an image. SAR's is huge on the linear scale (that's the whole problem); dB compresses it to something a fixed 0–255 range can actually represent.
- **Percentile clip** — discarding the most extreme low/high values (e.g. below the 2nd or above the 98th percentile) before stretching, so a handful of outliers can't set the range for everyone else.
- **False colour** — assigning real sensor channels to the R/G/B display channels in a way that isn't literal true colour (SAR has no "colour" at all), chosen because it makes a meaningful distinction visible — here, VV vs VH vs their ratio, which correspond to different scattering behaviour.

---

**Next:** Step 4 — `satquery/registry/{schema,loader,resolver}.py`, the model registry that picks a tool for a task and records every candidate it rejected and why.
