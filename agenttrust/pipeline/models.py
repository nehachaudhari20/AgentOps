"""Versioned result contracts for the AgentTrust end-to-end pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

PIPELINE_FORMAT_VERSION = "agenttrust-pipeline-result-v1"


class ComponentStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    INELIGIBLE = "ineligible"


@dataclass
class PipelineConfig:
    """Public configuration for one pipeline run (no ground-truth fields)."""

    run_p1: bool = True
    run_p2: bool = True
    allow_incomplete_rpa: bool = False
    primary_outcome_only: bool = False  # if True, only first outcome candidate
    include_inclusion_proof: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_p1": self.run_p1,
            "run_p2": self.run_p2,
            "allow_incomplete_rpa": self.allow_incomplete_rpa,
            "primary_outcome_only": self.primary_outcome_only,
            "include_inclusion_proof": self.include_inclusion_proof,
        }

    def fingerprint(self) -> str:
        import hashlib
        import json

        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class TracePipelineResult:
    """Machine-readable consolidated result for one trace."""

    format_version: str
    trace_id: str
    ok: bool
    hard_error: Optional[str]
    input_fingerprint_sha256: Optional[str]
    provenance_fingerprint: Optional[str]
    config: dict[str, Any]
    config_fingerprint: str
    versions: dict[str, str]
    validation: dict[str, Any]
    graph_summary: dict[str, Any]
    projection_eligibility: dict[str, Any]
    rpa: dict[str, Any]
    mfav: dict[str, Any]
    plhc: dict[str, Any]
    assurance: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timing_ms: Optional[dict[str, float]] = None  # excluded from content hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "trace_id": self.trace_id,
            "ok": self.ok,
            "hard_error": self.hard_error,
            "input_fingerprint_sha256": self.input_fingerprint_sha256,
            "provenance_fingerprint": self.provenance_fingerprint,
            "config": dict(self.config),
            "config_fingerprint": self.config_fingerprint,
            "versions": dict(self.versions),
            "validation": dict(self.validation),
            "graph_summary": dict(self.graph_summary),
            "projection_eligibility": dict(self.projection_eligibility),
            "rpa": dict(self.rpa),
            "mfav": dict(self.mfav),
            "plhc": dict(self.plhc),
            "assurance": dict(self.assurance),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "timing_ms": None if self.timing_ms is None else dict(self.timing_ms),
        }

    def deterministic_payload(self) -> dict[str, Any]:
        """Payload used for determinism checks (excludes timing)."""
        d = self.to_dict()
        d.pop("timing_ms", None)
        return d


@dataclass
class CorpusPipelineSummary:
    format_version: str
    corpus: str
    traces_root: str
    corpus_fingerprint_sha256: Optional[str]
    config_fingerprint: str
    n_examined: int
    n_eligible: int
    n_ineligible: int
    n_success: int
    n_failed: int
    n_hard_errors: int
    trace_ids_success: list[str]
    trace_ids_failed: list[str]
    trace_ids_ineligible: list[str]
    versions: dict[str, str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "corpus": self.corpus,
            "traces_root": self.traces_root,
            "corpus_fingerprint_sha256": self.corpus_fingerprint_sha256,
            "config_fingerprint": self.config_fingerprint,
            "n_examined": self.n_examined,
            "n_eligible": self.n_eligible,
            "n_ineligible": self.n_ineligible,
            "n_success": self.n_success,
            "n_failed": self.n_failed,
            "n_hard_errors": self.n_hard_errors,
            "trace_ids_success": list(self.trace_ids_success),
            "trace_ids_failed": list(self.trace_ids_failed),
            "trace_ids_ineligible": list(self.trace_ids_ineligible),
            "versions": dict(self.versions),
            "notes": list(self.notes),
        }
