"""
Deterministic synthetic multi-agent benchmark generator.

Emits native Phase 2.1 event/artifact dicts loadable by ProvenanceTrace.
Ground truth is kept separate from algorithm inputs.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

from agenttrust.benchmark.faults import FaultType, InterventionRecord, apply_interventions
from agenttrust.benchmark.ground_truth import (
    BenchmarkGroundTruth,
    StructuralGroundTruth,
    TraceQualityGroundTruth,
    build_lineage_from_events,
)
from agenttrust.benchmark.manifest import (
    GENERATOR_VERSION,
    SCALE_SPECS,
    BenchmarkConfig,
    ScenarioId,
    TopologyId,
    TraceManifest,
)
from agenttrust.benchmark.scenarios import assign_agents, get_scenario, role_for_agent
from agenttrust.benchmark.topologies import StepKind, WorkflowBlueprint, build_topology

BASE_TIMESTAMP = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


@dataclass
class GeneratedTrace:
    """One complete generated package (inputs + separate ground truth)."""

    events: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    manifest: TraceManifest
    ground_truth: BenchmarkGroundTruth
    config: BenchmarkConfig

    def algorithm_inputs(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Events/artifacts only — no ground-truth labels."""
        return self.events, self.artifacts


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _kind_to_category(kind: StepKind) -> str:
    return {
        StepKind.PROMPT: "instruction",
        StepKind.REASONING: "reasoning",
        StepKind.RETRIEVAL: "retrieval",
        StepKind.DOCUMENT: "knowledge",
        StepKind.EMBEDDING: "transformation",
        StepKind.TOOL: "tool",
        StepKind.ACTION: "decision",
        StepKind.INVOKE: "reasoning",
    }[kind]


def _kind_to_event_type(kind: StepKind) -> str:
    return {
        StepKind.PROMPT: "prompt",
        StepKind.REASONING: "reasoning",
        StepKind.RETRIEVAL: "retrieval",
        StepKind.DOCUMENT: "document",
        StepKind.EMBEDDING: "embedding",
        StepKind.TOOL: "tool_call",
        StepKind.ACTION: "action",
        StepKind.INVOKE: "reasoning",
    }[kind]


class BenchmarkGenerator:
    """Configurable, seed-reproducible synthetic trace generator."""

    def __init__(self, generator_version: str = GENERATOR_VERSION) -> None:
        self.generator_version = generator_version

    def generate(self, config: BenchmarkConfig) -> GeneratedTrace:
        if config.generator_version != self.generator_version:
            # Allow reading older configs but stamp with active generator
            pass
        rng = random.Random(int(config.seed))
        # Touch rng so future stochastic pads remain stable if added
        _ = rng.random()

        template = get_scenario(config.scenario_id)
        n_agents = SCALE_SPECS[config.scale_tier]["agents"]
        target_events = SCALE_SPECS[config.scale_tier]["target_events"]
        agents = assign_agents(template, n_agents)
        trace_id = config.make_trace_id()

        blueprint = build_topology(
            config.topology_id,
            agents,
            template,
            target_events,
        )
        events, artifacts, pre_gt_notes = self._materialize(
            blueprint=blueprint,
            agents=agents,
            template_scenario=config.scenario_id.value,
            template=template,
            trace_id=trace_id,
            seed=config.seed,
        )
        expected_count = len(events)

        # Capture pre-fault structural ids for quality GT
        pre_event_ids = {e["event_id"] for e in events}

        fault_types = [FaultType(f) for f in config.fault_types]
        events, artifacts, interventions, fault_notes = apply_interventions(
            events=events,
            artifacts=artifacts,
            fault_types=fault_types,
            scenario_id=config.scenario_id.value,
            seed=config.seed,
            generator_version=self.generator_version,
            incomplete=config.incomplete,
        )

        post_event_ids = {e["event_id"] for e in events}
        missing_events = sorted(pre_event_ids - post_event_ids)

        outcomes = [
            e["event_id"]
            for e in events
            if e.get("category") == "decision" or e.get("event_type") == "action"
        ]
        if not outcomes and events:
            # Ensure at least one outcome marker for complete traces
            events[-1]["category"] = "decision"
            events[-1]["event_type"] = "action"
            outcomes = [events[-1]["event_id"]]

        lineage = build_lineage_from_events(events)
        model_ids = sorted({e["model_id"] for e in events if e.get("model_id")})
        tool_ids = sorted({e["tool_id"] for e in events if e.get("tool_id")})
        categories = {e["event_id"]: e.get("category", "") for e in events}

        missing_dep_refs: list[str] = []
        known = {e["event_id"] for e in events}
        for e in events:
            for d in e.get("dependency_event_ids") or []:
                if d not in known:
                    missing_dep_refs.append(d)

        corrupted: list[str] = []
        for iv in interventions:
            if iv.fault_type in (
                FaultType.ARTIFACT_CORRUPTION.value,
                FaultType.INCORRECT_TOOL_OUTPUT.value,
            ):
                if iv.parameters.get("artifact_id"):
                    corrupted.append(str(iv.parameters["artifact_id"]))
                else:
                    corrupted.extend(str(a) for a in iv.affected_artifact_ids)
        corrupted = sorted(set(corrupted))

        quality = TraceQualityGroundTruth(
            intentionally_incomplete=bool(config.incomplete or missing_events or missing_dep_refs),
            missing_event_ids=missing_events,
            missing_dependency_refs=sorted(set(missing_dep_refs)),
            corrupted_artifact_ids=corrupted,
            incomplete_observation_notes=fault_notes + pre_gt_notes,
        )

        structural = StructuralGroundTruth(
            agent_ids=list(agents),
            model_ids=model_ids,
            tool_ids=tool_ids,
            event_categories=categories,
            topology_id=config.topology_id.value,
            scenario_id=config.scenario_id.value,
            outcome_event_ids=outcomes,
            scale_tier=config.scale_tier.value,
        )

        gt = BenchmarkGroundTruth(
            trace_id=trace_id,
            generator_version=self.generator_version,
            seed=config.seed,
            lineage=lineage,
            interventions=interventions,
            structural=structural,
            quality=quality,
        )

        manifest = TraceManifest(
            trace_id=trace_id,
            scenario_id=config.scenario_id.value,
            topology_id=config.topology_id.value,
            scale_tier=config.scale_tier.value,
            seed=config.seed,
            generator_version=self.generator_version,
            config_fingerprint=config.fingerprint(),
            expected_event_count=expected_count,
            actual_event_count=len(events),
            agent_count=len(agents),
            artifact_count=len(artifacts),
            intervention_count=len(interventions),
            outcome_event_ids=outcomes,
            incomplete=quality.intentionally_incomplete,
            fault_types=sorted({i.fault_type for i in interventions}),
            agent_ids=list(agents),
            notes=pre_gt_notes + fault_notes + blueprint.notes,
        )

        return GeneratedTrace(
            events=events,
            artifacts=artifacts,
            manifest=manifest,
            ground_truth=gt,
            config=config,
        )

    def _materialize(
        self,
        *,
        blueprint: WorkflowBlueprint,
        agents: Sequence[str],
        template_scenario: str,
        template,
        trace_id: str,
        seed: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        local_to_event: dict[str, str] = {}
        local_to_artifact: dict[str, str] = {}
        events: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        notes: list[str] = list(blueprint.notes)

        for idx, step in enumerate(blueprint.steps):
            eid = f"{trace_id}:e{idx:04d}"
            local_to_event[step.local_id] = eid
            agent_id = agents[step.agent_index % len(agents)]
            role = role_for_agent(template, agent_id)
            ts0 = BASE_TIMESTAMP + timedelta(seconds=idx * 5)
            ts1 = ts0 + timedelta(seconds=2)

            dep_ids = tuple(local_to_event[d] for d in step.dep_local_ids if d in local_to_event)
            invoke_ids = tuple(local_to_event[d] for d in step.invoke_local_ids if d in local_to_event)
            # invoke targets may be created later — second pass below
            input_arts = [
                local_to_artifact[c] for c in step.consume_from if c in local_to_artifact
            ]

            out_arts: list[str] = []
            if step.produce_artifact:
                aid = f"{trace_id}:a{idx:04d}"
                content = f"{template_scenario}|{step.kind.value}|{idx}|seed={seed}"
                atype = template.artifact_types[idx % len(template.artifact_types)]
                art: dict[str, Any] = {
                    "artifact_id": aid,
                    "artifact_type": atype,
                    "content_hash": f"sha256:{_sha256_hex(content)}",
                    "schema_version": "2.1.0",
                    "metadata": {"synthetic": "true", "step": step.local_id},
                }
                artifacts.append(art)
                local_to_artifact[step.local_id] = aid
                out_arts = [aid]

            category = _kind_to_category(step.kind)
            event_type = _kind_to_event_type(step.kind)
            rec: dict[str, Any] = {
                "event_id": eid,
                "trace_id": trace_id,
                "event_type": event_type,
                "category": category,
                "agent_id": agent_id,
                "status": "success",
                "ts_start": _iso(ts0),
                "ts_end": _iso(ts1),
                "dependency_event_ids": list(dep_ids),
                "input_artifact_ids": list(input_arts),
                "output_artifact_ids": out_arts,
                "schema_version": "2.1.0",
                "invokes_event_ids": list(invoke_ids),
                "observed_after_event_ids": [],
            }
            if step.retry_of and step.retry_of in local_to_event:
                rec["retries_event_id"] = local_to_event[step.retry_of]
            if step.tool_name:
                rec["tool_id"] = step.tool_name
            if step.use_model and role.default_model_id:
                rec["model_id"] = role.default_model_id
            if step.memory_tag:
                rec["metadata"] = {"subtype": "memory"}
            if step.is_outcome:
                rec["category"] = "decision"
                rec["event_type"] = "action"
            events.append(rec)

        # Second pass: resolve invoke targets declared before callees existed
        for step in blueprint.steps:
            if not step.invoke_local_ids:
                continue
            eid = local_to_event[step.local_id]
            for ev in events:
                if ev["event_id"] == eid:
                    ev["invokes_event_ids"] = [
                        local_to_event[x] for x in step.invoke_local_ids if x in local_to_event
                    ]
                    break

        # Stable ordering
        events.sort(key=lambda e: e["event_id"])
        artifacts.sort(key=lambda a: a["artifact_id"])
        return events, artifacts, notes

    def write_trace(
        self,
        trace: GeneratedTrace,
        *,
        events_dir: Path,
        ground_truth_dir: Path,
        manifests_dir: Path,
    ) -> dict[str, Path]:
        """
        Persist algorithm inputs and ground truth in separate directories.

        Layout:
          events_dir/<trace_id>/events.json
          events_dir/<trace_id>/artifacts.json
          ground_truth_dir/<trace_id>.json
          manifests_dir/<trace_id>.json
        """
        events_dir = Path(events_dir)
        ground_truth_dir = Path(ground_truth_dir)
        manifests_dir = Path(manifests_dir)
        tid = trace.manifest.trace_id
        tdir = events_dir / tid
        tdir.mkdir(parents=True, exist_ok=True)
        ground_truth_dir.mkdir(parents=True, exist_ok=True)
        manifests_dir.mkdir(parents=True, exist_ok=True)

        events_path = tdir / "events.json"
        arts_path = tdir / "artifacts.json"
        gt_path = ground_truth_dir / f"{tid}.json"
        man_path = manifests_dir / f"{tid}.json"

        events_path.write_text(
            json.dumps({"events": trace.events}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        arts_path.write_text(
            json.dumps({"artifacts": trace.artifacts}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        gt_path.write_text(
            json.dumps(trace.ground_truth.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        man_path.write_text(
            json.dumps(trace.manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "events": events_path,
            "artifacts": arts_path,
            "ground_truth": gt_path,
            "manifest": man_path,
        }


def pilot_configs(
    *,
    seeds: Sequence[int] = (1, 2),
    include_fault_samples: bool = True,
) -> list[BenchmarkConfig]:
    """
    Small pilot matrix: all topologies × all scale tiers × two seeds,
    rotating scenarios; plus a limited fault/incomplete sample set.
    """
    scenarios = list(ScenarioId)
    topologies = list(TopologyId)
    tiers = list(SCALE_SPECS.keys())
    configs: list[BenchmarkConfig] = []

    for ti, topology in enumerate(topologies):
        for scale in tiers:
            for seed in seeds:
                scenario = scenarios[(ti + seed) % len(scenarios)]
                configs.append(
                    BenchmarkConfig(
                        scenario_id=scenario,
                        topology_id=topology,
                        scale_tier=scale,
                        seed=int(seed),
                        fault_types=(),
                        incomplete=False,
                    )
                )

    if include_fault_samples:
        # One S1 fault sample per fault type on sequential + mixed
        fault_list = list(FaultType)
        for i, fault in enumerate(fault_list):
            topo = TopologyId.SEQUENTIAL if i % 2 == 0 else TopologyId.MIXED
            configs.append(
                BenchmarkConfig(
                    scenario_id=scenarios[i % len(scenarios)],
                    topology_id=topo,
                    scale_tier=list(SCALE_SPECS.keys())[0],
                    seed=100 + i,
                    fault_types=(fault.value,),
                    incomplete=(fault == FaultType.INCOMPLETE_TRACE),
                )
            )
    return configs
