from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_development_sequence_attack,
    generate_legitimate_example,
)
from governed_ap.evaluation_harness import run_scenarios
from governed_ap.evaluation_metrics import Rate
from governed_ap.evaluation_secondary_metrics import (
    calculate_secondary_metrics,
)
from governed_ap.schemas import ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


def evaluate_examples_with_actions(items):
    results = []

    for example, action in items:

        def fake_system(case):
            return SystemDecision(
                system_name=SystemName.DETERMINISTIC_BASELINE,
                action=action,
            )

        results.extend(run_scenarios([[example]], fake_system))

    return results


def test_secondary_metrics_on_mixed_examples():
    c1 = generate_legitimate_example(7001, "C1")
    c4 = generate_legitimate_example(7002, "C4")
    t1 = generate_development_attack_example(7003, "T1.1")
    t3 = generate_development_attack_example(7004, "T3.3")

    results = evaluate_examples_with_actions(
        [
            (c1, ExpectedAction.AUTO_APPROVE),
            (c4, ExpectedAction.ESCALATE),
            (t1, ExpectedAction.AUTO_APPROVE),
            (t3, ExpectedAction.BLOCK),
        ]
    )

    metrics = calculate_secondary_metrics(results)

    assert metrics.intervention_required_auto_approval == Rate(1, 3)
    assert metrics.malicious_intervention_auto_approval == Rate(1, 2)
    assert metrics.benign_intervention_auto_approval == Rate(0, 1)
    assert metrics.false_block_rate == Rate(0, 2)
    assert metrics.unnecessary_escalation_rate == Rate(0, 1)
    assert metrics.action_accuracy == Rate(3, 4)
    assert metrics.attack_containment_rate == Rate(1, 2)


def test_unnecessary_escalation():
    example = generate_legitimate_example(7101, "C1")

    results = evaluate_examples_with_actions([(example, ExpectedAction.ESCALATE)])

    metrics = calculate_secondary_metrics(results)

    assert metrics.unnecessary_escalation_rate == Rate(1, 1)


def test_legitimate_block_is_counted():
    example = generate_legitimate_example(7102, "C1")

    results = evaluate_examples_with_actions([(example, ExpectedAction.BLOCK)])

    metrics = calculate_secondary_metrics(results)

    assert metrics.false_block_rate == Rate(1, 1)


def test_undefined_denominators_remain_undefined():
    example = generate_legitimate_example(7103, "C1")

    results = evaluate_examples_with_actions([(example, ExpectedAction.AUTO_APPROVE)])

    metrics = calculate_secondary_metrics(results)

    assert metrics.intervention_required_auto_approval.value is None
    assert metrics.attack_containment_rate.value is None
    assert metrics.action_accuracy == Rate(1, 1)


def test_t4_containment_differs_from_reference_action_accuracy():
    scenario = generate_development_sequence_attack(
        seed=7104,
        attack_subtype="T4.1",
    )

    actions = iter(
        [
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.ESCALATE,
            ExpectedAction.AUTO_APPROVE,
        ]
    )

    def fake_system(case):
        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=next(actions),
        )

    results = run_scenarios([scenario], fake_system)

    metrics = calculate_secondary_metrics(results)

    assert metrics.attack_containment_rate == Rate(1, 1)
    assert metrics.intervention_required_auto_approval == Rate(1, 1)
    assert metrics.action_accuracy == Rate(1, 3)
