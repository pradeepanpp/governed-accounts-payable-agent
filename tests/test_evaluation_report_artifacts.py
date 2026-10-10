import hashlib

import pytest

from governed_ap.benchmark_generator import generate_legitimate_example
from governed_ap.evaluation_harness import run_scenarios
from governed_ap.evaluation_report_artifacts import (
    verify_evaluation_report,
    write_evaluation_report,
)
from governed_ap.evaluation_reporting import build_evaluation_report
from governed_ap.schemas import DatasetSplit, ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


def _make_report():
    example = generate_legitimate_example(
        seed=9101,
        case_type="C1",
    )

    scenarios = [[example]]

    def fake_system(case):
        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=ExpectedAction.AUTO_APPROVE,
        )

    evaluated = run_scenarios(scenarios, fake_system)

    return build_evaluation_report(
        scenarios,
        evaluated,
        run_id="development-test-001",
        source_revision="deadbeef",
        system_name=SystemName.DETERMINISTIC_BASELINE,
        execution_mode="test_double",
        benchmark_seed=9101,
        bootstrap_repetitions=20,
        bootstrap_seed=42,
    )


def test_report_round_trip(tmp_path):
    report = _make_report()

    artifact = write_evaluation_report(report, tmp_path)
    restored = verify_evaluation_report(
        artifact.path,
        artifact.sha256,
    )

    assert restored == report
    assert artifact.size_bytes == artifact.path.stat().st_size
    assert artifact.path.suffix == ".json"


def test_report_export_is_deterministic(tmp_path):
    report = _make_report()

    first = write_evaluation_report(report, tmp_path / "first")
    second = write_evaluation_report(report, tmp_path / "second")

    assert first.sha256 == second.sha256
    assert first.path.read_bytes() == second.path.read_bytes()


def test_existing_report_is_not_overwritten(tmp_path):
    report = _make_report()

    first = write_evaluation_report(report, tmp_path)
    original_content = first.path.read_bytes()

    with pytest.raises(FileExistsError):
        write_evaluation_report(report, tmp_path)

    assert first.path.read_bytes() == original_content


def test_unsafe_run_id_is_rejected(tmp_path):
    report = _make_report().model_copy(update={"run_id": "../outside"})

    with pytest.raises(ValueError, match="unsafe filename"):
        write_evaluation_report(report, tmp_path)


def test_reserved_split_cannot_be_exported(tmp_path):
    report = _make_report().model_copy(update={"split": DatasetSplit.IID_TEST})

    with pytest.raises(ValueError, match="Only development"):
        write_evaluation_report(report, tmp_path)


def test_modified_report_fails_verification(tmp_path):
    artifact = write_evaluation_report(_make_report(), tmp_path)

    with artifact.path.open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_evaluation_report(
            artifact.path,
            artifact.sha256,
        )


def test_wrong_expected_digest_is_rejected(tmp_path):
    artifact = write_evaluation_report(_make_report(), tmp_path)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_evaluation_report(
            artifact.path,
            "0" * 64,
        )


def test_noncanonical_json_is_rejected(tmp_path):
    artifact = write_evaluation_report(_make_report(), tmp_path)

    # Extra whitespace is valid JSON but violates our canonical format.
    content = artifact.path.read_bytes() + b"\n"
    artifact.path.write_bytes(content)

    updated_digest = hashlib.sha256(content).hexdigest()

    with pytest.raises(ValueError, match="canonical JSON"):
        verify_evaluation_report(
            artifact.path,
            updated_digest,
        )
