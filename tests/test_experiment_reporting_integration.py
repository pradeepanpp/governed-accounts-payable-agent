from dataclasses import replace
from decimal import Decimal
from functools import partial

import pytest

from governed_ap.benchmark_generator import generate_legitimate_example
from governed_ap.deterministic_baseline import evaluate_deterministic_baseline
from governed_ap.evaluation_reporting import build_report_from_experiment
from governed_ap.experiment_execution import run_experiment
from governed_ap.git_provenance import GitProvenance
from governed_ap.llm_usage import (
    CompletionWithUsage,
    MeteredTextProvider,
    UsageCollector,
)
from governed_ap.naive_llm_baseline import evaluate_naive_llm
from governed_ap.system_decision import SystemName


class MeasuredProvider:
    def complete_with_usage(self, *, system_prompt, user_prompt):
        return CompletionWithUsage(
            text=('{"action":"AUTO_APPROVE","reason_codes":[],"confidence":0.8}'),
            input_tokens=100,
            output_tokens=20,
            cost_usd=Decimal("0.002"),
            cost_basis="estimated",
            provider="test",
            model="test/model",
        )


@pytest.fixture(autouse=True)
def fixed_revision(monkeypatch):
    monkeypatch.setattr(
        "governed_ap.experiment_execution.read_git_provenance",
        lambda repository: GitProvenance(
            revision="b" * 40,
            dirty=True,
        ),
    )


def _scenarios():
    return [[generate_legitimate_example(9501, "C1")]]


def test_measured_experiment_produces_telemetry_report():
    collector = UsageCollector()
    provider = MeteredTextProvider(
        MeasuredProvider(),
        collector,
        role="naive",
    )

    scenarios = _scenarios()

    run = run_experiment(
        scenarios,
        partial(evaluate_naive_llm, provider=provider),
        run_id="dev-telemetry-report",
        system_name=SystemName.NAIVE_LLM,
        usage_collector=collector,
    )

    report = build_report_from_experiment(
        scenarios,
        run,
        benchmark_seed=9501,
        bootstrap_repetitions=20,
    )

    assert report.source_revision == "b" * 40
    assert report.source_dirty is True
    assert report.source_revision_origin == "local_git"
    assert report.telemetry_status == "usage_complete"

    summary = report.execution_summary
    assert summary.attempted_invoices == 1
    assert summary.input_tokens == 100
    assert summary.output_tokens == 20
    assert summary.llm_cost_usd == Decimal("0.002")
    assert summary.models_used == ["test/model"]
    assert summary.cost_basis_counts["estimated"] == 1


def test_uninstrumented_run_reports_latency_only():
    scenarios = _scenarios()

    run = run_experiment(
        scenarios,
        evaluate_deterministic_baseline,
        run_id="dev-latency-only",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    report = build_report_from_experiment(
        scenarios,
        run,
        benchmark_seed=9501,
        bootstrap_repetitions=20,
    )

    assert report.telemetry_status == "latency_only"
    assert report.execution_summary.input_tokens is None
    assert report.execution_summary.llm_cost_usd is None
    assert report.execution_summary.p50_latency_ms is not None


def test_incomplete_run_cannot_be_reported():
    scenarios = _scenarios()

    run = run_experiment(
        scenarios,
        evaluate_deterministic_baseline,
        run_id="dev-incomplete-test",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    incomplete = replace(run, attempts=())

    with pytest.raises(ValueError, match="incomplete experiment"):
        build_report_from_experiment(
            scenarios,
            incomplete,
            benchmark_seed=9501,
            bootstrap_repetitions=20,
        )
