"""Strict SHA-256 digest and integer field validation for PLHC."""

from __future__ import annotations

import re
from typing import Any

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class DigestError(ValueError):
    """Invalid digest or numeric integrity field."""


def normalize_sha256_hex(value: Any, *, field: str = "digest") -> str:
    """
    Validate and normalize a SHA-256 hex digest to lowercase.

    Rejects non-strings, wrong length, and non-hex characters.
    """
    if not isinstance(value, str):
        raise DigestError(f"{field}: expected str, got {type(value).__name__}")
    text = value.strip()
    if not _HEX64_RE.fullmatch(text):
        raise DigestError(f"{field}: must be exactly 64 hexadecimal characters")
    return text.lower()


def is_valid_sha256_hex(value: Any) -> bool:
    try:
        normalize_sha256_hex(value)
        return True
    except DigestError:
        return False


def require_nonneg_int(value: Any, *, field: str) -> int:
    """Require a real integer (not bool), >= 0."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise DigestError(f"{field}: must be a non-boolean int, got {type(value).__name__}")
    if value < 0:
        raise DigestError(f"{field}: must be >= 0, got {value}")
    return value
