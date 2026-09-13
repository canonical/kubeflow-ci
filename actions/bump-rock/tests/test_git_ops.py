# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the git/gh subprocess wrappers (subprocess mocked)."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src import git_ops
from src.errors import BumpRockError


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_run_raises_on_nonzero(tmp_path):
    with patch("subprocess.run", return_value=_completed(returncode=1, stderr="boom")):
        with pytest.raises(BumpRockError, match="boom"):
            git_ops._run(["git", "status"], cwd=tmp_path)


def test_assert_clean_main_passes(tmp_path):
    results = [_completed(stdout="main\n"), _completed(stdout="")]
    with patch("subprocess.run", side_effect=results):
        git_ops.assert_clean_main(tmp_path)


def test_assert_clean_main_rejects_wrong_branch(tmp_path):
    with patch("subprocess.run", return_value=_completed(stdout="feature\n")):
        with pytest.raises(BumpRockError, match="feature"):
            git_ops.assert_clean_main(tmp_path)


def test_assert_clean_main_rejects_dirty_tree(tmp_path):
    results = [_completed(stdout="main\n"), _completed(stdout=" M file.py\n")]
    with patch("subprocess.run", side_effect=results):
        with pytest.raises(BumpRockError, match="uncommitted"):
            git_ops.assert_clean_main(tmp_path)


def test_remote_branches_parses_ls_remote(tmp_path):
    stdout = (
        "deadbeef\trefs/heads/main\n"
        "cafef00d\trefs/heads/bump/pmml-v0.18.0\n"
        "1234abcd\trefs/tags/v1.0.0\n"  # tag, must be ignored
    )
    with patch("subprocess.run", return_value=_completed(stdout=stdout)):
        branches = git_ops.remote_branches(tmp_path)
    assert branches == ["main", "bump/pmml-v0.18.0"]


def test_create_commit_push_invokes_expected_commands(tmp_path):
    calls = []

    def fake(cmd, **kwargs):
        calls.append(list(cmd))
        return _completed(stdout="ok\n")

    with patch("subprocess.run", side_effect=fake):
        git_ops.create_commit_push(
            tmp_path,
            branch="bump/x",
            file_to_stage="x/rockcraft.yaml",
            commit_message="chore(x): bump",
        )

    assert [c[:2] for c in calls] == [
        ["git", "checkout"],
        ["git", "add"],
        ["git", "commit"],
        ["git", "push"],
    ]
    assert calls[0] == ["git", "checkout", "-b", "bump/x"]
    assert calls[1] == ["git", "add", "x/rockcraft.yaml"]
    assert "-m" in calls[2] and "chore(x): bump" in calls[2]
    assert calls[3] == ["git", "push", "-u", "origin", "bump/x"]


def test_create_pr_returns_url_and_labels(tmp_path):
    seq = [
        _completed(stdout="https://github.com/foo/bar/pull/1\n"),
        _completed(stdout=""),
    ]
    calls = []

    def fake(cmd, **kwargs):
        calls.append(list(cmd))
        return seq.pop(0)

    with patch("subprocess.run", side_effect=fake):
        url = git_ops.create_pr(
            tmp_path, title="t", body="b", label="ai-generated"
        )
    assert url == "https://github.com/foo/bar/pull/1"
    assert calls[0][:3] == ["gh", "pr", "create"]
    assert calls[1][:3] == ["gh", "pr", "edit"]
    assert "--add-label" in calls[1]


def test_create_pr_draft_passes_flag(tmp_path):
    seq = [_completed(stdout="https://github.com/foo/bar/pull/9\n")]
    captured = []

    def fake(cmd, **kwargs):
        captured.append(list(cmd))
        return seq.pop(0)

    with patch("subprocess.run", side_effect=fake):
        url = git_ops.create_pr(tmp_path, title="t", body="b", draft=True)
    assert url == "https://github.com/foo/bar/pull/9"
    assert "--draft" in captured[0]


def test_create_pr_swallows_label_failure(tmp_path):
    seq = [
        _completed(stdout="https://github.com/foo/bar/pull/1\n"),
        _completed(returncode=1, stderr="no such label"),
    ]

    def fake(cmd, **kwargs):
        return seq.pop(0)

    with patch("subprocess.run", side_effect=fake):
        url = git_ops.create_pr(
            tmp_path, title="t", body="b", label="missing-label"
        )
    assert url == "https://github.com/foo/bar/pull/1"
