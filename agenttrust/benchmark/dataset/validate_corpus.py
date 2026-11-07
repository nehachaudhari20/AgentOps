"""Corpus-level validation for Phase 2.9 experimental datasets."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from agenttrust.benchmark.dataset.corpus import (
    coverage_from_catalog,
    fingerprint_split,
    split_dir,
)
from agenttrust.benchmark.dataset.seeds import DatasetSplit, SEED_BANDS, PILOT_SEED_MAX
from agenttrust.benchmark.faults import PROHIBITED_ANSWER_KEYS
from agenttrust.benchmark.manifest import GENERATOR_VERSION
from agenttrust.benchmark.validation import load_and_validate_trace_dir


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


def validate_split(sdir: Path, *, max_trace_checks: int | None = None) -> dict[str, Any]:
    sdir = Path(sdir)
    report: dict[str, Any] = {
        "split_dir": str(sdir.as_posix()),
        "ok": True,
        "errors": [],
        "warnings": [],
        "n_catalog": 0,
        "n_checked_packages": 0,
        "coverage": {},
        "fingerprint": {},
    }
    catalog_path = sdir / "catalog.json"
    if not catalog_path.is_file():
        report["ok"] = False
        report["errors"].append("missing catalog.json")
        return report

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = catalog.get("entries", [])
    report["n_catalog"] = len(entries)
    report["coverage"] = coverage_from_catalog(catalog)

    # Unique IDs / seeds
    ids = [e["trace_id"] for e in entries]
    seeds = [e["seed"] for e in entries]
    if len(ids) != len(set(ids)):
        report["ok"] = False
        report["errors"].append("duplicate trace_id in catalog")
    if len(seeds) != len(set(seeds)):
        report["ok"] = False
        report["errors"].append("duplicate seed in catalog")

    split_name = catalog.get("split")
    if split_name in {s.value for s in DatasetSplit}:
        lo, hi = SEED_BANDS[DatasetSplit(split_name)]
        for s in seeds:
            if not (lo <= s <= hi) or s <= PILOT_SEED_MAX:
                report["ok"] = False
                report["errors"].append(f"seed {s} outside split band or in pilot band")
                break

    # Matched pair integrity
    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        pid = e.get("matched_pair_id")
        if pid:
            by_pair[pid].append(e)
    for pid, members in by_pair.items():
        roles = {m["role"] for m in members}
        splits = {m["split"] for m in members}
        if roles != {"pair_clean", "pair_fault"}:
            report["ok"] = False
            report["errors"].append(f"pair {pid} roles={roles}")
        if len(splits) != 1:
            report["ok"] = False
            report["errors"].append(f"pair {pid} crosses splits: {splits}")

    # Generator version
    for e in entries:
        if e.get("generator_version") != GENERATOR_VERSION:
            report["ok"] = False
            report["errors"].append(
                f"generator_version mismatch {e['trace_id']}: {e.get('generator_version')}"
            )
            break

    # Sample package checks
    check_entries = entries if max_trace_checks is None else entries[:max_trace_checks]
    for e in check_entries:
        tid = e["trace_id"]
        tdir = sdir / "traces" / tid
        gt_path = sdir / "ground_truth" / f"{tid}.json"
        if not tdir.is_dir():
            report["ok"] = False
            report["errors"].append(f"missing trace dir {tid}")
            continue
        events = json.loads((tdir / "events.json").read_text(encoding="utf-8"))
        arts = json.loads((tdir / "artifacts.json").read_text(encoding="utf-8"))
        leak = _scan_prohibited(events) + _scan_prohibited(arts)
        if leak:
            report["ok"] = False
            report["errors"].append(f"leakage in {tid}: {leak[:3]}")
        if not gt_path.is_file():
            report["ok"] = False
            report["errors"].append(f"missing GT {tid}")
        else:
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
            if "attribution_reference" not in gt:
                report["ok"] = False
                report["errors"].append(f"missing attribution_reference in GT {tid}")
            # Ensure GT not nested inside events dir
            if (tdir / "ground_truth.json").exists():
                report["ok"] = False
                report["errors"].append(f"GT leaked into trace dir {tid}")
        v = load_and_validate_trace_dir(
            tdir,
            pilot_root=sdir,
            require_complete=not (e.get("incomplete") or e.get("fault_types")),
        )
        report["n_checked_packages"] += 1
        if not v.ok and not e.get("incomplete") and not e.get("fault_types"):
            report["ok"] = False
            report["errors"].append(f"package validation failed {tid}: {v.errors[:3]}")

    try:
        report["fingerprint"] = fingerprint_split(sdir)
        (sdir / "fingerprint_manifest.json").write_text(
            json.dumps(report["fingerprint"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (sdir / "coverage_report.json").write_text(
            json.dumps(report["coverage"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        report["ok"] = False
        report["errors"].append(f"fingerprint failed: {exc}")

    (sdir / "validation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def validate_cross_split_isolation(root: Path) -> dict[str, Any]:
    root = Path(root)
    report: dict[str, Any] = {"ok": True, "errors": [], "seed_overlap": [], "pair_overlap": []}
    seeds: dict[str, set[int]] = {}
    pairs: dict[str, set[str]] = {}
    for split in DatasetSplit:
        cat = split_dir(root, split) / "catalog.json"
        if not cat.is_file():
            continue
        data = json.loads(cat.read_text(encoding="utf-8"))
        seeds[split.value] = {e["seed"] for e in data.get("entries", [])}
        pairs[split.value] = {
            e["matched_pair_id"]
            for e in data.get("entries", [])
            if e.get("matched_pair_id")
        }
    names = list(seeds)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            so = seeds[a] & seeds[b]
            if so:
                report["ok"] = False
                report["seed_overlap"].append({"a": a, "b": b, "n": len(so)})
                report["errors"].append(f"seed overlap {a}/{b}: {len(so)}")
            po = pairs[a] & pairs[b]
            if po:
                report["ok"] = False
                report["pair_overlap"].append({"a": a, "b": b, "n": len(po)})
                report["errors"].append(f"pair overlap {a}/{b}: {len(po)}")
    return report


def aggregate_statistics(root: Path) -> dict[str, Any]:
    root = Path(root)
    splits = {}
    total_traces = 0
    total_events = 0
    for split in DatasetSplit:
        cat_path = split_dir(root, split) / "catalog.json"
        if not cat_path.is_file():
            continue
        cat = json.loads(cat_path.read_text(encoding="utf-8"))
        cov = coverage_from_catalog(cat)
        splits[split.value] = cov
        total_traces += cov["n_traces"]
        total_events += cov["total_events"]
    return {
        "dataset_root": str(root.as_posix()),
        "n_traces_total": total_traces,
        "nested_event_volume_total": total_events,
        "note": "Do not treat nested_event_volume_total as independent N",
        "splits": splits,
        "cross_split": validate_cross_split_isolation(root),
    }
