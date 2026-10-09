import pytest

from governed_ap.benchmark_generator import (
    flatten_scenarios,
    generate_pilot_benchmark,
)
from governed_ap.schemas import DatasetSplit
from governed_ap.split_policy import (
    CALIBRATION_TEMPLATE_RESERVATIONS,
    DEVELOPMENT_TEMPLATE_CATALOG,
    HELD_OUT_ATTACK_SUBTYPES,
    IID_TEMPLATE_RESERVATIONS,
    OOD_TEMPLATE_RESERVATIONS,
    PLANNED_TEMPLATE_CATALOG,
    TemplateAssignment,
    TemplateKind,
    assert_materialization_allowed,
    template_ids_for_split,
    validate_template_catalog,
)


def test_planned_template_catalog_is_valid():
    validate_template_catalog(PLANNED_TEMPLATE_CATALOG)


def test_all_template_ids_are_unique():
    template_ids = [assignment.template_id for assignment in PLANNED_TEMPLATE_CATALOG]

    assert len(template_ids) == len(set(template_ids))


def test_pilot_uses_only_registered_development_templates():
    scenarios = generate_pilot_benchmark(seed=2026)

    examples = flatten_scenarios(scenarios)

    pilot_template_ids = {example.ground_truth.template_id for example in examples}

    development_template_ids = template_ids_for_split(DatasetSplit.DEVELOPMENT)

    assert pilot_template_ids == development_template_ids


def test_held_out_subtypes_are_reserved_only_for_ood():
    held_out = set(HELD_OUT_ATTACK_SUBTYPES)

    ood_subtypes = {assignment.attack_subtype for assignment in OOD_TEMPLATE_RESERVATIONS}

    assert ood_subtypes == held_out

    non_ood_assignments = (
        DEVELOPMENT_TEMPLATE_CATALOG + CALIBRATION_TEMPLATE_RESERVATIONS + IID_TEMPLATE_RESERVATIONS
    )

    assert all(assignment.attack_subtype not in held_out for assignment in non_ood_assignments)


def test_final_test_templates_are_not_materialized():
    test_reservations = IID_TEMPLATE_RESERVATIONS + OOD_TEMPLATE_RESERVATIONS

    assert all(assignment.materialized is False for assignment in test_reservations)


def test_calibration_templates_are_not_materialized_yet():
    assert all(assignment.materialized is False for assignment in CALIBRATION_TEMPLATE_RESERVATIONS)


def test_duplicate_template_id_is_rejected():
    assignments = (
        TemplateAssignment(
            template_id="T1.1-dev-v1",
            split=DatasetSplit.DEVELOPMENT,
            kind=TemplateKind.ATTACK_SINGLE,
            template_variant="dev-test",
            attack_subtype="T1.1",
        ),
        TemplateAssignment(
            template_id="T1.1-dev-v1",
            split=DatasetSplit.CALIBRATION,
            kind=TemplateKind.ATTACK_SINGLE,
            template_variant="cal-test",
            attack_subtype="T1.1",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Duplicate template_id",
    ):
        validate_template_catalog(assignments)


def test_held_out_subtype_outside_ood_is_rejected():
    assignments = (
        TemplateAssignment(
            template_id="T1.3-dev-invalid",
            split=DatasetSplit.DEVELOPMENT,
            kind=TemplateKind.ATTACK_SINGLE,
            template_variant="dev-test",
            attack_subtype="T1.3",
        ),
    )

    with pytest.raises(
        ValueError,
        match="may only appear in OOD",
    ):
        validate_template_catalog(assignments)


def test_non_held_out_subtype_in_ood_is_rejected():
    assignments = (
        TemplateAssignment(
            template_id="T1.1-ood-invalid",
            split=DatasetSplit.OOD_TEST,
            kind=TemplateKind.ATTACK_SINGLE,
            template_variant="ood-test",
            attack_subtype="T1.1",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Non-held-out subtype",
    ):
        validate_template_catalog(assignments)


def test_legitimate_template_in_ood_is_rejected():
    assignments = (
        TemplateAssignment(
            template_id="C1-ood-invalid",
            split=DatasetSplit.OOD_TEST,
            kind=TemplateKind.LEGITIMATE_SINGLE,
            template_variant="ood-test",
            legitimate_case="C1",
        ),
    )

    with pytest.raises(
        ValueError,
        match="OOD contains held-out",
    ):
        validate_template_catalog(assignments)


def test_unknown_attack_subtype_is_rejected():
    assignments = (
        TemplateAssignment(
            template_id="T9.9-dev-v1",
            split=DatasetSplit.DEVELOPMENT,
            kind=TemplateKind.ATTACK_SINGLE,
            template_variant="dev-test",
            attack_subtype="T9.9",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Unknown single attack subtype",
    ):
        validate_template_catalog(assignments)


def test_sequence_attack_cannot_be_marked_single():
    assignments = (
        TemplateAssignment(
            template_id="T4.1-dev-invalid",
            split=DatasetSplit.DEVELOPMENT,
            kind=TemplateKind.ATTACK_SINGLE,
            template_variant="dev-test",
            attack_subtype="T4.1",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Unknown single attack subtype",
    ):
        validate_template_catalog(assignments)


def test_unknown_legitimate_case_is_rejected():
    assignments = (
        TemplateAssignment(
            template_id="C99-dev-v1",
            split=DatasetSplit.DEVELOPMENT,
            kind=TemplateKind.LEGITIMATE_SINGLE,
            template_variant="dev-test",
            legitimate_case="C99",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Unknown single legitimate case",
    ):
        validate_template_catalog(assignments)


def test_sequence_legitimate_case_cannot_be_marked_single():
    assignments = (
        TemplateAssignment(
            template_id="C7-dev-invalid",
            split=DatasetSplit.DEVELOPMENT,
            kind=TemplateKind.LEGITIMATE_SINGLE,
            template_variant="dev-test",
            legitimate_case="C7",
        ),
    )

    with pytest.raises(
        ValueError,
        match="Unknown single legitimate case",
    ):
        validate_template_catalog(assignments)


def test_development_template_can_be_materialized():
    assignment = TemplateAssignment(
        template_id="C1-dev-test",
        split=DatasetSplit.DEVELOPMENT,
        kind=TemplateKind.LEGITIMATE_SINGLE,
        template_variant="dev-test",
        legitimate_case="C1",
        materialized=True,
    )

    assert_materialization_allowed(assignment)


def test_reserved_iid_template_cannot_be_materialized():
    assignment = TemplateAssignment(
        template_id="C1-iid-test",
        split=DatasetSplit.IID_TEST,
        kind=TemplateKind.LEGITIMATE_SINGLE,
        template_variant="iid-test",
        legitimate_case="C1",
        materialized=False,
    )

    with pytest.raises(
        ValueError,
        match="cannot be materialized",
    ):
        assert_materialization_allowed(assignment)


def test_reserved_ood_template_cannot_be_materialized():
    assignment = TemplateAssignment(
        template_id="T1.3-ood-test",
        split=DatasetSplit.OOD_TEST,
        kind=TemplateKind.ATTACK_SINGLE,
        template_variant="ood-test",
        attack_subtype="T1.3",
        materialized=False,
    )

    with pytest.raises(
        ValueError,
        match="cannot be materialized",
    ):
        assert_materialization_allowed(assignment)


def test_reserved_materialization_requires_explicit_override():
    assignment = TemplateAssignment(
        template_id="C1-cal-test",
        split=DatasetSplit.CALIBRATION,
        kind=TemplateKind.LEGITIMATE_SINGLE,
        template_variant="cal-test",
        legitimate_case="C1",
        materialized=False,
    )

    assert_materialization_allowed(
        assignment,
        allow_reserved=True,
    )


def test_split_variants_are_distinct():
    dev = {assignment.template_variant for assignment in DEVELOPMENT_TEMPLATE_CATALOG}

    calibration = {assignment.template_variant for assignment in CALIBRATION_TEMPLATE_RESERVATIONS}

    iid = {assignment.template_variant for assignment in IID_TEMPLATE_RESERVATIONS}

    assert dev.isdisjoint(calibration)
    assert dev.isdisjoint(iid)
    assert calibration.isdisjoint(iid)


def test_reserved_template_cannot_bypass_guard_with_materialized_true():
    assignment = TemplateAssignment(
        template_id="T1.3-ood-bypass-test",
        split=DatasetSplit.OOD_TEST,
        kind=TemplateKind.ATTACK_SINGLE,
        template_variant="ood-test",
        attack_subtype="T1.3",
        materialized=True,
    )

    with pytest.raises(
        ValueError,
        match="cannot be materialized",
    ):
        assert_materialization_allowed(assignment)
