import ast
import math
from pathlib import Path

from governed_ap.experiment_execution import ExperimentRun
from governed_ap.schemas import BenchmarkExample, DatasetSplit

SYSTEM_FILES = (
    "deterministic_baseline.py",
    "naive_llm_baseline.py",
    "governed_agent.py",
    "langgraph_agent.py",
    "deterministic_checks_layer.py",
    "history_risk_layer.py",
    "policy_engine_layer.py",
    "guardrail_layer.py",
    "decision_agent.py",
    "enforcement_gate.py",
    "identity_resolver.py",
    "llm_inputs.py",
)

HIDDEN_NAMES = frozenset(
    {
        "GroundTruth",
        "ground_truth",
        "is_malicious",
        "expected_action",
        "attack_family",
        "attack_subtype",
        "template_id",
        "scenario_id",
        "sequence_id",
        "sequence_position",
    }
)


def validate_experiment_integrity(
    scenarios: list[list[BenchmarkExample]],
    run: ExperimentRun,
) -> None:
    """Verify that execution attempts match the scored decisions."""
    if not scenarios or len(scenarios) != len(run.evaluated):
        raise ValueError("Benchmark and evaluation scenario mismatch.")

    expected_pairs = []

    for source_scenario, evaluated_scenario in zip(scenarios, run.evaluated, strict=True):
        if not source_scenario or len(source_scenario) != len(evaluated_scenario):
            raise ValueError("Incomplete experiment scenario.")

        for example, record in zip(source_scenario, evaluated_scenario, strict=True):
            if example.ground_truth.split != DatasetSplit.DEVELOPMENT:
                raise ValueError("Reserved benchmark split is not allowed.")

            if example != record.example:
                raise ValueError("Evaluated benchmark example mismatch.")

            if record.decision.system_name != run.system_name:
                raise ValueError("System identity mismatch.")

            expected_pairs.append((example, record))

    if len(run.attempts) != len(expected_pairs):
        raise ValueError("Cannot report an incomplete experiment: attempt count mismatch.")

    for (example, record), attempt in zip(expected_pairs, run.attempts, strict=True):
        if attempt.status != "COMPLETED" or attempt.action is None:
            raise ValueError("Cannot report an incomplete experiment.")

        if attempt.case_id != example.case.case_id:
            raise ValueError("Execution case ID mismatch.")

        if attempt.action != record.decision.action:
            raise ValueError("Execution action mismatch.")

        if attempt.error_type is not None:
            raise ValueError("Completed execution contains an error type.")

        if not math.isfinite(attempt.latency_ms) or attempt.latency_ms < 0:
            raise ValueError("Invalid execution latency.")


def find_system_label_access(
    package_directory: str | Path,
    *,
    filenames: tuple[str, ...] = SYSTEM_FILES,
) -> list[str]:
    """Static guard against direct hidden-label access in system modules."""
    folder = Path(package_directory)
    findings = []

    for filename in filenames:
        path = folder / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "governed_ap.oracle":
                        findings.append(f"{filename}:{node.lineno}: oracle import")

            elif isinstance(node, ast.ImportFrom):
                if node.module in {"governed_ap.oracle", "oracle"}:
                    findings.append(f"{filename}:{node.lineno}: oracle import")

                if node.level and node.module is None:
                    if any(alias.name == "oracle" for alias in node.names):
                        findings.append(f"{filename}:{node.lineno}: oracle import")

            elif isinstance(node, (ast.Name, ast.Attribute)):
                name = node.id if isinstance(node, ast.Name) else node.attr

                if name in HIDDEN_NAMES:
                    findings.append(f"{filename}:{node.lineno}: hidden label {name}")

            elif isinstance(node, ast.Subscript):
                key = node.slice
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and key.value in HIDDEN_NAMES
                ):
                    findings.append(f"{filename}:{node.lineno}: hidden label lookup")

    return findings


def assert_system_label_independence(
    package_directory: str | Path,
) -> None:
    findings = find_system_label_access(package_directory)

    if findings:
        raise ValueError("Experimental system label-access violations:\n" + "\n".join(findings))
