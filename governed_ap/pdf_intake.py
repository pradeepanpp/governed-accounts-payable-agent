"""Fail-closed PDF intake before accounts-payable governance."""

import argparse
from dataclasses import dataclass
from pathlib import Path

from governed_ap.native_invoice_reader import (
    PartialInvoice,
    parse_native_text,
    read_invoice_pdf,
)
from governed_ap.schemas import BenchmarkCase, ExpectedAction


@dataclass(frozen=True)
class PDFIntakeResult:
    action: ExpectedAction
    source: str
    extracted: PartialInvoice
    reason_codes: tuple[str, ...]


def assess_pdf(
    path: Path,
    trusted_case: BenchmarkCase | None = None,
    *,
    languages: str = "eng+ara",
) -> PDFIntakeResult:
    """Compare observed PDF fields with separately supplied ERP context."""

    try:
        text, source = read_invoice_pdf(path, languages=languages)
        extracted = parse_native_text(text)
    except Exception:
        # At the document-ingestion boundary, errors require review.
        return PDFIntakeResult(
            action=ExpectedAction.ESCALATE,
            source="ERROR",
            extracted=PartialInvoice(),
            reason_codes=("DOCUMENT_INTAKE_FAILURE",),
        )

    reasons: list[str] = []

    if not text.strip():
        reasons.append("DOCUMENT_UNREADABLE")

    observed_fields = (
        "invoice_number",
        "invoice_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    )

    for field in observed_fields:
        if getattr(extracted, field) is None:
            reasons.append(f"MISSING_{field.upper()}")

    if trusted_case is None:
        reasons.append("TRUSTED_ERP_CONTEXT_MISSING")
    else:
        invoice = trusted_case.invoice

        expected_fields = {
            "invoice_number": invoice.invoice_id,
            "invoice_date": invoice.invoice_date,
            "currency": invoice.currency,
            "subtotal": invoice.subtotal,
            "tax": invoice.tax_amount,
            "total": invoice.total_amount,
        }

        for field, expected in expected_fields.items():
            actual = getattr(extracted, field)

            if actual is not None and actual != expected:
                reasons.append(f"DOCUMENT_{field.upper()}_MISMATCH")

    # Our current PDF reader does not independently extract the
    # claimed bank account, PO and line-item details.
    # Never authorize payment by filling those gaps from the PO.
    reasons.append("REQUIRED_AP_FIELDS_UNVERIFIED")

    return PDFIntakeResult(
        action=ExpectedAction.ESCALATE,
        source=source,
        extracted=extracted,
        reason_codes=tuple(reasons),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline PDF accounts-payable intake screening.")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()

    result = assess_pdf(args.pdf)

    print(f"Extraction method: {result.source}")
    print(f"Invoice number: {result.extracted.invoice_number}")
    print(f"Currency: {result.extracted.currency}")
    print(f"Total: {result.extracted.total}")
    print(f"Intake action: {result.action.value}")
    print("Reasons:", ", ".join(result.reason_codes))
    print("Governance agent invoked: NO")
    print("Payment executed: NO")


if __name__ == "__main__":
    main()
