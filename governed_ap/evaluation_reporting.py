from dataclasses import asdict, fields
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from governed_ap.benchmark_freeze import dataset_sha256
from governed_ap.evaluation_bootstrap import bootstrap_headline_intervals
from governed_ap.evaluation_harness import EvaluationRecord, count_actions
from governed_ap.evaluation_metrics import (
    HeadlineMetrics,
    Rate,
    calculate_headline_metrics,
)
from governed_ap.evaluation_secondary_metrics import (
    SecondaryMetrics,
    calculate_secondary_metrics,
)
from governed_ap.experiment_execution import ExperimentRun
from governed_ap.schemas import BenchmarkExample, DatasetSplit
from governed_ap.system_decision import SystemName


class MetricRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None


class IntervalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    estimate: float | None
    lower: float | None
    upper: float | None
    eligible_scenarios: int = Field(ge=0)
    resamples: int = Field(ge=0)


class ExecutionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempted_invoices: int = Field(ge=0)
    completed_invoices: int = Field(ge=0)
    system_failure_invoices: int = Field(ge=0)

    p50_latency_ms: float | None
    p95_latency_ms: float | None

    observed_llm_calls: int | None = Field(default=None, ge=0)
    failed_llm_calls: int = Field(ge=0)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    llm_cost_usd: Decimal | None = None

    input_token_covered_calls: int = Field(ge=0)
    output_token_covered_calls: int = Field(ge=0)
    cost_covered_calls: int = Field(ge=0)

    models_used: list[str]
    cost_basis_counts: dict[str, int]


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_version: str = "development-v1"
    run_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=7)
    system_name: SystemName
    execution_mode: Literal["test_double", "live_provider"]
    model_id: str | None

    input_mode: str = "structured_benchmark_case"
    replay_mode: str = "reference_path_plus_HT4"
    split: DatasetSplit = DatasetSplit.DEVELOPMENT

    benchmark_seed: int
    benchmark_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_count: int = Field(gt=0)
    invoice_count: int = Field(gt=0)

    action_counts: dict[str, int]
    headline_metrics: dict[str, MetricRecord]
    secondary_metrics: dict[str, MetricRecord]
    headline_intervals: dict[str, IntervalRecord]

    bootstrap_method: str = "scenario_percentile_95"
    bootstrap_seed: int
    bootstrap_repetitions: int = Field(ge=2)

    source_dirty: bool | None = None
    source_revision_origin: Literal["caller_supplied", "local_git"] = "caller_supplied"

    telemetry_status: Literal[
        "not_collected",
        "latency_only",
        "usage_partial",
        "usage_complete",
    ] = "not_collected"

    execution_summary: ExecutionSummary | None = None


def _metric_records(
    metrics: HeadlineMetrics | SecondaryMetrics,
) -> dict[str, MetricRecord]:
    result = {}

    for item in fields(metrics):
        rate: Rate = getattr(metrics, item.name)

        result[item.name] = MetricRecord(
            numerator=rate.numerator,
            denominator=rate.denominator,
            value=rate.value,
        )

    return result


def build_evaluation_report(
    scenarios: list[list[BenchmarkExample]],
    evaluated: list[list[EvaluationRecord]],
    *,
    run_id: str,
    source_revision: str,
    system_name: SystemName,
    execution_mode: Literal["test_double", "live_provider"],
    benchmark_seed: int,
    model_id: str | None = None,
    bootstrap_repetitions: int = 200,
    bootstrap_seed: int = 2026,
) -> EvaluationReport:
    if not run_id.strip() or not source_revision.strip():
        raise ValueError("Run ID and source revision are required.")

    if execution_mode == "live_provider" and not model_id:
        raise ValueError("Live provider runs require a model ID.")

    if not scenarios or len(scenarios) != len(evaluated):
        raise ValueError("Benchmark and evaluation scenario counts differ.")

    for original_scenario, evaluated_scenario in zip(scenarios, evaluated, strict=True):
        if len(original_scenario) != len(evaluated_scenario):
            raise ValueError("Evaluation has missing or extra invoices.")

        for original, record in zip(original_scenario, evaluated_scenario, strict=True):
            if original.ground_truth.split != DatasetSplit.DEVELOPMENT:
                raise ValueError("Only development reports are supported.")

            if record.example != original:
                raise ValueError("Evaluated example does not match benchmark.")

            if record.decision.system_name != system_name:
                raise ValueError("Inconsistent system identity in evaluation.")

    headline = calculate_headline_metrics(evaluated)
    secondary = calculate_secondary_metrics(evaluated)

    intervals = bootstrap_headline_intervals(
        evaluated,
        repetitions=bootstrap_repetitions,
        seed=bootstrap_seed,
    )

    return EvaluationReport(
        run_id=run_id,
        source_revision=source_revision,
        system_name=system_name,
        execution_mode=execution_mode,
        model_id=model_id,
        benchmark_seed=benchmark_seed,
        benchmark_sha256=dataset_sha256(scenarios),
        scenario_count=len(scenarios),
        invoice_count=sum(len(s) for s in scenarios),
        action_counts=count_actions(evaluated),
        headline_metrics=_metric_records(headline),
        secondary_metrics=_metric_records(secondary),
        headline_intervals={
            name: IntervalRecord(**asdict(interval)) for name, interval in intervals.items()
        },
        bootstrap_seed=bootstrap_seed,
        bootstrap_repetitions=bootstrap_repetitions,
    )


def build_report_from_experiment(
    scenarios: list[list[BenchmarkExample]],
    run: ExperimentRun,
    *,
    benchmark_seed: int,
    bootstrap_repetitions: int = 200,
    bootstrap_seed: int = 2026,
) -> EvaluationReport:
    expected_count = sum(len(scenario) for scenario in scenarios)

    if len(run.attempts) != expected_count or any(
        attempt.status != "COMPLETED" for attempt in run.attempts
    ):
        raise ValueError("Cannot report an incomplete experiment.")

    base = build_evaluation_report(
        scenarios,
        run.evaluated,
        run_id=run.run_id,
        source_revision=run.provenance.revision,
        system_name=run.system_name,
        execution_mode=run.execution_mode,
        model_id=run.model_id,
        benchmark_seed=benchmark_seed,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=bootstrap_seed,
    )

    telemetry = run.telemetry

    calls = [call for attempt in run.attempts for call in attempt.llm_calls]

    cost_basis_counts = {
        basis: sum(call.cost_basis == basis for call in calls)
        for basis in ("unknown", "estimated", "provider_reported")
    }

    if not run.usage_instrumented:
        status = "latency_only"
    elif (
        calls
        and telemetry.failed_llm_calls == 0
        and telemetry.input_token_covered_calls == len(calls)
        and telemetry.output_token_covered_calls == len(calls)
        and telemetry.cost_covered_calls == len(calls)
    ):
        status = "usage_complete"
    else:
        status = "usage_partial"

    summary = ExecutionSummary(
        attempted_invoices=telemetry.attempted_invoices,
        completed_invoices=telemetry.completed_invoices,
        system_failure_invoices=telemetry.system_failure_invoices,
        p50_latency_ms=telemetry.p50_latency_ms,
        p95_latency_ms=telemetry.p95_latency_ms,
        observed_llm_calls=telemetry.observed_llm_calls,
        failed_llm_calls=telemetry.failed_llm_calls,
        input_tokens=telemetry.input_tokens,
        output_tokens=telemetry.output_tokens,
        llm_cost_usd=telemetry.provider_cost_usd,
        input_token_covered_calls=telemetry.input_token_covered_calls,
        output_token_covered_calls=telemetry.output_token_covered_calls,
        cost_covered_calls=telemetry.cost_covered_calls,
        models_used=sorted({call.model for call in calls if call.model}),
        cost_basis_counts=cost_basis_counts,
    )

    payload = base.model_dump()
    payload.update(
        source_dirty=run.provenance.dirty,
        source_revision_origin="local_git",
        telemetry_status=status,
        execution_summary=summary.model_dump(),
    )

    return EvaluationReport.model_validate(payload)
