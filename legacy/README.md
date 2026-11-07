# Legacy AgentOps Prototype

This directory preserves the **original pre–Phase 2.1** prototype for historical comparison.

It is **not** the active AgentTrust implementation. Active code lives in `agenttrust/`.

## Running legacy demos

From the repository root, add `legacy/` to `PYTHONPATH` so imports like `provenance_graph` resolve:

```powershell
$env:PYTHONPATH = "$PWD\legacy"
python -m experiments.run_rpa
```

Legacy scripts expect event data at `data/raw/events.json` (moved from `data/raw_events/events.json` in Phase 2.2; bytes unchanged).

## Contents

- `provenance_graph/` — original event-only MLPG (random edge weights)
- `attribution/` — original non-conserved RPA
- `accountability/`, `trust_scoring/`, `audit_integrity/`
- `simulation/`, `experiments/`, `visualizations/`
- `evaluation/` — empty metric stubs from the prototype

Do not treat legacy outputs or scores as validated AgentTrust results.
