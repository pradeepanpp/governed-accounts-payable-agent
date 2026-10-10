import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from governed_ap.evaluation_reporting import EvaluationReport
from governed_ap.schemas import DatasetSplit


@dataclass(frozen=True)
class ReportArtifact:
    path: Path
    sha256: str
    size_bytes: int


def _validate_exportable(report: EvaluationReport) -> None:
    if report.split != DatasetSplit.DEVELOPMENT:
        raise ValueError("Only development reports can be exported.")

    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", report.run_id) is None:
        raise ValueError("Run ID contains unsafe filename characters.")

    if report.execution_mode == "live_provider" and not report.model_id:
        raise ValueError("Live provider reports require a model ID.")


def _canonical_report_bytes(report: EvaluationReport) -> bytes:
    payload = json.dumps(
        report.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    return (payload + "\n").encode("utf-8")


def write_evaluation_report(
    report: EvaluationReport,
    directory: str | Path = "runs/reports",
) -> ReportArtifact:
    _validate_exportable(report)

    output_directory = Path(directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    output_path = output_directory / f"evaluation_{report.run_id}.json"
    content = _canonical_report_bytes(report)
    digest = hashlib.sha256(content).hexdigest()

    # "xb" means create a new binary file exclusively.
    # It raises FileExistsError instead of overwriting an existing report.
    with output_path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())

    return ReportArtifact(
        path=output_path,
        sha256=digest,
        size_bytes=len(content),
    )


def verify_evaluation_report(
    path: str | Path,
    expected_sha256: str,
) -> EvaluationReport:
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("Expected SHA-256 must be 64 lowercase hex characters.")

    content = Path(path).read_bytes()
    actual_sha256 = hashlib.sha256(content).hexdigest()

    if actual_sha256 != expected_sha256:
        raise ValueError("Report SHA-256 mismatch.")

    try:
        report = EvaluationReport.model_validate_json(content)
    except ValidationError as exc:
        raise ValueError("Report does not match its schema.") from exc

    _validate_exportable(report)

    if content != _canonical_report_bytes(report):
        raise ValueError("Report is not in canonical JSON format.")

    return report
