# PHASE 2.5 IMPLEMENTATION REPORT

Benchmark audit, ground-truth integrity, and fault-semantics hardening.

## 1. Starting commit and branch

| Item | Value |
|------|--------|
| Branch | `master` only |
| Start commit (Phase 2.5 work began from) | `77aa635ac32ac6945ef88a923ea9553b1b04acfa` — `Add benchmark` |
| Phase 2.5 implementation commit | **`583b57ad213c22f219eaa3cc906fd3569d9a3bbe`** — `harden benchmark ground-truth integrity and fault semantics` |
| Phase 2.5.1 | Corrective follow-up on top of `583b57a` (see §14); not a rewrite of Phase 2.5 historical results |

> An earlier draft of this report stated Phase 2.5 made no commits. That was true only before landing; the implementation is represented by **`583b57a`**.

## 2. Files inspected and changed

### Inspected

- `agenttrust/benchmark/{faults,generator,ground_truth,manifest,validation}.py`
- `agenttrust/mlpg/projections.py`, `graph_builder.py`, `validation/validator.py`
- `experiments/scripts/validate_benchmark_pilot.py`
- Checked-in pilot under `data/benchmarks/pilot/` (not overwritten)

### Changed / added

| Path | Change |
|------|--------|
| `agenttrust/benchmark/faults.py` | Hardened semantics; added `tool_call_failure`; GT-only expected hashes |
| `agenttrust/benchmark/validation.py` | Comprehensive GT consistency + intentional-defect awareness + adversarial hooks |
| `agenttrust/benchmark/generator.py` | Manifest fault_types from interventions; corruption IDs from GT |
| `agenttrust/benchmark/manifest.py` | `GENERATOR_VERSION=2.5.0` |
| `agenttrust/benchmark/__init__.py` | Export `validate_package`, `load_and_validate_trace_dir` |
| `tests/unit/test_benchmark_integrity.py` | Fault semantics + 12 adversarial + MultiDiGraph fidelity tests |
| `experiments/scripts/validate_benchmark_pilot.py` | Stricter package validation; pipeline stats |
| `experiments/scripts/check_benchmark_reproducibility.py` | Non-destructive regen comparison |
| `docs/methodology/BENCHMARK_DESIGN.md` | Phase 2.5 semantics |
| `docs/methodology/FINAL_EXPERIMENTAL_DATASET_PLAN.md` | Evaluation corpus design |
| `docs/phase-reports/PHASE_2_4_IMPLEMENTATION_REPORT.md` | Corrected commit status note |
| `docs/phase-reports/PHASE_2_5_IMPLEMENTATION_REPORT.md` | This report |

## 3. Defects found

1. **`incorrect_tool_output` conflated tool crash with wrong content** — forced `status=failure` and overwrote hashes while naming the fault “incorrect output.”
2. **`artifact_corruption` leaked a `corrupted=true` label** into algorithm-facing artifact metadata and omitted an independently retained expected hash in GT.
3. **`delegation_failure` mixed missing-callee and callee-failed** without an explicit mode.
4. **`retry_storm` reused parent output artifact IDs** on clones (weak semantic consistency).
5. **Validator was shallow** — did not systematically check lineage/intervention/manifest agreement or intentional vs accidental missing refs.
6. **Phase 2.4 report incorrectly stated work was uncommitted** after `77aa635` landed.
7. **Pilot summary paths used Windows backslashes** (serialization hygiene; fixed for future generation).

## 4. Corrections implemented

- Split **incorrect successful content** vs **tool_call_failure**.
- Corruption / incorrect-output: store `expected_content_hash` + `observed_content_hash` in intervention parameters only; remove algorithm-facing corruption labels.
- Delegation: explicit `mode` ∈ {`missing_callee`, `callee_failed`}.
- Retry storm: unique per-retry artifacts, `dependency_event_ids`, verified MLPG `RETRIES`.
- Validator: full GT consistency suite; intentional missing refs allowed when declared; fingerprint reconciliation for historical quality-bit vs request-flag mismatch.
- Generator version stamped **2.5.0** for new generations; **pilot corpus retained as 2.4.0**.

## 5. Fault semantics table

| Fault | Algorithm-facing change | GT representation | Detectable without GT? |
|-------|-------------------------|-------------------|------------------------|
| `missing_dependency` | Phantom id in `dependency_event_ids` | Intervention + quality missing refs | Yes (incomplete) |
| `incorrect_tool_output` | `status=success`, wrong artifact hash | expected/observed hashes in intervention | Hash anomaly only with GT expected |
| `tool_call_failure` | `status=failure` | Intervention mode `status_failure` | Yes |
| `artifact_corruption` | Hash → sentinel | expected/observed in GT | Hash anomaly only with GT expected |
| `retry_storm` | Extra retry events + artifacts | retry ids; lineage retries | Yes (RETRIES edges) |
| `delegation_failure` | Phantom INVOKES or callee `failure` | mode + ids | Yes |
| `conflicting_agent_outputs` | (Phase 2.5) used `conflict_label` — **superseded in 2.5.1** by structured `decision` values + distinct hashes; relation only in GT | expected_decisions / relation in GT | Yes, from decision/hash disagreement (2.5.1) |
| `incomplete_trace` | Event removed | removed id + dependents | Yes (dangling deps) |
| `misleading_delayed_observation` | `observed_after_event_ids` w/o DEPENDS_ON | observer/early ids | Yes; must not enter P1/P2 |

## 6. Ground-truth validation rules (summary)

- Unique event/artifact/intervention IDs
- Manifest counts and fault types agree with files / interventions
- Trace IDs agree across directory, manifest, GT
- Lineage refs exist unless intentional missing event/ref
- Intervention affected IDs accounted for
- Structural agent/model/tool/category agreement
- No `gt_*` metadata in algorithm inputs
- Config fingerprint verifiable (with documented historical incomplete-flag caveat)
- Fault observables checked when `check_fault_observables=True`
- `OBSERVED_AFTER` excluded from P1/P2; `RETRIES`/`INVOKES` present in MLPG when both endpoints exist

## 7. Adversarial tests added

`tests/unit/test_benchmark_integrity.py` covers unknown GT event/artifact refs, wrong manifest counts, duplicate intervention IDs, mismatched trace IDs, declared-but-absent faults, prohibited `gt_*` labels, intervention without observable effect, inconsistent corruption evidence, missing retry parent, MultiDiGraph multi-rel retention, and OBSERVED_AFTER projection exclusion.

## 8. Reproducibility findings

Command: `python experiments/scripts/check_benchmark_reproducibility.py`

| Metric | Value |
|--------|------:|
| Clean traces compared | 60 |
| Exact stripped-field match | **60** |
| Faulted traces skipped (expected 2.4≠2.5) | 8 |
| Pilot overwritten | **No** |

## 9. Actual test outputs

```bash
python -m pytest tests -q
```

| Metric | Value |
|--------|------:|
| Collected | **241** |
| Passed | **241** |
| Failed | **0** |
| Exit code | **0** |
| Prior baseline (Phase 2.4 / commit `77aa635`) | 219 |

## 10. Pilot validation outputs

```bash
python experiments/scripts/validate_benchmark_pilot.py --pipeline
```

| Metric | Value |
|--------|------:|
| Traces checked | **68** |
| Failures | **0** |
| Ground-truth error total | **0** |
| Intentionally incomplete | **2** |
| Pipeline-eligible | **66** |
| Exit code | **0** |

> Phase 2.4 historical pilot statistics (68 traces / 23190 events / …) are preserved as Phase 2.4 results and are **not** re-stated as Phase 2.5 experimental findings.

## 11. Final experimental dataset design summary

See `docs/methodology/FINAL_EXPERIMENTAL_DATASET_PLAN.md`.

- Feasible minimum ≈ **450** traces; stronger ≈ **1,110** traces
- Trace-level analysis; seeds as generative replicates
- Separate `pilot` / `eval` partitions; no GT leakage

**Not generated in this phase.**

## 12. Remaining limitations (as of Phase 2.5 / `583b57a`)

- On-disk pilot remains generator `2.4.0`; faulted traces do not match later generator semantics until a future regen into a new directory
- Historical pilot validation without `--strict-fault-observables` does **not** certify Phase 2.5 fault-observable semantics
- No statistical evaluation performed

## 13. Explicitly not implemented

- Assurance Profile / CTSM
- PLHC / Merkle integrity
- RPA/MFAV math changes
- Final eval corpus generation
- Causal attribution claims

## 14. Phase 2.5.1 corrective follow-up

**Base commit:** `583b57ad213c22f219eaa3cc906fd3569d9a3bbe`  
**Active generator after 2.5.1:** `2.5.1`  
**Pilot corpus:** unchanged (`2.4.0`)

### Issues closed

1. Removed `conflict_label` / equivalent answer markers from algorithm-facing conflicting-output artifacts; disagreement is carried by structured `decision` values and distinct `content_hash` values, with `relation=mutually_inconsistent_decisions` only in GT.
2. Validator rejects `conflict_label`, `is_conflicting`, and related leakage keys.
3. Documented and separated validation modes:
   - **Mode A:** `validate_benchmark_pilot.py [--pipeline]` — historical pilot consistency / pipeline
   - **Mode B:** `validate_phase25_fault_matrix.py` — fresh 2.5.x generator + strict fault observables
4. Expanded per-fault semantics tests; dataset plan total corrected to ≈ **1,110**.

### Commands and results (executed in Phase 2.5.1)

See `docs/phase-reports/PHASE_2_5_1_IMPLEMENTATION_REPORT.md` for full tables.

| Command | Result |
|---------|--------|
| `python -m pytest tests -q` | **262 passed**, exit 0 |
| `validate_benchmark_pilot.py --pipeline` (Mode A) | 68 checked, 0 failures, 66 pipeline-eligible |
| `validate_phase25_fault_matrix.py` (Mode B) | 10 checked, 0 failures, 9 fault types, 0 leakage violations |

Historical pilot Mode A does **not** claim strict Phase 2.5.1 fault semantics for 2.4.0 fault fixtures (`conflict_label` may appear as warnings only).
