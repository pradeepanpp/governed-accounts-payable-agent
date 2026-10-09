from datetime import datetime, timezone

import pytest

from governed_ap.benchmark_freeze import (
    FreezeVersions,
    build_freeze_manifest,
    dataset_sha256,
    manifest_json,
    template_catalog_sha256,
)
from governed_ap.benchmark_generator import (
    generate_pilot_benchmark,
)
from governed_ap.schemas import DatasetSplit
from governed_ap.split_policy import (
    DEVELOPMENT_TEMPLATE_CATALOG,
)


def make_versions() -> FreezeVersions:
    return FreezeVersions(
        benchmark_version="pilot-v1",
        threat_model_version="draft-v1",
        generator_version="generator-v1",
        oracle_version="oracle-v1",
        resolver_version="resolver-v1",
        source_revision="test-revision",
    )


def test_pilot_freeze_manifest_has_expected_counts():
    scenarios = generate_pilot_benchmark(seed=2026)

    manifest = build_freeze_manifest(
        scenarios,
        split=DatasetSplit.DEVELOPMENT,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
        created_at_utc=datetime(
            2026,
            10,
            9,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert manifest.scenario_count == 60
    assert manifest.invoice_count == 84
    assert manifest.split == DatasetSplit.DEVELOPMENT


def test_dataset_hash_is_deterministic():
    first = generate_pilot_benchmark(seed=2026)

    second = generate_pilot_benchmark(seed=2026)

    assert dataset_sha256(first) == dataset_sha256(second)


def test_different_seed_changes_dataset_hash():
    first = generate_pilot_benchmark(seed=2026)

    second = generate_pilot_benchmark(seed=2027)

    assert dataset_sha256(first) != dataset_sha256(second)


def test_manifest_uses_all_registered_development_templates():
    scenarios = generate_pilot_benchmark(seed=2026)

    manifest = build_freeze_manifest(
        scenarios,
        split=DatasetSplit.DEVELOPMENT,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    expected_template_ids = {assignment.template_id for assignment in DEVELOPMENT_TEMPLATE_CATALOG}

    assert set(manifest.template_ids) == expected_template_ids

    assert sum(manifest.template_scenario_counts.values()) == 60


def test_template_catalog_hash_is_deterministic():
    first = template_catalog_sha256(DEVELOPMENT_TEMPLATE_CATALOG)

    reversed_catalog = tuple(reversed(DEVELOPMENT_TEMPLATE_CATALOG))

    second = template_catalog_sha256(reversed_catalog)

    assert first == second


def test_duplicate_scenario_id_is_rejected():
    scenarios = generate_pilot_benchmark(seed=2026)

    duplicated = [
        scenarios[0],
        scenarios[0],
        *scenarios[1:],
    ]

    with pytest.raises(
        ValueError,
        match="Duplicate scenario_id",
    ):
        build_freeze_manifest(
            duplicated,
            split=DatasetSplit.DEVELOPMENT,
            seed=2026,
            template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
            versions=make_versions(),
        )


def test_wrong_split_is_rejected():
    scenarios = generate_pilot_benchmark(seed=2026)

    with pytest.raises(
        ValueError,
        match="requested split",
    ):
        build_freeze_manifest(
            scenarios,
            split=DatasetSplit.IID_TEST,
            seed=2026,
            template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
            versions=make_versions(),
        )


def test_unregistered_template_is_rejected():
    scenarios = generate_pilot_benchmark(seed=2026)

    scenarios = [[example.model_copy(deep=True) for example in scenario] for scenario in scenarios]

    scenarios[0][0].ground_truth.template_id = "UNREGISTERED-TEMPLATE"

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        build_freeze_manifest(
            scenarios,
            split=DatasetSplit.DEVELOPMENT,
            seed=2026,
            template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
            versions=make_versions(),
        )


def test_naive_freeze_timestamp_is_rejected():
    scenarios = generate_pilot_benchmark(seed=2026)

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        build_freeze_manifest(
            scenarios,
            split=DatasetSplit.DEVELOPMENT,
            seed=2026,
            template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
            versions=make_versions(),
            created_at_utc=datetime(
                2026,
                10,
                9,
                10,
                0,
            ),
        )


def test_manifest_json_is_deterministic_for_fixed_manifest():
    scenarios = generate_pilot_benchmark(seed=2026)

    manifest = build_freeze_manifest(
        scenarios,
        split=DatasetSplit.DEVELOPMENT,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
        created_at_utc=datetime(
            2026,
            10,
            9,
            10,
            0,
            tzinfo=timezone.utc,
        ),
    )

    first = manifest_json(manifest)
    second = manifest_json(manifest)

    assert first == second

    assert manifest.dataset_sha256 in first
