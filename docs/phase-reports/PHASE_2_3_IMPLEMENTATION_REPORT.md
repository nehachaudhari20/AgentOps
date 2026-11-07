# PHASE 2.3 IMPLEMENTATION REPORT

## 1. Branch and starting commit

| Item | Value |
|------|--------|
| Working branch | `master` (per project preference; no research branch used for delivery) |
| Start commit | `98686da0fb443692cd4c96bb6a4ecfaab6c0d643` (Phase 2.2 baseline) |
| Commits by agent | **None** (uncommitted work on `master`) |

## 2. Objective

Implement MFAV — Multi-Factor Accountability Vector: exclusive factor-level aggregation of conserved RPA allocations into an evidence-bounded accountability profile.

## 3. Schema extension (backward compatible)

Optional fields on `EventRecord` (absent ⇒ unobserved; never inferred):

| Field | Purpose |
|-------|---------|
| `model_id` | Explicit model identity |
| `tool_id` | Explicit tool identity |
| `metadata` | Non-sensitive tags (e.g. `subtype=memory`) |

Existing Phase 2.1 records without these fields continue to validate. `SCHEMA_VERSION` remains `2.1.0` for record compatibility. Graph builder stores the optional fields on EVENT nodes when present.

## 4. MFAV architecture

```text
agenttrust/accountability/
  __init__.py
  taxonomy.py      # factors, versions, secondary tags
  classifier.py    # exclusive category_primary_v1 mapping
  aggregator.py    # factor + entity aggregation, conservation
  result.py        # MFAVResult / entity / assignment types
  mfav.py          # public MFAV API
```

Pipeline: `ProvenanceTrace → MLPG → P1/P2 → ConservedRPA → MFAV`.

## 5. Mapping policy

Policy id: `category_primary_v1` / taxonomy `2.3.0`.

- INSTRUCTION → prompt
- REASONING → agent (or model if `model_id`)
- RETRIEVAL / KNOWLEDGE → data
- TRANSFORMATION → data (or tool if `tool_id`)
- TOOL → tool
- DECISION → execution
- OTHER → other

Memory is a secondary `data` subtype only when explicit metadata supports it.

## 6. RPA note (`allow_cycles`)

ConservedRPA still requires a DAG. The previous `allow_cycles=True` path marked an override then failed inside topological sort. Corrected: `allow_cycles=True` now raises an explicit “not implemented” error. Documented in architecture notes; dedicated regression test added. RPA mathematics unchanged.

## 7. Changed files

### Active implementation

- `agenttrust/schema/event.py` — optional `model_id`, `tool_id`, `metadata`
- `agenttrust/validation/validator.py` — validate optional fields
- `agenttrust/mlpg/graph_builder.py` — persist optional fields on EVENT nodes
- `agenttrust/attribution/rpa.py` — clarify/reject cyclic `allow_cycles`
- `agenttrust/accountability/*` — full MFAV package
- `agenttrust/__init__.py` — export `MFAV`, version `2.3.0`
- `pyproject.toml` — version `2.3.0`

### Tests

- `tests/unit/test_mfav.py` — classification, aggregation, conservation, completeness, P1/P2, determinism, mutation guards
- `tests/property/test_mfav_conservation.py` — random valid allocations conserve; exclusive mapping
- `tests/unit/test_rpa.py` — `allow_cycles` unsupported regression

### Documentation

- `docs/architecture/PHASE_2_3_MFAV.md`
- `docs/phase-reports/PHASE_2_3_IMPLEMENTATION_REPORT.md`
- `docs/architecture/PHASE_2_2_RPA.md` — cycle-guard clarification
- `README.md` — MFAV status and usage

## 8. Raw data integrity

| File | SHA-256 |
|------|---------|
| `data/raw/events.json` | Unchanged from Phase 2.2 baseline (`E52558BB…` — re-verified at report time) |

No migration rewrite of historical values; optional fields remain absent on old records.

## 9. Test command and results

```bash
python -m pytest tests -q
```

| Metric | Value |
|--------|--------|
| Collected | **202** |
| Passed | **202** |
| Failed | 0 |
| Baseline (Phase 2.2 report) | 126 |
| Exit code | 0 |

Raw SHA-256 of `data/raw/events.json` (unchanged):

`E52558BB4BD329EE6D7FC41A793F76FBE4873AE91E6384C11DA7D7D5A05FA3EB`

## 10. Acceptance checklist

| Criterion | Status |
|-----------|--------|
| Phase 2.1 tests pass | Yes |
| Phase 2.2 tests pass | Yes |
| New MFAV tests pass | Yes |
| Raw data unchanged | Yes |
| RPA math unchanged (α=0 conserved flow) | Yes |
| Factor totals conserve incoming RPA mass | Yes |
| Normalized vector sums to 1 when defined | Yes |
| Exclusive primary-factor mapping | Yes |
| No fabricated model/entity identity | Yes |
| No epsilon normalization | Yes |
| Docs + README updated | Yes |
| Commit / push | **Not performed** (per instructions) |

## 11. Out of scope (not started)

- Assurance Profile / CTSM
- PLHC / Merkle integrity
- Trust scoring, causal attribution, Shapley/Markov baselines
- Benchmark generation / performance claims
- Phase 2.4
