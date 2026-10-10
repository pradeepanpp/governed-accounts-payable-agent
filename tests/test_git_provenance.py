import re
import subprocess

import pytest

from governed_ap.git_provenance import read_git_provenance


def git(repository, *arguments):
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def test_git_provenance_detects_clean_and_dirty_repository(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test User")

    tracked = tmp_path / "sample.txt"
    tracked.write_text("original", encoding="utf-8")

    git(tmp_path, "add", "sample.txt")
    git(tmp_path, "commit", "-m", "initial test commit")

    clean = read_git_provenance(tmp_path)

    assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", clean.revision)
    assert clean.dirty is False

    tracked.write_text("modified", encoding="utf-8")

    dirty = read_git_provenance(tmp_path)

    assert dirty.revision == clean.revision
    assert dirty.dirty is True

    tracked.write_text("original", encoding="utf-8")

    assert read_git_provenance(tmp_path).dirty is False

    (tmp_path / "new_file.txt").write_text("untracked", encoding="utf-8")

    assert read_git_provenance(tmp_path).dirty is True


def test_non_git_directory_is_rejected(tmp_path):
    with pytest.raises(RuntimeError, match="Git provenance"):
        read_git_provenance(tmp_path)
