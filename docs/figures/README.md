# Paper figures (Figs. 2–6)

ACM-ready PDF + PNG (300 DPI) generated from live AgentTrust artifacts.

## Regenerate

```bash
python experiments/scripts/generate_paper_figures.py --out docs/figures
# optional: --only 2 3
```

## Files

| Figure | Files | Source |
|-------|-------|--------|
| Fig. 2 | `fig02_mlpg_example.{pdf,png}` | Pilot sequential S1 clean MLPG excerpt |
| Fig. 3 | `fig03_p1_vs_p2_bridge.{pdf,png}` | Phase 2.13 `multi_stage_artifact_chain` |
| Fig. 4 | `fig04_plhc_integrity.{pdf,png}` | Live PLHC snapshot + checkpoint verify |
| Fig. 5 | `fig05_eval_design_splits.{pdf,png}` | `experimental_2_9` split coverage / stats |
| Fig. 6 | `fig06_phase213_results.{pdf,png}` | Phase 2.13 held-out RQ JSON + power report |

## Suggested captions

- **Fig. 2.** Example event–artifact Multi-Layer Provenance Graph (MLPG) excerpt from a sequential S1 clean pilot trace. Circles denote events; squares denote artifacts. Edge styles encode DEPENDS_ON, PRODUCES, and CONSUMES.

- **Fig. 3.** P1 vs P2 attribution projections on the Phase 2.13 `multi_stage_artifact_chain` bridge scenario. P1 contains no event–event edges; P2 adds derived ARTIFACT_BRIDGE edges along PRODUCES→CONSUMES paths.

- **Fig. 4.** Provenance-Linked Hash Chain (PLHC) construction and verification relative to a retained checkpoint (Merkle v2). Clean verification succeeds; an event-payload attack is detected when the checkpoint is held honest. Not a claim of immutability or external anchoring.

- **Fig. 5.** Experimental evaluation design for corpus `experimental_2_9`: development / validation / held-out split sizes (trace = independent unit), held-out role composition, and topology coverage. Matched clean/fault pairs remain within splits.

- **Fig. 6.** Phase 2.13 held-out results: RQ1 edge F1 (simulator lineage fidelity); RQ2 MAE under equal-root (structurally aligned with RPA α=0) and intervention participation; RQ3 paired P2−P1 Δ; RQ5 PLHC attack detection with Wilson intervals; paired McNemar power at n=72.

## Notes

- Prefer **PDF** for camera-ready inclusion; PNG is for drafts/slides.
- Do not invent metrics when regenerating: Fig. 6 requires `experiments/results/phase_2_13/heldout_test_rq_summary.json`.
- Manifest: `generation_manifest.json`.
