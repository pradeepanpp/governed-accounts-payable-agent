from governed_ap.benchmark_generator import (
    generate_development_sequence_attack,
    generate_legitimate_example,
)
from governed_ap.identity_resolver import (
    resolve_vendor_identity,
)


def test_legal_vendor_name_resolves():
    example = generate_legitimate_example(
        seed=400,
        case_type="C1",
    )

    resolution = resolve_vendor_identity(example.case)

    assert resolution.resolved_vendor_id == example.case.vendor.vendor_id

    assert resolution.matches_po_vendor is True

    assert resolution.matched_via_alias is False


def test_registered_alias_resolves():
    example = generate_legitimate_example(
        seed=401,
        case_type="C1",
    )

    vendor = example.case.vendor

    assert vendor is not None

    example.case.invoice.vendor_name = vendor.aliases[0]

    resolution = resolve_vendor_identity(example.case)

    assert resolution.resolved_vendor_id == vendor.vendor_id

    assert resolution.matched_via_alias is True


def test_t43_aliases_resolve_to_same_vendor():
    sequence = generate_development_sequence_attack(
        seed=402,
        attack_subtype="T4.3",
    )

    resolved_ids = {
        resolve_vendor_identity(example.case).resolved_vendor_id for example in sequence
    }

    assert len(resolved_ids) == 1
    assert None not in resolved_ids
