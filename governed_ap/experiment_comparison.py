import hashlib
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from governed_ap.evaluation_bootstrap import bootstrap_paired_differences
from governed_ap.evaluation_reporting import (
    EvaluationReport,
    IntervalRecord,
    build_report_from_experiment,
)
from governed_ap.experiment_execution import ExperimentRun
from governed_ap.schemas import BenchmarkExample, DatasetSplit


class ComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    report_version: str = "development-comparison-v1"
    left: EvaluationReport
    right: EvaluationReport
    difference_direction: str = "left_minus_right"

    paired_differences: dict[str, IntervalRecord]

    p50_latency_difference_ms: float | None
    p95_latency_difference_ms: float | None
    llm_cost_difference_usd: Decimal | None

    warnings: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ComparisonArtifact:
    path: Path
    sha256: str


def _difference(left, right):
    if left is None or right is None:
        return None
    return left - right


def build_comparison_report(
    scenarios: list[list[BenchmarkExample]],
    left_run: ExperimentRun,
    right_run: ExperimentRun,
    *,
    benchmark_seed: int,
    bootstrap_repetitions: int = 200,
    bootstrap_seed: int = 2026,
) -> ComparisonReport:
    if left_run.run_id == right_run.run_id:
        raise ValueError("Comparison requires distinct run IDs.")

    if left_run.system_name == right_run.system_name:
        raise ValueError("Comparison requires different systems.")

    if left_run.execution_mode != right_run.execution_mode:
        raise ValueError("Execution modes must match.")

    if left_run.provenance.revision != right_run.provenance.revision:
        raise ValueError("Source revisions must match.")

    left = build_report_from_experiment(
        scenarios,
        left_run,
        benchmark_seed=benchmark_seed,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=bootstrap_seed,
    )

    right = build_report_from_experiment(
        scenarios,
        right_run,
        benchmark_seed=benchmark_seed,
        bootstrap_repetitions=bootstrap_repetitions,
        bootstrap_seed=bootstrap_seed,
    )

    if left.benchmark_sha256 != right.benchmark_sha256:
        raise ValueError("Benchmark fingerprints differ.")

    paired = bootstrap_paired_differences(
        left_run.evaluated,
        right_run.evaluated,
        repetitions=bootstrap_repetitions,
        seed=bootstrap_seed,
    )

    left_telemetry = left.execution_summary
    right_telemetry = right.execution_summary

    if left_telemetry is None or right_telemetry is None:
        raise ValueError("Both runs require execution telemetry.")

    warnings = []

    if left.source_dirty or right.source_dirty:
        warnings.append(
            "At least one run used a dirty working tree; "
            "the Git revision alone cannot reproduce its source."
        )

    if left.execution_mode == "test_double":
        warnings.append(
            "Test-double results validate evaluation infrastructure, "
            "not real LLM safety performance."
        )

    if left_telemetry.llm_cost_usd is None or right_telemetry.llm_cost_usd is None:
        warnings.append(
            "LLM cost comparison unavailable because at least one cost total is unknown."
        )
    else:
        warnings.append("Recorded LLM costs may be estimates, not billed charges.")

    return ComparisonReport(
        left=left,
        right=right,
        paired_differences={
            name: IntervalRecord(**vars(interval)) for name, interval in paired.items()
        },
        p50_latency_difference_ms=_difference(
            left_telemetry.p50_latency_ms,
            right_telemetry.p50_latency_ms,
        ),
        p95_latency_difference_ms=_difference(
            left_telemetry.p95_latency_ms,
            right_telemetry.p95_latency_ms,
        ),
        llm_cost_difference_usd=_difference(
            left_telemetry.llm_cost_usd,
            right_telemetry.llm_cost_usd,
        ),
        warnings=warnings,
    )


def _canonical_bytes(report: ComparisonReport) -> bytes:
    payload = json.dumps(
        report.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return (payload + "\n").encode("utf-8")


def _safe_id(value: str) -> bool:
    return (
        re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",
            value,
        )
        is not None
    )


def _validate_export(report: ComparisonReport) -> None:
    if (
        report.left.split != DatasetSplit.DEVELOPMENT
        or report.right.split != DatasetSplit.DEVELOPMENT
    ):
        raise ValueError("Only development comparisons can be exported.")

    if not all(_safe_id(run.run_id) for run in (report.left, report.right)):
        raise ValueError("Unsafe comparison run ID.")

    if report.left.benchmark_sha256 != report.right.benchmark_sha256:
        raise ValueError("Comparison benchmark mismatch.")


def write_comparison_report(
    report: ComparisonReport,
    directory: str | Path = "runs/reports",
) -> ComparisonArtifact:
    _validate_export(report)

    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / (f"comparison_{report.left.run_id}__{report.right.run_id}.json")

    content = _canonical_bytes(report)
    digest = hashlib.sha256(content).hexdigest()

    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())

    return ComparisonArtifact(path=path, sha256=digest)


def verify_comparison_report(
    path: str | Path,
    expected_sha256: str,
) -> ComparisonReport:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Invalid expected SHA-256.")

    content = Path(path).read_bytes()
    actual = hashlib.sha256(content).hexdigest()

    if actual != expected_sha256:
        raise ValueError("Comparison SHA-256 mismatch.")

    report = ComparisonReport.model_validate_json(content)
    _validate_export(report)

    if content != _canonical_bytes(report):
        raise ValueError("Noncanonical comparison JSON.")

    return report
