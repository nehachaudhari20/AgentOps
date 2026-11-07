"""Phase 2.9 experimental dataset design, seeds, GT separation, observability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agenttrust.benchmark.dataset.attribution_reference import (
    ATTRIBUTION_REFERENCE_METHOD,
    build_attribution_reference,
)
from agenttrust.benchmark.dataset.corpus import generate_split, write_design_and_reports
from agenttrust.benchmark.dataset.design import (
    count_specs,
    design_fingerprint,
    iter_trace_specs,
)
from agenttrust.benchmark.dataset.observability import (
    ObservabilityClass,
    observability_matrix,
    primary_class,
)
from agenttrust.benchmark.dataset.power import power_report, simulate_power
from agenttrust.benchmark.dataset.seeds import (
    PILOT_SEED_MAX,
    SEED_BANDS,
    DatasetSplit,
    SeedAllocator,
    bands_disjoint,
)
from agenttrust.benchmark.dataset.validate_corpus import (
    validate_cross_split_isolation,
    validate_split,
)
from agenttrust.benchmark.faults import FaultType, PROHIBITED_ANSWER_KEYS
from agenttrust.benchmark.generator import BenchmarkGenerator
from agenttrust.benchmark.manifest import BenchmarkConfig, ScenarioId, ScaleTier, TopologyId
from tests.conftest import make_event


def test_bands_disjoint_from_pilot_and_each_other():
    assert bands_disjoint()
    for split, (lo, hi) in SEED_BANDS.items():
        assert lo > PILOT_SEED_MAX
        assert hi > lo


def test_design_counts_match_spec():
    assert count_specs(DatasetSplit.DEVELOPMENT)["n_traces"] == 276
    assert count_specs(DatasetSplit.VALIDATION)["n_traces"] == 522
    assert count_specs(DatasetSplit.HELDOUT_TEST)["n_traces"] == 798
    # unique seeds within each split
    for split in DatasetSplit:
        c = count_specs(split)
        assert c["n_unique_seeds"] == c["n_traces"]


def test_no_seed_overlap_across_splits():
    seeds = {s: {spec.seed for spec in iter_trace_specs(s)} for s in DatasetSplit}
    assert not (seeds[DatasetSplit.DEVELOPMENT] & seeds[DatasetSplit.VALIDATION])
    assert not (seeds[DatasetSplit.DEVELOPMENT] & seeds[DatasetSplit.HELDOUT_TEST])
    assert not (seeds[DatasetSplit.VALIDATION] & seeds[DatasetSplit.HELDOUT_TEST])


def test_matched_pair_integrity_in_design():
    specs = list(iter_trace_specs(DatasetSplit.DEVELOPMENT))
    by_pair: dict[str, list] = {}
    for s in specs:
        if s.matched_pair_id:
            by_pair.setdefault(s.matched_pair_id, []).append(s)
    assert by_pair
    for pid, members in by_pair.items():
        roles = {m.role for m in members}
        assert roles == {"pair_clean", "pair_fault"}
        assert len({m.split for m in members}) == 1
        assert len({m.seed for m in members}) == 2


def test_reproducible_specs():
    a = [s.to_dict() for s in iter_trace_specs(DatasetSplit.DEVELOPMENT)]
    b = [s.to_dict() for s in iter_trace_specs(DatasetSplit.DEVELOPMENT)]
    assert a == b
    assert design_fingerprint() == design_fingerprint()


def test_attribution_reference_independent_of_rpa():
    events = [
        make_event("e1", category="reasoning", agent_id="A"),
        make_event("e2", category="decision", event_type="action", deps=["e1"], agent_id="B"),
    ]
    ref = build_attribution_reference(events, ["e2"])
    assert ref.method == ATTRIBUTION_REFERENCE_METHOD
    out = ref.outcomes[0]
    assert abs(sum(out.root_event_allocations.values()) - 1.0) < 1e-12
    assert out.root_event_allocations["e1"] == 1.0
    # Must not import RPA/MFAV in this module path
    import agenttrust.benchmark.dataset.attribution_reference as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "from agenttrust.attribution" not in src
    assert "from agenttrust.accountability" not in src
    assert "import ConservedRPA" not in src


def test_all_fault_families_in_observability():
    matrix = observability_matrix()
    for f in FaultType:
        assert f.value in matrix["faults"]
        primary_class(f.value)
    assert (
        primary_class(FaultType.CONFLICTING_OUTPUTS.value)
        == ObservabilityClass.NOT_RELIABLY_DETECTABLE.value
    )


def test_power_simulation_deterministic():
    # Phase 2.13: paired McNemar simulation (independent p0/delta API removed)
    import pytest
    from agenttrust.benchmark.dataset.power import simulate_paired_power

    with pytest.raises(ValueError):
        simulate_power(n_pairs=72, p0=0.7, delta=0.2, n_sims=500, seed=1)
    a = simulate_paired_power(
        n_pairs=72,
        p_both=0.35,
        p_fault_only=0.21,
        p_clean_only=0.09,
        n_sims=500,
        seed=1,
    )
    b = simulate_paired_power(
        n_pairs=72,
        p_both=0.35,
        p_fault_only=0.21,
        p_clean_only=0.09,
        n_sims=500,
        seed=1,
    )
    assert a == b
    report = power_report(n_sims=200)
    assert report["heldout_incompleteness_pairs"] == 72
    assert report["report_version"] == "2.13.0"
    assert "simulation_grid" in report


def test_ground_truth_separation_on_generated_package(tmp_path: Path):
    cfg = BenchmarkConfig(
        scenario_id=ScenarioId.FINANCIAL_LOAN,
        topology_id=TopologyId.SEQUENTIAL,
        scale_tier=ScaleTier.S1,
        seed=10001,
    )
    gen = BenchmarkGenerator()
    pkg = gen.generate(cfg)
    # algorithm inputs must not contain prohibited keys
    blob = json.dumps(pkg.algorithm_inputs())
    for k in PROHIBITED_ANSWER_KEYS:
        assert k not in blob
    assert "attribution_reference" not in blob


def test_generate_split_smoke_and_validate(tmp_path: Path):
    root = tmp_path / "experimental_2_9"
    write_design_and_reports(root)
    res = generate_split(DatasetSplit.DEVELOPMENT, root=root, force=True, limit=4)
    assert res.n_planned == 4
    assert res.n_failed == 0
    assert res.n_written == 4
    v = validate_split(root / "splits" / "development")
    assert v["ok"], v["errors"]
    # Resume skips existing
    res2 = generate_split(DatasetSplit.DEVELOPMENT, root=root, force=False, limit=4)
    assert res2.n_skipped_existing == 4
    assert res2.n_written == 0


def test_partial_generation_failure_reported(tmp_path: Path, monkeypatch):
    root = tmp_path / "experimental_2_9"
    from agenttrust.benchmark.dataset import corpus as corpus_mod

    real_generate = BenchmarkGenerator.generate
    calls = {"n": 0}

    def flaky(self, config):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("planted generation failure")
        return real_generate(self, config)

    monkeypatch.setattr(BenchmarkGenerator, "generate", flaky)
    res = generate_split(DatasetSplit.DEVELOPMENT, root=root, force=True, limit=3)
    assert res.n_failed >= 1
    assert res.failures
    assert res.n_written + res.n_failed == 3


def test_duplicate_id_detection(tmp_path: Path):
    root = tmp_path / "experimental_2_9"
    generate_split(DatasetSplit.DEVELOPMENT, root=root, force=True, limit=2)
    cat_path = root / "splits" / "development" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    cat["entries"].append(dict(cat["entries"][0]))
    cat_path.write_text(json.dumps(cat), encoding="utf-8")
    v = validate_split(root / "splits" / "development")
    assert v["ok"] is False
    assert any("duplicate" in e for e in v["errors"])


def test_manifest_generator_version_mismatch(tmp_path: Path):
    root = tmp_path / "experimental_2_9"
    generate_split(DatasetSplit.DEVELOPMENT, root=root, force=True, limit=1)
    cat_path = root / "splits" / "development" / "catalog.json"
    cat = json.loads(cat_path.read_text(encoding="utf-8"))
    cat["entries"][0]["generator_version"] = "0.0.0-wrong"
    cat_path.write_text(json.dumps(cat), encoding="utf-8")
    v = validate_split(root / "splits" / "development")
    assert v["ok"] is False


def test_allocator_exhaustion():
    # Tiny fake: use real allocator until near end by monkeypatching hi
    alloc = SeedAllocator(DatasetSplit.DEVELOPMENT)
    alloc.hi = alloc.lo + 1
    alloc._next = alloc.lo
    alloc.next_seed()
    alloc.next_seed()
    with pytest.raises(ValueError, match="exhausted"):
        alloc.next_seed()
