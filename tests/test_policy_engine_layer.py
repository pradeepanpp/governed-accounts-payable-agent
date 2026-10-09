from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_development_sequence_attack,
    generate_legitimate_example,
    generate_legitimate_sequence,
)
from governed_ap.governance_contracts import (
    LayerExecutionStatus,
)
from governed_ap.policy_engine_layer import (
    PolicyEngineLayer,
)
from governed_ap.schemas import (
    ExpectedAction,
)


def test_standard_invoice_passes_policy():
    example = generate_legitimate_example(
        seed=600,
        case_type="C1",
    )

    result = PolicyEngineLayer().evaluate(example.case)

    assert result.status == LayerExecutionStatus.PASS


def test_high_value_invoice_fires_p1():
    example = generate_legitimate_example(
        seed=601,
        case_type="C4",
    )

    result = PolicyEngineLayer().evaluate(example.case)

    assert result.minimum_action == ExpectedAction.ESCALATE

    assert "OVER_INVOICE_LIMIT" in result.reason_codes


def test_new_vendor_fires_p4():
    example = generate_legitimate_example(
        seed=602,
        case_type="C5",
    )

    result = PolicyEngineLayer().evaluate(example.case)

    assert "NEW_VENDOR" in result.reason_codes


def test_t41_crosses_vendor_window_limit():
    sequence = generate_development_sequence_attack(
        seed=603,
        attack_subtype="T4.1",
    )

    results = [PolicyEngineLayer().evaluate(example.case) for example in sequence]

    assert [result.status for result in results] == [
        LayerExecutionStatus.PASS,
        LayerExecutionStatus.PASS,
        LayerExecutionStatus.FIRED,
    ]

    assert "VENDOR_WINDOW_LIMIT" in results[2].reason_codes


def test_c7_stays_below_vendor_window_limit():
    sequence = generate_legitimate_sequence(
        seed=604,
        case_type="C7",
    )

    results = [PolicyEngineLayer().evaluate(example.case) for example in sequence]

    assert all(result.status == LayerExecutionStatus.PASS for result in results)


def test_t42_crosses_po_cumulative_limit():
    sequence = generate_development_sequence_attack(
        seed=605,
        attack_subtype="T4.2",
    )

    results = [PolicyEngineLayer().evaluate(example.case) for example in sequence]

    assert results[0].status == LayerExecutionStatus.PASS

    assert results[1].status == LayerExecutionStatus.PASS

    assert "PO_CUMULATIVE_LIMIT" in results[2].reason_codes


def test_c9_legitimate_sequence_still_obeys_p3():
    sequence = generate_legitimate_sequence(
        seed=606,
        case_type="C9",
    )

    results = [PolicyEngineLayer().evaluate(example.case) for example in sequence]

    assert "PO_CUMULATIVE_LIMIT" in results[2].reason_codes


def test_t43_aliases_share_vendor_window():
    sequence = generate_development_sequence_attack(
        seed=607,
        attack_subtype="T4.3",
    )

    results = [PolicyEngineLayer().evaluate(example.case) for example in sequence]

    assert "VENDOR_WINDOW_LIMIT" in results[2].reason_codes


def test_instruction_attack_does_not_fire_policy():
    example = generate_development_attack_example(
        seed=608,
        attack_subtype="T1.1",
    )

    result = PolicyEngineLayer().evaluate(example.case)

    assert result.status == LayerExecutionStatus.PASS
