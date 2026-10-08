from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VOLATILE_SUFFIXES = (".provenance.fetched_at",)

_MISSING: Any = object()


@dataclass(frozen=True, slots=True)
class Change:
    path: str
    before: Any
    after: Any

    def __str__(self) -> str:
        if self.before is _MISSING:
            return f"added {self.path} = {self.after!r}"
        if self.after is _MISSING:
            return f"removed {self.path} (was {self.before!r})"
        return f"changed {self.path}: {self.before!r} -> {self.after!r}"


def diff_snapshots(old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    old_flat, new_flat = flatten(old), flatten(new)
    changes = []
    for path in sorted(old_flat.keys() | new_flat.keys()):
        if path.endswith(VOLATILE_SUFFIXES):
            continue
        before, after = old_flat.get(path, _MISSING), new_flat.get(path, _MISSING)
        if before != after:
            changes.append(Change(path, before, after))
    return changes


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Dotted paths; lists of objects with ``id`` are keyed by it, so reordering is not a change."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out |= flatten(item, f"{prefix}.{key}" if prefix else str(key))
        return out
    if isinstance(value, list) and value and all(isinstance(i, dict) and "id" in i for i in value):
        out = {}
        for item in value:
            out |= flatten(item, f"{prefix}[{item['id']}]")
        return out
    return {prefix: value}
