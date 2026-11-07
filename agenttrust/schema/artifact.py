"""Artifact record schema."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from agenttrust.schema.enums import SCHEMA_VERSION

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SHA256_PREFIX_RE = re.compile(r"^sha256:([0-9a-fA-F]{64})$")


def normalize_content_hash(value: str) -> str:
    """
    Normalize a content hash to ``sha256:<hex>``.

    Accepts bare 64-hex SHA-256 or ``sha256:<hex>``.
    """
    text = value.strip()
    m = _SHA256_PREFIX_RE.match(text)
    if m:
        return f"sha256:{m.group(1).lower()}"
    if _SHA256_RE.match(text):
        return f"sha256:{text.lower()}"
    raise ValueError(f"invalid content_hash (expected SHA-256 hex): {value!r}")


@dataclass(frozen=True)
class ArtifactRecord:
    """Stable artifact identity with content hash (no sensitive payload in graph)."""

    artifact_id: str
    artifact_type: str
    content_hash: str
    schema_version: str = SCHEMA_VERSION
    storage_uri: Optional[str] = None
    # Non-sensitive metadata only (e.g., media_type, role labels)
    metadata: tuple[tuple[str, str], ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content_hash": self.content_hash,
            "schema_version": self.schema_version,
            "storage_uri": self.storage_uri,
            "metadata": dict(self.metadata),
        }
