#!/usr/bin/env python3
"""
AgentTrust Phase 2.8 — end-to-end evaluation CLI.

Evaluates one trace or a corpus through the integrated pipeline:
  load → validate → MLPG → P1/P2 → RPA → MFAV → PLHC → Assurance

Does not read ground-truth files. Does not produce a trust score.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agenttrust.pipeline import AgentTrustPipeline, PipelineConfig


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Evaluate AgentTrust end-to-end on one trace or a corpus."
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--trace",
        type=Path,
        help="Path to a single trace directory containing events.json and artifacts.json",
    )
    g.add_argument(
        "--corpus",
        type=Path,
        help="Path to a directory of trace directories (e.g. data/benchmarks/pilot/traces)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "results" / "pipeline_2_8",
        help="Output directory for machine-readable results",
    )
    p.add_argument("--corpus-label", default="corpus", help="Label stored in corpus summary")
    p.add_argument("--no-p1", action="store_true", help="Skip P1_DIRECT projection/RPA")
    p.add_argument("--no-p2", action="store_true", help="Skip P2_ARTIFACT_BRIDGE projection/RPA")
    p.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Pass allow_incomplete=True to ConservedRPA",
    )
    p.add_argument(
        "--primary-outcome-only",
        action="store_true",
        help="Attribute only the first outcome candidate",
    )
    p.add_argument(
        "--no-inclusion-proof",
        action="store_true",
        help="Skip PLHC inclusion proof generation",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="After writing outputs, re-load JSON and assert required keys exist",
    )
    return p


def _validate_trace_json(d: dict) -> list[str]:
    required = [
        "format_version",
        "trace_id",
        "ok",
        "config",
        "config_fingerprint",
        "versions",
        "validation",
        "graph_summary",
        "projection_eligibility",
        "rpa",
        "mfav",
        "plhc",
        "assurance",
        "warnings",
        "errors",
    ]
    missing = [k for k in required if k not in d]
    return missing


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = PipelineConfig(
        run_p1=not args.no_p1,
        run_p2=not args.no_p2,
        allow_incomplete_rpa=args.allow_incomplete,
        primary_outcome_only=args.primary_outcome_only,
        include_inclusion_proof=not args.no_inclusion_proof,
    )
    pipe = AgentTrustPipeline(cfg)
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    if args.trace is not None:
        result = pipe.run_trace_dir(args.trace)
        trace_path = out / f"{result.trace_id}.json"
        _write_json(trace_path, result.to_dict())
        print(
            json.dumps(
                {
                    "mode": "trace",
                    "trace_id": result.trace_id,
                    "ok": result.ok,
                    "hard_error": result.hard_error,
                    "output": str(trace_path.as_posix()),
                    "rpa_status": result.rpa.get("status"),
                    "mfav_status": result.mfav.get("status"),
                    "plhc_status": result.plhc.get("status"),
                    "assurance_status": result.assurance.get("status"),
                },
                indent=2,
            )
        )
        if args.validate_only:
            loaded = json.loads(trace_path.read_text(encoding="utf-8"))
            missing = _validate_trace_json(loaded)
            if missing:
                print(f"OUTPUT VALIDATION FAILED missing={missing}", file=sys.stderr)
                return 2
            print("output validation: ok")
        return 0 if result.ok else 1

    summary, results = pipe.run_corpus(args.corpus, corpus_label=args.corpus_label)
    traces_out = out / "traces"
    traces_out.mkdir(parents=True, exist_ok=True)
    for r in results:
        _write_json(traces_out / f"{r.trace_id}.json", r.to_dict())
    summary_path = out / "corpus_summary.json"
    _write_json(summary_path, summary.to_dict())

    print(
        json.dumps(
            {
                "mode": "corpus",
                "corpus": summary.corpus,
                "n_examined": summary.n_examined,
                "n_eligible": summary.n_eligible,
                "n_ineligible": summary.n_ineligible,
                "n_success": summary.n_success,
                "n_failed": summary.n_failed,
                "n_hard_errors": summary.n_hard_errors,
                "output": str(summary_path.as_posix()),
                "config_fingerprint": summary.config_fingerprint,
                "corpus_fingerprint_sha256": summary.corpus_fingerprint_sha256,
            },
            indent=2,
        )
    )

    if args.validate_only:
        loaded = json.loads(summary_path.read_text(encoding="utf-8"))
        for key in (
            "format_version",
            "n_examined",
            "n_eligible",
            "n_ineligible",
            "n_success",
            "n_failed",
        ):
            if key not in loaded:
                print(f"SUMMARY VALIDATION FAILED missing={key}", file=sys.stderr)
                return 2
        for r in results:
            missing = _validate_trace_json(r.to_dict())
            if missing:
                print(
                    f"TRACE VALIDATION FAILED {r.trace_id} missing={missing}",
                    file=sys.stderr,
                )
                return 2
        print("output validation: ok")

    # Fail-closed: any failed or hard-error trace → non-zero
    if summary.n_failed > 0 or summary.n_hard_errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
