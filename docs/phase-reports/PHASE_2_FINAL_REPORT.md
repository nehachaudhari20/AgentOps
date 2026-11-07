# Phase 2 Final Report — Research Freeze

## 1. Repository state

| Item | Value |
|------|--------|
| Branch | `master` |
| HEAD at Phase 2.12 start | `2645da23a88f2fc62688452ac4222732a98ef707` — Add baselines, ablations, and statistical evaluation |
| Package version | `2.12.0` |
| Commit/push this freeze | **Not performed** (unless separately requested) |

## 2. Final architecture

Observable events/artifacts → typed MLPG (P1/P2) → Conserved RPA → MFAV → PLHC (Merkle v2 + checkpoints) → Assurance Profile dimensions → evaluation baselines/metrics.

Orchestration: `AgentTrustPipeline`. Experimental unit: **trace**.

## 3. Implemented components

| Component | Location | Version notes |
|-----------|----------|---------------|
| Schema / validation / MLPG | `agenttrust/schema`, `validation`, `mlpg` | schema 2.1.x |
| Conserved RPA | `agenttrust/attribution` | algorithm 2.2.0 |
| MFAV | `agenttrust/accountability` | 2.3.0 |
| Benchmarks | `agenttrust/benchmark` | generator 2.5.1; pilot historical 2.4.0 |
| Assurance | `agenttrust/assurance` | 2.7.1 |
| PLHC | `agenttrust/integrity` | merkle/checkpoint v2 |
| Pipeline | `agenttrust/pipeline` | result format v1 |
| Evaluation | `agenttrust/evaluation` | baselines/metrics/RQ |
| Repro | `agenttrust/repro` | run manifests |

## 4. Datasets and fingerprints

| Corpus | Role | Notes |
|--------|------|-------|
| `data/benchmarks/pilot/` | Historical regression | gen 2.4.0; 68 traces |
| `data/benchmarks/experimental_2_9/` | Dev/val/held-out | 276 / 522 / 798 traces; gen 2.5.1 |
| Design fingerprint | `experimental_2_9/design_fingerprint.json` | |
| Split fingerprints | `splits/*/fingerprint_manifest.json` | held-out prefix `a4512469…` |

Ground truth is separate from algorithm inputs (`ground_truth/`).

## 5. Ground-truth methodology

- Lineage, interventions, structural, quality packages.
- Attribution reference: `equal_root_ancestor_mass.v1` (not causal; structurally close to RPA α=0).

## 6. Baselines and ablations

See `docs/methodology/BASELINE_AND_ABLATION_PROTOCOL.md`.  
B3 Markov not independently implemented. B2 is RPA-P1 alias.

## 7. RQ definitions and results

See `docs/results/FINAL_EVALUATION_REPORT.md` and `CLAIM_EVIDENCE_MATRIX.md`.

| RQ | Freeze verdict |
|----|----------------|
| RQ1 lineage F1 | Supported |
| RQ2 vs equal-root GT | Partially supported / qualified |
| RQ3 P2 vs P1 | Not supported (Δ=0) |
| RQ4 incompleteness | Partially supported |
| RQ5 PLHC tampers | Supported (local threat model) |

## 8. Statistical procedures

Trace-level bootstrap CIs; paired Δ for RQ3; Holm available in metrics helpers; confirmatory focus held-out. Plan: `STATISTICAL_ANALYSIS_PLAN.md`.

## 9. Reproducibility

- Env: `docs/methodology/ENVIRONMENT.md`
- Stages: `python experiments/scripts/reproduce.py --all-safe`
- Repeatability: `check_repeatability.py`
- Threat model: `THREAT_MODEL_AND_LIMITATIONS.md`

## 10. Validation outcomes (Phase 2.12 execution — actual)

```text
python -m pytest tests -q
# collected 474; all passed; exit 0

python experiments/scripts/check_repeatability.py
# ok=true; n_diffs=0; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0; exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0; exit 0

python experiments/scripts/validate_plhc.py
# pilot 68/68; fault_matrix 10/10; exit 0

python experiments/scripts/evaluate_assurance_profiles.py
# n_errors=0; exit 0

python experiments/scripts/validate_experimental_dataset.py --max-trace-checks 10
# ok=true; n_traces=1596; cross-split isolation ok; exit 0

python experiments/scripts/reproduce.py --stage env --stage pipeline --stage baselines --stage repeatability
# all stages exit 0; manifest written under experiments/results/repro_scratch/
```

Tested OS/Python: Windows 11 / Python 3.13.9; networkx 3.5; numpy 2.2.6.

## 11. Limitations and unsupported claims

Removed/qualified in public docs:

- No production validation.
- No legal liability / causal responsibility.
- No hidden-reasoning reconstruction.
- No universal trust score.
- No W3C PROV / RFC 6962 / immutability / external anchoring claims.
- Equal-root GT limits RQ2/RQ3 discrimination.

## 12. Remaining known issues

1. Frozen evaluation JSON under `experiments/results/` is gitignored — local regenerate required for offline audit of raw comparison files.
2. Shapley not in bulk held-out tables.
3. RQ4 uses sampled incompleteness contrast, not all fault types as detection targets.
4. Python 3.10–3.12 not re-tested in this freeze pass (declared ≥3.10; executed on 3.13.9).

## 13. Research readiness assessment

**Phase 2 research prototype is frozen for audit/reproduction** with explicit limitations. Suitable as synthetic-benchmark evidence for ACM TRUST–style methodology discussion. **Not** a production assurance product.
