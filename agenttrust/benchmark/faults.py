"""Controlled fault / intervention injection with explicit records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class FaultType(str, Enum):
    MISSING_DEPENDENCY = "missing_dependency"
    INCORRECT_TOOL_OUTPUT = "incorrect_tool_output"
    ARTIFACT_CORRUPTION = "artifact_corruption"
    RETRY_STORM = "retry_storm"
    DELEGATION_FAILURE = "delegation_failure"
    CONFLICTING_OUTPUTS = "conflicting_agent_outputs"
    INCOMPLETE_TRACE = "incomplete_trace"
    MISLEADING_OBSERVATION = "misleading_delayed_observation"


@dataclass
class InterventionRecord:
    """
    Planted intervention ground truth — separate from algorithm input events.

    Distinguishes the planted fault from merely dependent downstream events.
    Graph reachability is NOT causal ground truth.
    """

    intervention_id: str
    scenario_id: str
    fault_type: str
    affected_event_ids: list[str] = field(default_factory=list)
    affected_artifact_ids: list[str] = field(default_factory=list)
    injection_location: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_observable_effects: list[str] = field(default_factory=list)
    seed: int = 0
    generator_version: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InterventionRecord":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def apply_interventions(
    *,
    events: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    fault_types: list[FaultType | str],
    scenario_id: str,
    seed: int,
    generator_version: str,
    incomplete: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[InterventionRecord], list[str]]:
    """
    Apply requested interventions to copies of events/artifacts.

    Returns mutated events, artifacts, intervention records, and trace notes.
    Does not claim causal responsibility for outcomes.
    """
    events = [dict(e) for e in events]
    artifacts = [dict(a) for a in artifacts]
    arts_by_id = {a["artifact_id"]: a for a in artifacts}
    interventions: list[InterventionRecord] = []
    notes: list[str] = []

    # Normalize + dedupe while preserving order
    requested: list[FaultType] = []
    seen: set[str] = set()
    for ft in fault_types:
        f = FaultType(ft) if not isinstance(ft, FaultType) else ft
        if f.value not in seen:
            seen.add(f.value)
            requested.append(f)
    if incomplete and FaultType.INCOMPLETE_TRACE not in requested:
        requested.append(FaultType.INCOMPLETE_TRACE)

    def _iid(kind: str, n: int) -> str:
        return f"iv-{kind}-{seed}-{n:02d}"

    counter = 0
    for fault in requested:
        counter += 1
        iid = _iid(fault.value, counter)

        if fault == FaultType.MISSING_DEPENDENCY:
            # Point a mid-chain event at a never-emitted parent id
            target = _pick_event(events, prefer_categories=("reasoning", "retrieval", "tool"))
            if target is None:
                continue
            phantom = f"missing-parent-{seed}"
            deps = list(target.get("dependency_event_ids") or [])
            deps.append(phantom)
            target["dependency_event_ids"] = deps
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[target["event_id"]],
                    injection_location=target["event_id"],
                    parameters={"phantom_dependency": phantom},
                    expected_observable_effects=[
                        "validation reports missing dependency parent",
                        "trace completeness.incomplete == True",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                    notes=["Planted missing dependency reference; not a causal claim."],
                )
            )

        elif fault == FaultType.INCORRECT_TOOL_OUTPUT:
            target = _pick_event(events, prefer_categories=("tool",), prefer_types=("tool_call",))
            if target is None:
                target = _pick_event(events, prefer_categories=("transformation", "tool"))
            if target is None:
                continue
            target["status"] = "failure"
            # Corrupt linked output artifact content hash if present
            outs = list(target.get("output_artifact_ids") or [])
            affected_arts: list[str] = []
            if outs and outs[0] in arts_by_id:
                art = arts_by_id[outs[0]]
                art["content_hash"] = "sha256:" + ("0" * 64)
                art.setdefault("metadata", {})
                if isinstance(art["metadata"], dict):
                    art["metadata"]["synthetic_incorrect_output"] = "true"
                affected_arts.append(outs[0])
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[target["event_id"]],
                    affected_artifact_ids=affected_arts,
                    injection_location=target["event_id"],
                    parameters={"forced_status": "failure"},
                    expected_observable_effects=[
                        "tool/transform event status=failure",
                        "optional artifact hash overwritten to sentinel",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                )
            )

        elif fault == FaultType.ARTIFACT_CORRUPTION:
            if not artifacts:
                continue
            art = artifacts[len(artifacts) // 2]
            art["content_hash"] = "sha256:" + ("f" * 64)
            meta = art.get("metadata") or {}
            if not isinstance(meta, dict):
                meta = {}
            meta["corrupted"] = "true"
            art["metadata"] = meta
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_artifact_ids=[art["artifact_id"]],
                    injection_location=art["artifact_id"],
                    parameters={"sentinel_hash": art["content_hash"]},
                    expected_observable_effects=["artifact content_hash replaced with sentinel"],
                    seed=seed,
                    generator_version=generator_version,
                )
            )

        elif fault == FaultType.RETRY_STORM:
            # Clone a tool event as multiple retries of the same parent
            base = _pick_event(events, prefer_categories=("tool",), prefer_types=("tool_call",))
            if base is None:
                continue
            storm: list[str] = []
            parent_id = base["event_id"]
            for r in range(3):
                clone = dict(base)
                clone["event_id"] = f"{parent_id}-retry-{r}"
                clone["retries_event_id"] = parent_id if r == 0 else f"{parent_id}-retry-{r-1}"
                clone["status"] = "failure" if r < 2 else "success"
                # shift timestamps deterministically
                clone["ts_start"] = _shift_ts(base.get("ts_start"), 10 + r)
                clone["ts_end"] = _shift_ts(base.get("ts_end"), 11 + r)
                events.append(clone)
                storm.append(clone["event_id"])
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[parent_id] + storm,
                    injection_location=parent_id,
                    parameters={"retries_added": 3},
                    expected_observable_effects=["additional RETRIES-linked events present"],
                    seed=seed,
                    generator_version=generator_version,
                )
            )

        elif fault == FaultType.DELEGATION_FAILURE:
            target = None
            for e in events:
                if e.get("invokes_event_ids"):
                    target = e
                    break
            if target is None:
                # Fabricate invoke to a missing callee
                target = _pick_event(events, prefer_categories=("reasoning",))
                if target is None:
                    continue
                phantom = f"missing-callee-{seed}"
                target["invokes_event_ids"] = [phantom]
                interventions.append(
                    InterventionRecord(
                        intervention_id=iid,
                        scenario_id=scenario_id,
                        fault_type=fault.value,
                        affected_event_ids=[target["event_id"]],
                        injection_location=target["event_id"],
                        parameters={"phantom_callee": phantom},
                        expected_observable_effects=["INVOKES points at absent event"],
                        seed=seed,
                        generator_version=generator_version,
                    )
                )
            else:
                target["status"] = "failure"
                interventions.append(
                    InterventionRecord(
                        intervention_id=iid,
                        scenario_id=scenario_id,
                        fault_type=fault.value,
                        affected_event_ids=[target["event_id"]] + list(target.get("invokes_event_ids") or []),
                        injection_location=target["event_id"],
                        parameters={"forced_status": "failure"},
                        expected_observable_effects=["invoking event marked failure"],
                        seed=seed,
                        generator_version=generator_version,
                    )
                )

        elif fault == FaultType.CONFLICTING_OUTPUTS:
            # Two sibling events produce conflicting decision-like artifacts
            candidates = [e for e in events if e.get("category") in ("reasoning", "tool") or e.get("event_type") in ("reasoning", "tool_call")]
            if len(candidates) < 2:
                continue
            a, b = candidates[0], candidates[1]
            for ev, label in ((a, "approve"), (b, "reject")):
                outs = list(ev.get("output_artifact_ids") or [])
                if outs and outs[0] in arts_by_id:
                    arts_by_id[outs[0]].setdefault("metadata", {})
                    if isinstance(arts_by_id[outs[0]]["metadata"], dict):
                        arts_by_id[outs[0]]["metadata"]["conflict_label"] = label
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[a["event_id"], b["event_id"]],
                    affected_artifact_ids=[
                        *(a.get("output_artifact_ids") or [])[:1],
                        *(b.get("output_artifact_ids") or [])[:1],
                    ],
                    injection_location=a["event_id"],
                    parameters={"labels": ["approve", "reject"]},
                    expected_observable_effects=[
                        "two artifacts tagged with conflicting conflict_label metadata"
                    ],
                    seed=seed,
                    generator_version=generator_version,
                    notes=["Conflict is synthetic metadata only; not legal disagreement."],
                )
            )

        elif fault == FaultType.INCOMPLETE_TRACE:
            # Drop a non-outcome mid event from the emitted set (keep deps pointing to it)
            removable = [
                e
                for e in events
                if e.get("category") != "decision" and e.get("event_type") != "action"
            ]
            if len(removable) < 3:
                continue
            victim = removable[len(removable) // 2]
            victim_id = victim["event_id"]
            events = [e for e in events if e["event_id"] != victim_id]
            # Leave dangling dependency references in remaining events
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[victim_id],
                    injection_location=victim_id,
                    parameters={"removed_event_id": victim_id},
                    expected_observable_effects=[
                        "event absent from emitted trace",
                        "dependents may reference missing parent",
                        "completeness.incomplete == True",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                    notes=["Intentionally incomplete; validator must not silently repair."],
                )
            )
            notes.append(f"incomplete_trace removed {victim_id}")

        elif fault == FaultType.MISLEADING_OBSERVATION:
            # Add OBSERVED_AFTER from a late event to an early unrelated event without DEPENDS_ON
            if len(events) < 4:
                continue
            early = events[1]
            late = events[-2]
            obs = list(late.get("observed_after_event_ids") or [])
            if early["event_id"] not in obs:
                obs.append(early["event_id"])
            late["observed_after_event_ids"] = obs
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[late["event_id"], early["event_id"]],
                    injection_location=late["event_id"],
                    parameters={"observed_after": early["event_id"]},
                    expected_observable_effects=[
                        "OBSERVED_AFTER edge present without DEPENDS_ON",
                        "must not be treated as causal dependence",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                )
            )

    return events, artifacts, interventions, notes


def _pick_event(
    events: list[dict[str, Any]],
    *,
    prefer_categories: tuple[str, ...] = (),
    prefer_types: tuple[str, ...] = (),
) -> Optional[dict[str, Any]]:
    for e in events:
        if prefer_types and e.get("event_type") in prefer_types:
            return e
    for e in events:
        if prefer_categories and e.get("category") in prefer_categories:
            return e
    return events[len(events) // 2] if events else None


def _shift_ts(value: Any, seconds: int) -> Optional[str]:
    if not isinstance(value, str) or "T" not in value:
        return value
    # Deterministic string tweak for HH:MM:SS region when possible
    # Prefer parsing-free adjustment: append offset marker via second field if ISO Z
    try:
        from datetime import datetime, timedelta, timezone

        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text).astimezone(timezone.utc)
        dt2 = dt + timedelta(seconds=seconds)
        return dt2.isoformat().replace("+00:00", "Z")
    except Exception:
        return value
