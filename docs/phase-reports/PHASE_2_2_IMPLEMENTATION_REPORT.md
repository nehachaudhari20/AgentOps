# PHASE 2.2 IMPLEMENTATION REPORT

## 1. Branch and starting commit

| Item | Value |
|------|--------|
| Start branch | `master` (clean) |
| Start commit | `affc798e4581b4d908404a859ad68d2cad0c10f5` (Phase 2.1) |
| Implementation branch | `research/phase-2.2-rpa` |
| Commits by agent | **None** (uncommitted work on branch) |

## 2. Before / after repository tree (summary)

**Before (Phase 2.1 root):** `agenttrust/`, root-level legacy packages (`provenance_graph/`, `attribution/`, …), `data/raw_events/`, `data/processed_events/`, flat `tests/`, root `PHASE_2_1_IMPLEMENTATION_REPORT.md`.

**After:**

```text
agenttrust/          # sole active implementation
legacy/              # relocated prototype
data/{raw,processed,benchmarks,fixtures}/
experiments/{configs,scripts,results}/
tests/{unit,integration,property,fixtures}/
docs/{architecture,phase-reports,methodology,research}/
outputs/historical/
pyproject.toml
```

## 3. File moves and rationale

| Move | Rationale |
|------|-----------|
| Root prototype dirs → `legacy/` | Separate historical baseline from active `agenttrust/` |
| `data/raw_events/events.json` → `data/raw/events.json` | Immutable source location; **SHA-256 unchanged** `E52558BB…05FA3EB` |
| `data/processed_events/*` → `data/processed/` | Transformed records location |
| Phase reports → `docs/phase-reports/` | Predictable research documentation |
| `docs/PHASE_2_1_MLPG.md` → `docs/architecture/` | Architecture docs home |
| Legacy PDFs → `outputs/historical/` | Do not present as new experimental results |
| Tests → `tests/unit|integration|property` | Clear test taxonomy |
| Empty `config/*.yaml` → `experiments/configs/` | Active experiment configuration home |
| Empty `evaluation/*` → `legacy/evaluation/` | Prototype stubs, not active metrics |
| Tracked `__pycache__/*.pyc` removed from index | Hygiene; files ignored going forward |

## 4. Compatibility changes

- Legacy experiment `EVENT_PATH` updated to `data/raw/events.json`.
- Legacy demos require `PYTHONPATH=legacy` (documented in `legacy/README.md`).
- Migration CLI reads/writes `data/raw` and `data/processed`.
- Active imports remain `from agenttrust ...` (no `sys.path` hacks).

## 5. Packaging changes

- Added `pyproject.toml` (setuptools, pytest `pythonpath`, package discovery excluding `legacy*`).
- `requirements.txt` retained as convenience pins; **pyproject.toml is source of truth**.
- Expanded `.gitignore` for caches, venvs, and scratch results.

## 6. RPA mathematical formulation

Conserved backward flow on event-only DAG projections (P1/P2):

- Initialise \(f(o)=1\), \(a(v)=0\).
- Reverse-topo (stable ranking): roots absorb remaining flow; non-roots retain \(\alpha\cdot f(v)\) and forward \((1-\alpha)\cdot f(v)\) equally among parents.
- **Approved baseline \(\alpha=0\)**: intermediates retain **no** local share; roots absorb; \(\sum_v a(v)=1\) and \(\sum_{\mathrm{roots}} a(r)=1\).
- Equal parent split is a **structural convention**, not causal measurement.
- Multiple outcomes: independent runs; no silent aggregation.
- Incomplete / cyclic projections rejected unless explicitly overridden (results marked).

See `docs/architecture/PHASE_2_2_RPA.md`.

## 7. Exact alpha interpretation

\(\alpha=0\) means **root-allocation baseline**: mass is fully forwarded until absorbed at in-degree-0 nodes. It does **not** mean every intermediate is fully accountable; intermediates receive \(a(v)=0\) under the baseline.

## 8. Conservation tests and results

- Unit tests: linear, branch, shared ancestor, multi-outcome, disconnected, P1 vs P2, guards, determinism, α∈{0,1} boundaries.
- Property tests: 20 random DAGs × 4 alpha values — mass conserved to \(10^{-12}\).
- Sample processed loan trace (P1): conservation abs error from 1 within float tolerance.

## 9. P1 / P2 comparisons

Synthetic bridge-only case: P1 allocates all mass to the consumer (no edge); P2 bridges via artifact and allocates to producer. Original provenance fingerprint unchanged after projection/RPA.

On the migrated loan sample, P1 and P2 edge counts match (explicit deps already cover bridges), so root allocations match for that dataset.

## 10. Test output

```text
python -c "from agenttrust import ProvenanceTrace, ConservedRPA"  # OK
python -m pytest tests -q
# 126 passed
```

(Exact count from Phase 2.2 verification run: all tests green.)

## 11. Limitations and open questions

- Parent policy currently only `equal_parents`.
- Shapley / Markov baselines are **interfaces only** (`baselines.py`).
- Alpha sweeps available via `sensitivity.sweep_alpha` but α≠0 is experimental.
- Legacy package is relocated, not re-validated end-to-end beyond path updates.
- MFAV / Assurance / PLHC still unimplemented.

## 12. Confirmation: MFAV, Assurance, PLHC not implemented

Only empty package initialisers / reserved modules exist under:

- `agenttrust/accountability/`
- `agenttrust/assurance/`
- `agenttrust/integrity/`

No trust scoring, hash-chain redesign, or MFAV redesign was added.

## Raw dataset integrity

| When | SHA-256 of `data/raw/events.json` |
|------|-----------------------------------|
| Phase 2.2 start (as `data/raw_events/events.json`) | `E52558BB4BD329EE6D7FC41A793F76FBE4873AE91E6384C11DA7D7D5A05FA3EB` |
| After moves + RPA work | `E52558BB4BD329EE6D7FC41A793F76FBE4873AE91E6384C11DA7D7D5A05FA3EB` |

## Recommended next step

Await approval for **Phase 2.3 — MFAV** (or packaging/commit of this branch). Do not start without explicit approval.

## Suggested commit (for you)

```powershell
git add .
git commit -m "Phase 2.2: restructure repository and implement conserved RPA."
```
