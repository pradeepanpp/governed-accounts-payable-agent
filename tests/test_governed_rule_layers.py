from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.deterministic_checks_layer import (
    DeterministicChecksLayer,
)
from governed_ap.governance_contracts import (
    LayerExecutionStatus,
)
from governed_ap.history_risk_layer import (
    HistorySequenceRiskLayer,
)
from governed_ap.schemas import (
    ExpectedAction,
)


def test_clean_case_passes_both_layers():
    example = generate_legitimate_example(
        seed=500,
        case_type="C1",
    )

    deterministic = DeterministicChecksLayer().evaluate(example.case)

    history = HistorySequenceRiskLayer().evaluate(example.case)

    assert deterministic.status == LayerExecutionStatus.PASS

    assert history.status == LayerExecutionStatus.PASS


def test_price_attack_fires_deterministic_layer():
    example = generate_development_attack_example(
        seed=501,
        attack_subtype="T3.1",
    )

    result = DeterministicChecksLayer().evaluate(example.case)

    assert result.status == LayerExecutionStatus.FIRED

    assert result.minimum_action == ExpectedAction.ESCALATE

    assert "PRICE_MISMATCH" in result.reason_codes


def test_quantity_attack_fires_deterministic_layer():
    example = generate_development_attack_example(
        seed=502,
        attack_subtype="T3.2",
    )

    result = DeterministicChecksLayer().evaluate(example.case)

    assert "QUANTITY_MISMATCH" in result.reason_codes


def test_exact_duplicate_blocks():
    example = generate_development_attack_example(
        seed=503,
        attack_subtype="T3.3",
    )

    result = DeterministicChecksLayer().evaluate(example.case)

    assert result.minimum_action == ExpectedAction.BLOCK

    assert "EXACT_DUPLICATE" in result.reason_codes


def test_tax_attack_fires_deterministic_layer():
    example = generate_development_attack_example(
        seed=504,
        attack_subtype="T3.5",
    )

    result = DeterministicChecksLayer().evaluate(example.case)

    assert "TAX_MISMATCH" in result.reason_codes


def test_conflicting_values_fire_deterministic_layer():
    example = generate_development_attack_example(
        seed=505,
        attack_subtype="T5.1",
    )

    result = DeterministicChecksLayer().evaluate(example.case)

    assert "CONFLICTING_VALUES" in result.reason_codes


def test_unordered_item_fires_deterministic_layer():
    example = generate_development_attack_example(
        seed=506,
        attack_subtype="T5.2",
    )

    result = DeterministicChecksLayer().evaluate(example.case)

    assert "UNORDERED_ITEMS" in result.reason_codes


def test_bank_change_fires_history_layer():
    example = generate_development_attack_example(
        seed=507,
        attack_subtype="T2.1",
    )

    result = HistorySequenceRiskLayer().evaluate(example.case)

    assert result.status == LayerExecutionStatus.FIRED

    assert "BANK_DETAILS_DIFFER" in result.reason_codes


def test_lookalike_vendor_fires_history_layer():
    example = generate_development_attack_example(
        seed=508,
        attack_subtype="T2.3",
    )

    result = HistorySequenceRiskLayer().evaluate(example.case)

    assert "VENDOR_PO_MISMATCH" in result.reason_codes


def test_third_party_payee_fires_history_layer():
    example = generate_legitimate_example(
        seed=509,
        case_type="C1",
    )

    example.case.invoice.requested_payee = "External Finance Company"

    result = HistorySequenceRiskLayer().evaluate(example.case)

    assert "THIRD_PARTY_PAYEE" in result.reason_codes


def test_near_duplicate_fires_both_layers():
    example = generate_development_attack_example(
        seed=510,
        attack_subtype="T3.3",
    )

    purchase_order = example.case.purchase_order

    assert purchase_order is not None

    # Convert the exact-duplicate fixture into a near-duplicate
    # without making the PO fully invoiced.
    example.case.invoice.invoice_id = "INV-NEW-NUMBER"

    purchase_order.quantity_ordered = example.case.invoice.quantity * 2

    purchase_order.total_amount = example.case.invoice.total_amount * 2

    deterministic = DeterministicChecksLayer().evaluate(example.case)

    history = HistorySequenceRiskLayer().evaluate(example.case)

    assert deterministic.minimum_action == ExpectedAction.ESCALATE

    assert history.minimum_action == ExpectedAction.ESCALATE

    assert "PO_FULLY_INVOICED" not in deterministic.reason_codes

    assert "POSSIBLE_DUPLICATE" in deterministic.reason_codes

    assert "POSSIBLE_DUPLICATE" in history.reason_codes


def test_instruction_attack_does_not_fire_python_rule_layers():
    example = generate_development_attack_example(
        seed=511,
        attack_subtype="T1.1",
    )

    deterministic = DeterministicChecksLayer().evaluate(example.case)

    history = HistorySequenceRiskLayer().evaluate(example.case)

    assert deterministic.status == LayerExecutionStatus.PASS

    assert history.status == LayerExecutionStatus.PASS
