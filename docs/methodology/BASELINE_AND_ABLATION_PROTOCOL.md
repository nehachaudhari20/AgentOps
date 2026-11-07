# Baseline and Ablation Protocol (Phase 2.10)

**Status:** Binding comparison protocol. Locked before held-out evaluation.  
**Dataset:** Phase 2.9 `data/benchmarks/experimental_2_9/` (generator `2.5.1`).  
**Ground truth:** evaluation-only; independent `equal_root_ancestor_mass.v1` agent allocations.  
**Held-out rule:** No tuning or definition changes against `heldout_test` after lock.

## 1. Input contract (all online methods)

| Input | Source |
|-------|--------|
| Events / artifacts | `traces/<id>/events.json`, `artifacts.json` only |
| Outcome IDs | Same heuristic as `ProvenanceTrace.outcome_candidates()` (decision/action) |
| Eligible agents | Distinct `agent_id` on events that are ancestors of the outcome in the chosen projection (or all agents on the projection for B0) |
| Normalization | Non-negative agent vector summing to 1.0 when defined; else `status=undefined` |

**Forbidden:** planted responsibility vectors, fault labels, intervention records, GT quality flags as algorithm inputs.

## 2. Methods

### Online evidence-based

| ID | Method | Notes |
|----|--------|-------|
| `rpa_p1` | ConservedRPA α=0 on `P1_DIRECT` | Agent mass = sum of RPA node alloc by `agent_id` |
| `rpa_p2` | ConservedRPA α=0 on `P2_ARTIFACT_BRIDGE` | Same aggregation |
| `B0_uniform_agent` | Uniform over eligible agents on P1 ancestor set of outcome | |
| `B1_last_touch` | Latest (max `ts_start`, tie: max `event_id`) ancestor event’s agent | Temporal proximity ≠ causality |
| `B2_p1_equal_share` | **Alias of `rpa_p1`** — equal-parent reverse flow on P1 | Not an independent algorithm; retained as P2 comparator label |

### Offline / not independently implemented

| ID | Status | Reason |
|----|--------|--------|
| `B3_markov` | **Not implemented as separate method** | Equal-parent reverse absorbing flow on the attribution DAG is mathematically identical to ConservedRPA α=0 (`rpa_p1`/`rpa_p2`). A distinct transition model is not justified from available evidence. |
| `B4_shapley` | **Implemented (offline combinatorial)** | Exact Shapley over agents for ≤12 agents; Monte Carlo for larger. Value `v(S)=1` iff outcome remains reachable when retaining only events whose `agent_id∈S`. Uses public events only (no GT allocations). Information budget: structural reachability game — **not** the same as mass-flow RPA; reported in a separate offline table. |

## 3. Primary paired comparison

On traces where both P1 and P2 RPA succeed:

`Δ = MAE(rpa_p2, GT) − MAE(rpa_p1, GT)`

Negative mean Δ favors P2. Subgroups: artifact-bridge edges present vs absent.

## 4. Ablations

| Ablation | Configuration |
|----------|----------------|
| A-prov-p1 | RPA on P1 only |
| A-prov-p2 | RPA on P2 only |
| A-rpa-alpha | α ∈ {0, 0.25, 0.5, 0.75, 1.0} on P1 |
| A-mfav-vs-agent | MFAV factor vector vs agent aggregation (descriptive; no factor GT → no “correctness”) |
| A-plhc-attack | Controlled evidence tamper vs clean verify |
| A-assurance | Dimension statuses with/without RPA/MFAV/PLHC evidence |

## 5. Result schema

Format: `agenttrust-comparison-result-v1`  
Fields: method_id, method_version, config, trace_id, outcome_id, agent_allocations, status, eligibility, warnings, dataset fingerprints.

## 6. Split usage

1. Develop metrics/baselines on `development`.
2. Sanity-check on `validation`.
3. Freeze configs → run `heldout_test` once for confirmatory comparison artifacts.

## 7. Non-claims

- Agreement with synthetic GT ≠ causal/legal responsibility.
- Shapley reachability game ≠ causal credit.
- Last-touch ≠ causality.
- No universal “AgentTrust score.”
