# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""Tests for the upstream fetch helpers."""
from src import fetch


def test_retrying_session_retries_transient_errors_only():
    retry = fetch.retrying_session().get_adapter("https://example.com").max_retries
    assert retry.total == fetch.HTTP_RETRIES
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)
    # URL repair needs to see 404s immediately.
    assert 404 not in retry.status_forcelist
    assert retry.raise_on_status is False
