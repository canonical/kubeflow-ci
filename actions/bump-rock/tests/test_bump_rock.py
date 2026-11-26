# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for CLI helpers in bump_rock.py."""

import json
from unittest.mock import patch

import pytest
from src import bump_rock
from src.errors import BumpRockError


def test_rock_context_combines_agents_md_and_cli_text(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Use the deadsnakes PPA.\n")
    ctx = bump_rock._rock_context(tmp_path, "  skip the docs part  ")
    assert ctx.index("Use the deadsnakes PPA.") < ctx.index("skip the docs part")
    assert "AGENTS.md in the rock folder" in ctx


def test_rock_context_empty_without_sources(tmp_path):
    assert bump_rock._rock_context(tmp_path, "  ") == ""


def _open_pr_setup(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "pmml").mkdir()
    (repo / "pmml" / "rockcraft.yaml").write_text("old")
    out = tmp_path / "out"
    out.mkdir()
    (out / "metadata.json").write_text(json.dumps({"rock_name": "pmml", "target_version": "v1"}))
    (out / "rockcraft.yaml.new").write_text("new")
    return repo, out


def test_open_pr_dry_run_uses_custom_branch(tmp_path, capsys):
    repo, out = _open_pr_setup(tmp_path)
    args = bump_rock.build_parser().parse_args(
        ["open-pr", str(repo), "--out-dir", str(out), "--branch", "kf-1234/bump"]
    )
    with patch.object(bump_rock.pr_mod, "pr_body", return_value="body"):
        assert args.func(args) == 0
    assert json.loads(capsys.readouterr().out)["branch"] == "kf-1234/bump"


def test_open_pr_refuses_existing_custom_branch(tmp_path):
    repo, out = _open_pr_setup(tmp_path)
    args = bump_rock.build_parser().parse_args(
        ["open-pr", str(repo), "--out-dir", str(out), "--branch", "taken", "--confirm"]
    )
    with (
        patch.object(bump_rock.pr_mod, "pr_body", return_value="body"),
        patch.object(bump_rock.git_ops_mod, "assert_clean_main"),
        patch.object(bump_rock.git_ops_mod, "remote_branches", return_value=["main", "taken"]),
        patch.object(bump_rock.git_ops_mod, "create_commit_push") as push,
    ):
        with pytest.raises(BumpRockError, match="already exists"):
            args.func(args)
    push.assert_not_called()
    assert (repo / "pmml" / "rockcraft.yaml").read_text() == "old"


@pytest.mark.parametrize("name", ["main", "bad..name", "-x", "has space"])
def test_branch_flag_rejects_invalid_names(name):
    with pytest.raises(SystemExit):
        bump_rock.build_parser().parse_args(["open-pr", "r", "--out-dir", "o", "--branch", name])


def test_open_pr_dry_run_lists_reviewers(tmp_path, capsys):
    repo, out = _open_pr_setup(tmp_path)
    args = bump_rock.build_parser().parse_args(
        ["open-pr", str(repo), "--out-dir", str(out)]
        + ["--reviewer", "alice, canonical/mlops", "--reviewer", "bob", "--reviewer", "alice"]
    )
    with patch.object(bump_rock.pr_mod, "pr_body", return_value="body"):
        assert args.func(args) == 0
    assert json.loads(capsys.readouterr().out)["reviewers"] == ["alice", "canonical/mlops", "bob"]
