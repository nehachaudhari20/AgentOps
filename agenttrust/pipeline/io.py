"""
Trace I/O for the production-style AgentTrust pipeline.

Loads only observable event/artifact records. Never opens ground-truth files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class PipelineIOError(ValueError):
    """Unreadable or malformed trace package (algorithm inputs only)."""


FORBIDDEN_GT_NAMES = frozenset(
    {
        "ground_truth",
        "ground-truth",
        "gt",
        "labels",
        "fault_labels",
        "expected",
    }
)


def assert_no_ground_truth_path(path: Path) -> None:
    """Raise if a path clearly targets evaluation-only ground truth."""
    parts = {p.lower() for p in path.parts}
    if parts & FORBIDDEN_GT_NAMES:
        raise PipelineIOError(
            f"Refusing path that appears to be ground-truth evaluation data: {path}"
        )
    name = path.name.lower()
    if "ground_truth" in name or name.endswith(".gt.json"):
        raise PipelineIOError(f"Refusing ground-truth-like filename: {path}")


def load_trace_inputs(trace_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """
    Load events.json and artifacts.json from a trace directory.

    Returns (events, artifacts, input_fingerprint_sha256).
    Does not read ground_truth/.
    """
    trace_dir = Path(trace_dir)
    assert_no_ground_truth_path(trace_dir)
    if not trace_dir.is_dir():
        raise PipelineIOError(f"trace directory missing: {trace_dir}")

    events_path = trace_dir / "events.json"
    arts_path = trace_dir / "artifacts.json"
    for p in (events_path, arts_path):
        assert_no_ground_truth_path(p)
        if not p.is_file():
            raise PipelineIOError(f"required input missing: {p}")

    events_raw = events_path.read_bytes()
    arts_raw = arts_path.read_bytes()
    try:
        events_obj = json.loads(events_raw.decode("utf-8"))
        arts_obj = json.loads(arts_raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineIOError(f"invalid JSON in {trace_dir}: {exc}") from exc

    if not isinstance(events_obj, dict) or "events" not in events_obj:
        raise PipelineIOError(f"{events_path}: missing top-level 'events' array")
    if not isinstance(arts_obj, dict) or "artifacts" not in arts_obj:
        raise PipelineIOError(f"{arts_path}: missing top-level 'artifacts' array")

    events = list(events_obj["events"])
    arts = list(arts_obj["artifacts"])
    h = hashlib.sha256()
    h.update(trace_dir.name.encode("utf-8"))
    h.update(events_raw)
    h.update(arts_raw)
    return events, arts, h.hexdigest()


def corpus_fingerprint(traces_root: Path) -> str:
    """Fingerprint of all trace input packages under a corpus (events+artifacts only)."""
    traces_root = Path(traces_root)
    assert_no_ground_truth_path(traces_root)
    if not traces_root.is_dir():
        return ""
    h = hashlib.sha256()
    for tdir in sorted(p for p in traces_root.iterdir() if p.is_dir()):
        h.update(tdir.name.encode("utf-8"))
        for name in ("events.json", "artifacts.json"):
            f = tdir / name
            if f.is_file():
                h.update(f.read_bytes())
    return h.hexdigest()
