import pytest

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_development_sequence_attack,
    generate_legitimate_example,
    generate_pilot_benchmark,
)
from governed_ap.evaluation_bootstrap import (
    bootstrap_headline_intervals,
    bootstrap_paired_differences,
)
from governed_ap.evaluation_harness import run_scenarios
from governed_ap.schemas import ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


def constant_system(action):
    def system(case):
        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=action,
        )

    return system


def test_bootstrap_is_reproducible():
    scenarios = generate_pilot_benchmark()
    evaluated = run_scenarios(
        scenarios,
        constant_system(ExpectedAction.AUTO_APPROVE),
    )

    first = bootstrap_headline_intervals(evaluated, repetitions=100, seed=42)
    second = bootstrap_headline_intervals(evaluated, repetitions=100, seed=42)

    assert first == second
    assert first["unsafe_action_rate"].resamples == 100


def test_identical_systems_have_zero_paired_difference():
    scenarios = generate_pilot_benchmark()
    evaluated = run_scenarios(
        scenarios,
        constant_system(ExpectedAction.ESCALATE),
    )

    comparison = bootstrap_paired_differences(evaluated, evaluated, repetitions=100)

    for interval in comparison.values():
        assert interval.estimate == 0.0
        assert interval.lower == 0.0
        assert interval.upper == 0.0


def test_paired_difference_direction():
    scenarios = generate_pilot_benchmark()

    auto = run_scenarios(
        scenarios,
        constant_system(ExpectedAction.AUTO_APPROVE),
    )
    review = run_scenarios(
        scenarios,
        constant_system(ExpectedAction.ESCALATE),
    )

    comparison = bootstrap_paired_differences(auto, review, repetitions=100)

    assert comparison["unsafe_action_rate"].estimate == 1.0
    assert comparison["benign_automation_coverage"].estimate == 1.0
    assert comparison["human_review_rate"].estimate == -1.0


def test_t4_sequence_counts_as_one_bootstrap_unit():
    t4 = generate_development_sequence_attack(seed=8101, attack_subtype="T4.1")
    t1 = generate_development_attack_example(seed=8102, attack_subtype="T1.1")

    actions = iter(
        [
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.ESCALATE,
        ]
    )

    def system(case):
        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=next(actions),
        )

    evaluated = run_scenarios([t4, [t1]], system)

    result = bootstrap_headline_intervals(evaluated, repetitions=200, seed=45)["unsafe_action_rate"]

    assert result.eligible_scenarios == 2
    assert result.estimate == 0.5
    assert 0 <= result.lower <= result.upper <= 1


def test_undefined_metric_has_no_interval():
    c4 = generate_legitimate_example(8201, "C4")
    evaluated = run_scenarios(
        [[c4]],
        constant_system(ExpectedAction.ESCALATE),
    )

    result = bootstrap_headline_intervals(evaluated, repetitions=100)

    assert result["unsafe_action_rate"].estimate is None
    assert result["unsafe_action_rate"].lower is None
    assert result["benign_automation_coverage"].estimate is None
    assert result["human_review_rate"].estimate == 1.0


def test_pairing_rejects_different_benchmarks():
    c1 = generate_legitimate_example(8301, "C1")
    c2 = generate_legitimate_example(8302, "C1")

    left = run_scenarios([[c1]], constant_system(ExpectedAction.AUTO_APPROVE))
    right = run_scenarios([[c2]], constant_system(ExpectedAction.AUTO_APPROVE))

    with pytest.raises(ValueError, match="same scenarios"):
        bootstrap_paired_differences(left, right, repetitions=100)


def test_pairing_aligns_scenario_ids():
    c1 = generate_legitimate_example(8401, "C1")
    t1 = generate_development_attack_example(8402, "T1.1")

    left = run_scenarios(
        [[c1], [t1]],
        constant_system(ExpectedAction.ESCALATE),
    )
    right = run_scenarios(
        [[t1], [c1]],
        constant_system(ExpectedAction.ESCALATE),
    )

    results = bootstrap_paired_differences(left, right, repetitions=100)

    for interval in results.values():
        if interval.estimate is not None:
            assert interval.estimate == 0.0


def test_invalid_repetition_count_is_rejected():
    c1 = generate_legitimate_example(8501, "C1")
    evaluated = run_scenarios(
        [[c1]],
        constant_system(ExpectedAction.AUTO_APPROVE),
    )

    with pytest.raises(ValueError, match="at least two"):
        bootstrap_headline_intervals(evaluated, repetitions=1)
