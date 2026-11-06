# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for upstream URL parsing."""
import pytest

from src import urls
from src.errors import UpstreamUrlError


def test_parse_blob_url():
    ref = urls.parse("https://github.com/kserve/kserve/blob/v0.17.0/python/pmml.Dockerfile")
    assert ref.org == "kserve"
    assert ref.repo == "kserve"
    assert ref.ref == "v0.17.0"
    assert ref.path == "python/pmml.Dockerfile"
    assert ref.basename == "pmml.Dockerfile"


def test_parse_raw_url():
    ref = urls.parse(
        "https://raw.githubusercontent.com/kserve/kserve/v0.17.0/python/pmml.Dockerfile"
    )
    assert ref.org == "kserve"
    assert ref.path == "python/pmml.Dockerfile"


def test_parse_round_trip_urls():
    ref = urls.parse("https://github.com/k/k/blob/v1/p/Dockerfile")
    assert ref.blob_url() == "https://github.com/k/k/blob/v1/p/Dockerfile"
    assert ref.raw_url() == "https://raw.githubusercontent.com/k/k/v1/p/Dockerfile"


def test_with_ref_swaps_version():
    ref = urls.parse("https://github.com/k/k/blob/v1.0.0/p/Dockerfile")
    assert ref.with_ref("v2.0.0").ref == "v2.0.0"
    assert ref.with_ref("v2.0.0").blob_url() == (
        "https://github.com/k/k/blob/v2.0.0/p/Dockerfile"
    )


def test_parse_rejects_bad_host():
    with pytest.raises(UpstreamUrlError, match="not supported"):
        urls.parse("https://gitlab.com/k/k/blob/v1/Dockerfile")


def test_parse_rejects_bad_shape():
    with pytest.raises(UpstreamUrlError, match="not a recognised"):
        urls.parse("https://github.com/k/k/wat/v1/Dockerfile")


def test_parse_all_accepts_consistent_refs():
    refs = urls.parse_all(
        [
            "https://github.com/k/k/blob/v1/a.Dockerfile",
            "https://github.com/k/k/blob/v1/b.Dockerfile",
        ]
    )
    assert len(refs) == 2


def test_parse_all_rejects_mismatched_refs():
    with pytest.raises(UpstreamUrlError, match="different upstream refs"):
        urls.parse_all(
            [
                "https://github.com/k/k/blob/v1/a.Dockerfile",
                "https://github.com/k/k/blob/v2/b.Dockerfile",
            ]
        )
