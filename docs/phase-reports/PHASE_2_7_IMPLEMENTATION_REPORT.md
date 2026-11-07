# PHASE 2.7 IMPLEMENTATION REPORT

PLHC: Provenance-Linked Hash Chain and Merkle integrity layer.

## 1. Starting branch and HEAD

| Item | Value |
|------|--------|
| Branch | `master` (no branch created or switched) |
| Start / expected HEAD | `421a55cfb4e0e07113c7374e064cd28df72f16bd` — MFAV intregrity closure |
| Working tree at start | Clean |
| Commit/push this phase | **Not performed** |

## 2. Files changed / added

**New package `agenttrust/integrity/`:**

- `canonicalization.py` — `agenttrust-canonical-json-v1`
- `hashing.py` — domain-separated SHA-256
- `leaves.py` — event / artifact / relationship leaves
- `merkle.py` — AgentTrust Merkle v1 + inclusion proofs (`L`/`R`/`P`)
- `checkpoint.py` — linked checkpoints
- `result.py` — snapshot / verification result types
- `verifier.py` — `PLHC` end-to-end API
- `__init__.py` — public exports

**Assurance / package:**

- `assurance/dimensions.py` — `evaluate_audit_integrity`
- `assurance/calculator.py` — optional `plhc_result`; algorithm `2.7.0`
- `assurance/models.py` — version `2.7.0`
- `agenttrust/__init__.py`, `pyproject.toml` → `2.7.0`

**Tests / scripts / docs:**

- `tests/unit/test_plhc.py`
- `experiments/scripts/validate_plhc.py`
- `experiments/scripts/evaluate_assurance_profiles.py` — PLHC round-trip fail-closed
- `docs/architecture/PHASE_2_7_PLHC.md`
- `docs/architecture/PHASE_2_6_ASSURANCE_PROFILE.md` — audit_integrity
- `docs/phase-reports/PHASE_2_6_2_1_IMPLEMENTATION_REPORT.md` — commit history correction
- `docs/phase-reports/PHASE_2_7_IMPLEMENTATION_REPORT.md` (this file)
- `README.md`

## 3. Algorithms and formats

- **Canonicalization:** deterministic UTF-8 JSON; sorted keys; reject NaN/Inf/unsupported types; version `agenttrust-canonical-json-v1`.
- **Leaves:** domain tags `AT|LEAF|{EVENT,ARTIFACT,RELATIONSHIP}|v1|`; artifact `storage_uri` excluded; OBSERVED_AFTER committed as observation.
- **Merkle:** binary tree; odd promote; empty root domain-tagged; inclusion proofs with `L`/`R`/`P`; format `agenttrust-merkle-v1` (**not** RFC 6962).
- **Checkpoints:** genesis `GENESIS`; contiguous sequences; optional explicit `created_at`; format `agenttrust-checkpoint-v1`.
- **Security claim:** tamper-evident vs retained checkpoint — **not** immutable; no external anchoring.

## 4. Assurance integration

Dimension `audit_integrity` maps PLHC `IntegrityVerificationResult` statuses. Absent PLHC → `unavailable`. Does not claim immutability.

## 5. Verification (actual runs)

```text
python -m pytest tests -q
# collected 397; passed 397; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0 incomplete=2 pipeline_eligible=66; exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0 fault_types=9 leakage_violations=0; exit 0

python experiments/scripts/validate_plhc.py
# pilot 68/68 verified; fault_matrix 10/10 verified; exit 0

python experiments/scripts/evaluate_assurance_profiles.py
# algorithm 2.7.0; audit_integrity verified on 68+10; n_errors=0; exit 0
```

Determinism: repeated `build_snapshot` yields identical roots (unit tests + PLHC validator). Adversarial coverage in `test_plhc.py` (canon, leaves, relationships, Merkle, checkpoints, e2e, assurance). Independently reproducible from checked-in corpora + code.

## 6. Known limitations

- Local rewrite of evidence **and** checkpoints still possible.
- No signatures / external anchors.
- No Merkle consistency proofs.
- Not RFC 6962.
- Does not prove occurrence, content truth, or causation.

## 7. Stop conditions

- Working tree: **dirty** (Phase 2.7 uncommitted).
- Remained on `master`; no branch created or switched.
- No commit or push performed.
- STOP after Phase 2.7 — do not begin Phase 2.8 until review.
