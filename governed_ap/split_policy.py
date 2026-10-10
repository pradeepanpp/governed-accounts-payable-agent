from dataclasses import dataclass
from enum import Enum

from governed_ap.schemas import DatasetSplit

DEVELOPMENT_ATTACK_SUBTYPES = (
    "T1.1",
    "T1.2",
    "T2.1",
    "T2.3",
    "T3.1",
    "T3.2",
    "T3.3",
    "T3.5",
    "T5.1",
    "T5.2",
)

DEVELOPMENT_SEQUENCE_ATTACK_SUBTYPES = (
    "T4.1",
    "T4.2",
    "T4.3",
)

HELD_OUT_ATTACK_SUBTYPES = (
    "T1.3",
    "T2.2",
    "T3.4",
)

SINGLE_LEGITIMATE_CASES = (
    "C1",
    "C2",
    "C3",
    "C4",
    "C5",
    "C6",
    "C8",
    "C10",
)

SEQUENCE_LEGITIMATE_CASES = (
    "C7",
    "C9",
)


class TemplateKind(str, Enum):
    ATTACK_SINGLE = "attack_single"
    ATTACK_SEQUENCE = "attack_sequence"
    LEGITIMATE_SINGLE = "legitimate_single"
    LEGITIMATE_SEQUENCE = "legitimate_sequence"


@dataclass(frozen=True)
class TemplateAssignment:
    template_id: str
    split: DatasetSplit
    kind: TemplateKind
    template_variant: str
    attack_subtype: str | None = None
    legitimate_case: str | None = None
    materialized: bool = False


def _build_non_ood_catalog(
    split: DatasetSplit,
    suffix: str,
    *,
    materialized: bool,
) -> tuple[TemplateAssignment, ...]:
    assignments: list[TemplateAssignment] = []

    for attack_subtype in DEVELOPMENT_ATTACK_SUBTYPES:
        assignments.append(
            TemplateAssignment(
                template_id=(f"{attack_subtype}-{suffix}-v1"),
                split=split,
                kind=TemplateKind.ATTACK_SINGLE,
                template_variant=f"{suffix}-v1",
                attack_subtype=attack_subtype,
                materialized=materialized,
            )
        )

    for attack_subtype in DEVELOPMENT_SEQUENCE_ATTACK_SUBTYPES:
        assignments.append(
            TemplateAssignment(
                template_id=(f"{attack_subtype}-{suffix}-v1"),
                split=split,
                kind=TemplateKind.ATTACK_SEQUENCE,
                template_variant=f"{suffix}-v1",
                attack_subtype=attack_subtype,
                materialized=materialized,
            )
        )

    for case_type in SINGLE_LEGITIMATE_CASES:
        assignments.append(
            TemplateAssignment(
                template_id=f"{case_type}-{suffix}-v1",
                split=split,
                kind=TemplateKind.LEGITIMATE_SINGLE,
                template_variant=f"{suffix}-v1",
                legitimate_case=case_type,
                materialized=materialized,
            )
        )

    for case_type in SEQUENCE_LEGITIMATE_CASES:
        assignments.append(
            TemplateAssignment(
                template_id=f"{case_type}-{suffix}-v1",
                split=split,
                kind=TemplateKind.LEGITIMATE_SEQUENCE,
                template_variant=f"{suffix}-v1",
                legitimate_case=case_type,
                materialized=materialized,
            )
        )

    return tuple(assignments)


DEVELOPMENT_TEMPLATE_CATALOG = _build_non_ood_catalog(
    DatasetSplit.DEVELOPMENT,
    "dev",
    materialized=True,
)

CALIBRATION_TEMPLATE_RESERVATIONS = _build_non_ood_catalog(
    DatasetSplit.CALIBRATION,
    "cal",
    materialized=False,
)

IID_TEMPLATE_RESERVATIONS = _build_non_ood_catalog(
    DatasetSplit.IID_TEST,
    "iid",
    materialized=False,
)

OOD_TEMPLATE_RESERVATIONS = tuple(
    TemplateAssignment(
        template_id=f"{attack_subtype}-ood-v1",
        split=DatasetSplit.OOD_TEST,
        kind=TemplateKind.ATTACK_SINGLE,
        template_variant="ood-v1",
        attack_subtype=attack_subtype,
        materialized=False,
    )
    for attack_subtype in HELD_OUT_ATTACK_SUBTYPES
)


PLANNED_TEMPLATE_CATALOG = (
    DEVELOPMENT_TEMPLATE_CATALOG
    + CALIBRATION_TEMPLATE_RESERVATIONS
    + IID_TEMPLATE_RESERVATIONS
    + OOD_TEMPLATE_RESERVATIONS
)


def validate_template_catalog(
    assignments: tuple[TemplateAssignment, ...],
) -> None:
    if not assignments:
        raise ValueError("Template catalog cannot be empty.")

    template_ids: set[str] = set()

    held_out = set(HELD_OUT_ATTACK_SUBTYPES)

    valid_single_attacks = set(DEVELOPMENT_ATTACK_SUBTYPES) | held_out

    valid_sequence_attacks = set(DEVELOPMENT_SEQUENCE_ATTACK_SUBTYPES)

    valid_single_legitimate = set(SINGLE_LEGITIMATE_CASES)

    valid_sequence_legitimate = set(SEQUENCE_LEGITIMATE_CASES)

    for assignment in assignments:
        if assignment.template_id in template_ids:
            raise ValueError(f"Duplicate template_id: {assignment.template_id}")

        template_ids.add(assignment.template_id)

        if assignment.kind == TemplateKind.ATTACK_SINGLE:
            if assignment.attack_subtype is None:
                raise ValueError("Attack template must define attack_subtype.")

            if assignment.legitimate_case is not None:
                raise ValueError("Attack template cannot define legitimate_case.")

            if assignment.attack_subtype not in valid_single_attacks:
                raise ValueError(f"Unknown single attack subtype: {assignment.attack_subtype}")

        elif assignment.kind == TemplateKind.ATTACK_SEQUENCE:
            if assignment.attack_subtype is None:
                raise ValueError("Attack template must define attack_subtype.")

            if assignment.legitimate_case is not None:
                raise ValueError("Attack template cannot define legitimate_case.")

            if assignment.attack_subtype not in valid_sequence_attacks:
                raise ValueError(f"Unknown sequence attack subtype: {assignment.attack_subtype}")

        elif assignment.kind == TemplateKind.LEGITIMATE_SINGLE:
            if assignment.legitimate_case is None:
                raise ValueError("Legitimate template must define legitimate_case.")

            if assignment.attack_subtype is not None:
                raise ValueError("Legitimate template cannot define attack_subtype.")

            if assignment.legitimate_case not in valid_single_legitimate:
                raise ValueError(f"Unknown single legitimate case: {assignment.legitimate_case}")

        elif assignment.kind == TemplateKind.LEGITIMATE_SEQUENCE:
            if assignment.legitimate_case is None:
                raise ValueError("Legitimate template must define legitimate_case.")

            if assignment.attack_subtype is not None:
                raise ValueError("Legitimate template cannot define attack_subtype.")

            if assignment.legitimate_case not in valid_sequence_legitimate:
                raise ValueError(f"Unknown sequence legitimate case: {assignment.legitimate_case}")

        else:
            raise ValueError(f"Unknown template kind: {assignment.kind}")

        if assignment.attack_subtype in held_out and assignment.split != DatasetSplit.OOD_TEST:
            raise ValueError(
                f"Held-out subtype {assignment.attack_subtype} may only appear in OOD."
            )

        if assignment.split == DatasetSplit.OOD_TEST:
            if assignment.kind != TemplateKind.ATTACK_SINGLE:
                raise ValueError("OOD contains held-out single-attack subtypes only.")

            if assignment.attack_subtype not in held_out:
                raise ValueError("Non-held-out subtype cannot be assigned to OOD.")


def template_ids_for_split(
    split: DatasetSplit,
) -> set[str]:
    return {
        assignment.template_id
        for assignment in PLANNED_TEMPLATE_CATALOG
        if assignment.split == split
    }


def assert_materialization_allowed(
    assignment: TemplateAssignment,
    *,
    allow_reserved: bool = False,
) -> None:
    if assignment.split == DatasetSplit.DEVELOPMENT:
        return

    if allow_reserved:
        return

    raise ValueError(
        f"Template {assignment.template_id} is reserved "
        f"for split {assignment.split.value} and cannot "
        "be materialized during development."
    )


validate_template_catalog(PLANNED_TEMPLATE_CATALOG)
