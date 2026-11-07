# Phase 2.13 Claim–Evidence Matrix

| Claim | Implementation evidence | Experimental evidence | Limitation | Allowed wording |
|-------|-------------------------|----------------------|------------|-----------------|
| MLPG reconstructs simulator-declared lineage with high edge F1 | `rq1_lineage_fidelity`; graph builder; negative relationship diagnostics | Held-out RQ1 F1≈1.0 (historical); stratified re-run in phase_2_13 | Synthetic oracle ≠ production recovery | “Reconstruction fidelity vs simulator-declared lineage” |
| Equal-root MAE≈0 for ConservedRPA α=0 | `equal_root_ancestor_mass.v1`; ALIGNMENT_DISCLOSURE | RQ2 MAE≈0 | Structural alignment with RPA α=0 | “Consistent with equal-root structural reference; not independent accuracy” |
| Intervention participation reference is independent of RPA | `build_intervention_attribution_reference`; GT independence tests | Eligible only when interventions exist | Undefined on clean; not causal/legal | “Planted intervention participation mass (when defined)” |
| Uniform / last-touch differ from equal-root | Baselines B0/B1 | RQ2 B0≈0.23, B1≈0.65 | Relative to aligned GT only | “Worse under equal-root synthetic reference” |
| P2 improves attribution over P1 | P1/P2 projections; bridge corpus | Phase 2.9 Δ=0, bridge n=0; bridge corpus shows graph differentiation | Graph difference ≠ MAE improvement under aligned GT | “P2 adds artifact bridges when DEPENDS_ON absent; MAE superiority not demonstrated” |
| Assurance flags intentional incompleteness | Assurance dimensions; observability matrix | RQ4 det≈0.89 historical sample; stratified 2.13 | Not all fault families | “Diagnostic incompleteness signaling” |
| Unobservable faults excluded from ordinary FN | `ObservabilityClass.NOT_RELIABLY_DETECTABLE` | RQ4 observability-aware tables | Requires correct class declarations | “Excluded from ordinary Assurance FN denominators” |
| PLHC detects listed tampers vs retained checkpoint | PLHC + expanded attacks | RQ5 detection≈1.0 with CIs (stratified) | Not immutability | “Tamper-evident relative to retained checkpoint” |
| Paired power for 72 incompleteness pairs | `simulate_paired_power` / McNemar | `sample_size_power_2_13.json` | Grid assumptions; pilot joint rates uncertain | Report simulated power only; no independent-z citation |
| Framework measures agent trustworthiness | — | — | Out of scope | **Do not claim** |
| Causal / legal liability | — | — | Out of scope | **Do not claim** |
| Immutability / external anchoring | — | — | Out of scope | **Do not claim** |
| Production multi-agent validation | — | — | Synthetic only | **Do not claim** |
