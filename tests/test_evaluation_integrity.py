from dataclasses import replace
from pathlib import Path

import pytest

from governed_ap.benchmark_generator import generate_legitimate_example
from governed_ap.evaluation_integrity import (
    assert_system_label_independence,
    find_system_label_access,
    validate_experiment_integrity,
)
from governed_ap.evaluation_reporting import build_report_from_experiment
from governed_ap.experiment_execution import run_experiment
from governed_ap.git_provenance import GitProvenance
from governed_ap.schemas import ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


@pytest.fixture
def completed_run(monkeypatch):
    monkeypatch.setattr(
        "governed_ap.experiment_execution.read_git_provenance",
        lambda repository: GitProvenance(
            revision="d" * 40,
            dirty=False,
        ),
    )

    scenarios = [[generate_legitimate_example(9901, "C1")]]

    def system(case):
        return SystemDecision(
            system_name=SystemName.DETERMINISTIC_BASELINE,
            action=ExpectedAction.AUTO_APPROVE,
        )

    run = run_experiment(
        scenarios,
        system,
        run_id="dev-integrity-test",
        system_name=SystemName.DETERMINISTIC_BASELINE,
    )

    return scenarios, run


def test_valid_execution_passes(completed_run):
    scenarios, run = completed_run

    validate_experiment_integrity(scenarios, run)

    report = build_report_from_experiment(
        scenarios,
        run,
        benchmark_seed=9901,
        bootstrap_repetitions=20,
    )

    assert report.execution_summary.completed_invoices == 1


def test_wrong_case_id_is_rejected(completed_run):
    scenarios, run = completed_run

    changed_attempt = replace(run.attempts[0], case_id="WRONG-CASE")
    changed_run = replace(run, attempts=(changed_attempt,))

    with pytest.raises(ValueError, match="case ID mismatch"):
        build_report_from_experiment(
            scenarios,
            changed_run,
            benchmark_seed=9901,
            bootstrap_repetitions=20,
        )


def test_wrong_action_is_rejected(completed_run):
    scenarios, run = completed_run

    changed_attempt = replace(
        run.attempts[0],
        action=ExpectedAction.ESCALATE,
    )

    with pytest.raises(ValueError, match="action mismatch"):
        validate_experiment_integrity(
            scenarios,
            replace(run, attempts=(changed_attempt,)),
        )


def test_invalid_latency_is_rejected(completed_run):
    scenarios, run = completed_run

    changed_attempt = replace(
        run.attempts[0],
        latency_ms=float("nan"),
    )

    with pytest.raises(ValueError, match="Invalid execution latency"):
        validate_experiment_integrity(
            scenarios,
            replace(run, attempts=(changed_attempt,)),
        )


def test_incomplete_run_is_rejected(completed_run):
    scenarios, run = completed_run

    with pytest.raises(ValueError, match="incomplete experiment"):
        validate_experiment_integrity(
            scenarios,
            replace(run, attempts=()),
        )


def test_existing_system_modules_have_no_direct_label_access():
    package = Path(__file__).resolve().parents[1] / "governed_ap"

    assert_system_label_independence(package)


def test_oracle_import_is_detected(tmp_path):
    (tmp_path / "agent.py").write_text(
        "from governed_ap.oracle import evaluate_case\n",
        encoding="utf-8",
    )

    findings = find_system_label_access(
        tmp_path,
        filenames=("agent.py",),
    )

    assert any("oracle import" in finding for finding in findings)


def test_hidden_label_access_is_detected(tmp_path):
    (tmp_path / "agent.py").write_text(
        "def decide(case):\n    return case.ground_truth.expected_action\n",
        encoding="utf-8",
    )

    findings = find_system_label_access(
        tmp_path,
        filenames=("agent.py",),
    )

    assert any("hidden label" in finding for finding in findings)
