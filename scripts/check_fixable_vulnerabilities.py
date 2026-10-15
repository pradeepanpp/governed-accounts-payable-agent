"""Block release CI on HIGH/CRITICAL findings with a reported fixed version.

The full Trivy JSON report remains available for residual-risk review.
This deliberately narrow gate is NOT proof that the image is safe.
"""

import json
import sys
from pathlib import Path

BLOCKING_SEVERITIES = {"HIGH", "CRITICAL"}


def evaluate_report(report: dict) -> tuple[list[dict], int]:
    """Return (fixable blocking findings, all HIGH/CRITICAL findings)."""
    results = report.get("Results")
    if not isinstance(results, list) or not results:
        raise ValueError("Trivy report has no Results; refusing to pass a missing/empty scan")

    blocking = []
    total = 0
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("Invalid Trivy result entry")
        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            raise ValueError("Invalid Trivy Vulnerabilities field")
        for finding in vulnerabilities:
            if not isinstance(finding, dict):
                raise ValueError("Invalid Trivy vulnerability entry")
            if finding.get("Severity") not in BLOCKING_SEVERITIES:
                continue
            total += 1
            fixed_version = finding.get("FixedVersion")
            if isinstance(fixed_version, str) and fixed_version.strip():
                blocking.append(finding)
    return blocking, total


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "Usage: python scripts/check_fixable_vulnerabilities.py <trivy-report.json>",
            file=sys.stderr,
        )
        return 2

    try:
        report = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Expected a JSON object")
        blocking, total = evaluate_report(report)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: Cannot verify Trivy report: {exc}", file=sys.stderr)
        return 2

    print(f"Trivy HIGH/CRITICAL findings: {total}")
    print(f"HIGH/CRITICAL findings with a fixed version: {len(blocking)}")
    for finding in blocking:
        print(
            f"BLOCK: {finding.get('VulnerabilityID', 'unknown')} "
            f"{finding.get('PkgName', 'unknown')} "
            f"installed={finding.get('InstalledVersion', 'unknown')} "
            f"fixed={finding['FixedVersion']}"
        )
    if blocking:
        print("FAIL: Remediate fixable vulnerabilities or review policy explicitly.")
        return 1
    print("PASS: No fixable HIGH/CRITICAL findings detected.")
    print("WARNING: Unfixed/undetermined findings remain reportable and require risk review.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
