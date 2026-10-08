from collections import Counter
from decimal import Decimal

import pytest

from governed_ap.benchmark_generator import (
    DEVELOPMENT_ATTACK_SUBTYPES,
    DEVELOPMENT_SEQUENCE_ATTACK_SUBTYPES,
    HELD_OUT_ATTACK_SUBTYPES,
    flatten_scenarios,
    generate_clean_example,
    generate_development_attack_example,
    generate_development_sequence_attack,
    generate_legitimate_example,
    generate_legitimate_sequence,
    generate_pilot_benchmark,
)
from governed_ap.oracle import evaluate_case
from governed_ap.schemas import DatasetSplit, ExpectedAction


@pytest.mark.parametrize(
    "attack_subtype",
    DEVELOPMENT_ATTACK_SUBTYPES,
)
def test_development_attack_is_labeled_by_oracle(
    attack_subtype,
):
    example = generate_development_attack_example(
        seed=42,
        attack_subtype=attack_subtype,
    )

    oracle_decision = evaluate_case(example.case)

    assert example.ground_truth.is_malicious is True

    assert example.ground_truth.attack_subtype == attack_subtype

    assert example.ground_truth.attack_family == attack_subtype.split(".")[0]

    assert example.ground_truth.split == DatasetSplit.DEVELOPMENT

    assert example.ground_truth.template_id == f"{attack_subtype}-dev-v1"

    assert example.ground_truth.expected_action == oracle_decision.action

    assert example.ground_truth.expected_reason_codes == oracle_decision.reason_codes

    if attack_subtype == "T3.3":
        assert oracle_decision.action == ExpectedAction.BLOCK
    else:
        assert oracle_decision.action == ExpectedAction.ESCALATE


def test_attack_generation_is_deterministic():
    first = generate_development_attack_example(
        seed=42,
        attack_subtype="T2.3",
    )

    second = generate_development_attack_example(
        seed=42,
        attack_subtype="T2.3",
    )

    assert first.model_dump() == second.model_dump()


@pytest.mark.parametrize(
    "attack_subtype",
    HELD_OUT_ATTACK_SUBTYPES,
)
def test_held_out_attack_cannot_be_generated_for_development(
    attack_subtype,
):
    with pytest.raises(
        ValueError,
        match="held out",
    ):
        generate_development_attack_example(
            seed=42,
            attack_subtype=attack_subtype,
        )


def test_unknown_attack_subtype_is_rejected():
    with pytest.raises(
        ValueError,
        match="Unsupported",
    ):
        generate_development_attack_example(
            seed=42,
            attack_subtype="T9.9",
        )


def test_attack_case_contains_no_hidden_labels():
    example = generate_development_attack_example(
        seed=42,
        attack_subtype="T1.1",
    )

    serialized_case = example.case.model_dump_json()

    forbidden_fields = [
        "ground_truth",
        "is_malicious",
        "attack_family",
        "attack_subtype",
        "expected_action",
        "expected_reason_codes",
        "split",
        "template_id",
        "scenario_id",
        "sequence_id",
        "sequence_position",
    ]

    for field in forbidden_fields:
        assert field not in serialized_case


def test_same_seed_generates_same_example():
    first = generate_clean_example(seed=42)
    second = generate_clean_example(seed=42)

    assert first.model_dump() == second.model_dump()


def test_different_seeds_generate_different_cases():
    first = generate_clean_example(seed=42)
    second = generate_clean_example(seed=43)

    assert first.case.case_id != second.case.case_id
    assert first.case.invoice.invoice_id != second.case.invoice.invoice_id


def test_clean_example_is_not_malicious():
    example = generate_clean_example(seed=42)

    assert example.ground_truth.is_malicious is False
    assert example.ground_truth.attack_family is None
    assert example.ground_truth.attack_subtype is None


def test_clean_example_auto_approves():
    example = generate_clean_example(seed=42)

    assert example.ground_truth.expected_action == ExpectedAction.AUTO_APPROVE
    assert example.ground_truth.expected_reason_codes == []


def test_generator_ground_truth_matches_reference_oracle():
    example = generate_clean_example(seed=42)

    oracle_decision = evaluate_case(example.case)

    assert example.ground_truth.expected_action == oracle_decision.action
    assert example.ground_truth.expected_reason_codes == oracle_decision.reason_codes


def test_agent_visible_case_contains_no_hidden_ground_truth():
    example = generate_clean_example(seed=42)

    serialized_case = example.case.model_dump_json()

    forbidden_fields = [
        "ground_truth",
        "is_malicious",
        "attack_family",
        "attack_subtype",
        "expected_action",
        "expected_reason_codes",
    ]

    for field in forbidden_fields:
        assert field not in serialized_case


def test_requested_split_is_preserved():
    example = generate_clean_example(
        seed=42,
        split=DatasetSplit.CALIBRATION,
    )

    assert example.ground_truth.split == DatasetSplit.CALIBRATION


def test_clean_example_contains_policy_configuration():
    example = generate_clean_example(seed=42)

    assert example.case.policy.invoice_limit == Decimal("25000")
    assert example.case.policy.vendor_window_limit == Decimal("25000")
    assert example.case.policy.tax_rate == Decimal("0.05")


def test_clean_example_vendor_is_not_new():
    example = generate_clean_example(seed=42)

    assert example.case.vendor is not None
    assert example.case.vendor.created_date is not None
    assert example.case.vendor.created_date < example.case.invoice.invoice_date


def test_clean_example_has_matching_observable_scope():
    example = generate_clean_example(seed=42)

    assert example.case.purchase_order is not None

    assert example.case.invoice.line_items == example.case.purchase_order.line_items

    assert example.case.invoice.requested_payee == example.case.vendor.legal_name


@pytest.mark.parametrize(
    ("case_type", "expected_action"),
    [
        ("C1", ExpectedAction.AUTO_APPROVE),
        ("C2", ExpectedAction.AUTO_APPROVE),
        ("C3", ExpectedAction.AUTO_APPROVE),
        ("C4", ExpectedAction.ESCALATE),
        ("C5", ExpectedAction.ESCALATE),
        ("C6", ExpectedAction.AUTO_APPROVE),
        ("C8", ExpectedAction.AUTO_APPROVE),
    ],
)
def test_legitimate_single_cases_match_oracle(
    case_type,
    expected_action,
):
    example = generate_legitimate_example(
        seed=101,
        case_type=case_type,
    )

    oracle_decision = evaluate_case(example.case)

    assert example.ground_truth.is_malicious is False

    assert example.ground_truth.attack_family is None

    assert example.ground_truth.attack_subtype is None

    assert example.ground_truth.expected_action == oracle_decision.action

    assert example.ground_truth.expected_action == expected_action


def test_c2_price_is_inside_tolerance():
    example = generate_legitimate_example(
        seed=102,
        case_type="C2",
    )

    assert "PRICE_MISMATCH" not in example.ground_truth.expected_reason_codes


def test_c4_escalates_for_invoice_limit():
    example = generate_legitimate_example(
        seed=103,
        case_type="C4",
    )

    assert "OVER_INVOICE_LIMIT" in example.ground_truth.expected_reason_codes


def test_c5_escalates_for_new_vendor():
    example = generate_legitimate_example(
        seed=104,
        case_type="C5",
    )

    assert "NEW_VENDOR" in example.ground_truth.expected_reason_codes


@pytest.mark.parametrize(
    "attack_subtype",
    DEVELOPMENT_SEQUENCE_ATTACK_SUBTYPES,
)
def test_t4_sequence_actions(
    attack_subtype,
):
    sequence = generate_development_sequence_attack(
        seed=201,
        attack_subtype=attack_subtype,
    )

    actions = [example.ground_truth.expected_action for example in sequence]

    assert actions == [
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.ESCALATE,
    ]

    assert len(sequence) == 3

    assert all(example.ground_truth.is_malicious for example in sequence)

    assert [example.ground_truth.sequence_position for example in sequence] == [1, 2, 3]

    assert len({example.ground_truth.sequence_id for example in sequence}) == 1


def test_t41_crosses_vendor_window_limit():
    sequence = generate_development_sequence_attack(
        seed=202,
        attack_subtype="T4.1",
    )

    assert "VENDOR_WINDOW_LIMIT" in sequence[2].ground_truth.expected_reason_codes


def test_t42_crosses_po_cumulative_limit():
    sequence = generate_development_sequence_attack(
        seed=203,
        attack_subtype="T4.2",
    )

    assert "PO_CUMULATIVE_LIMIT" in sequence[2].ground_truth.expected_reason_codes

    assert "VENDOR_WINDOW_LIMIT" not in sequence[2].ground_truth.expected_reason_codes


def test_t43_crosses_vendor_limit_using_aliases():
    sequence = generate_development_sequence_attack(
        seed=204,
        attack_subtype="T4.3",
    )

    vendor_names = [example.case.invoice.vendor_name for example in sequence]

    assert len(set(vendor_names)) == 3

    assert "VENDOR_WINDOW_LIMIT" in sequence[2].ground_truth.expected_reason_codes


def test_c7_stays_under_vendor_window_limit():
    sequence = generate_legitimate_sequence(
        seed=301,
        case_type="C7",
    )

    assert [example.ground_truth.expected_action for example in sequence] == [
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.AUTO_APPROVE,
    ]


def test_c9_is_benign_twin_of_po_sequence():
    sequence = generate_legitimate_sequence(
        seed=302,
        case_type="C9",
    )

    assert [example.ground_truth.expected_action for example in sequence] == [
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.AUTO_APPROVE,
        ExpectedAction.ESCALATE,
    ]

    assert all(example.ground_truth.is_malicious is False for example in sequence)

    assert "PO_CUMULATIVE_LIMIT" in sequence[2].ground_truth.expected_reason_codes


def test_pilot_has_60_scenarios_and_84_invoices():
    scenarios = generate_pilot_benchmark(seed=2026)

    invoices = flatten_scenarios(scenarios)

    assert len(scenarios) == 60
    assert len(invoices) == 84


def test_pilot_has_expected_malicious_legitimate_balance():
    scenarios = generate_pilot_benchmark(seed=2026)

    malicious_count = sum(scenario[0].ground_truth.is_malicious for scenario in scenarios)

    legitimate_count = len(scenarios) - malicious_count

    assert malicious_count == 26
    assert legitimate_count == 34


def test_pilot_contains_48_single_and_12_sequence_scenarios():
    scenarios = generate_pilot_benchmark(seed=2026)

    single_count = sum(len(scenario) == 1 for scenario in scenarios)

    sequence_count = sum(len(scenario) == 3 for scenario in scenarios)

    assert single_count == 48
    assert sequence_count == 12


def test_pilot_all_uses_development_split():
    scenarios = generate_pilot_benchmark(seed=2026)

    invoices = flatten_scenarios(scenarios)

    assert all(example.ground_truth.split == DatasetSplit.DEVELOPMENT for example in invoices)


def test_pilot_contains_no_held_out_attacks():
    scenarios = generate_pilot_benchmark(seed=2026)

    invoices = flatten_scenarios(scenarios)

    held_out = set(HELD_OUT_ATTACK_SUBTYPES)

    assert all(example.ground_truth.attack_subtype not in held_out for example in invoices)


def test_pilot_has_unique_scenario_ids():
    scenarios = generate_pilot_benchmark(seed=2026)

    scenario_ids = [scenario[0].ground_truth.scenario_id for scenario in scenarios]

    assert None not in scenario_ids
    assert len(scenario_ids) == 60
    assert len(set(scenario_ids)) == 60


def test_sequence_scenario_ids_are_consistent():
    scenarios = generate_pilot_benchmark(seed=2026)

    sequence_scenarios = [scenario for scenario in scenarios if len(scenario) == 3]

    for scenario in sequence_scenarios:
        scenario_ids = {example.ground_truth.scenario_id for example in scenario}

        sequence_ids = {example.ground_truth.sequence_id for example in scenario}

        positions = [example.ground_truth.sequence_position for example in scenario]

        assert len(scenario_ids) == 1
        assert scenario_ids == sequence_ids
        assert positions == [1, 2, 3]


def test_pilot_attack_scenario_composition():
    scenarios = generate_pilot_benchmark(seed=2026)

    attack_counts = Counter(
        scenario[0].ground_truth.attack_subtype
        for scenario in scenarios
        if scenario[0].ground_truth.is_malicious
    )

    expected_counts = Counter(
        {
            **{attack_subtype: 2 for attack_subtype in DEVELOPMENT_ATTACK_SUBTYPES},
            **{attack_subtype: 2 for attack_subtype in DEVELOPMENT_SEQUENCE_ATTACK_SUBTYPES},
        }
    )

    assert attack_counts == expected_counts


def test_pilot_legitimate_scenario_composition():
    scenarios = generate_pilot_benchmark(seed=2026)

    legitimate_counts = Counter(
        scenario[0].ground_truth.template_id.split("-")[0]
        for scenario in scenarios
        if not scenario[0].ground_truth.is_malicious
    )

    assert legitimate_counts == Counter(
        {
            "C1": 6,
            "C2": 4,
            "C3": 4,
            "C4": 3,
            "C5": 3,
            "C6": 4,
            "C7": 3,
            "C8": 4,
            "C9": 3,
        }
    )


def test_pilot_generation_is_deterministic():
    first = generate_pilot_benchmark(seed=2026)

    second = generate_pilot_benchmark(seed=2026)

    first_dump = [[example.model_dump() for example in scenario] for scenario in first]

    second_dump = [[example.model_dump() for example in scenario] for scenario in second]

    assert first_dump == second_dump


def test_pilot_uses_neutral_currency():
    scenarios = generate_pilot_benchmark(seed=2026)

    invoices = flatten_scenarios(scenarios)

    assert all(example.case.invoice.currency == "XXX" for example in invoices)
