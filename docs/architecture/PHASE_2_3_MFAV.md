# Phase 2.3 — Multi-Factor Accountability Vector (MFAV)

## Purpose

MFAV is the factor-level aggregation layer built on conserved RPA. It represents how the **structural allocation** associated with an outcome is distributed across an **exclusive** set of observable accountability factors.

Pipeline:

```text
ProvenanceTrace → MLPG → P1/P2 projection → RPA → MFAV
```

RPA produces event-level structural allocations. MFAV maps each allocation to exactly one primary factor and aggregates.

## Explicit non-claims

MFAV **does not**:

- Independently calculate responsibility
- Infer causal influence or fault probability
- Reconstruct hidden model reasoning
- Produce trust scores or legal liability
- Manufacture missing model / agent / tool identities

The normalized MFAV vector describes the distribution of RPA’s structural allocation across factors — nothing more.

## Exclusive factor taxonomy

Version: `2.3.0`

| Factor | Meaning (observable) |
|--------|----------------------|
| `agent` | Agent-linked structural allocation |
| `model` | Explicit model-identity allocation |
| `prompt` | Instruction / prompt events |
| `data` | Retrieval, knowledge, (default) transformation |
| `tool` | Tool invocations / tool-identified transforms |
| `execution` | Decision / action events |
| `other` | Uncategorized / residual |

Every RPA event allocation maps to **exactly one** primary factor. No double-counting across factors.

### Memory

Memory is a **secondary subtype tag** of `data`, not a primary factor. It is applied only when explicit metadata supports it (e.g. `metadata.subtype = memory` or `metadata.memory = true`). Agent display names such as `"Memory"` never trigger the tag. Secondary tags are **not** added into primary factor totals.

## Mapping policy

Named policy: `category_primary_v1` (default).

| Observable `EventCategory` | MFAV factor |
|----------------------------|-------------|
| `instruction` | `prompt` |
| `reasoning` | `agent`, unless explicit `model_id` → `model` |
| `retrieval` | `data` |
| `knowledge` | `data` |
| `transformation` | `data`, unless explicit `tool_id` → `tool` |
| `tool` | `tool` |
| `decision` | `execution` |
| `other` | `other` |

Classification uses category and explicit optional identity fields — not fragile substring checks on agent names.

## Model vs agent

A model is distinct from an agent. Optional schema fields:

- `model_id` — explicit model identity when recorded
- `tool_id` — explicit tool identity when recorded
- `metadata` — non-sensitive tags (e.g. memory)

Absent fields remain absent. Historical records without these fields stay valid. **Never** infer a model name from an agent name.

## Mathematical formulation

Let \(V_o\) be event nodes with final RPA allocation for outcome \(o\), and \(a_v^{(o)} \ge 0\) the allocation to event \(v\).

Let \(F\) be the exclusive factor set and \(g: V_o \rightarrow F\) the deterministic classifier.

\[
A_f^{(o)} = \sum_{v \in V_o : g(v)=f} a_v^{(o)},
\qquad
A_{\mathrm{total}}^{(o)} = \sum_{f \in F} A_f^{(o)}
\]

When RPA is complete and conserved, \(A_{\mathrm{total}}^{(o)} \approx 1\).

Normalized vector (only when the total is strictly positive and finite):

\[
M_f^{(o)} = \frac{A_f^{(o)}}{A_{\mathrm{total}}^{(o)}},
\qquad
\sum_{f \in F} M_f^{(o)} = 1
\]

**No epsilon** is added to the denominator. If the total is zero, MFAV returns status `zero_allocation`, preserves raw zeros, and sets the normalized vector to `null` (never a uniform distribution).

## Entity-level aggregation

Within each primary factor, allocations are further grouped by stable IDs:

- `agent_id`, `model_id`, `tool_id`, artifact ids, or `event_id` as appropriate
- Distinct stable IDs are never merged because display names match
- Missing identity → explicit `__unidentified__` contribution under that factor

Each event allocation is counted **once** in the factor total and **once** in its entity contribution.

## Completeness propagation

If upstream RPA is incomplete or ran with overridden guards:

- MFAV status is `incomplete` or `overridden`
- `complete=false`
- RPA warnings and `overridden_guards` are preserved
- The profile must not be presented as a complete accountability profile

## Zero / invalid allocations

- Zero total → `zero_allocation`, no normalized vector
- Negative, NaN, or infinite RPA values → rejected (`MFAVError`)

## RPA integration

MFAV consumes `RPAResult` as-is. It does not rerun RPA or mutate allocations / provenance graphs.

Preserved metadata includes outcome id, projection kind, RPA algorithm/version/alpha/parent policy, completeness, warnings, taxonomy version, and mapping policy.

P1 and P2 results are never silently combined. Separate outcomes are never silently combined.

## API

```python
from agenttrust import ProvenanceTrace, ConservedRPA, MFAV
from agenttrust.mlpg.projections import ProjectionKind

trace = ProvenanceTrace()
trace.load_records(events, artifacts)

rpa_results = ConservedRPA().allocate_from_trace(
    trace,
    projection_kind=ProjectionKind.P1_DIRECT,
)

profiles = [MFAV().compute(result, trace=trace) for result in rpa_results]
```

## Limitations

- Structural allocation ≠ causation ≠ legal accountability
- Unobserved model identity remains unobserved
- Initial taxonomy is research-initial, not exhaustive organizational policy
- No claim that MFAV “improves accountability” until independent evaluation
