# PHASE 2.10 IMPLEMENTATION REPORT

Baselines, comparative evaluation, and ablation configurations.

## 1. Branch / HEAD

| Item | Value |
|------|--------|
| Branch | `master` |
| Start HEAD | `dfb45c0` — Benchmark expansion (Phase 2.9) |
| Working tree at start | Clean |
| Commit/push | **Not performed in-phase** (unless separately requested) |

## 2. Protocol

`docs/methodology/BASELINE_AND_ABLATION_PROTOCOL.md` — locked input contract, methods, paired P2−P1 comparison, ablations, split usage.

## 3. Implementations

| Component | Location |
|-----------|----------|
| Result schema | `agenttrust/evaluation/schema.py` |
| Metrics | `agenttrust/evaluation/metrics.py` |
| Baselines B0/B1/B2/RPA/Shapley | `agenttrust/evaluation/baselines.py` |
| Comparison runner | `agenttrust/evaluation/compare.py` |
| PLHC attacks | `agenttrust/evaluation/plhc_attacks.py` |
| CLI | `experiments/scripts/run_baseline_comparison.py` |

### Method status

- **B0** uniform-agent — implemented (online).
- **B1** last-touch — implemented (online; non-causal).
- **B2** — alias of RPA P1 α=0 (documented, not independent).
- **B3** Markov — **not implemented independently** (identical to RPA α=0 under equal-parent reverse flow).
- **B4** Shapley reachability — implemented (offline combinatorial; exact ≤12 agents).
- **rpa_p1 / rpa_p2** — ConservedRPA α=0.
- **Alpha ablation** — α ∈ {0, 0.25, 0.5, 0.75, 1.0} on P1.

## 4. Outputs

`experiments/results/phase_2_10/` — per-split comparison JSON + PLHC attack samples + run summary.

## 5. Tests

`tests/unit/test_evaluation_210.py` — metrics, baselines, determinism, GT separation, PLHC detection.

## 6. Held-out policy

Development and validation run first. Held-out executed only with frozen configs (same CLI flags) for confirmatory artifacts consumed by Phase 2.11.

## 7. Limitations

- Synthetic equal-root GT ≠ causal responsibility.
- B3 absent as independent method.
- Shapley optional in bulk runs (cost).
- No universal framework score.
