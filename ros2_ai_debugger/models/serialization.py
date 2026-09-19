"""Minimal dataclass <-> plain-dict conversion (no third-party dependency)."""
from __future__ import annotations

import dataclasses
import types
import typing
from typing import Any, TypeVar

T = TypeVar("T")


def to_dict(obj: Any) -> dict[str, Any]:
    """Convert a (nested) dataclass instance to JSON-compatible primitives."""
    return dataclasses.asdict(obj)


def from_dict(cls: type[T], data: dict[str, Any]) -> T:
    """Rebuild a dataclass from :func:`to_dict` output.

    Unknown keys are ignored and missing keys fall back to field defaults, so
    snapshots written by other versions of the tool still load.
    """
    return _convert(cls, data)


def _convert(tp: Any, value: Any) -> Any:
    origin = typing.get_origin(tp)
    args = typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        if value is None:
            return None
        inner = [a for a in args if a is not type(None)]
        return _convert(inner[0], value)
    if origin is list:
        return [_convert(args[0], v) for v in value]
    if origin is dict:
        return {k: _convert(args[1], v) for k, v in value.items()}
    if dataclasses.is_dataclass(tp) and isinstance(value, dict):
        hints = typing.get_type_hints(tp)
        kwargs = {
            f.name: _convert(hints[f.name], value[f.name])
            for f in dataclasses.fields(tp)
            if f.name in value and f.init
        }
        return tp(**kwargs)
    return value
