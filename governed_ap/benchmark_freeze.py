from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from governed_ap.schemas import BenchmarkExample, DatasetSplit
from governed_ap.split_policy import (
    TemplateAssignment,
    validate_template_catalog,
)


class FreezeVersions(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    benchmark_version: str = Field(min_length=1)
    threat_model_version: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    oracle_version: str = Field(min_length=1)
    resolver_version: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)


class FreezeManifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    split: DatasetSplit
    seed: int

    scenario_count: int = Field(gt=0)
    invoice_count: int = Field(gt=0)

    template_ids: tuple[str, ...]
    template_scenario_counts: dict[str, int]

    dataset_sha256: str = Field(
        min_length=64,
        max_length=64,
    )

    template_catalog_sha256: str = Field(
        min_length=64,
        max_length=64,
    )

    created_at_utc: datetime

    versions: FreezeVersions

    @field_validator("created_at_utc")
    @classmethod
    def validate_created_at_utc(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at_utc must be timezone-aware.")

        return value.astimezone(timezone.utc)


def _canonical_json_bytes(
    value: Any,
) -> bytes:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return text.encode("utf-8")


def _sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_dataset_payload(
    scenarios: list[list[BenchmarkExample]],
) -> list[list[dict[str, Any]]]:
    return [[example.model_dump(mode="json") for example in scenario] for scenario in scenarios]


def dataset_sha256(
    scenarios: list[list[BenchmarkExample]],
) -> str:
    payload = canonical_dataset_payload(scenarios)

    return _sha256_bytes(_canonical_json_bytes(payload))


def canonical_template_catalog_payload(
    assignments: tuple[TemplateAssignment, ...],
) -> list[dict[str, Any]]:
    ordered_assignments = sorted(
        assignments,
        key=lambda assignment: assignment.template_id,
    )

    return [
        {
            "template_id": assignment.template_id,
            "split": assignment.split.value,
            "kind": assignment.kind.value,
            "template_variant": (assignment.template_variant),
            "attack_subtype": (assignment.attack_subtype),
            "legitimate_case": (assignment.legitimate_case),
            "materialized": (assignment.materialized),
        }
        for assignment in ordered_assignments
    ]


def template_catalog_sha256(
    assignments: tuple[TemplateAssignment, ...],
) -> str:
    payload = canonical_template_catalog_payload(assignments)

    return _sha256_bytes(_canonical_json_bytes(payload))


def _validate_scenarios(
    scenarios: list[list[BenchmarkExample]],
    *,
    split: DatasetSplit,
) -> Counter[str]:
    if not scenarios:
        raise ValueError("Cannot freeze an empty benchmark.")

    seen_scenario_ids: set[str] = set()
    template_counts: Counter[str] = Counter()

    for scenario in scenarios:
        if not scenario:
            raise ValueError("Benchmark scenarios cannot be empty.")

        first_ground_truth = scenario[0].ground_truth

        scenario_id = first_ground_truth.scenario_id

        template_id = first_ground_truth.template_id

        if scenario_id is None:
            raise ValueError("Every frozen scenario must have a scenario_id.")

        if template_id is None:
            raise ValueError("Every frozen scenario must have a template_id.")

        if scenario_id in seen_scenario_ids:
            raise ValueError(f"Duplicate scenario_id: {scenario_id}")

        seen_scenario_ids.add(scenario_id)

        for example in scenario:
            ground_truth = example.ground_truth

            if ground_truth.split != split:
                raise ValueError("Scenario contains an example from the wrong split.")

            if ground_truth.scenario_id != scenario_id:
                raise ValueError("Scenario contains inconsistent scenario_id values.")

            if ground_truth.template_id != template_id:
                raise ValueError("Scenario contains inconsistent template_id values.")

        template_counts[template_id] += 1

    return template_counts


def build_freeze_manifest(
    scenarios: list[list[BenchmarkExample]],
    *,
    split: DatasetSplit,
    seed: int,
    template_catalog: tuple[
        TemplateAssignment,
        ...,
    ],
    versions: FreezeVersions,
    created_at_utc: datetime | None = None,
) -> FreezeManifest:
    validate_template_catalog(template_catalog)

    if any(assignment.split != split for assignment in template_catalog):
        raise ValueError("Freeze template catalog must contain only the requested split.")

    template_counts = _validate_scenarios(
        scenarios,
        split=split,
    )

    registered_template_ids = {assignment.template_id for assignment in template_catalog}

    observed_template_ids = set(template_counts)

    if observed_template_ids != registered_template_ids:
        missing = sorted(registered_template_ids - observed_template_ids)

        unexpected = sorted(observed_template_ids - registered_template_ids)

        raise ValueError(
            "Frozen benchmark template set does "
            "not match its registered catalog. "
            f"Missing={missing}; "
            f"unexpected={unexpected}."
        )

    invoice_count = sum(len(scenario) for scenario in scenarios)

    created_at = created_at_utc if created_at_utc is not None else datetime.now(timezone.utc)

    if created_at.tzinfo is None:
        raise ValueError("created_at_utc must be timezone-aware.")

    ordered_template_ids = tuple(sorted(registered_template_ids))

    ordered_template_counts = {
        template_id: template_counts[template_id] for template_id in ordered_template_ids
    }

    return FreezeManifest(
        split=split,
        seed=seed,
        scenario_count=len(scenarios),
        invoice_count=invoice_count,
        template_ids=ordered_template_ids,
        template_scenario_counts=(ordered_template_counts),
        dataset_sha256=dataset_sha256(scenarios),
        template_catalog_sha256=(template_catalog_sha256(template_catalog)),
        created_at_utc=created_at,
        versions=versions,
    )


def manifest_json(
    manifest: FreezeManifest,
) -> str:
    payload = manifest.model_dump(mode="json")

    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )
