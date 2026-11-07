# Phase 2.6 — Evidence-Bounded Assurance Profile

## Purpose

The Assurance Profile is a **transparent, evidence-bounded assessment** of observable multi-agent execution records. It reports what can be said about:

- Trace completeness for analysis
- Structural reference integrity
- Provenance coverage of recorded lineage references
- Whether structural responsibility allocation (RPA) is computable and conserved
- Sensitivity of factor profiles across P1/P2 (when comparable)
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

**Rule `assurance.completeness.v1`:**

| Condition | Status | Value |
|-----------|--------|-------|
| `incomplete=False` and `suitable_for_dag_attribution=True` and no dependency cycle | `verified` | `"complete"` |
| `incomplete=True` and no dependency cycle | `incomplete` | `"incomplete"` |
| dependency cycle or unsuitable for DAG attribution with cycle evidence | `contradicted` | `"invalid"` |
| completeness unavailable | `unavailable` | `null` |

**Intentional vs unexpected incompleteness** is **not** decided inside the profile calculator (that would require ground truth). Evaluation harnesses may classify planted incompleteness separately using GT.

**Limits.** Completeness ≠ trustworthiness; incomplete ≠ agent fault.

## Dimension B — Reference integrity

**Meaning.** Whether dependency, invocation, retry, and artifact references resolve to known event/artifact IDs in the loaded trace.

**Inputs.** `trace.events`, `trace.artifacts` only.

**Rule `assurance.reference_integrity.v1`:**

Collect required references:

- each `dependency_event_ids` entry
- each `invokes_event_ids` entry
- `retries_event_id` if set
- each `input_artifact_ids` / `output_artifact_ids` entry

Let \(R\) be that multiset, \(K_e\) known event ids, \(K_a\) known artifact ids.

\[
n_{\mathrm{ok}} = |\{r \in R : r \in K_e \cup K_a\}|,
\quad
n = |R|
\]

| Condition | Status | Value |
|-----------|--------|-------|
| \(n>0\) and \(n_{\mathrm{ok}}=n\) | `verified` | `{"resolved": n_ok, "total": n, "fraction": 1}` |
| \(n>0\) and \(0 \le n_{\mathrm{ok}} < n\) | `incomplete` | fraction \(n_{\mathrm{ok}}/n\) |
| \(n=0\) | `unavailable` | `null` (no required refs) |

Unexplained missing refs are reported in evidence; GT is not used to “excuse” them inside the calculator.

## Dimension C — Provenance coverage

**Meaning.** Fraction of required lineage references that resolve.

**Definition (same \(n_{\mathrm{ok}}, n\) as B):**

\[
C = \frac{n_{\mathrm{ok}}}{n} \quad (n>0)
\]

| Condition | Status | Value |
|-----------|--------|-------|
| \(n>0\) and \(C=1\) | `verified` | \(C\) |
| \(n>0\) and \(C<1\) | `incomplete` | \(C\) |
| \(n=0\) | `unavailable` | `null` |

Optional metadata absence (e.g. missing `model_id`) is **not** counted in the denominator.

## Dimension D — Attribution computability

**Meaning.** Whether a provided `RPAResult` is a valid conserved structural allocation for the requested projection, or why not.

**Inputs.** Optional `RPAResult` (caller supplies; profile does not silently invent allocations). If absent → `unavailable`.

**Rule `assurance.attribution_computability.v1`:**

| Condition | Status |
|-----------|--------|
| Result present, no cycle flag, conservation abs error ≤ \(10^{-9}\), no overridden guards that break validity claims | `verified` |
| Overridden incomplete guard or incomplete completeness flag | `incomplete` |
| Cycle / conservation abs error > tolerance | `contradicted` |
| No RPA result provided | `unavailable` |

Value includes projection kind, alpha, conservation summary, cycle flag, warnings. Conserved allocation ≠ causal responsibility.

## Dimension E — Attribution sensitivity

**Meaning.** Descriptive difference between P1 and P2 MFAV normalized factor vectors for the **same** outcome, when both are defined.

**Inputs.** Optional pair `(MFAVResult_P1, MFAVResult_P2)` with matching `outcome_id` and defined normalized vectors.

**Definition.** Let \(M^{P1}, M^{P2}\) be normalized factor vectors over exclusive factor set \(F\):

\[
\delta = \tfrac{1}{2}\sum_{f\in F}\lvert M^{P1}_f - M^{P2}_f\rvert \in [0,1]
\]

(total variation distance).

| Condition | Status |
|-----------|--------|
| Both vectors defined, same outcome | `verified` (δ is descriptive, not “fault”) |
| Either undefined / outcomes differ / missing inputs | `unavailable` |

**Limits.** δ ≠ uncertainty, ≠ agent fault, ≠ causal disagreement.

## Dimension F — Factor profile

**Meaning.** Descriptive exclusive MFAV factor allocation for one outcome/projection.

**Inputs.** Optional `MFAVResult`.

| Condition | Status |
|-----------|--------|
| MFAV complete with defined normalized vector | `verified` |
| MFAV incomplete/overridden/zero | `incomplete` or `unavailable` per MFAV status |
| No MFAV result | `unavailable` |

Value embeds raw/normalized factors (including `other`), conservation error, MFAV status. Factor concentration/entropy are **not** computed as trust scores.

## Profile API (design)

```text
AssuranceProfileCalculator.compute(
    trace: ProvenanceTrace,
    *,
    rpa_result: RPAResult | None = None,
    mfav_result: MFAVResult | None = None,
    mfav_p1: MFAVResult | None = None,
    mfav_p2: MFAVResult | None = None,
) -> AssuranceProfile
```

- Deterministic for identical inputs
- Does not mutate trace/graph/RPA/MFAV
- Does not read benchmark ground truth
- No single scalar “trust score”

## Explicit exclusions

No CTSM weighted trust score; no hardcoded policy/model confidence; no PLHC/Merkle; no causal/legal claims; no final eval corpus generation; no RPA/MFAV math changes.

## Unit / property tests (planned)

- Complete vs incomplete traces
- Missing / invalid references
- Zero-denominator coverage → unavailable
- RPA conservation / cycle / missing result
- P1/P2 comparable and incomparable cases
- MFAV integration
- Determinism and no mutation
- Calculator never imports/reads ground truth
- Generator version mismatch hard-fails strict validation
