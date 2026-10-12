"""Offline PDF intake plus a fictional, human-reviewed AP simulation."""

import argparse
from datetime import date
from decimal import Decimal
from pathlib import Path

from demo import create_agent, show_result
from governed_ap.native_invoice_reader import read_invoice_pdf
from governed_ap.pdf_intake import assess_pdf
from governed_ap.schemas import (
    BenchmarkCase,
    GoodsReceipt,
    Invoice,
    PolicyConfig,
    PurchaseOrder,
    Vendor,
)


def fictional_reviewed_case(document_text: str) -> BenchmarkCase:
    """Manually specified fictional records, NOT extracted ERP facts."""
    vendor_id = "V-FGF-DEMO"
    po_id = "PO-FGF-DEMO"
    supplier = "Fictional Gulf Foods LLC"
    bank = "BANK-FGF-FICTIONAL"

    invoice = Invoice(
        invoice_id="INV-2026-001",
        vendor_name=supplier,
        vendor_id_claim=vendor_id,
        po_id=po_id,
        invoice_date=date(2026, 8, 1),
        description="Sparkling Water 330ml",
        quantity=Decimal("24"),
        unit_price=Decimal("2.50"),
        subtotal=Decimal("60.00"),
        tax_amount=Decimal("3.00"),
        total_amount=Decimal("63.00"),
        currency="AED",
        invoice_bank_account=bank,
        payment_terms="NET30",
        raw_text=document_text,
        requested_payee=supplier,
        stated_totals=[Decimal("63.00")],
        line_items=["Sparkling Water 330ml"],
    )

    return BenchmarkCase(
        case_id="PDF-FICTIONAL-01",
        vendor=Vendor(
            vendor_id=vendor_id,
            legal_name=supplier,
            approved_bank_account=bank,
            created_date=date(2026, 1, 1),
        ),
        purchase_order=PurchaseOrder(
            po_id=po_id,
            vendor_id=vendor_id,
            description="Sparkling Water 330ml",
            quantity_ordered=Decimal("24"),
            unit_price=Decimal("2.50"),
            total_amount=Decimal("63.00"),
            currency="AED",
            line_items=["Sparkling Water 330ml"],
        ),
        goods_receipts=[
            GoodsReceipt(
                receipt_id="GR-FGF-DEMO",
                po_id=po_id,
                quantity_received=Decimal("24"),
                received_date=date(2026, 7, 31),
            )
        ],
        invoice=invoice,
        payment_history=[],
        policy=PolicyConfig(
            invoice_limit=Decimal("10000"),
            vendor_window_limit=Decimal("10000"),
            po_cumulative_limit=Decimal("10000"),
            tax_rate=Decimal("0.05"),
        ),
    )


def document_fields_match(extracted, case: BenchmarkCase) -> bool:
    """Require all six observed fields to match reviewed values."""
    invoice = case.invoice

    comparisons = (
        (extracted.invoice_number, invoice.invoice_id),
        (extracted.invoice_date, invoice.invoice_date),
        (extracted.currency, invoice.currency),
        (extracted.subtotal, invoice.subtotal),
        (extracted.tax, invoice.tax_amount),
        (extracted.total, invoice.total_amount),
    )

    return all(observed is not None and observed == reviewed for observed, reviewed in comparisons)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument(
        "--simulate-review",
        action="store_true",
        help="Run a fictional, manually completed ERP scenario.",
    )
    args = parser.parse_args()

    intake = assess_pdf(args.pdf)

    print("PDF source:", intake.source)
    print("Observed invoice:", intake.extracted.invoice_number)
    print("Observed total:", intake.extracted.total)
    print("Intake decision:", intake.action.value)
    print("Intake reasons:", ", ".join(intake.reason_codes))
    print("Payment executed: NO")

    if not args.simulate_review:
        return

    if intake.source != "NATIVE":
        print("Simulation refused: native text is required.")
        return

    text, _ = read_invoice_pdf(args.pdf)
    case = fictional_reviewed_case(text)

    # Compare the independently transcribed values with PDF observations.
    if not document_fields_match(intake.extracted, case):
        print("Simulation refused: reviewed values do not match PDF.")
        return

    comparison = assess_pdf(args.pdf, case)

    if comparison.reason_codes != ("REQUIRED_AP_FIELDS_UNVERIFIED",):
        print("Simulation refused: unresolved document discrepancy.")
        print("Reasons:", ", ".join(comparison.reason_codes))
        return

    print("\n=== CONTROLLED FICTIONAL ERP SIMULATION ===")
    print("The PDF does not verify the bank account or PO.")
    print("Missing AP information is fictional scenario input.")
    print("This is NOT production payment authorization.")

    agent = create_agent("mock", None)
    show_result("simulated human-reviewed invoice", case, agent)


if __name__ == "__main__":
    main()
