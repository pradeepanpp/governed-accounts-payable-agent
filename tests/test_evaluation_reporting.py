import pytest

from governed_ap.benchmark_generator import (
    generate_legitimate_example,
    generate_pilot_benchmark,
)
from governed_ap.evaluation_harness import run_scenarios
from governed_ap.evaluation_reporting import build_evaluation_report
from governed_ap.schemas import DatasetSplit, ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


def fake_system(case):
    return SystemDecision(
        system_name=SystemName.DETERMINISTIC_BASELINE,
        action=ExpectedAction.ESCALATE,
    )


def make_report(scenarios, evaluated, **overrides):
    settings = {
        "run_id": "pilot-test-001",
        "source_revision": "deadbeef",
        "system_name": SystemName.DETERMINISTIC_BASELINE,
        "execution_mode": "test_double",
        "benchmark_seed": 2026,
        "bootstrap_repetitions": 100,
        "bootstrap_seed": 42,
    }
    settings.update(overrides)

    return build_evaluation_report(scenarios, evaluated, **settings)


def test_report_contains_benchmark_identity_and_metrics():
    scenarios = generate_pilot_benchmark()
    evaluated = run_scenarios(scenarios, fake_system)

    report = make_report(scenarios, evaluated)

    assert report.scenario_count == 60
    assert report.invoice_count == 84
    assert len(report.benchmark_sha256) == 64
    assert report.action_counts["ESCALATE"] == 84
    assert report.headline_metrics["unsafe_action_rate"].denominator == 26
    assert report.headline_intervals["unsafe_action_rate"].resamples == 100


def test_report_is_reproducible():
    example = generate_legitimate_example(9001, "C1")
    scenarios = [[example]]
    evaluated = run_scenarios(scenarios, fake_system)

    first = make_report(scenarios, evaluated)
    second = make_report(scenarios, evaluated)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_report_does_not_export_invoice_contents():
    example = generate_legitimate_example(9002, "C1")
    scenarios = [[example]]
    evaluated = run_scenarios(scenarios, fake_system)

    report_json = make_report(scenarios, evaluated).model_dump_json()

    assert example.case.invoice.raw_text not in report_json
    assert example.case.invoice.invoice_bank_account not in report_json
    assert report_json.find("ground_truth") == -1


def test_report_rejects_mismatched_benchmark():
    source = [[generate_legitimate_example(9003, "C1")]]
    different = [[generate_legitimate_example(9004, "C1")]]

    evaluated = run_scenarios(source, fake_system)

    with pytest.raises(ValueError, match="does not match"):
        make_report(different, evaluated)


def test_report_rejects_reserved_split():
    example = generate_legitimate_example(9005, "C1")
    example.ground_truth.split = DatasetSplit.IID_TEST

    scenarios = [[example]]
    evaluated = run_scenarios(scenarios, fake_system)

    with pytest.raises(ValueError, match="Only development"):
        make_report(scenarios, evaluated)


def test_report_rejects_incorrect_system_identity():
    example = generate_legitimate_example(9006, "C1")
    scenarios = [[example]]
    evaluated = run_scenarios(scenarios, fake_system)

    with pytest.raises(ValueError, match="system identity"):
        make_report(
            scenarios,
            evaluated,
            system_name=SystemName.NAIVE_LLM,
        )


def test_live_provider_requires_model_identity():
    example = generate_legitimate_example(9007, "C1")
    scenarios = [[example]]
    evaluated = run_scenarios(scenarios, fake_system)

    with pytest.raises(ValueError, match="model ID"):
        make_report(
            scenarios,
            evaluated,
            execution_mode="live_provider",
        )
