from dataclasses import dataclass

from governed_ap.schemas import BenchmarkCase


@dataclass(frozen=True)
class VendorIdentityResolution:
    resolved_vendor_id: str | None
    matched_name: str | None
    matched_via_alias: bool
    matches_po_vendor: bool


def normalize_vendor_name(
    value: str,
) -> str:
    return " ".join(value.casefold().split())


def trusted_vendor_names(
    case: BenchmarkCase,
) -> dict[str, bool]:
    vendor = case.vendor

    if vendor is None:
        return {}

    names: dict[str, bool] = {normalize_vendor_name(vendor.legal_name): False}

    for alias in vendor.aliases:
        normalized = normalize_vendor_name(alias)

        names.setdefault(
            normalized,
            True,
        )

    return names


def resolve_vendor_identity(
    case: BenchmarkCase,
) -> VendorIdentityResolution:
    vendor = case.vendor
    purchase_order = case.purchase_order
    invoice = case.invoice

    if vendor is None or purchase_order is None:
        return VendorIdentityResolution(
            resolved_vendor_id=None,
            matched_name=None,
            matched_via_alias=False,
            matches_po_vendor=False,
        )

    trusted_names = trusted_vendor_names(case)

    claimed_name = normalize_vendor_name(invoice.vendor_name)

    if claimed_name not in trusted_names:
        return VendorIdentityResolution(
            resolved_vendor_id=None,
            matched_name=None,
            matched_via_alias=False,
            matches_po_vendor=False,
        )

    if invoice.vendor_id_claim is not None and invoice.vendor_id_claim != vendor.vendor_id:
        return VendorIdentityResolution(
            resolved_vendor_id=None,
            matched_name=invoice.vendor_name,
            matched_via_alias=(trusted_names[claimed_name]),
            matches_po_vendor=False,
        )

    matches_po_vendor = vendor.vendor_id == purchase_order.vendor_id

    if not matches_po_vendor:
        return VendorIdentityResolution(
            resolved_vendor_id=None,
            matched_name=invoice.vendor_name,
            matched_via_alias=(trusted_names[claimed_name]),
            matches_po_vendor=False,
        )

    return VendorIdentityResolution(
        resolved_vendor_id=(vendor.vendor_id),
        matched_name=invoice.vendor_name,
        matched_via_alias=(trusted_names[claimed_name]),
        matches_po_vendor=True,
    )
