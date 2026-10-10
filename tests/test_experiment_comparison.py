from dataclasses import replace

import pytest

from governed_ap.benchmark_generator import (
    generate_development_attack_example,
    generate_legitimate_example,
)
from governed_ap.experiment_comparison import (
    build_comparison_report,
    verify_comparison_report,
    write_comparison_report,
)
from governed_ap.experiment_execution import run_experiment
from governed_ap.git_provenance import GitProvenance
from governed_ap.schemas import ExpectedAction
from governed_ap.system_decision import SystemDecision, SystemName


@pytest.fixture(autouse=True)
def fixed_git(monkeypatch):
    monkeypatch.setattr(
        "governed_ap.experiment_execution.read_git_provenance",
        lambda repository: GitProvenance(
            revision="c" * 40,
            dirty=False,
        ),
    )


def _scenarios():
    return [
        [generate_development_attack_example(9601, "T1.1")],
        [generate_legitimate_example(9602, "C1")],
    ]


def _system(name, action):
    def decide(case):
        return SystemDecision(
            system_name=name,
            action=action,
        )

    return decide


def _runs(scenarios):
    left = run_experiment(
        scenarios,
        _system(
            SystemName.NAIVE_LLM,
            ExpectedAction.AUTO_APPROVE,
        ),
        run_id="dev-naive-compare",
        system_name=SystemName.NAIVE_LLM,
    )

    right = run_experiment(
        scenarios,
        _system(
            SystemName.GOVERNED_AGENT,
            ExpectedAction.ESCALATE,
        ),
        run_id="dev-governed-compare",
        system_name=SystemName.GOVERNED_AGENT,
    )

    return left, right


def _compare(scenarios, left, right):
    return build_comparison_report(
        scenarios,
        left,
        right,
        benchmark_seed=2026,
        bootstrap_repetitions=50,
        bootstrap_seed=42,
    )


def test_comparison_preserves_safety_utility_tradeoff():
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    report = _compare(scenarios, left, right)

    assert report.paired_differences["unsafe_action_rate"].estimate == 1.0

    assert report.paired_differences["benign_automation_coverage"].estimate == 1.0

    assert report.paired_differences["human_review_rate"].estimate == -1.0


def test_unavailable_cost_is_not_zero():
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    report = _compare(scenarios, left, right)

    assert report.llm_cost_difference_usd is None
    assert any("cost comparison unavailable" in warning for warning in report.warnings)


def test_different_revisions_are_rejected():
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    right = replace(
        right,
        provenance=GitProvenance(
            revision="d" * 40,
            dirty=False,
        ),
    )

    with pytest.raises(ValueError, match="Source revisions"):
        _compare(scenarios, left, right)


def test_different_execution_modes_are_rejected():
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    right = replace(
        right,
        execution_mode="live_provider",
        model_id="test/model",
    )

    with pytest.raises(ValueError, match="Execution modes"):
        _compare(scenarios, left, right)


def test_dirty_source_is_disclosed():
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    left = replace(
        left,
        provenance=GitProvenance(
            revision="c" * 40,
            dirty=True,
        ),
    )

    report = _compare(scenarios, left, right)

    assert any("dirty working tree" in warning for warning in report.warnings)


def test_comparison_export_round_trip(tmp_path):
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    report = _compare(scenarios, left, right)
    artifact = write_comparison_report(report, tmp_path)

    restored = verify_comparison_report(
        artifact.path,
        artifact.sha256,
    )

    assert restored == report

    with pytest.raises(FileExistsError):
        write_comparison_report(report, tmp_path)


def test_tampered_comparison_is_rejected(tmp_path):
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    artifact = write_comparison_report(
        _compare(scenarios, left, right),
        tmp_path,
    )

    with artifact.path.open("ab") as handle:
        handle.write(b"tampered")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_comparison_report(
            artifact.path,
            artifact.sha256,
        )


def test_comparison_rejects_different_benchmark():
    scenarios = _scenarios()
    left, right = _runs(scenarios)

    different = [
        [generate_development_attack_example(9701, "T1.1")],
        [generate_legitimate_example(9702, "C1")],
    ]

    with pytest.raises(ValueError, match="does not match benchmark"):
        _compare(different, left, right)
