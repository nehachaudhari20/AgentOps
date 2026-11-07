"""Simulation-based sample-size / power planning (Phase 2.9)."""

from __future__ import annotations

import math
import random
from typing import Any


def _two_prop_z_reject(x1: int, n1: int, x0: int, n0: int, alpha: float = 0.05) -> bool:
    """Unpooled two-proportion z-test (two-sided)."""
    if n1 <= 0 or n0 <= 0:
        return False
    p1 = x1 / n1
    p0 = x0 / n0
    p_pool = (x1 + x0) / (n1 + n0)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n0))
    if se <= 0:
        return abs(p1 - p0) > 0
    z = (p1 - p0) / se
    # Approximate critical value 1.96 for alpha=0.05
    zcrit = 1.95996398454 if abs(alpha - 0.05) < 1e-12 else abs(_norm_ppf(1 - alpha / 2))
    return abs(z) >= zcrit


def _norm_ppf(p: float) -> float:
    """Rough Acklam approximation for standard normal PPF (sufficient for planning)."""
    # Coefficients from Peter J. Acklam's approximation
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
    ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def simulate_power(
    *,
    n_pairs: int,
    p0: float,
    delta: float,
    alpha: float = 0.05,
    n_sims: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Monte Carlo power for detecting a rate difference of ``delta`` above ``p0``.

    Models pair-success indicators as i.i.d. Bernoulli (planning approximation).
    """
    p1 = min(1.0, p0 + delta)
    rng = random.Random(seed)
    rejects = 0
    for _ in range(n_sims):
        # Control arm: null rate; treatment: elevated detection of incompleteness contrast
        x0 = sum(1 for _ in range(n_pairs) if rng.random() < p0)
        x1 = sum(1 for _ in range(n_pairs) if rng.random() < p1)
        if _two_prop_z_reject(x1, n_pairs, x0, n_pairs, alpha=alpha):
            rejects += 1
    power = rejects / n_sims
    return {
        "n_pairs": n_pairs,
        "p0": p0,
        "p1": p1,
        "delta": delta,
        "alpha": alpha,
        "n_sims": n_sims,
        "power": power,
        "meets_80": power >= 0.80,
        "meets_90": power >= 0.90,
    }


def power_report(
    *,
    heldout_incompleteness_pairs: int = 72,
    n_sims: int = 10_000,
) -> dict[str, Any]:
    grid = []
    for p0 in (0.50, 0.70, 0.85):
        for delta in (0.10, 0.15, 0.20, 0.30):
            grid.append(
                simulate_power(
                    n_pairs=heldout_incompleteness_pairs,
                    p0=p0,
                    delta=delta,
                    n_sims=n_sims,
                    seed=42 + int(p0 * 100) + int(delta * 100),
                )
            )
    primary = [
        g
        for g in grid
        if abs(g["delta"] - 0.20) < 1e-12 and abs(g["p0"] - 0.70) < 1e-12
    ]
    return {
        "report_version": "2.9.0",
        "primary_endpoint": (
            "Paired incompleteness contrast success rate "
            "(incomplete_trace / missing_dependency vs matched clean)"
        ),
        "heldout_incompleteness_pairs": heldout_incompleteness_pairs,
        "derivation": "2 faults × 6 topologies × 2 scales × 3 replicates = 72",
        "alpha": 0.05,
        "target_power": 0.80,
        "preferred_power": 0.90,
        "pilot_limitation": (
            "Historical pilot has only 2 incomplete traces; variance uncertain. "
            "Sensitivity grid required."
        ),
        "simulation_grid": grid,
        "primary_planning_cell": primary[0] if primary else None,
        "decision": (
            "Adopt held-out n_pairs=72 for Δ=0.20 primary contrast; "
            "Δ≤0.10 and high-ceiling p0 treated as exploratory/precision-based."
        ),
    }
