"""
AgentTrust end-to-end pipeline orchestration (Phase 2.8).

Reuses existing ProvenanceTrace / ConservedRPA / MFAV / PLHC / Assurance APIs.
Does not invent new attribution mathematics. Does not read ground truth.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional, Sequence

from agenttrust.accountability.aggregator import MFAVError
from agenttrust.accountability.mfav import MFAV
from agenttrust.accountability.result import MFAVResult
from agenttrust.assurance.calculator import AssuranceProfileCalculator
from agenttrust.assurance.models import ASSURANCE_ALGORITHM_VERSION
from agenttrust.attribution.rpa import ALGORITHM_VERSION as RPA_VERSION
from agenttrust.attribution.rpa import ConservedRPA, RPAConfig, RPAError, RPAResult
from agenttrust.integrity.result import IntegrityStatus
from agenttrust.integrity.verifier import PLHC
from agenttrust.mlpg.graph_builder import graph_fingerprint
from agenttrust.mlpg.projections import ProjectionKind
from agenttrust.pipeline.io import (
    PipelineIOError,
    corpus_fingerprint,
    load_trace_inputs,
)
from agenttrust.pipeline.models import (
    PIPELINE_FORMAT_VERSION,
    CorpusPipelineSummary,
    PipelineConfig,
    TracePipelineResult,
)
from agenttrust.pipeline.validation import (
    mfav_usable_for_assurance,
    rpa_usable_for_assurance,
    validate_mfav_result,
    validate_rpa_result,
)
from agenttrust.provenance_trace import ProvenanceTrace
from agenttrust.schema.enums import SCHEMA_VERSION


def _versions() -> dict[str, str]:
    return {
        "pipeline_format": PIPELINE_FORMAT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "rpa_algorithm_version": RPA_VERSION,
        "assurance_algorithm_version": ASSURANCE_ALGORITHM_VERSION,
        "agenttrust_package_version": "2.8.0",
    }


def _empty_component(status: str, reason: str) -> dict[str, Any]:
    return {"status": status, "reason": reason, "results": []}


class AgentTrustPipeline:
    """
    Single orchestration path for one trace or a corpus of traces.

    Algorithm path consumes only events.json / artifacts.json (or in-memory records).
    """

    def __init__(self, config: Optional[PipelineConfig] = None) -> None:
        self.config = config or PipelineConfig()
        self._rpa = ConservedRPA()
        self._mfav = MFAV()
        self._plhc = PLHC()
        self._assurance = AssuranceProfileCalculator()

    def run_records(
        self,
        events: Sequence[dict[str, Any]],
        artifacts: Sequence[dict[str, Any]],
        *,
        trace_id: str,
        input_fingerprint_sha256: Optional[str] = None,
    ) -> TracePipelineResult:
        """Execute the full pipeline on in-memory event/artifact records."""
        t0 = time.perf_counter()
        timings: dict[str, float] = {}
        warnings: list[str] = []
        errors: list[str] = []
        cfg = self.config
        versions = _versions()

        # --- Load / validate / graph ---
        t_load = time.perf_counter()
        pt = ProvenanceTrace()
        try:
            report = pt.load_records(events, artifacts, default_trace_id=trace_id)
        except Exception as exc:  # noqa: BLE001 — surface as hard error
            timings["total"] = (time.perf_counter() - t0) * 1000.0
            return TracePipelineResult(
                format_version=PIPELINE_FORMAT_VERSION,
                trace_id=trace_id,
                ok=False,
                hard_error=f"load_records failed: {exc}",
                input_fingerprint_sha256=input_fingerprint_sha256,
                provenance_fingerprint=None,
                config=cfg.to_dict(),
                config_fingerprint=cfg.fingerprint(),
                versions=versions,
                validation={},
                graph_summary={},
                projection_eligibility={},
                rpa=_empty_component("failed", "load failed"),
                mfav=_empty_component("failed", "load failed"),
                plhc=_empty_component("failed", "load failed"),
                assurance=_empty_component("failed", "load failed"),
                warnings=warnings,
                errors=[str(exc)],
                timing_ms=timings,
            )
        timings["load_validate_ms"] = (time.perf_counter() - t_load) * 1000.0

        validation = report.to_dict()
        completeness = pt.completeness()
        provenance_fp = pt.fingerprint()
        graph = pt.graph
        graph_summary = {
            "n_nodes": graph.number_of_nodes(),
            "n_edges": graph.number_of_edges(),
            "n_events": len(pt.events),
            "n_artifacts": len(pt.artifacts),
            "n_relationships": len(pt.relationships),
            "fingerprint": provenance_fp,
            "completeness": completeness.to_dict(),
        }

        outcomes = pt.outcome_candidates()
        if cfg.primary_outcome_only and outcomes:
            outcomes = outcomes[:1]

        # Eligibility for attribution stages
        # Note: ValidationReport.suitable_for_dag_attribution may still be True when
        # incomplete; ConservedRPA refuses incomplete unless allow_incomplete=True.
        eligible_for_attribution = bool(outcomes)
        ineligibility_reason = ""
        if not outcomes:
            warnings.append("No outcome candidates; RPA/MFAV skipped.")
            ineligibility_reason = "no outcome candidates"
        if completeness.incomplete:
            warnings.append("Trace incomplete (missing dependency parents or artifacts).")
            if not cfg.allow_incomplete_rpa:
                eligible_for_attribution = False
                ineligibility_reason = (
                    "incomplete trace (missing dependency parents or artifacts); "
                    "RPA refused without allow_incomplete"
                )
        if completeness.has_dependency_cycle:
            warnings.append("Dependency cycle detected; ConservedRPA requires a DAG.")
            eligible_for_attribution = False
            ineligibility_reason = "dependency cycle; ConservedRPA requires a DAG"

        # --- Projections ---
        t_proj = time.perf_counter()
        projection_eligibility: dict[str, Any] = {}
        projections: dict[str, Any] = {}
        kinds: list[ProjectionKind] = []
        if cfg.run_p1:
            kinds.append(ProjectionKind.P1_DIRECT)
        if cfg.run_p2:
            kinds.append(ProjectionKind.P2_ARTIFACT_BRIDGE)

        for kind in kinds:
            try:
                proj = pt.project(kind)
                projections[kind.value] = proj
                projection_eligibility[kind.value] = {
                    "eligible": True,
                    "n_nodes": proj.graph.number_of_nodes(),
                    "n_edges": proj.graph.number_of_edges(),
                    "n_artifact_bridge_edges": sum(
                        1 for e in proj.edges if e.origin == "ARTIFACT_BRIDGE"
                    ),
                    "reason": "projection constructed",
                }
            except Exception as exc:  # noqa: BLE001
                projection_eligibility[kind.value] = {
                    "eligible": False,
                    "reason": f"projection failed: {exc}",
                }
                errors.append(f"projection {kind.value}: {exc}")
        timings["projection_ms"] = (time.perf_counter() - t_proj) * 1000.0

        # --- RPA ---
        t_rpa = time.perf_counter()
        rpa_block: dict[str, Any] = {
            "status": "ok",
            "reason": "",
            "results": [],
        }
        rpa_objects: dict[tuple[str, str], RPAResult] = {}
        rpa_cfg = RPAConfig(allow_incomplete=cfg.allow_incomplete_rpa)

        if not kinds:
            rpa_block = _empty_component("skipped", "no projections selected")
        elif not outcomes:
            rpa_block = _empty_component("ineligible", "no outcome candidates")
        elif not eligible_for_attribution:
            rpa_block = _empty_component(
                "ineligible",
                ineligibility_reason
                or (
                    "trace unsuitable for attribution "
                    f"(incomplete={completeness.incomplete}, "
                    f"cycle={completeness.has_dependency_cycle})"
                ),
            )
        else:
            any_ok = False
            any_fail = False
            for kind in kinds:
                pek = projection_eligibility.get(kind.value, {})
                if not pek.get("eligible"):
                    rpa_block["results"].append(
                        {
                            "projection_kind": kind.value,
                            "status": "skipped",
                            "reason": pek.get("reason", "projection ineligible"),
                        }
                    )
                    continue
                proj = projections[kind.value]
                for oid in outcomes:
                    if oid not in proj.graph:
                        rpa_block["results"].append(
                            {
                                "projection_kind": kind.value,
                                "outcome_id": oid,
                                "status": "ineligible",
                                "reason": "outcome not in projection graph",
                                "validation": None,
                                "result": None,
                            }
                        )
                        continue
                    try:
                        result = self._rpa.allocate(
                            proj,
                            oid,
                            config=rpa_cfg,
                            completeness=completeness,
                            provenance_fingerprint=provenance_fp,
                        )
                        v = validate_rpa_result(result)
                        entry = {
                            "projection_kind": kind.value,
                            "outcome_id": oid,
                            "status": "ok" if v["valid"] or v["status"] == "incomplete" else "failed",
                            "reason": v["reason"],
                            "validation": v,
                            "result": result.to_dict(),
                        }
                        if entry["status"] == "ok":
                            any_ok = True
                            rpa_objects[(kind.value, oid)] = result
                        else:
                            any_fail = True
                            errors.append(
                                f"RPA validation failed {kind.value}/{oid}: {v['reason']}"
                            )
                        rpa_block["results"].append(entry)
                    except RPAError as exc:
                        any_fail = True
                        rpa_block["results"].append(
                            {
                                "projection_kind": kind.value,
                                "outcome_id": oid,
                                "status": "failed",
                                "reason": str(exc),
                                "validation": None,
                                "result": None,
                            }
                        )
                        errors.append(f"RPA {kind.value}/{oid}: {exc}")
            if any_fail and not any_ok:
                rpa_block["status"] = "failed"
                rpa_block["reason"] = "all RPA allocations failed"
            elif any_fail:
                rpa_block["status"] = "partial"
                rpa_block["reason"] = "some RPA allocations failed"
            elif not any_ok:
                rpa_block["status"] = "ineligible"
                rpa_block["reason"] = "no successful RPA allocations"
            else:
                rpa_block["status"] = "ok"
                rpa_block["reason"] = "RPA allocations validated"
        timings["rpa_ms"] = (time.perf_counter() - t_rpa) * 1000.0

        # --- MFAV ---
        t_mfav = time.perf_counter()
        mfav_block: dict[str, Any] = {"status": "ok", "reason": "", "results": []}
        mfav_objects: dict[tuple[str, str], MFAVResult] = {}
        if not rpa_objects:
            mfav_block = _empty_component(
                "skipped" if rpa_block["status"] in ("skipped", "ineligible") else "failed",
                "no validated RPA results to aggregate",
            )
        else:
            any_ok = False
            any_fail = False
            for key, rpa_res in sorted(rpa_objects.items()):
                kind_v, oid = key
                try:
                    mfav_res = self._mfav.compute(rpa_res, trace=pt)
                    v = validate_mfav_result(mfav_res)
                    ok_status = v["status"] in ("verified", "incomplete")
                    entry = {
                        "projection_kind": kind_v,
                        "outcome_id": oid,
                        "status": "ok" if ok_status else "failed",
                        "reason": v["reason"],
                        "validation": v,
                        "result": mfav_res.to_dict(),
                    }
                    if ok_status:
                        any_ok = True
                        mfav_objects[key] = mfav_res
                    else:
                        any_fail = True
                        errors.append(f"MFAV validation failed {kind_v}/{oid}: {v['reason']}")
                    mfav_block["results"].append(entry)
                except MFAVError as exc:
                    any_fail = True
                    mfav_block["results"].append(
                        {
                            "projection_kind": kind_v,
                            "outcome_id": oid,
                            "status": "failed",
                            "reason": str(exc),
                            "validation": None,
                            "result": None,
                        }
                    )
                    errors.append(f"MFAV {kind_v}/{oid}: {exc}")
            if any_fail and not any_ok:
                mfav_block["status"] = "failed"
                mfav_block["reason"] = "all MFAV aggregations failed"
            elif any_fail:
                mfav_block["status"] = "partial"
                mfav_block["reason"] = "some MFAV aggregations failed"
            else:
                mfav_block["status"] = "ok"
                mfav_block["reason"] = "MFAV aggregations validated"
        timings["mfav_ms"] = (time.perf_counter() - t_mfav) * 1000.0

        # --- PLHC ---
        t_plhc = time.perf_counter()
        plhc_block: dict[str, Any] = {"status": "ok", "reason": "", "snapshot": None, "verification": None}
        plhc_result = None
        try:
            snap = self._plhc.build_snapshot(pt)
            # Deterministic created_at from fingerprint prefix (reproducible, ISO-8601)
            created_at = "2020-01-01T00:00:00+00:00"
            cp = self._plhc.create_checkpoint(snap, sequence_number=0, created_at=created_at)
            plhc_result = self._plhc.verify_against_checkpoint(pt, cp)
            inclusion = None
            if cfg.include_inclusion_proof and snap.leaf_count > 0:
                first_leaf_id = sorted(snap.leaf_index_by_id.keys())[0]
                proof = self._plhc.prove_inclusion(snap, first_leaf_id)
                inclusion_ok = self._plhc.verify_inclusion(
                    proof, expected_root=snap.merkle_root
                )
                inclusion = {
                    "leaf_id": first_leaf_id,
                    "verified": inclusion_ok,
                    "proof": proof.to_dict(),
                }
                if not inclusion_ok:
                    errors.append("PLHC inclusion proof verification failed")
            plhc_block = {
                "status": (
                    "ok"
                    if plhc_result.status == IntegrityStatus.VERIFIED
                    else "failed"
                ),
                "reason": plhc_result.explanation,
                "snapshot": {
                    "merkle_root": snap.merkle_root,
                    "leaf_count": snap.leaf_count,
                    "merkle_format_version": snap.merkle_format_version,
                    "canonicalization_version": snap.canonicalization_version,
                    "hash_algorithm": snap.hash_algorithm,
                    "provenance_fingerprint": snap.provenance_fingerprint,
                },
                "checkpoint": cp.to_dict(),
                "verification": plhc_result.to_dict(),
                "inclusion": inclusion,
            }
            if plhc_result.status != IntegrityStatus.VERIFIED:
                errors.append(f"PLHC verification: {plhc_result.status.value}")
        except Exception as exc:  # noqa: BLE001
            plhc_block = {
                "status": "failed",
                "reason": str(exc),
                "snapshot": None,
                "verification": None,
            }
            errors.append(f"PLHC: {exc}")
            plhc_result = None
        timings["plhc_ms"] = (time.perf_counter() - t_plhc) * 1000.0

        # --- Assurance (per outcome × primary projection with validated evidence) ---
        t_as = time.perf_counter()
        assurance_block: dict[str, Any] = {"status": "ok", "reason": "", "profiles": []}
        # Prefer feeding validated P1/P2 MFAV for sensitivity when both exist for same outcome
        profile_outcomes = sorted({oid for (_, oid) in rpa_objects.keys()}) or [None]
        if not outcomes and not rpa_objects:
            # Still compute structural + PLHC dimensions without RPA/MFAV
            profile_outcomes = [None]

        try:
            for oid in profile_outcomes:
                rpa_p1 = rpa_objects.get((ProjectionKind.P1_DIRECT.value, oid)) if oid else None
                rpa_p2 = (
                    rpa_objects.get((ProjectionKind.P2_ARTIFACT_BRIDGE.value, oid)) if oid else None
                )
                mfav_p1 = mfav_objects.get((ProjectionKind.P1_DIRECT.value, oid)) if oid else None
                mfav_p2 = (
                    mfav_objects.get((ProjectionKind.P2_ARTIFACT_BRIDGE.value, oid)) if oid else None
                )
                # Primary profile uses P1 when available else P2
                primary_rpa = rpa_p1 or rpa_p2
                primary_mfav = mfav_p1 or mfav_p2
                # Only pass evidence that passed independent validation
                if primary_rpa is not None:
                    rv = validate_rpa_result(primary_rpa)
                    if not rpa_usable_for_assurance(rv):
                        primary_rpa = None
                        warnings.append(
                            f"Assurance: withholding contradicted RPA for outcome={oid}"
                        )
                if primary_mfav is not None:
                    mv = validate_mfav_result(primary_mfav)
                    if not mfav_usable_for_assurance(mv):
                        primary_mfav = None
                        warnings.append(
                            f"Assurance: withholding contradicted MFAV for outcome={oid}"
                        )
                # Sensitivity pair only when both projections validated
                sens_p1 = mfav_p1
                sens_p2 = mfav_p2
                if sens_p1 is not None and not mfav_usable_for_assurance(
                    validate_mfav_result(sens_p1)
                ):
                    sens_p1 = None
                if sens_p2 is not None and not mfav_usable_for_assurance(
                    validate_mfav_result(sens_p2)
                ):
                    sens_p2 = None

                # PLHC: only pass if verification object exists (evaluator revalidates VERIFIED)
                plhc_for_assurance = plhc_result

                profile = self._assurance.compute(
                    pt,
                    rpa_result=primary_rpa,
                    mfav_result=primary_mfav,
                    mfav_p1=sens_p1,
                    mfav_p2=sens_p2,
                    plhc_result=plhc_for_assurance,
                )
                assurance_block["profiles"].append(profile.to_dict())

            if not assurance_block["profiles"]:
                assurance_block["status"] = "failed"
                assurance_block["reason"] = "no assurance profiles produced"
            else:
                assurance_block["status"] = "ok"
                assurance_block["reason"] = "assurance profiles computed from validated evidence"
        except Exception as exc:  # noqa: BLE001
            assurance_block = {
                "status": "failed",
                "reason": str(exc),
                "profiles": [],
            }
            errors.append(f"Assurance: {exc}")
        timings["assurance_ms"] = (time.perf_counter() - t_as) * 1000.0
        timings["total_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Overall ok (fail-closed) ---
        # Ineligible/skipped RPA (incomplete, no outcomes, cycles) is not a hard failure
        # when PLHC + Assurance succeed — those states are reported explicitly.
        hard_error = None
        component_failures = []
        if rpa_block["status"] == "failed":
            component_failures.append("rpa")
        if mfav_block["status"] == "failed" and bool(rpa_objects):
            component_failures.append("mfav")
        if plhc_block["status"] == "failed":
            component_failures.append("plhc")
        if assurance_block["status"] == "failed":
            component_failures.append("assurance")

        ok = plhc_block["status"] == "ok" and assurance_block["status"] == "ok"
        if rpa_block["status"] == "failed":
            ok = False
        if mfav_block["status"] == "failed" and bool(rpa_objects):
            ok = False
        if not ok and component_failures:
            hard_error = f"component failure(s): {', '.join(component_failures)}"

        # Provenance graph must be unchanged
        if graph_fingerprint(pt.graph) != provenance_fp:
            ok = False
            hard_error = "provenance graph mutated during pipeline"
            errors.append(hard_error)

        return TracePipelineResult(
            format_version=PIPELINE_FORMAT_VERSION,
            trace_id=trace_id,
            ok=ok,
            hard_error=hard_error,
            input_fingerprint_sha256=input_fingerprint_sha256,
            provenance_fingerprint=provenance_fp,
            config=cfg.to_dict(),
            config_fingerprint=cfg.fingerprint(),
            versions=versions,
            validation=validation,
            graph_summary=graph_summary,
            projection_eligibility=projection_eligibility,
            rpa=rpa_block,
            mfav=mfav_block,
            plhc=plhc_block,
            assurance=assurance_block,
            warnings=warnings,
            errors=errors,
            timing_ms=timings,
        )

    def run_trace_dir(self, trace_dir: Path | str) -> TracePipelineResult:
        """Load events/artifacts from a trace directory and run the pipeline."""
        trace_dir = Path(trace_dir)
        try:
            events, arts, fp = load_trace_inputs(trace_dir)
        except PipelineIOError as exc:
            return TracePipelineResult(
                format_version=PIPELINE_FORMAT_VERSION,
                trace_id=trace_dir.name,
                ok=False,
                hard_error=str(exc),
                input_fingerprint_sha256=None,
                provenance_fingerprint=None,
                config=self.config.to_dict(),
                config_fingerprint=self.config.fingerprint(),
                versions=_versions(),
                validation={},
                graph_summary={},
                projection_eligibility={},
                rpa=_empty_component("failed", "io failed"),
                mfav=_empty_component("failed", "io failed"),
                plhc=_empty_component("failed", "io failed"),
                assurance=_empty_component("failed", "io failed"),
                warnings=[],
                errors=[str(exc)],
                timing_ms=None,
            )
        return self.run_records(
            events,
            arts,
            trace_id=trace_dir.name,
            input_fingerprint_sha256=fp,
        )

    def run_corpus(
        self,
        traces_root: Path | str,
        *,
        corpus_label: str = "corpus",
    ) -> tuple[CorpusPipelineSummary, list[TracePipelineResult]]:
        """Evaluate every trace directory under ``traces_root``."""
        traces_root = Path(traces_root)
        results: list[TracePipelineResult] = []
        success_ids: list[str] = []
        failed_ids: list[str] = []
        ineligible_ids: list[str] = []
        n_hard = 0
        notes: list[str] = [
            "Ground truth directories are never opened by AgentTrustPipeline.",
            "Corpus success requires per-trace ok=True; component failures are not concealed.",
        ]

        if not traces_root.is_dir():
            summary = CorpusPipelineSummary(
                format_version=PIPELINE_FORMAT_VERSION,
                corpus=corpus_label,
                traces_root=str(traces_root.as_posix()),
                corpus_fingerprint_sha256=None,
                config_fingerprint=self.config.fingerprint(),
                n_examined=0,
                n_eligible=0,
                n_ineligible=0,
                n_success=0,
                n_failed=0,
                n_hard_errors=1,
                trace_ids_success=[],
                trace_ids_failed=[],
                trace_ids_ineligible=[],
                versions=_versions(),
                notes=notes + [f"traces_root missing: {traces_root}"],
            )
            return summary, results

        dirs = sorted(p for p in traces_root.iterdir() if p.is_dir())
        for tdir in dirs:
            res = self.run_trace_dir(tdir)
            results.append(res)
            if res.hard_error and res.provenance_fingerprint is None:
                n_hard += 1
                failed_ids.append(res.trace_id)
                continue
            rpa_status = (res.rpa or {}).get("status")
            rpa_reason = str((res.rpa or {}).get("reason", "")).lower()
            # Attribution-ineligible: no outcomes, incomplete without override, or cycles
            attribution_ineligible = rpa_status == "ineligible"
            if attribution_ineligible:
                ineligible_ids.append(res.trace_id)
            if res.ok:
                success_ids.append(res.trace_id)
            else:
                failed_ids.append(res.trace_id)
            _ = rpa_reason  # retained for diagnostics in per-trace JSON

        n_examined = len(dirs)
        n_ineligible = len(set(ineligible_ids))
        n_success = len(success_ids)
        n_failed = len(failed_ids)
        # Eligible for full attribution path = examined - attribution-ineligible
        n_eligible = n_examined - n_ineligible

        summary = CorpusPipelineSummary(
            format_version=PIPELINE_FORMAT_VERSION,
            corpus=corpus_label,
            traces_root=str(traces_root.as_posix()),
            corpus_fingerprint_sha256=corpus_fingerprint(traces_root),
            config_fingerprint=self.config.fingerprint(),
            n_examined=n_examined,
            n_eligible=n_eligible,
            n_ineligible=n_ineligible,
            n_success=n_success,
            n_failed=n_failed,
            n_hard_errors=n_hard,
            trace_ids_success=sorted(success_ids),
            trace_ids_failed=sorted(failed_ids),
            trace_ids_ineligible=sorted(set(ineligible_ids)),
            versions=_versions(),
            notes=notes,
        )
        return summary, results
