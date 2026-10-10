from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from time import perf_counter_ns
from typing import Literal

from governed_ap.evaluation_harness import (
    EvaluationRecord,
    normalize_decision,
    run_scenarios,
)
from governed_ap.git_provenance import (
    GitProvenance,
    read_git_provenance,
)
from governed_ap.governed_agent import GovernedAgentTrace
from governed_ap.schemas import (
    BenchmarkCase,
    BenchmarkExample,
    DatasetSplit,
    ExpectedAction,
)
from governed_ap.system_decision import SystemDecision, SystemName

ExecutionMode = Literal["test_double", "live_provider"]
ExecutionStatus = Literal["COMPLETED", "FAILED"]


@dataclass(frozen=True)
class InvoiceExecution:
    case_id: str
    latency_ms: float
    status: ExecutionStatus
    action: ExpectedAction | None
    system_failure_codes: tuple[str, ...] = ()
    error_type: str | None = None


@dataclass(frozen=True)
class ExecutionTelemetry:
    attempted_invoices: int
    completed_invoices: int
    system_failure_invoices: int
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_cost_usd: Decimal | None = None


@dataclass(frozen=True)
class ExperimentRun:
    run_id: str
    system_name: SystemName
    execution_mode: ExecutionMode
    model_id: str | None
    provenance: GitProvenance
    evaluated: list[list[EvaluationRecord]]
    attempts: tuple[InvoiceExecution, ...]

    @property
    def telemetry(self) -> ExecutionTelemetry:
        return summarize_execution(self.attempts)


class ExperimentExecutionError(RuntimeError):
    def __init__(self, attempts: tuple[InvoiceExecution, ...]) -> None:
        self.attempts = attempts
        super().__init__(
            "Experiment execution failed; no aggregate metrics "
            "should be published for this incomplete run."
        )


def _failure_codes(
    raw_result: SystemDecision | GovernedAgentTrace,
    decision: SystemDecision,
) -> tuple[str, ...]:
    codes = list(decision.reason_codes)

    if isinstance(raw_result, GovernedAgentTrace):
        for layer in raw_result.layer_results:
            codes.extend(layer.reason_codes)

        codes.extend(raw_result.recommendation.reason_codes)
        codes.extend(raw_result.enforcement.gate_reason_codes)

    return tuple(dict.fromkeys(code for code in codes if code.startswith("SYSTEM_")))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower

    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_execution(
    attempts: tuple[InvoiceExecution, ...],
) -> ExecutionTelemetry:
    latencies = [attempt.latency_ms for attempt in attempts]

    completed = sum(attempt.status == "COMPLETED" for attempt in attempts)

    failures = sum(
        attempt.status == "FAILED" or bool(attempt.system_failure_codes) for attempt in attempts
    )

    return ExecutionTelemetry(
        attempted_invoices=len(attempts),
        completed_invoices=completed,
        system_failure_invoices=failures,
        p50_latency_ms=(_percentile(latencies, 0.5) if latencies else None),
        p95_latency_ms=(_percentile(latencies, 0.95) if latencies else None),
    )


def run_experiment(
    scenarios: list[list[BenchmarkExample]],
    system: Callable[
        [BenchmarkCase],
        SystemDecision | GovernedAgentTrace,
    ],
    *,
    run_id: str,
    system_name: SystemName,
    execution_mode: ExecutionMode = "test_double",
    model_id: str | None = None,
    repository: str | Path = ".",
) -> ExperimentRun:
    if not run_id.strip():
        raise ValueError("Run ID cannot be empty.")

    if execution_mode not in {"test_double", "live_provider"}:
        raise ValueError("Unsupported execution mode.")

    if execution_mode == "live_provider" and not model_id:
        raise ValueError("Live provider runs require a model ID.")

    if not scenarios or any(not scenario for scenario in scenarios):
        raise ValueError("A nonempty benchmark is required.")

    if any(
        example.ground_truth.split != DatasetSplit.DEVELOPMENT
        for scenario in scenarios
        for example in scenario
    ):
        raise ValueError("Only development experiments are supported.")

    provenance = read_git_provenance(repository)
    attempts: list[InvoiceExecution] = []

    def timed_system(case: BenchmarkCase) -> SystemDecision:
        started = perf_counter_ns()

        try:
            raw_result = system(case)
            decision = normalize_decision(raw_result)

            if decision.system_name != system_name:
                raise ValueError("System identity mismatch.")

        except Exception as exc:
            elapsed_ms = max(0.0, (perf_counter_ns() - started) / 1_000_000)

            attempts.append(
                InvoiceExecution(
                    case_id=case.case_id,
                    latency_ms=elapsed_ms,
                    status="FAILED",
                    action=None,
                    error_type=type(exc).__name__,
                )
            )

            raise ExperimentExecutionError(tuple(attempts)) from exc

        elapsed_ms = max(0.0, (perf_counter_ns() - started) / 1_000_000)

        attempts.append(
            InvoiceExecution(
                case_id=case.case_id,
                latency_ms=elapsed_ms,
                status="COMPLETED",
                action=decision.action,
                system_failure_codes=_failure_codes(raw_result, decision),
            )
        )

        return decision

    evaluated = run_scenarios(scenarios, timed_system)

    return ExperimentRun(
        run_id=run_id,
        system_name=system_name,
        execution_mode=execution_mode,
        model_id=model_id,
        provenance=provenance,
        evaluated=evaluated,
        attempts=tuple(attempts),
    )
