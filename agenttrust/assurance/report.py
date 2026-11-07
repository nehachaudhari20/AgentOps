"""Serialize Assurance Profiles for evaluation reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from agenttrust.assurance.result import AssuranceProfile


def profiles_to_summary(profiles: Iterable[AssuranceProfile]) -> dict[str, Any]:
    items = list(profiles)
    by_status: dict[str, int] = {}
    dim_unavailable: dict[str, int] = {}
    for p in items:
        by_status[p.overall_status.value] = by_status.get(p.overall_status.value, 0) + 1
        for did, d in p.dimensions.items():
            if d.status.value == "unavailable":
                dim_unavailable[did] = dim_unavailable.get(did, 0) + 1
    return {
        "n_profiles": len(items),
        "overall_status_counts": by_status,
        "unavailable_dimension_counts": dim_unavailable,
    }


def write_profiles_json(path: Path, profiles: list[AssuranceProfile], *, extra: dict | None = None) -> None:
    payload = {
        "summary": profiles_to_summary(profiles),
        "profiles": [p.to_dict() for p in profiles],
    }
    if extra:
        payload["extra"] = extra
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
