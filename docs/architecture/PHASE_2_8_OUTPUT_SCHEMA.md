# Phase 2.8 — Output schema (`agenttrust-pipeline-result-v1`)

## Trace result (`TracePipelineResult`)

| Field | Type | Notes |
|-------|------|-------|
| `format_version` | string | `agenttrust-pipeline-result-v1` |
| `trace_id` | string | Trace directory name or supplied id |
| `ok` | bool | Fail-closed overall success |
| `hard_error` | string\|null | Fatal orchestration / IO / component failure summary |
| `input_fingerprint_sha256` | string\|null | Hash of events+artifacts bytes |
| `provenance_fingerprint` | string\|null | MLPG graph fingerprint |
| `config` | object | Public `PipelineConfig` |
| `config_fingerprint` | string | SHA-256 of canonical config JSON |
| `versions` | object | schema / RPA / assurance / package / format |
| `validation` | object | `ValidationReport.to_dict()` |
| `graph_summary` | object | node/edge counts + completeness |
| `projection_eligibility` | object | per P1/P2 eligibility + edge counts |
| `rpa` | object | `{status, reason, results[]}` with per-outcome validation |
| `mfav` | object | `{status, reason, results[]}` with per-outcome validation |
| `plhc` | object | snapshot summary, checkpoint, verification, optional inclusion |
| `assurance` | object | `{status, reason, profiles[]}` |
| `warnings` | string[] | Non-fatal notices |
| `errors` | string[] | Component-level error messages |
| `timing_ms` | object\|null | Wall timings; **excluded** from deterministic hashes |

`deterministic_payload()` returns `to_dict()` without `timing_ms`.

### Component status vocabulary

`ok` | `partial` | `failed` | `skipped` | `ineligible`

### RPA/MFAV validation status

`verified` | `incomplete` | `contradicted` | `unavailable` (from independent evidence validators)

## Corpus summary (`CorpusPipelineSummary`)

| Field | Meaning |
|-------|---------|
| `n_examined` | Trace directories visited |
| `n_eligible` | Examined minus structurally ineligible (e.g. no outcomes) |
| `n_ineligible` | No outcome candidates |
| `n_success` | `ok=True` |
| `n_failed` | `ok=False` |
| `n_hard_errors` | IO / load failures with no provenance fingerprint |
| `trace_ids_*` | Sorted id lists |
| `corpus_fingerprint_sha256` | Hash of all events+artifacts under corpus |

Corpus exit is fail-closed: any `n_failed` or `n_hard_errors` → CLI exit 1.
