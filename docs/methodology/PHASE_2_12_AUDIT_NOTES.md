# Phase 2.12 audit notes

## Dead / placeholder code (retained intentionally)

| Item | Disposition |
|------|-------------|
| `agenttrust/attribution/baselines.py` | Historical “not implemented” stubs; active baselines live in `agenttrust/evaluation/baselines.py`. Left in place to avoid breaking old imports; documented as non-results. |
| `legacy/` | Historical prototype; not active. |
| Markov B3 | Explicitly not independently implemented (protocol). |

## Cleanup performed

- Public README rewritten without phase-status tables.
- Environment / threat-model / claim-evidence / reproducibility docs added.
- Package version set to `2.12.0`.
- Staged `reproduce.py` + run manifests + repeatability checker.

## Not performed (by design)

- Broad unreviewed deletions.
- Held-out metric “improvements.”
- Pinning every Cursor ambient package.
- Overwriting frozen `experiments/results/phase_2_10` or `final_evaluation` (gitignored scratch used instead).
