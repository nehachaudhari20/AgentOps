"""Split seed bands and matched-pair seed allocation (Phase 2.9)."""

from __future__ import annotations

from enum import Enum


class DatasetSplit(str, Enum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    HELDOUT_TEST = "heldout_test"


# Historical pilot used small seeds; keep clear of experimental bands.
PILOT_SEED_MAX = 200

SEED_BANDS: dict[DatasetSplit, tuple[int, int]] = {
    DatasetSplit.DEVELOPMENT: (10_000, 19_999),
    DatasetSplit.VALIDATION: (20_000, 29_999),
    DatasetSplit.HELDOUT_TEST: (30_000, 39_999),
}


def assert_seed_in_split(seed: int, split: DatasetSplit) -> None:
    lo, hi = SEED_BANDS[split]
    if not (lo <= int(seed) <= hi):
        raise ValueError(f"seed {seed} outside band for {split.value}: [{lo},{hi}]")
    if int(seed) <= PILOT_SEED_MAX:
        raise ValueError(f"seed {seed} overlaps historical pilot band")


def bands_disjoint() -> bool:
    ranges = list(SEED_BANDS.values())
    for i, (a0, a1) in enumerate(ranges):
        if a0 <= PILOT_SEED_MAX:
            return False
        for b0, b1 in ranges[i + 1 :]:
            if not (a1 < b0 or b1 < a0):
                return False
    return True


class SeedAllocator:
    """Monotonic seed allocator within a split band (collision-free)."""

    def __init__(self, split: DatasetSplit) -> None:
        self.split = split
        self.lo, self.hi = SEED_BANDS[split]
        self._next = self.lo

    def next_seed(self) -> int:
        if self._next > self.hi:
            raise ValueError(f"seed band exhausted for {self.split.value}")
        seed = self._next
        self._next += 1
        assert_seed_in_split(seed, self.split)
        return seed
