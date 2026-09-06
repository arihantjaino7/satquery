"""Command-line entry points. Presentation only — all the real logic lives
in satquery.io.*; this module just calls it and formats the result.
"""

from __future__ import annotations

import json
from pathlib import Path

import rasterio

from satquery.agent.graph import run as run_agent
from satquery.agent.state import SatQueryState
from satquery.io.manifest import ManifestEntry, read_manifest
from satquery.io.modality import SAR, ModalityInference, infer_modality
from satquery.io.preprocess import optical_to_display, sar_to_display, write_png
from satquery.io.validate import ValidationReport, validate_pair
from satquery.registry.resolver import ResolutionResult, resolve
from satquery.serialize import to_jsonable


def _format_manifest(entry: ManifestEntry) -> str:
    a, b, c, d, e, f = entry.transform
    lines = [
        f"=== Manifest: {entry.path} ===",
        f"sha256          : {entry.sha256}",
        f"driver          : {entry.driver}",
        f"crs             : {entry.crs if entry.has_crs else 'MISSING'}",
        f"transform       : | {a:.3f} {b:.3f} {c:.2f} |",
        f"                  | {d:.3f} {e:.3f} {f:.2f} |",
        f"shape (h x w)   : {entry.shape[0]} x {entry.shape[1]}",
        f"dtype           : {entry.dtype}",
        f"band_count      : {entry.band_count}",
        f"nodata          : {entry.nodata if entry.nodata is not None else 'none'}",
        f"nodata_fraction : {entry.nodata_fraction * 100:.2f}%",
        f"gsd             : {entry.gsd[0]:g} x {entry.gsd[1]:g} m",
        f"footprint       : {entry.footprint_wkt}",
        "  corners       : TL={} TR={} BR={} BL={}".format(
            *[f"({x:.1f}, {y:.1f})" for x, y in entry.footprint_corners]
        ),
        f"acquisition_date: {entry.acquisition_date or 'unknown'}",
    ]
    return "\n".join(lines)


def _format_modality(inf: ModalityInference) -> str:
    if inf.filename_hint is None:
        agreement = "no filename hint to compare"
    elif inf.agrees_with_hint:
        agreement = "filename hint agrees"
    else:
        agreement = f"filename hint disagrees (hint: {inf.filename_hint})"

    lines = [f"modality        : {inf.inferred} ({agreement})"]
    for line in inf.evidence:
        lines.append(f"  evidence      : {line}")
    return "\n".join(lines)


def cmd_inspect(path: str) -> None:
    manifest = read_manifest(path)
    modality = infer_modality(path)
    print(_format_manifest(manifest))
    print(_format_modality(modality))


def _format_validation_report(report: ValidationReport) -> str:
    headers = ("STATUS", "CHECK", "EXPECTED", "ACTUAL", "MESSAGE")
    rows = [(r.status.value, r.name, r.expected, r.actual, r.message) for r in report.results]

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(row: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [f"=== Validate: {report.path_a.name}  x  {report.path_b.name} ==="]
    lines.append(fmt_row(headers))
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append(fmt_row(row))

    verdict = "OK, safe to proceed" if report.ok else "HALT (FATAL present)"
    lines.append("")
    lines.append(f"Result: {report.pass_count} PASS, {report.warn_count} WARN, {report.fatal_count} FATAL -> {verdict}")
    return "\n".join(lines)


def cmd_validate(path_a: str, path_b: str) -> ValidationReport:
    report = validate_pair(path_a, path_b)
    print(_format_validation_report(report))
    return report


def cmd_preprocess(path: str, out: str | None = None) -> Path:
    path_obj = Path(path)
    modality = infer_modality(path_obj)

    with rasterio.open(path_obj) as ds:
        arr = ds.read()
        descriptions = [d for d in ds.descriptions if d]
        band_names = descriptions if len(descriptions) == arr.shape[0] else None

    if modality.inferred == SAR:
        display = sar_to_display(arr)
        path_kind = "SAR: VV/VH/ratio false colour" if arr.shape[0] >= 2 else "SAR: single-pol grayscale"
    else:
        display = optical_to_display(arr, band_names=band_names)
        path_kind = "optical: true-colour band selection"

    out_path = Path(out) if out else path_obj.with_suffix(".preview.png")
    write_png(display, out_path)

    print(f"modality     : {modality.inferred}")
    print(f"display path : {path_kind}")
    print(f"wrote        : {out_path.resolve()}  ({display.shape[2]}x{display.shape[1]})")
    return out_path


def _format_resolution(result: ResolutionResult) -> str:
    headers = ("RESULT", "TOOL", "SCORE", "REASON")
    rows = []
    for c in result.candidates:
        if c.tool_id == result.chosen:
            status = "CHOSEN"
        elif c.eligible:
            status = "eligible"
        else:
            status = "rejected"
        score = f"{c.score:.2f}" if c.score is not None else "-"
        rows.append((status, c.tool_id, score, c.reason))

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(row: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [
        f"=== Resolve: capability={result.capability!r} modalities={list(result.modalities)} image_count={result.image_count} ===",
        fmt_row(headers),
        "  ".join("-" * w for w in widths),
    ]
    lines.extend(fmt_row(row) for row in rows)

    lines.append("")
    if result.chosen is not None:
        lines.append(f"Chosen: {result.chosen}  ({len(result.eligible)} eligible, {len(result.rejected)} rejected)")
    else:
        lines.append(f"Chosen: none - no candidate qualifies ({len(result.rejected)} rejected)")
    return "\n".join(lines)


def cmd_resolve(capability: str, modalities: list[str], image_count: int) -> ResolutionResult:
    result = resolve(capability, modalities, image_count)
    print(_format_resolution(result))
    return result


def _state_to_trace_json(state: SatQueryState) -> dict:
    return {
        "question": state.question,
        "images": [str(p) for p in state.image_paths],
        "outcome": state.outcome,
        "task": state.task,
        "modalities": list(state.modalities) if state.modalities else None,
        "plan": {
            "chosen": state.plan.chosen,
            "candidates": to_jsonable(state.plan.candidates),
        } if state.plan is not None else None,
        "execution": to_jsonable(state.execution),
        "confidence": state.confidence,
        "answer": state.answer,
        "trace": [to_jsonable(e) for e in state.trace],
    }


def cmd_ask(question: str, image_paths: list[str]) -> SatQueryState:
    state = run_agent(question, image_paths)
    print(json.dumps(_state_to_trace_json(state), indent=2))
    return state
