from datetime import timedelta

import pytest

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_development_sequence_attack,
    generate_legitimate_example,
)
from governed_ap.evaluation_harness import run_scenarios
from governed_ap.evaluation_metrics import Rate, calculate_headline_metrics
from governed_ap.schemas import ExpectedAction, PaymentRecord, PaymentStatus
from governed_ap.system_decision import SystemDecision, SystemName


def evaluate_with_actions(scenario, actions):
    action_iterator = iter(actions)

    def fake_system(case):
        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=next(action_iterator),
        )

    return run_scenarios([scenario], fake_system)


@pytest.mark.parametrize("subtype", ["T4.1", "T4.2", "T4.3"])
def test_t4_all_approvals_cross_limit(subtype):
    scenario = generate_development_sequence_attack(
        seed=3001,
        attack_subtype=subtype,
    )

    results = evaluate_with_actions(
        scenario,
        [ExpectedAction.AUTO_APPROVE] * 3,
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.unsafe_action_rate == Rate(1, 1)


@pytest.mark.parametrize("subtype", ["T4.1", "T4.2", "T4.3"])
def test_t4_last_invoice_escalation_prevents_violation(subtype):
    scenario = generate_development_sequence_attack(
        seed=3002,
        attack_subtype=subtype,
    )

    results = evaluate_with_actions(
        scenario,
        [
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.ESCALATE,
        ],
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.unsafe_action_rate == Rate(0, 1)
    assert metrics.human_review_rate == Rate(1, 3)


@pytest.mark.parametrize("subtype", ["T4.1", "T4.2", "T4.3"])
def test_t4_reference_history_is_not_double_counted(subtype):
    scenario = generate_development_sequence_attack(
        seed=3003,
        attack_subtype=subtype,
    )

    results = evaluate_with_actions(
        scenario,
        [
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.ESCALATE,
            ExpectedAction.AUTO_APPROVE,
        ],
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.unsafe_action_rate == Rate(0, 1)


def test_single_invoice_unsafe_auto_approval():
    example = generate_development_attack_example(
        seed=4001,
        attack_subtype="T1.1",
    )

    results = evaluate_with_actions(
        [example],
        [ExpectedAction.AUTO_APPROVE],
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.unsafe_action_rate == Rate(1, 1)


def test_benign_automation_coverage():
    example = generate_legitimate_example(
        seed=5001,
        case_type="C1",
    )

    results = evaluate_with_actions(
        [example],
        [ExpectedAction.AUTO_APPROVE],
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.benign_automation_coverage == Rate(1, 1)
    assert metrics.human_review_rate == Rate(0, 1)


def test_zero_denominator_is_undefined():
    example = generate_legitimate_example(
        seed=5002,
        case_type="C4",
    )

    results = evaluate_with_actions(
        [example],
        [ExpectedAction.ESCALATE],
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.unsafe_action_rate.value is None
    assert metrics.benign_automation_coverage.value is None
    assert metrics.human_review_rate == Rate(1, 1)


def test_incomplete_t4_sequence_is_rejected():
    scenario = generate_development_sequence_attack(
        seed=6001,
        attack_subtype="T4.1",
    )

    results = evaluate_with_actions(
        scenario[:2],
        [ExpectedAction.AUTO_APPROVE] * 2,
    )

    with pytest.raises(ValueError, match="three ordered positions"):
        calculate_headline_metrics(results)


def test_out_of_order_t4_sequence_is_rejected():
    scenario = generate_development_sequence_attack(
        seed=6002,
        attack_subtype="T4.1",
    )

    reordered = [scenario[1], scenario[0], scenario[2]]

    results = evaluate_with_actions(
        reordered,
        [ExpectedAction.AUTO_APPROVE] * 3,
    )

    with pytest.raises(ValueError, match="three ordered positions"):
        calculate_headline_metrics(results)


@pytest.mark.parametrize(
    ("was_auto_approved", "expected_unsafe"),
    [
        (True, Rate(1, 1)),
        (False, Rate(0, 1)),
    ],
)
def test_t4_external_history_eligibility(
    was_auto_approved,
    expected_unsafe,
):
    scenario = generate_development_sequence_attack(
        seed=6003,
        attack_subtype="T4.1",
    )

    first_case = scenario[0].case

    seed_payment = PaymentRecord(
        payment_id="PAY-EXTERNAL",
        invoice_id="INV-EXTERNAL",
        vendor_id=first_case.vendor.vendor_id,
        po_id="PO-EXTERNAL",
        amount="20000.00",
        currency=first_case.invoice.currency,
        payment_date=first_case.invoice.invoice_date - timedelta(days=1),
        status=PaymentStatus.PAID,
        was_auto_approved=was_auto_approved,
    )

    for example in scenario:
        example.case.payment_history.append(seed_payment.model_copy(deep=True))

    results = evaluate_with_actions(
        scenario,
        [
            ExpectedAction.AUTO_APPROVE,
            ExpectedAction.ESCALATE,
            ExpectedAction.ESCALATE,
        ],
    )

    metrics = calculate_headline_metrics(results)

    assert metrics.unsafe_action_rate == expected_unsafe


def test_duplicate_scenario_is_rejected():
    example = generate_legitimate_example(
        seed=6004,
        case_type="C1",
    )

    results = evaluate_with_actions(
        [example],
        [ExpectedAction.AUTO_APPROVE],
    )

    with pytest.raises(ValueError, match="Duplicate scenario"):
        calculate_headline_metrics(results + results)
