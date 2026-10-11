from pathlib import Path

import governed_ap.pdf_intake as intake
from governed_ap.benchmark_generator import generate_legitimate_example
from governed_ap.schemas import ExpectedAction


def sample_text(case):
    invoice = case.invoice

    return "\n".join(
        [
            f"Invoice: {invoice.invoice_id}",
            f"Date: {invoice.invoice_date}",
            f"Currency: {invoice.currency}",
            "Subtotal",
            f"{invoice.currency} {invoice.subtotal}",
            "VAT 5%",
            f"{invoice.currency} {invoice.tax_amount}",
            "Total",
            f"{invoice.currency} {invoice.total_amount}",
        ]
    )


def test_matching_document_still_requires_verification(monkeypatch):
    case = generate_legitimate_example(seed=1100, case_type="C1").case

    monkeypatch.setattr(
        intake,
        "read_invoice_pdf",
        lambda *args, **kwargs: (sample_text(case), "NATIVE"),
    )

    result = intake.assess_pdf(Path("sample.pdf"), case)

    assert result.action == ExpectedAction.ESCALATE
    assert result.extracted.invoice_number == case.invoice.invoice_id
    assert "REQUIRED_AP_FIELDS_UNVERIFIED" in result.reason_codes
    assert not any(reason.endswith("_MISMATCH") for reason in result.reason_codes)


def test_document_amount_mismatch_is_detected(monkeypatch):
    case = generate_legitimate_example(seed=1100, case_type="C1").case

    text = sample_text(case).replace(
        f"{case.invoice.currency} {case.invoice.total_amount}",
        f"{case.invoice.currency} 1.00",
    )

    monkeypatch.setattr(
        intake,
        "read_invoice_pdf",
        lambda *args, **kwargs: (text, "NATIVE"),
    )

    result = intake.assess_pdf(Path("sample.pdf"), case)

    assert "DOCUMENT_TOTAL_MISMATCH" in result.reason_codes
    assert result.action == ExpectedAction.ESCALATE


def test_missing_erp_context_escalates(monkeypatch):
    case = generate_legitimate_example(seed=1100, case_type="C1").case

    monkeypatch.setattr(
        intake,
        "read_invoice_pdf",
        lambda *args, **kwargs: (sample_text(case), "OCR"),
    )

    result = intake.assess_pdf(Path("sample.pdf"))

    assert result.source == "OCR"
    assert "TRUSTED_ERP_CONTEXT_MISSING" in result.reason_codes


def test_pdf_read_failure_escalates(monkeypatch):
    def broken_reader(*args, **kwargs):
        raise ValueError("Corrupt PDF")

    monkeypatch.setattr(
        intake,
        "read_invoice_pdf",
        broken_reader,
    )

    result = intake.assess_pdf(Path("broken.pdf"))

    assert result.action == ExpectedAction.ESCALATE
    assert result.reason_codes == ("DOCUMENT_INTAKE_FAILURE",)
