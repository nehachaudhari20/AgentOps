"""Machine-readable validation diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RecordDisposition(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    severity: DiagnosticSeverity
    disposition: RecordDisposition
    record_kind: str
    record_id: Optional[str] = None
    details: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "disposition": self.disposition.value,
            "record_kind": self.record_kind,
            "record_id": self.record_id,
            "details": dict(self.details),
        }


@dataclass
class ValidationReport:
    """Aggregated validation outcome for a trace ingest."""

    diagnostics: list[Diagnostic] = field(default_factory=list)
    accepted_event_ids: list[str] = field(default_factory=list)
    rejected_event_ids: list[str] = field(default_factory=list)
    quarantined_event_ids: list[str] = field(default_factory=list)
    accepted_artifact_ids: list[str] = field(default_factory=list)
    rejected_artifact_ids: list[str] = field(default_factory=list)
    quarantined_artifact_ids: list[str] = field(default_factory=list)
    incomplete: bool = False
    has_dependency_cycle: bool = False
    suitable_for_dag_attribution: bool = True
    missing_dependency_parents: list[str] = field(default_factory=list)

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def counts(self) -> dict[str, int]:
        return {
            "diagnostics": len(self.diagnostics),
            "accepted_events": len(self.accepted_event_ids),
            "rejected_events": len(self.rejected_event_ids),
            "quarantined_events": len(self.quarantined_event_ids),
            "accepted_artifacts": len(self.accepted_artifact_ids),
            "rejected_artifacts": len(self.rejected_artifact_ids),
            "quarantined_artifacts": len(self.quarantined_artifact_ids),
            "missing_dependency_parents": len(self.missing_dependency_parents),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts(),
            "incomplete": self.incomplete,
            "has_dependency_cycle": self.has_dependency_cycle,
            "suitable_for_dag_attribution": self.suitable_for_dag_attribution,
            "accepted_event_ids": list(self.accepted_event_ids),
            "rejected_event_ids": list(self.rejected_event_ids),
            "quarantined_event_ids": list(self.quarantined_event_ids),
            "accepted_artifact_ids": list(self.accepted_artifact_ids),
            "rejected_artifact_ids": list(self.rejected_artifact_ids),
            "quarantined_artifact_ids": list(self.quarantined_artifact_ids),
            "missing_dependency_parents": list(self.missing_dependency_parents),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }
