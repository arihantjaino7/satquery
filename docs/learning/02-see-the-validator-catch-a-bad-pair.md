# 02 — See the validator catch a bad pair

> **Status:** done. `python -m satquery validate fixtures/optical_a.tif fixtures/sar_a.tif` prints 20 PASS; every `broken_*.tif` produces specific, correctly-named WARN/FATAL rows against it.

## What we built

One file, `satquery/io/validate.py`: it takes the facts `manifest.py` reads out of a file and *judges* them. Nothing here reads pixels itself — it calls `read_manifest()` and `infer_modality()` and asks "is this actually usable?" Thirteen named checks, seven that run once per image (`readable`, `format_allowed`, `has_crs`, `has_transform`, `band_count`, `nodata_fraction`, `dimensions`) and six that compare a pair (`crs_match`, `footprint_overlap`, `gsd_ratio`, `grid_alignment`, `modality_distinct`, `temporal_order`). Every check returns a `CheckResult(name, status, expected, actual, message)` — never an exception, never a silent skip.

## The one big idea: PASS is evidence too

The tempting way to write a validator is to only emit something when it finds a problem — "no output" means "it's fine." That's not auditable: you can't tell the difference between "we checked the CRS and it matched" and "we forgot to check the CRS at all." So every check always runs and always produces a row, PASS included. `python -m satquery validate` on the good pair prints all 20 rows as PASS, not silence — that's the proof the checks actually ran, not just that nothing complained.

The second idea, right there in the plan, is: **only FATAL halts.** A WARN means "flagged, keep going" — useful because real pairs are rarely perfect (a 60% footprint overlap is still worth analysing over the shared region). A FATAL means "the ground truth this check depends on is violated, don't trust anything computed from it."

## Why one broken fixture trips *three* checks, not one

`broken_wrong_crs.tif` has bit-for-bit the same transform numbers as `optical_a.tif` — same origin, same pixel size — just tagged `EPSG:32644` (the neighbouring UTM zone) instead of `EPSG:32643`. Nothing about the raw numbers looks wrong. Only reprojecting exposes it: those coordinates in zone 44N are actually ~637 km away from where they'd sit in zone 43N.

Three checks catch it independently, each from a different angle:

- `crs_match` — FATAL, because the CRS strings themselves don't match.
- `footprint_overlap` — FATAL at 0.0%, because after reprojecting the footprint into `optical_a`'s CRS, it lands nowhere near it.
- `grid_alignment` — FATAL too, for a subtler reason explained below.

That's defense in depth: if a caller ever adds a fourth broken variant that happens to dodge one check, the others are still independently true.

## `grid_alignment` — the check that separates "same area" from "co-registered"

This is the one the plan calls out by name, so it's worth being able to explain to a judge precisely. Two images can have CRS, footprint, and GSD all agreeing, and *still* not overlay correctly pixel-for-pixel — because their grids are offset by a fraction of a pixel. That corrupts anything that compares pixels directly: a change-detection diff, a band ratio, a fused optical+SAR stack.

```python
# satquery/io/validate.py
ax, ay = a.transform[2], a.transform[5]   # a's pixel-grid origin, in a's CRS
bx, by = b.transform[2], b.transform[5]   # b's origin
if a.crs != b.crs:
    bx, by = Transformer.from_crs(b.crs, a.crs, always_xy=True).transform(bx, by)

gx, gy = a.gsd
offset_x_px = (bx - ax) / gx              # how many of a's pixels apart the origins are
offset_y_px = (by - ay) / gy
frac_x = abs(offset_x_px - round(offset_x_px))   # distance to the *nearest* whole pixel
frac_y = abs(offset_y_px - round(offset_y_px))
max_frac = max(frac_x, frac_y)
```

The key subtlety: `frac_x`/`frac_y` measure distance to the nearest integer pixel, which is mathematically bounded to `[0, 0.5]` — you can never be more than half a pixel out of phase, because past that you're closer to the *next* pixel instead. So `0.5` isn't a scale that runs on forever; it's the worst case a grid can be in (imagine the two rasters checkerboarded with each other — that's `0.5`, exactly as bad as sub-pixel misalignment gets). That's why the thresholds are `PASS <= 0.10`, `FATAL >= 0.42`: FATAL is set near that ceiling, not at some arbitrary fraction.

Which is also why `broken_wrong_crs` still lands FATAL here even though its *real* offset is 637 km, not a fraction of a pixel: 637 km, expressed in units of a 10 m pixel, wraps around to `0.44` — close enough to the 0.5 worst case to fail. The huge distance is already caught decisively by `footprint_overlap`; `grid_alignment`'s job starts once you already believe it's roughly the same place.

Compare that with `broken_gsd_mismatch`: same CRS, same origin point, just 4x coarser pixels. Its offset is `0.00` — **PASS** — because the two grids share an anchor point even though they disagree on density. That pair fails on `gsd_ratio` alone (`4.00x`, threshold is `3.0x`), which is the correct, narrow diagnosis: nothing wrong with alignment, only resolution.

And `broken_partial_overlap` (origin shifted east by exactly `0.4 * width * GSD` so only 60% of the frame overlaps) lands at `0.40` — inside the WARN band, not FATAL. It's a real, meaningfully different problem from the wrong-CRS case (a modest, correctable sub-pixel offset vs. being in a completely different location), and the two threshold bands keep that distinction visible in the trace instead of collapsing both into one generic failure.

## What each broken fixture actually produces

| fixture vs. `optical_a.tif` | what fails |
|---|---|
| `sar_a.tif` (the good pair) | nothing — 20/20 PASS |
| `broken_wrong_crs.tif` | `crs_match` FATAL, `footprint_overlap` FATAL, `grid_alignment` FATAL |
| `broken_partial_overlap.tif` | `footprint_overlap` WARN (60%), `grid_alignment` WARN (0.40px) |
| `broken_gsd_mismatch.tif` | `gsd_ratio` FATAL (4.00x) only |
| `broken_no_crs.tif` | `has_crs[b]` FATAL, plus every pair check that needs a CRS (`crs_match`, `footprint_overlap`, `grid_alignment`) — but `gsd_ratio`, `modality_distinct`, `temporal_order` still evaluate and PASS, because they don't actually depend on CRS |

That last row matters: missing CRS doesn't turn into a wall of identical failures. Each check is asked independently "do I actually need what's broken here?", and only the ones that do report FATAL.

## Try it

```bash
./.venv/Scripts/python.exe -m satquery validate fixtures/optical_a.tif fixtures/sar_a.tif
./.venv/Scripts/python.exe -m satquery validate fixtures/optical_a.tif fixtures/broken_wrong_crs.tif
```

- The exit code is `0` when there's no FATAL, `1` when there is — so a script (or, later, the agent's `validate` node) can branch on it without parsing text.
- `tests/test_validate.py` has two layers: integration tests running `validate_pair()` against real fixtures for each broken case, and unit tests that use `dataclasses.replace()` on a real `ManifestEntry` to hit WARN/FATAL bands (e.g. 75% nodata) that no fixture file happens to exercise.
- Run `pytest tests/ -v` — 36 tests, all green.

## Words worth knowing

- **Footprint** — the ground rectangle a raster covers, as a polygon in real-world coordinates (derived from its transform + shape).
- **Reprojection** — converting coordinates from one CRS into another. Two rasters that disagree on CRS can't be compared by their raw numbers; the numbers have to be translated into a shared reference frame first (here, via `pyproj.Transformer`).
- **GSD (ground sample distance)** — the real-world size of one pixel, e.g. "10 m" — how coarse or fine the image is, independent of how big it looks in pixels.
- **Sub-pixel / fractional offset** — how far two grids' origins are from lining up on the same pixel lattice, measured in fractions of a pixel rather than whole pixels. `0` means perfectly co-registered; `0.5` is the worst case possible.
- **Co-registration** — two images sharing not just the same area, but the same pixel grid, so pixel `(i, j)` in one genuinely corresponds to pixel `(i, j)` in the other.

---

**Next:** Step 3 — `satquery/io/preprocess.py`, making SAR (and optical) actually viewable: the naive min-max stretch produces a near-black image, and the fix is linear → dB → percentile clip → 8-bit.
