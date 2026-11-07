# AgentOps

AgentOps is the implementation repository for the **AgentTrust** research framework (governance, provenance, accountability, and auditability for multi-agent AI workflows).

## Phase 2.1 — Research MLPG (current foundation)

The `agenttrust/` package is the Phase 2.1 provenance layer:

- Versioned **EVENT + ARTIFACT** schema with strict validation
- Typed, **unweighted** MultiDiGraph (no random edge weights)
- `ProvenanceTrace` API with completeness / cycle diagnostics
- Attribution projections **P1** (direct `DEPENDS_ON`) and **P2** (plus verified artifact bridges)
- Non-destructive migration: `data/raw_events/events.json` → `data/processed_events/`

**Documentation:** [docs/PHASE_2_1_MLPG.md](docs/PHASE_2_1_MLPG.md)

```bash
pip install -r requirements.txt
python -m agenttrust.migration.cli
python -m pytest tests/ -q
```

**Important limitations (Phase 2.1):** the graph represents *observable* lineage only. It does not reconstruct hidden LLM reasoning, prove causality, or compute responsibility / trust / cryptographic integrity. Redesigned RPA, MFAV, Assurance, and PLHC are **not** implemented in this phase.

Legacy demo modules below (`provenance_graph/`, `attribution/`, …) remain for historical experiments and are separate from the Phase 2.1 API.

## Features (legacy prototype + Phase 2.1)

- **Provenance graph (MLPG)** — Phase 2.1: typed EVENT+ARTIFACT graph; legacy: event-only graph with edge weights
- **Responsibility Propagation Algorithm (RPA)** — Backward propagation of responsibility from outcome nodes to upstream contributors
- **Multi-Factor Accountability Vector (MFAV)** — Aggregates node-level responsibility into accountability factors (agent, prompt, data, tool, memory, execution)
- **Trust scoring** — Weighted composite score from evidence strength, causality confidence, tool reliability, policy compliance, and model confidence, with risk classification
- **Audit integrity** — SHA-256 hash chain over provenance events with tamper detection
- **Simulation** — Synthetic multi-agent workflow generators (linear and branched)
- **Visualizations** — Matplotlib plots for graphs, heatmaps, attribution, MFAV, trust components, and pie charts

## Architecture

```
Event Log (JSON)
      │
      ▼
┌─────────────────┐
│  MLPG Builder   │  provenance_graph/
└────────┬────────┘
         │
    ┌────┴────┬──────────────┬─────────────┐
    ▼         ▼              ▼             ▼
   RPA      MFAV      Trust Scoring   Hash Chain
attribution/ accountability/ trust_scoring/ audit_integrity/
    │         │              │             │
    └────┬────┴──────────────┴─────────────┘
         ▼
  Reports & Visualizations
```

## Project Structure

```
AgentOps/
├── provenance_graph/     # MLPG construction, nodes, edges, weights, visualization
├── attribution/          # RPA and agent-level aggregation
├── accountability/       # MFAV computation and entity mapping
├── trust_scoring/        # Trust model, feature extraction, risk classification
├── audit_integrity/      # Hash chain, tamper simulation, integrity verification
├── simulation/           # Event schema and workflow generators
├── visualizations/       # Matplotlib plotting utilities
├── experiments/          # Runnable entry points
└── data/
    └── raw_events/       # Sample event logs (events.json)
```

## Requirements

- Python 3.9+
- [NetworkX](https://networkx.org/)
- [NumPy](https://numpy.org/)
- [Matplotlib](https://matplotlib.org/)

Install dependencies:

```bash
pip install networkx numpy matplotlib
```

Run all commands from the repository root so imports and data paths resolve correctly.

## Quick Start

### 1. Generate synthetic events (optional)

The repo includes a sample loan-approval workflow in `data/raw_events/events.json`. To regenerate it:

```bash
python -m simulation.agent_simulator
```

### 2. Run experiments

**Provenance graph**

Build the MLPG and display an interactive graph visualization:

```bash
python -m experiments.run_provenance_graph
```

**Responsibility, accountability, and trust**

Run RPA, agent attribution, MFAV, trust scoring, and risk classification:

```bash
python -m experiments.run_rpa
```

**Audit integrity**

Build a hash chain, verify integrity, simulate tampering, and re-verify:

```bash
python -m experiments.run_audit
```

**All visualizations**

Generate MLPG, responsibility heatmap, agent attribution, MFAV, and trust plots:

```bash
python -m experiments.run_visualizations
```

## Event Schema

Events are stored as JSON arrays. Each event has the following fields:

| Field          | Type     | Description                                      |
|----------------|----------|--------------------------------------------------|
| `event_id`     | string   | Unique identifier (UUID)                         |
| `agent_id`     | string   | Agent that produced the event                    |
| `event_type`   | string   | Node type (see below)                            |
| `input_data`   | string   | Input description                                |
| `output_data`  | string   | Output description                               |
| `dependencies` | string[] | List of upstream `event_id` values               |
| `timestamp`    | float    | Unix timestamp                                   |
| `metadata`     | object   | Optional extra metadata                          |

Supported `event_type` values and their provenance layers:

| Type        | Layer | Description              |
|-------------|-------|--------------------------|
| `reasoning` | 1     | Planning / reasoning     |
| `prompt`    | 2     | User or system prompts   |
| `retrieval` | 3     | Data retrieval           |
| `document`  | 3     | Document access          |
| `embedding` | 3     | Embedding operations     |
| `tool_call` | 4     | External tool invocation |
| `action`    | 5     | Final outcome / action   |

## Core Concepts

### Responsibility Propagation (RPA)

RPA starts at the outcome node (`event_type: action`) with responsibility `1.0` and propagates backward through the graph in reverse topological order. Each parent receives a share of its child's responsibility proportional to incoming edge weights.

### Multi-Factor Accountability Vector (MFAV)

Node-level responsibility scores are mapped to accountability factors — `agent`, `prompt`, `data`, `tool`, `memory`, `execution`, and `other` — then normalized to produce an MFAV distribution.

### Trust Score

The trust model combines five weighted components:

| Component          | Weight |
|--------------------|--------|
| Evidence strength  | 0.25   |
| Causality confidence | 0.25 |
| Tool reliability   | 0.20   |
| Policy compliance  | 0.15   |
| Model confidence   | 0.15   |

Risk is classified as **LOW** (> 0.8), **MEDIUM** (> 0.5), or **HIGH** (≤ 0.5).

### Audit Hash Chain

Each graph node is hashed from its event payload and parent hashes (SHA-256). The chain supports integrity verification and detects tampered events.

## License

No license file is included yet. Add one before distributing or contributing.
