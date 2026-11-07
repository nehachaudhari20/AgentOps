# Phase 2.1 — Event Schema and MLPG

This document describes the AgentTrust provenance layer introduced in Phase 2.1.

## Scope

Phase 2.1 provides:

- A versioned event and artifact schema
- Strict validation with diagnostics
- A typed EVENT + ARTIFACT provenance graph (MLPG)
- `ProvenanceTrace` as the stable API
- Attribution projections **P1** and **P2** (no responsibility scores)
- Non-destructive migration from legacy `data/raw_events/events.json`

Phase 2.1 does **not** implement RPA, MFAV, Assurance/CTSM, or PLHC redesigns.

## What the graph represents

The MLPG encodes **observable execution lineage** from recorded events and artifacts.

It does **not**:

- Reconstruct hidden LLM reasoning or internal model cognition
- Prove causal influence
- Establish legal or organizational responsibility
- Claim W3C PROV compliance (the design is PROV-inspired only)

## Event schema (core)

| Field | Notes |
|-------|--------|
| `event_id` | Unique within a trace |
| `trace_id` | Trace identifier |
| `event_type` | Non-empty string |
| `category` | Explicit category; unknown types → `other` |
| `agent_id` | Optional / nullable |
| `status` | Extensible vocabulary; missing → `unknown` (not inferred success) |
| `ts_start` / `ts_end` | Timezone-aware ISO 8601 preferred; `ts_end` ≥ `ts_start` |
| `input_artifact_ids` / `output_artifact_ids` | Deterministic ID lists |
| `dependency_event_ids` | Declared event dependencies |
| `schema_version` | Explicit (currently `2.1.0`) |

Optional explicit fields: `invokes_event_ids`, `retries_event_id`, `observed_after_event_ids`.

Categories: `instruction`, `reasoning`, `retrieval`, `knowledge`, `transformation`, `tool`, `decision`, `other`.

## Artifact schema

| Field | Notes |
|-------|--------|
| `artifact_id` | Stable unique ID within the trace |
| `artifact_type` | Type label |
| `content_hash` | SHA-256 (`sha256:<hex>`) |
| `schema_version` | Explicit |
| `storage_uri` | Optional reference (not content) |
| `metadata` | Optional non-sensitive key/value pairs |

Sensitive raw prompts, documents, credentials, or payment data are **not** stored on graph nodes. A content hash does **not** prove the source content is trustworthy.

## Relationships

Directed edges with explicit `rel_type`:

| Type | Direction | Meaning |
|------|-----------|---------|
| `DEPENDS_ON` | upstream event → dependent event | Declared event dependency |
| `PRODUCES` | event → artifact | Event produced artifact |
| `CONSUMES` | artifact → event | Event consumed artifact |
| `INVOKES` | caller → callee event | Explicit invocation |
| `RETRIES` | retrying event → original | Explicit retry |
| `OBSERVED_AFTER` | earlier → later event | Explicit temporal observation only |

`OBSERVED_AFTER` is **never** auto-generated from sortable timestamps. It is temporal, not causal.

The provenance graph is **unweighted**. Weighting belongs to future attribution algorithms.

Implementation note: the graph is a NetworkX **MultiDiGraph** so multiple relationship types between the same endpoint pair are preserved. Edges are keyed by `rel_type` and have no `weight` attribute.

## Validation and quarantine

| Condition | Behavior |
|-----------|----------|
| Duplicate event IDs | Quarantine duplicate; never overwrite |
| Conflicting artifact IDs | Quarantine |
| Self-dependency | Quarantine |
| Missing dependency parent | Accept event; mark trace **incomplete** |
| Unknown event type | Accept with category `other` |
| Unknown relationship type | Reject |
| Invalid timestamps / order | Reject |
| Missing optional metadata | Accept |
| Missing required fields | Reject |
| DEPENDS_ON cycles | Detect; `suitable_for_dag_attribution=false` |
| Repeated load | `ProvenanceTrace.load_records(..., replace=True)` resets state |

Diagnostics are machine-readable (`code`, `disposition`, `severity`) and human-readable (`message`). Input records are never mutated.

## Trace completeness and cycles

- **Incomplete:** missing parents or artifact references.
- **Cycle:** DEPENDS_ON subgraph not a DAG → unsuitable for DAG-based attribution (future RPA), with diagnostics retained.

## ProvenanceTrace API

```python
from agenttrust import ProvenanceTrace
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
report = trace.load_records(events, artifacts)
g = trace.graph
trace.completeness()
trace.outcome_candidates()  # no responsibility calculation
p1 = trace.project(ProjectionKind.P1_DIRECT)
p2 = trace.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
```

## Projections (for later RPA)

- **P1:** explicit `DEPENDS_ON` only.
- **P2:** P1 plus verified artifact bridges (`PRODUCES` then `CONSUMES`), marked `derived=True`, with evidence path `(producer, artifact, consumer)`. Explicit edges win over bridges (no double-counting). Unverified/missing artifacts create no bridge. The original MLPG is unchanged.

Projections do **not** prove causal responsibility.

## Legacy migration

```bash
python -m agenttrust.migration.cli
```

Or programmatically via `migrate_legacy_events_file`.

- Reads `data/raw/events.json` without modifying it.
- Writes `data/processed/events_v2.json`, `artifacts_v2.json`, `migration_report.json`.
- Derives content-addressed artifacts from present inline `input_data`/`output_data`.
- Does not invent status, INVOKES, RETRIES, or OBSERVED_AFTER.
- Reports omissions and limitations in the migration report.

## Limitations

- Attribution (RPA), accountability vectors (MFAV), assurance scoring, and cryptographic integrity (PLHC) are out of scope for Phase 2.1.
- Unit tests verify correctness of schema/graph/projection/migration behavior; they are not experimental performance claims.
