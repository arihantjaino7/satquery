"""Turn dataclasses, Pydantic models, enums, and Paths into plain
JSON-serialisable Python (dict/list/str/number/bool/None), recursively.

Used to print full agent traces and resolver results as JSON without hand
writing a `to_dict()` for every dataclass in `satquery.io` and
`satquery.registry` that a trace might reference.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return to_jsonable(obj.model_dump(mode="json"))
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in obj]
    return obj
