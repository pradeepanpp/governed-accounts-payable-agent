"""Offline unit tests for the narrow container vulnerability policy."""

import json

from scripts.check_fixable_vulnerabilities import evaluate_report, main


def report_with(*findings):
    return {"Results": [{"Target": "test-image", "Vulnerabilities": list(findings)}]}


def test_blocks_high_with_known_fix(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text(
        json.dumps(report_with({"Severity": "HIGH", "FixedVersion": "2.0", "PkgName": "demo"})),
        encoding="utf-8",
    )
    assert main(["check", str(path)]) == 1


def test_blocks_critical_with_known_fix():
    blockers, total = evaluate_report(report_with({"Severity": "CRITICAL", "FixedVersion": "1.2"}))
    assert total == 1
    assert len(blockers) == 1


def test_unfixed_high_is_reported_but_not_blocked():
    blockers, total = evaluate_report(report_with({"Severity": "HIGH", "FixedVersion": ""}))
    assert total == 1
    assert blockers == []


def test_low_is_not_blocked_even_with_fix():
    blockers, total = evaluate_report(report_with({"Severity": "LOW", "FixedVersion": "2.0"}))
    assert total == 0
    assert blockers == []


def test_rejects_missing_scan_results(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text('{"Results": []}', encoding="utf-8")
    assert main(["check", str(path)]) == 2


def test_rejects_missing_file(tmp_path):
    assert main(["check", str(tmp_path / "missing.json")]) == 2
