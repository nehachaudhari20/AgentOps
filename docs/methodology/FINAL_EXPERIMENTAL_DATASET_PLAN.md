# Final Experimental Dataset Plan (Design Only)

**Status:** Design document for a future evaluation phase.  
**Not generated in Phase 2.5.** The checked-in pilot remains a development corpus.

## Units of analysis

- **Primary unit:** one *trace* (one generated multi-agent execution).
- Events within a trace are **dependent**; do not treat every event as an independent experimental observation.
- Traces from the same template family and nearby seeds are related; report them as such.

## Research questions supported by dataset dimensions

| Dimension | Supports |
|-----------|----------|
| Topology (6) | RQ: does structural allocation / MFAV factor mix vary by workflow shape? |
| Scale tier (S1–S5) | RQ: does behavior remain stable as agent/event volume grows? |
| Scenario (5) | RQ: are findings robust across domain role/tool templates? |
| Fault type (9 after Phase 2.5) | RQ: do planted interventions produce expected observable integrity signals? |
| Seed / repetition | Uncertainty estimation; avoid single-seed anecdotes |
| Fault-free vs injected | Controlled contrast for completeness / integrity handling |

## Proposed primary evaluation matrix

**Condition cell** = `(topology × scale_tier × scenario_bucket × fault_regime)`.

To avoid a blind full factorial explosion:

1. **Core topology×scale grid** (always): 6 topologies × 5 scales.
2. **Scenario rotation** (not full cross): assign scenarios round-robin across the grid (as in the pilot), plus a locked scenario hold-out subset.
3. **Fault regimes** (separate blocks):
   - Fault-free
   - One-fault-at-a-time (each fault type)
   - Small multi-fault subset (optional, later)

### Feasible minimum dataset (recommended floor)

| Block | Construction | Traces |
|-------|--------------|-------:|
| Clean core | 6 topologies × 5 scales × **3 seeds** (scenario rotated) | 90 |
| Fault block | 9 fault types × 6 topologies × **S1+S2 only** × **3 seeds** | 324 |
| Incomplete focus | `incomplete_trace` + `missing_dependency` × 6 topologies × S1 × 3 seeds | 36 |
| **Total (min)** | | **≈ 450** |

Approx. event volume (using pilot means ~340 events/trace as a rough upper guide, dominated by S3–S5 in the clean core):

- Clean core: order **10⁴–10⁵** events
- Full min corpus: order **10⁵** events

This is large enough for per-cell means with **n=3 seeds** but **not** a high-power multi-factor ANOVA without further assumptions.

### Stronger recommended dataset

| Block | Construction | Traces |
|-------|--------------|-------:|
| Clean core | 6 × 5 × **5 seeds** | 150 |
| Fault block | 9 × 6 × {S1,S2,S3} × **5 seeds** | 810 |
| Scenario locked replicate | 1 fixed scenario × 6 × 5 × 5 (clean) | 150 |
| **Total (strong)** | | **≈ 1,110** |

Approx. event volume: order **10⁵–10⁶** events depending on scale mix.

## Seeds and “independence”

- Use **distinct seeds** per cell (e.g. `1000 + cell_index * 10 + rep`).
- Seeds produce related traces from the same generator — treat as **exchangeable replicates under the generative model**, not as independent real-world sites.
- Do **not** invent a frequentist power calculation without stating effect size, variance, and test. Prefer:
  - Report **cell means ± bootstrap CI** over seeds (trace-level)
  - Pre-register contrasts (e.g. sequential vs hierarchical MFAV entropy)

## Partitions

| Partition | Use |
|-----------|-----|
| `pilot/` (existing 68 traces) | Generator development, regression, CI |
| `dev/` (optional small draw) | Tuning validators / notebooks |
| `eval/` (final corpus) | Frozen evaluation; generate once, checksum, never regenerate in-place |

**No ground-truth labels in algorithm inputs.** Eval runners may read GT only for scoring.

## Confidence intervals and comparisons

- Trace-level metrics (e.g. RPA conservation error, MFAV factor vector distance to a baseline, completeness flags).
- For each cell: mean over seeds, **percentile bootstrap CI** (e.g. 2.5–97.5%) when n≥5; for n=3 report range + mean transparently.
- Comparisons: paired by seed across topologies where applicable; avoid p-hacking across all cells — pre-specify primary contrasts.

## Explicit non-claims

- This plan does **not** assert that the pilot validates production multi-agent systems.
- Graph reachability from interventions is **not** causal ground truth.
- Larger N does not by itself create external validity.

## Generation policy (future phase)

- Pin `generator_version`, write manifests with full config fingerprints.
- Publish SHA-256 manifests for `eval/`.
- Do not overwrite `pilot/` when generating `eval/`.
