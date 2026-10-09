from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_development_sequence_attack,
    generate_legitimate_example,
)
from governed_ap.deterministic_baseline import (
    evaluate_deterministic_baseline,
)
from governed_ap.schemas import ExpectedAction
from governed_ap.system_decision import (
    SystemName,
)


def test_clean_invoice_is_auto_approved():
    example = generate_legitimate_example(
        seed=100,
        case_type="C1",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.system_name == SystemName.DETERMINISTIC_BASELINE

    assert decision.action == ExpectedAction.AUTO_APPROVE

    assert decision.reason_codes == []


def test_instruction_attack_is_not_detected_by_rules_baseline():
    example = generate_development_attack_example(
        seed=101,
        attack_subtype="T1.1",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.action == ExpectedAction.AUTO_APPROVE

    assert "INSTRUCTION_TEXT" not in decision.reason_codes


def test_bank_redirection_is_escalated():
    example = generate_development_attack_example(
        seed=102,
        attack_subtype="T2.1",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.action == ExpectedAction.ESCALATE

    assert "BANK_DETAILS_DIFFER" in decision.reason_codes


def test_price_attack_is_escalated():
    example = generate_development_attack_example(
        seed=103,
        attack_subtype="T3.1",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.action == ExpectedAction.ESCALATE

    assert "PRICE_MISMATCH" in decision.reason_codes


def test_exact_duplicate_is_blocked():
    example = generate_development_attack_example(
        seed=104,
        attack_subtype="T3.3",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.action == ExpectedAction.BLOCK

    assert "EXACT_DUPLICATE" in decision.reason_codes


def test_legitimate_high_value_invoice_escalates():
    example = generate_legitimate_example(
        seed=105,
        case_type="C4",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.action == ExpectedAction.ESCALATE

    assert "OVER_INVOICE_LIMIT" in decision.reason_codes


def test_t41_third_invoice_crosses_vendor_window():
    sequence = generate_development_sequence_attack(
        seed=106,
        attack_subtype="T4.1",
    )

    decisions = [evaluate_deterministic_baseline(example.case) for example in sequence]

    assert [decision.action for decision in decisions] == [
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.ESCALATE,
    ]

    assert "VENDOR_WINDOW_LIMIT" in decisions[2].reason_codes


def test_t42_third_invoice_crosses_po_limit():
    sequence = generate_development_sequence_attack(
        seed=107,
        attack_subtype="T4.2",
    )

    decisions = [evaluate_deterministic_baseline(example.case) for example in sequence]

    assert [decision.action for decision in decisions] == [
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.ESCALATE,
    ]

    assert "PO_CUMULATIVE_LIMIT" in decisions[2].reason_codes


def test_unordered_item_is_escalated():
    example = generate_development_attack_example(
        seed=108,
        attack_subtype="T5.2",
    )

    decision = evaluate_deterministic_baseline(example.case)

    assert decision.action == ExpectedAction.ESCALATE

    assert "UNORDERED_ITEMS" in decision.reason_codes
