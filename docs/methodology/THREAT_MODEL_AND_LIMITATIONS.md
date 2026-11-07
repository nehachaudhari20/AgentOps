# Threat model and limitations (research freeze)

## In scope

| Boundary | Guarantee |
|----------|-----------|
| Algorithm inputs vs ground truth | GT lives in separate files; pipeline/baselines must not read GT as inputs |
| Typed references | Fail-closed validation for event/artifact ID kinds |
| RPA / MFAV | Conservation fail-closed under documented tolerances |
| Assurance Profile | Evidence-bounded dimension statuses; not a trust score |
| PLHC | Tamper-evident Merkle + checkpoint verification **relative to a retained checkpoint** |

## Out of scope (explicit)

- Immutable storage, WORM media, or append-only cloud logs
- Cryptographic signatures / PKI
- External anchoring (e.g. RFC 6962 Certificate Transparency style)
- W3C PROV compliance certification
- Reconstruction of hidden LLM reasoning
- Causal or legal liability attribution
- Production multi-agent system validation
- Universal agent “trustworthiness” scoring

## PLHC threat model (precise)

A verifier that retains an honest checkpoint can detect modifications to the protected evidence set that change the Merkle root, leaf count, format versions, or checkpoint binding.

A **local-only** hash chain does **not** imply:

- that evidence cannot be rewritten if the checkpoint is also rewritten,
- that an adversary without the checkpoint cannot forge an alternate chain,
- that events occurred in the real world,
- or that artifact content is truthful.

## Dataset / evaluation limitations

- Synthetic generator evidence only (experimental corpus `2.5.1`; historical pilot `2.4.0`).
- Trace is the independent unit; nested events are not N.
- Equal-root attribution reference is structurally aligned with RPA α=0 → weak RQ2/RQ3 discrimination; intervention reference undefined on clean traces.
- RQ1 measures reconstruction fidelity vs simulator declarations, not independent real-world lineage recovery.
- RQ4 is diagnostic (completeness + observability), not comprehensive fault detection.
- RQ5 is tamper-evidence vs retained checkpoint, not immutability.
- Phase 2.9 corpus often has DEPENDS_ON covering artifact paths → empty bridge subgroup; see `experimental_2_13_bridges`.
- Markov baseline not independently implemented (equivalence to RPA α=0 documented).
- Paired power supersedes Phase 2.9 independent two-proportion planning figures.
