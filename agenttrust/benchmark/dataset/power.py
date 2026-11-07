"""
Paired sample-size / power planning (Phase 2.13 correction).

Primary endpoint: matched clean/fault pair binary contrast (incompleteness).
Uses McNemar / exact binomial on discordant pairs — NOT independent two-proportion z-tests.

Historical Phase 2.9 independent-Bernoulli power figures are superseded and must not
be cited as valid evidence for the paired design.
"""

from __future__ import annotations

import math
import random
from typing import Any


def mcnemar_exact_pvalue(b: int, c: int) -> float:
    """
    Two-sided exact McNemar p-value via binomial on discordant pairs.

    Under H0, P(fault-only | discordant) = 1/2.
    b = fault success & clean fail; c = fault fail & clean success.
    """
    n = b + c
    if n == 0:
        return 1.0
    # P(|X - n/2| >= |b - n/2|) under X~Bin(n, 0.5)
    k = min(b, c)
    # two-sided: 2 * cdf(k) but capped at 1; for even n and k=n/2 returns 1
    cdf = sum(math.comb(n, i) for i in range(0, k + 1)) / (2**n)
    return min(1.0, 2.0 * cdf)


def mcnemar_reject(b: int, c: int, *, alpha: float = 0.05) -> bool:
    return mcnemar_exact_pvalue(b, c) < alpha


def simulate_paired_power(
    *,
    n_pairs: int,
    p_both: float,
    p_fault_only: float,
    p_clean_only: float,
    alpha: float = 0.05,
    n_sims: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Monte Carlo power for McNemar on matched pairs.

    Each pair is drawn from a 4-cell multinomial:
      both / fault_only / clean_only / neither
    with probabilities that must sum to ≤ 1 (remainder = neither).
    """
    p_neither = 1.0 - (p_both + p_fault_only + p_clean_only)
    if min(p_both, p_fault_only, p_clean_only, p_neither) < -1e-15:
        raise ValueError("Invalid joint probabilities (negative cell)")
    if p_neither < -1e-12:
        raise ValueError("Joint probabilities exceed 1")
    # Normalize tiny negatives
    cells = [max(0.0, p_both), max(0.0, p_fault_only), max(0.0, p_clean_only), max(0.0, p_neither)]
    s = sum(cells)
    cells = [c / s for c in cells]

    rng = random.Random(int(seed))
    rejects = 0
    for _ in range(n_sims):
        b = c = 0  # fault_only, clean_only
        for _p in range(n_pairs):
            u = rng.random()
            if u < cells[0]:
                continue  # both
            u -= cells[0]
            if u < cells[1]:
                b += 1
            else:
                u -= cells[1]
                if u < cells[2]:
                    c += 1
                # else neither
        if mcnemar_reject(b, c, alpha=alpha):
            rejects += 1
    power = rejects / float(n_sims)
    return {
        "method": "mcnemar_exact_binomial_discordant",
        "n_pairs": n_pairs,
        "p_both": p_both,
        "p_fault_only": p_fault_only,
        "p_clean_only": p_clean_only,
        "p_neither": cells[3] * s if s else p_neither,
        "alpha": alpha,
        "n_sims": n_sims,
        "seed": seed,
        "power": power,
        "meets_80": power >= 0.80,
        "meets_90": power >= 0.90,
        "design": "paired_matched_clean_fault",
    }


def _grid_joints_for_delta(p_disc: float, delta_odds: float) -> tuple[float, float, float, float]:
    """
    Construct joint cells with discordant rate p_disc and asymmetry favoring fault_only.

    Under alternative: among discordant pairs, P(fault_only)=0.5+delta_odds/2.
    Concordant mass split equally between both/neither for planning.
    """
    p_disc = min(max(p_disc, 0.0), 1.0)
    p_conc = 1.0 - p_disc
    p_fault_only = p_disc * (0.5 + delta_odds / 2.0)
    p_clean_only = p_disc * (0.5 - delta_odds / 2.0)
    p_both = p_conc / 2.0
    p_neither = p_conc / 2.0
    return p_both, p_fault_only, p_clean_only, p_neither


def power_report(
    *,
    heldout_incompleteness_pairs: int = 72,
    n_sims: int = 10_000,
) -> dict[str, Any]:
    """
    Corrected Phase 2.13 paired power report.

    Supersedes invalid Phase 2.9 independent two-proportion simulations.
    """
    grid = []
    # Sensitivity: discordant rates and odds asymmetries
    for p_disc in (0.20, 0.30, 0.40, 0.50):
        for delta_odds in (0.20, 0.40, 0.60, 0.80):  # P(fault|disc)-P(clean|disc)
            pb, pf, pc, pn = _grid_joints_for_delta(p_disc, delta_odds)
            cell = simulate_paired_power(
                n_pairs=heldout_incompleteness_pairs,
                p_both=pb,
                p_fault_only=pf,
                p_clean_only=pc,
                n_sims=n_sims,
                seed=13_000 + int(p_disc * 1000) + int(delta_odds * 100),
            )
            cell["p_discordant"] = p_disc
            cell["discordant_asymmetry"] = delta_odds
            grid.append(cell)

    # Primary planning cell: moderate discordance + moderate asymmetry
    primary = next(
        (
            g
            for g in grid
            if abs(g["p_discordant"] - 0.30) < 1e-12 and abs(g["discordant_asymmetry"] - 0.40) < 1e-12
        ),
        None,
    )

    # Find minimum n for 80% at primary joint params
    n_needed_80 = None
    if primary:
        pb, pf, pc = primary["p_both"], primary["p_fault_only"], primary["p_clean_only"]
        for n in range(20, 401, 4):
            sim = simulate_paired_power(
                n_pairs=n, p_both=pb, p_fault_only=pf, p_clean_only=pc, n_sims=n_sims, seed=99_000 + n
            )
            if sim["meets_80"]:
                n_needed_80 = n
                break

    decision = (
        f"Under McNemar paired simulation, n_pairs={heldout_incompleteness_pairs} "
        f"primary-cell power={primary['power']:.4f} (p_disc=0.30, asym=0.40). "
    )
    if primary and primary["meets_80"]:
        decision += "Existing 72 pairs remain adequate for this primary paired cell."
    else:
        decision += (
            f"Existing 72 pairs do NOT meet 80% for the primary cell; "
            f"suggested n_pairs≈{n_needed_80}. Historical Phase 2.9 corpus preserved; "
            "regeneration requires explicit approval (not auto-run)."
        )

    return {
        "report_version": "2.13.0",
        "supersedes": "2.9.0_independent_two_proportion_invalid_for_paired_design",
        "primary_endpoint": (
            "McNemar on matched pairs: incompleteness-inducing fault vs clean twin "
            "(pair success = fault incomplete flagged XOR/AND structure via discordant cells)"
        ),
        "null_hypothesis": "P(fault-only success) = P(clean-only success) among discordant pairs",
        "heldout_incompleteness_pairs": heldout_incompleteness_pairs,
        "derivation": "2 faults × 6 topologies × 2 scales × 3 replicates = 72 (unchanged catalog)",
        "alpha": 0.05,
        "target_power": 0.80,
        "preferred_power": 0.90,
        "n_sims": n_sims,
        "pilot_limitation": (
            "Pilot incompleteness n=2; joint probabilities for planning use sensitivity grid, "
            "not precise empirical estimates."
        ),
        "simulation_grid": grid,
        "primary_planning_cell": primary,
        "n_pairs_for_80_primary_cell": n_needed_80,
        "decision": decision,
        "historical_note": (
            "Phase 2.9 power≈0.8691 from independent Bernoulli z-tests is INVALID for this "
            "paired design and must not be cited."
        ),
    }


# Backward-compatible name used by corpus.write_design_and_reports
def simulate_power(**kwargs: Any) -> dict[str, Any]:
    """
    Deprecated wrapper. Raises if called with old independent-Bernoulli kwargs alone.

    Prefer simulate_paired_power(...).
    """
    if "p0" in kwargs or "delta" in kwargs:
        raise ValueError(
            "Independent two-proportion simulate_power(p0=, delta=) was removed in Phase 2.13. "
            "Use simulate_paired_power with joint pair probabilities."
        )
    return simulate_paired_power(**kwargs)
