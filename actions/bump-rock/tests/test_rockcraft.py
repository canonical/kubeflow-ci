# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for rockcraft.yaml parsing."""
from pathlib import Path

import pytest

from src import rockcraft
from src.errors import RockcraftParseError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_happy_path():
    doc = rockcraft.load(FIXTURES / "happy")
    assert doc.name == "pmmlserver"
    assert doc.version == "0.17.0"
    assert doc.based_on_urls == [
        "https://github.com/kserve/kserve/blob/v0.17.0/python/pmml.Dockerfile"
    ]


def test_load_multi_url():
    doc = rockcraft.load(FIXTURES / "multi_url")
    assert len(doc.based_on_urls) == 2
    assert all("kserve/kserve" in u for u in doc.based_on_urls)


def test_load_missing_file(tmp_path):
    with pytest.raises(RockcraftParseError, match="not found"):
        rockcraft.load(tmp_path)


def test_load_no_based_on_comment():
    with pytest.raises(RockcraftParseError, match="no '# Based on"):
        rockcraft.load(FIXTURES / "no_based_on")


def test_load_missing_required_field():
    with pytest.raises(RockcraftParseError, match="missing required field 'version'"):
        rockcraft.load(FIXTURES / "missing_version")


def test_extract_stops_at_first_non_comment():
    text = (
        "# Based on https://github.com/a/b/blob/v1/D\n"
        "name: foo\n"
        "# Based on https://github.com/x/y/blob/v9/D\n"
    )
    assert rockcraft._extract_based_on_urls(text) == [
        "https://github.com/a/b/blob/v1/D"
    ]
