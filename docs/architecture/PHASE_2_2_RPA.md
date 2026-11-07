# Phase 2.2 — Conserved Responsibility Propagation (RPA)

## Scope

Structural responsibility allocation over Phase 2.1 event projections (P1/P2).

**Not causal attribution. Not legal responsibility. Not hidden-reasoning reconstruction.**

## Formulation (α = 0 baseline)

For outcome \(o\) on attribution DAG \(G=(V,E)\):

1. Initialise flow \(f(o)=1\), \(f(v)=0\) otherwise; allocations \(a(v)=0\).
2. Process nodes in reverse topological order (stable tie-break by node id / rank).
3. For node \(v\) with mass \(f(v)\):
   - **No parents (root):** \(a(v) \leftarrow a(v)+f(v)\); clear flow.
   - **Has parents:** retain \(\alpha\cdot f(v)\) in \(a(v)\); forward \((1-\alpha)\cdot f(v)\) to parents by the parent policy; clear flow.

With **α = 0**, intermediates retain nothing; roots absorb all mass:

\[
\sum_{v\in V} a(v)=1,\qquad \sum_{r\in\mathrm{roots}} a(r)=1
\]

(when \(o\in V\) and \(G\) is a finite DAG).

## Parent policy

Baseline: `equal_parents` — equal structural split among inbound parents. This is a **convention**, not measured causal weight. The policy is configurable for future experiments.

## Guards

- Incomplete traces: rejected unless `allow_incomplete=True` (result marked overridden).
- Cycles: always rejected — ConservedRPA requires a DAG. `allow_cycles=True` does **not** enable cyclic propagation; it raises an explicit unsupported error (corrected in Phase 2.3).
- Provenance MultiDiGraph is never mutated by projection or RPA.

## API

```python
from agenttrust import ConservedRPA, ProvenanceTrace
from agenttrust.mlpg.projections import ProjectionKind

ConservedRPA().allocate_from_trace(trace, projection_kind=ProjectionKind.P1_DIRECT)
```
