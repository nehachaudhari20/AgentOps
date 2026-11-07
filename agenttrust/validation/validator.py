"""Strict validation of event/artifact/relationship inputs without mutating originals."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

import networkx as nx

from agenttrust.schema.artifact import ArtifactRecord, normalize_content_hash
from agenttrust.schema.enums import (
    EventCategory,
    EventStatus,
    RelationshipType,
    SCHEMA_VERSION,
    category_for_event_type,
)
from agenttrust.schema.event import EventRecord, parse_timestamp
from agenttrust.schema.relationship import RelationshipRecord
from agenttrust.validation.report import (
    Diagnostic,
    DiagnosticSeverity,
    RecordDisposition,
    ValidationReport,
)


def _diag(
    code: str,
    message: str,
    *,
    severity: DiagnosticSeverity,
    disposition: RecordDisposition,
    record_kind: str,
    record_id: Optional[str] = None,
    **details: str,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        message=message,
        severity=severity,
        disposition=disposition,
        record_kind=record_kind,
        record_id=record_id,
        details=tuple(sorted((k, str(v)) for k, v in details.items())),
    )


class TraceValidator:
    """Validate raw mappings into typed records; never mutates input dicts."""

    def validate_trace(
        self,
        *,
        events: Iterable[Mapping[str, Any]],
        artifacts: Iterable[Mapping[str, Any]] | None = None,
        relationships: Iterable[Mapping[str, Any]] | None = None,
        default_trace_id: Optional[str] = None,
    ) -> tuple[list[EventRecord], list[ArtifactRecord], list[RelationshipRecord], ValidationReport]:
        report = ValidationReport()
        event_list = [dict(e) for e in events]
        artifact_list = [dict(a) for a in (artifacts or [])]
        rel_list = [dict(r) for r in (relationships or [])]

        accepted_events: list[EventRecord] = []
        accepted_artifacts: list[ArtifactRecord] = []
        accepted_rels: list[RelationshipRecord] = []

        seen_event_ids: set[str] = set()
        seen_artifact_ids: dict[str, str] = {}  # id -> content_hash

        # --- artifacts first (events may reference them) ---
        for raw in artifact_list:
            art, dlist = self._validate_artifact(raw, seen_artifact_ids)
            for d in dlist:
                report.add(d)
            if art is None:
                aid = str(raw.get("artifact_id") or "")
                if any(d.disposition == RecordDisposition.QUARANTINED for d in dlist):
                    if aid:
                        report.quarantined_artifact_ids.append(aid)
                else:
                    if aid:
                        report.rejected_artifact_ids.append(aid)
                continue
            accepted_artifacts.append(art)
            seen_artifact_ids[art.artifact_id] = art.content_hash
            report.accepted_artifact_ids.append(art.artifact_id)

        known_artifact_ids = set(seen_artifact_ids)

        # --- events ---
        for raw in event_list:
            ev, dlist = self._validate_event(raw, default_trace_id=default_trace_id)
            for d in dlist:
                report.add(d)
            if ev is None:
                eid = str(raw.get("event_id") or "")
                if any(d.disposition == RecordDisposition.QUARANTINED for d in dlist):
                    if eid:
                        report.quarantined_event_ids.append(eid)
                else:
                    if eid:
                        report.rejected_event_ids.append(eid)
                continue
            if ev.event_id in seen_event_ids:
                report.add(
                    _diag(
                        "duplicate_event_id",
                        f"Duplicate event_id {ev.event_id!r}; record quarantined (not overwritten).",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.QUARANTINED,
                        record_kind="event",
                        record_id=ev.event_id,
                    )
                )
                report.quarantined_event_ids.append(ev.event_id)
                continue
            seen_event_ids.add(ev.event_id)
            accepted_events.append(ev)
            report.accepted_event_ids.append(ev.event_id)

        event_ids = {e.event_id for e in accepted_events}

        # --- missing dependency parents (completeness, not invalid event) ---
        missing_parents: list[str] = []
        for ev in accepted_events:
            for dep in ev.dependency_event_ids:
                if dep not in event_ids:
                    missing_parents.append(dep)
                    report.add(
                        _diag(
                            "missing_dependency_parent",
                            f"Event {ev.event_id!r} depends on missing parent {dep!r}.",
                            severity=DiagnosticSeverity.WARNING,
                            disposition=RecordDisposition.ACCEPTED,
                            record_kind="event",
                            record_id=ev.event_id,
                            missing_parent=dep,
                        )
                    )
            for aid in ev.input_artifact_ids + ev.output_artifact_ids:
                if aid not in known_artifact_ids:
                    report.incomplete = True
                    report.add(
                        _diag(
                            "missing_artifact_reference",
                            f"Event {ev.event_id!r} references unknown artifact {aid!r}.",
                            severity=DiagnosticSeverity.WARNING,
                            disposition=RecordDisposition.ACCEPTED,
                            record_kind="event",
                            record_id=ev.event_id,
                            artifact_id=aid,
                        )
                    )

        if missing_parents:
            report.incomplete = True
            # unique preserve order
            seen_m: set[str] = set()
            for m in missing_parents:
                if m not in seen_m:
                    seen_m.add(m)
                    report.missing_dependency_parents.append(m)

        # --- relationships: auto from events + optional explicit ---
        auto_rels = self._relationships_from_events(accepted_events, known_artifact_ids, report)
        accepted_rels.extend(auto_rels)

        for raw in rel_list:
            rel, dlist = self._validate_relationship(raw, event_ids, known_artifact_ids)
            for d in dlist:
                report.add(d)
            if rel is not None:
                accepted_rels.append(rel)

        # Deduplicate relationships by edge key (prefer non-derived)
        accepted_rels = self._dedupe_relationships(accepted_rels)

        # --- cycle detection on DEPENDS_ON subgraph ---
        dep_graph = nx.DiGraph()
        for ev in accepted_events:
            dep_graph.add_node(ev.event_id)
        for rel in accepted_rels:
            if rel.rel_type == RelationshipType.DEPENDS_ON and not rel.derived:
                if rel.source_id in event_ids and rel.target_id in event_ids:
                    dep_graph.add_edge(rel.source_id, rel.target_id)

        if dep_graph.number_of_nodes() > 0 and not nx.is_directed_acyclic_graph(dep_graph):
            report.has_dependency_cycle = True
            report.suitable_for_dag_attribution = False
            try:
                cycle = nx.find_cycle(dep_graph, orientation="original")
                cycle_ids = " -> ".join(f"{u}" for u, v, *_ in cycle) + f" -> {cycle[0][0]}"
            except nx.NetworkXNoCycle:
                cycle_ids = "unknown"
            report.add(
                _diag(
                    "dependency_cycle",
                    "DEPENDS_ON subgraph contains a cycle; unsuitable for DAG attribution.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.ACCEPTED,
                    record_kind="trace",
                    cycle=cycle_ids,
                )
            )
        elif report.incomplete:
            # Incomplete traces remain usable for some analyses but flagged.
            report.suitable_for_dag_attribution = True

        return accepted_events, accepted_artifacts, accepted_rels, report

    def _validate_artifact(
        self,
        raw: Mapping[str, Any],
        seen: Mapping[str, str],
    ) -> tuple[Optional[ArtifactRecord], list[Diagnostic]]:
        diags: list[Diagnostic] = []
        aid = raw.get("artifact_id")
        if not isinstance(aid, str) or not aid.strip():
            diags.append(
                _diag(
                    "missing_required_field",
                    "Artifact missing required field artifact_id.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    field="artifact_id",
                )
            )
            return None, diags
        aid = aid.strip()
        atype = raw.get("artifact_type")
        if not isinstance(atype, str) or not atype.strip():
            diags.append(
                _diag(
                    "missing_required_field",
                    f"Artifact {aid!r} missing required field artifact_type.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    record_id=aid,
                    field="artifact_type",
                )
            )
            return None, diags
        ch = raw.get("content_hash")
        if not isinstance(ch, str) or not ch.strip():
            diags.append(
                _diag(
                    "missing_required_field",
                    f"Artifact {aid!r} missing required field content_hash.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    record_id=aid,
                    field="content_hash",
                )
            )
            return None, diags
        try:
            content_hash = normalize_content_hash(ch)
        except ValueError as exc:
            diags.append(
                _diag(
                    "invalid_content_hash",
                    str(exc),
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    record_id=aid,
                )
            )
            return None, diags

        if aid in seen and seen[aid] != content_hash:
            diags.append(
                _diag(
                    "duplicate_artifact_id",
                    f"Conflicting artifact_id {aid!r} with different content_hash; quarantined.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.QUARANTINED,
                    record_kind="artifact",
                    record_id=aid,
                )
            )
            return None, diags
        if aid in seen and seen[aid] == content_hash:
            diags.append(
                _diag(
                    "duplicate_artifact_id_identical",
                    f"Duplicate identical artifact_id {aid!r}; subsequent copy ignored.",
                    severity=DiagnosticSeverity.WARNING,
                    disposition=RecordDisposition.QUARANTINED,
                    record_kind="artifact",
                    record_id=aid,
                )
            )
            return None, diags

        schema_version = raw.get("schema_version", SCHEMA_VERSION)
        if not isinstance(schema_version, str) or not schema_version.strip():
            diags.append(
                _diag(
                    "missing_required_field",
                    f"Artifact {aid!r} has invalid schema_version.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    record_id=aid,
                    field="schema_version",
                )
            )
            return None, diags

        storage_uri = raw.get("storage_uri")
        if storage_uri is not None and not isinstance(storage_uri, str):
            diags.append(
                _diag(
                    "invalid_storage_uri",
                    f"Artifact {aid!r} storage_uri must be a string when present.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    record_id=aid,
                )
            )
            return None, diags

        meta_raw = raw.get("metadata") or {}
        if meta_raw is None:
            meta_raw = {}
        if not isinstance(meta_raw, dict):
            diags.append(
                _diag(
                    "invalid_metadata",
                    f"Artifact {aid!r} metadata must be an object when present.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="artifact",
                    record_id=aid,
                )
            )
            return None, diags
        metadata = tuple(sorted((str(k), str(v)) for k, v in meta_raw.items()))

        return (
            ArtifactRecord(
                artifact_id=aid,
                artifact_type=atype.strip(),
                content_hash=content_hash,
                schema_version=schema_version.strip(),
                storage_uri=storage_uri,
                metadata=metadata,
            ),
            diags,
        )

    def _validate_event(
        self,
        raw: Mapping[str, Any],
        *,
        default_trace_id: Optional[str],
    ) -> tuple[Optional[EventRecord], list[Diagnostic]]:
        diags: list[Diagnostic] = []

        def require_str(key: str) -> Optional[str]:
            val = raw.get(key)
            if not isinstance(val, str) or not val.strip():
                diags.append(
                    _diag(
                        "missing_required_field",
                        f"Event missing required field {key}.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="event",
                        record_id=str(raw.get("event_id") or "") or None,
                        field=key,
                    )
                )
                return None
            return val.strip()

        event_id = require_str("event_id")
        event_type = require_str("event_type")
        schema_version = raw.get("schema_version", SCHEMA_VERSION)
        if not isinstance(schema_version, str) or not schema_version.strip():
            diags.append(
                _diag(
                    "missing_required_field",
                    "Event has invalid schema_version.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="event",
                    record_id=event_id,
                    field="schema_version",
                )
            )
            return None, diags
        schema_version = schema_version.strip()

        trace_id = raw.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id.strip():
            if default_trace_id:
                trace_id = default_trace_id
            else:
                diags.append(
                    _diag(
                        "missing_required_field",
                        "Event missing required field trace_id.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="event",
                        record_id=event_id,
                        field="trace_id",
                    )
                )
                return None, diags
        else:
            trace_id = trace_id.strip()

        if event_id is None or event_type is None:
            return None, diags

        # category
        if "category" in raw and raw["category"] is not None:
            try:
                category = EventCategory(str(raw["category"]).strip().lower())
            except ValueError:
                diags.append(
                    _diag(
                        "invalid_category",
                        f"Unknown category {raw['category']!r}; quarantined.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.QUARANTINED,
                        record_kind="event",
                        record_id=event_id,
                    )
                )
                return None, diags
        else:
            category = category_for_event_type(event_type)
            if category == EventCategory.OTHER:
                diags.append(
                    _diag(
                        "unknown_event_type",
                        f"Unknown event_type {event_type!r} mapped to category other.",
                        severity=DiagnosticSeverity.INFO,
                        disposition=RecordDisposition.ACCEPTED,
                        record_kind="event",
                        record_id=event_id,
                    )
                )

        agent_id = raw.get("agent_id")
        if agent_id is not None:
            if not isinstance(agent_id, str):
                diags.append(
                    _diag(
                        "invalid_agent_id",
                        "agent_id must be a string or null.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="event",
                        record_id=event_id,
                    )
                )
                return None, diags
            agent_id = agent_id.strip() or None

        status_raw = raw.get("status")
        if status_raw is None:
            status = EventStatus.UNKNOWN
            diags.append(
                _diag(
                    "missing_status",
                    "status absent; recorded as unknown (not inferred as success).",
                    severity=DiagnosticSeverity.INFO,
                    disposition=RecordDisposition.ACCEPTED,
                    record_kind="event",
                    record_id=event_id,
                )
            )
        else:
            try:
                status = EventStatus(str(status_raw).strip().lower())
            except ValueError:
                diags.append(
                    _diag(
                        "invalid_status",
                        f"Unknown status {status_raw!r}; quarantined.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.QUARANTINED,
                        record_kind="event",
                        record_id=event_id,
                    )
                )
                return None, diags

        ts_start = None
        ts_end = None
        if "ts_start" in raw and raw["ts_start"] is not None:
            try:
                ts_start = parse_timestamp(raw["ts_start"], field_name="ts_start")
            except ValueError as exc:
                diags.append(
                    _diag(
                        "invalid_timestamp",
                        str(exc),
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="event",
                        record_id=event_id,
                        field="ts_start",
                    )
                )
                return None, diags
        if "ts_end" in raw and raw["ts_end"] is not None:
            try:
                ts_end = parse_timestamp(raw["ts_end"], field_name="ts_end")
            except ValueError as exc:
                diags.append(
                    _diag(
                        "invalid_timestamp",
                        str(exc),
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="event",
                        record_id=event_id,
                        field="ts_end",
                    )
                )
                return None, diags
        if ts_start is not None and ts_end is not None and ts_end < ts_start:
            diags.append(
                _diag(
                    "invalid_timestamp_order",
                    "ts_end precedes ts_start.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="event",
                    record_id=event_id,
                )
            )
            return None, diags

        try:
            input_ids = EventRecord.normalize_id_list(
                raw.get("input_artifact_ids"), field_name="input_artifact_ids"
            )
            output_ids = EventRecord.normalize_id_list(
                raw.get("output_artifact_ids"), field_name="output_artifact_ids"
            )
            dep_ids = EventRecord.normalize_id_list(
                raw.get("dependency_event_ids"), field_name="dependency_event_ids"
            )
            invokes = EventRecord.normalize_id_list(
                raw.get("invokes_event_ids"), field_name="invokes_event_ids"
            )
            observed_after = EventRecord.normalize_id_list(
                raw.get("observed_after_event_ids"), field_name="observed_after_event_ids"
            )
        except ValueError as exc:
            diags.append(
                _diag(
                    "invalid_id_list",
                    str(exc),
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="event",
                    record_id=event_id,
                )
            )
            return None, diags

        if event_id in dep_ids:
            diags.append(
                _diag(
                    "self_dependency",
                    f"Event {event_id!r} lists itself as a dependency; quarantined.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.QUARANTINED,
                    record_kind="event",
                    record_id=event_id,
                )
            )
            return None, diags

        retries = raw.get("retries_event_id")
        if retries is not None:
            if not isinstance(retries, str) or not retries.strip():
                diags.append(
                    _diag(
                        "invalid_retries_event_id",
                        "retries_event_id must be a non-empty string when present.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="event",
                        record_id=event_id,
                    )
                )
                return None, diags
            retries = retries.strip()
            if retries == event_id:
                diags.append(
                    _diag(
                        "self_retry",
                        f"Event {event_id!r} retries itself; quarantined.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.QUARANTINED,
                        record_kind="event",
                        record_id=event_id,
                    )
                )
                return None, diags

        return (
            EventRecord(
                event_id=event_id,
                trace_id=trace_id,
                event_type=event_type,
                category=category,
                agent_id=agent_id,
                status=status,
                ts_start=ts_start,
                ts_end=ts_end,
                input_artifact_ids=input_ids,
                output_artifact_ids=output_ids,
                dependency_event_ids=dep_ids,
                schema_version=schema_version,
                invokes_event_ids=invokes,
                retries_event_id=retries,
                observed_after_event_ids=observed_after,
            ),
            diags,
        )

    def _relationships_from_events(
        self,
        events: list[EventRecord],
        known_artifacts: set[str],
        report: ValidationReport,
    ) -> list[RelationshipRecord]:
        rels: list[RelationshipRecord] = []
        event_ids = {e.event_id for e in events}
        for ev in events:
            for dep in ev.dependency_event_ids:
                if dep in event_ids:
                    rels.append(
                        RelationshipRecord(
                            rel_type=RelationshipType.DEPENDS_ON,
                            source_id=dep,
                            target_id=ev.event_id,
                            derived=False,
                            evidence="dependency_event_ids",
                        )
                    )
            for aid in ev.output_artifact_ids:
                if aid in known_artifacts:
                    rels.append(
                        RelationshipRecord(
                            rel_type=RelationshipType.PRODUCES,
                            source_id=ev.event_id,
                            target_id=aid,
                            derived=False,
                            evidence="output_artifact_ids",
                        )
                    )
            for aid in ev.input_artifact_ids:
                if aid in known_artifacts:
                    rels.append(
                        RelationshipRecord(
                            rel_type=RelationshipType.CONSUMES,
                            source_id=aid,
                            target_id=ev.event_id,
                            derived=False,
                            evidence="input_artifact_ids",
                        )
                    )
            for callee in ev.invokes_event_ids:
                if callee in event_ids:
                    rels.append(
                        RelationshipRecord(
                            rel_type=RelationshipType.INVOKES,
                            source_id=ev.event_id,
                            target_id=callee,
                            derived=False,
                            evidence="invokes_event_ids",
                        )
                    )
            if ev.retries_event_id and ev.retries_event_id in event_ids:
                rels.append(
                    RelationshipRecord(
                        rel_type=RelationshipType.RETRIES,
                        source_id=ev.event_id,
                        target_id=ev.retries_event_id,
                        derived=False,
                        evidence="retries_event_id",
                    )
                )
            for earlier in ev.observed_after_event_ids:
                if earlier in event_ids:
                    rels.append(
                        RelationshipRecord(
                            rel_type=RelationshipType.OBSERVED_AFTER,
                            source_id=earlier,
                            target_id=ev.event_id,
                            derived=False,
                            evidence="observed_after_event_ids",
                        )
                    )
        return rels

    def _validate_relationship(
        self,
        raw: Mapping[str, Any],
        event_ids: set[str],
        artifact_ids: set[str],
    ) -> tuple[Optional[RelationshipRecord], list[Diagnostic]]:
        diags: list[Diagnostic] = []
        rt = raw.get("rel_type")
        try:
            rel_type = RelationshipType(str(rt))
        except Exception:
            diags.append(
                _diag(
                    "unknown_relationship_type",
                    f"Unknown relationship type {rt!r}; rejected.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="relationship",
                )
            )
            return None, diags
        src = raw.get("source_id")
        tgt = raw.get("target_id")
        if not isinstance(src, str) or not isinstance(tgt, str) or not src.strip() or not tgt.strip():
            diags.append(
                _diag(
                    "invalid_relationship_endpoints",
                    "Relationship source_id and target_id must be non-empty strings.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="relationship",
                )
            )
            return None, diags
        src, tgt = src.strip(), tgt.strip()
        if rel_type == RelationshipType.DEPENDS_ON and src == tgt:
            diags.append(
                _diag(
                    "self_dependency",
                    "DEPENDS_ON self-loop rejected.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="relationship",
                    record_id=src,
                )
            )
            return None, diags

        # Endpoint kind checks
        if rel_type in (
            RelationshipType.DEPENDS_ON,
            RelationshipType.INVOKES,
            RelationshipType.RETRIES,
            RelationshipType.OBSERVED_AFTER,
        ):
            if src not in event_ids or tgt not in event_ids:
                diags.append(
                    _diag(
                        "relationship_endpoint_missing",
                        f"{rel_type.value} endpoints must be known events.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="relationship",
                        source_id=src,
                        target_id=tgt,
                    )
                )
                return None, diags
        elif rel_type == RelationshipType.PRODUCES:
            if src not in event_ids or tgt not in artifact_ids:
                diags.append(
                    _diag(
                        "relationship_endpoint_missing",
                        "PRODUCES requires event → artifact with known ids.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="relationship",
                    )
                )
                return None, diags
        elif rel_type == RelationshipType.CONSUMES:
            if src not in artifact_ids or tgt not in event_ids:
                diags.append(
                    _diag(
                        "relationship_endpoint_missing",
                        "CONSUMES requires artifact → event with known ids.",
                        severity=DiagnosticSeverity.ERROR,
                        disposition=RecordDisposition.REJECTED,
                        record_kind="relationship",
                    )
                )
                return None, diags

        derived = bool(raw.get("derived", False))
        evidence = raw.get("evidence")
        if evidence is not None and not isinstance(evidence, str):
            diags.append(
                _diag(
                    "invalid_evidence",
                    "evidence must be a string when present.",
                    severity=DiagnosticSeverity.ERROR,
                    disposition=RecordDisposition.REJECTED,
                    record_kind="relationship",
                )
            )
            return None, diags

        return (
            RelationshipRecord(
                rel_type=rel_type,
                source_id=src,
                target_id=tgt,
                derived=derived,
                evidence=evidence,
            ),
            diags,
        )

    @staticmethod
    def _dedupe_relationships(rels: list[RelationshipRecord]) -> list[RelationshipRecord]:
        best: dict[tuple[str, str, str], RelationshipRecord] = {}
        for rel in rels:
            key = rel.edge_key()
            prev = best.get(key)
            if prev is None:
                best[key] = rel
            elif prev.derived and not rel.derived:
                best[key] = rel
        # deterministic order
        return [best[k] for k in sorted(best.keys())]
