import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitProvenance:
    revision: str
    dirty: bool


def _git_output(repository: str | Path, *arguments: str) -> str:
    command = ["git", "-C", str(repository), *arguments]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("Could not verify local Git provenance.") from exc

    return result.stdout.strip()


def read_git_provenance(
    repository: str | Path = ".",
) -> GitProvenance:
    revision = _git_output(repository, "rev-parse", "--verify", "HEAD")

    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None:
        raise ValueError("Invalid Git revision returned by Git.")

    changes = _git_output(
        repository,
        "status",
        "--porcelain",
        "--untracked-files=normal",
    )

    return GitProvenance(
        revision=revision,
        dirty=bool(changes),
    )
