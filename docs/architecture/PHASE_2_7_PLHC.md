# Phase 2.7 — PLHC: Provenance-Linked Hash Chain

## Threat model

**Adversary:** Can modify local event/artifact/relationship records, leaf sets, Merkle roots, or checkpoint files after evidence is written.

**Asset:** A retained integrity checkpoint (Merkle root + linked checkpoint hash) that the verifier trusts as the commitment reference.

**Goal:** Detect unauthorized modification, insertion, deletion, or reordering of committed evidence relative to that checkpoint.

## Security properties

| Property | Provided? |
|----------|-----------|
| Tamper evidence vs retained checkpoint | **Yes** |
| Deterministic reproducibility of roots | **Yes** |
| Inclusion proofs for individual leaves | **Yes** |
| Local-only immutability | **No** |
| External anchoring / signatures | **No** (out of scope) |
| Proof that an event “really happened” | **No** |
| Causal validity of relationships | **No** |
| Truthfulness of artifact content | **No** (only consistency with declared `content_hash`) |

**Honest boundary:** An attacker who rewrites *both* the evidence store *and* all retained checkpoints can forge a consistent alternate history. PLHC is tamper-evident relative to an independently retained or trusted checkpoint — not inherently immutable.

## Non-goals

- PLHC does not replace RPA/MFAV mathematics.
- No CTSM trust score.
- No Merkle consistency proofs (inclusion only in 2.7 / 2.7.1).
- No RFC 6962 compliance claim (construction is AgentTrust Merkle **v2**).
- No signing / TSA / blockchain anchoring.

## Canonicalization profile (`agenttrust-canonical-json-v1`)

Deterministic UTF-8 JSON:

- Object keys sorted by Unicode code-point order (`sort_keys=True`).
- Separators `(',', ':')` — no insignificant whitespace.
- `ensure_ascii=False`, `allow_nan=False`.
- Accepted types: `null`, `bool`, `int` (not bool), finite `float`, `str`, arrays, objects with string keys.
- Rejected: NaN, ±Inf, non-string keys, arbitrary objects, `repr()` dumps.

Timestamps in commitments use schema `format_timestamp` (ISO-8601 UTC with `Z`).

**Not** RFC 8785 / JCS. Version string is bound into checkpoints so profile changes cannot silently reinterpret historical hashes.

### Examples

```text
{"b":1,"a":2}  →  {"a":2,"b":1}
True ≠ 1 ≠ 1.0 ≠ "1" ≠ null
```

## Leaf commitments

Domain-separated content hash: `SHA-256(DS || canonicalize(payload))`.

| Kind | Domain tag | Leaf ID |
|------|------------|---------|
| Event | `AT\|LEAF\|EVENT\|v1\|` | `event:{event_id}` |
| Artifact | `AT\|LEAF\|ARTIFACT\|v1\|` | `artifact:{artifact_id}` |
| Relationship | `AT\|LEAF\|RELATIONSHIP\|v1\|` | `rel:{ordinal}:{type}:{src_ns}:{src}:{tgt_ns}:{tgt}` |

### Event payload fields (included)

`event_id`, `trace_id`, `event_type`, `category`, `agent_id`, `status`, `ts_start`, `ts_end`, `input_artifact_ids`, `output_artifact_ids`, `dependency_event_ids`, `invokes_event_ids`, `retries_event_id`, `observed_after_event_ids`, `schema_version`, `model_id`, `tool_id`, `metadata` (sorted `[k,v]` pairs).

### Artifact payload fields

`artifact_id`, `artifact_type`, `content_hash`, `schema_version`, `metadata`.

**Excluded:** `storage_uri` (private/relocatable pointer), raw payloads, credentials.

### Relationship payload fields

`ordinal`, `rel_type`, `source_namespace`, `source_id`, `target_namespace`, `target_id`, `derived`, `evidence`.

Namespaces: EVENT↔EVENT for DEPENDS_ON/INVOKES/RETRIES/OBSERVED_AFTER; EVENT→ARTIFACT for PRODUCES; ARTIFACT→EVENT for CONSUMES.

`OBSERVED_AFTER` is committed as a typed observation — **not** interpreted as causation.

Duplicate stable IDs rejected before tree construction. Leaves ordered by `leaf_id`.

## Merkle construction (`agenttrust-merkle-v2`)

Phase 2.7.1 migration from v1 → v2 (breaking hash change; old roots are not reinterpreted).

- Leaf hash: `SHA-256(AT|MERKLE|LEAF|v2| || canonicalize({leaf_id, content_hash}))`  
  **Binds leaf identity** — changing only `leaf_id` on a proof fails.
- Node hash: `SHA-256(AT|MERKLE|NODE|v2| || left || "|" || right)`
- Odd count: last hash **promoted** unchanged
- Empty tree root: `SHA-256(AT|MERKLE|EMPTY|v2|)`
- Inclusion proof steps: `L`/`R` (combine) or `P` (promote)

**Structural proof validation:** from `(leaf_index, leaf_count)` reconstruct the exact expected `L`/`R`/`P` sequence; reject extra/missing/wrong steps even if a forged root could otherwise be computed. Historical `agenttrust-merkle-v1` proofs are **rejected**, never silently verified under v2.

**Not** claiming RFC 6962. Consistency proofs not implemented.

## Checkpoint chain (`agenttrust-checkpoint-v2`)

Bound fields: `sequence_number`, `previous_checkpoint_hash`, `merkle_root`, `leaf_count`, `canonicalization_version`, `hash_algorithm`, `checkpoint_format_version`, **`merkle_format_version`**, `created_at` (optional ISO-8601).

Digests must be exactly 64 hex chars (normalized lowercase). Integers must be non-boolean and non-negative. Unsupported algorithms/versions are rejected at creation and verification.

- Genesis: `sequence_number=0`, `previous_checkpoint_hash="GENESIS"`.
- Contiguous sequences required; self-hash recomputed.
- A valid chain **prefix** proves integrity of the supplied sequence only — **not** that no later checkpoint exists.
- Checkpoint hash: `SHA-256(AT|CHECKPOINT|v1| || canonicalize(payload))`.

## Verification procedure

1. Rebuild leaves from `ProvenanceTrace` (no mutation).
2. Rebuild Merkle root (v2).
3. Verify checkpoint field validity, self-hash, and previous link.
4. Compare rebuilt root, leaf count, **and format/algorithm versions** to checkpoint.
5. Optionally verify structurally validated inclusion proofs.

Statuses: `verified` | `contradicted` | `unavailable` | `incomplete`.

## Assurance Profile integration

Dimension `audit_integrity` (`assurance.audit_integrity.v1_1`):

Caller-supplied `IntegrityVerificationResult.status == VERIFIED` is **not** trusted alone. Before mapping to Assurance `verified`, the calculator rechecks snapshot/checkpoint digests, format agreement, rebuilt Merkle root, checkpoint self-hash, and genesis/predecessor link evidence (`checkpoint_link_verified` / `previous_checkpoint`).

| Condition | Assurance status |
|-----------|------------------|
| absent PLHC result | `unavailable` |
| claimed VERIFIED + complete consistent evidence | `verified` |
| claimed VERIFIED + missing snapshot/checkpoint | `unavailable` |
| claimed VERIFIED + non-genesis without predecessor | `incomplete` |
| malformed / mismatched evidence | `contradicted` |
| claimed incomplete / unavailable / contradicted | same |

Never infers immutability or external trust from local verification. In-process objects ≠ trusted external checkpoint.

## Complexity

- Canonicalization: O(size of evidence JSON)
- Leaf construction: O(E + A + R)
- Merkle build: O(N) hashes for N leaves
- Inclusion proof: O(log N) steps
- Checkpoint verify: O(1) per checkpoint; O(K) for chain length K

## Residual risks

- Local rewrite of evidence **and** checkpoints.
- No external root of trust in Phase 2.7.
- Canonicalization profile upgrades require explicit version bumps.
- Relationship ordinals depend on deterministic sort of the relationship set; set membership changes still change the root.
