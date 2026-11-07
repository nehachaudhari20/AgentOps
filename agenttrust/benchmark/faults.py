"""Controlled fault / intervention injection with explicit records (Phase 2.5 hardened)."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class FaultType(str, Enum):
    """
    Planted intervention kinds.

    ``incorrect_tool_output`` = successful tool call with wrong content (not a crash).
    ``tool_call_failure`` = tool/transport failure (status=failure).
    """

    MISSING_DEPENDENCY = "missing_dependency"
    INCORRECT_TOOL_OUTPUT = "incorrect_tool_output"
    TOOL_CALL_FAILURE = "tool_call_failure"
    ARTIFACT_CORRUPTION = "artifact_corruption"
    RETRY_STORM = "retry_storm"
    DELEGATION_FAILURE = "delegation_failure"
    CONFLICTING_OUTPUTS = "conflicting_agent_outputs"
    INCOMPLETE_TRACE = "incomplete_trace"
    MISLEADING_OBSERVATION = "misleading_delayed_observation"


# Sentinel hashes used only as observable planted values (expected hashes live in GT).
SENTINEL_INCORRECT_OUTPUT_HASH = "sha256:" + ("0" * 64)
SENTINEL_CORRUPTION_HASH = "sha256:" + ("f" * 64)


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


def intentional_missing_event_ids(interventions: list[InterventionRecord]) -> set[str]:
    """Event IDs allowed to be absent because an intervention removed them."""
    missing: set[str] = set()
    for iv in interventions:
        if iv.fault_type == FaultType.INCOMPLETE_TRACE.value:
            removed = iv.parameters.get("removed_event_id")
            if removed:
                missing.add(str(removed))
            missing.update(iv.affected_event_ids)
    return missing


def intentional_missing_dependency_refs(interventions: list[InterventionRecord]) -> set[str]:
    """Phantom dependency / callee IDs planted by interventions."""
    refs: set[str] = set()
    for iv in interventions:
        for key in ("phantom_dependency", "phantom_callee"):
            if key in iv.parameters:
                refs.add(str(iv.parameters[key]))
    return refs


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
    Does not embed ``gt_*`` answer labels in algorithm-facing records.
    """
    events = [dict(e) for e in events]
    artifacts = [dict(a) for a in artifacts]
    arts_by_id = {a["artifact_id"]: a for a in artifacts}
    interventions: list[InterventionRecord] = []
    notes: list[str] = []

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
                        "event.dependency_event_ids contains phantom id",
                        "trace completeness.incomplete == True",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                    notes=["Planted missing dependency reference; not a causal claim."],
                )
            )

        elif fault == FaultType.INCORRECT_TOOL_OUTPUT:
            # Successful call with wrong content — distinct from tool_call_failure
            target = _pick_event(events, prefer_categories=("tool",), prefer_types=("tool_call",))
            if target is None:
                target = _pick_event(events, prefer_categories=("transformation", "tool"))
            if target is None:
                continue
            outs = list(target.get("output_artifact_ids") or [])
            if not outs or outs[0] not in arts_by_id:
                notes.append("incorrect_tool_output skipped: no output artifact on tool event")
                continue
            art = arts_by_id[outs[0]]
            expected_hash = art.get("content_hash")
            target["status"] = "success"
            art["content_hash"] = SENTINEL_INCORRECT_OUTPUT_HASH
            # Do not set gt_* or "incorrect" answer labels on algorithm-facing metadata
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[target["event_id"]],
                    affected_artifact_ids=[outs[0]],
                    injection_location=target["event_id"],
                    parameters={
                        "mode": "incorrect_success",
                        "expected_content_hash": expected_hash,
                        "observed_content_hash": SENTINEL_INCORRECT_OUTPUT_HASH,
                        "artifact_id": outs[0],
                    },
                    expected_observable_effects=[
                        "tool/transform event status remains success",
                        "output artifact content_hash differs from GT expected_content_hash",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                    notes=[
                        "Models incorrect successful tool content, not a transport/tool crash."
                    ],
                )
            )

        elif fault == FaultType.TOOL_CALL_FAILURE:
            target = _pick_event(events, prefer_categories=("tool",), prefer_types=("tool_call",))
            if target is None:
                target = _pick_event(events, prefer_categories=("tool", "transformation"))
            if target is None:
                continue
            target["status"] = "failure"
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[target["event_id"]],
                    injection_location=target["event_id"],
                    parameters={"mode": "status_failure", "forced_status": "failure"},
                    expected_observable_effects=["tool/transform event status=failure"],
                    seed=seed,
                    generator_version=generator_version,
                    notes=["Distinct from incorrect_tool_output (wrong successful content)."],
                )
            )

        elif fault == FaultType.ARTIFACT_CORRUPTION:
            if not artifacts:
                continue
            art = artifacts[len(artifacts) // 2]
            expected_hash = art.get("content_hash")
            art["content_hash"] = SENTINEL_CORRUPTION_HASH
            # No algorithm-facing "corrupted" label — evidence lives in GT only
            if isinstance(art.get("metadata"), dict):
                art["metadata"] = {
                    k: v for k, v in art["metadata"].items() if k not in {"corrupted", "gt_corrupted"}
                }
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_artifact_ids=[art["artifact_id"]],
                    injection_location=art["artifact_id"],
                    parameters={
                        "mode": "hash_replacement",
                        "expected_content_hash": expected_hash,
                        "observed_content_hash": SENTINEL_CORRUPTION_HASH,
                        "artifact_id": art["artifact_id"],
                    },
                    expected_observable_effects=[
                        "artifact content_hash equals observed sentinel",
                        "GT expected_content_hash differs from observed",
                    ],
                    seed=seed,
                    generator_version=generator_version,
                    notes=[
                        "Corruption = planted hash mismatch vs independently retained expected hash."
                    ],
                )
            )

        elif fault == FaultType.RETRY_STORM:
            base = _pick_event(events, prefer_categories=("tool",), prefer_types=("tool_call",))
            if base is None:
                continue
            storm: list[str] = []
            parent_id = base["event_id"]
            new_arts: list[dict[str, Any]] = []
            for r in range(3):
                clone = dict(base)
                clone["event_id"] = f"{parent_id}-retry-{r}"
                clone["retries_event_id"] = parent_id if r == 0 else f"{parent_id}-retry-{r - 1}"
                clone["status"] = "failure" if r < 2 else "success"
                clone["dependency_event_ids"] = [parent_id]
                clone["invokes_event_ids"] = []
                clone["ts_start"] = _shift_ts(base.get("ts_start"), 10 + r)
                clone["ts_end"] = _shift_ts(base.get("ts_end"), 11 + r)
                # Unique output artifact per retry (do not share parent outputs)
                aid = f"{clone['event_id']}:out"
                content = f"retry-storm|{parent_id}|{r}|{seed}"
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                new_art = {
                    "artifact_id": aid,
                    "artifact_type": "retry_output",
                    "content_hash": f"sha256:{digest}",
                    "schema_version": "2.1.0",
                    "metadata": {"synthetic": "true", "retry_index": str(r)},
                }
                new_arts.append(new_art)
                arts_by_id[aid] = new_art
                clone["output_artifact_ids"] = [aid]
                clone["input_artifact_ids"] = list(base.get("output_artifact_ids") or [])[:1]
                events.append(clone)
                storm.append(clone["event_id"])
            artifacts.extend(new_arts)
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[parent_id] + storm,
                    affected_artifact_ids=[a["artifact_id"] for a in new_arts],
                    injection_location=parent_id,
                    parameters={"retries_added": 3, "retry_event_ids": storm},
                    expected_observable_effects=[
                        "additional events with retries_event_id chain",
                        "MLPG RETRIES edges present for each retry",
                    ],
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
                # Missing-callee mode
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
                        parameters={
                            "mode": "missing_callee",
                            "phantom_callee": phantom,
                        },
                        expected_observable_effects=["INVOKES points at absent event"],
                        seed=seed,
                        generator_version=generator_version,
                        notes=["Missing callee is distinct from a callee that exists but fails."],
                    )
                )
            else:
                # Callee-failed mode: callee exists and is marked failure
                callees = list(target.get("invokes_event_ids") or [])
                callee_id = callees[0]
                callee = next((e for e in events if e["event_id"] == callee_id), None)
                if callee is None:
                    # Fall back to missing-callee semantics if ID dangling
                    interventions.append(
                        InterventionRecord(
                            intervention_id=iid,
                            scenario_id=scenario_id,
                            fault_type=fault.value,
                            affected_event_ids=[target["event_id"]],
                            injection_location=target["event_id"],
                            parameters={
                                "mode": "missing_callee",
                                "phantom_callee": callee_id,
                            },
                            expected_observable_effects=["INVOKES points at absent event"],
                            seed=seed,
                            generator_version=generator_version,
                        )
                    )
                else:
                    callee["status"] = "failure"
                    interventions.append(
                        InterventionRecord(
                            intervention_id=iid,
                            scenario_id=scenario_id,
                            fault_type=fault.value,
                            affected_event_ids=[target["event_id"], callee_id],
                            injection_location=callee_id,
                            parameters={
                                "mode": "callee_failed",
                                "caller_event_id": target["event_id"],
                                "callee_event_id": callee_id,
                                "forced_status": "failure",
                            },
                            expected_observable_effects=[
                                "callee event status=failure",
                                "INVOKES edge caller→callee retained",
                            ],
                            seed=seed,
                            generator_version=generator_version,
                            notes=["Callee failed; distinct from missing_callee mode."],
                        )
                    )

        elif fault == FaultType.CONFLICTING_OUTPUTS:
            candidates = [
                e
                for e in events
                if e.get("category") in ("reasoning", "tool")
                or e.get("event_type") in ("reasoning", "tool_call")
            ]
            if len(candidates) < 2:
                continue
            a, b = candidates[0], candidates[1]
            affected_arts: list[str] = []
            for ev, label in ((a, "approve"), (b, "reject")):
                outs = list(ev.get("output_artifact_ids") or [])
                if outs and outs[0] in arts_by_id:
                    meta = arts_by_id[outs[0]].get("metadata") or {}
                    if not isinstance(meta, dict):
                        meta = {}
                    meta = dict(meta)
                    meta["conflict_label"] = label  # planted observable effect, not gt_* answer
                    arts_by_id[outs[0]]["metadata"] = meta
                    affected_arts.append(outs[0])
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[a["event_id"], b["event_id"]],
                    affected_artifact_ids=affected_arts,
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
            removable = [
                e
                for e in events
                if e.get("category") != "decision" and e.get("event_type") != "action"
            ]
            if len(removable) < 3:
                continue
            victim = removable[len(removable) // 2]
            victim_id = victim["event_id"]
            dependents = [
                e["event_id"]
                for e in events
                if victim_id in (e.get("dependency_event_ids") or [])
            ]
            events = [e for e in events if e["event_id"] != victim_id]
            interventions.append(
                InterventionRecord(
                    intervention_id=iid,
                    scenario_id=scenario_id,
                    fault_type=fault.value,
                    affected_event_ids=[victim_id],
                    injection_location=victim_id,
                    parameters={
                        "removed_event_id": victim_id,
                        "dependent_event_ids": dependents,
                    },
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
            if len(events) < 4:
                continue
            early = events[1]
            late = events[-2]
            # Ensure we do not also add DEPENDS_ON
            deps = list(late.get("dependency_event_ids") or [])
            if early["event_id"] in deps:
                deps = [d for d in deps if d != early["event_id"]]
                late["dependency_event_ids"] = deps
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
                    parameters={
                        "observed_after": early["event_id"],
                        "observer_event_id": late["event_id"],
                    },
                    expected_observable_effects=[
                        "OBSERVED_AFTER edge present without DEPENDS_ON",
                        "must not appear in P1/P2 attribution projections",
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
    try:
        from datetime import datetime, timedelta, timezone

        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text).astimezone(timezone.utc)
        dt2 = dt + timedelta(seconds=seconds)
        return dt2.isoformat().replace("+00:00", "Z")
    except Exception:
        return value
