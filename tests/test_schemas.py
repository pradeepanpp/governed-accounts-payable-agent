from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from governed_ap.schemas import (
    BenchmarkCase,
    BenchmarkExample,
    DatasetSplit,
    ExpectedAction,
    GoodsReceipt,
    GoodsReceiptStatus,
    GroundTruth,
    Invoice,
    PaymentRecord,
    PaymentStatus,
    PurchaseOrder,
    PurchaseOrderStatus,
    Vendor,
)


def test_valid_vendor():
    vendor = Vendor(
        vendor_id="V001",
        legal_name="Alpha Medical Supplies",
        aliases=["Alpha Medical", "AMS"],
        approved_bank_account="BANK-V001-PRIMARY",
    )

    assert vendor.vendor_id == "V001"
    assert vendor.legal_name == "Alpha Medical Supplies"
    assert vendor.aliases == ["Alpha Medical", "AMS"]
    assert vendor.approved_bank_account == "BANK-V001-PRIMARY"
    assert vendor.is_active is True


def test_vendor_rejects_empty_id():
    with pytest.raises(ValidationError):
        Vendor(
            vendor_id="",
            legal_name="Alpha Medical Supplies",
            approved_bank_account="BANK-V001-PRIMARY",
        )


def test_vendor_strips_whitespace():
    vendor = Vendor(
        vendor_id="  V001  ",
        legal_name="  Alpha Medical Supplies  ",
        approved_bank_account="  BANK-V001-PRIMARY  ",
    )

    assert vendor.vendor_id == "V001"
    assert vendor.legal_name == "Alpha Medical Supplies"
    assert vendor.approved_bank_account == "BANK-V001-PRIMARY"


def test_vendor_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Vendor(
            vendor_id="V001",
            legal_name="Alpha Medical Supplies",
            approved_bank_account="BANK-V001-PRIMARY",
            unknown_field="unexpected",
        )


def test_valid_purchase_order():
    purchase_order = PurchaseOrder(
        po_id="PO-1001",
        vendor_id="V001",
        description="MRI maintenance service",
        quantity_ordered="1",
        unit_price="5000.00",
        total_amount="5000.00",
        currency="USD",
    )

    assert purchase_order.po_id == "PO-1001"
    assert purchase_order.vendor_id == "V001"
    assert purchase_order.quantity_ordered == Decimal("1")
    assert purchase_order.unit_price == Decimal("5000.00")
    assert purchase_order.total_amount == Decimal("5000.00")
    assert purchase_order.currency == "USD"
    assert purchase_order.status == PurchaseOrderStatus.OPEN


def test_purchase_order_rejects_zero_quantity():
    with pytest.raises(ValidationError):
        PurchaseOrder(
            po_id="PO-1001",
            vendor_id="V001",
            description="MRI maintenance service",
            quantity_ordered="0",
            unit_price="5000.00",
            total_amount="5000.00",
            currency="USD",
        )


def test_purchase_order_rejects_invalid_status():
    with pytest.raises(ValidationError):
        PurchaseOrder(
            po_id="PO-1001",
            vendor_id="V001",
            description="MRI maintenance service",
            quantity_ordered="1",
            unit_price="5000.00",
            total_amount="5000.00",
            currency="USD",
            status="PAID",
        )


def test_valid_goods_receipt():
    goods_receipt = GoodsReceipt(
        receipt_id="GR-5001",
        po_id="PO-1001",
        quantity_received="1",
        received_date="2026-10-01",
    )

    assert goods_receipt.receipt_id == "GR-5001"
    assert goods_receipt.po_id == "PO-1001"
    assert goods_receipt.quantity_received == Decimal("1")
    assert goods_receipt.received_date == date(2026, 10, 1)
    assert goods_receipt.status == GoodsReceiptStatus.RECEIVED


def test_goods_receipt_rejects_zero_quantity():
    with pytest.raises(ValidationError):
        GoodsReceipt(
            receipt_id="GR-5001",
            po_id="PO-1001",
            quantity_received="0",
            received_date="2026-10-01",
        )


def test_goods_receipt_rejects_invalid_status():
    with pytest.raises(ValidationError):
        GoodsReceipt(
            receipt_id="GR-5001",
            po_id="PO-1001",
            quantity_received="1",
            received_date="2026-10-01",
            status="DELIVERED",
        )


def test_valid_invoice():
    invoice = Invoice(
        invoice_id="INV-9001",
        vendor_name="Alpha Medical Supplies",
        vendor_id_claim="V001",
        po_id="PO-1001",
        invoice_date="2026-10-02",
        description="MRI maintenance service",
        quantity="1",
        unit_price="5000.00",
        subtotal="5000.00",
        tax_amount="0.00",
        total_amount="5000.00",
        currency="USD",
        invoice_bank_account="BANK-V001-PRIMARY",
        payment_terms="NET30",
        raw_text="Invoice for MRI maintenance service.",
    )

    assert invoice.invoice_id == "INV-9001"
    assert invoice.invoice_date == date(2026, 10, 2)
    assert invoice.total_amount == Decimal("5000.00")
    assert invoice.invoice_bank_account == "BANK-V001-PRIMARY"


def test_invoice_rejects_negative_tax():
    with pytest.raises(ValidationError):
        Invoice(
            invoice_id="INV-9001",
            vendor_name="Alpha Medical Supplies",
            vendor_id_claim="V001",
            po_id="PO-1001",
            invoice_date="2026-10-02",
            description="MRI maintenance service",
            quantity="1",
            unit_price="5000.00",
            subtotal="5000.00",
            tax_amount="-10.00",
            total_amount="4990.00",
            currency="USD",
            invoice_bank_account="BANK-V001-PRIMARY",
            payment_terms="NET30",
            raw_text="Invoice for MRI maintenance service.",
        )


def test_invoice_rejects_invalid_currency_length():
    with pytest.raises(ValidationError):
        Invoice(
            invoice_id="INV-9001",
            vendor_name="Alpha Medical Supplies",
            vendor_id_claim="V001",
            po_id="PO-1001",
            invoice_date="2026-10-02",
            description="MRI maintenance service",
            quantity="1",
            unit_price="5000.00",
            subtotal="5000.00",
            tax_amount="0.00",
            total_amount="5000.00",
            currency="US",
            invoice_bank_account="BANK-V001-PRIMARY",
            payment_terms="NET30",
            raw_text="Invoice for MRI maintenance service.",
        )


def test_valid_payment_record():
    payment = PaymentRecord(
        payment_id="PAY-1001",
        invoice_id="INV-8001",
        vendor_id="V001",
        po_id="PO-1001",
        amount="2500.00",
        currency="USD",
        payment_date="2026-09-28",
        status="PAID",
    )

    assert payment.payment_id == "PAY-1001"
    assert payment.amount == Decimal("2500.00")
    assert payment.payment_date == date(2026, 9, 28)
    assert payment.status == PaymentStatus.PAID


def test_payment_record_rejects_zero_amount():
    with pytest.raises(ValidationError):
        PaymentRecord(
            payment_id="PAY-1001",
            invoice_id="INV-8001",
            vendor_id="V001",
            po_id="PO-1001",
            amount="0",
            currency="USD",
            payment_date="2026-09-28",
            status="PAID",
        )


def test_payment_record_rejects_invalid_status():
    with pytest.raises(ValidationError):
        PaymentRecord(
            payment_id="PAY-1001",
            invoice_id="INV-8001",
            vendor_id="V001",
            po_id="PO-1001",
            amount="2500.00",
            currency="USD",
            payment_date="2026-09-28",
            status="SENT",
        )


def test_valid_benchmark_example():
    vendor = Vendor(
        vendor_id="V001",
        legal_name="Alpha Medical Supplies",
        approved_bank_account="BANK-V001-PRIMARY",
    )

    purchase_order = PurchaseOrder(
        po_id="PO-1001",
        vendor_id="V001",
        description="MRI maintenance service",
        quantity_ordered="1",
        unit_price="5000.00",
        total_amount="5000.00",
        currency="USD",
    )

    goods_receipt = GoodsReceipt(
        receipt_id="GR-5001",
        po_id="PO-1001",
        quantity_received="1",
        received_date="2026-10-01",
    )

    invoice = Invoice(
        invoice_id="INV-9001",
        vendor_name="Alpha Medical Supplies",
        vendor_id_claim="V001",
        po_id="PO-1001",
        invoice_date="2026-10-02",
        description="MRI maintenance service",
        quantity="1",
        unit_price="5000.00",
        subtotal="5000.00",
        tax_amount="0.00",
        total_amount="5000.00",
        currency="USD",
        invoice_bank_account="BANK-V001-PRIMARY",
        payment_terms="NET30",
        raw_text="Invoice for MRI maintenance service.",
    )

    case = BenchmarkCase(
        case_id="CASE-0001",
        vendor=vendor,
        purchase_order=purchase_order,
        goods_receipts=[goods_receipt],
        invoice=invoice,
    )

    ground_truth = GroundTruth(
        is_malicious=False,
        expected_action="AUTO_APPROVE",
        expected_reason_codes=[],
        split="development",
    )

    example = BenchmarkExample(
        case=case,
        ground_truth=ground_truth,
    )

    assert example.case.case_id == "CASE-0001"
    assert example.case.vendor.vendor_id == "V001"
    assert example.case.purchase_order.po_id == "PO-1001"
    assert len(example.case.goods_receipts) == 1
    assert example.ground_truth.expected_action == ExpectedAction.AUTO_APPROVE
    assert example.ground_truth.split == DatasetSplit.DEVELOPMENT


def test_benchmark_case_allows_missing_purchase_order():
    invoice = Invoice(
        invoice_id="INV-9002",
        vendor_name="Unknown Supplier",
        vendor_id_claim="V999",
        po_id="PO-NOT-FOUND",
        invoice_date="2026-10-02",
        description="Unapproved consulting service",
        quantity="1",
        unit_price="1000.00",
        subtotal="1000.00",
        tax_amount="0.00",
        total_amount="1000.00",
        currency="USD",
        invoice_bank_account="BANK-UNKNOWN",
        payment_terms="NET30",
        raw_text="Invoice for consulting service.",
    )

    case = BenchmarkCase(
        case_id="CASE-0002",
        invoice=invoice,
    )

    assert case.vendor is None
    assert case.purchase_order is None
    assert case.goods_receipts == []
    assert case.payment_history == []


def test_ground_truth_rejects_invalid_action():
    with pytest.raises(ValidationError):
        GroundTruth(
            is_malicious=True,
            expected_action="PAY_NOW",
            expected_reason_codes=["NO_MATCHING_PO"],
            split="development",
        )


def test_ground_truth_rejects_zero_sequence_position():
    with pytest.raises(ValidationError):
        GroundTruth(
            is_malicious=True,
            expected_action="ESCALATE",
            expected_reason_codes=[],
            split="development",
            sequence_id="SEQ-001",
            sequence_position=0,
        )


def test_benchmark_case_does_not_contain_ground_truth():
    invoice = Invoice(
        invoice_id="INV-9003",
        vendor_name="Alpha Medical Supplies",
        vendor_id_claim="V001",
        po_id="PO-1001",
        invoice_date="2026-10-02",
        description="MRI maintenance service",
        quantity="1",
        unit_price="5000.00",
        subtotal="5000.00",
        tax_amount="0.00",
        total_amount="5000.00",
        currency="USD",
        invoice_bank_account="BANK-V001-PRIMARY",
        payment_terms="NET30",
        raw_text="Invoice for MRI maintenance service.",
    )

    case = BenchmarkCase(
        case_id="CASE-0003",
        invoice=invoice,
    )

    case_data = case.model_dump()

    assert "ground_truth" not in case_data
    assert "is_malicious" not in case_data
    assert "expected_action" not in case_data


def test_ground_truth_requires_complete_sequence_metadata():
    with pytest.raises(ValidationError):
        GroundTruth(
            is_malicious=True,
            expected_action="ESCALATE",
            expected_reason_codes=[],
            split="development",
            sequence_id="SEQ-001",
        )
