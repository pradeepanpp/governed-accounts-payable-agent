from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from governed_ap.benchmark_freeze import (
    FreezeManifest,
    FreezeVersions,
    build_freeze_manifest,
    canonical_dataset_bytes,
    manifest_json,
)
from governed_ap.schemas import (
    BenchmarkExample,
    DatasetSplit,
)
from governed_ap.split_policy import (
    TemplateAssignment,
    assert_materialization_allowed,
)

DATASET_FILENAME = "benchmark.json"
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class BenchmarkArtifact:
    directory: Path
    dataset_path: Path
    manifest_path: Path
    manifest: FreezeManifest


def _file_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while chunk := file_handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def verify_benchmark_artifact(
    directory: Path,
) -> FreezeManifest:
    dataset_path = directory / DATASET_FILENAME

    manifest_path = directory / MANIFEST_FILENAME

    if not dataset_path.is_file():
        raise FileNotFoundError(f"Missing benchmark dataset: {dataset_path}")

    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing benchmark manifest: {manifest_path}")

    manifest = FreezeManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    actual_hash = _file_sha256(dataset_path)

    if actual_hash != manifest.dataset_sha256:
        raise ValueError("Benchmark dataset SHA-256 does not match its manifest.")

    return manifest


def write_development_artifact(
    scenarios: list[list[BenchmarkExample]],
    *,
    destination: Path,
    seed: int,
    template_catalog: tuple[
        TemplateAssignment,
        ...,
    ],
    versions: FreezeVersions,
    created_at_utc: datetime | None = None,
) -> BenchmarkArtifact:
    if destination.exists():
        raise FileExistsError(f"Benchmark artifact already exists: {destination}")

    for assignment in template_catalog:
        assert_materialization_allowed(assignment)

        if assignment.split != DatasetSplit.DEVELOPMENT:
            raise ValueError("Development artifact writer accepts development templates only.")

    manifest = build_freeze_manifest(
        scenarios,
        split=DatasetSplit.DEVELOPMENT,
        seed=seed,
        template_catalog=template_catalog,
        versions=versions,
        created_at_utc=created_at_utc,
    )

    dataset_bytes = canonical_dataset_bytes(scenarios)

    calculated_hash = hashlib.sha256(dataset_bytes).hexdigest()

    if calculated_hash != manifest.dataset_sha256:
        raise RuntimeError("Dataset serialization does not match freeze-manifest hash.")

    parent = destination.parent

    parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix=(f".{destination.name}.tmp-"),
            dir=parent,
        )
    )

    try:
        temporary_dataset = temporary_directory / DATASET_FILENAME

        temporary_manifest = temporary_directory / MANIFEST_FILENAME

        temporary_dataset.write_bytes(dataset_bytes)

        temporary_manifest.write_text(
            manifest_json(manifest),
            encoding="utf-8",
        )

        written_hash = _file_sha256(temporary_dataset)

        if written_hash != manifest.dataset_sha256:
            raise RuntimeError("Written benchmark dataset failed SHA-256 verification.")

        written_manifest = FreezeManifest.model_validate_json(
            temporary_manifest.read_text(encoding="utf-8")
        )

        if written_manifest != manifest:
            raise RuntimeError("Written benchmark manifest does not round-trip correctly.")

        temporary_directory.rename(destination)

    except Exception:
        shutil.rmtree(
            temporary_directory,
            ignore_errors=True,
        )
        raise

    verified_manifest = verify_benchmark_artifact(destination)

    if verified_manifest != manifest:
        raise RuntimeError("Published benchmark artifact failed final verification.")

    return BenchmarkArtifact(
        directory=destination,
        dataset_path=(destination / DATASET_FILENAME),
        manifest_path=(destination / MANIFEST_FILENAME),
        manifest=manifest,
    )
