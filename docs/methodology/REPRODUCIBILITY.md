# Reproducibility instructions

## Quick start

```bash
pip install -e ".[dev]"
python experiments/scripts/reproduce.py --all-safe
```

Stages are logged separately. Default scratch outputs go to `experiments/results/repro_scratch/` and **do not** overwrite frozen evaluation directories.

Frozen comparison/statistical JSON under `experiments/results/phase_2_10` and `final_evaluation` are **gitignored**; regenerate locally with the Phase 2.10/2.11 scripts if needed.

## Stage reference

| Stage | Command | Notes |
|-------|---------|-------|
| env | `reproduce.py --stage env` | Import smoke |
| dataset_validate | `--stage dataset_validate` | Experimental corpus catalogs |
| dataset_regenerate | `--stage dataset_regenerate --regenerate-dataset` | Explicit only |
| pipeline | `--stage pipeline` | Pilot trace smoke |
| baselines | `--stage baselines` | Dev split limit=3 |
| stats | `--stage stats` | Uses frozen comparison if present |
| repeatability | `--stage repeatability` | Dual-run deterministic equality |
| tests | `--stage tests` | `pytest tests -q` |
| validators | `--stage validators` | Pilot, fault matrix, PLHC, assurance |

## Determinism expectation

For fixed seeds and frozen inputs: provenance fingerprints, RPA/MFAV allocations, and PLHC roots are expected **bit-identical** (floats within `1e-12`). Wall-clock timings are excluded from content hashes.

## Dataset fingerprints

See `data/benchmarks/experimental_2_9/design_fingerprint.json` and each split’s `fingerprint_manifest.json`.
