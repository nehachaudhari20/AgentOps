"""
Trace-level evaluation metrics (Phase 2.10–2.11).

Formulas and empty-set behavior are explicit. Failed/ineligible cases are not
silently discarded by these functions — callers manage denominators.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional, Sequence


def _aligned(
    pred: Mapping[str, float],
    truth: Mapping[str, float],
) -> tuple[list[str], list[float], list[float]]:
    keys = sorted(set(pred) | set(truth))
    p = [float(pred.get(k, 0.0)) for k in keys]
    t = [float(truth.get(k, 0.0)) for k in keys]
    return keys, p, t


def mae(pred: Mapping[str, float], truth: Mapping[str, float]) -> float:
    """Mean absolute error over the union support (zeros for absent keys)."""
    keys, p, t = _aligned(pred, truth)
    if not keys:
        return float("nan")
    return sum(abs(a - b) for a, b in zip(p, t)) / float(len(keys))


def rmse(pred: Mapping[str, float], truth: Mapping[str, float]) -> float:
    keys, p, t = _aligned(pred, truth)
    if not keys:
        return float("nan")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p, t)) / float(len(keys)))


def spearman(pred: Mapping[str, float], truth: Mapping[str, float]) -> float:
    """Spearman rank correlation on union support; NaN if undefined."""
    keys, p, t = _aligned(pred, truth)
    n = len(keys)
    if n < 2:
        return float("nan")

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: (vals[i], keys[i]))
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rp, rt = ranks(p), ranks(t)
    mp = sum(rp) / n
    mt = sum(rt) / n
    num = sum((a - mp) * (b - mt) for a, b in zip(rp, rt))
    denp = math.sqrt(sum((a - mp) ** 2 for a in rp))
    dent = math.sqrt(sum((b - mt) ** 2 for b in rt))
    if denp <= 0 or dent <= 0:
        return float("nan")
    return num / (denp * dent)


def top_k_agreement(
    pred: Mapping[str, float],
    truth: Mapping[str, float],
    k: int = 1,
) -> float:
    """Jaccard of top-k agent sets (by mass, ties broken by agent id)."""
    if k <= 0:
        return float("nan")

    def top(m: Mapping[str, float]) -> set[str]:
        items = sorted(m.items(), key=lambda kv: (-kv[1], kv[0]))
        return {a for a, _ in items[:k]}

    # Include zeros so empty pred/truth behave clearly
    keys = set(pred) | set(truth)
    p = {k: float(pred.get(k, 0.0)) for k in keys}
    t = {k: float(truth.get(k, 0.0)) for k in keys}
    if not keys:
        return float("nan")
    A, B = top(p), top(t)
    if not A and not B:
        return 1.0
    return len(A & B) / float(len(A | B))


def total_variation(pred: Mapping[str, float], truth: Mapping[str, float]) -> float:
    """½ Σ |p-t| over union support."""
    keys, p, t = _aligned(pred, truth)
    if not keys:
        return float("nan")
    return 0.5 * sum(abs(a - b) for a, b in zip(p, t))


def edge_prf(
    predicted: set[tuple[str, str]],
    reference: set[tuple[str, str]],
) -> dict[str, float]:
    """Precision/recall/F1 for edge sets. Empty ref+pred → all 1.0; empty one side handled."""
    if not predicted and not reference:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "tp": 0, "fp": 0, "fn": 0}
    tp = len(predicted & reference)
    fp = len(predicted - reference)
    fn = len(reference - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
    }


def mean_ci_bootstrap(
    values: Sequence[float],
    *,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> dict[str, float]:
    """Percentile bootstrap CI for the mean; NaNs dropped with count noted by caller."""
    import random

    xs = [float(v) for v in values if v == v]
    if not xs:
        return {"mean": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"), "n": 0.0}
    rng = random.Random(seed)
    means = []
    n = len(xs)
    for _ in range(n_boot):
        sample = [xs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_i = int(math.floor(alpha / 2 * n_boot))
    hi_i = int(math.ceil((1 - alpha / 2) * n_boot)) - 1
    hi_i = min(max(hi_i, 0), n_boot - 1)
    return {
        "mean": sum(xs) / n,
        "ci_low": means[lo_i],
        "ci_high": means[hi_i],
        "n": float(n),
    }


def paired_mean_diff_ci(
    a: Sequence[float],
    b: Sequence[float],
    *,
    n_boot: int = 2000,
    seed: int = 0,
) -> dict[str, float]:
    """Bootstrap CI for mean(a_i - b_i)."""
    diffs = [float(x) - float(y) for x, y in zip(a, b) if x == x and y == y]
    return mean_ci_bootstrap(diffs, n_boot=n_boot, seed=seed)


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Effect size Cliff's δ for paired or unpaired samples of equal interest."""
    xs = [float(v) for v in a if v == v]
    ys = [float(v) for v in b if v == v]
    if not xs or not ys:
        return float("nan")
    gt = sum(1 for x in xs for y in ys if x > y)
    lt = sum(1 for x in xs for y in ys if x < y)
    return (gt - lt) / float(len(xs) * len(ys))


def holm_correct(pvalues: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Holm–Bonferroni adjusted p-values for a confirmatory family."""
    items = sorted(((k, float(p)) for k, p in pvalues), key=lambda kv: kv[1])
    m = len(items)
    adj: dict[str, float] = {}
    prev = 0.0
    for i, (k, p) in enumerate(items):
        val = min(1.0, (m - i) * p)
        val = max(val, prev)
        adj[k] = val
        prev = val
    return adj
