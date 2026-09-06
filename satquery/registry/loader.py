"""Read every YAML file in `registry/entries/`, schema-validate each one
against `ToolSpec`, and fail loudly — naming the file and the field — the
moment something is wrong.

The whole point of validating here rather than lazily wherever a tool gets
used: a malformed entry should break at startup, in a message that says
exactly which file and field is broken, never as a confusing crash (or worse,
a silent misfire) in the middle of answering someone's query.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from satquery.registry.schema import ToolSpec

DEFAULT_ENTRIES_DIR = Path(__file__).resolve().parent.parent.parent / "registry" / "entries"


class RegistryLoadError(Exception):
    """A registry entry (or the registry as a whole) failed to load. The
    message always names the offending file and, where possible, the field.
    """


def _load_one(path: Path) -> ToolSpec:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryLoadError(f"{path.name}: invalid YAML - {exc}") from exc

    if not isinstance(raw, dict):
        raise RegistryLoadError(f"{path.name}: expected a YAML mapping at the top level, got {type(raw).__name__}")

    try:
        return ToolSpec.model_validate(raw)
    except ValidationError as exc:
        field_errors = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['msg']}" for e in exc.errors())
        raise RegistryLoadError(f"{path.name}: schema validation failed - {field_errors}") from exc


def load_registry(entries_dir: str | Path = DEFAULT_ENTRIES_DIR) -> list[ToolSpec]:
    """Load and validate every `*.yaml`/`*.yml` file in `entries_dir`.

    Sorted by filename so load (and therefore resolver candidate) order is
    reproducible across machines and runs, not dependent on filesystem
    iteration order. Raises `RegistryLoadError` naming the specific file and
    field on the first problem found - a malformed entry, a duplicate `id`,
    or a `fallback` that doesn't match any loaded tool.
    """
    entries_dir = Path(entries_dir)
    paths = sorted({*entries_dir.glob("*.yaml"), *entries_dir.glob("*.yml")}, key=lambda p: p.name)

    if not paths:
        raise RegistryLoadError(f"no registry entries found in {entries_dir}")

    specs = [_load_one(p) for p in paths]

    ids = [s.id for s in specs]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise RegistryLoadError(f"duplicate tool id(s) across {entries_dir}: {dupes}")

    id_set = set(ids)
    for spec in specs:
        if spec.fallback is not None and spec.fallback not in id_set:
            raise RegistryLoadError(f"{spec.id}: fallback {spec.fallback!r} does not match any loaded tool id")

    return specs


@lru_cache(maxsize=1)
def get_registry() -> tuple[ToolSpec, ...]:
    """Cached load of the default `registry/entries/` directory. This is the
    "at boot" load: the first thing that touches the registry for real
    (the CLI's `resolve` command, the agent's `plan` node) calls this, so a
    malformed entry surfaces immediately rather than mid-query.
    """
    return tuple(load_registry())
