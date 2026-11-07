# Phase 2.6 / 2.6.1 — Evidence-Bounded Assurance Profile

## Purpose

The Assurance Profile is a **transparent, evidence-bounded assessment** of observable multi-agent execution records. It reports what can be said about:

- Trace completeness for analysis
- Typed structural reference integrity (and resolved fraction when references exist)
- Whether structural responsibility allocation (RPA) is computable and conserved
- Sensitivity of factor profiles across P1/P2 (when comparable under strict preconditions)
- Descriptive MFAV factor allocation

It does **not** measure inherent trustworthiness, honesty, intelligence, reliability, or probability of responsibility. It does **not** reconstruct hidden LLM reasoning. It does **not** prove causal or legal responsibility.

## Concept separation

| Concept | Meaning |
|---------|---------|
| Provenance validity | Records parse and form a typed graph |
| Evidence availability | Required observable fields/refs are present |
| Structural responsibility allocation | Conserved RPA mass on a projection |
| Assurance | Evidence-bounded status of the above dimensions |
| Causal responsibility | **Out of scope** |
| Trustworthiness | **Out of scope** (no CTSM trust score) |

## Status vocabulary

Every dimension carries exactly one status:

| Status | Meaning |
|--------|---------|
| `verified` | Required evidence present; checks passed under documented rules |
| `incomplete` | Some required evidence missing; partial assessment possible |
| `contradicted` | Internal inconsistency among available evidence |
| `unavailable` | Dimension cannot be computed (missing inputs, zero denominator, incomparable) |
| `not_applicable` | Dimension does not apply to this case |

**Precedence** (for aggregate “worst status” summaries):  
`contradicted` > `incomplete` > `unavailable` > `not_applicable` > `verified`.

Never replace missing information with zero, a default confidence, or an arbitrary constant.

A profile with any `contradicted` or `incomplete` required dimension **cannot** have overall status `verified`.

## Shared dimension result fields

Each dimension result includes:

- `dimension_id`
- `value` (numeric/structured or `null`)
- `status`
- `evidence_refs` (event/artifact/result identifiers used)
- `rule_id` (calculation/rule identifier)
- `warnings`
- `explanation`
- `limitations`

## Dimension A — Trace completeness

**Meaning.** Whether the loaded provenance completeness report indicates a complete, incomplete, or structurally invalid dependency situation for DAG analysis.

**Inputs.** `ProvenanceTrace.completeness()` only (no ground truth).

**Rule `assurance.completeness.v1_1`:**

| Condition | Status | Value |
|-----------|--------|-------|
| `incomplete=False` and `suitable_for_dag_attribution=True` and no dependency cycle | `verified` | `"complete"` |
| `incomplete=True` and no dependency cycle | `incomplete` | `"incomplete"` |
| dependency cycle | `contradicted` | `"invalid"` |
| otherwise unclassifiable | `unavailable` | `null` |

**Unexpected missing parents** surface as `incomplete` via the completeness report. Wrong-namespace references are handled under reference integrity (`contradicted`), not by inventing GT-based excuses.

**Intentional vs unexpected incompleteness** is **not** decided inside the profile calculator (that would require ground truth). Evaluation harnesses may annotate planted incompleteness separately using GT.

**Limits.** Completeness ≠ trustworthiness; incomplete ≠ agent fault. Missing optional metadata (e.g. `model_id`) does not make a trace incomplete.

## Dimension B — Reference integrity (typed; Phase 2.6.1 consolidation)

**Meaning.** Typed referential validity of required lineage references, plus a resolved fraction when \(n>0\).

**Phase 2.6.1 decision.** Prior Phase 2.6 exposed both `reference_integrity` and `provenance_coverage` with the **same** untyped numerator/denominator (\(r \in K_e \cup K_a\)). That duplicated a single quantity and incorrectly accepted cross-namespace IDs. Research meaning:

- Reference integrity must report **typed** referential validity (event refs → events only; artifact refs → artifacts only).
- A separate “coverage” dimension would need a genuinely distinct property. No such distinct, non-invented coverage property is available from current records without inventing optional-evidence penalties.

**Therefore:** `provenance_coverage` is **removed**. One dimension `reference_integrity` reports typed resolution counts and fraction.

**Inputs.** `trace.events`, `trace.artifacts` only.

**Rule `assurance.reference_integrity.v1_1`:**

Collect required references as `(owner_event_id, ref_type, target_id)`:

| Field | Namespace |
|-------|-----------|
| `dependency_event_ids` | event |
| `invokes_event_ids` | event |
| `retries_event_id` | event |
| `input_artifact_ids` | artifact |
| `output_artifact_ids` | artifact |

Resolution classes:

- `resolved` — target exists in the **correct** namespace
- `wrong_namespace` — target exists only in the **other** namespace
- `missing` — target exists in neither

Optional metadata (`model_id`, `tool_id`, …) is **never** required.

Let \(n\) be the number of collected refs, \(n_{\mathrm{resolved}}\) those resolved in-namespace.

\[
C = \frac{n_{\mathrm{resolved}}}{n} \quad (n>0)
\]

| Condition | Status | Value |
|-----------|--------|-------|
| \(n>0\) and no wrong-namespace and no missing | `verified` | structured counts + fraction \(C=1\) |
| \(n>0\) and any wrong-namespace | `contradicted` | counts + `wrong_namespace` list (owner, ref_type, target_id) |
| \(n>0\) and missing only | `incomplete` | counts + `missing` list |
| \(n=0\) | `unavailable` | `null` |

## Dimension C — Attribution computability

**Meaning.** Whether a provided `RPAResult` is a valid conserved structural allocation for the requested projection, or why not.

**Inputs.** Optional `RPAResult` (caller supplies; profile does not silently invent allocations). If absent → `unavailable`.

**Rule `assurance.attribution_computability.v1_2` (Phase 2.6.2 fail-closed):**

Tolerances (absolute): conservation \(10^{-9}\); reported↔recomputed agreement \(10^{-9}\); non-negativity float allowance \(10^{-12}\).

Before `verified`, all of the following must hold:

1. Conservation dict present with required keys `abs_error_from_one_nodes`, `sum_node_allocations` (missing → `unavailable`; never treated as zero).
2. Required conservation values numeric (not bool), finite, non-negative (within float allowance).
3. Independently recompute \(S=\sum_v a(v)\) from `node_allocations` and \(\epsilon=|S-1|\); reported sum and abs-error must agree within agreement tolerance.
4. Every node allocation numeric, finite, non-negative (within float allowance); empty map → `contradicted`.
5. \(0 \le \alpha \le 1\) and α finite.
6. `cycle_diagnostics.has_cycle` must be false (else `contradicted`).
7. \(\epsilon \le 10^{-9}\).
8. Incomplete/overridden guards → `incomplete` (never `verified`), even when conservation is valid.

| Condition | Status |
|-----------|--------|
| Valid conserved consistent result, no cycle, no incomplete guards | `verified` |
| Valid under incomplete/overridden conditions | `incomplete` |
| Malformed / non-finite / inconsistent / negative / non-conserved / cycle / bad α | `contradicted` |
| Missing RPA result or missing required conservation fields | `unavailable` |

Value includes projection kind, alpha, conservation summary, cycle flag, warnings. Conserved allocation ≠ causal responsibility.

## Dimension D — Attribution sensitivity

**Meaning.** Descriptive difference between P1 and P2 MFAV normalized factor vectors for the **same** outcome, when both pass strict preconditions.

**Inputs.** Optional pair `(MFAVResult_P1, MFAVResult_P2)`.

**Preconditions (`assurance.attribution_sensitivity.v1_1`):**

1. Both results provided
2. `mfav_p1.projection_kind` is exactly `P1_DIRECT`
3. `mfav_p2.projection_kind` is exactly `P2_ARTIFACT_BRIDGE`
4. Same `outcome_id`
5. Both normalized vectors defined
6. Both vectors have **exactly** the exclusive taxonomy factor keys (no zero-fill of missing keys)
7. Every value finite and non-negative
8. Each vector sums to 1 within absolute tolerance \(10^{-9}\)

Failed identity/outcome/missing-input preconditions → `unavailable`. Failed numeric/support preconditions → `contradicted`.

**Definition.** Let \(M^{P1}, M^{P2}\) be validated normalized factor vectors over exclusive factor set \(F\):

\[
\delta = \tfrac{1}{2}\sum_{f\in F}\lvert M^{P1}_f - M^{P2}_f\rvert \in [0,1]
\]

**δ measures descriptive allocation sensitivity only** — not uncertainty, causal disagreement, or fault probability.

## Dimension E — Factor profile

**Meaning.** Descriptive exclusive MFAV factor allocation for one outcome/projection.

**Inputs.** Optional `MFAVResult`.

**Rule `assurance.factor_profile.v1_2` (Phase 2.6.2.1):** does **not** trust `MFAVStatus.COMPLETE` alone. Missing factors are **not** zero-filled. Missing evidence is **never** replaced with zero.

When claiming `verified` for a complete profile, validate:

1. Exact exclusive taxonomy factor-key support on raw and normalized maps.
2. Normalized values numeric, finite, non-negative; sum to 1 within \(10^{-9}\).
3. Raw values numeric, finite, non-negative.
4. \(T_{\mathrm{reported}}\approx T_{\mathrm{factors}}=\sum_f A_f\) within `REPORT_AGREEMENT_TOL` (\(10^{-9}\)).
5. Every `EventAssignment`: non-empty `event_id`, taxonomy factor, finite non-negative allocation; **no duplicate event IDs**.
6. \(T_{\mathrm{events}}=\sum_e a(e)\approx T_{\mathrm{factors}}\).
7. Per-factor aggregation: \(A_f \approx \sum_{e:\mathrm{factor}(e)=f} a(e)\) for every exclusive factor.
8. Independently recompute \(\epsilon_{\mathrm{MFAV}}=\lvert T_{\mathrm{factors}}-T_{\mathrm{events}}\rvert\); reported `conservation_error` must agree within \(10^{-9}\); for COMPLETE \(\epsilon_{\mathrm{MFAV}}\le 10^{-9}\).
9. `outcome_id` and `projection_kind` present and non-empty.

(Empty assignments with positive \(T_{\mathrm{factors}}\) → `contradicted`. Missing assignment list → `unavailable`.)

| Condition | Status |
|-----------|--------|
| COMPLETE + validated vectors/assignments/totals/ε | `verified` |
| Valid but incomplete/overridden | `incomplete` |
| Duplicate IDs / bad factors / non-finite / aggregation inconsistency | `contradicted` |
| No MFAV / ZERO / UNDEFINED / missing normalized or assignment evidence | `unavailable` |

Value embeds raw/normalized factors (including `other`), conservation error, MFAV status, assignment count. Factor concentration/entropy are **not** computed as trust scores.

## Dimension F — Audit integrity (Phase 2.7)

**Rule `assurance.audit_integrity.v1`:** maps an optional PLHC `IntegrityVerificationResult` into Assurance statuses. Absent PLHC → `unavailable`. Valid retained checkpoint match → `verified`. Tampering / broken chain → `contradicted`. Never claims immutability or external trust. See [PHASE_2_7_PLHC.md](PHASE_2_7_PLHC.md).

## Profile API

```text
AssuranceProfileCalculator.compute(
    trace: ProvenanceTrace,
    *,
    rpa_result: RPAResult | None = None,
    mfav_result: MFAVResult | None = None,
    mfav_p1: MFAVResult | None = None,
    mfav_p2: MFAVResult | None = None,
    plhc_result: IntegrityVerificationResult | None = None,
) -> AssuranceProfile
```

- Deterministic for identical inputs
- Does not mutate trace/graph/RPA/MFAV
- Does not read benchmark ground truth
- No single scalar “trust score”
- Algorithm version `2.7.0`

## Evaluation runner (fail-closed)

`experiments/scripts/evaluate_assurance_profiles.py`:

- Accounts for every trace directory
- Records a profile outcome or an explicit error per trace
- Writes diagnostics under `experiments/results/assurance_phase26/`
- Exits non-zero if any trace/corpus evaluation error occurred
- Does not silently skip unsupported traces

## Explicit exclusions

No CTSM weighted trust score; no hardcoded policy/model confidence; no PLHC/Merkle; no causal/legal claims; no final eval corpus generation; no RPA/MFAV math changes.
