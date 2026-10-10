import json
from collections import Counter

from governed_ap.benchmark_freeze import dataset_sha256
from governed_ap.benchmark_generator import generate_pilot_benchmark
from governed_ap.deterministic_baseline import evaluate_deterministic_baseline
from governed_ap.evaluation_harness import run_scenarios
from governed_ap.evaluation_metrics import calculate_headline_metrics
from governed_ap.oracle import evaluate_case
from governed_ap.schemas import BenchmarkExample, DatasetSplit
from governed_ap.split_policy import HELD_OUT_ATTACK_SUBTYPES


def _rate_dict(rate):
    return {
        "numerator": rate.numerator,
        "denominator": rate.denominator,
        "value": rate.value,
    }


def _length_shortcut_screen(
    samples: list[tuple[int, bool]],
) -> float:
    """
    Find the best length-only threshold on the pilot.

    This is a diagnostic, not a held-out classifier result.
    """
    attacks = sum(malicious for _, malicious in samples)
    benign = len(samples) - attacks

    if not attacks or not benign:
        raise ValueError("Both attack and benign scenarios are required.")

    best = 0.0
    lengths = {length for length, _ in samples}

    for threshold in lengths:
        for attack_if_long in (True, False):
            correct_attack = 0
            correct_benign = 0

            for length, malicious in samples:
                predicted_attack = length >= threshold if attack_if_long else length <= threshold

                if malicious and predicted_attack:
                    correct_attack += 1

                if not malicious and not predicted_attack:
                    correct_benign += 1

            balanced_accuracy = (correct_attack / attacks + correct_benign / benign) / 2

            best = max(best, balanced_accuracy)

    return round(best, 4)


def review_pilot(
    scenarios: list[list[BenchmarkExample]],
) -> dict:
    """Audit a development pilot without modifying benchmark data."""
    problems = []
    seen_scenarios = set()
    seen_cases = set()

    attack_types = Counter()
    benign_types = Counter()
    expected_actions = Counter()
    lengths = []

    malicious_count = 0
    benign_count = 0
    invoice_count = 0

    for scenario in scenarios:
        if not scenario:
            problems.append("Empty scenario")
            continue

        first = scenario[0].ground_truth
        scenario_id = first.scenario_id

        if not scenario_id or scenario_id in seen_scenarios:
            problems.append(f"Invalid or duplicate scenario: {scenario_id}")

        seen_scenarios.add(scenario_id)

        if first.is_malicious:
            malicious_count += 1
            attack_types[first.attack_subtype or "UNKNOWN"] += 1
        else:
            benign_count += 1
            benign_types[first.template_id or "UNKNOWN"] += 1

        lengths.append(
            (
                sum(len(example.case.invoice.raw_text) for example in scenario),
                first.is_malicious,
            )
        )

        invoice_ids = set()
        dates = []

        for position, example in enumerate(scenario, start=1):
            truth = example.ground_truth
            case = example.case
            invoice_count += 1

            if truth.split != DatasetSplit.DEVELOPMENT:
                problems.append(f"Reserved split encountered: {case.case_id}")

            if truth.scenario_id != scenario_id:
                problems.append(f"Inconsistent scenario: {case.case_id}")

            if truth.is_malicious != first.is_malicious:
                problems.append(f"Mixed maliciousness: {scenario_id}")

            if truth.template_id != first.template_id:
                problems.append(f"Mixed templates: {scenario_id}")

            if case.case_id in seen_cases:
                problems.append(f"Duplicate case ID: {case.case_id}")

            seen_cases.add(case.case_id)

            if case.invoice.invoice_id in invoice_ids:
                problems.append(f"Repeated invoice in {scenario_id}")

            invoice_ids.add(case.invoice.invoice_id)
            dates.append(case.invoice.invoice_date)

            if len(scenario) > 1:
                if truth.sequence_id != scenario_id or truth.sequence_position != position:
                    problems.append(f"Sequence order error: {scenario_id}")
            elif truth.sequence_id is not None:
                problems.append(f"Unexpected sequence metadata: {scenario_id}")

            if truth.attack_subtype in HELD_OUT_ATTACK_SUBTYPES:
                problems.append(f"Held-out attack leaked: {case.case_id}")

            oracle_decision = evaluate_case(case)

            if truth.expected_action != oracle_decision.action:
                problems.append(f"Oracle action mismatch: {case.case_id}")

            if truth.expected_reason_codes != oracle_decision.reason_codes:
                problems.append(f"Oracle reason mismatch: {case.case_id}")

            expected_actions[truth.expected_action.value] += 1

        if dates != sorted(dates):
            problems.append(f"Unordered dates: {scenario_id}")

    if len(scenarios) != 60 or invoice_count != 84:
        problems.append("Pilot size differs from 60 scenarios / 84 invoices")

    if malicious_count != 26 or benign_count != 34:
        problems.append("Pilot attack/benign distribution differs")

    expected_legitimate_templates = {
        "C1-dev-v1": 4,
        "C2-dev-v1": 3,
        "C3-dev-v1": 3,
        "C4-dev-v1": 3,
        "C5-dev-v1": 3,
        "C6-dev-v1": 3,
        "C7-dev-v1": 3,
        "C8-dev-v1": 3,
        "C9-dev-v1": 3,
        "C10-dev-v1": 6,
    }

    if dict(benign_types) != expected_legitimate_templates:
        problems.append("Pilot legitimate-template composition differs from v0.3")

    if problems:
        raise ValueError("Pilot integrity failed:\n" + "\n".join(problems))

    evaluated = run_scenarios(
        scenarios,
        evaluate_deterministic_baseline,
    )

    metrics = calculate_headline_metrics(evaluated)

    baseline_actions = Counter(
        record.decision.action.value for scenario in evaluated for record in scenario
    )

    return {
        "status": "DEVELOPMENT_AUDIT_ONLY",
        "scenario_count": len(scenarios),
        "invoice_count": invoice_count,
        "malicious_scenarios": malicious_count,
        "legitimate_scenarios": benign_count,
        "dataset_sha256": dataset_sha256(scenarios),
        "attack_subtypes": dict(sorted(attack_types.items())),
        "legitimate_templates": dict(sorted(benign_types.items())),
        "reference_actions": dict(sorted(expected_actions.items())),
        "deterministic_baseline_actions": dict(sorted(baseline_actions.items())),
        "deterministic_baseline_metrics": {
            "unsafe_action_rate": _rate_dict(metrics.unsafe_action_rate),
            "benign_automation_coverage": _rate_dict(metrics.benign_automation_coverage),
            "human_review_rate": _rate_dict(metrics.human_review_rate),
        },
        "length_only_in_sample_balanced_accuracy": (_length_shortcut_screen(lengths)),
        "interpretation": (
            "Pilot debugging only. Length screen is fitted and "
            "evaluated on the same data, not held-out validation. "
            "Oracle consistency is not independent label validation."
        ),
    }


def main():
    pilot = generate_pilot_benchmark(seed=2026)
    report = review_pilot(pilot)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
