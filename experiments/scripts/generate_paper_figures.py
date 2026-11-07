#!/usr/bin/env python3
"""
Generate ACM-ready paper figures (Figs. 2–6) from live AgentTrust artifacts.

Usage:
  python experiments/scripts/generate_paper_figures.py --out docs/figures

Exports PDF (vector) + PNG (300 DPI). Numbers and edges come from real data only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.benchmark.bridge_scenarios import (  # noqa: E402
    build_trace,
    scenario_multi_stage_chain,
)
from agenttrust.evaluation.plhc_attacks import attack_event_payload  # noqa: E402
from agenttrust.integrity.verifier import PLHC  # noqa: E402
from agenttrust.mlpg.projections import ProjectionKind  # noqa: E402
from agenttrust.provenance_trace import ProvenanceTrace  # noqa: E402
from agenttrust.schema.enums import NodeKind, RelationshipType  # noqa: E402

# Print-safe palette (no purple glow)
C_EVENT = "#2F4A6D"
C_ARTIFACT = "#C47A3A"
C_DEPENDS = "#1F3A5F"
C_PRODUCES = "#2E7D4F"
C_CONSUMES = "#8B4513"
C_BRIDGE = "#B33A3A"
C_OTHER = "#666666"
C_PANEL = "#F7F5F2"
C_ACCENT = "#1A5F7A"
C_WARN = "#8B4513"


def _setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "DejaVu Serif", "serif"],
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "legend.fontsize": 8,
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save_figure(fig: plt.Figure, out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("pdf", "png"):
        p = out_dir / f"{stem}.{ext}"
        fig.savefig(p, bbox_inches="tight", facecolor="white", edgecolor="none")
        if p.stat().st_size <= 0:
            raise RuntimeError(f"Empty figure output: {p}")
        paths.append(p)
        print(f"wrote {p} ({p.stat().st_size} bytes)")
    plt.close(fig)
    return paths


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_trace_dir(trace_dir: Path) -> ProvenanceTrace:
    events = load_json(trace_dir / "events.json")["events"]
    arts = load_json(trace_dir / "artifacts.json")["artifacts"]
    pt = ProvenanceTrace()
    pt.load_records(events, arts, default_trace_id=trace_dir.name)
    return pt


def short_id(nid: str, *, max_len: int = 10) -> str:
    if ":" in nid:
        nid = nid.rsplit(":", 1)[-1]
    if len(nid) <= max_len:
        return nid
    return nid[: max_len - 1] + "…"


def excerpt_subgraph(g: nx.MultiDiGraph, *, max_events: int = 8) -> nx.MultiDiGraph:
    """Keep first max_events (by sorted id) and their adjacent artifacts."""
    events = sorted(
        n for n, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.EVENT.value
    )[:max_events]
    keep = set(events)
    for u, v, _, data in g.edges(keys=True, data=True):
        if u in keep or v in keep:
            for x in (u, v):
                if g.nodes[x].get("node_kind") == NodeKind.ARTIFACT.value:
                    keep.add(x)
            if u in events:
                keep.add(v)
            if v in events:
                keep.add(u)
    # Include artifacts linked from kept events
    for eid in events:
        for _, v, _, data in g.out_edges(eid, keys=True, data=True):
            keep.add(v)
        for u, _, _, data in g.in_edges(eid, keys=True, data=True):
            keep.add(u)
    return g.subgraph(keep).copy()


def layout_mlpg(g: nx.MultiDiGraph, seed: int = 42) -> dict[str, Any]:
    events = [n for n, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.EVENT.value]
    arts = [n for n, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.ARTIFACT.value]
    # Layered: events on a path-ish layout, artifacts below
    pos: dict[str, tuple[float, float]] = {}
    for i, e in enumerate(sorted(events)):
        pos[e] = (float(i), 1.0)
    for i, a in enumerate(sorted(arts)):
        # place under mean of neighbor events when possible
        nbrs = [n for n in list(g.predecessors(a)) + list(g.successors(a)) if n in pos]
        x = float(np.mean([pos[n][0] for n in nbrs])) if nbrs else float(i)
        pos[a] = (x, 0.0)
    # Mild spring refine among current positions
    if len(pos) > 1:
        pos = nx.spring_layout(g, pos=pos, seed=seed, k=1.2, iterations=50)
    return pos


def draw_mlpg_on_ax(
    ax: plt.Axes,
    g: nx.MultiDiGraph,
    *,
    title: str,
    show_edge_labels: bool = True,
) -> None:
    pos = layout_mlpg(g)
    events = [n for n, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.EVENT.value]
    arts = [n for n, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.ARTIFACT.value]

    nx.draw_networkx_nodes(
        g, pos, nodelist=events, node_color=C_EVENT, node_shape="o",
        node_size=520, ax=ax, edgecolors="white", linewidths=0.6,
    )
    nx.draw_networkx_nodes(
        g, pos, nodelist=arts, node_color=C_ARTIFACT, node_shape="s",
        node_size=420, ax=ax, edgecolors="white", linewidths=0.6,
    )
    labels = {n: short_id(n, max_len=8) for n in g.nodes}
    nx.draw_networkx_labels(g, pos, labels=labels, font_size=7, font_color="white", ax=ax)

    style_map = {
        RelationshipType.DEPENDS_ON.value: (C_DEPENDS, "solid", 1.6),
        RelationshipType.PRODUCES.value: (C_PRODUCES, "solid", 1.4),
        RelationshipType.CONSUMES.value: (C_CONSUMES, "dashed", 1.4),
        RelationshipType.INVOKES.value: (C_OTHER, "dotted", 1.2),
        RelationshipType.RETRIES.value: (C_OTHER, "dashdot", 1.2),
    }
    for u, v, _, data in g.edges(keys=True, data=True):
        rt = data.get("rel_type", "")
        color, ls, lw = style_map.get(rt, (C_OTHER, "solid", 1.0))
        nx.draw_networkx_edges(
            g, pos, edgelist=[(u, v)], edge_color=color, style=ls, width=lw,
            arrows=True, arrowsize=12, ax=ax, connectionstyle="arc3,rad=0.08",
            min_source_margin=12, min_target_margin=12,
        )

    handles = [
        mpatches.Patch(color=C_EVENT, label="Event"),
        mpatches.Patch(color=C_ARTIFACT, label="Artifact"),
        plt.Line2D([0], [0], color=C_DEPENDS, lw=1.6, label="DEPENDS_ON"),
        plt.Line2D([0], [0], color=C_PRODUCES, lw=1.4, label="PRODUCES"),
        plt.Line2D([0], [0], color=C_CONSUMES, lw=1.4, ls="--", label="CONSUMES"),
    ]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=7)
    ax.set_title(title)
    ax.set_axis_off()
    ax.set_facecolor(C_PANEL)


# ---------------------------------------------------------------------------
# Fig. 2
# ---------------------------------------------------------------------------

def fig02_mlpg(out_dir: Path) -> list[Path]:
    trace_id = "bench-fraud_investigation-sequential-S1-s1-clean-cmp"
    tdir = ROOT / "data" / "benchmarks" / "pilot" / "traces" / trace_id
    pt = load_trace_dir(tdir)
    full = pt.graph
    g = excerpt_subgraph(full, max_events=8)
    n_ev = sum(1 for _, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.EVENT.value)
    n_ar = sum(1 for _, d in g.nodes(data=True) if d.get("node_kind") == NodeKind.ARTIFACT.value)

    fig, ax = plt.subplots(figsize=(7.0, 3.6))
    draw_mlpg_on_ax(
        ax,
        g,
        title=(
            f"MLPG excerpt — {n_ev} events, {n_ar} artifacts "
            f"(from {trace_id}; full trace {full.number_of_nodes()} nodes)"
        ),
    )
    fig.text(
        0.5,
        0.01,
        "Fig. 2 source: pilot sequential S1 clean trace; edges are typed MLPG relationships.",
        ha="center",
        fontsize=7,
        color=C_OTHER,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    return save_figure(fig, out_dir, "fig02_mlpg_example")


# ---------------------------------------------------------------------------
# Fig. 3
# ---------------------------------------------------------------------------

def fig03_p1_p2(out_dir: Path) -> list[Path]:
    sc = scenario_multi_stage_chain()
    pt = build_trace(sc)
    p1 = pt.project(ProjectionKind.P1_DIRECT)
    p2 = pt.project(ProjectionKind.P2_ARTIFACT_BRIDGE)
    assert p1.graph.number_of_edges() == 0, "expected P1 with no event edges"
    assert sum(1 for e in p2.edges if e.origin == "ARTIFACT_BRIDGE") == 3

    # Shared layout on event nodes
    nodes = sorted(p2.graph.nodes())
    base = nx.DiGraph()
    base.add_nodes_from(nodes)
    for e in p2.edges:
        base.add_edge(e.source_event_id, e.target_event_id)
    pos = {n: (float(i), 0.0) for i, n in enumerate(nodes)}
    # slight vertical stagger for readability
    for i, n in enumerate(nodes):
        pos[n] = (float(i), 0.15 * (i % 2))

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.8))
    for ax, proj, title in (
        (axes[0], p1, f"P1_DIRECT  (edges={p1.graph.number_of_edges()})"),
        (axes[1], p2, f"P2_ARTIFACT_BRIDGE  (edges={p2.graph.number_of_edges()})"),
    ):
        g = proj.graph
        nx.draw_networkx_nodes(
            g, pos, node_color=C_EVENT, node_size=700, ax=ax, edgecolors="white"
        )
        nx.draw_networkx_labels(
            g, pos, labels={n: n for n in g.nodes}, font_size=8, font_color="white", ax=ax
        )
        for e in proj.edges:
            color = C_BRIDGE if e.origin == "ARTIFACT_BRIDGE" else C_DEPENDS
            ls = "--" if e.origin == "ARTIFACT_BRIDGE" else "-"
            nx.draw_networkx_edges(
                g,
                pos,
                edgelist=[(e.source_event_id, e.target_event_id)],
                edge_color=color,
                style=ls,
                width=2.0,
                arrows=True,
                arrowsize=14,
                ax=ax,
                connectionstyle="arc3,rad=0.15",
            )
            if e.origin == "ARTIFACT_BRIDGE" and len(e.evidence_path) >= 3:
                mid = (
                    (pos[e.source_event_id][0] + pos[e.target_event_id][0]) / 2,
                    0.55,
                )
                ax.text(mid[0], mid[1], e.evidence_path[1], ha="center", fontsize=7, color=C_ARTIFACT)
        ax.set_title(title)
        ax.set_xlim(-0.5, len(nodes) - 0.5)
        ax.set_ylim(-0.6, 1.0)
        ax.set_axis_off()
        ax.set_facecolor(C_PANEL)

    handles = [
        plt.Line2D([0], [0], color=C_DEPENDS, lw=2, label="DEPENDS_ON"),
        plt.Line2D([0], [0], color=C_BRIDGE, lw=2, ls="--", label="ARTIFACT_BRIDGE"),
        mpatches.Patch(color=C_ARTIFACT, label="artifact on evidence path"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=8)
    fig.suptitle(
        "Fig. 3 — multi_stage_artifact_chain (Phase 2.13 bridge corpus)",
        fontsize=10,
        y=1.02,
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.98])
    return save_figure(fig, out_dir, "fig03_p1_vs_p2_bridge")


# ---------------------------------------------------------------------------
# Fig. 4
# ---------------------------------------------------------------------------

def _box(ax, xy, w, h, text, *, fc="#FFFFFF", ec=C_ACCENT):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.05",
        linewidth=1.2, edgecolor=ec, facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=7.5, wrap=True)
    return patch


def fig04_plhc(out_dir: Path) -> list[Path]:
    sc = scenario_multi_stage_chain()
    pt = build_trace(sc)
    plhc = PLHC()
    snap = plhc.build_snapshot(pt)
    cp = plhc.create_checkpoint(
        snap, sequence_number=0, created_at="2020-01-01T00:00:00+00:00"
    )
    clean = plhc.verify_against_checkpoint(pt, cp)
    tampered = attack_event_payload(pt)
    attacked = plhc.verify_against_checkpoint(tampered, cp)

    leaf_ids = [lf.leaf_id for lf in snap.leaves][:6]
    more = max(0, snap.leaf_count - len(leaf_ids))
    root_short = snap.merkle_root[:12] + "…"

    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
    ax.set_axis_off()
    ax.set_facecolor("white")

    # Stage 1: leaves
    _box(ax, (0.3, 4.4), 2.6, 1.4,
         f"Canonical leaves\n(n={snap.leaf_count})\n" + "\n".join(short_id(x, max_len=14) for x in leaf_ids)
         + (f"\n(+{more} more)" if more else ""),
         fc="#EEF4F7")
    # Stage 2: merkle
    _box(ax, (3.6, 4.4), 2.8, 1.4,
         f"Merkle tree v2\naggregate upward\nroot={root_short}",
         fc="#E8F0E9")
    # Stage 3: checkpoint
    _box(ax, (7.0, 4.4), 2.7, 1.4,
         f"Checkpoint\nseq={cp.sequence_number}\nbind root + meta\nprev=none (genesis)",
         fc="#F7F0E8")

    ax.annotate("", xy=(3.5, 5.1), xytext=(3.0, 5.1),
                arrowprops=dict(arrowstyle="->", color=C_ACCENT, lw=1.5))
    ax.annotate("", xy=(6.9, 5.1), xytext=(6.5, 5.1),
                arrowprops=dict(arrowstyle="->", color=C_ACCENT, lw=1.5))

    # Verify path
    _box(ax, (0.3, 2.2), 4.4, 1.5,
         f"Verify vs retained checkpoint\nrebuild snapshot → compare root/leaf_count\n"
         f"clean status: {clean.status.value.upper()}",
         fc="#EEF4F7", ec=C_PRODUCES)
    _box(ax, (5.3, 2.2), 4.4, 1.5,
         f"Attack inset: event_payload_change\nverify status: {attacked.status.value.upper()}\n"
         f"(tamper-evident; checkpoint held honest)",
         fc="#F8ECEC", ec=C_BRIDGE)

    ax.annotate("", xy=(2.5, 3.7), xytext=(4.8, 4.35),
                arrowprops=dict(arrowstyle="->", color=C_OTHER, lw=1.2))
    ax.annotate("", xy=(7.5, 3.7), xytext=(8.2, 4.35),
                arrowprops=dict(arrowstyle="->", color=C_OTHER, lw=1.2))

    ax.text(
        5.0,
        0.85,
        "Threat model: tamper-evident relative to an honestly retained checkpoint.\n"
        "Not immutability, external anchoring, or dual-rewrite resistance.",
        ha="center",
        va="center",
        fontsize=7.5,
        color=C_WARN,
    )
    ax.set_title(
        f"Fig. 4 — PLHC construction & verification  "
        f"(scenario={sc.scenario_id}; leaf_count={snap.leaf_count})",
        fontsize=10,
        pad=8,
    )
    fig.tight_layout()
    return save_figure(fig, out_dir, "fig04_plhc_integrity")


# ---------------------------------------------------------------------------
# Fig. 5
# ---------------------------------------------------------------------------

def fig05_design(out_dir: Path) -> list[Path]:
    cov = load_json(ROOT / "data" / "benchmarks" / "experimental_2_9" / "reports" / "split_coverage.json")
    stats = load_json(ROOT / "data" / "benchmarks" / "experimental_2_9" / "reports" / "dataset_statistics.json")

    splits = ["development", "validation", "heldout_test"]
    labels = ["development", "validation", "held-out"]
    sizes = [cov[s]["n_traces"] for s in splits]
    total = sum(sizes)

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.4))

    # Panel A: split sizes
    ax = axes[0]
    bars = ax.bar(labels, sizes, color=[C_ACCENT, "#3D7A6A", C_EVENT], width=0.65)
    for b, v in zip(bars, sizes):
        ax.text(b.get_x() + b.get_width() / 2, v + 12, str(v), ha="center", fontsize=8)
    ax.set_ylabel("Traces (N)")
    ax.set_title(f"(a) Split sizes  (total={total})")
    ax.set_ylim(0, max(sizes) * 1.18)

    # Panel B: role composition held-out
    ax = axes[1]
    role = cov["heldout_test"]["role"]
    role_labels = list(role.keys())
    role_vals = [role[k] for k in role_labels]
    ax.barh(role_labels, role_vals, color=C_ARTIFACT)
    for y, v in enumerate(role_vals):
        ax.text(v + 5, y, str(v), va="center", fontsize=8)
    ax.set_xlabel("Traces")
    ax.set_title("(b) Held-out roles")

    # Panel C: held-out topology counts (horizontal for readable labels)
    ax = axes[2]
    topo = cov["heldout_test"]["topology"]
    names = list(topo.keys())
    vals = [topo[k] for k in names]
    short = [n.replace("_", " ") for n in names]
    y = range(len(names))
    ax.barh(list(y), vals, color=C_EVENT)
    ax.set_yticks(list(y))
    ax.set_yticklabels(short, fontsize=7)
    for yi, v in zip(y, vals):
        ax.text(v + 2, yi, str(v), va="center", fontsize=7)
    ax.set_xlabel("Traces")
    ax.set_title("(c) Held-out topologies")
    ax.invert_yaxis()

    fig.suptitle(
        "Fig. 5 — Evaluation design (experimental_2_9); unit = trace; pairs stay in-split",
        fontsize=10,
    )
    note = (
        f"n_traces_total={stats.get('n_traces_total', total)}. "
        "Event/artifact totals are nested volume, not independent N. "
        "Phase 2.13 bridge corpus is separate."
    )
    fig.text(0.5, 0.01, note, ha="center", fontsize=7, color=C_OTHER)
    fig.tight_layout(rect=[0, 0.05, 1, 0.92])
    return save_figure(fig, out_dir, "fig05_eval_design_splits")


# ---------------------------------------------------------------------------
# Fig. 6
# ---------------------------------------------------------------------------

def _finite(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def fig06_results(out_dir: Path) -> list[Path]:
    rq_path = ROOT / "experiments" / "results" / "phase_2_13" / "heldout_test_rq_summary.json"
    iv_path = ROOT / "experiments" / "results" / "phase_2_13" / "intervention_attribution_heldout.json"
    power_path = ROOT / "data" / "benchmarks" / "experimental_2_9" / "reports" / "sample_size_power_2_13.json"
    if not rq_path.is_file():
        raise FileNotFoundError(f"Missing {rq_path}; run Phase 2.13 evaluation first")
    data = load_json(rq_path)
    iv = load_json(iv_path) if iv_path.is_file() else None
    power = load_json(power_path) if power_path.is_file() else None

    fig, axes = plt.subplots(2, 3, figsize=(7.4, 5.2))

    # (a) RQ1 F1
    ax = axes[0, 0]
    rels = ["depends_on_f1", "produces_f1", "consumes_f1"]
    names = ["DEPENDS_ON", "PRODUCES", "CONSUMES"]
    means, los, his = [], [], []
    for r in rels:
        m = data["rq1"][r]
        means.append(m["mean"])
        los.append(m["mean"] - m["ci_low"])
        his.append(m["ci_high"] - m["mean"])
    ax.bar(names, means, yerr=[los, his], color=C_ACCENT, capsize=3, width=0.6)
    ax.set_ylim(0.98, 1.005)
    ax.set_ylabel("F1")
    ax.set_title(f"(a) RQ1 lineage F1 (n={int(data['rq1']['n_traces'])})")
    ax.tick_params(axis="x", labelsize=7)

    # (b) RQ2 equal-root MAE
    ax = axes[0, 1]
    methods = ["rpa_p1", "rpa_p2", "B0_uniform_agent", "B1_last_touch"]
    labels = ["RPA-P1", "RPA-P2", "B0", "B1"]
    mae_m, mae_lo, mae_hi = [], [], []
    for m in methods:
        row = data["rq2"]["methods"][m]["mae"]
        mean = _finite(row["mean"]) or 0.0
        lo = _finite(row["ci_low"])
        hi = _finite(row["ci_high"])
        mae_m.append(mean)
        mae_lo.append(0.0 if lo is None else max(0.0, mean - lo))
        mae_hi.append(0.0 if hi is None else max(0.0, hi - mean))
    ax.bar(labels, mae_m, yerr=[mae_lo, mae_hi], color=C_EVENT, capsize=3, width=0.65)
    ax.set_ylabel("MAE")
    ax.set_title("(b) RQ2 MAE vs equal-root*")
    ax.text(0.5, -0.22, "*structurally aligned with RPA α=0", transform=ax.transAxes,
            ha="center", fontsize=6.5, color=C_WARN)

    # (c) Intervention MAE
    ax = axes[0, 2]
    if iv and iv.get("methods"):
        iv_methods = ["rpa_p1", "rpa_p2", "B0_uniform_agent", "B1_last_touch"]
        iv_labels = ["RPA-P1", "RPA-P2", "B0", "B1"]
        vals, elo, ehi = [], [], []
        for m in iv_methods:
            row = iv["methods"][m]["mae"]
            mean = row["mean"]
            vals.append(mean)
            elo.append(mean - row["ci_low"])
            ehi.append(row["ci_high"] - mean)
        ax.bar(iv_labels, vals, yerr=[elo, ehi], color=C_ARTIFACT, capsize=3, width=0.65)
        ax.set_title(f"(c) Intervention MAE (n_def={iv['n_defined']})")
    else:
        ax.text(0.5, 0.5, "intervention results unavailable", ha="center", va="center")
        ax.set_title("(c) Intervention MAE")
    ax.set_ylabel("MAE")

    # (d) RQ3 delta
    ax = axes[1, 0]
    d = data["rq3"]["delta_p2_minus_p1"]
    ax.axhline(0.0, color=C_OTHER, lw=0.8)
    ax.errorbar(
        [0], [d["mean"]],
        yerr=[[d["mean"] - d["ci_low"]], [d["ci_high"] - d["mean"]]],
        fmt="o", color=C_BRIDGE, markersize=8, capsize=5,
    )
    ax.set_xlim(-0.8, 0.8)
    ax.set_xticks([0])
    ax.set_xticklabels(["Δ MAE(P2−P1)"])
    ax.set_title(
        f"(d) RQ3 paired Δ  (n={data['rq3']['n_paired']}; "
        f"bridges={data['rq3']['n_with_artifact_bridge_edges']})"
    )
    ax.set_ylabel("Δ MAE")

    # (e) RQ5 detection rates
    ax = axes[1, 1]
    attacks = data["rq5"]["per_attack"]
    # pick a readable subset + order
    order = [
        "event_payload_change",
        "artifact_content_change",
        "leaf_removal_via_event_delete",
        "artifact_deletion",
        "relationship_modification",
        "event_reordering",
        "identity_substitution",
        "checkpoint_alteration",
        "checkpoint_chain_alteration",
    ]
    short_map = {
        "event_payload_change": "evt payload",
        "artifact_content_change": "art content",
        "leaf_removal_via_event_delete": "evt delete",
        "artifact_deletion": "art delete",
        "relationship_modification": "rel mod",
        "event_reordering": "reorder",
        "identity_substitution": "identity",
        "checkpoint_alteration": "ckpt root",
        "checkpoint_chain_alteration": "ckpt chain",
    }
    xs, rates, los, his = [], [], [], []
    for k in order:
        if k not in attacks:
            continue
        w = attacks[k]["wilson_95"]
        xs.append(short_map.get(k, k))
        rates.append(w["rate"])
        los.append(w["rate"] - w["ci_low"])
        his.append(w["ci_high"] - w["rate"])
    ax.barh(xs[::-1], rates[::-1], xerr=[los[::-1], his[::-1]], color=C_PRODUCES, capsize=2)
    ax.set_xlim(0.9, 1.01)
    ax.set_xlabel("Detection rate")
    ax.set_title(f"(e) RQ5 PLHC attacks (n={data['rq5']['n_traces']})")

    # (f) Power
    ax = axes[1, 2]
    ax.set_axis_off()
    if power:
        primary = power.get("primary_planning_cell") or {}
        txt = (
            "Paired McNemar power\n"
            f"n_pairs={power.get('heldout_incompleteness_pairs')}\n"
            f"primary power={primary.get('power'):.4f}\n"
            f"meets_80={primary.get('meets_80')}\n"
            f"suggested n≈{power.get('n_pairs_for_80_primary_cell')}\n\n"
            "Independent z-test figure\n(Phase 2.9) is invalid."
        )
    else:
        txt = "Power report missing"
    ax.text(
        0.5, 0.5, txt, ha="center", va="center", fontsize=8,
        family="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=C_PANEL, edgecolor=C_ACCENT),
    )
    ax.set_title("(f) Sample-size / power")

    fig.suptitle(
        "Fig. 6 — Phase 2.13 held-out evaluation (machine-readable sources)",
        fontsize=10,
    )
    fig.text(
        0.5,
        0.01,
        "RQ1 = simulator lineage fidelity (not real-world recovery). "
        "PLHC = tamper-evident vs retained checkpoint.",
        ha="center",
        fontsize=6.5,
        color=C_OTHER,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.94])
    return save_figure(fig, out_dir, "fig06_phase213_results")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "docs" / "figures",
        help="Output directory for PDF/PNG figures",
    )
    p.add_argument(
        "--only",
        nargs="+",
        choices=["2", "3", "4", "5", "6"],
        help="Generate only selected figure numbers",
    )
    args = p.parse_args(argv)
    _setup_style()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    only = set(args.only) if args.only else {"2", "3", "4", "5", "6"}

    writers = {
        "2": fig02_mlpg,
        "3": fig03_p1_p2,
        "4": fig04_plhc,
        "5": fig05_design,
        "6": fig06_results,
    }
    written: list[Path] = []
    for key in sorted(only):
        print(f"\n=== Generating Fig. {key} ===", flush=True)
        written.extend(writers[key](out))

    # Smoke checks
    for path in written:
        assert path.is_file() and path.stat().st_size > 0
    meta = {
        "figures": [str(p.as_posix()) for p in written],
        "out_dir": str(out.as_posix()),
    }
    (out / "generation_manifest.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"ok": True, "n_files": len(written), "out": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
