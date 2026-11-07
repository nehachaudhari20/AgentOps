# Experimental Dataset Design (Phase 2.9)

**Status:** Binding design for the Phase 2.9 experimental corpus.  
**Generator:** `2.5.1` (active). Historical pilot remains `2.4.0` under `data/benchmarks/pilot/`.  
**Primary experimental unit:** one **trace** (not nested events/artifacts/agents).

## 1. Historical pilot (inspected, not reused as final eval)

From `data/benchmarks/pilot/summary.json` (generator `2.4.0`):

| Quantity | Value |
|----------|------:|
| Traces | 68 |
| Events | 23,190 |
| Artifacts | 23,188 |
| Unique agent IDs | 107 |
| Topologies | 6 |
| Scenarios | 5 |
| Fault-injected (pilot sample) | 8 (+ incompleteness via 2 traces) |

The pilot validates the generator and Phase 2.8 pipeline. It is **not** the held-out final evaluation set.

## 2. Experimental factors (supported only)

| Factor | Levels | Independently controlled? |
|--------|--------|---------------------------|
| Topology | 6 (`sequential`, `hierarchical`, `parallel_fanout_fanin`, `shared_artifact`, `delegated_multi_agent`, `mixed_realistic`) | Yes |
| Domain scenario | 5 | Yes (rotated; not full cross in all blocks) |
| Scale tier | S1–S5 | Yes (agents/events are **targets**, actual counts recorded) |
| Fault family | 9 `FaultType` values + clean | Yes (one-fault-at-a-time in fault block) |
| Clean vs fault | binary | Yes; matched pairs share `matched_pair_id` |
| Fault location / severity | generator defaults per type | **Partially** — location chosen deterministically by seed; no separate severity dial beyond type semantics |
| Seed / replicate | integer | Yes within split seed bands |

**Not invented:** continuous severity knobs, multi-fault stacks (deferred), production traffic mixes.

### Scale targets (ranges)

| Tier | Agents | Target events |
|------|-------:|--------------:|
| S1 | 5 | 50 |
| S2 | 10 | 100 |
| S3 | 20 | 250 |
| S4 | 50 | 500 |
| S5 | 50 | 1,000 |

Actual counts are validated against manifests; deviations are reported, not silently ignored.

## 3. Coverage design (fractional, documented)

A full factorial  
`6 topologies × 5 scenarios × 5 scales × (1 clean + 9 faults) × R replicates`  
≈ **1,800 × R** traces — too large for this phase and unnecessary for primary contrasts.

### Blocks

**A. Clean core (topology × scale, scenario rotated)**  
Scenarios assigned round-robin by cell index so every scenario appears; locked-scenario full cross is **not** claimed.

**B. Fault block (one fault at a time)**  
`9 faults × 6 topologies × {S1, S2} × R` with a **matched clean twin** (same topology, scale, scenario, `base_seed`; different concrete seed; shared `matched_pair_id`).  
S3–S5 faults omitted from the primary matrix (cost); noted as a coverage gap, not silently “covered.”

**C. Incomplete focus**  
Already included via `incomplete_trace` and `missing_dependency` fault families.

### Split sizes (trace counts = independent units)

| Split | Clean core | Fault pairs (fault+clean) | Total traces | Replicates R |
|-------|----------:|--------------------------:|-------------:|-------------:|
| `development` | 6×5×2 = 60 | 9×6×1×2×2 = 216 | **276** | 2 |
| `validation` | 6×5×3 = 90 | 9×6×2×2×2 = 432 | **522** | 2–3 |
| `heldout_test` | 6×5×5 = 150 | 9×6×2×3×2 = 648 | **798** | 3–5 |
| **All Phase 2.9** | | | **1,596** | |

Fault-pair formula: `faults × topologies × scales × R × 2` (fault + matched clean).

Seed bands (no overlap across splits or historical pilot seeds 1–200):

| Split | Seed range |
|-------|------------|
| development | 10_000 – 19_999 |
| validation | 20_000 – 29_999 |
| heldout_test | 30_000 – 39_999 |

## 4. Sample-size and power rationale (summary)

Full procedure: [SAMPLE_SIZE_AND_POWER.md](SAMPLE_SIZE_AND_POWER.md).

Prespecified primary comparison (held-out):

- **P1:** Paired difference in Assurance `trace_completeness` / reference-integrity status between matched clean vs incompleteness-inducing faults (`incomplete_trace`, `missing_dependency`), at trace level.
- **Smallest effect of interest:** absolute detection-rate difference Δ = 0.20 (20 percentage points).
- **α = 0.05** (two-sided), target power **≥ 0.80** (0.90 preferred where feasible).
- Pilot variance: near-ceiling success on clean complete traces; incompleteness n=2 → **high uncertainty**; sensitivity analysis over null rates p₀ ∈ {0.5, 0.7, 0.9}.

With R=3 at S1+S2 across 6 topologies for those two fault families:  
`2 faults × 6 topo × 2 scales × 3 = 72` fault traces (+72 matched cleans) in held-out — adequate for Δ=0.20 under mid-range variance by simulation (see power report).

Secondary / exploratory (precision-based, not powered claims):

- Topology contrasts on MFAV vectors (clean core, cell means ± bootstrap CI over seeds).
- P1/P2 MFAV total variation δ.
- Fault observability agreement with declared matrix (not “Assurance detects all faults”).

**Do not** treat event counts as N.

## 5. Independence and splits

- Entire traces assigned to exactly one of `development` | `validation` | `heldout_test`.
- Matched clean/fault pairs never cross splits.
- No event-level splitting.
- No base-seed reuse across splits.
- Algorithm parameters must not be tuned on `heldout_test`.
- Ground truth remains evaluation-only; Phase 2.8 pipeline must not read it.

Historical `pilot/` stays frozen for regression.

## 6. Ground-truth design

Version: **`gt-2.9.0`**.

Stored only under `ground_truth/` (never in `events.json` / `artifacts.json`).

| Component | Meaning | Not claimed |
|-----------|---------|-------------|
| Lineage | Post-emission dependency / produce / consume / invoke / retry maps | Causality |
| Interventions | Planted fault records + expected observables | Which agent is “at fault” morally |
| Structural | Agents, tools, models, outcomes, topology | |
| Quality | Intentional incompleteness, missing refs, corrupt artifacts | |
| **Attribution reference** | Equal mass over **root ancestors** of each outcome in the post-generation event DAG (simulator lineage), keyed by `event_id` / `agent_id` | Causal responsibility; **not** copied from ConservedRPA |

Reference attribution method id: `equal_root_ancestor_mass.v1`.  
Validators prove algorithm inputs lack prohibited answer keys and GT paths.

## 7. Fault observability (declaration classes)

| Class | Meaning |
|-------|---------|
| `directly_observable` | Evidence appears in public events/artifacts alone |
| `indirect_inconsistency` | Detectable as structural inconsistency without knowing “truth” |
| `requires_ground_truth` | Needs retained expected hash / removed-id list / etc. |
| `not_reliably_detectable` | Observable disagreement without uniquely identifying the correct party |

Assurance Profile is **not** assumed to detect every injected fault. See fault observability matrix report.

## 8. Storage layout

```text
data/benchmarks/experimental_2_9/
  design_fingerprint.json
  splits/{development,validation,heldout_test}/
    traces/<trace_id>/{events.json,artifacts.json}
    ground_truth/<trace_id>.json
    manifests/<trace_id>.json
    catalog.json
    coverage_report.json
    validation_report.json
    fingerprint_manifest.json
  reports/
    dataset_statistics.json
    split_coverage.json
    ground_truth_validation.json
    fault_observability_matrix.json
    sample_size_power.json
```

## 9. Non-goals (Phase 2.9)

- Baseline / ablation algorithm runs (Phase 2.10+).
- Claiming external validity to production multi-agent systems.
- Expanding beyond supported fault types.
- Silent omission of expensive cells without documentation.
