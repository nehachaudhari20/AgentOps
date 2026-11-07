"""Experiment run manifests (Phase 2.12). Timing metadata excluded from content hashes."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _git(cmd: list[str]) -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", *cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        return out.strip() or None
    except Exception:
        return None


def _pkg_version(name: str) -> Optional[str]:
    try:
        mod = __import__(name)
        return getattr(mod, "__version__", None)
    except Exception:
        return None


@dataclass
class RunManifest:
    run_id: str
    stage: str
    repository: str
    branch: Optional[str]
    commit_sha: Optional[str]
    python_version: str
    platform: str
    dependency_versions: dict[str, Optional[str]]
    schema_version: str
    generator_version: Optional[str]
    algorithm_versions: dict[str, str]
    dataset_fingerprint: Optional[str]
    config_fingerprint: Optional[str]
    seeds: list[int] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    validation_status: str = "unknown"
    notes: list[str] = field(default_factory=list)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    # Nondeterministic wall-clock / host fields — excluded from content_hash
    host: Optional[str] = None

    def deterministic_payload(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("started_at", "ended_at", "host"):
            d.pop(k, None)
        return d

    def content_hash(self) -> str:
        blob = json.dumps(self.deterministic_payload(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["content_hash_sha256"] = self.content_hash()
        d["disclaimer"] = (
            "started_at/ended_at/host excluded from content_hash_sha256 "
            "(nondeterministic execution metadata)."
        )
        return d


def build_run_manifest(
    *,
    run_id: str,
    stage: str,
    commands: list[str],
    output_paths: Optional[list[str]] = None,
    dataset_fingerprint: Optional[str] = None,
    config_fingerprint: Optional[str] = None,
    seeds: Optional[list[int]] = None,
    validation_status: str = "unknown",
    notes: Optional[list[str]] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
) -> RunManifest:
    import agenttrust
    from agenttrust.assurance.models import ASSURANCE_ALGORITHM_VERSION
    from agenttrust.attribution.rpa import ALGORITHM_VERSION as RPA_VERSION
    from agenttrust.benchmark.manifest import GENERATOR_VERSION
    from agenttrust.schema.enums import SCHEMA_VERSION

    return RunManifest(
        run_id=run_id,
        stage=stage,
        repository="https://github.com/nehachaudhari20/AgentOps.git",
        branch=_git(["branch", "--show-current"]),
        commit_sha=_git(["rev-parse", "HEAD"]),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        dependency_versions={
            "agenttrust": getattr(agenttrust, "__version__", None),
            "networkx": _pkg_version("networkx"),
            "numpy": _pkg_version("numpy"),
            "pytest": _pkg_version("pytest"),
        },
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        algorithm_versions={
            "rpa": RPA_VERSION,
            "assurance": ASSURANCE_ALGORITHM_VERSION,
            "pipeline_package": getattr(agenttrust, "__version__", "unknown"),
        },
        dataset_fingerprint=dataset_fingerprint,
        config_fingerprint=config_fingerprint,
        seeds=list(seeds or []),
        commands=list(commands),
        output_paths=list(output_paths or []),
        validation_status=validation_status,
        notes=list(notes or []),
        started_at=started_at,
        ended_at=ended_at,
        host=platform.node(),
    )


def write_manifest(path: Path, manifest: RunManifest) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
