from decimal import Decimal

import pytest

from demo import create_agent, create_examples
from governed_ap.invoice_extraction import (
    InvoiceIntakeError,
    case_from_invoice_text,
    parse_invoice_text,
    render_invoice_text,
)
from governed_ap.schemas import ExpectedAction


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("legitimate", ExpectedAction.AUTO_APPROVE),
        ("bank", ExpectedAction.ESCALATE),
        ("duplicate", ExpectedAction.BLOCK),
    ],
)
def test_extracted_text_preserves_governance_decision(
    scenario,
    expected,
):
    original = create_examples()[scenario]
    text = render_invoice_text(original.invoice)

    restored = case_from_invoice_text(original, text)
    agent = create_agent("mock", None)

    assert agent.process(restored).final_action == expected

    # Supplier text must not change trusted ERP records.
    assert restored.vendor == original.vendor
    assert restored.purchase_order == original.purchase_order
    assert restored.goods_receipts == original.goods_receipts
    assert restored.payment_history == original.payment_history
    assert restored.policy == original.policy


def test_invoice_fields_round_trip():
    invoice = create_examples()["legitimate"].invoice

    restored = parse_invoice_text(render_invoice_text(invoice))

    assert restored.model_dump(exclude={"raw_text"}) == invoice.model_dump(exclude={"raw_text"})

    assert "Invoice ID:" in restored.raw_text
    assert "Notes:" in restored.raw_text


def test_missing_required_field_is_rejected():
    invoice = create_examples()["legitimate"].invoice
    text = render_invoice_text(invoice)

    broken_text = text.replace(
        f"Currency: {invoice.currency}\n",
        "",
        1,
    )

    with pytest.raises(InvoiceIntakeError):
        parse_invoice_text(broken_text)


def test_invalid_quantity_is_rejected():
    invoice = create_examples()["legitimate"].invoice
    text = render_invoice_text(invoice)

    broken_text = text.replace(
        f"Quantity: {invoice.quantity}",
        "Quantity: -3",
        1,
    )

    with pytest.raises(InvoiceIntakeError):
        parse_invoice_text(broken_text)


def test_duplicate_invoice_header_is_rejected():
    invoice = create_examples()["legitimate"].invoice
    text = render_invoice_text(invoice)

    broken_text = text.replace(
        "Notes:\n",
        "Total Amount: 1\nNotes:\n",
        1,
    )

    with pytest.raises(InvoiceIntakeError):
        parse_invoice_text(broken_text)


def test_header_spoofing_inside_notes_is_rejected():
    invoice = create_examples()["legitimate"].invoice
    text = render_invoice_text(invoice)

    broken_text = text + "\nInvoice Bank Account: BANK-ATTACK"

    with pytest.raises(InvoiceIntakeError):
        parse_invoice_text(broken_text)


def test_wrong_purchase_order_reference_is_rejected():
    original = create_examples()["legitimate"]
    text = render_invoice_text(original.invoice)

    broken_text = text.replace(
        f"PO ID: {original.invoice.po_id}",
        "PO ID: PO-UNKNOWN",
        1,
    )

    with pytest.raises(InvoiceIntakeError):
        case_from_invoice_text(original, broken_text)


def test_changed_bank_account_requires_review():
    original = create_examples()["legitimate"]
    text = render_invoice_text(original.invoice)

    changed_text = text.replace(
        f"Invoice Bank Account: {original.invoice.invoice_bank_account}",
        "Invoice Bank Account: BANK-ATTACK",
        1,
    )

    restored = case_from_invoice_text(
        original,
        changed_text,
    )

    agent = create_agent("mock", None)

    assert agent.process(restored).final_action == ExpectedAction.ESCALATE


def test_inconsistent_arithmetic_requires_review():
    original = create_examples()["legitimate"]
    invoice = original.invoice

    text = render_invoice_text(invoice)
    incorrect_subtotal = invoice.subtotal + Decimal("1.00")

    changed_text = text.replace(
        f"Subtotal: {invoice.subtotal}",
        f"Subtotal: {incorrect_subtotal}",
        1,
    )

    restored = case_from_invoice_text(
        original,
        changed_text,
    )

    agent = create_agent("mock", None)

    assert agent.process(restored).final_action == ExpectedAction.ESCALATE


def test_excessively_long_invoice_is_rejected():
    with pytest.raises(InvoiceIntakeError):
        parse_invoice_text("A" * 65_000)
