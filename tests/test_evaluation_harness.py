from governed_ap.benchmark_generator import (
    generate_development_sequence_attack,
    generate_pilot_benchmark,
)
from governed_ap.deterministic_baseline import evaluate_deterministic_baseline
from governed_ap.evaluation_harness import (
    count_actions,
    run_scenarios,
)
from governed_ap.schemas import BenchmarkCase, ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


def test_pilot_runner_keeps_all_scenarios_and_invoices():
    scenarios = generate_pilot_benchmark()

    results = run_scenarios(
        scenarios,
        evaluate_deterministic_baseline,
    )

    assert len(results) == 60
    assert sum(len(scenario) for scenario in results) == 84
    assert sum(count_actions(results).values()) == 84


def test_system_receives_only_benchmark_case():
    scenarios = generate_pilot_benchmark()

    received_ids = []

    def fake_system(case: BenchmarkCase) -> SystemDecision:
        assert isinstance(case, BenchmarkCase)
        assert not hasattr(case, "ground_truth")

        received_ids.append(case.case_id)

        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=ExpectedAction.ESCALATE,
        )

    results = run_scenarios(scenarios, fake_system)

    assert len(received_ids) == 84
    assert count_actions(results)["ESCALATE"] == 84


def test_sequence_order_is_preserved():
    sequence = generate_development_sequence_attack(
        seed=2027,
        attack_subtype="T4.1",
    )

    results = run_scenarios(
        [sequence],
        evaluate_deterministic_baseline,
    )

    assert len(results) == 1
    assert [record.example.ground_truth.sequence_position for record in results[0]] == [1, 2, 3]


def test_invalid_system_result_is_rejected():
    scenarios = generate_pilot_benchmark()

    def invalid_system(case: BenchmarkCase):
        return None

    import pytest

    with pytest.raises(TypeError):
        run_scenarios(scenarios, invalid_system)
