# Claim–evidence matrix (Phase 2.12)

Sources: `docs/results/FINAL_EVALUATION_REPORT.md`, `experiments/results/final_evaluation/`, architecture docs.

| Research claim | Evidence artifact | Evaluation | Limitation | Status |
|----------------|-------------------|------------|------------|--------|
| MLPG reconstructs observable generator lineage with high edge F1 | `final_evaluation/heldout_test_rq_summary.json` RQ1; FINAL_EVALUATION_REPORT RQ1 | Held-out n=798; DEPENDS_ON F1≈0.999; PRODUCES/CONSUMES F1=1.0 | Not causal inference | **Supported** |
| ConservedRPA matches equal-root synthetic agent reference (MAE≈0) | Phase 2.10 comparison + RQ2 summary | n_scored=738 | Reference structurally aligned with RPA α=0; not causal/legal proof | **Partially supported / qualified** |
| Uniform / last-touch baselines differ from equal-root reference | RQ2 table (B0 MAE≈0.23; B1≈0.65) | Held-out | Synthetic reference only | **Supported (relative to this GT)** |
| P2 improves attribution over P1 | RQ3 paired Δ | mean Δ=0, CI [0,0], n=738 | Artifact bridges often dedupe with DEPENDS_ON; GT not discriminative | **Not supported** |
| Assurance flags intentional incompleteness | RQ4 sample n=100 | det≈0.89; FAR=0 | Not all fault families; not fraud detection | **Partially supported** |
| PLHC detects listed local tampers vs retained checkpoint | RQ5 n=50; PLHC attack JSONs | detection=1.0; FRR=0 | Local tamper-evidence ≠ immutability/signatures/anchoring | **Supported (scoped)** |
| Framework measures agent trustworthiness | — | — | Explicitly out of scope | **Unsupported — do not claim** |
| Framework establishes legal liability | — | — | Explicitly out of scope | **Unsupported — do not claim** |
| W3C PROV / RFC 6962 compliance | — | — | Not implemented | **Unsupported — do not claim** |
| Production multi-agent validation | — | — | Synthetic only | **Unsupported — do not claim** |
| Reconstructs hidden model reasoning | — | — | Explicitly out of scope | **Unsupported — do not claim** |
