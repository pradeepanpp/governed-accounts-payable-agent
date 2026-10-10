import pytest

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.git_provenance import GitProvenance
from governed_ap.governance_ablation import ALL_LAYERS
from governed_ap.governance_ablation_runner import (
    compare_ablations_to_full,
    run_ablation_suite,
)
from governed_ap.schemas import ExpectedAction


class FakeProvider:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def complete(self, *, system_prompt, user_prompt):
        self.calls += 1
        return self.response


@pytest.fixture(autouse=True)
def fixed_git(monkeypatch):
    monkeypatch.setattr(
        "governed_ap.experiment_execution.read_git_provenance",
        lambda repository: GitProvenance(
            revision="e" * 40,
            dirty=False,
        ),
    )


def scenarios():
    return [
        [generate_legitimate_example(11001, "C1")],
        [generate_legitimate_example(11002, "C4")],
        [generate_development_attack_example(11003, "T3.3")],
    ]


def providers_for(config):
    return (
        FakeProvider('{"flagged":false,"reason_codes":[]}'),
        FakeProvider('{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.9}'),
    )


def test_all_conditions_run_with_duplicate_execution_reused():
    created = []

    def factory(config):
        created.append(config.name)
        return providers_for(config)

    suite = run_ablation_suite(
        scenarios(),
        factory,
    )

    assert len(suite.results) == 9
    assert suite.unique_execution_count == 8
    assert len(created) == 8

    assert suite.by_name("full_governance").config.enabled_layers == (ALL_LAYERS)


def test_duplicate_layer_sets_share_the_same_run():
    suite = run_ablation_suite(scenarios(), providers_for)

    ladder_three = next(
        result for result in suite.results if result.config.name.startswith("ladder_3_")
    )

    without_policy = next(
        result
        for result in suite.results
        if result.config.name.startswith("without_")
        and result.config.enabled_layers == ladder_three.config.enabled_layers
    )

    assert without_policy.reused
    assert without_policy.run is ladder_three.run
    assert without_policy.executed_as == ladder_three.config.name


def test_all_unique_runs_have_complete_execution_records():
    suite = run_ablation_suite(scenarios(), providers_for)

    for result in suite.results:
        run = result.run

        assert len(run.evaluated) == 3
        assert run.telemetry.attempted_invoices == 3
        assert run.telemetry.completed_invoices == 3
        assert run.telemetry.system_failure_invoices == 0


def test_disabled_guardrail_saves_llm_calls():
    suite = run_ablation_suite(scenarios(), providers_for)

    minimal = suite.by_name("decision_and_gate_only")
    full = suite.by_name("full_governance")

    assert minimal.run.telemetry.observed_llm_calls == 3
    assert full.run.telemetry.observed_llm_calls == 6

    assert minimal.run.telemetry.provider_cost_usd is None
    assert full.run.telemetry.provider_cost_usd is None


def test_policy_removal_changes_reference_decision():
    suite = run_ablation_suite(scenarios(), providers_for)

    full = suite.by_name("full_governance")
    without_policy = next(
        result
        for result in suite.results
        if result.config.enabled_layers
        == ALL_LAYERS - {next(layer for layer in ALL_LAYERS if layer.value == "policy_engine")}
    )

    # Second scenario is legitimate C4: policy review required.
    assert full.run.evaluated[1][0].decision.action == ExpectedAction.ESCALATE

    assert without_policy.run.evaluated[1][0].decision.action == ExpectedAction.AUTO_APPROVE


def test_paired_comparisons_use_full_governance_as_reference():
    suite = run_ablation_suite(scenarios(), providers_for)

    comparisons = compare_ablations_to_full(
        suite,
        repetitions=50,
        seed=42,
    )

    assert len(comparisons) == 8

    minimal = comparisons["decision_and_gate_only"]

    assert "unsafe_action_rate" in minimal
    assert "benign_automation_coverage" in minimal
    assert "human_review_rate" in minimal

    # Minimal governance should not have lower UAR in this
    # fixed-response development test.
    assert minimal["unsafe_action_rate"].estimate >= 0


def test_repeated_runs_are_deterministic_with_fake_providers():
    first = run_ablation_suite(scenarios(), providers_for)
    second = run_ablation_suite(scenarios(), providers_for)

    for left, right in zip(first.results, second.results, strict=True):
        left_actions = [
            record.decision.action for scenario in left.run.evaluated for record in scenario
        ]

        right_actions = [
            record.decision.action for scenario in right.run.evaluated for record in scenario
        ]

        assert left_actions == right_actions


def test_duplicate_configuration_names_are_rejected():
    from governed_ap.governance_ablation import ablation_plan

    same = ablation_plan()[0]

    with pytest.raises(ValueError, match="names must be unique"):
        run_ablation_suite(
            scenarios(),
            providers_for,
            configurations=(same, same),
        )


def test_empty_plan_is_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        run_ablation_suite(
            scenarios(),
            providers_for,
            configurations=(),
        )
