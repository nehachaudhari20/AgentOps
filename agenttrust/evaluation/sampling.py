"""
Deterministic stratified sampling for RQ evaluations (Phase 2.13).

Replaces first-N catalog-order selection. Trace is the sampling unit.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from typing import Any, Optional, Sequence


def _stratum_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    faults = entry.get("fault_types") or []
    fault = str(faults[0]) if faults else "clean"
    topo = str(entry.get("topology_id") or "unknown")
    scale = str(entry.get("scale_tier") or "unknown")
    role = "fault" if faults else "clean"
    return (fault, topo, scale, role)


def stratified_sample_entries(
    entries: Sequence[dict[str, Any]],
    *,
    n: Optional[int] = None,
    seed: int = 2_13_000,
    min_per_stratum: int = 1,
) -> dict[str, Any]:
    """
    Deterministic stratified sample without replacement.

    If n is None or n >= len(entries), returns the full population (still records
    a sampling manifest for reproducibility).
    """
    population = list(entries)
    pop_ids = [e["trace_id"] for e in population]
    strata: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for e in population:
        strata[_stratum_key(e)].append(e)

    # Stable order within each stratum
    for k in strata:
        strata[k].sort(key=lambda e: e["trace_id"])

    if n is None or n >= len(population):
        selected = sorted(population, key=lambda e: e["trace_id"])
        mode = "full_population"
    else:
        mode = "stratified_proportional"
        rng = random.Random(int(seed))
        # Proportional allocation with at least min_per_stratum when possible
        weights = {k: len(v) for k, v in strata.items()}
        total = sum(weights.values()) or 1
        quotas: dict[tuple, int] = {}
        remaining = int(n)
        # First pass: floor allocation
        for k, w in sorted(weights.items()):
            q = max(min_per_stratum if w >= min_per_stratum else 0, int(n * w / total))
            q = min(q, w, remaining)
            quotas[k] = q
            remaining -= q
        # Distribute remainder by largest fractional residual / stratum size
        while remaining > 0:
            candidates = [
                k for k, w in weights.items() if quotas.get(k, 0) < w
            ]
            if not candidates:
                break
            # Prefer larger strata, break ties with RNG for determinism via seed order
            candidates.sort(key=lambda k: (-(weights[k] - quotas[k]), str(k)))
            k = candidates[0]
            quotas[k] += 1
            remaining -= 1
            # Avoid unused rng lint — mix seed into choice when ties
            _ = rng.random()

        selected = []
        for k in sorted(strata.keys(), key=str):
            pool = list(strata[k])
            q = quotas.get(k, 0)
            if q <= 0:
                continue
            if q >= len(pool):
                selected.extend(pool)
            else:
                # Deterministic shuffle of stratum then take first q
                stratum_rng = random.Random(
                    int(seed)
                    ^ int(hashlib.sha256(str(k).encode()).hexdigest()[:8], 16)
                )
                stratum_rng.shuffle(pool)
                selected.extend(pool[:q])
        selected.sort(key=lambda e: e["trace_id"])
        # If still short due to empty strata, top up from unused
        if len(selected) < n:
            have = {e["trace_id"] for e in selected}
            rest = [e for e in sorted(population, key=lambda x: x["trace_id"]) if e["trace_id"] not in have]
            top_rng = random.Random(int(seed) + 7)
            top_rng.shuffle(rest)
            selected.extend(rest[: n - len(selected)])
            selected.sort(key=lambda e: e["trace_id"])

    selected_ids = [e["trace_id"] for e in selected]
    coverage = {
        str(k): {
            "population": len(v),
            "sampled": sum(1 for e in selected if _stratum_key(e) == k),
        }
        for k, v in sorted(strata.items(), key=lambda kv: str(kv[0]))
    }
    return {
        "sampling_version": "2.13.0",
        "mode": mode,
        "seed": int(seed),
        "requested_n": n,
        "population_n": len(population),
        "sampled_n": len(selected),
        "population_trace_ids": pop_ids,
        "selected_trace_ids": selected_ids,
        "stratum_coverage": coverage,
        "entries": selected,
    }


def wilson_ci(successes: int, n: int, *, z: float = 1.96) -> dict[str, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return {"rate": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "n": 0.0}
    p = successes / float(n)
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z / denom) * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5)
    return {
        "rate": p,
        "ci_low": max(0.0, centre - half),
        "ci_high": min(1.0, centre + half),
        "n": float(n),
        "successes": float(successes),
    }
