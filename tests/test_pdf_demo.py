from decimal import Decimal

from demo import create_agent
from governed_ap.native_invoice_reader import PartialInvoice
from governed_ap.schemas import ExpectedAction

from pdf_demo import document_fields_match, fictional_reviewed_case


def matching_fields():
    return PartialInvoice(
        invoice_number="INV-2026-001",
        invoice_date="2026-08-01",
        currency="AED",
        subtotal="60.00",
        tax="3.00",
        total="63.00",
    )


def test_six_pdf_fields_match_fictional_review():
    case = fictional_reviewed_case("Fictional invoice text")
    assert document_fields_match(matching_fields(), case)


def test_tampered_total_fails_review():
    case = fictional_reviewed_case("Fictional invoice text")
    extracted = matching_fields().model_copy(update={"total": Decimal("630.00")})

    assert not document_fields_match(extracted, case)


def test_missing_tax_fails_review():
    case = fictional_reviewed_case("Fictional invoice text")
    extracted = matching_fields().model_copy(update={"tax": None})

    assert not document_fields_match(extracted, case)


def test_fictional_case_can_run_through_existing_agent():
    case = fictional_reviewed_case("Fictional invoice text")
    agent = create_agent("mock", None)

    assert agent.process(case).final_action == ExpectedAction.AUTO_APPROVE
