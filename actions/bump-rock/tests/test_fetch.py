# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the upstream fetch helpers."""

from src import fetch
from src.urls import UpstreamRef


def test_retrying_session_retries_transient_errors_only():
    retry = fetch.retrying_session().get_adapter("https://example.com").max_retries
    assert retry.total == fetch.HTTP_RETRIES
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)
    # URL repair needs to see 404s immediately.
    assert 404 not in retry.status_forcelist
    assert retry.raise_on_status is False


def test_write_pair_to_disk_keeps_same_basename_pairs_apart(tmp_path):
    def pair(path, text):
        old = UpstreamRef(org="o", repo="r", ref="v1", path=path)
        return fetch.DockerfilePair(
            old_ref=old, new_ref=old.with_ref("v2"), old_text=f"{text} old", new_text=f"{text} new"
        )

    a = fetch.write_pair_to_disk(pair("builder/Dockerfile", "builder"), tmp_path)
    b = fetch.write_pair_to_disk(pair("runtime/Dockerfile", "runtime"), tmp_path)
    assert a["old"] != b["old"] and a["new"] != b["new"]
    assert a["old"].read_text() == "builder old"
    assert b["new"].read_text() == "runtime new"
