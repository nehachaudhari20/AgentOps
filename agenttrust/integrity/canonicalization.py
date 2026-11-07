"""
Deterministic canonicalization for PLHC (agenttrust-canonical-json-v1).

Not RFC 8785 / JCS. Rules are documented in PHASE_2_7_PLHC.md.
"""

from __future__ import annotations

import json
import math
from typing import Any

CANONICALIZATION_VERSION = "agenttrust-canonical-json-v1"


class CanonicalizationError(ValueError):
    """Raised when a value cannot be canonically serialized."""


def _validate(value: Any, *, path: str = "$") -> Any:
    """Return a JSON-safe structure; reject ambiguous / non-finite values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"{path}: non-finite float {value!r}")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [_validate(v, path=f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise CanonicalizationError(f"{path}: non-string object key {k!r}")
            out[k] = _validate(v, path=f"{path}.{k}")
        return out
    raise CanonicalizationError(
        f"{path}: unsupported type {type(value).__name__} (value={value!r})"
    )


def canonicalize(value: Any) -> bytes:
    """
    Deterministic UTF-8 JSON bytes.

    - Keys sorted lexicographically (Unicode code-point order via Python str sort)
    - No insignificant whitespace
    - allow_nan=False
    - ensure_ascii=False (UTF-8)
    - bool / int / float / null / str distinctions preserved by json module
    """
    safe = _validate(value)
    try:
        text = json.dumps(
            safe,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError(str(exc)) from exc
    return text.encode("utf-8")


def canonicalize_hex_digest_preview(value: Any) -> str:
    """Debug helper: UTF-8 canonical text as str (not for hashing)."""
    return canonicalize(value).decode("utf-8")
