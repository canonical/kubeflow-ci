# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for CLI helpers in bump_rock.py."""

from src import bump_rock


def test_rock_context_combines_agents_md_and_cli_text(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Use the deadsnakes PPA.\n")
    ctx = bump_rock._rock_context(tmp_path, "  skip the docs part  ")
    assert ctx.index("Use the deadsnakes PPA.") < ctx.index("skip the docs part")
    assert "AGENTS.md in the rock folder" in ctx


def test_rock_context_empty_without_sources(tmp_path):
    assert bump_rock._rock_context(tmp_path, "  ") == ""
