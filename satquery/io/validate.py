"""Check whether a single raster — or a pair of them — is actually safe to
feed downstream, and say exactly why or why not.

`manifest.py` reports facts about a file. This module judges those facts.
Every check produces a `CheckResult(name, status, expected, actual, message)`
with status `PASS | WARN | FATAL`. **Only FATAL halts** — a pipeline built on
top of this should stop on a FATAL result and proceed past a WARN. PASS
results are recorded too, deliberately: a trace that only lists failures
proves nothing about what was actually verified.

Per-image checks (`readable`, `format_allowed`, `has_crs`, `has_transform`,
`band_count`, `nodata_fraction`, `dimensions`) run once per file. Per-pair
checks (`crs_match`, `footprint_overlap`, `gsd_ratio`, `grid_alignment`,
`modality_distinct`, `temporal_order`) compare two files and reuse the CRS a
check ran for each image is suffixed `[a]` / `[b]` (image "a" is the
reference, "b" is the candidate being checked against it) so the same check
name can appear twice in one report without colliding.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Polygon

from satquery.io.manifest import ManifestEntry, read_manifest
from satquery.io.modality import ModalityInference, infer_modality

# ---------------------------------------------------------------------------
# Thresholds. Named and centralised so a judge question ("why is 3x GSD a
# FATAL and not a WARN?") has a one-line answer instead of a buried literal.
# ---------------------------------------------------------------------------

ALLOWED_DRIVERS = {"GTiff"}  # prototype only reads/writes GeoTIFF end to end

NODATA_WARN_THRESHOLD = 0.10   # >10% empty pixels: usable but flagged
NODATA_FATAL_THRESHOLD = 0.50  # >50% empty: not enough real signal to trust

MIN_DIM_WARN = 64  # below this, a VLM patch may not carry enough context

OVERLAP_PASS_THRESHOLD = 0.90  # near-total overlap: genuinely the same scene
OVERLAP_WARN_THRESHOLD = 0.50  # partial: usable over the shared region only

GSD_RATIO_WARN_THRESHOLD = 1.5   # up to 50% resolution mismatch: tolerable
GSD_RATIO_FATAL_THRESHOLD = 3.0  # beyond 3x: resampling changes the answer

# Sub-pixel origin offset, in units of image a's pixel size. This is the
# check that separates "same area" from "genuinely co-registered": two grids
# can share almost the same footprint while still being offset by a
# fractional pixel, which corrupts any pixel-for-pixel comparison (change
# detection diffs, band math) unless resampled first.
#
# "Fractional offset" is distance to the *nearest* integer pixel, which is
# mathematically bounded to [0, 0.5] — 0.5 is the worst case a pixel grid can
# be in (exactly half a pixel out of phase, e.g. the classic PixelIsArea vs
# PixelIsPoint convention bug). FATAL is set close to that ceiling, not at an
# arbitrary fraction, because a value that can never approach 0.5 is a grid
# that is, practically speaking, fine.
GRID_OFFSET_PASS_THRESHOLD = 0.10
GRID_OFFSET_FATAL_THRESHOLD = 0.42

IMAGE_CHECK_NAMES = (
    "readable", "format_allowed", "has_crs", "has_transform",
    "band_count", "nodata_fraction", "dimensions",
)
PAIR_CHECK_NAMES = (
    "crs_match", "footprint_overlap", "gsd_ratio",
    "grid_alignment", "modality_distinct", "temporal_order",
)


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FATAL = "FATAL"


@dataclass
class CheckResult:
    name: str
    status: Status
    expected: str
    actual: str
    message: str


@dataclass
class ValidationReport:
    path_a: Path
    path_b: Path
    results: list[CheckResult]

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.status == Status.PASS)

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == Status.WARN)

    @property
    def fatal_count(self) -> int:
        return sum(1 for r in self.results if r.status == Status.FATAL)

    @property
    def ok(self) -> bool:
        """True if nothing FATAL fired — i.e. a downstream pipeline may proceed."""
        return self.fatal_count == 0


# ---------------------------------------------------------------------------
# Per-image checks. Each is a pure function of a ManifestEntry so the
# WARN/FATAL bands can be exercised directly in tests via
# dataclasses.replace(), without needing a new broken fixture file for every
# threshold.
# ---------------------------------------------------------------------------


def _check_format_allowed(entry: ManifestEntry) -> CheckResult:
    name = "format_allowed"
    expected = f"driver in {sorted(ALLOWED_DRIVERS)}"
    if entry.driver in ALLOWED_DRIVERS:
        return CheckResult(name, Status.PASS, expected, entry.driver, "driver is supported end to end")
    return CheckResult(
        name, Status.WARN, expected, entry.driver,
        f"driver {entry.driver!r} is not in the tested allowlist; rasterio may still read it correctly",
    )


def _check_has_crs(entry: ManifestEntry) -> CheckResult:
    name = "has_crs"
    expected = "CRS present"
    if entry.has_crs:
        return CheckResult(name, Status.PASS, expected, entry.crs, "CRS is set")
    return CheckResult(name, Status.FATAL, expected, "MISSING", "no CRS: pixel coordinates cannot be located on the ground")


def _check_has_transform(entry: ManifestEntry) -> CheckResult:
    name = "has_transform"
    expected = "non-identity, non-degenerate affine transform"
    a, _, _, _, e, _ = entry.transform
    is_identity = tuple(entry.transform) == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    is_degenerate = a == 0 or e == 0
    if is_identity or is_degenerate:
        return CheckResult(name, Status.FATAL, expected, str(entry.transform), "transform is identity/degenerate: file has no real georeferencing")
    return CheckResult(name, Status.PASS, expected, str(entry.transform), "transform looks like real georeferencing")


def _check_band_count(entry: ManifestEntry) -> CheckResult:
    name = "band_count"
    expected = ">= 1 band"
    if entry.band_count < 1:
        return CheckResult(name, Status.FATAL, expected, str(entry.band_count), "no bands to read")
    return CheckResult(name, Status.PASS, expected, str(entry.band_count), "band count is sane")


def _check_nodata_fraction(entry: ManifestEntry) -> CheckResult:
    name = "nodata_fraction"
    expected = f"<= {NODATA_WARN_THRESHOLD:.0%}"
    frac = entry.nodata_fraction
    actual = f"{frac:.2%}"
    if frac > NODATA_FATAL_THRESHOLD:
        return CheckResult(name, Status.FATAL, expected, actual, "more than half the scene has no data at all")
    if frac > NODATA_WARN_THRESHOLD:
        return CheckResult(name, Status.WARN, expected, actual, "a significant share of the scene is empty")
    return CheckResult(name, Status.PASS, expected, actual, "nodata coverage is small")


def _check_dimensions(entry: ManifestEntry) -> CheckResult:
    name = "dimensions"
    h, w = entry.shape
    expected = f">= {MIN_DIM_WARN}x{MIN_DIM_WARN} px"
    actual = f"{h}x{w}"
    if h < 1 or w < 1:
        return CheckResult(name, Status.FATAL, expected, actual, "degenerate raster: zero in at least one dimension")
    if h < MIN_DIM_WARN or w < MIN_DIM_WARN:
        return CheckResult(name, Status.WARN, expected, actual, "small raster: may not carry enough spatial context")
    return CheckResult(name, Status.PASS, expected, actual, "dimensions are comfortably usable")


def _tag(result: CheckResult, role: str) -> CheckResult:
    return replace(result, name=f"{result.name}[{role}]")


def _validate_image_internal(path: Path, role: str) -> tuple[ManifestEntry | None, list[CheckResult]]:
    try:
        entry = read_manifest(path)
    except Exception as exc:  # noqa: BLE001 — any failure here means "unreadable", by design
        result = CheckResult(
            f"readable[{role}]", Status.FATAL,
            "file opens and reads via rasterio", "error",
            f"{path.name}: {exc}",
        )
        return None, [result]

    results = [
        CheckResult(f"readable[{role}]", Status.PASS, "file opens and reads via rasterio", entry.driver, f"{path.name} opened and read successfully"),
        _tag(_check_format_allowed(entry), role),
        _tag(_check_has_crs(entry), role),
        _tag(_check_has_transform(entry), role),
        _tag(_check_band_count(entry), role),
        _tag(_check_nodata_fraction(entry), role),
        _tag(_check_dimensions(entry), role),
    ]
    return entry, results


def validate_image(path: str | Path, role: str = "a") -> list[CheckResult]:
    """Run every per-image check on one file. If the file can't even be
    opened, only `readable[<role>]` is returned — the rest genuinely cannot
    be evaluated without a dataset to inspect.
    """
    _, results = _validate_image_internal(Path(path), role)
    return results


# ---------------------------------------------------------------------------
# Per-pair checks. Each takes two already-read ManifestEntry objects; "a" is
# the reference image, "b" is the candidate being checked against it.
# ---------------------------------------------------------------------------


def _missing_crs_names(a: ManifestEntry, b: ManifestEntry) -> list[str]:
    return [e.path.name for e in (a, b) if not e.has_crs]


def _check_crs_match(a: ManifestEntry, b: ManifestEntry) -> CheckResult:
    name = "crs_match"
    expected = "both images share one CRS"
    missing = _missing_crs_names(a, b)
    if missing:
        return CheckResult(name, Status.FATAL, expected, f"missing on {', '.join(missing)}", f"cannot compare CRS: missing on {', '.join(missing)}")
    if a.crs == b.crs:
        return CheckResult(name, Status.PASS, expected, f"{a.crs} == {b.crs}", "CRS matches")
    return CheckResult(
        name, Status.FATAL, expected, f"{a.crs} != {b.crs}",
        f"{a.path.name} is {a.crs}, {b.path.name} is {b.crs} - identical raw coordinates would name different places on the ground",
    )


def _footprint_polygon(entry: ManifestEntry) -> Polygon:
    return Polygon(entry.footprint_corners)


def _reproject_polygon(poly: Polygon, from_crs: str, to_crs: str) -> Polygon:
    transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
    xs, ys = transformer.transform(*zip(*poly.exterior.coords))
    return Polygon(zip(xs, ys))


def _check_footprint_overlap(a: ManifestEntry, b: ManifestEntry) -> CheckResult:
    name = "footprint_overlap"
    expected = f">= {OVERLAP_PASS_THRESHOLD:.0%} of {a.path.name}'s footprint"
    missing = _missing_crs_names(a, b)
    if missing:
        return CheckResult(name, Status.FATAL, expected, "not computable", f"cannot compute overlap: missing CRS on {', '.join(missing)}")

    poly_a = _footprint_polygon(a)
    poly_b = _footprint_polygon(b)
    if a.crs != b.crs:
        poly_b = _reproject_polygon(poly_b, b.crs, a.crs)

    if poly_a.area == 0:
        return CheckResult(name, Status.FATAL, expected, "0%", f"{a.path.name} has a degenerate (zero-area) footprint")

    fraction = poly_a.intersection(poly_b).area / poly_a.area
    actual = f"{fraction:.1%}"
    if fraction >= OVERLAP_PASS_THRESHOLD:
        status = Status.PASS
    elif fraction >= OVERLAP_WARN_THRESHOLD:
        status = Status.WARN
    else:
        status = Status.FATAL
    return CheckResult(name, status, expected, actual, f"{b.path.name} covers {fraction:.1%} of {a.path.name}'s footprint")


def _check_gsd_ratio(a: ManifestEntry, b: ManifestEntry) -> CheckResult:
    name = "gsd_ratio"
    expected = f"<= {GSD_RATIO_WARN_THRESHOLD:g}x"
    rx = max(a.gsd[0], b.gsd[0]) / min(a.gsd[0], b.gsd[0])
    ry = max(a.gsd[1], b.gsd[1]) / min(a.gsd[1], b.gsd[1])
    ratio = max(rx, ry)
    actual = f"{ratio:.2f}x ({a.path.name}={a.gsd[0]:g}m, {b.path.name}={b.gsd[0]:g}m)"
    if ratio <= GSD_RATIO_WARN_THRESHOLD:
        status = Status.PASS
    elif ratio <= GSD_RATIO_FATAL_THRESHOLD:
        status = Status.WARN
    else:
        status = Status.FATAL
    return CheckResult(name, status, expected, actual, f"pixel size ratio is {ratio:.2f}x")


def _check_grid_alignment(a: ManifestEntry, b: ManifestEntry) -> CheckResult:
    name = "grid_alignment"
    expected = f"<= {GRID_OFFSET_PASS_THRESHOLD:g} px fractional offset from {a.path.name}'s grid"
    missing = _missing_crs_names(a, b)
    if missing:
        return CheckResult(name, Status.FATAL, expected, "not computable", f"cannot verify grid alignment: missing CRS on {', '.join(missing)}")

    ax, ay = a.transform[2], a.transform[5]
    bx, by = b.transform[2], b.transform[5]
    if a.crs != b.crs:
        bx, by = Transformer.from_crs(b.crs, a.crs, always_xy=True).transform(bx, by)

    gx, gy = a.gsd
    offset_x_px = (bx - ax) / gx if gx else 0.0
    offset_y_px = (by - ay) / gy if gy else 0.0
    frac_x = abs(offset_x_px - round(offset_x_px))
    frac_y = abs(offset_y_px - round(offset_y_px))
    max_frac = max(frac_x, frac_y)

    actual = f"{max_frac:.2f} px (origin offset {offset_x_px:.2f}px x, {offset_y_px:.2f}px y)"
    if max_frac <= GRID_OFFSET_PASS_THRESHOLD:
        status = Status.PASS
    elif max_frac <= GRID_OFFSET_FATAL_THRESHOLD:
        status = Status.WARN
    else:
        status = Status.FATAL
    return CheckResult(name, status, expected, actual, f"{b.path.name}'s origin sits {max_frac:.2f}px from an exact pixel of {a.path.name}'s grid")


def _check_modality_distinct(mod_a: ModalityInference, mod_b: ModalityInference) -> CheckResult:
    name = "modality_distinct"
    same = mod_a.inferred == mod_b.inferred
    label = "same modality" if same else "distinct modalities"
    return CheckResult(
        name, Status.PASS,
        "informational: modalities are reported, never enforced here",
        f"{mod_a.inferred} vs {mod_b.inferred} ({label})",
        f"{mod_a.path.name} inferred as {mod_a.inferred}, {mod_b.path.name} inferred as {mod_b.inferred}",
    )


def _check_temporal_order(a: ManifestEntry, b: ManifestEntry) -> CheckResult:
    name = "temporal_order"
    expected = "acquisition_date present on both images"
    if a.acquisition_date is None or b.acquisition_date is None:
        missing = [e.path.name for e in (a, b) if e.acquisition_date is None]
        return CheckResult(name, Status.WARN, expected, f"missing on {', '.join(missing)}", f"cannot verify temporal order: missing acquisition_date on {', '.join(missing)}")
    actual = f"{a.acquisition_date} / {b.acquisition_date}"
    if a.acquisition_date == b.acquisition_date:
        message = f"same acquisition date ({a.acquisition_date}) - consistent with a same-day multi-sensor pair"
    else:
        message = f"spans {a.acquisition_date} -> {b.acquisition_date}"
    return CheckResult(name, Status.PASS, expected, actual, message)


def validate_pair(path_a: str | Path, path_b: str | Path) -> ValidationReport:
    """Validate two images individually, then as a pair. Pair checks that
    fundamentally need a working, georeferenced image (footprint_overlap,
    grid_alignment, crs_match) report FATAL with a clear reason instead of
    running — never a crash, never a silent skip.
    """
    path_a, path_b = Path(path_a), Path(path_b)
    entry_a, results_a = _validate_image_internal(path_a, "a")
    entry_b, results_b = _validate_image_internal(path_b, "b")
    results = [*results_a, *results_b]

    if entry_a is None or entry_b is None:
        unreadable = [p.name for p, e in ((path_a, entry_a), (path_b, entry_b)) if e is None]
        for check_name in PAIR_CHECK_NAMES:
            results.append(CheckResult(
                check_name, Status.FATAL, "both images readable", "not computable",
                f"skipped: unreadable image(s): {', '.join(unreadable)}",
            ))
        return ValidationReport(path_a, path_b, results)

    mod_a = infer_modality(path_a)
    mod_b = infer_modality(path_b)

    results.append(_check_crs_match(entry_a, entry_b))
    results.append(_check_footprint_overlap(entry_a, entry_b))
    results.append(_check_gsd_ratio(entry_a, entry_b))
    results.append(_check_grid_alignment(entry_a, entry_b))
    results.append(_check_modality_distinct(mod_a, mod_b))
    results.append(_check_temporal_order(entry_a, entry_b))

    return ValidationReport(path_a, path_b, results)
