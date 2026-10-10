import random
from dataclasses import dataclass

from governed_ap.evaluation_harness import EvaluationRecord
from governed_ap.evaluation_metrics import (
    HeadlineMetrics,
    Rate,
    calculate_headline_metrics,
)

METRIC_NAMES = (
    "unsafe_action_rate",
    "benign_automation_coverage",
    "human_review_rate",
)


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float | None
    lower: float | None
    upper: float | None
    eligible_scenarios: int
    resamples: int


def _check_repetitions(repetitions: int) -> None:
    if repetitions < 2:
        raise ValueError("Bootstrap requires at least two repetitions.")


def _scenario_scores(
    scenarios: list[list[EvaluationRecord]],
) -> list[HeadlineMetrics]:
    if not scenarios:
        raise ValueError("Cannot bootstrap an empty evaluation.")

    # Validate all original scenarios together, including unique IDs.
    calculate_headline_metrics(scenarios)

    # Calculate each scenario's contribution once.
    return [calculate_headline_metrics([scenario]) for scenario in scenarios]


def _rate(summary: HeadlineMetrics, metric: str) -> Rate:
    return getattr(summary, metric)


def _pooled_rate(
    summaries: list[HeadlineMetrics],
    metric: str,
) -> Rate:
    return Rate(
        numerator=sum(_rate(row, metric).numerator for row in summaries),
        denominator=sum(_rate(row, metric).denominator for row in summaries),
    )


def _defined_value(rate: Rate) -> float:
    value = rate.value
    if value is None:
        raise ValueError("Cannot estimate a rate with zero denominator.")
    return value


def _percentile(sorted_values: list[float], fraction: float) -> float:
    position = (len(sorted_values) - 1) * fraction
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)

    weight = position - lower_index

    return sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight


def _interval(
    estimate: float | None,
    draws: list[float],
    eligible_scenarios: int,
) -> BootstrapInterval:
    if not draws:
        return BootstrapInterval(
            estimate=estimate,
            lower=None,
            upper=None,
            eligible_scenarios=eligible_scenarios,
            resamples=0,
        )

    ordered = sorted(draws)

    return BootstrapInterval(
        estimate=estimate,
        lower=_percentile(ordered, 0.025),
        upper=_percentile(ordered, 0.975),
        eligible_scenarios=eligible_scenarios,
        resamples=len(draws),
    )


def bootstrap_headline_intervals(
    scenarios: list[list[EvaluationRecord]],
    *,
    repetitions: int = 2000,
    seed: int = 2026,
) -> dict[str, BootstrapInterval]:
    _check_repetitions(repetitions)

    scores = _scenario_scores(scenarios)
    rng = random.Random(seed)
    results = {}

    for metric in METRIC_NAMES:
        eligible = [row for row in scores if _rate(row, metric).denominator > 0]

        if not eligible:
            results[metric] = _interval(None, [], 0)
            continue

        estimate = _defined_value(_pooled_rate(eligible, metric))
        draws = []

        for _ in range(repetitions):
            # Sample entire scenario summaries with replacement.
            sampled = [eligible[rng.randrange(len(eligible))] for _ in range(len(eligible))]

            draws.append(_defined_value(_pooled_rate(sampled, metric)))

        results[metric] = _interval(estimate, draws, len(eligible))

    return results


def bootstrap_paired_differences(
    left: list[list[EvaluationRecord]],
    right: list[list[EvaluationRecord]],
    *,
    repetitions: int = 2000,
    seed: int = 2026,
) -> dict[str, BootstrapInterval]:
    """Compute paired differences: left rate minus right rate."""
    _check_repetitions(repetitions)

    left_scores = _scenario_scores(left)
    right_scores = _scenario_scores(right)

    if len(left) != len(right):
        raise ValueError("Systems must evaluate the same scenarios.")

    right_by_id = {
        scenario[0].example.ground_truth.scenario_id: (scenario, summary)
        for scenario, summary in zip(right, right_scores, strict=True)
    }

    left_ids = {scenario[0].example.ground_truth.scenario_id for scenario in left}

    if left_ids != set(right_by_id):
        raise ValueError("Systems must evaluate the same scenarios.")

    aligned_pairs = []

    for scenario, left_summary in zip(left, left_scores, strict=True):
        scenario_id = scenario[0].example.ground_truth.scenario_id
        right_scenario, right_summary = right_by_id[scenario_id]

        if [record.example for record in scenario] != [record.example for record in right_scenario]:
            raise ValueError("Paired systems must use identical benchmark examples.")

        aligned_pairs.append((left_summary, right_summary))

    rng = random.Random(seed)
    results = {}

    for metric in METRIC_NAMES:
        eligible = []

        for left_summary, right_summary in aligned_pairs:
            left_rate = _rate(left_summary, metric)
            right_rate = _rate(right_summary, metric)

            if left_rate.denominator != right_rate.denominator:
                raise ValueError("Paired metric denominators differ.")

            if left_rate.denominator > 0:
                eligible.append((left_summary, right_summary))

        if not eligible:
            results[metric] = _interval(None, [], 0)
            continue

        estimate = _defined_value(
            _pooled_rate([pair[0] for pair in eligible], metric)
        ) - _defined_value(_pooled_rate([pair[1] for pair in eligible], metric))

        draws = []

        for _ in range(repetitions):
            # Identical sampled scenario indices for both systems.
            sampled = [eligible[rng.randrange(len(eligible))] for _ in range(len(eligible))]

            left_value = _defined_value(_pooled_rate([pair[0] for pair in sampled], metric))
            right_value = _defined_value(_pooled_rate([pair[1] for pair in sampled], metric))

            draws.append(left_value - right_value)

        results[metric] = _interval(estimate, draws, len(eligible))

    return results
