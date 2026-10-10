from collections.abc import Callable
from dataclasses import dataclass

from governed_ap.governed_agent import GovernedAgentTrace
from governed_ap.schemas import BenchmarkCase, BenchmarkExample, ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


@dataclass(frozen=True)
class EvaluationRecord:
    example: BenchmarkExample
    decision: SystemDecision


def normalize_decision(
    result: SystemDecision | GovernedAgentTrace,
) -> SystemDecision:
    if isinstance(result, SystemDecision):
        return result

    if isinstance(result, GovernedAgentTrace):
        return SystemDecision(
            system_name=SystemName.GOVERNED_AGENT,
            action=result.final_action,
            reason_codes=result.enforcement.reason_codes,
            confidence=result.recommendation.confidence,
        )

    raise TypeError("System returned an unsupported decision type.")


def run_scenarios(
    scenarios: list[list[BenchmarkExample]],
    system: Callable[
        [BenchmarkCase],
        SystemDecision | GovernedAgentTrace,
    ],
) -> list[list[EvaluationRecord]]:
    if not scenarios:
        raise ValueError("The benchmark cannot be empty.")

    evaluated_scenarios = []

    for scenario in scenarios:
        if not scenario:
            raise ValueError("A benchmark scenario cannot be empty.")

        evaluated_invoices = []

        for example in scenario:
            # Pass observable data only. Never pass ground_truth.
            result = system(example.case)

            decision = normalize_decision(result)

            evaluated_invoices.append(
                EvaluationRecord(
                    example=example,
                    decision=decision,
                )
            )

        evaluated_scenarios.append(evaluated_invoices)

    return evaluated_scenarios


def count_actions(
    evaluated_scenarios: list[list[EvaluationRecord]],
) -> dict[str, int]:
    counts = {action.value: 0 for action in ExpectedAction}

    for scenario in evaluated_scenarios:
        for record in scenario:
            counts[record.decision.action.value] += 1

    return counts
