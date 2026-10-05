from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Vendor(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    vendor_id: str = Field(min_length=1)
    legal_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    approved_bank_account: str = Field(min_length=1)
    is_active: bool = True


class PurchaseOrderStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class PurchaseOrder(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    po_id: str = Field(min_length=1)
    vendor_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    quantity_ordered: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    total_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    status: PurchaseOrderStatus = PurchaseOrderStatus.OPEN


class GoodsReceiptStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class GoodsReceipt(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    receipt_id: str = Field(min_length=1)
    po_id: str = Field(min_length=1)
    quantity_received: Decimal = Field(gt=0)
    received_date: date
    status: GoodsReceiptStatus = GoodsReceiptStatus.RECEIVED


class Invoice(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    invoice_id: str = Field(min_length=1)
    vendor_name: str = Field(min_length=1)
    vendor_id_claim: str = Field(min_length=1)
    po_id: str = Field(min_length=1)
    invoice_date: date
    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    subtotal: Decimal = Field(ge=0)
    tax_amount: Decimal = Field(ge=0)
    total_amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    invoice_bank_account: str = Field(min_length=1)
    payment_terms: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)


class PaymentStatus(str, Enum):
    APPROVED = "APPROVED"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PaymentRecord(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    payment_id: str = Field(min_length=1)
    invoice_id: str = Field(min_length=1)
    vendor_id: str = Field(min_length=1)
    po_id: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    payment_date: date
    status: PaymentStatus


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    case_id: str = Field(min_length=1)
    vendor: Vendor | None = None
    purchase_order: PurchaseOrder | None = None
    goods_receipts: list[GoodsReceipt] = Field(default_factory=list)
    invoice: Invoice
    payment_history: list[PaymentRecord] = Field(default_factory=list)


class ExpectedAction(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    ESCALATE = "ESCALATE"
    BLOCK = "BLOCK"


class DatasetSplit(str, Enum):
    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    IID_TEST = "iid_test"
    OOD_TEST = "ood_test"


class GroundTruth(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    attack_family: str | None = None
    attack_subtype: str | None = None
    is_malicious: bool
    expected_action: ExpectedAction
    expected_reason_codes: list[str] = Field(default_factory=list)
    split: DatasetSplit
    sequence_id: str | None = None
    sequence_position: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_sequence_fields(self):
        has_sequence_id = self.sequence_id is not None
        has_sequence_position = self.sequence_position is not None

        if has_sequence_id != has_sequence_position:
            raise ValueError(
                "sequence_id and sequence_position must either both be provided or both be omitted"
            )

        return self


class BenchmarkExample(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    case: BenchmarkCase
    ground_truth: GroundTruth
