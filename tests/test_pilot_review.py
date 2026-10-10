import pytest

from governed_ap.benchmark_generator import generate_pilot_benchmark
from governed_ap.pilot_review import review_pilot
from governed_ap.schemas import DatasetSplit, ExpectedAction
from governed_ap.split_policy import HELD_OUT_ATTACK_SUBTYPES


@pytest.fixture
def pilot():
    return generate_pilot_benchmark(seed=2026)


def test_pilot_has_expected_size(pilot):
    report = review_pilot(pilot)

    assert report["scenario_count"] == 60
    assert report["invoice_count"] == 84
    assert report["malicious_scenarios"] == 26
    assert report["legitimate_scenarios"] == 34


def test_all_development_attack_subtypes_are_present(pilot):
    report = review_pilot(pilot)

    assert len(report["attack_subtypes"]) == 13
    assert all(count == 2 for count in report["attack_subtypes"].values())


def test_held_out_attacks_are_not_in_pilot(pilot):
    report = review_pilot(pilot)

    assert not (set(report["attack_subtypes"]) & set(HELD_OUT_ATTACK_SUBTYPES))


def test_pilot_summary_has_baseline_metrics(pilot):
    report = review_pilot(pilot)

    assert set(report["deterministic_baseline_metrics"]) == {
        "unsafe_action_rate",
        "benign_automation_coverage",
        "human_review_rate",
    }

    assert sum(report["deterministic_baseline_actions"].values()) == 84


def test_mismatched_oracle_label_is_rejected(pilot):
    first = pilot[0][0]

    replacement = (
        ExpectedAction.AUTO_APPROVE
        if first.ground_truth.expected_action != ExpectedAction.AUTO_APPROVE
        else ExpectedAction.ESCALATE
    )

    first.ground_truth.expected_action = replacement

    with pytest.raises(ValueError, match="Oracle action mismatch"):
        review_pilot(pilot)


def test_reserved_split_is_rejected(pilot):
    pilot[0][0].ground_truth.split = DatasetSplit.IID_TEST

    with pytest.raises(ValueError, match="Reserved split"):
        review_pilot(pilot)


def test_duplicate_scenario_is_rejected(pilot):
    pilot[1] = [example.model_copy(deep=True) for example in pilot[0]]

    with pytest.raises(ValueError, match="duplicate scenario"):
        review_pilot(pilot)


def test_length_screen_is_reported_as_diagnostic(pilot):
    report = review_pilot(pilot)

    score = report["length_only_in_sample_balanced_accuracy"]

    assert 0.5 <= score <= 1.0
    assert report["status"] == "DEVELOPMENT_AUDIT_ONLY"


def test_c10_lexical_controls_are_legitimate(pilot):
    report = review_pilot(pilot)

    assert report["legitimate_templates"]["C10-dev-v1"] == 6

    c10_examples = [
        example
        for scenario in pilot
        for example in scenario
        if example.ground_truth.template_id == "C10-dev-v1"
    ]

    assert len(c10_examples) == 6

    assert all(
        example.ground_truth.expected_action == ExpectedAction.AUTO_APPROVE
        for example in c10_examples
    )

    assert all(
        "INSTRUCTION_TEXT" not in example.ground_truth.expected_reason_codes
        for example in c10_examples
    )

    assert len({example.case.invoice.raw_text for example in c10_examples}) == 6


def test_pilot_has_eight_valid_matched_pairs(pilot):
    from collections import Counter, defaultdict

    pairs = defaultdict(list)

    for scenario in pilot:
        for example in scenario:
            pair_id = example.ground_truth.pair_id
            if pair_id is not None:
                pairs[pair_id].append(example)

    assert len(pairs) == 8

    paired_attack_types = Counter()

    for examples in pairs.values():
        assert len(examples) == 2

        attacks = [e for e in examples if e.ground_truth.is_malicious]
        controls = [e for e in examples if not e.ground_truth.is_malicious]

        assert len(attacks) == 1
        assert len(controls) == 1

        attack = attacks[0]
        control = controls[0]

        paired_attack_types[attack.ground_truth.attack_subtype] += 1

        assert attack.case.vendor == control.case.vendor
        assert attack.case.purchase_order == control.case.purchase_order
        assert attack.case.goods_receipts == control.case.goods_receipts
        assert attack.case.policy == control.case.policy
        assert attack.case.payment_history == control.case.payment_history

        # Only attack-relevant invoice fields may differ.
        excluded = {
            "raw_text",
            "vendor_name",
            "invoice_bank_account",
        }

        assert attack.case.invoice.model_dump(exclude=excluded) == control.case.invoice.model_dump(
            exclude=excluded
        )

        assert attack.ground_truth.expected_action == ExpectedAction.ESCALATE
        assert control.ground_truth.expected_action == ExpectedAction.AUTO_APPROVE

        assert attack.ground_truth.split == control.ground_truth.split == DatasetSplit.DEVELOPMENT

    assert paired_attack_types == Counter(
        {
            "T1.1": 2,
            "T1.2": 2,
            "T2.1": 2,
            "T2.3": 2,
        }
    )
