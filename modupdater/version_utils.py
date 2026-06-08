"""Tiny helpers to order version strings like '1.21.1' and '26.1.2'."""

from __future__ import annotations

from typing import Iterable, List, Tuple


def parse_version(v: str) -> Tuple[int, ...]:
    """Turn '1.21.1' -> (1, 21, 1) so versions sort numerically, not as text.

    Non-numeric chunks degrade gracefully to their digits (or 0) so a weird
    label never crashes the sort.
    """
    parts: List[int] = []
    for chunk in v.replace("-", ".").replace("_", ".").split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            digits = "".join(ch for ch in chunk if ch.isdigit())
            parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def sort_desc(versions: Iterable[str]) -> List[str]:
    """Newest first."""
    return sorted(versions, key=parse_version, reverse=True)


def latest(versions: Iterable[str]) -> str | None:
    versions = list(versions)
    return max(versions, key=parse_version) if versions else None
