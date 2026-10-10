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
from governed_ap.llm_usage import LLMCallUsage, UsageCollector
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
    llm_calls: tuple[LLMCallUsage, ...] = ()


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

    observed_llm_calls: int | None = None
    failed_llm_calls: int = 0
    input_token_covered_calls: int = 0
    output_token_covered_calls: int = 0
    cost_covered_calls: int = 0


@dataclass(frozen=True)
class ExperimentRun:
    run_id: str
    system_name: SystemName
    execution_mode: ExecutionMode
    model_id: str | None
    provenance: GitProvenance
    evaluated: list[list[EvaluationRecord]]
    attempts: tuple[InvoiceExecution, ...]
    usage_instrumented: bool = False

    @property
    def telemetry(self) -> ExecutionTelemetry:
        return summarize_execution(
            self.attempts,
            usage_instrumented=self.usage_instrumented,
        )


class ExperimentExecutionError(RuntimeError):
    def __init__(
        self,
        attempts: tuple[InvoiceExecution, ...],
    ) -> None:
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


def _percentile(
    values: list[float],
    fraction: float,
) -> float:
    ordered = sorted(values)

    position = (len(ordered) - 1) * fraction

    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)

    weight = position - lower

    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_execution(
    attempts: tuple[InvoiceExecution, ...],
    *,
    usage_instrumented: bool = False,
) -> ExecutionTelemetry:
    # Collect latency from all attempted invoices.
    latencies = [attempt.latency_ms for attempt in attempts]

    # An execution is completed if it returned a valid decision.
    completed = sum(attempt.status == "COMPLETED" for attempt in attempts)

    # Count both execution failures and recorded system failures.
    failures = sum(
        attempt.status == "FAILED" or bool(attempt.system_failure_codes) for attempt in attempts
    )

    # Collect all recorded LLM calls across invoices.
    calls = [call for attempt in attempts for call in attempt.llm_calls]

    def complete_total(attribute: str):
        """
        Return the total only when every observed LLM call
        provides a value for the requested attribute.

        Missing usage must not be silently treated as zero.
        """
        if not calls:
            return None

        values = [getattr(call, attribute) for call in calls]

        if any(value is None for value in values):
            return None

        return sum(values)

    return ExecutionTelemetry(
        attempted_invoices=len(attempts),
        completed_invoices=completed,
        system_failure_invoices=failures,
        p50_latency_ms=(_percentile(latencies, 0.5) if latencies else None),
        p95_latency_ms=(_percentile(latencies, 0.95) if latencies else None),
        input_tokens=complete_total("input_tokens"),
        output_tokens=complete_total("output_tokens"),
        provider_cost_usd=complete_total("cost_usd"),
        observed_llm_calls=(len(calls) if usage_instrumented else None),
        failed_llm_calls=sum(call.status == "FAILED" for call in calls),
        input_token_covered_calls=sum(call.input_tokens is not None for call in calls),
        output_token_covered_calls=sum(call.output_tokens is not None for call in calls),
        cost_covered_calls=sum(call.cost_usd is not None for call in calls),
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
    usage_collector: UsageCollector | None = None,
) -> ExperimentRun:
    # Validate experiment configuration.
    if not run_id.strip():
        raise ValueError("Run ID cannot be empty.")

    if execution_mode not in {
        "test_double",
        "live_provider",
    }:
        raise ValueError("Unsupported execution mode.")

    if execution_mode == "live_provider" and not model_id:
        raise ValueError("Live provider runs require a model ID.")

    if not scenarios or any(not scenario for scenario in scenarios):
        raise ValueError("A nonempty benchmark is required.")

    # Protect reserved benchmark splits.
    if any(
        example.ground_truth.split != DatasetSplit.DEVELOPMENT
        for scenario in scenarios
        for example in scenario
    ):
        raise ValueError("Only development experiments are supported.")

    # Read actual Git provenance.
    provenance = read_git_provenance(repository)

    attempts: list[InvoiceExecution] = []

    def timed_system(
        case: BenchmarkCase,
    ) -> SystemDecision:
        # Remember the usage collector position before this invoice.
        usage_mark = usage_collector.mark() if usage_collector is not None else None

        def current_calls() -> tuple[LLMCallUsage, ...]:
            """
            Return LLM calls recorded while processing
            this particular invoice.
            """
            if usage_mark is None or usage_collector is None:
                return ()

            return usage_collector.since(usage_mark)

        # Start timing the system execution.
        started = perf_counter_ns()

        try:
            # Execute the selected experimental system.
            raw_result = system(case)

            # Convert results to the common decision format.
            decision = normalize_decision(raw_result)

            # Verify the returned system identity.
            if decision.system_name != system_name:
                raise ValueError("System identity mismatch.")

        except Exception as exc:
            elapsed_ms = max(
                0.0,
                (perf_counter_ns() - started) / 1_000_000,
            )

            # Record failure without inventing a safe action.
            attempts.append(
                InvoiceExecution(
                    case_id=case.case_id,
                    latency_ms=elapsed_ms,
                    status="FAILED",
                    action=None,
                    error_type=type(exc).__name__,
                    llm_calls=current_calls(),
                )
            )

            raise ExperimentExecutionError(tuple(attempts)) from exc

        # Successful system execution.
        elapsed_ms = max(
            0.0,
            (perf_counter_ns() - started) / 1_000_000,
        )

        # Keep this invoice's action, failures, and LLM calls.
        attempts.append(
            InvoiceExecution(
                case_id=case.case_id,
                latency_ms=elapsed_ms,
                status="COMPLETED",
                action=decision.action,
                system_failure_codes=_failure_codes(
                    raw_result,
                    decision,
                ),
                llm_calls=current_calls(),
            )
        )

        return decision

    # Execute every development benchmark scenario.
    evaluated = run_scenarios(
        scenarios,
        timed_system,
    )

    # Return the complete run with usage instrumentation status.
    return ExperimentRun(
        run_id=run_id,
        system_name=system_name,
        execution_mode=execution_mode,
        model_id=model_id,
        provenance=provenance,
        evaluated=evaluated,
        attempts=tuple(attempts),
        usage_instrumented=(usage_collector is not None),
    )
