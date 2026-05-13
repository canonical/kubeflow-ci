# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for URL validation and bounded repair."""
import pytest
import responses

from src import repair, urls

REF = urls.UpstreamRef(org="k", repo="k", ref="v1", path="python/pmml.Dockerfile")


def _raw(path):
    return f"https://raw.githubusercontent.com/k/k/v1/{path}"


def _tree(repo="k/k", ref="v1"):
    return (
        f"https://api.github.com/repos/{repo}/git/trees/{ref}?recursive=1"
    )


@responses.activate
def test_validate_or_repair_happy_path():
    responses.get(_raw("python/pmml.Dockerfile"), status=200, body="FROM scratch")
    res = repair.validate_or_repair(REF)
    assert res.ok is True
    assert res.was_repaired is False
    assert res.ref == REF


@responses.activate
def test_repair_unique_match():
    # First lookup at the original (broken) path 404s.
    responses.get(_raw("python/pmml.Dockerfile"), status=404)
    # Tree listing returns the file under a different directory.
    responses.get(
        _tree(),
        status=200,
        json={
            "tree": [
                {"path": "src/python/pmml.Dockerfile", "type": "blob"},
                {"path": "README.md", "type": "blob"},
            ]
        },
    )
    # Re-validation of the candidate succeeds.
    responses.get(_raw("src/python/pmml.Dockerfile"), status=200, body="FROM scratch")

    res = repair.validate_or_repair(REF)

    assert res.ok is True
    assert res.was_repaired is True
    assert res.ref.path == "src/python/pmml.Dockerfile"
    assert res.repaired_from == REF


@responses.activate
def test_repair_no_match():
    responses.get(_raw("python/pmml.Dockerfile"), status=404)
    responses.get(
        _tree(),
        status=200,
        json={"tree": [{"path": "README.md", "type": "blob"}]},
    )
    res = repair.validate_or_repair(REF)
    assert res.ok is False
    assert "no file named" in res.error


@responses.activate
def test_repair_multiple_matches_returns_candidates():
    responses.get(_raw("python/pmml.Dockerfile"), status=404)
    responses.get(
        _tree(),
        status=200,
        json={
            "tree": [
                {"path": "a/pmml.Dockerfile", "type": "blob"},
                {"path": "b/pmml.Dockerfile", "type": "blob"},
            ]
        },
    )
    res = repair.validate_or_repair(REF)
    assert res.ok is False
    assert res.candidates is not None
    assert {c.path for c in res.candidates} == {
        "a/pmml.Dockerfile",
        "b/pmml.Dockerfile",
    }


@responses.activate
def test_repair_tree_api_failure_returns_error():
    responses.get(_raw("python/pmml.Dockerfile"), status=404)
    responses.get(_tree(), status=403, body="rate limited")
    res = repair.validate_or_repair(REF)
    assert res.ok is False
    assert "tree listing failed" in res.error.lower()
