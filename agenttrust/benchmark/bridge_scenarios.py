"""
Artifact-mediated lineage scenarios (Phase 2.13).

These scenarios intentionally omit explicit DEPENDS_ON where lineage is carried
only by PRODUCES→CONSUMES so P1 and P2 projections differ.

Versioned separately from the frozen Phase 2.9 experimental corpus.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.provenance_trace import ProvenanceTrace

BRIDGE_CORPUS_VERSION = "experimental_2_13_bridges.v1"
BRIDGE_SEED = 213_100


def _sha(s: str) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()


def _art(aid: str, content: str) -> dict[str, Any]:
    return {
        "artifact_id": aid,
        "artifact_type": "document",
        "content_hash": _sha(content),
        "schema_version": "2.1.0",
        "metadata": {"synthetic": "true"},
    }


def _ev(
    eid: str,
    *,
    agent: str,
    deps: list[str] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    outcome: bool = False,
    ts: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": eid,
        "trace_id": "bridge",
        "event_type": "action" if outcome else "reasoning",
        "category": "decision" if outcome else "reasoning",
        "agent_id": agent,
        "status": "success",
        "ts_start": f"2020-01-01T00:00:{ts:02d}+00:00",
        "ts_end": f"2020-01-01T00:00:{ts + 1:02d}+00:00",
        "dependency_event_ids": list(deps or []),
        "input_artifact_ids": list(inputs or []),
        "output_artifact_ids": list(outputs or []),
        "schema_version": "2.1.0",
        "invokes_event_ids": [],
        "observed_after_event_ids": [],
    }


@dataclass
class BridgeScenario:
    scenario_id: str
    description: str
    events: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    expect_p1_p2_differ: bool
    expect_bridge_edges: int
    tags: list[str]


def scenario_multi_stage_chain() -> BridgeScenario:
    """A→art1→B→art2→C→art3→D outcome; no explicit DEPENDS_ON."""
    arts = [
        _art("a1", "stage1"),
        _art("a2", "stage2"),
        _art("a3", "stage3"),
    ]
    events = [
        _ev("eA", agent="agent_A", outputs=["a1"], ts=0),
        _ev("eB", agent="agent_B", inputs=["a1"], outputs=["a2"], ts=2),
        _ev("eC", agent="agent_C", inputs=["a2"], outputs=["a3"], ts=4),
        _ev("eD", agent="agent_D", inputs=["a3"], outcome=True, ts=6),
    ]
    return BridgeScenario(
        scenario_id="multi_stage_artifact_chain",
        description="Four-agent artifact chain without DEPENDS_ON",
        events=events,
        artifacts=arts,
        expect_p1_p2_differ=True,
        expect_bridge_edges=3,
        tags=["chain", "multi_stage"],
    )


def scenario_shared_fanout_fanin() -> BridgeScenario:
    """Shared artifact fan-out then fan-in merge via artifacts only."""
    arts = [_art("shared", "shared-doc"), _art("m1", "m1"), _art("m2", "m2"), _art("out", "out")]
    events = [
        _ev("eProd", agent="producer", outputs=["shared"], ts=0),
        _ev("eC1", agent="consumer_1", inputs=["shared"], outputs=["m1"], ts=2),
        _ev("eC2", agent="consumer_2", inputs=["shared"], outputs=["m2"], ts=4),
        _ev(
            "eMerge",
            agent="merger",
            inputs=["m1", "m2"],
            outputs=["out"],
            outcome=True,
            ts=6,
        ),
    ]
    return BridgeScenario(
        scenario_id="shared_fanout_fanin",
        description="Shared artifact reused by two consumers then merged",
        events=events,
        artifacts=arts,
        expect_p1_p2_differ=True,
        expect_bridge_edges=4,  # prod→c1, prod→c2, c1→merge, c2→merge
        tags=["shared", "fanout", "fanin", "reuse"],
    )


def scenario_delegated_artifact_exchange() -> BridgeScenario:
    """Coordinator produces brief; delegate consumes and returns result artifact."""
    arts = [_art("brief", "brief"), _art("result", "result")]
    events = [
        _ev("eCoord", agent="coordinator", outputs=["brief"], ts=0),
        _ev("eDel", agent="delegate", inputs=["brief"], outputs=["result"], ts=2),
        _ev("eFinal", agent="coordinator", inputs=["result"], outcome=True, ts=4),
    ]
    return BridgeScenario(
        scenario_id="delegated_artifact_exchange",
        description="Delegated workflow with explicit artifact exchange only",
        events=events,
        artifacts=arts,
        expect_p1_p2_differ=True,
        expect_bridge_edges=2,
        tags=["delegated", "exchange"],
    )


def scenario_with_explicit_depends_negative() -> BridgeScenario:
    """Negative control: consume + DEPENDS_ON → bridge deduped; P1≈P2 edges."""
    arts = [_art("ax", "x")]
    events = [
        _ev("e1", agent="a1", outputs=["ax"], ts=0),
        _ev("e2", agent="a2", deps=["e1"], inputs=["ax"], outcome=True, ts=2),
    ]
    return BridgeScenario(
        scenario_id="explicit_depends_negative",
        description="Artifact consume with DEPENDS_ON; bridge should not add edge",
        events=events,
        artifacts=arts,
        expect_p1_p2_differ=False,
        expect_bridge_edges=0,
        tags=["negative", "dedupe"],
    )


def scenario_missing_artifact_ref() -> BridgeScenario:
    """Consumer references missing artifact — incomplete; no verified bridge."""
    events = [
        _ev("e1", agent="a1", outputs=["missing_art"], ts=0),
        _ev("e2", agent="a2", inputs=["missing_art"], outcome=True, ts=2),
    ]
    return BridgeScenario(
        scenario_id="missing_artifact_ref",
        description="Missing artifact record; no verified bridge",
        events=events,
        artifacts=[],
        expect_p1_p2_differ=False,
        expect_bridge_edges=0,
        tags=["negative", "missing"],
    )


def scenario_corrupted_artifact_evidence() -> BridgeScenario:
    """Artifact present but empty content_hash → excluded from verified bridges."""
    art = {
        "artifact_id": "bad",
        "artifact_type": "document",
        "content_hash": "",
        "schema_version": "2.1.0",
        "metadata": {"synthetic": "true", "corrupted": "true"},
    }
    events = [
        _ev("e1", agent="a1", outputs=["bad"], ts=0),
        _ev("e2", agent="a2", inputs=["bad"], outcome=True, ts=2),
    ]
    return BridgeScenario(
        scenario_id="corrupted_artifact_evidence",
        description="Empty content_hash blocks verified artifact bridge",
        events=events,
        artifacts=[art],
        expect_p1_p2_differ=False,
        expect_bridge_edges=0,
        tags=["negative", "corrupted"],
    )


ALL_SCENARIO_BUILDERS: list[Callable[[], BridgeScenario]] = [
    scenario_multi_stage_chain,
    scenario_shared_fanout_fanin,
    scenario_delegated_artifact_exchange,
    scenario_with_explicit_depends_negative,
    scenario_missing_artifact_ref,
    scenario_corrupted_artifact_evidence,
]


def build_trace(scenario: BridgeScenario) -> ProvenanceTrace:
    pt = ProvenanceTrace()
    events = []
    for e in scenario.events:
        ee = dict(e)
        ee["trace_id"] = scenario.scenario_id
        events.append(ee)
    pt.load_records(events, list(scenario.artifacts), default_trace_id=scenario.scenario_id)
    return pt


def analyze_projection_diff(scenario: BridgeScenario) -> dict[str, Any]:
    pt = build_trace(scenario)
    p1 = pt.project(ProjectionKind.P1_DIRECT)
    p2 = pt.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    bridges = [e for e in p2.edges if e.origin == "ARTIFACT_BRIDGE"]
    p1_edges = {(e.source_event_id, e.target_event_id) for e in p1.edges}
    p2_edges = {(e.source_event_id, e.target_event_id) for e in p2.edges}
    differ = p1_edges != p2_edges
    return {
        "scenario_id": scenario.scenario_id,
        "n_p1_edges": len(p1_edges),
        "n_p2_edges": len(p2_edges),
        "n_artifact_bridge_edges": len(bridges),
        "p1_p2_differ": differ,
        "expect_p1_p2_differ": scenario.expect_p1_p2_differ,
        "expect_bridge_edges": scenario.expect_bridge_edges,
        "match_expectation": (
            differ == scenario.expect_p1_p2_differ
            and len(bridges) == scenario.expect_bridge_edges
        ),
        "bridge_edge_list": [
            {"source": e.source_event_id, "target": e.target_event_id, "path": list(e.evidence_path)}
            for e in bridges
        ],
        "tags": scenario.tags,
        "incomplete": pt.completeness().incomplete,
    }


def generate_bridge_corpus(root: Path) -> dict[str, Any]:
    """Write versioned bridge corpus + projection coverage report."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    traces_dir = root / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)

    catalog = []
    analyses = []
    for builder in ALL_SCENARIO_BUILDERS:
        sc = builder()
        tdir = traces_dir / sc.scenario_id
        tdir.mkdir(parents=True, exist_ok=True)
        events = []
        for e in sc.events:
            ee = dict(e)
            ee["trace_id"] = sc.scenario_id
            events.append(ee)
        (tdir / "events.json").write_text(
            json.dumps({"events": events}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (tdir / "artifacts.json").write_text(
            json.dumps({"artifacts": sc.artifacts}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        analysis = analyze_projection_diff(sc)
        analyses.append(analysis)
        catalog.append(
            {
                "trace_id": sc.scenario_id,
                "description": sc.description,
                "tags": sc.tags,
                "expect_p1_p2_differ": sc.expect_p1_p2_differ,
                "expect_bridge_edges": sc.expect_bridge_edges,
                "observed_bridge_edges": analysis["n_artifact_bridge_edges"],
                "p1_p2_differ": analysis["p1_p2_differ"],
            }
        )

    report = {
        "corpus_version": BRIDGE_CORPUS_VERSION,
        "seed": BRIDGE_SEED,
        "n_scenarios": len(catalog),
        "n_positive_bridge": sum(1 for c in catalog if c["expect_p1_p2_differ"]),
        "n_negative": sum(1 for c in catalog if not c["expect_p1_p2_differ"]),
        "all_expectations_met": all(a["match_expectation"] for a in analyses),
        "scenarios": analyses,
        "note": (
            "Phase 2.9 frozen corpus unchanged. This block isolates artifact-mediated "
            "lineage where P1/P2 are distinguishable by construction."
        ),
    }
    (root / "catalog.json").write_text(
        json.dumps({"entries": catalog, "corpus_version": BRIDGE_CORPUS_VERSION}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (reports / "bridge_projection_coverage.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
