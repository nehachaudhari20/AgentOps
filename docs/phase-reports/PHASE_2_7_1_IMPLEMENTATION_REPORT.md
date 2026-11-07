# PHASE 2.7.1 IMPLEMENTATION REPORT

PLHC cryptographic verification hardening.

## 1. Starting branch and HEAD

| Item | Value |
|------|--------|
| Branch | `master` (no branch created or switched) |
| Start / expected HEAD | `3b9ee6f8645a4c4c6a8b607ca24e908dbcf68f05` — Add PLHC layer |
| Working tree at start | Clean |
| Commit/push this phase | **Not performed** |

## 2. Changes

### Merkle v2 + structural proofs
- Leaf hash binds `leaf_id` + `content_hash` via canonical JSON.
- Format `agenttrust-merkle-v2`; historical v1 proofs rejected (not reinterpreted).
- `expected_proof_sides(index, count)` enforces exact `L`/`R`/`P` sequence; extra/missing/wrong steps fail.

### Digests / checkpoints
- `digests.py`: strict 64-hex SHA-256 normalization; non-boolean non-negative ints.
- Checkpoint format `agenttrust-checkpoint-v2` binds `merkle_format_version`.
- Creation/verification reject unsupported algorithms and versions.
- Chain prefix verification does not claim complete history.

### Snapshot/checkpoint compatibility
- `verify_against_checkpoint` compares canonicalization, hash algorithm, Merkle format, root, and leaf count.

### Assurance
- `assurance.audit_integrity.v1_1` revalidates evidence before accepting claimed VERIFIED.
- Non-genesis without predecessor → incomplete (not verified).
- Algorithm version → **`2.7.1`**.

## 3. Files

- `agenttrust/integrity/{digests,hashing,merkle,checkpoint,result,verifier}.py`
- `agenttrust/assurance/{dimensions,models}.py`
- `agenttrust/__init__.py`, `pyproject.toml`
- `tests/unit/test_plhc_271.py`, updates to `test_plhc.py` / assurance version tests
- Docs: `PHASE_2_7_PLHC.md`, `PHASE_2_7` history correction, this report, `README.md`

## 4. Verification (actual)

```text
python -m pytest tests -q
# collected 424; passed 424; exit 0

python experiments/scripts/validate_benchmark_pilot.py --pipeline
# checked=68 failures=0; exit 0

python experiments/scripts/validate_phase25_fault_matrix.py
# checked=10 failures=0; exit 0

python experiments/scripts/validate_plhc.py
# pilot 68/68; fault_matrix 10/10; exit 0
# (Merkle roots differ from Phase 2.7 v1 — expected under v2 migration)

python experiments/scripts/evaluate_assurance_profiles.py
# algorithm 2.7.1; audit_integrity verified 68+10; n_errors=0; exit 0
```

## 5. Backward compatibility

- Merkle v1 roots/proofs are **not** accepted by the v2 verifier.
- Checkpoint v1 objects lacking `merkle_format_version` fail validation.
- Corpora are rebuilt at verification time; no historical expected-root fixtures are silently rewritten — the documented version bump explains root changes.

## 6. Residual risks

- Local replacement of evidence **and** checkpoints still possible.
- No signatures / external anchoring.
- Valid chain prefix ≠ proof of complete history.
- In-process VERIFIED objects are rechecked but are not an external root of trust.

## 7. Stop

- Working tree: **dirty** (2.7.1 uncommitted).
- Remained on `master`; no branch created or switched.
- No commit or push performed.
- STOP after Phase 2.7.1 — do not start Phase 2.8 until review.
