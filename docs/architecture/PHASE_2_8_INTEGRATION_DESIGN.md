# Phase 2.8 — Integration Design (pre-implementation)

## Goal

Single deterministic pipeline: load → validate → MLPG → P1/P2 → RPA → MFAV → PLHC → Assurance → machine-readable result.

## Reused APIs

| Stage | API |
|-------|-----|
| Load/validate/graph | `ProvenanceTrace.load_records`, `completeness()`, `fingerprint()`, `project()` |
| RPA | `ConservedRPA.allocate` / `allocate_from_trace`, `evaluate_attribution_computability` |
| MFAV | `MFAV.compute`, `evaluate_factor_profile` |
| PLHC | `PLHC.build_snapshot`, `create_checkpoint`, `verify_against_checkpoint` |
| Assurance | `AssuranceProfileCalculator.compute` with RPA/MFAV/PLHC results |

## Dimension inventory (actual)

After Phase 2.6.1, dimensions are: `trace_completeness`, `reference_integrity`, `attribution_computability`, `attribution_sensitivity`, `factor_profile`, `audit_integrity`.  
**`provenance_coverage` was consolidated into typed `reference_integrity`** — not reintroduced.

## Gaps addressed

1. No single orchestration module — add `agenttrust/pipeline/`.
2. Overlapping eval scripts — new `evaluate_agenttrust.py` is the primary E2E runner; existing scripts remain specialized validators.
3. GT leakage risk — pipeline I/O loads only `events.json` / `artifacts.json`; never opens `ground_truth/`.
4. Partial failures — per-component status recorded; corpus exit fail-closed on hard errors.

## Non-goals

No new RPA/MFAV math, no trust score, no Phase 2.9, no algorithm semantic changes.
