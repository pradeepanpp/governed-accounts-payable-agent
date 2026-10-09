from datetime import datetime, timezone

import pytest

from governed_ap.benchmark_artifacts import (
    DATASET_FILENAME,
    MANIFEST_FILENAME,
    verify_benchmark_artifact,
    write_development_artifact,
)
from governed_ap.benchmark_freeze import (
    FreezeVersions,
)
from governed_ap.benchmark_generator import (
    generate_pilot_benchmark,
)
from governed_ap.schemas import DatasetSplit
from governed_ap.split_policy import (
    DEVELOPMENT_TEMPLATE_CATALOG,
    IID_TEMPLATE_RESERVATIONS,
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


def test_development_artifact_is_written(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
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

    assert artifact.directory.is_dir()

    assert artifact.dataset_path == destination / DATASET_FILENAME

    assert artifact.manifest_path == destination / MANIFEST_FILENAME

    assert artifact.dataset_path.is_file()
    assert artifact.manifest_path.is_file()

    assert artifact.manifest.scenario_count == 60

    assert artifact.manifest.invoice_count == 84


def test_written_artifact_can_be_verified(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    verified = verify_benchmark_artifact(destination)

    assert verified == artifact.manifest


def test_dataset_file_hash_matches_manifest(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    import hashlib

    dataset_bytes = artifact.dataset_path.read_bytes()

    file_hash = hashlib.sha256(dataset_bytes).hexdigest()

    assert file_hash == artifact.manifest.dataset_sha256


def test_existing_artifact_is_not_overwritten(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    with pytest.raises(
        FileExistsError,
        match="already exists",
    ):
        write_development_artifact(
            scenarios,
            destination=destination,
            seed=2026,
            template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
            versions=make_versions(),
        )


def test_iid_catalog_cannot_use_development_writer(
    tmp_path,
):
    destination = tmp_path / "iid-invalid"

    scenarios = generate_pilot_benchmark(seed=2026)

    with pytest.raises(
        ValueError,
        match="cannot be materialized",
    ):
        write_development_artifact(
            scenarios,
            destination=destination,
            seed=2026,
            template_catalog=(IID_TEMPLATE_RESERVATIONS),
            versions=make_versions(),
        )

    assert not destination.exists()


def test_tampered_dataset_is_detected(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    original = artifact.dataset_path.read_bytes()

    artifact.dataset_path.write_bytes(original + b" ")

    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        verify_benchmark_artifact(destination)


def test_missing_manifest_is_detected(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    artifact.manifest_path.unlink()

    with pytest.raises(
        FileNotFoundError,
        match="Missing benchmark manifest",
    ):
        verify_benchmark_artifact(destination)


def test_missing_dataset_is_detected(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    artifact.dataset_path.unlink()

    with pytest.raises(
        FileNotFoundError,
        match="Missing benchmark dataset",
    ):
        verify_benchmark_artifact(destination)


def test_written_manifest_is_development_split(
    tmp_path,
):
    destination = tmp_path / "development-pilot"

    scenarios = generate_pilot_benchmark(seed=2026)

    artifact = write_development_artifact(
        scenarios,
        destination=destination,
        seed=2026,
        template_catalog=(DEVELOPMENT_TEMPLATE_CATALOG),
        versions=make_versions(),
    )

    assert artifact.manifest.split == DatasetSplit.DEVELOPMENT
