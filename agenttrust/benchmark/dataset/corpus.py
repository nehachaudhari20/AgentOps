"""
Experimental corpus generation and fingerprinting (Phase 2.9).

Does not overwrite historical pilot/. Resumes by skipping existing valid catalogs
unless force=True. Never reads ground truth into algorithm execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agenttrust.benchmark.dataset.attribution_reference import (
    GROUND_TRUTH_VERSION,
    build_attribution_reference,
)
from agenttrust.benchmark.dataset.design import (
    DATASET_ID,
    DESIGN_VERSION,
    TraceSpec,
    design_document_dict,
    design_fingerprint,
    iter_trace_specs,
)
from agenttrust.benchmark.dataset.observability import observability_matrix
from agenttrust.benchmark.dataset.power import power_report
from agenttrust.benchmark.dataset.seeds import DatasetSplit
from agenttrust.benchmark.faults import PROHIBITED_ANSWER_KEYS
from agenttrust.benchmark.generator import BenchmarkGenerator, GeneratedTrace
from agenttrust.benchmark.manifest import GENERATOR_VERSION
from agenttrust.benchmark.validation import validate_generated_trace

DEFAULT_ROOT = Path("data/benchmarks/experimental_2_9")


@dataclass
class GenerationResult:
    split: str
    n_planned: int
    n_written: int
    n_skipped_existing: int
    n_failed: int
    failures: list[dict[str, Any]] = field(default_factory=list)
    catalog_path: Optional[str] = None


def split_dir(root: Path, split: DatasetSplit | str) -> Path:
    name = split.value if isinstance(split, DatasetSplit) else split
    return Path(root) / "splits" / name


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _enrich_trace(trace: GeneratedTrace, spec: TraceSpec) -> GeneratedTrace:
    """Attach dataset metadata + independent attribution reference to GT/manifest."""
    ref = build_attribution_reference(trace.events, list(trace.manifest.outcome_event_ids))
    gt = trace.ground_truth
    gt.ground_truth_version = GROUND_TRUTH_VERSION
    gt.attribution_reference = ref
    # Manifest extensions (optional fields)
    m = trace.manifest
    m.notes = list(m.notes) + [
        f"dataset_id={DATASET_ID}",
        f"split={spec.split}",
        f"role={spec.role}",
        f"design_version={DESIGN_VERSION}",
    ]
    if spec.matched_pair_id:
        m.notes.append(f"matched_pair_id={spec.matched_pair_id}")
    m.notes.append(f"base_seed={spec.base_seed}")
    return trace


def _scan_prohibited(obj: Any, *, path: str = "$") -> list[str]:
    bad: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in PROHIBITED_ANSWER_KEYS or lk.startswith("gt_"):
                bad.append(f"{path}.{k}")
            bad.extend(_scan_prohibited(v, path=f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            bad.extend(_scan_prohibited(v, path=f"{path}[{i}]"))
    return bad


def generate_split(
    split: DatasetSplit,
    *,
    root: Path = DEFAULT_ROOT,
    force: bool = False,
    limit: Optional[int] = None,
) -> GenerationResult:
    root = Path(root)
    sdir = split_dir(root, split)
    traces_dir = sdir / "traces"
    gt_dir = sdir / "ground_truth"
    man_dir = sdir / "manifests"
    for d in (traces_dir, gt_dir, man_dir):
        d.mkdir(parents=True, exist_ok=True)

    gen = BenchmarkGenerator()
    specs = list(iter_trace_specs(split))
    if limit is not None:
        specs = specs[: int(limit)]

    catalog: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    n_written = 0
    n_skipped = 0

    existing_catalog = sdir / "catalog.json"
    existing_ids: set[str] = set()
    if existing_catalog.is_file() and not force:
        prev = json.loads(existing_catalog.read_text(encoding="utf-8"))
        existing_ids = {e["trace_id"] for e in prev.get("entries", [])}

    for spec in specs:
        cfg = spec.to_config()
        tid = cfg.make_trace_id()
        if tid in existing_ids and not force:
            n_skipped += 1
            continue
        try:
            trace = gen.generate(cfg)
            trace = _enrich_trace(trace, spec)
            require_complete = not (spec.incomplete or spec.fault_types)
            v = validate_generated_trace(trace, require_complete=require_complete)
            leak = _scan_prohibited(trace.events) + _scan_prohibited(trace.artifacts)
            if leak:
                raise ValueError(f"answer leakage keys in algorithm inputs: {leak[:5]}")
            if not v.ok:
                failures.append({"trace_id": tid, "errors": v.errors, "stage": "validate"})
                # Still write? Spec says do not silently skip failures — record and continue
                # We do not write invalid packages.
                continue
            paths = gen.write_trace(
                trace,
                events_dir=traces_dir,
                ground_truth_dir=gt_dir,
                manifests_dir=man_dir,
            )
            entry = {
                "trace_id": tid,
                "split": spec.split,
                "role": spec.role,
                "seed": spec.seed,
                "base_seed": spec.base_seed,
                "matched_pair_id": spec.matched_pair_id,
                "scenario_id": spec.scenario_id.value,
                "topology_id": spec.topology_id.value,
                "scale_tier": spec.scale_tier.value,
                "fault_types": list(spec.fault_types),
                "incomplete": spec.incomplete,
                "config_fingerprint": cfg.fingerprint(),
                "generator_version": GENERATOR_VERSION,
                "ground_truth_version": GROUND_TRUTH_VERSION,
                "actual_event_count": trace.manifest.actual_event_count,
                "agent_count": trace.manifest.agent_count,
                "artifact_count": trace.manifest.artifact_count,
                "paths": {k: str(p.as_posix()) for k, p in paths.items()},
            }
            catalog.append(entry)
            n_written += 1
            existing_ids.add(tid)
        except Exception as exc:  # noqa: BLE001 — record exact failure
            failures.append({"trace_id": tid, "errors": [str(exc)], "stage": "generate"})

    # Merge with previous catalog entries if resuming
    if existing_catalog.is_file() and not force:
        prev = json.loads(existing_catalog.read_text(encoding="utf-8"))
        prev_entries = [
            e for e in prev.get("entries", []) if e["trace_id"] not in {c["trace_id"] for c in catalog}
        ]
        catalog = sorted(prev_entries + catalog, key=lambda e: e["trace_id"])
    else:
        catalog = sorted(catalog, key=lambda e: e["trace_id"])

    catalog_obj = {
        "dataset_id": DATASET_ID,
        "design_version": DESIGN_VERSION,
        "design_fingerprint_sha256": design_fingerprint(),
        "split": split.value,
        "generator_version": GENERATOR_VERSION,
        "n_entries": len(catalog),
        "n_failed_this_run": len(failures),
        "failures": failures,
        "entries": catalog,
    }
    catalog_path = sdir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog_obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return GenerationResult(
        split=split.value,
        n_planned=len(specs),
        n_written=n_written,
        n_skipped_existing=n_skipped,
        n_failed=len(failures),
        failures=failures,
        catalog_path=str(catalog_path.as_posix()),
    )


def fingerprint_split(sdir: Path) -> dict[str, Any]:
    sdir = Path(sdir)
    catalog = json.loads((sdir / "catalog.json").read_text(encoding="utf-8"))
    file_fps: dict[str, str] = {}
    h = hashlib.sha256()
    for entry in sorted(catalog["entries"], key=lambda e: e["trace_id"]):
        tid = entry["trace_id"]
        for rel in (
            f"traces/{tid}/events.json",
            f"traces/{tid}/artifacts.json",
            f"ground_truth/{tid}.json",
            f"manifests/{tid}.json",
        ):
            p = sdir / rel
            digest = _sha256_file(p) if p.is_file() else ""
            file_fps[rel] = digest
            h.update(rel.encode("utf-8"))
            h.update(digest.encode("utf-8"))
    return {
        "split": catalog.get("split"),
        "n_entries": catalog.get("n_entries"),
        "design_fingerprint_sha256": catalog.get("design_fingerprint_sha256"),
        "corpus_fingerprint_sha256": h.hexdigest(),
        "files": file_fps,
    }


def write_design_and_reports(root: Path = DEFAULT_ROOT) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (root / "design_fingerprint.json").write_text(
        json.dumps(design_document_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "sample_size_power.json").write_text(
        json.dumps(power_report(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "fault_observability_matrix.json").write_text(
        json.dumps(observability_matrix(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def coverage_from_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    from collections import Counter

    entries = catalog.get("entries", [])
    return {
        "split": catalog.get("split"),
        "n_traces": len(entries),
        "topology": dict(Counter(e["topology_id"] for e in entries)),
        "scenario": dict(Counter(e["scenario_id"] for e in entries)),
        "scale": dict(Counter(e["scale_tier"] for e in entries)),
        "role": dict(Counter(e["role"] for e in entries)),
        "fault": dict(
            Counter(
                (e["fault_types"][0] if e["fault_types"] else "clean") for e in entries
            )
        ),
        "n_matched_pair_ids": len(
            {e["matched_pair_id"] for e in entries if e.get("matched_pair_id")}
        ),
        "n_unique_seeds": len({e["seed"] for e in entries}),
        "total_events": sum(int(e.get("actual_event_count") or 0) for e in entries),
        "total_artifacts": sum(int(e.get("artifact_count") or 0) for e in entries),
        "note": "total_events/artifacts are nested volume, not independent sample size",
    }
