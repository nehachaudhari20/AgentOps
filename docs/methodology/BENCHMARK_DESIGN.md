# Benchmark Design — Synthetic Multi-Agent Traces (Phase 2.4)

## Why a synthetic benchmark

Controlled evaluation of provenance, structural allocation (RPA), and factor aggregation (MFAV) requires:

- Known workflow topologies and agent populations
- Explicit, reproducible seeds
- Separately stored intervention ground truth
- Intentionally incomplete and fault-injected cases

A single 14-event loan fixture is a smoke test, not a research corpus. Synthetic generation provides scale and topology diversity **without** claiming that results transfer to production multi-agent systems.

## What this benchmark establishes

| Layer | Role |
|-------|------|
| Unit / property tests | Algorithm and schema correctness on small fixtures |
| Pilot generation (this phase) | Generator + data-model validation |
| Final experimental evaluation | **Phase 2.9 corpus** under `data/benchmarks/experimental_2_9/` (design + held-out splits); algorithm baselines later |

The pilot does **not** validate production-scale behavior or AgentTrust “performance.”

## Representation

- **Agents**: stable synthetic IDs from scenario role templates (`coordinator-0`, `researcher`, …). No real personal data.
- **Events / artifacts**: native Phase 2.1 schema dicts (`EventRecord` / `ArtifactRecord` fields), loadable by `ProvenanceTrace` without migration.
- **Optional identities**: `model_id`, `tool_id`, memory subtype metadata when the scenario/topology specifies them.
- **Timestamps**: fixed base epoch + deterministic offsets (not wall-clock).

## Topologies (explicit construction rules)

1. **sequential** — linear chain; each step depends on the previous; pad middle specialist units to target size.
2. **hierarchical** — coordinator plan → specialist wave(s) → coordinator synthesis → executor.
3. **parallel_fanout_fanin** — shared prompt/plan → parallel branches → merge → decision.
4. **shared_artifact** — producers emit artifacts reused by multiple consumers.
5. **delegated_multi_agent** — multi-level `INVOKES` with caller dependence on callee completion.
6. **mixed_realistic** — parallel evidence + shared docs + retry + delegation + decision.

These are **not** arbitrary random DAGs labeled realistic.

## Domain scenarios

Configurable templates: financial loan, fraud investigation, compliance review, research synthesis, transaction execution. Each supplies roles, tools, artifact types, and an outcome label. Content strings are synthetic placeholders.

## Scale tiers

| Tier | Agents | Target events |
|------|-------:|--------------:|
| S1 | 5 | 50 |
| S2 | 10 | 100 |
| S3 | 20 | 250 |
| S4 | 50 | 500 |
| S5 | 50 | 1000 |

Actual generated counts may differ slightly by topology construction; manifests record **actual** counts.

## Interventions and ground truth

Faults are planted as explicit `InterventionRecord` objects with IDs, locations, parameters, and expected *observable* effects.

Ground truth is stored in **separate files** under `ground_truth/`, never as answer labels inside algorithm-facing event metadata (`gt_*` keys are rejected by the Phase 2.5 validator).

Categories:

- **Lineage** — dependencies, producers/consumers, invocations, retries
- **Intervention** — planted faults (distinct from mere downstream dependents)
- **Structural** — agents, models/tools, categories, topology, outcomes
- **Trace quality** — missing events/deps, corrupted artifacts, incompleteness flags

**Non-claim:** graph reachability from an intervention to an outcome is **not** causal ground truth.

### Phase 2.5 fault-semantics notes

| Fault | Meaning (hardened) |
|-------|--------------------|
| `incorrect_tool_output` | Successful tool call with wrong content hash (expected hash only in GT) |
| `tool_call_failure` | Tool/transport failure (`status=failure`) — distinct from incorrect content |
| `artifact_corruption` | Hash replacement; expected vs observed hashes retained in GT only |
| `retry_storm` | Unique retry events + artifacts; MLPG `RETRIES` edges required |
| `delegation_failure` | Modes `missing_callee` vs `callee_failed` |
| `misleading_delayed_observation` | `OBSERVED_AFTER` without `DEPENDS_ON`; excluded from P1/P2 |
| `missing_dependency` / `incomplete_trace` | Intentional defects; validator must not silently repair |
| `conflicting_agent_outputs` | Distinct structured `decision` values + hashes (no `conflict_label`); relation only in GT |

Active generator version: **`2.5.1`**. The checked-in pilot corpus remains **`2.4.0`** historical data (not overwritten).

### Validation modes

| Mode | Command | Claims |
|------|---------|--------|
| A — Historical pilot | `python experiments/scripts/validate_benchmark_pilot.py [--pipeline]` | Package/schema/GT/pipeline for `data/benchmarks/pilot/` — **not** Phase 2.5.1 fault-observable certification |
| B — Strict 2.5 fault matrix | `python experiments/scripts/validate_phase25_fault_matrix.py` | Fresh generator traces with `check_fault_observables=True` for every fault type |

## Reproducibility

Identical `BenchmarkConfig` (scenario, topology, scale, seed, faults, incomplete flag, generator version) regenerates identical logical records. Manifests include config fingerprint, expected vs actual event counts, and generator version.

Phase 2.5 verification: all **60 clean** pilot traces regenerate with matching stripped logical payloads under generator `2.5.0` (faulted traces intentionally diverge due to semantic fixes). See `data/benchmarks/pilot/reproducibility_check.json`.

## Trace completeness

Complete traces have valid in-trace dependency references. Incomplete / missing-dependency interventions are marked in the manifest and quality GT. Validators must **not** silently repair them. RPA remains gated by existing completeness guards. The validator distinguishes **intentional** missing refs (declared by interventions) from **accidental** generator defects.

## Graph / projection fidelity

- MLPG retains `DEPENDS_ON`, `PRODUCES`, `CONSUMES`, `INVOKES`, `RETRIES`, `OBSERVED_AFTER` as distinct MultiDiGraph edge keys.
- P1 uses explicit `DEPENDS_ON` only; P2 adds verified artifact bridges.
- `OBSERVED_AFTER` is never treated as structural responsibility dependence.

## Final evaluation corpus

See [FINAL_EXPERIMENTAL_DATASET_PLAN.md](FINAL_EXPERIMENTAL_DATASET_PLAN.md) — design only; not generated in Phase 2.5.

## Limitations of synthetic data

- Interaction patterns are stylized, not empirical multi-agent logs
- Tool/model IDs are placeholders
- Fault effects are observational markers, not measured real-world impact
- No claim of coverage of all production failure modes

## Complement with real traces (later)

A future phase can add anonymized or consented real traces for external validity, while keeping this generator for controlled ablation over topology, scale, and interventions.

## Out of scope here

Assurance/CTSM, PLHC, new RPA math, Shapley/Markov baselines, final performance tables, causal performance claims.
