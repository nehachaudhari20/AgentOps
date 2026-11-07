"""
Migrate legacy AgentOps event JSON into Phase 2.1 records.

Rules:
- Preserve event_id and dependency references when valid.
- Do not invent agent identities or relationship types not present in source.
- Derive artifact records only from present inline input_data/output_data
  (content-addressed); document this derivation in the migration report.
- Convert existing numeric timestamps to ISO 8601 UTC (format conversion).
- Missing status → recorded as absent (validator uses unknown).
- Never overwrite the raw dataset.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from agenttrust.schema.enums import SCHEMA_VERSION, category_for_event_type


def _sha256_text(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _stable_artifact_id(event_id: str, role: str, content_hash: str) -> str:
    # Deterministic ID from event, role, and content hash (not a random UUID).
    return f"legacy:{event_id}:{role}:{content_hash[7:23]}"


def migrate_legacy_records(
    legacy_events: list[dict[str, Any]],
    *,
    trace_id: str = "legacy-raw-events",
) -> dict[str, Any]:
    """
    Transform legacy event dicts into Phase 2.1 event + artifact dicts.

    Returns a migration payload with events, artifacts, report. Does not mutate inputs.
    """
    source = deepcopy(legacy_events)
    events_out: list[dict[str, Any]] = []
    artifacts_out: list[dict[str, Any]] = []
    artifact_index: dict[str, dict[str, Any]] = {}

    omissions: list[dict[str, str]] = []
    mappings: list[dict[str, str]] = []

    for raw in source:
        eid = raw.get("event_id")
        if not isinstance(eid, str) or not eid.strip():
            omissions.append({"reason": "missing_event_id", "detail": str(raw)[:120]})
            continue
        eid = eid.strip()
        etype = raw.get("event_type")
        if not isinstance(etype, str) or not etype.strip():
            omissions.append({"reason": "missing_event_type", "event_id": eid})
            continue
        etype = etype.strip()
        category = category_for_event_type(etype)
        mappings.append(
            {
                "event_id": eid,
                "event_type": etype,
                "category": category.value,
            }
        )

        agent_id = raw.get("agent_id")
        if agent_id is not None and not isinstance(agent_id, str):
            omissions.append({"reason": "invalid_agent_id_type", "event_id": eid})
            agent_id = None

        deps = raw.get("dependencies") or []
        if not isinstance(deps, list):
            omissions.append({"reason": "invalid_dependencies", "event_id": eid})
            deps = []
        dep_ids = [str(d) for d in deps if isinstance(d, str) and d.strip()]

        input_ids: list[str] = []
        output_ids: list[str] = []

        # Derive artifacts only when inline content is present
        for role, field in (("input", "input_data"), ("output", "output_data")):
            content = raw.get(field)
            if content is None:
                omissions.append({"reason": f"missing_{field}", "event_id": eid})
                continue
            if not isinstance(content, str):
                omissions.append({"reason": f"non_string_{field}", "event_id": eid})
                continue
            # Empty string still has observable content "" — hash it but note
            ch = _sha256_text(content)
            aid = _stable_artifact_id(eid, role, ch)
            if aid not in artifact_index:
                artifact_index[aid] = {
                    "artifact_id": aid,
                    "artifact_type": f"legacy_{role}",
                    "content_hash": ch,
                    "schema_version": SCHEMA_VERSION,
                    "storage_uri": None,
                    "metadata": {
                        "source_field": field,
                        "source_event_id": eid,
                        "derivation": "content_addressed_from_inline_legacy_field",
                    },
                }
            if role == "input":
                input_ids.append(aid)
            else:
                output_ids.append(aid)

        ts = raw.get("timestamp")
        ts_start = None
        ts_end = None
        if ts is None:
            omissions.append({"reason": "missing_timestamp", "event_id": eid})
        else:
            # Format conversion of existing numeric/string timestamp — not invention
            ts_start = ts
            ts_end = ts

        # status intentionally omitted → validator records unknown
        if "status" not in raw:
            omissions.append({"reason": "status_absent_in_source", "event_id": eid})

        events_out.append(
            {
                "event_id": eid,
                "trace_id": trace_id,
                "event_type": etype,
                "category": category.value,
                "agent_id": agent_id if isinstance(agent_id, str) else None,
                "input_artifact_ids": input_ids,
                "output_artifact_ids": output_ids,
                "dependency_event_ids": dep_ids,
                "schema_version": SCHEMA_VERSION,
                "ts_start": ts_start,
                "ts_end": ts_end,
                # no invokes / retries / observed_after in legacy source
            }
        )

    artifacts_out = [artifact_index[k] for k in sorted(artifact_index.keys())]

    report = {
        "source_event_count": len(source),
        "migrated_event_count": len(events_out),
        "migrated_artifact_count": len(artifacts_out),
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "category_mappings": mappings,
        "omissions": omissions,
        "limitations": [
            "Legacy records lack explicit status; migrated records omit status so validators mark unknown.",
            "Inline input_data/output_data are converted to content-addressed artifacts; raw text is not stored on graph nodes.",
            "Numeric timestamps are preserved via format conversion to ISO 8601 during validation/parse.",
            "No INVOKES, RETRIES, or OBSERVED_AFTER relationships exist in the legacy source.",
            "Artifact IDs are derived deterministically from event_id, role, and content hash (not present in raw JSON).",
        ],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "trace_id": trace_id,
        "events": events_out,
        "artifacts": artifacts_out,
        "relationships": [],
        "migration_report": report,
    }


def migrate_legacy_events_file(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    trace_id: str = "legacy-raw-events",
) -> dict[str, Any]:
    """
    Read legacy JSON, write processed events under output_dir, return migration payload.

    Never modifies source_path.
    """
    source_path = Path(source_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(source_path, "r", encoding="utf-8") as f:
        legacy = json.load(f)
    if not isinstance(legacy, list):
        raise ValueError("Legacy events file must be a JSON array")

    payload = migrate_legacy_records(legacy, trace_id=trace_id)

    events_path = output_dir / "events_v2.json"
    artifacts_path = output_dir / "artifacts_v2.json"
    report_path = output_dir / "migration_report.json"

    with open(events_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": payload["schema_version"],
                "trace_id": payload["trace_id"],
                "events": payload["events"],
            },
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    with open(artifacts_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": payload["schema_version"],
                "artifacts": payload["artifacts"],
            },
            f,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload["migration_report"], f, indent=2, sort_keys=True)
        f.write("\n")

    payload["output_paths"] = {
        "events": str(events_path),
        "artifacts": str(artifacts_path),
        "report": str(report_path),
    }
    return payload
